#include "Common.h"
#include "MediaStream.h"

static HRESULT CreateVideoType(REFGUID subtype, const OutputConfig& config, UINT stride, UINT bitsPerPixel, IMFMediaType** type)
{
	winrt::com_ptr<IMFMediaType> mt;
	RETURN_IF_FAILED(MFCreateMediaType(mt.put()));
	RETURN_IF_FAILED(mt->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video));
	RETURN_IF_FAILED(mt->SetGUID(MF_MT_SUBTYPE, subtype));
	RETURN_IF_FAILED(MFSetAttributeSize(mt.get(), MF_MT_FRAME_SIZE, config.width, config.height));
	RETURN_IF_FAILED(mt->SetUINT32(MF_MT_DEFAULT_STRIDE, stride));
	RETURN_IF_FAILED(mt->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive));
	RETURN_IF_FAILED(mt->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT, TRUE));
	RETURN_IF_FAILED(MFSetAttributeRatio(mt.get(), MF_MT_FRAME_RATE, config.fps, 1));
	RETURN_IF_FAILED(mt->SetUINT32(MF_MT_AVG_BITRATE, config.width * config.height * bitsPerPixel * config.fps));
	RETURN_IF_FAILED(MFSetAttributeRatio(mt.get(), MF_MT_PIXEL_ASPECT_RATIO, 1, 1));
	*type = mt.detach();
	return S_OK;
}

HRESULT MediaStream::Initialize(IMFMediaSource* source, DWORD index, const OutputConfig& config)
{
	RETURN_HR_IF_NULL(E_POINTER, source);
	_source.copy_from(source);
	_index = index;
	_config = config;

	RETURN_IF_FAILED(SetGUID(MF_DEVICESTREAM_STREAM_CATEGORY, PINNAME_VIDEO_CAPTURE));
	RETURN_IF_FAILED(SetUINT32(MF_DEVICESTREAM_STREAM_ID, index));
	RETURN_IF_FAILED(SetUINT32(MF_DEVICESTREAM_FRAMESERVER_SHARED, 1));
	RETURN_IF_FAILED(SetUINT32(MF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES, MFFrameSourceTypes::MFFrameSourceTypes_Color));
	RETURN_IF_FAILED(MFCreateEventQueue(_queue.put()));

	// RGB32 is our native format (BGRA from the app); NV12 is what most consumers prefer.
	winrt::com_ptr<IMFMediaType> rgbType;
	winrt::com_ptr<IMFMediaType> nv12Type;
	RETURN_IF_FAILED(CreateVideoType(MFVideoFormat_RGB32, config, config.width * 4, 32, rgbType.put()));
	RETURN_IF_FAILED(CreateVideoType(MFVideoFormat_NV12, config, config.width, 12, nv12Type.put()));
	IMFMediaType* types[] = { rgbType.get(), nv12Type.get() };
	RETURN_IF_FAILED(MFCreateStreamDescriptor(_index, _countof(types), types, _descriptor.put()));

	winrt::com_ptr<IMFMediaTypeHandler> handler;
	RETURN_IF_FAILED(_descriptor->GetMediaTypeHandler(handler.put()));
	RETURN_IF_FAILED(handler->SetCurrentMediaType(rgbType.get()));

	SvcLog(L"MediaStream: initialized %ux%u @ %u fps", config.width, config.height, config.fps);
	return S_OK;
}

HRESULT MediaStream::Start(IMFMediaType* type)
{
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue || !_allocator);

	if (type)
	{
		_currentType.copy_from(type);
		RETURN_IF_FAILED(type->GetGUID(MF_MT_SUBTYPE, &_format));
	}
	RETURN_HR_IF(MF_E_INVALIDMEDIATYPE, !_currentType);

	_reader.EnsureOpen();
	_nextSampleTime = 0;
	if (!_timerResolution)
	{
		// 1 ms sleep granularity, otherwise pacing above ~60 fps is erratic
		_timerResolution = timeBeginPeriod(1) == TIMERR_NOERROR;
	}
	RETURN_IF_FAILED(_allocator->InitializeSampleAllocator(10, _currentType.get()));
	RETURN_IF_FAILED(_queue->QueueEventParamVar(MEStreamStarted, GUID_NULL, S_OK, nullptr));
	_state = MF_STREAM_STATE_RUNNING;
	SvcLog(L"MediaStream: started (%s)", _format == MFVideoFormat_NV12 ? L"NV12" : L"RGB32");
	return S_OK;
}

HRESULT MediaStream::Stop()
{
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue || !_allocator);

	RETURN_IF_FAILED(_allocator->UninitializeSampleAllocator());
	RETURN_IF_FAILED(_queue->QueueEventParamVar(MEStreamStopped, GUID_NULL, S_OK, nullptr));
	_state = MF_STREAM_STATE_STOPPED;
	ReleaseTimerResolution();
	SvcLog(L"MediaStream: stopped");
	return S_OK;
}

HRESULT MediaStream::SetAllocator(IUnknown* allocator)
{
	RETURN_HR_IF_NULL(E_POINTER, allocator);
	_allocator = nullptr;
	return allocator->QueryInterface(IID_PPV_ARGS(_allocator.put()));
}

void MediaStream::Shutdown()
{
	if (_queue)
	{
		_queue->Shutdown();
		_queue = nullptr;
	}

	ReleaseTimerResolution();
	_reader.Close();
	_descriptor = nullptr;
	_source = nullptr;
	_allocator = nullptr;
	_currentType = nullptr;
}

void MediaStream::ReleaseTimerResolution()
{
	if (_timerResolution)
	{
		timeEndPeriod(1);
		_timerResolution = false;
	}
}

HRESULT MediaStream::FillSample(IMFSample* sample)
{
	winrt::com_ptr<IMFMediaBuffer> buffer;
	RETURN_IF_FAILED(sample->GetBufferByIndex(0, buffer.put()));
	auto buffer2D = buffer.try_as<IMF2DBuffer2>();
	RETURN_HR_IF(E_NOINTERFACE, !buffer2D);

	BYTE* scanline;
	LONG pitch;
	BYTE* start;
	DWORD length;
	RETURN_IF_FAILED(buffer2D->Lock2DSize(MF2DBuffer_LockFlags_Write, &scanline, &pitch, &start, &length));

	auto width = _config.width;
	auto height = _config.height;
	if (_format == MFVideoFormat_NV12)
	{
		auto srcPitch = (LONG)width * 4;
		_bgra.resize((size_t)srcPitch * height);
		if (_reader.Read(_bgra.data(), srcPitch, width, height))
		{
			BgraToNv12(_bgra.data(), srcPitch, width, height, scanline, pitch);
		}
		else
		{
			FillBlackNv12(scanline, pitch, width, height);
		}
	}
	else if (!_reader.Read(scanline, pitch, width, height))
	{
		FillBlackBgra(scanline, pitch, width, height);
	}

	buffer2D->Unlock2D();
	return S_OK;
}

// IMFMediaEventGenerator
STDMETHODIMP MediaStream::BeginGetEvent(IMFAsyncCallback* pCallback, IUnknown* punkState)
{
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue);
	return _queue->BeginGetEvent(pCallback, punkState);
}

STDMETHODIMP MediaStream::EndGetEvent(IMFAsyncResult* pResult, IMFMediaEvent** ppEvent)
{
	RETURN_HR_IF_NULL(E_POINTER, ppEvent);
	*ppEvent = nullptr;
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue);
	return _queue->EndGetEvent(pResult, ppEvent);
}

STDMETHODIMP MediaStream::GetEvent(DWORD dwFlags, IMFMediaEvent** ppEvent)
{
	RETURN_HR_IF_NULL(E_POINTER, ppEvent);
	*ppEvent = nullptr;

	// GetEvent may block: don't hold the lock while waiting
	winrt::com_ptr<IMFMediaEventQueue> queue;
	{
		winrt::slim_lock_guard lock(_lock);
		RETURN_HR_IF(MF_E_SHUTDOWN, !_queue);
		queue = _queue;
	}
	return queue->GetEvent(dwFlags, ppEvent);
}

STDMETHODIMP MediaStream::QueueEvent(MediaEventType met, REFGUID guidExtendedType, HRESULT hrStatus, const PROPVARIANT* pvValue)
{
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue);
	return _queue->QueueEventParamVar(met, guidExtendedType, hrStatus, pvValue);
}

// IMFMediaStream
STDMETHODIMP MediaStream::GetMediaSource(IMFMediaSource** ppMediaSource)
{
	RETURN_HR_IF_NULL(E_POINTER, ppMediaSource);
	*ppMediaSource = nullptr;
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_source);
	_source.copy_to(ppMediaSource);
	return S_OK;
}

STDMETHODIMP MediaStream::GetStreamDescriptor(IMFStreamDescriptor** ppStreamDescriptor)
{
	RETURN_HR_IF_NULL(E_POINTER, ppStreamDescriptor);
	*ppStreamDescriptor = nullptr;
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_descriptor);
	_descriptor.copy_to(ppStreamDescriptor);
	return S_OK;
}

STDMETHODIMP MediaStream::RequestSample(IUnknown* pToken)
{
	// Pace delivery to the announced frame rate: consumers expect the source to block like a real camera.
	const MFTIME period = 10000000LL / _config.fps;
	MFTIME wait = 0;
	{
		winrt::slim_lock_guard lock(_lock);
		auto now = MFGetSystemTime();
		if (_nextSampleTime > now)
		{
			wait = _nextSampleTime - now;
		}
	}

	if (wait > 0)
	{
		Sleep((DWORD)(wait / 10000));
	}

	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_allocator || !_queue);

	auto now = MFGetSystemTime();
	_nextSampleTime = (_nextSampleTime > now - period ? _nextSampleTime : now) + period;

	winrt::com_ptr<IMFSample> sample;
	RETURN_IF_FAILED(_allocator->AllocateSample(sample.put()));
	RETURN_IF_FAILED(sample->SetSampleTime(now));
	RETURN_IF_FAILED(sample->SetSampleDuration(period));
	RETURN_IF_FAILED(FillSample(sample.get()));

	if (pToken)
	{
		RETURN_IF_FAILED(sample->SetUnknown(MFSampleExtension_Token, pToken));
	}
	return _queue->QueueEventParamUnk(MEMediaSample, GUID_NULL, S_OK, sample.get());
}

// IMFMediaStream2
STDMETHODIMP MediaStream::SetStreamState(MF_STREAM_STATE value)
{
	if (_state == value)
		return S_OK;

	switch (value)
	{
	case MF_STREAM_STATE_PAUSED:
		RETURN_HR_IF(MF_E_INVALID_STATE_TRANSITION, _state != MF_STREAM_STATE_RUNNING);
		_state = value;
		return S_OK;

	case MF_STREAM_STATE_RUNNING:
		return Start(nullptr);

	case MF_STREAM_STATE_STOPPED:
		return Stop();

	default:
		return MF_E_INVALID_STATE_TRANSITION;
	}
}

STDMETHODIMP MediaStream::GetStreamState(MF_STREAM_STATE* value)
{
	RETURN_HR_IF_NULL(E_POINTER, value);
	*value = _state;
	return S_OK;
}

// IKsControl: we expose no camera controls
STDMETHODIMP_(NTSTATUS) MediaStream::KsProperty(PKSPROPERTY property, ULONG, LPVOID, ULONG, ULONG* bytesReturned)
{
	RETURN_HR_IF_NULL(E_POINTER, property);
	RETURN_HR_IF_NULL(E_POINTER, bytesReturned);
	return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}

STDMETHODIMP_(NTSTATUS) MediaStream::KsMethod(PKSMETHOD method, ULONG, LPVOID, ULONG, ULONG* bytesReturned)
{
	RETURN_HR_IF_NULL(E_POINTER, method);
	RETURN_HR_IF_NULL(E_POINTER, bytesReturned);
	return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}

STDMETHODIMP_(NTSTATUS) MediaStream::KsEvent(PKSEVENT, ULONG, LPVOID, ULONG, ULONG* bytesReturned)
{
	RETURN_HR_IF_NULL(E_POINTER, bytesReturned);
	return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}

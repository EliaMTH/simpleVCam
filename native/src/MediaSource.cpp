#include "Common.h"
#include "MediaStream.h"
#include "MediaSource.h"

HRESULT MediaSource::Initialize(IMFAttributes* attributes)
{
	if (attributes)
	{
		RETURN_IF_FAILED(attributes->CopyAllItems(this));
	}

	// sensor profiles: some consumers (e.g. the Windows Camera app) look for them
	winrt::com_ptr<IMFSensorProfileCollection> collection;
	RETURN_IF_FAILED(MFCreateSensorProfileCollection(collection.put()));

	winrt::com_ptr<IMFSensorProfile> profile;
	RETURN_IF_FAILED(MFCreateSensorProfile(KSCAMERAPROFILE_Legacy, 0, nullptr, profile.put()));
	RETURN_IF_FAILED(profile->AddProfileFilter(0, L"((RES==;FRT<=120,1;SUT==))"));
	RETURN_IF_FAILED(collection->AddProfile(profile.get()));

	profile = nullptr;
	RETURN_IF_FAILED(MFCreateSensorProfile(KSCAMERAPROFILE_HighFrameRate, 0, nullptr, profile.put()));
	RETURN_IF_FAILED(profile->AddProfileFilter(0, L"((RES==;FRT>=60,1;SUT==))"));
	RETURN_IF_FAILED(collection->AddProfile(profile.get()));
	RETURN_IF_FAILED(SetUnknown(MF_DEVICEMFT_SENSORPROFILE_COLLECTION, collection.get()));

	auto config = OutputConfig::Load();
	_stream = winrt::make_self<MediaStream>();
	RETURN_IF_FAILED(_stream->Initialize(this, 0, config));

	winrt::com_ptr<IMFStreamDescriptor> streamDescriptor;
	RETURN_IF_FAILED(_stream->GetStreamDescriptor(streamDescriptor.put()));
	IMFStreamDescriptor* descriptors[] = { streamDescriptor.get() };
	RETURN_IF_FAILED(MFCreatePresentationDescriptor(_countof(descriptors), descriptors, _descriptor.put()));
	RETURN_IF_FAILED(MFCreateEventQueue(_queue.put()));
	return S_OK;
}

// IMFMediaEventGenerator
STDMETHODIMP MediaSource::BeginGetEvent(IMFAsyncCallback* pCallback, IUnknown* punkState)
{
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue);
	return _queue->BeginGetEvent(pCallback, punkState);
}

STDMETHODIMP MediaSource::EndGetEvent(IMFAsyncResult* pResult, IMFMediaEvent** ppEvent)
{
	RETURN_HR_IF_NULL(E_POINTER, ppEvent);
	*ppEvent = nullptr;
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue);
	return _queue->EndGetEvent(pResult, ppEvent);
}

STDMETHODIMP MediaSource::GetEvent(DWORD dwFlags, IMFMediaEvent** ppEvent)
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

STDMETHODIMP MediaSource::QueueEvent(MediaEventType met, REFGUID guidExtendedType, HRESULT hrStatus, const PROPVARIANT* pvValue)
{
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue);
	return _queue->QueueEventParamVar(met, guidExtendedType, hrStatus, pvValue);
}

// IMFMediaSource
STDMETHODIMP MediaSource::CreatePresentationDescriptor(IMFPresentationDescriptor** ppPresentationDescriptor)
{
	RETURN_HR_IF_NULL(E_POINTER, ppPresentationDescriptor);
	*ppPresentationDescriptor = nullptr;
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_descriptor);
	return _descriptor->Clone(ppPresentationDescriptor);
}

STDMETHODIMP MediaSource::GetCharacteristics(DWORD* pdwCharacteristics)
{
	RETURN_HR_IF_NULL(E_POINTER, pdwCharacteristics);
	*pdwCharacteristics = MFMEDIASOURCE_IS_LIVE;
	return S_OK;
}

STDMETHODIMP MediaSource::Pause()
{
	return MF_E_INVALID_STATE_TRANSITION;
}

STDMETHODIMP MediaSource::Shutdown()
{
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue);

	_queue->Shutdown();
	_queue = nullptr;
	if (_stream)
	{
		_stream->Shutdown(); // breaks the stream -> source reference cycle
		_stream = nullptr;
	}
	_descriptor = nullptr;
	SvcLog(L"MediaSource: shutdown");
	return S_OK;
}

STDMETHODIMP MediaSource::Start(IMFPresentationDescriptor* pPresentationDescriptor, const GUID* pguidTimeFormat, const PROPVARIANT* pvarStartPosition)
{
	RETURN_HR_IF_NULL(E_POINTER, pPresentationDescriptor);
	RETURN_HR_IF_NULL(E_POINTER, pvarStartPosition);
	RETURN_HR_IF(E_INVALIDARG, pguidTimeFormat && *pguidTimeFormat != GUID_NULL);
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue || !_descriptor || !_stream);

	DWORD count;
	RETURN_IF_FAILED(pPresentationDescriptor->GetStreamDescriptorCount(&count));
	RETURN_HR_IF(E_INVALIDARG, count != 1);

	PROPVARIANT time;
	RETURN_IF_FAILED(InitPropVariantFromInt64(MFGetSystemTime(), &time));

	winrt::com_ptr<IMFStreamDescriptor> desc;
	BOOL selected = FALSE;
	RETURN_IF_FAILED(pPresentationDescriptor->GetStreamDescriptorByIndex(0, &selected, desc.put()));

	MF_STREAM_STATE state;
	RETURN_IF_FAILED(_stream->GetStreamState(&state));
	BOOL running = state != MF_STREAM_STATE_STOPPED;
	if (selected != running)
	{
		if (selected)
		{
			RETURN_IF_FAILED(_descriptor->SelectStream(0));

			winrt::com_ptr<IUnknown> unk;
			unk.copy_from(static_cast<IMFMediaStream2*>(_stream.get()));
			RETURN_IF_FAILED(_queue->QueueEventParamUnk(MENewStream, GUID_NULL, S_OK, unk.get()));

			winrt::com_ptr<IMFMediaTypeHandler> handler;
			winrt::com_ptr<IMFMediaType> type;
			RETURN_IF_FAILED(desc->GetMediaTypeHandler(handler.put()));
			RETURN_IF_FAILED(handler->GetCurrentMediaType(type.put()));
			RETURN_IF_FAILED(_stream->Start(type.get()));
		}
		else
		{
			RETURN_IF_FAILED(_descriptor->DeselectStream(0));
			RETURN_IF_FAILED(_stream->Stop());
		}
	}

	return _queue->QueueEventParamVar(MESourceStarted, GUID_NULL, S_OK, &time);
}

STDMETHODIMP MediaSource::Stop()
{
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(MF_E_SHUTDOWN, !_queue || !_descriptor || !_stream);

	PROPVARIANT time;
	RETURN_IF_FAILED(InitPropVariantFromInt64(MFGetSystemTime(), &time));

	RETURN_IF_FAILED(_stream->Stop());
	RETURN_IF_FAILED(_descriptor->DeselectStream(0));
	return _queue->QueueEventParamVar(MESourceStopped, GUID_NULL, S_OK, &time);
}

// IMFMediaSourceEx
STDMETHODIMP MediaSource::GetSourceAttributes(IMFAttributes** ppAttributes)
{
	RETURN_HR_IF_NULL(E_POINTER, ppAttributes);
	return QueryInterface(IID_PPV_ARGS(ppAttributes));
}

STDMETHODIMP MediaSource::GetStreamAttributes(DWORD dwStreamIdentifier, IMFAttributes** ppAttributes)
{
	RETURN_HR_IF_NULL(E_POINTER, ppAttributes);
	*ppAttributes = nullptr;
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(E_FAIL, dwStreamIdentifier != 0 || !_stream);
	return _stream->QueryInterface(IID_PPV_ARGS(ppAttributes));
}

STDMETHODIMP MediaSource::SetD3DManager(IUnknown* pManager)
{
	// CPU only: frames come from system memory, so we ignore the D3D manager
	RETURN_HR_IF_NULL(E_POINTER, pManager);
	return S_OK;
}

// IMFGetService
STDMETHODIMP MediaSource::GetService(REFGUID, REFIID, LPVOID* ppvObject)
{
	if (ppvObject)
	{
		*ppvObject = nullptr;
	}
	return MF_E_UNSUPPORTED_SERVICE;
}

// IMFSampleAllocatorControl
STDMETHODIMP MediaSource::SetDefaultAllocator(DWORD dwOutputStreamID, IUnknown* pAllocator)
{
	RETURN_HR_IF_NULL(E_POINTER, pAllocator);
	winrt::slim_lock_guard lock(_lock);
	RETURN_HR_IF(E_FAIL, dwOutputStreamID != 0 || !_stream);
	return _stream->SetAllocator(pAllocator);
}

STDMETHODIMP MediaSource::GetAllocatorUsage(DWORD dwOutputStreamID, DWORD* pdwInputStreamID, MFSampleAllocatorUsage* peUsage)
{
	RETURN_HR_IF_NULL(E_POINTER, peUsage);
	RETURN_HR_IF_NULL(E_POINTER, pdwInputStreamID);
	RETURN_HR_IF(E_FAIL, dwOutputStreamID != 0);
	*pdwInputStreamID = dwOutputStreamID;
	*peUsage = MFSampleAllocatorUsage_UsesProvidedAllocator;
	return S_OK;
}

// IKsControl: we expose no camera controls
STDMETHODIMP_(NTSTATUS) MediaSource::KsProperty(PKSPROPERTY property, ULONG, LPVOID, ULONG, ULONG* bytesReturned)
{
	RETURN_HR_IF_NULL(E_POINTER, property);
	RETURN_HR_IF_NULL(E_POINTER, bytesReturned);
	return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}

STDMETHODIMP_(NTSTATUS) MediaSource::KsMethod(PKSMETHOD method, ULONG, LPVOID, ULONG, ULONG* bytesReturned)
{
	RETURN_HR_IF_NULL(E_POINTER, method);
	RETURN_HR_IF_NULL(E_POINTER, bytesReturned);
	return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}

STDMETHODIMP_(NTSTATUS) MediaSource::KsEvent(PKSEVENT, ULONG, LPVOID, ULONG, ULONG* bytesReturned)
{
	RETURN_HR_IF_NULL(E_POINTER, bytesReturned);
	return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
}

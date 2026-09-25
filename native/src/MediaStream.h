#pragma once

#include "BaseAttributes.h"
#include "SharedFrame.h"

struct MediaStream : winrt::implements<MediaStream, CBaseAttributes<IMFAttributes>, IMFMediaStream2, IKsControl>
{
public:
	// IMFMediaEventGenerator
	STDMETHOD(BeginGetEvent)(IMFAsyncCallback* pCallback, IUnknown* punkState);
	STDMETHOD(EndGetEvent)(IMFAsyncResult* pResult, IMFMediaEvent** ppEvent);
	STDMETHOD(GetEvent)(DWORD dwFlags, IMFMediaEvent** ppEvent);
	STDMETHOD(QueueEvent)(MediaEventType met, REFGUID guidExtendedType, HRESULT hrStatus, const PROPVARIANT* pvValue);

	// IMFMediaStream
	STDMETHOD(GetMediaSource)(IMFMediaSource** ppMediaSource);
	STDMETHOD(GetStreamDescriptor)(IMFStreamDescriptor** ppStreamDescriptor);
	STDMETHOD(RequestSample)(IUnknown* pToken);

	// IMFMediaStream2
	STDMETHOD(SetStreamState)(MF_STREAM_STATE value);
	STDMETHOD(GetStreamState)(MF_STREAM_STATE* value);

	// IKsControl
	STDMETHOD_(NTSTATUS, KsProperty)(PKSPROPERTY Property, ULONG PropertyLength, LPVOID PropertyData, ULONG DataLength, ULONG* BytesReturned);
	STDMETHOD_(NTSTATUS, KsMethod)(PKSMETHOD Method, ULONG MethodLength, LPVOID MethodData, ULONG DataLength, ULONG* BytesReturned);
	STDMETHOD_(NTSTATUS, KsEvent)(PKSEVENT Event, ULONG EventLength, LPVOID EventData, ULONG DataLength, ULONG* BytesReturned);

public:
	HRESULT Initialize(IMFMediaSource* source, DWORD index, const OutputConfig& config);
	HRESULT SetAllocator(IUnknown* allocator);
	HRESULT Start(IMFMediaType* type);
	HRESULT Stop();
	void Shutdown();

private:
	HRESULT FillSample(IMFSample* sample);
	void ReleaseTimerResolution();

	winrt::slim_mutex _lock;
	MF_STREAM_STATE _state = MF_STREAM_STATE_STOPPED;
	GUID _format = GUID_NULL;
	OutputConfig _config;
	FrameReader _reader;
	std::vector<BYTE> _bgra; // scratch frame for the NV12 conversion
	MFTIME _nextSampleTime = 0;
	bool _timerResolution = false; // timeBeginPeriod(1) active
	DWORD _index = 0;
	winrt::com_ptr<IMFMediaType> _currentType;
	winrt::com_ptr<IMFStreamDescriptor> _descriptor;
	winrt::com_ptr<IMFMediaEventQueue> _queue;
	winrt::com_ptr<IMFMediaSource> _source;
	winrt::com_ptr<IMFVideoSampleAllocatorEx> _allocator;
};

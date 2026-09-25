#pragma once

#include "BaseAttributes.h"

struct MediaSource;

// Object created by the class factory; the Frame Server activates the media source through it.
struct Activator : winrt::implements<Activator, CBaseAttributes<IMFActivate>>
{
public:
	// IMFActivate
	STDMETHOD(ActivateObject)(REFIID riid, void** ppv);
	STDMETHOD(ShutdownObject)();
	STDMETHOD(DetachObject)();

public:
	HRESULT Initialize();

private:
	winrt::com_ptr<MediaSource> _source;
};

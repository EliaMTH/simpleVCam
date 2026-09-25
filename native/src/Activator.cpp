#include "Common.h"
#include "MediaStream.h"
#include "MediaSource.h"
#include "Activator.h"

HRESULT Activator::Initialize()
{
	_source = winrt::make_self<MediaSource>();
	RETURN_IF_FAILED(SetUINT32(MF_VIRTUALCAMERA_PROVIDE_ASSOCIATED_CAMERA_SOURCES, 1));
	RETURN_IF_FAILED(SetGUID(MFT_TRANSFORM_CLSID_Attribute, CLSID_SimpleVCam));
	RETURN_IF_FAILED(_source->Initialize(this));
	return S_OK;
}

STDMETHODIMP Activator::ActivateObject(REFIID riid, void** ppv)
{
	RETURN_HR_IF_NULL(E_POINTER, ppv);
	*ppv = nullptr;
	RETURN_HR_IF(MF_E_SHUTDOWN, !_source);
	return _source->QueryInterface(riid, ppv);
}

STDMETHODIMP Activator::ShutdownObject()
{
	return S_OK;
}

STDMETHODIMP Activator::DetachObject()
{
	_source = nullptr;
	return S_OK;
}

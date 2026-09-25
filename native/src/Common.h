// simpleVCam native virtual camera.
// Media source structure adapted from VCamSample by Simon Mourier (MIT, see LICENSE-VCamSample.txt).
#pragma once

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <strsafe.h>
#include <sddl.h>
#include <initguid.h>
#include <propvarutil.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfvirtualcamera.h>
#include <mferror.h>
#include <mfcaptureengine.h>
#include <ks.h>
#include <ksproxy.h>
#include <ksmedia.h>
#include <timeapi.h>

#include <string>
#include <vector>
#include <mutex>

#include <winrt/base.h>

// {5FF39D7F-AB7D-467D-8A8F-9D45DFE61F9C}
extern const GUID CLSID_SimpleVCam;
#define SVC_CLSID_STRING L"{5FF39D7F-AB7D-467D-8A8F-9D45DFE61F9C}"
#define SVC_FRIENDLY_NAME L"simpleVCam"

// Shared with simplevcam/vcam.py: keep in sync.
#define SVC_SECTION_NAME L"Global\\simpleVCam_Frame"
#define SVC_CONFIG_FILE L"%ProgramData%\\simpleVCam\\output.cfg"
#define SVC_LOG_FILE L"%ProgramData%\\simpleVCam\\vcam.log"

void SvcLog(PCWSTR format, ...);

#define RETURN_IF_FAILED(expr)                                                                  \
	do                                                                                          \
	{                                                                                           \
		const HRESULT hr__ = (expr);                                                            \
		if (FAILED(hr__))                                                                       \
		{                                                                                       \
			SvcLog(L"%hs(%d): 0x%08X %hs", __FILE__, __LINE__, (unsigned)hr__, #expr);          \
			return hr__;                                                                        \
		}                                                                                       \
	} while (0)

#define RETURN_HR_IF(hr, cond)                                                                  \
	do                                                                                          \
	{                                                                                           \
		if (cond)                                                                               \
			return (hr);                                                                        \
	} while (0)

#define RETURN_HR_IF_NULL(hr, ptr) RETURN_HR_IF(hr, !(ptr))

// winrt::implements only answers QueryInterface for the exact IIDs listed;
// these specializations make it answer for the base interfaces too.
namespace winrt
{
	template<> inline bool is_guid_of<IMFMediaSourceEx>(guid const& id) noexcept
	{
		return is_guid_of<IMFMediaSourceEx, IMFMediaSource, IMFMediaEventGenerator>(id);
	}

	template<> inline bool is_guid_of<IMFMediaStream2>(guid const& id) noexcept
	{
		return is_guid_of<IMFMediaStream2, IMFMediaStream, IMFMediaEventGenerator>(id);
	}

	template<> inline bool is_guid_of<IMFActivate>(guid const& id) noexcept
	{
		return is_guid_of<IMFActivate, IMFAttributes>(id);
	}
}

// Output format announced by the camera, written by the app to SVC_CONFIG_FILE as "width height fps".
struct OutputConfig
{
	UINT width = 1280;
	UINT height = 720;
	UINT fps = 60;

	static OutputConfig Load();
};

std::wstring ExpandPath(PCWSTR path);

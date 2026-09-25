// Functions called by the simpleVCam app (through ctypes) to create and remove the virtual camera.
// The camera object lives on a dedicated MTA thread, so callers can be on any thread/apartment.
#include "Common.h"

namespace
{
	struct CameraThread
	{
		HANDLE thread = nullptr;
		HANDLE stopEvent = nullptr;
		HANDLE startedEvent = nullptr;
		HRESULT startResult = E_PENDING;
		std::wstring name;
	};

	std::mutex g_lock;
	CameraThread* g_camera = nullptr;

	DWORD WINAPI CameraThreadProc(LPVOID param)
	{
		auto ctx = (CameraThread*)param;
		auto hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
		auto comInitialized = SUCCEEDED(hr);
		if (SUCCEEDED(hr))
		{
			hr = MFStartup(MF_VERSION);
		}

		winrt::com_ptr<IMFVirtualCamera> camera;
		if (SUCCEEDED(hr))
		{
			hr = MFCreateVirtualCamera(
				MFVirtualCameraType_SoftwareCameraSource,
				MFVirtualCameraLifetime_Session,   // removed automatically when this process exits
				MFVirtualCameraAccess_CurrentUser, // no admin rights needed
				ctx->name.c_str(),
				SVC_CLSID_STRING,
				nullptr,
				0,
				camera.put());
			if (SUCCEEDED(hr))
			{
				hr = camera->Start(nullptr);
			}
		}

		ctx->startResult = hr;
		SvcLog(L"SvcStart '%s': 0x%08X", ctx->name.c_str(), (unsigned)hr);
		SetEvent(ctx->startedEvent);

		if (SUCCEEDED(hr))
		{
			WaitForSingleObject(ctx->stopEvent, INFINITE);
			// don't call Shutdown before Remove: it would shut the media source down twice
			hr = camera->Remove();
			SvcLog(L"SvcStop: 0x%08X", (unsigned)hr);
		}

		camera = nullptr;
		MFShutdown();
		if (comInitialized)
		{
			CoUninitialize();
		}
		return 0;
	}

	void DestroyCamera(CameraThread* ctx)
	{
		if (ctx->thread)
		{
			SetEvent(ctx->stopEvent);
			WaitForSingleObject(ctx->thread, 10000);
			CloseHandle(ctx->thread);
		}
		CloseHandle(ctx->stopEvent);
		CloseHandle(ctx->startedEvent);
		delete ctx;
	}
}

// Creates and starts the virtual camera. Returns an HRESULT.
extern "C" HRESULT SvcStart(LPCWSTR friendlyName)
{
	std::lock_guard guard(g_lock);
	if (g_camera)
		return S_FALSE; // already running

	auto ctx = new CameraThread();
	ctx->name = friendlyName && *friendlyName ? friendlyName : SVC_FRIENDLY_NAME;
	ctx->stopEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
	ctx->startedEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
	ctx->thread = CreateThread(nullptr, 0, CameraThreadProc, ctx, 0, nullptr);
	if (!ctx->thread)
	{
		auto hr = HRESULT_FROM_WIN32(GetLastError());
		DestroyCamera(ctx);
		return hr;
	}

	WaitForSingleObject(ctx->startedEvent, INFINITE);
	auto hr = ctx->startResult;
	if (FAILED(hr))
	{
		DestroyCamera(ctx);
		return hr;
	}

	g_camera = ctx;
	return S_OK;
}

// Removes the virtual camera, if running.
extern "C" HRESULT SvcStop()
{
	std::lock_guard guard(g_lock);
	if (!g_camera)
		return S_FALSE;

	DestroyCamera(g_camera);
	g_camera = nullptr;
	return S_OK;
}

extern "C" BOOL SvcIsRunning()
{
	std::lock_guard guard(g_lock);
	return g_camera != nullptr;
}

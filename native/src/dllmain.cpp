#include "Common.h"
#include "MediaStream.h"
#include "MediaSource.h"
#include "Activator.h"

const GUID CLSID_SimpleVCam = { 0x5ff39d7f, 0xab7d, 0x467d, { 0x8a, 0x8f, 0x9d, 0x45, 0xdf, 0xe6, 0x1f, 0x9c } };
HMODULE g_module = nullptr;

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID)
{
	if (reason == DLL_PROCESS_ATTACH)
	{
		g_module = module;
		DisableThreadLibraryCalls(module);
	}
	return TRUE;
}

struct ClassFactory : winrt::implements<ClassFactory, IClassFactory>
{
	STDMETHODIMP CreateInstance(IUnknown* outer, GUID const& riid, void** result) noexcept final
	{
		RETURN_HR_IF_NULL(E_POINTER, result);
		*result = nullptr;
		RETURN_HR_IF(CLASS_E_NOAGGREGATION, outer);

		try
		{
			auto activator = winrt::make_self<Activator>();
			RETURN_IF_FAILED(activator->Initialize());
			return activator->QueryInterface(riid, result);
		}
		catch (...)
		{
			auto hr = winrt::to_hresult();
			SvcLog(L"ClassFactory::CreateInstance failed 0x%08X", (unsigned)hr);
			return hr;
		}
	}

	STDMETHODIMP LockServer(BOOL) noexcept final
	{
		return S_OK;
	}
};

STDAPI DllCanUnloadNow()
{
	if (winrt::get_module_lock())
		return S_FALSE;

	winrt::clear_factory_cache();
	return S_OK;
}

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, LPVOID* ppv)
{
	RETURN_HR_IF_NULL(E_POINTER, ppv);
	*ppv = nullptr;
	RETURN_HR_IF(CLASS_E_CLASSNOTAVAILABLE, rclsid != CLSID_SimpleVCam);
	return winrt::make<ClassFactory>().as<IUnknown>()->QueryInterface(riid, ppv);
}

static std::wstring ModulePath()
{
	wchar_t path[MAX_PATH * 2];
	auto len = GetModuleFileNameW(g_module, path, _countof(path));
	return std::wstring(path, len);
}

static LSTATUS SetStringValue(HKEY key, PCWSTR name, const std::wstring& value)
{
	return RegSetValueExW(key, name, 0, REG_SZ, (const BYTE*)value.c_str(), (DWORD)((value.size() + 1) * sizeof(wchar_t)));
}

// A virtual camera media source must be registered in HKLM: the Frame Server services load it.
STDAPI DllRegisterServer()
{
	std::wstring clsidKey = L"Software\\Classes\\CLSID\\" SVC_CLSID_STRING;
	HKEY key = nullptr;
	auto status = RegCreateKeyExW(HKEY_LOCAL_MACHINE, clsidKey.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &key, nullptr);
	if (status != ERROR_SUCCESS)
		return HRESULT_FROM_WIN32(status);

	status = SetStringValue(key, nullptr, SVC_FRIENDLY_NAME L" media source");
	RegCloseKey(key);
	if (status != ERROR_SUCCESS)
		return HRESULT_FROM_WIN32(status);

	status = RegCreateKeyExW(HKEY_LOCAL_MACHINE, (clsidKey + L"\\InprocServer32").c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &key, nullptr);
	if (status != ERROR_SUCCESS)
		return HRESULT_FROM_WIN32(status);

	status = SetStringValue(key, nullptr, ModulePath());
	if (status == ERROR_SUCCESS)
	{
		status = SetStringValue(key, L"ThreadingModel", L"Both");
	}
	RegCloseKey(key);
	return HRESULT_FROM_WIN32(status);
}

STDAPI DllUnregisterServer()
{
	auto status = RegDeleteTreeW(HKEY_LOCAL_MACHINE, L"Software\\Classes\\CLSID\\" SVC_CLSID_STRING);
	if (status == ERROR_FILE_NOT_FOUND)
		return S_OK;

	return HRESULT_FROM_WIN32(status);
}

#include "Common.h"

std::wstring ExpandPath(PCWSTR path)
{
	wchar_t buffer[MAX_PATH * 2];
	auto len = ExpandEnvironmentStringsW(path, buffer, _countof(buffer));
	if (!len || len > _countof(buffer))
		return path;

	return buffer;
}

// Appends a line to %ProgramData%\simpleVCam\vcam.log (and the debugger output).
// Used only for rare events and errors, never per frame.
void SvcLog(PCWSTR format, ...)
{
	wchar_t message[1024];
	va_list args;
	va_start(args, format);
	StringCchVPrintfW(message, _countof(message), format, args);
	va_end(args);

	SYSTEMTIME st;
	GetLocalTime(&st);
	wchar_t line[1200];
	StringCchPrintfW(line, _countof(line), L"%04u-%02u-%02u %02u:%02u:%02u.%03u [%u] %s\r\n",
		st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond, st.wMilliseconds, GetCurrentProcessId(), message);
	OutputDebugStringW(line);

	static std::mutex lock;
	std::lock_guard guard(lock);
	static const auto path = ExpandPath(SVC_LOG_FILE);

	auto file = CreateFileW(path.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (file == INVALID_HANDLE_VALUE)
		return;

	LARGE_INTEGER size{};
	if (GetFileSizeEx(file, &size) && size.QuadPart > 1024 * 1024)
	{
		// keep the log small: start over
		CloseHandle(file);
		file = CreateFileW(path.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
		if (file == INVALID_HANDLE_VALUE)
			return;
	}

	auto utf8Len = WideCharToMultiByte(CP_UTF8, 0, line, -1, nullptr, 0, nullptr, nullptr);
	if (utf8Len > 1)
	{
		std::string utf8(utf8Len, '\0');
		WideCharToMultiByte(CP_UTF8, 0, line, -1, utf8.data(), utf8Len, nullptr, nullptr);
		DWORD written;
		WriteFile(file, utf8.data(), (DWORD)(utf8Len - 1), &written, nullptr);
	}
	CloseHandle(file);
}

OutputConfig OutputConfig::Load()
{
	OutputConfig config;
	auto path = ExpandPath(SVC_CONFIG_FILE);
	auto file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (file == INVALID_HANDLE_VALUE)
	{
		SvcLog(L"OutputConfig: '%s' not found, using defaults", path.c_str());
		return config;
	}

	char text[128]{};
	DWORD read = 0;
	ReadFile(file, text, sizeof(text) - 1, &read, nullptr);
	CloseHandle(file);

	UINT width = 0, height = 0, fps = 0;
	if (sscanf_s(text, "%u %u %u", &width, &height, &fps) == 3 &&
		width >= 160 && width <= 3840 && height >= 120 && height <= 2160 && fps >= 1 && fps <= 120)
	{
		// NV12 needs even dimensions
		config.width = width & ~1u;
		config.height = height & ~1u;
		config.fps = fps;
	}
	else
	{
		SvcLog(L"OutputConfig: invalid content, using defaults");
	}
	return config;
}

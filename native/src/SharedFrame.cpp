#include "Common.h"
#include "SharedFrame.h"

bool FrameReader::EnsureOpen()
{
	if (_view)
		return true;

	// SYSTEM, LocalService and Administrators: full access; authenticated users (the app): read/write.
	PSECURITY_DESCRIPTOR sd = nullptr;
	if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(L"D:P(A;;GA;;;SY)(A;;GA;;;LS)(A;;GA;;;BA)(A;;GRGW;;;AU)", SDDL_REVISION_1, &sd, nullptr))
	{
		SvcLog(L"FrameReader: security descriptor error %u", GetLastError());
		return false;
	}

	SECURITY_ATTRIBUTES sa{ sizeof(sa), sd, FALSE };
	_section = CreateFileMappingW(INVALID_HANDLE_VALUE, &sa, PAGE_READWRITE, (DWORD)(SVC_SECTION_SIZE >> 32), (DWORD)(SVC_SECTION_SIZE & 0xFFFFFFFF), SVC_SECTION_NAME);
	auto error = GetLastError();
	LocalFree(sd);
	if (!_section)
	{
		SvcLog(L"FrameReader: CreateFileMapping error %u", error);
		return false;
	}

	_view = (BYTE*)MapViewOfFile(_section, FILE_MAP_READ, 0, 0, SVC_SECTION_SIZE);
	if (!_view)
	{
		SvcLog(L"FrameReader: MapViewOfFile error %u", GetLastError());
		CloseHandle(_section);
		_section = nullptr;
		return false;
	}

	SvcLog(L"FrameReader: section ready (%s)", error == ERROR_ALREADY_EXISTS ? L"existing" : L"created");
	return true;
}

void FrameReader::Close()
{
	if (_view)
	{
		UnmapViewOfFile(_view);
		_view = nullptr;
	}

	if (_section)
	{
		CloseHandle(_section);
		_section = nullptr;
	}
}

bool FrameReader::Read(BYTE* dst, LONG pitch, UINT width, UINT height)
{
	if (!EnsureOpen())
		return false;

	auto header = (volatile SharedHeader*)_view;
	auto pixels = _view + sizeof(SharedHeader);
	for (int attempt = 0; attempt < 5; attempt++)
	{
		auto seq = header->seq;
		if (seq & 1)
		{
			// the app is writing right now
			Sleep(1);
			continue;
		}

		MemoryBarrier();
		if (header->magic != SVC_MAGIC || header->version != SVC_VERSION || header->width != width || header->height != height)
			return false;

		auto stride = header->stride;
		if (stride < width * 4 || (SIZE_T)stride * height > SVC_SECTION_SIZE - sizeof(SharedHeader))
			return false;

		FILETIME ft;
		GetSystemTimePreciseAsFileTime(&ft);
		auto now = (LONG64)(((ULONG64)ft.dwHighDateTime << 32) | ft.dwLowDateTime);
		if (now - header->timestamp > SVC_STALE_100NS)
			return false;

		for (UINT y = 0; y < height; y++)
		{
			CopyMemory(dst + (LONG_PTR)y * pitch, pixels + (SIZE_T)y * stride, (SIZE_T)width * 4);
		}

		MemoryBarrier();
		if (header->seq == seq)
			return true;
	}

	// kept being overwritten: better a torn frame than a black one
	return true;
}

static inline BYTE ClampByte(int v)
{
	return (BYTE)(v < 0 ? 0 : (v > 255 ? 255 : v));
}

// BT.601 limited range, the usual default for webcams.
void BgraToNv12(const BYTE* src, LONG srcPitch, UINT width, UINT height, BYTE* dst, LONG pitch)
{
	auto uvPlane = dst + (LONG_PTR)pitch * height;
	for (UINT y = 0; y < height; y += 2)
	{
		auto row0 = src + (LONG_PTR)y * srcPitch;
		auto row1 = row0 + srcPitch;
		auto y0 = dst + (LONG_PTR)y * pitch;
		auto y1 = y0 + pitch;
		auto uv = uvPlane + (LONG_PTR)(y / 2) * pitch;
		for (UINT x = 0; x < width; x += 2)
		{
			int sumB = 0, sumG = 0, sumR = 0;
			const BYTE* px[4] = { row0 + x * 4, row0 + x * 4 + 4, row1 + x * 4, row1 + x * 4 + 4 };
			BYTE* py[4] = { y0 + x, y0 + x + 1, y1 + x, y1 + x + 1 };
			for (int i = 0; i < 4; i++)
			{
				int b = px[i][0], g = px[i][1], r = px[i][2];
				*py[i] = (BYTE)(((66 * r + 129 * g + 25 * b + 128) >> 8) + 16);
				sumB += b;
				sumG += g;
				sumR += r;
			}

			int b = sumB / 4, g = sumG / 4, r = sumR / 4;
			uv[x] = ClampByte(((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128);
			uv[x + 1] = ClampByte(((112 * r - 94 * g - 18 * b + 128) >> 8) + 128);
		}
	}
}

void FillBlackNv12(BYTE* dst, LONG pitch, UINT width, UINT height)
{
	for (UINT y = 0; y < height; y++)
	{
		FillMemory(dst + (LONG_PTR)y * pitch, width, 16);
	}

	auto uvPlane = dst + (LONG_PTR)pitch * height;
	for (UINT y = 0; y < height / 2; y++)
	{
		FillMemory(uvPlane + (LONG_PTR)y * pitch, width, 128);
	}
}

void FillBlackBgra(BYTE* dst, LONG pitch, UINT width, UINT height)
{
	for (UINT y = 0; y < height; y++)
	{
		auto row = (UINT32*)(dst + (LONG_PTR)y * pitch);
		for (UINT x = 0; x < width; x++)
		{
			row[x] = 0xFF000000;
		}
	}
}

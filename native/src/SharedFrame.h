#pragma once

// Layout of the shared section SVC_SECTION_NAME. Must match simplevcam/vcam.py.
//
// The section is created by this DLL inside the Frame Server service (session 0), because
// only privileged accounts can create objects in the Global namespace. The app opens it
// and writes frames using `seq` as a seqlock: odd while writing, even when a frame is complete.
#pragma pack(push, 1)
struct SharedHeader
{
	UINT32 magic;       // SVC_MAGIC once the app has written a frame
	UINT32 version;     // SVC_VERSION
	UINT32 width;
	UINT32 height;
	UINT32 stride;      // bytes per row of the BGRA pixels
	UINT32 fps;
	volatile LONG64 seq;
	LONG64 timestamp;   // FILETIME (100 ns since 1601, UTC) of the last written frame
	BYTE reserved[24];
};
#pragma pack(pop)
static_assert(sizeof(SharedHeader) == 64, "header must be 64 bytes");

constexpr UINT32 SVC_MAGIC = 0x4D435653; // 'SVCM'
constexpr UINT32 SVC_VERSION = 1;
constexpr UINT SVC_MAX_WIDTH = 3840;
constexpr UINT SVC_MAX_HEIGHT = 2160;
constexpr SIZE_T SVC_SECTION_SIZE = sizeof(SharedHeader) + (SIZE_T)SVC_MAX_WIDTH * SVC_MAX_HEIGHT * 4;

// Frames older than this are considered stale (app stopped sending) and replaced with black.
constexpr LONG64 SVC_STALE_100NS = 10000000; // 1 s

class FrameReader
{
public:
	~FrameReader() { Close(); }

	// Creates (or opens) the shared section. Safe to call repeatedly.
	bool EnsureOpen();
	void Close();

	// Copies the latest frame (BGRA, width x height) to dst, row by row with the given pitch.
	// Returns false if no fresh frame of that size is available; dst is then left untouched or partial.
	bool Read(BYTE* dst, LONG pitch, UINT width, UINT height);

private:
	HANDLE _section = nullptr;
	BYTE* _view = nullptr;
};

// BGRA (top-down, srcPitch) -> NV12 in a buffer whose luma plane has `pitch` and is followed by the chroma plane.
void BgraToNv12(const BYTE* src, LONG srcPitch, UINT width, UINT height, BYTE* dst, LONG pitch);
void FillBlackNv12(BYTE* dst, LONG pitch, UINT width, UINT height);
void FillBlackBgra(BYTE* dst, LONG pitch, UINT width, UINT height);

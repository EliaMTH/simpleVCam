cmake_minimum_required(VERSION 3.20)
project(simplevcam_source LANGUAGES CXX)

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "Build with the x64 toolchain (vcvars64.bat)")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>") # static CRT: no redistributable needed in the Frame Server

add_library(simplevcam_source SHARED
  src/Activator.cpp
  src/Control.cpp
  src/dllmain.cpp
  src/MediaSource.cpp
  src/MediaStream.cpp
  src/SharedFrame.cpp
  src/Util.cpp
  src/simplevcam.def
)

target_compile_definitions(simplevcam_source PRIVATE UNICODE _UNICODE NOMINMAX)
target_compile_options(simplevcam_source PRIVATE /W3 /permissive- /EHsc /utf-8)
target_link_libraries(simplevcam_source PRIVATE mfplat mfuuid mfsensorgroup ole32 oleaut32 advapi32 propsys windowsapp winmm)

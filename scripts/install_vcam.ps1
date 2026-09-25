# Installs the simpleVCam virtual camera (one time, needs administrator rights).
#   - copies the DLL to %ProgramFiles%\simpleVCam (the Frame Server services cannot read user folders)
#   - registers it in HKLM with regsvr32
#   - creates %ProgramData%\simpleVCam (output.cfg written by the app, vcam.log written by the camera)
#Requires -RunAsAdministrator
param(
    [string]$Dll = (Join-Path $PSScriptRoot '..\native\build\simplevcam_source.dll')
)
$ErrorActionPreference = 'Stop'
Start-Transcript -Path (Join-Path $env:TEMP 'simplevcam_install.log') -Force | Out-Null
try {
    if (-not (Test-Path $Dll)) { throw "DLL not found: $Dll (run native\build.bat first)" }

    $installDir = Join-Path $env:ProgramFiles 'simpleVCam'
    $dataDir = Join-Path $env:ProgramData 'simpleVCam'
    $target = Join-Path $installDir 'simplevcam_source.dll'

    # the Frame Server services may still have the previous DLL loaded
    Stop-Service FrameServer, FrameServerMonitor -Force -ErrorAction SilentlyContinue

    New-Item -ItemType Directory -Force $installDir | Out-Null
    Copy-Item $Dll $target -Force

    $p = Start-Process regsvr32.exe -ArgumentList '/s', "`"$target`"" -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "regsvr32 failed with exit code $($p.ExitCode)" }

    New-Item -ItemType Directory -Force $dataDir | Out-Null
    # BUILTIN\Users and LOCAL SERVICE (the Frame Server account): modify
    & icacls.exe $dataDir /grant '*S-1-5-32-545:(OI)(CI)M' '*S-1-5-19:(OI)(CI)M' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls failed with exit code $LASTEXITCODE" }

    Write-Host "simpleVCam installed: $target"
    Write-Host 'OK'
}
catch {
    Write-Host "ERROR: $_"
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}

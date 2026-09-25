# Removes the simpleVCam virtual camera (needs administrator rights). Close simpleVCam first.
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
Start-Transcript -Path (Join-Path $env:TEMP 'simplevcam_uninstall.log') -Force | Out-Null
try {
    $installDir = Join-Path $env:ProgramFiles 'simpleVCam'
    $dataDir = Join-Path $env:ProgramData 'simpleVCam'
    $target = Join-Path $installDir 'simplevcam_source.dll'

    Stop-Service FrameServer, FrameServerMonitor -Force -ErrorAction SilentlyContinue

    if (Test-Path $target) {
        $p = Start-Process regsvr32.exe -ArgumentList '/u', '/s', "`"$target`"" -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "regsvr32 /u failed with exit code $($p.ExitCode)" }
    }

    Remove-Item $installDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $dataDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'simpleVCam removed'
    Write-Host 'OK'
}
catch {
    Write-Host "ERROR: $_"
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}

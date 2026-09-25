# Builds the release installer: dist\simpleVCam-<version>-setup.exe (+ .sha256).
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_release.ps1
#
# Steps: camera DLL (MSVC) -> tests -> app folder (PyInstaller) -> smoke test of the built exe
#        -> license texts -> installer (Inno Setup) -> SHA256 checksum.
# Needs: Visual Studio C++ build tools + Windows SDK, CMake, Inno Setup 6, and the Python packages
# of requirements-dev.txt. Used as is by .github/workflows/release.yml.
param(
    [string]$Python,           # default: .venv\Scripts\python.exe if present, else python on PATH
    [string]$ExpectedVersion   # optional: fail if simplevcam.__version__ differs (CI passes the git tag)
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Invoke-Step([string]$name, [scriptblock]$action) {
    Write-Host "==> $name" -ForegroundColor Cyan
    & $action
    if ($LASTEXITCODE) { throw "$name failed (exit code $LASTEXITCODE)" }
}

if (-not $Python) {
    $Python = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
}
$version = (Select-String -Path 'simplevcam\__init__.py' -Pattern '__version__ = "(.+?)"').Matches[0].Groups[1].Value
if ($ExpectedVersion -and $ExpectedVersion.TrimStart('v') -ne $version) {
    throw "Version mismatch: tag $ExpectedVersion, simplevcam.__version__ $version"
}
Write-Host "simpleVCam $version" -ForegroundColor Green

$iscc = @(
    (Get-Command 'iscc.exe' -ErrorAction SilentlyContinue).Source,
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup 6 not found (winget install JRSoftware.InnoSetup)' }

$license = @('LICENSE', 'LICENSE.txt', 'LICENCE', 'LICENCE.txt') | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $license) { throw 'No LICENSE file in the repository root' }

$build = Join-Path $root 'build'
$dist = Join-Path $root 'dist'
$appDir = Join-Path $build 'dist\simpleVCam'
New-Item -ItemType Directory -Force $build, $dist | Out-Null

Invoke-Step 'Camera DLL' { cmd /c native\build.bat }
Invoke-Step 'Tests' { & $Python -m pytest -q }
Invoke-Step 'App (PyInstaller)' {
    & $Python -m PyInstaller packaging\simplevcam.spec --noconfirm --clean --distpath "$build\dist" --workpath "$build\pyinstaller"
}

Write-Host '==> Smoke test of the built app' -ForegroundColor Cyan
$report = Join-Path $build 'smoke-test.txt'
$p = Start-Process -FilePath "$appDir\simpleVCam.exe" -ArgumentList '--smoke-test', "`"$report`"" -Wait -PassThru
Get-Content $report
if ($p.ExitCode -ne 0) { throw "Smoke test failed (exit code $($p.ExitCode))" }

Invoke-Step 'License texts' { & $Python packaging\collect_licenses.py "$build\licenses" }
Invoke-Step 'Installer (Inno Setup)' {
    & $iscc /Qp `
        "/DAppVersion=$version" `
        "/DAppDir=$appDir" `
        "/DCameraDll=$root\native\build\simplevcam_source.dll" `
        "/DLicenseFile=$root\$license" `
        "/DNoticesFile=$root\packaging\THIRD-PARTY-NOTICES.txt" `
        "/DLicensesDir=$build\licenses" `
        "/DIconFile=$root\simplevcam\assets\simplevcam.ico" `
        "/DOutputDir=$dist" `
        packaging\simplevcam.iss
}

$installer = Join-Path $dist "simpleVCam-$version-setup.exe"
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
"$hash  $(Split-Path $installer -Leaf)" | Set-Content -Encoding ascii "$installer.sha256"
Write-Host "Done: $installer" -ForegroundColor Green
Write-Host "SHA256: $hash"

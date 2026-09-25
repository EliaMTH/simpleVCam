; Inno Setup script for the simpleVCam installer.
; Built by packaging/build_release.ps1, which defines: AppVersion, AppDir (PyInstaller output folder),
; CameraDll, LicenseFile, NoticesFile, LicensesDir, IconFile and OutputDir.

#ifndef AppVersion
  #error Build with packaging/build_release.ps1
#endif

[Setup]
; AppId identifies the app for upgrades and uninstall: never change it.
AppId={{3B591937-BCF7-467B-8996-055E3BF6C053}
AppName=simpleVCam
AppVersion={#AppVersion}
AppVerName=simpleVCam {#AppVersion}
AppPublisher=EliaMTh
AppPublisherURL=https://github.com/EliaMTH/simpleVCam
AppSupportURL=https://github.com/EliaMTH/simpleVCam/issues
AppUpdatesURL=https://github.com/EliaMTH/simpleVCam/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\simpleVCam
DisableProgramGroupPage=yes
; the camera must be registered machine-wide (HKLM) and live where the Frame Server services can read it
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; virtual cameras (MFCreateVirtualCamera) exist from Windows 11
MinVersion=10.0.22000
LicenseFile={#LicenseFile}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\simpleVCam.exe
OutputDir={#OutputDir}
OutputBaseFilename=simpleVCam-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
; output.cfg (written by the app) and vcam.log (written by the camera, which runs in a service)
Name: "{commonappdata}\simpleVCam"; Permissions: users-modify service-modify

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; the virtual camera: a COM media source, registered on install and unregistered on uninstall
Source: "{#CameraDll}"; DestDir: "{app}"; Flags: ignoreversion regserver 64bit
Source: "{#LicenseFile}"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "{#NoticesFile}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#LicensesDir}\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\simpleVCam"; Filename: "{app}\simpleVCam.exe"
Name: "{autodesktop}\simpleVCam"; Filename: "{app}\simpleVCam.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\simpleVCam.exe"; Description: "{cm:LaunchProgram,simpleVCam}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallDelete]
Type: filesandordirs; Name: "{commonappdata}\simpleVCam"

[Code]
// While an app uses the camera, the Frame Server services keep its DLL loaded. Stop them so the DLL
// can be replaced or removed; Windows starts them again when an app opens a camera.
procedure StopFrameServer();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\net.exe'), 'stop FrameServer /y', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\net.exe'), 'stop FrameServerMonitor /y', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopFrameServer();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopFrameServer();
end;

; Inno Setup script for the Windows installer.
; Build: ISCC /DAppVersion=<version> /DSourceDir=<build folder> /DOutputDir=<dir> echo-shift.iss
; The AppId must never change: it is how a new installer finds and upgrades an
; existing install. Saves live in %APPDATA%\EchoShift and are never touched.

#ifndef AppVersion
  #error Pass /DAppVersion=<version>
#endif
#ifndef SourceDir
  #error Pass /DSourceDir=<folder with EchoShift.exe and _internal>
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

[Setup]
AppId={{97D7D7E8-B453-46DE-AE92-88DB2C611AFF}
AppName=Echo Shift
AppVersion={#AppVersion}
AppVerName=Echo Shift {#AppVersion}
AppPublisher=Saalim Saadman Araf
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\Echo Shift
DefaultGroupName=Echo Shift
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
OutputDir={#OutputDir}
OutputBaseFilename=Echo_Shift-{#AppVersion}-windows-x64-setup
SetupIconFile=echo-shift.ico
UninstallDisplayIcon={app}\echo-shift.ico
WizardStyle=modern
Compression=lzma2
SolidCompression=yes

[Tasks]
Name: desktopicon; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Clear the previous version's runtime so an upgrade never mixes old and new files.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "echo-shift.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Echo Shift"; Filename: "{app}\EchoShift.exe"; IconFilename: "{app}\echo-shift.ico"
Name: "{autodesktop}\Echo Shift"; Filename: "{app}\EchoShift.exe"; IconFilename: "{app}\echo-shift.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\EchoShift.exe"; Description: "{cm:LaunchProgram,Echo Shift}"; Flags: nowait postinstall skipifsilent

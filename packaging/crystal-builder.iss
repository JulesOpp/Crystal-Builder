; Crystal Builder, the Windows installer.
;
;   pyinstaller --noconfirm packaging\windows.spec
;   iscc /DAppVersion=0.1.0rc1 packaging\crystal-builder.iss
;
; Per-user by default, and that is the important decision here.  A
; scientific tool is very often installed on a managed lab machine by
; somebody who cannot get administrator rights, and PrivilegesRequired
; below means no UAC prompt and no refusal: it installs under the
; user's own AppData and writes its associations to HKCU.  The cost is
; that it is installed for one account, which is the right trade for
; the machines this will actually land on.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Crystal Builder"
#define AppExeName "Crystal Builder.exe"
#define AppPublisher "Crystal Builder"
#define AppURL "https://github.com/JulesOpp/Crystal-Builder"
#define SourceDir "..\dist\Crystal Builder"

[Setup]
AppId={{7C6C4B2E-3F1A-4A5D-9B21-4B0E3A6F52D1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=Crystal-Builder-{#AppVersion}-setup
SetupIconFile=icons\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-user: `lowest` asks for nothing, so a user without admin rights
; can install, and `autopf` resolves to their own AppData rather than
; Program Files.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; The bundle carries a 64-bit Python and 64-bit Qt.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Explorer caches file icons, and without this the associations
; registered below do not show their icons until the next logon.
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; Unticked, deliberately, and it is the same decision the macOS
; Info.plist makes with LSHandlerRank: Alternate.  A .cif on a working
; machine is usually already associated with VESTA or Mercury, and an
; installer that silently takes it is the fastest way to be
; uninstalled.  .xtalproj is ticked because this application writes
; that format and nothing else reads it.
Name: "assoccif"; Description: "Open .cif files with {#AppName}"; \
    GroupDescription: "File associations:"; Flags: unchecked
Name: "assocproj"; \
    Description: "Open .xtalproj project files with {#AppName}"; \
    GroupDescription: "File associations:"

[Files]
Source: "{#SourceDir}\{#AppExeName}"; DestDir: "{app}"; \
    Flags: ignoreversion
Source: "{#SourceDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; \
    Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
    Tasks: desktopicon

[Registry]
; HKA with PrivilegesRequired=lowest resolves to HKCU, so this is a
; per-user association and needs no elevation.  ProgID first, then the
; extension pointing at it, which is the order Explorer expects.
Root: HKA; Subkey: "Software\Classes\CrystalBuilder.cif"; \
    ValueType: string; ValueName: ""; \
    ValueData: "Crystallographic Information File"; \
    Flags: uninsdeletekey; Tasks: assoccif
Root: HKA; Subkey: "Software\Classes\CrystalBuilder.cif\DefaultIcon"; \
    ValueType: string; ValueName: ""; \
    ValueData: "{app}\cif.ico"; Tasks: assoccif
Root: HKA; \
    Subkey: "Software\Classes\CrystalBuilder.cif\shell\open\command"; \
    ValueType: string; ValueName: ""; \
    ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: assoccif
Root: HKA; Subkey: "Software\Classes\.cif"; ValueType: string; \
    ValueName: ""; ValueData: "CrystalBuilder.cif"; \
    Flags: uninsdeletevalue; Tasks: assoccif

Root: HKA; Subkey: "Software\Classes\CrystalBuilder.xtalproj"; \
    ValueType: string; ValueName: ""; \
    ValueData: "Crystal Builder Project"; \
    Flags: uninsdeletekey; Tasks: assocproj
Root: HKA; \
    Subkey: "Software\Classes\CrystalBuilder.xtalproj\DefaultIcon"; \
    ValueType: string; ValueName: ""; \
    ValueData: "{app}\xtalproj.ico"; Tasks: assocproj
Root: HKA; \
    Subkey: "Software\Classes\CrystalBuilder.xtalproj\shell\open\command"; \
    ValueType: string; ValueName: ""; \
    ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: assocproj
Root: HKA; Subkey: "Software\Classes\.xtalproj"; ValueType: string; \
    ValueName: ""; ValueData: "CrystalBuilder.xtalproj"; \
    Flags: uninsdeletevalue; Tasks: assocproj

; So the Open With list offers this application for a .cif even when
; the association above was declined, which is the polite half of not
; taking it.
Root: HKA; \
    Subkey: "Software\Classes\Applications\{#AppExeName}\shell\open\command"; \
    ValueType: string; ValueName: ""; \
    ValueData: """{app}\{#AppExeName}"" ""%1"""; \
    Flags: uninsdeletekey
Root: HKA; \
    Subkey: "Software\Classes\Applications\{#AppExeName}\SupportedTypes"; \
    ValueType: string; ValueName: ".cif"; ValueData: ""
Root: HKA; \
    Subkey: "Software\Classes\Applications\{#AppExeName}\SupportedTypes"; \
    ValueType: string; ValueName: ".xtalproj"; ValueData: ""

[Run]
Filename: "{app}\{#AppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller's onedir tree gets .pyc files written beside it on
; first run in some configurations, and an uninstaller that leaves a
; directory behind looks like it failed.
Type: filesandordirs; Name: "{app}\_internal"

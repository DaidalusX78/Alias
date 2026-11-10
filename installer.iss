; Inno Setup Script for Alias Media Renamer
; Target: Windows 10 / Windows 11 (64-bit)

#define MyAppName "Alias"
#define MyAppVersion "1.1.05"
#define MyAppPublisher "Marc Bailey"
#define MyAppCopyright "Created by Marc Bailey 2026"
#define MyAppURL "https://github.com/DaidalusX78/Alias"
#define MyAppExeName "Alias.exe"
#define MyIconName "alias.ico"
#define MyAppUserModelId "daidalus.alias.renamer.1.1"

[Setup]
; Unique AppId generated for Alias (prevents collision with other apps)
AppId={{D37E84B1-6284-48FE-95CB-3CE502B61B78}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright={#MyAppCopyright}
VersionInfoCopyright={#MyAppCopyright}

; Install directory (defaults to per-user AppData\Local\Programs unless user chooses all-users in dialog)
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Visuals & Branding
SetupIconFile={#MyIconName}
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern

; Output settings
OutputDir=installer_output
OutputBaseFilename=Alias_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes

; Gracefully close running instances during upgrade/uninstall
CloseApplications=yes

; Windows 64-bit targeting
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "contextmenu"; Description: "Add 'Rename with Alias' to Windows Explorer right-click context menu"; GroupDescription: "Windows Explorer Integration:"

[Files]
; Automatically support both PyInstaller --onedir (dist\Alias\*) and --onefile (dist\Alias.exe)
#if FileExists("dist\Alias\" + MyAppExeName)
Source: "dist\Alias\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#else
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
#endif
; Application icon
Source: "{#MyIconName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu Shortcut (AppUserModelID matches app.py so taskbar pinning never duplicates icons)
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyIconName}"; AppUserModelID: "{#MyAppUserModelId}"
; Desktop Shortcut (Optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyIconName}"; AppUserModelID: "{#MyAppUserModelId}"; Tasks: desktopicon

[Registry]
; Right-click context menu for folders / directories
Root: HKA; Subkey: "Software\Classes\Directory\shell\Alias"; ValueType: string; ValueData: "Rename with Alias"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\Alias"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyIconName}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\Alias\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: contextmenu

; Right-click context menu in folder background
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\Alias"; ValueType: string; ValueData: "Rename with Alias"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\Alias"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyIconName}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\Alias\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%V"""; Tasks: contextmenu

[Run]
; Option to launch Alias immediately after installation
Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Filename: "{app}\{#MyAppExeName}"; Flags: nowait postinstall skipifsilent

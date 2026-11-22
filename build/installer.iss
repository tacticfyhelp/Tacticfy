; Inno Setup 6 script: packages the PyInstaller one-folder build (dist\Tacticfy) into dist\TacticfySetup.exe.
; Build with build_installer.bat, or: iscc /DAppVersion=1.1.0 build\installer.iss

#ifndef AppVersion
  #error Pass the version: iscc /DAppVersion=x.y.z (build_installer.bat reads it from srcpp_paths.py)
#endif
#define AppName "Tacticfy"
#define AppExe "Tacticfy.exe"
#define AppUrl "https://github.com/tacticfyhelp/Tacticfy"

[Setup]
AppId={{71C26C05-747A-4AF9-88AB-D316CFDF74D1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
; Version stamped on TacticfySetup.exe itself (Properties > Details), so two installers can be told apart.
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} {#AppVersion} Setup
AppPublisher={#AppName}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Installs per-machine by default; users without admin rights can pick a per-user install.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=TacticfySetup
SetupLogging=yes
SetupIconFile=..\assets\Tacticfy.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Tacticfy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"; IconFilename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; User data (%LOCALAPPDATA%\Tacticfy: logs, calibrated offsets) is intentionally kept on uninstall.

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{71C26C05-747A-4AF9-88AB-D316CFDF74D1}_is1';

function InstalledVersion(): String;
begin
  Result := '';
  if not RegQueryStringValue(HKLM, UninstallKey, 'DisplayVersion', Result) then
    if not RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', Result) then
      Result := '';
end;

// Refuse to silently downgrade: running an old TacticfySetup.exe over a newer install would bring back
// that version's bundled offsets.json (e.g. without the human_team layout).
function InitializeSetup(): Boolean;
var
  Installed: String;
  InstalledPacked, ThisPacked: Int64;
begin
  Result := True;
  Installed := InstalledVersion();
  if (Installed = '') or not StrToVersion(Installed, InstalledPacked)
     or not StrToVersion('{#AppVersion}', ThisPacked) then
    exit;
  if ComparePackedVersion(InstalledPacked, ThisPacked) > 0 then
  begin
    if WizardSilent() then
    begin
      Log('Newer version ' + Installed + ' is installed; refusing to downgrade to {#AppVersion}.');
      Result := False;
    end
    else
      Result := MsgBox('{#AppName} ' + Installed + ' is already installed, and this installer is the OLDER '
        + 'version {#AppVersion}.' + #13#10#13#10
        + 'Installing it would downgrade {#AppName}. Get the latest installer from:' + #13#10
        + '{#AppUrl}/releases/latest' + #13#10#13#10
        + 'Downgrade anyway?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  end;
end;

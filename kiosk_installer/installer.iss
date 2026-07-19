; Inno Setup script for the ZK9500 kiosk agent.
; Build with kiosk_installer\build.ps1 (runs PyInstaller first, then ISCC on this file).
;
; What this installer does, end to end:
;   1. Asks for the server URL + device token (generated beforehand on the
;      VPS via `python manage.py kiosk_device create`).
;   2. Reminds the admin to have the ZKTeco ZKFinger driver already
;      installed (not bundled here -- see docs/kiosk_deployment.md).
;   3. Before copying files (ssInstall): stops + unregisters any existing
;      "ZK9500KioskListener" Scheduled Task and force-kills any running
;      kiosk_agent(_service).exe process. Needed for reinstalls/upgrades --
;      Windows locks a running exe against being overwritten, and without
;      this step the old process would otherwise keep running the old code
;      until its own next restart. kiosk_agent.py's own named-mutex
;      singleton lock (see _acquire_singleton_lock) is a second, independent
;      safety net that stops two `listen` processes ever touching the
;      reader at once even if this step were somehow skipped.
;   4. Copies kiosk_agent.exe / kiosk_agent_service.exe to Program Files.
;   5. Writes .env under %LOCALAPPDATA%\ZK9500Kiosk\ with the collected
;      values -- NOT next to the exes: Program Files isn't writable by the
;      Scheduled Task, which intentionally runs as the logged-on user, not
;      elevated (kiosk_agent.py reads/logs from the same folder -- see the
;      comment above its logging setup).
;   6. Registers + starts the "ZK9500KioskListener" Scheduled Task
;      (kiosk_agent_service.exe listen, at logon, auto-restart on failure).
;   7. Uninstalling removes the Scheduled Task before removing the files.

#define MyAppName "ZK9500 Kiosk"
#define MyAppVersion "1.2"

[Setup]
AppId={{5F051ACE-0489-4AD6-844C-FDBD962193CC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\ZK9500Kiosk
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=ZK9500KioskSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "dist\kiosk_agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\kiosk_agent_service.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "enroll_manual.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}\Cadastrar biometria (manual)"; Filename: "{app}\enroll_manual.cmd"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\Ver logs"; Filename: "{win}\notepad.exe"; Parameters: """{localappdata}\ZK9500Kiosk\kiosk_agent.log"""; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Unregister-ScheduledTask -TaskName 'ZK9500KioskListener' -Confirm:$false -ErrorAction SilentlyContinue"""; Flags: runhidden; RunOnceId: "RemoveKioskTask"

[Code]
var
  ServerPage: TInputQueryWizardPage;
  DriverInfoPage: TOutputMsgWizardPage;

procedure InitializeWizard;
begin
  ServerPage := CreateInputQueryPage(wpSelectDir,
    'Configuração do Quiosque', 'Dados de conexão com o servidor',
    'Antes de continuar, gere um token de dispositivo NO SERVIDOR (via SSH):' + #13#10 +
    '  python manage.py kiosk_device create --name "Nome deste quiosque"' + #13#10#13#10 +
    'O token só é exibido uma vez -- copie e cole abaixo junto com a URL do servidor.');
  ServerPage.Add('URL do servidor:', False);
  ServerPage.Add('Token do dispositivo:', True);
  ServerPage.Values[0] := 'https://expomarcas.cloud';

  DriverInfoPage := CreateOutputMsgPage(ServerPage.ID,
    'Driver do Leitor ZK9500', 'Verifique antes de continuar',
    'Este instalador NÃO inclui o driver/SDK ZKFinger da ZKTeco.' + #13#10#13#10 +
    'Certifique-se de que ele já esteja instalado neste computador (o mesmo ' +
    'instalador/CD que acompanha o leitor ZK9500) antes de prosseguir -- sem ' +
    'ele, o quiosque não conseguirá se comunicar com o leitor mesmo depois ' +
    'de instalado.');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ServerPage.ID then
  begin
    if (Trim(ServerPage.Values[0]) = '') or (Trim(ServerPage.Values[1]) = '') then
    begin
      MsgBox('Preencha a URL do servidor e o token do dispositivo.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure StopExistingInstance;
var
  ScriptContent, ScriptPath: String;
  ResultCode: Integer;
begin
  { Runs before [Files] copies anything (see CurStepChanged's ssInstall
    branch below) so a reinstall/upgrade never fights a locked exe or
    leaves the old process running the old code in the background. Safe
    to run even on a first-time install -- every cmdlet here is a no-op
    (via -ErrorAction SilentlyContinue) when nothing exists yet. }
  ScriptContent :=
    'Stop-ScheduledTask -TaskName "ZK9500KioskListener" -ErrorAction SilentlyContinue' + #13#10 +
    'Unregister-ScheduledTask -TaskName "ZK9500KioskListener" -Confirm:$false -ErrorAction SilentlyContinue' + #13#10 +
    'Get-Process -Name "kiosk_agent_service" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue' + #13#10 +
    'Get-Process -Name "kiosk_agent" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue' + #13#10 +
    'Start-Sleep -Milliseconds 500' + #13#10;
  ScriptPath := ExpandConstant('{tmp}') + '\_stop_previous.ps1';
  SaveStringToFile(ScriptPath, ScriptContent, False);
  Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  DeleteFile(ScriptPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDir, DataDir, EnvContent, ScriptContent, ScriptPath: String;
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    StopExistingInstance;
  end;

  if CurStep = ssPostInstall then
  begin
    AppDir := ExpandConstant('{app}');
    DataDir := ExpandConstant('{localappdata}') + '\ZK9500Kiosk';
    ForceDirectories(DataDir);

    EnvContent :=
      'KIOSK_SERVER_URL=' + ServerPage.Values[0] + #13#10 +
      'KIOSK_DEVICE_TOKEN=' + ServerPage.Values[1] + #13#10 +
      'KIOSK_DEVICE_ID=0' + #13#10 +
      'KIOSK_TEMPLATE_REFRESH_SECONDS=30' + #13#10 +
      'KIOSK_ENROLL_POLL_SECONDS=5' + #13#10 +
      'KIOSK_HTTP_TIMEOUT=10' + #13#10;
    SaveStringToFile(DataDir + '\.env', EnvContent, False);

    { A generated .ps1 avoids fragile nested quoting between Inno/PowerShell
      when passed inline via -Command; deleted again right after running. }
    ScriptContent :=
      '$action = New-ScheduledTaskAction -Execute "' + AppDir + '\kiosk_agent_service.exe" -Argument "listen" -WorkingDirectory "' + AppDir + '"' + #13#10 +
      '$trigger = New-ScheduledTaskTrigger -AtLogOn' + #13#10 +
      '$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable' + #13#10 +
      'Register-ScheduledTask -TaskName "ZK9500KioskListener" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null' + #13#10 +
      'Start-ScheduledTask -TaskName "ZK9500KioskListener"' + #13#10;
    ScriptPath := AppDir + '\_register_task.ps1';
    SaveStringToFile(ScriptPath, ScriptContent, False);

    if not Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      MsgBox('Não foi possível registrar a tarefa agendada automaticamente. Consulte docs/kiosk_deployment.md para configurar manualmente.', mbError, MB_OK);

    DeleteFile(ScriptPath);
  end;
end;

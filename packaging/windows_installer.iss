#define AppVersion "0.5.0"
#ifndef AppBinary
  #define AppBinary "..\dist\notes-prompter.exe"
#endif
#ifndef SetupOutput
  #define SetupOutput "..\dist"
#endif

[Setup]
AppId=NotesPrompter
AppName=Notes Prompter
AppVersion={#AppVersion}
AppVerName=Notes Prompter {#AppVersion}
AppPublisher=Notes Prompter
AppComments=Live speaker notes and per-slide presets
DefaultDirName={localappdata}\Programs\NotesPrompter
DefaultGroupName=Notes Prompter
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupArchitecture=x64
MinVersion=10.0
Uninstallable=yes
CreateUninstallRegKey=yes
UninstallDisplayIcon={app}\notes-prompter.ico
UninstallDisplayName=Notes Prompter
DisableProgramGroupPage=no
DisableWelcomePage=no
DisableDirPage=no
AllowNoIcons=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
WizardStyle=modern
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=no
UsePreviousLanguage=no
LicenseFile=..\LICENSE
InfoBeforeFile=installer-readme.txt
OutputDir={#SetupOutput}
OutputBaseFilename=Notes-Prompter-Setup-{#AppVersion}
SetupIconFile=notes-prompter.ico
Compression=lzma2
SolidCompression=yes
CloseApplications=no
RestartApplications=no
VersionInfoDescription=Notes Prompter installer
VersionInfoVersion=0.5.0.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"; InfoBeforeFile: "installer-readme.txt"
Name: "catalan"; MessagesFile: "compiler:Languages\Catalan.isl"; InfoBeforeFile: "installer-readme-ca.txt"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"; InfoBeforeFile: "installer-readme-es.txt"

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; GroupDescription: "{cm:ShortcutGroup}"; Flags: unchecked

[Files]
Source: "{#AppBinary}"; DestDir: "{app}"; DestName: "notes-prompter.exe"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "installer-readme.txt"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion; Languages: english
Source: "installer-readme-ca.txt"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion; Languages: catalan
Source: "installer-readme-es.txt"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion; Languages: spanish
Source: "notes-prompter.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Notes Prompter"; Filename: "{app}\notes-prompter.exe"; WorkingDir: "{app}"; IconFilename: "{app}\notes-prompter.ico"
Name: "{group}\{cm:Guide}"; Filename: "{app}\README.txt"; WorkingDir: "{app}"
Name: "{group}\{cm:Uninstall}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Notes Prompter"; Filename: "{app}\notes-prompter.exe"; WorkingDir: "{app}"; IconFilename: "{app}\notes-prompter.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\notes-prompter.exe"; Description: "{cm:OpenApp}"; Flags: nowait postinstall skipifsilent unchecked

[Messages]
english.WelcomeLabel2=This wizard installs Notes Prompter for your Windows user.%n%nQuit the previous version using Application > Quit. Closing the window keeps it running.%n%nExisting presets and settings are preserved.
catalan.WelcomeLabel2=Aquest assistent instal·la Notes Prompter per al teu usuari de Windows.%n%nTanca la versió anterior amb Aplicació > Sortir. La X la manté en segon pla.%n%nEs conserven les preconfiguracions i els ajustos existents.
spanish.WelcomeLabel2=Este asistente instala Notes Prompter para tu usuario de Windows.%n%nCierra la versión anterior con Aplicación > Salir. La X la mantiene en segundo plano.%n%nSe conservan los presets y ajustes existentes.
english.FinishedLabel=Notes Prompter is installed. In Listen mode, use Administration panel to configure reading settings and per-PowerPoint/slide presets.
catalan.FinishedLabel=Notes Prompter està instal·lat. En mode Escoltar, obre Panell d’administració per configurar la lectura i les preconfiguracions per PowerPoint i diapositiva.
spanish.FinishedLabel=Notes Prompter está instalado. En modo Escuchar, abre Panel de administración para configurar la lectura y los presets por PowerPoint y diapositiva.
english.ConfirmUninstall=Uninstall Notes Prompter?%n%nYour presets and reading settings will be preserved.
catalan.ConfirmUninstall=Vols desinstal·lar Notes Prompter?%n%nEs conservaran les preconfiguracions i els ajustos de lectura.
spanish.ConfirmUninstall=¿Quieres desinstalar Notes Prompter?%n%nSe conservarán los presets y ajustes de lectura.

[CustomMessages]
english.DesktopShortcut=Create a desktop shortcut
catalan.DesktopShortcut=Crea un accés directe a l’escriptori
spanish.DesktopShortcut=Crear un acceso directo en el escritorio
english.ShortcutGroup=Shortcuts:
catalan.ShortcutGroup=Accessos directes:
spanish.ShortcutGroup=Accesos directos:
english.Guide=User guide
catalan.Guide=Guia d’ús
spanish.Guide=Guía de uso
english.Uninstall=Uninstall Notes Prompter
catalan.Uninstall=Desinstal·lar Notes Prompter
spanish.Uninstall=Desinstalar Notes Prompter
english.OpenApp=Open Notes Prompter
catalan.OpenApp=Obrir Notes Prompter
spanish.OpenApp=Abrir Notes Prompter
english.CloseBeforeUpdate=Quit Notes Prompter using Application > Quit before updating. Closing the window keeps it running.
catalan.CloseBeforeUpdate=Tanca Notes Prompter amb Aplicació > Sortir abans d’actualitzar-lo. La X el manté en segon pla.
spanish.CloseBeforeUpdate=Cierra Notes Prompter con Aplicación > Salir antes de actualizarlo. La X lo mantiene en segundo plano.
english.CloseBeforeUninstall=Quit Notes Prompter using Application > Quit before uninstalling.
catalan.CloseBeforeUninstall=Tanca Notes Prompter amb Aplicació > Sortir abans de desinstal·lar-lo.
spanish.CloseBeforeUninstall=Cierra Notes Prompter con Aplicación > Salir antes de desinstalarlo.

[Code]
function OpenExecutableForWrite(FileName: String; Access, ShareMode: Cardinal;
  Security: NativeInt; Creation, Attributes: Cardinal; Template: NativeInt): NativeInt;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseExecutableHandle(Handle: NativeInt): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function CanReplaceApplication: Boolean;
var
  FileName: String;
  Handle: NativeInt;
begin
  Result := True;
  FileName := ExpandConstant('{app}\notes-prompter.exe');
  if not FileExists(FileName) then
    Exit;
  { OPEN_EXISTING y GENERIC_WRITE: abre sin modificar ni truncar el archivo. }
  Handle := OpenExecutableForWrite(FileName, $40000000, 7, 0, 3, 0, 0);
  Result := Handle <> -1;
  if Result then
    CloseExecutableHandle(Handle);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not CanReplaceApplication then
    Result := CustomMessage('CloseBeforeUpdate');
end;

function InitializeUninstall: Boolean;
begin
  Result := CanReplaceApplication;
  if not Result then
    MsgBox(CustomMessage('CloseBeforeUninstall'), mbError, MB_OK);
end;

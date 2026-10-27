; Inno Setup 脚本 —— 双击编译后生成真正的「下一步下一步」安装程序
; 1) 装 Inno Setup 6（免费）：https://jrsoftware.org/isdl.php
; 2) 用 Inno Setup 打开本文件，点 Build → Compile（或 Ctrl+F9）
; 3) 产物在 installer\MiniCursor_1.0.0_Windows_x64_Setup.exe

#define MyAppName "MiniCursor"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "你的名字"
#define MyAppExeName "MiniCursor.exe"

[Setup]
AppId={{8F1C2D57-6B4A-4E9E-9A31-0C5D2E7B41A0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=MiniCursor_{#MyAppVersion}_Windows_x64_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayName={#MyAppName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "..\dist\MiniCursor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 MiniCursor"; Flags: nowait postinstall skipifsilent

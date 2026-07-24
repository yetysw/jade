; ============================================================
;  Jade — installateur Windows
;
;  AUCUN secret n'est embarqué dans cet installateur : les identifiants
;  (jetons Cloudflare, mot de passe admin) sont saisis par le technicien
;  PENDANT l'installation, puis écrits dans un fichier .env local sur le poste.
;  L'installateur peut donc être distribué sans risque de fuite.
; ============================================================

#define AppName "Jade"
#define AppVersion "1.5.0"
#define AppPublisher "Jade Sàrl"
; exécutable principal = application native Flutter (lance le backend sidecar)
#define AppExeName "jade.exe"
#define RepoRoot ".."
#define FlutterRelease RepoRoot + "\flutter_app\build\windows\x64\runner\Release"

[Setup]
AppId={{7E6A2C43-9B1D-4F5E-A9D0-JADEJade0001}
AppName={#AppName}
AppVersion={#AppVersion}
; afficher « Jade » seul (sans le numéro de version) dans l'assistant et le
; Panneau de configuration ; la version reste connue en interne (AppVersion)
AppVerName={#AppName}
UninstallDisplayName={#AppName}
AppPublisher={#AppPublisher}
AppPublisherURL=https://www.example.com
#ifdef TESTBUILD
DefaultDirName={localappdata}\JadeTest
#else
DefaultDirName={autopf}\Jade
#endif
DefaultGroupName=Jade
DisableProgramGroupPage=yes
OutputDir={#RepoRoot}\dist\installer
#ifndef TESTBUILD
OutputBaseFilename=Jade-Setup-{#AppVersion}
#endif
SetupIconFile=jade.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
#ifdef TESTBUILD
; variante de validation (non livrée) : sans élévation, dans le profil utilisateur
PrivilegesRequired=lowest
OutputBaseFilename=Jade-Setup-TEST
#else
PrivilegesRequired=admin
#endif
WizardStyle=modern
; Protection de l'installateur : si le mot de passe est fourni au build
;   ISCC /DSetupPassword=xxxxx installer\jade.iss
; le contenu est CHIFFRE et l'installation exige le mot de passe (protege si
; l'exe fuite). Le mot de passe n'est JAMAIS versionne (passe en ligne de
; commande, jamais ecrit dans ce script).
#ifdef SetupPassword
Password={#SetupPassword}
Encryption=yes
#endif

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; 1) application native Flutter (interface) -> {app}
Source: "{#FlutterRelease}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; 2) backend Python gelé (PyInstaller) en sidecar -> {app}\backend
;    lancé par l'app Flutter en « Jade.exe serve ». Le .env est généré par
;    l'assistant à côté de ce backend (jamais embarqué).
Source: "{#RepoRoot}\dist\Jade\*"; DestDir: "{app}\backend"; Excludes: ".env,data\*,logs\*,models\*"; Flags: recursesubdirs ignoreversion
#ifndef TESTBUILD
; Les modèles (embeddings + reranker) ne sont PAS embarqués : l'application les
; télécharge automatiquement au premier lancement dans {commonappdata}\Jade\models
; (rendu inscriptible ci-dessous).

[Dirs]
; index partagé, journaux, modèles : inscriptibles par tous les utilisateurs du serveur
Name: "{commonappdata}\Jade"; Permissions: users-modify
Name: "{commonappdata}\Jade\data"; Permissions: users-modify
Name: "{commonappdata}\Jade\logs"; Permissions: users-modify
Name: "{commonappdata}\Jade\models"; Permissions: users-modify
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; l'index se reconstruit ; les conversations des utilisateurs (%LOCALAPPDATA%) sont conservées
Type: filesandordirs; Name: "{commonappdata}\Jade\data"
Type: filesandordirs; Name: "{commonappdata}\Jade\logs"
Type: filesandordirs; Name: "{commonappdata}\Jade\models"
; le fichier de configuration local (identifiants) est retiré à la désinstallation
Type: files; Name: "{app}\backend\.env"

; ============================================================
;  Assistant : saisie des identifiants -> écriture d'un .env local
; ============================================================
[Code]
var
  LlmPage: TInputQueryWizardPage;
  WebPage: TInputQueryWizardPage;

function EnvFileExists: Boolean;
var
  Dir: String;
begin
  // IMPORTANT : ne PAS utiliser la constante app ici. En mode interactif, elle
  // n'est pas encore initialisee quand l'assistant evalue les pages -> erreur
  // « An attempt was made to expand the app constant before it was initialized ».
  // WizardDirValue (dossier cible choisi) est toujours defini pendant l'assistant.
  Dir := WizardDirValue;
  Result := (Dir <> '') and FileExists(Dir + '\backend\.env');
end;

{ Mise a jour (un .env existe deja) ou installation silencieuse (auto-update) :
  on ne redemande pas les identifiants et on CONSERVE la configuration en place. }
function KeepExistingConfig: Boolean;
begin
  Result := WizardSilent or EnvFileExists;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PageID = LlmPage.ID) or (PageID = WebPage.ID) then
    Result := KeepExistingConfig;
end;

procedure InitializeWizard;
begin
  LlmPage := CreateInputQueryPage(wpSelectDir,
    'Acces aux services Jade',
    'Identifiants Cloudflare Access (uniques pour tous les services)',
    'Ces informations sont fournies par Jade. Le meme couple Client ID / Secret ' +
    'sert pour le serveur IA et la recherche web. Elles sont enregistrees ' +
    'uniquement sur ce poste, jamais incluses dans le programme d''installation.');
  LlmPage.Add('Adresse du serveur LLM (OLLAMA_URL) :', False);
  LlmPage.Add('Cloudflare Access - Client ID :', False);
  LlmPage.Add('Cloudflare Access - Client Secret :', True);
  LlmPage.Values[0] := 'https://llm.example.com';

  WebPage := CreateInputQueryPage(LlmPage.ID,
    'Recherche web et retours utilisateur',
    'Recherche web interne et envoi des retours a Jade',
    'Laisser vide un champ non utilise : la fonctionnalite correspondante sera ' +
    'simplement desactivee.');
  WebPage.Add('Adresse SearXNG (SEARXNG_URL) :', False);
  WebPage.Add('Cle API Resend (retours utilisateur) :', True);
  WebPage.Values[0] := 'https://search.example.com';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if KeepExistingConfig then Exit;  // maj/silencieux : pas de saisie a valider
  if CurPageID = LlmPage.ID then
  begin
    if Trim(LlmPage.Values[0]) = '' then
    begin
      MsgBox('L''adresse du serveur LLM est requise.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure WriteEnvFile;
var
  S: String;
  NL: String;
begin
  { Mise a jour ou install silencieuse : conserver le .env existant (identifiants
    saisis a la 1re installation) — ne jamais l'ecraser ni ecrire une config vide. }
  if KeepExistingConfig then Exit;
  NL := #13#10;
  S :=
    '# Configuration Jade - generee par l''installateur. Ne pas partager.' + NL +
    'EMBED_MODEL=intfloat/multilingual-e5-large' + NL +
    'CHUNK_TOKENS=400' + NL +
    'CHUNK_OVERLAP=60' + NL +
    'TOP_K=10' + NL +
    'MIN_SCORE=0.35' + NL +
    'OLLAMA_URL=' + Trim(LlmPage.Values[0]) + NL +
    'OLLAMA_MODEL=qwen3.5:4b' + NL +
    'ROUTER_MODEL=qwen3.5:2b' + NL +
    'STRONG_MODEL=qwen3.5:9b' + NL +
    'VISION_MODEL=qwen3.5:9b' + NL +
    'NUM_CTX=8192' + NL +
    'REQUEST_TIMEOUT=120' + NL +
    'CF_ACCESS_CLIENT_ID=' + Trim(LlmPage.Values[1]) + NL +
    'CF_ACCESS_CLIENT_SECRET=' + Trim(LlmPage.Values[2]) + NL +
    'UI_HOST=127.0.0.1' + NL +
    'UI_PORT=8765' + NL +
    'CLIENT_NAME=Jade' + NL +
    'KEEP_ALIVE=30m' + NL +
    'REINDEX_MINUTES=30' + NL +
    'HYBRID_ENABLED=1' + NL +
    'RERANK_ENABLED=1' + NL +
    'CPU_THREADS=2' + NL +
    'NTFS_FILTER=1' + NL +
    'UPDATE_ENABLED=1' + NL +
    '# UPDATE_MODE : manual (poste client, bouton) ou scheduled (RDS, tache nocturne)' + NL +
    'UPDATE_MODE=manual' + NL +
    'GITEA_API_URL=https://git.example.com' + NL +
    'GITEA_REPO=example/jade' + NL +
    'GITEA_TOKEN=' + NL +
    'MODELS_URL=https://models.example.com/jade-models.tar' + NL +
#ifdef SetupPassword
    'SETUP_PASSWORD={#SetupPassword}' + NL +
#endif
    'WEB_FALLBACK=1' + NL +
    'SEARXNG_URL=' + Trim(WebPage.Values[0]) + NL +
    { meme service token Cloudflare Access pour tous les services Jade }
    'SEARXNG_CF_ACCESS_CLIENT_ID=' + Trim(LlmPage.Values[1]) + NL +
    'SEARXNG_CF_ACCESS_CLIENT_SECRET=' + Trim(LlmPage.Values[2]) + NL +
    'FEEDBACK_EMAIL=feedback@example.com' + NL +
    'RESEND_API_KEY=' + Trim(WebPage.Values[1]) + NL;
  { le backend (PyInstaller) lit le .env à côté de son exécutable }
  SaveStringToFile(ExpandConstant('{app}\backend\.env'), S, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteEnvFile;
end;

# Journal des versions — Jade

Versionnage **sémantique** `MAJEUR.MINEUR.CORRECTIF` :
- **MAJEUR** : refonte ou rupture de compatibilité ;
- **MINEUR** : nouvelles fonctionnalités ;
- **CORRECTIF** : corrections de bugs.

---

## 1.10.0 — 🚧 dev : ⭐ Jade sait qui elle est, modes de recherche et réponses rapides

- ⭐ **Identité de l'assistant** : Jade sait désormais qu'elle s'appelle Jade,
  qu'elle est éditée par Jade Sàrl et qu'elle fonctionne en local. L'identité est
  assemblée en un point unique (`rag.system_prompt`) et injectée dans tous les
  chemins où elle s'adresse à l'utilisateur (documentaire, web, général,
  smalltalk) — sans toucher aux appels utilitaires (routeur, titres, mémoire).
- ⭐ **Nom de l'utilisateur** : saisie facultative au premier lancement
  (« Comment souhaitez-vous que Jade vous appelle ? ») et modifiable dans les
  réglages. Endpoints `GET`/`POST` `/api/profile` ; le nom prime partout sur le
  compte Windows.
  - **Correction de la cause du « Leo »** : faute d'identité, l'assistant avait
    halluciné un prénom, et l'extraction de mémoire avait enregistré ses propres
    phrases (« Je m'appelle Léo ») comme des faits **sur l'utilisateur**.
    L'extraction refuse désormais les propos de l'assistant à la 1re personne, et
    le nom déclaré fait foi sur tout fait mémorisé.
- ⭐ **Modes de recherche explicites** : les trois cartes d'accueil ne lancent
  plus de question pré-remplie — elles **sélectionnent un mode**
  (`documents` / `web` / `créer un fichier`), et l'utilisateur écrit sa propre
  question. Le mode reste visible et modifiable en cours de conversation, avec
  retour au mode automatique en un clic. Champ `mode` sur `/ask`.
- ⭐ **Réponses rapides** : quand Jade pose une question, l'interface propose
  jusqu'à 3 réponses cliquables (générées par le petit modèle), le champ de
  saisie restant disponible pour répondre librement. Événement SSE `replies`.
- **Dossiers de conversations** : deux correctifs — déplacer une conversation
  vers un dossier **fermé** la faisait disparaître silencieusement ; **renommer
  et supprimer un dossier** étaient impossibles (fonctions non reliées à
  l'interface). Ajout d'un **menu au clic droit** sur les conversations et les
  dossiers.
- **Tests** : 76 → **114**.

## 1.9.1 — 🚧 dev : robustesse et sécurité (audit multi-agents)

Correctifs issus d'une passe d'équipe d'agents (security-watch, backend-rag,
qa-tests, ui-flutter) sur les nouveautés 1.9.0.

- **Sécurité** (audit `security-watch`) :
  - Le **zip de diagnostic** (bouton « Retour ») n'embarque plus le `body` du
    journal sortant (question + extraits de documents) : vue **caviardée**
    (ts/méthode/url uniquement). `CF-Access-Client-Id` désormais masqué.
  - **Sauvegarde `.jadebak`** (en clair) écrite par défaut sous `%LOCALAPPDATA%`
    au lieu de `Documents` (évite la synchronisation OneDrive/DFS hors du poste).
  - **licsrv** : l'app d'administration écoute sur `127.0.0.1` par défaut
    (`LICSRV_ADMIN_HOST`) ; une exécution bare-metal n'expose plus l'admin par
    accident. Risque résiduel DPAPI-machine sur RDS documenté.
- **Robustesse** (`backend-rag`) :
  - `prefs.json` : écriture **atomique** + verrou (plus de perte d'acceptation
    CGU / onboarding sur crash ou écritures concurrentes).
  - Restauration de sauvegarde **transactionnelle** (rollback) : une sauvegarde
    corrompue ne laisse plus d'historique à moitié importé.
  - Durées de licence bornées côté `licsrv` (plus d'`OverflowError`).
- **Tests** (`qa-tests`) : +24 tests (round-trip sauvegarde/restauration,
  écriture `.env`, documents légaux) → **76 tests** au total.
- **Interface** (`ui-flutter`) : animation des points d'onboarding gatée par
  `context.motion` (respect de « réduire les animations »).

## 1.9.0 — 🚧 dev : ⭐ Autonomie du poste (santé, sauvegarde, 1er lancement, réglages de connexion)

- ⭐ **Panneau « État du système »** (réglages) + **bandeau d'alerte rouge**
  (accueil) : serveur d'IA joignable, modèles prêts, espace disque, index.
  Contrôle de santé au lancement et rafraîchissement périodique. Endpoint
  `/api/health` et bloc `health` dans `/api/status`.
- ⭐ **Sauvegarde et migration des conversations** : export **portable**
  (déchiffré) dans un fichier `.jadebak`, restauration **re-chiffrée** avec la
  clé DPAPI de la machine cible (une simple copie de `chats.db` ne migrerait pas,
  le chiffrement étant lié au compte Windows). Boutons dédiés dans les réglages,
  fichier géré par l'utilisateur. Endpoints `/api/backup` et `/api/restore`.
- ⭐ **Premier lancement guidé** : écran d'**acceptation des CGU + politique de
  confidentialité** (documents embarqués, adaptés à la nLPD suisse) puis
  **onboarding** (présentation, choix d'un dossier, première question). Endpoints
  `/api/onboarding*` ; version légale suivie pour redemander l'accord si le texte
  change.
- ⭐ **Édition des identifiants de connexion dans les réglages** (adresses des
  services + service token Cloudflare Access) : plus besoin de réinstaller ni
  d'éditer le `.env` à la main. Écriture du `.env`, **scellement DPAPI** et
  **application à chaud** (sans redémarrage). Endpoints `GET`/`POST` `/api/config`.
- **Documentation** : refonte des CGU et de la politique de confidentialité
  (droit suisse, nLPD/OPDo) et **runbook de déploiement des licences** en
  facturation manuelle (`docs/deploiement-licences.md`).
- **Tests** : couverture portée à **52 tests** (licences client + serveur,
  configuration, sécurité DPAPI), tous hors réseau et déterministes.
- **Build** : `jwt`/`cryptography` embarqués de façon fiable dans le bundle
  PyInstaller ; documents légaux inclus dans l'exécutable.

## 1.8.0 — 🚧 dev : ⭐ Système de licences (optionnel)

- ⭐ **Serveur de licences `licsrv/`** (interne, jamais livré) : FastAPI + SQLite,
  **JWT Ed25519**, CLI d'admin (`add`/`extend`/`revoke`/`list`), secret client
  haché (PBKDF2), **aucune PII**, réponse d'erreur constante (pas d'oracle). À
  héberger derrière Cloudflare Access comme le LLM/SearXNG.
- **Intégration client** (`ragagent/licensing.py`) : vérification de
  l'abonnement au démarrage + périodique (toutes ~6 h), **non bloquante**,
  **JWT vérifié hors ligne** (clé publique embarquée) avec **période de grâce**
  configurable. États : off/active/grace/expired/suspended, exposés par
  `/api/status` et `/api/license`. À l'expiration : envoi de questions **bloqué
  proprement** (message « contactez Jade »), historique consultable. Bandeau
  d'état dans l'application.
- **Désactivé par défaut** (`LICENSE_ENABLED=0`) : aucune obligation de déployer
  le serveur ; le kill-switch reste la révocation du service token Cloudflare par
  client. Secrets licence scellés (DPAPI machine) comme les autres.
- Documentation de mise en place complète : `README.md` (section Licences) +
  `licsrv/README.md`.

*RDS multi-utilisateur (décision produit) : un déploiement = une société →
posture « statu quo + révocation CF » retenue ; le relais privilégié reste en
réserve (documenté) si un besoin multi-tenant / conformité apparaît.*

---

## 1.7.0 — 🚧 dev : ⭐ Durcissement sécurité (audit) + robustesse LLM

Issu d'un audit par une équipe de 7 sous-agents, re-validé par des agents
sécurité et QA.

**Sécurité**
- ⭐ **Isolation inter-session RDS** : l'API locale exige désormais un **jeton de
  session** (`X-Jade-Token`, comparaison constant-time) sur toutes les routes
  `/api/*`. Le jeton est généré par backend, publié dans `backend.json` (ACL
  par-utilisateur) et injecté par l'app. Sur RDS le loopback est commun aux
  sessions : sans ce jeton, un co-utilisateur pouvait atteindre le backend d'un
  autre (lecture des conversations/mémoire, etc.). Corrige aussi la réutilisation
  de port (la découverte rejette un backend au jeton non concordant).
- **`.env` : ACL restrictive posée AVANT l'écriture des secrets** + code retour
  d'`icacls` vérifié (plus de fenêtre en clair ; échec signalé).
- **Vérification d'intégrité SHA-256 des modèles ACTIVÉE** (`MODELS_SHA256`
  renseigné, empreinte vérifiée contre R2 ; repli HuggingFace si non concordant).
- **Filtrage NTFS appliqué AVANT la troncature** : un utilisateur restreint
  reçoit jusqu'à 8 extraits *lisibles* au lieu de « 8 moins les masqués ».

**Robustesse / concurrence LLM**
- **Annulation qui coupe réellement Ollama** (`gen.close()` en `finally`) : libère
  le slot GPU au lieu de laisser la génération continuer — corrige la saturation.
- `think=False` explicite sur la génération principale (plus de fuite `<think>`).
- Warmup **sans retry** et appels de confort (routeur, titre, suivi, accueil) en
  `retry=False` + timeout court : n'amplifient plus la saturation, ne bloquent
  plus 120 s.

**Qualité / UI / tests**
- **Socle de tests** (`pytest`) : semver auto-update, fusion RRF, garde du routeur.
- UI : cartes d'accueil aux couleurs du thème (lisibles en sombre) ; dialogue
  Réglages à largeur bornée (plus de débordement).

*Restent à traiter (documentés) : compte de service pour lire le `.env` sur RDS
(l'ACL admins exclut les standards) ; frontière de préfixe sur `/api/open`
(hygiène, rendue quasi-nulle par le jeton) ; synchro de `MODELS_SHA256` à chaque
nouvelle archive.*

---

## 1.6.0 — 🚧 dev : ⭐ Durcissement sécurité (RDS) + retour par e-mail

- ⭐ **Isolation par session RDS** : le backend choisit un **port libre par
  session** (`UI_PORT=auto`) et le publie dans `%LOCALAPPDATA%\Jade\backend.json` ;
  l'app Flutter découvre ce port au démarrage. Fini le backend unique partagé
  entre utilisateurs (conversations, mémoire et **droits NTFS** d'autrui).
- **Secrets du `.env` scellés** (DPAPI **machine**) via `jade seal-env`, lancé
  par l'installateur : le fichier ne livre plus les jetons en clair, tout en
  restant déchiffrable par toutes les sessions de la machine. **ACL** du `.env`
  restreinte aux administrateurs + SYSTEM (retrait du groupe *Users*).
- **Journal sortant par utilisateur** : `outbound.jsonl` déplacé dans
  `%LOCALAPPDATA%\Jade\logs` (un utilisateur RDS ne peut plus lire/falsifier les
  extraits envoyés par les autres).
- **Garde anti-DNS-rebinding** : l'API locale rejette (421) toute requête dont
  l'en-tête `Host` n'est pas le loopback.
- **Retour utilisateur par e-mail** (remplace l'intégration Resend de 1.5.0,
  jamais publiée) : ouvre le **client e-mail par défaut** (mailto, multi-OS)
  pré-rempli vers `feedback@example.com` et prépare un **zip de diagnostic** (journaux,
  version, état — **sans aucun secret**) révélé dans l'explorateur à joindre au
  message. Un `mailto:` ne pouvant pas attacher de fichier, le zip est fourni à
  côté.
- **Correctif** : l'endpoint `/api/open-url` masquait `openers.open_url`
  (auto-appel récursif) → ouverture des liens web des sources cassée depuis
  1.2.0. Renommé `open_url_route`.

---

## 1.5.0 — dev (non publiée) : réglages sans mot de passe (retour Resend, remplacé en 1.6.0)

- ⭐ **Bouton « Donner mon avis »** (barre latérale) : le message part
  directement à `feedback@example.com` via l'**API Resend** (clé saisie à
  l'installation), avec nom d'utilisateur, version et client en pied de message.
  Sans clé configurée : repli sur le client mail local. Endpoint
  `POST /api/feedback` inchangé côté nom.
- **Réglages sans mot de passe** : la gestion des dossiers indexés,
  la réindexation et le sélecteur ne sont plus protégés par mot de passe
  (`SETTINGS_PASSWORD` supprimé). L'API reste limitée à `127.0.0.1`.
- **Installateur simplifié** : un **seul couple** Cloudflare Access
  (Client ID/Secret) saisi une fois et réutilisé pour le LLM **et** SearXNG ;
  champ **clé API Resend** ajouté ; champ mot de passe administrateur supprimé.

---

## 1.4.3 — Correctif : installateur interactif (« app constant »)

- **L'installateur 1.4.0–1.4.2 plantait au lancement en mode interactif**
  (double-clic) : `Runtime error … An attempt was made to expand the "app"
  constant before it was initialized`. Cause : la détection de mise à jour
  (ajoutée en 1.4.0) lisait `{app}\backend\.env` via `ExpandConstant('{app}…')`,
  or `{app}` n'est pas encore initialisé quand l'assistant évalue les pages en
  interactif. Les tests en mode **silencieux** ne déclenchaient pas ce chemin,
  d'où le passage inaperçu. Corrigé : utilisation de `WizardDirValue` (toujours
  défini pendant l'assistant) au lieu de `{app}`.

---

## 1.4.2 — Modèles hébergés sur Cloudflare R2

- **`MODELS_URL` pointe désormais vers Cloudflare R2** (stockage objet, pas de
  serveur d'origine à proxifier). Un premier hébergement sur un site classique
  derrière Cloudflare (nuage orange) échouait systématiquement au-delà d'~2 Go :
  le proxy HTTP de Cloudflare a un timeout d'environ 120 s et ne relayait pas les
  requêtes Range. **R2 n'a ni l'un ni l'autre problème** — vérifié : taille exacte
  (3,2 Go, aucune troncature), `Accept-Ranges: bytes`, requête Range → `206
  Partial Content` correct.
- Bucket R2 exposé via un **domaine personnalisé** (`models.example.com`), pas le
  sous-domaine `pub-*.r2.dev` : ce dernier est documenté par Cloudflare comme
  « test uniquement », avec un débit bridé — constaté en pratique (401 après
  quelques téléchargements de test). Un domaine personnalisé connecté à R2
  est nativement public (pas de bouton « autoriser » séparé) et sans cette
  limite. Vérifié : taille exacte (3,2 Go), `Accept-Ranges`, `206 Partial
  Content`, téléchargement complet répété sans erreur.
- Accès **public**, sans jeton R2 : les modèles (embeddings + reranker) sont des
  poids open-source déjà librement téléchargeables sur HuggingFace, donc aucune
  information sensible n'est exposée — distribuer une clé d'accès R2 pour
  protéger un fichier déjà public aurait été contre-productif.

---

## 1.4.1 — Correctif : téléchargement des modèles fiable

- **Cause du téléchargement « bloqué » au 1er lancement identifiée** : les
  requêtes **non authentifiées** vers HuggingFace sont **bridées** (rate-limit),
  un fichier reste « pendu » plusieurs minutes → barre figée (constaté :
  message HF « set a HF_TOKEN to enable higher rate limits »).
- **Durcissement HuggingFace** (repli) : `HF_HUB_DOWNLOAD_TIMEOUT=30` (plus de
  blocage infini) + **boucle de reprise** (les fichiers partiels sont repris).
- **Source Jade (Gitea) prioritaire** (`MODELS_URL`) : au 1er lancement, les
  modèles sont tirés d'une **archive `.tar` hébergée par Jade** au lieu de
  HuggingFace — **une seule requête**, **reprise** sur coupure (HTTP Range),
  **timeouts + retries**. `models_fetch.py`. Repli automatique sur HuggingFace si
  l'archive est indisponible. Validé E2E : download + progression précise +
  extraction + rechargement 100 % hors-ligne + reprise sans corruption.

---

## 1.4.0 — ⭐ Démarrage progressif + installateur protégé

- ⭐ **Écran de démarrage avec progression** : le téléchargement des modèles de
  recherche (au 1er lancement, ~2 Go) et leur chargement ne **bloquent plus** le
  moteur (chargement **paresseux** de l'embedder). L'application affiche une
  **barre de progression + un mini-journal** de ce qui se passe (téléchargement
  Mo / Mo, chargement, démarrage du moteur) jusqu'à « Prêt ». Endpoint
  `GET /api/init`.
- **Correctif du faux message d'erreur au 1er lancement** : le blocage du
  démarrage (téléchargement des modèles) déclenchait un « Backend indisponible —
  indexation initiale en cours ? » trompeur (rien n'est indexé tant qu'aucun
  dossier n'est configuré). Le moteur répond désormais immédiatement.
- **Installateur protégé par mot de passe** (Inno `Encryption=yes`) : si l'exe
  fuite, l'installation exige le mot de passe. Le mot de passe est passé **au
  build** (`ISCC /DSetupPassword=…`), **jamais versionné** ; il est écrit dans le
  `.env` local (`SETUP_PASSWORD`) pour que l'**auto-update reste silencieux**
  (poste : `/PASSWORD=` ; RDS : lu depuis le `.env` installé).

---

## 1.3.1 — Correctif : lancement (`.env` non-UTF-8)

- **Crash au démarrage corrigé** : l'assistant d'installation écrit le `.env` en
  ANSI (cp1252) ; un commentaire contenant des guillemets `« »` faisait échouer
  la lecture UTF-8 (`UnicodeDecodeError`). Le commentaire généré est repassé en
  ASCII **et** le chargement du `.env` tolère désormais un fichier cp1252 (repli
  d'encodage) — un `.env` édité à la main avec des accents ne plante plus.

---

## 1.3.0 — ⭐ Mises à jour automatiques (releases Gitea)

- ⭐ **Détection de mise à jour** côté backend : interroge la dernière *release*
  du dépôt Gitea (`GITEA_API_URL` / `GITEA_REPO`, jeton facultatif) et compare
  en *semver*. Résultat mis en cache 1 h, non bloquant, dégrade proprement hors
  ligne.
- **Poste client** (`UPDATE_MODE=manual`) : un bouton **« Mise à jour
  disponible »** apparaît dans la barre latérale → dialogue qui **télécharge**
  l'installateur (progression) puis le **lance** ; Inno Setup ferme et relance
  Jade.
- **Serveur RDS** (`UPDATE_MODE=scheduled`) : le bouton est masqué ; une **tâche
  planifiée nocturne** (`installer/jade-update-task.ps1`, compte SYSTEM, 01:00)
  applique la mise à jour **hors session** (seulement si aucun utilisateur n'est
  connecté).
- Endpoints : `GET /api/update`, `POST /api/update/download`,
  `GET /api/update/progress`, `POST /api/update/apply`.

---

## 1.2.0 — 🚧 dev : ⭐ Base multiplateforme (Windows · macOS · Linux)

- ⭐ **Portage du backend** vers des solutions communes aux 3 OS (pas de variante
  « grandement différente ») :
  - ouverture fichiers / URL / dossiers portable (`openers.py` : `startfile` /
    `open` / `xdg-open`) ;
  - chemins de données via **`platformdirs`** (mêmes emplacements sous Windows) ;
  - préférences en **JSON** portable (au lieu du registre) ;
  - `security` (DPAPI/EFS), `winmem` : gardes explicites, dégradation propre
    hors Windows ; `ntfs` déjà portable (basé sur `open()`).
  - nom d'utilisateur via `getpass` en repli.
- **Runners Flutter macOS + Linux** générés ; `backend.dart` cherche l'exécutable
  backend par plateforme.
- *Reste à faire pour livrer sur macOS/Linux : builds + installateurs natifs
  (`.dmg`, `.deb`/AppImage), à réaliser sur ces OS.*

---

## 1.1.0 — 🚧 dev : logo spirale + animation

- ⭐ **Logo** : retour au **logo spirale** de Jade partout (application, icône
  .exe / barre des tâches, installateur, dépôt). La gemme bleue est retirée.
- **Animation de génération** : le logo **tourne** pendant que Jade réfléchit /
  répond (respecte « réduire les animations »).

---

## 1.0.0 — Première version stable

Assistant documentaire interne « local d'abord » : Jade indexe les documents de
l'entreprise sur le poste/serveur du client, répond en citant ses sources, et
**n'envoie jamais les documents à l'extérieur** (seuls la question et de courts
extraits transitent, chiffrés, vers le serveur d'inférence Jade).

**Interface — application native**
- Application **Windows native (Flutter)** : barre latérale (conversations,
  dossiers, recherche, épingles), fil de conversation en streaming, panneau
  Sources, cartes de fichiers.
- Identité soignée : police **Geomini**, icônes **Tabler**, marque « gemme »
  bleu Jade, thème clair / sombre / automatique.
- **Page Réglages** : dossiers à indexer (protégée par mot de passe admin), état
  de l'index et réindexation ; suppression de tout l'historique et de la mémoire.

**Intelligence & recherche**
- **Pré-analyse par un petit modèle** avant chaque question : décide *documents
  internes / web / réponse directe* et détecte un éventuel fichier à créer.
- Architecture **3 niveaux** (petit / standard / performant) selon la complexité.
- **Recherche hybride + reranking** : vectoriel (`multilingual-e5-large`) + BM25,
  fusion RRF, puis cross-encoder multilingue (`jina-reranker-v2`).
- **Suggestions d'accueil personnalisées** d'après l'historique, et **questions
  de suivi** après chaque réponse — générées par le petit modèle (économe).

**Contenus**
- **Création de fichiers** à la demande : Word, Excel, PDF, PowerPoint, CSV,
  Texte, Markdown, HTML.
- **Recherche web** encadrée (SearXNG interne, repli DuckDuckGo), déclenchée
  seulement quand c'est utile.
- **Pièces jointes** analysées localement ; **mémoire** inter-conversations locale.
- **Sans dossier indexé**, Jade fonctionne comme un assistant général (web +
  connaissances + création de fichiers).

**Sécurité**
- Rien ne sort du poste sauf la question + extraits (journalisés avant envoi).
- Chiffrement au repos (conversations DPAPI, index EFS), filtrage des droits
  NTFS par utilisateur, télémétrie désactivée.
- Installateur chiffré (AES-256) protégé par mot de passe.

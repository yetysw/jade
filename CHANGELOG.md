# Journal des versions — Jade

Versionnage **sémantique** `MAJEUR.MINEUR.CORRECTIF` :
- **MAJEUR** : refonte ou rupture de compatibilité ;
- **MINEUR** : nouvelles fonctionnalités ;
- **CORRECTIF** : corrections de bugs.

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

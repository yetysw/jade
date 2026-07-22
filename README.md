<div align="center">
  <img src="docs/logo.png" width="96" alt="Jade" />

  # Jade

  **Assistant documentaire d'entreprise, « local d'abord »**

  ![Version](https://img.shields.io/badge/version-1.1.0-00357F)
  ![Plateforme](https://img.shields.io/badge/Windows-10%2F11-informational)
  ![UI](https://img.shields.io/badge/interface-Flutter%20native-blue)
  ![Licence](https://img.shields.io/badge/licence-Jade%20S%C3%A0rl-lightgrey)
</div>

Jade indexe les documents d'une entreprise sur le poste ou le serveur du client,
répond aux questions en citant ses sources, et **n'envoie jamais les documents à
l'extérieur** : seuls la question et de courts extraits de texte transitent, en
HTTPS chiffré, vers le serveur d'inférence Jade (Ollama, via Cloudflare Tunnel
+ Access).

> 🔐 **Aucun secret dans ce dépôt.** Les identifiants (jetons Cloudflare, mots de
> passe) sont saisis par le technicien pendant l'installation, ou renseignés dans
> un `.env` local en développement (voir `.env.example`).

---

## Comment ça fonctionne

```
┌─────────────────── Poste / serveur RDS du client ───────────────────┐
│                                                                      │
│   Application native (Flutter Windows)   ← flutter_app/              │
│        │  interface : conversations, streaming, sources, fichiers    │
│        ▼  HTTP + SSE, en local uniquement                            │
│   Backend local (FastAPI)  ── 127.0.0.1:8765 ──  ragagent/          │
│     • indexation locale (ChromaDB + fastembed CPU, BM25)             │
│     • recherche hybride + reranking     • création de fichiers       │
│     • mémoire locale     • conversations chiffrées     • accès NTFS   │
│                                                                      │
└───────────┬──────────────────────────────────────────┬─────────────┘
   question +│  HTTPS + Cloudflare Access (service token) │ question seule
   extraits  ▼                                            ▼
      llm.example.com (Ollama / AI01, RTX 2000 Ada)     search.example.com
```

- **Interface et backend sont séparés.** L'application **Flutter native**
  (`flutter_app/`) ne fait que l'interface ; toute l'intelligence (indexation,
  recherche, sécurité, génération) vit dans le **backend local** (`ragagent/`),
  une API qui n'écoute que sur `127.0.0.1`.
- Au premier lancement, l'application démarre le backend s'il est installé à côté
  d'elle, puis s'y connecte.
- **Rien ne sort du poste** sauf la question et de courts extraits — journalisés
  avant envoi dans `logs/outbound.jsonl`. Pas de cloud tiers, pas d'API IA externe.

## Fonctionnalités

- **Intelligence** : une **pré-analyse** (petit modèle) décide à chaque question
  entre *documents internes / recherche web / réponse directe*, et détecte un
  éventuel fichier à créer. Trois niveaux de modèles (petit / standard /
  performant) selon la complexité.
- **Recherche hybride + reranking** : vectoriel (`multilingual-e5-large`,
  CPU/ONNX) + BM25, fusion RRF, puis cross-encoder multilingue (`jina-reranker-v2`).
- **Formats indexés** : `.docx .xlsx .xls .pdf .txt .md .csv .html .odt .eml .msg`
  (`.pst` best-effort). OCR local (RapidOCR) pour images et PDF scannés —
  **optionnel** (`pip install .[ocr]`), non inclus dans l'installateur léger.
- **Création de fichiers** à la demande : Word, Excel, PDF, PowerPoint, CSV,
  Texte, Markdown, HTML.
- **Recherche web** encadrée (SearXNG interne, repli DuckDuckGo), sur intention
  explicite ou quand les documents ne répondent pas.
- **Suggestions d'accueil personnalisées** (d'après l'historique) et **questions
  de suivi** après chaque réponse.
- **Conversations** : multi-tours, dossiers, épingles, titres générés par IA,
  recherche dans le contenu, export Word. **Mémoire** inter-conversations locale.
- **Réglages** : dossiers à indexer (mot de passe admin), réindexation,
  suppression de tout l'historique. **Sans dossier indexé**, Jade répond comme un
  assistant général (web + connaissances).
- **Sécurité** : chiffrement au repos (conversations DPAPI, index EFS),
  filtrage des droits NTFS par utilisateur au moment de la recherche.
- **Confort** : mode incognito, thème clair / sombre / **auto**, multi-utilisateur
  (conversations isolées par session), interface française.

## Prérequis

- Windows 10/11 (x64).
- Accès réseau sortant HTTPS vers `llm.example.com` et `search.example.com`.
- Pour le **développement** : Python **3.12+** et le **SDK Flutter** (canal stable,
  desktop Windows activé).

## Installation (poste client)

Utiliser l'installateur `Jade-Setup-1.1.0.exe` (voir *Build* plus bas).
**Aucun secret n'est embarqué dans l'installateur** : pendant l'installation,
l'assistant demande les **identifiants d'accès Jade** (adresse du serveur LLM,
jetons Cloudflare Access, éventuel SearXNG) et le **mot de passe administrateur**.
Ils sont écrits dans un fichier `.env` **local au poste** — rien ne sort, rien
n'est distribué avec l'exe.

- Installe l'application dans `C:\Program Files\Jade`.
- Pose l'index partagé, les journaux et le cache de modèles dans
  `C:\ProgramData\Jade` (inscriptible par tous les utilisateurs du serveur).
- Les conversations de chaque utilisateur restent dans `%LOCALAPPDATA%\Jade`.
- Les **modèles de recherche locaux** (embeddings + reranker) sont **téléchargés
  automatiquement au premier lancement** dans `C:\ProgramData\Jade\models`
  (connexion Internet requise la première fois). L'installateur reste léger
  (~90 Mo). *Note : l'OCR des documents scannés/images n'est pas inclus dans
  cette version légère.*

Au premier démarrage, l'index est vide : ouvrir les **Réglages** (roue crantée →
mot de passe admin) et ajouter les dossiers / lecteurs réseau à indexer.

## Mot de passe administrateur

Le mot de passe des **Réglages** (roue crantée → ajout/retrait de dossiers,
réindexation) est **défini par le technicien pendant l'installation**. En
développement, il se règle via `SETTINGS_PASSWORD` dans le `.env`.

## Configuration

La configuration vit dans un fichier **`.env`** :
- **En développement** : copier `.env.example` en `.env` et renseigner les
  identifiants (`copy .env.example .env`).
- **En installé** : le fichier est **généré automatiquement par l'assistant
  d'installation** (à côté de l'exécutable), à partir des identifiants saisis.

**Aucun secret n'est versionné dans le dépôt.** Principales clés :

| Clé | Rôle |
|-----|------|
| `OLLAMA_URL`, `OLLAMA_MODEL`, `ROUTER_MODEL`, `STRONG_MODEL` | LLM central (3 niveaux) |
| `CF_ACCESS_CLIENT_ID/SECRET` | service token Cloudflare Access du LLM |
| `SEARXNG_URL` + `SEARXNG_CF_ACCESS_CLIENT_ID/SECRET` | recherche web interne |
| `EMBED_MODEL`, `RERANK_ENABLED` | embeddings / reranker |
| `SETTINGS_PASSWORD` | mot de passe des réglages (admin) |
| `NTFS_FILTER` | filtrage des droits NTFS par utilisateur |
| `REINDEX_MINUTES` | réindexation automatique périodique |

## Développement

```bash
# 1) Backend local (API)
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env   # puis renseigner les identifiants
jade check       # vérifie embeddings, store local, accès LLM
jade serve       # backend sur http://127.0.0.1:8765

# 2) Application native (dans un autre terminal)
cd flutter_app
flutter run -d windows
```

## Build

```bash
# 1) Application native  ->  flutter_app/build/windows/x64/runner/Release/
cd flutter_app
flutter build windows --release

# 2) Backend gelé (sidecar)  ->  dist/Jade/
python -m PyInstaller jade.spec --noconfirm

# 3) Installateur  ->  dist/installer/
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\jade.iss
```

- `jade.spec` : recette PyInstaller du backend.
- `installer/jade.iss` : script Inno Setup — **assistant** qui demande les
  identifiants pendant l'installation et écrit le `.env` local (aucun secret
  embarqué dans l'exe, aucun secret versionné).

> Non fait à ce stade : **signature de code** (SmartScreen affichera « éditeur
> inconnu »), service Windows d'indexation, auto-update.

## Structure

```
flutter_app/       application native (Flutter Windows) — l'interface
  lib/               écrans, thème, design system, client HTTP/SSE
  assets/fonts/      polices embarquées (Geomini, Tabler Icons)
ragagent/          backend (API pure)
  web/app.py         endpoints FastAPI + orchestration RAG
  ingest/            parsing multi-format + indexation incrémentale
  rag.py, hybrid.py  retrieval hybride, BM25, fusion RRF, reranker
  router.py          pré-analyse (routage documents/web/direct)
  memory.py          mémoire inter-conversations (locale)
  chat_store.py      conversations SQLite chiffrées (DPAPI)
  ntfs.py            filtrage des droits NTFS par utilisateur
  filegen.py         création de fichiers (docx/xlsx/pdf/pptx/…)
jade.spec          build PyInstaller du backend
installer/         script Inno Setup (assistant qui écrit le .env local)
.env.example       modèle de configuration (sans secret) à copier en .env
```

## Sécurité — comment la démontrer

1. Chaque appel HTTP sortant est journalisé **avant émission** dans
   `logs/outbound.jsonl` (secret Cloudflare masqué) : seul du texte (question +
   extraits) part vers `OLLAMA_URL` / `SEARXNG_URL`.
2. Télémétrie ChromaDB désactivée ; embeddings 100 % locaux (ONNX CPU).
3. Conversations chiffrées au repos (DPAPI, clé liée au compte Windows).
4. Le backend refuse de s'exposer au-delà de `127.0.0.1`.

## Licence

Logiciel interne Jade Sàrl. Tous droits réservés.

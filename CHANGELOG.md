# Journal des versions — Jade

Versionnage **sémantique** `MAJEUR.MINEUR.CORRECTIF` :
- **MAJEUR** : refonte ou rupture de compatibilité ;
- **MINEUR** : nouvelles fonctionnalités ;
- **CORRECTIF** : corrections de bugs.

---

## 1.4.0 — 🚧 dev : ⭐ Démarrage progressif + installateur protégé

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

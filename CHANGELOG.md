# Journal des versions — Jade

Versionnage **sémantique** `MAJEUR.MINEUR.CORRECTIF` :
- **MAJEUR** : refonte ou rupture de compatibilité ;
- **MINEUR** : nouvelles fonctionnalités ;
- **CORRECTIF** : corrections de bugs.

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

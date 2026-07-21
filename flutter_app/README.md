# Jade — application native (Flutter Windows)

Interface de bureau de Jade. Toute la logique documentaire (RAG, indexation,
sécurité, création de fichiers) vit dans le backend local Python
([`../ragagent`](../ragagent)) ; cette application ne fait que l'interface et
s'y connecte sur `127.0.0.1:8765` (elle démarre le backend en sidecar si elle
est installée à côté).

## Développement

```bash
# backend dans un premier terminal (voir README racine)
jade serve

# application dans un second terminal
flutter run -d windows
```

## Build

```bash
flutter build windows --release
# -> build/windows/x64/runner/Release/jade.exe
```

## Structure

```
lib/
  main.dart           démarrage (attente du backend) + thème clair/sombre/auto
  home.dart           écran principal : barre latérale, conversations, dossiers
  chat.dart           fil de conversation : streaming SSE, markdown, citations
  sources_panel.dart  panneau Sources (extraits cités, ouverture d'un clic)
  settings.dart       réglages : dossiers à indexer (admin), données utilisateur
  design.dart         système de design : espacements, typographie, rayons…
  theme.dart          palette sémantique (bleu Jade / vert jade)
  tabler.dart         icônes Tabler embarquées (police d'icônes)
  api.dart            client HTTP/SSE du backend
  backend.dart        démarrage/surveillance du backend sidecar
  models.dart         modèles de données (miroir de l'API)
assets/fonts/         polices embarquées (Geomini, Tabler Icons)
```

Le système de design est documenté dans `.claude/skills/jade-ui-design` :
aucune valeur visuelle codée en dur, tout vient de `design.dart` / `theme.dart`.

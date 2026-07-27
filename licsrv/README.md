# Serveur de licences Jade (`licsrv`)

> Composant **interne Jade**, **jamais livré** aux clients ni embarqué dans
> l'installateur. À héberger côté Jade (même VM que SearXNG/AI01 ou séparée).

FastAPI + SQLite. Chaque client détient une clé opaque `LICENSE_KEY` ; le serveur
vérifie l'abonnement et renvoie un **JWT Ed25519** court (« bail ») que le client
Jade vérifie **hors ligne** (clé publique embarquée) avec période de grâce. Le
kill-switch dur reste la **révocation du service token Cloudflare** du client.

## Installation

```bash
python -m venv .venv && . .venv/Scripts/activate   # (ou source .venv/bin/activate)
pip install -r licsrv/requirements.txt
```

## 1) Générer la paire de clés (une fois)

```bash
python -m licsrv.keys
```
- Crée la clé **privée** dans `licsrv/keys/license_ed25519.pem` — **ne jamais
  versionner ni distribuer** (déjà gitignore).
- Affiche la clé **publique** PEM → à embarger dans le client Jade
  (`LICENSE_PUBLIC_KEY`, à l'intégration côté `ragagent`).

## 2) Créer / gérer des clients (CLI locale, hors réseau)

```bash
python -m licsrv.manage add "Cabinet Durand" --plan monthly       # affiche la clé UNE fois
python -m licsrv.manage extend <id> --months 1                    # « prolonger d'un mois »
python -m licsrv.manage revoke <id>                               # suspendre
python -m licsrv.manage reactivate <id>
python -m licsrv.manage list
```

## Déploiement recommandé : Docker (un conteneur, deux ports)

Le conteneur lance **deux serveurs** dans un seul processus (`licsrv.serve`) :

| Port | Rôle | Exposition |
|------|------|-----------|
| **8790** | API publique — `POST /api/verify` (les postes clients) | derrière **Cloudflare Tunnel + Access** |
| **8791** | **Web-UI d'administration** + API de gestion | **local uniquement** (127.0.0.1) |

```bash
cd licsrv
# (facultatif mais recommandé) protéger la web-UI :
#   copier .env.example en .env et definir LICSRV_ADMIN_TOKEN
docker compose up -d --build
```

- La base `licenses.db` et la clé privée vivent dans `licsrv/data/` (volume `/data`),
  **jamais dans l'image**. Générées automatiquement au premier lancement.
- Récupérer la **clé publique** à embarquer côté client (`LICENSE_PUBLIC_KEY`) :
  ```bash
  docker compose exec licsrv python -m licsrv.keys
  ```
- **Web-UI** : `http://127.0.0.1:8791/`. Accès distant : tunnel SSH
  `ssh -L 8791:127.0.0.1:8791 user@serveur`, puis ouvrir `http://127.0.0.1:8791`.
- Exposer **seulement 8790** publiquement, via un Cloudflare Tunnel protégé par un
  **service token Access dédié** (comme SearXNG). Ne JAMAIS exposer 8791.

### Web-UI d'administration

Une page unique, sans dépendance : lister les licences, en **créer** (la clé en
clair s'affiche une fois), **prolonger** (+1 mois), **révoquer** / **réactiver**.
C'est l'équivalent visuel de `licsrv.manage`. Cycle Odoo :
facture émise → *Créer* ; renouvellement → *+1 mois* ; non-paiement → *Révoquer*.

## Alternative sans Docker

```bash
python -m licsrv.serve      # lance les deux ports (8790 public, 8791 admin)
# ou l'API publique seule :
uvicorn licsrv.app:app --host 127.0.0.1 --port 8790
```

## Sécurité / exploitation

- **Aucune PII** en base (juste un libellé libre). Le secret client est **haché**
  (PBKDF2) : une fuite de la base ne donne aucune clé utilisable.
- Réponse d'erreur **constante** (`403 invalid`) sur `/api/verify` → pas d'oracle
  d'énumération.
- **Web-UI d'admin uniquement en local** (port publié sur 127.0.0.1). Protection
  facultative supplémentaire par `LICSRV_ADMIN_TOKEN` (en-tête `X-Admin-Token`,
  la page le demande et le mémorise).
- **Sauvegarder** `data/licenses.db` **et** `data/keys/license_ed25519.pem` (perte
  de la clé privée = toutes les licences à re-signer / re-déployer la publique).
- L'app admin écoute par défaut sur **`127.0.0.1`** (variable `LICSRV_ADMIN_HOST`) :
  une exécution **bare-metal** n'expose donc jamais l'admin au réseau par accident.
  L'image Docker force `LICSRV_ADMIN_HOST=0.0.0.0` (nécessaire au forwarding), et
  l'exposition reste bornée par le mapping hôte `127.0.0.1:8791:8791` du compose.
- Variables d'environnement : `LICSRV_DB`, `LICSRV_PRIVATE_KEY`, `LICSRV_ISSUER`,
  `LICSRV_BAIL_DAYS` (défaut 14), `LICSRV_PUBLIC_PORT` (8790), `LICSRV_ADMIN_PORT`
  (8791), `LICSRV_PUBLIC_HOST` (défaut `0.0.0.0`), `LICSRV_ADMIN_HOST` (défaut
  `127.0.0.1`), `LICSRV_ADMIN_TOKEN` (vide = pas de contrôle ; recommandé si l'admin
  n'est pas strictement en loopback).

## Intégration client

Faite (Jade ≥ 1.8.0) : `ragagent/licensing.py` vérifie l'abonnement au démarrage +
périodiquement, valide le JWT **hors ligne**, tolère les coupures (grâce), et
expose l'état via `/api/status` + `/api/license`. Runbook d'exploitation complet
(facturation manuelle Odoo) : [`docs/deploiement-licences.md`](../docs/deploiement-licences.md).

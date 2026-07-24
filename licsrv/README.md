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

## 3) Lancer l'API (face client)

```bash
uvicorn licsrv.app:app --host 127.0.0.1 --port 8790
```
Puis exposer `127.0.0.1:8790` via un **Cloudflare Tunnel protégé par Access**
(service token), comme SearXNG. Seul `POST /api/verify` est utile côté client.

## Sécurité / exploitation

- **Aucune PII** en base (juste un libellé libre). Le secret client est **haché**
  (PBKDF2) : une fuite de la base ne donne aucune clé utilisable.
- Réponse d'erreur **constante** (`403 invalid`) → pas d'oracle d'énumération.
- **CLI d'admin uniquement en local** (pas d'endpoint admin exposé).
- **Sauvegarder** `licenses.db` **et** `keys/license_ed25519.pem` (perte de la clé
  privée = toutes les licences à re-signer / re-déployer la publique).
- Réglages via variables d'environnement : `LICSRV_DB`, `LICSRV_PRIVATE_KEY`,
  `LICSRV_ISSUER`, `LICSRV_BAIL_DAYS` (défaut 14).

## Intégration client (à faire, décisions requises)

Module `ragagent/licensing.py` (calqué sur `updater.py`) : refresh threadé + cache
+ vérif JWT hors ligne + grâce, branché dans `_background_loop`, exposé via
`/api/status` + `/api/license`, blocage propre à l'expiration. Voir le plan de
`architect-plan` et les décisions ouvertes (bail, grâce, blocage, cache, CF token
dédié, télémétrie).

# Licensing

Licensing is optional and off by default (`LICENSE_ENABLED=0`). Without it, the kill switch for a customer is the revocation of their Cloudflare service token. With it, you manage subscriptions: extend or suspend a customer, and the app shows a clear message at the end of a term.

## How it works

`licsrv` is a small FastAPI and SQLite server that you host, behind Cloudflare Access like the inference server. It gives each customer a short Ed25519 JWT (a lease, 14 days by default). jade checks it offline with the public key, and caches it. If the server is unreachable, jade keeps working until the lease plus `GRACE_DAYS` (7). The server only knows opaque IDs, no personal data.

States: `off`, `active`, `grace`, `expired`, `suspended`. In the last two, sending questions is blocked and the history stays readable.

`licsrv` is for you, not for customers: do not ship it in the installer.

## Set up the server

```bash
pip install -r licsrv/requirements.txt
python -m licsrv.keys          # creates the private key, prints the public key
python -m licsrv.serve         # public API on 8790, admin on 8791
```

Or with Docker: `cd licsrv && docker compose up -d --build`. Port 8790 (`POST /api/verify`) goes behind a Cloudflare Tunnel with a dedicated Access service token. Port 8791 (admin web page and API) listens on `127.0.0.1` and must never be exposed. Set `LICSRV_ADMIN_TOKEN` to protect it. The ports and hosts come from `LICSRV_PUBLIC_PORT`, `LICSRV_ADMIN_PORT`, `LICSRV_PUBLIC_HOST` and `LICSRV_ADMIN_HOST`.

Back up `licenses.db` and the private key. Never commit them.

## Manage customers

```bash
python -m licsrv.manage add "Customer name" --plan monthly   # prints the key once
python -m licsrv.manage extend <id> --months 1
python -m licsrv.manage revoke <id>
python -m licsrv.manage reactivate <id>
python -m licsrv.manage list
```

## Turn it on in a client `.env`

```ini
LICENSE_ENABLED=1
LICENSE_URL=https://license.example.com
LICENSE_KEY=<the key printed by "add">
LICENSE_CF_ACCESS_CLIENT_ID=<dedicated service token>
LICENSE_CF_ACCESS_CLIENT_SECRET=<dedicated service token>
LICENSE_PUBLIC_KEY=<public key of your server>
GRACE_DAYS=7
```

!!! warning
    The public key embedded in `ragagent/config.py` is a development key. Use your own pair in production.

The state is available at `/api/license` and shows as a banner in the app.

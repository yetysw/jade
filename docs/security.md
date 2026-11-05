# Security

## What jade protects

- **Documents stay on the machine.** Only the question and short excerpts of text go to your inference server, over HTTPS with a Cloudflare Access service token. Web search sends the question to your SearXNG, or to DuckDuckGo if none is set.
- **Every outbound call is logged first.** Each HTTP call is written to `%LOCALAPPDATA%\Jade\logs\outbound.jsonl` before it is sent, with the Cloudflare headers masked. Open it to check what leaves.
- **No telemetry, no cloud API.** ChromaDB telemetry is off and the embeddings run on the CPU, locally.
- **Local API only.** The backend refuses to bind anything but loopback, rejects non-loopback `Host` headers (DNS rebinding) and requires a per-session token.
- **Encryption at rest on Windows.** Conversations use DPAPI with the user's account key. The data folders are marked for EFS.
- **NTFS rights** are applied to each search, with the rights of the user who asks.
- **Secrets in `.env`** are sealed with DPAPI at machine scope. The file ACL gives `Users` modify rights, because the backend runs without elevation.
- **Formula injection.** Excel and CSV files created by jade neutralise cells that start like a formula.

## What it does not protect

- **Local processes on the same machine can decrypt the sealed secrets.** On an RDS server, a standard user can copy `backend\.env` and decrypt the secrets. This does not expose another user's documents, but it gives access to the Cloudflare gateway outside jade.
- **Limit the damage.** Restrict the Cloudflare service token to the hosts jade needs, rotate it, and watch for use from elsewhere. A stronger setup (a dedicated service account and a privileged relay) is not built.
- **The excerpts are sent in clear to your server** (inside HTTPS). Trust it as you trust the document store.
- **Outside Windows** conversations and secrets are stored without encryption.
- **Backups are not encrypted** (`.jadebak`).
- **The installer is not code-signed.**

## Verify it yourself

1. Use jade, then read `outbound.jsonl`: only text for `OLLAMA_URL`, `SEARXNG_URL` and the web pages appears.
2. Check that the backend only listens on loopback (`netstat -ano`).
3. Read the `.env`: secrets start with `dpapi-m:`.

## Report a vulnerability

See [SECURITY.md](https://github.com/yetysw/jade/blob/main/SECURITY.md).

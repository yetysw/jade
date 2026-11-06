# Ports and paths

## Port

The backend listens on `127.0.0.1` only. With `UI_PORT=auto` (the installer default) it picks a free port at each start, and writes it with a session token to `backend.json` in the user's data folder. The interface reads that file. In development, `jade serve` uses port `8765`.

Every `/api/*` call needs the `X-Jade-Token` header, and a request whose `Host` is not loopback is refused with 421.

Outbound, jade opens HTTPS connections to `OLLAMA_URL`, `SEARXNG_URL`, `LICENSE_URL`, `GITEA_API_URL` and `MODELS_URL`, and to the web pages it reads for web search.

## Paths on Windows

| Path | Content |
|---|---|
| `C:\Program Files\Jade` | Interface |
| `C:\Program Files\Jade\backend\.env` | Configuration, secrets sealed |
| `C:\ProgramData\Jade\data` | Shared index (`chroma`, `manifest.db`, `index_roots.json`) |
| `C:\ProgramData\Jade\logs` | `jade.log` (2 MB, 2 backups) |
| `C:\ProgramData\Jade\models` | Search models |
| `C:\ProgramData\Jade\license.jwt`, `license.state.json` | Licence cache, when licensing is on |
| `%LOCALAPPDATA%\Jade\chats.db` | Conversations, encrypted per user |
| `%LOCALAPPDATA%\Jade\memory.db` | Memory across conversations |
| `%LOCALAPPDATA%\Jade\backend.json` | Port and session token |
| `%LOCALAPPDATA%\Jade\logs\outbound.jsonl` | Log of outbound calls |
| `%LOCALAPPDATA%\Jade\sauvegardes` | Backups (`.jadebak`) |
| `%LOCALAPPDATA%\Jade\diagnostics` | Diagnostic zips |
| `%LOCALAPPDATA%\Jade\attachments` | Attachments |
| `Documents\Jade` | Files created by jade and Word exports |

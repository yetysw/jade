# Configuration

jade reads a `.env` file. In development, copy `.env.example` to `.env`. On an installed machine the wizard writes `backend\.env` next to the backend executable. The defaults live in `ragagent/config.py`. A secret left empty switches off the matching feature.

These keys are sealed with DPAPI (machine scope) by `jade seal-env`: `CF_ACCESS_CLIENT_SECRET`, `SEARXNG_CF_ACCESS_CLIENT_SECRET`, `LICENSE_CF_ACCESS_CLIENT_SECRET`, `LICENSE_KEY`, `GITEA_TOKEN`, `SETUP_PASSWORD`. Values already sealed or empty are left alone.

Booleans are false for `0`, `false` or an empty value.

## Folders

| Key | Default | Meaning |
|---|---|---|
| `DOCS_DIR` | `.\testdata` in dev, `<ProgramData>\Jade\documents` installed | Fallback folder to index when none was configured in the app |
| `DATA_DIR` | `.\data`, installed `<ProgramData>\Jade\data` | Index (`chroma`), manifest, folder list |
| `LOG_DIR` | `.\logs`, installed `<ProgramData>\Jade\logs` | `jade.log` |
| `MODEL_CACHE_DIR` | `.\models`, installed `<ProgramData>\Jade\models` | Search models |

Relative paths are resolved from the project root, or from the folder of the backend executable when installed.

## Search

| Key | Default | Meaning |
|---|---|---|
| `EMBED_MODEL` | `intfloat/multilingual-e5-large` | Embedding model. Changing it forces a full reindex |
| `CHUNK_TOKENS` / `CHUNK_OVERLAP` | `400` / `60` | Chunking |
| `TOP_K` / `MIN_SCORE` | `10` / `0.35` | Candidates and relevance threshold |
| `HYBRID_ENABLED` | `1` | Add BM25 to vector search |
| `RERANK_ENABLED` | `1` | Cross-encoder reranking |
| `RERANK_MODEL` | `jinaai/jina-reranker-v2-base-multilingual` | Reranker |
| `CPU_THREADS` | `2` | ONNX threads, kept low for shared servers |
| `REINDEX_MINUTES` | `30` | Automatic reindex period |
| `NTFS_FILTER` | `1` | Filter excerpts by the user's file rights |
| `OCR_ENABLED` / `OCR_INDEX` | `1` / `1` | Local OCR, needs the `ocr` extra |

## Inference server

| Key | Default | Meaning |
|---|---|---|
| `OLLAMA_URL` | `https://llm.example.com` | Ollama server (placeholder: set your own) |
| `OLLAMA_MODEL` | `qwen3.5:4b` | Standard model |
| `ROUTER_MODEL` | empty (uses `OLLAMA_MODEL`) | Small model for the first pass |
| `STRONG_MODEL` | empty (uses `OLLAMA_MODEL`) | Model for complex questions |
| `VISION_MODEL` | `qwen3.5:9b` | Multimodal model for images |
| `NUM_CTX` | `8192` | Context size |
| `REQUEST_TIMEOUT` | `120` | Seconds |
| `KEEP_ALIVE` | `30m` | How long the model stays loaded |
| `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` | empty | Cloudflare Access service token |

## Web search

| Key | Default | Meaning |
|---|---|---|
| `WEB_FALLBACK` | `1` | Allow web search when documents do not answer |
| `WEB_RESULTS` | `3` | Number of results |
| `SEARXNG_URL` | empty | Your SearXNG. Empty means DuckDuckGo |
| `SEARXNG_CF_ACCESS_CLIENT_ID` / `SEARXNG_CF_ACCESS_CLIENT_SECRET` | empty | Service token for SearXNG |

## Local API and interface

| Key | Default | Meaning |
|---|---|---|
| `UI_HOST` | `127.0.0.1` | Only `127.0.0.1`, `localhost` and `::1` are accepted. Anything else is refused |
| `UI_PORT` | `8765` in code, `auto` in the installer and `.env.example` | `auto` picks a free port per session |
| `CLIENT_NAME` | `Jade` | Label used in the feedback subject |
| `FEEDBACK_EMAIL` | `feedback@example.com` | Recipient of feedback mail (placeholder: set your own) |

## Updates and models archive

| Key | Default | Meaning |
|---|---|---|
| `UPDATE_ENABLED` | `1` | Check for updates |
| `UPDATE_MODE` | `manual` | `manual` shows a button, `scheduled` hides it (RDS) |
| `GITEA_API_URL` | `https://git.example.com` | Gitea that publishes releases (placeholder) |
| `GITEA_REPO` | `example/jade` | `owner/repo` (placeholder) |
| `GITEA_TOKEN` | empty | Read token for a private repository |
| `SETUP_PASSWORD` | empty | Installer password, so silent updates work |
| `MODELS_URL` | `https://models.example.com/jade-models.tar` | Archive of the models (placeholder) |
| `MODELS_SHA256` | empty | Expected SHA-256 of the archive, checked before extraction |

## Licensing

See [Licensing](licensing.md): `LICENSE_ENABLED` (`0`), `LICENSE_URL`, `LICENSE_KEY`, `LICENSE_PUBLIC_KEY`, `LICENSE_CF_ACCESS_CLIENT_ID`, `LICENSE_CF_ACCESS_CLIENT_SECRET`, `GRACE_DAYS` (`7`).

!!! note
    The defaults for the inference, search, update and models addresses are placeholders on `example.com`. Set every one you use.

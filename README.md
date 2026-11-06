<div align="center">

<a href="https://www.yety.ch"><img src=".github/assets/banner.svg" alt="jade: a local-first document assistant for Windows" width="100%"></a>

<h3>A document assistant that indexes your files on your own PC and answers with its sources.</h3>

[Website](https://www.yety.ch) · [Documentation](docs/index.md) · [Sponsor](https://github.com/sponsors/yetysw)

[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat)](LICENSE)

</div>

## Overview

- jade indexes the documents of a company on the user's PC or on the company's server, then answers questions in French and cites the passages it used.
- The documents never leave the machine. Only the question and a few short text excerpts go out, over HTTPS, to the inference server you configure (Ollama behind Cloudflare Access). Every outbound call is logged before it is sent.
- It is a native Windows app (Flutter) that starts a local backend (Python, FastAPI) listening on `127.0.0.1` only.

MIT licence. An optional licence server is included and off by default: see [Licensing](docs/licensing.md).

## Quick start

jade ships as a Windows installer. There is no Docker image: it is a desktop app.

1. Get the installer, `Jade-Setup-<version>.exe`. There are no GitHub releases yet: build it from source ([Building](docs/building.md)) or ask whoever runs your jade server.
2. Run it as administrator. The wizard asks for the address of the inference server, the Cloudflare Access client ID and secret, and optionally the address of a SearXNG search service. They are written to a local `.env`, never into the installer.
3. Start jade. On the first launch it downloads the search models (about 3.2 GB, once) into `C:\ProgramData\Jade\models`, then asks you to accept the terms.
4. Open the settings (gear icon), add the folders or network drives to index, and ask a question.

Where things are stored, and how to back up your conversations: [Install](docs/install.md), [Back up and restore](docs/backup.md).

## What it does

- Hybrid search: vectors (`multilingual-e5-large`, on CPU) plus BM25, merged with RRF, then reranked by a cross-encoder (`jina-reranker-v2`).
- Indexes `.docx .xlsx .xls .pdf .txt .md .csv .html .htm .odt .eml .msg` and, best effort, `.pst`. Local OCR for images and scanned PDFs is optional (`pip install .[ocr]`) and not in the installer.
- Three modes, chosen on the home screen or left to automatic: your documents, web search, create a file.
- Creates Word, Excel, PDF, PowerPoint, CSV, text, Markdown and HTML files in `Documents\Jade`.
- Conversations with folders, pins, search, Word export and a local memory across conversations. An incognito mode keeps nothing.
- Respects NTFS rights: a user never gets an excerpt of a file they cannot read.
- Update check against the latest release of a Gitea repository you configure: a button on workstations, a nightly scheduled task on RDS servers.
- Optional licence server for subscriptions ([Licensing](docs/licensing.md)). It is off by default.

## Architecture

The Flutter app (`flutter_app/`) is only the interface. It launches the backend (`ragagent/`) next to it and talks to it over HTTP and SSE on `127.0.0.1`, with a per-session token. The backend does the indexing (ChromaDB, fastembed), the search, the file creation and the calls to the inference server. On an RDS server each session gets its own backend on its own port.

## Limits

- Windows 10 and 11 (x64) only. The code is written to be portable, but there is no macOS or Linux build or installer yet.
- The interface is in French only.
- It needs a reachable inference server. Without one, jade cannot answer.
- The question and short excerpts do leave the PC, by design. Web search sends the question to your SearXNG, or to DuckDuckGo when none is configured.
- The secrets in `.env` are sealed with DPAPI at machine scope, so any local process on the same machine can decrypt them. On a shared RDS server, restrict the Cloudflare service token. Details: [Security](docs/security.md).
- Conversations are encrypted with the Windows account key. A copy of `chats.db` does not move to another machine: use the backup.
- The installer is not code-signed, so SmartScreen shows an unknown publisher.
- No Windows indexing service. The index is rebuilt every 30 minutes by default (`REINDEX_MINUTES`).

## Status

Version 1.10.1, in use. The settings, the licence flow and the installer can still change. There is no CI and no published release yet.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities as described in [SECURITY.md](SECURITY.md). Everyone follows the [Code of Conduct](CODE_OF_CONDUCT.md). The full docs are in [`docs/`](docs/index.md).

## License

MIT, see [LICENSE](LICENSE). The software is provided as is, without warranty of any kind. The Geomini font is under SIL OFL 1.1 and the Tabler icons are under MIT.

## Support jade

jade is open source. If it saves you time, you can support its development:

[Sponsor us on GitHub](https://github.com/sponsors/yetysw), recurring or one-off.

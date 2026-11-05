# Install jade

At the end of this page jade is installed on a Windows 10 or 11 (x64) workstation or server.

## Before you start

- An inference server that jade can reach over HTTPS (Ollama, behind Cloudflare Access), and its Cloudflare Access client ID and secret.
- Optionally the address of a SearXNG service for web search.
- About 3.2 GB of free disk space for the search models, downloaded on the first launch.

There is no published installer on GitHub yet. Build `Jade-Setup-<version>.exe` from source ([Building](building.md)), or use the one given to you.

## Install

1. Run the installer as administrator. The default folder is `C:\Program Files\Jade`.
2. On a fresh install the wizard asks for the inference server address, the Cloudflare Access client ID and secret, and the SearXNG address (optional). The same ID and secret are used for the LLM and the web search.
3. Finish the wizard and start jade.

If a protected installer was built with `/DSetupPassword`, the wizard asks for that password.

On an update, or on a silent install, an existing `backend\.env` is kept and the wizard does not ask again.

## What the installer does

- Installs the interface and the backend (`backend\`) in `C:\Program Files\Jade`.
- Creates `C:\ProgramData\Jade` with `data`, `logs` and `models`, writable by all users of the machine. This holds the shared index, the logs and the models.
- Writes `backend\.env` with the values you typed, then seals the secrets with DPAPI (machine scope).
- Adds a Start menu shortcut, and a desktop shortcut if you tick the option.

The conversations of each user stay in that user's `%LOCALAPPDATA%\Jade`.

## Undo

Uninstalling removes `C:\ProgramData\Jade\data`, `logs` and `models` and `backend\.env`. The index is rebuilt on the next install. The conversations in `%LOCALAPPDATA%\Jade` are kept.

## Next

[First run](first-run.md).

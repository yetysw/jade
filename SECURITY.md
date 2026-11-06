# Security policy

jade reads the documents of a company and sends short excerpts to an inference server. We take reports seriously and appreciate the time it takes to write one.

## Supported versions

| Version | Supported |
|---|---|
| `main` | Yes |
| Latest release | Yes |
| Older versions | No, upgrade |

## Report a vulnerability

Do not open a public issue. Use GitHub private vulnerability reporting: the repository's Security tab, then Report a vulnerability, or https://github.com/yetysw/jade/security/advisories/new.

Include the affected component, the steps to reproduce or a proof of concept, the impact as you see it, and the version or commit you tested.

## What to expect

- Acknowledgement within 7 days.
- A first assessment within 14 days.
- A fix on `main`, a new release and a published advisory. Disclosure is coordinated: the advisory stays private until a fix is out.
- Credit in the advisory unless you prefer not to be named.

These are goals, not guarantees. There is no bug bounty.

## Scope

In scope: the local API (token, host check), secret handling (`.env` sealing, `seal-env`), the NTFS filter, what leaves the PC and the outbound log, file creation (formula injection), the updater and installer, the licence flow and `licsrv`.

Out of scope: weaknesses in Windows, Ollama, Cloudflare or SearXNG themselves, attacks that need control of the machine or of the administrator account, and automated scanner output without a demonstrated impact.

Known and documented limits are on the [Security page](docs/security.md), including that sealed secrets can be read by other local processes on a shared server.

## Verifying releases

Releases and signatures are not published yet. When they are, this section will say how to check them.

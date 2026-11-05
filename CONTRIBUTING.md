# Contributing to jade

Thanks for helping. Keep it simple: one topic per pull request.

## Set up

See [Building](docs/building.md): Python 3.12+ for the backend, the Flutter SDK for the interface. Copy `.env.example` to `.env` and never commit it.

## Checks

Before you open a pull request:

```bash
python -m pytest
cd flutter_app && flutter analyze
```

There is no CI yet, so the checks are yours to run.

## Branches and pull requests

- Branch from `main`: `feat/...`, `fix/...`, `docs/...` or `chore/...`. Never push to `main` directly.
- Pull request titles follow Conventional Commits: `fix(updater): handle a missing release`.
- Fill in the template. Interface changes include before and after screenshots, dark and light.
- Sign your commits off (`git commit -s`): this is the Developer Certificate of Origin.

## Conventions

- Backend code and comments are in French, as in the existing code. The interface is in French.
- The interface takes every colour, size and spacing from `flutter_app/lib/theme.dart` and `design.dart`. No colour written in a widget. Status is never shown by colour alone: use an icon and a word. Click targets are at least 40 px. Dark is the default theme.
- A new setting goes in `ragagent/config.py`, `.env.example` and `docs/configuration.md`.
- A bug fix comes with a test that fails without the fix.
- Docs are plain Markdown in `docs/`, in English, with task titles that start with a verb.

## Public repository hygiene

Never commit a secret, a token, a captured document, a real hostname, an address or customer data. Use `example.com` and the documentation address ranges.

## Security

Do not open an issue for a vulnerability. See [SECURITY.md](SECURITY.md).

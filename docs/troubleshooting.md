# Troubleshooting

## The app says the backend is not found

The message is "Backend Jade introuvable". The installed backend is looked for in `backend\Jade.exe` next to the app. In development, run `jade serve`, then reopen the app.

## The local engine does not answer after 60 seconds

Close and reopen the app. If it persists, check the antivirus (it may block `Jade.exe`) or reinstall. Read `C:\ProgramData\Jade\logs\jade.log`.

## The app does not start after install, with `PermissionError` on `.env`

This was fixed in 1.10.1. Make sure you run 1.10.1 or later: the `Users` group needs modify rights on `backend\.env`.

## The first launch is stuck downloading the models

Models are about 3.2 GB. The download resumes after a cut. The default source is the archive at `MODELS_URL`, with HuggingFace as a fallback, which can throttle anonymous downloads. Check the disk space, and set `MODELS_URL` to an archive you host. Host it on object storage that supports Range requests rather than behind a proxy with a short timeout: a download cut near 2 GB is the usual sign of that.

## The health banner is red

The system status panel in the settings shows the cause: inference server unreachable, models not ready, or less than 2 GB free on the data disk. Press refresh after fixing it.

## Answers say nothing about my documents

Check that the folders are listed in the settings and online, that the index has finished, and that the user can read the files (NTFS filtering hides the others). Lower `MIN_SCORE` if too much is filtered out.

## Subscription messages

If a banner says the subscription expired or is suspended, contact whoever runs your jade server. See [Licensing](licensing.md).

## Report a problem

Use the feedback button: it builds a diagnostic zip with no secret and no conversation content.

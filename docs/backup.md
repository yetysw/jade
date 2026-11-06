# Back up and restore

At the end of this page you can move your conversations to another PC.

## Why a copy of `chats.db` is not enough

Conversations are encrypted with a key tied to your Windows account (DPAPI). A copy of the file cannot be read on another machine. Use the backup instead: it exports the history in a portable form and re-encrypts it with the key of the target machine on restore.

## Back up

In the settings, use the backup button. jade writes `jade-sauvegarde-<timestamp>.jadebak` (a zip) into `%LOCALAPPDATA%\Jade\sauvegardes` unless you pick another folder. It holds conversations and folders, and the list of indexed folders for reference.

!!! warning
    The `.jadebak` file is not encrypted. That is why it is not written to `Documents`, which often syncs to OneDrive. Keep it where you would keep any readable copy of your conversations.

## Restore

In the settings, use the restore button and pick the `.jadebak` file. The restore merges: existing conversations are kept. If the file is corrupt, the import is rolled back and nothing is half imported.

## What is not covered

The index is shared and rebuilt from your documents, so it is not part of the backup. The memory and the preferences are not in the backup file either.

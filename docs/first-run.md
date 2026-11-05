# First run

At the end of this page jade answers a question about your own documents.

## Start

jade starts its backend if it is installed next to the app, then waits for it. If the search models are missing, it downloads them (about 3.2 GB, once) into `C:\ProgramData\Jade\models` and shows a progress bar. The download resumes after a cut. By default it comes from the archive at `MODELS_URL`, with HuggingFace as a fallback.

## The welcome screens

1. Accept the terms of use and the privacy policy.
2. Add the folders to index with "Ajouter ce dossier".
3. Optionally tell jade how to call you. You can change it later in the settings.

You can skip the steps that are optional.

## Add folders later

Open the settings (gear icon), add folders or network drives, and start a reindex if you want it now. Indexing is incremental and repeats every `REINDEX_MINUTES` (30 by default). The list of folders is stored in `C:\ProgramData\Jade\data\index_roots.json` and is shared by all users of the server.

Without any indexed folder, jade answers as a general assistant, with web search and its own knowledge.

## Ask

Type a question. jade writes its answer as it goes and lists the sources it used. Click a source to open the file.

See [Ask a question](ask.md) for the modes.

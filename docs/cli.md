# Command line

The backend installs a `jade` command (`pip install -e .`). In the installed app, the frozen backend `Jade.exe serve` does the same job as `jade serve`.

| Command | What it does |
|---|---|
| `jade check` | Checks the embeddings, the local store and the inference server |
| `jade index` | Indexes `DOCS_DIR` incrementally |
| `jade ask "<question>"` | Asks a question from the terminal, needs an index first |
| `jade serve` | Starts the local backend |
| `jade seal-env` | Seals the secrets of the `.env` with DPAPI (machine). Does nothing outside Windows |

`jade ask` takes `--dry-run` (local search only, shows the excerpts without calling the inference server) and `--json`. `jade index` takes `--full` to purge and reindex everything. `--env <file>` before the command loads another `.env`.

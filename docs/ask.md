# Ask a question

At the end of this page you know which mode to use and what jade does with your question.

## Modes

The home screen has three cards. Each one selects a mode, and you write your own question afterwards. The mode stays visible in the conversation and you can go back to automatic in one click.

| Mode | What jade does |
|---|---|
| Your documents | Searches the index and answers from the passages it finds |
| Web search | Searches the web for an up to date answer |
| Create a file | Writes a file for you, see [Create a file](create-files.md) |

In automatic mode, a first pass with a small model decides between your documents, web search and a direct answer, and detects a file to create. Questions that look complex go to the stronger model when `STRONG_MODEL` is set.

## Sources

Every answer from your documents lists numbered sources. They come from a hybrid search (vectors plus BM25, merged, then reranked). Only passages above `MIN_SCORE` are used, and at most `TOP_K` candidates.

## Web search

Web search runs when you pick the mode, when the wording asks for it, or when the documents do not answer, unless `WEB_FALLBACK=0`. It uses your SearXNG (`SEARXNG_URL`). Without one it falls back to DuckDuckGo, directly from the PC. jade also downloads the pages it uses.

## Quick replies

When jade asks you a question, it can offer up to three clickable replies. You can still type your own.

## Rights

A user only receives excerpts of files they can read. This is checked at question time with the user's own Windows rights, unless `NTFS_FILTER=0`.

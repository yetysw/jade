"""Chunking : regroupe les Sections en chunks de taille bornee, avec chevauchement.

Comptage de tokens estime : tokens ~ caracteres / 3 (prudent pour le francais
sous tokenizer XLM-R). e5-small tronque a 512 tokens -> cible 400 par defaut.
Les feuilles xlsx recoivent une ligne de contexte "Feuille: X (fichier Y)".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .parsers import Section

CHARS_PER_TOKEN = 3

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    text: str
    meta: dict


def _est_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """Coupe un texte trop long sur les phrases, puis en dur si necessaire."""
    parts: list[str] = []
    current = ""
    for sent in _SENTENCE_SPLIT.split(text):
        while len(sent) > max_chars:  # phrase geante : coupe en dur
            parts.append(sent[:max_chars])
            sent = sent[max_chars:]
        if len(current) + len(sent) + 1 > max_chars and current:
            parts.append(current)
            current = sent
        else:
            current = f"{current} {sent}".strip()
    if current:
        parts.append(current)
    return parts


def _meta_label(meta: dict) -> tuple:
    return (meta.get("section"), meta.get("sheet"))


def chunk_sections(
    sections: list[Section],
    filename: str,
    max_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    max_chars = max_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN
    chunks: list[Chunk] = []

    buffer: list[str] = []
    buffer_meta: dict = {}
    buffer_len = 0
    pages: set[int] = set()

    def flush():
        nonlocal buffer, buffer_len, pages
        if not buffer:
            return
        text = "\n".join(buffer)
        meta = dict(buffer_meta)
        if pages:
            meta["pages"] = (
                str(min(pages)) if len(pages) == 1 else f"{min(pages)}-{max(pages)}"
            )
        if meta.get("sheet"):
            text = f"Feuille: {meta['sheet']} (fichier {filename})\n{text}"
        chunks.append(Chunk(text, meta))
        # chevauchement : garde la fin du buffer pour le chunk suivant
        tail = ""
        for part in reversed(buffer):
            tail = f"{part}\n{tail}" if tail else part
            if len(tail) >= overlap_chars:
                break
        buffer = [tail] if tail and overlap_chars > 0 else []
        buffer_len = len(tail) if buffer else 0
        pages = set()

    prev_label = None
    for sec in sections:
        label = _meta_label(sec.meta)
        # changement de section/feuille : on termine le chunk en cours (sans overlap inter-section)
        if prev_label is not None and label != prev_label and buffer:
            flush()
            buffer, buffer_len = [], 0
        prev_label = label
        buffer_meta = dict(sec.meta)

        for piece in _split_long_text(sec.text, max_chars):
            if buffer_len + len(piece) + 1 > max_chars and buffer:
                flush()
            buffer.append(piece)
            buffer_len += len(piece) + 1
            if "page" in sec.meta:
                pages.add(sec.meta["page"])
            if buffer_len >= max_chars:
                flush()
    flush()

    # ne garder que les chunks non vides et significatifs
    return [c for c in chunks if c.text.strip() and _est_tokens(c.text) >= 3]

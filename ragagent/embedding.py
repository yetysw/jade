"""Embeddings locaux CPU via fastembed (ONNX Runtime).

Modele par defaut : paraphrase-multilingual-MiniLM-L12-v2 (384 dim, multilingue,
present dans le registre fastembed — multilingual-e5-small n'y figure pas).
Les modeles E5 (ex. multilingual-e5-large) exigent les prefixes "passage: " /
"query: " ; ils sont appliques automatiquement si le nom contient "e5".
Si le modele configure n'est pas dans le registre fastembed, repli sur
paraphrase-multilingual-MiniLM-L12-v2 avec avertissement.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastembed import TextEmbedding

log = logging.getLogger(__name__)

FALLBACK_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _supported_names() -> set[str]:
    return {m["model"] for m in TextEmbedding.list_supported_models()}


class Embedder:
    def __init__(self, model_name: str, cache_dir: Path, threads: int | None = None):
        supported = _supported_names()
        if model_name not in supported:
            log.warning(
                "Modele d'embeddings %s absent du registre fastembed ; repli sur %s",
                model_name,
                FALLBACK_MODEL,
            )
            model_name = FALLBACK_MODEL
        self.model_name = model_name
        self.is_e5 = "e5" in model_name.lower()
        # threads borné : évite de monopoliser tous les cœurs d'un serveur partagé
        self._model = TextEmbedding(
            model_name=model_name, cache_dir=str(cache_dir), threads=threads
        )

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if self.is_e5:
            texts = [f"passage: {t}" for t in texts]
        return [e.tolist() for e in self._model.embed(texts, batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        if self.is_e5:
            text = f"query: {text}"
        return next(iter(self._model.embed([text]))).tolist()

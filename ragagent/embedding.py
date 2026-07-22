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
import threading
from pathlib import Path

from fastembed import TextEmbedding

log = logging.getLogger(__name__)

FALLBACK_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _supported_names() -> set[str]:
    return {m["model"] for m in TextEmbedding.list_supported_models()}


class Embedder:
    """Chargement **paresseux** : la construction ne télécharge rien (résolution
    du nom de modèle seulement, via le registre statique fastembed). Le
    téléchargement + chargement ONNX du modèle (~2 Go au 1er lancement) n'a lieu
    qu'à `ensure_loaded()` — appelé explicitement en tâche de fond au démarrage
    (avec progression) pour ne jamais bloquer le serveur ni la 1re requête."""

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
        self._cache_dir = cache_dir
        self._threads = threads  # threads borné : évite de monopoliser tous les cœurs
        self._model: TextEmbedding | None = None
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._model is not None

    def ensure_loaded(self) -> TextEmbedding:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = TextEmbedding(
                        model_name=self.model_name,
                        cache_dir=str(self._cache_dir),
                        threads=self._threads,
                    )
        return self._model

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        model = self.ensure_loaded()
        if self.is_e5:
            texts = [f"passage: {t}" for t in texts]
        return [e.tolist() for e in model.embed(texts, batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        model = self.ensure_loaded()
        if self.is_e5:
            text = f"query: {text}"
        return next(iter(model.embed([text]))).tolist()

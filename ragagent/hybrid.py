"""Recherche hybride : vectoriel (ChromaDB) + mots-clés (BM25), fusion RRF,
reranker optionnel (cross-encoder).

Le vectoriel capte le sens ; BM25 capte les termes exacts (numéro de facture,
adresse IP, nom propre, référence) que la similarité sémantique rate souvent.
La fusion Reciprocal Rank Fusion (RRF) combine les deux classements. Un
cross-encoder multilingue peut ensuite réordonner finement les candidats et
fournir un score de pertinence 0..1 utilisable comme seuil.
"""

from __future__ import annotations

import logging
import math
import re

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"\w+", re.UNICODE)
RRF_K = 60


def _tok(text: str) -> list[str]:
    return [w.lower() for w in _TOKEN.findall(text)]


class Bm25Index:
    """Index BM25 en mémoire, reconstruit après chaque (ré)indexation."""

    def __init__(self):
        self.ids: list[str] = []
        self._bm = None

    def build(self, ids: list[str], texts: list[str]) -> None:
        from rank_bm25 import BM25Okapi

        self.ids = ids
        self._bm = BM25Okapi([_tok(t) for t in texts]) if ids else None

    def search(self, query: str, k: int) -> list[str]:
        """Retourne les ids des meilleurs chunks (score > 0), ordonnés."""
        if not self._bm:
            return []
        scores = self._bm.get_scores(_tok(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self.ids[i] for i in order[:k] if scores[i] > 0]


def rrf_fuse(rank_lists: list[list[str]]) -> dict[str, float]:
    """Fusion RRF de plusieurs classements d'ids -> {id: score fusionné}."""
    fused: dict[str, float] = {}
    for lst in rank_lists:
        for rank, _id in enumerate(lst):
            fused[_id] = fused.get(_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    return fused


class Reranker:
    """Cross-encoder (fastembed). Score de pertinence 0..1 via sigmoïde."""

    def __init__(self, model_name: str, cache_dir, threads: int | None = None):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model_name = model_name
        self._m = TextCrossEncoder(
            model_name=model_name, cache_dir=str(cache_dir), threads=threads
        )

    def scores(self, query: str, docs: list[str]) -> list[float]:
        raw = list(self._m.rerank(query, docs))
        return [1.0 / (1.0 + math.exp(-s)) for s in raw]

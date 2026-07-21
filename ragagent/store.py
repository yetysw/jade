"""Vector store local et embarque : ChromaDB PersistentClient (fichier, pas de serveur).

Les embeddings sont toujours fournis explicitement (fastembed) — Chroma ne
telecharge donc jamais son modele par defaut. Telemetrie desactivee.
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

COLLECTION = "docs"


class Store:
    def __init__(self, path: Path):
        self._client = chromadb.PersistentClient(
            path=str(path),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._col = self._client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    # Chroma refuse les lots au-delà de ~5461 entrées (get_max_batch_size) :
    # un gros fichier (CSV volumineux...) doit être inséré par tranches.
    UPSERT_BATCH = 4096

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        for i in range(0, len(ids), self.UPSERT_BATCH):
            j = i + self.UPSERT_BATCH
            self._col.upsert(
                ids=ids[i:j], embeddings=embeddings[i:j],
                documents=documents[i:j], metadatas=metadatas[i:j],
            )

    def delete_ids(self, ids: list[str]) -> None:
        for i in range(0, len(ids), self.UPSERT_BATCH):
            self._col.delete(ids=ids[i:i + self.UPSERT_BATCH])

    def query(self, embedding: list[float], top_k: int) -> list[dict]:
        res = self._col.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            hits.append({"text": doc, "meta": meta, "score": round(1.0 - dist, 4)})
        return hits

    def count(self) -> int:
        return self._col.count()

    def embedding_dim(self) -> int | None:
        """Dimension des vecteurs stockés (None si l'index est vide) — permet de
        détecter un index construit avec un autre modèle d'embeddings."""
        try:
            res = self._col.peek(1)
            embs = res.get("embeddings")
            if embs is not None and len(embs) > 0:
                return len(embs[0])
        except Exception:  # noqa: BLE001
            return None
        return None

    def all_documents(self) -> tuple[list[str], list[str]]:
        """(ids, textes) de tous les chunks — pour construire l'index BM25."""
        res = self._col.get(include=["documents"])
        return res.get("ids", []), res.get("documents", [])

    def get_by_ids(self, ids: list[str]) -> dict[str, dict]:
        """id -> {text, meta} pour un ensemble d'ids (candidats BM25)."""
        if not ids:
            return {}
        res = self._col.get(ids=ids, include=["documents", "metadatas"])
        out = {}
        for i, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
            out[i] = {"text": doc, "meta": meta}
        return out

    def query_ids(self, embedding: list[float], top_k: int) -> list[dict]:
        """Comme query() mais expose aussi l'id de chaque hit."""
        res = self._col.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for _id, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            hits.append({"id": _id, "text": doc, "meta": meta, "score": round(1.0 - dist, 4)})
        return hits

    def reset(self) -> None:
        self._client.delete_collection(COLLECTION)
        self._col = self._client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}
        )

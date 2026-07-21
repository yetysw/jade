"""Manifeste SQLite pour l'indexation incrementale.

Une ligne par fichier indexe : (path, mtime, size, sha256, n_chunks).
Les IDs de chunks Chroma etant deterministes (hash du chemin + index),
supprimer les chunks d'un fichier ne demande que path_hash et n_chunks.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    n_chunks INTEGER NOT NULL,
    indexed_at TEXT NOT NULL
);
"""


def norm_path(p: Path) -> str:
    return str(p.resolve()).casefold()


def path_hash(norm: str) -> str:
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def chunk_ids(norm: str, n_chunks: int) -> list[str]:
    h = path_hash(norm)
    return [f"{h}-{i:04d}" for i in range(n_chunks)]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class FileRecord:
    path: str
    mtime: float
    size: int
    sha256: str
    n_chunks: int


class Manifest:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(db_path)
        self._con.execute(_SCHEMA)
        self._con.commit()

    def get(self, norm: str) -> FileRecord | None:
        row = self._con.execute(
            "SELECT path, mtime, size, sha256, n_chunks FROM files WHERE path = ?",
            (norm,),
        ).fetchone()
        return FileRecord(*row) if row else None

    def upsert(self, rec: FileRecord) -> None:
        self._con.execute(
            "INSERT INTO files (path, mtime, size, sha256, n_chunks, indexed_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, size=excluded.size, "
            "sha256=excluded.sha256, n_chunks=excluded.n_chunks, indexed_at=excluded.indexed_at",
            (
                rec.path,
                rec.mtime,
                rec.size,
                rec.sha256,
                rec.n_chunks,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        self._con.commit()

    def touch_mtime(self, norm: str, mtime: float) -> None:
        self._con.execute("UPDATE files SET mtime = ? WHERE path = ?", (mtime, norm))
        self._con.commit()

    def delete(self, norm: str) -> None:
        self._con.execute("DELETE FROM files WHERE path = ?", (norm,))
        self._con.commit()

    def all_paths(self) -> dict[str, FileRecord]:
        rows = self._con.execute(
            "SELECT path, mtime, size, sha256, n_chunks FROM files"
        ).fetchall()
        return {r[0]: FileRecord(*r) for r in rows}

    def reset(self) -> None:
        self._con.execute("DELETE FROM files")
        self._con.commit()

    def close(self) -> None:
        self._con.close()

"""Persistance des conversations (SQLite local, data/chats.db).

conversations : id (uuid), title, created_at, updated_at
messages      : role user/assistant, content, sources (json), timings (json)
Thread-safe via un verrou (FastAPI execute les endpoints sync dans un threadpool).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import security

log = logging.getLogger(__name__)

# Chiffrement au repos des conversations via DPAPI (clé liée au compte Windows).
# Actif si disponible ; sinon stockage en clair (rétro-compatible à la lecture).
_ENC = security.dpapi_available()
DEFAULT_TITLE = "Nouvelle conversation"


def _enc(s):
    if s and _ENC and not s.startswith(security.DPAPI_PREFIX):
        try:
            return security.protect(s)
        except OSError as e:
            log.warning("Chiffrement DPAPI échoué : %s", e)
    return s


def _dec(s):
    if not s:
        return s
    try:
        return security.unprotect(s)
    except OSError:
        return s


_SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Nouvelle conversation',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    folder_id TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources TEXT,
    timings TEXT,
    attachments TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conv_id, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_int(value: object, default: int = 0) -> int:
    """Entier robuste pour l'import : une valeur absente ou corrompue dans une
    sauvegarde (éditée à la main, tronquée) retombe sur `default` plutôt que de
    faire échouer toute la migration."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class ChatStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.execute("PRAGMA foreign_keys = ON")
        self._con.executescript(_SCHEMA)
        # migration douce des bases antérieures
        cols = {r[1] for r in self._con.execute("PRAGMA table_info(conversations)")}
        for col in ("pinned", "archived"):
            if col not in cols:
                self._con.execute(
                    f"ALTER TABLE conversations ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
                )
        if "folder_id" not in cols:
            self._con.execute("ALTER TABLE conversations ADD COLUMN folder_id TEXT")
        mcols = {r[1] for r in self._con.execute("PRAGMA table_info(messages)")}
        if "attachments" not in mcols:
            self._con.execute("ALTER TABLE messages ADD COLUMN attachments TEXT")
        self._con.commit()
        self._lock = threading.Lock()

    def create_conversation(self) -> dict:
        cid = uuid.uuid4().hex[:12]
        now = _now()
        with self._lock:
            self._con.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (cid, "Nouvelle conversation", now, now),
            )
            self._con.commit()
        return {"id": cid, "title": "Nouvelle conversation", "created_at": now, "updated_at": now}

    def list_conversations(self, include_archived: bool = False) -> list[dict]:
        where = "" if include_archived else "WHERE c.archived = 0"
        with self._lock:
            rows = self._con.execute(
                "SELECT c.id, c.title, c.updated_at, COUNT(m.id), c.pinned, c.archived, "
                "c.folder_id "
                "FROM conversations c LEFT JOIN messages m ON m.conv_id = c.id "
                f"{where} GROUP BY c.id ORDER BY c.pinned DESC, c.updated_at DESC"
            ).fetchall()
        return [
            {"id": r[0], "title": _dec(r[1]), "updated_at": r[2], "n_messages": r[3],
             "pinned": bool(r[4]), "archived": bool(r[5]), "folder_id": r[6]}
            for r in rows
        ]

    def search(self, query: str, limit: int = 40) -> list[dict]:
        """Recherche dans le titre ET le contenu des messages.

        Le contenu est chiffré au repos (DPAPI) : on ne peut pas filtrer en SQL,
        on déchiffre donc en Python et on cherche la sous-chaîne. Retourne un
        extrait autour de la première correspondance de contenu.
        """
        q = query.strip().lower()
        if not q:
            return []
        with self._lock:
            convs = self._con.execute(
                "SELECT id, title, updated_at, folder_id, pinned FROM conversations "
                "WHERE archived = 0 ORDER BY pinned DESC, updated_at DESC"
            ).fetchall()
            out: list[dict] = []
            for cid, title, updated, folder_id, pinned in convs:
                dtitle = _dec(title) or ""
                snippet = ""
                matched = q in dtitle.lower()
                if not matched:
                    rows = self._con.execute(
                        "SELECT content FROM messages WHERE conv_id = ? ORDER BY id", (cid,)
                    ).fetchall()
                    for (content,) in rows:
                        dc = _dec(content) or ""
                        pos = dc.lower().find(q)
                        if pos >= 0:
                            matched = True
                            start = max(0, pos - 40)
                            frag = dc[start:pos + len(q) + 60].replace("\n", " ").strip()
                            snippet = ("… " if start > 0 else "") + frag + " …"
                            break
                if matched:
                    out.append({
                        "id": cid, "title": dtitle, "updated_at": updated,
                        "folder_id": folder_id, "pinned": bool(pinned), "snippet": snippet,
                    })
                if len(out) >= limit:
                    break
        return out

    # -------------------------------------------------------------- dossiers

    def list_folders(self) -> list[dict]:
        with self._lock:
            rows = self._con.execute(
                "SELECT id, name FROM folders ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [{"id": r[0], "name": r[1]} for r in rows]

    def create_folder(self, name: str) -> dict:
        fid = uuid.uuid4().hex[:10]
        with self._lock:
            self._con.execute(
                "INSERT INTO folders (id, name, created_at) VALUES (?, ?, ?)",
                (fid, name[:50], _now()),
            )
            self._con.commit()
        return {"id": fid, "name": name[:50]}

    def rename_folder(self, fid: str, name: str) -> None:
        with self._lock:
            self._con.execute("UPDATE folders SET name = ? WHERE id = ?", (name[:50], fid))
            self._con.commit()

    def delete_folder(self, fid: str) -> None:
        """Supprime le dossier ; ses conversations redeviennent non classées."""
        with self._lock:
            self._con.execute(
                "UPDATE conversations SET folder_id = NULL WHERE folder_id = ?", (fid,)
            )
            self._con.execute("DELETE FROM folders WHERE id = ?", (fid,))
            self._con.commit()

    def get_folder_id(self, cid: str) -> str | None:
        with self._lock:
            row = self._con.execute(
                "SELECT folder_id FROM conversations WHERE id = ?", (cid,)
            ).fetchone()
        return row[0] if row else None

    def set_conv_folder(self, cid: str, fid: str | None) -> None:
        with self._lock:
            self._con.execute(
                "UPDATE conversations SET folder_id = ? WHERE id = ?", (fid, cid)
            )
            self._con.commit()

    def set_flag(self, cid: str, field: str, value: bool) -> None:
        if field not in ("pinned", "archived"):
            raise ValueError(field)
        with self._lock:
            self._con.execute(
                f"UPDATE conversations SET {field} = ? WHERE id = ?", (1 if value else 0, cid)
            )
            self._con.commit()

    def delete_from(self, cid: str, message_id: int) -> None:
        """Supprime le message donné et tous les suivants (édition d'une question)."""
        with self._lock:
            self._con.execute(
                "DELETE FROM messages WHERE conv_id = ? AND id >= ?", (cid, message_id)
            )
            self._con.commit()

    def get_conversation(self, cid: str) -> dict | None:
        with self._lock:
            conv = self._con.execute(
                "SELECT id, title, created_at FROM conversations WHERE id = ?", (cid,)
            ).fetchone()
            if not conv:
                return None
            rows = self._con.execute(
                "SELECT id, role, content, sources, timings, created_at, attachments "
                "FROM messages WHERE conv_id = ? ORDER BY id",
                (cid,),
            ).fetchall()
        return {
            "id": conv[0],
            "title": _dec(conv[1]),
            "created_at": conv[2],
            "messages": [
                {
                    "id": r[0],
                    "role": r[1],
                    "content": _dec(r[2]),
                    "sources": json.loads(_dec(r[3])) if r[3] else None,
                    "timings": json.loads(r[4]) if r[4] else None,
                    "created_at": r[5],
                    "attachments": json.loads(_dec(r[6])) if r[6] else None,
                }
                for r in rows
            ],
        }

    def add_message(
        self, cid: str, role: str, content: str,
        sources: list | None = None, timings: dict | None = None,
        attachments: list | None = None,
    ) -> None:
        with self._lock:
            self._con.execute(
                "INSERT INTO messages "
                "(conv_id, role, content, sources, timings, attachments, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    cid, role, _enc(content),
                    _enc(json.dumps(sources, ensure_ascii=False)) if sources else None,
                    json.dumps(timings) if timings else None,
                    _enc(json.dumps(attachments, ensure_ascii=False)) if attachments else None,
                    _now(),
                ),
            )
            self._con.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (_now(), cid)
            )
            self._con.commit()

    def set_title_if_new(self, cid: str, title: str) -> None:
        # le titre par défaut reste en clair (sentinelle pour ce WHERE) ; le
        # vrai titre est chiffré
        with self._lock:
            self._con.execute(
                "UPDATE conversations SET title = ? WHERE id = ? AND title = ?",
                (_enc(title[:60]), cid, DEFAULT_TITLE),
            )
            self._con.commit()

    def rename(self, cid: str, title: str) -> None:
        with self._lock:
            self._con.execute(
                "UPDATE conversations SET title = ? WHERE id = ?", (_enc(title[:60]), cid)
            )
            self._con.commit()

    def delete(self, cid: str) -> None:
        with self._lock:
            self._con.execute("DELETE FROM conversations WHERE id = ?", (cid,))
            self._con.commit()

    def clear_all(self) -> int:
        """Supprime TOUT l'historique : conversations, messages et dossiers.
        Retourne le nombre de conversations supprimées."""
        with self._lock:
            n = self._con.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            self._con.execute("DELETE FROM messages")
            self._con.execute("DELETE FROM conversations")
            self._con.execute("DELETE FROM folders")
            self._con.commit()
        return int(n)

    # ----------------------------------------------- sauvegarde / migration

    def export_all(self) -> dict:
        """Exporte tout l'historique dans une structure PORTABLE (déchiffrée).

        Le contenu en base est chiffré par DPAPI, clé liée au compte Windows
        courant : une simple copie de chats.db ne se rouvrirait pas sur une autre
        machine ou un autre compte. On exporte donc en clair (JSON) pour permettre
        une vraie migration ; la restauration re-chiffre avec la clé de la machine
        cible. Le fichier produit contient l'historique en clair : c'est à
        l'utilisateur de le stocker en lieu sûr.

        Returns:
            dict: {folders: [...], conversations: [...]} où chaque conversation
            porte ses métadonnées et la liste complète de ses messages déchiffrés.
        """
        with self._lock:
            folders = [
                {"id": r[0], "name": r[1], "created_at": r[2]}
                for r in self._con.execute(
                    "SELECT id, name, created_at FROM folders ORDER BY created_at"
                ).fetchall()
            ]
            conv_rows = self._con.execute(
                "SELECT id, title, created_at, updated_at, pinned, archived, folder_id "
                "FROM conversations ORDER BY created_at"
            ).fetchall()
            conversations = []
            for c in conv_rows:
                msg_rows = self._con.execute(
                    "SELECT role, content, sources, timings, attachments, created_at "
                    "FROM messages WHERE conv_id = ? ORDER BY id",
                    (c[0],),
                ).fetchall()
                conversations.append({
                    "id": c[0],
                    "title": _dec(c[1]),
                    "created_at": c[2],
                    "updated_at": c[3],
                    "pinned": int(c[4]),
                    "archived": int(c[5]),
                    "folder_id": c[6],
                    "messages": [
                        {
                            "role": m[0],
                            "content": _dec(m[1]),
                            "sources": json.loads(_dec(m[2])) if m[2] else None,
                            "timings": json.loads(m[3]) if m[3] else None,
                            "attachments": json.loads(_dec(m[4])) if m[4] else None,
                            "created_at": m[5],
                        }
                        for m in msg_rows
                    ],
                })
        return {"folders": folders, "conversations": conversations}

    def import_all(self, data: dict) -> dict:
        """Importe un export produit par [export_all], en re-chiffrant le contenu.

        Fusion non destructive : les conversations et dossiers dont l'identifiant
        existe déjà sont ignorés (aucune donnée existante n'est écrasée ni
        supprimée). Convient à une migration vers une machine neuve comme à une
        fusion partielle.

        Args:
            data: structure {folders, conversations} issue de [export_all].

        Returns:
            dict: {folders, conversations, messages} = nombres réellement insérés.

        Raises:
            ValueError: si `data` n'a pas la forme attendue.
        """
        if not isinstance(data, dict) or "conversations" not in data:
            raise ValueError("Fichier de sauvegarde invalide.")
        n_folders = n_convs = n_msgs = 0
        with self._lock:
            # Transaction atomique : au moindre incident (sauvegarde partiellement
            # corrompue, erreur SQLite en cours de boucle), on annule TOUT — sans
            # rollback explicite, les insertions déjà exécutées mais non validées
            # seraient publiées par le prochain commit d'une autre opération, ce
            # qui produirait un import à moitié appliqué.
            try:
                existing_folders = {
                    r[0] for r in self._con.execute("SELECT id FROM folders").fetchall()
                }
                for f in data.get("folders", []):
                    fid = f.get("id")
                    if not fid or fid in existing_folders:
                        continue
                    self._con.execute(
                        "INSERT INTO folders (id, name, created_at) VALUES (?, ?, ?)",
                        (fid, str(f.get("name", ""))[:50], f.get("created_at") or _now()),
                    )
                    existing_folders.add(fid)
                    n_folders += 1

                existing_convs = {
                    r[0] for r in self._con.execute("SELECT id FROM conversations").fetchall()
                }
                for c in data.get("conversations", []):
                    cid = c.get("id")
                    if not cid or cid in existing_convs:
                        continue
                    # un dossier référencé mais absent -> conversation non classée
                    folder_id = c.get("folder_id")
                    if folder_id and folder_id not in existing_folders:
                        folder_id = None
                    self._con.execute(
                        "INSERT INTO conversations "
                        "(id, title, created_at, updated_at, pinned, archived, folder_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            cid, _enc(str(c.get("title", DEFAULT_TITLE))[:60]),
                            c.get("created_at") or _now(), c.get("updated_at") or _now(),
                            _as_int(c.get("pinned", 0)), _as_int(c.get("archived", 0)),
                            folder_id,
                        ),
                    )
                    existing_convs.add(cid)
                    n_convs += 1
                    for m in c.get("messages", []):
                        role = m.get("role")
                        if role not in ("user", "assistant"):
                            continue
                        sources = m.get("sources")
                        attachments = m.get("attachments")
                        timings = m.get("timings")
                        self._con.execute(
                            "INSERT INTO messages "
                            "(conv_id, role, content, sources, timings, attachments, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                cid, role, _enc(str(m.get("content", ""))),
                                _enc(json.dumps(sources, ensure_ascii=False)) if sources else None,
                                json.dumps(timings) if timings else None,
                                _enc(json.dumps(attachments, ensure_ascii=False)) if attachments else None,
                                m.get("created_at") or _now(),
                            ),
                        )
                        n_msgs += 1
                self._con.commit()
            except Exception:
                self._con.rollback()
                raise
        return {"folders": n_folders, "conversations": n_convs, "messages": n_msgs}

    def history(self, cid: str, limit: int = 8) -> list[dict]:
        """Derniers messages (role/content) pour le contexte multi-tours."""
        with self._lock:
            rows = self._con.execute(
                "SELECT role, content FROM messages WHERE conv_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (cid, limit),
            ).fetchall()
        return [{"role": r[0], "content": _dec(r[1])} for r in reversed(rows)]

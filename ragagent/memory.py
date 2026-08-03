"""Mémoire persistante entre les conversations (par utilisateur Windows).

Même principe que mem0, appliqué à notre pile locale :
1. après chaque échange, le LLM extrait les faits durables (préférences,
   rôle, projets, contexte de l'utilisateur) — JSON strict, souvent vide ;
2. chaque fait est dédoublonné par similarité d'embedding avant stockage
   (SQLite dans %APPDATA%\\Jade, embeddings en blob, comparaison numpy) ;
3. à chaque question, les faits les plus proches sont injectés dans le
   prompt système.

Rien ne sort du poste : extraction via le LLM central (texte uniquement),
stockage et similarité 100 % locaux.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

EXTRACT_PROMPT = """Tu extrais les faits durables à mémoriser sur l'utilisateur à partir
d'un échange avec un assistant documentaire d'entreprise.
Ne retiens QUE ce qui restera vrai et utile dans de futures conversations :
prénom/nom, rôle, équipe, préférences exprimées, projets ou sujets récurrents,
façon dont il veut qu'on lui réponde.
N'invente rien. Ignore le contenu des documents cités, les questions ponctuelles
et tout ce qui est déjà évident.
Ne retiens JAMAIS ce que l'assistant dit de LUI-MÊME (son nom, son rôle, son
fonctionnement) : seul ce qui concerne l'UTILISATEUR compte. Un fait doit
toujours parler de l'utilisateur à la troisième personne.
Chaque fait doit être une PHRASE COMPLÈTE ET AUTONOME, compréhensible sans
contexte. Exemples : "L'utilisateur s'appelle Noé", "Il est technicien
informatique chez Jade", "Il préfère des réponses courtes".
Jamais de mots isolés.
Réponds UNIQUEMENT par un tableau JSON de chaînes en français.
S'il n'y a rien à retenir (cas le plus fréquent) : []"""

DEDUP_THRESHOLD = 0.90   # au-delà : considéré comme déjà connu
INJECT_THRESHOLD = 0.25  # pertinence minimale pour injecter un fait
MAX_INJECTED = 4
INJECT_ALL_BELOW = 15    # peu de faits : on les injecte tous (coût négligeable)
MAX_MEMORIES = 400

# Fait rédigé à la 1re personne : c'est presque toujours une phrase de
# l'ASSISTANT sur lui-même que l'extraction a recopiée (« Je m'appelle Léo »,
# « Je suis assistant documentaire ») — mémorisée comme un fait sur
# l'utilisateur, elle lui faisait attribuer un prénom qu'il n'a jamais donné.
# Les faits attendus sont à la 3e personne (« L'utilisateur s'appelle… »).
_SELF_FACT = re.compile(r"^(je\b|j'|mon\b|ma\b|mes\b)", re.IGNORECASE)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at TEXT NOT NULL,
    folder_id TEXT
);
"""


class MemoryStore:
    def __init__(self, db_path: Path, embedder):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.executescript(_SCHEMA)
        # migration douce : folder_id ajouté pour la mémoire par dossier (projet)
        cols = {r[1] for r in self._con.execute("PRAGMA table_info(memories)")}
        if "folder_id" not in cols:
            self._con.execute("ALTER TABLE memories ADD COLUMN folder_id TEXT")
        self._con.commit()
        self._lock = threading.Lock()
        self._embedder = embedder
        self._migrate_embeddings()

    def _migrate_embeddings(self) -> None:
        """Changement de modèle d'embeddings : les vecteurs stockés (autre
        dimension / autre espace) sont recalculés à partir du texte des faits.
        Suivi via une petite table meta (nom du modèle)."""
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        model = getattr(self._embedder, "model_name", "")
        try:
            row = self._con.execute(
                "SELECT value FROM meta WHERE key='embed_model'").fetchone()
            previous = row[0] if row else ""
            if previous == model:
                return
            rows = self._con.execute("SELECT id, text FROM memories").fetchall()
            if rows and previous != model:
                log.info("Mémoire : ré-embedding de %d fait(s) (modèle %s)",
                         len(rows), model or "?")
                for mid, text in rows:
                    emb = np.asarray(
                        self._embedder.embed_query(text), dtype=np.float32)
                    self._con.execute(
                        "UPDATE memories SET embedding=? WHERE id=?",
                        (emb.tobytes(), mid))
            self._con.execute(
                "INSERT INTO meta (key, value) VALUES ('embed_model', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (model,))
            self._con.commit()
        except sqlite3.Error as e:
            log.warning("Migration mémoire impossible : %s", e)

    # ------------------------------------------------------------- interne

    def _all(self, folder_id: str | None = "__ALL__") -> list[tuple[int, str, np.ndarray]]:
        """Faits, filtrés par portée. folder_id :
        - "__ALL__" (défaut) : tous les faits (pour dédup / liste) ;
        - None : faits globaux (appris hors dossier) uniquement ;
        - "<id>" : faits globaux + faits appris dans ce dossier (mémoire projet).
        """
        with self._lock:
            rows = self._con.execute(
                "SELECT id, text, embedding, folder_id FROM memories"
            ).fetchall()
        out = []
        for r in rows:
            fid = r[3]
            if folder_id == "__ALL__" or fid is None or fid == folder_id:
                out.append((r[0], r[1], np.frombuffer(r[2], dtype=np.float32)))
        return out

    @staticmethod
    def _cos(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    # ------------------------------------------------------------- écriture

    def add(self, text: str, folder_id: str | None = None) -> bool:
        """Ajoute un fait s'il n'est pas déjà connu. Retourne True si ajouté.
        folder_id : dossier (projet) auquel rattacher le fait ; None = global."""
        text = text.strip()
        if not text or len(text) > 300:
            return False
        if _SELF_FACT.match(text):
            log.debug("Fait ignoré (propos de l'assistant sur lui-même) : %s", text)
            return False
        emb = np.asarray(self._embedder.embed_query(text), dtype=np.float32)
        for _id, _t, e in self._all():  # dédup contre TOUS les faits
            if self._cos(emb, e) >= DEDUP_THRESHOLD:
                return False  # déjà mémorisé (ou quasi identique)
        with self._lock:
            self._con.execute(
                "INSERT INTO memories (text, embedding, created_at, folder_id) "
                "VALUES (?, ?, ?, ?)",
                (text, emb.tobytes(),
                 datetime.now(timezone.utc).isoformat(timespec="seconds"), folder_id),
            )
            # garde-fou : ne pas croître sans limite
            self._con.execute(
                "DELETE FROM memories WHERE id NOT IN "
                f"(SELECT id FROM memories ORDER BY id DESC LIMIT {MAX_MEMORIES})"
            )
            self._con.commit()
        log.info("Mémoire ajoutée : %s", text)
        return True

    def extract_from_exchange(self, llm, question: str, answer: str,
                              folder_id: str | None = None,
                              model: str | None = None) -> int:
        """Demande au LLM les faits à retenir de cet échange, les stocke.
        folder_id : rattache les faits appris au dossier (projet) courant.
        model : petit modèle de fond (pré-analyse) pour ne pas charger le gros."""
        try:
            raw = llm.chat([
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user",
                 "content": f"Utilisateur : {question[:800]}\n\nAssistant : {answer[:800]}"},
            ], model=model or None, think=False)
            m = re.search(r"\[.*\]", raw, re.S)
            facts = json.loads(m.group(0)) if m else []
        except Exception as e:
            log.warning("Extraction mémoire échouée : %s", e)
            return 0
        added = 0
        for fact in facts[:5]:
            if isinstance(fact, str) and self.add(fact, folder_id):
                added += 1
        return added

    # ------------------------------------------------------------- lecture

    def context_for(self, question: str, folder_id: str | None = None) -> str:
        """Faits pertinents pour cette question, formatés pour le prompt.
        Dans un dossier : faits globaux + faits appris dans ce dossier ;
        hors dossier : faits globaux uniquement."""
        rows = self._all(folder_id)
        if not rows:
            return ""
        if len(rows) <= INJECT_ALL_BELOW:
            return "\n".join(f"- {t}" for _id, t, _e in rows)
        q = np.asarray(self._embedder.embed_query(question), dtype=np.float32)
        scored = sorted(
            ((self._cos(q, e), t) for _id, t, e in rows), reverse=True
        )
        picked = [t for s, t in scored[:MAX_INJECTED] if s >= INJECT_THRESHOLD]
        if not picked:
            return ""
        return "\n".join(f"- {t}" for t in picked)

    def list_all(self) -> list[dict]:
        with self._lock:
            rows = self._con.execute(
                "SELECT id, text, created_at FROM memories ORDER BY id DESC"
            ).fetchall()
        return [{"id": r[0], "text": r[1], "created_at": r[2]} for r in rows]

    def delete(self, mid: int) -> None:
        with self._lock:
            self._con.execute("DELETE FROM memories WHERE id = ?", (mid,))
            self._con.commit()

    def clear(self) -> None:
        with self._lock:
            self._con.execute("DELETE FROM memories")
            self._con.commit()

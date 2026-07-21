"""Orchestration de l'indexation incrementale.

Par fichier : absent du manifeste -> indexer ; mtime+taille inchanges -> skip
(chemin rapide, sans hash) ; sinon hash sha256 -> si different, re-parse +
re-embed + remplacement des chunks ; si identique, simple mise a jour du mtime.
Fichiers disparus -> suppression de leurs chunks. Fichiers verrouilles (frequent
sur RDS) -> avertissement et skip, retente au prochain run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import Settings
from ..embedding import Embedder
from ..store import Store
from .chunker import chunk_sections
from .manifest import FileRecord, Manifest, chunk_ids, file_sha256, norm_path
from .parsers import parse_file

log = logging.getLogger(__name__)


@dataclass
class IndexReport:
    indexed: int = 0
    unchanged: int = 0
    deleted: int = 0
    skipped_errors: list[str] = field(default_factory=list)
    total_chunks: int = 0


def run_index(settings: Settings, embedder: Embedder, store: Store, full: bool = False) -> IndexReport:
    settings.ensure_dirs()
    manifest = Manifest(settings.manifest_path)
    report = IndexReport()

    # Changement de modèle d'embeddings : l'index existant (autre dimension /
    # autre espace vectoriel) est inutilisable -> réindexation complète
    # automatique. Le modèle courant est mémorisé à côté de l'index.
    marker = settings.data_dir / "embed_model.txt"
    current_model = getattr(embedder, "model_name", "")
    previous_model = (
        marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    )
    if previous_model and current_model and previous_model != current_model:
        log.info(
            "Modèle d'embeddings changé (%s -> %s) : réindexation complète",
            previous_model, current_model,
        )
        full = True
    elif not previous_model and store.count() > 0:
        # installation mise à niveau (marqueur absent) : comparer les dimensions
        stored_dim = store.embedding_dim()
        if stored_dim and stored_dim != len(embedder.embed_query("dimension")):
            log.info(
                "Index existant en %dd, modèle actuel différent : réindexation complète",
                stored_dim,
            )
            full = True

    if full:
        log.info("Reindexation complete demandee (--full) : purge du store et du manifeste")
        store.reset()
        manifest.reset()
    if current_model:
        marker.write_text(current_model, encoding="utf-8")

    from ..index_config import get_roots

    known = manifest.all_paths()
    seen: set[str] = set()

    # dossiers à indexer (multi-dossiers / lecteurs réseau). On ne scanne que
    # ceux qui sont accessibles : un lecteur réseau hors ligne ne doit PAS
    # entraîner la suppression de ses fichiers déjà indexés.
    roots = get_roots(settings)
    accessible = [r for r in roots if r.is_dir()]
    for r in roots:
        if r not in accessible:
            log.warning("Dossier à indexer inaccessible, ignoré ce run : %s", r)
    if not accessible:
        raise FileNotFoundError(
            "Aucun dossier à indexer accessible. Configurez-les dans les paramètres."
        )
    accessible_norm = [norm_path(r) + "\\" for r in accessible]

    for root in accessible:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in settings.extensions:
                continue
            if path.name.startswith("~$"):  # fichiers temporaires Office
                continue
            norm = norm_path(path)
            seen.add(norm)
            try:
                stat = path.stat()
                rec = known.get(norm)
                if rec and rec.mtime == stat.st_mtime and rec.size == stat.st_size:
                    report.unchanged += 1
                    continue
                sha = file_sha256(path)
                if rec and rec.sha256 == sha:
                    manifest.touch_mtime(norm, stat.st_mtime)  # touche mais pas modifie
                    report.unchanged += 1
                    continue
                _index_file(path, norm, sha, stat, rec, settings, embedder, store, manifest)
                report.indexed += 1
            except (PermissionError, OSError) as e:
                log.warning("Fichier inaccessible, ignore pour ce run : %s (%s)", path, e)
                report.skipped_errors.append(str(path))
            except Exception as e:
                log.error("Echec de parsing, fichier ignore : %s (%s)", path, e)
                report.skipped_errors.append(str(path))

    # fichiers supprimés depuis le dernier run — uniquement sous un dossier
    # accessible (on ne purge pas ce qui vient d'un lecteur hors ligne)
    for norm, rec in known.items():
        if norm in seen:
            continue
        if not any(norm.startswith(a) for a in accessible_norm):
            continue
        store.delete_ids(chunk_ids(norm, rec.n_chunks))
        manifest.delete(norm)
        report.deleted += 1
        log.info("Fichier supprime, chunks retires : %s", norm)

    report.total_chunks = store.count()
    manifest.close()
    return report


def _index_file(path, norm, sha, stat, old_rec, settings, embedder, store, manifest) -> None:
    sections = parse_file(path, ocr=settings.ocr_index)
    chunks = chunk_sections(
        sections, path.name, settings.chunk_tokens, settings.chunk_overlap
    )
    # supprime les anciens chunks avant d'inserer les nouveaux (le nombre peut changer)
    if old_rec:
        store.delete_ids(chunk_ids(norm, old_rec.n_chunks))

    if chunks:
        ids = chunk_ids(norm, len(chunks))
        embeddings = embedder.embed_passages([c.text for c in chunks])
        metadatas = []
        for i, c in enumerate(chunks):
            meta = {
                "path": str(path),
                "filename": path.name,
                "filetype": path.suffix.lower().lstrip("."),
                "chunk_index": i,
                "mtime_iso": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds"),
            }
            for key in ("section", "sheet", "pages"):
                if c.meta.get(key):
                    meta[key] = str(c.meta[key])
            metadatas.append(meta)
        store.upsert(ids, embeddings, [c.text for c in chunks], metadatas)

    manifest.upsert(
        FileRecord(norm, stat.st_mtime, stat.st_size, sha, len(chunks))
    )
    log.info("Indexe : %s (%d chunks)", path.name, len(chunks))

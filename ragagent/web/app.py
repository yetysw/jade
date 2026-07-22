"""Application web locale (FastAPI, localhost uniquement).

- Conversations persistantes (SQLite) avec suivi multi-tours
- Reponses en streaming (SSE) avec chronometrage detaille par etape
- Ouverture des fichiers sources dans l'application par defaut / l'Explorateur
  (chemins valides : uniquement sous DOCS_DIR)
- Reindexation incrementale en arriere-plan : periodique + a la demande
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .. import ntfs, ocr, prefs, updater, winmem
from ..chat_store import DEFAULT_TITLE, ChatStore
from ..config import Settings
from ..openers import open_path, open_url, reveal_path
from ..embedding import Embedder
from ..hybrid import Bm25Index, Reranker
from ..ingest.indexer import run_index
from ..llm import LLMError, OllamaClient
from ..rag import (
    GENERAL_PROMPT, SMALLTALK_PROMPT, build_messages, format_sources, is_smalltalk,
    retrieve_timed, today_fr,
)
from ..router import route_question
from ..security import encrypt_at_rest
from ..store import Store
from ..websearch import wants_web, web_context, web_query

log = logging.getLogger(__name__)

LLM_CHECK_TTL = 60  # secondes de cache pour l'etat du LLM central


NO_INFO_ANSWER = (
    "Je ne trouve pas d'information pertinente dans les documents indexés "
    "pour cette question."
)
OFFLINE_NOTICE = (
    "**Mode hors ligne** — aucune donnée n'a été envoyée au serveur central. "
    "Voici les extraits locaux les plus pertinents :"
)


class Attachment(BaseModel):
    name: str
    data_b64: str  # contenu du fichier en base64 (max ~10 Mo)


class HistoryTurn(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str
    offline: bool = False
    dry_run: bool = False  # alias historique (CLI) de offline
    attachments: list[Attachment] = []
    req_id: str = ""       # identifiant client pour l'arrêt de génération
    incognito: bool = False
    history: list[HistoryTurn] = []  # historique fourni par le client (incognito)


class StopRequest(BaseModel):
    req_id: str


class PrefsRequest(BaseModel):
    incognito: bool = False


class SaveRequest(BaseModel):
    title: str
    content: str
    format: str  # docx | xlsx | pdf


class FlagRequest(BaseModel):
    field: str  # pinned | archived
    value: bool


class TruncateRequest(BaseModel):
    message_id: int


class FeedbackRequest(BaseModel):
    content: str = ""


class FolderAssignRequest(BaseModel):
    folder_id: str | None = None


class RootsRequest(BaseModel):
    password: str
    action: str  # add | remove
    path: str


class ReindexRequest(BaseModel):
    password: str
    full: bool = False


class OpenRequest(BaseModel):
    path: str
    reveal: bool = False


class OpenUrlRequest(BaseModel):
    url: str


class RenameRequest(BaseModel):
    title: str


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _session_display_name() -> str:
    """Nom complet du compte de la session Windows (ex. « Claire Fontaine »).

    1. GetUserNameExW(NameDisplay) — comptes de domaine (RDS clients)
    2. NetUserGetInfo niveau 10 — nom complet d'un compte local
    3. repli : identifiant de connexion
    """
    try:
        import ctypes

        NAME_DISPLAY = 3
        size = ctypes.c_ulong(0)
        ctypes.windll.secur32.GetUserNameExW(NAME_DISPLAY, None, ctypes.byref(size))
        buf = ctypes.create_unicode_buffer(size.value + 1)
        if ctypes.windll.secur32.GetUserNameExW(NAME_DISPLAY, buf, ctypes.byref(size)):
            if buf.value.strip():
                return buf.value.strip()
    except Exception:
        pass
    # repli portable (macOS / Linux / Windows sans domaine)
    import getpass

    try:
        username = getpass.getuser()
    except Exception:
        username = os.environ.get("USERNAME") or os.environ.get("USER") or "Utilisateur"
    if sys.platform != "win32":
        return username
    try:
        import ctypes

        class USER_INFO_10(ctypes.Structure):
            _fields_ = [
                ("name", ctypes.c_wchar_p), ("comment", ctypes.c_wchar_p),
                ("usr_comment", ctypes.c_wchar_p), ("full_name", ctypes.c_wchar_p),
            ]

        netapi32 = ctypes.windll.netapi32
        pbuf = ctypes.POINTER(USER_INFO_10)()
        if netapi32.NetUserGetInfo(None, username, 10, ctypes.byref(pbuf)) == 0:
            full = (pbuf.contents.full_name or "").strip()
            netapi32.NetApiBufferFree(pbuf)
            if full:
                return full
    except Exception:
        pass
    return username


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
DOC_EXTS = {".docx", ".xlsx", ".xls", ".pdf", ".txt", ".md", ".csv",
            ".html", ".htm", ".odt", ".eml", ".msg"}
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_MB = 10
MAX_DOC_CHARS = 6000


def _process_attachments(attachments: list[Attachment]) -> tuple[str, list[str], list[str]]:
    """Pieces jointes -> (texte extrait des documents, images b64, erreurs).

    Les documents sont parses LOCALEMENT (memes parseurs que l'indexation) ;
    seul le texte extrait part vers le LLM. Les images partent en base64
    vers le modele de vision.
    """
    from ..ingest.parsers import parse_file

    texts: list[str] = []
    images: list[str] = []
    errors: list[str] = []
    for att in attachments[:MAX_ATTACHMENTS]:
        ext = Path(att.name).suffix.lower()
        if len(att.data_b64) > MAX_ATTACHMENT_MB * 1400000:
            errors.append(f"{att.name} : fichier trop volumineux (max {MAX_ATTACHMENT_MB} Mo)")
            continue
        try:
            raw = base64.b64decode(att.data_b64)
        except (binascii.Error, ValueError):
            errors.append(f"{att.name} : contenu illisible")
            continue
        if ext in IMAGE_EXTS:
            # OCR local d'abord (extraction de texte) ; à défaut, modèle de vision
            text = ocr.ocr_image_bytes(raw) if ocr.available() else ""
            if text.strip():
                texts.append(f"--- {att.name} (texte extrait par OCR) ---\n{text}")
            else:
                images.append(att.data_b64)
        elif ext in DOC_EXTS:
            try:
                if ext == ".csv":  # csv : lecture texte directe
                    text = raw.decode("utf-8", errors="replace")
                else:
                    with tempfile.NamedTemporaryFile(
                        suffix=ext, delete=False
                    ) as tmp:
                        tmp.write(raw)
                        tmp_path = Path(tmp.name)
                    try:
                        # ocr=True : les PDF scannés joints sont océrisés
                        sections = parse_file(tmp_path, ocr=True)
                        text = "\n".join(s.text for s in sections)
                    finally:
                        tmp_path.unlink(missing_ok=True)
                if not text.strip():
                    errors.append(f"{att.name} : aucun texte extractible")
                    continue
                if len(text) > MAX_DOC_CHARS:
                    text = text[:MAX_DOC_CHARS] + "\n[... document tronque ...]"
                texts.append(f"--- {att.name} ---\n{text}")
            except Exception as e:
                errors.append(f"{att.name} : analyse impossible ({e})")
        else:
            errors.append(f"{att.name} : type de fichier non pris en charge")
    return "\n\n".join(texts), images, errors


def _persist_attachments(base_dir: Path, cid: str, attachments: list) -> list[dict]:
    """Sauvegarde les pièces jointes sur le disque (par utilisateur) pour qu'elles
    restent consultables/rouvrables depuis l'historique. Retourne des
    descripteurs [{name, path, kind}]."""
    if not attachments:
        return []
    dest = base_dir / "attachments" / cid
    dest.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    for att in attachments[:MAX_ATTACHMENTS]:
        try:
            raw = base64.b64decode(att.data_b64)
        except (binascii.Error, ValueError):
            continue
        ext = Path(att.name).suffix.lower()
        safe = re.sub(r"[^\w.\- ]", "_", att.name)[:80] or "fichier"
        fpath = dest / f"{uuid4().hex[:8]}__{safe}"
        try:
            fpath.write_bytes(raw)
        except OSError as e:
            log.warning("Sauvegarde de la pièce jointe %s échouée : %s", att.name, e)
            continue
        out.append({
            "name": att.name,
            "path": str(fpath),
            "kind": "image" if ext in IMAGE_EXTS else "doc",
        })
    return out


def _guess_kind(text: str) -> str:
    """Devine le type d'une suggestion d'après son texte (repli quand le petit
    modèle n'émet pas le préfixe [DOC]/[WEB]/[FICHIER])."""
    t = text.lower()
    if any(w in t for w in ("fichier", "tableau", "excel", "word", "pdf",
                            "powerpoint", "présentation", "presentation", "génère",
                            "genere", "crée un", "creer un", "créer un", "rédige",
                            "redige", "export")):
        return "file"
    if any(w in t for w in ("web", "internet", "en ligne", "actualité",
                            "actualite", "dernières", "dernieres", "récent",
                            "recent", "nouveau", "microsoft", "cve")):
        return "web"
    return "docs"


def _parse_welcome(raw: str) -> list[dict]:
    """Sortie du petit modèle -> <=3 suggestions {kind, prompt}. Accepte les
    lignes préfixées [DOC]/[WEB]/[FICHIER] ; sinon devine le type."""
    kmap = {"DOC": "docs", "DOCS": "docs", "WEB": "web",
            "FICHIER": "file", "FICHER": "file", "FILE": "file"}
    out: list[dict] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"\[?(DOCS?|WEB|FICHIER|FICHER|FILE)\]?\s*[:.\-]?\s*(.+)", s, re.I)
        if m:
            kind = kmap.get(m.group(1).upper(), "docs")
            prompt = m.group(2)
        else:
            prompt = re.sub(r"^[\-•*\d.)\s]+", "", s)
            kind = _guess_kind(prompt)
        prompt = prompt.strip().strip('"«»“”').strip()
        if 8 <= len(prompt) <= 120:
            out.append({"kind": kind, "prompt": prompt})
        if len(out) == 3:
            break
    return out


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Jade", docs_url=None, redoc_url=None)

    # Chiffrement au repos (EFS) : index partagé + conversations par utilisateur
    encrypt_at_rest(settings.data_dir)
    encrypt_at_rest(settings.user_data_dir)

    embedder = Embedder(
        settings.embed_model, settings.model_cache_dir, threads=settings.cpu_threads
    )
    store = Store(settings.chroma_path)
    llm = OllamaClient(settings)
    # conversations isolées par utilisateur Windows (%APPDATA%\Jade)
    chats = ChatStore(settings.chats_db)
    from ..memory import MemoryStore

    memory = MemoryStore(settings.user_data_dir / "memory.db", embedder)

    state = {
        "llm_ok": None, "llm_models": [], "llm_error": "", "llm_checked_at": 0.0,
        "indexing": False, "last_index": None,
        "bm25": Bm25Index(), "reranker": None, "reranker_tried": False,
        "cancels": {},  # req_id -> threading.Event (arrêt de génération)
        "welcome": {"at": 0.0, "sig": "", "items": []},  # suggestions d'accueil (cache)
    }
    index_lock = threading.Lock()

    def _rebuild_bm25() -> None:
        if not settings.hybrid_enabled:
            return
        try:
            ids, docs = store.all_documents()
            state["bm25"].build(ids, docs)
            log.info("Index BM25 reconstruit (%d chunks)", len(ids))
        except Exception as e:
            log.warning("Construction BM25 échouée : %s", e)

    def _load_reranker() -> None:
        """Charge le cross-encoder (télécharge le modèle au 1er lancement, ~1 Go).

        Exécuté en tâche de fond au démarrage : le téléchargement ne bloque jamais
        une question. Tant qu'il n'est pas prêt, les requêtes utilisent la fusion
        hybride sans reranking."""
        if not settings.rerank_enabled or state["reranker_tried"]:
            return
        state["reranker_tried"] = True
        try:
            state["reranker"] = Reranker(
                settings.rerank_model, settings.model_cache_dir,
                threads=settings.cpu_threads,
            )
            log.info("Reranker %s chargé", settings.rerank_model)
        except Exception as e:
            log.warning("Reranker indisponible : %s", e)

    def _get_reranker():
        # non bloquant : None tant que le chargement en tâche de fond n'est pas fini
        return state["reranker"]

    # ---------------------------------------------------------------- fond

    def _do_index(full: bool = False) -> None:
        if not index_lock.acquire(blocking=False):
            return  # un run est deja en cours
        state["indexing"] = True
        try:
            t0 = time.perf_counter()
            report = run_index(settings, embedder, store, full=full)
            state["last_index"] = {
                "at": time.strftime("%H:%M:%S"),
                "duration_s": round(time.perf_counter() - t0, 1),
                "indexed": report.indexed,
                "unchanged": report.unchanged,
                "deleted": report.deleted,
                "errors": len(report.skipped_errors),
                "total_chunks": report.total_chunks,
            }
            _rebuild_bm25()  # garder l'index mots-clés synchrone avec le vectoriel
        except Exception as e:
            log.error("Reindexation echouee : %s", e)
            state["last_index"] = {"at": time.strftime("%H:%M:%S"), "error": str(e)}
        finally:
            state["indexing"] = False
            index_lock.release()
            winmem.trim_working_set()  # rendre au système la RAM des buffers d'indexation

    def _background_loop() -> None:
        _rebuild_bm25()  # index BM25 initial
        llm.warmup()  # charge le modele en VRAM des le demarrage
        _check_llm(force=True)
        # migration d'embeddings : si le modèle configuré ne correspond plus à
        # l'index existant, réindexation complète immédiate en tâche de fond
        # (pendant ce temps, BM25 + reranker continuent de répondre).
        try:
            marker = settings.data_dir / "embed_model.txt"
            previous = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
            if store.count() > 0 and previous != embedder.model_name:
                log.info("Migration d'embeddings détectée : réindexation lancée")
                threading.Thread(target=_do_index, daemon=True).start()
        except OSError:
            pass
        _load_reranker()  # télécharge/charge le cross-encoder sans bloquer les requêtes
        winmem.trim_working_set()  # démarrage terminé : libérer la RAM inutilisée
        while True:
            if settings.reindex_minutes > 0:
                time.sleep(settings.reindex_minutes * 60)
                _do_index()
            else:
                return

    threading.Thread(target=_background_loop, daemon=True).start()

    def _gen_title(cid: str, question: str, answer: str) -> None:
        """Titre de conversation généré par le LLM après le premier échange
        (tâche de fond). Ne remplace jamais un titre choisi par l'utilisateur :
        on ne renomme que si le titre est encore le titre automatique."""
        try:
            title = llm.chat([
                {"role": "system", "content":
                    "Tu génères des titres de conversation. Réponds UNIQUEMENT par un "
                    "titre court en français (3 à 6 mots), précis et descriptif, sans "
                    "guillemets, sans ponctuation finale, sans préfixe."},
                {"role": "user", "content":
                    f"Question : {question[:300]}\nRéponse : {answer[:400]}\n\nTitre :"},
            ], model=settings.router_model or None, think=False,
            ).strip().strip('"«»“” ').rstrip(".")
            title = title.splitlines()[0].strip()[:60]
            if len(title) < 3:
                return
            conv = chats.get_conversation(cid)
            if conv and conv["title"] in (question[:60], DEFAULT_TITLE):
                chats.rename(cid, title)
        except Exception as e:  # tâche de confort : ne jamais perturber la réponse
            log.debug("Génération du titre échouée : %s", e)

    # ------------------------------------------------ suggestions (petit modèle)

    def _suggest_followups(question: str, answer: str) -> list[str]:
        """2-3 questions de suivi pertinentes, générées par le PETIT modèle
        (router_model) pour rester économe. Renvoie [] en cas d'échec."""
        if len(answer.strip()) < 40:
            return []
        try:
            raw = llm.chat(
                [
                    {"role": "system", "content":
                        "Propose 3 questions de suivi que L'UTILISATEUR poserait pour "
                        "CONTINUER dans le même fil : approfondir, préciser un point ou "
                        "passer à l'étape suivante logique. Formulées du point de vue de "
                        "l'utilisateur qui s'adresse à l'assistant (ex. « Comment… ? », "
                        "« Peux-tu détailler… ? », « Et pour… ? »). Ne pose JAMAIS de "
                        "question à l'utilisateur. Courtes (max 10 mots), en français, une "
                        "par ligne, se terminant par « ? », sans numéro ni tiret. Rien d'autre."},
                    {"role": "user", "content":
                        f"Question : {question[:300]}\nRéponse : {answer[:700]}\n\n"
                        "Questions de suivi :"},
                ],
                model=settings.router_model or None, think=False,
                options={"temperature": 0.3, "num_predict": 90},
            )
        except Exception as e:
            log.debug("Suggestions de suivi échouées : %s", e)
            return []
        out: list[str] = []
        for line in raw.splitlines():
            s = line.strip().lstrip("-•*—0123456789.) ").strip().strip('"«»“”').strip()
            if s.endswith("?") and 6 <= len(s) <= 100 and s not in out:
                out.append(s)
        return out[:3]

    DEFAULT_WELCOME = [
        {"kind": "docs",
         "prompt": "Résume la procédure de sauvegarde décrite dans nos documents."},
        {"kind": "web",
         "prompt": "Quelles sont les dernières recommandations de sécurité Microsoft 365 ?"},
        {"kind": "file",
         "prompt": "Crée un tableau Excel de suivi des incidents."},
    ]

    def _welcome_suggestions() -> list[dict]:
        """3 suggestions d'accueil personnalisées d'après l'historique de
        l'utilisateur (petit modèle). Résultat mis en cache (min. de ressources)."""
        try:
            convs = [c for c in chats.list_conversations()
                     if c.get("title") and c["title"] != DEFAULT_TITLE]
        except Exception:
            convs = []
        titles = [c["title"] for c in convs[:12]]
        sig = "|".join(sorted(c["id"] for c in convs[:12]))
        cache = state["welcome"]
        if cache["items"] and cache["sig"] == sig and time.time() - cache["at"] < 1800:
            return cache["items"]
        items = DEFAULT_WELCOME
        personalized = False
        if len(titles) >= 2 and state.get("llm_ok") is not False:
            try:
                raw = llm.chat(
                    [
                        {"role": "system", "content":
                            "Tu proposes 3 suggestions d'accueil pour Jade, un assistant "
                            "documentaire d'entreprise. À partir des sujets récents de "
                            "l'utilisateur, propose EXACTEMENT 3 actions pertinentes et "
                            "variées. Chaque ligne : un préfixe [DOC], [WEB] ou [FICHIER] "
                            "suivi d'une question/consigne courte (max 12 mots) en "
                            "français. [DOC]=chercher dans les documents internes, "
                            "[WEB]=recherche web, [FICHIER]=créer un fichier. Réponds "
                            "UNIQUEMENT par 3 lignes."},
                        {"role": "user", "content":
                            "Sujets récents : " + " ; ".join(titles) + "\n\nSuggestions :"},
                    ],
                    model=settings.router_model or None, think=False,
                    options={"temperature": 0.5, "num_predict": 120},
                )
                parsed = _parse_welcome(raw)
                if parsed:
                    # compléter jusqu'à 3 cartes si le modèle en a donné moins
                    items = (parsed + DEFAULT_WELCOME)[:3]
                    personalized = True
            except Exception as e:
                log.debug("Suggestions d'accueil échouées : %s", e)
        # on ne mémorise longtemps que les suggestions personnalisées ; un repli
        # sur les défauts (LLM pas encore prêt) est ré-essayé au prochain appel
        state["welcome"] = {
            "at": time.time() if personalized else 0.0, "sig": sig, "items": items,
        }
        return items

    def _check_llm(force: bool = False) -> None:
        if not force and time.time() - state["llm_checked_at"] < LLM_CHECK_TTL:
            return
        try:
            state["llm_models"] = llm.check()
            state["llm_ok"] = True
            state["llm_error"] = ""
        except LLMError as e:
            state["llm_ok"] = False
            state["llm_error"] = str(e)
        state["llm_checked_at"] = time.time()

    # ---------------------------------------------------------------- API

    @app.get("/")
    def index():
        # API pure : l'interface est l'application native (flutter_app/)
        return {"app": "Jade", "api": "ok", "hint": "interface : application native"}

    @app.get("/api/status")
    def status():
        _check_llm()
        from .. import __version__

        return {
            "client_name": settings.client_name,
            "app_name": "Jade",
            "app_version": __version__,
            "username": _session_display_name(),
            "chunks_indexed": store.count(),
            "docs_dir": str(settings.docs_dir),
            "llm_ok": state["llm_ok"],
            "llm_error": state["llm_error"],
            "indexing": state["indexing"],
            "last_index": state["last_index"],
            "reindex_minutes": settings.reindex_minutes,
        }

    # ------------------------------------------------------------ mises à jour

    @app.get("/api/update")
    def update_check(force: bool = False):
        """État de mise à jour (release Gitea la plus récente). Non bloquant."""
        if not settings.update_enabled:
            from .. import __version__

            return {"current": __version__, "available": False, "mode": "off"}
        return updater.check(settings, force=force)

    @app.post("/api/update/download")
    def update_download():
        """Lance le téléchargement de l'installateur en tâche de fond."""
        if not settings.update_enabled:
            raise HTTPException(400, "Mises à jour désactivées.")
        return updater.start_download(settings)

    @app.get("/api/update/progress")
    def update_progress():
        """Progression du téléchargement (idle | downloading | ready | error)."""
        return updater.download_state()

    @app.post("/api/update/apply")
    def update_apply():
        """Lance l'installateur téléchargé (l'app se ferme juste après)."""
        if not settings.update_enabled:
            raise HTTPException(400, "Mises à jour désactivées.")
        res = updater.apply(settings)
        if not res.get("ok"):
            raise HTTPException(409, res.get("error") or "Installation impossible.")
        return res

    # ------------------------------------------------------------ suggestions

    @app.get("/api/suggestions/welcome")
    def welcome_suggestions():
        """Suggestions d'accueil personnalisées d'après l'historique (par
        utilisateur, cache côté serveur)."""
        return {"suggestions": _welcome_suggestions()}

    # ------------------------------------------------------- préférences (registre)

    @app.get("/api/prefs")
    def get_prefs():
        return {"incognito": prefs.get_bool("Incognito", False)}

    @app.post("/api/prefs")
    def set_prefs(req: PrefsRequest):
        prefs.set_bool("Incognito", req.incognito)
        return {"incognito": req.incognito}

    # -------------------------------------------- arrêt de la génération en cours

    @app.post("/api/stop")
    def stop_generation(req: StopRequest):
        ev = state["cancels"].get(req.req_id)
        if ev is not None:
            ev.set()
            return {"stopped": True}
        return {"stopped": False}

    # ------------------------------------------------------------ index

    @app.post("/api/index")
    def trigger_index():
        if state["indexing"]:
            return {"started": False, "reason": "deja en cours"}
        threading.Thread(target=_do_index, daemon=True).start()
        return {"started": True}

    # ------------------------------------------------------- paramètres (admin)

    def _check_pwd(pwd: str):
        import hmac

        # pas de mot de passe configuré -> réglages verrouillés (jamais un
        # mot de passe vide accepté)
        if not settings.settings_password:
            raise HTTPException(403, "Aucun mot de passe administrateur configuré "
                                     "(SETTINGS_PASSWORD)")
        if not hmac.compare_digest(pwd or "", settings.settings_password):
            raise HTTPException(403, "Mot de passe incorrect")

    @app.post("/api/settings/unlock")
    def settings_unlock(req: ReindexRequest):
        _check_pwd(req.password)
        return {"ok": True}

    @app.get("/api/settings")
    def get_settings():
        from ..index_config import get_roots

        roots = []
        for r in get_roots(settings):
            roots.append({"path": str(r), "online": r.is_dir()})
        return {
            "roots": roots,
            "chunks_indexed": store.count(),
            "indexing": state["indexing"],
            "last_index": state["last_index"],
            "reindex_minutes": settings.reindex_minutes,
        }

    @app.post("/api/settings/roots")
    def edit_roots(req: RootsRequest):
        from ..index_config import get_roots, set_roots

        _check_pwd(req.password)
        current = [str(r) for r in get_roots(settings)]
        # si on part encore du repli DOCS_DIR implicite et qu'on ajoute, on
        # démarre une liste vide pour ne pas coller le dossier de démo
        from ..index_config import _file

        if not _file(settings).exists():
            current = []
        path = req.path.strip().rstrip("\\/")
        if req.action == "add":
            if not path:
                raise HTTPException(400, "Chemin vide")
            if not Path(path).is_dir():
                raise HTTPException(400, f"Dossier introuvable ou inaccessible : {path}")
            current.append(path)
        elif req.action == "remove":
            current = [p for p in current if p != path]
        else:
            raise HTTPException(400, "Action inconnue")
        saved = set_roots(settings, current)
        return {"roots": [{"path": p, "online": Path(p).is_dir()} for p in saved]}

    @app.post("/api/settings/reindex")
    def settings_reindex(req: ReindexRequest):
        _check_pwd(req.password)
        if state["indexing"]:
            return {"started": False, "reason": "déjà en cours"}
        threading.Thread(target=lambda: _do_index(full=req.full), daemon=True).start()
        return {"started": True}

    @app.post("/api/settings/pick-folder")
    def pick_folder(req: ReindexRequest):
        """Ouvre le sélecteur de dossier natif (application de bureau)."""
        _check_pwd(req.password)
        picker = state.get("folder_picker")
        if not picker:
            raise HTTPException(501, "Sélecteur natif indisponible (mode navigateur)")
        try:
            path = picker()
        except Exception as e:
            raise HTTPException(500, f"Sélecteur indisponible : {e}")
        return {"path": path or ""}

    # -------------------------------------------------------------- dossiers

    @app.get("/api/folders")
    def list_folders():
        return chats.list_folders()

    @app.post("/api/folders")
    def create_folder(req: RenameRequest):
        if not req.title.strip():
            raise HTTPException(400, "Nom vide")
        return chats.create_folder(req.title.strip())

    @app.patch("/api/folders/{fid}")
    def rename_folder(fid: str, req: RenameRequest):
        if not req.title.strip():
            raise HTTPException(400, "Nom vide")
        chats.rename_folder(fid, req.title.strip())
        return {"ok": True}

    @app.delete("/api/folders/{fid}")
    def delete_folder(fid: str):
        chats.delete_folder(fid)
        return {"ok": True}

    @app.patch("/api/conversations/{cid}/folder")
    def move_conversation(cid: str, req: FolderAssignRequest):
        chats.set_conv_folder(cid, req.folder_id or None)
        return {"ok": True}

    # -------------------------------------------------------------- mémoire

    @app.get("/api/memory")
    def list_memory():
        return memory.list_all()

    @app.delete("/api/memory/{mid}")
    def delete_memory(mid: int):
        memory.delete(mid)
        return {"ok": True}

    @app.post("/api/memory/clear")
    def clear_memory():
        memory.clear()
        return {"ok": True}

    # ---------------------------------------------------- conversations

    @app.get("/api/conversations")
    def list_conversations(archived: bool = False):
        convs = chats.list_conversations(include_archived=archived)
        if archived:
            return [c for c in convs if c["archived"]]
        return convs

    @app.get("/api/conversations/search")
    def search_conversations(q: str = ""):
        """Recherche dans les titres ET le contenu des conversations."""
        return chats.search(q)

    @app.post("/api/conversations")
    def create_conversation():
        return chats.create_conversation()

    @app.delete("/api/conversations")
    def clear_conversations():
        """Supprime TOUT l'historique de conversations de l'utilisateur."""
        n = chats.clear_all()
        state["welcome"] = {"at": 0.0, "sig": "", "items": []}  # invalide le cache
        return {"deleted": n}

    @app.get("/api/conversations/{cid}")
    def get_conversation(cid: str):
        conv = chats.get_conversation(cid)
        if not conv:
            raise HTTPException(404, "Conversation introuvable")
        return conv

    @app.patch("/api/conversations/{cid}")
    def rename_conversation(cid: str, req: RenameRequest):
        if not req.title.strip():
            raise HTTPException(400, "Titre vide")
        chats.rename(cid, req.title.strip())
        return {"ok": True}

    @app.delete("/api/conversations/{cid}")
    def delete_conversation(cid: str):
        chats.delete(cid)
        return {"ok": True}

    @app.patch("/api/conversations/{cid}/flag")
    def set_flag(cid: str, req: FlagRequest):
        chats.set_flag(cid, req.field, req.value)
        return {"ok": True}

    @app.post("/api/conversations/{cid}/truncate")
    def truncate_conversation(cid: str, req: TruncateRequest):
        # édition d'une question : on efface ce message et tous les suivants
        chats.delete_from(cid, req.message_id)
        return {"ok": True}

    # -------------------------------------------------------- retour utilisateur

    @app.post("/api/feedback")
    def feedback(req: FeedbackRequest):
        """Ouvre directement le client mail : destinataire et objet pré-remplis,
        l'objet contient le nom de la session Windows."""
        import urllib.parse

        user = _session_display_name()
        subject = f"Retour utilisateur - {user}"
        mailto = f"mailto:{settings.feedback_email}?subject={urllib.parse.quote(subject)}"
        if req.content.strip():
            mailto += f"&body={urllib.parse.quote(req.content.strip())}"
        try:
            open_url(mailto)
        except OSError as e:
            raise HTTPException(500, f"Impossible d'ouvrir le client mail : {e}")
        return {"ok": True}

    # ------------------------------------------------------------- ask

    @app.post("/api/conversations/{cid}/ask")
    def ask(cid: str, req: AskRequest):
        question = req.question.strip()
        if not question:
            raise HTTPException(400, "Question vide")
        incognito = req.incognito
        # incognito : conversation éphémère, jamais persistée ni mémorisée ;
        # l'historique est fourni par le client (rien en base).
        if not incognito and chats.get_conversation(cid) is None:
            raise HTTPException(404, "Conversation introuvable")
        # index vide (installation neuve, dossiers pas encore configurés) : on ne
        # bloque plus la question — le routage bascule vers une réponse générale /
        # web / création de fichier, qui ne dépendent pas des documents indexés.

        # arrêt réel côté serveur : le client déclenche /api/stop avec ce req_id,
        # ce qui coupe la boucle de streaming et ferme le flux vers Ollama.
        cancel = threading.Event()
        if req.req_id:
            state["cancels"][req.req_id] = cancel

        offline = req.offline or req.dry_run
        from ..filegen import wanted_format

        file_fmt = wanted_format(question)
        attachments_text, images, att_errors = _process_attachments(req.attachments)
        has_attachments = bool(attachments_text or images)
        # pas de fallback web quand la question porte sur une piece jointe
        force_web = (settings.web_fallback and not offline
                     and not has_attachments and wants_web(question))
        att_names = ", ".join(a.name for a in req.attachments[:MAX_ATTACHMENTS])
        stored_question = (
            f"{question}\n[Pièces jointes : {att_names}]" if att_names else question
        )
        # pièces jointes conservées sur le disque (jamais en incognito) : elles
        # restent consultables/rouvrables depuis l'historique
        saved_atts = (
            [] if incognito
            else _persist_attachments(settings.user_data_dir, cid, req.attachments)
        )
        # dossier (projet) de la conversation : porte la mémoire par dossier
        folder_id = None if incognito else chats.get_folder_id(cid)

        def stream_llm(messages, sources, timings, t_start, model=None, num_ctx=None,
                       file_fmt=None, gen_title=False, rescue_history=None, suggest=True):
            """Streame la generation LLM, sauvegarde le message, emet done.
            file_fmt : si l'utilisateur a demande un fichier (xlsx/docx/pdf), il
            est cree depuis la reponse puis ouvert, et un evenement 'file' est emis."""
            if file_fmt and messages:
                # tableur (xlsx/csv) -> tableau markdown ; le reste -> contenu
                # structuré (titres, listes, tableaux). Défaut sûr si format inconnu.
                if file_fmt in ("xlsx", "csv"):
                    hint = ("Réponds UNIQUEMENT par les données sous forme de tableau "
                            "markdown (| colonne | colonne |), sans phrase d'introduction.")
                elif file_fmt == "pptx":
                    hint = ("Structure la réponse pour une présentation : un titre par "
                            "section (## Titre) puis des puces courtes (- point).")
                else:  # docx, pdf, txt, md, html
                    hint = ("Réponds directement par le CONTENU du document "
                            "(titres #, listes à puces, tableaux markdown).")
                # Le système crée le fichier automatiquement à partir de la réponse :
                # le modèle ne doit JAMAIS expliquer comment créer/convertir un fichier
                # (il le faisait — « ouvrez Word, enregistrez en PDF… »).
                messages[-1]["content"] += (
                    "\n\nConsigne de format : " + hint
                    + " N'explique PAS comment créer ou convertir un fichier et ne donne "
                    "aucune instruction de logiciel : le fichier est généré automatiquement "
                    "à partir de ta réponse."
                )
            answer_parts: list[str] = []
            t_llm = time.perf_counter()
            ttfb_ms = None
            llm_stats: dict = {}
            interrupted = False
            for event in llm.chat_stream(messages, model=model, num_ctx=num_ctx):
                # arrêt demandé : on sort de la boucle, ce qui referme le flux
                # HTTP vers Ollama (fin du generator) et stoppe la génération.
                if cancel.is_set():
                    interrupted = True
                    break
                if event.get("done"):
                    llm_stats = event["stats"]
                    break
                if ttfb_ms is None:
                    ttfb_ms = round((time.perf_counter() - t_llm) * 1000)
                answer_parts.append(event["delta"])
                yield _sse({"type": "token", "delta": event["delta"]})

            answer_text = "".join(answer_parts)
            timings.update(llm_stats)
            timings["llm_ttfb_ms"] = ttfb_ms or 0
            timings["llm_total_ms"] = round((time.perf_counter() - t_llm) * 1000)
            timings["total_ms"] = round((time.perf_counter() - t_start) * 1000)
            if llm_stats.get("completion_tokens") and llm_stats.get("gen_ms"):
                timings["tokens_per_s"] = round(
                    llm_stats["completion_tokens"] / (llm_stats["gen_ms"] / 1000), 1
                )
            not_found = "je ne trouve pas cette information" in answer_text.lower()
            # Les documents ne répondaient pas (souvent des extraits faiblement
            # correspondants sur des mots communs) : on relance en réponse
            # conversationnelle / culture générale — SANS recherche web — en
            # remplaçant la réponse affichée (événement 'reset' côté client).
            if not_found and not interrupted and rescue_history is not None:
                yield _sse({"type": "reset"})
                yield _sse({"type": "sources", "sources": []})
                gen_system = GENERAL_PROMPT.format(client=settings.client_name)
                gen_system += f"\nNous sommes le {today_fr()}."
                mem = "" if incognito else memory.context_for(question, folder_id)
                if mem:
                    gen_system += "\n\nFaits mémorisés sur cet utilisateur :\n" + mem
                gmsgs = [
                    {"role": "system", "content": gen_system},
                    *rescue_history[-6:],
                    {"role": "user", "content": question},
                ]
                # on conserve file_fmt : une demande de fichier doit aboutir même
                # quand les documents ne répondaient pas (repli culture générale)
                yield from stream_llm(gmsgs, [], timings, t_start,
                                      file_fmt=file_fmt, gen_title=gen_title,
                                      suggest=suggest)
                return
            # si la reponse dit qu'elle n'a rien trouve, ne pas afficher de
            # sources : elles seraient contradictoires
            if sources and not_found:
                sources = []
                yield _sse({"type": "sources", "sources": []})
            # création de fichier demandée explicitement (AVANT la persistance :
            # le fichier est attaché au message pour rester visible et rouvrable
            # depuis la conversation, comme une pièce jointe).
            created_file = None
            file_error = None
            if file_fmt and answer_text.strip() and not interrupted:
                from ..filegen import SAVERS

                try:
                    path = SAVERS[file_fmt](question[:60], answer_text)
                    created_file = {"name": path.name, "path": str(path), "kind": "doc"}
                except Exception as e:
                    log.warning("Creation du fichier %s echouee : %s", file_fmt, e)
                    file_error = str(e)
            # incognito : on ne persiste rien et on n'alimente pas la mémoire
            if not incognito:
                chats.add_message(
                    cid, "assistant", answer_text, sources, timings,
                    attachments=[created_file] if created_file else None,
                )
                # mémoire entre conversations : extraction des faits en arrière-plan
                if answer_text.strip() and not interrupted:
                    threading.Thread(
                        target=memory.extract_from_exchange,
                        args=(llm, question, answer_text, folder_id,
                              settings.router_model or None), daemon=True,
                    ).start()
                # titre de conversation amélioré par IA (premier échange)
                if gen_title and answer_text.strip() and not interrupted:
                    threading.Thread(
                        target=_gen_title, args=(cid, question, answer_text),
                        daemon=True,
                    ).start()
            if interrupted:
                yield _sse({"type": "done", "timings": timings, "interrupted": True})
                return
            # fichier créé : on NE l'ouvre PAS automatiquement (l'ouverture volait
            # le focus, la fenêtre du visualiseur passait DEVANT Jade — l'utilisateur
            # croyait l'app disparue). Il apparaît comme carte cliquable dans la
            # réponse ; l'utilisateur l'ouvre d'un clic quand il le souhaite.
            if created_file:
                yield _sse({"type": "file", "path": created_file["path"],
                            "name": created_file["name"]})
            elif file_error:
                yield _sse({"type": "progress",
                            "message": f"Création du fichier impossible : {file_error}"})
            # questions de suivi suggérées (petit modèle, économe) — jamais après
            # un smalltalk (suggest=False) ni une génération interrompue
            if suggest and answer_text.strip():
                followups = _suggest_followups(question, answer_text)
                if followups:
                    yield _sse({"type": "followups", "questions": followups})
            yield _sse({"type": "done", "timings": timings})

        def finish(message, sources, timings, t_start):
            timings["total_ms"] = round((time.perf_counter() - t_start) * 1000)
            if not incognito:
                chats.add_message(cid, "assistant", message, sources or None, timings)
            yield _sse({"type": "notice", "message": message})
            yield _sse({"type": "done", "timings": timings})

        def event_stream():
            nonlocal file_fmt  # la pré-analyse LLM peut compléter le format détecté
            t_start = time.perf_counter()
            if incognito:
                history = [t.model_dump() for t in req.history][-16:]
            else:
                history = chats.history(cid)
                chats.add_message(cid, "user", stored_question,
                                  attachments=saved_atts or None)
                chats.set_title_if_new(cid, question)
            # premier échange d'une conversation persistée : titre généré par IA
            first_exchange = not incognito and not history
            try:
                timings: dict = {}
                hits: list = []
                sources: list = []
                # modèle de génération : « standard » par défaut ; la pré-analyse
                # peut escalader vers le modèle performant (STRONG_MODEL) si la
                # question est complexe. None = OLLAMA_MODEL (standard).
                answer_model = None
                for err in att_errors:
                    yield _sse({"type": "progress", "message": f"Pièce jointe ignorée — {err}"})

                # Message conversationnel (« salut », « merci », propos perso) :
                # réponse directe, sans recherche ni sources. On ne court-circuite
                # PAS si l'utilisateur demande un fichier ou une recherche web.
                if (not has_attachments and not force_web and not file_fmt
                        and is_smalltalk(question)):
                    yield _sse({"type": "sources", "sources": []})
                    if offline:
                        yield from finish("Bonjour ! Posez-moi une question sur vos documents.",
                                          None, timings, t_start)
                        return
                    st_system = SMALLTALK_PROMPT.format(client=settings.client_name)
                    st_system += f"\nNous sommes le {today_fr()}."
                    mem = "" if incognito else memory.context_for(question, folder_id)
                    if mem:
                        st_system += "\n\nFaits mémorisés sur cet utilisateur :\n" + mem
                    messages = [
                        {"role": "system", "content": st_system},
                        *history[-6:],
                        {"role": "user", "content": question},
                    ]
                    yield from stream_llm(messages, [], timings, t_start,
                                          gen_title=first_exchange, suggest=False)
                    return

                if images:
                    _check_llm()
                    if state["llm_ok"] and not any(
                        m.startswith(settings.vision_model.split(":")[0])
                        for m in state["llm_models"]
                    ):
                        yield from finish(
                            "L'analyse d'images nécessite le modèle de vision "
                            f"« {settings.vision_model} », qui n'est pas installé sur le "
                            f"serveur central. Sur AI01 : ollama pull {settings.vision_model}",
                            None, timings, t_start,
                        )
                        return

                def general_answer(file_fmt=None):
                    """Réponse conversationnelle / culture générale, sans recherche
                    ni sources — questions hors documents et sans intention web."""
                    yield _sse({"type": "sources", "sources": []})
                    gen_system = GENERAL_PROMPT.format(client=settings.client_name)
                    gen_system += f"\nNous sommes le {today_fr()}."
                    mem = "" if incognito else memory.context_for(question, folder_id)
                    if mem:
                        gen_system += "\n\nFaits mémorisés sur cet utilisateur :\n" + mem
                    gmsgs = [
                        {"role": "system", "content": gen_system},
                        *history[-6:],
                        {"role": "user", "content": question},
                    ]
                    yield from stream_llm(gmsgs, [], timings, t_start,
                                          model=answer_model,
                                          file_fmt=file_fmt, gen_title=first_exchange)

                # ---- Décision de routage : documents internes / web / direct ----
                # Un routeur LLM court tranche à chaque question (bien plus fiable
                # que les mots-clés) : on ne fouille les documents que si la réponse
                # peut s'y trouver, et on ne va sur le web que si c'est utile.
                has_docs = store.count() > 0
                from ..filegen import is_reformat_request

                if offline or images or has_attachments:
                    decided_route, web_q = "docs", None  # local uniquement
                elif force_web:
                    decided_route, web_q = "web", web_query(question, history)
                elif file_fmt and history and is_reformat_request(question):
                    # « mets ça en pdf » : reformater la réponse précédente en
                    # fichier — le contenu est dans la conversation, pas de recherche
                    decided_route, web_q = "direct", None
                else:
                    decided_route, web_q, llm_fmt, level = route_question(
                        llm, question, history, has_docs,
                        allow_web=settings.web_fallback, model=settings.router_model,
                    )
                    # fichier : le regex explicite prime (instantané, fiable) ;
                    # sinon la pré-analyse récupère les demandes implicites
                    if not file_fmt and llm_fmt:
                        file_fmt = llm_fmt
                    # escalade vers le modèle performant sur les questions complexes
                    if settings.strong_model and level == "complexe":
                        answer_model = settings.strong_model

                # ---- WEB : recherche en ligne encadrée ----
                if decided_route == "web" and not offline:
                    yield _sse({"type": "progress", "message": "Recherche web en cours…"})
                    web_hits, web_timings = web_context(
                        question, settings, search_query=web_q
                    )
                    timings.update(web_timings)
                    if web_hits:
                        sources = format_sources(web_hits)
                        yield _sse({"type": "sources", "sources": sources})
                        messages = build_messages(question, web_hits, history, settings)
                        yield from stream_llm(messages, sources, timings, t_start,
                                              model=answer_model,
                                              file_fmt=file_fmt, gen_title=first_exchange)
                    else:
                        yield from general_answer(file_fmt)
                    return

                # ---- DIRECT : réponse sans recherche (culture générale, rédaction,
                # création de fichier à partir de connaissances générales) ----
                if decided_route == "direct" and not images and not has_attachments:
                    yield from general_answer(file_fmt)
                    return

                # ---- DOCUMENTS : retrieval local hybride ----
                if not images:
                    hits, timings = retrieve_timed(
                        question, history, settings, embedder, store,
                        bm25=state["bm25"], reranker=_get_reranker(),
                    )
                    # droits NTFS : masquer les extraits que cet utilisateur ne
                    # peut pas lire sur le disque (l'index est partagé)
                    if settings.ntfs_filter:
                        hits, _removed = ntfs.filter_readable(hits)
                    sources = format_sources(hits)
                    yield _sse({"type": "sources", "sources": sources})

                if offline:
                    if has_attachments:
                        yield from finish(
                            OFFLINE_NOTICE + " (Les pièces jointes ne peuvent pas être "
                            "analysées en mode hors ligne.)",
                            sources if hits else None, timings, t_start,
                        )
                    elif not hits:
                        yield from finish(NO_INFO_ANSWER, None, timings, t_start)
                    else:
                        yield from finish(OFFLINE_NOTICE, sources, timings, t_start)
                    return

                # Aucun extrait pertinent et pas de pièce jointe : réponse utile
                # (culture générale / conversation) plutôt qu'un échec sec.
                if not hits and not has_attachments:
                    yield from general_answer(file_fmt)
                    return

                messages = build_messages(
                    question, hits, history, settings,
                    attachments_text=attachments_text, images=images or None,
                    memory_text="" if incognito else memory.context_for(question, folder_id),
                )
                model = settings.vision_model if images else answer_model
                # contexte reduit pour la vision : moins de pression VRAM avec
                # les deux modeles charges sur AI01
                num_ctx = min(4096, settings.num_ctx) if images else None
                yield from stream_llm(
                    messages, sources, timings, t_start, model=model, num_ctx=num_ctx,
                    file_fmt=file_fmt, gen_title=first_exchange,
                    # si les documents ne répondent pas (« je ne trouve pas »),
                    # bascule vers une réponse conversationnelle/générale — SANS web —
                    # plutôt qu'un échec sec (sauf si une pièce jointe fournit le contexte)
                    rescue_history=None if (images or has_attachments) else history,
                )
            except LLMError as e:
                yield _sse({"type": "error", "message": str(e)})
            except Exception as e:
                log.exception("Erreur pendant le traitement de la question")
                yield _sse({"type": "error", "message": f"Erreur interne : {e}"})
            finally:
                if req.req_id:
                    state["cancels"].pop(req.req_id, None)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ------------------------------------------------------ creation fichiers

    @app.post("/api/files/save")
    def save_file(req: SaveRequest):
        """Cree un fichier docx/xlsx/pdf a partir d'un contenu (reponse de
        l'assistant) dans Documents\\Jade, puis l'ouvre."""
        from ..filegen import SAVERS

        saver = SAVERS.get(req.format)
        if not saver:
            raise HTTPException(400, f"Format inconnu : {req.format}")
        if not req.content.strip():
            raise HTTPException(400, "Contenu vide")
        try:
            path = saver(req.title.strip() or "document", req.content)
        except Exception as e:
            log.exception("Creation de fichier echouee")
            raise HTTPException(500, f"Création impossible : {e}")
        try:
            open_path(str(path))
        except OSError:
            pass
        return {"path": str(path)}

    # ------------------------------------------------------------ export

    @app.post("/api/conversations/{cid}/export")
    def export_conversation(cid: str):
        """Exporte la conversation en document Word (.docx) et l'ouvre.

        Demonstration de la capacite native : le backend ecrit un vrai
        fichier Office sur le poste (dossier Documents\\Jade de l'utilisateur).
        """
        import re as _re
        from datetime import datetime as _dt

        import docx

        conv = chats.get_conversation(cid)
        if not conv:
            raise HTTPException(404, "Conversation introuvable")
        if not conv["messages"]:
            raise HTTPException(400, "Conversation vide")

        doc = docx.Document()
        doc.add_heading(conv["title"], 0)
        doc.add_paragraph(
            f"Conversation exportée le {_dt.now().strftime('%d.%m.%Y à %H:%M')} — Jade"
        )
        for m in conv["messages"]:
            if m["role"] == "user":
                doc.add_heading(m["content"], level=2)
            else:
                doc.add_paragraph(m["content"])
                if m.get("sources"):
                    src = doc.add_paragraph(
                        "Sources : "
                        + " · ".join(f"[{s['n']}] {s['label']}" for s in m["sources"])
                    )
                    src.runs[0].italic = True

        out_dir = Path.home() / "Documents" / "Jade"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = _re.sub(r"[^\w\- ]", "", conv["title"]).strip()[:40] or "conversation"
        out_path = out_dir / f"{safe} {_dt.now().strftime('%Y-%m-%d %H%M%S')}.docx"
        doc.save(str(out_path))
        try:
            open_path(str(out_path))  # ouvre dans l'appli par défaut
        except OSError:
            pass  # pas de Word installe : le fichier est cree quand meme
        return {"path": str(out_path)}

    # ----------------------------------------------------------- fichiers

    @app.post("/api/open-url")
    def open_url(req: OpenUrlRequest):
        """Ouvre une page web (source de recherche web) dans le navigateur par
        défaut du poste. http/https uniquement — jamais de chemin local ici."""
        from urllib.parse import urlparse

        parsed = urlparse(req.url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(400, "URL invalide")
        try:
            open_url(req.url)  # navigateur par défaut du système
        except OSError as e:
            raise HTTPException(500, f"Ouverture impossible : {e}")
        return {"ok": True}

    def _allowed_roots() -> list[str]:
        """Racines autorisées à l'ouverture : dossiers indexés + pièces jointes +
        fichiers créés par Jade (Documents\\Jade)."""
        from ..filegen import OUTPUT_DIR
        from ..index_config import get_roots

        roots = [settings.docs_dir, settings.user_data_dir / "attachments", OUTPUT_DIR]
        roots += list(get_roots(settings))
        return [str(r.resolve()).casefold() for r in roots]

    @app.get("/api/attachments")
    def get_attachment(path: str):
        """Sert le fichier d'une pièce jointe (aperçu image / consultation)."""
        try:
            resolved = Path(path).resolve(strict=True)
        except OSError:
            raise HTTPException(404, "Pièce jointe introuvable")
        att_root = str((settings.user_data_dir / "attachments").resolve()).casefold()
        if not str(resolved).casefold().startswith(att_root):
            raise HTTPException(403, "Chemin non autorisé")
        return FileResponse(str(resolved))

    @app.post("/api/open")
    def open_file(req: OpenRequest):
        target = Path(req.path)
        try:
            resolved = target.resolve(strict=True)
        except OSError:
            raise HTTPException(404, "Fichier introuvable (supprime ou deplace ?)")
        rp = str(resolved).casefold()
        if not any(rp.startswith(root) for root in _allowed_roots()):
            raise HTTPException(403, "Chemin hors des dossiers autorisés")
        try:
            if req.reveal:
                reveal_path(str(resolved))
            else:
                open_path(str(resolved))  # application par défaut du système
        except OSError as e:
            raise HTTPException(500, f"Ouverture impossible : {e}")
        return {"ok": True}

    app.jade_state = state  # permet au mode bureau d'injecter le sélecteur natif
    return app

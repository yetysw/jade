"""Configuration de Jade, chargee depuis .env (python-dotenv) avec valeurs par defaut."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import site_data_dir
from platformdirs import user_data_dir as _user_data_dir

# HuggingFace : sans ce timeout, un téléchargement bridé (rate-limit HF sur les
# requêtes non authentifiées) peut rester « pendu » indéfiniment → barre figée au
# 1er lancement. Avec un timeout, une connexion muette échoue et notre boucle de
# reprise repart (huggingface_hub reprend les fichiers partiels).
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")

FROZEN = getattr(sys, "frozen", False)  # exécutable PyInstaller (application installée)

if FROZEN:
    # Application installée : le .env vit à côté de l'exécutable backend
    # (écrit par l'assistant d'installation, modifiable par l'admin).
    PROJECT_ROOT = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    # Données partagées (index, journaux, cache modèles) dans le dossier système
    # standard : %PROGRAMDATA%\Jade (Windows), /Library/Application Support/Jade
    # (macOS), /usr/local/share/Jade (Linux) — via platformdirs.
    _SHARED = Path(site_data_dir("Jade", appauthor=False))
    _DEF_DOCS = str(_SHARED / "documents")
    _DEF_DATA = str(_SHARED / "data")
    _DEF_LOGS = str(_SHARED / "logs")
    _DEF_MODELS = str(_SHARED / "models")
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = PROJECT_ROOT
    _DEF_DOCS = r".\testdata"
    _DEF_DATA = r".\data"
    _DEF_LOGS = r".\logs"
    _DEF_MODELS = r".\models"


def _path(value: str) -> Path:
    p = Path(os.path.expandvars(value)).expanduser()
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p.resolve()


def _port(value: str) -> int:
    """UI_PORT : « auto » (ou 0) = port libre choisi au démarrage, publié dans
    le fichier de découverte (voir cli._cmd_serve). Indispensable sur RDS :
    un backend PAR session, sinon les sessions partageraient le même processus
    (conversations et droits NTFS d'un autre utilisateur)."""
    v = value.strip().lower()
    if v in ("auto", ""):
        return 0
    return int(v)


@dataclass
class Settings:
    docs_dir: Path
    data_dir: Path
    log_dir: Path
    embed_model: str
    model_cache_dir: Path
    chunk_tokens: int
    chunk_overlap: int
    top_k: int
    min_score: float
    ollama_url: str
    ollama_model: str  # modèle « standard » (réponses courantes)
    router_model: str  # petit modèle de pré-analyse (routage + fichier + niveau) ; vide = ollama_model
    strong_model: str  # modèle « performant » pour les questions complexes ; vide = ollama_model
    num_ctx: int
    request_timeout: float
    cf_access_client_id: str
    cf_access_client_secret: str
    ui_host: str
    ui_port: int
    client_name: str
    keep_alive: str
    reindex_minutes: int
    web_fallback: bool
    searxng_url: str
    searxng_cf_client_id: str
    searxng_cf_client_secret: str
    web_results: int
    vision_model: str
    feedback_email: str
    ocr_enabled: bool
    ocr_index: bool
    hybrid_enabled: bool
    rerank_enabled: bool
    rerank_model: str
    ntfs_filter: bool
    cpu_threads: int
    # Mises à jour (releases Gitea) — voir updater.py
    update_enabled: bool
    update_mode: str  # "manual" (poste client, bouton) | "scheduled" (RDS, tâche)
    gitea_api_url: str
    gitea_repo: str  # "owner/repo", ex. "example/jade"
    gitea_token: str  # jeton lecture (dépôt privé) ; vide si public
    setup_password: str  # mot de passe de l'installateur chiffré (auto-update silencieux)
    # URL d'une archive .tar des modèles hébergée par Jade (Gitea) : téléchargée
    # au 1er lancement au lieu de HuggingFace (fiable, sur votre infra). Vide =
    # HuggingFace directement. Voir models_fetch.py.
    models_url: str

    # Extensions prises en charge par les parseurs (voir ingest/parsers.py)
    extensions: tuple[str, ...] = field(
        default=(
            ".docx", ".xlsx", ".xls", ".pdf", ".txt", ".md", ".csv",
            ".html", ".htm", ".odt", ".eml", ".msg", ".pst",
        ),
        repr=False,
    )

    @property
    def manifest_path(self) -> Path:
        return self.data_dir / "manifest.db"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def outbound_log(self) -> Path:
        """Journal des appels sortants — PAR UTILISATEUR (%LOCALAPPDATA%), pas
        dans le dossier partagé : il contient les extraits envoyés au LLM, un
        autre utilisateur du serveur ne doit pas pouvoir les lire (le dossier
        partagé est users-modify) ni les falsifier."""
        return self.user_data_dir / "logs" / "outbound.jsonl"

    @property
    def user_data_dir(self) -> Path:
        """Dossier par utilisateur : les conversations de chaque session y sont
        isolées (local, non itinérant). %LOCALAPPDATA%\\Jade (Windows),
        ~/Library/Application Support/Jade (macOS), ~/.local/share/Jade (Linux)."""
        return Path(_user_data_dir("Jade", appauthor=False))

    @property
    def chats_db(self) -> Path:
        return self.user_data_dir / "chats.db"


    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.log_dir, self.model_cache_dir,
                  self.user_data_dir / "logs"):
            d.mkdir(parents=True, exist_ok=True)


def load_settings(env_file: str | Path | None = None) -> Settings:
    # Le .env peut avoir été écrit en ANSI/cp1252 (assistant Inno) ou contenir
    # des accents saisis à la main : on tente l'UTF-8 puis on retombe sur cp1252
    # (qui décode n'importe quel octet) au lieu de planter au démarrage.
    env_path = env_file or PROJECT_ROOT / ".env"
    try:
        load_dotenv(env_path, encoding="utf-8")
    except UnicodeDecodeError:
        load_dotenv(env_path, encoding="cp1252")

    from .security import unprotect

    def get(key: str, default: str = "") -> str:
        # valeurs scellées DPAPI (« jade seal-env » à l'installation) :
        # déchiffrement transparent — le reste du code ignore le scellement
        return unprotect(os.environ.get(key, default))
    return Settings(
        docs_dir=_path(get("DOCS_DIR", _DEF_DOCS)),
        data_dir=_path(get("DATA_DIR", _DEF_DATA)),
        log_dir=_path(get("LOG_DIR", _DEF_LOGS)),
        # multilingual-e5-large (1024d) : nettement meilleur que MiniLM en
        # multilingue (préfixes query/passage gérés par Embedder). Changer de
        # modèle déclenche automatiquement une réindexation complète.
        embed_model=get("EMBED_MODEL", "intfloat/multilingual-e5-large"),
        model_cache_dir=_path(get("MODEL_CACHE_DIR", _DEF_MODELS)),
        chunk_tokens=int(get("CHUNK_TOKENS", "400")),
        chunk_overlap=int(get("CHUNK_OVERLAP", "60")),
        top_k=int(get("TOP_K", "10")),
        min_score=float(get("MIN_SCORE", "0.35")),
        ollama_url=get("OLLAMA_URL", "https://llm.example.com").rstrip("/"),
        ollama_model=get("OLLAMA_MODEL", "qwen3.5:4b"),
        # petit modèle rapide pour la pré-analyse (routage docs/web/direct +
        # détection de fichier) — ex. qwen3.5:2b sur AI01.
        # Vide -> réutilise le modèle principal (aucun changement d'infra requis).
        router_model=get("ROUTER_MODEL", ""),
        # modèle performant pour les questions complexes (analyse, rédaction
        # longue, raisonnement) ; vide -> pas d'escalade, on garde OLLAMA_MODEL.
        strong_model=get("STRONG_MODEL", ""),
        num_ctx=int(get("NUM_CTX", "8192")),
        request_timeout=float(get("REQUEST_TIMEOUT", "120")),
        cf_access_client_id=get("CF_ACCESS_CLIENT_ID", ""),
        cf_access_client_secret=get("CF_ACCESS_CLIENT_SECRET", ""),
        ui_host=get("UI_HOST", "127.0.0.1"),
        ui_port=_port(get("UI_PORT", "8765")),
        client_name=get("CLIENT_NAME", "Jade"),
        keep_alive=get("KEEP_ALIVE", "30m"),
        reindex_minutes=int(get("REINDEX_MINUTES", "30")),
        web_fallback=get("WEB_FALLBACK", "1") not in ("0", "false", ""),
        searxng_url=get("SEARXNG_URL", "").rstrip("/"),
        searxng_cf_client_id=get("SEARXNG_CF_ACCESS_CLIENT_ID", ""),
        searxng_cf_client_secret=get("SEARXNG_CF_ACCESS_CLIENT_SECRET", ""),
        web_results=int(get("WEB_RESULTS", "3")),
        vision_model=get("VISION_MODEL", "qwen3.5:9b"),
        feedback_email=get("FEEDBACK_EMAIL", "feedback@example.com"),
        ocr_enabled=get("OCR_ENABLED", "1") not in ("0", "false", ""),
        ocr_index=get("OCR_INDEX", "1") not in ("0", "false", ""),
        hybrid_enabled=get("HYBRID_ENABLED", "1") not in ("0", "false", ""),
        # activé par défaut : le reranking cross-encoder (top-50 -> top-8) est le
        # plus gros gain de qualité du pipeline (similarité vectorielle ≠
        # pertinence réelle). Chargé en tâche de fond, RAM rendue via winmem.
        # Désactivable sur poste très contraint (RERANK_ENABLED=0).
        rerank_enabled=get("RERANK_ENABLED", "1") not in ("0", "false", ""),
        rerank_model=get("RERANK_MODEL", "jinaai/jina-reranker-v2-base-multilingual"),
        ntfs_filter=get("NTFS_FILTER", "1") not in ("0", "false", ""),
        # threads ONNX (embeddings/reranker) : borné pour ne pas monopoliser le
        # CPU d'un serveur RDS partagé
        cpu_threads=int(get("CPU_THREADS", "2")),
        update_enabled=get("UPDATE_ENABLED", "1") not in ("0", "false", ""),
        # "manual" par défaut (poste client) ; "scheduled" sur serveur RDS où la
        # mise à jour est appliquée par une tâche planifiée (le bouton est masqué).
        update_mode=get("UPDATE_MODE", "manual").strip().lower(),
        gitea_api_url=get("GITEA_API_URL", "https://git.example.com").rstrip("/"),
        gitea_repo=get("GITEA_REPO", "example/jade").strip("/ "),
        gitea_token=get("GITEA_TOKEN", ""),
        setup_password=get("SETUP_PASSWORD", ""),
        models_url=get(
            "MODELS_URL",
            "https://models.example.com/jade-models.tar",
        ).strip(),
    )

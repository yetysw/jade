"""CLI : jade check | index [--full] | ask "question" [--dry-run] | serve."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jade", description="Jade — assistant documentaire local (backend)"
    )
    parser.add_argument("--env", help="Chemin d'un fichier .env alternatif")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Verifie embeddings, store local et acces au LLM central")

    p_index = sub.add_parser("index", help="Indexe (incrementalement) le dossier DOCS_DIR")
    p_index.add_argument("--full", action="store_true", help="Purge et reindexe tout")

    p_ask = sub.add_parser("ask", help="Pose une question")
    p_ask.add_argument("question")
    p_ask.add_argument(
        "--dry-run", action="store_true",
        help="Retrieval local seul : affiche les extraits sans appeler le LLM",
    )
    p_ask.add_argument("--json", action="store_true", help="Sortie JSON brute")

    sub.add_parser("serve", help="Lance le backend local (localhost uniquement) ; "
                                 "l'interface est l'application native (flutter_app/)")

    sub.add_parser("seal-env", help="Scelle les secrets du .env (DPAPI machine) — "
                                    "lance par l'installateur, idempotent")

    args = parser.parse_args(argv)
    # Console Windows souvent en cp1252 : force UTF-8 pour ne jamais crasher
    # sur un caractere exotique (ex. pages d'erreur Cloudflare)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # Reduit le bruit des libs
    for noisy in ("httpx", "chromadb", "onnxruntime"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    from .config import load_settings

    settings = load_settings(args.env)
    settings.ensure_dirs()

    if args.command == "check":
        return _cmd_check(settings)
    if args.command == "index":
        return _cmd_index(settings, args.full)
    if args.command == "ask":
        return _cmd_ask(settings, args.question, args.dry_run, args.json)
    if args.command == "serve":
        return _cmd_serve(settings)
    if args.command == "seal-env":
        return _cmd_seal_env(args.env)
    return 2


def _load_local_stack(settings):
    from .embedding import Embedder
    from .store import Store

    print(f"* Modele d'embeddings : {settings.embed_model} (chargement...)")
    embedder = Embedder(settings.embed_model, settings.model_cache_dir)
    store = Store(settings.chroma_path)
    return embedder, store


def _cmd_check(settings) -> int:
    from .llm import LLMError, OllamaClient

    ok = True
    embedder, store = _load_local_stack(settings)
    vec = embedder.embed_query("Bonjour, ceci est un test.")
    print(f"  OK — embeddings locaux ({embedder.model_name}, dim {len(vec)})")
    print(f"  OK — vector store local ({store.count()} chunks indexes)")

    print(f"* LLM central : {settings.ollama_url} (modele {settings.ollama_model})")
    llm = OllamaClient(settings)
    try:
        models = llm.check()
        print(f"  OK — Ollama joignable, modeles disponibles : {', '.join(models)}")
        if not any(m.startswith(settings.ollama_model.split(":")[0]) for m in models):
            print(f"  ATTENTION — {settings.ollama_model} absent d'AI01. "
                  f"Sur AI01 : ollama pull {settings.ollama_model}")
    except LLMError as e:
        ok = False
        print(f"  ECHEC — {e}")
    finally:
        llm.close()
    return 0 if ok else 1


def _cmd_index(settings, full: bool) -> int:
    from .ingest.indexer import run_index

    embedder, store = _load_local_stack(settings)
    print(f"* Indexation de {settings.docs_dir} {'(complete)' if full else '(incrementale)'}")
    t0 = time.perf_counter()
    report = run_index(settings, embedder, store, full=full)
    dt = time.perf_counter() - t0
    print(
        f"  Termine en {dt:.1f}s — {report.indexed} indexes, {report.unchanged} inchanges, "
        f"{report.deleted} supprimes, {len(report.skipped_errors)} erreurs. "
        f"Total : {report.total_chunks} chunks."
    )
    for p in report.skipped_errors:
        print(f"  ERREUR ignoree : {p}")
    return 0


def _cmd_ask(settings, question: str, dry_run: bool, as_json: bool) -> int:
    from .llm import LLMError, OllamaClient
    from .rag import build_messages, format_sources, retrieve_timed

    embedder, store = _load_local_stack(settings)
    if store.count() == 0:
        print("Aucun document indexe. Lancer d'abord : jade index")
        return 1

    llm = None if dry_run else OllamaClient(settings)
    try:
        t0 = time.perf_counter()
        hits, _ = retrieve_timed(question, [], settings, embedder, store)
        result = {"answer": None, "sources": format_sources(hits)}
        if not hits:
            result["answer"] = ("Je ne trouve pas d'information pertinente dans les "
                                "documents indexes pour cette question.")
        elif not dry_run:
            result["answer"] = llm.chat(build_messages(question, hits, [], settings))
        dt = time.perf_counter() - t0
    except LLMError as e:
        print(f"ECHEC de l'appel au LLM central : {e}", file=sys.stderr)
        return 1
    finally:
        if llm:
            llm.close()

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if result["answer"] is not None:
        print(f"\n=== Reponse ({dt:.1f}s) ===\n{result['answer']}\n")
    print("=== Sources (retrieval local) ===")
    for s in result["sources"]:
        print(f"[Source {s['n']}] {s['label']} (score {s['score']})")
        if dry_run:
            preview = s["text"][:300].replace("\n", " ")
            print(f"    {preview}...")
    return 0


# Clés du .env scellées par « seal-env » (DPAPI machine). Les autres valeurs
# (URLs, réglages) restent lisibles : seuls les secrets sont chiffrés.
_SECRET_KEYS = (
    "CF_ACCESS_CLIENT_SECRET",
    "SEARXNG_CF_ACCESS_CLIENT_SECRET",
    "LICENSE_CF_ACCESS_CLIENT_SECRET",
    "LICENSE_KEY",
    "GITEA_TOKEN",
    "SETUP_PASSWORD",
)


def _cmd_seal_env(env_file: str | None) -> int:
    """Chiffre (DPAPI machine) les valeurs secrètes du .env, en place.

    Lancé par l'installateur (contexte élevé, Program Files inscriptible).
    Idempotent : une valeur déjà scellée ou vide est laissée telle quelle.
    Hors Windows / DPAPI absent : no-op propre."""
    from .config import PROJECT_ROOT
    from .security import DPAPI_MACHINE_PREFIX, protect_machine

    path = _path_of(env_file) or PROJECT_ROOT / ".env"
    if not path.exists():
        print(f"seal-env : aucun fichier {path} — rien a faire")
        return 0
    if sys.platform != "win32":
        print("seal-env : DPAPI indisponible (hors Windows) — fichier laisse en clair")
        return 0
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="cp1252")
    out, sealed = [], 0
    for line in raw.splitlines():
        stripped = line.strip()
        key, _, value = stripped.partition("=")
        if (
            not stripped.startswith("#") and key.strip() in _SECRET_KEYS
            and value and not value.startswith(DPAPI_MACHINE_PREFIX)
        ):
            try:
                line = f"{key.strip()}={protect_machine(value)}"
                sealed += 1
            except OSError as e:
                print(f"seal-env : echec sur {key.strip()} ({e}) — laisse en clair")
        out.append(line)
    if sealed:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"seal-env : {sealed} secret(s) scelle(s) dans {path}")
    return 0


def _path_of(value: str | None):
    from pathlib import Path

    return Path(value) if value else None


def _free_port() -> int:
    """Choisit un port libre sur 127.0.0.1 (fenêtre minuscule de course :
    acceptable en local, le bind uvicorn échouerait bruyamment sinon)."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_discovery(settings, port: int, token: str) -> None:
    """Publie port + jeton de session du backend de CETTE session dans
    %LOCALAPPDATA%\\Jade — par utilisateur. Le jeton authentifie l'UI auprès de
    SON backend : sur RDS le loopback est commun à toutes les sessions, donc le
    port seul ne suffit pas (un co-utilisateur peut le trouver via netstat).
    backend.json hérite de l'ACL du profil utilisateur → illisible par un autre
    utilisateur standard, donc son jeton reste secret."""
    import os

    info = {"port": port, "pid": os.getpid(), "token": token}
    path = settings.user_data_dir / "backend.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info), encoding="utf-8")


def _already_running(settings) -> int | None:
    """Port d'un backend déjà vivant pour CET utilisateur, sinon None. Le jeton
    est vérifié : un backend qui répond sans notre jeton (port réutilisé par la
    session d'un autre utilisateur) est rejeté."""
    import httpx

    path = settings.user_data_dir / "backend.json"
    if not path.exists():
        return None
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        port, token = int(info["port"]), info.get("token", "")
        r = httpx.get(f"http://127.0.0.1:{port}/api/status",
                      headers={"X-Jade-Token": token}, timeout=2.0)
        if r.status_code == 200 and r.json().get("app_name") == "Jade":
            return port
    except Exception:
        pass
    return None


def _cmd_serve(settings) -> int:
    import secrets

    import uvicorn

    if settings.ui_host not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"REFUS : UI_HOST={settings.ui_host}. Jade ne sert qu'en localhost "
            "(pas d'exposition reseau).",
            file=sys.stderr,
        )
        return 1

    port = settings.ui_port
    if port == 0:  # UI_PORT=auto : un backend PAR session (isolation RDS)
        existing = _already_running(settings)
        if existing:
            print(f"* Backend deja en cours pour cette session (port {existing})")
            return 0
        port = _free_port()

    from .web.app import create_app

    token = secrets.token_urlsafe(32)
    app = create_app(settings, token=token)
    _write_discovery(settings, port, token)
    print(f"* Backend local (API) : http://{settings.ui_host}:{port} "
          "— interface : application native (flutter_app/)")
    uvicorn.run(app, host=settings.ui_host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())

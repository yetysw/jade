"""Mises à jour de l'application via les *releases* Gitea.

Source de vérité : les *releases* du dépôt Gitea (`git.example.com`). Chaque
version publie un installateur en pièce jointe (`Jade-Setup-x.y.z.exe` sous
Windows). Le backend :

1. **détecte** une version plus récente (`check`) en interrogeant l'API Gitea ;
2. **télécharge** l'installateur en tâche de fond, avec progression (`start_download`) ;
3. **applique** en lançant l'installateur (`apply`) — Inno Setup ferme puis
   relance l'application (Restart Manager).

Deux modes (`UPDATE_MODE`) :

- ``manual`` (postes clients) : l'UI affiche un bouton « Mise à jour disponible » ;
  l'utilisateur déclenche quand il veut. Install par utilisateur (%LOCALAPPDATA%),
  donc pas d'UAC.
- ``scheduled`` (serveurs RDS) : l'UI **n'affiche pas** de bouton ; une tâche
  planifiée nocturne (voir ``installer/jade-update-task.ps1``) applique la mise
  à jour hors session, avec droits élevés.

Tout est *best-effort* et dégrade proprement : sans réseau / sans release, on
renvoie simplement « à jour », jamais d'erreur bloquante.
"""

from __future__ import annotations

import logging
import platform
import threading
import time
from pathlib import Path

import httpx
from platformdirs import user_data_dir

from . import __version__
from .config import Settings

log = logging.getLogger(__name__)

_CHECK_TTL = 3600.0  # cache de la vérification (1 h) — pas la peine de marteler Gitea
_CHECK_TIMEOUT = 8.0  # s : la vérification ne doit jamais faire attendre l'UI

# --- extension de l'installateur attendue selon la plateforme -----------------
# Windows : Inno Setup (.exe). macOS : .dmg. Linux : .AppImage (ou .deb).
_ASSET_SUFFIXES = {
    "windows": (".exe",),
    "darwin": (".dmg",),
    "linux": (".AppImage", ".deb"),
}


def _platform_key() -> str:
    return {"Windows": "windows", "Darwin": "darwin", "Linux": "linux"}.get(
        platform.system(), "linux"
    )


def _parse_version(raw: str) -> tuple[int, ...]:
    """« v1.3.0 » ou « 1.3.0+2 » -> (1, 3, 0). Robuste aux suffixes."""
    s = (raw or "").strip().lstrip("vV")
    s = s.split("+", 1)[0].split("-", 1)[0]  # ignore build/pré-release
    parts: list[int] = []
    for p in s.split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        if not num:
            break
        parts.append(int(num))
    return tuple(parts) or (0,)


def _is_newer(candidate: str, current: str) -> bool:
    return _parse_version(candidate) > _parse_version(current)


# ------------------------------------------------------------------ vérification

_check_cache: dict | None = None
_check_at: float = 0.0
_check_lock = threading.Lock()


def _headers(settings: Settings) -> dict[str, str]:
    tok = getattr(settings, "gitea_token", "")
    return {"Authorization": f"token {tok}"} if tok else {}


def _pick_asset(assets: list[dict]) -> dict | None:
    """Choisit l'installateur correspondant à la plateforme courante."""
    suffixes = _ASSET_SUFFIXES.get(_platform_key(), (".exe",))
    for a in assets:
        name = (a.get("name") or "").lower()
        if any(name.endswith(sfx.lower()) for sfx in suffixes):
            return a
    return None


def _fetch_latest(settings: Settings) -> dict:
    """Interroge l'API Gitea. Retourne le dict de vérification (voir check)."""
    current = __version__
    base = getattr(settings, "gitea_api_url", "").rstrip("/")
    repo = getattr(settings, "gitea_repo", "")
    result = {
        "current": current,
        "latest": current,
        "available": False,
        "mode": getattr(settings, "update_mode", "manual"),
        "notes": "",
        "asset_name": "",
        "asset_url": "",
        "asset_size": 0,
        "error": "",
    }
    if not base or not repo:
        result["error"] = "Mise à jour non configurée (GITEA_API_URL/GITEA_REPO)."
        return result
    url = f"{base}/api/v1/repos/{repo}/releases/latest"
    try:
        with httpx.Client(timeout=_CHECK_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=_headers(settings))
            resp.raise_for_status()
            rel = resp.json()
    except Exception as e:  # réseau, 404 (aucune release), auth… : non bloquant
        log.info("Vérification de mise à jour indisponible : %s", e)
        result["error"] = "Vérification impossible (hors ligne ou aucune version publiée)."
        return result

    latest = str(rel.get("tag_name") or rel.get("name") or "").strip()
    result["latest"] = latest.lstrip("vV") or current
    result["notes"] = str(rel.get("body") or "").strip()
    asset = _pick_asset(rel.get("assets") or [])
    if asset:
        result["asset_name"] = asset.get("name") or ""
        result["asset_url"] = asset.get("browser_download_url") or ""
        result["asset_size"] = int(asset.get("size") or 0)
    result["available"] = bool(
        latest and _is_newer(latest, current) and result["asset_url"]
    )
    return result


def check(settings: Settings, *, force: bool = False) -> dict:
    """Vérifie s'il existe une version plus récente (résultat mis en cache 1 h)."""
    global _check_cache, _check_at
    now = time.monotonic()
    with _check_lock:
        if not force and _check_cache is not None and now - _check_at < _CHECK_TTL:
            return dict(_check_cache)
    fresh = _fetch_latest(settings)
    with _check_lock:
        _check_cache = fresh
        _check_at = now
    return dict(fresh)


# ------------------------------------------------------------------ téléchargement

# État partagé du téléchargement (un seul à la fois, processus backend unique).
_dl_lock = threading.Lock()
_dl_state: dict = {
    "state": "idle",  # idle | downloading | ready | error
    "done": 0,
    "total": 0,
    "path": "",
    "name": "",
    "error": "",
}


def _updates_dir() -> Path:
    d = Path(user_data_dir("Jade", appauthor=False)) / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_state() -> dict:
    with _dl_lock:
        return dict(_dl_state)


def _reset_state(**kw) -> None:
    with _dl_lock:
        _dl_state.update(
            {"state": "idle", "done": 0, "total": 0, "path": "", "name": "", "error": ""}
        )
        _dl_state.update(kw)


def _download_worker(settings: Settings, url: str, name: str, size: int) -> None:
    dest = _updates_dir() / name
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with httpx.Client(timeout=None, follow_redirects=True) as client:
            with client.stream("GET", url, headers=_headers(settings)) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length") or size or 0)
                with _dl_lock:
                    _dl_state["total"] = total
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=256 * 1024):
                        f.write(chunk)
                        with _dl_lock:
                            _dl_state["done"] += len(chunk)
        tmp.replace(dest)
        with _dl_lock:
            _dl_state["state"] = "ready"
            _dl_state["path"] = str(dest)
        log.info("Mise à jour téléchargée : %s", dest)
    except Exception as e:
        log.warning("Échec du téléchargement de la mise à jour : %s", e)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        with _dl_lock:
            _dl_state["state"] = "error"
            _dl_state["error"] = "Téléchargement interrompu."


def start_download(settings: Settings) -> dict:
    """Lance (si besoin) le téléchargement de l'installateur en tâche de fond."""
    with _dl_lock:
        if _dl_state["state"] == "downloading":
            return dict(_dl_state)
    info = check(settings)
    if not info.get("available") or not info.get("asset_url"):
        _reset_state(state="error", error="Aucune mise à jour à télécharger.")
        return download_state()
    name = info["asset_name"]
    _reset_state(state="downloading", name=name, total=info.get("asset_size", 0))
    threading.Thread(
        target=_download_worker,
        args=(settings, info["asset_url"], name, info.get("asset_size", 0)),
        daemon=True,
    ).start()
    return download_state()


# ------------------------------------------------------------------ application

def apply(settings: Settings) -> dict:
    """Lance l'installateur téléchargé. Inno Setup (Restart Manager) ferme puis
    relance Jade. L'UI doit se fermer juste après cet appel."""
    import subprocess
    import sys

    with _dl_lock:
        state, path = _dl_state["state"], _dl_state["path"]
    if state != "ready" or not path or not Path(path).exists():
        return {"ok": False, "error": "Aucun installateur prêt."}
    try:
        if sys.platform == "win32":
            # Inno : ferme les applis ouvertes et relance après installation.
            subprocess.Popen(
                [path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
                close_fds=True,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen([path])
        return {"ok": True}
    except Exception as e:
        log.warning("Impossible de lancer l'installateur : %s", e)
        return {"ok": False, "error": str(e)}

"""Licence côté client — vérification de l'abonnement, non bloquante, avec grâce.

Calqué sur updater.py : au démarrage + périodiquement, le backend interroge le
serveur de licences Jade (`LICENSE_URL`, derrière Cloudflare Access) avec sa clé
opaque `LICENSE_KEY`. Le serveur renvoie un JWT Ed25519 court (« bail ») que l'on
**vérifie hors ligne** avec la clé publique embarquée (`LICENSE_PUBLIC_KEY`), puis
que l'on met en cache (partagé, ProgramData) — ainsi Jade continue de fonctionner
tant que le tunnel est momentanément indisponible, jusqu'au bail + période de
grâce. Le kill-switch dur reste la révocation du token Cloudflare par client.

États exposés : off (désactivé) · active · grace (serveur injoignable / bail juste
dépassé, dans la fenêtre de grâce) · expired · suspended (le serveur a répondu
« invalide »). L'appel /ask n'est bloqué proprement que pour expired/suspended.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .config import Settings

log = logging.getLogger(__name__)

_TTL = 3600.0            # cache mémoire de l'état (1 h)
_VERIFY_TIMEOUT = 8.0

_state_cache: dict | None = None
_state_at = 0.0
_lock = threading.Lock()


def _jwt_path(s: Settings) -> Path:
    # cache PARTAGÉ entre sessions RDS (décision produit) : dossier de données machine
    return s.data_dir.parent / "license.jwt"


def _marker_path(s: Settings) -> Path:
    return s.data_dir.parent / "license.state.json"


def _cf_headers(s: Settings) -> dict[str, str]:
    if s.license_cf_client_id and s.license_cf_client_secret:
        return {"CF-Access-Client-Id": s.license_cf_client_id,
                "CF-Access-Client-Secret": s.license_cf_client_secret}
    return {}


def _decode(token: str, s: Settings) -> dict | None:
    """Vérifie la signature Ed25519 + exp (hors ligne). None si invalide."""
    if not token or not s.license_public_key:
        return None
    try:
        import jwt

        return jwt.decode(token, s.license_public_key, algorithms=["EdDSA"],
                          options={"require": ["exp", "sub"]})
    except Exception as e:  # signature/exp invalide, lib absente…
        log.debug("JWT licence invalide : %s", e)
        return None


def refresh(settings: Settings) -> None:
    """Interroge le serveur de licences et met à jour le cache local. Best-effort :
    une panne réseau ne change pas l'état (le cache/grâce prend le relais)."""
    if not settings.license_enabled or not settings.license_url or not settings.license_key:
        return
    url = settings.license_url.rstrip("/") + "/api/verify"
    try:
        with httpx.Client(timeout=_VERIFY_TIMEOUT, follow_redirects=True) as client:
            resp = client.post(url, headers=_cf_headers(settings),
                               json={"key": settings.license_key})
        if resp.status_code == 200:
            token = resp.json().get("token", "")
            if _decode(token, settings) is not None:  # ne cache qu'un JWT valide
                _jwt_path(settings).write_text(token, encoding="utf-8")
                _marker_path(settings).write_text(
                    json.dumps({"last": "active", "at": time.time()}), encoding="utf-8")
        elif resp.status_code == 403:
            # réponse générique du serveur = licence invalide/suspendue/expirée
            _marker_path(settings).write_text(
                json.dumps({"last": "invalid", "at": time.time()}), encoding="utf-8")
    except httpx.HTTPError as e:
        log.info("Serveur de licences injoignable (%s) — grâce hors ligne", e)


def _compute(settings: Settings) -> dict:
    if not settings.license_enabled:
        return {"status": "off"}
    grace_s = max(0, settings.grace_days) * 86400
    now = time.time()

    marker = {}
    try:
        marker = json.loads(_marker_path(settings).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if marker.get("last") == "invalid":
        return {"status": "suspended", "detail": "Licence suspendue ou expirée."}

    token = ""
    try:
        token = _jwt_path(settings).read_text(encoding="utf-8").strip()
    except OSError:
        pass
    claims = _decode(token, settings) if token else None

    if claims is None and not token:
        # jamais réussi à obtenir de bail (1re install / hors ligne) : grâce initiale
        return {"status": "grace", "detail": "Vérification de licence en attente."}

    # claims=None ici = JWT présent mais expiré (decode rejette exp) → on relit exp
    exp = _read_exp(token)
    sub_end = _read_sub_end(token)
    if claims is not None:
        return {"status": "active", "sub_end": sub_end,
                "days_left": _days(exp, now)}
    if exp and now < exp + grace_s:
        return {"status": "grace", "sub_end": sub_end,
                "detail": "Vérification indisponible — l'application continue."}
    return {"status": "expired", "sub_end": sub_end,
            "detail": "Abonnement Jade échu. Contactez Jade (feedback@example.com)."}


def _read_exp(token: str) -> float | None:
    p = _payload(token)
    return float(p["exp"]) if p and "exp" in p else None


def _read_sub_end(token: str) -> str:
    p = _payload(token)
    return (p or {}).get("sub_end", "")


def _payload(token: str) -> dict | None:
    """Décode le payload SANS vérifier (pour lire exp/sub_end d'un JWT expiré)."""
    try:
        import base64

        seg = token.split(".")[1]
        seg += "=" * (-len(seg) % 4)
        return json.loads(base64.urlsafe_b64decode(seg))
    except Exception:
        return None


def _days(exp: float | None, now: float) -> int:
    return max(0, int((exp - now) // 86400)) if exp else 0


def status(settings: Settings, *, force: bool = False) -> dict:
    """État de licence (mis en cache 1 h). Ne lève jamais."""
    global _state_cache, _state_at
    now = time.monotonic()
    with _lock:
        if not force and _state_cache is not None and now - _state_at < _TTL:
            return dict(_state_cache)
    st = _compute(settings)
    with _lock:
        _state_cache = st
        _state_at = now
    return dict(st)


def blocks_usage(settings: Settings) -> str | None:
    """Message de blocage si l'usage doit être refusé (expired/suspended), sinon
    None. active/grace/off n'empêchent pas l'utilisation."""
    st = status(settings)
    if st.get("status") in ("expired", "suspended"):
        return st.get("detail") or "Licence Jade invalide. Contactez Jade."
    return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

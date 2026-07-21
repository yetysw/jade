"""Journal d'audit des appels sortants.

Chaque appel HTTP sortant est enregistre AVANT emission dans logs/outbound.jsonl :
c'est la preuve demontrable que seul du texte (question + extraits) quitte le poste.
Le secret Cloudflare est masque dans le journal.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_REDACTED_HEADERS = {"cf-access-client-secret", "authorization"}


def log_outbound(log_path: Path, method: str, url: str, headers: dict, body: object) -> None:
    safe_headers = {
        k: ("***" if k.lower() in _REDACTED_HEADERS else v) for k, v in headers.items()
    }
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": method,
        "url": url,
        "headers": safe_headers,
        "body": body,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

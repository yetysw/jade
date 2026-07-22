"""Téléchargement fiable des modèles de recherche depuis une archive Jade.

Au 1er lancement, les modèles (embeddings + reranker, ~3,2 Go) sont d'habitude
tirés de HuggingFace — mais les requêtes non authentifiées y sont **bridées**
(rate-limit), ce qui fait « pendre » le téléchargement plusieurs minutes derrière
certains réseaux (barre figée au démarrage).

Si `MODELS_URL` est configurée, on télécharge à la place une **archive .tar**
hébergée par Jade (Gitea, servie via Cloudflare — les téléchargements ne sont pas
limités, contrairement aux envois). Avantages :

- **une seule requête** au lieu de dizaines de fichiers HF ;
- **reprise** sur coupure (en-tête HTTP Range) : un téléchargement interrompu
  repart d'où il s'est arrêté au lieu de tout recommencer ;
- **timeouts + retries** : jamais de blocage infini.

L'archive contient le cache fastembed « déréférencé » (symlinks résolus, sans le
dossier `blobs/`) ; extraite dans `MODEL_CACHE_DIR`, fastembed y trouve les
modèles sans aucun appel réseau (validé hors-ligne).
"""

from __future__ import annotations

import logging
import tarfile
import time
from pathlib import Path
from typing import Callable

import httpx

log = logging.getLogger(__name__)

_CHUNK = 1 << 20  # 1 Mo
_RETRIES = 6

# Rappel de progression : (phase, octets_faits, octets_total). phase ∈
# {"downloading", "extracting"}. total=0 si inconnu.
Progress = Callable[[str, int, int], None]


def models_present(cache_dir: Path) -> bool:
    """Heuristique « modèles déjà là » : cache d'au moins ~1,5 Go."""
    return _dir_size(cache_dir) >= 1_500 * 1024 * 1024


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def fetch_and_extract(
    url: str,
    cache_dir: Path,
    token: str = "",
    progress: Progress | None = None,
) -> None:
    """Télécharge l'archive .tar (avec reprise/retries) puis l'extrait dans le
    cache. Lève en cas d'échec définitif (l'appelant retombe alors sur HF)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    part = cache_dir / ".jade-models.tar.part"
    base_headers = {"Authorization": f"token {token}"} if token else {}

    for attempt in range(1, _RETRIES + 1):
        done = part.stat().st_size if part.exists() else 0
        headers = dict(base_headers)
        if done:
            headers["Range"] = f"bytes={done}-"
        try:
            timeout = httpx.Timeout(30.0, read=60.0)
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 416:  # déjà complet côté serveur
                        break
                    resp.raise_for_status()
                    # 206 = reprise acceptée (on append) ; 200 = tout depuis 0
                    if done and resp.status_code != 206:
                        done = 0
                    total = int(resp.headers.get("content-length", 0)) + done
                    mode = "ab" if (done and resp.status_code == 206) else "wb"
                    with open(part, mode) as f:
                        for chunk in resp.iter_bytes(_CHUNK):
                            f.write(chunk)
                            done += len(chunk)
                            if progress:
                                progress("downloading", done, total)
            break  # téléchargement terminé
        except Exception as e:
            log.warning(
                "Modèles : téléchargement interrompu (tentative %d/%d) : %s",
                attempt, _RETRIES, e,
            )
            if attempt == _RETRIES:
                raise
            time.sleep(min(20, 2 ** attempt))

    if progress:
        progress("extracting", 0, 0)
    # Archive maîtrisée (hébergée par Jade) ; filter="data" bloque tout de même
    # les chemins hors du dossier cible (traversal) par sécurité.
    with tarfile.open(part, "r:*") as tar:
        try:
            tar.extractall(cache_dir, filter="data")
        except TypeError:  # Python < 3.12 : pas de filtre
            tar.extractall(cache_dir)
    part.unlink(missing_ok=True)
    log.info("Modèles installés depuis %s", url)

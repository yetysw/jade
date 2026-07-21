"""OCR local (rapidocr-onnxruntime, CPU) pour images et PDF scannés.

Extraction de texte 100 % locale, sans binaire système ni service externe.
Utilisé pour :
  - les images jointes (capture, photo de document) -> texte,
  - les PDF sans couche texte (scans) -> texte par page, à l'indexation et en
    pièce jointe.
Le moteur est chargé paresseusement (premier appel) et réutilisé.
"""

from __future__ import annotations

import io
import logging

log = logging.getLogger(__name__)

_engine = None
MAX_OCR_PAGES = 25


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def _to_ndarray(data: bytes):
    from PIL import Image
    import numpy as np

    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.array(img)


def ocr_image_bytes(data: bytes) -> str:
    """Texte extrait d'une image (octets). Chaîne vide si rien / échec."""
    try:
        result, _ = _get_engine()(_to_ndarray(data))
    except Exception as e:
        log.warning("OCR image échoué : %s", e)
        return ""
    if not result:
        return ""
    return "\n".join(line[1] for line in result if len(line) > 1).strip()


def ocr_pdf_pages(path, max_pages: int = MAX_OCR_PAGES) -> list[tuple[int, str]]:
    """Rasterise chaque page d'un PDF scanné et l'OCR. Retourne [(page, texte)]."""
    import numpy as np
    import pypdfium2 as pdfium

    out: list[tuple[int, str]] = []
    pdf = pdfium.PdfDocument(str(path))
    try:
        n = min(len(pdf), max_pages)
        for i in range(n):
            page = pdf[i]
            pil = page.render(scale=2.0).to_pil().convert("RGB")
            page.close()
            try:
                result, _ = _get_engine()(np.array(pil))
            except Exception as e:
                log.warning("OCR page %d de %s échoué : %s", i + 1, path, e)
                continue
            if result:
                text = "\n".join(l[1] for l in result if len(l) > 1).strip()
                if text:
                    out.append((i + 1, text))
    finally:
        pdf.close()
    return out

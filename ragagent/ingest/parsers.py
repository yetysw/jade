"""Parseurs multi-format -> liste de Section(text, meta).

Formats pris en charge : .docx, .xlsx, .xls, .pdf, .txt/.md, .csv, .html/.htm,
.odt, .eml, .msg, .pst. Chaque Section porte les metadonnees d'origine
(section/feuille/page) pour l'affichage des sources.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

MAX_XLSX_ROWS_PER_SHEET = 5000


@dataclass
class Section:
    text: str
    meta: dict = field(default_factory=dict)


def parse_file(path: Path, ocr: bool = False) -> list[Section]:
    ext = path.suffix.lower()
    if ext == ".docx":
        return _parse_docx(path)
    if ext == ".xlsx":
        return _parse_xlsx(path)
    if ext == ".xls":
        return _parse_xls(path)
    if ext == ".pdf":
        return _parse_pdf(path, ocr=ocr)
    if ext in (".txt", ".md"):
        return _parse_txt(path)
    if ext == ".csv":
        return _parse_csv(path)
    if ext in (".html", ".htm"):
        return _parse_html(path)
    if ext == ".odt":
        return _parse_odt(path)
    if ext == ".eml":
        return _parse_eml(path)
    if ext == ".msg":
        return _parse_msg(path)
    if ext == ".pst":
        return _parse_pst(path)
    raise ValueError(f"Extension non prise en charge : {ext}")


def _parse_docx(path: Path) -> list[Section]:
    import docx
    from docx.document import Document as DocxDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc: DocxDocument = docx.Document(str(path))
    sections: list[Section] = []
    current_heading = ""

    def iter_blocks(parent):
        from docx.oxml.ns import qn

        for child in parent.element.body.iterchildren():
            if child.tag == qn("w:p"):
                yield Paragraph(child, parent)
            elif child.tag == qn("w:tbl"):
                yield Table(child, parent)

    for block in iter_blocks(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style = (block.style.name or "") if block.style else ""
            if style.startswith(("Heading", "Titre", "Title")):
                current_heading = text
            sections.append(Section(text, {"section": current_heading}))
        else:  # Table
            lines = []
            for row in block.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(cells):
                    lines.append(" | ".join(cells))
            if lines:
                sections.append(Section("\n".join(lines), {"section": current_heading}))
    return sections


def _parse_xlsx(path: Path) -> list[Section]:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    sections: list[Section] = []
    try:
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                continue
            header = [str(h) if h is not None else f"Col{i+1}" for i, h in enumerate(header)]
            count = 0
            for row in rows:
                if count >= MAX_XLSX_ROWS_PER_SHEET:
                    log.warning(
                        "%s / feuille %s : plus de %d lignes, tronque",
                        path.name, ws.title, MAX_XLSX_ROWS_PER_SHEET,
                    )
                    break
                if row is None or all(v is None for v in row):
                    continue
                pairs = [
                    f"{h}: {v}" for h, v in zip(header, row) if v is not None and str(v).strip()
                ]
                if pairs:
                    sections.append(Section(" | ".join(pairs), {"sheet": ws.title}))
                    count += 1
    finally:
        wb.close()
    return sections


def _parse_pdf(path: Path, ocr: bool = False) -> list[Section]:
    # pypdfium2 (moteur C PDFium) : extraction 5-20x plus rapide que pypdf,
    # repli sur pypdf si indisponible ou si le fichier le fait echouer
    sections: list[Section] = []
    try:
        sections = _parse_pdf_pdfium(path)
    except ImportError:
        sections = _parse_pdf_pypdf(path)
    except Exception as e:
        log.warning("%s : pypdfium2 a echoue (%s), repli sur pypdf", path.name, e)
        sections = _parse_pdf_pypdf(path)
    # PDF scanné (aucune couche texte) : OCR local si demandé
    if not sections and ocr:
        try:
            from ..ocr import ocr_pdf_pages

            for page, text in ocr_pdf_pages(path):
                sections.append(Section(text, {"page": page}))
            if sections:
                log.info("%s : texte récupéré par OCR (%d pages)", path.name, len(sections))
        except Exception as e:
            log.warning("%s : OCR échoué (%s)", path.name, e)
    return sections


def _parse_pdf_pdfium(path: Path) -> list[Section]:
    import pypdfium2 as pdfium

    sections: list[Section] = []
    pdf = pdfium.PdfDocument(str(path))
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            text = (textpage.get_text_bounded() or "").strip()
            textpage.close()
            page.close()
            if text:
                sections.append(Section(text, {"page": i + 1}))
    finally:
        pdf.close()
    if not sections:
        log.warning("%s : aucun texte extractible (PDF scanne ? OCR non installe)", path.name)
    return sections


def _parse_pdf_pypdf(path: Path) -> list[Section]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    sections: list[Section] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            sections.append(Section(text, {"page": i}))
    if not sections:
        log.warning("%s : aucun texte extractible (PDF scanne ? OCR non installe)", path.name)
    return sections


def _parse_txt(path: Path) -> list[Section]:
    raw_bytes = path.read_bytes()
    if b"\x00" in raw_bytes[:4096]:
        log.warning("%s : contenu binaire deguise en texte, ignore", path.name)
        return []
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            raw = raw_bytes.decode("cp1252")
        except UnicodeDecodeError:
            raw = raw_bytes.decode("utf-8", errors="replace")
    sections = []
    for para in raw.split("\n\n"):
        para = para.strip()
        if para:
            sections.append(Section(para))
    return sections


def _decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _rows_to_sections(header, rows, meta: dict) -> list[Section]:
    """Transforme (en-tete, lignes) en Sections « col: valeur | col: valeur »."""
    header = [str(h).strip() if h not in (None, "") else f"Col{i+1}"
              for i, h in enumerate(header)]
    sections: list[Section] = []
    for row in rows:
        if row is None or all(v in (None, "") for v in row):
            continue
        pairs = [f"{h}: {v}" for h, v in zip(header, row)
                 if v not in (None, "") and str(v).strip()]
        if pairs:
            sections.append(Section(" | ".join(pairs), dict(meta)))
    return sections


def _parse_csv(path: Path) -> list[Section]:
    import csv

    text = _decode_bytes(path.read_bytes())
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(text.splitlines(), dialect)
    all_rows = [r for r in reader]
    if not all_rows:
        return []
    header, data = all_rows[0], all_rows[1:]
    sections = _rows_to_sections(header, data[:MAX_XLSX_ROWS_PER_SHEET], {"section": path.stem})
    if len(data) > MAX_XLSX_ROWS_PER_SHEET:
        log.warning("%s : plus de %d lignes, tronque", path.name, MAX_XLSX_ROWS_PER_SHEET)
    return sections


def _parse_xls(path: Path) -> list[Section]:
    import xlrd

    book = xlrd.open_workbook(str(path))
    sections: list[Section] = []
    for sheet in book.sheets():
        if sheet.nrows < 1:
            continue
        header = sheet.row_values(0)
        rows = (sheet.row_values(i) for i in range(1, min(sheet.nrows, MAX_XLSX_ROWS_PER_SHEET + 1)))
        for s in _rows_to_sections(header, rows, {"sheet": sheet.name}):
            sections.append(s)
        if sheet.nrows > MAX_XLSX_ROWS_PER_SHEET + 1:
            log.warning("%s / feuille %s : tronque a %d lignes",
                        path.name, sheet.name, MAX_XLSX_ROWS_PER_SHEET)
    return sections


def _html_to_text(raw_html: str) -> str:
    import re

    h = re.sub(r"<(script|style|nav|header|footer|svg|noscript)[^>]*>.*?</\1>",
               " ", raw_html, flags=re.S | re.I)
    h = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>", "\n", h, flags=re.I)
    import html as _htmllib
    text = _htmllib.unescape(re.sub(r"<[^>]+>", " ", h))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _parse_html(path: Path) -> list[Section]:
    import re

    raw = _decode_bytes(path.read_bytes())
    m = re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.S | re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else path.stem
    text = _html_to_text(raw)
    sections: list[Section] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if len(para) > 1:
            sections.append(Section(para, {"section": title}))
    return sections


def _parse_odt(path: Path) -> list[Section]:
    from odf import teletype
    from odf.opendocument import load
    from odf.text import H, P

    doc = load(str(path))
    sections: list[Section] = []
    current_heading = ""
    for el in doc.getElementsByType(H) + doc.getElementsByType(P):
        text = teletype.extractText(el).strip()
        if not text:
            continue
        if el.qname[1] == "h":
            current_heading = text
        sections.append(Section(text, {"section": current_heading}))
    # getElementsByType ne garantit pas l'ordre du document : on retombe sur un
    # parcours à plat, suffisant pour l'indexation sémantique.
    return sections


def _email_sections(msg, name: str) -> list[Section]:
    """Construit les Sections communes .eml / .msg à partir d'un objet email."""
    headers = []
    for label, key in (("De", "from"), ("À", "to"), ("Objet", "subject"), ("Date", "date")):
        val = msg.get(key) if hasattr(msg, "get") else None
        if val:
            headers.append(f"{label}: {val}")
    subject = (msg.get("subject") if hasattr(msg, "get") else "") or name
    body = ""
    if hasattr(msg, "is_multipart") and msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                body = part.get_content()
                break
            if ctype == "text/html" and not body:
                body = _html_to_text(part.get_content())
    elif hasattr(msg, "get_content"):
        try:
            body = msg.get_content()
        except (KeyError, LookupError):
            body = ""
        if msg.get_content_type() == "text/html":
            body = _html_to_text(body)
    meta = {"section": str(subject)[:120]}
    sections: list[Section] = []
    if headers:
        sections.append(Section("\n".join(headers), dict(meta)))
    for para in (body or "").split("\n\n"):
        para = para.strip()
        if para:
            sections.append(Section(para, dict(meta)))
    return sections


def _parse_eml(path: Path) -> list[Section]:
    from email import policy
    from email.parser import BytesParser

    msg = BytesParser(policy=policy.default).parse(path.open("rb"))
    return _email_sections(msg, path.stem)


def _parse_msg(path: Path) -> list[Section]:
    import extract_msg

    m = extract_msg.Message(str(path))
    try:
        headers = []
        for label, val in (("De", m.sender), ("À", m.to), ("Objet", m.subject), ("Date", m.date)):
            if val:
                headers.append(f"{label}: {val}")
        subject = (m.subject or path.stem)
        meta = {"section": str(subject)[:120]}
        sections: list[Section] = []
        if headers:
            sections.append(Section("\n".join(headers), dict(meta)))
        for para in (m.body or "").split("\n\n"):
            para = para.strip()
            if para:
                sections.append(Section(para, dict(meta)))
        return sections
    finally:
        m.close()


def _parse_pst(path: Path) -> list[Section]:
    """Archive Outlook .pst : nécessite libpff/pypff (non fourni par défaut).

    pypff n'a pas de roue Windows sur PyPI : sans lui, on ignore proprement le
    fichier plutôt que d'échouer l'indexation. Recommander l'export des messages
    en .msg/.eml, ou installer libpff, pour couvrir ce format.
    """
    try:
        import pypff  # type: ignore
    except ImportError:
        raise ValueError(
            ".pst non pris en charge (libpff/pypff absent) — exporter les messages "
            "en .msg ou .eml, ou installer pypff"
        )
    sections: list[Section] = []
    pst = pypff.file()
    pst.open(str(path))

    def walk(folder):
        for i in range(folder.number_of_sub_messages):
            m = folder.get_sub_message(i)
            body = m.plain_text_body
            if body:
                body = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
                subject = (m.subject or "message")
                sections.append(Section(body.strip(), {"section": str(subject)[:120]}))
        for i in range(folder.number_of_sub_folders):
            walk(folder.get_sub_folder(i))

    try:
        walk(pst.get_root_folder())
    finally:
        pst.close()
    return sections

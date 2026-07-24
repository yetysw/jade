"""Creation de fichiers Office/PDF a partir d'une reponse de l'assistant.

Les fichiers sont TOUJOURS crees dans Documents\\Jade de l'utilisateur courant
(profil personnel, jamais un dossier partage entre tous les utilisateurs) —
jamais dans le dossier des documents sources (promesse lecture seule).
Formats : .docx (python-docx), .xlsx (openpyxl, tableaux markdown), .pdf
(reportlab). Le contenu markdown simple est interprete : titres, listes,
tableaux |...|, gras.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# Dossier de sortie par utilisateur (Documents\Jade du profil courant) : chaque
# utilisateur Windows a son propre Documents, donc pas de melange entre sessions.
OUTPUT_DIR = Path.home() / "Documents" / "Jade"

_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")

# Protection contre l'injection de formule (CSV/Excel injection) : une cellule
# commençant par = + - @ ou une tabulation/retour chariot peut être interprétée
# comme une formule à l'ouverture dans Excel/LibreOffice. On la neutralise en la
# préfixant d'une apostrophe (convention standard ; la valeur reste lisible).
# N'est appliqué qu'aux sorties tabulaires (CSV, XLSX), jamais aux autres formats.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _formula_safe(value) -> str:
    s = "" if value is None else str(value)
    if s and s[0] in _FORMULA_LEAD:
        return "'" + s
    return s


def _out_path(title: str, ext: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\- ]", "", title).strip()[:40] or "document"
    stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
    return OUTPUT_DIR / f"{safe} {stamp}.{ext}"


def _parse_blocks(text: str) -> list[tuple[str, object]]:
    """Markdown simple -> [(kind, payload)] : heading/bullet/table/para."""
    blocks: list[tuple[str, object]] = []
    table: list[list[str]] = []
    for line in text.split("\n"):
        row = _TABLE_ROW.match(line)
        if row and not _TABLE_SEP.match(line):
            table.append([c.strip().replace("**", "") for c in row.group(1).split("|")])
            continue
        if _TABLE_SEP.match(line):
            continue
        if table:
            blocks.append(("table", table))
            table = []
        line = line.rstrip()
        if not line.strip():
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            blocks.append((f"h{len(m.group(1))}", m.group(2).replace("**", "")))
        elif re.match(r"^\s*[-*]\s+", line):
            blocks.append(("bullet", re.sub(r"^\s*[-*]\s+", "", line).replace("**", "")))
        elif re.match(r"^\s*\d+[.)]\s+", line):
            blocks.append(("bullet", re.sub(r"^\s*\d+[.)]\s+", "", line).replace("**", "")))
        else:
            blocks.append(("para", line.replace("**", "")))
    if table:
        blocks.append(("table", table))
    return blocks


def save_docx(title: str, text: str) -> Path:
    import docx

    doc = docx.Document()
    doc.add_heading(title, 0)
    for kind, payload in _parse_blocks(text):
        if kind.startswith("h"):
            doc.add_heading(payload, level=int(kind[1]))
        elif kind == "bullet":
            doc.add_paragraph(payload, style="List Bullet")
        elif kind == "table":
            rows = payload
            t = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
            t.style = "Light Grid Accent 1"
            for i, r in enumerate(rows):
                for j, cell in enumerate(r):
                    t.rows[i].cells[j].text = cell
        else:
            doc.add_paragraph(payload)
    path = _out_path(title, "docx")
    doc.save(str(path))
    return path


def save_xlsx(title: str, text: str) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Feuille 1"
    tables = [p for k, p in _parse_blocks(text) if k == "table"]
    if tables:
        row_idx = 1
        for t_i, table in enumerate(tables):
            for i, row in enumerate(table):
                for j, cell in enumerate(row, start=1):
                    c = ws.cell(row=row_idx, column=j, value=_formula_safe(cell))
                    if i == 0:
                        c.font = Font(bold=True)
                row_idx += 1
            row_idx += 1  # ligne vide entre tableaux
        for col in ws.columns:
            width = max((len(str(c.value)) for c in col if c.value), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(width + 2, 60)
    else:
        # pas de tableau dans la reponse : une ligne de texte par cellule
        for i, (kind, payload) in enumerate(_parse_blocks(text), start=1):
            if kind != "table":
                ws.cell(row=i, column=1, value=_formula_safe(payload))
        ws.column_dimensions["A"].width = 100
    path = _out_path(title, "xlsx")
    wb.save(str(path))
    return path


def save_pdf(title: str, text: str) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 10)]
    for kind, payload in _parse_blocks(text):
        if kind == "h1":
            story.append(Paragraph(payload, styles["Heading1"]))
        elif kind == "h2":
            story.append(Paragraph(payload, styles["Heading2"]))
        elif kind == "h3":
            story.append(Paragraph(payload, styles["Heading3"]))
        elif kind == "bullet":
            story.append(Paragraph(f"• {payload}", styles["Normal"]))
        elif kind == "table":
            t = Table(payload, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00357f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(Spacer(1, 6))
            story.append(t)
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(payload, styles["Normal"]))
            story.append(Spacer(1, 4))
    path = _out_path(title, "pdf")
    SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm
    ).build(story)
    return path


def save_pptx(title: str, text: str) -> Path:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    ts = prs.slides.add_slide(prs.slide_layouts[0])
    ts.shapes.title.text = title

    # Regrouper en diapositives : chaque titre (#, ##, ###) démarre une diapo,
    # les puces/paragraphes qui suivent forment son corps ; un tableau = diapo dédiée.
    slides: list[dict] = []
    cur: dict = {"title": title, "lines": [], "table": None}
    for kind, payload in _parse_blocks(text):
        if kind in ("h1", "h2", "h3"):
            if cur["lines"] or cur["table"]:
                slides.append(cur)
            cur = {"title": payload, "lines": [], "table": None}
        elif kind == "table":
            if cur["lines"]:
                slides.append(cur)
            slides.append({"title": cur["title"], "lines": [], "table": payload})
            cur = {"title": cur["title"], "lines": [], "table": None}
        else:
            cur["lines"].append(payload)
    if cur["lines"] or cur["table"]:
        slides.append(cur)

    for s in slides:
        if s["table"]:
            sl = prs.slides.add_slide(prs.slide_layouts[5])
            sl.shapes.title.text = s["title"]
            rows = s["table"]
            nr, nc = len(rows), max(len(r) for r in rows)
            tbl = sl.shapes.add_table(
                nr, nc, Inches(0.5), Inches(1.7), Inches(9), Inches(min(0.5 * nr, 5))
            ).table
            for i, r in enumerate(rows):
                for j in range(nc):
                    tbl.cell(i, j).text = r[j] if j < len(r) else ""
        else:
            sl = prs.slides.add_slide(prs.slide_layouts[1])
            sl.shapes.title.text = s["title"]
            tf = sl.placeholders[1].text_frame
            for i, line in enumerate(s["lines"] or [""]):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.text = line
    path = _out_path(title, "pptx")
    prs.save(str(path))
    return path


def save_csv(title: str, text: str) -> Path:
    import csv as _csv

    tables = [p for k, p in _parse_blocks(text) if k == "table"]
    path = _out_path(title, "csv")
    # utf-8-sig + séparateur ; : Excel FR ouvre le CSV avec les bons accents/colonnes
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.writer(f, delimiter=";")
        if tables:
            for t in tables:
                for row in t:
                    w.writerow([_formula_safe(c) for c in row])
                w.writerow([])
        else:
            for kind, payload in _parse_blocks(text):
                if kind != "table":
                    w.writerow([_formula_safe(payload)])
    return path


def save_txt(title: str, text: str) -> Path:
    lines = [title, "=" * len(title), ""]
    for kind, payload in _parse_blocks(text):
        if kind == "h1":
            lines += ["", payload.upper(), ""]
        elif kind in ("h2", "h3"):
            lines += ["", payload, "-" * len(payload)]
        elif kind == "bullet":
            lines.append("  - " + payload)
        elif kind == "table":
            for row in payload:
                lines.append("\t".join(row))
            lines.append("")
        else:
            lines.append(payload)
    path = _out_path(title, "txt")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def save_md(title: str, text: str) -> Path:
    path = _out_path(title, "md")
    body = text if text.lstrip().startswith("#") else f"# {title}\n\n{text}"
    path.write_text(body, encoding="utf-8")
    return path


def save_html(title: str, text: str) -> Path:
    import html as _h

    out: list[str] = []
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for kind, payload in _parse_blocks(text):
        if kind == "bullet":
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_h.escape(payload)}</li>")
            continue
        close_ul()
        if kind in ("h1", "h2", "h3"):
            out.append(f"<{kind[0]}{kind[1]}>{_h.escape(payload)}</{kind[0]}{kind[1]}>")
        elif kind == "table":
            out.append("<table>")
            for i, row in enumerate(payload):
                cell = "th" if i == 0 else "td"
                out.append("<tr>" + "".join(f"<{cell}>{_h.escape(c)}</{cell}>" for c in row) + "</tr>")
            out.append("</table>")
        else:
            out.append(f"<p>{_h.escape(payload)}</p>")
    close_ul()
    doc = (
        "<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
        f"<title>{_h.escape(title)}</title><style>"
        "body{font-family:'Segoe UI',system-ui,sans-serif;max-width:820px;margin:40px auto;padding:0 20px;color:#1b1b1b;line-height:1.6}"
        "h1{color:#00357f}table{border-collapse:collapse;width:100%;margin:14px 0}"
        "th,td{border:1px solid #ccc;padding:7px 10px;text-align:left}th{background:#00357f;color:#fff}"
        "</style></head><body>"
        f"<h1>{_h.escape(title)}</h1>\n" + "\n".join(out) + "</body></html>"
    )
    path = _out_path(title, "html")
    path.write_text(doc, encoding="utf-8")
    return path


SAVERS = {
    "docx": save_docx, "xlsx": save_xlsx, "pdf": save_pdf, "pptx": save_pptx,
    "csv": save_csv, "txt": save_txt, "md": save_md, "html": save_html,
}

# Detection d'une demande explicite de creation de fichier dans la question :
# un verbe de creation/export suivi (a moins de ~40 caracteres) d'un format,
# ou la tournure « en excel / en pdf / en word ».
_FMT_WORDS = {
    "excel": "xlsx", "xlsx": "xlsx", "tableur": "xlsx", "classeur": "xlsx",
    "word": "docx", "docx": "docx",
    "pdf": "pdf",
    "powerpoint": "pptx", "pptx": "pptx", "ppt": "pptx",
    "présentation": "pptx", "presentation": "pptx", "diaporama": "pptx", "slides": "pptx",
    "csv": "csv",
    "txt": "txt", "texte": "txt", "markdown": "md", "md": "md",
    "html": "html", "htm": "html",
}
# groupe de formats reconnus par un VERBE de création (« texte » exclu ici :
# « rédige un texte sur X » veut une réponse rédigée, pas un fichier .txt)
_FMTS = (r"excel|xlsx|tableur|classeur|word|docx|pdf|powerpoint|pptx|ppt"
         r"|pr[ée]sentation|diaporama|slides|csv|txt|markdown|md|html|htm")
# groupe pour « en/au format/fichier X » : ajoute « texte » (non ambigu ici)
_FMTS_EN = _FMTS + r"|texte"
_CREATE_RE = re.compile(
    # les formes infinitives (créer, générer, exporter…) ajoutent un « r » final :
    # le motif accepte cet « r » optionnel, sinon « creer un pdf » n'était PAS détecté
    r"\b(fais|fait|faire|cr[ée]{1,2}r?|g[ée]n[èée]rer?|exporter?|produi[ts]|produire"
    r"|pr[ée]parer?|converti[rs]|sors|sortir|met[s]?|mettre|transformer?"
    r"|[ée]tabli[rs]|dresser?|r[ée]diger?|compiler?|r[ée]capituler?"
    r"|structurer?|lister?)\b[^.!?]{0,45}?"
    r"\b(" + _FMTS + r")\b",
    re.IGNORECASE,
)
# Format cité même sans verbe de création explicite : « en excel », « sous pdf »,
# « au format word », « dans un tableur », « un fichier pdf de… ».
_EN_FMT_RE = re.compile(
    r"\b(en|sous|au format|dans un|dans une|format|fichier|document)\s+"
    r"(" + _FMTS_EN + r")\b",
    re.IGNORECASE,
)


def wanted_format(question: str) -> str | None:
    """'xlsx' | 'docx' | 'pdf' si l'utilisateur demande un fichier, sinon None."""
    m = _CREATE_RE.search(question) or _EN_FMT_RE.search(question)
    if not m:
        return None
    return _FMT_WORDS[m.group(m.lastindex).lower()]


# Demande de simplement METTRE EN FICHIER ce qui vient d'être dit (« mets ça en
# pdf », « fais-en un word », « exporte le résultat en excel ») : le contenu est
# déjà dans la conversation, il ne faut PAS relancer une recherche documentaire —
# on réutilise la réponse précédente. Repéré uniquement par des marqueurs
# référentiels explicites (ça / ce résultat…), pas par un sujet concret comme
# « notre inventaire » (qui doit, lui, aller chercher dans les documents).
_REFORMAT_RE = re.compile(
    r"\b(ça|ca|ceci|cela)\b"
    r"|\b(le|ce|ça) (r[ée]sultat|tableau|texte|document|contenu|list[e]?)\b"
    r"|\bfais[- ]en\b"
    r"|\bmets?[- ](le|la|les|ça|ca)\b",
    re.IGNORECASE,
)


def is_reformat_request(question: str) -> bool:
    """Vrai si la question ne fait que demander de mettre le contenu précédent
    dans un fichier (à n'utiliser que si un format est déjà demandé et qu'il
    existe un historique de conversation)."""
    return bool(_REFORMAT_RE.search(question))

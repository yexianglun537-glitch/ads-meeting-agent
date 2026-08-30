from __future__ import annotations

import html
import re
from pathlib import Path

from docx import Document
from docx.document import Document as _Document
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph as RParagraph, Spacer, Table as RTable, TableStyle, PageBreak, KeepTogether


ROOT = Path(__file__).resolve().parents[1]
DOCX_PATH = ROOT / "materials" / "01-ADS会议智能体项目说明书.docx"
PDF_PATH = ROOT / "materials" / "01-ADS会议智能体项目说明书.pdf"

pdfmetrics.registerFont(TTFont("SimSun", r"C:\Windows\Fonts\simsun.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("TimesNewRoman", r"C:\Windows\Fonts\times.ttf"))
pdfmetrics.registerFont(TTFont("TimesNewRoman-Bold", r"C:\Windows\Fonts\timesbd.ttf"))


def iter_block_items(parent):
    if isinstance(parent, _Document):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError("Unsupported parent")
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def mixed_markup(text: str, bold=False, italic=False, color=None) -> str:
    text = html.escape(text, quote=False)
    attrs = []
    if bold:
        attrs.append("<b>")
    if italic:
        attrs.append("<i>")
    if color:
        attrs.append(f'<font color="#{color}">')
    prefix = "".join(attrs)
    suffix = ("</font>" if color else "") + ("</i>" if italic else "") + ("</b>" if bold else "")
    parts = re.split(r"([A-Za-z0-9]+)", text)
    inner = "".join(
        f'<font name="TimesNewRoman">{part}</font>' if re.fullmatch(r"[A-Za-z0-9]+", part) else f'<font name="SimSun">{part}</font>'
        for part in parts if part
    )
    return prefix + inner + suffix


def paragraph_text(p: Paragraph) -> str:
    return "".join(run.text for run in p.runs)


def run_size(p: Paragraph) -> float:
    for run in p.runs:
        if run.font.size:
            return run.font.size.pt
    return 12.0


def run_bold(p: Paragraph) -> bool:
    return any(bool(run.bold) for run in p.runs)


def make_styles():
    return {
        "body": ParagraphStyle("body", fontName="SimSun", fontSize=12, leading=22, firstLineIndent=24, textColor=colors.HexColor("#222222"), spaceAfter=0, alignment=TA_LEFT),
        "heading1": ParagraphStyle("heading1", fontName="SimSun", fontSize=16, leading=22, textColor=colors.HexColor("#1F4E79"), spaceBefore=10, spaceAfter=4, alignment=TA_LEFT),
        "heading2": ParagraphStyle("heading2", fontName="SimSun", fontSize=14, leading=22, textColor=colors.HexColor("#1F4E79"), spaceBefore=6, spaceAfter=4, alignment=TA_LEFT),
        "title": ParagraphStyle("title", fontName="SimSun", fontSize=22, leading=28, textColor=colors.HexColor("#1F4E79"), alignment=TA_CENTER, spaceAfter=2),
        "subtitle": ParagraphStyle("subtitle", fontName="SimSun", fontSize=16, leading=26, textColor=colors.HexColor("#263746"), alignment=TA_CENTER, spaceAfter=12),
        "covermeta": ParagraphStyle("covermeta", fontName="SimSun", fontSize=12, leading=18, textColor=colors.HexColor("#222222"), alignment=TA_LEFT),
        "table": ParagraphStyle("table", fontName="SimSun", fontSize=12, leading=22, textColor=colors.HexColor("#222222"), alignment=TA_LEFT),
        "tablehead": ParagraphStyle("tablehead", fontName="SimSun", fontSize=12, leading=22, textColor=colors.HexColor("#1F4E79"), alignment=TA_CENTER),
        "callout": ParagraphStyle("callout", fontName="SimSun", fontSize=12, leading=22, textColor=colors.HexColor("#25313D"), alignment=TA_LEFT),
    }


def p_from_docx(p: Paragraph, styles):
    text = paragraph_text(p)
    if not text.strip():
        return Spacer(1, 4)
    size = run_size(p)
    is_center = p.alignment == 1
    if size >= 20:
        style = styles["title"]
    elif size >= 15:
        style = styles["subtitle"] if is_center else styles["heading1"]
    elif text.startswith(("一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、")):
        style = styles["heading1"]
    else:
        style = styles["covermeta"] if is_center else styles["body"]
    if is_center and style is styles["body"]:
        style = ParagraphStyle("center", parent=style, alignment=TA_CENTER, firstLineIndent=0, textColor=colors.HexColor("#5B6573"), fontSize=10, leading=22)
    # Rebuild mixed fonts while retaining bold for paragraphs that are labels or headings.
    markup = mixed_markup(text, bold=run_bold(p) or style in (styles["title"], styles["subtitle"], styles["heading1"], styles["heading2"]))
    return RParagraph(markup, style)


def table_from_docx(table: Table, styles):
    rows = []
    for ridx, row in enumerate(table.rows):
        cells = []
        for cell in row.cells:
            value = "\n".join(paragraph_text(p) for p in cell.paragraphs).strip()
            style = styles["tablehead"] if ridx == 0 else styles["table"]
            cells.append(RParagraph(mixed_markup(value, bold=(ridx == 0)), style))
        rows.append(cells)
    ncols = len(rows[0])
    usable = 16 * cm
    if ncols == 1:
        widths = [usable]
    elif ncols == 2:
        widths = [3.6 * cm, usable - 3.6 * cm]
    else:
        widths = [3.0 * cm, 8.0 * cm, usable - 11.0 * cm]
    tbl = RTable(rows, colWidths=widths, repeatRows=1, hAlign="CENTER")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#C9D7E3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2F8")),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            commands.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F5F9FC")))
    tbl.setStyle(TableStyle(commands))
    return tbl


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("SimSun", 9)
    canvas.setFillColor(colors.HexColor("#5B6573"))
    canvas.drawString(2.5 * cm, 1.25 * cm, "ADS 会议智能体｜项目说明书")
    canvas.drawRightString(18.5 * cm, 1.25 * cm, f"第 {doc.page} 页")
    canvas.restoreState()


def build_pdf():
    source = Document(DOCX_PATH)
    styles = make_styles()
    frame = Frame(2.5 * cm, 2.0 * cm, 16 * cm, 24.7 * cm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="normal")
    doc = BaseDocTemplate(str(PDF_PATH), pagesize=A4, leftMargin=2.5 * cm, rightMargin=2.5 * cm, topMargin=2.2 * cm, bottomMargin=2.0 * cm)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=header_footer)])
    story = []
    for block in iter_block_items(source):
        if isinstance(block, Paragraph):
            txt = paragraph_text(block)
            if txt.startswith("五、产品使用流程"):
                story.append(PageBreak())
            story.append(p_from_docx(block, styles))
            if txt.startswith("启智杯 AI 应用成果挑战赛"):
                story.append(PageBreak())
        else:
            story.append(table_from_docx(block, styles))
            story.append(Spacer(1, 6))
    doc.build(story)
    print(PDF_PATH)


if __name__ == "__main__":
    build_pdf()

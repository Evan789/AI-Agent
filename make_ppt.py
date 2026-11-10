import re
import sys
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

OUT = r"C:\Users\Evan\Deep Learning\AI Agent\WorkBuddy-Enterprise-私有化使用与费用.pptx"
FONT = "微软雅黑"
NAVY = RGBColor(0x14, 0x32, 0x4A)
TEAL = RGBColor(0x1F, 0x6F, 0x8B)
INK = RGBColor(0x1C, 0x24, 0x2B)
MUTED = RGBColor(0x5C, 0x6B, 0x76)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PAPER = RGBColor(0xF4, 0xF7, 0xF8)
LINE = RGBColor(0xD5, 0xDE, 0xE3)
AMBER = RGBColor(0xB5, 0x68, 0x1A)

W, H = Inches(13.333), Inches(7.5)


def font(run, size, bold=False, color=INK, name=FONT):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = name
    rpr = run._r.get_or_add_rPr()
    for tag in ("latin", "ea", "cs"):
        node = rpr.find(qn(f"a:{tag}"))
        if node is None:
            node = rpr.makeelement(qn(f"a:{tag}"))
            rpr.append(node)
        node.set("typeface", name)


def add_text(slide, text, x, y, w, h, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    font(run, size, bold, color)
    return box


def add_bullets(slide, items, x, y, w, h, size=16, color=INK, space=8):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.level = 0
        p.space_after = Pt(space)
        run = p.add_run()
        run.text = item
        font(run, size, False, color)
    return box


def chrome(slide, title, page, pages, footer):
    bar = slide.shapes.add_shape(1, 0, 0, W, Inches(0.92))
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()
    add_text(slide, title, Inches(0.48), Inches(0.22), Inches(11.5), Inches(0.52), 26, True, WHITE)
    foot = slide.shapes.add_shape(1, 0, Inches(7.18), W, Inches(0.32))
    foot.fill.solid()
    foot.fill.fore_color.rgb = PAPER
    foot.line.fill.background()
    add_text(slide, footer, Inches(0.48), Inches(7.18), Inches(10), Inches(0.3), 11, False, MUTED)
    add_text(slide, f"{page} / {pages}", Inches(11.6), Inches(7.18), Inches(1.3), Inches(0.3), 11, False, MUTED, PP_ALIGN.RIGHT)


def shade_cell(cell, rgb):
    cell.fill.solid()
    cell.fill.fore_color.rgb = rgb


def write_cell(cell, text, size=12, bold=False, color=INK, fill=None, align=PP_ALIGN.LEFT):
    cell.text = ""
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    if fill:
        shade_cell(cell, fill)
    p = cell.text_frame.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    font(run, size, bold, color)
    cell.margin_left = Inches(0.08)
    cell.margin_right = Inches(0.06)
    cell.margin_top = Inches(0.04)
    cell.margin_bottom = Inches(0.04)


def add_table(slide, rows, x, y, w, h, col_w, header=True, font_size=12):
    table_shape = slide.shapes.add_table(len(rows), len(rows[0]), x, y, w, h)
    table = table_shape.table
    for i, width in enumerate(col_w):
        table.columns[i].width = width
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            is_header = header and r == 0
            write_cell(
                table.cell(r, c),
                value,
                font_size if not is_header else font_size,
                bold=is_header or c == 0,
                color=WHITE if is_header else INK,
                fill=NAVY if is_header else (PAPER if r % 2 == 0 else WHITE),
                align=PP_ALIGN.LEFT,
            )
    return table


SECTION = re.compile(r"^[一二三四五六七八九十百]+、")
HEADING_STYLES = {"Heading 1", "Heading 2", "Heading 3", "标题 1", "标题 2", "标题 3", "标题"}


def _strip_quotes(text: str) -> str:
    for char in '"“”„‟«»':
        text = text.replace(char, "")
    return text


def resolve_source(args: list[str]) -> Path:
    if not args:
        raise SystemExit("用法：python make_ppt.py 文档.docx")
    joined = ["".join(args), " ".join(args)]
    for text in joined:
        path = Path(text)
        if path.is_file():
            return path
    parent = Path(args[0]).parent
    if parent.is_dir():
        wanted = _strip_quotes(Path("".join(args)).name)
        matches = [
            item for item in parent.iterdir()
            if item.is_file() and item.suffix.lower() == ".docx" and _strip_quotes(item.name) == wanted
        ]
        if len(matches) == 1:
            return matches[0]
    raise SystemExit(f"找不到文件：{joined[0]}")


def output_path(source: Path) -> Path:
    return source.with_suffix(".pptx")


def _is_heading(style: str, text: str) -> bool:
    if style in HEADING_STYLES or style.startswith("Heading") or style.startswith("标题"):
        return True
    return bool(SECTION.match(text))


def _explode(text: str) -> list[str]:
    if "；" in text and len(text) > 40:
        parts = [part.strip().rstrip("。") for part in text.split("；")]
        return [part for part in parts if part]
    return [text]


def read_document(path: Path) -> tuple[str, list[tuple[str, list[str]]]]:
    if path.suffix.lower() != ".docx":
        raise SystemExit("请传入 .docx 文件。旧版 .doc 请先另存为 .docx。")
    document = Document(str(path))
    blocks: list[tuple[str, str]] = []
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = paragraph.style.name if paragraph.style is not None else ""
            blocks.append((style, text))
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                line = " | ".join(cell for cell in cells if cell)
                if line:
                    rows.append(line)
            if rows:
                blocks.append(("table", "\n".join(rows)))
    if not blocks:
        raise SystemExit("文档里没有可排进 PPT 的文字。")
    title = blocks[0][1]
    sections: list[tuple[str, list[str]]] = []
    current_title = None
    current_items: list[str] = []
    for style, text in blocks[1:]:
        if style != "table" and _is_heading(style, text):
            if current_title is not None:
                sections.append((current_title, current_items))
            current_title = text
            current_items = []
            continue
        pieces = text.split("\n") if style == "table" else _explode(text)
        if current_title is None:
            current_title = "内容"
        current_items.extend(pieces)
    if current_title is not None:
        sections.append((current_title, current_items))
    if not sections:
        sections.append(("内容", []))
    return title, sections


def chunk(items: list[str], size: int = 7) -> list[list[str]]:
    if not items:
        return [[]]
    return [items[index : index + size] for index in range(0, len(items), size)]


def build(source: Path, dest: Path):
    title, sections = read_document(source)
    slides: list[tuple[str, list[str]]] = []
    for heading, items in sections:
        parts = chunk(items)
        for index, part in enumerate(parts, start=1):
            slide_title = heading if len(parts) == 1 else f"{heading}（{index}）"
            slides.append((slide_title, part))
    pages = 1 + len(slides)
    footer = source.name

    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    blank = prs.slide_layouts[6]
    cover = prs.slides.add_slide(blank)
    band = cover.shapes.add_shape(1, 0, 0, Inches(0.28), H)
    band.fill.solid()
    band.fill.fore_color.rgb = TEAL
    band.line.fill.background()
    add_text(cover, title, Inches(0.85), Inches(2.15), Inches(11.2), Inches(2.4), 32, True, NAVY)

    for number, (heading, items) in enumerate(slides, start=2):
        slide = prs.slides.add_slide(blank)
        chrome(slide, heading, number, pages, footer)
        if items:
            add_bullets(slide, items, Inches(0.55), Inches(1.25), Inches(12.2), Inches(5.6), 20, INK, 12)
        else:
            add_text(slide, "（这一节没有正文）", Inches(0.55), Inches(1.4), Inches(10), Inches(0.5), 18, False, MUTED)
    prs.save(dest)


if __name__ == "__main__":
    source = resolve_source(sys.argv[1:])
    dest = output_path(source)
    build(source, dest)
    print(dest)

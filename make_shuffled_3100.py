from __future__ import annotations

import argparse
import hashlib
import html
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow the copied script in 原版/校正版 to reuse the project's local
# dependencies without requiring a second installation.
SCRIPT_DIR = Path(__file__).resolve().parent
for dependency_dir in (
    SCRIPT_DIR / "tmp" / "pdf-deps",
    SCRIPT_DIR.parent / "tmp" / "pdf-deps",
):
    if dependency_dir.is_dir():
        sys.path.insert(0, str(dependency_dir))

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as canvas_module
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


BODY_TOP = 60.0
BODY_BOTTOM = 765.0
PAGE_SIDE_MARGIN = 18.5 * mm
# A ReportLab frame adds 6 pt padding on each side. Keep a further 13 pt
# tolerance because the wrapper may retain one full-width punctuation mark
# on the preceding line after that line reaches its nominal width.
ENTRY_WRAP_WIDTH = A4[0] - 2 * PAGE_SIDE_MARGIN - 12.0 - 13.0

FONT_CJK = Path(r"C:\Windows\Fonts\STKAITI.TTF")
FONT_TITLE = Path(r"C:\Windows\Fonts\STSONG.TTF")
FONT_LATIN = Path(r"C:\Windows\Fonts\times.ttf")
FONT_LATIN_BOLD = Path(r"C:\Windows\Fonts\timesbd.ttf")

DERIVATIVE_PREFIX = re.compile(
    r"^(?:a|adj|ad|adv|n|v|vi|vt|prep|pron|conj)\.", re.IGNORECASE
)
LETTER_HEADING = re.compile(r"^[A-Z]$")


@dataclass(frozen=True)
class VisualRow:
    page: int
    y: float
    text: str


@dataclass(frozen=True)
class Entry:
    rows: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n".join(self.rows)

    @property
    def headword(self) -> str:
        first = self.rows[0]
        for marker in ("/", " ["):
            if marker in first:
                return first.split(marker, 1)[0].strip()
        match = re.match(r"^[A-Za-z][A-Za-z .()=\-（）]*?(?=\s(?:n|v|adj|adv|prep|pron|conj)\b|$)", first)
        return match.group(0).strip() if match else first[:60]


class NumberedCanvas(canvas_module.Canvas):
    """Add a stable `current / total` footer after all pages are known."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(total_pages)
            super().showPage()
        super().save()

    def _draw_page_number(self, total_pages: int) -> None:
        self.saveState()
        width, _ = A4
        self.setStrokeColor(colors.HexColor("#D8D8D8"))
        self.setLineWidth(0.4)
        self.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
        self.setFillColor(colors.HexColor("#666666"))
        self.setFont("STKaiti", 8.5)
        self.drawString(18 * mm, 8.5 * mm, "编制：LaoShui")
        self.drawRightString(width - 18 * mm, 8.5 * mm, f"第 {self._pageNumber} 页（共 {total_pages} 页）")
        self.restoreState()


def extract_visual_rows(pdf_path: Path) -> list[VisualRow]:
    rows: list[VisualRow] = []
    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            pieces: list[tuple[float, float, str]] = []
            page_dict = page.get_text("dict", sort=True)
            for block in page_dict["blocks"]:
                for line in block.get("lines", []):
                    y = float(line["bbox"][1])
                    if not BODY_TOP < y < BODY_BOTTOM:
                        continue
                    text = "".join(span["text"] for span in line["spans"])
                    if text.strip():
                        pieces.append((y, float(line["bbox"][0]), text))

            grouped: list[tuple[float, list[tuple[float, str]]]] = []
            for y, x, text in sorted(pieces, key=lambda item: (item[0], item[1])):
                if grouped and abs(grouped[-1][0] - y) < 1.0:
                    grouped[-1][1].append((x, text))
                else:
                    grouped.append((y, [(x, text)]))

            for y, parts in grouped:
                combined = " ".join(
                    text.strip()
                    for _, text in sorted(parts, key=lambda item: item[0])
                    if text.strip()
                ).strip()
                if combined:
                    rows.append(VisualRow(page_index + 1, y, combined))
    return rows


def is_entry_start(text: str) -> bool:
    if not re.match(r"^[A-Za-z]", text):
        return False

    # These entries use no slash-style pronunciation in the source PDF.
    if text.startswith(
        (
            "AI (=artificial intelligence)",
            "BCE (Before the Common Era)**",
            "CE（Common Era）**",
            "survey [",
        )
    ):
        return True

    # "a. m." is a real headword, not a derivative label.
    if text.startswith(("a. m./", "a.m./")):
        return True

    # A normal entry contains a complete /phonetic/ pair.  A continuation
    # such as ``dreamed/dreamt)vt. ...`` has only one slash and must stay
    # attached to the preceding ``dream`` entry.
    if text.count("/") < 2:
        return False
    if DERIVATIVE_PREFIX.match(text):
        return False
    return True


def extract_entries(rows: list[VisualRow]) -> list[Entry]:
    entries: list[Entry] = []
    current: list[str] = []
    started = False

    for row in rows:
        text = row.text
        if LETTER_HEADING.fullmatch(text):
            continue

        if is_entry_start(text):
            if current:
                entries.append(Entry(tuple(current)))
            current = [text]
            started = True
        elif started:
            current.append(text)

    if current:
        entries.append(Entry(tuple(current)))
    return entries


def register_fonts() -> tuple[fitz.Font, fitz.Font]:
    for path in (FONT_CJK, FONT_TITLE, FONT_LATIN, FONT_LATIN_BOLD):
        if not path.exists():
            raise FileNotFoundError(f"Required font not found: {path}")

    pdfmetrics.registerFont(TTFont("STKaiti", str(FONT_CJK)))
    pdfmetrics.registerFont(TTFont("STSong", str(FONT_TITLE)))
    pdfmetrics.registerFont(TTFont("TimesNewRoman", str(FONT_LATIN)))
    pdfmetrics.registerFont(TTFont("TimesNewRoman-Bold", str(FONT_LATIN_BOLD)))
    return fitz.Font(fontfile=str(FONT_CJK)), fitz.Font(fontfile=str(FONT_LATIN))


def markup_text(text: str, cjk_font: fitz.Font, latin_font: fitz.Font) -> str:
    runs: list[tuple[str, bool]] = []
    for char in text:
        codepoint = ord(char)
        use_latin = (
            codepoint < 0x0250
            or 0x0250 <= codepoint <= 0x02FF
        ) and latin_font.has_glyph(codepoint)
        if not cjk_font.has_glyph(codepoint) and latin_font.has_glyph(codepoint):
            use_latin = True
        if runs and runs[-1][1] == use_latin:
            runs[-1] = (runs[-1][0] + char, use_latin)
        else:
            runs.append((char, use_latin))

    output: list[str] = []
    for run, use_latin in runs:
        escaped = html.escape(run, quote=False)
        if use_latin:
            output.append(f'<font name="TimesNewRoman">{escaped}</font>')
        else:
            output.append(escaped)
    return "".join(output)


NO_LINE_START_PUNCTUATION = set("，。；：、！？）》】」』”’％%,.;:!?/)…")
PREFERRED_BREAK_AFTER = set("，。；：、！？,;: ")


def merge_entry_rows(rows: tuple[str, ...]) -> str:
    text = " ".join(row.strip() for row in rows if row.strip()).replace("\u00ad", "-")
    text = re.sub(r"\s+([，。；：、！？）》】」』”’％%,.;:!?/)])", r"\1", text)
    text = re.sub(r"([，。；：、！？])\s+", r"\1", text)
    text = re.sub(r"([（(《【「『“‘])\s*", r"\1", text)
    text = re.sub(
        r"(?<=[\u4e00-\u9fff）])\s+(?=[\u4e00-\u9fff（])",
        "",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def text_width(text: str, font_size: float, cjk_font: fitz.Font, latin_font: fitz.Font) -> float:
    width = 0.0
    for char in text:
        codepoint = ord(char)
        use_latin = (
            codepoint < 0x0250 or 0x0250 <= codepoint <= 0x02FF
        ) and latin_font.has_glyph(codepoint)
        if not cjk_font.has_glyph(codepoint) and latin_font.has_glyph(codepoint):
            use_latin = True
        width += pdfmetrics.stringWidth(
            char, "TimesNewRoman" if use_latin else "STKaiti", font_size
        )
    return width


def wrap_entry_text(
    text: str,
    max_width: float,
    font_size: float,
    cjk_font: fitz.Font,
    latin_font: fitz.Font,
) -> list[str]:
    lines: list[str] = []
    current: list[str] = []
    current_width = 0.0
    for char in text:
        char_width = text_width(char, font_size, cjk_font, latin_font)
        if current and current_width + char_width > max_width:
            if char in NO_LINE_START_PUNCTUATION:
                current.append(char)
                lines.append("".join(current))
                current = []
                current_width = 0.0
                continue
            break_at = next(
                (
                    index
                    for index in range(len(current) - 1, max(-1, len(current) - 17), -1)
                    if current[index] in PREFERRED_BREAK_AFTER
                ),
                None,
            )
            if break_at is not None and break_at < len(current) - 1:
                lines.append("".join(current[: break_at + 1]))
                current = current[break_at + 1 :] + [char]
                current_width = text_width(
                    "".join(current), font_size, cjk_font, latin_font
                )
                continue
            lines.append("".join(current))
            current = [char]
            current_width = char_width
        else:
            current.append(char)
            current_width += char_width
    if current:
        lines.append("".join(current))

    index = 1
    while index < len(lines):
        leading = ""
        while lines[index] and lines[index][0] in NO_LINE_START_PUNCTUATION:
            leading += lines[index][0]
            lines[index] = lines[index][1:]
        if leading:
            lines[index - 1] += leading
        if not lines[index]:
            del lines[index]
        else:
            index += 1
    return lines or [""]


def markup_text_keep_punctuation(
    text: str, cjk_font: fitz.Font, latin_font: fitz.Font
) -> str:
    output: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if text[index] not in NO_LINE_START_PUNCTUATION or index <= start:
            index += 1
            continue
        punctuation_end = index + 1
        while (
            punctuation_end < len(text)
            and text[punctuation_end] in NO_LINE_START_PUNCTUATION
        ):
            punctuation_end += 1
        protected_start = index - 1
        if protected_start > start:
            output.append(markup_text(text[start:protected_start], cjk_font, latin_font))
        output.append(
            "<nobr>"
            + markup_text(text[protected_start:punctuation_end], cjk_font, latin_font)
            + "</nobr>"
        )
        start = punctuation_end
        index = punctuation_end
    if start < len(text):
        output.append(markup_text(text[start:], cjk_font, latin_font))
    return "".join(output)


def footer(canvas, document) -> None:
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(colors.HexColor("#D8D8D8"))
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.restoreState()


def build_pdf(entries: list[Entry], output_path: Path, seed: str, edition: str) -> list[Entry]:
    cjk_font, latin_font = register_fonts()
    shuffled = list(entries)
    random.Random(seed).shuffle(shuffled)

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=PAGE_SIDE_MARGIN,
        rightMargin=PAGE_SIDE_MARGIN,
        topMargin=22 * mm,
        bottomMargin=25 * mm,
        title=f"高中英语《新课程标准》3100词总表 · {edition} · 乱序版",
        author="编制：LaoShui",
        subject=f"普通高中英语课程标准3100词表 · {edition}",
        creator="编制：LaoShui",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ChineseTitle",
        parent=styles["Title"],
        fontName="STSong",
        fontSize=19,
        leading=29,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#171717"),
        spaceAfter=5 * mm,
    )
    subtitle_style = ParagraphStyle(
        "ChineseSubtitle",
        parent=styles["BodyText"],
        fontName="STKaiti",
        fontSize=12,
        leading=18,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
    )
    note_style = ParagraphStyle(
        "ChineseNote",
        parent=styles["BodyText"],
        fontName="STKaiti",
        fontSize=11.2,
        leading=20,
        wordWrap="CJK",
        alignment=TA_LEFT,
        textColor=colors.black,
        leftIndent=4 * mm,
        rightIndent=4 * mm,
    )
    entry_style = ParagraphStyle(
        "Entry",
        parent=styles["BodyText"],
        fontName="STKaiti",
        fontSize=10.8,
        leading=16.5,
        alignment=TA_LEFT,
        textColor=colors.black,
        spaceAfter=2.6,
        allowWidows=0,
        allowOrphans=0,
        wordWrap=None,
    )
    final_title_style = ParagraphStyle(
        "FinalTitle",
        parent=title_style,
        fontSize=17,
        leading=28,
        spaceAfter=15 * mm,
    )
    final_style = ParagraphStyle(
        "Final",
        parent=subtitle_style,
        fontSize=14,
        leading=25,
        textColor=colors.HexColor("#222222"),
    )

    story = [
        Spacer(1, 15 * mm),
        Paragraph("高中英语《新课程标准》3100词总表", title_style),
        Paragraph(f"{edition} · 乱序版", subtitle_style),
        Spacer(1, 8 * mm),
        Paragraph("【编写说明】", note_style),
        Paragraph(
            "本词表以《普通高中英语课程标准（2017年版2025年修订）》附录2为词头与星级依据，并结合多方资料补充音标、高考高频释义、必要熟词生义及常用派生/搭配。",
            note_style,
        ),
        Paragraph("(1) 无星号：义务教育阶段要求掌握的词汇。", note_style),
        Paragraph("(2) *：高中英语必修课程应学习和掌握的词汇。", note_style),
        Paragraph("(3) **：高中英语选择性必修课程应学习和掌握的词汇。", note_style),
        Paragraph(
            '(4) 本词表由 LaoShui 依据多方资料整理编制而成。虽经反复校核，然限于学识，错漏之处在所难免，敬请读者不吝赐教。如蒙指正，烦请访问 '
            '<font name="TimesNewRoman"><link href="https://github.com/laoshuikaixue/gaokao-3100-wordlist" color="#245A9A">https://github.com/laoshuikaixue/gaokao-3100-wordlist</link></font>，'
            '提交 Issue 或 Pull Request，以便及时修订完善。谨此致谢。',
            note_style,
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            "注：音标以英式读音为主，必要时标注英美差异；正文为乱序版。",
            note_style,
        ),
        PageBreak(),
    ]

    for entry in shuffled:
        text = merge_entry_rows(entry.rows)
        lines = wrap_entry_text(text, ENTRY_WRAP_WIDTH, 10.8, cjk_font, latin_font)
        paragraph = Paragraph(
            "<br/>".join(
                markup_text_keep_punctuation(line, cjk_font, latin_font)
                for line in lines
            ),
            entry_style,
        )
        story.append(KeepTogether([paragraph]))

    document.build(
        story,
        onFirstPage=footer,
        onLaterPages=footer,
        canvasmaker=NumberedCanvas,
    )
    return shuffled


def digest_entries(entries: list[Entry]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entry.text for entry in entries):
        digest.update(entry.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a shuffled Gaokao 3100 word-list PDF.")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_pdf", type=Path)
    parser.add_argument(
        "--seed",
        default="LaoShui-gaokao-3100-wordlist-2026-07-20",
        help="Deterministic shuffle seed.",
    )
    args = parser.parse_args()

    rows = extract_visual_rows(args.input_pdf)
    entries = extract_entries(rows)
    if len(entries) < 3000:
        raise RuntimeError(f"Only {len(entries)} entries were detected; extraction is incomplete.")

    before = digest_entries(entries)
    if "2026版" in args.input_pdf.name:
        edition = "2026版"
    elif "2025差异版" in args.input_pdf.name:
        edition = "2025差异版"
    elif "校正版" in args.input_pdf.name:
        edition = "2025差异版"
    else:
        edition = "2025版"
    shuffled = build_pdf(entries, args.output_pdf, args.seed, edition)
    after = digest_entries(shuffled)
    if before != after:
        raise RuntimeError("Entry content changed during shuffling.")

    unchanged_positions = sum(a == b for a, b in zip(entries, shuffled))
    print(f"Detected entries: {len(entries)}")
    print(f"Visual rows: {sum(len(entry.rows) for entry in entries)}")
    print(f"Content SHA-256: {before}")
    print(f"Unchanged positions after shuffle: {unchanged_positions}")
    print(f"Edition: {edition}")
    print(f"Output: {args.output_pdf.resolve()}")


if __name__ == "__main__":
    main()

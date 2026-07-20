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
        self.setFillColor(colors.HexColor("#666666"))
        self.setFont("STKaiti", 8.5)
        self.drawCentredString(
            width / 2,
            8.5 * mm,
            f"第 {self._pageNumber} 页 共 {total_pages} 页",
        )
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
    if text.startswith("a. m./"):
        return True

    if "/" not in text:
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


def footer(canvas, document) -> None:
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(colors.HexColor("#D8D8D8"))
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.restoreState()


def build_pdf(
    entries: list[Entry], output_path: Path, seed: str, corrected: bool
) -> list[Entry]:
    cjk_font, latin_font = register_fonts()
    shuffled = list(entries)
    random.Random(seed).shuffle(shuffled)

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=19 * mm,
        rightMargin=19 * mm,
        topMargin=17 * mm,
        bottomMargin=20 * mm,
        title=(
            "高中英语《新课程标准》3100词总表（2025校正版）乱序版"
            if corrected
            else "高中英语《新课程标准》3100词总表（2025版）乱序版"
        ),
        author="LaoShui",
        subject="单词原始来源：IAI English",
        creator="LaoShui",
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

    intro_lines = [
        "【编写说明】",
        (
            "本词汇表共3100词，按字母顺序，依次分类包括："
            if corrected
            else "本词汇表共3000词，按字母顺序，依次分类包括："
        ),
        "(1) 初中英语义务教育阶段要求掌握的1600个单词；",
        "(2) 高中英语必修课程应学习和掌握500个单词（词尾加有一个*号）；",
        (
            "(3) 高中英语选择性必修课程应学习和掌握1000个单词（词尾加有两个*号）。"
            if corrected
            else "(3) 高中英语选择性必修课程应学习和掌握l000个单词（词尾加有两个*号）。"
        ),
    ]
    if corrected:
        intro_lines.append(
            "(4) 本版系在2025版基础上由LaoShui校正，限于学识，错漏之处在所难免，尚祈读者不吝指正。"
        )
    intro_lines.extend(
        [
            "注：本表出现的单词要求全部背诵，并要求掌握其派生词！",
            "如：sight-sighted；space-spacious",
            "新高考命题以新课标为准！",
        ]
    )
    intro_markup_lines: list[str] = []
    for line in intro_lines:
        marked_up = markup_text(line, cjk_font, latin_font)
        if corrected and line.startswith("(4) "):
            # This line fits at 11 pt but narrowly wraps at the default 11.2 pt.
            marked_up = f'<font size="11">{marked_up}</font>'
            marked_up += "<br/>"
        intro_markup_lines.append(marked_up)
    intro_markup = "<br/>".join(intro_markup_lines)

    story = [
        Spacer(1, 15 * mm),
        Paragraph("高中英语《新课程标准》3100词总表", title_style),
        Paragraph("2025校正版 · 乱序版" if corrected else "2025版 · 乱序版", subtitle_style),
        Spacer(1, 13 * mm),
        Paragraph(intro_markup, note_style),
        PageBreak(),
    ]

    for entry in shuffled:
        lines = [markup_text(line, cjk_font, latin_font) for line in entry.rows]
        paragraph = Paragraph("<br/>".join(lines), entry_style)
        story.append(KeepTogether([paragraph]))

    story.extend(
        [
            PageBreak(),
            Spacer(1, 58 * mm),
            Paragraph("编制说明", final_title_style),
            Paragraph('<font name="TimesNewRoman-Bold">Powered By LaoShui</font>', final_style),
            Spacer(1, 5 * mm),
            Paragraph(
                markup_text("单词原始来源：IAI English", cjk_font, latin_font),
                final_style,
            ),
        ]
    )

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
    parser = argparse.ArgumentParser(description="Create a shuffled IAI English word-list PDF.")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_pdf", type=Path)
    parser.add_argument(
        "--seed",
        default="LaoShui-IAI-English-3100-2026-07-15",
        help="Deterministic shuffle seed.",
    )
    args = parser.parse_args()

    rows = extract_visual_rows(args.input_pdf)
    entries = extract_entries(rows)
    if len(entries) < 3000:
        raise RuntimeError(f"Only {len(entries)} entries were detected; extraction is incomplete.")

    before = digest_entries(entries)
    corrected = "校正版" in args.input_pdf.name
    shuffled = build_pdf(entries, args.output_pdf, args.seed, corrected)
    after = digest_entries(shuffled)
    if before != after:
        raise RuntimeError("Entry content changed during shuffling.")

    unchanged_positions = sum(a == b for a, b in zip(entries, shuffled))
    print(f"Detected entries: {len(entries)}")
    print(f"Visual rows: {sum(len(entry.rows) for entry in entries)}")
    print(f"Content SHA-256: {before}")
    print(f"Unchanged positions after shuffle: {unchanged_positions}")
    print(f"Edition: {'2025校正版' if corrected else '2025版'}")
    print(f"Output: {args.output_pdf.resolve()}")


if __name__ == "__main__":
    main()

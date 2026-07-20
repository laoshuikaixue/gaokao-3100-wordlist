from __future__ import annotations

import argparse
import hashlib
import html
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SCRIPT_DIR, SCRIPT_DIR.parent, SCRIPT_DIR.parent.parent):
    if (candidate / "make_shuffled_3100.py").exists():
        sys.path.insert(0, str(candidate))
for candidate in (SCRIPT_DIR, SCRIPT_DIR.parent, SCRIPT_DIR.parent.parent):
    dependency_dir = candidate / "tmp" / "pdf-deps"
    if dependency_dir.is_dir():
        sys.path.insert(0, str(dependency_dir))

from make_shuffled_3100 import (  # noqa: E402
    BODY_BOTTOM,
    BODY_TOP,
    Entry,
    NumberedCanvas,
    extract_entries,
    extract_visual_rows,
    markup_text,
    register_fonts,
)
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


@dataclass(frozen=True)
class Question:
    number: int
    entry: Entry
    direction: str


class DictationCanvas(NumberedCanvas):
    """Use the shared footer: signature left, page number right."""


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def quiz_headword(entry: Entry) -> str:
    first_row = normalize_text(entry.rows[0])
    acronym = re.match(
        r"^(AI\s*\(=artificial intelligence\)|BCE\s*\(Before the Common Era\)|CE（Common Era）)\**",
        first_row,
    )
    headword = acronym.group(1) if acronym else normalize_text(entry.headword)
    headword = re.sub(r"\s+(?:BrE|AmE)$", "", headword)
    headword = re.sub(r"\*+$", "", headword)
    return headword.strip()


def contains_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def remove_non_chinese_parentheses(text: str) -> str:
    pattern = re.compile(r"([（(])([^()（）]*)([）)])")

    def replace(match: re.Match[str]) -> str:
        content = match.group(2).strip()
        if not contains_chinese(content) or re.search(r"[A-Za-z]", content):
            return " "
        return f"（{content}）"

    previous = None
    while text != previous:
        previous = text
        text = pattern.sub(replace, text)
    return text


def balance_chinese_parentheses(text: str) -> str:
    output: list[str] = []
    open_positions: list[int] = []
    for char in text:
        if char == "（":
            open_positions.append(len(output))
            output.append(char)
        elif char == "）":
            if open_positions:
                open_positions.pop()
                output.append(char)
        else:
            output.append(char)
    for position in reversed(open_positions):
        del output[position]
    return "".join(output)


def chinese_prompt(entry: Entry) -> str:
    full_text = normalize_text(" ".join(entry.rows))
    headword = quiz_headword(entry)
    remainder = full_text[len(headword) :] if full_text.startswith(headword) else full_text
    remainder = re.sub(r"^\*+", "", remainder).lstrip()

    # A slash pair is pronunciation only when its contents have no Chinese.
    # This preserves real Chinese alternatives such as 上方/部 and 上层/流.
    remainder = re.sub(
        r"/([^/\n]{1,120})/",
        lambda match: " " if not contains_chinese(match.group(1)) else match.group(0),
        remainder,
    )
    # Remove English-only inflection notes and abbreviations as complete units,
    # rather than leaving their commas and closing parentheses behind.
    remainder = remove_non_chinese_parentheses(remainder)
    remainder = re.sub(
        r"\[([^\[\]]*)\]",
        lambda match: match.group(0) if contains_chinese(match.group(1)) else " ",
        remainder,
    )
    # Convert part-of-speech boundaries into a readable Chinese separator.
    remainder = re.sub(
        r"(?i)(?<![A-Za-z])(?:modal\s+v|aux(?:iliary)?\s+v|art|adj|adv|prep|pron|conj|num|det|int|abbr|vt|vi|pl|n|v|ad|a)\.?(?=\s|[A-Za-z\u4e00-\u9fff（(\[<])",
        "；",
        remainder,
    )
    remainder = re.sub(r"[A-Za-z]+(?:[.'’-][A-Za-z]+)*", " ", remainder)

    allowed_punctuation = set(
        "，。；：、（）()《》〈〉…“”‘’！!?？-—·/＋+＝=,.%％℃°"
    )
    kept: list[str] = []
    for char in remainder:
        if "\u4e00" <= char <= "\u9fff" or char.isdigit() or char in allowed_punctuation:
            kept.append(char)
        else:
            kept.append(" ")
    prompt = normalize_text("".join(kept))
    prompt = prompt.translate(str.maketrans({",": "，", ";": "；", ":": "：", "!": "！", "?": "？"}))
    prompt = re.sub(r"\.{2,}", "…", prompt)
    prompt = re.sub(r"(?<!\d)\.(?!\d)", "", prompt)
    prompt = prompt.replace("(", "（").replace(")", "）")
    prompt = re.sub(r"\s*([，。；：、！？）])\s*", r"\1", prompt)
    prompt = re.sub(r"\s*（\s*", "（", prompt)
    prompt = re.sub(
        r"(?<=[\u4e00-\u9fff）])\s+(?=[\u4e00-\u9fff（])",
        "",
        prompt,
    )
    prompt = re.sub(r"[；，]{2,}", "；", prompt)
    prompt = re.sub(r"；(?=[，。；：])", "", prompt)
    prompt = re.sub(r"，(?=[，。；：])", "", prompt)
    prompt = balance_chinese_parentheses(prompt)
    prompt = re.sub(r"^[\s，。；：、/）.。-]+", "", prompt)
    prompt = re.sub(r"[\s，。；：、/.（]+$", "", prompt)
    prompt = re.sub(r"(?:反|同|派生)$", "", prompt).rstrip("，。；：、 ")
    return prompt or "（请根据词条释义作答）"


def direction_for(entry: Entry) -> str:
    digest = hashlib.sha256(quiz_headword(entry).encode("utf-8")).digest()
    return "en_to_zh" if digest[0] % 2 == 0 else "zh_to_en"


def make_questions(entries: list[Entry], mode: str) -> list[Question]:
    if mode not in {"mixed", "en_to_zh", "zh_to_en"}:
        raise ValueError(f"Unsupported dictation mode: {mode}")
    return [
        Question(
            number=index,
            entry=entry,
            direction=direction_for(entry) if mode == "mixed" else mode,
        )
        for index, entry in enumerate(entries, start=1)
    ]


def answer_text(question: Question) -> str:
    text = normalize_text(" ".join(question.entry.rows))
    text = re.sub(
        r"(?<=[\u4e00-\u9fff）])\s+(?=[\u4e00-\u9fff（])",
        "",
        text,
    )
    text = re.sub(r"(?<=[\u4e00-\u9fff）])\s+(?=[，。；：、！？])", "", text)
    text = re.sub(r"(?<=[，。；：、！？])\s+(?=[\u4e00-\u9fff（])", "", text)
    return text


NO_LINE_START_PUNCTUATION = set("，。；：、！？）》】」』”’％%,.;:!?/)")


def text_width(text: str, font_size: float, cjk_font, latin_font) -> float:
    width = 0.0
    for char in text:
        codepoint = ord(char)
        use_latin = (
            codepoint < 0x0250 or 0x0250 <= codepoint <= 0x02FF
        ) and latin_font.has_glyph(codepoint)
        if not cjk_font.has_glyph(codepoint) and latin_font.has_glyph(codepoint):
            use_latin = True
        font_name = "TimesNewRoman" if use_latin else "STKaiti"
        width += pdfmetrics.stringWidth(char, font_name, font_size)
    return width


def wrap_text_for_cell(
    text: str,
    first_line_width: float,
    later_line_width: float,
    font_size: float,
    cjk_font,
    latin_font,
) -> list[str]:
    """Pre-wrap text so closing punctuation always remains on the prior line."""
    lines: list[str] = []
    current: list[str] = []
    current_width = 0.0
    limit = first_line_width

    for char in text:
        char_width = text_width(char, font_size, cjk_font, latin_font)
        if current and current_width + char_width > limit:
            if char in NO_LINE_START_PUNCTUATION:
                current.append(char)
                lines.append("".join(current))
                current = []
                current_width = 0.0
                limit = later_line_width
                continue
            lines.append("".join(current))
            current = [char]
            current_width = char_width
            limit = later_line_width
        else:
            current.append(char)
            current_width += char_width

    if current:
        lines.append("".join(current))
    # A closing bracket can itself fill the line and be followed by another
    # punctuation mark. Move any such leading punctuation back after wrapping.
    line_index = 1
    while line_index < len(lines):
        leading: list[str] = []
        while lines[line_index] and lines[line_index][0] in NO_LINE_START_PUNCTUATION:
            leading.append(lines[line_index][0])
            lines[line_index] = lines[line_index][1:]
        if leading:
            lines[line_index - 1] += "".join(leading)
        if not lines[line_index]:
            del lines[line_index]
        else:
            line_index += 1
    return lines or [""]


def question_text(
    question: Question, cjk_font, latin_font, show_direction: bool
) -> str:
    if question.direction == "en_to_zh":
        plain_prompt = quiz_headword(question.entry)
        direction_markup = ""
        direction_width = 0.0
        if show_direction:
            direction_markup = "<font color='#245A9A'>英</font>　"
            direction_width = text_width("英　", 9.6, cjk_font, latin_font)
    else:
        plain_prompt = chinese_prompt(question.entry)
        direction_markup = ""
        direction_width = 0.0
        if show_direction:
            direction_markup = "<font color='#A05A00'>中</font>　"
            direction_width = text_width("中　", 9.6, cjk_font, latin_font)

    number_width = pdfmetrics.stringWidth(
        f"{question.number}. ", "TimesNewRoman-Bold", 9.6
    )
    lines = wrap_text_for_cell(
        plain_prompt,
        max(120.0, 228.0 - number_width - direction_width),
        228.0,
        9.6,
        cjk_font,
        latin_font,
    )
    first_line = (
        f"<b>{question.number}.</b> {direction_markup}"
        + markup_text(lines[0], cjk_font, latin_font)
    )
    remaining_lines = [markup_text(line, cjk_font, latin_font) for line in lines[1:]]
    return "<br/>".join(
        [first_line, *remaining_lines, "<font color='#999999'>________________________________</font>"]
    )


def answer_cell_text(
    question: Question, cjk_font, latin_font, show_direction: bool
) -> str:
    direction = "英→中" if question.direction == "en_to_zh" else "中→英"
    marker = f"[{direction}] " if show_direction else ""
    text = f"{question.number}. {marker}{answer_text(question)}"
    # Mixed IPA/Latin/CJK runs can measure slightly wider after ReportLab
    # fragments them by font, so keep a larger safety margin than questions.
    lines = wrap_text_for_cell(text, 210.0, 210.0, 8.1, cjk_font, latin_font)
    return "<br/>".join(
        markup_text(line, cjk_font, latin_font) for line in lines
    )


def draw_header(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#D8D8D8"))
    canvas.setLineWidth(0.4)
    canvas.line(12 * mm, height - 16 * mm, width - 12 * mm, height - 16 * mm)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.setFont("STKaiti", 8.5)
    canvas.drawString(12 * mm, height - 11.5 * mm, document._dictation_header)
    canvas.restoreState()


def build_pdf(
    questions: list[Question],
    output_path: Path,
    title: str,
    header: str,
    show_direction: bool,
    answer: bool,
) -> None:
    cjk_font, latin_font = register_fonts()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DictationTitle",
        parent=styles["Title"],
        fontName="STSong",
        fontSize=18,
        leading=25,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#171717"),
        spaceAfter=3 * mm,
    )
    question_style = ParagraphStyle(
        "DictationQuestion",
        parent=styles["BodyText"],
        fontName="STKaiti",
        fontSize=9.6,
        leading=12.2,
        alignment=TA_LEFT,
        textColor=colors.black,
        wordWrap=None,
    )
    answer_style = ParagraphStyle(
        "DictationAnswer",
        parent=question_style,
        fontSize=8.1,
        leading=10.2,
    )

    usable_width = A4[0] - 24 * mm
    cell_width = usable_width / 2
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=21 * mm,
        bottomMargin=17 * mm,
        title=title,
        author="LaoShui",
        subject="高中英语3100词默写版",
        creator="LaoShui",
    )
    document._dictation_header = header

    story = [
        Spacer(1, 3 * mm),
        Paragraph(title, title_style),
        Spacer(1, 1.5 * mm),
    ]

    table_rows = []
    for row_start in range(0, len(questions), 2):
        pair = questions[row_start : row_start + 2]
        cells = []
        for question in pair:
            cell_markup = (
                answer_cell_text(question, cjk_font, latin_font, show_direction)
                if answer
                else question_text(question, cjk_font, latin_font, show_direction)
            )
            cells.append(Paragraph(cell_markup, answer_style if answer else question_style))
        if len(cells) == 1:
            cells.append("")
        table_rows.append(cells)

    # One long table lets ReportLab fill each page to the usable bottom edge,
    # while still splitting only between complete question rows.
    table = LongTable(
        table_rows,
        colWidths=[cell_width, cell_width],
        hAlign="LEFT",
        repeatRows=0,
        splitByRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.2 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#E2E2E2")),
                ("LINEAFTER", (0, 0), (0, -1), 0.25, colors.HexColor("#E2E2E2")),
            ]
        )
    )
    story.append(table)

    document.build(
        story,
        onFirstPage=draw_header,
        onLaterPages=draw_header,
        canvasmaker=DictationCanvas,
    )


def make_outputs(input_pdf: Path, output_dir: Path, seed: str) -> list[Path]:
    rows = extract_visual_rows(input_pdf)
    entries = extract_entries(rows)
    if len(entries) < 3000:
        raise RuntimeError(f"Only {len(entries)} entries were detected; extraction is incomplete.")

    shuffled_entries = list(entries)
    random.Random(seed).shuffle(shuffled_entries)

    if "2026版" in input_pdf.name:
        edition = "2026版"
    elif "2025差异版" in input_pdf.name or "校正版" in input_pdf.name:
        edition = "2025差异版"
    else:
        edition = "2025版"
    stem = f"高中英语3100词默写版（{edition}）"
    variants = [
        ("混合", "mixed", True),
        ("中写英", "zh_to_en", False),
        ("英写中", "en_to_zh", False),
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for label, mode, show_direction in variants:
        ordered = make_questions(entries, mode)
        shuffled = make_questions(shuffled_entries, mode)
        ordered_output = output_dir / f"{stem}_{label}_正序.pdf"
        shuffled_output = output_dir / f"{stem}_{label}_乱序.pdf"
        answer_output = output_dir / f"{stem}_{label}_乱序答案.pdf"
        outputs.extend([ordered_output, shuffled_output, answer_output])
        build_pdf(
            ordered,
            ordered_output,
            f"高中英语3100词默写版（{edition}）· {label} · 正序",
            f"{edition} · 默写版 · {label} · 正序",
            show_direction,
            False,
        )
        build_pdf(
            shuffled,
            shuffled_output,
            f"高中英语3100词默写版（{edition}）· {label} · 乱序",
            f"{edition} · 默写版 · {label} · 乱序",
            show_direction,
            False,
        )
        build_pdf(
            shuffled,
            answer_output,
            f"高中英语3100词默写版（{edition}）· {label} · 乱序答案",
            f"{edition} · 默写答案 · {label} · 乱序",
            show_direction,
            True,
        )
    print(f"Detected entries: {len(entries)}")
    print(f"Output directory: {output_dir.resolve()}")
    for output in outputs:
        print(f"Output: {output.resolve()}")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Create ordered and shuffled dictation PDFs.")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--seed",
        default="LaoShui-gaokao-3100-wordlist-dictation-2026-07-20",
        help="Deterministic shuffle seed.",
    )
    args = parser.parse_args()
    make_outputs(args.input_pdf, args.output_dir, args.seed)


if __name__ == "__main__":
    main()

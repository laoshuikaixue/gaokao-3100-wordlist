from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
PDF_DEPS = ROOT / "tmp" / "pdf-deps"
if PDF_DEPS.exists():
    sys.path.insert(0, str(PDF_DEPS))

import pymupdf as fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


SOURCE = ROOT / "2025届高考英语《新课程标准》3100词总表.pdf"
OUTPUT_DIR = ROOT / "output" / "pdf"
CORRECTED = OUTPUT_DIR / "2025届高考英语《新课程标准》3100词总表（2025校正版）_LaoShui.pdf"
DETAILS = OUTPUT_DIR / "2025届高考英语3100词总表_校正明细.pdf"
TEMP_DIR = ROOT / "tmp" / "pdfs"
FONT_DIR = TEMP_DIR / "fonts"

SYSTEM_TIMES = Path(r"C:\Windows\Fonts\times.ttf")
SYSTEM_KAITI = Path(r"C:\Windows\Fonts\STKAITI.TTF")
DETAIL_REGULAR = Path(r"C:\Windows\Fonts\Deng.ttf")
DETAIL_BOLD = Path(r"C:\Windows\Fonts\Dengb.ttf")

BLACK = (0.0, 0.0, 0.0)
LIGHT_BLUE = (74 / 255, 144 / 255, 217 / 255)
MEDIUM_BLUE = (31 / 255, 111 / 255, 178 / 255)
DEEP_BLUE = (11 / 255, 79 / 255, 156 / 255)
RED = (192 / 255, 0.0, 0.0)
COLORS = {
    "black": BLACK,
    "light": LIGHT_BLUE,
    "medium": MEDIUM_BLUE,
    "deep": DEEP_BLUE,
    "red": RED,
}
COLOR_NAMES = {
    "light": "浅蓝",
    "medium": "中蓝",
    "deep": "深蓝",
}


@dataclass(frozen=True)
class Correction:
    code: str
    page: int
    entry: str
    kind: str
    original: str
    corrected: str
    level: str
    note: str


CORRECTIONS = [
    Correction("F001", 1, "标题", "版本", "2025版", "2025校正版", "deep", "按校正版要求更新标题。"),
    Correction("F002", 1, "编写说明", "数量", "本词汇表共3000词", "本词汇表共3100词", "deep", "分项1600+500+1000合计为3100。"),
    Correction("F003", 1, "编写说明", "字符", "l000个单词", "1000个单词", "deep", "把文本层误写的小写字母l改为数字1。"),
    Correction("F004", 1, "编写说明", "署名", "无校正说明", "(4) 本版系在2025版基础上由LaoShui校正，限于学识，错漏之处在所难免，尚祈读者不吝指正。", "medium", "作为编写说明第(4)条补充。"),
    Correction("C044", 1, "a(an)", "音标完善", "/ə(n)/", "/ə, eɪ; ən, æn/", "light", "补充a、an的强读形式。"),
    Correction("C038", 1, "ability", "反义词", "反disability", "反inability", "medium", "inability才是ability的直接反义词。"),
    Correction("C004", 2, "ad (=advertisement)", "音标", "/əd'vɜːtɪsmənt/", "/æd/", "light", "原音标是advertisement的全称读音。"),
    Correction("C026a", 3, "AI", "音标补充", "未标音", "/ˌeɪ ˈaɪ/", "light", "补充缩写读音。"),
    Correction("C006", 4, "addict", "音标/词性", "名词、动词共用/ə'dɪkt/", "名词/ˈædɪkt/；动词/əˈdɪkt/", "light", "按词性区分重音。"),
    Correction("C020", 10, "better", "重音", "/betə/", "/ˈbetə/", "light", "补主重音。"),
    Correction("C002", 12, "behaviour", "拼写/排版", "behaviour)*", "behaviour(behavior)*", "deep", "删除多余右括号并补充美式拼写。"),
    Correction("C026b", 13, "BCE", "音标补充", "未标音", "/ˌbiː siː ˈiː/", "light", "补充缩写读音。"),
    Correction("C032", 13, "bias", "释义", "含“天赋、偏重心球形、偏统”等错误或破损文本", "偏见；偏向；统计偏差；斜纹；偏压/偏流等", "deep", "重写破损释义，保留常用及必要专业义。"),
    Correction("C033", 15, "can", "变形/用法", "听(could, could)", "删除“听”；标为past: could", "medium", "情态动词没有过去分词，删除多余字。"),
    Correction("C007", 15, "car", "音标", "/kaː/", "BrE /kɑː(r)/；AmE /kɑːr/", "light", "补全英式非卷舌提示和美式卷舌读音。"),
    Correction("C026c", 22, "CE", "音标补充", "未标音", "/ˌsiː ˈiː/", "light", "补充缩写读音。"),
    Correction("C008", 23, "circumstance", "音标", "/'səːkəmstəns/", "/ˈsɜːkəmstəns/", "light", "把错误的/əː/改为/ɜː/。"),
    Correction("C021", 26, "cruel", "重音", "/kruːəl/", "/ˈkruːəl/", "light", "补主重音。"),
    Correction("C027", 30, "due to", "词头/用法/释义", "due to /djuː/ adj. 应得的、到期的等", "due to /ˈdjuː tə/ prep. 由于；因为", "deep", "原内容实际解释的是形容词due。"),
    Correction("C009", 31, "deserve", "音标", "/dɪ'zəːv/", "/dɪˈzɜːv/", "light", "把错误的/əː/改为/ɜː/。"),
    Correction("C005", 34, "exam (=examination)", "音标/释义", "/ɪgˌzæmɪ'neɪʃn/；考试(=exam)；检查", "/ɪɡˈzæm/；考试；（身体）检查", "light", "修正简称音标，并删除循环解释、明确检查义。"),
    Correction("C034", 36, "emphasis", "派生词", "v.emphsise/emphasize", "v.emphasise/emphasize", "medium", "修正emphasise拼写。"),
    Correction("C040", 43, "fluent", "派生词性", "v.fluency", "n.fluency adv.fluently", "medium", "fluency是名词，并补充常用副词。"),
    Correction("C010", 43, "fountain", "音标", "/'fauntɪn/", "/ˈfaʊntən/", "light", "修正双元音并采用维词读音。"),
    Correction("C039", 48, "helpful", "反义词", "反helpless", "反unhelpful", "medium", "helpless不是helpful的直接反义词。"),
    Correction("C011", 56, "laptop", "音标", "/ˈlæplɒp/", "/ˈlæptɒp/", "light", "补回漏掉的/t/。"),
    Correction("C028", 57, "lightening", "词头/释义", "lightening及lighten的-ing义、产科义", "lightning /ˈlaɪtnɪŋ/ n. 闪电", "deep", "改回高中常用核心词lightning。"),
    Correction("C022", 61, "meaning", "重音", "/miːnɪŋ/", "/ˈmiːnɪŋ/", "light", "补主重音。"),
    Correction("C023", 61, "meeting", "重音", "/miːtɪŋ/", "/ˈmiːtɪŋ/", "light", "补主重音。"),
    Correction("C029", 63, "mobile phone", "词头/音标/词性/释义", "内容实际解释mobile形容词", "mobile phone /ˌməʊbaɪl ˈfəʊn/ n. 移动电话；手机", "deep", "改为与词头一致的名词短语。"),
    Correction("C012", 66, "not", "音标", "/nɔt/", "/nɒt/", "light", "修正为本表英式体系读音。"),
    Correction("C030", 68, "Olympics", "词形/词性", "Olympics标作adj.且释为奥运会", "Olympic adj.奥林匹克的；the Olympics n.奥林匹克运动会", "deep", "分列形容词和名词用法。"),
    Correction("C013", 69, "ought to", "音标", "/ɔːt/", "/ˈɔːt tə/", "light", "补全to的弱读。"),
    Correction("C014", 69, "overseas", "重音", "/ˈəʊvəˈsiːz/", "/ˌəʊvəˈsiːz/", "light", "首个主重音改为次重音。"),
    Correction("C015", 70, "overall", "重音", "/ˈəʊvərɔːl/", "/ˌəʊvərˈɔːl/", "light", "按形容词/副词义修正重音。"),
    Correction("N001", 71, "penguin", "删除噪声", "空军地勤人员", "删除", "medium", "删除与高考核心词义无关的低频行业义。"),
    Correction("C003", 71, "per cent (percent)", "排版/词性", "多一个左括号；仅标n.", "per cent（percent）/pə'sent/ n., adj. & adv.", "medium", "修正括号并补充常用词性。"),
    Correction("N002", 72, "pizza", "删除噪声", "(Pizza)(意)皮扎(人名)", "删除", "medium", "删除专名义。"),
    Correction("C042", 73, "popular / pop", "词条混写", "popular与pop的音标、词性和释义混在一条", "popular与pop分成两条", "deep", "分别给出形容词和流行音乐义。"),
    Correction("N003", 73, "porridge", "删除噪声", "<英，非正式>关押期，监禁期", "删除", "medium", "删除与高考核心词义无关的低频俚语。"),
    Correction("C016", 75, "pollution", "音标", "/pəː'luːʃn/", "/pəˈluːʃn/", "light", "删除首音节错误长音。"),
    Correction("C035", 80, "regret", "派生词", "regretable", "regrettable", "medium", "补回漏掉的t。"),
    Correction("C017", 83, "rhythm", "音标", "/ˈrɪðəmn/", "/ˈrɪðəm/", "light", "删除末尾多余的/n/。"),
    Correction("C036", 83, "romantic", "派生词", "romanism", "romanticism", "medium", "浪漫主义应为romanticism。"),
    Correction("C024", 93, "slightly", "重音", "/slaɪtli/", "/ˈslaɪtli/", "light", "补主重音。"),
    Correction("C018", 95, "sausage", "音标", "/'sɔːsɪdʒ/", "/ˈsɒsɪdʒ/", "light", "修正常用英式元音。"),
    Correction("C031", 97, "statistic", "词形/释义", "单数statistic同时释为统计学", "区分statistic与statistics", "deep", "分别列统计数字/统计量与统计资料/统计学。"),
    Correction("C037", 97, "subsequent", "派生/词性", "n.subsequence", "adv.subsequently", "medium", "改为常用派生副词。"),
    Correction("C041", 100, "tour", "派生词性", "a.tourism", "n.tourism", "medium", "tourism是名词。"),
    Correction("C019", 103, "tournament", "音标/口音标注", "/'tɔːnəmənt/（未标口音）", "BrE /ˈtʊənəmənt/（也作 /ˈtɔːnəmənt/）；AmE /ˈtɜːrnəmənt/", "light", "原读音不再定为硬错；明确区分英式主要变体与美式卷舌读音。"),
    Correction("C025", 107, "website", "重音", "/websaɪt/", "/ˈwebsaɪt/", "light", "补主重音。"),
    Correction("N004", 108, "wolf", "删除噪声", "<美，非正式>同性恋者", "删除", "medium", "删除过时且可能冒犯的俚语义。"),
    Correction("N005", 109, "wetland", "删除噪声", "(Wetland)(德)韦特兰(人名)", "删除", "medium", "删除专名义。"),
    Correction("C043", 109, "Wi-Fi", "用法/事实", "全写为wireless fidelity", "删除", "medium", "Wi-Fi是品牌名称，并非Wireless Fidelity的正式缩写；该说法源于早期营销标语。"),
    Correction("C045", 109, "worse", "变形说明", "dad, badly的比较级", "bad, badly的比较级", "deep", "dad为bad的误写。"),
    Correction("C046", 109, "worst", "变形说明", "dad, badly的最高级", "bad, badly的最高级", "deep", "dad为bad的误写。"),
]

DETAIL_CORRECTIONS = [item for item in CORRECTIONS if not item.code.startswith("F")]


def is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x9FFF
        or 0x3000 <= code <= 0x303F
        or 0xFF00 <= code <= 0xFFEF
    )


def iter_font_runs(text: str):
    if not text:
        return
    start = 0
    current = "kaiti" if is_cjk(text[0]) else "times"
    for index, char in enumerate(text[1:], 1):
        kind = "kaiti" if is_cjk(char) else "times"
        if kind != current:
            yield text[start:index], current
            start = index
            current = kind
    yield text[start:], current


def extract_original_fonts(doc: fitz.Document) -> dict[str, Path]:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    wanted = {
        "TimesNewRomanPSMT": "times",
        "HYKaiTiKW": "kaiti",
        "STKaiti": "stkaiti",
        "HYShuSongErKW": "shusong",
    }
    found = {}
    for page in doc:
        for xref, _ext, _type, basefont, *_rest in page.get_fonts(full=True):
            plain_name = basefont.split("+")[-1]
            key = wanted.get(plain_name)
            if not key or key in found:
                continue
            name, ext, _font_type, content = doc.extract_font(xref)
            path = FONT_DIR / f"{name.split('+')[-1]}.{ext}"
            path.write_bytes(content)
            found[key] = path
        if len(found) == len(wanted):
            break
    found.setdefault("times", SYSTEM_TIMES)
    found.setdefault("kaiti", SYSTEM_KAITI)
    found.setdefault("stkaiti", SYSTEM_KAITI)
    found.setdefault("shusong", SYSTEM_KAITI)
    return found


def text_lines(page: fitz.Page):
    return [
        line
        for block in page.get_text("dict")["blocks"]
        if block.get("type") == 0
        for line in block["lines"]
    ]


def line_text(line) -> str:
    return "".join(span["text"] for span in line["spans"])


def find_line(page: fitz.Page, contains: str, occurrence: int = 0):
    matches = [line for line in text_lines(page) if contains in line_text(line)]
    if len(matches) <= occurrence:
        raise RuntimeError(
            f"Page {page.number + 1}: cannot find line containing {contains!r}; found {len(matches)}"
        )
    return matches[occurrence]


def baseline_for_rect(page: fitz.Page, rect: fitz.Rect) -> tuple[float, float]:
    center_y = (rect.y0 + rect.y1) / 2
    candidates = []
    for line in text_lines(page):
        box = fitz.Rect(line["bbox"])
        if box.y0 - 0.5 <= center_y <= box.y1 + 0.5 and box.x1 >= rect.x0 and box.x0 <= rect.x1:
            candidates.append(line)
    if not candidates:
        raise RuntimeError(f"Page {page.number + 1}: no baseline for {rect}")
    line = min(candidates, key=lambda item: abs(fitz.Rect(item["bbox"]).y0 - rect.y0))
    return line["spans"][0]["origin"][1], line["spans"][0]["size"]


class Corrector:
    def __init__(self, doc: fitz.Document, font_paths: dict[str, Path]):
        self.doc = doc
        self.font_paths = font_paths
        self.fonts = {
            key: fitz.Font(fontfile=str(path)) for key, path in font_paths.items()
        }
        self.redactions: dict[int, list[fitz.Rect]] = {}
        self.draws: dict[int, list[dict]] = {}
        self.changed_regions: list[dict] = []

    def add_redaction(self, page_number: int, rect: fitz.Rect):
        rect = fitz.Rect(rect.x0 - 0.12, rect.y0 - 0.12, rect.x1 + 0.12, rect.y1 + 0.12)
        self.redactions.setdefault(page_number, []).append(rect)
        self.changed_regions.append(
            {"page": page_number, "rect": [rect.x0, rect.y0, rect.x1, rect.y1]}
        )

    def add_draw(self, page_number: int, x: float, baseline: float, size: float, runs):
        self.draws.setdefault(page_number, []).append(
            {"x": x, "baseline": baseline, "size": size, "runs": runs}
        )

    def replace(
        self,
        page_number: int,
        old: str,
        new: str,
        level: str,
        font: str = "times",
        occurrence: int | None = None,
    ):
        page = self.doc[page_number - 1]
        rects = page.search_for(old)
        if occurrence is not None:
            if len(rects) <= occurrence:
                raise RuntimeError(
                    f"Page {page_number}: occurrence {occurrence} of {old!r} not found"
                )
            rects = [rects[occurrence]]
        if len(rects) > 1:
            ordered = sorted(rects, key=lambda item: (item.y0, item.x0))
            same_line = max(item.y1 for item in ordered) - min(item.y0 for item in ordered) < 22
            horizontally_joined = all(
                right.x0 - left.x1 < 2.0
                for left, right in zip(sorted(ordered, key=lambda item: item.x0), sorted(ordered, key=lambda item: item.x0)[1:])
            )
            if same_line and horizontally_joined:
                rects = [fitz.Rect(
                    min(item.x0 for item in ordered),
                    min(item.y0 for item in ordered),
                    max(item.x1 for item in ordered),
                    max(item.y1 for item in ordered),
                )]
        if len(rects) != 1:
            raise RuntimeError(
                f"Page {page_number}: expected one occurrence of {old!r}, found {len(rects)}"
            )
        rect = rects[0]
        baseline, size = baseline_for_rect(page, rect)
        self.add_redaction(page_number, rect)
        self.add_draw(page_number, rect.x0, baseline, size, [(new, level, font)])

    def delete(self, page_number: int, old: str):
        page = self.doc[page_number - 1]
        rects = page.search_for(old)
        if not rects:
            raise RuntimeError(f"Page {page_number}: cannot find deletion text {old!r}")
        for rect in rects:
            self.add_redaction(page_number, rect)

    def redraw_line(
        self,
        page_number: int,
        contains: str,
        runs,
        *,
        occurrence: int = 0,
        x: float | None = None,
        size: float | None = None,
        center: bool = False,
    ):
        page = self.doc[page_number - 1]
        line = find_line(page, contains, occurrence)
        rect = fitz.Rect(line["bbox"])
        baseline = line["spans"][0]["origin"][1]
        line_size = size or line["spans"][0]["size"]
        self.add_redaction(page_number, rect)
        if center:
            width = self.runs_width(runs, line_size)
            draw_x = (page.rect.width - width) / 2
        else:
            draw_x = x if x is not None else line["spans"][0]["origin"][0]
        self.add_draw(page_number, draw_x, baseline, line_size, runs)
        width = self.runs_width(runs, line_size)
        if not center and draw_x + width > page.rect.width - 48.0:
            raise RuntimeError(
                f"Page {page_number}: corrected line {contains!r} is too wide "
                f"({draw_x + width:.1f} > {page.rect.width - 48.0:.1f})"
            )

    def add_note(self, page_number: int, x: float, baseline: float, size: float, runs):
        self.add_draw(page_number, x, baseline, size, runs)
        width = self.runs_width(runs, size)
        if x + width > self.doc[page_number - 1].rect.width - 53.0:
            raise RuntimeError(f"Page {page_number}: added note is too wide")
        self.changed_regions.append(
            {"page": page_number, "rect": [x, baseline - size, x + width, baseline + 2]}
        )

    def runs_width(self, runs, size: float) -> float:
        width = 0.0
        for text, _level, forced_font in runs:
            for part, inferred_font in iter_font_runs(text):
                font_key = forced_font or inferred_font
                width += self.fonts[font_key].text_length(part, size)
        return width

    def apply(self):
        pages = sorted(set(self.redactions) | set(self.draws))
        for page_number in pages:
            page = self.doc[page_number - 1]
            for rect in self.redactions.get(page_number, []):
                page.add_redact_annot(rect, fill=False, cross_out=False)
            if self.redactions.get(page_number):
                page.apply_redactions(
                    images=fitz.PDF_REDACT_IMAGE_NONE,
                    graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                    text=fitz.PDF_REDACT_TEXT_REMOVE,
                )
            for command in self.draws.get(page_number, []):
                x = command["x"]
                baseline = command["baseline"]
                size = command["size"]
                for text, level, forced_font in command["runs"]:
                    for part, inferred_font in iter_font_runs(text):
                        font_key = forced_font or inferred_font
                        page.insert_text(
                            (x, baseline),
                            part,
                            fontsize=size,
                            fontname=f"Corr{font_key.title()}",
                            fontfile=str(self.font_paths[font_key]),
                            color=COLORS[level],
                            overlay=True,
                        )
                        x += self.fonts[font_key].text_length(part, size)


def queue_corrections(doc: fitz.Document, font_paths: dict[str, Path]) -> Corrector:
    c = Corrector(doc, font_paths)

    c.redraw_line(
        1,
        "高中英语《新课程标准》3100 词总表（2025 版）",
        [
            ("高中英语《新课程标准》3100 词总表（2025", "black", None),
            ("校正", "black", "kaiti"),
            ("版）", "black", "kaiti"),
        ],
        center=True,
    )
    c.replace(1, "3000", "3100", "black")
    c.replace(1, "l000", "1000", "black")
    c.redraw_line(
        1,
        "a(an) /ə(n)/",
        [
            ("a(an) ", "black", "times"),
            ("/ə, eɪ; ən, æn/", "light", "times"),
            (" art. （非特指的）一（个）；（一类事物中的）任何一个；一；每一；某一", "black", None),
        ],
    )
    c.replace(1, "disability", "inability", "medium")

    c.redraw_line(
        2,
        "ad（=advertisement）",
        [
            ("ad（=advertisement）", "black", None),
            ("/æd/", "light", "times"),
            (" n.广告", "black", None),
        ],
    )
    c.redraw_line(
        3,
        "AI (=artificial intelligence)",
        [
            ("AI ", "black", "times"),
            ("/ˌeɪ ˈaɪ/", "light", "times"),
            (" (=artificial intelligence) [ U ] ( abbr. AI )人工智能", "black", None),
        ],
    )
    c.redraw_line(
        4,
        "addict* /ə'dɪkt/",
        [
            ("addict* ", "black", "times"),
            ("/ˈædɪkt/", "light", "times"),
            (" n.吸毒成瘾的人;瘾君子;对…入迷的人 ", "black", None),
            ("/əˈdɪkt/", "light", "times"),
            (" vt.使沉溺;使上瘾;", "black", None),
        ],
    )
    c.redraw_line(
        4,
        "a.addicted,addictive",
        [("使自己沾染（某些恶习） a.addicted, addictive n.addiction", "black", None)],
    )

    c.redraw_line(
        10,
        "better /betə/",
        [
            ("better ", "black", "times"),
            ("/ˈbetə/", "light", "times"),
            (" adj.较好的;更好的;能力更强的;更熟练的;更合适的;更得体的adv.更好;更愉快;不那么差;", "black", None),
        ],
    )
    c.redraw_line(
        12,
        "behaviour)*",
        [
            ("behaviour(behavior)*", "deep", "times"),
            (" /bɪ'heɪvjə/ n. 行为，举止；（物体等）反应，性能，行为方式，习性", "black", None),
        ],
    )
    c.redraw_line(
        13,
        "BCE (Before the Common Era)",
        [
            ("BCE (Before the Common Era)** ", "black", "times"),
            ("/ˌbiː siː ˈiː/", "light", "times"),
            (" 公元前", "black", None),
        ],
    )
    c.redraw_line(
        13,
        "bias** /ˈbaɪəs/",
        [("bias** /ˈbaɪəs/ n.偏见，成见；偏向；（统计）偏差，偏倚；斜纹；（电子）偏压，偏流", "deep", None)],
    )
    c.redraw_line(
        13,
        "偏压，偏统",
        [("v.使有偏见，使偏心；给……加偏压（或偏流）", "deep", None)],
    )

    c.redraw_line(
        15,
        "can /kæn/ n.",
        [("can /kæn/ n. 金属容器，罐子；modal v. 能，会；能够，可能；可以；究竟能，难", "black", None)],
    )
    c.redraw_line(
        15,
        "道会，到底是",
        [
            ("道会，到底是（can't/cannot；", "black", None),
            ("past: could", "medium", "times"),
            ("）", "black", "kaiti"),
        ],
    )
    c.redraw_line(
        15,
        "car /kaː/ n.",
        [
            ("car ", "black", "times"),
            ("BrE /kɑː(r)/, AmE /kɑːr/", "light", "times"),
            (" n. 小汽车；火车车厢", "black", None),
        ],
    )

    c.redraw_line(
        22,
        "CE（Common Era）",
        [
            ("CE（Common Era）** ", "black", None),
            ("/ˌsiː ˈiː/", "light", "times"),
            (" 公元纪年法：基督诞生后的时期，基督教历法开始计算年份的", "black", None),
        ],
    )
    c.redraw_line(
        22,
        "元”（AD）相对应。",
        [("时期，与“公元”（AD）相对应。", "black", None)],
    )
    c.redraw_line(
        23,
        "circumstance** /'səːkəmstəns/",
        [
            ("circumstance** ", "black", "times"),
            ("/ˈsɜːkəmstəns/", "light", "times"),
            (" n. 情况，情形；境况，状况（尤指经济状况）", "black", None),
        ],
    )
    c.redraw_line(
        26,
        "cruel** /kruːəl/",
        [
            ("cruel** ", "black", "times"),
            ("/ˈkruːəl/", "light", "times"),
            (" adj. 残忍的，残酷的；无情的", "black", None),
        ],
    )

    c.redraw_line(
        30,
        "due to* /djuː/",
        [("due to* /ˈdjuː tə/ prep. 由于；因为", "deep", None)],
    )
    c.redraw_line(
        31,
        "deserve** /dɪ'zəːv/",
        [
            ("deserve** ", "black", "times"),
            ("/dɪˈzɜːv/", "light", "times"),
            (" vt. 应受，值得", "black", None),
        ],
    )
    c.redraw_line(
        34,
        "exam(=examination)",
        [
            ("exam(=examination) ", "black", "times"),
            ("/ɪɡˈzæm/", "light", "times"),
            (" n. 考试；（身体）检查", "black", None),
        ],
    )
    c.replace(36, "v.emphsise/emphasize", "v.emphasise/emphasize", "medium")

    c.replace(43, "v.fluency", "n.fluency adv.fluently", "medium")
    c.redraw_line(
        43,
        "fountain** /'fauntɪn/",
        [
            ("fountain** ", "black", "times"),
            ("/ˈfaʊntən/", "light", "times"),
            (" n. 泉水，喷泉；源泉，来源", "black", None),
        ],
    )
    c.replace(48, "helpless", "unhelpful", "medium")
    c.redraw_line(
        56,
        "laptop /ˈlæplɒp/",
        [
            ("laptop ", "black", "times"),
            ("/ˈlæptɒp/", "light", "times"),
            (" n [C] 笔记本电脑；便携式电脑", "black", None),
        ],
    )
    c.redraw_line(
        57,
        "lightening/ˈlaɪt(ə)nɪŋ/",
        [("lightning /ˈlaɪtnɪŋ/ n. 闪电", "deep", None)],
    )
    c.redraw_line(
        61,
        "meaning /miːnɪŋ/",
        [
            ("meaning ", "black", "times"),
            ("/ˈmiːnɪŋ/", "light", "times"),
            (" n. 意思，含义；意义，重要性", "black", None),
        ],
    )
    c.redraw_line(
        61,
        "meeting /miːtɪŋ/",
        [
            ("meeting ", "black", "times"),
            ("/ˈmiːtɪŋ/", "light", "times"),
            (" n. 会议，集会；会面，会见；运动会", "black", None),
        ],
    )
    c.redraw_line(
        63,
        "mobile phone */'məʊbaɪl/",
        [("mobile phone* /ˌməʊbaɪl ˈfəʊn/ n. 移动电话；手机", "deep", None)],
    )
    c.redraw_line(
        66,
        "not /nɔt/",
        [
            ("not ", "black", "times"),
            ("/nɒt/", "light", "times"),
            (" adv. 不，不是；并非，并不；不太", "black", None),
        ],
    )
    c.redraw_line(
        68,
        "Olympics /ə'lɪmpɪk(s)/",
        [("Olympic /əˈlɪmpɪk/ adj. 奥林匹克的；the Olympics /ði ˈɒlɪmpɪks/ n. 奥林匹克运动会", "deep", None)],
    )
    c.redraw_line(
        69,
        "ought to* /ɔːt/",
        [
            ("ought to* ", "black", "times"),
            ("/ˈɔːt tə/", "light", "times"),
            (" modal v. （常用搭配ought to）应该，应当；该", "black", None),
        ],
    )
    c.redraw_line(
        69,
        "overseas* /ˈəʊvəˈsiːz/",
        [
            ("overseas* ", "black", "times"),
            ("/ˌəʊvəˈsiːz/", "light", "times"),
            (" adv 在国外；向海外adj 海外的；国外的", "black", None),
        ],
    )
    c.redraw_line(
        70,
        "overall** /ˈəʊvərɔːl/",
        [
            ("overall** ", "black", "times"),
            ("/ˌəʊvərˈɔːl/", "light", "times"),
            (" adj 全部的；全面的adv 总共；总的说来", "black", None),
        ],
    )

    c.delete(71, "；空军地勤人员")
    c.redraw_line(
        71,
        "per cent（percent）（/pə'sent/",
        [
            ("per cent", "black", "times"),
            ("（percent）", "medium", None),
            ("/pə'sent/ n.", "black", "times"),
            (", adj. & adv.", "medium", "times"),
            (" 百分之…", "black", None),
        ],
    )
    c.delete(72, "；（Pizza）（意）皮扎（人名）")
    c.redraw_line(
        73,
        "popular /'pɒpjələ/ /pɒp/",
        [("popular /ˈpɒpjələ/ adj. 流行的，受欢迎的；大众化的，通俗的 n.popularity", "deep", None)],
    )
    c.redraw_line(
        73,
        "曲，流行（歌曲等）唱片n.popularity",
        [("pop /pɒp/ n. 流行音乐，流行歌曲；adj. 流行音乐的", "deep", None)],
    )
    c.delete(73, "；<英，非正式>关押期，监禁期")
    c.replace(75, "/pəː'luːʃn/", "/pəˈluːʃn/", "light")
    c.replace(80, "regretable", "regrettable", "medium")
    c.replace(83, "/ˈrɪðəmn/", "/ˈrɪðəm/", "light")
    c.replace(83, "romanism", "romanticism", "medium")
    c.redraw_line(
        93,
        "slightly* /slaɪtli/",
        [
            ("slightly* ", "black", "times"),
            ("/ˈslaɪtli/", "light", "times"),
            (" adv 略微；稍微", "black", None),
        ],
    )
    c.replace(95, "/'sɔːsɪdʒ/", "/ˈsɒsɪdʒ/", "light")

    c.redraw_line(
        97,
        "statistic** /stəˈtɪstɪk/",
        [("statistic** /stəˈtɪstɪk/ n. 统计数字；统计量；statistics /stəˈtɪstɪks/ n. 统计资料；统计学", "deep", None)],
    )
    c.replace(97, "n.subsequence", "adv.subsequently", "medium")
    c.replace(100, "a.tourism", "n.tourism", "medium")
    c.redraw_line(
        103,
        "tournament** /'tɔːnəmənt/",
        [
            ("tournament** ", "black", "times"),
            ("BrE /ˈtʊənəmənt/（也作 /ˈtɔːnəmənt/）；AmE /ˈtɜːrnəmənt/", "light", None),
            (" n. 锦标赛，联赛", "black", None),
        ],
    )
    c.redraw_line(
        107,
        "website /websaɪt/",
        [
            ("website ", "black", "times"),
            ("/ˈwebsaɪt/", "light", "times"),
            (" n. 网站", "black", None),
        ],
    )
    c.redraw_line(
        108,
        "wolf /wʊlf/ n.",
        [("wolf /wʊlf/ n.狼；色狼，色鬼；（喻）残忍凶狠的人；狼音，不谐和音，粗厉音v.狼吞虎咽地吃", "red", None)],
    )
    c.delete(108, "粗厉音v.狼吞虎咽地吃")
    c.delete(109, "n.（Wetland）（德）韦特兰（人名）")
    c.delete(109, "(全写为wireless fidelity)")
    c.replace(109, "dad", "bad", "deep", occurrence=0)
    c.replace(109, "dad", "bad", "deep", occurrence=1)

    return c


def color_int_to_rgb(value: int) -> tuple[float, float, float]:
    return (
        ((value >> 16) & 0xFF) / 255,
        ((value >> 8) & 0xFF) / 255,
        (value & 0xFF) / 255,
    )


def original_font_key(font_name: str) -> str:
    if "Times" in font_name or "CorrTimes" in font_name:
        return "times"
    if "ShuSong" in font_name:
        return "shusong"
    if "STKaiti" in font_name:
        return "stkaiti"
    return "kaiti"


def reflow_first_page(doc: fitz.Document, font_paths: dict[str, Path]):
    page = doc[0]
    fonts = {key: fitz.Font(fontfile=str(path)) for key, path in font_paths.items()}
    movable = []
    for line in text_lines(page):
        baseline = line["spans"][0]["origin"][1]
        if 247.0 <= baseline <= 749.0:
            movable.append(line)

    for line in movable:
        rect = fitz.Rect(line["bbox"])
        page.add_redact_annot(
            fitz.Rect(rect.x0 - 0.12, rect.y0 - 0.12, rect.x1 + 0.12, rect.y1 + 0.12),
            fill=False,
            cross_out=False,
        )
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )

    for line in movable:
        old_baseline = line["spans"][0]["origin"][1]
        if old_baseline < 328.0:
            new_baseline = old_baseline + 40.0
        else:
            new_baseline = 368.009 + (old_baseline - 328.009) * 0.95
        for span in line["spans"]:
            font_key = original_font_key(span["font"])
            text = span["text"]
            page.insert_text(
                (span["origin"][0], new_baseline),
                text,
                fontsize=span["size"],
                fontname=f"Flow{font_key.title()}",
                fontfile=str(font_paths[font_key]),
                color=color_int_to_rgb(span["color"]),
                overlay=True,
            )

    page.insert_text(
        (75.0, 247.970),
        "(4)",
        fontsize=11.5,
        fontname="FlowTimes",
        fontfile=str(font_paths["times"]),
        color=BLACK,
        overlay=True,
    )
    cursor = 94.2
    item_four = "本版系在2025版基础上由LaoShui校正，限于学识，错漏之处在所难免，尚祈读者不吝指正。"
    for run, font_key in iter_font_runs(item_four):
        page.insert_text(
            (cursor, 247.970),
            run,
            fontsize=11.5,
            fontname=f"Flow{font_key.title()}",
            fontfile=str(font_paths[font_key]),
            color=BLACK,
            overlay=True,
        )
        cursor += fonts[font_key].text_length(run, 11.5)


def close_wolf_gap(doc: fitz.Document, font_paths: dict[str, Path]):
    page = doc[107]
    movable = []
    for line in text_lines(page):
        baseline = line["spans"][0]["origin"][1]
        if 607.0 <= baseline <= 760.0:
            movable.append(line)

    for line in movable:
        rect = fitz.Rect(line["bbox"])
        page.add_redact_annot(
            fitz.Rect(rect.x0 - 0.12, rect.y0 - 0.12, rect.x1 + 0.12, rect.y1 + 0.12),
            fill=False,
            cross_out=False,
        )
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )

    for line in movable:
        new_baseline = line["spans"][0]["origin"][1] - 20.041
        for span in line["spans"]:
            font_key = original_font_key(span["font"])
            page.insert_text(
                (span["origin"][0], new_baseline),
                span["text"],
                fontsize=span["size"],
                fontname=f"WolfFlow{font_key.title()}",
                fontfile=str(font_paths[font_key]),
                color=color_int_to_rgb(span["color"]),
                overlay=True,
            )


def shift_page_lines(doc: fitz.Document, page_number: int, font_paths: dict[str, Path], ranges):
    page = doc[page_number - 1]
    movable = []
    for line in text_lines(page):
        baseline = line["spans"][0]["origin"][1]
        for start, end, delta in ranges:
            if start <= baseline < end:
                movable.append((line, delta))
                break

    for line, _delta in movable:
        rect = fitz.Rect(line["bbox"])
        page.add_redact_annot(
            fitz.Rect(rect.x0 - 0.12, rect.y0 - 0.12, rect.x1 + 0.12, rect.y1 + 0.12),
            fill=False,
            cross_out=False,
        )
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )

    for line, delta in movable:
        new_baseline = line["spans"][0]["origin"][1] + delta
        for span in line["spans"]:
            font_key = original_font_key(span["font"])
            page.insert_text(
                (span["origin"][0], new_baseline),
                span["text"],
                fontsize=span["size"],
                fontname=f"GapFlow{font_key.title()}",
                fontfile=str(font_paths[font_key]),
                color=color_int_to_rgb(span["color"]),
                overlay=True,
            )


def remove_source_blank_lines(doc: fitz.Document, font_paths: dict[str, Path]):
    thresholds = {
        4: [607.969],
        5: [748.009],
        12: [388.009],
        13: [328.009],
        20: [228.050],
        22: [148.009],
        30: [228.050],
        34: [588.050],
        35: [648.050],
        41: [228.050],
        42: [268.009],
        45: [588.050],
        46: [247.970],
        49: [708.050],
        50: [348.050],
        52: [208.009, 748.009],
        54: [688.009],
        55: [607.969],
        58: [547.969],
        59: [228.050],
        63: [127.970, 748.009],
        66: [688.009],
        67: [247.970],
        69: [268.009, 748.009],
        75: [168.050],
        76: [568.009],
        79: [568.009, 607.969],
        82: [388.009],
        83: [427.969],
        92: [328.009],
        94: [667.969],
        101: [708.050],
        102: [508.009],
        104: [388.009, 588.050],
        105: [528.050, 667.969],
        109: [408.050, 568.009],
        111: [127.970, 307.970],
    }

    for page_number, page_thresholds in thresholds.items():
        page = doc[page_number - 1]
        movable = []
        for line in text_lines(page):
            baseline = line["spans"][0]["origin"][1]
            closed_gaps = sum(baseline >= threshold - 0.2 for threshold in page_thresholds)
            if closed_gaps and baseline < 760.0:
                movable.append((line, -20.0 * closed_gaps))

        for line, _delta in movable:
            rect = fitz.Rect(line["bbox"])
            page.add_redact_annot(
                fitz.Rect(rect.x0 - 0.12, rect.y0 - 0.12, rect.x1 + 0.12, rect.y1 + 0.12),
                fill=False,
                cross_out=False,
            )
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )

        for line, delta in movable:
            new_baseline = line["spans"][0]["origin"][1] + delta
            for span in line["spans"]:
                font_key = original_font_key(span["font"])
                page.insert_text(
                    (span["origin"][0], new_baseline),
                    span["text"],
                    fontsize=span["size"],
                    fontname=f"BlankFlow{font_key.title()}",
                    fontfile=str(font_paths[font_key]),
                    color=color_int_to_rgb(span["color"]),
                    overlay=True,
                )


def build_corrected_pdf():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(SOURCE)
    if doc.page_count != 111:
        raise RuntimeError(f"Expected 111 source pages, got {doc.page_count}")
    font_paths = extract_original_fonts(doc)
    corrector = queue_corrections(doc, font_paths)
    corrector.apply()
    reflow_first_page(doc, font_paths)
    close_wolf_gap(doc, font_paths)
    remove_source_blank_lines(doc, font_paths)
    metadata = dict(doc.metadata)
    metadata.update(
        {
            "title": "2025届高考英语《新课程标准》3100词总表（2025校正版）",
            "author": "原编写：胡悠；校正：LaoShui",
            "subject": "高考英语新课程标准3100词校正版",
        }
    )
    doc.set_metadata(metadata)
    doc.save(CORRECTED, garbage=4, deflate=True, clean=True)
    doc.close()
    regions = [item for item in corrector.changed_regions if item["page"] != 1]
    regions.extend(
        [
            {"page": 1, "rect": [75.0, 88.0, 525.0, 114.0]},
            {"page": 1, "rect": [54.0, 154.0, 545.0, 273.0]},
            {"page": 1, "rect": [54.0, 352.0, 545.0, 390.0]},
        ]
    )
    return regions


def build_details_pdf():
    pdfmetrics.registerFont(TTFont("Deng", str(DETAIL_REGULAR)))
    pdfmetrics.registerFont(TTFont("DengBold", str(DETAIL_BOLD)))
    pdfmetrics.registerFont(TTFont("DetailTimes", str(SYSTEM_TIMES)))

    def mixed_markup(text: str) -> str:
        parts = []
        for run, font_kind in iter_font_runs(text):
            safe = escape(run)
            if font_kind == "times":
                parts.append(f'<font name="DetailTimes">{safe}</font>')
            else:
                parts.append(safe)
        return "".join(parts)

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TitleCN",
        parent=styles["Title"],
        fontName="DengBold",
        fontSize=20,
        leading=28,
        textColor=colors.HexColor("#17324D"),
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    subtitle = ParagraphStyle(
        "SubtitleCN",
        parent=styles["Normal"],
        fontName="Deng",
        fontSize=9.5,
        leading=15,
        textColor=colors.HexColor("#52606D"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    body = ParagraphStyle(
        "BodyCN",
        parent=styles["Normal"],
        fontName="Deng",
        fontSize=9.2,
        leading=14,
        textColor=colors.HexColor("#1F2933"),
        alignment=TA_LEFT,
    )
    small = ParagraphStyle(
        "SmallCN",
        parent=body,
        fontSize=8.3,
        leading=12.5,
        textColor=colors.HexColor("#52606D"),
    )
    item_head = ParagraphStyle(
        "ItemHeadCN",
        parent=body,
        fontName="DengBold",
        fontSize=10.2,
        leading=15,
        textColor=colors.HexColor("#17324D"),
        spaceAfter=3,
    )

    class NumberedCanvas(pdf_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            page_count = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self.setFont("Deng", 8)
                self.setFillColor(colors.HexColor("#6B7785"))
                self.drawRightString(
                    A4[0] - 18 * mm,
                    9 * mm,
                    f"第 {self._pageNumber} 页（共 {page_count} 页）",
                )
                super().showPage()
            super().save()

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9E2EC"))
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
        canvas.setFont("Deng", 8)
        canvas.setFillColor(colors.HexColor("#6B7785"))
        canvas.drawString(18 * mm, 9 * mm, "2025校正版校正明细 · LaoShui")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(DETAILS),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=20 * mm,
        title="2025届高考英语3100词总表校正明细",
        author="LaoShui",
    )
    story = [
        Paragraph("2025届高考英语《新课程标准》3100词总表", title),
        Paragraph("2025校正版 · 校正内容明细", title),
        Paragraph(
            f"共列出 {len(DETAIL_CORRECTIONS)} 项正文词条修改。页码均指原2025版PDF页码；删除项以“删除”表示。",
            subtitle,
        ),
    ]

    legend = Table(
        [
            [
                Paragraph('<font color="#4A90D9">● 浅蓝</font>：音标、重音等轻微修正', body),
                Paragraph('<font color="#1F6FB2">● 中蓝</font>：派生、词性、用法及删除项', body),
                Paragraph('<font color="#0B4F9C">● 深蓝</font>：词头、整条词义或数量错误', body),
            ]
        ],
        colWidths=[(A4[0] - 36 * mm) / 3] * 3,
    )
    legend.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F7FA")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E2EC")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9E2EC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([legend, Spacer(1, 10)])

    for index, item in enumerate(DETAIL_CORRECTIONS, 1):
        color = {
            "light": "#4A90D9",
            "medium": "#1F6FB2",
            "deep": "#0B4F9C",
        }[item.level]
        header = (
            f'<font color="{color}">●</font> {index:02d}　原第 {item.page} 页　'
            f'{escape(item.entry)}　<span color="#52606D">{escape(item.kind)}</span>'
        )
        block = [
            Paragraph(header, item_head),
            Paragraph(f"<b>原：</b>{mixed_markup(item.original)}", body),
            Paragraph(f'<b>正：</b><font color="{color}">{mixed_markup(item.corrected)}</font>', body),
            Paragraph(f"说明：{mixed_markup(item.note)}", small),
            Spacer(1, 5),
            Table(
                [[""]],
                colWidths=[A4[0] - 36 * mm],
                rowHeights=[0.4],
                style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E6ECF1"))]),
            ),
            Spacer(1, 7),
        ]
        story.append(KeepTogether(block))

    story.extend(
        [
            PageBreak(),
            Paragraph("校审边界说明", title),
            Paragraph(
                "nearby、mature存在词典或口音变体，未作为硬错修改；substantial的罕见名词义与scare下的scaring虽不适合作为核心记忆项，但并非明确事实错误，本校正版保持原文。",
                body,
            ),
            Spacer(1, 8),
            Paragraph(
                "本次同时删除pizza、wetland的专名义，wolf的过时冒犯性俚语义，以及penguin、porridge中与高考核心词义无关的低频行业/俚语义。",
                body,
            ),
            Spacer(1, 8),
            Paragraph(
                "上述取舍，皆属编者一孔之见，是否允当，惟待读者明鉴。",
                body,
            ),
        ]
    )
    document.build(
        story,
        onFirstPage=on_page,
        onLaterPages=on_page,
        canvasmaker=NumberedCanvas,
    )


def main():
    regions = build_corrected_pdf()
    build_details_pdf()
    regions_path = TEMP_DIR / "corrected_regions.txt"
    regions_path.write_text(
        "\n".join(
            f"{item['page']}\t" + ",".join(f"{value:.3f}" for value in item["rect"])
            for item in regions
        ),
        encoding="utf-8",
    )
    print(f"corrected={CORRECTED}")
    print(f"details={DETAILS}")
    print(f"corrections={len(CORRECTIONS)}")
    print(f"changed_regions={len(regions)}")


if __name__ == "__main__":
    main()

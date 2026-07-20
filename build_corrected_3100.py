from __future__ import annotations

from dataclasses import dataclass
import html
from html import escape
from pathlib import Path
import re
import sys
import unicodedata


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

from make_shuffled_3100 import LETTER_HEADING, is_entry_start


SOURCE = ROOT / "原版" / "2025届高考英语《新课程标准》3100词总表.pdf"
AUTHORITY_PDF = ROOT / "普通高中英语课程标准日常修订版（2017年版2025年修订）.pdf"
OUTPUT_DIR = ROOT / "校正版"
DIFF_2025 = OUTPUT_DIR / "2025届高考英语《新课程标准》3100词总表（2025差异版）.pdf"
FINAL_2026 = OUTPUT_DIR / "2025届高考英语《新课程标准》3100词总表（2026版）.pdf"
# Keep this alias for callers that still import CORRECTED.
CORRECTED = FINAL_2026
DETAILS = OUTPUT_DIR / "2025届高考英语3100词总表_校正明细.pdf"
REPORT = OUTPUT_DIR / "2025届高考英语3100词总表审校报告.md"
TEMP_DIR = ROOT / "tmp" / "pdfs"
FONT_DIR = TEMP_DIR / "fonts"
BASE_CORRECTED = TEMP_DIR / "2025差异版_定点校正中间稿.pdf"

SYSTEM_TIMES = Path(r"C:\Windows\Fonts\times.ttf")
SYSTEM_TIMES_BOLD = Path(r"C:\Windows\Fonts\timesbd.ttf")
SYSTEM_KAITI = Path(r"C:\Windows\Fonts\STKAITI.TTF")
SYSTEM_SONG = Path(r"C:\Windows\Fonts\STSONG.TTF")
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

BLACK_HEX = "#000000"
LIGHT_BLUE_HEX = "#4A90D9"
MEDIUM_BLUE_HEX = "#1F6FB2"
DEEP_BLUE_HEX = "#0B4F9C"


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
    Correction("F001", 1, "标题", "版本", "2025版", "2025差异版", "deep", "按差异版要求更新标题。"),
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
    Correction("C010", 43, "fountain", "音标", "/'fauntɪn/", "/ˈfaʊntən/", "light", "修正双元音，并经多套词典交叉核对。"),
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

BASE_DETAIL_CORRECTIONS = [item for item in CORRECTIONS if not item.code.startswith("F")]

SYSTEM_CORRECTIONS = [
    Correction(
        "S001",
        0,
        "全表",
        "字母排序",
        "同一字母、同一星级组内检测到211处相邻逆序，且存在整批词条错位。",
        "按规范化词头严格升序排列；星号只标识课程层级，不参与排序。",
        "deep",
        "修正accept、argue、abroad、calendar、damage等代表性错位，并对3090个真实词条统一重排。",
    ),
    Correction(
        "S002",
        0,
        "全表音标",
        "IPA符号统一",
        "部分音标混用ASCII撇号/冒号、西里尔ә或缺失字符，另有重音与长音符号被空格替代。",
        "统一使用IPA ə、ˈ、ˌ、ː等符号；对明确损坏的音标逐条覆盖。",
        "light",
        "只修正明确的编码、OCR或符号体例问题；词典间可接受的口音差异不批量改写。",
    ),
    Correction(
        "S003",
        0,
        "全表词性",
        "词性缩写统一",
        "正文混用a.、ad.与adj.、adv.。",
        "统一为adj.、adv.；其余n.、v.、vt.、vi.等保留规范点号。",
        "medium",
        "避免把a.、ad.误读为词条内容，并保持高中词表常见缩写体例。",
    ),
    Correction(
        "S004",
        0,
        "全表分隔符",
        "标点统一",
        "71处使用异体分号;（U+037E），外观近似分号但编码不同。",
        "统一替换为中文分号；。",
        "medium",
        "消除复制、检索与网页导出时的编码歧义。",
    ),
]


IPA_SPECIAL = set("əәɪʊɑɒɔʌæɛɜɚɝθðʃʒŋɡɹɾˈˌːʤʧ\x00")
POS_RE = re.compile(
    r"(?<![A-Za-z])(?:modal\s+v|aux(?:iliary)?\s+v|art|adj|adv|prep|pron|conj|num|det|int|abbr|vt|vi|pl|n|v|ad|a)\.",
    re.I,
)


IPA_OVERRIDES = {
    "bacteria": "/bækˈtɪəriə/",
    "charm": "/tʃɑːm/",
    "childhood": "/ˈtʃaɪldhʊd/",
    "collaborate": "/kəˈlæbəreɪt/",
    "command": "/kəˈmɑːnd/",
    "casual": "/ˈkæʒuəl/",
    "cautious": "/ˈkɔːʃəs/",
    "ceremony": "/ˈserəməni/",
    "confucianism": "/kənˈfjuːʃənɪzəm/",
    "economy": "/ɪˈkɒnəmi/",
    "fertile": "/ˈfɜːtaɪl/",
    "fascinating": "/ˈfæsɪneɪtɪŋ/",
    "gesture": "/ˈdʒestʃə(r)/",
    "giant": "/ˈdʒaɪənt/",
    "gene": "/dʒiːn/",
    "glance": "/ɡlɑːns/",
    "graceful": "/ˈɡreɪsfl/",
    "headline": "/ˈhedlaɪn/",
    "hybrid": "/ˈhaɪbrɪd/",
    "ingredient": "/ɪnˈɡriːdiənt/",
    "invest": "/ɪnˈvest/",
    "irrigation": "/ˌɪrɪˈɡeɪʃn/",
    "keen": "/kiːn/",
    "kung fu": "/ˌkʌŋˈfuː/",
    "lean": "/liːn/",
    "lifestyle": "/ˈlaɪfstaɪl/",
    "leap": "/liːp/",
    "legend": "/ˈledʒənd/",
    "neutral": "/ˈnjuːtrəl/",
    "obey": "/əˈbeɪ/",
    "offend": "/əˈfend/",
    "obstacle": "/ˈɒbstəkl/",
    "pagoda": "/pəˈɡəʊdə/",
    "patriotism": "/ˈpeɪtriətɪzəm/",
    "portrait": "/ˈpɔːtreɪt/",
    "relieve": "/rɪˈliːv/",
    "religion": "/rɪˈlɪdʒən/",
    "reinforce": "/ˌriːɪnˈfɔːs/",
    "rejuvenate": "/rɪˈdʒuːvəneɪt/",
}


MEANING_REPLACEMENTS = {
    "arctic": "adj. 北极的 n. the Arctic 北极；北极地区（圈）",
    "bee": "n. 蜜蜂",
    "bully": "n. 恃强凌弱者 v. 恐吓；欺凌；胁迫",
    "butterfly": "n. 蝴蝶",
    "bug": "n. 虫子；小病；（计算机程序等的）故障、漏洞 v. 烦扰；秘密安装窃听器",
    "casual": "adj. 随意的；非正式的；漫不经心的；偶然的；临时的",
    "doll": "n. 玩偶；洋娃娃",
    "drone": "n. 无人机；雄蜂；嗡嗡声 v. 嗡嗡响；懒洋洋地说",
    "fool": "n. 傻瓜 v. 愚弄；欺骗 adj. 傻的",
    "float": "v. （使）漂浮；（使）漂流；提出（想法或计划） n. 浮标",
    "flame": "n. 火焰 v. 燃烧；（脸）变红",
    "frame": "n. 框架；结构；画面 v. 给……装框；陷害",
    "fulfil": "v. 履行；实现；完成",
    "god": "n. 神；上帝、天主或真主；偶像",
    "humour（humor）": "n. 幽默；诙谐",
    "heritage": "n. 遗产；传统；文化遗产",
    "highway": "n. 公路；大道；交通要道",
    "horror": "n. 恐怖；惊恐；恐怖的事物、故事或电影",
    "ink": "n. 墨水 v. 用墨水书写；签署",
    "invest": "v. 投资；投入（时间或精力）",
    "keen": "adj. 热衷的；渴望的；强烈的；敏锐的",
    "lip": "n. 嘴唇；边缘",
    "mine": "pron. 我的 n. 矿山；矿井；知识等的宝库 v. 开采；采矿",
    "obey": "v. 服从；遵守",
    "offend": "v. 得罪；冒犯；令人不适；违反",
    "orchestra": "n. 管弦乐队",
    "packet": "n. 小包；小袋；数据包",
    "porridge": "n. 粥；麦片粥",
    "princess": "n. 公主；王妃",
    "pants": "n. 裤子（美式）；内裤（英式）",
    "pile": "n. 堆；大量 v. 堆积；聚集",
    "principal": "adj. 最重要的；首要的 n. 校长",
    "religion": "n. 宗教；宗教信仰",
    "romantic": "adj. 浪漫的；传奇式的；浪漫主义的；不切实际的；虚构的 n. romance, romanticism",
    "rough": "adj. 粗糙的；崎岖的；粗略的；艰难的；恶劣的；粗暴的",
    "sore": "adj. 疼痛的；酸痛的 n. 疮；痛处",
    "sauce": "n. 酱汁；调味汁",
    "saucer": "n. 茶碟；茶托",
    "scale": "n. 规模；程度；秤；天平；比例；比例尺；鳞片 v. 攀登；刮鳞；按比例缩放",
    "split": "v. （使）分裂；（使）分开；分担；分摊 n. 裂缝；分裂",
    "steady": "adj. 稳定的；稳固的；持续的 v. 使稳定",
    "shell": "n. 壳；炮弹 v. 剥壳；炮击",
    "souvenir": "n. 纪念品；纪念物",
    "tap": "n. 水龙头；轻拍 v. 轻拍；开发、利用（资源）",
    "union": "n. 协会；工会；联盟；联邦；联合",
}


HEADWORD_RENAMES = {
    "a. m.": "a.m.",
    "disk=disc": "disc (disk)",
    "humorous": "humourous",
    "practice": "practise (practice)",
    "television(tv)": "TV (=television)",
    "toward(s)": "towards (toward)",
}


# Entries required by the Ministry of Education 2025-revised Appendix 2 but
# not independently listed in the source PDF.  Meanings retain high-frequency
# Gaokao senses plus necessary familiar-word meanings only.
SUPPLEMENTAL_ENTRIES = [
    ("application", 1, "/ˌæplɪˈkeɪʃən/", "n. 应用；运用；申请"),
    ("dedicate", 2, "/ˈdedɪkeɪt/", "v. 致力于；献身于"),
    ("minute", 0, "/ˈmɪnɪt/", "n. 分钟；一会儿；片刻"),
    ("operate", 0, "/ˈɒpəreɪt/", "v. 操作；使运行；运转；经营；动手术"),
    ("rhythm", 1, "/ˈrɪðəm/", "n. 节奏；韵律；节拍"),
    ("sausage", 2, "/ˈsɒsɪdʒ/", "n. 香肠；腊肠"),
    ("slave", 1, "/sleɪv/", "n. 奴隶；苦工 v. 苦干；做苦工"),
    ("teamwork", 0, "/ˈtiːmwɜːk/", "n. 团队合作；协作"),
    ("teenage", 0, "/ˈtiːneɪdʒ/", "adj. 十几岁的；青少年的"),
    ("tent", 0, "/tent/", "n. 帐篷"),
    ("theirs", 0, "/ðeəz/", "pron. 他们的；她们的；它们的（名词性物主代词）"),
    ("throat", 0, "/θrəʊt/", "n. 喉咙；咽喉"),
    ("together", 0, "/təˈɡeðə(r)/", "adv. 一起；共同"),
    ("tomb", 1, "/tuːm/", "n. 坟墓；陵墓"),
    (
        "transfer",
        1,
        "/trænsˈfɜː(r)/",
        "v. 转移；调动；转让；/ˈtrænsfɜː(r)/ n. 转移；转让；调动；转学；换乘",
    ),
    ("transition", 2, "/trænˈzɪʃn/", "n. 过渡；转变；变迁"),
    ("tropical", 2, "/ˈtrɒpɪkəl/", "adj. 热带的"),
    ("tunnel", 1, "/ˈtʌnl/", "n. 隧道；地道 v. 挖隧道"),
]


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


@dataclass
class ColoredChar:
    char: str
    color: str


@dataclass
class ColoredRow:
    page: int
    y: float
    chars: list[ColoredChar]

    @property
    def text(self) -> str:
        return "".join(item.char for item in self.chars)


@dataclass
class ColoredEntry:
    source_page: int
    original_index: int
    headword: str
    level: int
    letter: str
    sort_key: str
    chars: list[ColoredChar]

    @property
    def text(self) -> str:
        return "".join(item.char for item in self.chars)


def color_hex(value: int) -> str:
    return f"#{value & 0xFFFFFF:06X}"


def visual_rows(pdf_path: Path) -> list[ColoredRow]:
    rows: list[ColoredRow] = []
    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            pieces = []
            for block in page.get_text("dict", sort=True)["blocks"]:
                for line in block.get("lines", []):
                    y = float(line["bbox"][1])
                    if not 60.0 < y < 765.0:
                        continue
                    for span in line["spans"]:
                        text = span["text"]
                        if text:
                            pieces.append(
                                (
                                    y,
                                    float(span["bbox"][0]),
                                    float(span["bbox"][2]),
                                    text,
                                    color_hex(int(span["color"])),
                                )
                            )

            grouped = []
            for y, x0, x1, text, color in sorted(
                pieces, key=lambda item: (item[0], item[1])
            ):
                if grouped and abs(grouped[-1][0] - y) < 1.0:
                    grouped[-1][1].append((x0, x1, text, color))
                else:
                    grouped.append((y, [(x0, x1, text, color)]))

            for y, parts in grouped:
                chars = []
                previous_x1 = None
                for x0, x1, text, color in sorted(parts, key=lambda item: item[0]):
                    if (
                        previous_x1 is not None
                        and x0 - previous_x1 > 1.5
                        and chars
                        and not chars[-1].char.isspace()
                        and not text[:1].isspace()
                    ):
                        chars.append(ColoredChar(" ", BLACK_HEX))
                    chars.extend(ColoredChar(char, color) for char in text)
                    previous_x1 = x1
                if any(not item.char.isspace() for item in chars):
                    rows.append(ColoredRow(page_index + 1, y, chars))
    return rows


def find_ipa_ranges(text: str) -> list[tuple[int, int]]:
    positions = [index for index, char in enumerate(text) if char == "/"]
    output = []
    position_index = 0
    while position_index < len(positions):
        start = positions[position_index]
        found = None
        for end in positions[position_index + 1 :]:
            content = text[start + 1 : end]
            if "*" in content or "=" in content:
                continue
            if any(char in IPA_SPECIAL for char in content) or re.fullmatch(
                r"[A-Za-z()ː'ˈˌ., -]{1,40}", content.strip()
            ):
                found = end + 1
                break
        if found is not None:
            output.append((start, found))
            position_index = next(
                (index for index, value in enumerate(positions) if value >= found),
                len(positions),
            )
        else:
            position_index += 1
    return output


def parse_headword(text: str) -> tuple[str, int]:
    ranges = find_ipa_ranges(text)
    if ranges:
        prefix = text[: ranges[0][0]]
    elif text.startswith("survey ["):
        prefix = "survey"
    else:
        pos = POS_RE.search(text)
        prefix = text[: pos.start()] if pos else text
    groups = re.findall(r"\*+", prefix)
    level = max((len(group) for group in groups), default=0)
    prefix = re.sub(r"\*+", "", prefix)
    prefix = re.sub(r"\b(?:BrE|AmE)\b\s*$", "", prefix, flags=re.I)
    return re.sub(r"\s+", " ", prefix).strip(" ,，；;"), level


def normalized_sort_key(headword: str) -> str:
    value = unicodedata.normalize("NFKD", headword).casefold()
    value = re.split(r"[（(]", value, maxsplit=1)[0]
    return re.sub(r"[^a-z0-9]+", "", value)


def coverage_key(headword: str) -> str:
    value = unicodedata.normalize("NFKD", headword).casefold()
    value = re.split(r"[/（(]", value, maxsplit=1)[0]
    return re.sub(r"[^a-z0-9]+", "", value)


def authority_word_lines() -> list[str]:
    if not AUTHORITY_PDF.exists():
        raise FileNotFoundError(AUTHORITY_PDF)
    words: list[str] = []
    started = False
    with fitz.open(AUTHORITY_PDF) as document:
        for page_number in range(76, 133):
            for raw in document[page_number - 1].get_text().splitlines():
                text = " ".join(raw.split())
                if not started:
                    if text == "A":
                        started = True
                    continue
                if text in {
                    "普通高中英语课程标准（2017年版2025年修订）",
                    "续表",
                }:
                    continue
                if re.match(r"^│ 附录 │", text) or re.fullmatch(r"\d+", text):
                    continue
                if re.fullmatch(r"[A-Z]", text):
                    continue
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9 .'/()=*-]*", text):
                    words.append(text)
    if len(words) != 3093:
        raise RuntimeError(f"Authority Appendix 2 extraction expected 3093 lines, got {len(words)}")
    return words


def authority_levels() -> dict[str, list[tuple[str, int]]]:
    output: dict[str, list[tuple[str, int]]] = {}
    for word in authority_word_lines():
        match = re.search(r"(\*+)$", word)
        level = len(match.group(1)) if match else 0
        headword = re.sub(r"\*+$", "", word).strip()
        output.setdefault(coverage_key(headword), []).append((headword, level))
    return output


def apply_headword_renames(
    entries: list[ColoredEntry],
) -> list[tuple[ColoredEntry, str, str]]:
    changed: list[tuple[ColoredEntry, str, str]] = []
    for entry in entries:
        replacement = HEADWORD_RENAMES.get(entry.headword.casefold())
        if not replacement or replacement == entry.headword:
            continue
        original = entry.headword
        start = 0
        end = len(entry.headword)
        replace_range(entry.chars, start, end, replacement, DEEP_BLUE_HEX)
        entry.headword = replacement
        entry.sort_key = normalized_sort_key(replacement)
        entry.letter = next((char.upper() for char in entry.sort_key if char.isalpha()), "#")
        changed.append((entry, original, replacement))
    return changed


def sync_authority_levels(
    entries: list[ColoredEntry],
) -> list[tuple[ColoredEntry, int, int]]:
    levels = authority_levels()
    changed: list[tuple[ColoredEntry, int, int]] = []
    for entry in entries:
        candidates = levels.get(coverage_key(entry.headword), [])
        if not candidates:
            continue
        if len(candidates) == 1:
            target = candidates[0][1]
        else:
            exact = [
                level
                for official, level in candidates
                if official.split("/", 1)[0].split("(", 1)[0].strip() == entry.headword
            ]
            if not exact:
                exact = [
                    level
                    for official, level in candidates
                    if official[:1].isupper() == entry.headword[:1].isupper()
                ]
            if len(exact) != 1:
                continue
            target = exact[0]
        if target == entry.level:
            continue
        original = entry.level
        star_start = len(entry.headword)
        star_end = star_start
        while star_end < len(entry.chars) and entry.chars[star_end].char == "*":
            star_end += 1
        replace_range(entry.chars, star_start, star_end, "*" * target, DEEP_BLUE_HEX)
        entry.level = target
        changed.append((entry, original, target))
    return changed


def supplemental_entries(existing: list[ColoredEntry]) -> list[ColoredEntry]:
    existing_keys = {normalized_sort_key(entry.headword) for entry in existing}
    output: list[ColoredEntry] = []
    next_index = max((entry.original_index for entry in existing), default=0) + 1
    for headword, level, pronunciation, meaning in SUPPLEMENTAL_ENTRIES:
        if normalized_sort_key(headword) in existing_keys:
            continue
        text = headword + ("*" * level) + " " + pronunciation + " " + meaning
        chars = [ColoredChar(char, DEEP_BLUE_HEX) for char in text]
        key = normalized_sort_key(headword)
        output.append(
            ColoredEntry(
                0,
                next_index,
                headword,
                level,
                next((char.upper() for char in key if char.isalpha()), "#"),
                key,
                chars,
            )
        )
        existing_keys.add(key)
        next_index += 1
    return output


def authority_missing(entries: list[ColoredEntry]) -> list[str]:
    current = {coverage_key(entry.headword) for entry in entries}
    missing = []
    for word in authority_word_lines():
        headword = re.sub(r"\*+$", "", word).strip()
        key = coverage_key(headword)
        if key not in current:
            missing.append(word)
    return missing


def make_authority_corrections(
    renamed: list[tuple[ColoredEntry, str, str]],
    levels: list[tuple[ColoredEntry, int, int]],
    supplements: list[ColoredEntry],
) -> list[Correction]:
    corrections: list[Correction] = []
    for index, (entry, original, corrected) in enumerate(renamed, 1):
        corrections.append(
            Correction(
                f"A{index:03d}",
                entry.source_page,
                corrected,
                "教育部课标词头统一",
                original,
                corrected,
                "deep",
                "按《普通高中英语课程标准（2017年版2025年修订）》附录2采用英式主词头及官方写法。",
            )
        )
    offset = len(corrections)
    for index, (entry, original, corrected) in enumerate(levels, 1):
        labels = {0: "无星号", 1: "*", 2: "**"}
        corrections.append(
            Correction(
                f"A{offset + index:03d}",
                entry.source_page,
                entry.headword,
                "教育部课标星级统一",
                labels[original],
                labels[corrected],
                "deep",
                "按教育部2025修订课标附录2修正课程层级标记。",
            )
        )
    offset = len(corrections)
    for index, entry in enumerate(supplements, 1):
        corrections.append(
            Correction(
                f"A{offset + index:03d}",
                0,
                entry.headword,
                "教育部课标缺项补充",
                "原版未独立列出，或错误并入相邻词条。",
                entry.text,
                "deep",
                "依据教育部2025修订课标附录2补入，并结合多方资料核对音标和高频释义。",
            )
        )
    return corrections


def join_rows(rows: list[ColoredRow]) -> list[ColoredChar]:
    output = []
    for row in rows:
        row_chars = list(row.chars)
        if output and row_chars:
            left = output[-1].char
            right = row_chars[0].char
            if not left.isspace() and not right.isspace():
                if not (is_cjk(left) and is_cjk(right)):
                    output.append(ColoredChar(" ", BLACK_HEX))
        output.extend(row_chars)
    return output


def extract_colored_entries(pdf_path: Path) -> list[ColoredEntry]:
    entries = []
    current_rows = []
    original_index = 0
    for row in visual_rows(pdf_path):
        text = row.text.strip()
        if LETTER_HEADING.fullmatch(text):
            continue
        if is_entry_start(text):
            if current_rows:
                original_index += 1
                chars = join_rows(current_rows)
                headword, level = parse_headword("".join(item.char for item in chars))
                key = normalized_sort_key(headword)
                letter = next((char.upper() for char in key if char.isalpha()), "#")
                entries.append(
                    ColoredEntry(
                        current_rows[0].page,
                        original_index,
                        headword,
                        level,
                        letter,
                        key,
                        chars,
                    )
                )
            current_rows = [row]
        elif current_rows:
            current_rows.append(row)
    if current_rows:
        original_index += 1
        chars = join_rows(current_rows)
        headword, level = parse_headword("".join(item.char for item in chars))
        key = normalized_sort_key(headword)
        letter = next((char.upper() for char in key if char.isalpha()), "#")
        entries.append(
            ColoredEntry(current_rows[0].page, original_index, headword, level, letter, key, chars)
        )
    return entries


def replace_range(
    chars: list[ColoredChar], start: int, end: int, text: str, color: str
) -> None:
    chars[start:end] = [ColoredChar(char, color) for char in text]


def normalize_symbols(chars: list[ColoredChar]) -> dict[str, int]:
    counts = {"ipaSymbols": 0, "semicolons": 0, "pos": 0}
    text = "".join(item.char for item in chars)
    ipa_positions = set()
    for start, end in find_ipa_ranges(text):
        ipa_positions.update(range(start + 1, end - 1))
    for index, item in enumerate(chars):
        if index in ipa_positions:
            mapped = {"ә": "ə", "'": "ˈ", ":": "ː"}.get(item.char)
            if mapped and item.char != mapped:
                item.char = mapped
                item.color = LIGHT_BLUE_HEX
                counts["ipaSymbols"] += 1
        if item.char == ";":
            item.char = "；"
            item.color = MEDIUM_BLUE_HEX
            counts["semicolons"] += 1

    text = "".join(item.char for item in chars)
    replacements = []
    for match in re.finditer(r"(?<![A-Za-z])ad\.", text, flags=re.I):
        replacements.append((match.start(), match.end(), "adv."))
    for match in re.finditer(r"(?<![A-Za-z])a\.", text, flags=re.I):
        if match.start() == 0 and re.match(r"a\.\s*m\.", text, flags=re.I):
            continue
        replacements.append((match.start(), match.end(), "adj."))
    for start, end, value in sorted(replacements, reverse=True):
        replace_range(chars, start, end, value, MEDIUM_BLUE_HEX)
        counts["pos"] += 1
    return counts


def apply_ipa_override(entry: ColoredEntry) -> bool:
    replacement = IPA_OVERRIDES.get(entry.headword.casefold())
    if not replacement:
        return False
    ranges = find_ipa_ranges(entry.text)
    if not ranges:
        return False
    if entry.text[ranges[0][0] : ranges[0][1]] == replacement:
        return False
    replace_range(entry.chars, ranges[0][0], ranges[0][1], replacement, LIGHT_BLUE_HEX)
    return True


def apply_meaning_replacement(entry: ColoredEntry) -> bool:
    replacement = MEANING_REPLACEMENTS.get(entry.headword.casefold())
    if not replacement:
        return False
    ranges = find_ipa_ranges(entry.text)
    pronunciation = "；".join(entry.text[start:end] for start, end in ranges)
    headword = entry.headword + ("*" * entry.level)
    chars = [ColoredChar(char, BLACK_HEX) for char in headword]
    if pronunciation:
        chars.append(ColoredChar(" ", BLACK_HEX))
        chars.extend(ColoredChar(char, LIGHT_BLUE_HEX) for char in pronunciation)
    chars.append(ColoredChar(" ", BLACK_HEX))
    chars.extend(ColoredChar(char, MEDIUM_BLUE_HEX) for char in replacement)
    entry.chars = chars
    return True


def make_second_round_corrections(entries: list[ColoredEntry]) -> list[Correction]:
    corrections = list(SYSTEM_CORRECTIONS)
    for entry in entries:
        key = entry.headword.casefold()
        replacement = IPA_OVERRIDES.get(key)
        if replacement:
            ranges = find_ipa_ranges(entry.text)
            original = entry.text[ranges[0][0] : ranges[0][1]] if ranges else "音标损坏或未识别"
            if original != replacement:
                corrections.append(
                    Correction(
                        f"I{len([c for c in corrections if c.code.startswith('I')]) + 1:03d}",
                        entry.source_page,
                        entry.headword,
                        "音标修正",
                        original.replace("\x00", "[缺失字符]"),
                        replacement,
                        "light",
                        "结合多方资料及IPA结构核对，修复缺失的重音、长音或音素。",
                    )
                )
        meaning = MEANING_REPLACEMENTS.get(key)
        if meaning:
            corrections.append(
                Correction(
                    f"M{len([c for c in corrections if c.code.startswith('M')]) + 1:03d}",
                    entry.source_page,
                    entry.headword,
                    "高考释义精简",
                    "原词条混入低频、俚语、专名或全量词典义项。",
                    meaning,
                    "medium",
                    "保留高考高频核心义、必要熟词生义和常见现代用法，删除会增加无效记忆负担的边缘义。",
                )
            )
    return corrections


def transform_entries(entries: list[ColoredEntry]) -> dict[str, int]:
    stats = {
        "entries": len(entries),
        "ipaSymbols": 0,
        "semicolons": 0,
        "pos": 0,
        "ipaOverrides": 0,
        "meaningReplacements": 0,
    }
    for entry in entries:
        counts = normalize_symbols(entry.chars)
        for key, value in counts.items():
            stats[key] += value
        stats["ipaOverrides"] += int(apply_ipa_override(entry))
        stats["meaningReplacements"] += int(apply_meaning_replacement(entry))
        entry.sort_key = normalized_sort_key(entry.headword)
        entry.letter = next((char.upper() for char in entry.sort_key if char.isalpha()), "#")
    entries.sort(key=lambda item: (item.letter, item.sort_key, item.headword.casefold(), item.level))
    return stats


def build_base_corrected_pdf():
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
            "title": "高中英语《新课程标准》3100词总表（2025差异版）",
            "author": "编制：LaoShui",
            "subject": "普通高中英语课程标准3100词表差异版",
        }
    )
    doc.set_metadata(metadata)
    doc.save(BASE_CORRECTED, garbage=4, deflate=True, clean=True)
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


def sorted_font_markup(
    text: str, color: str, cjk_font: fitz.Font, latin_font: fitz.Font
) -> str:
    if not text:
        return ""
    if "<br/>" in text:
        return "<br/>".join(
            sorted_font_markup(part, color, cjk_font, latin_font)
            for part in text.split("<br/>")
        )
    runs = []
    start = 0

    def latin(char: str) -> bool:
        codepoint = ord(char)
        use_latin = (
            codepoint < 0x0250 or 0x0250 <= codepoint <= 0x02FF
        ) and latin_font.has_glyph(codepoint)
        if not cjk_font.has_glyph(codepoint) and latin_font.has_glyph(codepoint):
            use_latin = True
        return use_latin

    current = latin(text[0])
    for index, char in enumerate(text[1:], 1):
        kind = latin(char)
        if kind != current:
            runs.append((text[start:index], current))
            start = index
            current = kind
    runs.append((text[start:], current))
    parts = []
    for run, is_latin in runs:
        safe = html.escape(run, quote=False)
        font = ' name="TimesNewRoman"' if is_latin else ""
        parts.append(f'<font{font} color="{color}">{safe}</font>')
    return "".join(parts)


def entry_markup(
    entry: ColoredEntry,
    cjk_font: fitz.Font,
    latin_font: fitz.Font,
    preserve_colors: bool,
) -> str:
    groups = []
    for item in entry.chars:
        if groups and groups[-1][1] == item.color:
            groups[-1] = (groups[-1][0] + item.char, item.color)
        else:
            groups.append((item.char, item.color))
    return "".join(
        sorted_font_markup(
            text, color if preserve_colors else BLACK_HEX, cjk_font, latin_font
        )
        for text, color in groups
    )


def register_sorted_fonts() -> tuple[fitz.Font, fitz.Font]:
    for path in (SYSTEM_KAITI, SYSTEM_SONG, SYSTEM_TIMES, SYSTEM_TIMES_BOLD):
        if not path.exists():
            raise FileNotFoundError(path)
    for name, path in (
        ("STKaiti", SYSTEM_KAITI),
        ("STSong", SYSTEM_SONG),
        ("TimesNewRoman", SYSTEM_TIMES),
        ("TimesNewRoman-Bold", SYSTEM_TIMES_BOLD),
    ):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    return fitz.Font(fontfile=str(SYSTEM_KAITI)), fitz.Font(fontfile=str(SYSTEM_TIMES))


class SortedNumberedCanvas(pdf_canvas.Canvas):
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
            self.saveState()
            self.setStrokeColor(colors.HexColor("#D0D0D0"))
            self.setLineWidth(0.45)
            self.line(18.5 * mm, 13.5 * mm, A4[0] - 18.5 * mm, 13.5 * mm)
            self.setFillColor(colors.HexColor("#555555"))
            self.setFont("STKaiti", 9)
            self.drawString(18.5 * mm, 8.5 * mm, "编制：LaoShui")
            self.drawRightString(
                A4[0] - 18.5 * mm,
                8.5 * mm,
                f"第 {self._pageNumber} 页（共 {page_count} 页）",
            )
            self.restoreState()
            super().showPage()
        super().save()


def decorate_sorted_page(canvas, _document):
    return None


def build_sorted_pdf(
    entries: list[ColoredEntry],
    output: Path,
    edition: str,
    preserve_colors: bool,
) -> None:
    cjk_font, latin_font = register_sorted_fonts()
    output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=18.5 * mm,
        rightMargin=18.5 * mm,
        topMargin=22 * mm,
        bottomMargin=25 * mm,
        title=f"高中英语《新课程标准》3100词总表（{edition}）",
        author="编制：LaoShui",
        subject=f"普通高中英语课程标准3100词表（{edition}）",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SortedTitle",
        parent=styles["Title"],
        fontName="STSong",
        fontSize=18.5,
        leading=28,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#171717"),
        spaceAfter=3 * mm,
    )
    subtitle_style = ParagraphStyle(
        "SortedSubtitle",
        parent=styles["BodyText"],
        fontName="STKaiti",
        fontSize=12,
        leading=18,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
        spaceAfter=4 * mm,
    )
    note_style = ParagraphStyle(
        "SortedNote",
        parent=styles["BodyText"],
        fontName="STKaiti",
        fontSize=10.8,
        leading=18,
        alignment=TA_LEFT,
        wordWrap="CJK",
        spaceAfter=3 * mm,
    )
    letter_style = ParagraphStyle(
        "SortedLetter",
        parent=styles["Heading1"],
        fontName="TimesNewRoman-Bold",
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#222222"),
        spaceBefore=5,
        spaceAfter=2,
    )
    level_style = ParagraphStyle(
        "SortedLevel",
        parent=styles["Heading2"],
        fontName="STKaiti",
        fontSize=9.6,
        leading=13,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#777777"),
        spaceBefore=2,
        spaceAfter=1,
    )
    entry_style = ParagraphStyle(
        "SortedEntry",
        parent=styles["BodyText"],
        fontName="STKaiti",
        fontSize=10.7,
        leading=16.5,
        alignment=TA_LEFT,
        wordWrap="CJK",
        textColor=colors.black,
        spaceAfter=2.2,
        allowWidows=0,
        allowOrphans=0,
    )

    story = [
        Spacer(1, 2 * mm),
        Paragraph("高中英语《新课程标准》3100词总表", title_style),
        Paragraph(edition, subtitle_style),
        Paragraph("【编写说明】", note_style),
        Paragraph(
            "本词表以《普通高中英语课程标准（2017年版2025年修订）》附录2为词头与星级依据，并结合多套词典数据补充音标、高考高频释义、必要熟词生义及常用派生/搭配。",
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
            "注：正文按词头字母顺序排列；音标以英式读音为主，必要时标注英美差异。"
            + ("蓝色文字表示相对2025版的校正或补充。" if preserve_colors else ""),
            note_style,
        ),
    ]
    current_letter = None
    for entry in entries:
        if entry.letter != current_letter:
            current_letter = entry.letter
            story.append(Paragraph(entry.letter, letter_style))
        story.append(
            KeepTogether(
                [
                    Paragraph(
                        entry_markup(entry, cjk_font, latin_font, preserve_colors),
                        entry_style,
                    )
                ]
            )
        )
    document.build(
        story,
        onFirstPage=decorate_sorted_page,
        onLaterPages=decorate_sorted_page,
        canvasmaker=SortedNumberedCanvas,
    )


def build_corrected_pdf():
    regions = build_base_corrected_pdf()
    entries = extract_colored_entries(BASE_CORRECTED)
    if len(entries) != 3090:
        raise RuntimeError(f"Expected 3090 true entry blocks, got {len(entries)}")
    renamed = apply_headword_renames(entries)
    level_changes = sync_authority_levels(entries)
    supplements = supplemental_entries(entries)
    entries.extend(supplements)
    missing = authority_missing(entries)
    if missing:
        raise RuntimeError(
            "The corrected wordbook still misses Ministry Appendix 2 entries: "
            + ", ".join(missing)
        )
    authority_corrections = make_authority_corrections(
        renamed, level_changes, supplements
    )
    second_round = make_second_round_corrections(entries)
    stats = transform_entries(entries)
    stats.update(
        {
            "sourceEntries": 3090,
            "authorityLines": len(authority_word_lines()),
            "headwordRenames": len(renamed),
            "authorityLevelChanges": len(level_changes),
            "authoritySupplements": len(supplements),
            "authorityMissing": len(missing),
        }
    )
    build_sorted_pdf(entries, DIFF_2025, "2025差异版", True)
    build_sorted_pdf(entries, FINAL_2026, "2026版", False)
    with fitz.open(DIFF_2025) as document:
        stats["differencePages"] = document.page_count
    with fitz.open(FINAL_2026) as document:
        stats["finalPages"] = document.page_count
    return (
        regions,
        stats,
        BASE_DETAIL_CORRECTIONS + authority_corrections + second_round,
    )


def build_details_pdf(detail_corrections: list[Correction]):
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
        canvas.drawString(18 * mm, 9 * mm, "校正明细 · 编制：LaoShui")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(DETAILS),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=20 * mm,
        title="高中英语《新课程标准》3100词总表校正明细",
        author="LaoShui",
    )
    story = [
        Paragraph("高中英语《新课程标准》3100词总表", title),
        Paragraph("2025差异版 · 校正内容明细", title),
        Paragraph(
            f"共列出 {len(detail_corrections)} 项正文与全表系统校正。页码均指原2025版PDF页码；“全表”表示统一处理。",
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

    for index, item in enumerate(detail_corrections, 1):
        color = {
            "light": "#4A90D9",
            "medium": "#1F6FB2",
            "deep": "#0B4F9C",
        }[item.level]
        page_label = "全表" if item.page <= 0 else f"原第 {item.page} 页"
        header = (
            f'<font color="{color}">●</font> {index:03d}　{page_label}　'
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


def markdown_cell(text: str) -> str:
    return text.replace("\n", " ").replace("|", "\\|").replace("\x00", "[缺失字符]")


def correction_table(items: list[Correction]) -> list[str]:
    lines = [
        "| ID | 原页 | 词条/范围 | 类型 | 原问题 | 校正后 |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for item in items:
        page = "全表" if item.page <= 0 else str(item.page)
        lines.append(
            f"| {item.code} | {page} | {markdown_cell(item.entry)} | "
            f"{markdown_cell(item.kind)} | {markdown_cell(item.original)} | "
            f"{markdown_cell(item.corrected)} |"
        )
    return lines


def build_report_md(detail_corrections: list[Correction], stats: dict[str, int]) -> None:
    first_round = [item for item in detail_corrections if item.code.startswith(("C", "N"))]
    system = [item for item in detail_corrections if item.code.startswith("S")]
    authority = [item for item in detail_corrections if item.code.startswith("A")]
    ipa = [item for item in detail_corrections if item.code.startswith("I")]
    meanings = [item for item in detail_corrections if item.code.startswith("M")]
    lines = [
        "# 高中英语《新课程标准》3100词总表审校报告",
        "",
        "## 结论",
        "",
        f"当前2025差异版与2026版累计记录 **{len(detail_corrections)} 项正文或全表校正**。"
        f"其中保留第一轮正文校正 {len(first_round)} 项，教育部课标词头统一/补充 {len(authority)} 项，新增全表系统修正 {len(system)} 项、"
        f"明确音标覆盖 {len(ipa)} 项、高考适配释义精简 {len(meanings)} 项。",
        "",
        "本次是在原有蓝色版本上继续完善：蓝色2025差异版用于已打印2025版的同学勘误；黑色2026版作为正式使用版。浅蓝表示音标与符号修正，中蓝表示词性、释义和用法调整，深蓝表示词头、整条内容、课标补充或全表结构性修正。",
        "",
        "## 第二轮全表审计摘要",
        "",
        "- 真实词条块：3090。",
        "- 词头、音标和释义均使用多方资料交叉核对；本地参考数据不作为公开版出处列示。",
        "- 原表同一字母、同一星级组内相邻逆序：211处，现已统一排序。",
        "- 原审计检出含损坏或非统一IPA字符的候选292条；其中只对编码符号和39项明确损坏音标实施修改，未把词典口音差异一概判错。",
        f"- 本次实际规范IPA字符 {stats['ipaSymbols']} 处，异体分号 {stats['semicolons']} 处，词性缩写 {stats['pos']} 处。",
        "- 低频、俚语、专名或全量词典释义候选42条，另对3处原版跨词条合并内容做拆分清理；均经多方资料交叉核对后按高考用途精简，同时保留必要熟词生义。",
        "",
        "## 全表系统修正",
        "",
        *correction_table(system),
        "",
        "## 教育部课标词头统一与缺项补充",
        "",
        f"教育部附录2共提取3093条展示行（其中含括号/斜线变体合并），当前版本在原3090个词条块基础上统一了{stats['headwordRenames']}个官方词头、修正{stats['authorityLevelChanges']}处课程星级，并补入{stats['authoritySupplements']}个原版未独立列出的课标词。",
        "",
        *correction_table(authority),
        "",
        "## 第二轮新增明确音标修正",
        "",
        *correction_table(ipa),
        "",
        "## 第二轮新增高考适配释义精简",
        "",
        *correction_table(meanings),
        "",
        "## 第一轮已保留校正",
        "",
        *correction_table(first_round),
        "",
        "## 审校方法与边界",
        "",
        "1. 对原版111页PDF和既有蓝色校正版做视觉文本提取，以成对音标斜杠和词条结构识别3090个真实词条块；跨行的dreamed/dreamt、lit/lighted等仍归入原词条。",
        "2. 音标、词性和释义使用多方资料交叉核对；公开报告不列示仅供本地构建参考的数据文件。",
        "3. 正文按规范化词头严格升序排列；星号只标识课程层级，不参与排序，括号中的英美拼写不改变主词头排序。",
        "4. IPA只统一明确的OCR/编码损坏与符号体例。nearby、mature、tournament等有词典或口音变体者，采用保守处理或明确标出口音，不把可接受变体当作硬错。",
        "5. 释义以高考高频义为核心，并保留考试中常见的熟词生义；极低频行业义、过时俚语、专名和词典全量义不作为背诵负担。",
        "6. 所有最终PDF须同时通过词条数、排序、旧错误清除、页码/水印和关键页渲染检查。",
        "",
        "上述取舍，皆属编者一孔之见，是否允当，惟待读者明鉴。",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    regions, stats, detail_corrections = build_corrected_pdf()
    build_details_pdf(detail_corrections)
    build_report_md(detail_corrections, stats)
    regions_path = TEMP_DIR / "corrected_regions.txt"
    regions_path.write_text(
        "\n".join(
            f"{item['page']}\t" + ",".join(f"{value:.3f}" for value in item["rect"])
            for item in regions
        ),
        encoding="utf-8",
    )
    print(f"difference={DIFF_2025}")
    print(f"final={FINAL_2026}")
    print(f"details={DETAILS}")
    print(f"report={REPORT}")
    print(f"corrections={len(detail_corrections)}")
    print(f"changed_regions={len(regions)}")
    print(f"stats={stats}")


if __name__ == "__main__":
    main()

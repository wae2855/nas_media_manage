import re
import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


DEFAULT_CONFIDENCE_CONFIG = {
    "provider_match_threshold": 0.85,
    "title_exact_with_year": 1.0,
    "title_exact_with_season": 0.9,
    "title_exact_no_year": 0.7,
    "title_exact_year_mismatch": 0.4,
    "title_fuzzy_year_coeff": 0.7,
    "title_min_similarity": 0.3,
    "R_formula": "log",
    "R_max_results_cap": 10,
    "R_min_value": 0.1,
    "R_T_floor": 1.0,
    "R_T_curve": 1.5,
    "source_priority": ["tmdb", "ai", "file"],
    "ai_cap_high_similarity": 0.7,
    "ai_cap_low_similarity": 0.3,
    "ai_cap_no_title": 0.3,
    "ai_cap_no_match": 0.2,
    "ai_cap_low_coeff": 0.5,
    "pass_threshold": 0.8,
    "confirm_threshold": 0.5,
    "review_threshold": 0.3,
    "dimensions": {},
}


@dataclass
class CleanResult:
    clean_title: str
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    removed_items: List[str] = field(default_factory=list)
    method: str = "regex"
    year_suspect: bool = False
    cjk_title: Optional[str] = None


@dataclass
class MatchResult:
    level: str
    T: float
    similarity: float
    year_match: Optional[bool] = None
    reason: str = ""


@dataclass
class ConfidenceResult:
    final_confidence: float
    search_conf: float = 0.0
    data_conf: float = 1.0
    data_gate: float = 1.0
    gate_blocked: Optional[Dict[str, Any]] = None
    veto: Optional[Dict[str, Any]] = None
    llm_raw_confidence: Optional[float] = None
    dimensions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    scrape_trace: Dict[str, Any] = field(default_factory=dict)
    confidence_detail: Dict[str, Any] = field(default_factory=dict)


_RESOLUTION_PATTERNS = re.compile(
    r'[.\s_-](1080[pi]|720p|2160p|4320p|4[Kk]|UHD|FHD|MiniHD|MiniWT|HDS)(?=[.\s_-]|$)',
    re.IGNORECASE
)
_SOURCE_CODEC_PATTERNS = re.compile(
    r'[.\s_-](BluRay|BD|WEB-DL|WEBRip|WEB|HDTV|BDRip|BRRip|HDRip|DVDRip|DVDSCR|HDTC|HDTS|CAM|TS|HC|REMUX|REPACK|PROPER|INTERNAL|RETAIL|UNRATED|EXTENDED|REMASTERED|THEATRICAL|DC|SE|UNCUT|UNCENSORED|DUBBED|SUBBED|DUAL|Complete|Criterion[\s._]Collection|Festival[\s._]Cut|IMAX|Open[\s._]Matte|Half[\s._-]SBS|SBS|x264|x265|XviD|DivX|HEVC|H\.264|H\.265|H265|AVC|HDR10\+?|HDR|10bit|12bit|6ch|8ch|AAC|AC3|DTS-HD\.?MA\d*(?:\.\d+)*|DTS-X|DTS\.X|DTS|DDP\d+\.?\d*|DD\d*\.?\d*|Atmos|FLAC\d*(?:\.\d+)*|TrueHD(?:[\s.]?Atmos)?(?:[\s.]?\d+(?:\.\d+)*)?|DV|DolbyVision|NF|DSNP|AMZN|R[1-6]|CRF\d+|\d+[Aa]udio)(?=[.\s_-]|$)',
    re.IGNORECASE
)
_RELEASE_GROUP_START = re.compile(r'^\[([^\]]+)\][.\s_-]?')
_RELEASE_GROUP_END = re.compile(r'[.\s_-]-([A-Za-z0-9_.@&\u4e00-\u9fff\u3400-\u4dbf]+)$')
_RELEASE_GROUP_TAIL = re.compile(r'[.\s_-]([A-Z][A-Z0-9]{2,})$')
_SEASON_EPISODE = re.compile(r'[.\s_-]?[Ss](\d+)[Ee](\d+)(?:[Ee](\d+))?', re.IGNORECASE)
_SEASON_ONLY = re.compile(r'[.\s_-]?[Ss](\d+)(?![Ee]\d)', re.IGNORECASE)
_YEAR_PATTERN = re.compile(r'[.\s_(](19\d{2}|20\d{2})(?=[.\s_)]|$)')
_YEAR_PAREN = re.compile(r'\s*\((19\d{2}|20\d{2})\)')
_AD_PATTERN = re.compile(r'(www\.|https?://|\.com\b|\.net\b|\.org\b)', re.IGNORECASE)
_AD_FULL_PATTERN = re.compile(r'(?:www\.|https?://)?[a-zA-Z0-9-]+\.(com|net|org)\b[.\s_-]*[\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9]*', re.IGNORECASE)
_EDITION_PATTERN = re.compile(r'[.\s_-](\d+th[.\s_-]*Anniversary(?:[.\s_-]*Edition)?|Special[.\s_-]*Edition|Collector\'?s?[.\s_-]*Edition|Director\'?s?[.\s_-]*Cut|Ultimate[.\s_-]*Edition|Limited[.\s_-]*Edition|Deluxe[.\s_-]*Edition|Remastered[.\s_-]*Edition|Extended[.\s_-]*Edition|Theatrical[.\s_-]*Edition|Edition)(?=[.\s_-]|$)', re.IGNORECASE)
_BRACKET_CONTENT = re.compile(r'[\[(].*?[\])]')
_EXTENSION_PATTERN = re.compile(r'\.(mkv|mp4|avi|wmv|flv|mov|ts|m4v|rmvb|rm|srt|ass|ssa|sub|idx|vtt)$', re.IGNORECASE)
_MULTI_EP = re.compile(r'[.\s_-]?[Ss](\d+)[Ee](\d+)[Ee](\d+)', re.IGNORECASE)

_SUBTITLE_LANG_PATTERN = re.compile(
    r'[.\s_-](chs|cht|chi|eng|jpn|kor|zh-cn|zh-tw|zh&eng|chs&eng|cht&eng|zh|cn|tw|ja|ko|简体|繁体|简英|繁英|中字|中英|英字|双语|国语|粤语|国英双语|简繁外|简繁英)(?=[.\s_-]|$)',
    re.IGNORECASE
)
_CJK_DESCRIPTOR_PATTERN = re.compile(
    r'[.\s_-](国英双语|国语|粤语|双语|中字|中英|英字|简体|繁体|简繁外|简繁英|简英|繁英|内嵌字幕|外挂字幕)(?=[.\s_-]|$)',
    re.IGNORECASE
)

_CODEC_PREFIX_RE = re.compile(
    r'^(MA\d*|Atmos|TrueHD|AC3|DTS|FLAC|AAC|DDP\d*\.?\d*|DD\d*\.?\d*|HEVC|AVC|x264|x265|XviD|HDR\d*|DV|SBS|Remux|PROPER|REPACK)$',
    re.IGNORECASE
)


def _calc_R(total_results: int, formula: str, cap: int, min_val: float) -> float:
    N = min(total_results, cap) if cap > 0 else total_results
    if N <= 0:
        return 1.0
    if formula == "inverse":
        R = 1.0 / N
    elif formula == "log":
        R = 1.0 / math.log2(N + 1)
    elif formula == "sqrt":
        R = 1.0 / math.sqrt(N)
    elif formula == "flat":
        R = 1.0
    else:
        R = 1.0 / math.log2(N + 1)
    return max(R, min_val)


def _aggregate(values: List[float], weights: List[float], method: str = "geometric_mean") -> float:
    if not values:
        return 1.0
    if method == "product":
        result = 1.0
        for v in values:
            result *= v
        return result
    if method == "min":
        return min(values)
    weighted_product = 1.0
    total_weight = 0.0
    for v, w in zip(values, weights):
        weighted_product *= v ** w
        total_weight += w
    if total_weight <= 0:
        return 1.0
    return weighted_product ** (1.0 / total_weight)

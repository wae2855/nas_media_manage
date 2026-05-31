import re
import json
import math
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set


DEFAULT_CONFIDENCE_CONFIG = {
    "tmdb_match_threshold": 0.85,
    "title_exact_with_year": 1.0,
    "title_exact_with_season": 0.9,
    "title_exact_no_year": 0.7,
    "title_exact_year_mismatch": 0.4,
    "title_fuzzy_year_coeff": 0.7,
    "title_min_similarity": 0.3,
    "R_formula": "log",
    "R_max_results_cap": 10,
    "R_min_value": 0.1,
    "R_T_floor": 0.5,
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
    data_gate: float = 1.0
    gate_blocked: Optional[Dict[str, Any]] = None
    dimensions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    scrape_trace: Dict[str, Any] = field(default_factory=dict)


_RESOLUTION_PATTERNS = re.compile(
    r'[.\s_-](1080[pi]|720p|2160p|4320p|4[Kk]|UHD|FHD|MiniHD|MiniWT|HDS)(?=[.\s_-]|$)',
    re.IGNORECASE
)
_SOURCE_CODEC_PATTERNS = re.compile(
    r'[.\s_-](BluRay|WEB-DL|WEBRip|WEB|HDTV|BDRip|BRRip|HDRip|DVDRip|DVDSCR|HDTC|HDTS|CAM|TS|HC|REMUX|REPACK|PROPER|INTERNAL|RETAIL|UNRATED|EXTENDED|REMASTERED|THEATRICAL|DC|SE|UNCUT|UNCENSORED|DUBBED|SUBBED|DUAL|Complete|Criterion[\s._]Collection|Festival[\s._]Cut|IMAX|Open[\s._]Matte|Half[\s._-]SBS|SBS|x264|x265|XviD|DivX|HEVC|H\.264|H\.265|H265|AVC|HDR10\+?|HDR|10bit|12bit|6ch|8ch|AAC|AC3|DTS-HD\.?MA\d*(?:\.\d+)*|DTS-X|DTS|DDP\d+\.?\d*|DD\d*\.?\d*|Atmos|FLAC\d*(?:\.\d+)*|TrueHD(?:[\s.]?Atmos)?(?:[\s.]?\d+(?:\.\d+)*)?|DV|DolbyVision|NF|DSNP|AMZN|R[1-6]|CRF\d+|\d+[Aa]udio)(?=[.\s_-]|$)',
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
_EDITION_PATTERN = re.compile(r'[.\s_-](\d+th[.\s_-]*Anniversary(?:[.\s_-]*Edition)?|Special[.\s_-]*Edition|Collector\'?s?[.\s_-]*Edition|Director\'?s?[.\s_-]*Cut|Ultimate[.\s_-]*Edition|Limited[.\s_-]*Edition|Deluxe[.\s_-]*Edition|Remastered[.\s_-]*Edition|Extended[.\s_-]*Edition|Theatrical[.\s_-]*Edition)(?=[.\s_-]|$)', re.IGNORECASE)
_BRACKET_CONTENT = re.compile(r'[\[(].*?[\])]')
_EXTENSION_PATTERN = re.compile(r'\.(mkv|mp4|avi|wmv|flv|mov|ts|m4v|rmvb|rm)$', re.IGNORECASE)
_MULTI_EP = re.compile(r'[.\s_-]?[Ss](\d+)[Ee](\d+)[Ee](\d+)', re.IGNORECASE)


_CODEC_PREFIX_RE = re.compile(
    r'^(MA\d*|Atmos|TrueHD|AC3|DTS|FLAC|AAC|DDP\d*\.?\d*|DD\d*\.?\d*|HEVC|AVC|x264|x265|XviD|HDR\d*|DV|SBS|Remux|PROPER|REPACK)$',
    re.IGNORECASE
)


class FilenameCleaner:
    def clean(self, filename: str) -> CleanResult:
        original = filename
        name = _EXTENSION_PATTERN.sub('', filename)
        removed = []

        name = _RELEASE_GROUP_START.sub('', name)
        if name != _EXTENSION_PATTERN.sub('', filename):
            removed.append("制作组标签")

        rg_match = re.search(r'-\s*([A-Za-z0-9_.@&\u4e00-\u9fff\u3400-\u4dbf]+)$', name)
        if rg_match:
            group_name = rg_match.group(1)
            pre_dash = name[:rg_match.start()].rstrip()
            is_after_ad = bool(_AD_FULL_PATTERN.search(pre_dash)) if pre_dash else False
            if not _CODEC_PREFIX_RE.match(group_name) and not is_after_ad:
                name = name[:rg_match.start()] + name[rg_match.end():]
                removed.append(f"发布组={group_name}")

        name = _MULTI_EP.sub('', name)
        name = _SEASON_EPISODE.sub('', name)

        season = None
        episode = None
        se_match = _SEASON_EPISODE.search(_EXTENSION_PATTERN.sub('', filename))
        if se_match:
            season = int(se_match.group(1))
            episode = int(se_match.group(2))
            removed.append(f"季集=S{season:02d}E{episode:02d}")

        if season is None:
            so_match = _SEASON_ONLY.search(_EXTENSION_PATTERN.sub('', filename))
            if so_match:
                season = int(so_match.group(1))
                removed.append(f"季=S{season:02d}")
            name = _SEASON_ONLY.sub('', name)

        year = None
        yp_match = _YEAR_PAREN.search(name)
        if yp_match:
            year = int(yp_match.group(1))
            name = _YEAR_PAREN.sub('', name)
            removed.append(f"年份={year}")

        if year is None:
            year_match = _YEAR_PATTERN.search(name)
            if year_match:
                year = int(year_match.group(1))
                name = name[:year_match.start()] + name[year_match.end():]
                removed.append(f"年份={year}")

        name = _RESOLUTION_PATTERNS.sub('', name)
        name = _SOURCE_CODEC_PATTERNS.sub('', name)
        name = _EDITION_PATTERN.sub('', name)
        name = _AD_FULL_PATTERN.sub('', name)
        name = _AD_PATTERN.sub('', name)
        name = _BRACKET_CONTENT.sub('', name)

        result = _RELEASE_GROUP_TAIL.sub('', name)
        if result != name:
            removed.append("发布组标记")
            name = result

        name = re.sub(r'[.\s_-]+', ' ', name).strip()
        name = re.sub(r'^[\s._-]+|[\s._-]+$', '', name)

        cjk_title = None
        _CJK = r'\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef'
        _CJK_COLON = r'\uff1a\uFE55\u003a'
        mixed_match = re.match(
            rf'([{_CJK}][{_CJK}{_CJK_COLON}\s：:]+?)\s+([A-Za-z][A-Za-z\s\':,&!?\-]+)$',
            name
        )
        if mixed_match:
            cjk_part = mixed_match.group(1).strip()
            eng_part = mixed_match.group(2).strip()
            if len(cjk_part) >= 2 and len(eng_part) >= 3:
                removed.append(f"中文标题={cjk_part}")
                cjk_title = cjk_part
                name = eng_part

        year_suspect = False
        if year is not None:
            import datetime
            _current_year = datetime.datetime.now().year
            if year > _current_year + 1:
                year_suspect = True
            if not year_suspect and re.search(r'(?:^|\s)(19\d{2}|20\d{2})(?:\s|$)', name):
                year_suspect = True

        return CleanResult(
            clean_title=name,
            year=year,
            season=season,
            episode=episode,
            removed_items=removed,
            method="regex",
            year_suspect=year_suspect,
            cjk_title=cjk_title,
        )

    def ai_clean(self, filename: str, llm_scraper) -> CleanResult:
        prompt = (
            "从以下视频文件名中提取影视作品的标题和上映年份。\n"
            "注意：文件名可能包含制作组名、分辨率、编码信息等干扰项，年份可能是标题的一部分而非上映年份。\n"
            "请按以下JSON格式返回，不要返回其他内容：\n"
            '{"title": "标题", "year": 年份或null}\n'
            f"文件名: {filename}"
        )
        try:
            ai_result = llm_scraper.extract_title(prompt)
            if ai_result and ai_result.strip():
                import json
                text = ai_result.strip()
                think_match = re.search(r'</think\s*>', text, re.DOTALL)
                if think_match:
                    text = text[think_match.end():].strip()
                json_match = re.search(r'\{[^}]+\}', text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    title = data.get("title", "").strip()
                    year = data.get("year")
                    if title:
                        return CleanResult(
                            clean_title=title,
                            year=year if isinstance(year, int) else None,
                            method="ai"
                        )
                return CleanResult(clean_title=text, method="ai")
        except Exception:
            pass
        return self.clean(filename)


def _normalize_title(title: str) -> str:
    return title.lower().replace(' ', '').replace('.', '').replace('-', '').replace('_', '')


def _similarity(a: str, b: str) -> float:
    a_clean = _normalize_title(a)
    b_clean = _normalize_title(b)
    return SequenceMatcher(None, a_clean, b_clean).ratio()


class TitleMatcher:
    def __init__(self, config: dict = None):
        self._config = config or DEFAULT_CONFIDENCE_CONFIG

    def match(self, clean_title: str, tmdb_result: dict, year: int = None, season: int = None) -> MatchResult:
        original_title = tmdb_result.get("original_title", "") or tmdb_result.get("original_name", "")
        title = tmdb_result.get("title", "") or tmdb_result.get("name", "")
        release_date = tmdb_result.get("release_date", "") or tmdb_result.get("first_air_date", "")
        tmdb_year = None
        if release_date and len(release_date) >= 4:
            try:
                tmdb_year = int(release_date[:4])
            except (ValueError, TypeError):
                pass

        clean_norm = _normalize_title(clean_title)
        orig_norm = _normalize_title(original_title)
        title_norm = _normalize_title(title)

        exact_orig = clean_norm == orig_norm and len(clean_norm) > 0
        exact_title = clean_norm == title_norm and len(clean_norm) > 0
        exact_match = exact_orig or exact_title

        year_match = None
        if year is not None and tmdb_year is not None:
            year_match = year == tmdb_year

        if exact_match:
            if year is not None:
                if year_match:
                    return MatchResult(
                        level="L1", T=self._config["title_exact_with_year"],
                        similarity=1.0, year_match=True,
                        reason="L1: 标题精确匹配 + 年份一致"
                    )
                elif year_match is False:
                    return MatchResult(
                        level="L4", T=self._config["title_exact_year_mismatch"],
                        similarity=1.0, year_match=False,
                        reason="L4: 标题精确匹配，年份不匹配"
                    )
            elif season is not None:
                return MatchResult(
                    level="L2", T=self._config.get("title_exact_with_season", 0.9),
                    similarity=1.0, year_match=None,
                    reason=f"L2: 标题精确匹配 + 季号信息(S{season:02d})"
                )
            else:
                return MatchResult(
                    level="L3", T=self._config["title_exact_no_year"],
                    similarity=1.0, year_match=None,
                    reason="L3: 标题精确匹配，无年份/季号"
                )

        best_sim = max(
            _similarity(clean_title, original_title),
            _similarity(clean_title, title)
        )

        min_sim = self._config["title_min_similarity"]
        if best_sim < min_sim:
            return MatchResult(
                level="L7", T=0.0,
                similarity=best_sim, year_match=year_match,
                reason=f"L7: 相似度({best_sim:.2f})低于阈值({min_sim})，无匹配"
            )

        if year is not None:
            if year_match:
                return MatchResult(
                    level="L5", T=best_sim,
                    similarity=best_sim, year_match=True,
                    reason=f"L5: 模糊匹配(S={best_sim:.2f}) + 年份精确相等"
                )
            else:
                fuzzy_coeff = self._config["title_fuzzy_year_coeff"]
                return MatchResult(
                    level="L6", T=best_sim * fuzzy_coeff,
                    similarity=best_sim, year_match=year_match,
                    reason=f"L6: 模糊匹配(S={best_sim:.2f})，年份系数={fuzzy_coeff}"
                )
        else:
            fuzzy_coeff = self._config["title_fuzzy_year_coeff"]
            return MatchResult(
                level="L6", T=best_sim * fuzzy_coeff,
                similarity=best_sim, year_match=None,
                reason=f"L6: 模糊匹配(S={best_sim:.2f})，无年份过滤"
            )


class ScrapeTraceBuilder:
    def build(
        self,
        original_filename: str,
        clean_result: CleanResult,
        ai_clean_result: Optional[CleanResult],
        tmdb_search_info: Dict[str, Any],
        match_result: MatchResult,
        search_conf: float,
        R: float,
        R_formula: str,
        R_base: float = None,
        data_gate: float = 1.0,
        gate_blocked: Optional[Dict[str, Any]] = None,
        dimensions: Dict[str, Dict[str, Any]] = None,
        final_confidence: float = 0.0,
        llm_raw_confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        if dimensions is None:
            dimensions = {}
        search_conf_detail = {
            "T": match_result.T,
            "T_reason": match_result.reason,
            "R": R,
            "R_formula": R_formula,
            "total_results": tmdb_search_info.get("total_results", 0),
            "search_conf": search_conf,
        }
        if R_base is not None and abs(R - R_base) > 0.001:
            search_conf_detail["R_base"] = R_base
            search_conf_detail["R_adjusted"] = True
            search_conf_detail["R_adjust_reason"] = f"T={match_result.T:.2f} > R_T_floor, R从{R_base:.4f}调整为{R:.4f}"

        trace = {
            "mode": "tmdb_ai",
            "filename_clean": {
                "original": original_filename,
                "clean_title": clean_result.clean_title,
                "year": clean_result.year,
                "season": clean_result.season,
                "episode": clean_result.episode,
                "clean_method": clean_result.method,
                "removed_items": clean_result.removed_items,
            },
            "ai_clean": None,
            "tmdb_search": tmdb_search_info,
            "confidence_calc": {
                "formula": "final = search_conf × data_gate",
                "search_conf": search_conf_detail,
                "data_gate": {
                    "value": data_gate,
                    "blocked": gate_blocked,
                    "dimensions": dimensions,
                },
                "final_confidence": final_confidence,
                "llm_raw_confidence": llm_raw_confidence,
            },
            "dimensions": dimensions,
            "final_confidence": final_confidence,
        }

        if ai_clean_result:
            trace["ai_clean"] = {
                "clean_title": ai_clean_result.clean_title,
                "method": ai_clean_result.method,
            }

        return trace


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


class ConfidenceEngine:
    def __init__(self, config: dict = None):
        self._config = {**DEFAULT_CONFIDENCE_CONFIG}
        if config:
            self._config.update(config)
        self._dim_config = self._config.get("dimensions", {})
        self._source_priority = self._config.get("source_priority", ["tmdb", "ai", "file"])
        self._cleaner = FilenameCleaner()
        self._matcher = TitleMatcher(self._config)
        self._trace_builder = ScrapeTraceBuilder()

    @property
    def cleaner(self):
        return self._cleaner

    @property
    def matcher(self):
        return self._matcher

    def _get_dim_source(self, dim_name: str, dim_value: Any, source_priority: List[str]) -> str:
        if dim_value is None:
            return "missing"
        if isinstance(dim_value, dict):
            multi_sources = dim_value.get("sources")
            if multi_sources and isinstance(multi_sources, dict):
                for src in source_priority:
                    if src in multi_sources and multi_sources[src] is not None:
                        return src
                return "missing"
            return dim_value.get("source", "ai")
        return "ai"

    def _get_dim_source_config(self, dim_name: str) -> list:
        dim_cfg = self._dim_config.get(dim_name, {})
        sources_cfg = dim_cfg.get("sources", None)
        if sources_cfg and isinstance(sources_cfg, list):
            return sources_cfg
        legacy_trusted = dim_cfg.get("trusted_sources", None)
        if legacy_trusted is not None:
            return [
                {"source": s, "trusted": s in legacy_trusted}
                for s in self._source_priority
            ]
        return [{"source": s, "trusted": True} for s in self._source_priority]

    def _calc_data_gate(
        self,
        dimensions: Dict[str, Any],
        enabled_dims: Optional[Set[str]] = None,
    ) -> tuple:
        dim_results = {}
        gate_blocked = None

        for dim_name, dim_value in dimensions.items():
            if enabled_dims is not None and dim_name not in enabled_dims:
                dim_results[dim_name] = {
                    "value": dim_value.get("value") if isinstance(dim_value, dict) else dim_value,
                    "source": "disabled",
                    "trusted": True,
                    "skipped": True,
                    "detail": "维度已禁用，不参与计算",
                }
                continue

            sources_cfg = self._get_dim_source_config(dim_name)
            source_priority = [s["source"] for s in sources_cfg]
            trusted_set = {s["source"] for s in sources_cfg if s.get("trusted", True)}

            available_sources = {}
            if dim_value is None:
                pass
            elif isinstance(dim_value, dict):
                multi_sources = dim_value.get("sources")
                if multi_sources and isinstance(multi_sources, dict):
                    for src_key, src_val in multi_sources.items():
                        if src_val is not None:
                            if isinstance(src_val, dict):
                                available_sources[src_key] = src_val.get("value", src_val)
                            else:
                                available_sources[src_key] = src_val
                else:
                    single_src = dim_value.get("source", "ai")
                    available_sources[single_src] = dim_value.get("value")
            else:
                available_sources["ai"] = dim_value

            resolved_source = "missing"
            resolved_value = None
            for src in source_priority:
                if src in available_sources:
                    resolved_source = src
                    resolved_value = available_sources[src]
                    break

            trusted = resolved_source in trusted_set if trusted_set else True
            has_trusted_available = any(src in available_sources for src in trusted_set) if trusted_set else True

            if not trusted and not has_trusted_available:
                trusted = True

            dim_results[dim_name] = {
                "value": resolved_value,
                "source": resolved_source,
                "trusted": trusted,
                "detail": f"来源={resolved_source}, 信任={'是' if trusted else '否'}",
            }

            if not trusted and gate_blocked is None:
                gate_blocked = {
                    "dim_name": dim_name,
                    "source": resolved_source,
                    "reason": f"维度 {dim_name} 的来源 {resolved_source} 不在信任列表中",
                }

        data_gate = 0.0 if gate_blocked else 1.0
        return data_gate, dim_results, gate_blocked

    def _calc_search_conf(self, T: float, total_results: int) -> tuple:
        R_formula = self._config.get("R_formula", "log")
        R_cap = self._config.get("R_max_results_cap", 10)
        R_min = self._config.get("R_min_value", 0.1)
        R_base = _calc_R(total_results, R_formula, R_cap, R_min)

        R_T_floor = self._config.get("R_T_floor", 0.5)
        R_T_curve = self._config.get("R_T_curve", 1.5)
        if T > R_T_floor and R_T_floor < 1.0:
            alpha = ((T - R_T_floor) / (1.0 - R_T_floor)) ** R_T_curve
            R = R_base * (1.0 - alpha) + alpha
        else:
            R = R_base

        search_conf = T * R
        return search_conf, R, R_formula, R_base

    def calculate(
        self,
        scrape_result: dict,
        tmdb_search_info: dict,
        clean_result: CleanResult,
        ai_clean_result: Optional[CleanResult] = None,
        match_result: Optional[MatchResult] = None,
        llm_raw_confidence: Optional[float] = None,
        enabled_dims: Optional[Set[str]] = None,
    ) -> ConfidenceResult:
        T = match_result.T if match_result else 0.0
        total_results = tmdb_search_info.get("total_results", 0)

        search_conf, R, R_formula, R_base = self._calc_search_conf(T, total_results)

        dimensions = scrape_result.get("dimensions", {})
        if isinstance(dimensions, str):
            try:
                dimensions = json.loads(dimensions)
            except (json.JSONDecodeError, TypeError):
                dimensions = {}

        data_gate, dim_results, gate_blocked = self._calc_data_gate(
            dimensions, enabled_dims
        )

        final_confidence = round(search_conf * data_gate, 4)

        trace = self._trace_builder.build(
            original_filename=tmdb_search_info.get("original_filename", ""),
            clean_result=clean_result,
            ai_clean_result=ai_clean_result,
            tmdb_search_info=tmdb_search_info,
            match_result=match_result or MatchResult(level="L7", T=0.0, similarity=0.0, reason="无匹配结果"),
            search_conf=search_conf,
            R=R,
            R_formula=R_formula,
            R_base=R_base,
            data_gate=data_gate,
            gate_blocked=gate_blocked,
            dimensions=dim_results,
            final_confidence=final_confidence,
            llm_raw_confidence=llm_raw_confidence,
        )

        return ConfidenceResult(
            final_confidence=final_confidence,
            search_conf=search_conf,
            data_gate=data_gate,
            gate_blocked=gate_blocked,
            dimensions=dim_results,
            scrape_trace=trace,
        )

    def calculate_ai_only(
        self,
        scrape_result: dict,
        clean_result: CleanResult,
        llm_raw_confidence: Optional[float] = None,
        enabled_dims: Optional[Set[str]] = None,
        ai_clean_result: Optional[CleanResult] = None,
    ) -> ConfidenceResult:
        dimensions = scrape_result.get("dimensions", {})
        if isinstance(dimensions, str):
            try:
                dimensions = json.loads(dimensions)
            except (json.JSONDecodeError, TypeError):
                dimensions = {}

        llm_title = scrape_result.get("title_en", "") or scrape_result.get("title", "")
        objective_cap = self._compute_ai_cap(clean_result.clean_title, llm_title)

        data_gate, dim_results, gate_blocked = self._calc_data_gate(
            dimensions, enabled_dims
        )

        final_confidence = round(objective_cap * data_gate, 4)

        ai_clean_trace = None
        if ai_clean_result:
            ai_clean_trace = {
                "clean_title": ai_clean_result.clean_title,
                "method": ai_clean_result.method,
            }

        trace = {
            "mode": "ai",
            "filename_clean": {
                "original": clean_result.clean_title,
                "clean_title": clean_result.clean_title,
                "year": clean_result.year,
                "season": clean_result.season,
                "episode": clean_result.episode,
                "clean_method": clean_result.method,
            },
            "ai_clean": ai_clean_trace,
            "tmdb_search": None,
            "confidence_calc": {
                "formula": "final = objective_cap × data_gate",
                "ai_cap": {
                    "cap": objective_cap,
                    "reason": f"clean_title 与 AI 标题相似度={objective_cap:.4f}",
                },
                "objective_cap": objective_cap,
                "data_gate": {
                    "value": data_gate,
                    "blocked": gate_blocked,
                    "dimensions": dim_results,
                },
                "llm_raw_confidence": llm_raw_confidence,
                "final_confidence": final_confidence,
            },
            "dimensions": dim_results,
            "final_confidence": final_confidence,
        }

        return ConfidenceResult(
            final_confidence=final_confidence,
            search_conf=objective_cap,
            data_gate=data_gate,
            gate_blocked=gate_blocked,
            dimensions=dim_results,
            scrape_trace=trace,
        )

    def _compute_ai_cap(self, clean_title: str, llm_title: str) -> float:
        if not llm_title:
            return self._config["ai_cap_no_title"]

        sim = _similarity(clean_title, llm_title)

        if sim >= self._config["ai_cap_high_similarity"]:
            return sim
        elif sim >= self._config["ai_cap_low_similarity"]:
            return sim * self._config["ai_cap_low_coeff"]
        else:
            return self._config["ai_cap_no_match"]

    def get_confidence_level(self, final_confidence: float, gate_blocked: Optional[Dict[str, Any]] = None) -> str:
        if gate_blocked:
            return "NEEDS_REVIEW"
        if final_confidence >= self._config["pass_threshold"]:
            return "PASS"
        elif final_confidence >= self._config["confirm_threshold"]:
            return "CONFIRMING"
        elif final_confidence >= self._config["review_threshold"]:
            return "NEEDS_REVIEW"
        else:
            return "FAILED"

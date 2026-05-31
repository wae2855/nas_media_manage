from difflib import SequenceMatcher
from .confidence_models import MatchResult, DEFAULT_CONFIDENCE_CONFIG


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

    def match_standard(self, clean_title: str, search_item, year=None, season=None) -> MatchResult:
        from media_importer.scraper.providers.base import SearchItem
        original_title = search_item.original_title or ""
        title = search_item.title or ""
        tmdb_year = search_item.year

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

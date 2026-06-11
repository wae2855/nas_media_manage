import json
from typing import Optional, List, Dict, Any, Set

from media_importer.features.scraping.confidence_models import (
    DEFAULT_CONFIDENCE_CONFIG,
    CleanResult,
    MatchResult,
    ConfidenceResult,
    _calc_R,
    _aggregate,
)
from media_importer.scraper.filename_cleaner import FilenameCleaner
from media_importer.scraper.title_matcher import TitleMatcher, _similarity
from media_importer.scraper.trace_builder import ScrapeTraceBuilder


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

            dim_cfg = self._config.get("dimensions", {}).get(dim_name, {})
            source_conf = dim_cfg.get("source_confidence", {})
            veto_threshold = dim_cfg.get("veto_threshold")
            dim_weight = dim_cfg.get("weight", 1.0)

            dim_confidence = 1.0 if trusted else 0.5
            if resolved_source == "missing":
                dim_confidence = 0.5
            if resolved_source in source_conf:
                dim_confidence = source_conf[resolved_source]
            elif resolved_source == "missing" and "missing" in source_conf:
                dim_confidence = source_conf["missing"]
            elif isinstance(dim_value, dict) and dim_value.get("confidence") is not None:
                dim_confidence = dim_value["confidence"]

            dim_results[dim_name] = {
                "value": resolved_value,
                "source": resolved_source,
                "trusted": trusted,
                "confidence": dim_confidence,
                "dim_confidence": dim_confidence,
                "weight": dim_weight,
                "veto_threshold": veto_threshold,
                "veto": False,
                "detail": f"来源={resolved_source}, 信任={'是' if trusted else '否'}",
            }

            if veto_threshold is not None and dim_confidence < veto_threshold:
                dim_results[dim_name]["veto"] = True
                if gate_blocked is None:
                    gate_blocked = {
                        "dim_name": dim_name,
                        "source": resolved_source,
                        "reason": f"维度 {dim_name} 置信度 {dim_confidence} 低于否决阈值 {veto_threshold}",
                    }

            if not trusted and gate_blocked is None and veto_threshold is None:
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
        provider_search_info: dict,
        clean_result: CleanResult,
        ai_clean_result: Optional[CleanResult] = None,
        match_result: Optional[MatchResult] = None,
        llm_raw_confidence: Optional[float] = None,
        enabled_dims: Optional[Set[str]] = None,
    ) -> ConfidenceResult:
        T = match_result.T if match_result else 0.0
        total_results = provider_search_info.get("total_results", 0)

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
            original_filename=provider_search_info.get("original_filename", ""),
            clean_result=clean_result,
            ai_clean_result=ai_clean_result,
            provider_search_info=provider_search_info,
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
            search_enhanced=scrape_result.get("search_enhanced", False),
        )

        veto = None
        for dim_name, dim_info in dim_results.items():
            if dim_info.get("veto"):
                veto = {
                    "dim_name": dim_name,
                    "dim_confidence": dim_info.get("confidence", 0),
                    "veto_threshold": dim_info.get("veto_threshold", 0.9),
                }
                break

        data_conf = 1.0
        if dim_results:
            values = []
            weights = []
            for dim_name, dim_info in dim_results.items():
                if dim_info.get("skipped"):
                    continue
                conf = dim_info.get("confidence", 1.0)
                values.append(conf)
                weights.append(dim_info.get("weight", 1.0))
            if values:
                agg_method = self._config.get("aggregation_method", "geometric_mean")
                data_conf = _aggregate(values, weights, agg_method)

        confidence_detail = {
            "formula": "T × R × data_gate",
            "T": round(T, 4),
            "R": round(R, 4),
            "R_formula": R_formula,
            "R_base": round(R_base, 4),
            "total_results": total_results,
            "search_conf": round(search_conf, 4),
            "data_gate": data_gate,
            "gate_blocked": gate_blocked is not None,
            "final_confidence": final_confidence,
        }

        return ConfidenceResult(
            final_confidence=final_confidence,
            search_conf=search_conf,
            data_conf=data_conf,
            data_gate=data_gate,
            gate_blocked=gate_blocked,
            veto=veto,
            llm_raw_confidence=llm_raw_confidence,
            dimensions=dim_results,
            scrape_trace=trace,
            confidence_detail=confidence_detail,
        )

    def calculate_ai_only(
        self,
        scrape_result: dict,
        clean_result: CleanResult,
        llm_raw_confidence: Optional[float] = None,
        enabled_dims: Optional[Set[str]] = None,
        ai_clean_result: Optional[CleanResult] = None,
        provider_fallback_reasons: Optional[List[Dict[str, Any]]] = None,
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
            "search_enhanced": scrape_result.get("search_enhanced", False),
            "filename_clean": {
                "original": clean_result.clean_title,
                "clean_title": clean_result.clean_title,
                "year": clean_result.year,
                "season": clean_result.season,
                "episode": clean_result.episode,
                "clean_method": clean_result.method,
            },
            "ai_clean": ai_clean_trace,
            "provider_search": None,
            "provider_fallback_reasons": provider_fallback_reasons,
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

        confidence_detail = {
            "formula": "objective_cap × data_gate",
            "objective_cap": round(objective_cap, 4),
            "clean_title": clean_result.clean_title,
            "llm_title": llm_title,
            "data_gate": data_gate,
            "gate_blocked": gate_blocked is not None,
            "final_confidence": final_confidence,
        }

        return ConfidenceResult(
            final_confidence=final_confidence,
            search_conf=objective_cap,
            data_gate=data_gate,
            gate_blocked=gate_blocked,
            dimensions=dim_results,
            scrape_trace=trace,
            confidence_detail=confidence_detail,
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


__all__ = [
    "ConfidenceEngine",
    "FilenameCleaner",
    "TitleMatcher",
    "ScrapeTraceBuilder",
    "CleanResult",
    "MatchResult",
    "ConfidenceResult",
    "DEFAULT_CONFIDENCE_CONFIG",
]

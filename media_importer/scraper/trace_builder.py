from typing import Optional, Dict, Any
from media_importer.features.scraping.confidence_models import CleanResult, MatchResult


class ScrapeTraceBuilder:
    def build(
        self,
        original_filename: str,
        clean_result: CleanResult,
        ai_clean_result: Optional[CleanResult],
        provider_search_info: Dict[str, Any],
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
            "total_results": provider_search_info.get("total_results", 0),
            "search_conf": search_conf,
        }
        if R_base is not None and abs(R - R_base) > 0.001:
            search_conf_detail["R_base"] = R_base
            search_conf_detail["R_adjusted"] = True
            search_conf_detail["R_adjust_reason"] = f"T={match_result.T:.2f} > R_T_floor, R从{R_base:.4f}调整为{R:.4f}"

        trace = {
            "mode": "provider_ai",
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
            "provider_type": provider_search_info.get("provider_type", "tmdb"),
            "provider_search": provider_search_info,
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

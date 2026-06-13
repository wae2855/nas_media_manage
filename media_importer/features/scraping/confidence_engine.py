"""置信度引擎兼容层。

原始置信度引擎已被三级匹配引擎（match_engine.py）替代。
此文件保留为薄 re-export 兼容层，确保旧代码不报错。
新代码应直接使用 match_engine.MatchEngine。
"""

import logging
from typing import Optional, List, Dict, Any, Set

from media_importer.features.scraping.confidence_models import (
    DEFAULT_CONFIDENCE_CONFIG,
    CleanResult,
    MatchResult,
    ConfidenceResult,
)
from media_importer.scraper.filename_cleaner import FilenameCleaner
from media_importer.scraper.title_matcher import TitleMatcher
from media_importer.scraper.trace_builder import ScrapeTraceBuilder
from media_importer.scraper.title_matcher import _similarity

logger = logging.getLogger(__name__)


class ConfidenceEngine:
    """置信度引擎兼容层。

    所有计算逻辑已迁移到 match_engine.MatchEngine。
    此类保留接口兼容，内部委托给新引擎或返回默认值。
    """

    def __init__(self, config: dict = None):
        self._config = {**DEFAULT_CONFIDENCE_CONFIG}
        if config:
            self._config.update(config)
        self._cleaner = FilenameCleaner()
        self._matcher = TitleMatcher(self._config)
        self._trace_builder = ScrapeTraceBuilder()

    @property
    def cleaner(self):
        return self._cleaner

    @property
    def matcher(self):
        return self._matcher

    def calculate(self, scrape_result, provider_search_info, clean_result,
                  ai_clean_result=None, match_result=None,
                  llm_raw_confidence=None, enabled_dims=None):
        """兼容方法：返回默认 ConfidenceResult。

        新代码应使用 match_engine.MatchEngine.match() 获取 MatchResult。
        """
        T = match_result.T if match_result else 0.0
        return ConfidenceResult(
            final_confidence=T,
            search_conf=T,
            data_conf=1.0,
            data_gate=1.0,
            gate_blocked=None,
            veto=None,
            llm_raw_confidence=llm_raw_confidence,
            dimensions={},
            scrape_trace={},
            confidence_detail={
                "formula": "兼容层：已迁移到三级匹配引擎",
                "T": round(T, 4),
                "final_confidence": round(T, 4),
            },
        )

    def calculate_ai_only(self, scrape_result, clean_result,
                          llm_raw_confidence=None, enabled_dims=None,
                          ai_clean_result=None, provider_fallback_reasons=None):
        """兼容方法：返回默认 ConfidenceResult。"""
        return ConfidenceResult(
            final_confidence=0.5,
            search_conf=0.5,
            data_conf=1.0,
            data_gate=1.0,
            gate_blocked=None,
            dimensions={},
            scrape_trace={},
            confidence_detail={
                "formula": "兼容层：已迁移到三级匹配引擎",
                "final_confidence": 0.5,
            },
        )

    def get_confidence_level(self, final_confidence, gate_blocked=None):
        """兼容方法：将置信度数值映射为 match_level。

        旧代码可能仍调用此方法，映射规则：
        - >= 0.8 → PASS (对应 AUTO_PASS)
        - >= 0.5 → CONFIRMING (对应 NEEDS_CONFIRM)
        - >= 0.3 → NEEDS_REVIEW (对应 NEEDS_CONFIRM)
        - < 0.3 → FAILED (对应 NEEDS_CONFIRM)
        """
        if gate_blocked:
            return "NEEDS_REVIEW"
        if final_confidence >= self._config.get("pass_threshold", 0.8):
            return "PASS"
        elif final_confidence >= self._config.get("confirm_threshold", 0.5):
            return "CONFIRMING"
        elif final_confidence >= self._config.get("review_threshold", 0.3):
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
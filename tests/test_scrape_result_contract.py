"""刮削结果契约测试。

当前事实（ADR-0005）：刮削结果只使用 media_type，不再兼容旧 type 字段。
"""

import pytest


class TestMediaTypeContract:
    """验证刮削结果使用 media_type 字段。"""

    def test_provider_only_result_with_media_type(self):
        """Provider 只返回 media_type 时，验证应正常通过。"""
        from media_importer.features.import_flow.services.review import (
            ReviewDecisionService,
        )

        service = ReviewDecisionService()
        scraped = {
            "title_cn": "测试电影",
            "title_en": "Test Movie",
            "year": 2024,
            "media_type": "movie",
            "match_level": "AUTO_PASS",
        }

        decision = service.evaluate(scraped)
        assert decision.action == "continue", (
            f"有 media_type 应通过验证，实际: {decision.action}"
        )

    def test_neither_type_nor_media_type_is_missing(self):
        """缺少 media_type 时应报告缺失。"""
        from media_importer.features.import_flow.services.review import (
            ReviewDecisionService,
        )

        service = ReviewDecisionService()
        scraped = {
            "title_cn": "测试电影",
            "title_en": "Test Movie",
            "year": 2024,
            "match_level": "AUTO_PASS",
        }

        decision = service.evaluate(scraped)
        assert decision.action == "confirm", (
            "缺少媒体类型应触发确认"
        )
        codes = [c.get("code", "") for c in decision.concerns]
        assert "MISSING_FIELDS" in codes, (
            f"concerns 应含 MISSING_FIELDS，实际: {decision.concerns}"
        )

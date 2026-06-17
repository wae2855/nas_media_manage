"""P0 数据正确性修复的回归测试。

覆盖 docs/plans/2026-06-16-confirm-workflow-overhaul-plan.md 的三个修复点：
- P0-1: _build_provider_only_result 补 title_cn/title_en
- P0-3: render_template 加 title_cn → title_en → title 三层兜底
- 联动: provider-only result 通过命名模板不再退化为只剩年份
"""

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.features.import_flow.services.classification_rules import (
    render_template,
)
from media_importer.features.import_flow.services.naming import (
    apply_filename_template,
)


class TestRenderTemplateTitleFallback(unittest.TestCase):
    """P0-3: render_template 在标题缺失时的多层兜底。"""

    def test_title_cn_present_uses_directly(self):
        scraped = {"title_cn": "阿凡达", "title_en": "Avatar", "year": 2009}
        result = render_template("{title_cn}.{year}", scraped)
        self.assertEqual(result, "阿凡达.2009/")

    def test_title_cn_empty_falls_back_to_title_en(self):
        scraped = {"title_cn": "", "title_en": "Avatar", "year": 2009}
        result = render_template("{title_cn}.{year}", scraped)
        self.assertEqual(result, "Avatar.2009/")

    def test_title_cn_and_en_empty_falls_back_to_title(self):
        """P0-3 关键兜底：cn/en 都空时回退到 title 字段，避免文件名退化成只剩年份。"""
        scraped = {"title_cn": "", "title_en": "", "title": "Avatar", "year": 2009}
        result = render_template("{title_cn}.{year}", scraped)
        self.assertEqual(result, "Avatar.2009/")

    def test_title_all_empty_degenerates_only_when_no_title(self):
        """完全没有 title 字段时才允许退化。"""
        scraped = {"title_cn": "", "title_en": "", "year": 2009}
        result = render_template("{title_cn}.{year}", scraped)
        self.assertEqual(result, "2009/")


class TestApplyFilenameTemplateNoDegradation(unittest.TestCase):
    """P0-3 联动：电影命名模板在标题缺失时不应退化为只剩年份。"""

    MOVIE_TEMPLATE = "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}"

    def test_full_scrape_produces_normal_filename(self):
        scraped = {
            "title_cn": "阿凡达",
            "title_en": "Avatar",
            "year": 2009,
            "resolution": "1080p",
            "quality": "BluRay",
        }
        filename = apply_filename_template(scraped, self.MOVIE_TEMPLATE, ".mkv")
        self.assertEqual(filename, "阿凡达.Avatar.2009.1080p.BluRay.mkv")

    def test_provider_only_result_with_only_title_does_not_degrade_to_year_only(self):
        """P0-1+P0-3 联动核心场景：scrape_result 只有 title（provider-only 修复前的 bug 形态），
        通过三层兜底后退化为 'Avatar.2009.mkv'，而不是只剩 '2009.mkv'。"""
        scraped = {
            "title": "Avatar",
            "title_cn": "",
            "title_en": "",
            "year": 2009,
        }
        filename = apply_filename_template(scraped, self.MOVIE_TEMPLATE, ".mkv")
        self.assertEqual(filename, "Avatar.2009.mkv")
        self.assertNotEqual(filename, "2009.mkv", "不应退化成只剩年份")

    def test_resolution_quality_missing_collapses_correctly(self):
        """标题存在但分辨率/质量缺失时，多个点应被合并，仍保留标题。"""
        scraped = {"title_cn": "阿凡达", "title_en": "", "year": 2009}
        filename = apply_filename_template(scraped, self.MOVIE_TEMPLATE, ".mkv")
        self.assertEqual(filename, "阿凡达.2009.mkv")


class TestBuildProviderOnlyResultTitles(unittest.TestCase):
    """P0-1: _build_provider_only_result 必须写入 title_cn/title_en。"""

    def _build_call_args(self):
        from media_importer.scraper.metadata_scrape_flow import (
            _build_provider_only_result,
        )

        details = SimpleNamespace(
            title="Avatar",
            original_title="Avatar",
            year=2009,
            overview="A paraplegic Marine...",
            genres=[SimpleNamespace(name="Sci-Fi")],
            vote_average=8.0,
            poster_url="https://example.com/poster.jpg",
        )
        search_item = SimpleNamespace(
            title="Avatar", original_title="Avatar",
        )
        clean_result = SimpleNamespace(
            clean_title="Avatar", year=2009, season=None, episode=None,
        )

        return _build_provider_only_result, details, search_item, clean_result

    def test_provider_only_result_contains_title_cn_and_en(self):
        """P0-1 核心：provider-only 路径返回的 dict 必须包含 title_cn 和 title_en。"""
        fn, details, search_item, clean_result = self._build_call_args()

        result = fn(
            scraper=None,
            details=details,
            search_item=search_item,
            media_type="movie",
            clean_result=clean_result,
            provider_dimensions={},
            search_info={},
            match_result={},
            ai_clean_result=None,
            enabled_dims_set=None,
            log=__import__("logging").getLogger(__name__),
            t_start=0.0,
        )

        self.assertIn("title_cn", result, "provider-only 结果必须包含 title_cn")
        self.assertIn("title_en", result, "provider-only 结果必须包含 title_en")
        self.assertEqual(result["title_cn"], "Avatar")
        self.assertEqual(result["title_en"], "Avatar")
        self.assertEqual(result["title"], "Avatar")
        self.assertEqual(result["original_title"], "Avatar")

    def test_provider_only_result_falls_back_to_search_item(self):
        """details.title 为空时应回退到 search_item.title。"""
        fn, details, search_item, clean_result = self._build_call_args()
        details.title = ""
        details.original_title = ""

        result = fn(
            scraper=None,
            details=details,
            search_item=search_item,
            media_type="movie",
            clean_result=clean_result,
            provider_dimensions={},
            search_info={},
            match_result={},
            ai_clean_result=None,
            enabled_dims_set=None,
            log=__import__("logging").getLogger(__name__),
            t_start=0.0,
        )

        self.assertEqual(result["title_cn"], "Avatar")
        self.assertEqual(result["title_en"], "Avatar")


class TestProviderOnlyResultPlusNamingE2E(unittest.TestCase):
    """P0-1 + P0-3 联动：provider-only 结果直接喂给命名模板，文件名应包含标题。"""

    def test_end_to_end_movie_filename_has_title(self):
        from media_importer.scraper.metadata_scrape_flow import (
            _build_provider_only_result,
        )

        details = SimpleNamespace(
            title="阿凡达",
            original_title="Avatar",
            year=2009,
            overview="",
            genres=[],
            vote_average=8.0,
            poster_url="",
        )
        search_item = SimpleNamespace(title="阿凡达", original_title="Avatar")
        clean_result = SimpleNamespace(
            clean_title="阿凡达", year=2009, season=None, episode=None,
        )

        result = _build_provider_only_result(
            scraper=None,
            details=details,
            search_item=search_item,
            media_type="movie",
            clean_result=clean_result,
            provider_dimensions={},
            search_info={},
            match_result={},
            ai_clean_result=None,
            enabled_dims_set=None,
            log=__import__("logging").getLogger(__name__),
            t_start=0.0,
        )

        template = "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}"
        filename = apply_filename_template(result, template, ".mkv")

        self.assertIn("阿凡达", filename)
        self.assertIn("2009", filename)
        self.assertNotEqual(filename, "2009.mkv", "不应退化成只剩年份")


if __name__ == "__main__":
    unittest.main()

"""Preview job 异步刮削预览测试。"""

import time
from unittest.mock import MagicMock, patch

import pytest

from media_importer.api.tmdb_handlers import (
    _SCRAPE_PREVIEW_JOBS,
    _find_provider,
    _preview_add_step,
    _run_scrape_preview_job,
)


class TestScrapePreviewJob:
    """Preview job 单元测试。"""

    def test_start_returns_job_id(self):
        job_id = "test-job-123"
        now = time.time()
        _SCRAPE_PREVIEW_JOBS[job_id] = {
            "job_id": job_id,
            "status": "running",
            "filename": "test.mkv",
            "started_at": now,
            "updated_at": now,
            "steps": [],
            "partial": {},
            "result": None,
            "error": "",
        }
        assert job_id in _SCRAPE_PREVIEW_JOBS
        assert _SCRAPE_PREVIEW_JOBS[job_id]["status"] == "running"
        del _SCRAPE_PREVIEW_JOBS[job_id]

    def test_job_status_contains_steps(self):
        job_id = "test-job-steps"
        now = time.time()
        job = {
            "job_id": job_id,
            "status": "running",
            "filename": "test.mkv",
            "started_at": now,
            "updated_at": now,
            "steps": [],
            "partial": {},
            "result": None,
            "error": "",
        }
        _SCRAPE_PREVIEW_JOBS[job_id] = job
        _preview_add_step(job, "clean", "文件名清洗", "running", "正在清洗")
        _preview_add_step(job, "clean", "文件名清洗", "done", "清洗完成")
        assert len(job["steps"]) == 2
        assert job["steps"][0]["key"] == "clean"
        assert job["steps"][0]["status"] == "running"
        assert job["steps"][1]["status"] == "done"
        del _SCRAPE_PREVIEW_JOBS[job_id]

    def test_find_provider_by_type(self):
        provider_a = MagicMock()
        provider_a.provider_type = "tmdb"
        provider_b = MagicMock()
        provider_b.provider_type = "douban"
        found = _find_provider([provider_a, provider_b], "tmdb")
        assert found is provider_a
        found_none = _find_provider([provider_a, provider_b], "unknown")
        assert found_none is None

    def test_preview_needs_confirm_uses_first_candidate(self):
        from media_importer.features.providers.base import (
            MediaDetails, SearchItem, SearchResult,
        )
        from media_importer.features.scraping.match_models import (
            MatchConcern, MatchResult, MatchTraceStep,
        )

        job_id = "test-job-needs-confirm"
        now = time.time()
        job = {
            "job_id": job_id, "status": "running",
            "filename": "jinji.S01E02.mp4",
            "started_at": now, "updated_at": now,
            "steps": [], "partial": {}, "result": None, "error": "",
        }
        _SCRAPE_PREVIEW_JOBS[job_id] = job

        mock_provider = MagicMock()
        mock_provider.provider_type = "tmdb"
        mock_provider.display_name = "TMDb"
        mock_provider.search.return_value = SearchResult(
            items=[SearchItem(
                provider_type="tmdb", item_id="1429",
                title="Attack on Titan", original_title="Shingeki no Kyojin",
                year=2013, media_type="tv",
                poster_url="https://example.com/poster.jpg",
                vote_average=8.5, raw_data={"overview": "Giants"},
            )], total_results=1,
        )
        mock_provider.get_details.return_value = MediaDetails(
            provider_type="tmdb", item_id="1429", media_type="tv",
            title="Attack on Titan", original_title="Shingeki no Kyojin",
            year=2013, genres=[], overview="Giants", vote_average=8.5,
            origin_country=["JP"], original_language="ja",
            adult=False, tagline="",
            poster_url="https://example.com/poster.jpg", raw_data={},
        )

        mock_match_result = MatchResult(
            match_level="NEEDS_CONFIRM", match_tier=3,
            concerns=[MatchConcern(code="FUZZY_TITLE", message="标题模糊匹配", detail="")],
            trace_steps=[
                MatchTraceStep(tier=1, name="Provider", matched=False, reason="no match"),
                MatchTraceStep(tier=3, name="Confirm", matched=False, reason="need confirm"),
            ],
            candidates=[{
                "provider_type": "tmdb", "display_name": "TMDb",
                "id": "1429", "title": "Attack on Titan",
                "original_title": "Shingeki no Kyojin",
                "year": 2013, "media_type": "tv",
                "overview": "Giants", "poster_url": "https://example.com/poster.jpg",
                "vote_average": 8.5,
            }],
        )

        config = {"classification": {"rules": []}, "path_rules": [], "fallback_dir": ""}

        with patch("media_importer.api.scrape_preview_job.globals._global_logger", MagicMock()):
            with patch("media_importer.features.scraping.match_engine.MatchEngine._tier1_exact_match", return_value=None):
                with patch("media_importer.features.scraping.match_engine.MatchEngine._tier2_context_match", return_value=None):
                    with patch("media_importer.features.scraping.match_engine.MatchEngine._tier3_user_confirm", return_value=mock_match_result):
                        with patch("media_importer.features.providers.create_providers", return_value=[mock_provider]):
                            _run_scrape_preview_job(job_id, job["filename"], config)

        assert job["status"] == "done"
        result = job["result"]
        assert result is not None
        sr = result["scrape_result"]
        assert sr["provider_id"] == "1429"
        assert sr["match_level"] == "NEEDS_CONFIRM"
        assert sr["tier_short_reason"] is not None
        assert sr["media_type"] == "tv"
        del _SCRAPE_PREVIEW_JOBS[job_id]

    def test_preview_needs_confirm_without_candidates_returns_minimal(self):
        from media_importer.features.providers.base import SearchResult
        from media_importer.features.scraping.match_models import (
            MatchConcern, MatchResult, MatchTraceStep,
        )

        job_id = "test-job-no-candidates"
        now = time.time()
        job = {
            "job_id": job_id, "status": "running",
            "filename": "UnknownMovie.2099.mkv",
            "started_at": now, "updated_at": now,
            "steps": [], "partial": {}, "result": None, "error": "",
        }
        _SCRAPE_PREVIEW_JOBS[job_id] = job

        mock_provider = MagicMock()
        mock_provider.provider_type = "tmdb"
        mock_provider.display_name = "TMDb"
        mock_provider.search.return_value = SearchResult(items=[], total_results=0)

        mock_match_result = MatchResult(
            match_level="NEEDS_CONFIRM", match_tier=3,
            concerns=[MatchConcern(code="NO_RESULT", message="未找到匹配作品", detail="")],
            trace_steps=[
                MatchTraceStep(tier=1, name="Provider", matched=False, reason="no result"),
                MatchTraceStep(tier=3, name="Confirm", matched=False, reason="need confirm"),
            ],
            candidates=[],
        )

        config = {"classification": {"rules": []}, "path_rules": [], "fallback_dir": ""}

        with patch("media_importer.api.scrape_preview_job.globals._global_logger", MagicMock()):
            with patch("media_importer.features.scraping.match_engine.MatchEngine._tier1_exact_match", return_value=None):
                with patch("media_importer.features.scraping.match_engine.MatchEngine._tier2_context_match", return_value=None):
                    with patch("media_importer.features.scraping.match_engine.MatchEngine._tier3_user_confirm", return_value=mock_match_result):
                        with patch("media_importer.features.providers.create_providers", return_value=[mock_provider]):
                            _run_scrape_preview_job(job_id, job["filename"], config)

        assert job["status"] == "done"
        sr = job["result"]["scrape_result"]
        assert sr["match_level"] == "NEEDS_CONFIRM"
        assert sr["tier_short_reason"] is not None
        assert len(sr["tier_short_reason"]) > 0
        del _SCRAPE_PREVIEW_JOBS[job_id]

    def test_preview_job_does_not_call_full_llm_scrape(self):
        from media_importer.features.providers.base import (
            MediaDetails, SearchItem, SearchResult,
        )
        from media_importer.features.scraping.match_models import (
            MatchResult, MatchTraceStep,
        )

        job_id = "test-job-no-llm"
        now = time.time()
        job = {
            "job_id": job_id, "status": "running",
            "filename": "Inception.2010.1080p.mkv",
            "started_at": now, "updated_at": now,
            "steps": [], "partial": {}, "result": None, "error": "",
        }
        _SCRAPE_PREVIEW_JOBS[job_id] = job

        mock_provider = MagicMock()
        mock_provider.provider_type = "tmdb"
        mock_provider.display_name = "TMDb"
        mock_provider.search.return_value = SearchResult(
            items=[SearchItem(
                provider_type="tmdb", item_id="27205",
                title="Inception", original_title="Inception",
                year=2010, media_type="movie",
                poster_url=None, vote_average=8.8, raw_data={},
            )], total_results=1,
        )
        mock_provider.get_details.return_value = MediaDetails(
            provider_type="tmdb", item_id="27205", media_type="movie",
            title="Inception", original_title="Inception", year=2010,
            genres=[], overview="A dream within a dream", vote_average=8.8,
            origin_country=["US"], original_language="en",
            adult=False, tagline="", poster_url="", raw_data={},
        )

        mock_match_result = MatchResult(
            match_level="AUTO_PASS", provider_id="27205",
            provider_title="Inception", match_tier=1,
            trace_steps=[MatchTraceStep(tier=1, name="Provider", matched=True, reason="exact")],
            candidates=[{
                "provider_type": "tmdb", "display_name": "TMDb",
                "id": "27205", "title": "Inception",
                "original_title": "Inception", "year": 2010,
                "media_type": "movie", "overview": "",
                "poster_url": "", "vote_average": 8.8,
            }],
        )

        config = {"classification": {"rules": []}, "path_rules": [], "fallback_dir": ""}

        with patch("media_importer.api.scrape_preview_job.globals._global_logger", MagicMock()):
            with patch("media_importer.features.scraping.match_engine.MatchEngine._tier1_exact_match", return_value=mock_match_result):
                with patch("media_importer.features.providers.create_providers", return_value=[mock_provider]):
                    with patch("media_importer.features.scraping.MetadataScraper") as mock_scraper:
                        _run_scrape_preview_job(job_id, job["filename"], config)
                        mock_scraper.assert_not_called()

        assert job["status"] == "done"
        assert job["result"]["scrape_result"]["match_level"] == "AUTO_PASS"
        del _SCRAPE_PREVIEW_JOBS[job_id]

    def test_preview_job_exception_sets_failed_status(self):
        """后端异常时 job 状态设为 failed，并记录错误"""
        from media_importer.features.providers.base import SearchResult

        job_id = "test-job-exception"
        now = time.time()
        job = {
            "job_id": job_id, "status": "running",
            "filename": "crash_test.mkv",
            "started_at": now, "updated_at": now,
            "steps": [], "partial": {}, "result": None, "error": "",
        }
        _SCRAPE_PREVIEW_JOBS[job_id] = job

        mock_provider = MagicMock()
        mock_provider.provider_type = "tmdb"
        mock_provider.display_name = "TMDb"
        mock_provider.search.side_effect = RuntimeError("API connection timeout")

        config = {"classification": {"rules": []}, "path_rules": [], "fallback_dir": ""}

        with patch("media_importer.api.scrape_preview_job.globals._global_logger", MagicMock()):
            with patch("media_importer.features.providers.create_providers", return_value=[mock_provider]):
                with patch("media_importer.features.scraping.match_engine.MatchEngine._tier1_exact_match", side_effect=RuntimeError("search engine crash")):
                    _run_scrape_preview_job(job_id, job["filename"], config)

        assert job["status"] == "failed", f"期望 failed，实际 {job['status']}"
        assert job["error"], f"error 不应为空"
        failed_steps = [s for s in job["steps"] if s.get("status") == "failed"]
        assert len(failed_steps) > 0, f"steps 中应有 failed 步骤，steps={job['steps']}"
        assert any("search engine crash" in s.get("message", "") or "search engine crash" in s.get("label", "") for s in failed_steps), \
            f"failed step 应包含错误信息，failed_steps={failed_steps}"
        del _SCRAPE_PREVIEW_JOBS[job_id]

    def test_preview_job_no_provider_returns_early(self):
        job_id = "test-job-no-provider"
        now = time.time()
        job = {
            "job_id": job_id, "status": "running",
            "filename": "test.mkv",
            "started_at": now, "updated_at": now,
            "steps": [], "partial": {}, "result": None, "error": "",
        }
        _SCRAPE_PREVIEW_JOBS[job_id] = job

        config = {}

        with patch("media_importer.api.scrape_preview_job.globals._global_logger", MagicMock()):
            with patch("media_importer.features.providers.create_providers", return_value=[]):
                _run_scrape_preview_job(job_id, job["filename"], config)

        assert job["status"] == "done"
        sr = job["result"]["scrape_result"]
        assert sr["match_level"] == "NEEDS_CONFIRM"
        assert sr["tier_short_reason"] == "未配置 Provider，无法自动匹配"
        del _SCRAPE_PREVIEW_JOBS[job_id]

    def test_preview_job_auto_pass_gets_details(self):
        from media_importer.features.providers.base import (
            MediaDetails, SearchItem, SearchResult,
        )
        from media_importer.features.scraping.match_models import (
            MatchResult, MatchTraceStep,
        )

        job_id = "test-job-auto-pass"
        now = time.time()
        job = {
            "job_id": job_id, "status": "running",
            "filename": "Inception.2010.1080p.mkv",
            "started_at": now, "updated_at": now,
            "steps": [], "partial": {}, "result": None, "error": "",
        }
        _SCRAPE_PREVIEW_JOBS[job_id] = job

        mock_provider = MagicMock()
        mock_provider.provider_type = "tmdb"
        mock_provider.display_name = "TMDb"
        mock_provider.search.return_value = SearchResult(
            items=[SearchItem(
                provider_type="tmdb", item_id="27205",
                title="Inception", original_title="Inception",
                year=2010, media_type="movie",
                poster_url="https://example.com/poster.jpg",
                vote_average=8.8, raw_data={"overview": "A dream"},
            )], total_results=1,
        )
        mock_provider.get_details.return_value = MediaDetails(
            provider_type="tmdb", item_id="27205", media_type="movie",
            title="Inception", original_title="Inception", year=2010,
            genres=[], overview="A dream", vote_average=8.8,
            origin_country=["US"], original_language="en",
            adult=False, tagline="",
            poster_url="https://example.com/poster.jpg", raw_data={},
        )

        mock_match_result = MatchResult(
            match_level="AUTO_PASS", provider_id="27205",
            provider_title="Inception", match_tier=1,
            trace_steps=[MatchTraceStep(tier=1, name="Provider", matched=True, reason="exact")],
            candidates=[{
                "provider_type": "tmdb", "display_name": "TMDb",
                "id": "27205", "title": "Inception",
                "original_title": "Inception", "year": 2010,
                "media_type": "movie", "overview": "",
                "poster_url": "", "vote_average": 8.8,
            }],
        )

        config = {"classification": {"rules": []}, "path_rules": [], "fallback_dir": ""}

        with patch("media_importer.api.scrape_preview_job.globals._global_logger", MagicMock()):
            with patch("media_importer.features.scraping.match_engine.MatchEngine._tier1_exact_match", return_value=mock_match_result):
                with patch("media_importer.features.providers.create_providers", return_value=[mock_provider]):
                    _run_scrape_preview_job(job_id, job["filename"], config)

        assert job["status"] == "done"
        sr = job["result"]["scrape_result"]
        assert sr["match_level"] == "AUTO_PASS"
        assert sr["title_cn"] == "Inception"
        assert sr["provider_id"] == "27205"
        assert sr["poster_url"] == "https://example.com/poster.jpg"
        del _SCRAPE_PREVIEW_JOBS[job_id]

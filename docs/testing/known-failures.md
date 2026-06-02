# Known Test Failures

This file records known failures that existed before a refactor. Keep it updated when failures are fixed or become irrelevant.

Current source of truth before manual curation:

- `.pytest_cache/v/cache/lastfailed`

## 2026-05-31 Baseline

Baseline commit: `1426c17`

Observed while running:

- `python3 -m pytest tests/test_task_context_lifecycle.py tests/test_task_operations.py tests/test_sqlite_refactor.py`

The following failures matched the existing `.pytest_cache/v/cache/lastfailed` list and are treated as pre-existing until manually investigated:

- `tests/test_sqlite_refactor.py::TestDB::test_14_has_active_tasks`
- `tests/test_sqlite_refactor.py::TestTaskManager::test_08_has_active_tasks`
- `tests/test_sqlite_refactor.py::TestFileScanner::test_03_scan_single_video`
- `tests/test_sqlite_refactor.py::TestFileScanner::test_04_scan_video_with_subtitles`
- `tests/test_sqlite_refactor.py::TestFileScanner::test_05_scan_multiple_videos`
- `tests/test_sqlite_refactor.py::TestFileScanner::test_06_scan_ignores_non_media`
- `tests/test_sqlite_refactor.py::TestFileScanner::test_07_scan_subdir`
- `tests/test_sqlite_refactor.py::TestFileScanner::test_08_scan_skips_hidden_dirs`
- `tests/test_sqlite_refactor.py::TestFileScanner::test_09_file_size`
- `tests/test_sqlite_refactor.py::TestFileScanner::test_10_scan_and_group_alias`
- `tests/test_sqlite_refactor.py::TestFileScanner::test_11_scan_and_filter_no_task_manager`
- `tests/test_sqlite_refactor.py::TestFileScanner::test_12_scan_and_filter_with_dedup`
- `tests/test_sqlite_refactor.py::TestPipeline::test_10_process_one_validate_failure`
- `tests/test_scrape_results.py`
- `tests/test_tmdb_config.py`

## 2026-06-02 Default Regression Gating

The default `pytest tests/` entry now excludes environment-gated suites and known failures through `tests/conftest.py`.

Environment-gated suites:

- External service UI: `tests/test_confidence_config_ui.py`, `tests/test_confidence_ui.py`, `tests/test_confidence_v2_ui.py`, `tests/test_config_page_full.py`, `tests/test_scrape_ui.py`, `tests/test_tmdb_config.py`.
- Self-started UI: `tests/test_frontend_recycle.py`.
- Self-started service integration: `tests/test_integration_recycle.py`.
- Live provider E2E: `tests/test_e2e_file_processing.py`.

Additional known failure nodeids observed during default-gating setup:

- `tests/test_deep_e2e.py::TestTC15SourceCleanerKeepMediaOnly::test_media_files_not_moved`
- `tests/test_deep_e2e.py::TestTC15SourceCleanerKeepMediaOnly::test_non_media_files_moved_to_recycle`
- `tests/test_deep_e2e.py::TestTC17JunkVideoDetection::test_small_video_detected_as_junk`
- `tests/test_deep_e2e.py::TestTC18BlacklistMatch::test_blacklist_wildcard_match`
- `tests/test_deep_e2e.py::TestTC19CleanerConfirmMode::test_confirm_mode_returns_need_confirm`
- `tests/test_deep_e2e.py::TestTC19CleanerConfirmMode::test_confirmed_execution_succeeds`
- `tests/test_deep_e2e.py::TestTC19CleanerEmptyDirs::test_empty_dir_cleaned`
- `tests/test_deep_e2e.py::TestTC19CleanerEmptyDirs::test_non_empty_dir_preserved`
- `tests/test_full_flow.py::TestBFailureFlow::test_B1_scrape_failure`
- `tests/test_full_flow.py::TestBFailureFlow::test_B2_failed_moved_to_recycle_bin`
- `tests/test_full_flow.py::TestDRetryFlow::test_D8_retry_preserves_recycle_location`
- `tests/test_full_flow.py::TestKQueueControl::test_K2_has_active_tasks`
- `tests/test_full_flow.py::TestKQueueControl::test_K3_no_active_tasks`
- `tests/test_full_flow.py::TestMQuarantine::test_M3_retry_from_recycle_bin_keeps_location`

Clean checks for the current refactor slice:

- `python3 -m pytest tests/test_task_context_lifecycle.py tests/test_task_operations.py` -> 54 passed
- `PYTHONPYCACHEPREFIX=/private/tmp/nas_media_pycache python3 -m py_compile media_importer/pipeline/context.py media_importer/core/task_lifecycle.py media_importer/pipeline/runner.py media_importer/pipeline/confirm.py media_importer/core/task_manager.py`

## 2026-06-01 Network-Dependent E2E

Observed while running:

- `python3 -m pytest tests/test_e2e_file_processing.py`

Result: 3 passed, 10 failed. The failures all occurred before the refactored service path could complete because TMDB/provider search could not resolve network hostnames in the current sandbox:

- `<urlopen error [Errno 8] nodename nor servname provided, or not known>`

Affected tests:

- `tests/test_e2e_file_processing.py::TestE2E1MovieFullFlow::test_movie_with_subtitle`
- `tests/test_e2e_file_processing.py::TestE2E2TVSeriesFlow::test_tv_episode`
- `tests/test_e2e_file_processing.py::TestE2E3DocumentaryFlow::test_documentary_movie`
- `tests/test_e2e_file_processing.py::TestE2E4LowConfidenceConfirm::test_low_confidence_confirm_flow`
- `tests/test_e2e_file_processing.py::TestE2E5DedupQuality::test_quality_strategy_keep_better`
- `tests/test_e2e_file_processing.py::TestE2E6DedupSkip::test_skip_strategy`
- `tests/test_e2e_file_processing.py::TestE2E7SourceDedup::test_rename_detected`
- `tests/test_e2e_file_processing.py::TestE2E7SourceDedup::test_reprocess_changed_file`
- `tests/test_e2e_file_processing.py::TestE2E7SourceDedup::test_skip_existing_file`
- `tests/test_e2e_file_processing.py::TestE2E9ReadOnlyMode::test_cleanup_source_false_preserves_source`

Maintenance rule:

- Do not use this file to excuse new failures.
- When a failure is fixed, remove or update the entry.

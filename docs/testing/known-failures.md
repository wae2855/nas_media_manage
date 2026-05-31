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

Clean checks for the current refactor slice:

- `python3 -m pytest tests/test_task_context_lifecycle.py tests/test_task_operations.py` -> 54 passed
- `PYTHONPYCACHEPREFIX=/private/tmp/nas_media_pycache python3 -m py_compile media_importer/pipeline/context.py media_importer/core/task_lifecycle.py media_importer/pipeline/runner.py media_importer/pipeline/confirm.py media_importer/core/task_manager.py`

Maintenance rule:

- Do not use this file to excuse new failures.
- When a failure is fixed, remove or update the entry.

import socket
from pathlib import Path

import pytest


EXTERNAL_UI_FILES = {
    "test_confidence_config_ui.py",
    "test_confidence_ui.py",
    "test_confidence_v2_ui.py",
    "test_config_page_full.py",
    "test_scrape_ui.py",
    "test_tmdb_config.py",
}

SELF_STARTED_UI_FILES = {
    "test_frontend_recycle.py",
}

SERVICE_INTEGRATION_FILES = {
    "test_integration_recycle.py",
}

LIVE_E2E_FILES = {
    "test_e2e_file_processing.py",
}

KNOWN_FAILURE_FILES = {
    "test_scrape_results.py",
}

KNOWN_FAILURE_NODEIDS = {
    "tests/test_sqlite_refactor.py::TestDB::test_14_has_active_tasks",
    "tests/test_sqlite_refactor.py::TestTaskManager::test_08_has_active_tasks",
    "tests/test_sqlite_refactor.py::TestFileScanner::test_03_scan_single_video",
    "tests/test_sqlite_refactor.py::TestFileScanner::test_04_scan_video_with_subtitles",
    "tests/test_sqlite_refactor.py::TestFileScanner::test_05_scan_multiple_videos",
    "tests/test_sqlite_refactor.py::TestFileScanner::test_06_scan_ignores_non_media",
    "tests/test_sqlite_refactor.py::TestFileScanner::test_07_scan_subdir",
    "tests/test_sqlite_refactor.py::TestFileScanner::test_08_scan_skips_hidden_dirs",
    "tests/test_sqlite_refactor.py::TestFileScanner::test_09_file_size",
    "tests/test_sqlite_refactor.py::TestFileScanner::test_10_scan_and_group_alias",
    "tests/test_sqlite_refactor.py::TestFileScanner::test_11_scan_and_filter_no_task_manager",
    "tests/test_sqlite_refactor.py::TestFileScanner::test_12_scan_and_filter_with_dedup",
    "tests/test_sqlite_refactor.py::TestPipeline::test_10_process_one_validate_failure",
    "tests/test_deep_e2e.py::TestTC15SourceCleanerKeepMediaOnly::test_media_files_not_moved",
    "tests/test_deep_e2e.py::TestTC15SourceCleanerKeepMediaOnly::test_non_media_files_moved_to_recycle",
    "tests/test_deep_e2e.py::TestTC17JunkVideoDetection::test_small_video_detected_as_junk",
    "tests/test_deep_e2e.py::TestTC18BlacklistMatch::test_blacklist_wildcard_match",
    "tests/test_deep_e2e.py::TestTC19CleanerConfirmMode::test_confirm_mode_returns_need_confirm",
    "tests/test_deep_e2e.py::TestTC19CleanerConfirmMode::test_confirmed_execution_succeeds",
    "tests/test_deep_e2e.py::TestTC19CleanerEmptyDirs::test_empty_dir_cleaned",
    "tests/test_deep_e2e.py::TestTC19CleanerEmptyDirs::test_non_empty_dir_preserved",
    "tests/test_full_flow.py::TestBFailureFlow::test_B1_scrape_failure",
    "tests/test_full_flow.py::TestBFailureFlow::test_B2_failed_moved_to_recycle_bin",
    "tests/test_full_flow.py::TestDRetryFlow::test_D8_retry_preserves_recycle_location",
    "tests/test_full_flow.py::TestKQueueControl::test_K2_has_active_tasks",
    "tests/test_full_flow.py::TestKQueueControl::test_K3_no_active_tasks",
    "tests/test_full_flow.py::TestMQuarantine::test_M3_retry_from_recycle_bin_keeps_location",
}


def pytest_addoption(parser):
    parser.addoption(
        "--run-ui",
        action="store_true",
        default=False,
        help="run Playwright UI tests that do not require an external service",
    )
    parser.addoption(
        "--run-external-ui",
        action="store_true",
        default=False,
        help="run Playwright UI tests that require an external service on port 9855",
    )
    parser.addoption(
        "--run-live-e2e",
        action="store_true",
        default=False,
        help="run live E2E tests that need real config, network, or provider credentials",
    )
    parser.addoption(
        "--run-service-integration",
        action="store_true",
        default=False,
        help="run tests that start an HTTP service inside the test process",
    )
    parser.addoption(
        "--run-known-failures",
        action="store_true",
        default=False,
        help="include known pre-existing failures tracked in docs/testing/known-failures.md",
    )


def pytest_ignore_collect(collection_path, config):
    filename = Path(collection_path).name
    if filename in KNOWN_FAILURE_FILES and not config.getoption("--run-known-failures"):
        return True
    if filename in EXTERNAL_UI_FILES and not config.getoption("--run-external-ui"):
        return True
    if filename in SELF_STARTED_UI_FILES and not config.getoption("--run-ui"):
        return True
    if filename in SERVICE_INTEGRATION_FILES and not config.getoption("--run-service-integration"):
        return True
    if filename in LIVE_E2E_FILES and not config.getoption("--run-live-e2e"):
        return True
    return False


def pytest_collection_modifyitems(config, items):
    run_ui = config.getoption("--run-ui")
    run_external_ui = config.getoption("--run-external-ui")
    run_live_e2e = config.getoption("--run-live-e2e")
    run_service_integration = config.getoption("--run-service-integration")
    run_known_failures = config.getoption("--run-known-failures")
    external_service_ready = _port_open("127.0.0.1", 9855) or _port_open("localhost", 9855)

    skip_ui = pytest.mark.skip(reason="UI tests require --run-ui")
    skip_external_ui = pytest.mark.skip(
        reason="external UI tests require --run-external-ui and a service on port 9855"
    )
    skip_external_service_down = pytest.mark.skip(reason="service on port 9855 is not reachable")
    skip_live_e2e = pytest.mark.skip(reason="live E2E tests require --run-live-e2e")
    skip_service_integration = pytest.mark.skip(
        reason="service integration tests require --run-service-integration"
    )
    skip_known_failure = pytest.mark.skip(reason="known pre-existing failure")

    for item in items:
        filename = Path(item.fspath).name
        nodeid = item.nodeid

        if filename in EXTERNAL_UI_FILES:
            item.add_marker(pytest.mark.ui)
            item.add_marker(pytest.mark.external_service)
            if not run_external_ui:
                item.add_marker(skip_external_ui)
            elif not external_service_ready:
                item.add_marker(skip_external_service_down)
            continue

        if filename in SELF_STARTED_UI_FILES:
            item.add_marker(pytest.mark.ui)
            item.add_marker(pytest.mark.self_started_service)
            if not run_ui:
                item.add_marker(skip_ui)

        if filename in LIVE_E2E_FILES:
            item.add_marker(pytest.mark.live_e2e)
            if not run_live_e2e:
                item.add_marker(skip_live_e2e)

        if filename in SERVICE_INTEGRATION_FILES:
            item.add_marker(pytest.mark.self_started_service)
            if not run_service_integration:
                item.add_marker(skip_service_integration)

        if nodeid in KNOWN_FAILURE_NODEIDS:
            item.add_marker(pytest.mark.known_failure)
            if not run_known_failures:
                item.add_marker(skip_known_failure)


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False

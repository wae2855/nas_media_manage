import os
from pathlib import Path

import pytest


def pytest_configure(config):
    worker_count = os.environ.get("PYTEST_XDIST_WORKER_COUNT")
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    if worker_count and worker_count != "0":
        raise pytest.UsageError(
            "Live E2E tests are not safe under pytest-xdist parallelism: the application is not designed for concurrent writers against a single SQLite + filesystem state. Run them with -n 0 (or omit -n)."
        )
    if worker_id and worker_id not in ("master", "gw0"):
        pass

EXTERNAL_UI_FILES = {
    "test_confidence_config_ui.py",
    "test_confidence_ui.py",
    "test_confidence_v2_ui.py",
    "test_scrape_ui.py",
    "test_source_cleaner_e2e.py",
    "test_e2e_cinema_workflow.py",
}

SELF_STARTED_UI_FILES = {
    "test_frontend_recycle.py",
}

SERVICE_INTEGRATION_FILES = {
    "test_integration_recycle.py",
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
        "--run-e2e-cinema",
        action="store_true",
        default=False,
        help="run end-to-end Playwright workflow tests for the cinema UI (tests/test_e2e_cinema_workflow.py)",
    )
    parser.addoption(
        "--run-service-integration",
        action="store_true",
        default=False,
        help="run tests that start an HTTP service inside the test process",
    )


def pytest_ignore_collect(collection_path, config):
    filename = Path(collection_path).name
    if filename in EXTERNAL_UI_FILES and not config.getoption("--run-external-ui"):
        return True
    if filename in SELF_STARTED_UI_FILES and not config.getoption("--run-ui"):
        return True
    if filename in SERVICE_INTEGRATION_FILES and not config.getoption("--run-service-integration"):
        return True
    return False


def pytest_collection_modifyitems(config, items):
    run_external_ui = config.getoption("--run-external-ui")
    run_e2e_cinema = config.getoption("--run-e2e-cinema")
    run_service_integration = config.getoption("--run-service-integration")
    external_service_ready = _port_open("127.0.0.1", 9855) or _port_open("localhost", 9855)

    skip_external_ui = pytest.mark.skip(
        reason="external UI tests require --run-external-ui and a service on port 9855"
    )
    skip_e2e_cinema = pytest.mark.skip(
        reason="end-to-end cinema workflow tests require --run-e2e-cinema and a service on port 9855"
    )
    skip_external_service_down = pytest.mark.skip(reason="service on port 9855 is not reachable")
    skip_service_integration = pytest.mark.skip(
        reason="service integration tests require --run-service-integration"
    )

    for item in items:
        filename = Path(item.fspath).name

        if filename in EXTERNAL_UI_FILES:
            item.add_marker(pytest.mark.ui)
            item.add_marker(pytest.mark.external_service)
            if filename == "test_e2e_cinema_workflow.py":
                if not run_e2e_cinema:
                    item.add_marker(skip_e2e_cinema)
                elif not external_service_ready:
                    item.add_marker(skip_external_service_down)
            elif not run_external_ui:
                item.add_marker(skip_external_ui)
            elif not external_service_ready:
                item.add_marker(skip_external_service_down)
            continue

        if filename in SERVICE_INTEGRATION_FILES:
            item.add_marker(pytest.mark.self_started_service)
            if not run_service_integration:
                item.add_marker(skip_service_integration)


def _port_open(host: str, port: int) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False
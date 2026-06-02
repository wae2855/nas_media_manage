import socket
from pathlib import Path

import pytest


EXTERNAL_UI_FILES = {
    "test_confidence_config_ui.py",
    "test_confidence_ui.py",
    "test_confidence_v2_ui.py",
    "test_scrape_ui.py",
}

SELF_STARTED_UI_FILES = {
    "test_frontend_recycle.py",
}

SERVICE_INTEGRATION_FILES = {
    "test_integration_recycle.py",
}

LIVE_E2E_FILES = set()


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


def pytest_ignore_collect(collection_path, config):
    filename = Path(collection_path).name
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

    for item in items:
        filename = Path(item.fspath).name

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


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False

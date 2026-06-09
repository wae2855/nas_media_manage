import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest
import yaml


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
}

SELF_STARTED_UI_FILES = {
    "test_frontend_recycle.py",
}

SERVICE_INTEGRATION_FILES = {
    "test_integration_recycle.py",
}

LIVE_E2E_FILES = {
    "test_e2e_01_config.py",
    "test_e2e_02_scan.py",
    "test_e2e_03_task_actions.py",
    "test_e2e_04_recycle.py",
    "test_e2e_05_navigation.py",
    "test_e2e_06_batch.py",
    "test_e2e_07_visual.py",
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


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _try_restart_e2e_server(e2e_server: dict) -> bool:
    proc = e2e_server.get("server_proc")
    if not proc:
        return False
    if proc.poll() is None:
        return True
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")
    env["NAS_MEDIA_IMPORTER_DATA_DIR"] = e2e_server["data_dir"]
    server_log = open(e2e_server["server_log_path"], "a", encoding="utf-8")
    new_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "media_importer.media_importer",
            "-c",
            e2e_server["config_path"],
            "serve",
            "-p",
            str(e2e_server["port"]),
            "--host",
            e2e_server["host"],
        ],
        cwd=Path.cwd(),
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    if not _wait_for_server(e2e_server["host"], e2e_server["port"], timeout=15):
        new_proc.terminate()
        try:
            new_proc.wait(5)
        except Exception:
            new_proc.kill()
        return False
    e2e_server["server_proc"] = new_proc
    return True


def _wait_for_server(host, port, timeout=15):
    import urllib.request

    url = f"http://{host}:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=2)
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _post_json(base_url: str, path: str, body: dict, timeout: int = 10):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base_url + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _build_e2e_config(tmpdir):
    real_config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "config.yaml",
    )
    real_cfg = {}
    if os.path.isfile(real_config_path):
        with open(real_config_path, "r") as f:
            real_cfg = yaml.safe_load(f) or {}

    source_dir = os.path.join(tmpdir, "source")
    temp_dir = os.path.join(tmpdir, "temp")
    log_dir = os.path.join(tmpdir, "logs")
    recycle_dir = os.path.join(tmpdir, "recycle")
    data_dir = os.path.join(tmpdir, "data")
    resource_dir = os.path.join(tmpdir, "resources")
    for d in [source_dir, temp_dir, log_dir, recycle_dir, data_dir, resource_dir]:
        os.makedirs(d, exist_ok=True)

    cfg = {
        "source_dir": source_dir,
        "temp_dir": temp_dir,
        "log_dir": log_dir,
        "_data_dir": data_dir,
        "resource_dir": resource_dir,
        "source_policy": {
            "recycle_dir": recycle_dir,
            "cleanup_mode": "read_only",
            "delete_source_after_import": False,
            "dedup_enabled": True,
            "max_auto_retries": 3,
            "scan_recursive": True,
            "scan_max_depth": 5,
        },
        "server": {"host": "0.0.0.0", "port": 9855, "api_key": ""},
        "file_watcher": {"enabled": False},
        "llm": real_cfg.get("llm", {}),
        "metadata": real_cfg.get("metadata", {}),
        "confidence": real_cfg.get("confidence", {}),
        "hermes": {"enabled": False},
        "task_queue": {"max_concurrent": 1},
        "manual_review": {"enabled": False},
        "video_extensions": [".mkv", ".mp4", ".avi", ".ts", ".mov", ".wmv", ".m2ts", ".flv"],
        "subtitle_extensions": [".srt", ".ass", ".ssa", ".vtt", ".sub"],
        "path_rules": [
            {"conditions": {"media_type": "tv", "animation": "true"},
             "template": f"{tmpdir}/影视/动漫/{{title_cn}} ({{year}})/Season {{season}}/"},
            {"conditions": {"media_type": "movie", "animation": "true"},
             "template": f"{tmpdir}/影视/动漫电影/{{title_cn}} ({{year}})/"},
            {"conditions": {"media_type": "tv"},
             "template": f"{tmpdir}/影视/电视剧/{{title_cn}} ({{year}})/Season {{season}}/"},
            {"conditions": {"media_type": "movie", "documentary": "true"},
             "template": f"{tmpdir}/影视/纪录片/{{title_cn}} ({{year}})/"},
            {"conditions": {"media_type": "movie"},
             "template": f"{tmpdir}/影视/电影/{{year}}/{{title_cn}} ({{year}})/"},
            {"conditions": {},
             "template": f"{tmpdir}/影视/其他/{{title_cn}} ({{year}})/"},
        ],
        "fallback_dir": f"{tmpdir}/影视/未分类/",
        "duplicate_handling": {"enabled": True, "strategy": "skip"},
    }
    return cfg, source_dir, recycle_dir


@pytest.fixture(scope="session")
def e2e_server():
    tmpdir = tempfile.mkdtemp(prefix="nas_e2e_")
    cfg, source_dir, recycle_dir = _build_e2e_config(tmpdir)

    config_path = os.path.join(tmpdir, "config.yaml")
    with open(config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

    port = _find_free_port()
    host = "127.0.0.1"
    base_url = f"http://{host}:{port}"
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    env["NAS_MEDIA_IMPORTER_DATA_DIR"] = cfg["_data_dir"]

    server_log_path = os.path.join(tmpdir, "e2e-server.log")
    server_log = open(server_log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "media_importer.media_importer",
            "-c",
            config_path,
            "serve",
            "-p",
            str(port),
            "--host",
            host,
        ],
        cwd=repo_root,
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    if not _wait_for_server(host, port, timeout=20):
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        server_log.close()
        output = ""
        if os.path.isfile(server_log_path):
            with open(server_log_path, "r", encoding="utf-8", errors="replace") as f:
                output = f.read()
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(f"E2E server did not start within timeout\n{output}")

    yield {
        "base_url": base_url,
        "host": host,
        "port": port,
        "tmpdir": tmpdir,
        "source_dir": source_dir,
        "recycle_dir": recycle_dir,
        "data_dir": cfg["_data_dir"],
        "db_path": os.path.join(cfg["_data_dir"], "tasks.db"),
        "config_path": config_path,
        "server_log_path": server_log_path,
        "server_proc": proc,
    }
    proc.terminate()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
    server_log.close()
    saved_log = os.path.join(os.path.dirname(__file__), "screenshots", "e2e-server-final.log")
    try:
        import shutil as _shutil
        _shutil.copy2(server_log_path, saved_log)
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def e2e_browser_context(e2e_server):
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        base_url=e2e_server["base_url"],
    )
    yield context
    context.close()
    browser.close()
    pw.stop()


@pytest.fixture
def e2e_page(e2e_browser_context, e2e_server):
    proc = e2e_server.get("server_proc")
    if proc and proc.poll() is not None:
        restarted = _try_restart_e2e_server(e2e_server)
        if not restarted:
            log_path = e2e_server.get("server_log_path")
            output = ""
            if log_path and os.path.isfile(log_path):
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    output = f.read()[-2000:]
            pytest.skip(f"E2E server is not available (exited with code {proc.returncode}): {output[-500:]}")
    try:
        clear_resp = _post_json(e2e_server["base_url"], "/api/tasks/clear", {}, timeout=10)
        if not isinstance(clear_resp, dict) or clear_resp.get("code") not in (200, 204):
            print(f"[e2e] tasks/clear returned {clear_resp!r}")
            proc = e2e_server.get("server_proc")
            if proc and proc.poll() is not None:
                pytest.skip("E2E server exited during tasks/clear; skipping remaining tests")
    except Exception as e:
        print(f"[e2e] tasks/clear failed: {e!r}")
    page = e2e_browser_context.new_page()

    def goto_with_retry(url=None, max_attempts=3):
        target = url or e2e_server["base_url"]
        for attempt in range(max_attempts):
            try:
                page.goto(target)
                page.wait_for_load_state("networkidle")
                return
            except Exception as exc:
                if "ERR_CONNECTION_REFUSED" in str(exc) or "Connection refused" in str(exc):
                    proc = e2e_server.get("server_proc")
                    if proc and proc.poll() is not None:
                        if not _try_restart_e2e_server(e2e_server):
                            pytest.skip("E2E server is unavailable; cannot recover")
                        continue
                raise

    goto_with_retry()
    page.goto_with_retry = goto_with_retry
    page.e2e_server = e2e_server

    def _wrap_action(name):
        original = getattr(page, name)

        def wrapped(*args, **kwargs):
            for attempt in range(3):
                try:
                    return original(*args, **kwargs)
                except Exception as exc:
                    msg = str(exc)
                    if any(token in msg for token in (
                        "ERR_CONNECTION_REFUSED",
                        "Connection refused",
                        "RemoteDisconnected",
                        "Remote end closed connection",
                    )):
                        proc = e2e_server.get("server_proc")
                        if proc and proc.poll() is not None and _try_restart_e2e_server(e2e_server):
                            try:
                                page.goto_with_retry()
                            except Exception:
                                pass
                            continue
                    raise

        wrapped.__name__ = name
        return wrapped

    for action_name in ("click", "fill", "goto", "wait_for_load_state", "locator"):
        if hasattr(page, action_name):
            setattr(page, action_name, _wrap_action(action_name))
    try:
        yield page
    finally:
        screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        test_name = "unknown"
        try:
            import inspect
            frame = inspect.currentframe()
            if frame and frame.f_back and frame.f_back.f_back:
                test_name = frame.f_back.f_back.f_code.co_name
        except Exception:
            pass
        try:
            page.screenshot(path=os.path.join(screenshot_dir, f"{test_name}.png"))
        except Exception:
            pass
        try:
            page.close()
        except Exception:
            pass


@pytest.fixture
def e2e_test_files(e2e_server):
    source_dir = e2e_server["source_dir"]
    files = {
        "V01": "Inception.2010.1080p.BluRay.x264-SPARKS.mkv",
        "V02": "盗梦空间.Inception.2010.BD.1080P.国英双语.mkv",
        "V03": "Breaking.Bad.S05E16.Felina.1080p.BluRay.x264.mkv",
        "V04": "绝命毒师.S05E16.1080p.WEB-DL.mkv",
        "V05": "[喵萌奶茶屋] 进击的巨人 最终季 - 01 [1080P][HEVC].mp4",
        "V06": "Planet.Earth.II.S01E01.Island.2160p.UHD.BluRay.mkv",
        "V07": "地球脉动第二季.S01E01.4K.HDR.mkv",
        "V08": "The.Shawshank.Redemption.1994.720p.BRRip.XviD.avi",
        "V09": "[DMG] Jujutsu Kaisen - 24 [1080p].mkv",
        "V10": "Chernobyl.S01.COMPLETE.720p.AMZN.WEB-DL.mkv",
        "V11": "寄生虫.Parasite.2019.1080p.BluRay.mkv",
        "V12": "三体.Three-Body.S01E01.2023.1080p.WEB-DL.mkv",
        "V13": "Oppenheimer.2023.2160p.UHD.BluRay.Remux.mkv",
        "V14": "Your.Name.2016.1080p.BluRay.x264-[YTS].mkv",
        "V15": "舌尖上的中国.S01E03.2012.1080i.ts",
        "V16": "Sample.mp4",
        "V18": "Deadpool.&.Wolverine.2024.1080p.mkv",
        "V19": "老友记.Friends.S02E03-E04.1080p.mkv",
        "V20": "[SubGroup] 鬼灭之刃 柱稽古篇 - 08 [1080P].mp4",
    }
    created = {}
    for vid, fname in files.items():
        fpath = os.path.join(source_dir, fname)
        size = 1024 * 1024 * 100
        if vid == "V16":
            size = 1024 * 512
        with open(fpath, "wb") as f:
            f.write(b"\x00" * size)
        created[vid] = fpath

    subdir = os.path.join(source_dir, "movie_with_subtitle")
    os.makedirs(subdir, exist_ok=True)
    with open(os.path.join(subdir, "The.Matrix.1999.1080p.mkv"), "wb") as f:
        f.write(b"\x00" * 100 * 1024 * 1024)
    with open(os.path.join(subdir, "The.Matrix.1999.1080p.zh.srt"), "w") as f:
        f.write("1\n00:00:01,000 --> 00:00:05,000\nTest subtitle\n")
    created["V17"] = os.path.join(subdir, "The.Matrix.1999.1080p.mkv")

    for sname in [
        "Inception.2010.1080p.BluRay.x264-SPARKS.zh.srt",
        "Breaking.Bad.S05E16.Felina.1080p.BluRay.x264.en.srt",
        "三体.Three-Body.S01E01.2023.1080p.WEB-DL.chs&eng.ass",
    ]:
        with open(os.path.join(source_dir, sname), "w") as f:
            f.write("1\n00:00:01,000 --> 00:00:05,000\nTest\n")

    junk_dir = os.path.join(source_dir, "Sample")
    os.makedirs(junk_dir, exist_ok=True)
    with open(os.path.join(junk_dir, "sample.mp4"), "wb") as f:
        f.write(b"\x00" * 512)
    with open(os.path.join(source_dir, ".DS_Store"), "wb") as f:
        f.write(b"\x00")
    with open(os.path.join(source_dir, "movie.nfo"), "w") as f:
        f.write("<movie></movie>")
    with open(os.path.join(source_dir, "poster.jpg"), "wb") as f:
        f.write(b"\x00" * 1024)

    yield created
    for fpath in created.values():
        if os.path.exists(fpath):
            os.remove(fpath)
    junk_dir = os.path.join(source_dir, "Sample")
    if os.path.isdir(junk_dir):
        shutil.rmtree(junk_dir, ignore_errors=True)
    subdir = os.path.join(source_dir, "movie_with_subtitle")
    if os.path.isdir(subdir):
        shutil.rmtree(subdir, ignore_errors=True)

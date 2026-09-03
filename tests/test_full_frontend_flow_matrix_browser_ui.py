"""真实前端文件全流程矩阵。

普通场景必须从 Chromium 点击“立即扫描”进入业务流程；测试只在外部
Provider 边界注入确定性结果。文件复制、目标冲突、回收、来源处置、
SQLite 和 HTTP 均使用正式实现。每个场景保存文件树、SHA-256、任务状态、
截图和浏览器错误，便于产品验收复核。
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import signal
import socket
import sqlite3
import time
import urllib.error
import urllib.request
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from playwright.sync_api import Page, sync_playwright

from media_importer.features.providers import (
    DimensionMapping,
    Genre,
    MediaDetails,
    MetadataProvider,
    SearchItem,
    SearchResult,
    register_provider,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "output" / "full-frontend-flow-matrix"


@register_provider
class MatrixFixtureProvider(MetadataProvider):
    """Deterministic external boundary; all file-flow code remains real."""

    provider_type = "matrix_fixture"
    display_name = "本地验收 Provider"

    def __init__(self, config: dict):
        self.config = config

    @staticmethod
    def _identity(query: str, year: int | None, media_type: str | None) -> tuple[str, int, str]:
        title = " ".join(str(query).replace(".", " ").split()) or "Matrix Movie"
        resolved_type = "tv" if media_type == "tv" or "Show" in title else "movie"
        resolved_year = int(year or (2025 if resolved_type == "tv" else 2026))
        return title, resolved_year, resolved_type

    def search(
        self,
        query: str,
        year: int | None = None,
        media_type: str | None = None,
    ) -> SearchResult:
        normalized_query = " ".join(str(query).replace(".", " ").split())
        if normalized_query.casefold() in {"00001", "video"}:
            return SearchResult(items=[], total_results=0)
        if normalized_query.casefold() == "the office":
            items = [
                SearchItem(
                    provider_type=self.provider_type,
                    item_id=f"tv-{item_year}-The Office",
                    title="The Office",
                    original_title="The Office",
                    year=item_year,
                    media_type="tv",
                    poster_url="",
                    vote_average=8.5,
                    raw_data={"vote_count": 5000, "popularity": popularity},
                )
                for item_year, popularity in ((2005, 100), (2001, 80))
            ]
            return SearchResult(items=items, total_results=len(items))
        special = {
            "double vision": ("双瞳", "雙瞳", 2002, "movie"),
            "双瞳": ("双瞳", "雙瞳", 2002, "movie"),
            "权力的游戏": ("权力的游戏", "Game of Thrones", 2011, "tv"),
        }.get(normalized_query.casefold())
        if special:
            title, original_title, resolved_year, resolved_type = special
            item = SearchItem(
                provider_type=self.provider_type,
                item_id=f"{resolved_type}-{resolved_year}-{title}",
                title=title,
                original_title=original_title,
                year=resolved_year,
                media_type=resolved_type,
                poster_url="",
                vote_average=8.8,
                raw_data={"vote_count": 5000, "popularity": 100},
            )
            return SearchResult(items=[item], total_results=1)
        title, resolved_year, resolved_type = self._identity(query, year, media_type)
        item = SearchItem(
            provider_type=self.provider_type,
            item_id=f"{resolved_type}-{resolved_year}-{title}",
            title=title,
            original_title=title,
            year=resolved_year,
            media_type=resolved_type,
            poster_url="",
            vote_average=8.8,
            raw_data={"vote_count": 5000, "popularity": 100},
        )
        return SearchResult(items=[item], total_results=1)

    def get_details(self, item_id: str, media_type: str) -> MediaDetails:
        _, year_text, title = item_id.split("-", 2)
        return MediaDetails(
            provider_type=self.provider_type,
            item_id=item_id,
            media_type=media_type,
            title=title,
            original_title=title,
            year=int(year_text),
            genres=[Genre(id="18", name="剧情")],
            overview="本地前端全流程验收固定资料",
            vote_average=8.8,
            origin_country=["CN"],
            original_language="zh",
            adult=False,
            tagline="",
            poster_url="",
            raw_data={
                "genres": [{"id": 18, "name": "剧情"}],
                "origin_country": ["CN"],
                "original_language": "zh",
                "adult": False,
            },
        )

    def get_genres(self, media_type: str | None = None):
        return {"genres": [{"id": 18, "name": "剧情"}]}

    def test_connection(self) -> bool:
        return True

    def map_dimensions(
        self,
        dim_configs: list,
        details: MediaDetails,
    ) -> list[DimensionMapping]:
        values = {
            "documentary": "false",
            "restricted_level": "13-16",
            "content_sensitivity": "normal",
            "animation": "false",
            "region": "other",
            "broad_genre": "drama",
        }
        return [
            DimensionMapping(
                name=item["name"],
                value=values.get(item["name"]),
                source_reliability=1.0,
                source=self.provider_type,
            )
            for item in dim_configs
            if item.get("name") in values
        ]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _server_process(config_path: str, data_dir: str, host: str, port: int, fault: str = ""):
    from media_importer.api.handler import start_server
    from media_importer.features.configuration import load_config

    config = load_config(config_path)
    config["_data_dir"] = data_dir
    config["_config_path"] = config_path
    context = nullcontext()
    if fault == "exit_after_commit":
        import media_importer.infrastructure.db as database

        original_update = database.update_task

        def exit_after_commit_update(conn, task_id, **fields):
            result = original_update(conn, task_id, **fields)
            if fields.get("bundle_state") == "COMMITTED":
                os._exit(73)
            return result

        context = patch.object(database, "update_task", exit_after_commit_update)
    elif fault == "exit_during_copy":
        from media_importer.features.import_flow.services import file_operations

        def exit_during_copy(source, destination, **_kwargs):
            partial = destination + ".copying"
            os.makedirs(os.path.dirname(partial), exist_ok=True)
            with open(source, "rb") as reader, open(partial, "xb") as writer:
                writer.write(reader.read(1024 * 1024))
                writer.flush()
                os.fsync(writer.fileno())
            os._exit(74)

        context = patch.object(file_operations, "verified_copy", exit_during_copy)
    elif fault == "slow_copy_for_external_sigkill":
        from media_importer.features.import_flow.services import file_operations

        original_verified_copy = file_operations.verified_copy

        def slow_verified_copy(source, destination, **kwargs):
            original_phase_callback = kwargs.get("phase_callback")

            def slow_phase_callback(phase, completed, total):
                if original_phase_callback:
                    original_phase_callback(phase, completed, total)
                if phase == "transfer" and 0 < completed < total:
                    time.sleep(0.04)

            kwargs["phase_callback"] = slow_phase_callback
            return original_verified_copy(source, destination, **kwargs)

        context = patch.object(file_operations, "verified_copy", slow_verified_copy)
    with context:
        start_server(host, port, config)


def _wait_server(url: str, process, timeout: float = 12) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process is not None and not process.is_alive():
            raise RuntimeError(f"服务提前退出，exit={process.exitcode}")
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("本地矩阵服务未在预期时间启动")


def _json_request(url: str, path: str) -> dict:
    try:
        with urllib.request.urlopen(f"{url}{path}", timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError):
        return {}


def _tasks(url: str) -> list[dict]:
    return (_json_request(url, "/api/tasks?limit=100").get("data") or {}).get("tasks", [])


def _offline_tasks(data_dir: Path) -> list[dict]:
    """Read crash evidence without starting recovery or mutating the database."""
    connection = sqlite3.connect(data_dir / "tasks.db")
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT task_id, source_filename, source_path, status, stage,
                      percentage, bundle_state, bundle_committed,
                      bundle_manifest, import_video_path, error_message
                 FROM tasks ORDER BY id"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _wait_task(url: str, filename: str, predicate, timeout: float = 18) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        for task in _tasks(url):
            if task.get("source_filename") == filename:
                last = task
                if predicate(task):
                    return task
        time.sleep(0.15)
    raise AssertionError(f"任务未到达预期状态: {filename}; last={last}")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(root: Path) -> list[dict]:
    if not root.exists():
        return []
    result = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root))):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            result.append({"path": relative, "type": "symlink", "target": os.readlink(path)})
        elif path.is_dir():
            result.append({"path": relative, "type": "directory"})
        elif path.is_file():
            result.append({
                "path": relative,
                "type": "file",
                "size": path.stat().st_size,
                "sha256": _hash(path),
            })
    return result


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_media(path: Path, marker: str, size_mb: int = 2) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    block = (marker.encode("utf-8") + b"\0") * 1024
    with path.open("wb") as handle:
        remaining = size_mb * 1024 * 1024
        while remaining > 0:
            chunk = block[: min(len(block), remaining)]
            handle.write(chunk)
            remaining -= len(chunk)
    return _hash(path)


class Scenario:
    def __init__(
        self,
        run_dir: Path,
        scenario_id: str,
        *,
        source_mode: str = "preserve_all",
        disposal_mode: str = "local_recycle",
        rules: bool = True,
        fault: str = "",
    ):
        self.id = scenario_id
        self.root = run_dir / scenario_id
        self.evidence = self.root / "evidence"
        self.paths = {
            name: self.root / name
            for name in ("source", "library", "recycle", "logs", "resources", "data")
        }
        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)
        rule_yaml = ""
        if rules:
            rule_yaml = """
path_rules:
  - name: 电影规则
    conditions:
      media_type: movie
    library_root_id: main
    template: 电影/{title_cn} ({year})
  - name: 剧集规则
    conditions:
      media_type: tv
    library_root_id: main
    template: 剧集/{title_cn}/Season {season}
"""
        self.config_path = self.root / "config.yaml"
        self.config_path.write_text(
            f"""source_dir: {self.paths['source']}
log_dir: {self.paths['logs']}
resource_dir: {self.paths['resources']}
library_roots:
  - id: main
    name: 主片库
    path: {self.paths['library']}
    enabled: true
default_library_root_id: main
fallback_library_root_id: main
fallback_dir: 待整理
video_extensions: [.mkv, .mp4, .m2ts]
subtitle_extensions: [.srt, .ass]
media_candidate_filter:
  enabled: true
  small_video_max_mb: 1
  main_video_min_mb: 2
  max_size_ratio: 0.1
filename_templates:
  movie: "{{title_cn}}.{{year}}.{{ext}}"
  tv: "{{title_cn}}.{{year}}.S{{season:02d}}E{{episode:02d}}.{{ext}}"
  subtitle: "{{video_filename}}.{{lang}}.{{ext}}"
source_policy:
  mode: {source_mode}
  disposal_mode: {disposal_mode}
  recycle_dir: {self.paths['recycle']}
  unit_settle_seconds: 0
file_watcher:
  enabled: false
metadata:
  providers:
    - type: matrix_fixture
      enabled: true
manual_review:
  enabled: false
dedup:
  enabled: true
{rule_yaml}
""",
            encoding="utf-8",
        )
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.fault = fault
        self.process = None

    def start(self, fault: str | None = None) -> None:
        # Chromium starts helper threads.  Forking the next scenario from that
        # process can crash SQLite on macOS, so each service must use a clean
        # interpreter.  This also matches fnOS' independent service process
        # more closely than inheriting pytest/Playwright state.
        ctx = multiprocessing.get_context("spawn")
        self.process = ctx.Process(
            target=_server_process,
            args=(
                str(self.config_path),
                str(self.paths["data"]),
                "127.0.0.1",
                self.port,
                self.fault if fault is None else fault,
            ),
        )
        self.process.start()
        _wait_server(self.url, self.process)

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=5)

    def snapshot(self, name: str, task_id: str = "", browser: dict | None = None) -> None:
        payload = {
            role: _inventory(self.paths[role])
            for role in ("source", "library", "recycle")
        }
        _write_json(self.evidence / f"{name}-files.json", payload)
        if task_id:
            _write_json(
                self.evidence / f"{name}-task.json",
                _json_request(self.url, f"/api/tasks/{task_id}"),
            )
        if browser is not None:
            _write_json(self.evidence / f"{name}-browser.json", browser)


def _open_tasks(page: Page) -> None:
    page.locator(".bottom-nav [data-nav='tasks']").click()
    page.wait_for_selector("#task-list")


def _scan(page: Page) -> None:
    page.locator("button[data-action='scan']").click()


def _refresh(page: Page) -> None:
    button = page.get_by_role("button", name="刷新任务列表")
    if button.count():
        button.click()


def _open_task(page: Page, task_id: str) -> None:
    _refresh(page)
    page.locator(f"[data-task-action='view-task'][data-task-id='{task_id}']").first.click()
    page.wait_for_selector(".cinema-modal")


def _wait_process_exit(process, expected: int, timeout: float = 15) -> None:
    process.join(timeout=timeout)
    assert not process.is_alive(), "故障注入后服务进程未退出"
    assert process.exitcode == expected


def _scenario_browser(browser, scenario: Scenario):
    errors: list[str] = []
    bad_responses: list[str] = []
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "response",
        lambda response: bad_responses.append(f"{response.status} {response.url}")
        if response.status >= 500
        else None,
    )
    page.goto(scenario.url)
    page.wait_for_load_state("networkidle")
    return page, errors, bad_responses


def _find_file(inventory: list[dict], suffix: str) -> dict:
    matches = [item for item in inventory if item.get("type") == "file" and item["path"].endswith(suffix)]
    assert len(matches) == 1, (suffix, matches)
    return matches[0]


@pytest.mark.ui
def test_local_customer_full_frontend_file_flow_matrix():
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_dir = EVIDENCE_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    summary: list[dict] = []
    failures: list[str] = []

    def execute(scenario_id: str, callback, **options):
        scenario = Scenario(run_dir, scenario_id, **options)
        browser_state = {"page_errors": [], "http_5xx": []}
        scenario.snapshot("before")
        try:
            scenario.start()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page, page_errors, bad_responses = _scenario_browser(browser, scenario)
                try:
                    callback(scenario, page)
                    page.set_viewport_size({"width": 390, "height": 844})
                    overflow = page.evaluate(
                        "() => document.documentElement.scrollWidth - window.innerWidth"
                    )
                    assert overflow <= 0
                finally:
                    browser_state = {"page_errors": page_errors, "http_5xx": bad_responses}
                    page.close()
                    browser.close()
            assert browser_state == {"page_errors": [], "http_5xx": []}
            summary.append({"id": scenario_id, "status": "PASS"})
        except Exception as error:  # keep remaining evidence and scenarios running
            failures.append(f"{scenario_id}: {error}")
            summary.append({"id": scenario_id, "status": "FAIL", "error": repr(error)})
        finally:
            task_rows = _tasks(scenario.url) if scenario.process and scenario.process.is_alive() else []
            task_id = task_rows[0].get("task_id", "") if task_rows else ""
            scenario.snapshot("after", task_id=task_id, browser=browser_state)
            scenario.stop()
            _write_json(run_dir / "matrix-summary.json", summary)

    def f01(scenario: Scenario, page: Page):
        source = scenario.paths["source"] / "MatrixMovie.2026.1080p.mkv"
        source_hash = _write_media(source, "F01-new-movie")
        scenario.snapshot("prepared")
        _scan(page)
        task = _wait_task(
            scenario.url, source.name,
            lambda item: item.get("status") == "SUCCESS" and item.get("stage") == "DONE",
        )
        _open_tasks(page)
        _open_task(page, task["task_id"])
        page.screenshot(path=str(scenario.evidence / "task-complete.png"), full_page=False)
        after = _inventory(scenario.paths["library"])
        imported = _find_file(after, "MatrixMovie.2026.mkv")
        assert imported["sha256"] == source_hash
        assert source.is_file() and _hash(source) == source_hash

    execute("F01-movie-preserve", f01)

    def f02(scenario: Scenario, page: Page):
        unit = scenario.paths["source"] / "MatrixShow.S01E02"
        source = unit / "MatrixShow.2025.S01E02.1080p.mkv"
        subtitle_zh = unit / "MatrixShow.2025.S01E02.1080p.zh.srt"
        subtitle_en = unit / "MatrixShow.2025.S01E02.1080p.en.ass"
        video_hash = _write_media(source, "F02-tv-video")
        subtitle_zh.parent.mkdir(parents=True, exist_ok=True)
        subtitle_zh.write_text("F02 中文字幕", encoding="utf-8")
        subtitle_en.write_text("F02 English subtitle", encoding="utf-8")
        subtitle_hashes = {_hash(subtitle_zh), _hash(subtitle_en)}
        scenario.snapshot("prepared")
        _scan(page)
        task = _wait_task(scenario.url, source.name, lambda item: item.get("status") == "SUCCESS")
        _open_tasks(page)
        _open_task(page, task["task_id"])
        page.screenshot(path=str(scenario.evidence / "tv-subtitle-complete.png"), full_page=False)
        library = _inventory(scenario.paths["library"])
        video = _find_file(library, "MatrixShow.2025.S01E02.mkv")
        assert video["sha256"] == video_hash
        imported_subtitles = [item["sha256"] for item in library if item.get("type") == "file" and item["path"].endswith((".srt", ".ass"))]
        assert set(imported_subtitles) == subtitle_hashes

    execute("F02-tv-subtitle-bundle", f02)

    def f03(scenario: Scenario, page: Page):
        source = scenario.paths["source"] / "FallbackMovie.2026.mkv"
        source_hash = _write_media(source, "F03-fallback")
        scenario.snapshot("prepared")
        _scan(page)
        task = _wait_task(scenario.url, source.name, lambda item: item.get("stage") == "AWAIT_REVIEW")
        assert _inventory(scenario.paths["library"]) == []
        _open_tasks(page)
        _open_task(page, task["task_id"])
        page.get_by_role("button", name="确认放入待整理区").click()
        final = _wait_task(scenario.url, source.name, lambda item: item.get("status") == "SUCCESS")
        assert final.get("organization_status") == "FALLBACK_PENDING"
        _open_task(page, final["task_id"])
        page.screenshot(path=str(scenario.evidence / "fallback-accepted.png"), full_page=False)
        imported = _find_file(_inventory(scenario.paths["library"]), "FallbackMovie.2026.mkv")
        assert imported["sha256"] == source_hash

    execute("F03-fallback-explicit-accept", f03, rules=False)

    def conflict_flow(action: str, scenario: Scenario, page: Page):
        source = scenario.paths["source"] / "ConflictMovie.2026.mkv"
        new_hash = _write_media(source, f"{scenario.id}-new")
        existing = scenario.paths["library"] / "电影" / "ConflictMovie (2026)" / "ConflictMovie.2026.mkv"
        old_hash = _write_media(existing, f"{scenario.id}-old")
        scenario.snapshot("prepared")
        _scan(page)
        task = _wait_task(
            scenario.url, source.name,
            lambda item: item.get("stage") == "AWAIT_REVIEW" and bool(item.get("dedup_result")),
        )
        _open_tasks(page)
        _open_task(page, task["task_id"])
        if action == "keep":
            page.locator("#btn-conflict-keep-existing").click()
        elif action == "both":
            page.locator("#btn-conflict-keep-both").click()
        else:
            page.locator("#btn-conflict-replace").click()
            confirm_modal = page.locator(".cinema-modal").last
            assert "确认替换片库文件" in confirm_modal.inner_text()
            confirm_modal.get_by_role("button", name="确认", exact=True).click()
        final = _wait_task(
            scenario.url, source.name,
            lambda item: item.get("status") in {"SUCCESS", "SKIPPED"},
        )
        _open_task(page, final["task_id"])
        page.screenshot(path=str(scenario.evidence / f"conflict-{action}.png"), full_page=False)
        library = _inventory(scenario.paths["library"])
        if action == "keep":
            assert final["status"] == "SKIPPED"
            assert _find_file(library, "ConflictMovie.2026.mkv")["sha256"] == old_hash
            assert source.is_file() and _hash(source) == new_hash
        elif action == "both":
            hashes = {item["sha256"] for item in library if item.get("type") == "file" and item["path"].endswith(".mkv")}
            assert hashes == {old_hash, new_hash}
            assert source.is_file()
        else:
            assert _find_file(library, "ConflictMovie.2026.mkv")["sha256"] == new_hash
            recycle_hashes = {item["sha256"] for item in _inventory(scenario.paths["recycle"]) if item.get("type") == "file"}
            assert old_hash in recycle_hashes

    execute("F04-conflict-keep-existing", lambda s, p: conflict_flow("keep", s, p))
    execute("F05-conflict-keep-both", lambda s, p: conflict_flow("both", s, p))
    execute("F06-conflict-replace", lambda s, p: conflict_flow("replace", s, p))

    def source_disposal(scenario: Scenario, page: Page, permanent: bool):
        unit = scenario.paths["source"] / ("PermanentUnit" if permanent else "RecycleUnit")
        source = unit / ("PermanentMovie.2026.mkv" if permanent else "RecycleMovie.2026.mkv")
        source_hash = _write_media(source, f"{scenario.id}-source")
        note = unit / "release-note.txt"
        note.write_text("whole source unit member", encoding="utf-8")
        scenario.snapshot("prepared")
        _scan(page)
        task = _wait_task(scenario.url, source.name, lambda item: item.get("status") == "SUCCESS")
        _open_tasks(page)
        _open_task(page, task["task_id"])
        page.screenshot(path=str(scenario.evidence / "source-disposition.png"), full_page=False)
        assert not unit.exists()
        target = _find_file(_inventory(scenario.paths["library"]), source.name)
        assert target["sha256"] == source_hash
        recycled = _inventory(scenario.paths["recycle"])
        if permanent:
            assert not [item for item in recycled if item.get("type") == "file"]
        else:
            assert source_hash in {item.get("sha256") for item in recycled}

    execute(
        "F07-source-unit-local-recycle",
        lambda s, p: source_disposal(s, p, False),
        source_mode="recycle_source_unit",
        disposal_mode="local_recycle",
    )
    execute(
        "F08-source-unit-permanent-delete",
        lambda s, p: source_disposal(s, p, True),
        source_mode="recycle_source_unit",
        disposal_mode="permanent_delete",
    )

    def f09(scenario: Scenario, page: Page):
        source = scenario.paths["source"] / "InterruptedCopy.2026.mkv"
        source_hash = _write_media(source, "F09-interrupted-copy", size_mb=8)
        scenario.snapshot("prepared")
        _scan(page)
        _wait_process_exit(scenario.process, 74)
        scenario.snapshot("interrupted")
        _write_json(
            scenario.evidence / "interrupted-task.json",
            {"tasks": _offline_tasks(scenario.paths["data"])},
        )
        partials = [
            item for item in _inventory(scenario.paths["library"])
            if item.get("type") == "file" and item["path"].endswith(".copying")
        ]
        assert len(partials) == 1
        assert source.is_file() and _hash(source) == source_hash

        scenario.start(fault="")
        page.goto(scenario.url)
        page.wait_for_load_state("networkidle")
        failed = _wait_task(
            scenario.url,
            source.name,
            lambda item: item.get("status") == "FAILED"
            and item.get("bundle_state") == "ROLLED_BACK",
        )
        assert not [
            item for item in _inventory(scenario.paths["library"])
            if item.get("type") == "file"
        ]
        _open_tasks(page)
        _open_task(page, failed["task_id"])
        page.screenshot(
            path=str(scenario.evidence / "copy-interrupted-recovered.png"),
            full_page=False,
        )
        page.locator(".cinema-modal").last.get_by_text("关闭", exact=True).click()
        page.locator(
            f"[data-task-action='retry-task'][data-task-id='{failed['task_id']}']"
        ).click()
        retry_modal = page.locator(".cinema-modal").last
        assert "重试任务" in retry_modal.inner_text()
        retry_modal.get_by_role("button", name="确认", exact=True).click()
        completed = _wait_task(
            scenario.url,
            source.name,
            lambda item: item.get("status") == "SUCCESS",
        )
        _open_task(page, completed["task_id"])
        page.screenshot(
            path=str(scenario.evidence / "copy-retry-complete.png"),
            full_page=False,
        )
        imported = _find_file(
            _inventory(scenario.paths["library"]),
            "InterruptedCopy.2026.mkv",
        )
        assert imported["sha256"] == source_hash
        assert source.is_file() and _hash(source) == source_hash

    execute("F09-copy-interrupt-and-ui-retry", f09, fault="exit_during_copy")

    def f10(scenario: Scenario, page: Page):
        source = scenario.paths["source"] / "CommittedCrash.2026.mkv"
        source_hash = _write_media(source, "F10-committed-crash")
        scenario.snapshot("prepared")
        _scan(page)
        _wait_process_exit(scenario.process, 73)
        scenario.snapshot("interrupted")
        _write_json(
            scenario.evidence / "interrupted-task.json",
            {"tasks": _offline_tasks(scenario.paths["data"])},
        )
        imported = _find_file(
            _inventory(scenario.paths["library"]),
            "CommittedCrash.2026.mkv",
        )
        assert imported["sha256"] == source_hash

        scenario.start(fault="")
        page.goto(scenario.url)
        page.wait_for_load_state("networkidle")
        recovered = _wait_task(
            scenario.url,
            source.name,
            lambda item: item.get("status") == "SUCCESS"
            and item.get("bundle_state") == "COMMITTED_RECOVERED",
        )
        _open_tasks(page)
        _open_task(page, recovered["task_id"])
        page.screenshot(
            path=str(scenario.evidence / "committed-crash-recovered.png"),
            full_page=False,
        )
        assert source.is_file() and _hash(source) == source_hash
        assert recovered.get("source_disposition") == "kept"

    execute("F10-commit-crash-auto-recovery", f10, fault="exit_after_commit")

    def f11(scenario: Scenario, page: Page):
        source = scenario.paths["source"] / "ChangedTargetCrash.2026.mkv"
        source_hash = _write_media(source, "F11-original-source")
        scenario.snapshot("prepared")
        _scan(page)
        _wait_process_exit(scenario.process, 73)
        target = (
            scenario.paths["library"]
            / "电影"
            / "ChangedTargetCrash (2026)"
            / "ChangedTargetCrash.2026.mkv"
        )
        assert target.is_file()
        target.write_bytes(b"F11-target-was-changed-after-crash")
        changed_hash = _hash(target)
        assert changed_hash != source_hash
        scenario.snapshot("interrupted-and-mutated")
        _write_json(
            scenario.evidence / "interrupted-task.json",
            {"tasks": _offline_tasks(scenario.paths["data"])},
        )

        scenario.start(fault="")
        page.goto(scenario.url)
        page.wait_for_load_state("networkidle")
        review = _wait_task(
            scenario.url,
            source.name,
            lambda item: item.get("status") == "FAILED"
            and item.get("bundle_state") == "RECOVERY_REQUIRED",
        )
        _open_tasks(page)
        _open_task(page, review["task_id"])
        modal = page.locator(".cinema-modal").last
        assert "请人工检查后处理" in modal.inner_text()
        page.screenshot(
            path=str(scenario.evidence / "changed-target-manual-review.png"),
            full_page=False,
        )
        assert source.is_file() and _hash(source) == source_hash
        assert target.is_file() and _hash(target) == changed_hash

    execute("F11-changed-target-manual-recovery", f11, fault="exit_after_commit")

    def f12(scenario: Scenario, page: Page):
        source = scenario.paths["source"] / "ExternalSigkill.2026.mkv"
        source_hash = _write_media(source, "F12-external-sigkill", size_mb=64)
        source_size = source.stat().st_size
        scenario.snapshot("prepared")
        _scan(page)

        deadline = time.time() + 20
        partial = None
        partial_size = 0
        while time.time() < deadline:
            candidates = list(scenario.paths["library"].rglob("*.copying"))
            if len(candidates) == 1:
                candidate_size = candidates[0].stat().st_size
                if 0 < candidate_size < source_size:
                    partial = candidates[0]
                    partial_size = candidate_size
                    break
            time.sleep(0.02)
        assert partial is not None, "未命中真实复制中的 .copying 窗口"

        process = scenario.process
        assert process is not None and process.is_alive()
        killed_pid = process.pid
        assert isinstance(killed_pid, int) and killed_pid > 1
        os.kill(killed_pid, signal.SIGKILL)
        _wait_process_exit(process, -signal.SIGKILL)
        scenario.snapshot("sigkill-interrupted")
        _write_json(
            scenario.evidence / "sigkill.json",
            {
                "pid": killed_pid,
                "signal": "SIGKILL",
                "exitcode": process.exitcode,
                "partial_path": str(partial.relative_to(scenario.paths["library"])),
                "partial_size": partial_size,
                "source_size": source_size,
            },
        )
        _write_json(
            scenario.evidence / "sigkill-task.json",
            {"tasks": _offline_tasks(scenario.paths["data"])},
        )
        assert partial.is_file()
        assert 0 < partial.stat().st_size < source_size
        assert source.is_file() and _hash(source) == source_hash

        scenario.start(fault="")
        page.goto(scenario.url)
        page.wait_for_load_state("networkidle")
        failed = _wait_task(
            scenario.url,
            source.name,
            lambda item: item.get("status") == "FAILED"
            and item.get("bundle_state") == "ROLLED_BACK",
        )
        assert not [
            item for item in _inventory(scenario.paths["library"])
            if item.get("type") == "file"
        ]
        _open_tasks(page)
        _open_task(page, failed["task_id"])
        modal = page.locator(".cinema-modal").last
        assert "失败" in modal.inner_text()
        page.screenshot(
            path=str(scenario.evidence / "sigkill-recovered.png"),
            full_page=False,
        )
        modal.get_by_text("关闭", exact=True).click()
        page.locator(
            f"[data-task-action='retry-task'][data-task-id='{failed['task_id']}']"
        ).click()
        retry_modal = page.locator(".cinema-modal").last
        assert "重试任务" in retry_modal.inner_text()
        retry_modal.get_by_role("button", name="确认", exact=True).click()
        completed = _wait_task(
            scenario.url,
            source.name,
            lambda item: item.get("status") == "SUCCESS",
            timeout=30,
        )
        _open_task(page, completed["task_id"])
        page.screenshot(
            path=str(scenario.evidence / "sigkill-retry-complete.png"),
            full_page=False,
        )
        imported = _find_file(
            _inventory(scenario.paths["library"]),
            "ExternalSigkill.2026.mkv",
        )
        assert imported["sha256"] == source_hash
        assert source.is_file() and _hash(source) == source_hash

    execute(
        "F12-external-sigkill-copy-recovery",
        f12,
        fault="slow_copy_for_external_sigkill",
    )

    def f13(scenario: Scenario, page: Page):
        source_root = scenario.paths["source"]
        double_vision_folder = source_root / (
            "【首发于高清影视之家 www.BBQDDQ.com】"
            "双瞳[国粤英多音轨+简繁字幕].Double.Vision.2002.UNRATED."
            "BluRay.1080p.2Audio.DTS-HD.MA.2.0.x265.10bit-ALT"
        )
        expected_success = [
            source_root / "Inception.2010.1080p.BluRay.x265.mkv",
            double_vision_folder
            / "Double.Vision.2002.UNRATED.BluRay.1080p.2Audio."
            "DTS-HD.MA.2.0.x265.10bit-ALT.mkv",
            source_root
            / "随手建的无关目录"
            / "Interstellar.2014.2160p.UHD.BluRay.REMUX.HEVC.TrueHD.Atmos.mkv",
            source_root / "权力的游戏" / "Season 01" / "S01E01.mkv",
            source_root / "Blade.Runner.1982" / "BDMV" / "STREAM" / "00001.m2ts",
            source_root / "合集目录" / "Avatar.2009.1080p.mkv",
            source_root / "合集目录" / "Titanic.1997.1080p.mkv",
            source_root / "Dune.2021" / "Dune.1984.1080p.mkv",
            source_root
            / "动漫下载"
            / "[Lilith-Raws] 葬送的芙莉莲 - 01 "
            "[Baha][WEB-DL][1080p][AVC AAC][CHT][MP4].mp4",
        ]
        expected_review = [
            source_root / "downloads" / "video.mkv",
            source_root / "Arrival.2016" / "Interview.mkv",
            source_root / "The.Office.mkv",
        ]
        for index, path in enumerate(expected_success + expected_review, start=1):
            _write_media(path, f"F13-{index}", size_mb=3)

        ignored_videos = [
            double_vision_folder / "点击进入www.example.com下载更多电影.mp4",
            source_root / "Blade.Runner.1982" / "BDMV" / "STREAM" / "00002.m2ts",
            source_root / "Blade.Runner.1982" / "BDMV" / "STREAM" / "00003.m2ts",
        ]
        for index, path in enumerate(ignored_videos, start=1):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"F13-ignored-{index}".encode("utf-8"))
        incomplete = source_root / "尚未完成下载" / "Movie.2026.mkv.part"
        incomplete.parent.mkdir(parents=True, exist_ok=True)
        incomplete.write_bytes(b"unfinished")

        scenario.snapshot("prepared")
        _scan(page)

        success_tasks = {
            path.name: _wait_task(
                scenario.url,
                path.name,
                lambda item: item.get("status") == "SUCCESS",
                timeout=30,
            )
            for path in expected_success
        }
        review_tasks = {
            path.name: _wait_task(
                scenario.url,
                path.name,
                lambda item: item.get("stage") == "AWAIT_REVIEW",
                timeout=30,
            )
            for path in expected_review
        }
        all_tasks = _tasks(scenario.url)
        task_names = {item.get("source_filename") for item in all_tasks}
        assert len(all_tasks) == len(expected_success) + len(expected_review)
        assert not ({path.name for path in ignored_videos} & task_names)
        assert incomplete.name not in task_names

        double_task = success_tasks[next(
            name for name in success_tasks if name.startswith("Double.Vision.2002")
        )]
        double_trace = double_task["scrape_result"]["match_trace"]
        assert double_trace["provider_id"] == "movie-2002-双瞳"
        assert double_trace["selected_candidate"]["why_selected"] == "evidence_converged"
        assert {item["source"] for item in double_trace["identity_evidence"]["signals"]} == {
            "file", "folder",
        }

        root_trace = success_tasks["Inception.2010.1080p.BluRay.x265.mkv"][
            "scrape_result"
        ]["match_trace"]["identity_evidence"]
        assert [item["source"] for item in root_trace["signals"]] == ["file"]
        assert root_trace["ignored_directories"][0]["reason"] == "视频直接位于来源根目录"

        unrelated_trace = success_tasks[
            "Interstellar.2014.2160p.UHD.BluRay.REMUX.HEVC.TrueHD.Atmos.mkv"
        ]["scrape_result"]["match_trace"]
        assert unrelated_trace["provider_title"] == "Interstellar"
        assert not any(
            step.get("name") == "文件夹辅助检索"
            for step in unrelated_trace["trace"]
        )

        tv_trace = success_tasks["S01E01.mkv"]["scrape_result"]["match_trace"]
        assert tv_trace["provider_title"] == "权力的游戏"
        assert tv_trace["selected_candidate"]["media_type"] == "tv"
        assert tv_trace["selected_candidate"]["why_selected"] == "folder_rescue"

        bluray_trace = success_tasks["00001.m2ts"]["scrape_result"]["match_trace"]
        assert bluray_trace["provider_title"] == "Blade Runner"
        assert bluray_trace["selected_candidate"]["why_selected"] == "folder_rescue"

        for name in ("Avatar.2009.1080p.mkv", "Titanic.1997.1080p.mkv"):
            ignored = success_tasks[name]["scrape_result"]["match_trace"][
                "identity_evidence"
            ]["ignored_directories"]
            assert any("多个视频" in item["reason"] for item in ignored)

        dune_trace = success_tasks["Dune.1984.1080p.mkv"]["scrape_result"]["match_trace"]
        assert dune_trace["selected_candidate"]["year"] == 1984
        assert dune_trace["provider_title"] == "Dune"

        generic_trace = review_tasks["video.mkv"]["scrape_result"]["match_trace"]
        assert any(
            item["reason"] == "通用目录名不作为片名"
            for item in generic_trace["identity_evidence"]["ignored_directories"]
        )
        conflict_trace = review_tasks["Interview.mkv"]["scrape_result"]["match_trace"]
        assert any(
            item["code"] == "CONFLICTING_INFO"
            for item in conflict_trace["concerns"]
        )
        office_trace = review_tasks["The.Office.mkv"]["scrape_result"]["match_trace"]
        assert office_trace["match_level"] == "NEEDS_CONFIRM"
        assert len(office_trace["candidates"]) == 2

        _write_json(
            scenario.evidence / "identity-task-matrix.json",
            {
                "success": success_tasks,
                "review": review_tasks,
                "ignored_files": [str(path.relative_to(source_root)) for path in ignored_videos],
                "incomplete_file": str(incomplete.relative_to(source_root)),
            },
        )

        _open_tasks(page)
        _refresh(page)
        page.wait_for_selector("[data-task-action='view-task']")
        page.screenshot(
            path=str(scenario.evidence / "identity-task-list-desktop.png"),
            full_page=True,
        )
        _open_task(page, double_task["task_id"])
        double_modal = page.locator(".cinema-modal").last
        double_modal.get_by_text("决策路径", exact=True).click()
        assert "辅助目录名" in double_modal.inner_text()
        assert "多语言证据收敛" in double_modal.inner_text()
        assert "文件名与目录名均指向 双瞳 (2002)" in double_modal.inner_text()
        page.screenshot(
            path=str(scenario.evidence / "double-vision-detail.png"),
            full_page=False,
        )
        double_modal.get_by_text("关闭", exact=True).click()

        _open_task(page, review_tasks["Interview.mkv"]["task_id"])
        conflict_modal = page.locator(".cinema-modal").last
        conflict_modal.get_by_text("决策路径", exact=True).click()
        assert "文件名和文件夹名指向不同作品" in conflict_modal.inner_text()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth") <= 0
        page.screenshot(
            path=str(scenario.evidence / "conflict-detail-mobile.png"),
            full_page=False,
        )

    execute("F13-real-download-identity-boundaries", f13)

    _write_json(run_dir / "matrix-summary.json", summary)
    assert not failures, "\n".join(failures)

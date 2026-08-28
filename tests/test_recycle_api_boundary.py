import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from media_importer.api import globals as api_globals
from media_importer.api.recycle_handlers import RecycleHandlers
from media_importer.core.db.connection import init_db
from media_importer.features.recycle import (
    delete_from_recycle,
    list_recycle_dir,
    restore_from_recycle,
)


def _write_sidecar(recycle_dir: Path, name: str, original_path: Path) -> Path:
    data_path = recycle_dir / name
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_bytes(b"recycled-content")
    (Path(str(data_path) + ".meta")).write_text(
        json.dumps(
            {
                "original_path": str(original_path),
                "source_zone": "source",
                "reason": "test",
                "task_id": "task-1",
                "moved_at": "2026-08-28T10:00:00",
                "file_size_mb": 0.1,
            }
        ),
        encoding="utf-8",
    )
    return data_path


class _ResponseHandler(RecycleHandlers):
    def __init__(self):
        self.wfile = io.BytesIO()
        self._request_id = "test-request"
        self.status_code = None
        self.headers = {}

    def send_response(self, code):
        self.status_code = code

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        return None


@pytest.fixture
def recycle_context(tmp_path):
    recycle_dir = tmp_path / "recycle"
    originals_dir = tmp_path / "originals"
    recycle_dir.mkdir()
    originals_dir.mkdir()
    conn = init_db(str(tmp_path / "app.db"))
    original_path = originals_dir / "movie.mkv"
    recycled_path = _write_sidecar(recycle_dir, "2026-08-28/movie.mkv", original_path)
    yield conn, recycle_dir, original_path, recycled_path
    conn.close()


def test_valid_sidecar_is_imported_with_stable_opaque_server_id(recycle_context):
    """SAFE-002: 有效旧 sidecar 必须导入 SQLite，且客户端只看到稳定服务端 ID。"""
    conn, recycle_dir, _original_path, recycled_path = recycle_context

    first = list_recycle_dir(str(recycle_dir), conn=conn)
    second = list_recycle_dir(str(recycle_dir), conn=conn)

    assert first["total"] == 1
    assert first["items"][0]["id"] == second["items"][0]["id"]
    assert first["items"][0]["id"] != str(recycled_path)
    row = conn.execute(
        "SELECT recycle_path, status FROM recycle_items WHERE item_id = ?",
        (first["items"][0]["id"],),
    ).fetchone()
    assert row is not None
    assert row["recycle_path"] == os.path.realpath(recycled_path)
    assert row["status"] == "ACTIVE"


def test_delete_resolves_server_id_and_cannot_delete_arbitrary_path(recycle_context, tmp_path):
    """SAFE-002: 删除只能解析台账 ID，任意绝对路径不得成为删除目标。"""
    conn, recycle_dir, _original_path, recycled_path = recycle_context
    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"must-survive")
    item_id = list_recycle_dir(str(recycle_dir), conn=conn)["items"][0]["id"]

    rejected = delete_from_recycle([str(outside)], str(recycle_dir), conn=conn)

    assert rejected["deleted"] == []
    assert rejected["failed"][0]["status"] == "not_found"
    assert outside.read_bytes() == b"must-survive"

    deleted = delete_from_recycle([item_id], str(recycle_dir), conn=conn)
    assert deleted["failed"] == []
    assert deleted["deleted"][0]["id"] == item_id
    assert not recycled_path.exists()
    assert conn.execute(
        "SELECT status FROM recycle_items WHERE item_id=?", (item_id,)
    ).fetchone()[0] == "DELETED"


def test_restore_resolves_server_id_and_updates_ledger(recycle_context):
    """SAFE-002: 合法服务端 ID 可以恢复，完成后不再作为活动回收项出现。"""
    conn, recycle_dir, original_path, recycled_path = recycle_context
    item_id = list_recycle_dir(str(recycle_dir), conn=conn)["items"][0]["id"]

    result = restore_from_recycle(
        [item_id],
        recycle_dir=str(recycle_dir),
        conn=conn,
    )

    assert result["failed"] == []
    assert result["restored"][0]["id"] == item_id
    assert original_path.read_bytes() == b"recycled-content"
    assert not recycled_path.exists()
    assert conn.execute(
        "SELECT status FROM recycle_items WHERE item_id=?", (item_id,)
    ).fetchone()[0] == "RESTORED"


def test_restore_by_server_id_rejects_overwrite_fail_closed(recycle_context):
    """SAFE-002: 覆盖恢复在二次回收事务落地前必须 fail closed，不能永久删除原文件。"""
    conn, recycle_dir, original_path, recycled_path = recycle_context
    item_id = list_recycle_dir(str(recycle_dir), conn=conn)["items"][0]["id"]
    original_path.write_bytes(b"newer-original")

    result = restore_from_recycle(
        [item_id],
        conflict_mode="overwrite",
        recycle_dir=str(recycle_dir),
        conn=conn,
    )

    assert result["restored"] == []
    assert result["failed"][0]["status"] == "overwrite_not_supported"
    assert original_path.read_bytes() == b"newer-original"
    assert recycled_path.read_bytes() == b"recycled-content"


def test_sidecar_symlink_resolving_outside_recycle_root_is_not_imported(tmp_path):
    """SAFE-002: canonicalize 后越出回收根的 symlink 不能进入台账。"""
    recycle_dir = tmp_path / "recycle"
    recycle_dir.mkdir()
    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"outside")
    link = recycle_dir / "escape.mkv"
    link.symlink_to(outside)
    Path(str(link) + ".meta").write_text(
        json.dumps(
            {
                "original_path": str(tmp_path / "restore" / "escape.mkv"),
                "moved_at": "2026-08-28T10:00:00",
            }
        ),
        encoding="utf-8",
    )
    conn = init_db(str(tmp_path / "app.db"))
    try:
        result = list_recycle_dir(str(recycle_dir), conn=conn)
        assert result["items"] == []
        assert conn.execute("SELECT COUNT(*) FROM recycle_items").fetchone()[0] == 0
    finally:
        conn.close()


def test_recycle_api_rejects_client_path_payload(recycle_context, tmp_path):
    """SAFE-002: HTTP 副作用入口不再兼容 recycle_path 字段。"""
    conn, recycle_dir, _original_path, _recycled_path = recycle_context
    outside = tmp_path / "outside-api.mkv"
    outside.write_bytes(b"must-survive")
    previous_config = api_globals._config
    previous_manager = api_globals._global_task_manager
    api_globals._config = {"source_policy": {"recycle_dir": str(recycle_dir)}}
    api_globals._global_task_manager = SimpleNamespace(conn=conn)
    handler = _ResponseHandler()
    try:
        handler.recycle_delete(
            body={"items": [{"recycle_path": str(outside)}]},
            params={},
            query={},
        )
        payload = json.loads(handler.wfile.getvalue())
        assert handler.status_code == 400
        assert payload["status"] == "bad_request"
        assert outside.read_bytes() == b"must-survive"
    finally:
        api_globals._config = previous_config
        api_globals._global_task_manager = previous_manager

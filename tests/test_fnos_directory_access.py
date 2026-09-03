import json
import os
import socketserver
import threading
import uuid

import pytest

from media_importer.features.configuration.fnos_directory_access import (
    FnosOpenAPIError,
    authorized_root_for_path,
    get_shared_accessible_folders,
    is_fnos_app_managed_path,
    is_fnos_runtime,
    validate_fnos_directory_paths,
)


class _Handler(socketserver.StreamRequestHandler):
    response = {"code": 0, "msg": "", "data": ["/vol1/media", "/vol2/tv"]}
    received = b""

    def handle(self):
        request_line = self.rfile.readline()
        headers = {}
        while True:
            line = self.rfile.readline()
            if line in {b"\r\n", b"\n", b""}:
                break
            key, value = line.decode().split(":", 1)
            headers[key.lower()] = value.strip()
        body = self.rfile.read(int(headers.get("content-length", "0")))
        type(self).received = request_line + body
        payload = json.dumps(type(self).response).encode()
        self.wfile.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(payload)).encode() + b"\r\n\r\n" + payload
        )


def _serve(_tmp_path, response):
    path = f"/tmp/nmmi-{uuid.uuid4().hex[:12]}.sock"
    _Handler.response = response
    server = socketserver.UnixStreamServer(path, _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, path


def test_queries_authorized_folders_without_exposing_token(tmp_path):
    server, path = _serve(tmp_path, {
        "code": 0, "msg": "", "data": ["/vol1/media", "/vol2/tv", "relative"],
    })
    try:
        result = get_shared_accessible_folders(socket_path=path, token="secret-token")
    finally:
        server.shutdown()
        server.server_close()
        os.unlink(path)

    assert result == ["/vol1/media", "/vol2/tv"]
    assert b"trim.file.getSharedAccessibleFolders" in _Handler.received
    assert b"secret-token" not in _Handler.received  # token only belongs to HTTP header


def test_missing_token_fails_closed(tmp_path):
    with pytest.raises(FnosOpenAPIError, match="凭据"):
        get_shared_accessible_folders(socket_path=str(tmp_path / "missing.sock"), token="")


def test_partial_fnos_host_signal_still_enforces_acl(tmp_path):
    socket_path = tmp_path / "trim.sock"
    socket_path.touch()

    assert is_fnos_runtime(socket_path=str(socket_path), token="") is True
    assert is_fnos_runtime(socket_path=str(tmp_path / "missing.sock"), token="host-token") is True
    assert is_fnos_runtime(socket_path=str(tmp_path / "missing.sock"), token="") is False


def test_authorized_root_uses_path_boundary_and_accepts_children():
    folders = ["/vol1/media", "/vol1/media/movies"]

    assert authorized_root_for_path("/vol1/media/movies/Forrest Gump", folders) == "/vol1/media/movies"
    assert authorized_root_for_path("/vol1/media-archive/movie", folders) == ""
    assert authorized_root_for_path("relative/path", folders) == ""


def test_app_managed_path_is_narrowly_limited_to_this_package(monkeypatch, tmp_path):
    package_var = tmp_path / "package-var"
    package_var.mkdir()
    monkeypatch.setenv("TRIM_PKGVAR", str(package_var))

    assert is_fnos_app_managed_path(str(package_var / "logs"))
    assert not is_fnos_app_managed_path("/vol12/@appdata/nas-media-importer/resources")
    monkeypatch.delenv("TRIM_PKGVAR")
    assert is_fnos_app_managed_path("/vol12/@appdata/nas-media-importer/resources")
    assert not is_fnos_app_managed_path("/vol12/@appdata/another-app/resources")
    assert not is_fnos_app_managed_path("/vol12/media")


def test_fnos_role_validation_rejects_configured_paths_outside_acl_roots():
    config = {
        "source_dir": "/vol1/downloads",
        "library_roots": [
            {"id": "movies", "name": "电影盘", "path": "/vol2/movies", "enabled": True},
            {"id": "off", "name": "停用盘", "path": "/vol9/off", "enabled": False},
        ],
        "source_policy": {"recycle_dir": "/vol1/recycle"},
    }
    capability = {
        "enforced": True,
        "available": True,
        "folders": ["/vol1", "/vol2/tv"],
    }

    errors = validate_fnos_directory_paths(config, capability=capability)

    assert len(errors) == 1
    assert "电影盘" in errors[0]


def test_non_fnos_runtime_keeps_manual_path_fallback():
    config = {"source_dir": "/any/source"}
    capability = {"enforced": False, "available": False, "folders": []}

    assert validate_fnos_directory_paths(config, {"source"}, capability) == []


def test_fnos_role_validation_covers_user_selected_system_directories():
    config = {
        "log_dir": "/vol1/logs",
        "resource_dir": "/vol2/resources",
    }
    capability = {
        "enforced": True,
        "available": True,
        "folders": ["/vol1"],
    }

    errors = validate_fnos_directory_paths(
        config, {"log", "resource"}, capability,
    )

    assert len(errors) == 1
    assert "海报与缓存目录" in errors[0]


def test_fnos_role_validation_does_not_send_private_appdata_to_shared_picker():
    config = {
        "log_dir": "/vol3/@appdata/nas-media-importer/logs",
        "resource_dir": "/vol3/@appdata/nas-media-importer/resources",
    }
    capability = {"enforced": True, "available": True, "folders": []}

    assert validate_fnos_directory_paths(
        config, {"log", "resource"}, capability,
    ) == []

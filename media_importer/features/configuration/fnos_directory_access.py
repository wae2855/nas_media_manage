"""fnOS 共享目录授权查询适配器。

token 只从当前进程环境读取；本模块不会持久化或返回 token。
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import time

FNOS_SOCKET_PATH = "/var/run/trim_open_gateway_apiscope.socket"
FNOS_API_PATH = "/api/v1/trimapp"
FNOS_APP_NAME = "nas-media-importer"


class FnosOpenAPIError(RuntimeError):
    pass


def is_fnos_runtime(*, socket_path: str = FNOS_SOCKET_PATH,
                    token: str | None = None) -> bool:
    """Only enforce ACLs when the process is actually hosted by fnOS."""
    current_token = token if token is not None else os.environ.get("TRIM_API_TOKEN", "")
    # Either signal means we are inside (or partially inside) the fnOS host.
    # A missing token/socket is itself an authorization fault and must not
    # silently downgrade a real installation to manual-path development mode.
    return bool(current_token or os.path.exists(socket_path))


def authorized_root_for_path(path: str, folders: list[str]) -> str:
    """Return the narrowest authorized root containing path, or an empty string."""
    if not isinstance(path, str) or not os.path.isabs(path):
        return ""
    candidate = os.path.normpath(os.path.abspath(path))
    matches = []
    for folder in folders or []:
        if not isinstance(folder, str) or not os.path.isabs(folder):
            continue
        root = os.path.normpath(os.path.abspath(folder))
        try:
            if os.path.commonpath([candidate, root]) == root:
                matches.append(root)
        except ValueError:
            continue
    return max(matches, key=len, default="")


def is_path_authorized(path: str, folders: list[str]) -> bool:
    return bool(authorized_root_for_path(path, folders))


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 5.0):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def _call(req: str, data: dict | None = None, *, socket_path: str = FNOS_SOCKET_PATH,
          token: str | None = None) -> dict:
    current_token = token if token is not None else os.environ.get("TRIM_API_TOKEN", "")
    if not current_token:
        raise FnosOpenAPIError("fnOS 未向当前进程提供开放 API 凭据")
    if not os.path.exists(socket_path):
        raise FnosOpenAPIError("当前环境没有 fnOS 开放 API Socket")
    payload = json.dumps({
        "reqId": str(time.time_ns()),
        "req": req,
        "appName": FNOS_APP_NAME,
        "data": data or {},
    }, ensure_ascii=False).encode("utf-8")
    connection = _UnixHTTPConnection(socket_path)
    try:
        connection.request(
            "POST", FNOS_API_PATH, body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
                "Authorization": f"Bearer {current_token}",
            },
        )
        response = connection.getresponse()
        raw = response.read()
    except (OSError, http.client.HTTPException) as exc:
        raise FnosOpenAPIError(f"调用 fnOS 开放 API 失败: {exc}") from exc
    finally:
        connection.close()
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FnosOpenAPIError("fnOS 开放 API 返回了无法解析的数据") from exc
    if response.status != 200 or result.get("code") != 0:
        raise FnosOpenAPIError(result.get("msg") or f"fnOS 开放 API 返回 {response.status}")
    return result


def get_shared_accessible_folders(*, socket_path: str = FNOS_SOCKET_PATH,
                                  token: str | None = None) -> list[str]:
    result = _call(
        "trim.file.getSharedAccessibleFolders", {},
        socket_path=socket_path, token=token,
    )
    data = result.get("data", [])
    if isinstance(data, dict):
        data = data.get("folders") or data.get("paths") or []
    if not isinstance(data, list):
        raise FnosOpenAPIError("fnOS 授权目录返回格式无效")
    return list(dict.fromkeys(
        os.path.normpath(item) for item in data
        if isinstance(item, str) and os.path.isabs(item)
    ))


def build_fnos_directory_capability() -> dict:
    enforced = is_fnos_runtime()
    try:
        folders = get_shared_accessible_folders()
    except FnosOpenAPIError as exc:
        return {
            "available": False,
            "enforced": enforced,
            "folders": [],
            "message": str(exc),
            "minimum": {"system": "1.2.0401", "app": "1.34.0"},
        }
    return {
        "available": True,
        "enforced": enforced,
        "folders": folders,
        "message": "已读取当前应用获得授权的共享目录",
        "minimum": {"system": "1.2.0401", "app": "1.34.0"},
    }


def validate_fnos_directory_paths(config: dict, roles: set[str] | None = None,
                                  capability: dict | None = None) -> list[str]:
    """Validate only submitted external roles; local development is not blocked."""
    current = capability if capability is not None else build_fnos_directory_capability()
    if not current.get("enforced"):
        return []
    selected_roles = roles or {"source", "target", "recycle"}
    if not current.get("available"):
        return ["fnOS 目录授权状态无法读取，请刷新授权状态后重试"]
    folders = current.get("folders") or []
    errors = []
    policy = config.get("source_policy", {}) or {}
    values: list[tuple[str, str]] = []
    if "source" in selected_roles:
        values.append(("来源目录", str(config.get("source_dir", "") or "")))
    if "recycle" in selected_roles:
        values.append(("回收目录", str(policy.get("recycle_dir", "") or policy.get("quarantine_dir", "") or "")))
    if "temp" in selected_roles:
        values.append(("中转目录", str(config.get("temp_dir", "") or "")))
    if "log" in selected_roles:
        values.append(("日志目录", str(config.get("log_dir", "") or "")))
    if "resource" in selected_roles:
        values.append(("海报与缓存目录", str(config.get("resource_dir", "") or config.get("resources_dir", "") or "")))
    if "target" in selected_roles:
        roots = config.get("library_roots") or []
        if isinstance(roots, list) and roots:
            values.extend(
                (f"片库“{root.get('name') or index + 1}”", str(root.get("path", "") or ""))
                for index, root in enumerate(roots)
                if isinstance(root, dict) and root.get("enabled", True) is not False
            )
        elif config.get("library_root"):
            values.append(("片库目录", str(config.get("library_root") or "")))
    for label, path in values:
        if path and not is_path_authorized(path, folders):
            errors.append(f"{label}尚未授权给本应用，请先通过 fnOS 目录选择器授权")
    return errors

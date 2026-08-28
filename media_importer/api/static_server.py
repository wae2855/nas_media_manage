import hashlib
import os

from .utils import json_response

WEBUI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webui")

# 文件修改时间缓存，避免每次请求都 stat
_file_mtimes = {}


def _get_etag(file_path: str) -> str:
    """基于文件修改时间生成 ETag，文件内容变化自动失效。"""
    mtime = os.path.getmtime(file_path)
    key = f"{file_path}:{mtime}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


class StaticServerMixin:
    def _serve_static_file(self, filename):
        file_path = os.path.join(WEBUI_DIR, filename)
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(os.path.realpath(WEBUI_DIR)):
            json_response(self, 403, message="Access denied")
            return
        if not os.path.isfile(file_path):
            json_response(self, 404, message=f"File not found: {filename}")
            return

        etag = _get_etag(file_path)

        # 检查客户端缓存
        if_none_match = self.headers.get("If-None-Match", "")
        if if_none_match and if_none_match.strip('"') == etag:
            self.send_response(304)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("ETag", f'"{etag}"')
            self.end_headers()
            return

        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except Exception as e:
            json_response(self, 500, message=f"Failed to read file: {e}")
            return

        content_type = "text/html"
        if filename.endswith(".css"):
            content_type = "text/css"
        elif filename.endswith(".js"):
            content_type = "application/javascript"
        elif filename.endswith(".png"):
            content_type = "image/png"
        elif filename.endswith(".svg"):
            content_type = "image/svg+xml"

        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("ETag", f'"{etag}"')
        self.send_header("X-Frame-Options", "ALLOWALL")
        self.send_header("Content-Security-Policy", "frame-ancestors *")
        self.end_headers()
        self.wfile.write(content)
        self.wfile.flush()

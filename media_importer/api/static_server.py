import os
from .utils import json_response

WEBUI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webui")


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
        self.send_header("X-Frame-Options", "ALLOWALL")
        self.send_header("Content-Security-Policy", "frame-ancestors *")
        self.end_headers()
        self.wfile.write(content)
        self.wfile.flush()

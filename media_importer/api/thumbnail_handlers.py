import os
import mimetypes
from .utils import json_response
from . import globals

# 允许的图片扩展名
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _find_thumbnail_dir_in(parent_dir: str) -> str:
    """在指定父目录下不区分大小写地查找 thumbnail 文件夹"""
    if not parent_dir or not os.path.isdir(parent_dir):
        return ""

    # 尝试常见的几种拼写
    common_names = ["Thumbnail", "thumbnail", "THUMBNAIL", "Thumbnails", "thumbnails"]

    for name in common_names:
        thumb_dir = os.path.join(parent_dir, name)
        if os.path.isdir(thumb_dir):
            return thumb_dir

    # 如果常见拼写都不匹配，尝试在目录中搜索不区分大小写的匹配
    try:
        for item in os.listdir(parent_dir):
            item_path = os.path.join(parent_dir, item)
            if os.path.isdir(item_path) and item.lower() == "thumbnail":
                return item_path
    except OSError:
        pass

    return ""


def _get_thumbnail_dir() -> str:
    """从系统配置中获取缩略图文件夹路径（优先 resource_dir，其次 source_dir）"""
    config = globals._config
    if not config:
        return ""

    # 优先在 resource_dir 下查找
    resource_dir = config.get("resource_dir", "")
    thumb_dir = _find_thumbnail_dir_in(resource_dir)
    if thumb_dir:
        return thumb_dir

    # 如果找不到，再在 source_dir 下查找
    source_dir = config.get("source_dir", "")
    thumb_dir = _find_thumbnail_dir_in(source_dir)
    if thumb_dir:
        return thumb_dir

    return ""


class ThumbnailHandlersMixin:
    """提供缩略图列表和文件服务的 API"""

    def _thumbnails_list(self):
        """GET /api/thumbnails — 返回 Thumbnail 目录下的图片列表，按修改时间倒序，最多 12 张"""
        thumb_dir = _get_thumbnail_dir()
        if not thumb_dir:
            json_response(self, 200, data={"thumbnails": [], "dir": ""})
            return

        try:
            files = []
            for f in os.listdir(thumb_dir):
                ext = os.path.splitext(f)[1].lower()
                if ext in _IMAGE_EXTENSIONS:
                    full_path = os.path.join(thumb_dir, f)
                    try:
                        st = os.stat(full_path)
                        size = st.st_size
                        mtime = st.st_mtime
                    except OSError:
                        size = 0
                        mtime = 0
                    files.append({
                        "name": f,
                        "url": f"/api/thumbnails/{f}",
                        "size": size,
                        "mtime": mtime,
                    })
            files.sort(key=lambda x: x["mtime"], reverse=True)
            files = files[:12]
            for item in files:
                del item["mtime"]
            json_response(self, 200, data={"thumbnails": files, "dir": thumb_dir})
        except Exception as e:
            json_response(self, 500, message=f"读取缩略图目录失败: {e}")

    def _thumbnails_serve(self, filename):
        """GET /api/thumbnails/{filename} — 返回单张缩略图文件"""
        thumb_dir = _get_thumbnail_dir()
        if not thumb_dir:
            json_response(self, 404, message="缩略图目录未配置或不存在")
            return

        file_path = os.path.join(thumb_dir, filename)
        real_path = os.path.realpath(file_path)
        real_thumb_dir = os.path.realpath(thumb_dir)

        # 安全检查：防止路径穿越
        if not real_path.startswith(real_thumb_dir):
            json_response(self, 403, message="访问被拒绝")
            return

        if not os.path.isfile(file_path):
            json_response(self, 404, message=f"文件不存在: {filename}")
            return

        ext = os.path.splitext(filename)[1].lower()
        if ext not in _IMAGE_EXTENSIONS:
            json_response(self, 403, message="不支持的文件类型")
            return

        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            self.wfile.write(content)
            self.wfile.flush()
        except Exception as e:
            json_response(self, 500, message=f"读取文件失败: {e}")

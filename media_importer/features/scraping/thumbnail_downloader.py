import logging
import os
import re
import urllib.error
import urllib.request

_log = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _sanitize_filename(title: str, provider_id: str) -> str:
    """生成安全的文件名：标题_提供者ID"""
    safe_title = re.sub(r'[\\/:*?"<>|\s]+', '_', title.strip())[:60]
    safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(provider_id))[:20]
    if safe_title and safe_id:
        return f"{safe_title}_{safe_id}"
    return safe_title or safe_id or "unknown"


def _get_thumbnail_dir(config: dict) -> str:
    """从配置获取 thumbnail 目录路径，优先 resource_dir，不存在则创建"""
    resource_dir = config.get("resource_dir", "")
    if resource_dir:
        thumb_dir = os.path.join(resource_dir, "thumbnail")
        os.makedirs(thumb_dir, exist_ok=True)
        return thumb_dir
    source_dir = config.get("source_dir", "")
    if source_dir:
        thumb_dir = os.path.join(source_dir, "thumbnail")
        os.makedirs(thumb_dir, exist_ok=True)
        return thumb_dir
    return ""


def download_thumbnail(poster_url: str, config: dict,
                       title: str = "", provider_id: str = "") -> str:
    """下载海报图片到 thumbnail 目录，返回本地文件路径；失败返回空字符串。"""
    if not poster_url:
        return ""

    thumb_dir = _get_thumbnail_dir(config)
    if not thumb_dir:
        _log.debug("[thumbnail] 无可用资源目录，跳过下载")
        return ""

    # 从 URL 推断扩展名
    ext = ".jpg"
    for candidate in (".webp", ".png", ".jpeg", ".jpg"):
        if poster_url.lower().endswith(candidate):
            ext = candidate
            break

    base_name = _sanitize_filename(title, provider_id)
    filename = f"{base_name}{ext}"
    dest_path = os.path.join(thumb_dir, filename)

    # 已存在同名文件则跳过
    if os.path.isfile(dest_path):
        _log.debug(f"[thumbnail] 已存在: {dest_path}")
        return dest_path

    try:
        req = urllib.request.Request(poster_url, headers={
            "User-Agent": "nas-media-importer/1.0",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if len(data) < 500:
            _log.warning(f"[thumbnail] 图片过小({len(data)}B)，跳过: {poster_url}")
            return ""
        with open(dest_path, "wb") as f:
            f.write(data)
        _log.info(f"[thumbnail] 已保存: {dest_path} ({len(data)}B)")
        return dest_path
    except (urllib.error.URLError, OSError) as e:
        _log.warning(f"[thumbnail] 下载失败: {poster_url} — {e}")
        return ""

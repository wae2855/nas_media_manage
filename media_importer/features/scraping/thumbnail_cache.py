"""首页海报缓存的安全选择与软上限治理。"""

from __future__ import annotations

import logging
import os
import stat
from urllib.parse import quote

_log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
DEFAULT_MAX_FILES = 500
DEFAULT_MAX_BYTES = 200 * 1024 * 1024


def _safe_thumbnail_root(
    root: str,
    protected_roots: list[str] | None = None,
    *,
    protected_roots_canonical: bool = False,
) -> str:
    if not root or os.path.islink(root):
        return ""
    try:
        info = os.lstat(root)
        if not stat.S_ISDIR(info.st_mode):
            return ""
        real_root = os.path.realpath(root)
        for protected_root in protected_roots or []:
            protected = (
                os.path.normpath(os.path.abspath(protected_root))
                if protected_roots_canonical
                else os.path.realpath(protected_root)
            )
            if os.path.commonpath((real_root, protected)) in {real_root, protected}:
                return ""
        return real_root
    except (OSError, ValueError):
        return ""


def _contained_regular_image(root: str, path: str) -> str:
    if not root or not path:
        return ""
    real_root = _safe_thumbnail_root(root)
    if not real_root:
        return ""
    real_path = os.path.realpath(path)
    try:
        if os.path.commonpath((real_root, real_path)) != real_root:
            return ""
        info = os.stat(path, follow_symlinks=False)
    except (OSError, ValueError):
        return ""
    if not stat.S_ISREG(info.st_mode) or os.path.islink(path):
        return ""
    if os.path.splitext(path)[1].lower() not in IMAGE_EXTENSIONS:
        return ""
    return real_path


def recent_movie_items(rows: list[dict], thumbnail_dir: str, limit: int = 12) -> list[dict]:
    """按已排序任务生成去重后的最近影片，不暴露服务器绝对路径。"""
    items: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        image_path = _contained_regular_image(thumbnail_dir, str(row.get("thumbnail_path") or ""))
        if not image_path:
            continue
        provider_type = str(row.get("provider_type") or "").strip().lower()
        provider_id = str(row.get("provider_id") or "").strip()
        if provider_type and provider_id:
            dedupe_key = f"provider:{provider_type}:{provider_id}"
        else:
            import_path = os.path.normcase(str(row.get("import_video_path") or "").strip())
            title = str(row.get("scrape_title_cn") or row.get("scrape_title_en") or "").strip().lower()
            year = str(row.get("scrape_year") or "").strip()
            dedupe_key = f"path:{import_path}" if import_path else f"title:{title}:{year}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        name = os.path.basename(image_path)
        items.append(
            {
                "task_id": str(row.get("task_id") or ""),
                "title": str(
                    row.get("scrape_title_cn")
                    or row.get("scrape_title_en")
                    or row.get("source_filename")
                    or "最近入库影片"
                ),
                "year": str(row.get("scrape_year") or ""),
                "completed_at": row.get("completed_at"),
                "name": name,
                "url": f"/api/thumbnails/{quote(name, safe='')}",
                "_path": image_path,
            }
        )
        if len(items) >= limit:
            break
    return items


def prune_thumbnail_cache(
    thumbnail_dir: str,
    protected_paths: set[str],
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes: int = DEFAULT_MAX_BYTES,
    protected_roots: list[str] | None = None,
    protected_roots_canonical: bool = False,
) -> dict:
    """清理可再生成海报缓存；只删除根目录内非保护的普通图片文件。"""
    safe_root = _safe_thumbnail_root(
        thumbnail_dir,
        protected_roots,
        protected_roots_canonical=protected_roots_canonical,
    )
    if not safe_root:
        return {"files": 0, "bytes": 0, "removed": 0, "removed_bytes": 0}
    protected = {
        safe for path in protected_paths
        if (safe := _contained_regular_image(thumbnail_dir, path))
    }
    records: list[dict] = []
    try:
        names = os.listdir(safe_root)
    except OSError:
        return {"files": 0, "bytes": 0, "removed": 0, "removed_bytes": 0}
    for name in names:
        path = os.path.join(safe_root, name)
        safe = _contained_regular_image(safe_root, path)
        if not safe:
            continue
        try:
            info = os.stat(safe, follow_symlinks=False)
        except OSError:
            continue
        records.append({"path": safe, "size": int(info.st_size), "mtime": float(info.st_mtime)})

    total_files = len(records)
    total_bytes = sum(item["size"] for item in records)
    removed = 0
    removed_bytes = 0
    for item in sorted(records, key=lambda record: record["mtime"]):
        if total_files <= max_files and total_bytes <= max_bytes:
            break
        if item["path"] in protected:
            continue
        try:
            before = os.lstat(item["path"])
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size != item["size"]
            ):
                continue
            current = os.lstat(item["path"])
            if current.st_dev != before.st_dev or current.st_ino != before.st_ino:
                continue
            os.unlink(item["path"])
        except OSError as exc:
            _log.warning("[thumbnail-cache] 清理失败: %s", exc)
            continue
        total_files -= 1
        total_bytes -= item["size"]
        removed += 1
        removed_bytes += item["size"]
    return {
        "files": total_files,
        "bytes": total_bytes,
        "removed": removed,
        "removed_bytes": removed_bytes,
    }

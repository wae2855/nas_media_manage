import os
import shutil
import json
from datetime import datetime


def recycle_cleanup(recycle_dir: str, retention_days: int) -> list:
    if not recycle_dir or not os.path.isdir(recycle_dir):
        return []
    if retention_days <= 0:
        return []

    now = datetime.now()
    deleted = []

    dir_metas = []
    file_metas = []

    for dirpath, dirnames, filenames in os.walk(recycle_dir):
        for fname in filenames:
            if fname.endswith(".dir.meta"):
                dir_metas.append(os.path.join(dirpath, fname))
            elif fname.endswith(".meta"):
                file_metas.append(os.path.join(dirpath, fname))

    for meta_path in dir_metas:
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            moved_at_str = meta.get("moved_at", "")
            if not moved_at_str:
                continue
            moved_at = datetime.fromisoformat(moved_at_str)
            age_days = (now - moved_at).days
            if age_days > retention_days:
                dir_data_path = meta_path[:-9]
                if os.path.isdir(dir_data_path):
                    shutil.rmtree(dir_data_path)
                    deleted.append({"path": dir_data_path, "age_days": age_days, "reason": "recycle_expired_dir"})
                os.remove(meta_path)
                deleted.append({"path": meta_path, "age_days": age_days, "reason": "dir_meta_expired"})
        except (OSError, json.JSONDecodeError, ValueError):
            continue

    for meta_path in file_metas:
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            moved_at_str = meta.get("moved_at", "")
            if not moved_at_str:
                continue
            moved_at = datetime.fromisoformat(moved_at_str)
            age_days = (now - moved_at).days
            if age_days > retention_days:
                data_path = meta_path[:-5]
                if os.path.isfile(data_path):
                    os.remove(data_path)
                    deleted.append({"path": data_path, "age_days": age_days, "reason": "recycle_expired"})
                os.remove(meta_path)
                deleted.append({"path": meta_path, "age_days": age_days, "reason": "meta_expired"})
        except (OSError, json.JSONDecodeError, ValueError):
            continue

    return deleted


def list_recycle_dir(recycle_dir: str, zone: str = None, reason: str = None,
                     limit: int = 100, offset: int = 0) -> dict:
    if not recycle_dir or not os.path.isdir(recycle_dir):
        return {
            "items": [], "total": 0, "total_count": 0, "total_size": 0,
            "total_size_mb": 0, "zones": {}, "partition_stats": {},
            "partitions": [], "reasons": [],
        }

    items = []
    zones = {}
    total_size = 0
    reasons_set = set()

    for dirpath, dirnames, filenames in os.walk(recycle_dir):
        for fname in filenames:
            meta_path = os.path.join(dirpath, fname)
            is_dir_meta = fname.endswith(".dir.meta")
            is_file_meta = fname.endswith(".meta") and not is_dir_meta

            if not is_file_meta and not is_dir_meta:
                continue

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            original_path = meta.get("original_path", "")
            meta_reason = meta.get("reason", "")
            moved_at = meta.get("moved_at", "")
            file_size_mb = meta.get("file_size_mb", 0) or meta.get("total_size_mb", 0)
            source_zone = meta.get("source_zone", "other")
            task_id = meta.get("task_id", "")
            is_dir = meta.get("is_dir", False)

            if is_dir_meta:
                data_path = meta_path[:-9]
            else:
                data_path = meta_path[:-5]

            recycle_path = data_path if os.path.exists(data_path) else ""

            zone_name = ""
            if meta_reason.startswith("source_cleaner:"):
                zone_name = "[清理器-源目录]"
            elif source_zone == "source":
                zone_name = "[源目录]"
            elif source_zone == "import":
                zone_name = "[入库目录]"
            else:
                zone_name = "[其他]"

            if zone and zone_name != zone:
                continue
            if reason and meta_reason != reason:
                continue

            parent_dir = os.path.dirname(original_path)
            restorable = False
            if original_path and not os.path.exists(original_path):
                if os.path.isdir(parent_dir) and os.access(parent_dir, os.W_OK):
                    restorable = True

            file_size_bytes = int(file_size_mb * 1024 * 1024) if file_size_mb else 0

            zones.setdefault(zone_name, {"count": 0, "size": 0})
            zones[zone_name]["count"] += 1
            zones[zone_name]["size"] += file_size_bytes
            total_size += file_size_bytes

            reasons_set.add(meta_reason)

            items.append({
                "id": recycle_path or meta_path,
                "recycle_path": recycle_path,
                "original_path": original_path,
                "source_zone": source_zone,
                "zone_name": zone_name,
                "partition": zone_name,
                "reason": meta_reason,
                "moved_at": moved_at,
                "file_size_mb": file_size_mb,
                "size": file_size_bytes,
                "task_id": task_id,
                "is_dir": is_dir,
                "restorable": restorable,
            })

    items.sort(key=lambda x: x.get("moved_at", ""), reverse=True)
    total = len(items)
    paged = items[offset:offset + limit]

    return {
        "items": paged,
        "total": total,
        "total_count": total,
        "total_size": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 1) if total_size else 0,
        "zones": zones,
        "partition_stats": zones,
        "partitions": list(zones.keys()),
        "reasons": list(reasons_set),
    }


def restore_from_recycle(items: list, conflict_mode: str = "skip") -> dict:
    restored = []
    failed = []

    for item in items:
        recycle_path = item.get("recycle_path", "")
        if not recycle_path or not os.path.exists(recycle_path):
            failed.append({"recycle_path": recycle_path, "status": "not_found", "message": "回收站文件不存在"})
            continue

        is_dir = os.path.isdir(recycle_path)
        meta_suffix = ".dir.meta" if is_dir else ".meta"
        meta_path = recycle_path + meta_suffix

        original_path = ""
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                original_path = meta.get("original_path", "")
            except (OSError, json.JSONDecodeError):
                pass

        if not original_path:
            failed.append({"recycle_path": recycle_path, "status": "no_meta", "message": "无法获取原始路径"})
            continue

        parent_dir = os.path.dirname(original_path)
        if not os.path.isdir(parent_dir):
            failed.append({"recycle_path": recycle_path, "status": "parent_missing", "message": f"原位置父目录不存在: {parent_dir}"})
            continue

        if not os.access(parent_dir, os.W_OK):
            failed.append({"recycle_path": recycle_path, "status": "no_write", "message": f"原位置无写入权限: {parent_dir}"})
            continue

        if os.path.exists(original_path):
            if conflict_mode == "skip":
                failed.append({"recycle_path": recycle_path, "status": "conflict", "message": f"原位置已存在同名文件: {original_path}"})
                continue
            elif conflict_mode == "overwrite":
                if os.path.isdir(original_path):
                    shutil.rmtree(original_path)
                else:
                    os.remove(original_path)
            elif conflict_mode == "rename":
                name, ext = os.path.splitext(original_path)
                original_path = f"{name}_restored{ext}"

        try:
            os.rename(recycle_path, original_path)
        except OSError:
            try:
                if is_dir:
                    shutil.copytree(recycle_path, original_path)
                    shutil.rmtree(recycle_path)
                else:
                    shutil.copy2(recycle_path, original_path)
                    os.remove(recycle_path)
            except (OSError, shutil.Error) as e:
                failed.append({"recycle_path": recycle_path, "status": "move_failed", "message": str(e)})
                continue

        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except OSError:
                pass

        restored.append({"recycle_path": recycle_path, "restored_to": original_path, "status": "ok"})

    return {"restored": restored, "failed": failed}


def delete_from_recycle(items: list) -> dict:
    deleted = []
    failed = []

    for item in items:
        recycle_path = item.get("recycle_path", "")
        if not recycle_path or not os.path.exists(recycle_path):
            failed.append({"recycle_path": recycle_path, "status": "not_found"})
            continue

        is_dir = os.path.isdir(recycle_path)
        meta_suffix = ".dir.meta" if is_dir else ".meta"
        meta_path = recycle_path + meta_suffix

        try:
            if is_dir:
                shutil.rmtree(recycle_path)
            else:
                os.remove(recycle_path)
            deleted.append({"recycle_path": recycle_path, "status": "ok"})
        except OSError as e:
            failed.append({"recycle_path": recycle_path, "status": "error", "message": str(e)})
            continue

        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except OSError:
                pass

    return {"deleted": deleted, "failed": failed}

import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from media_importer.infrastructure.filesystem.safety import safe_move, verified_copy

from .ledger import (
    get_active_item,
    import_valid_sidecars,
    list_active_items,
    mark_item_status,
    path_within_recycle_root,
)


def _verified_cross_device_move(source: str, target: str, *, is_dir: bool) -> tuple[bool, str]:
    if not is_dir:
        return verified_copy(source, target, remove_source=True)

    staging = target + f".{uuid.uuid4().hex}.copying"
    try:
        os.mkdir(staging)
        for current_dir, dir_names, file_names in os.walk(source):
            relative = os.path.relpath(current_dir, source)
            target_dir = staging if relative == "." else os.path.join(staging, relative)
            os.makedirs(target_dir, exist_ok=True)
            for dir_name in dir_names:
                os.makedirs(os.path.join(target_dir, dir_name), exist_ok=True)
            for file_name in file_names:
                source_file = os.path.join(current_dir, file_name)
                target_file = os.path.join(target_dir, file_name)
                if os.path.exists(target_file):
                    continue
                copied, message = verified_copy(source_file, target_file)
                if not copied:
                    return False, message
        if os.path.lexists(target):
            return False, "恢复目标在复制期间出现，已保留回收项"
        os.rename(staging, target)
        shutil.rmtree(source)
        return True, "目录已校验恢复"
    except (OSError, shutil.Error) as exc:
        return False, str(exc)


def recycle_cleanup(recycle_dir: str, retention_days: int, *,
                    protected_roots: Optional[list[str]] = None,
                    protected_roots_canonical: bool = False) -> list:
    if not recycle_dir or not os.path.isdir(recycle_dir):
        return []
    if retention_days <= 0:
        return []
    if protected_roots:
        if protected_roots_canonical:
            recycle_real = os.path.realpath(os.path.abspath(recycle_dir))
            for root in protected_roots:
                root_value = str(root or "").strip()
                if not root_value or not os.path.isabs(root_value):
                    return []
                protected = os.path.normpath(os.path.abspath(root_value))
                try:
                    if os.path.commonpath((recycle_real, protected)) in {
                        recycle_real,
                        protected,
                    }:
                        return []
                except ValueError:
                    continue
        else:
            from media_importer.features.configuration.storage_topology import paths_overlap

            if any(paths_overlap(recycle_dir, root) for root in protected_roots if root):
                return []

    now = datetime.now()
    deleted = []

    dir_metas = []
    file_metas = []

    for dirpath, _dirnames, filenames in os.walk(recycle_dir):
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


def list_recycle_dir(recycle_dir: str, zone: Optional[str] = None, reason: Optional[str] = None,
                     limit: int = 100, offset: int = 0,
                     conn: Optional[sqlite3.Connection] = None) -> dict:
    if not recycle_dir or not os.path.isdir(recycle_dir):
        return {
            "items": [], "total": 0, "total_count": 0, "total_size": 0,
            "total_size_mb": 0, "zones": {}, "partition_stats": {},
            "partitions": [], "reasons": [],
        }

    if conn is not None:
        import_valid_sidecars(conn, recycle_dir)
        return _list_recycle_ledger(conn, zone=zone, reason=reason, limit=limit, offset=offset)

    items = []
    zones = {}
    total_size = 0
    reasons_set = set()

    for dirpath, _dirnames, filenames in os.walk(recycle_dir):
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


def _list_recycle_ledger(conn: sqlite3.Connection, zone: Optional[str],
                         reason: Optional[str], limit: int, offset: int) -> dict:
    items = []
    zones = {}
    reasons_set = set()
    total_size = 0

    for row in list_active_items(conn):
        if not os.path.exists(row["recycle_path"]):
            continue
        meta_reason = row.get("reason", "")
        source_zone = row.get("source_zone", "other")
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

        recycle_path = row["recycle_path"]
        original_path = row.get("original_path", "")
        parent_dir = os.path.dirname(original_path)
        restorable = bool(
            recycle_path
            and original_path
            and not os.path.exists(original_path)
            and os.path.isdir(parent_dir)
            and os.access(parent_dir, os.W_OK)
        )
        size_bytes = int(row.get("size_bytes", 0) or 0)
        zones.setdefault(zone_name, {"count": 0, "size": 0})
        zones[zone_name]["count"] += 1
        zones[zone_name]["size"] += size_bytes
        total_size += size_bytes
        reasons_set.add(meta_reason)
        items.append({
            "id": row["item_id"],
            # Physical paths remain server-side; clients operate on item_id only.
            "recycle_path": "",
            "original_path": original_path,
            "source_zone": source_zone,
            "zone_name": zone_name,
            "partition": zone_name,
            "reason": meta_reason,
            "moved_at": row.get("moved_at", ""),
            "file_size_mb": round(size_bytes / (1024 * 1024), 1) if size_bytes else 0,
            "size": size_bytes,
            "task_id": row.get("task_id", ""),
            "is_dir": bool(row.get("is_dir", 0)),
            "restorable": restorable,
        })

    total = len(items)
    return {
        "items": items[offset:offset + limit],
        "total": total,
        "total_count": total,
        "total_size": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 1) if total_size else 0,
        "zones": zones,
        "partition_stats": zones,
        "partitions": list(zones.keys()),
        "reasons": list(reasons_set),
    }


def restore_from_recycle(items: list, conflict_mode: str = "skip", *,
                         recycle_dir: str = "",
                         conn: Optional[sqlite3.Connection] = None) -> dict:
    if conn is not None:
        return _restore_ledger_items(conn, recycle_dir, items, conflict_mode)

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

        if os.path.lexists(original_path):
            if conflict_mode == "skip":
                failed.append({"recycle_path": recycle_path, "status": "conflict", "message": f"原位置已存在同名文件: {original_path}"})
                continue
            elif conflict_mode == "overwrite":
                failed.append({"recycle_path": recycle_path, "status": "overwrite_not_supported", "message": "覆盖恢复需要先将现有文件二次回收，当前已安全拒绝"})
                continue
            elif conflict_mode == "rename":
                name, ext = os.path.splitext(original_path)
                original_path = f"{name}_restored{ext}"

        if is_dir:
            moved, message = _verified_cross_device_move(
                recycle_path, original_path, is_dir=is_dir,
            )
        else:
            moved, message = safe_move(recycle_path, original_path)
        if not moved:
            failed.append({"recycle_path": recycle_path, "status": "move_failed", "message": message})
            continue

        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except OSError:
                pass

        restored.append({"recycle_path": recycle_path, "restored_to": original_path, "status": "ok"})

    return {"restored": restored, "failed": failed}


def _restore_ledger_items(conn: sqlite3.Connection, recycle_dir: str,
                          item_ids: list, conflict_mode: str) -> dict:
    restored = []
    failed = []
    for item_id in item_ids:
        row = get_active_item(conn, item_id)
        if row is None:
            failed.append({"id": item_id, "status": "not_found", "message": "回收项不存在"})
            continue
        recycle_path = row["recycle_path"]
        meta_path = row["metadata_path"]
        if not path_within_recycle_root(recycle_dir, recycle_path):
            failed.append({"id": item_id, "status": "boundary_violation", "message": "回收项超出回收目录"})
            continue
        if not path_within_recycle_root(recycle_dir, meta_path):
            failed.append({"id": item_id, "status": "boundary_violation", "message": "回收元数据超出回收目录"})
            continue
        if not os.path.exists(recycle_path):
            failed.append({"id": item_id, "status": "not_found", "message": "回收站文件不存在"})
            continue

        original_path = row.get("original_path", "")
        parent_dir = os.path.dirname(original_path)
        if not original_path or not os.path.isdir(parent_dir):
            failed.append({"id": item_id, "status": "parent_missing", "message": f"原位置父目录不存在: {parent_dir}"})
            continue
        if not os.access(parent_dir, os.W_OK):
            failed.append({"id": item_id, "status": "no_write", "message": f"原位置无写入权限: {parent_dir}"})
            continue
        if os.path.lexists(original_path):
            if conflict_mode == "overwrite":
                failed.append({
                    "id": item_id,
                    "status": "overwrite_not_supported",
                    "message": "覆盖恢复需要先将现有文件二次回收，当前已安全拒绝",
                })
                continue
            if conflict_mode == "rename":
                name, ext = os.path.splitext(original_path)
                candidate = f"{name}_restored{ext}"
                counter = 1
                while os.path.exists(candidate):
                    candidate = f"{name}_restored_{counter}{ext}"
                    counter += 1
                original_path = candidate
            else:
                failed.append({"id": item_id, "status": "conflict", "message": f"原位置已存在同名文件: {original_path}"})
                continue

        is_dir = bool(row.get("is_dir", 0))
        if is_dir:
            moved, message = _verified_cross_device_move(
                recycle_path, original_path, is_dir=is_dir,
            )
        else:
            moved, message = safe_move(recycle_path, original_path)
        if not moved:
            failed.append({"id": item_id, "status": "move_failed", "message": message})
            continue

        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except OSError:
                pass
        mark_item_status(conn, item_id, "RESTORED")
        restored.append({"id": item_id, "restored_to": original_path, "status": "ok"})

    return {"restored": restored, "failed": failed}


def delete_from_recycle(items: list, recycle_dir: str = "",
                        conn: Optional[sqlite3.Connection] = None) -> dict:
    if conn is not None:
        return _delete_ledger_items(conn, recycle_dir, items)

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


def _delete_ledger_items(conn: sqlite3.Connection, recycle_dir: str,
                         item_ids: list) -> dict:
    deleted = []
    failed = []
    for item_id in item_ids:
        row = get_active_item(conn, item_id)
        if row is None:
            failed.append({"id": item_id, "status": "not_found"})
            continue
        recycle_path = row["recycle_path"]
        meta_path = row["metadata_path"]
        if not path_within_recycle_root(recycle_dir, recycle_path):
            failed.append({"id": item_id, "status": "boundary_violation"})
            continue
        if not path_within_recycle_root(recycle_dir, meta_path):
            failed.append({"id": item_id, "status": "boundary_violation"})
            continue
        if not os.path.exists(recycle_path):
            failed.append({"id": item_id, "status": "not_found"})
            continue

        try:
            if bool(row.get("is_dir", 0)):
                shutil.rmtree(recycle_path)
            else:
                os.remove(recycle_path)
        except OSError as exc:
            failed.append({"id": item_id, "status": "error", "message": str(exc)})
            continue

        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except OSError:
                pass
        mark_item_status(conn, item_id, "DELETED")
        deleted.append({"id": item_id, "status": "ok"})
    return {"deleted": deleted, "failed": failed}

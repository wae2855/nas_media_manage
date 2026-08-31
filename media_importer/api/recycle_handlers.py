#!/usr/bin/env python3
from urllib.parse import parse_qs

from media_importer.api import globals
from media_importer.api.utils import json_response
from media_importer.features.recycle import (
    delete_from_recycle,
    list_recycle_dir,
    restore_from_recycle,
)


def _query_first(query, key, default=""):
    if not isinstance(query, dict):
        parsed = parse_qs(query or "")
        val = parsed.get(key)
        return val[0] if val else default
    val = query.get(key)
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default


class RecycleHandlers:

    @staticmethod
    def _topology_error(config: dict) -> str:
        from media_importer.features.configuration.storage_topology import (
            topology_error_messages,
        )

        conflicts = topology_error_messages(config)
        return conflicts[0] if conflicts else ""

    @staticmethod
    def _recycle_db():
        manager = globals._global_task_manager
        return manager.conn if manager and hasattr(manager, "conn") else None

    @staticmethod
    def _server_item_ids(items) -> list:
        if not isinstance(items, list):
            return []
        item_ids = []
        for item in items:
            if isinstance(item, str) and item:
                item_ids.append(item)
            elif (
                isinstance(item, dict)
                and set(item) == {"id"}
                and isinstance(item.get("id"), str)
                and item["id"]
            ):
                item_ids.append(item["id"])
            else:
                return []
        return item_ids

    def recycle_list(self, *, body: dict, params: dict, query: dict):
        config = globals._config or {}
        recycle_dir = config.get("source_policy", {}).get("recycle_dir", "")
        zone = _query_first(query, "zone") or _query_first(query, "partition")
        reason = _query_first(query, "reason")
        limit = int(_query_first(query, "limit", "100"))
        offset = int(_query_first(query, "offset", "0"))
        conn = self._recycle_db()
        if conn is None:
            return json_response(self, 503, message="回收台账数据库不可用")
        result = list_recycle_dir(
            recycle_dir,
            zone=zone,
            reason=reason,
            limit=limit,
            offset=offset,
            conn=conn,
        )
        return json_response(self, 200, result)

    def recycle_restore(self, *, body: dict, params: dict, query: dict):
        body = body or {}
        items = self._server_item_ids(body.get("items", []))
        conflict_mode = body.get("conflict_mode", "skip")
        if not items:
            return json_response(self, 400, {"restored": [], "failed": []}, "未指定有效的回收项 ID")
        config = globals._config or {}
        topology_error = self._topology_error(config)
        if topology_error:
            return json_response(
                self, 400, {"restored": [], "failed": []},
                "目录边界不安全，已阻止回收恢复：" + topology_error,
            )
        recycle_dir = config.get("source_policy", {}).get("recycle_dir", "")
        conn = self._recycle_db()
        if conn is None:
            return json_response(self, 503, message="回收台账数据库不可用")
        result = restore_from_recycle(
            items,
            conflict_mode=conflict_mode,
            recycle_dir=recycle_dir,
            conn=conn,
        )
        restored_count = len(result.get("restored", []))
        failed_count = len(result.get("failed", []))
        if failed_count == 0:
            return json_response(self, 200, result, f"成功恢复 {restored_count} 个文件")
        elif restored_count == 0:
            return json_response(self, 400, result, f"恢复失败 {failed_count} 个文件")
        else:
            return json_response(self, 207, result, f"恢复 {restored_count} 个成功，{failed_count} 个失败")

    def recycle_delete(self, *, body: dict, params: dict, query: dict):
        body = body or {}
        items = self._server_item_ids(body.get("items", []))
        if not items:
            return json_response(self, 400, {"deleted": [], "failed": []}, "未指定有效的回收项 ID")
        config = globals._config or {}
        topology_error = self._topology_error(config)
        if topology_error:
            return json_response(
                self, 400, {"deleted": [], "failed": []},
                "目录边界不安全，已阻止永久删除：" + topology_error,
            )
        recycle_dir = config.get("source_policy", {}).get("recycle_dir", "")
        conn = self._recycle_db()
        if conn is None:
            return json_response(self, 503, message="回收台账数据库不可用")
        result = delete_from_recycle(items, recycle_dir, conn=conn)
        deleted_count = len(result.get("deleted", []))
        failed_count = len(result.get("failed", []))
        if failed_count == 0:
            return json_response(self, 200, result, f"成功删除 {deleted_count} 个文件")
        elif deleted_count == 0:
            return json_response(self, 400, result, f"删除失败 {failed_count} 个文件")
        else:
            return json_response(self, 207, result, f"删除 {deleted_count} 个成功，{failed_count} 个失败")

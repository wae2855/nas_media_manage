#!/usr/bin/env python3
from urllib.parse import parse_qs

from media_importer.api import globals
from media_importer.api.utils import json_response
from media_importer.features.source_cleaning import SourceCleaner  # noqa: F401
from media_importer.features.source_cleaning.application_service import (
    ai_preview_source_cleaning,
    execute_source_cleaning,
    get_source_cleaner_status,
    list_source_cleaner_records,
    preview_source_cleaning,
)
from media_importer.monitor.permission_checker import check_path_permission


class SourceCleanerHandlers:

    def source_cleaner_preview(self, *, body: dict, params: dict, query: dict):
        config = globals._config or {}
        conn = globals._global_task_manager.conn if globals._global_task_manager else None
        return json_response(self, 200, preview_source_cleaning(config, conn))

    def source_cleaner_ai_preview(self, *, body: dict, params: dict, query: dict):
        config = globals._config or {}
        conn = globals._global_task_manager.conn if globals._global_task_manager else None
        result = ai_preview_source_cleaning(config, conn)
        return json_response(self, 200, result)

    def source_cleaner_records(self, *, body: dict, params: dict, query: dict):
        conn = globals._global_task_manager.conn if globals._global_task_manager else None
        raw_query = query if isinstance(query, dict) else parse_qs(query or "")
        def _first(key, default=""):
            val = raw_query.get(key)
            if isinstance(val, list):
                return val[0] if val else default
            return val if val is not None else default
        limit = int(_first("limit", "20"))
        offset = int(_first("offset", "0"))
        records = list_source_cleaner_records(conn, limit=limit, offset=offset)
        return json_response(self, 200, records)

    def source_cleaner_execute(self, *, body: dict, params: dict, query: dict):
        config = globals._config or {}
        conn = globals._global_task_manager.conn if globals._global_task_manager else None
        merge_strategy = (body or {}).get("merge_strategy", None)
        result = execute_source_cleaning(
            config,
            conn,
            merge_strategy=merge_strategy,
            permission_check=check_path_permission,
        )
        if not result.ok:
            return json_response(self, 400, None, result.message)
        return json_response(self, 200, result.record)

    def source_cleaner_status(self, *, body: dict, params: dict, query: dict):
        conn = globals._global_task_manager.conn if globals._global_task_manager else None
        config = globals._config or {}
        status = get_source_cleaner_status(config, conn)
        return json_response(self, 200, status)

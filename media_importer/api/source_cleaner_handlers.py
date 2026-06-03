#!/usr/bin/env python3
from media_importer.api.utils import get_db, json_response, read_json_body
from media_importer.api import globals
from media_importer.features.source_cleaning import SourceCleaner
from media_importer.features.source_cleaning.application_service import (
    ai_preview_source_cleaning,
    execute_source_cleaning,
    get_source_cleaner_status,
    list_source_cleaner_records,
    preview_source_cleaning,
)
from media_importer.monitor.permission_checker import check_path_permission


class SourceCleanerHandlers:

    def source_cleaner_preview(self, handler):
        config = globals._config or {}
        conn = get_db(handler)
        return json_response(handler, 200, preview_source_cleaning(config, conn))

    def source_cleaner_ai_preview(self, handler):
        config = globals._config or {}
        conn = get_db(handler)
        result = ai_preview_source_cleaning(config, conn)
        return json_response(handler, 200, result)

    def source_cleaner_records(self, handler):
        conn = get_db(handler)
        limit = int(handler.query_params.get("limit", "20"))
        offset = int(handler.query_params.get("offset", "0"))
        records = list_source_cleaner_records(conn, limit=limit, offset=offset)
        return json_response(handler, 200, records)

    def source_cleaner_execute(self, handler):
        config = globals._config or {}
        conn = get_db(handler)
        body = read_json_body(handler)
        merge_strategy = body.get("merge_strategy", None)
        result = execute_source_cleaning(
            config,
            conn,
            merge_strategy=merge_strategy,
            permission_check=check_path_permission,
        )
        if not result.ok:
            return json_response(handler, 400, None, result.message)
        return json_response(handler, 200, result.record)

    def source_cleaner_status(self, handler):
        conn = get_db(handler)
        config = globals._config or {}
        status = get_source_cleaner_status(config, conn)
        return json_response(handler, 200, status)

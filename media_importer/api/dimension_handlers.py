from media_importer.api import globals
from media_importer.features.scraping import (
    disable_dimension_detail,
    enable_dimension_detail,
    get_dimension_detail,
    get_dimension_mapping_detail,
    list_dimensions,
    list_enabled_dimensions,
    preview_dimension_mapping,
    reset_dimension_detail,
    update_dimension_detail,
    update_dimension_mapping_detail,
)

from .utils import json_response


class DimensionHandlersMixin:
    def _dimensions_list(self, *, body: dict, params: dict, query: dict):
        try:
            dims = list_dimensions(globals._global_task_manager.conn)
            json_response(self, 200, data={"dimensions": dims, "total": len(dims)})
        except Exception as e:
            json_response(self, 500, message=f"获取维度列表失败: {e}")

    def _dimensions_enabled(self, *, body: dict, params: dict, query: dict):
        try:
            dims = list_enabled_dimensions(globals._global_task_manager.conn)
            json_response(self, 200, data={"dimensions": dims, "total": len(dims)})
        except Exception as e:
            json_response(self, 500, message=f"获取已启用维度失败: {e}")

    def _dimension_get(self, *, body: dict, params: dict, query: dict):
        name = params.get("dim_name", "")
        try:
            result = get_dimension_detail(globals._global_task_manager.conn, name)
            json_response(self, result.code, data=result.data, message=result.message)
        except Exception as e:
            json_response(self, 500, message=f"获取维度失败: {e}")

    def _dimension_update(self, *, body: dict, params: dict, query: dict):
        name = params.get("dim_name", "")
        try:
            result = update_dimension_detail(
                globals._global_task_manager.conn,
                name,
                body,
                config=globals._config or {},
            )
            json_response(self, result.code, data=result.data, message=result.message)
        except Exception as e:
            json_response(self, 500, message=f"更新维度失败: {e}")

    def _dimension_mapping_get(self, *, body: dict, params: dict, query: dict):
        try:
            result = get_dimension_mapping_detail(
                globals._global_task_manager.conn,
                params.get("dim_name", ""),
                params.get("provider_type", ""),
            )
            json_response(self, result.code, data=result.data, message=result.message)
        except Exception as e:
            json_response(self, 500, message=f"获取映射失败: {e}")

    def _dimension_mapping_update(self, *, body: dict, params: dict, query: dict):
        try:
            result = update_dimension_mapping_detail(
                globals._global_task_manager.conn,
                params.get("dim_name", ""),
                params.get("provider_type", ""),
                body,
            )
            json_response(self, result.code, data=result.data, message=result.message)
        except Exception as e:
            json_response(self, 500, message=f"保存映射失败: {e}")

    def _dimension_mapping_preview(self, *, body: dict, params: dict, query: dict):
        try:
            result = preview_dimension_mapping(
                globals._global_task_manager.conn,
                params.get("dim_name", ""),
                params.get("provider_type", ""),
                body,
            )
            json_response(self, result.code, data=result.data, message=result.message)
        except Exception as e:
            json_response(self, 500, message=f"预览映射失败: {e}")

    def _dimension_enable(self, *, body: dict, params: dict, query: dict):
        name = params.get("dim_name", "")
        try:
            result = enable_dimension_detail(globals._global_task_manager.conn, name)
            json_response(self, result.code, data=result.data, message=result.message)
        except Exception as e:
            json_response(self, 500, message=f"启用维度失败: {e}")

    def _dimension_disable(self, *, body: dict, params: dict, query: dict):
        name = params.get("dim_name", "")
        try:
            result = disable_dimension_detail(globals._global_task_manager.conn, name)
            json_response(self, result.code, data=result.data, message=result.message)
        except Exception as e:
            json_response(self, 500, message=f"禁用维度失败: {e}")

    def _dimension_reset(self, *, body: dict, params: dict, query: dict):
        name = params.get("dim_name", "")
        try:
            result = reset_dimension_detail(globals._global_task_manager.conn, name)
            json_response(self, result.code, data=result.data, message=result.message)
        except Exception as e:
            json_response(self, 500, message=f"恢复默认失败: {e}")

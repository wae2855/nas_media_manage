from media_importer.core.db import (
    get_all_dimensions as db_get_all_dimensions,
    get_enabled_dimensions as db_get_enabled_dimensions,
    get_dimension as db_get_dimension,
    update_dimension as db_update_dimension,
    enable_dimension as db_enable_dimension,
    disable_dimension as db_disable_dimension,
    reset_dimension as db_reset_dimension,
)
from media_importer.scraper.dimension_manager import check_tier_access
from media_importer.api import globals
from .utils import json_response


class DimensionHandlersMixin:
    def _dimensions_list(self):
        try:
            dims = db_get_all_dimensions(globals._global_task_manager.conn)
            json_response(self, 200, data={"dimensions": dims, "total": len(dims)})
        except Exception as e:
            json_response(self, 500, message=f"获取维度列表失败: {e}")

    def _dimensions_enabled(self):
        try:
            dims = db_get_enabled_dimensions(globals._global_task_manager.conn)
            json_response(self, 200, data={"dimensions": dims, "total": len(dims)})
        except Exception as e:
            json_response(self, 500, message=f"获取已启用维度失败: {e}")

    def _dimension_get(self, name: str):
        try:
            dim = db_get_dimension(globals._global_task_manager.conn, name)
            if dim is None:
                json_response(self, 404, message=f"维度不存在: {name}")
                return
            json_response(self, 200, data=dim)
        except Exception as e:
            json_response(self, 500, message=f"获取维度失败: {e}")

    def _dimension_update(self, name: str, body: dict):
        try:
            dim = db_get_dimension(globals._global_task_manager.conn, name)
            if dim is None:
                json_response(self, 404, message=f"维度不存在: {name}")
                return
            allowed = {}
            for key in ("label", "ai_prompt", "tmdb_field", "value_list", "color", "description"):
                if key in body:
                    allowed[key] = body[key]
            if not allowed:
                json_response(self, 400, message="无有效更新字段")
                return
            updated = db_update_dimension(globals._global_task_manager.conn, name, **allowed)
            json_response(self, 200, data=updated, message="维度配置已更新")
        except Exception as e:
            json_response(self, 500, message=f"更新维度失败: {e}")

    def _dimension_enable(self, name: str):
        try:
            dim = db_get_dimension(globals._global_task_manager.conn, name)
            if dim is None:
                json_response(self, 404, message=f"维度不存在: {name}")
                return
            required_tier = dim.get("required_tier", "free")
            if required_tier != "free" and not check_tier_access(required_tier):
                json_response(self, 403, message=f"该维度需要 {required_tier.upper()} 许可")
                return
            updated = db_enable_dimension(globals._global_task_manager.conn, name)
            json_response(self, 200, data=updated, message=f"维度 {dim.get('label', name)} 已启用")
        except Exception as e:
            json_response(self, 500, message=f"启用维度失败: {e}")

    def _dimension_disable(self, name: str):
        try:
            dim = db_get_dimension(globals._global_task_manager.conn, name)
            if dim is None:
                json_response(self, 404, message=f"维度不存在: {name}")
                return
            updated = db_disable_dimension(globals._global_task_manager.conn, name)
            json_response(self, 200, data=updated, message=f"维度 {dim.get('label', name)} 已禁用")
        except Exception as e:
            json_response(self, 500, message=f"禁用维度失败: {e}")

    def _dimension_reset(self, name: str):
        try:
            dim = db_get_dimension(globals._global_task_manager.conn, name)
            if dim is None:
                json_response(self, 404, message=f"维度不存在: {name}")
                return
            updated = db_reset_dimension(globals._global_task_manager.conn, name)
            if updated is None:
                json_response(self, 500, message="恢复默认失败: 缺少默认配置")
                return
            json_response(self, 200, data=updated, message=f"维度 {dim.get('label', name)} 已恢复默认配置")
        except Exception as e:
            json_response(self, 500, message=f"恢复默认失败: {e}")

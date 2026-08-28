from dataclasses import dataclass, field

from media_importer.infrastructure.db import (
    disable_dimension as db_disable_dimension,
)
from media_importer.infrastructure.db import (
    enable_dimension as db_enable_dimension,
)
from media_importer.infrastructure.db import (
    get_all_dimensions as db_get_all_dimensions,
)
from media_importer.infrastructure.db import (
    get_dimension as db_get_dimension,
)
from media_importer.infrastructure.db import (
    get_enabled_dimensions as db_get_enabled_dimensions,
)
from media_importer.infrastructure.db import (
    reset_dimension as db_reset_dimension,
)
from media_importer.infrastructure.db import (
    update_dimension as db_update_dimension,
)

from .dimension_manager import check_tier_access


@dataclass
class DimensionActionResult:
    code: int
    data: dict = field(default_factory=dict)
    message: str = ""


def list_dimensions(conn) -> list:
    return db_get_all_dimensions(conn)


def list_enabled_dimensions(conn) -> list:
    return db_get_enabled_dimensions(conn)


def get_dimension_detail(conn, name: str) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")
    return DimensionActionResult(code=200, data=dimension or {})


def update_dimension_detail(conn, name: str, body: dict) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")

    allowed = {
        key: body[key]
        for key in ("label", "ai_prompt", "tmdb_field", "value_list", "color", "description")
        if key in body
    }
    if not allowed:
        return DimensionActionResult(code=400, message="无有效更新字段")

    updated = db_update_dimension(conn, name, **allowed)
    return DimensionActionResult(code=200, data=updated or {}, message="维度配置已更新")


def enable_dimension_detail(conn, name: str) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")

    required_tier = dimension.get("required_tier", "free")
    if required_tier != "free" and not check_tier_access(required_tier):
        return DimensionActionResult(code=403, message=f"该维度需要 {required_tier.upper()} 许可")

    updated = db_enable_dimension(conn, name)
    return DimensionActionResult(
        code=200,
        data=updated or {},
        message=f"维度 {dimension.get('label', name)} 已启用",
    )


def disable_dimension_detail(conn, name: str) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")

    updated = db_disable_dimension(conn, name)
    return DimensionActionResult(
        code=200,
        data=updated or {},
        message=f"维度 {dimension.get('label', name)} 已禁用",
    )


def reset_dimension_detail(conn, name: str) -> DimensionActionResult:
    dimension = db_get_dimension(conn, name)
    if dimension is None:
        return DimensionActionResult(code=404, message=f"维度不存在: {name}")

    updated = db_reset_dimension(conn, name)
    if updated is None:
        return DimensionActionResult(code=500, message="恢复默认失败: 缺少默认配置")

    return DimensionActionResult(
        code=200,
        data=updated or {},
        message=f"维度 {dimension.get('label', name)} 已恢复默认配置",
    )

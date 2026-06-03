from unittest.mock import patch

from media_importer.features.scraping import (
    disable_dimension_detail,
    enable_dimension_detail,
    get_dimension_detail,
    reset_dimension_detail,
    update_dimension_detail,
)


def test_get_dimension_detail_returns_404_when_missing():
    with patch(
        "media_importer.features.scraping.dimensions_service.db_get_dimension",
        return_value=None,
    ):
        result = get_dimension_detail(object(), "media_type")

    assert result.code == 404
    assert "维度不存在" in result.message


def test_update_dimension_detail_rejects_empty_update():
    with patch(
        "media_importer.features.scraping.dimensions_service.db_get_dimension",
        return_value={"name": "media_type"},
    ):
        result = update_dimension_detail(object(), "media_type", {})

    assert result.code == 400
    assert result.message == "无有效更新字段"


def test_enable_dimension_detail_checks_tier_before_enabling():
    with patch(
        "media_importer.features.scraping.dimensions_service.db_get_dimension",
        return_value={"name": "restricted_level", "required_tier": "pro"},
    ), patch(
        "media_importer.features.scraping.dimensions_service.check_tier_access",
        return_value=False,
    ):
        result = enable_dimension_detail(object(), "restricted_level")

    assert result.code == 403
    assert "PRO" in result.message


def test_disable_dimension_detail_returns_updated_dimension():
    with patch(
        "media_importer.features.scraping.dimensions_service.db_get_dimension",
        return_value={"name": "media_type", "label": "媒体类型"},
    ), patch(
        "media_importer.features.scraping.dimensions_service.db_disable_dimension",
        return_value={"name": "media_type", "is_enabled": 0},
    ):
        result = disable_dimension_detail(object(), "media_type")

    assert result.code == 200
    assert result.data["is_enabled"] == 0
    assert "已禁用" in result.message


def test_reset_dimension_detail_reports_missing_default():
    with patch(
        "media_importer.features.scraping.dimensions_service.db_get_dimension",
        return_value={"name": "media_type", "label": "媒体类型"},
    ), patch(
        "media_importer.features.scraping.dimensions_service.db_reset_dimension",
        return_value=None,
    ):
        result = reset_dimension_detail(object(), "media_type")

    assert result.code == 500
    assert "缺少默认配置" in result.message

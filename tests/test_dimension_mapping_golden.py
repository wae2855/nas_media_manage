"""Golden tests for the current dimension mapping and persistence contract.

These tests intentionally describe the behaviour that exists before the
advanced dimension-mapping redesign.  In particular, dimension definitions
live in SQLite rather than the main YAML config, and the current update API can
customise display values but cannot customise provider mapping rules.
"""

import json

import pytest
import yaml

from media_importer.core.db.connection import init_db
from media_importer.features.configuration import ConfigView
from media_importer.features.scraping.dimension_manager import (
    _map_restricted_level,
    get_dimensions_for_provider,
    map_provider_to_dimension,
)
from media_importer.features.scraping.dimensions_service import (
    get_dimension_detail,
    reset_dimension_detail,
    update_dimension_detail,
)


@pytest.fixture
def dimension_conn(tmp_path):
    conn = init_db(str(tmp_path / "dimension-golden.sqlite3"))
    try:
        yield conn
    finally:
        conn.close()


def _tmdb_dimension(conn, name: str) -> dict:
    dimensions = get_dimensions_for_provider(conn, "tmdb")
    return next(dimension for dimension in dimensions if dimension["name"] == name)


@pytest.mark.parametrize(
    ("country", "certification", "expected_value", "expected_reliability"),
    [
        ("HK", "I", "0-6", 0.95),
        ("HK", "IIA", "13-16", 0.95),
        ("HK", "IIB", "13-16", 0.95),
        ("HK", "III", "17+", 0.95),
        ("US", "PG-13", "13-16", 1.0),
        ("GB", "15", "13-16", 0.95),
        ("DE", "FSK 16", "13-16", 0.95),
        ("FR", "-18", "17+", 0.95),
        ("JP", "R-15+", "13-16", 0.95),
        ("KR", "19", "17+", 0.95),
        ("AU", "MA15+", "13-16", 0.95),
        ("CA", "18A", "17+", 0.95),
    ],
)
def test_restricted_level_country_mapping_golden(
    country,
    certification,
    expected_value,
    expected_reliability,
):
    result = _map_restricted_level(
        "restricted_level",
        [],
        [
            {
                "iso_3166_1": country,
                "rating": certification,
                "release_dates": [],
            }
        ],
    )

    assert result == {
        "name": "restricted_level",
        "value": expected_value,
        "source_reliability": expected_reliability,
    }


def test_restricted_level_uses_current_country_priority_golden():
    """The current product chooses US before a stricter JP certification."""
    result = _map_restricted_level(
        "restricted_level",
        [],
        [
            {"iso_3166_1": "JP", "rating": "R-18+", "release_dates": []},
            {"iso_3166_1": "US", "rating": "PG", "release_dates": []},
        ],
    )

    assert result == {
        "name": "restricted_level",
        "value": "7-12",
        "source_reliability": 1.0,
    }


def test_hong_kong_certification_precedes_us_for_local_rating_golden():
    result = _map_restricted_level(
        "restricted_level",
        [],
        [
            {"iso_3166_1": "US", "rating": "PG-13", "release_dates": []},
            {"iso_3166_1": "HK", "rating": "III", "release_dates": []},
        ],
    )

    assert result == {
        "name": "restricted_level",
        "value": "17+",
        "source_reliability": 0.95,
    }


def test_unknown_restricted_level_remains_unresolved_golden():
    result = _map_restricted_level(
        "restricted_level",
        [],
        [
            {"iso_3166_1": "BR", "rating": "14", "release_dates": []},
            {"iso_3166_1": "US", "rating": "UNRATED", "release_dates": []},
        ],
    )

    assert result == {
        "name": "restricted_level",
        "value": None,
        "source_reliability": 0,
    }


def test_seeded_tmdb_mapping_results_golden(dimension_conn):
    cases = [
        ("documentary", {"genres": [{"id": 99}]}, "true"),
        ("animation", {"genres": [{"id": 16}]}, "true"),
        ("region", {"origin_country": ["CN"]}, "cn"),
        ("origin_lang", {"original_language": "es"}, "other"),
        # Current implementation follows Provider genre order for conflicts;
        # configured ``priority`` values are not consulted here.
        ("broad_genre", {"genres": [{"id": 35}, {"id": 28}]}, "comedy"),
    ]

    actual = {}
    for name, provider_data, _expected in cases:
        actual[name] = map_provider_to_dimension(
            _tmdb_dimension(dimension_conn, name),
            provider_data,
        )["value"]

    assert actual == {name: expected for name, _data, expected in cases}


def test_user_value_override_and_reset_round_trip_preserve_mapping(dimension_conn):
    before = get_dimension_detail(dimension_conn, "restricted_level")
    assert before.code == 200
    original_mapping = before.data["provider_mappings"]
    original_values = before.data["value_list"]
    customised_values = [
        {"value": item["value"], "label": f"自定义：{item['label']}"}
        for item in original_values
    ]

    updated = update_dimension_detail(
        dimension_conn,
        "restricted_level",
        {"value_list": customised_values},
    )
    reloaded = get_dimension_detail(dimension_conn, "restricted_level")

    assert updated.code == 200
    assert updated.data["value_list"] == customised_values
    assert reloaded.data["value_list"] == customised_values
    assert reloaded.data["provider_mappings"] == original_mapping

    reset = reset_dimension_detail(dimension_conn, "restricted_level")
    reset_reloaded = get_dimension_detail(dimension_conn, "restricted_level")

    assert reset.code == 200
    assert reset_reloaded.data["value_list"] == original_values
    assert reset_reloaded.data["provider_mappings"] == original_mapping


def test_current_update_api_does_not_accept_provider_mapping_override(dimension_conn):
    before = get_dimension_detail(dimension_conn, "restricted_level").data
    attempted_mapping = json.dumps(
        {"tmdb": {"match_type": "certification", "country_priority": ["JP", "US"]}},
        ensure_ascii=False,
    )

    result = update_dimension_detail(
        dimension_conn,
        "restricted_level",
        {"provider_mappings": attempted_mapping},
    )
    after = get_dimension_detail(dimension_conn, "restricted_level").data

    assert result.code == 400
    assert result.message == "无有效更新字段"
    assert after["provider_mappings"] == before["provider_mappings"]


def test_yaml_config_round_trip_does_not_mutate_dimension_mapping(dimension_conn):
    before = get_dimension_detail(dimension_conn, "restricted_level").data
    config_document = {
        "source_dir": "/mnt/source",
        "log_dir": "/mnt/local-logs",
        "source_policy": {"recycle_dir": "/mnt/local-recycle"},
        # ConfigView preserves unknown YAML keys in raw data, but dimensions are
        # not read from or persisted to YAML by the current product.
        "dimensions": {"restricted_level": {"country_priority": ["JP", "US"]}},
    }

    restored_document = yaml.safe_load(
        yaml.safe_dump(config_document, allow_unicode=True)
    )
    view = ConfigView.from_dict(restored_document)
    after = get_dimension_detail(dimension_conn, "restricted_level").data

    assert view.raw["dimensions"] == config_document["dimensions"]
    assert after["value_list"] == before["value_list"]
    assert after["provider_mappings"] == before["provider_mappings"]

"""Requirement: REQ-20260901-233114 — Provider 映射 v2 合同。"""

import json

import pytest

from media_importer.core.db.connection import init_db
from media_importer.features.scraping.dimension_mapping_engine import (
    MappingValidationError,
    default_provider_mappings,
    execute_mapping,
    mapping_content_hash,
    provider_capabilities,
    validate_mapping,
)
from media_importer.features.scraping.dimensions_service import (
    get_dimension_mapping_detail,
    preview_dimension_mapping,
    update_dimension_detail,
    update_dimension_mapping_detail,
)


def test_tmdb_capabilities_describe_bounded_shapes():
    result = provider_capabilities("tmdb")

    assert result["display_name"] == "TMDB"
    assert {field["shape"] for field in result["fields"]} <= {
        "scalar", "boolean", "set", "ordered_set", "country_value"
    }


def test_mapping_validator_fails_closed_for_unknown_target_and_operator():
    mapping = default_provider_mappings("restricted_level")["tmdb"]
    invalid_target = json.loads(json.dumps(mapping))
    invalid_target["rules"][0]["target"] = "missing"
    with pytest.raises(MappingValidationError, match="不存在"):
        validate_mapping(invalid_target, {"0-6", "7-12", "13-16", "17+"})

    invalid_operator = json.loads(json.dumps(mapping))
    invalid_operator["operator"] = "python_eval"
    with pytest.raises(MappingValidationError, match="不受支持"):
        validate_mapping(invalid_operator, {"0-6", "7-12", "13-16", "17+"})


def test_babel_r_is_viewing_restriction_but_not_explicit_content():
    rating = execute_mapping(
        "restricted_level",
        default_provider_mappings("restricted_level")["tmdb"],
        {"adult": False},
        release_dates=[
            {"iso_3166_1": "JP", "rating": "PG12", "release_dates": []},
            {"iso_3166_1": "US", "rating": "R", "release_dates": []},
            {"iso_3166_1": "GB", "rating": "15", "release_dates": []},
        ],
        allowed_targets={"0-6", "7-12", "13-16", "17+"},
    )
    sensitivity = execute_mapping(
        "content_sensitivity",
        default_provider_mappings("content_sensitivity")["tmdb"],
        {"adult": False},
        allowed_targets={"normal", "adult"},
    )

    assert rating["value"] == "17+"
    assert rating["mapping_evidence"]["matched_input"] == {
        "country": "US", "certification": "R"
    }
    assert sensitivity["value"] == "normal"
    assert sensitivity["mapping_evidence"]["rule_id"] == "tmdb-adult-no"


def test_hong_kong_category_three_is_viewing_restriction_not_adult_flag():
    rating = execute_mapping(
        "restricted_level",
        default_provider_mappings("restricted_level")["tmdb"],
        {"adult": False},
        release_dates=[
            {"iso_3166_1": "US", "rating": "PG-13", "release_dates": []},
            {"iso_3166_1": "HK", "rating": "III", "release_dates": []},
        ],
        allowed_targets={"0-6", "7-12", "13-16", "17+"},
    )
    sensitivity = execute_mapping(
        "content_sensitivity",
        default_provider_mappings("content_sensitivity")["tmdb"],
        {"adult": False},
        allowed_targets={"normal", "adult"},
    )

    assert rating["value"] == "17+"
    assert rating["mapping_evidence"]["matched_input"] == {
        "country": "HK", "certification": "III"
    }
    assert sensitivity["value"] == "normal"


def test_explicit_adult_flag_maps_only_content_sensitivity():
    result = execute_mapping(
        "content_sensitivity",
        default_provider_mappings("content_sensitivity")["tmdb"],
        {"adult": True},
        allowed_targets={"normal", "adult"},
    )

    assert result["value"] == "adult"
    assert result["mapping_evidence"]["rule_id"] == "tmdb-adult-yes"


def test_mapping_save_uses_hash_and_preserves_user_override(tmp_path):
    conn = init_db(str(tmp_path / "mapping.sqlite3"))
    current = get_dimension_mapping_detail(conn, "restricted_level", "tmdb")
    mapping = json.loads(json.dumps(current.data["mapping"]))
    mapping["country_priority"] = ["JP", "US", "GB"]

    saved = update_dimension_mapping_detail(conn, "restricted_level", "tmdb", {
        "expected_hash": current.data["content_hash"],
        "mapping": mapping,
    })
    stale = update_dimension_mapping_detail(conn, "restricted_level", "tmdb", {
        "expected_hash": current.data["content_hash"],
        "mapping": current.data["mapping"],
    })

    assert saved.code == 200
    assert saved.data["mapping"]["country_priority"][0] == "JP"
    assert stale.code == 409
    assert saved.data["content_hash"] == mapping_content_hash(mapping)


def test_preview_uses_unsaved_mapping_without_persisting(tmp_path):
    conn = init_db(str(tmp_path / "preview.sqlite3"))
    current = get_dimension_mapping_detail(conn, "restricted_level", "tmdb")
    candidate = json.loads(json.dumps(current.data["mapping"]))
    next(
        rule for rule in candidate["rules"]
        if rule["id"] == "tmdb-cert-us-17-plus"
    )["target"] = "13-16"

    preview = preview_dimension_mapping(conn, "restricted_level", "tmdb", {
        "mapping": candidate,
        "release_dates": [{"iso_3166_1": "US", "rating": "R", "release_dates": []}],
    })
    reloaded = get_dimension_mapping_detail(conn, "restricted_level", "tmdb")

    assert preview.data["value"] == "13-16"
    assert reloaded.data["content_hash"] == current.data["content_hash"]


def test_legacy_database_migrates_product_defaults_but_keeps_custom_mapping(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    conn = init_db(str(db_path))
    legacy = {"tmdb": {"field": "release_dates", "match_type": "certification"}}
    conn.execute(
        "UPDATE dimensions SET provider_mappings=?, label='限制级分类' WHERE name='restricted_level'",
        (json.dumps(legacy, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()

    migrated = init_db(str(db_path))
    row = migrated.execute(
        "SELECT label, provider_mappings, value_list FROM dimensions WHERE name='restricted_level'"
    ).fetchone()
    assert row["label"] == "观看分级"
    assert json.loads(row["provider_mappings"])["tmdb"]["schema_version"] == 2
    assert next(
        item for item in json.loads(row["value_list"]) if item["value"] == "17+"
    )["label"] == "限制观看"

    custom = {"tmdb": {"field": "custom", "match_type": "custom"}}
    migrated.execute(
        "UPDATE dimensions SET provider_mappings=? WHERE name='restricted_level'",
        (json.dumps(custom),),
    )
    migrated.commit()
    migrated.close()
    preserved = init_db(str(db_path))
    assert json.loads(preserved.execute(
        "SELECT provider_mappings FROM dimensions WHERE name='restricted_level'"
    ).fetchone()[0]) == custom


def test_unchanged_previous_default_receives_hong_kong_mapping_on_upgrade(tmp_path):
    db_path = tmp_path / "previous-default.sqlite3"
    conn = init_db(str(db_path))
    current = json.loads(conn.execute(
        "SELECT provider_mappings FROM dimensions WHERE name='restricted_level'"
    ).fetchone()[0])
    previous = json.loads(json.dumps(current))
    previous["tmdb"]["country_priority"].remove("HK")
    previous["tmdb"]["rules"] = [
        rule for rule in previous["tmdb"]["rules"]
        if rule.get("country") != "HK"
    ]
    previous_json = json.dumps(previous, ensure_ascii=False)
    conn.execute(
        "UPDATE dimensions SET provider_mappings=?, default_provider_mappings=? "
        "WHERE name='restricted_level'",
        (previous_json, previous_json),
    )
    conn.commit()
    conn.close()

    upgraded = init_db(str(db_path))
    row = upgraded.execute(
        "SELECT provider_mappings, default_provider_mappings FROM dimensions "
        "WHERE name='restricted_level'"
    ).fetchone()
    active = json.loads(row["provider_mappings"])["tmdb"]
    default = json.loads(row["default_provider_mappings"])["tmdb"]

    assert active["country_priority"][0] == "HK"
    assert any(rule["id"] == "tmdb-cert-hk-17-plus" for rule in active["rules"])
    assert active == default


def test_custom_mapping_is_preserved_when_hong_kong_default_is_added(tmp_path):
    db_path = tmp_path / "custom-before-hk.sqlite3"
    conn = init_db(str(db_path))
    current = json.loads(conn.execute(
        "SELECT provider_mappings FROM dimensions WHERE name='restricted_level'"
    ).fetchone()[0])
    previous = json.loads(json.dumps(current))
    previous["tmdb"]["country_priority"].remove("HK")
    previous["tmdb"]["rules"] = [
        rule for rule in previous["tmdb"]["rules"]
        if rule.get("country") != "HK"
    ]
    custom = json.loads(json.dumps(previous))
    custom["tmdb"]["country_priority"] = ["JP", "US"]
    conn.execute(
        "UPDATE dimensions SET provider_mappings=?, default_provider_mappings=? "
        "WHERE name='restricted_level'",
        (json.dumps(custom), json.dumps(previous)),
    )
    conn.commit()
    conn.close()

    upgraded = init_db(str(db_path))
    row = upgraded.execute(
        "SELECT provider_mappings, default_provider_mappings FROM dimensions "
        "WHERE name='restricted_level'"
    ).fetchone()

    assert json.loads(row["provider_mappings"]) == custom
    assert json.loads(row["default_provider_mappings"])["tmdb"][
        "country_priority"
    ][0] == "HK"


def test_new_database_contains_optional_content_sensitivity(tmp_path):
    conn = init_db(str(tmp_path / "new.sqlite3"))
    row = conn.execute(
        "SELECT label, is_enabled FROM dimensions WHERE name='content_sensitivity'"
    ).fetchone()

    assert dict(row) == {"label": "成人电影标记", "is_enabled": 0}
    values = json.loads(conn.execute(
        "SELECT value_list FROM dimensions WHERE name='content_sensitivity'"
    ).fetchone()[0])
    assert values == [
        {"value": "normal", "label": "否"},
        {"value": "adult", "label": "是"},
    ]


def test_existing_default_content_sensitivity_label_is_renamed(tmp_path):
    db_path = tmp_path / "existing-label.sqlite3"
    conn = init_db(str(db_path))
    conn.execute(
        "UPDATE dimensions SET label='内容敏感度' "
        "WHERE name='content_sensitivity'"
    )
    conn.execute(
        "UPDATE dimensions SET value_list=? WHERE name='content_sensitivity'",
        (json.dumps([
            {"value": "normal", "label": "普通内容"},
            {"value": "restricted", "label": "限制内容"},
            {"value": "adult", "label": "成人内容"},
        ], ensure_ascii=False),),
    )
    conn.commit()
    conn.close()

    migrated = init_db(str(db_path))
    row = migrated.execute(
        "SELECT label, value_list FROM dimensions WHERE name='content_sensitivity'"
    ).fetchone()

    assert row["label"] == "成人电影标记"
    assert json.loads(row["value_list"]) == [
        {"value": "normal", "label": "否"},
        {"value": "adult", "label": "是"},
    ]


def test_custom_content_sensitivity_label_is_preserved(tmp_path):
    db_path = tmp_path / "custom-label.sqlite3"
    conn = init_db(str(db_path))
    conn.execute(
        "UPDATE dimensions SET label='我的成人分类' "
        "WHERE name='content_sensitivity'"
    )
    conn.commit()
    conn.close()

    migrated = init_db(str(db_path))
    row = migrated.execute(
        "SELECT label FROM dimensions WHERE name='content_sensitivity'"
    ).fetchone()

    assert row["label"] == "我的成人分类"


def test_previous_adult_only_mapping_migrates_to_boolean_mapping(tmp_path):
    db_path = tmp_path / "adult-mapping.sqlite3"
    conn = init_db(str(db_path))
    previous_mapping = {
        "tmdb": {
            "schema_version": 2,
            "field": "adult",
            "shape": "boolean",
            "operator": "lookup",
            "rules": [{
                "id": "tmdb-adult-explicit",
                "inputs": [True],
                "target": "adult",
            }],
            "unmatched": {"action": "review"},
        }
    }
    conn.execute(
        "UPDATE dimensions SET provider_mappings=? "
        "WHERE name='content_sensitivity'",
        (json.dumps(previous_mapping),),
    )
    conn.commit()
    conn.close()

    migrated = init_db(str(db_path))
    mapping = json.loads(migrated.execute(
        "SELECT provider_mappings FROM dimensions "
        "WHERE name='content_sensitivity'"
    ).fetchone()[0])["tmdb"]

    assert [(rule["inputs"], rule["target"]) for rule in mapping["rules"]] == [
        ([False], "normal"),
        ([True], "adult"),
    ]


def test_dimension_value_cannot_be_deleted_while_mapping_or_path_rule_uses_it(tmp_path):
    conn = init_db(str(tmp_path / "referenced-value.sqlite3"))
    dimension = conn.execute(
        "SELECT value_list FROM dimensions WHERE name='restricted_level'"
    ).fetchone()
    values = [
        item for item in json.loads(dimension[0]) if item["value"] != "17+"
    ]

    result = update_dimension_detail(
        conn,
        "restricted_level",
        {"value_list": values},
        config={
            "path_rules": [{
                "name": "限制片库",
                "conditions": {"restricted_level": "17+"},
            }]
        },
    )

    assert result.code == 409
    assert "TMDB 映射" in result.message
    assert "限制片库" in result.message

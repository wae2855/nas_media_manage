import os

import pytest

from media_importer.features.configuration.library_paths import (
    LibraryPathError,
    canonicalize_library_config,
    migrate_legacy_library_rules,
    resolve_library_template,
    resolve_rule_template,
)


def test_legacy_absolute_rules_require_explicit_user_selected_root(tmp_path):
    root = tmp_path / "library"
    config = {
        "path_rules": [
            {"conditions": {"media_type": "movie"}, "library_root_id": "movies", "template": str(root / "电影" / "{title_cn}")},
            {"conditions": {"media_type": "tv"}, "library_root_id": "movies", "template": str(root / "剧集" / "{title_cn}")},
        ],
        "fallback_library_root_id": "movies",
        "fallback_dir": str(root / "其他"),
    }

    with pytest.raises(LibraryPathError, match="确认迁移"):
        canonicalize_library_config(config)

    canonical = migrate_legacy_library_rules(
        config,
        [{"id": "movies", "name": "影音盘", "path": str(root), "enabled": True}],
        "movies",
    )

    assert canonical["library_root"] == str(root)
    assert canonical["library_roots"] == [
        {"id": "movies", "name": "影音盘", "path": str(root), "enabled": True}
    ]
    assert canonical["path_rules"][0]["library_root_id"] == "movies"
    assert canonical["path_rules"][0]["template"] == os.path.join("电影", "{title_cn}")
    assert canonical["fallback_dir"] == "其他"


def test_unrelated_absolute_rules_fail_closed_instead_of_guessing_a_root():
    with pytest.raises(LibraryPathError, match="确认迁移"):
        canonicalize_library_config({
            "path_rules": [
                {"template": "/volume-a/movies/{title_cn}"},
                {"template": "/volume-b/tv/{title_cn}"},
            ]
        })


def test_multiple_legacy_volumes_map_to_user_selected_roots():
    canonical = migrate_legacy_library_rules({
        "path_rules": [
            {"library_root_id": "movies", "template": "/volume-a/movies/{title_cn}"},
            {"library_root_id": "tv", "template": "/volume-b/tv/{title_cn}"},
        ],
    }, [
        {"id": "movies", "path": "/volume-a/movies"},
        {"id": "tv", "path": "/volume-b/tv"},
    ], "movies")

    assert [rule["library_root_id"] for rule in canonical["path_rules"]] == ["movies", "tv"]
    assert [rule["template"] for rule in canonical["path_rules"]] == ["{title_cn}", "{title_cn}"]


def test_legacy_migration_is_atomic_when_a_rule_has_not_selected_a_root():
    config = {
        "path_rules": [
            {"library_root_id": "movies", "template": "/volume-a/movies/{title_cn}"},
            {"template": "/volume-b/tv/{title_cn}"},
        ],
    }
    with pytest.raises(LibraryPathError) as error:
        migrate_legacy_library_rules(
            config, [{"id": "movies", "path": "/volume-a/movies"}], "movies"
        )
    message = str(error.value)
    assert "第 2 条规则“默认入库规则”尚未选择目标片库" in message
    assert config["path_rules"][0]["template"].startswith("/volume-a")


def test_legacy_rule_rejects_a_selected_root_that_does_not_contain_its_old_path():
    config = {
        "path_rules": [
            {
                "conditions": {
                    "media_type": "movie",
                    "documentary": "no",
                    "restricted": "yes",
                },
                "library_root_id": "movies",
                "template": "/vol2/1000/X-rated/{title_cn}",
            }
        ],
    }

    with pytest.raises(LibraryPathError) as error:
        migrate_legacy_library_rules(
            config, [{"id": "movies", "path": "/vol5/1000/movies"}], "movies"
        )

    assert str(error.value) == (
        "第 1 条规则“限制级电影规则”的旧路径不在所选片库内: "
        "/vol2/1000/X-rated"
    )


def test_unassigned_rule_is_preserved_during_root_setup_but_required_before_running(tmp_path):
    config = {
        "library_roots": [
            {"id": "movies", "name": "电影盘", "path": str(tmp_path / "movies")},
        ],
        "default_library_root_id": "movies",
        "path_rules": [
            {"name": "普通电影", "conditions": {"media_type": "movie"}, "template": "电影/{title_cn}"},
        ],
        "fallback_dir": "",
    }

    staged = canonicalize_library_config(config)
    assert "library_root_id" not in staged["path_rules"][0]

    with pytest.raises(LibraryPathError, match="普通电影.*尚未选择目标片库"):
        canonicalize_library_config(config, require_rule_assignments=True)


def test_library_root_may_remain_unused_when_every_rule_reference_is_valid(tmp_path):
    canonical = canonicalize_library_config({
        "library_roots": [
            {"id": "movies", "path": str(tmp_path / "movies")},
            {"id": "spare", "path": str(tmp_path / "spare")},
        ],
        "default_library_root_id": "movies",
        "path_rules": [
            {"library_root_id": "movies", "template": "电影/{title_cn}"},
        ],
        "fallback_dir": "",
    }, require_rule_assignments=True)

    assert [root["id"] for root in canonical["library_roots"]] == ["movies", "spare"]
    assert canonical["path_rules"][0]["library_root_id"] == "movies"


@pytest.mark.parametrize("template", ["../outside/{title_cn}", "/absolute/{title_cn}"])
def test_relative_rule_cannot_escape_library_root(tmp_path, template):
    with pytest.raises(LibraryPathError):
        resolve_library_template(str(tmp_path / "library"), template, {"title_cn": "Movie"})


def test_rendered_dynamic_value_cannot_escape_library_root(tmp_path):
    with pytest.raises(LibraryPathError):
        resolve_library_template(
            str(tmp_path / "library"), "电影/{title_cn}", {"title_cn": "../../outside"}
        )


def test_multiple_roots_bind_each_rule_to_an_explicit_target(tmp_path):
    movies = tmp_path / "disk-a"
    tv = tmp_path / "disk-b"
    config = canonicalize_library_config({
        "library_roots": [
            {"id": "movies", "name": "电影盘", "path": str(movies)},
            {"id": "tv", "name": "剧集盘", "path": str(tv)},
        ],
        "default_library_root_id": "movies",
        "path_rules": [
            {"conditions": {"media_type": "movie"}, "library_root_id": "movies", "template": "电影/{title_cn}"},
            {"conditions": {"media_type": "tv"}, "library_root_id": "tv", "template": "剧集/{title_cn}"},
        ],
        "fallback_library_root_id": "movies",
        "fallback_dir": "其他",
    })

    assert resolve_rule_template(
        config, config["path_rules"][1], "剧集/三体", {}
    ) == str(tv / "剧集" / "三体")


def test_resolve_rule_template_does_not_touch_unselected_library_root(tmp_path, monkeypatch):
    selected = tmp_path / "disk-a"
    sleeping = tmp_path / "disk-b"
    config = {
        "library_roots": [
            {"id": "movies", "path": str(selected), "enabled": True},
            {"id": "archive", "path": str(sleeping), "enabled": True},
        ],
    }
    calls = []
    real_realpath = os.path.realpath

    def record_realpath(path):
        calls.append(str(path))
        return real_realpath(path)

    monkeypatch.setattr(
        "media_importer.features.configuration.library_paths.os.path.realpath",
        record_realpath,
    )

    resolved = resolve_rule_template(
        config,
        {"library_root_id": "movies"},
        "电影/{title_cn}",
        {"title_cn": "测试电影"},
    )

    assert resolved == str(selected / "电影" / "测试电影")
    assert str(sleeping) not in calls


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"library_roots": [
            {"id": "same", "path": "/vol1/a"}, {"id": "same", "path": "/vol2/b"},
        ]}, "ID 重复"),
        ({"library_roots": [
            {"id": "a", "path": "/vol1/a"}, {"id": "b", "path": "/vol1/a"},
        ]}, "路径重复"),
        ({
            "library_roots": [{"id": "a", "path": "/vol1/a"}],
            "path_rules": [{"library_root_id": "missing", "template": "电影"}],
        }, "不存在的片库"),
    ],
)
def test_invalid_multiple_root_contract_fails_closed(patch, message):
    with pytest.raises(LibraryPathError, match=message):
        canonicalize_library_config(patch)


def test_rule_cannot_escape_its_selected_root(tmp_path):
    with pytest.raises(LibraryPathError):
        canonicalize_library_config({
            "library_roots": [{"id": "one", "path": str(tmp_path / "one")}],
            "path_rules": [{"library_root_id": "one", "template": "../two/movie"}],
        })


def test_rule_cannot_reference_a_disabled_root(tmp_path):
    with pytest.raises(LibraryPathError, match="已停用"):
        canonicalize_library_config({
            "library_roots": [
                {"id": "active", "path": str(tmp_path / "active")},
                {"id": "offline", "path": str(tmp_path / "offline"), "enabled": False},
            ],
            "default_library_root_id": "active",
            "path_rules": [{"library_root_id": "offline", "template": "电影"}],
        })


def test_single_root_migrates_legacy_storage_identity_to_stable_id(tmp_path):
    identity = {"realpath": str(tmp_path / "library"), "device": 1, "mount_source": "disk"}
    canonical = canonicalize_library_config({
        "library_root": str(tmp_path / "library"),
        "storage_identities": {"target:4": identity},
    })
    assert canonical["storage_identities"]["target:default"] == identity

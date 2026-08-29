import os

import pytest

from media_importer.features.configuration.library_paths import (
    LibraryPathError,
    canonicalize_library_config,
    resolve_library_template,
)


def test_legacy_absolute_rules_are_migrated_under_a_common_library_root(tmp_path):
    root = tmp_path / "library"
    config = {
        "path_rules": [
            {"conditions": {"media_type": "movie"}, "template": str(root / "电影" / "{title_cn}")},
            {"conditions": {"media_type": "tv"}, "template": str(root / "剧集" / "{title_cn}")},
        ],
        "fallback_dir": str(root / "其他"),
    }

    canonical = canonicalize_library_config(config)

    assert canonical["library_root"] == str(root)
    assert canonical["path_rules"][0]["template"] == os.path.join("电影", "{title_cn}")
    assert canonical["fallback_dir"] == "其他"


def test_unrelated_absolute_rules_fail_closed_instead_of_guessing_a_root():
    with pytest.raises(LibraryPathError, match="共同的入库根目录"):
        canonicalize_library_config({
            "path_rules": [
                {"template": "/volume-a/movies/{title_cn}"},
                {"template": "/volume-b/tv/{title_cn}"},
            ]
        })


def test_single_fixed_absolute_target_can_become_its_own_library_root():
    canonical = canonicalize_library_config({
        "path_rules": [{"conditions": {}, "template": "/volume/library"}],
    })

    assert canonical["library_root"] == "/volume/library"
    assert canonical["path_rules"][0]["template"] == "."


@pytest.mark.parametrize("template", ["../outside/{title_cn}", "/absolute/{title_cn}"])
def test_relative_rule_cannot_escape_library_root(tmp_path, template):
    with pytest.raises(LibraryPathError):
        resolve_library_template(str(tmp_path / "library"), template, {"title_cn": "Movie"})


def test_rendered_dynamic_value_cannot_escape_library_root(tmp_path):
    with pytest.raises(LibraryPathError):
        resolve_library_template(
            str(tmp_path / "library"), "电影/{title_cn}", {"title_cn": "../../outside"}
        )

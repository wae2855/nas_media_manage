import os
import tempfile

from media_importer.features.prompts import (
    load_global_prompt_for_ui,
    load_provider_prompt_for_ui,
    reset_global_prompt,
    reset_provider_prompt,
    save_global_prompt,
    save_provider_prompt,
)
from media_importer.features.prompts import application_service


def _config_path(root: str) -> str:
    config_dir = os.path.join(root, "config")
    os.makedirs(config_dir, exist_ok=True)
    path = os.path.join(config_dir, "config.yaml")
    with open(path, "w", encoding="utf-8") as config_file:
        config_file.write("source_dir: /tmp/source\n")
    return path


def test_global_prompt_save_load_and_reset_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = _config_path(tmpdir)

        save_global_prompt(config_path, {"system_prompt": "custom prompt"})
        loaded = load_global_prompt_for_ui(config_path)
        reset_global_prompt(config_path)
        reloaded = load_global_prompt_for_ui(config_path)

    assert loaded == {"system_prompt": "custom prompt", "using_custom": True}
    assert reloaded["using_custom"] is False
    assert "专业的影视信息刮削助手" in reloaded["system_prompt"]


def test_global_prompt_uses_example_before_default():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = _config_path(tmpdir)
        example_path = os.path.join(tmpdir, "config", "scraper_prompts.example.md")
        with open(example_path, "w", encoding="utf-8") as example_file:
            example_file.write("system_prompt: example prompt\n")

        loaded = load_global_prompt_for_ui(config_path)

    assert loaded == {"system_prompt": "example prompt", "using_custom": False}


def test_provider_prompt_save_load_and_reset_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = _config_path(tmpdir)

        display_name = save_provider_prompt(
            config_path,
            "tmdb",
            {"system_prompt": "tmdb custom prompt"},
        )
        loaded = load_provider_prompt_for_ui(config_path, "tmdb")
        reset_name = reset_provider_prompt(config_path, "tmdb")
        reloaded = load_provider_prompt_for_ui(config_path, "tmdb")

    assert display_name == reset_name
    assert loaded == {"system_prompt": "tmdb custom prompt", "using_custom": True}
    assert reloaded["using_custom"] is False
    assert reloaded["system_prompt"]


def test_default_prompt_root_matches_package_config_dir():
    root = application_service._prompts_root(None)

    assert root.endswith("media_importer")

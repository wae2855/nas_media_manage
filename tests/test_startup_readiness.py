from media_importer.features.configuration.startup_readiness import inspect_startup_readiness


def _config(tmp_path):
    paths = {}
    for name in ("source", "temp", "recycle", "library"):
        path = tmp_path / name
        path.mkdir()
        paths[name] = str(path)
    return {
        "source_dir": paths["source"],
        "temp_dir": paths["temp"],
        "library_root": paths["library"],
        "fallback_dir": "其他",
        "path_rules": [{"conditions": {"media_type": "movie"}, "template": "电影/{title_cn}"}],
        "source_policy": {"mode": "preserve_all", "recycle_dir": paths["recycle"]},
        "metadata": {"providers": [{"type": "tmdb", "enabled": True, "api_key": "key"}]},
    }


def test_startup_readiness_aggregates_storage_provider_and_optional_llm(tmp_path):
    result = inspect_startup_readiness(
        _config(tmp_path),
        provider_probe=lambda provider: (True, "TMDB 可连接"),
        llm_probe=lambda llm: (_ for _ in ()).throw(AssertionError("LLM should be skipped")),
    )

    assert result["state"] == "PASS"
    checks = {item["id"]: item for item in result["checks"]}
    assert checks["storage"]["status"] == "PASS"
    assert checks["tmdb"]["status"] == "PASS"
    assert checks["llm"]["status"] == "SKIPPED"


def test_llm_is_required_only_when_preserve_media_ai_cleaning_is_enabled(tmp_path):
    config = _config(tmp_path)
    config["source_policy"]["mode"] = "preserve_media"
    config["source_cleaner"] = {"enabled": True, "ai_enabled": True}
    config["llm"] = {"base_url": "https://llm.example/v1", "api_key": "key", "model": "m"}

    result = inspect_startup_readiness(
        config,
        provider_probe=lambda provider: (True, "ok"),
        llm_probe=lambda llm: (False, "LLM 不可连接"),
    )

    assert result["state"] == "BLOCKED"
    llm = next(item for item in result["checks"] if item["id"] == "llm")
    assert llm["status"] == "BLOCKED"
    assert llm["fix_target"] == "source.llm"

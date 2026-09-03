from media_importer.core.db.connection import init_db
from media_importer.features.configuration.startup_readiness import inspect_startup_readiness


def _config(tmp_path):
    paths = {}
    for name in ("source", "recycle", "library"):
        path = tmp_path / name
        path.mkdir()
        paths[name] = str(path)
    return {
        "source_dir": paths["source"],
        "library_root": paths["library"],
        "library_roots": [
            {"id": "movies", "name": "电影片库", "path": paths["library"], "enabled": True},
        ],
        "default_library_root_id": "movies",
        "fallback_library_root_id": "movies",
        "fallback_dir": "其他",
        "path_rules": [{
            "name": "电影",
            "conditions": {"media_type": "movie"},
            "template": "电影/{title_cn}",
            "library_root_id": "movies",
        }],
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


def test_configuration_check_validates_enabled_provider_mappings(tmp_path):
    conn = init_db(str(tmp_path / "mapping-check.sqlite3"))
    result = inspect_startup_readiness(
        _config(tmp_path),
        provider_probe=lambda provider: (True, "TMDB 可连接"),
        conn=conn,
    )

    mapping = next(item for item in result["checks"] if item["id"] == "dimension_mappings")
    assert mapping["status"] == "PASS"


def test_configuration_check_warns_legacy_17_plus_rule_without_rewriting_it(tmp_path):
    config = _config(tmp_path)
    config["path_rules"][0]["conditions"]["restricted_level"] = "17+"

    result = inspect_startup_readiness(
        config,
        provider_probe=lambda provider: (True, "TMDB 可连接"),
    )

    warning = next(item for item in result["checks"] if item["id"] == "viewing_rating_rules")
    assert warning["status"] == "WARN"
    assert "不等于成人内容" in warning["message"]
    assert config["path_rules"][0]["conditions"]["restricted_level"] == "17+"


# Requirement: REQ-20260901-001019-2
def test_configuration_check_blocks_when_watcher_is_configured_but_not_running(tmp_path):
    config = _config(tmp_path)
    config["file_watcher"] = {"enabled": True, "poll_interval": 60}

    result = inspect_startup_readiness(
        config,
        provider_probe=lambda provider: (True, "TMDB 可连接"),
        watcher_running=False,
    )

    automation = next(item for item in result["checks"] if item["id"] == "automation")
    assert result["state"] == "BLOCKED"
    assert automation["status"] == "BLOCKED"
    assert "后台监控没有运行" in automation["message"]


# Requirement: REQ-20260901-001019-2
def test_configuration_check_passes_when_watcher_is_really_running(tmp_path):
    config = _config(tmp_path)
    config["file_watcher"] = {"enabled": True, "poll_interval": 60}

    result = inspect_startup_readiness(
        config,
        provider_probe=lambda provider: (True, "TMDB 可连接"),
        watcher_running=True,
    )

    automation = next(item for item in result["checks"] if item["id"] == "automation")
    assert result["state"] == "PASS"
    assert automation["status"] == "PASS"
    assert "正在运行" in automation["message"]


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


def test_startup_blocks_rule_without_explicit_library_assignment(tmp_path):
    config = _config(tmp_path)
    config["path_rules"][0].pop("library_root_id")

    result = inspect_startup_readiness(
        config,
        provider_probe=lambda provider: (True, "ok"),
    )

    library = next(item for item in result["checks"] if item["id"] == "library")
    assert result["state"] == "BLOCKED"
    assert library["fix_target"] == "rules"
    assert "第 1 条规则“电影”尚未选择目标片库" in library["message"]


def test_startup_blocks_rule_that_references_missing_library(tmp_path):
    config = _config(tmp_path)
    config["path_rules"][0]["library_root_id"] = "missing-disk"

    result = inspect_startup_readiness(
        config,
        provider_probe=lambda provider: (True, "ok"),
    )

    library = next(item for item in result["checks"] if item["id"] == "library")
    assert result["state"] == "BLOCKED"
    assert "引用了不存在的片库: missing-disk" in library["message"]


def test_startup_allows_unused_library_root(tmp_path):
    config = _config(tmp_path)
    unused = tmp_path / "unused-library"
    unused.mkdir()
    config["library_roots"].append({
        "id": "unused",
        "name": "暂未使用",
        "path": str(unused),
        "enabled": True,
    })

    result = inspect_startup_readiness(
        config,
        provider_probe=lambda provider: (True, "ok"),
    )

    library = next(item for item in result["checks"] if item["id"] == "library")
    assert result["state"] == "PASS"
    assert library["status"] == "PASS"


# Requirement: REQ-20260831-214244
def test_configuration_check_blocks_rule_target_without_required_permissions(
    tmp_path, monkeypatch,
):
    config = _config(tmp_path)

    monkeypatch.setattr(
        "media_importer.features.configuration.startup_readiness.inspect_storage_readiness",
        lambda _config: {
            "state": "BLOCKED",
            "automatic_allowed": False,
            "blocking": ["target:movies"],
            "warnings": [],
            "locations": [{
                "id": "target:movies",
                "role": "target",
                "level": "error",
                "message": "目录权限不足",
                "capabilities": {"read": True, "write": False},
            }],
        },
    )

    result = inspect_startup_readiness(
        config,
        provider_probe=lambda provider: (True, "ok"),
    )

    library = next(item for item in result["checks"] if item["id"] == "library")
    assert result["state"] == "BLOCKED"
    assert library["label"] == "规则与目标片库"
    assert library["status"] == "BLOCKED"
    assert library["fix_target"] == "storage"
    assert "电影的目标片库不可用：目录权限不足" in library["message"]

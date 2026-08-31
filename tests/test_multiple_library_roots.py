from media_importer.features.configuration.storage_readiness import inspect_storage_readiness
from media_importer.features.import_flow.services.classification import ClassificationService
from media_importer.features.import_flow.services.paths import allowed_dirs_from_config


def _config(tmp_path):
    paths = {}
    for name in ("source", "temp", "recycle", "resources", "movies", "tv"):
        path = tmp_path / name
        path.mkdir()
        paths[name] = str(path)
    return {
        "source_dir": paths["source"],
        "temp_dir": paths["temp"],
        "resource_dir": paths["resources"],
        "source_policy": {"mode": "preserve_all", "recycle_dir": paths["recycle"]},
        "library_roots": [
            {"id": "movies", "name": "电影盘", "path": paths["movies"], "enabled": True},
            {"id": "tv", "name": "剧集盘", "path": paths["tv"], "enabled": True},
        ],
        "default_library_root_id": "movies",
        "path_rules": [
            {"conditions": {"media_type": "movie"}, "library_root_id": "movies", "template": "电影/{title_cn}"},
            {"conditions": {"media_type": "tv"}, "library_root_id": "tv", "template": "剧集/{title_cn}"},
        ],
        "fallback_library_root_id": "movies",
        "fallback_dir": "其他",
    }, paths


def test_classification_routes_different_rules_to_different_roots(tmp_path):
    config, paths = _config(tmp_path)
    movie = ClassificationService(config).classify_task({
        "scrape_result": {"title_cn": "沙丘", "dimensions": {"media_type": "movie"}},
    })
    tv = ClassificationService(config).classify_task({
        "scrape_result": {"title_cn": "三体", "dimensions": {"media_type": "tv"}},
    })

    assert movie.import_path == f'{paths["movies"]}/电影/沙丘'
    assert tv.import_path == f'{paths["tv"]}/剧集/三体'


def test_all_enabled_roots_are_in_allowed_directories_and_readiness(tmp_path):
    config, paths = _config(tmp_path)

    assert set(allowed_dirs_from_config(config)) >= {
        paths["source"], paths["temp"], paths["movies"], paths["tv"],
    }
    report = inspect_storage_readiness(config)
    targets = {item["id"]: item for item in report["locations"] if item["role"] == "target"}
    assert set(targets) == {"target:movies", "target:tv"}
    assert all(item["level"] == "ok" for item in targets.values())
    resources = [item for item in report["locations"] if item["role"] == "resource"]
    assert len(resources) == 1
    assert resources[0]["path"] == paths["resources"]
    assert resources[0]["level"] == "ok"


def test_readiness_does_not_infer_targets_from_legacy_rules():
    report = inspect_storage_readiness({
        "source_dir": "",
        "temp_dir": "",
        "source_policy": {"recycle_dir": ""},
        "path_rules": [
            {"template": "/vol1/movies/{title_cn}"},
            {"template": "/vol2/tv/{title_cn}"},
        ],
    }, authorization_capability={"enforced": False, "available": False, "folders": []})

    assert [item for item in report["locations"] if item["role"] == "target"] == []


def test_ten_library_roots_remain_independent_without_a_product_limit(tmp_path):
    config, _paths = _config(tmp_path)
    roots = []
    for index in range(10):
        path = tmp_path / f"disk-{index}"
        path.mkdir()
        roots.append({
            "id": f"disk-{index}", "name": f"片库 {index + 1}",
            "path": str(path), "enabled": True,
        })
    config["library_roots"] = roots
    config["default_library_root_id"] = "disk-0"
    config["library_root"] = roots[0]["path"]
    config["path_rules"] = [{"library_root_id": "disk-0", "template": "电影/{title_cn}"}]

    report = inspect_storage_readiness(config)
    targets = [item for item in report["locations"] if item["role"] == "target"]

    assert len(targets) == 10
    assert [item["label"] for item in targets] == [f"片库 {index}" for index in range(1, 11)]

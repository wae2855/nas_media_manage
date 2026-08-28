from media_importer.features.configuration.storage_readiness import inspect_storage_readiness


def _config(tmp_path):
    source = tmp_path / "source"
    temp = tmp_path / "temp"
    recycle = tmp_path / "recycle"
    target = tmp_path / "target"
    for path in (source, temp, recycle, target):
        path.mkdir()
    return {
        "source_dir": str(source),
        "temp_dir": str(temp),
        "source_policy": {"recycle_dir": str(recycle)},
        "fallback_dir": str(target),
    }


def test_existing_local_locations_are_ready(tmp_path):
    result = inspect_storage_readiness(_config(tmp_path))

    assert result["state"] == "READY"
    assert result["blocking"] == []
    assert {item["role"] for item in result["locations"]} == {
        "source", "temp", "recycle", "target",
    }


def test_missing_source_is_blocked_without_creating_it(tmp_path):
    config = _config(tmp_path)
    missing = tmp_path / "unmounted-source"
    config["source_dir"] = str(missing)

    result = inspect_storage_readiness(config)

    assert result["state"] == "BLOCKED"
    assert "source" in result["blocking"]
    assert not missing.exists()


def test_identity_change_is_blocked(tmp_path):
    config = _config(tmp_path)
    config["storage_identities"] = {
        "source": {
            "realpath": config["source_dir"],
            "device": -1,
            "mount_source": "different",
        }
    }

    result = inspect_storage_readiness(config)
    source = next(item for item in result["locations"] if item["role"] == "source")

    assert result["state"] == "BLOCKED"
    assert source["status"] == "RECOVERING"
    assert "身份已变化" in source["message"]


def test_capacity_shortage_blocks_write_roles(tmp_path):
    config = _config(tmp_path)
    result = inspect_storage_readiness(config, write_bytes=10 ** 30)

    assert result["state"] == "BLOCKED"
    assert any(item["message"] == "磁盘可用空间不足" for item in result["locations"])


def test_distinct_volume_level_target_roots_are_not_collapsed():
    from media_importer.features.configuration.storage_readiness import _target_roots

    roots = _target_roots({
        "path_rules": [
            {"template": "/vol1/library-a"},
            {"template": "/vol1/library-b"},
        ],
    })

    assert roots == ["/vol1/library-a", "/vol1/library-b"]

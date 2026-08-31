from media_importer.features.configuration.storage_readiness import (
    MountIdentity,
    inspect_storage_readiness,
)


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
        "library_roots": [
            {"id": "main", "name": "主片库", "path": str(target), "enabled": True},
        ],
        "default_library_root_id": "main",
        "library_root": str(target),
        "fallback_library_root_id": "main",
        "fallback_dir": "未分类",
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


def test_legacy_rules_are_not_inferred_as_fresh_target_roots():
    from media_importer.features.configuration.storage_readiness import _target_roots

    roots = _target_roots({
        "path_rules": [
            {"template": "/vol1/library-a"},
            {"template": "/vol1/library-b"},
        ],
    })

    assert roots == []


def test_remote_source_warns_but_remote_recycle_is_blocked(tmp_path, monkeypatch):
    config = _config(tmp_path)

    def remote_identity(path):
        return MountIdentity(
            realpath=str(path), device=1, filesystem_type="fuse.rclone",
            mount_point=str(path), mount_source="remote:test", locality="remote",
        )

    monkeypatch.setattr(
        "media_importer.features.configuration.storage_readiness.inspect_mount",
        remote_identity,
    )
    result = inspect_storage_readiness(config)
    source = next(item for item in result["locations"] if item["role"] == "source")
    recycle = next(item for item in result["locations"] if item["role"] == "recycle")

    assert source["level"] == "warning"
    assert source["capabilities"]["automatic"] is False
    assert recycle["level"] == "error"
    assert "本地磁盘" in recycle["message"]


def test_fnos_ungranted_external_path_blocks_before_filesystem_check(tmp_path):
    config = _config(tmp_path)
    capability = {
        "enforced": True,
        "available": True,
        "folders": [config["temp_dir"]],
    }

    result = inspect_storage_readiness(config, authorization_capability=capability)
    source = next(item for item in result["locations"] if item["role"] == "source")

    assert result["state"] == "BLOCKED"
    assert source["authorization"]["authorized"] is False
    assert "尚未授权" in source["message"]


def test_fnos_authorized_parent_covers_role_subdirectories(tmp_path):
    config = _config(tmp_path)
    capability = {
        "enforced": True,
        "available": True,
        "folders": [str(tmp_path)],
    }

    result = inspect_storage_readiness(config, authorization_capability=capability)

    assert result["state"] == "READY"
    external = [item for item in result["locations"] if item["role"] in {"source", "target", "recycle"}]
    assert all(item["authorization"]["authorized"] for item in external)


# Requirement: REQ-20260831-004019
def test_storage_readiness_blocks_overlapping_source_and_library(tmp_path):
    config = _config(tmp_path)
    config["source_dir"] = config["library_root"]

    result = inspect_storage_readiness(config)

    assert result["state"] == "BLOCKED"
    topology = [item for item in result["locations"] if item["role"] == "topology"]
    assert topology
    assert any("文件来源" in item["message"] and "片库" in item["message"] for item in topology)

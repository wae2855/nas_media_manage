from media_importer.features.configuration.storage_readiness import (
    MountIdentity,
    inspect_processing_support_readiness,
    inspect_selected_target_readiness,
    inspect_source_scan_readiness,
    inspect_storage_readiness,
)


def _config(tmp_path):
    source = tmp_path / "source"
    recycle = tmp_path / "recycle"
    target = tmp_path / "target"
    for path in (source, recycle, target):
        path.mkdir()
    return {
        "source_dir": str(source),
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
        "source", "recycle", "target",
    }
    target = next(item for item in result["locations"] if item["role"] == "target")
    assert target["capabilities"]["read"] is True
    assert target["capabilities"]["create"] is True
    assert target["capabilities"]["update"] is True
    assert target["capabilities"]["delete"] is False
    assert "不执行通用删除" in target["message"]
    for item in result["locations"]:
        if item["role"] == "recycle":
            assert item["capabilities"]["delete"] is True


# Requirement: REQ-20260902-013607
def test_scoped_readiness_touches_only_stage_owned_directories(tmp_path, monkeypatch):
    config = _config(tmp_path)
    target_two = tmp_path / "target-two"
    target_two.mkdir()
    config["library_roots"].append({
        "id": "second", "name": "第二片库", "path": str(target_two), "enabled": True,
    })
    writes = []
    monkeypatch.setattr(
        "media_importer.features.configuration.storage_readiness._check_write",
        lambda path: writes.append(path) or (True, ""),
    )

    source = inspect_source_scan_readiness(config)
    assert source["automatic_allowed"] is True
    assert writes == []

    support = inspect_processing_support_readiness(config)
    assert support["automatic_allowed"] is True
    assert set(writes) == {config["source_policy"]["recycle_dir"]}
    assert str(tmp_path / "target") not in writes
    assert str(target_two) not in writes

    writes.clear()
    selected = inspect_selected_target_readiness(
        config,
        str(target_two / "movies" / "Example"),
    )
    assert selected["automatic_allowed"] is True
    assert writes == [str(target_two)]


def test_selected_target_fails_closed_when_modern_roots_overlap(tmp_path):
    outer = tmp_path / "library"
    inner = outer / "nested"
    inner.mkdir(parents=True)
    config = _config(tmp_path)
    config["library_roots"] = [
        {"id": "outer", "path": str(outer), "enabled": True},
        {"id": "inner", "path": str(inner), "enabled": True},
    ]

    result = inspect_selected_target_readiness(
        config,
        str(inner / "Movie"),
    )

    assert result["automatic_allowed"] is False
    assert "无法唯一归属" in result["locations"][0]["message"]


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


def test_device_number_change_is_not_a_mount_change(tmp_path, monkeypatch):
    config = _config(tmp_path)
    source_path = config["source_dir"]
    config["storage_identities"] = {
        "source": {
            "realpath": source_path,
            "device": 56,
            "filesystem_type": "btrfs",
            "mount_point": str(tmp_path),
            "mount_source": "/dev/mapper/stable-volume",
        }
    }

    original = __import__(
        "media_importer.features.configuration.storage_readiness",
        fromlist=["inspect_mount"],
    ).inspect_mount

    def renumbered_identity(path):
        identity = original(path)
        return MountIdentity(
            realpath=identity.realpath,
            device=61,
            filesystem_type="btrfs",
            mount_point=str(tmp_path),
            mount_source="/dev/mapper/stable-volume",
            locality="local",
        )

    monkeypatch.setattr(
        "media_importer.features.configuration.storage_readiness.inspect_mount",
        renumbered_identity,
    )
    result = inspect_storage_readiness(config)
    source = next(item for item in result["locations"] if item["role"] == "source")

    assert source["level"] == "ok"
    assert source["identity"]["device"] == 61


def test_mount_source_change_still_requires_rebinding(tmp_path, monkeypatch):
    config = _config(tmp_path)
    source_path = config["source_dir"]
    config["storage_identities"] = {
        "source": {
            "realpath": source_path,
            "device": 56,
            "filesystem_type": "btrfs",
            "mount_point": str(tmp_path),
            "mount_source": "/dev/mapper/old-volume",
        }
    }

    monkeypatch.setattr(
        "media_importer.features.configuration.storage_readiness.inspect_mount",
        lambda path: MountIdentity(
            realpath=str(path), device=61, filesystem_type="btrfs",
            mount_point=str(tmp_path), mount_source="/dev/mapper/new-volume",
            locality="local",
        ),
    )
    result = inspect_storage_readiness(config)
    source = next(item for item in result["locations"] if item["role"] == "source")

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


def test_remote_source_can_automate_but_remote_recycle_is_blocked(tmp_path, monkeypatch):
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
    assert source["capabilities"]["automatic"] is True
    assert recycle["level"] == "error"
    assert "本地磁盘" in recycle["message"]


# Requirement: REQ-20260901-001019-2
def test_recognized_remote_source_allows_automation_with_local_support_dirs(
    tmp_path, monkeypatch,
):
    config = _config(tmp_path)
    source_path = config["source_dir"]
    original = __import__(
        "media_importer.features.configuration.storage_readiness",
        fromlist=["inspect_mount"],
    ).inspect_mount

    def source_is_remote(path):
        if str(path) == source_path:
            return MountIdentity(
                realpath=str(path), device=1, filesystem_type="fuse.rclone",
                mount_point=str(path), mount_source="remote:test", locality="remote",
            )
        return original(path)

    monkeypatch.setattr(
        "media_importer.features.configuration.storage_readiness.inspect_mount",
        source_is_remote,
    )

    result = inspect_storage_readiness(config)
    source = next(item for item in result["locations"] if item["role"] == "source")

    assert result["state"] == "READY"
    assert result["automatic_allowed"] is True
    assert result["automatic_blocking"] == []
    assert result["warnings"] == ["source"]
    assert source["identity"]["filesystem_type"] == "fuse.rclone"
    assert "每轮扫描前复核" in source["message"]


# Requirement: REQ-20260901-001019-2
def test_unknown_source_remains_manual_only(tmp_path, monkeypatch):
    config = _config(tmp_path)
    source_path = config["source_dir"]
    original = __import__(
        "media_importer.features.configuration.storage_readiness",
        fromlist=["inspect_mount"],
    ).inspect_mount

    def source_is_unknown(path):
        if str(path) == source_path:
            return MountIdentity(
                realpath=str(path), device=1, filesystem_type="unknown",
                mount_point="", mount_source="unknown", locality="unknown",
            )
        return original(path)

    monkeypatch.setattr(
        "media_importer.features.configuration.storage_readiness.inspect_mount",
        source_is_unknown,
    )

    result = inspect_storage_readiness(config)

    assert result["state"] == "READY"
    assert result["automatic_allowed"] is False
    assert result["automatic_blocking"] == ["source"]


def test_fnos_ungranted_external_path_blocks_before_filesystem_check(tmp_path):
    config = _config(tmp_path)
    capability = {
        "enforced": True,
        "available": True,
        "folders": [config["source_policy"]["recycle_dir"]],
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


def test_fnos_private_service_directories_use_real_access_not_shared_acl(tmp_path, monkeypatch):
    config = _config(tmp_path)
    logs = tmp_path / "logs"
    resources = tmp_path / "resources"
    logs.mkdir()
    resources.mkdir()
    config.update({"log_dir": str(logs), "resource_dir": str(resources)})
    config["storage_identities"] = {
        "log": {"realpath": "/stale/install/logs", "device": 1, "mount_source": "old"},
        "resource": {"realpath": "/stale/install/resources", "device": 1, "mount_source": "old"},
    }
    monkeypatch.setenv("TRIM_PKGVAR", str(tmp_path))
    capability = {
        "enforced": True,
        "available": True,
        "folders": [config["source_dir"], config["library_root"]],
    }

    result = inspect_storage_readiness(config, authorization_capability=capability)
    managed = [item for item in result["locations"] if item["role"] in {"recycle", "log", "resource"}]

    assert all(item["managed_by_app"] for item in managed)
    assert all(item["level"] == "ok" for item in managed)
    assert all("authorization" not in item for item in managed)
    assert all("无需 fnOS" in item["message"] for item in managed)


# Requirement: REQ-20260831-004019
def test_storage_readiness_blocks_overlapping_source_and_library(tmp_path):
    config = _config(tmp_path)
    config["source_dir"] = config["library_root"]

    result = inspect_storage_readiness(config)

    assert result["state"] == "BLOCKED"
    topology = [item for item in result["locations"] if item["role"] == "topology"]
    assert topology
    assert any("文件来源" in item["message"] and "片库" in item["message"] for item in topology)

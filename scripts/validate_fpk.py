#!/usr/bin/env python3
"""Validate an fnOS FPK's structure and release-critical contents."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath

OUTER_REQUIRED = {
    "manifest",
    "app.tgz",
    "cmd/main",
    "cmd/install_callback",
    "cmd/upgrade_callback",
    "cmd/uninstall_callback",
    "cmd/config_callback",
    "wizard/install",
    "wizard/config",
    "wizard/uninstall",
    "config/resource",
    "config/privilege",
}
INNER_REQUIRED = {
    "ui/config",
    "ui/index.cgi",
    "server/VERSION",
    "server/fnos_config.py",
    "server/config.yaml.example",
    "server/requirements.txt",
    "server/requirements-fnos.lock",
    "server/THIRD_PARTY_NOTICES.md",
    "server/media_importer/features/configuration/fnos_directory_access.py",
    "server/media_importer/features/configuration/storage_readiness.py",
    "server/media_importer/features/configuration/application_service.py",
    "server/media_importer/features/configuration/startup_readiness.py",
    "server/media_importer/features/configuration/library_paths.py",
    "server/media_importer/features/configuration/storage_topology.py",
    "server/media_importer/features/source_files/source_units.py",
    "server/media_importer/core/task_manager.py",
    "server/media_importer/core/logger.py",
    "server/media_importer/infrastructure/filesystem/safety.py",
    "server/media_importer/features/recycle/manager.py",
    "server/media_importer/features/recycle/browser.py",
    "server/media_importer/features/scraping/thumbnail_cache.py",
    "server/media_importer/features/scraping/thumbnail_downloader.py",
    "server/media_importer/features/source_cleaning/application_service.py",
    "server/media_importer/monitor/file_watcher.py",
    "server/media_importer/api/config_save.py",
    "server/media_importer/features/import_flow/services/dedup.py",
    "server/media_importer/features/import_flow/services/file_operations.py",
    "server/media_importer/features/tasks/delete_service.py",
    "server/media_importer/features/tasks/file_lifecycle_service.py",
    "server/media_importer/core/db/source_unit_repo.py",
}
JSON_FILES = {
    "wizard/install",
    "wizard/config",
    "wizard/uninstall",
    "config/resource",
    "config/privilege",
}
EXECUTABLE_FILES = {
    "cmd/main",
    "cmd/install_callback",
    "cmd/upgrade_callback",
    "cmd/uninstall_callback",
    "cmd/config_callback",
}
INNER_EXECUTABLE_FILES = {"ui/index.cgi"}


class ValidationError(ValueError):
    pass


def _normalize(name: str) -> str:
    return name.removeprefix("./")


def _forbidden(name: str) -> bool:
    path = PurePosixPath(_normalize(name))
    return (
        "__pycache__" in path.parts
        or path.name == ".DS_Store"
        or path.name == ".env"
        or path.suffix in {".pyc", ".db", ".sqlite", ".log"}
    )


def _manifest(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        if "=" not in raw_line or raw_line.lstrip().startswith("#"):
            continue
        key, value = raw_line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _wizard_fields(value) -> set[str]:
    if isinstance(value, dict):
        fields = {value["field"]} if isinstance(value.get("field"), str) else set()
        for child in value.values():
            fields.update(_wizard_fields(child))
        return fields
    if isinstance(value, list):
        fields: set[str] = set()
        for child in value:
            fields.update(_wizard_fields(child))
        return fields
    return set()


def _yaml_section_scalar(text: str, section: str, key: str) -> str:
    """Read one scalar from a top-level YAML section without a YAML dependency."""
    in_section = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not in_section:
            if raw_line == f"{section}:":
                in_section = True
            continue
        if stripped and not raw_line[:1].isspace():
            break
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(rf"^[ \t]+{re.escape(key)}:[ \t]*(.*?)[ \t]*$", raw_line)
        if match:
            return match.group(1).split("#", 1)[0].strip().strip("\"'")
    return ""


def validate(path: Path, expected_version: str | None = None) -> dict[str, object]:
    errors: list[str] = []
    try:
        outer = tarfile.open(path, "r:*")
    except (OSError, tarfile.TarError) as exc:
        raise ValidationError(f"无法读取 FPK: {exc}") from exc

    with outer:
        members = {_normalize(member.name): member for member in outer.getmembers()}
        missing = OUTER_REQUIRED - set(members)
        if missing:
            errors.append("外层缺少: " + ", ".join(sorted(missing)))
        forbidden = [name for name in members if _forbidden(name)]
        if forbidden:
            errors.append("外层包含禁止文件: " + ", ".join(sorted(forbidden)[:10]))

        for name in JSON_FILES & set(members):
            extracted = outer.extractfile(members[name])
            try:
                json.loads(extracted.read().decode("utf-8") if extracted else "")
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"JSON 无效 {name}: {exc}")

        for name in {"wizard/install", "wizard/config"} & set(members):
            extracted = outer.extractfile(members[name])
            try:
                wizard = json.loads(extracted.read().decode("utf-8") if extracted else "")
                forbidden_fields = _wizard_fields(wizard) & {"wizard_api_key", "wizard_port"}
                if forbidden_fields:
                    errors.append(f"{name} 暴露托管字段: " + ", ".join(sorted(forbidden_fields)))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass

        if "config/resource" in members:
            extracted = outer.extractfile(members["config/resource"])
            try:
                resource = json.loads(extracted.read().decode("utf-8") if extracted else "")
                if "trim.file.sharedAccess" not in resource.get("api-scope", []):
                    errors.append("config/resource 未声明 trim.file.sharedAccess")
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass

        for name in EXECUTABLE_FILES & set(members):
            if members[name].mode & 0o111 == 0:
                errors.append(f"脚本不可执行: {name}")
        if "cmd/main" in members:
            extracted = outer.extractfile(members["cmd/main"])
            command_main = extracted.read().decode("utf-8", errors="replace") if extracted else ""
            if "serve --host 127.0.0.1" not in command_main:
                errors.append("fnOS 服务必须只监听 127.0.0.1")
            if "serve --host 0.0.0.0" in command_main:
                errors.append("fnOS 服务禁止监听 0.0.0.0")

        manifest_data: dict[str, str] = {}
        if "manifest" in members:
            extracted = outer.extractfile(members["manifest"])
            manifest_data = _manifest(extracted.read().decode("utf-8") if extracted else "")
            if expected_version and manifest_data.get("version") != expected_version:
                errors.append(f"版本不匹配: {manifest_data.get('version')} != {expected_version}")
            dependencies = {item.strip() for item in manifest_data.get("install_dep_apps", "").split(",")}
            if "python312" not in dependencies:
                errors.append("manifest 未声明 python312")
            if manifest_data.get("micro_app") != "true":
                errors.append("manifest 未声明 micro_app=true")
            if manifest_data.get("disable_authorization_path") != "false":
                errors.append("manifest 必须保留 fnOS 目录授权入口")
            if manifest_data.get("service_port") != "14591":
                errors.append("manifest service_port 必须固定为 14591")
            if manifest_data.get("checkport") != "true":
                errors.append("manifest 固定服务端口必须声明 checkport=true")
            if manifest_data.get("maintainer") != "oneway":
                errors.append("manifest maintainer 必须为 oneway")
            repository_url = "https://github.com/wae2855/nas_media_manage"
            if manifest_data.get("maintainer_url") != repository_url:
                errors.append("manifest maintainer_url 必须指向公开 GitHub 仓库")
            if manifest_data.get("distributor_url") != repository_url:
                errors.append("manifest distributor_url 必须指向公开 GitHub 仓库")

        inner_names: set[str] = set()
        inner_members: dict[str, tarfile.TarInfo] = {}
        inner_text: dict[str, str] = {}
        if "app.tgz" in members:
            extracted = outer.extractfile(members["app.tgz"])
            try:
                with tarfile.open(fileobj=io.BytesIO(extracted.read() if extracted else b""), mode="r:gz") as inner:
                    inner_members = {_normalize(member.name): member for member in inner.getmembers()}
                    inner_names = set(inner_members)
                    for name in {
                        "server/VERSION",
                        "server/config.yaml.example",
                        "server/media_importer/features/import_flow/services/dedup.py",
                        "server/media_importer/features/import_flow/services/file_operations.py",
                        "server/media_importer/features/tasks/delete_service.py",
                        "server/media_importer/features/tasks/file_lifecycle_service.py",
                        "server/media_importer/features/source_files/source_units.py",
                        "server/media_importer/core/task_manager.py",
                        "server/media_importer/core/logger.py",
                        "server/media_importer/infrastructure/filesystem/safety.py",
                        "server/media_importer/features/recycle/manager.py",
                        "server/media_importer/features/recycle/browser.py",
                        "server/media_importer/features/scraping/thumbnail_cache.py",
                        "server/media_importer/features/scraping/thumbnail_downloader.py",
                        "server/media_importer/features/source_cleaning/application_service.py",
                        "server/media_importer/features/configuration/storage_readiness.py",
                        "server/media_importer/features/configuration/application_service.py",
                        "server/media_importer/monitor/file_watcher.py",
                        "server/media_importer/api/config_save.py",
                    } & inner_names:
                        member_file = inner.extractfile(inner_members[name])
                        inner_text[name] = (
                            member_file.read().decode("utf-8", errors="replace")
                            if member_file else ""
                        )
            except tarfile.TarError as exc:
                errors.append(f"app.tgz 无效: {exc}")
            inner_missing = INNER_REQUIRED - inner_names
            if inner_missing:
                errors.append("应用层缺少: " + ", ".join(sorted(inner_missing)))
            inner_forbidden = [name for name in inner_names if _forbidden(name)]
            if inner_forbidden:
                errors.append("应用层包含禁止文件: " + ", ".join(sorted(inner_forbidden)[:10]))
            for name in INNER_EXECUTABLE_FILES & inner_names:
                if inner_members[name].mode & 0o111 == 0:
                    errors.append(f"应用脚本不可执行: {name}")
            wheels = [name for name in inner_names if name.startswith("server/wheelhouse/") and name.endswith(".whl")]
            if not wheels:
                errors.append("应用层缺少离线 wheelhouse")
            elif any(not name.endswith("-none-any.whl") for name in wheels):
                errors.append("wheelhouse 包含平台相关 wheel，不能声明 platform=all")

            runtime_version = inner_text.get("server/VERSION", "").strip()
            manifest_version = manifest_data.get("version", "")
            if runtime_version != manifest_version:
                errors.append(
                    f"包内运行时版本与 manifest 不一致: {runtime_version or '<missing>'} != "
                    f"{manifest_version or '<missing>'}"
                )

            config_text = inner_text.get("server/config.yaml.example", "")
            if _yaml_section_scalar(config_text, "duplicate_handling", "strategy") != "confirm":
                errors.append("包内重复文件策略必须固定为逐项确认 confirm")

            dedup_text = inner_text.get(
                "server/media_importer/features/import_flow/services/dedup.py", ""
            )
            if "_recycle_duplicate(" in dedup_text:
                errors.append("包内去重检测仍包含自动处置片库文件逻辑")

            file_ops_text = inner_text.get(
                "server/media_importer/features/import_flow/services/file_operations.py", ""
            )
            if re.search(r"safe_delete\s*\(\s*dest_video\b", file_ops_text):
                errors.append("包内目标覆盖仍包含永久删除片库文件兜底")
            if "hash_file(existing_path) != expected_fingerprint" not in file_ops_text:
                errors.append("包内目标替换未使用内容哈希复核现有片库文件")
            if "incoming_paths" not in file_ops_text:
                errors.append("包内入库未保护被误标为输入的片库视频或字幕")
            if "os.replace(staged_video, dest_video)" in file_ops_text:
                errors.append("包内目标替换仍会无条件覆盖并发出现的片库文件")
            if "claimed_fingerprint != expected_fingerprint" not in file_ops_text:
                errors.append("包内目标替换未在长复制后再次复核现有文件内容")

            safety_text = inner_text.get(
                "server/media_importer/infrastructure/filesystem/safety.py", ""
            )
            if "_publish_file_noreplace" not in safety_text:
                errors.append("包内文件发布缺少禁止覆盖的原子门禁")
            if "O_NOFOLLOW" not in safety_text or "os.path.lexists(partial)" not in safety_text:
                errors.append("包内断点复制未拒绝符号链接临时文件")
            if 'prefix=".write_test_"' not in safety_text:
                errors.append("包内写权限检查仍可能使用可预测固定探针")

            recycle_text = inner_text.get(
                "server/media_importer/features/recycle/manager.py", ""
            )
            if "_write_json_exclusive" not in recycle_text or "O_NOFOLLOW" not in recycle_text:
                errors.append("包内回收记录未使用独占且不跟随链接的安全写入")

            recycle_browser_text = inner_text.get(
                "server/media_importer/features/recycle/browser.py", ""
            )
            if "os.rename(recycle_path, original_path)" in recycle_browser_text:
                errors.append("包内回收恢复仍可能覆盖并发出现的原位置文件")

            logger_text = inner_text.get("server/media_importer/core/logger.py", "")
            if "SafeRotatingFileHandler" not in logger_text or "O_NOFOLLOW" not in logger_text:
                errors.append("包内日志文件仍可能跟随符号链接写入片库")

            thumbnail_text = inner_text.get(
                "server/media_importer/features/scraping/thumbnail_cache.py", ""
            )
            if "_safe_thumbnail_root" not in thumbnail_text or "os.path.islink(root)" not in thumbnail_text:
                errors.append("包内缩略图清理未拒绝指向片库的目录符号链接")

            thumbnail_downloader_text = inner_text.get(
                "server/media_importer/features/scraping/thumbnail_downloader.py", ""
            )
            if "_safe_thumbnail_dir" not in thumbnail_downloader_text or "O_EXCL" not in thumbnail_downloader_text:
                errors.append("包内缩略图下载仍可能跟随或覆盖片库链接")

            config_save_text = inner_text.get("server/media_importer/api/config_save.py", "")
            if "captured_storage_identities" not in config_save_text:
                errors.append("包内目录选择未持久化挂载身份供运行时复核")

            source_cleaning_text = inner_text.get(
                "server/media_importer/features/source_cleaning/application_service.py", ""
            )
            if "inspect_storage_readiness" not in source_cleaning_text:
                errors.append("包内源清理未在文件动作前复核挂载身份")

            watcher_text = inner_text.get("server/media_importer/monitor/file_watcher.py", "")
            if (
                "_source_ready_for_scan" not in watcher_text
                or "_processing_support_ready" not in watcher_text
            ):
                errors.append("包内自动扫描未在每轮动作前复核挂载身份")

            storage_readiness_text = inner_text.get(
                "server/media_importer/features/configuration/storage_readiness.py", ""
            )
            if (
                "网盘来源当前在线" not in storage_readiness_text
                or '"automatic_allowed": state == "READY" and not automatic_blocking'
                not in storage_readiness_text
            ):
                errors.append("包内仍禁止已识别且在线的网盘来源自动扫描")

            watcher_status_text = inner_text.get(
                "server/media_importer/features/configuration/application_service.py", ""
            )
            if "configured_enabled" not in watcher_status_text:
                errors.append("包内 watcher 状态未区分配置意图与真实运行状态")

            delete_text = inner_text.get(
                "server/media_importer/features/tasks/delete_service.py", ""
            )
            if "_task_references_library_file" not in delete_text:
                errors.append("包内任务删除未按真实路径保护片库文件")

            lifecycle_text = inner_text.get(
                "server/media_importer/features/tasks/file_lifecycle_service.py", ""
            )
            if "path_in_library" not in lifecycle_text:
                errors.append("包内任务重命名未按真实路径保护片库文件")

            source_unit_text = inner_text.get(
                "server/media_importer/features/source_files/source_units.py", ""
            )
            if (
                'canonical_path(unit["source_root"])' not in source_unit_text
                or "import_roots=configured_library_roots" not in source_unit_text
            ):
                errors.append("包内历史来源单元未复核当前来源与片库边界")

            task_manager_text = inner_text.get(
                "server/media_importer/core/task_manager.py", ""
            )
            if "protected_paths" not in task_manager_text or "path_in_library" not in task_manager_text:
                errors.append("包内任务回收未同时保护片库视频和字幕")

    if errors:
        raise ValidationError("; ".join(errors))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": str(path),
        "version": manifest_data.get("version"),
        "sha256": digest,
        "outer_entries": len(members),
        "app_entries": len(inner_names),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fpk", type=Path)
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(validate(args.fpk, args.version), ensure_ascii=False, indent=2))
        return 0
    except ValidationError as exc:
        print(f"FPK 验证失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = ROOT / "docs"


def test_current_fact_docs_do_not_link_archive_as_primary_source():
    allowed_docs = {
        DOCS_ROOT / "legacy.md",
        DOCS_ROOT / "architecture" / "archive-policy.md",
        DOCS_ROOT / "architecture" / "repository-structure.md",
        DOCS_ROOT / "decisions" / "0001-ai-ready-documentation-system.md",
        DOCS_ROOT / "decisions" / "0002-domain-directory-migration-strategy.md",
        DOCS_ROOT / "decisions" / "0003-deploy-package-generation-strategy.md",
        DOCS_ROOT / "testing" / "test-inventory.md",
        DOCS_ROOT / "testing" / "known-failures.md",
    }

    fact_docs = list((DOCS_ROOT / "features").glob("*.md"))
    fact_docs += list((DOCS_ROOT / "architecture").glob("*.md"))
    fact_docs += list((DOCS_ROOT / "product").glob("*.md"))
    fact_docs += [DOCS_ROOT / "README.md", DOCS_ROOT / "INDEX.md", DOCS_ROOT / "ai-map.md"]

    violations = []
    for path in fact_docs:
        if path in allowed_docs or not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "docs/_archive/" in text:
            violations.append(str(path.relative_to(ROOT)))

    assert not violations, f"Current fact docs should not link archive as source: {violations}"


def test_cli_api_and_watcher_do_not_import_legacy_storage_scanner():
    paths = [
        ROOT / "media_importer" / "media_importer.py",
        ROOT / "media_importer" / "api" / "handler.py",
        ROOT / "media_importer" / "monitor" / "file_watcher.py",
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "from media_importer.storage.file_scanner import" not in source
        assert "from media_importer.features.import_flow import scan_source_dir" in source or (
            "from media_importer.features.import_flow.scan_service import FileScanner" in source
        )


def test_import_flow_rules_do_not_import_legacy_storage_business_helpers():
    paths = [
        ROOT / "media_importer" / "features" / "import_flow" / "steps" / "file.py",
        ROOT / "media_importer" / "features" / "import_flow" / "services" / "classification.py",
        ROOT / "media_importer" / "features" / "import_flow" / "services" / "dedup.py",
        ROOT / "media_importer" / "features" / "import_flow" / "services" / "import_service.py",
        ROOT / "media_importer" / "features" / "import_flow" / "services" / "source_cleanup.py",
        ROOT / "media_importer" / "features" / "import_flow" / "runner.py",
    ]

    forbidden = [
        "from media_importer.storage.classifier import",
        "from media_importer.storage.dedup_checker import",
        "from media_importer.storage.file_scanner import",
        "from media_importer.storage.file_mover import apply_filename_template",
        "from media_importer.storage.file_mover import move_to_import",
        "from media_importer.storage.file_mover import delete_source_files",
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        for banned in forbidden:
            assert banned not in source, f"{path.name} should not import {banned}"


def test_filesystem_safety_lives_in_infrastructure():
    source_paths = [
        ROOT / "media_importer" / "features" / "import_flow" / "run_file_service.py",
        ROOT / "media_importer" / "features" / "import_flow" / "services" / "file_operations.py",
        ROOT / "media_importer" / "infrastructure" / "filesystem" / "file_copier.py",
        ROOT / "media_importer" / "api" / "connectivity_handlers.py",
    ]
    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        assert "media_importer.core.safety" not in source

    # core/safety.py facade 已于简洁化 Phase 0 删除，不得复活
    assert not (ROOT / "media_importer" / "core" / "safety.py").exists(), (
        "core/safety.py 兼容 facade 已删除；安全能力直接使用 media_importer.infrastructure.filesystem"
    )


def test_source_file_strategy_lives_in_source_files_feature():
    source_paths = [
        ROOT / "media_importer" / "features" / "import_flow" / "runner.py",
        ROOT / "media_importer" / "features" / "import_flow" / "services" / "import_service.py",
    ]
    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        assert "from media_importer.features.source_files import" in source

    wrapper_source = (
        ROOT / "media_importer" / "features" / "import_flow" / "services" / "source_cleanup.py"
    ).read_text(encoding="utf-8")
    assert (
        "from media_importer.features.source_files import SourceCleanupResult, SourceCleanupService" in wrapper_source
    )


def test_source_files_feature_does_not_depend_on_import_flow():
    for path in (ROOT / "media_importer" / "features" / "source_files").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "media_importer.features.import_flow" not in source


def test_source_cleaner_api_handler_uses_feature_application_service():
    source = (ROOT / "media_importer" / "api" / "source_cleaner_handlers.py").read_text(encoding="utf-8")
    assert "from media_importer.features.source_cleaning.application_service import (" in source
    assert "from media_importer.core.db.task_repo import list_all_tasks" not in source


def test_dimension_api_handler_uses_feature_dimension_service():
    source = (ROOT / "media_importer" / "api" / "dimension_handlers.py").read_text(encoding="utf-8")
    assert "from media_importer.features.scraping import (" in source
    assert "from media_importer.core.db import (" not in source


def test_config_handler_delegates_runtime_component_refresh():
    source = (ROOT / "media_importer" / "api" / "config_handlers.py").read_text(encoding="utf-8")
    assert "apply_runtime_config" in source
    assert "restart_watcher" in source
    assert "from media_importer.notify.hermes_hook import HermesNotifier" not in source
    assert "from media_importer.monitor.file_watcher import FileWatcher" not in source


def test_config_handler_delegates_task_listing_to_tasks_feature():
    source = (ROOT / "media_importer" / "api" / "config_handlers.py").read_text(encoding="utf-8")
    assert "from media_importer.features.tasks import list_tasks_for_api" in source
    assert "from media_importer.core.db import list_tasks" not in source
    assert "from media_importer.core.db import VALID_STATUSES" not in source


def test_task_handler_delegates_queue_actions_to_tasks_feature():
    source = (ROOT / "media_importer" / "api" / "task_handlers.py").read_text(encoding="utf-8")
    assert "from media_importer.features.tasks import (" in source
    assert "clear_tasks_for_api" in source
    assert "retry_task_for_api" in source
    assert "retry_all_failed_for_api" in source
    assert "pause_queue_for_api" in source
    assert "resume_queue_for_api" in source
    assert "get_queue_status_for_api" in source
    assert "VALID_STATUSES" not in source


def test_task_handler_delegates_review_actions_to_tasks_feature():
    source = (ROOT / "media_importer" / "api" / "task_handlers.py").read_text(encoding="utf-8")
    assert "confirm_task_for_api" in source
    assert "reclassify_task_for_api" in source
    assert "confirm_all_tasks_for_api" in source
    assert "confirm_task(task_id)" not in source
    assert "reclassify_task(task_id" not in source
    assert 'list_tasks(status="CONFIRMING"' not in source


def test_task_handler_delegates_rename_to_tasks_file_lifecycle_service():
    source = (ROOT / "media_importer" / "api" / "task_handlers.py").read_text(encoding="utf-8")
    assert "rename_task_file_for_api" in source
    assert "os.rename" not in source
    assert "new_filename 只能是文件名" not in source


def test_task_handler_delegates_ignore_to_tasks_file_lifecycle_service():
    source = (ROOT / "media_importer" / "api" / "task_handlers.py").read_text(encoding="utf-8")
    assert "ignore_task_for_api" in source
    assert "os.remove" not in source
    assert "move_to_recycle_bin" not in source
    assert "update_task as db_update_task" not in source
    assert "update_subtitles_by_task as db_update_subtitles_by_task" not in source


def test_task_handler_delegates_run_file_to_import_flow_service():
    source = (ROOT / "media_importer" / "api" / "task_handlers.py").read_text(encoding="utf-8")
    assert "from media_importer.features.import_flow import run_batch_for_api, run_file_for_api" in source
    assert "run_batch_for_api" in source
    assert "validate_path_safety" not in source
    assert "validate_file_ext" not in source
    assert "create_task(" not in source
    assert "process_one(task)" not in source
    assert "file_size_mb" not in source


def test_task_handler_delegates_detail_queries_to_tasks_feature():
    source = (ROOT / "media_importer" / "api" / "task_handlers.py").read_text(encoding="utf-8")
    assert "get_task_for_api" in source
    assert "get_task_subtitles_for_api" in source
    assert "get_task_stats_for_api" in source
    assert "_global_task_manager.get_task" not in source
    assert "get_subtitles_by_task" not in source
    assert "count_by_status()" not in source


def test_no_production_code_imports_core_db_directly():
    """生产代码不得直接 import media_importer.core.db(core/db/ 和 infrastructure/db/ 自身除外)。

    DB 层的推荐入口是 media_importer.infrastructure.db facade。
    core/db/ 保留为真实实现,infrastructure/db/ 是 facade。
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    media_importer_root = root / "media_importer"
    core_db_root = media_importer_root / "core" / "db"
    infra_db_root = media_importer_root / "infrastructure" / "db"
    violations = []
    forbidden_pattern = re.compile(
        r"^\s*(?:from\s+media_importer\.core\.db|import\s+media_importer\.core\.db)",
        re.MULTILINE,
    )
    for py_file in media_importer_root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        if core_db_root in py_file.parents:
            continue
        if infra_db_root in py_file.parents:
            continue
        source = py_file.read_text(encoding="utf-8")
        for match in forbidden_pattern.finditer(source):
            line_no = source[: match.start()].count("\n") + 1
            violations.append(f"{py_file.relative_to(root)}:{line_no}: {match.group().strip()}")
    assert not violations, (
        "生产代码不得直接 import media_importer.core.db。以下违规需改为 infrastructure.db facade:\n"
        + "\n".join(violations)
    )


def test_no_production_code_imports_scraper_package():
    """scraper/ 兼容层已于 2026-08-22 删除（简洁化 Phase 0，ADR-0008 收尾）。

    守护两条：
    1. media_importer/scraper/ 目录不得复活；
    2. 任何代码（生产+测试）不得 import media_importer.scraper.*。
    """
    import re

    media_importer_root = ROOT / "media_importer"
    scraper_root = media_importer_root / "scraper"
    assert not scraper_root.exists(), "media_importer/scraper/ 兼容层已删除，不得重新引入"

    violations = []
    forbidden_pattern = re.compile(
        r"^\s*(?:from\s+media_importer\.scraper|import\s+media_importer\.scraper)",
        re.MULTILINE,
    )
    for py_file in ROOT.rglob("*.py"):
        if "__pycache__" in py_file.parts or ".venv" in py_file.parts:
            continue
        if "deploy" in py_file.parts:
            continue  # deploy/ 是生成的 package workspace（ADR-0003：build_fpk.sh 从根源码重建）
        if "docs" in py_file.parts and "_archive" in py_file.parts:
            continue
        source = py_file.read_text(encoding="utf-8")
        for match in forbidden_pattern.finditer(source):
            line_no = source[: match.start()].count("\n") + 1
            violations.append(f"{py_file.relative_to(ROOT)}:{line_no}: {match.group().strip()}")
    assert not violations, (
        "不得 import media_importer.scraper.*（兼容层已删除）。违规需改为 features.* 新路径:\n" + "\n".join(violations)
    )

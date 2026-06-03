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
    ]

    forbidden = [
        "from media_importer.storage.classifier import",
        "from media_importer.storage.dedup_checker import",
        "from media_importer.storage.file_scanner import",
        "from media_importer.storage.file_mover import apply_filename_template",
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        for banned in forbidden:
            assert banned not in source, f"{path.name} should not import {banned}"


def test_source_cleaner_api_handler_uses_feature_application_service():
    source = (
        ROOT / "media_importer" / "api" / "source_cleaner_handlers.py"
    ).read_text(encoding="utf-8")
    assert "from media_importer.features.source_cleaning.application_service import (" in source
    assert "from media_importer.core.db.task_repo import list_all_tasks" not in source


def test_dimension_api_handler_uses_feature_dimension_service():
    source = (
        ROOT / "media_importer" / "api" / "dimension_handlers.py"
    ).read_text(encoding="utf-8")
    assert "from media_importer.features.scraping import (" in source
    assert "from media_importer.core.db import (" not in source


def test_prompt_file_operations_live_in_prompts_feature():
    prompt_handler = (
        ROOT / "media_importer" / "api" / "prompt_handlers.py"
    ).read_text(encoding="utf-8")
    provider_handler = (
        ROOT / "media_importer" / "api" / "provider_handlers.py"
    ).read_text(encoding="utf-8")

    assert "from media_importer.features.prompts import (" in prompt_handler
    assert "from media_importer.features.prompts import (" in provider_handler
    for source in (prompt_handler, provider_handler):
        assert "ruamel.yaml" not in source
        assert "yaml.safe_load" not in source
        assert "system_prompt:" not in source


def test_config_handler_delegates_runtime_component_refresh():
    source = (
        ROOT / "media_importer" / "api" / "config_handlers.py"
    ).read_text(encoding="utf-8")
    assert "apply_runtime_config" in source
    assert "restart_watcher" in source
    assert "from media_importer.notify.hermes_hook import HermesNotifier" not in source
    assert "from media_importer.monitor.file_watcher import FileWatcher" not in source

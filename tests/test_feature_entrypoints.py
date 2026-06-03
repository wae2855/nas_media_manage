from pathlib import Path


def test_application_entrypoints_use_import_flow_feature_runner():
    root = Path(__file__).resolve().parents[1]
    entrypoints = [
        root / "media_importer" / "api" / "handler.py",
        root / "media_importer" / "media_importer.py",
    ]

    for path in entrypoints:
        source = path.read_text(encoding="utf-8")
        assert "from media_importer.features.import_flow import PipelineRunner" in source
        assert "from media_importer.features.import_flow import scan_source_dir" in source or path.name != "media_importer.py"
        assert "from media_importer.features.configuration import load_config, mask_sensitive" in source
        assert "from media_importer.features.tasks import TaskManager" in source
        assert "from media_importer.pipeline import PipelineRunner" not in source


def test_feature_consumers_use_feature_public_apis():
    root = Path(__file__).resolve().parents[1]
    expected_imports = {
        root / "media_importer" / "api" / "dimension_handlers.py": [
            "from media_importer.features.scraping import (",
            "get_dimension_detail",
            "update_dimension_detail",
            "enable_dimension_detail",
            "disable_dimension_detail",
            "reset_dimension_detail",
        ],
        root / "media_importer" / "api" / "task_delete.py": [
            "from media_importer.features.tasks import delete_task as delete_task_service",
        ],
        root / "media_importer" / "api" / "task_handlers.py": [
            "from media_importer.features.import_flow import run_batch_for_api, run_file_for_api",
            "from media_importer.features.tasks import (",
            "clear_tasks_for_api",
            "confirm_all_tasks_for_api",
            "confirm_task_for_api",
            "get_queue_status_for_api",
            "get_task_for_api",
            "get_task_stats_for_api",
            "get_task_subtitles_for_api",
            "ignore_task_for_api",
            "pause_queue_for_api",
            "reclassify_task_for_api",
            "rename_task_file_for_api",
            "resume_queue_for_api",
            "retry_all_failed_for_api",
            "retry_task_for_api",
        ],
        root / "media_importer" / "api" / "handler.py": [
            "from media_importer.features.import_flow import PipelineRunner",
            "from media_importer.features.import_flow import scan_source_dir",
        ],
        root / "media_importer" / "api" / "connectivity_handlers.py": [
            "from media_importer.features.scraping import TMDbClient",
            "from media_importer.features.configuration import test_llm_api",
            "from media_importer.features.configuration import test_hermes_webhook",
        ],
        root / "media_importer" / "api" / "config_handlers.py": [
            "from media_importer.features.configuration import (",
            "build_config_ui_payload",
            "build_section_config_update",
            "build_config_permission_payload",
            "build_path_test_payload",
            "build_watcher_status_payload",
            "apply_runtime_config",
            "restart_watcher",
            "from media_importer.features.tasks import list_tasks_for_api",
        ],
        root / "media_importer" / "api" / "tmdb_handlers.py": [
            "from media_importer.features.scraping import TMDbClient",
            "from media_importer.features.scraping import TMDbClient, TMDbError",
        ],
        root / "media_importer" / "features" / "import_flow" / "steps" / "scrape.py": [
            "from media_importer.features.scraping import get_dimensions_for_file",
        ],
        root / "media_importer" / "features" / "import_flow" / "runner.py": [
            "from media_importer.infrastructure.filesystem import FileCopier",
            "from media_importer.features.source_files import SourceCleanupService",
            "from media_importer.features.import_flow.scan_service import FileScanner",
            "from media_importer.features.import_flow.services.file_operations import delete_source_files",
        ],
        root / "media_importer" / "features" / "import_flow" / "services" / "classification.py": [
            "from .classification_rules import classify, render_template",
        ],
        root / "media_importer" / "features" / "import_flow" / "services" / "dedup.py": [
            "from media_importer.features.source_files import SourceCleanupService",
            "from .dedup_rules import check_duplicate",
        ],
        root / "media_importer" / "features" / "import_flow" / "steps" / "file.py": [
            "from media_importer.features.import_flow.services.naming import apply_filename_template",
        ],
        root / "media_importer" / "features" / "import_flow" / "services" / "import_service.py": [
            "from media_importer.features.source_files import SourceCleanupResult, SourceCleanupService",
            "from .file_operations import move_to_import",
        ],
        root / "media_importer" / "features" / "import_flow" / "services" / "source_cleanup.py": [
            "from media_importer.features.source_files import SourceCleanupResult, SourceCleanupService",
        ],
        root / "media_importer" / "storage" / "classifier.py": [
            "from media_importer.features.import_flow.services.classification_rules import",
        ],
        root / "media_importer" / "storage" / "dedup_checker.py": [
            "from media_importer.features.import_flow.services.dedup_rules import",
        ],
        root / "media_importer" / "storage" / "file_scanner.py": [
            "from media_importer.features.import_flow.scan_service import FileScanner, scan_source_dir",
        ],
        root / "media_importer" / "storage" / "file_copier.py": [
            "from media_importer.infrastructure.filesystem import FileCopier",
        ],
        root / "media_importer" / "monitor" / "file_watcher.py": [
            "from media_importer.features.import_flow import scan_source_dir",
        ],
        root / "media_importer" / "storage" / "file_mover.py": [
            "from media_importer.features.import_flow.services.file_operations import (",
            "from media_importer.features.import_flow.services.naming import (",
        ],
        root / "media_importer" / "storage" / "source_cleaner.py": [
            "from media_importer.features.source_cleaning import cleaner as _cleaner",
            "sys.modules[__name__] = _cleaner",
        ],
        root / "media_importer" / "api" / "source_cleaner_handlers.py": [
            "from media_importer.features.source_cleaning.application_service import (",
            "preview_source_cleaning",
            "execute_source_cleaning",
            "get_source_cleaner_status",
        ],
        root / "media_importer" / "features" / "scraping" / "metadata_scraper.py": [
            "from media_importer.features.configuration import ConfigView",
            "from media_importer.features.providers import create_providers",
            "from media_importer.features.providers import (",
            "from media_importer.features.scraping.confidence_engine import",
        ],
        root / "media_importer" / "scraper" / "providers" / "__init__.py": [
            "from media_importer.features.providers import",
        ],
        root / "media_importer" / "scraper" / "providers" / "base.py": [
            "from media_importer.features.providers.base import",
        ],
        root / "media_importer" / "scraper" / "providers" / "tmdb_provider.py": [
            "from media_importer.features.providers.tmdb_provider import TMDbProvider",
        ],
        root / "media_importer" / "scraper" / "confidence_engine.py": [
            "from media_importer.features.scraping.confidence_engine import",
        ],
        root / "media_importer" / "scraper" / "dimension_manager.py": [
            "from media_importer.features.scraping.dimension_manager import",
        ],
        root / "media_importer" / "scraper" / "metadata_scraper.py": [
            "from media_importer.features.scraping.metadata_scraper import MetadataScraper",
        ],
        root / "media_importer" / "scraper" / "llm_scraper.py": [
            "from media_importer.features.configuration import ConfigView",
            "from media_importer.features.prompts.prompt_builder import LLMPromptBuilder",
        ],
        root / "media_importer" / "scraper" / "llm_prompts.py": [
            "from media_importer.features.prompts.prompt_builder import LLMPromptBuilder",
        ],
        root / "media_importer" / "api" / "prompt_handlers.py": [
            "from media_importer.features.prompts import (",
            "load_global_prompt_for_ui",
            "save_global_prompt",
            "reset_global_prompt",
        ],
        root / "media_importer" / "api" / "provider_handlers.py": [
            "from media_importer.features.prompts import (",
            "load_provider_prompt_for_ui",
            "save_provider_prompt",
            "reset_provider_prompt",
        ],
    }

    forbidden_imports = [
        "from media_importer.core.config_view import ConfigView",
        "from media_importer.scraper.dimension_manager import",
        "from media_importer.scraper.tmdb_client import",
        "from media_importer.core.db.task_repo import list_all_tasks",
    ]

    for path, imports in expected_imports.items():
        source = path.read_text(encoding="utf-8")
        for expected in imports:
            assert expected in source
        for forbidden in forbidden_imports:
            assert forbidden not in source


def test_feature_public_apis_are_importable():
    from media_importer.features.configuration import ConfigView, load_config, mask_sensitive
    from media_importer.features.configuration import (
        build_config_permission_payload,
        build_config_ui_payload,
        build_path_test_payload,
        build_section_config_update,
        build_watcher_status_payload,
        apply_runtime_config,
        restart_watcher,
    )
    from media_importer.features.import_flow import (
        FileScanner,
        run_batch_for_api,
        run_file_for_api,
        scan_source_dir,
    )
    from media_importer.features.import_flow.services.classification_rules import classify
    from media_importer.features.import_flow.services.dedup_rules import check_duplicate
    from media_importer.features.import_flow.services.file_operations import move_to_import
    from media_importer.features.import_flow.services.naming import apply_filename_template
    from media_importer.features.source_files import SourceCleanupService
    from media_importer.features.source_cleaning import SourceCleaner
    from media_importer.features.tasks import delete_task
    from media_importer.features.tasks import (
        clear_tasks_for_api,
        confirm_all_tasks_for_api,
        confirm_task_for_api,
        get_queue_status_for_api,
        get_task_for_api,
        get_task_stats_for_api,
        get_task_subtitles_for_api,
        ignore_task_for_api,
        pause_queue_for_api,
        reclassify_task_for_api,
        rename_task_file_for_api,
        resume_queue_for_api,
        retry_all_failed_for_api,
        retry_task_for_api,
    )
    from media_importer.features.providers import (
        MetadataProvider,
        TMDbProvider,
        create_providers,
        get_provider_class,
    )
    from media_importer.features.prompts import LLMPromptBuilder
    from media_importer.features.prompts import (
        load_global_prompt_for_ui,
        load_provider_prompt_for_ui,
        reset_global_prompt,
        reset_provider_prompt,
        save_global_prompt,
        save_provider_prompt,
    )
    from media_importer.features.scraping import (
        CleanResult,
        ConfidenceEngine,
        DimensionActionResult,
        LLMScraper,
        MetadataScraper,
        TMDbClient,
        disable_dimension_detail,
        enable_dimension_detail,
        check_tier_access,
        get_dimension_detail,
        get_dimensions_for_file,
        list_dimensions,
        list_enabled_dimensions,
        reset_dimension_detail,
        update_dimension_detail,
    )
    from media_importer.features.tasks import TaskManager, mark_imported
    from media_importer.features.tasks import TaskListResult, list_tasks_for_api
    from media_importer.features.tasks.repository import create_task, update_task
    from media_importer.infrastructure.db import init_db
    from media_importer.infrastructure.filesystem import FileCopier

    assert ConfigView is not None
    assert build_config_ui_payload.__module__ == "media_importer.features.configuration.application_service"
    assert build_section_config_update.__module__ == "media_importer.features.configuration.application_service"
    assert build_config_permission_payload.__module__ == "media_importer.features.configuration.application_service"
    assert build_path_test_payload.__module__ == "media_importer.features.configuration.application_service"
    assert build_watcher_status_payload.__module__ == "media_importer.features.configuration.application_service"
    assert apply_runtime_config.__module__ == "media_importer.features.configuration.runtime_service"
    assert restart_watcher.__module__ == "media_importer.features.configuration.runtime_service"
    assert FileScanner.__module__ == "media_importer.features.import_flow.scan_service"
    assert run_batch_for_api.__module__ == "media_importer.features.import_flow.run_file_service"
    assert run_file_for_api.__module__ == "media_importer.features.import_flow.run_file_service"
    assert scan_source_dir.__module__ == "media_importer.features.import_flow.scan_service"
    assert classify.__module__ == "media_importer.features.import_flow.services.classification_rules"
    assert check_duplicate.__module__ == "media_importer.features.import_flow.services.dedup_rules"
    assert move_to_import.__module__ == "media_importer.features.import_flow.services.file_operations"
    assert apply_filename_template.__module__ == "media_importer.features.import_flow.services.naming"
    assert SourceCleanupService.__module__ == "media_importer.features.source_files.cleanup_service"
    assert SourceCleaner.__module__ == "media_importer.features.source_cleaning.cleaner"
    assert delete_task.__module__ == "media_importer.features.tasks.delete_service"
    assert clear_tasks_for_api.__module__ == "media_importer.features.tasks.queue_service"
    assert confirm_all_tasks_for_api.__module__ == "media_importer.features.tasks.review_service"
    assert confirm_task_for_api.__module__ == "media_importer.features.tasks.review_service"
    assert get_queue_status_for_api.__module__ == "media_importer.features.tasks.queue_service"
    assert get_task_for_api.__module__ == "media_importer.features.tasks.detail_service"
    assert get_task_stats_for_api.__module__ == "media_importer.features.tasks.detail_service"
    assert get_task_subtitles_for_api.__module__ == "media_importer.features.tasks.detail_service"
    assert ignore_task_for_api.__module__ == "media_importer.features.tasks.file_lifecycle_service"
    assert pause_queue_for_api.__module__ == "media_importer.features.tasks.queue_service"
    assert reclassify_task_for_api.__module__ == "media_importer.features.tasks.review_service"
    assert rename_task_file_for_api.__module__ == "media_importer.features.tasks.file_lifecycle_service"
    assert resume_queue_for_api.__module__ == "media_importer.features.tasks.queue_service"
    assert retry_all_failed_for_api.__module__ == "media_importer.features.tasks.queue_service"
    assert retry_task_for_api.__module__ == "media_importer.features.tasks.queue_service"
    assert load_config is not None
    assert mask_sensitive is not None
    assert TaskManager is not None
    assert TaskListResult.__module__ == "media_importer.features.tasks.list_service"
    assert list_tasks_for_api.__module__ == "media_importer.features.tasks.list_service"
    assert mark_imported is not None
    assert create_task is not None
    assert update_task is not None
    assert init_db is not None
    assert FileCopier.__module__ == "media_importer.infrastructure.filesystem.file_copier"
    assert ConfidenceEngine is not None
    assert ConfidenceEngine.__module__ == "media_importer.features.scraping.confidence_engine"
    assert DimensionActionResult.__module__ == "media_importer.features.scraping.dimensions_service"
    assert LLMScraper is not None
    assert MetadataScraper is not None
    assert MetadataScraper.__module__ == "media_importer.features.scraping.metadata_scraper"
    assert CleanResult.__module__ == "media_importer.features.scraping.confidence_models"
    assert get_dimensions_for_file is not None
    assert get_dimensions_for_file.__module__ == "media_importer.features.scraping.dimension_manager"
    assert list_dimensions.__module__ == "media_importer.features.scraping.dimensions_service"
    assert list_enabled_dimensions.__module__ == "media_importer.features.scraping.dimensions_service"
    assert get_dimension_detail.__module__ == "media_importer.features.scraping.dimensions_service"
    assert update_dimension_detail.__module__ == "media_importer.features.scraping.dimensions_service"
    assert enable_dimension_detail.__module__ == "media_importer.features.scraping.dimensions_service"
    assert disable_dimension_detail.__module__ == "media_importer.features.scraping.dimensions_service"
    assert reset_dimension_detail.__module__ == "media_importer.features.scraping.dimensions_service"
    assert check_tier_access("pro") is True
    assert TMDbClient is not None
    assert create_providers is not None
    assert get_provider_class("tmdb") is not None
    assert MetadataProvider.__module__ == "media_importer.features.providers.base"
    assert TMDbProvider.__module__ == "media_importer.features.providers.tmdb_provider"
    assert LLMPromptBuilder is not None
    assert LLMPromptBuilder.__module__ == "media_importer.features.prompts.prompt_builder"
    assert load_global_prompt_for_ui.__module__ == "media_importer.features.prompts.application_service"
    assert load_provider_prompt_for_ui.__module__ == "media_importer.features.prompts.application_service"
    assert save_global_prompt.__module__ == "media_importer.features.prompts.application_service"
    assert save_provider_prompt.__module__ == "media_importer.features.prompts.application_service"
    assert reset_global_prompt.__module__ == "media_importer.features.prompts.application_service"
    assert reset_provider_prompt.__module__ == "media_importer.features.prompts.application_service"

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
        assert "from media_importer.features.configuration import load_config, mask_sensitive" in source
        assert "from media_importer.features.tasks import TaskManager" in source
        assert "from media_importer.pipeline import PipelineRunner" not in source


def test_feature_consumers_use_feature_public_apis():
    root = Path(__file__).resolve().parents[1]
    expected_imports = {
        root / "media_importer" / "api" / "dimension_handlers.py": [
            "from media_importer.features.scraping import check_tier_access",
        ],
        root / "media_importer" / "api" / "connectivity_handlers.py": [
            "from media_importer.features.scraping import TMDbClient",
            "from media_importer.features.configuration import test_llm_api",
            "from media_importer.features.configuration import test_hermes_webhook",
        ],
        root / "media_importer" / "api" / "tmdb_handlers.py": [
            "from media_importer.features.scraping import TMDbClient",
            "from media_importer.features.scraping import TMDbClient, TMDbError",
        ],
        root / "media_importer" / "features" / "import_flow" / "steps" / "scrape.py": [
            "from media_importer.features.scraping import get_dimensions_for_file",
        ],
        root / "media_importer" / "storage" / "file_scanner.py": [
            "from media_importer.features.configuration import ConfigView",
        ],
        root / "media_importer" / "features" / "scraping" / "metadata_scraper.py": [
            "from media_importer.features.configuration import ConfigView",
            "from media_importer.features.providers import create_providers",
        ],
        root / "media_importer" / "scraper" / "metadata_scraper.py": [
            "from media_importer.features.scraping.metadata_scraper import MetadataScraper",
        ],
        root / "media_importer" / "scraper" / "llm_scraper.py": [
            "from media_importer.features.configuration import ConfigView",
        ],
    }

    forbidden_imports = [
        "from media_importer.core.config_view import ConfigView",
        "from media_importer.scraper.dimension_manager import",
        "from media_importer.scraper.tmdb_client import",
    ]

    for path, imports in expected_imports.items():
        source = path.read_text(encoding="utf-8")
        for expected in imports:
            assert expected in source
        for forbidden in forbidden_imports:
            assert forbidden not in source


def test_feature_public_apis_are_importable():
    from media_importer.features.configuration import ConfigView, load_config, mask_sensitive
    from media_importer.features.providers import create_providers, get_provider_class
    from media_importer.features.prompts import LLMPromptBuilder
    from media_importer.features.scraping import (
        ConfidenceEngine,
        LLMScraper,
        MetadataScraper,
        TMDbClient,
        check_tier_access,
        get_dimensions_for_file,
    )
    from media_importer.features.tasks import TaskManager, mark_imported
    from media_importer.features.tasks.repository import create_task, update_task
    from media_importer.infrastructure.db import init_db

    assert ConfigView is not None
    assert load_config is not None
    assert mask_sensitive is not None
    assert TaskManager is not None
    assert mark_imported is not None
    assert create_task is not None
    assert update_task is not None
    assert init_db is not None
    assert ConfidenceEngine is not None
    assert LLMScraper is not None
    assert MetadataScraper is not None
    assert MetadataScraper.__module__ == "media_importer.features.scraping.metadata_scraper"
    assert TMDbClient is not None
    assert check_tier_access("pro") is True
    assert get_dimensions_for_file is not None
    assert create_providers is not None
    assert get_provider_class("tmdb") is not None
    assert LLMPromptBuilder is not None

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


def test_feature_public_apis_are_importable():
    from media_importer.features.configuration import ConfigView, load_config, mask_sensitive
    from media_importer.features.providers import create_providers, get_provider_class
    from media_importer.features.prompts import LLMPromptBuilder
    from media_importer.features.scraping import ConfidenceEngine, LLMScraper, MetadataScraper
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
    assert create_providers is not None
    assert get_provider_class("tmdb") is not None
    assert LLMPromptBuilder is not None

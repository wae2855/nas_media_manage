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
        assert "from media_importer.pipeline import PipelineRunner" not in source

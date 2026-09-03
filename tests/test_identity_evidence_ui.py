from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSEMBLER = ROOT / "media_importer/webui/js/build-match-path-data.js"
RENDERER = ROOT / "media_importer/webui/js/cinema-config-simulator.js"


def test_task_detail_passes_identity_evidence_to_shared_match_renderer():
    script = ASSEMBLER.read_text(encoding="utf-8")

    assert "matchTrace.identity_evidence" in script
    assert "scrapeTrace.identity_evidence" in script


def test_match_renderer_explains_used_or_ignored_directory_evidence():
    script = RENDERER.read_text(encoding="utf-8")

    assert "辅助目录名" in script
    assert "目录未参与" in script
    assert "ignored_directories" in script


def test_match_renderer_keeps_backend_evidence_order_ahead_of_popularity():
    script = RENDERER.read_text(encoding="utf-8")

    assert "evidence_score" in script
    assert "候选列表（按身份依据排序）" in script
    assert script.index("evidenceDiff") < script.index("b.popularity")

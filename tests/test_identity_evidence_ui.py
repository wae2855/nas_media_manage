from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSEMBLER = ROOT / "media_importer/webui/js/build-match-path-data.js"
RENDERER = ROOT / "media_importer/webui/js/cinema-config-simulator.js"
TASK_LIST = ROOT / "media_importer/webui/js/cinema-task-list.js"


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


def test_operator_ui_explains_folder_id_and_failed_identity_lookup():
    simulator = RENDERER.read_text(encoding="utf-8")
    task_list = TASK_LIST.read_text(encoding="utf-8")

    assert "folder_provider_id" in simulator
    assert "作品目录身份编号精确命中" in simulator
    assert "IDENTITY_LOOKUP_FAILED" in task_list
    assert "身份编号暂时无法验证" in task_list

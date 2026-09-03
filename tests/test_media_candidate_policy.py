"""Requirement: REQ-20260901-233114 — 媒体候选过滤安全边界。"""

import json
from pathlib import Path

from media_importer.features.import_flow.scan_service import FileScanner
from media_importer.features.source_files.media_candidates import (
    ACCEPT,
    IGNORE_PROMOTION,
    IGNORE_SMALL_COMPANION,
    MediaCandidatePolicy,
)


def _sparse(path: Path, megabytes: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(megabytes * 1024 * 1024)
    return path


def _config() -> dict:
    return {
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt", ".ass"],
        "media_candidate_filter": {
            "enabled": True,
            "small_video_max_mb": 50,
            "main_video_min_mb": 500,
            "max_size_ratio": 0.02,
        },
    }


def test_real_world_promotion_name_is_ignored_without_creating_scan_group(tmp_path: Path):
    main = _sparse(tmp_path / "通天塔.2006.mkv", 800)
    ad = _sparse(
        tmp_path / "【更多无水印高清电影请访问 www.HDBTHD.com】.mp4",
        1,
    )

    decisions = MediaCandidatePolicy(_config()).classify_tree(
        str(tmp_path), [str(main), str(ad)]
    )
    groups = FileScanner(_config()).scan_path(str(tmp_path))

    assert decisions[str(ad.resolve())].disposition == IGNORE_PROMOTION
    assert [group["video_file"] for group in groups] == [main.name]


def test_builtin_name_patterns_are_a_versioned_data_asset():
    asset = (
        Path(__file__).parents[1]
        / "media_importer/features/source_files/data/media_candidate_patterns.v1.json"
    )
    payload = json.loads(asset.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert "访问" in payload["action_terms"]
    assert "com" in payload["domain_tlds"]


def test_small_companion_requires_large_sibling_and_ratio_evidence(tmp_path: Path):
    folder = tmp_path / "Movie"
    main = _sparse(folder / "Movie.mkv", 1000)
    sample = _sparse(folder / "sample.mp4", 10)

    decisions = MediaCandidatePolicy(_config()).classify_tree(
        str(tmp_path), [str(main), str(sample)]
    )

    assert decisions[str(main.resolve())].disposition == ACCEPT
    assert decisions[str(sample.resolve())].disposition == IGNORE_SMALL_COMPANION
    assert decisions[str(sample.resolve())].evidence["size_ratio"] == 0.01


def test_standalone_small_video_is_kept_for_normal_identification(tmp_path: Path):
    short_film = _sparse(tmp_path / "独立短片.2024.mp4", 20)

    decision = MediaCandidatePolicy(_config()).classify_tree(
        str(tmp_path), [str(short_film)]
    )[str(short_film.resolve())]

    assert decision.disposition == ACCEPT


def test_two_legitimate_feature_videos_are_both_kept(tmp_path: Path):
    folder = tmp_path / "Movie"
    disc1 = _sparse(folder / "Movie.CD1.mkv", 900)
    disc2 = _sparse(folder / "Movie.CD2.mkv", 850)

    decisions = MediaCandidatePolicy(_config()).classify_tree(
        str(tmp_path), [str(disc1), str(disc2)]
    )

    assert {decision.disposition for decision in decisions.values()} == {ACCEPT}


def test_user_extra_pattern_is_explicit_and_auditable(tmp_path: Path):
    ad = _sparse(tmp_path / "my-release-group-promo.mkv", 80)
    config = _config()
    config["media_candidate_filter"]["extra_name_patterns"] = ["*release-group-promo*"]

    decision = MediaCandidatePolicy(config).classify_tree(
        str(tmp_path), [str(ad)]
    )[str(ad.resolve())]

    assert decision.disposition == IGNORE_PROMOTION
    assert decision.evidence["matched_extra_pattern"] == "*release-group-promo*"

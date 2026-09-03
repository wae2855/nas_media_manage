#!/usr/bin/env python3
"""Run the public media-name corpus against the configured live TMDB Provider.

The corpus contains names and zero-byte placeholders only.  This command never
prints Provider credentials or persists Provider responses.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from media_importer.core.config_loader import load_config
from media_importer.features.providers import create_providers
from media_importer.features.scraping.filename_cleaner import FilenameCleaner
from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.features.scraping.metadata_scrape_flow import (
    _scrape_provider_first,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "internet_media_name_cases.yaml"


class CachedProvider:
    """Per-run cache that preserves the MetadataProvider interface."""

    def __init__(self, provider):
        self._provider = provider
        self.provider_type = provider.provider_type
        self.display_name = provider.display_name
        self._cache: dict[tuple[Any, ...], Any] = {}

    def _cached(self, key: tuple[Any, ...], callback):
        if key not in self._cache:
            self._cache[key] = callback()
        return self._cache[key]

    def search(self, query, year=None, media_type=None):
        key = ("search", str(query).casefold(), year, media_type)
        return self._cached(
            key,
            lambda: self._provider.search(query, year=year, media_type=media_type),
        )

    def get_by_provider_id(self, item_id, media_type=None):
        key = ("provider_id", str(item_id), media_type)
        return self._cached(
            key,
            lambda: self._provider.get_by_provider_id(item_id, media_type=media_type),
        )

    def lookup_external_id(self, external_id, external_source, media_type=None):
        key = ("external_id", str(external_id), external_source, media_type)
        return self._cached(
            key,
            lambda: self._provider.lookup_external_id(
                external_id,
                external_source,
                media_type=media_type,
            ),
        )

    def get_alternative_titles(self, item_id, media_type):
        key = ("alternative_titles", str(item_id), media_type)
        return self._cached(
            key,
            lambda: self._provider.get_alternative_titles(item_id, media_type),
        )

    def get_details(self, item_id, media_type):
        key = ("details", str(item_id), media_type)
        return self._cached(
            key,
            lambda: self._provider.get_details(item_id, media_type),
        )

    @property
    def request_count(self) -> int:
        return len(self._cache)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用开发配置的真实 TMDB 验证互联网媒体路径/文件名语料",
    )
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config" / "config.yaml"))
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--output", required=True, help="脱敏 JSON 报告输出路径")
    parser.add_argument("--minimum-rate", type=float, default=0.90)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="仅运行前 N 个正向样本；0 表示全部",
    )
    return parser.parse_args()


def _materialize_case(root: Path, sample: dict) -> tuple[Path, Path]:
    source = root / "source"
    video = source / sample["path"]
    video.parent.mkdir(parents=True, exist_ok=True)
    video.touch()
    nfo = sample.get("nfo")
    if nfo:
        nfo_path = source / nfo["path"]
        nfo_path.parent.mkdir(parents=True, exist_ok=True)
        nfo_path.write_text(nfo["xml"], encoding="utf-8")
    return source, video


def _file_signal(result) -> dict:
    return next(
        (
            signal
            for signal in result.identity_evidence.get("signals", [])
            if signal.get("source") == "file"
        ),
        {},
    )


def _check_positive(result, scrape_result: dict, expected: dict, sample: dict) -> dict:
    selected = result.selected_candidate
    file_signal = _file_signal(result)
    path_structure = result.identity_evidence.get("path_structure", {})
    effective_season = file_signal.get("season")
    if effective_season is None:
        effective_season = path_structure.get("season")

    checks = {
        "auto_pass": result.match_level == "AUTO_PASS",
        "provider_id": str(result.provider_id or "") == str(expected["provider_id"]),
        "media_type": bool(selected and selected.media_type == expected["media_type"]),
        "year": bool(selected and selected.year == expected["year"]),
        "season": "season" not in sample or effective_season == sample["season"],
        "episode": "episode" not in sample or file_signal.get("episode") == sample["episode"],
        "details": bool(scrape_result),
    }
    if scrape_result:
        checks.update(
            {
                "scrape_provider_id": str(scrape_result.get("provider_id") or "")
                == str(expected["provider_id"]),
                "scrape_media_type": scrape_result.get("media_type")
                == expected["media_type"],
                "scrape_year": scrape_result.get("year") == expected["year"],
                "scrape_season": "season" not in sample
                or scrape_result.get("season") == sample["season"],
                "scrape_episode": "episode" not in sample
                or scrape_result.get("episode") == sample["episode"],
            }
        )
    return checks


def _scrape_selected(provider, video: Path, result) -> dict:
    if result.match_level != "AUTO_PASS" or not result.selected_candidate:
        return {}
    scraper = SimpleNamespace(
        _cleaner=FilenameCleaner(),
        providers=[provider],
    )
    return _scrape_provider_first(
        scraper,
        video.name,
        [],
        None,
        video_path=str(video),
        match_result=result,
    )


def _run_positive_case(
    root: Path,
    family: dict,
    sample: dict,
    works: dict,
    provider: CachedProvider,
) -> dict:
    source, video = _materialize_case(root, sample)
    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )
    expected = works[family["work"]]
    try:
        scrape_result = _scrape_selected(provider, video, result)
        details_error = ""
    except Exception as exc:  # external API failures belong in the report
        scrape_result = {}
        details_error = f"{type(exc).__name__}: {str(exc)[:160]}"
    checks = _check_positive(result, scrape_result, expected, sample)
    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        "family": family["id"],
        "source": family["source"],
        "path": sample["path"],
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "match_level": result.match_level,
        "actual_provider_id": str(result.provider_id or ""),
        "expected_provider_id": str(expected["provider_id"]),
        "media_type": result.selected_candidate.media_type
        if result.selected_candidate
        else "",
        "concerns": [concern.code for concern in result.concerns],
        "details_error": details_error,
    }


def _run_safety_case(
    root: Path,
    sample: dict,
    provider: CachedProvider,
) -> dict:
    source, video = _materialize_case(root, sample)
    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )
    return {
        "id": sample["id"],
        "path": sample["path"],
        "passed": result.match_level != "AUTO_PASS",
        "match_level": result.match_level,
        "actual_provider_id": str(result.provider_id or ""),
        "concerns": [concern.code for concern in result.concerns],
    }


def _build_report(args: argparse.Namespace) -> tuple[dict, int]:
    fixture_path = Path(args.fixture).resolve()
    corpus = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    config = load_config(args.config)
    tmdb_config = next(
        (
            item
            for item in config.get("metadata", {}).get("providers", [])
            if item.get("type") == "tmdb" and item.get("enabled")
        ),
        {},
    )
    providers = create_providers(config)
    tmdb = next((item for item in providers if item.provider_type == "tmdb"), None)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture": str(fixture_path),
        "provider": "tmdb",
        "credentials_present": bool(tmdb_config.get("api_key")),
        "connection": "NOT_RUN",
        "minimum_rate": args.minimum_rate,
        "positive": [],
        "safety": [],
    }
    if tmdb is None:
        report["connection"] = "NOT_RUN"
        report["error"] = "未找到启用且可实例化的 TMDB Provider"
        return report, 2

    try:
        connected = tmdb.test_connection()
    except Exception as exc:
        report["connection"] = "FAIL"
        report["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return report, 2
    if not connected:
        report["connection"] = "FAIL"
        report["error"] = "TMDB 连接测试未通过"
        return report, 2

    report["connection"] = "PASS"
    provider = CachedProvider(tmdb)
    families = corpus["positive_families"]
    positive_inputs = [
        (family, sample)
        for family in families
        for sample in family["samples"]
    ]
    if args.limit > 0:
        positive_inputs = positive_inputs[: args.limit]

    with tempfile.TemporaryDirectory(prefix="nas-media-name-live-") as temp_dir:
        temp_root = Path(temp_dir)
        for index, (family, sample) in enumerate(positive_inputs):
            report["positive"].append(
                _run_positive_case(
                    temp_root / f"positive-{index:03d}",
                    family,
                    sample,
                    corpus["works"],
                    provider,
                )
            )
        for index, sample in enumerate(corpus["safety_cases"]):
            report["safety"].append(
                _run_safety_case(
                    temp_root / f"safety-{index:03d}",
                    sample,
                    provider,
                )
            )

    positives = report["positive"]
    passed_samples = sum(item["passed"] for item in positives)
    family_results: dict[str, list[bool]] = {}
    for item in positives:
        family_results.setdefault(item["family"], []).append(item["passed"])
    passed_families = sum(all(values) for values in family_results.values())
    unsafe = [item for item in report["safety"] if not item["passed"]]
    sample_rate = passed_samples / len(positives) if positives else 0.0
    family_rate = passed_families / len(family_results) if family_results else 0.0
    report["summary"] = {
        "sample_total": len(positives),
        "sample_passed": passed_samples,
        "sample_rate": round(sample_rate, 4),
        "family_total": len(family_results),
        "family_passed": passed_families,
        "family_rate": round(family_rate, 4),
        "safety_total": len(report["safety"]),
        "safety_passed": len(report["safety"]) - len(unsafe),
        "provider_cache_entries": provider.request_count,
    }
    passed = (
        sample_rate >= args.minimum_rate
        and family_rate >= args.minimum_rate
        and not unsafe
    )
    report["status"] = "PASS" if passed else "FAIL"
    return report, 0 if passed else 1


def main() -> int:
    args = _parse_args()
    report, exit_code = _build_report(args)
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report.get("status", report.get("connection")),
        "connection": report.get("connection"),
        "summary": report.get("summary", {}),
        "output": str(output_path),
    }, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

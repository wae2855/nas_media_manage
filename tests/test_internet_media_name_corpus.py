from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from media_importer.features.providers.base import SearchItem, SearchResult
from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.features.scraping.title_normalizer import TitleNormalizer

FIXTURE = Path(__file__).parent / "fixtures" / "internet_media_name_cases.yaml"


def _load_corpus() -> dict:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class CorpusOutcome:
    family: str
    path: str
    passed: bool
    level: str
    provider_id: str
    reason: str


class CorpusProvider:
    """Small deterministic Provider built from the public-name fixture."""

    provider_type = "tmdb"
    display_name = "TMDB fixture"

    def __init__(self, works: dict):
        self.works = works

    @staticmethod
    def _item(work: dict) -> SearchItem:
        return SearchItem(
            provider_type="tmdb",
            item_id=str(work["provider_id"]),
            title=work["title"],
            original_title=work["original_title"],
            year=work["year"],
            media_type=work["media_type"],
            poster_url=None,
            vote_average=8.0,
            raw_data={"popularity": 10, "vote_count": 100},
        )

    @staticmethod
    def _terms(work: dict) -> set[str]:
        values = [work["title"], work["original_title"], *work.get("aliases", [])]
        return {TitleNormalizer.strict_key(value) for value in values if value}

    def search(self, query, year=None, media_type=None):
        query_key = TitleNormalizer.strict_key(query)
        matches = []
        for work in self.works.values():
            if media_type and work["media_type"] != media_type:
                continue
            if year is not None and work["year"] != year:
                continue
            if query_key in self._terms(work):
                matches.append(self._item(work))
        return SearchResult(items=matches, total_results=len(matches))

    def get_by_provider_id(self, item_id, media_type=None):
        matches = [
            self._item(work)
            for work in self.works.values()
            if str(work["provider_id"]) == str(item_id)
            and (not media_type or work["media_type"] == media_type)
        ]
        return SearchResult(items=matches, total_results=len(matches))

    def lookup_external_id(self, external_id, external_source, media_type=None):
        key = f"{external_source}_id"
        matches = [
            self._item(work)
            for work in self.works.values()
            if str(work.get(key) or "") == str(external_id)
            and (not media_type or work["media_type"] == media_type)
        ]
        return SearchResult(items=matches, total_results=len(matches))

    def get_alternative_titles(self, item_id, media_type):
        for work in self.works.values():
            if (
                str(work["provider_id"]) == str(item_id)
                and work["media_type"] == media_type
            ):
                return list(work.get("aliases", []))
        return []


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


def _positive_outcome(
    root: Path,
    family: dict,
    sample: dict,
    works: dict,
    provider: CorpusProvider,
) -> CorpusOutcome:
    source, video = _materialize_case(root, sample)
    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )
    expected = works[family["work"]]
    selected = result.selected_candidate
    file_signal = next(
        item
        for item in result.identity_evidence.get("signals", [])
        if item["source"] == "file"
    )
    effective_season = file_signal.get("season")
    if effective_season is None:
        effective_season = (
            result.identity_evidence.get("path_structure", {}).get("season")
        )
    checks = {
        "level": result.match_level == "AUTO_PASS",
        "provider_id": str(result.provider_id or "") == str(expected["provider_id"]),
        "media_type": bool(selected and selected.media_type == expected["media_type"]),
        "year": bool(selected and selected.year == expected["year"]),
        "season": (
            "season" not in sample or effective_season == sample["season"]
        ),
        "episode": (
            "episode" not in sample or file_signal.get("episode") == sample["episode"]
        ),
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    concerns = ",".join(item.code for item in result.concerns)
    reason = (
        f"failed={','.join(failed_checks)} concerns={concerns} "
        f"selected={result.provider_id or '-'}"
        if failed_checks
        else "ok"
    )
    return CorpusOutcome(
        family=family["id"],
        path=sample["path"],
        passed=not failed_checks,
        level=result.match_level,
        provider_id=str(result.provider_id or ""),
        reason=reason,
    )


def test_corpus_contract_and_public_sources():
    corpus = _load_corpus()
    meta = corpus["meta"]
    families = corpus["positive_families"]
    sample_count = sum(len(family["samples"]) for family in families)
    safety_count = len(corpus["safety_cases"])
    kinds = [family["kind"] for family in families]

    assert len(families) >= meta["minimum_positive_families"]
    assert sample_count >= meta["minimum_positive_samples"]
    assert safety_count >= meta["minimum_safety_samples"]
    assert kinds.count("movie") / len(kinds) >= 0.35
    assert kinds.count("tv") / len(kinds) >= 0.35
    assert {family["source"] for family in families} == set(corpus["sources"])
    assert all(
        value.startswith("https://") or value.startswith("docs/")
        for value in corpus["sources"].values()
    )


def test_positive_corpus_reaches_90_percent_correct_auto_scrape(tmp_path):
    corpus = _load_corpus()
    works = corpus["works"]
    provider = CorpusProvider(works)
    outcomes = []
    family_results: dict[str, list[bool]] = {}

    for family_index, family in enumerate(corpus["positive_families"]):
        family_results[family["id"]] = []
        for sample_index, sample in enumerate(family["samples"]):
            root = tmp_path / f"f{family_index:02d}-s{sample_index:02d}"
            outcome = _positive_outcome(root, family, sample, works, provider)
            outcomes.append(outcome)
            family_results[family["id"]].append(outcome.passed)

    passed_samples = sum(outcome.passed for outcome in outcomes)
    passed_families = sum(all(values) for values in family_results.values())
    sample_rate = passed_samples / len(outcomes)
    family_rate = passed_families / len(family_results)
    minimum = float(corpus["meta"]["minimum_auto_rate"])
    failures = [
        f"{item.family}: {item.path} -> {item.level}; {item.reason}"
        for item in outcomes
        if not item.passed
    ]

    assert sample_rate >= minimum, (
        f"sample auto rate {sample_rate:.1%} < {minimum:.0%}\n" + "\n".join(failures)
    )
    assert family_rate >= minimum, (
        f"family auto rate {family_rate:.1%} < {minimum:.0%}\n" + "\n".join(failures)
    )


def test_safety_corpus_never_auto_passes(tmp_path):
    corpus = _load_corpus()
    provider = CorpusProvider(corpus["works"])
    unsafe = []

    for index, sample in enumerate(corpus["safety_cases"]):
        source, video = _materialize_case(tmp_path / f"safety-{index:02d}", sample)
        result = MatchEngine({"source_dir": str(source)}).match(
            video.name,
            [provider],
            video_path=str(video),
        )
        if result.match_level == "AUTO_PASS":
            unsafe.append(
                f"{sample['id']}: {sample['path']} -> {result.provider_id}"
            )

    assert not unsafe, "safety cases were auto-passed:\n" + "\n".join(unsafe)

from pathlib import Path

import yaml

from media_importer.features.providers.base import SearchItem, SearchResult
from media_importer.features.providers.tmdb_provider import TMDbProvider
from media_importer.features.scraping.confidence_models import CleanResult
from media_importer.features.scraping.deterministic_identity import resolve_deterministic_identity
from media_importer.features.scraping.filename_cleaner import FilenameCleaner
from media_importer.features.scraping.identity_evidence import build_identity_evidence
from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.features.scraping.nfo_identity import parse_nfo_identity
from media_importer.features.scraping.path_roles import (
    is_structural_directory,
    is_supplementary_directory,
)
from media_importer.features.scraping.release_identity import parse_release_identity
from media_importer.features.scraping.title_normalizer import TitleNormalizer


def _item(item_id, title, year, media_type="movie", popularity=0):
    return SearchItem(
        provider_type="tmdb",
        item_id=str(item_id),
        title=title,
        original_title=title,
        year=year,
        media_type=media_type,
        poster_url=None,
        vote_average=7.0,
        raw_data={"popularity": popularity},
    )


class IdentityProvider:
    provider_type = "tmdb"
    display_name = "TMDB"

    def __init__(
        self, *, native=None, external=None, searches=None, alternatives=None,
        native_error=None,
    ):
        self.native = native or {}
        self.external = external or {}
        self.searches = searches or {}
        self.alternatives = alternatives or {}
        self.native_error = native_error
        self.calls = []

    def get_by_provider_id(self, item_id, media_type=None):
        self.calls.append(("native", item_id, media_type))
        if self.native_error:
            raise self.native_error
        return SearchResult(items=list(self.native.get(str(item_id), [])))

    def lookup_external_id(self, external_id, external_source, media_type=None):
        self.calls.append(("external", external_source, external_id, media_type))
        return SearchResult(items=list(self.external.get((external_source, str(external_id)), [])))

    def search(self, query, year=None, media_type=None):
        self.calls.append(("search", query, year, media_type))
        return SearchResult(items=list(self.searches.get(query, [])))

    def get_alternative_titles(self, item_id, media_type):
        return list(self.alternatives.get((str(item_id), media_type), []))


def test_real_release_fixture_contract():
    fixture = Path(__file__).parent / "fixtures" / "media_identity_resolution_v2.yaml"
    cases = yaml.safe_load(fixture.read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 10
    for case in cases:
        identity = parse_release_identity(case["filename"])
        assert list(identity.title_candidates) == case["titles"], case["family"]
        for field in ("year", "season", "episode", "tmdb_id", "imdb_id", "tvdb_id", "release_date", "disc", "part", "episode_title", "alternative_title"):
            if field in case:
                assert getattr(identity, field) == case[field], (case["family"], field)


def test_real_directory_fixture_contract(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "media_identity_resolution_v2.yaml"
    directory_cases = yaml.safe_load(fixture.read_text(encoding="utf-8"))["directory_cases"]
    source = tmp_path / "source"
    for case in directory_cases:
        video = source / case["relative_path"]
        video.parent.mkdir(parents=True, exist_ok=True)
        video.touch()
        evidence = build_identity_evidence(
            video.name,
            video_path=str(video),
            source_dir=str(source),
            cleaner=FilenameCleaner(),
        )
        if case.get("expected_folder"):
            folder_signal = next(
                signal for signal in evidence["signals"] if signal["source"] == "folder"
            )
            assert folder_signal["raw_name"] == case["expected_folder"], case["family"]
        if case.get("expected_file_title"):
            file_signal = next(
                signal for signal in evidence["signals"] if signal["source"] == "file"
            )
            assert case["expected_file_title"] in file_signal["titles"], case["family"]


def test_title_normalizer_strict_and_loose_contract():
    assert TitleNormalizer.strict_key("Spider–Man：Homecoming") == "spidermanhomecoming"
    assert TitleNormalizer.strict_key("ＴＨＥ  ＯＦＦＩＣＥ") == "theoffice"
    assert TitleNormalizer.strict_key("Amélie") != TitleNormalizer.strict_key("Amelie")
    assert TitleNormalizer.loose_key("Amélie") == TitleNormalizer.loose_key("Amelie")
    assert TitleNormalizer.loose_key("Dungeons & Dragons") == TitleNormalizer.loose_key("Dungeons and Dragons")
    assert TitleNormalizer.loose_key("Léon") == TitleNormalizer.loose_key("Leon")
    assert TitleNormalizer.strict_key("WALL·E") == TitleNormalizer.strict_key("WALL-E")
    assert TitleNormalizer.strict_key("Kiki’s Delivery Service") == TitleNormalizer.strict_key("Kiki's Delivery Service")
    assert [TitleNormalizer.strict(value) for value in ("1984", "4K", "Se7en", "M", "X")] == [
        "1984", "4k", "se7en", "m", "x"
    ]


def test_nfo_parser_reads_unique_and_legacy_ids(tmp_path):
    nfo = tmp_path / "movie.nfo"
    nfo.write_text(
        "<movie><title>Inception</title><year>2010</year>"
        "<uniqueid type='tmdb'>27205</uniqueid><imdbid>tt1375666</imdbid></movie>",
        encoding="utf-8",
    )
    identity = parse_nfo_identity(str(nfo))
    assert identity is not None
    assert identity.tmdb_id == "27205"
    assert identity.imdb_id == "tt1375666"
    assert identity.title == "Inception"
    assert identity.year == 2010
    assert identity.media_type_hint == "movie"
    assert identity.identity_scope == "movie"


def test_nfo_parser_rejects_symlink_and_oversized_file(tmp_path):
    target = tmp_path / "target.nfo"
    target.write_text("<movie><tmdbid>27205</tmdbid></movie>", encoding="utf-8")
    link = tmp_path / "movie.nfo"
    link.symlink_to(target)
    assert parse_nfo_identity(str(link)) is None
    large = tmp_path / "large.nfo"
    large.write_bytes(b"x" * (1024 * 1024 + 1))
    assert parse_nfo_identity(str(large)) is None
    broken = tmp_path / "broken.nfo"
    broken.write_text("<movie><tmdbid>27205", encoding="utf-8")
    assert parse_nfo_identity(str(broken)) is None


def test_generic_and_structural_directories_are_skipped_continuously(tmp_path):
    source = tmp_path / "source"
    episode_dir = source / "权力的游戏" / "downloads" / "Season 01"
    episode_dir.mkdir(parents=True)
    video = episode_dir / "S01E01.mkv"
    video.touch()
    evidence = build_identity_evidence(
        video.name,
        video_path=str(video),
        source_dir=str(source),
        cleaner=FilenameCleaner(),
    )
    assert evidence["signals"][1]["raw_name"] == "权力的游戏"
    assert [item["name"] for item in evidence["ignored_directories"]] == ["Season 01", "downloads"]


def test_filename_tmdb_id_resolves_before_title_search(tmp_path):
    video = tmp_path / "Wrong.Title.2023.[tmdbid-872585].mkv"
    video.touch()
    provider = IdentityProvider(native={"872585": [_item("872585", "Oppenheimer", 2023)]})
    result = MatchEngine({"source_dir": str(tmp_path)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "872585"
    assert result.selected_candidate.why_selected == "explicit_provider_id"
    assert not any(call[0] == "search" for call in provider.calls)
    assert result.identity_evidence["identity_resolution"]["source"] == "filename"
    assert result.identity_evidence["identity_resolution"]["identity_source"] == "filename_provider_id"


def test_nfo_id_is_used_when_filename_has_no_id(tmp_path):
    video = tmp_path / "Inception.2010.mkv"
    video.touch()
    (tmp_path / "movie.nfo").write_text(
        "<movie><uniqueid type='imdb'>tt1375666</uniqueid></movie>", encoding="utf-8"
    )
    provider = IdentityProvider(external={("imdb", "tt1375666"): [_item("27205", "Inception", 2010)]})
    result = MatchEngine({"source_dir": str(tmp_path)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "27205"
    assert result.selected_candidate.why_selected == "nfo_provider_id"


def test_filename_tvdb_id_uses_external_lookup_with_tv_type(tmp_path):
    video = tmp_path / "Game.of.Thrones.[tvdbid-121361].S01E01.mkv"
    video.touch()
    provider = IdentityProvider(external={
        ("tvdb", "121361"): [_item("1399", "Game of Thrones", 2011, media_type="tv")]
    })
    result = MatchEngine({"source_dir": str(tmp_path)}).match(
        video.name, [provider], video_path=str(video)
    )
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "1399"
    assert provider.calls[0] == ("external", "tvdb", "121361", "tv")


def test_explicit_id_media_type_conflict_requires_confirmation(tmp_path):
    video = tmp_path / "Show.[tvdbid-121361].S01E01.mkv"
    video.touch()
    provider = IdentityProvider(external={
        ("tvdb", "121361"): [_item("1", "Wrong Movie", 2020, media_type="movie")]
    })
    result = MatchEngine({"source_dir": str(tmp_path)}).match(
        video.name, [provider], video_path=str(video)
    )
    assert result.match_level == "NEEDS_CONFIRM"
    assert "媒体类型冲突" in result.concerns[0].detail


def test_filename_id_has_priority_over_conflicting_nfo(tmp_path):
    video = tmp_path / "Inception.2010.[tmdbid-27205].mkv"
    video.touch()
    (tmp_path / "movie.nfo").write_text("<movie><tmdbid>999</tmdbid></movie>", encoding="utf-8")
    provider = IdentityProvider(native={
        "27205": [_item("27205", "Inception", 2010)],
        "999": [_item("999", "Other", 2010)],
    })
    result = MatchEngine({"source_dir": str(tmp_path)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "27205"
    assert ("native", "999", "movie") not in provider.calls


def test_explicit_id_year_conflict_requires_confirmation(tmp_path):
    video = tmp_path / "Inception.2020.[tmdbid-27205].mkv"
    video.touch()
    provider = IdentityProvider(native={"27205": [_item("27205", "Inception", 2010)]})
    result = MatchEngine({"source_dir": str(tmp_path)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "NEEDS_CONFIRM"
    assert result.concerns[0].code == "IDENTITY_CONFLICT"
    assert "年份冲突" in result.concerns[0].detail


def test_id_lookup_error_falls_back_to_title_without_crashing(tmp_path):
    video = tmp_path / "Inception.2010.[tmdbid-27205].mkv"
    video.touch()
    provider = IdentityProvider(
        native_error=RuntimeError("timeout"),
        searches={"Inception": [_item("27205", "Inception", 2010)]},
    )
    result = MatchEngine({"source_dir": str(tmp_path)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert any("保守降级" in step.reason for step in result.trace_steps)


def test_conflicting_filename_ids_require_confirmation(tmp_path):
    video = tmp_path / "Movie.2020.[tmdbid-1].[imdbid-tt0000002].mkv"
    video.touch()
    provider = IdentityProvider(
        native={"1": [_item("1", "Movie A", 2020)]},
        external={("imdb", "tt0000002"): [_item("2", "Movie B", 2020)]},
    )
    result = MatchEngine({"source_dir": str(tmp_path)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "NEEDS_CONFIRM"
    assert result.concerns[0].code == "IDENTITY_CONFLICT"
    assert len(result.candidates) == 2


def test_single_tmdb_id_uses_title_and_year_to_disambiguate_id_namespaces(tmp_path):
    video = tmp_path / "Inception.2010.[tmdbid-27205].mkv"
    video.touch()
    provider = IdentityProvider(native={"27205": [
        _item("27205", "Unrelated Show", 2022, media_type="tv"),
        _item("27205", "Inception", 2010, media_type="movie"),
    ]})
    result = MatchEngine({"source_dir": str(tmp_path)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert result.selected_candidate.media_type == "movie"


def test_historical_binding_is_lower_priority_than_nfo_but_supported(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    video = source / "Unknown.mkv"
    video.touch()
    evidence = build_identity_evidence(
        video.name,
        video_path=str(video),
        source_dir=str(source),
        cleaner=FilenameCleaner(),
        path_context={
            "historical_binding": {
                "provider_type": "tmdb",
                "provider_id": "42",
                "media_type": "movie",
                "year": 2000,
            }
        },
    )
    assert evidence["provider_ids"][-1]["source"] == "history"
    assert evidence["provider_ids"][-1]["value"] == "42"


def test_nfo_binding_wins_before_conflicting_history(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    video = source / "Unknown.mkv"
    video.touch()
    (source / "movie.nfo").write_text("<movie><tmdbid>1</tmdbid></movie>", encoding="utf-8")
    provider = IdentityProvider(native={
        "1": [_item("1", "NFO Movie", 2020)],
        "2": [_item("2", "History Movie", 2020)],
    })
    evidence = build_identity_evidence(
        video.name,
        video_path=str(video),
        source_dir=str(source),
        cleaner=FilenameCleaner(),
        path_context={
            "historical_binding": {
                "provider_type": "tmdb", "provider_id": "2", "media_type": "movie"
            }
        },
    )
    result, _ = resolve_deterministic_identity(
        evidence, [provider], year=None, media_type_hint=""
    )
    assert result is not None
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "1"
    assert ("native", "2", "movie") not in provider.calls


def test_close_fuzzy_candidates_are_ranked_by_evidence_not_popularity(tmp_path):
    video = tmp_path / "Matrixx.1999.mkv"
    video.touch()
    provider = IdentityProvider(searches={
        "Matrixx": [
            _item("1", "Matrix", 1999, popularity=1),
            _item("2", "Matrix X", 1999, popularity=1000),
        ]
    })
    result = MatchEngine({"source_dir": str(tmp_path)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "NEEDS_CONFIRM"
    assert result.candidates[0]["id"] == "2"
    assert all("evidence_score" in candidate for candidate in result.candidates)
    assert any(concern.code == "CLOSE_CANDIDATES" for concern in result.concerns)


def test_tmdb_external_lookup_maps_movie_and_tv_results():
    class Client:
        def find_by_external_id(self, external_id, external_source):
            assert (external_id, external_source) == ("tt1234567", "imdb_id")
            return {
                "movie_results": [{"id": 1, "title": "Movie", "release_date": "2020-01-01"}],
                "tv_results": [{"id": 2, "name": "Show", "first_air_date": "2021-01-01"}],
            }

    provider = object.__new__(TMDbProvider)
    provider._client = Client()
    result = provider.lookup_external_id("tt1234567", "imdb")
    assert [(item.item_id, item.media_type) for item in result.items] == [("1", "movie"), ("2", "tv")]


def test_tmdb_native_id_lookup_returns_standard_search_item():
    class Client:
        def get_movie_details(self, item_id):
            assert item_id == 27205
            return {"id": 27205, "title": "Inception", "release_date": "2010-07-16"}

    provider = object.__new__(TMDbProvider)
    provider._client = Client()
    result = provider.get_by_provider_id("27205", "movie")
    assert len(result.items) == 1
    assert result.items[0].item_id == "27205"
    assert result.items[0].year == 2010


def test_supplementary_video_does_not_inherit_movie_nfo(tmp_path):
    source = tmp_path / "source"
    movie = source / "Inception.2010"
    extras = movie / "Extras"
    extras.mkdir(parents=True)
    (movie / "movie.nfo").write_text(
        "<movie><uniqueid type='tmdb'>27205</uniqueid></movie>", encoding="utf-8"
    )
    video = extras / "Making.Of.mkv"
    video.touch()
    provider = IdentityProvider(native={"27205": [_item("27205", "Inception", 2010)]})
    result = MatchEngine({"source_dir": str(source)}).match(video.name, [provider], video_path=str(video))
    assert result.provider_id != "27205"
    assert not any(call[0] == "native" for call in provider.calls)
    assert any("附加内容" in item["reason"] for item in result.identity_evidence["ignored_nfo"])


def test_supplementary_video_can_use_its_own_nfo(tmp_path):
    source = tmp_path / "source"
    extras = source / "Inception.2010" / "Extras"
    extras.mkdir(parents=True)
    video = extras / "Making.Of.mkv"
    video.touch()
    (extras / "Making.Of.nfo").write_text(
        "<movie><uniqueid type='tmdb'>999</uniqueid></movie>", encoding="utf-8"
    )
    provider = IdentityProvider(native={"999": [_item("999", "Making Of Inception", 2010)]})
    result = MatchEngine({"source_dir": str(source)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "999"


def test_season_episode_inherits_series_tvshow_nfo(tmp_path):
    source = tmp_path / "source"
    series = source / "Game of Thrones"
    season = series / "Season 01"
    season.mkdir(parents=True)
    (series / "tvshow.nfo").write_text(
        "<tvshow><uniqueid type='tmdb'>1399</uniqueid></tvshow>", encoding="utf-8"
    )
    video = season / "S01E01.mkv"
    video.touch()
    provider = IdentityProvider(native={
        "1399": [_item("1399", "Game of Thrones", 2011, media_type="tv")]
    })
    result = MatchEngine({"source_dir": str(source)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "1399"
    assert result.identity_evidence["nfo_identities"][0]["identity_scope"] == "series"


def test_tv_specials_is_structural_and_uses_series_folder_identity(tmp_path):
    source = tmp_path / "source"
    specials = source / "Game of Thrones" / "Specials"
    specials.mkdir(parents=True)
    video = specials / "S00E01.mkv"
    video.touch()

    evidence = build_identity_evidence(
        video.name,
        video_path=str(video),
        source_dir=str(source),
        cleaner=FilenameCleaner(),
    )

    file_signal = next(signal for signal in evidence["signals"] if signal["source"] == "file")
    folder_signal = next(signal for signal in evidence["signals"] if signal["source"] == "folder")
    assert (file_signal["season"], file_signal["episode"]) == (0, 1)
    assert (folder_signal["season"], folder_signal["episode"]) == (0, 1)
    assert folder_signal["raw_name"] == "Game of Thrones"
    assert any(
        item == {"name": "Specials", "reason": "结构目录不作为片名"}
        for item in evidence["ignored_directories"]
    )
    assert is_structural_directory("Specials")
    assert not is_supplementary_directory("Specials")
    assert all(
        is_supplementary_directory(name)
        for name in ("Special Features", "Special-Features", "special_features")
    )

    provider = IdentityProvider()
    MatchEngine({"source_dir": str(source)}).match(
        video.name, [provider], video_path=str(video)
    )
    assert any(call[0] == "search" and call[3] == "tv" for call in provider.calls)


def test_tv_specials_inherits_series_tvshow_nfo(tmp_path):
    source = tmp_path / "source"
    series = source / "Game of Thrones"
    specials = series / "Specials"
    specials.mkdir(parents=True)
    (series / "tvshow.nfo").write_text(
        "<tvshow><uniqueid type='tmdb'>1399</uniqueid></tvshow>", encoding="utf-8"
    )
    video = specials / "S00E01.mkv"
    video.touch()
    provider = IdentityProvider(native={
        "1399": [_item("1399", "Game of Thrones", 2011, media_type="tv")]
    })

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name, [provider], video_path=str(video)
    )

    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "1399"
    assert result.identity_evidence["nfo_identities"][0]["identity_scope"] == "series"


def test_bdmv_stream_inherits_movie_nfo(tmp_path):
    source = tmp_path / "source"
    movie = source / "Inception.2010"
    stream = movie / "BDMV" / "STREAM"
    stream.mkdir(parents=True)
    (movie / "movie.nfo").write_text(
        "<movie><uniqueid type='tmdb'>27205</uniqueid></movie>", encoding="utf-8"
    )
    video = stream / "00001.m2ts"
    video.touch()
    provider = IdentityProvider(native={"27205": [_item("27205", "Inception", 2010)]})
    result = MatchEngine({"source_dir": str(source)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "27205"


def test_episode_nfo_id_is_not_queried_as_series_id(tmp_path):
    source = tmp_path / "source"
    season = source / "Show" / "Season 01"
    season.mkdir(parents=True)
    video = season / "S01E01.mkv"
    video.touch()
    (season / "S01E01.nfo").write_text(
        "<episodedetails><uniqueid type='tmdb'>123456</uniqueid></episodedetails>", encoding="utf-8"
    )
    provider = IdentityProvider(native={
        "123456": [_item("123456", "Wrong Series", 2020, media_type="tv")]
    })
    result = MatchEngine({"source_dir": str(source)}).match(video.name, [provider], video_path=str(video))
    assert result.provider_id != "123456"
    assert not any(call[0] == "native" for call in provider.calls)
    assert result.identity_evidence["nfo_identities"][0]["identity_scope"] == "episode"
    assert any("episode" in item["reason"] for item in result.identity_evidence["ignored_nfo"])


def test_technical_directory_is_skipped_to_meaningful_movie_folder(tmp_path):
    source = tmp_path / "source"
    technical = source / "Inception.2010" / "2160p"
    technical.mkdir(parents=True)
    video = technical / "00001.mkv"
    video.touch()
    evidence = build_identity_evidence(
        video.name, video_path=str(video), source_dir=str(source), cleaner=FilenameCleaner()
    )
    folder = next(signal for signal in evidence["signals"] if signal["source"] == "folder")
    assert folder["raw_name"] == "Inception.2010"
    assert any(item["name"] == "2160p" for item in evidence["ignored_directories"])


def test_untrusted_unknown_directory_continues_to_parent(tmp_path):
    class CleanerWithUntrustedXxx(FilenameCleaner):
        def clean(self, filename):
            if filename == "xxx":
                return CleanResult(clean_title="")
            return super().clean(filename)

    source = tmp_path / "source"
    unknown = source / "Inception.2010" / "xxx"
    unknown.mkdir(parents=True)
    video = unknown / "00001.mkv"
    video.touch()
    evidence = build_identity_evidence(
        video.name, video_path=str(video), source_dir=str(source), cleaner=CleanerWithUntrustedXxx()
    )
    folder = next(signal for signal in evidence["signals"] if signal["source"] == "folder")
    assert folder["raw_name"] == "Inception.2010"
    assert any(item["name"] == "xxx" for item in evidence["ignored_directories"])


def test_conflicting_exact_file_title_candidates_require_confirmation(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    video = source / "中文标题A.EnglishTitleB.2020.mkv"
    video.touch()
    provider = IdentityProvider(searches={
        "中文标题": [_item("1", "中文标题", 2020)],
        "EnglishTitleB": [_item("2", "EnglishTitleB", 2020)],
    })
    result = MatchEngine({"source_dir": str(source)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "NEEDS_CONFIRM"
    assert {candidate["id"] for candidate in result.candidates} == {"1", "2"}
    assert any(concern.code == "CONFLICTING_INFO" for concern in result.concerns)


def test_multiple_exact_file_titles_resolving_to_same_work_auto_pass(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    video = source / "中文标题A.EnglishTitleB.2020.mkv"
    video.touch()
    work = _item("1", "中文标题", 2020)
    provider = IdentityProvider(searches={"中文标题": [work], "EnglishTitleB": [work]})
    result = MatchEngine({"source_dir": str(source)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "1"


def test_one_exact_file_title_and_one_empty_result_auto_pass(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    video = source / "中文标题A.EnglishTitleB.2020.mkv"
    video.touch()
    provider = IdentityProvider(searches={"中文标题": [_item("1", "中文标题", 2020)]})
    result = MatchEngine({"source_dir": str(source)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "1"


def test_exact_and_provider_alias_file_titles_for_same_work_auto_pass(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    video = source / "中文标题A.EnglishTitleB.2020.mkv"
    video.touch()
    work = _item("1", "中文标题", 2020)
    provider = IdentityProvider(
        searches={"中文标题": [work], "EnglishTitleB": [work]},
        alternatives={("1", "movie"): ["EnglishTitleB"]},
    )
    result = MatchEngine({"source_dir": str(source)}).match(video.name, [provider], video_path=str(video))
    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "1"
    assert result.selected_candidate.why_selected == "provider_alias"


def test_loose_accent_folding_only_changes_latin_characters():
    assert TitleNormalizer.loose_key("Léon") == TitleNormalizer.loose_key("Leon")
    assert TitleNormalizer.loose_key("Amélie") == TitleNormalizer.loose_key("Amelie")
    assert TitleNormalizer.loose_key("が") != TitleNormalizer.loose_key("か")
    assert TitleNormalizer.loose_key("ば") != TitleNormalizer.loose_key("は")
    assert TitleNormalizer.loose_key("ぱ") != TitleNormalizer.loose_key("は")

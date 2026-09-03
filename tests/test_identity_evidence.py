
from media_importer.features.providers.base import SearchItem, SearchResult
from media_importer.features.scraping.filename_cleaner import FilenameCleaner
from media_importer.features.scraping.identity_evidence import build_identity_evidence
from media_importer.features.scraping.match_engine import MatchEngine

DOUBLE_VISION_FOLDER = (
    "【首发于高清影视之家 www.BBQDDQ.com】"
    "双瞳[国粤英多音轨+简繁字幕].Double.Vision.2002.UNRATED."
    "BluRay.1080p.2Audio.DTS-HD.MA.2.0.x265.10bit-ALT"
)
DOUBLE_VISION_FILE = (
    "Double.Vision.2002.UNRATED.BluRay.1080p.2Audio."
    "DTS-HD.MA.2.0.x265.10bit-ALT.mkv"
)


def _item(item_id, title, original_title, year, media_type="movie"):
    return SearchItem(
        item_id=str(item_id),
        title=title,
        original_title=original_title,
        year=year,
        media_type=media_type,
        provider_type="tmdb",
        poster_url=None,
        vote_average=7.0,
        raw_data={"popularity": 10},
    )


class QueryProvider:
    provider_type = "tmdb"
    display_name = "TMDB"

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def search(self, query, year=None, media_type=None):
        self.calls.append((query, year, media_type))
        return SearchResult(items=list(self.responses.get(query, [])))

    def get_alternative_titles(self, item_id, media_type):
        return []


def test_double_vision_folder_cleans_to_independent_chinese_and_english_titles():
    clean = FilenameCleaner().clean(DOUBLE_VISION_FOLDER)

    assert clean.cjk_title == "双瞳"
    assert clean.clean_title == "Double Vision"
    assert clean.year == 2002


def test_double_vision_file_and_folder_converge_on_same_tmdb_work(tmp_path):
    source = tmp_path / "source"
    folder = source / DOUBLE_VISION_FOLDER
    folder.mkdir(parents=True)
    video = folder / DOUBLE_VISION_FILE
    video.touch()
    double_vision = _item("57100", "双瞳", "雙瞳", 2002)
    provider = QueryProvider({"Double Vision": [double_vision], "双瞳": [double_vision]})

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "57100"
    assert result.selected_candidate.why_selected == "evidence_converged"
    assert result.tier_short_reason == "文件名与目录名指向同一作品"
    assert {signal["source"] for signal in result.identity_evidence["signals"]} == {
        "file", "folder",
    }


def test_unrelated_folder_cannot_block_strong_filename_match(tmp_path):
    source = tmp_path / "source"
    folder = source / "随手建的无关目录"
    folder.mkdir(parents=True)
    video = folder / "Inception.2010.1080p.BluRay.mkv"
    video.touch()
    inception = _item("27205", "Inception", "Inception", 2010)
    unrelated = _item("999", "随手建的无关目录", "Unrelated", 2020)
    provider = QueryProvider({"Inception": [inception], "随手建的无关目录": [unrelated]})

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "27205"
    assert all(call[0] != "随手建的无关目录" for call in provider.calls)


def test_generic_tv_folder_cannot_force_exact_movie_filename_to_tv(tmp_path):
    source = tmp_path / "source"
    folder = source / "TV"
    folder.mkdir(parents=True)
    video = folder / "Inception.2010.mkv"
    video.touch()
    inception = _item("27205", "Inception", "Inception", 2010)
    provider = QueryProvider({"Inception": [inception]})

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "27205"
    assert provider.calls[0][2] is None


def test_file_directly_under_source_root_does_not_use_root_name(tmp_path):
    source = tmp_path / "本周下载"
    source.mkdir()
    video = source / "Inception.2010.mkv"
    video.touch()

    evidence = build_identity_evidence(
        video.name,
        video_path=str(video),
        source_dir=str(source),
        cleaner=FilenameCleaner(),
    )

    assert [signal["source"] for signal in evidence["signals"]] == ["file"]
    assert evidence["ignored_directories"][0]["reason"] == "视频直接位于来源根目录"


def test_generic_download_folder_is_ignored_when_filename_is_weak(tmp_path):
    source = tmp_path / "source"
    folder = source / "downloads"
    folder.mkdir(parents=True)
    video = folder / "video.mkv"
    video.touch()

    evidence = build_identity_evidence(
        video.name,
        video_path=str(video),
        source_dir=str(source),
        cleaner=FilenameCleaner(),
    )

    assert [signal["source"] for signal in evidence["signals"]] == ["file"]
    assert evidence["ignored_directories"][-1]["reason"] == "通用目录名不作为片名"


def test_movie_folder_with_multiple_videos_is_not_title_evidence(tmp_path):
    source = tmp_path / "source"
    folder = source / "合集目录"
    folder.mkdir(parents=True)
    video = folder / "Movie.A.2020.mkv"
    sibling = folder / "Movie.B.2021.mp4"
    video.touch()
    sibling.touch()

    engine = MatchEngine({"source_dir": str(source)})
    context = engine._collect_context(str(video))
    evidence = build_identity_evidence(
        video.name,
        video_path=str(video),
        source_dir=str(source),
        cleaner=FilenameCleaner(),
        path_context=context,
    )

    assert [signal["source"] for signal in evidence["signals"]] == ["file"]
    assert "多个视频" in evidence["ignored_directories"][-1]["reason"]


def test_ignored_promotion_video_does_not_disable_movie_folder_evidence(tmp_path):
    source = tmp_path / "source"
    folder = source / DOUBLE_VISION_FOLDER
    folder.mkdir(parents=True)
    video = folder / DOUBLE_VISION_FILE
    video.write_bytes(b"main" * 1024 * 1024)
    (folder / "点击进入www.example.com下载更多电影.mp4").write_bytes(b"ad")
    double_vision = _item("57100", "双瞳", "雙瞳", 2002)
    provider = QueryProvider({"Double Vision": [double_vision], "双瞳": [double_vision]})

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "AUTO_PASS"
    assert result.selected_candidate.why_selected == "evidence_converged"
    assert {signal["source"] for signal in result.identity_evidence["signals"]} == {
        "file", "folder",
    }


def test_weak_bdmv_filename_uses_nearest_meaningful_ancestor(tmp_path):
    source = tmp_path / "source"
    stream = source / "Inception.2010" / "BDMV" / "STREAM"
    stream.mkdir(parents=True)
    video = stream / "00001.m2ts"
    video.touch()
    inception = _item("27205", "Inception", "Inception", 2010)
    provider = QueryProvider({"Inception": [inception]})

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "27205"
    assert result.selected_candidate.why_selected == "folder_rescue"


def test_bdmv_stream_segments_do_not_turn_movie_folder_into_multi_movie_container(tmp_path):
    source = tmp_path / "source"
    stream = source / "Inception.2010" / "BDMV" / "STREAM"
    stream.mkdir(parents=True)
    video = stream / "00001.m2ts"
    video.touch()
    (stream / "00002.m2ts").touch()
    (stream / "00003.m2ts").touch()
    inception = _item("27205", "Inception", "Inception", 2010)
    provider = QueryProvider({"Inception": [inception]})

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "27205"
    assert result.selected_candidate.why_selected == "folder_rescue"


def test_episode_only_filename_uses_series_folder_above_season_directory(tmp_path):
    source = tmp_path / "source"
    season = source / "权力的游戏" / "Season 01"
    season.mkdir(parents=True)
    video = season / "S01E01.mkv"
    video.touch()
    series = _item("1399", "权力的游戏", "Game of Thrones", 2011, media_type="tv")
    provider = QueryProvider({"权力的游戏": [series]})

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "1399"
    assert result.selected_candidate.why_selected == "folder_rescue"
    assert provider.calls[0][2] == "tv"


def test_credible_file_folder_conflict_requires_confirmation(tmp_path):
    source = tmp_path / "source"
    folder = source / "Arrival.2016"
    folder.mkdir(parents=True)
    video = folder / "Interview.mkv"
    video.touch()
    interview = _item("1", "Interview", "Interview", 2014)
    arrival = _item("2", "Arrival", "Arrival", 2016)
    provider = QueryProvider({"Interview": [interview], "Arrival": [arrival]})

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "NEEDS_CONFIRM"
    assert any(concern.code == "CONFLICTING_INFO" for concern in result.concerns)


def test_unrelated_folder_does_not_promote_one_item_from_broad_file_results(tmp_path):
    source = tmp_path / "source"
    folder = source / "Arrival.2016"
    folder.mkdir(parents=True)
    video = folder / "Mystery.2016.mkv"
    video.touch()
    other = _item("1", "Mystery Road", "Mystery Road", 2016)
    arrival = _item("2", "Arrival", "Arrival", 2016)
    provider = QueryProvider({"Mystery": [other, arrival], "Arrival": [arrival]})

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "NEEDS_CONFIRM"


def test_unrelated_folder_does_not_promote_only_same_year_fuzzy_file_result(tmp_path):
    source = tmp_path / "source"
    folder = source / "Arrival.2016"
    folder.mkdir(parents=True)
    video = folder / "Mystery.2016.mkv"
    video.touch()
    arrival = _item("2", "Arrival", "Arrival", 2016)
    provider = QueryProvider({"Mystery": [arrival], "Arrival": [arrival]})

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "NEEDS_CONFIRM"


def test_provider_official_alias_can_confirm_unique_same_year_movie(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    video = source / "As.Far.As.My.Feet.Will.Carry.Me.2001.1080p.BluRay.mkv"
    video.touch()
    movie = _item("11476", "极地重生", "So weit die Füße tragen", 2001)

    class AliasProvider(QueryProvider):
        def get_alternative_titles(self, item_id, media_type):
            assert item_id == "11476"
            assert media_type == "movie"
            return ["As Far as My Feet Will Carry Me"]

    provider = AliasProvider({"As Far As My Feet Will Carry Me": [movie]})
    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [provider],
        video_path=str(video),
    )

    assert result.match_level == "AUTO_PASS"
    assert result.provider_id == "11476"
    assert result.selected_candidate.why_selected == "provider_alias"
    assert result.tier_short_reason == "标题命中影视资料官方别名"


def test_provider_alias_never_overrides_year_mismatch(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    video = source / "As.Far.As.My.Feet.Will.Carry.Me.2002.1080p.BluRay.mkv"
    video.touch()
    movie = _item("11476", "极地重生", "So weit die Füße tragen", 2001)

    class AliasProvider(QueryProvider):
        def get_alternative_titles(self, item_id, media_type):
            return ["As Far as My Feet Will Carry Me"]

    result = MatchEngine({"source_dir": str(source)}).match(
        video.name,
        [AliasProvider({"As Far As My Feet Will Carry Me": [movie]})],
        video_path=str(video),
    )

    assert result.match_level == "NEEDS_CONFIRM"


def test_episode_range_folder_does_not_override_concrete_file_episode(tmp_path):
    source = tmp_path / "source"
    folder = source / "北海鲸梦.第一季.2021.EP01-05.HD1080P"
    folder.mkdir(parents=True)
    video = folder / "北海鲸梦.第一季.2021.EP05.HD1080P.mkv"
    video.touch()

    evidence = build_identity_evidence(
        video.name,
        video_path=str(video),
        source_dir=str(source),
        cleaner=FilenameCleaner(),
    )

    file_signal, folder_signal = evidence["signals"]
    assert file_signal["episode"] == 5
    assert folder_signal["episodes"] == [1, 2, 3, 4, 5]
    assert folder_signal["episode"] == 5


def test_fnos_north_water_episode_batch_uses_clean_series_identity(tmp_path):
    source = tmp_path / "source"
    folder = source / "北海鲸梦.第一季.2021.EP01-05.HD1080P.X264.AAC.English.CHS-ENG.Mp4er"
    folder.mkdir(parents=True)
    series = _item("86941", "北海鲸梦", "The North Water", 2021, media_type="tv")
    provider = QueryProvider({"北海鲸梦": [series]})

    for episode in range(1, 6):
        video = folder / (
            f"北海鲸梦.第一季.2021.EP{episode:02d}."
            "HD1080P.X264.AAC.English.CHS-ENG.Mp4er.mp4"
        )
        video.touch()
        result = MatchEngine({"source_dir": str(source)}).match(
            video.name,
            [provider],
            video_path=str(video),
        )

        assert result.match_level == "AUTO_PASS"
        assert result.provider_id == "86941"
        file_signal, folder_signal = result.identity_evidence["signals"]
        assert file_signal["titles"] == ["北海鲸梦"]
        assert file_signal["season"] == 1
        assert file_signal["episode"] == episode
        assert folder_signal["episode"] == episode

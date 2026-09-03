import itertools

import pytest

from media_importer.features.scraping.filename_cleaner import FilenameCleaner
from media_importer.features.scraping.release_identity import parse_release_identity


@pytest.mark.parametrize(
    ("filename", "title", "cjk", "year", "season", "episode"),
    [
        ("小姐.加长版.中英特效字幕.The.Handmaiden.2016.EXTENDED.KOREAN.BD1080P.X264.mkv", "The Handmaiden", "小姐", 2016, None, None),
        ("[YYeTs].Gintama.S01E01.720p.mkv", "Gintama", None, None, 1, 1),
        ("[Nekomoe kissaten&LoliHouse] 葬送的芙莉莲 - 28 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv", "葬送的芙莉莲", None, None, 1, 28),
        ("The.4K.Movie.2020.2160p.WEB-DL.DDP5.1.H265-GROUP.mkv", "The 4K Movie", None, 2020, None, None),
        ("Korean.Extended.2018.1080p.WEB-DL.mkv", "Korean Extended", None, 2018, None, None),
        ("1984.1984.1080p.BluRay.x264.mkv", "1984", None, 1984, None, None),
        ("权力的游戏.Game.of.Thrones.1x02.1080p.BluRay.mkv", "Game of Thrones", "权力的游戏", None, 1, 2),
        ("流浪地球2.The.Wandering.Earth.II.2023.2160p.UHD.BluRay.REMUX.HEVC.TrueHD.Atmos.mkv", "The Wandering Earth II", "流浪地球2", 2023, None, None),
        ("大汉王朝01.mkv", "大汉王朝", None, None, 1, 1),
        ("The.Office.US.S02E03.PROPER.1080p.WEB-DL.mkv", "The Office US", None, None, 2, 3),
        ("[REC].2007.1080p.BluRay.x264.mkv", "REC", None, 2007, None, None),
        ("[Moozzi2] Violet Evergarden - 01 [BD 1920x1080 x.264 FLACx2].mkv", "Violet Evergarden", None, None, 1, 1),
        ("电影天堂www.dytt89.com.阿甘正传.Forrest.Gump.1994.BluRay.1080p.x265.10bit.mkv", "Forrest Gump", "阿甘正传", 1994, None, None),
        ("【高清影视之家发布 www.BBQDDQ.com】奥本海默.Oppenheimer.2023.2160p.UHD.BluRay.REMUX.mkv", "Oppenheimer", "奥本海默", 2023, None, None),
    ],
)
def test_representative_release_names(filename, title, cjk, year, season, episode):
    result = FilenameCleaner().clean(filename)
    assert result.clean_title == title
    assert result.cjk_title == cjk
    assert result.year == year
    assert result.season == season
    assert result.episode == episode


def test_release_identity_keeps_structured_evidence():
    identity = parse_release_identity(
        "小姐.加长版.中英特效字幕.The.Handmaiden.2016.EXTENDED.KOREAN.BD1080P.X264-GROUP.mkv"
    )
    assert identity.title_candidates == ("小姐", "The Handmaiden")
    assert "加长版" in identity.editions
    assert "中英特效字幕" in identity.subtitle_tags
    assert "KOREAN" in identity.languages
    assert identity.resolution == "BD1080P"
    assert identity.release_group == "GROUP"
    assert any(item.startswith("年份=") for item in identity.evidence)


def test_source_token_hyphen_is_not_mistaken_for_release_group():
    identity = parse_release_identity("Movie.2020.1080p.WEB-DL.H265.mkv")
    assert identity.release_group == ""
    assert identity.source == "WEB-DL"


def test_fnos_as_far_as_my_feet_will_carry_me_release_keeps_both_titles():
    identity = parse_release_identity(
        "极地重生(蓝光特效中英双字幕).As.Far.As.My.Feet.Will.Carry.Me."
        "2001.BD-1080p.X264.AAC.CHS.ENG-UUMp4.mp4"
    )

    assert identity.title_candidates[:2] == (
        "极地重生",
        "As Far As My Feet Will Carry Me",
    )
    assert identity.year == 2001
    assert identity.resolution in {"BD-1080P", "1080P"}
    assert "蓝光特效中英双字幕" in identity.subtitle_tags
    assert not any("广告域名=Carry.Me" in item for item in identity.evidence)


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("Stand.By.Me.1986.1080p.BluRay.x264.mkv", "Stand By Me"),
        ("Let.Me.In.2010.1080p.BluRay.x264.mkv", "Let Me In"),
        ("Call.Me.By.Your.Name.2017.1080p.BluRay.x264.mkv", "Call Me By Your Name"),
    ],
)
def test_dot_me_inside_a_title_is_not_an_ad_domain(filename, expected):
    identity = parse_release_identity(filename)

    assert identity.primary_title == expected
    assert not any(item.startswith("广告域名=") for item in identity.evidence)


@pytest.mark.parametrize("season_text,season", [("第一季", 1), ("第二季", 2), ("第十二季", 12)])
def test_chinese_number_season_is_removed_from_series_title(season_text, season):
    identity = parse_release_identity(f"北海鲸梦.{season_text}.2021.EP05.HD1080P.X264.mkv")

    assert identity.title_candidates == ("北海鲸梦",)
    assert identity.season == season
    assert identity.episode == 5


def test_episode_range_is_preserved_as_structured_evidence():
    identity = parse_release_identity("北海鲸梦.第一季.2021.EP01-05.HD1080P.X264.mkv")

    assert identity.title_candidates == ("北海鲸梦",)
    assert identity.season == 1
    assert identity.episodes == (1, 2, 3, 4, 5)
    assert "集范围=E01-E05" in identity.evidence


@pytest.mark.parametrize(
    ("filename", "titles", "year", "season", "episode", "media_type"),
    [
        (
            "极地重生(蓝光特效中英双字幕).As.Far.As.My.Feet.Will.Carry.Me."
            "2001.BD-1080p.X264.AAC.CHS.ENG-UUMp4.mp4",
            ("极地重生", "As Far As My Feet Will Carry Me"),
            2001,
            None,
            None,
            "movie",
        ),
        (
            "北海鲸梦.第一季.2021.EP05.HD1080P.X264.AAC."
            "English.CHS-ENG.Mp4er.mp4",
            ("北海鲸梦",),
            2021,
            1,
            5,
            "tv",
        ),
        (
            "I.Am.Legend.2007.BluRay.2160p.x265.10bit.HDR.3Audio-MiniHD.mkv",
            ("I Am Legend",),
            2007,
            None,
            None,
            "movie",
        ),
        (
            "Double.Vision.2002.UNRATED.BluRay.1080p.2Audio."
            "DTS-HD.MA.2.0.x265.10bit-ALT.mkv",
            ("Double Vision",),
            2002,
            None,
            None,
            "movie",
        ),
        (
            "Babel.2006.2160p.HQ.WEB-DL.H265.60fps.AAC-DreamHD.mp4",
            ("Babel",),
            2006,
            None,
            None,
            "movie",
        ),
        (
            "小姐.아가씨.2016.mkv",
            ("小姐",),
            2016,
            None,
            None,
            "movie",
        ),
        (
            "小姐.加长版.中英特效字幕.The.Handmaiden.2016.EXTENDED.KOREAN."
            "BD1080P.X264.DTS-HD.MA.5.1.Mandarin&Korean.CHS-ENG.FFa....mkv",
            ("小姐", "The Handmaiden"),
            2016,
            None,
            None,
            "movie",
        ),
    ],
)
def test_current_fnos_release_names_remain_structured(
    filename, titles, year, season, episode, media_type
):
    identity = parse_release_identity(filename)

    assert identity.title_candidates == titles
    assert identity.year == year
    assert identity.season == season
    assert identity.episode == episode
    assert identity.media_type_hint == media_type


def test_combinatorial_release_corpus_has_at_least_800_contract_cases():
    titles = [
        "The.Handmaiden", "Forrest.Gump", "The.4K.Movie", "Korean", "Extended",
        "流浪地球.The.Wandering.Earth", "寄生虫.Parasite", "霸王别姬.Farewell.My.Concubine",
        "千与千寻.Spirited.Away", "无间道.Infernal.Affairs",
    ]
    years = ["1994", "2001", "2016", "2019", "2023"]
    technical = [
        "1080p.BluRay.x264", "2160p.WEB-DL.H265", "BD1080P.X264",
        "720p.HDTV.HEVC", "2160p.UHD.REMUX", "1080p.WEBRip.AV1",
    ]
    groups = ["-GROUP", "-WiKi", "-MTeam"]
    cases = list(itertools.product(titles, years, technical, groups))
    assert len(cases) >= 800
    for title, year, tags, group in cases:
        identity = parse_release_identity(f"{title}.{year}.{tags}{group}.mkv")
        assert identity.year == int(year)
        assert identity.title_candidates
        assert identity.resolution

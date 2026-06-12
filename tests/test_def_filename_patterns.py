import unittest
from media_importer.scraper.filename_cleaner import FilenameCleaner


FILENAME_TEST_CASES = [
    # ============================================================
    # Category 1: Standard English Movies (10)
    # ============================================================
    {
        "id": "M01",
        "filename": "The.Shawshank.Redemption.1994.1080p.BluRay.x264-SPARKS.mkv",
        "category": "movie",
        "expected_title": "The Shawshank Redemption",
        "expected_year": 1994,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "M02",
        "filename": "Inception.2010.720p.BRrip.x264.YIFY.mp4",
        "category": "movie",
        "expected_title": "Inception",
        "expected_year": 2010,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "M03",
        "filename": "The.Dark.Knight.2008.2160p.UHD.BluRay.x265-HDH.mkv",
        "category": "movie",
        "expected_title": "The Dark Knight",
        "expected_year": 2008,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "M04",
        "filename": "Parasite.2019.1080p.WEB-DL.DDP5.1.x264-EVO.mkv",
        "category": "movie",
        "expected_title": "Parasite",
        "expected_year": 2019,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "M05",
        "filename": "Interstellar.2014.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-EPSiLON.mkv",
        "category": "movie",
        "expected_title": "Interstellar",
        "expected_year": 2014,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "M06",
        "filename": "Avengers.Endgame.2019.1080p.HDR.HEVC.DTS.X-PTP.mkv",
        "category": "movie",
        "expected_title": "Avengers Endgame",
        "expected_year": 2019,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "M07",
        "filename": "John.Wick.Chapter.4.2023.1080p.WEB-DL.DDP5.1.x264-CM.mkv",
        "category": "movie",
        "expected_title": "John Wick Chapter 4",
        "expected_year": 2023,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "M08",
        "filename": "Dune.Part.Two.2024.2160p.UHD.WEB-DL.DV.HDR10.Plus.mkv",
        "category": "movie",
        "expected_title": "Dune Part Two",
        "expected_year": 2024,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "M09",
        "filename": "Oppenheimer.2023.1080p.BluRay.x264-PLUTONIUM.mkv",
        "category": "movie",
        "expected_title": "Oppenheimer",
        "expected_year": 2023,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "M10",
        "filename": "The.Matrix.1999.1080p.BluRay.HEVC.DTS-HD.MA.5.1-FGT.mkv",
        "category": "movie",
        "expected_title": "The Matrix",
        "expected_year": 1999,
        "expected_season": None,
        "expected_episode": None,
    },

    # ============================================================
    # Category 2: Chinese+English Mixed Title Movies (5)
    # ============================================================
    {
        "id": "CM01",
        "filename": "盗梦空间.Inception.2010.BD.1080P.国英双语.mkv",
        "category": "movie_cjk",
        "expected_title": "Inception",
        "expected_year": 2010,
        "expected_season": None,
        "expected_episode": None,
        "expected_cjk_title": "盗梦空间",
    },
    {
        "id": "CM02",
        "filename": "肖申克的救赎.The.Shawshank.Redemption.1994.1080p.BluRay.x264.mkv",
        "category": "movie_cjk",
        "expected_title": "The Shawshank Redemption",
        "expected_year": 1994,
        "expected_season": None,
        "expected_episode": None,
        "expected_cjk_title": "肖申克的救赎",
    },
    {
        "id": "CM03",
        "filename": "流浪地球2.The.Wandering.Earth.II.2023.1080p.WEB-DL.mkv",
        "category": "movie_cjk",
        "expected_title": "流浪地球2 The Wandering Earth II",
        "expected_year": 2023,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "CM04",
        "filename": "长津湖.The.Battle.at.Lake.Changjin.2021.1080p.HDR.mkv",
        "category": "movie_cjk",
        "expected_title": "The Battle at Lake Changjin",
        "expected_year": 2021,
        "expected_season": None,
        "expected_episode": None,
        "expected_cjk_title": "长津湖",
    },
    {
        "id": "CM05",
        "filename": "满江红.Full.River.Red.2023.1080p.WEB-DL.H.265.mkv",
        "category": "movie_cjk",
        "expected_title": "Full River Red",
        "expected_year": 2023,
        "expected_season": None,
        "expected_episode": None,
        "expected_cjk_title": "满江红",
    },

    # ============================================================
    # Category 3: TV Series - Breaking Bad S01 (5 episodes)
    # ============================================================
    {
        "id": "TV01",
        "filename": "Breaking.Bad.S01E01.720p.BluRay.x264-CLUE.mkv",
        "category": "tv",
        "expected_title": "Breaking Bad",
        "expected_year": None,
        "expected_season": 1,
        "expected_episode": 1,
    },
    {
        "id": "TV02",
        "filename": "Breaking.Bad.S01E02.720p.BluRay.x264-CLUE.mkv",
        "category": "tv",
        "expected_title": "Breaking Bad",
        "expected_year": None,
        "expected_season": 1,
        "expected_episode": 2,
    },
    {
        "id": "TV03",
        "filename": "Breaking.Bad.S01E03.720p.BluRay.x264-CLUE.mkv",
        "category": "tv",
        "expected_title": "Breaking Bad",
        "expected_year": None,
        "expected_season": 1,
        "expected_episode": 3,
    },
    {
        "id": "TV04",
        "filename": "Breaking.Bad.S01E04.720p.BluRay.x264-CLUE.mkv",
        "category": "tv",
        "expected_title": "Breaking Bad",
        "expected_year": None,
        "expected_season": 1,
        "expected_episode": 4,
    },
    {
        "id": "TV05",
        "filename": "Breaking.Bad.S01E05.720p.BluRay.x264-CLUE.mkv",
        "category": "tv",
        "expected_title": "Breaking Bad",
        "expected_year": None,
        "expected_season": 1,
        "expected_episode": 5,
    },

    # ============================================================
    # Category 4: TV Series - 三体 Three-Body S01 (5 episodes)
    # ============================================================
    {
        "id": "TV06",
        "filename": "三体.Three-Body.S01E01.2023.1080p.WEB-DL.mkv",
        "category": "tv_cjk",
        "expected_title": "Three Body",
        "expected_year": 2023,
        "expected_season": 1,
        "expected_episode": 1,
        "expected_cjk_title": "三体",
    },
    {
        "id": "TV07",
        "filename": "三体.Three-Body.S01E02.2023.1080p.WEB-DL.mkv",
        "category": "tv_cjk",
        "expected_title": "Three Body",
        "expected_year": 2023,
        "expected_season": 1,
        "expected_episode": 2,
        "expected_cjk_title": "三体",
    },
    {
        "id": "TV08",
        "filename": "三体.Three-Body.S01E03.2023.1080p.WEB-DL.mkv",
        "category": "tv_cjk",
        "expected_title": "Three Body",
        "expected_year": 2023,
        "expected_season": 1,
        "expected_episode": 3,
        "expected_cjk_title": "三体",
    },
    {
        "id": "TV09",
        "filename": "三体.Three-Body.S01E04.2023.1080p.WEB-DL.mkv",
        "category": "tv_cjk",
        "expected_title": "Three Body",
        "expected_year": 2023,
        "expected_season": 1,
        "expected_episode": 4,
        "expected_cjk_title": "三体",
    },
    {
        "id": "TV10",
        "filename": "三体.Three-Body.S01E05.2023.1080p.WEB-DL.mkv",
        "category": "tv_cjk",
        "expected_title": "Three Body",
        "expected_year": 2023,
        "expected_season": 1,
        "expected_episode": 5,
        "expected_cjk_title": "三体",
    },

    # ============================================================
    # Category 5: TV Series - Game of Thrones S08 (5 episodes)
    # ============================================================
    {
        "id": "TV11",
        "filename": "Game.of.Thrones.S08E01.1080p.WEB-DL.DDP5.1.H264-BTN.mkv",
        "category": "tv",
        "expected_title": "Game of Thrones",
        "expected_year": None,
        "expected_season": 8,
        "expected_episode": 1,
    },
    {
        "id": "TV12",
        "filename": "Game.of.Thrones.S08E02.1080p.WEB-DL.DDP5.1.H264-BTN.mkv",
        "category": "tv",
        "expected_title": "Game of Thrones",
        "expected_year": None,
        "expected_season": 8,
        "expected_episode": 2,
    },
    {
        "id": "TV13",
        "filename": "Game.of.Thrones.S08E03.1080p.WEB-DL.DDP5.1.H264-BTN.mkv",
        "category": "tv",
        "expected_title": "Game of Thrones",
        "expected_year": None,
        "expected_season": 8,
        "expected_episode": 3,
    },
    {
        "id": "TV14",
        "filename": "Game.of.Thrones.S08E04.1080p.WEB-DL.DDP5.1.H264-BTN.mkv",
        "category": "tv",
        "expected_title": "Game of Thrones",
        "expected_year": None,
        "expected_season": 8,
        "expected_episode": 4,
    },
    {
        "id": "TV15",
        "filename": "Game.of.Thrones.S08E05.1080p.WEB-DL.DDP5.1.H264-BTN.mkv",
        "category": "tv",
        "expected_title": "Game of Thrones",
        "expected_year": None,
        "expected_season": 8,
        "expected_episode": 5,
    },

    # ============================================================
    # Category 6: Anime (5)
    # ============================================================
    {
        "id": "AN01",
        "filename": "[喵萌奶茶屋] 进击的巨人 最终季 - 01 [1080P][HEVC].mp4",
        "category": "anime",
        "expected_title": "进击的巨人 最终季 01",
        "expected_year": None,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "AN02",
        "filename": "[DMG][間諜過家家] Spy.x.Family.S02E01.1080p.WEB-DL.mkv",
        "category": "anime",
        "expected_title": "Spy x Family",
        "expected_year": None,
        "expected_season": 2,
        "expected_episode": 1,
    },
    {
        "id": "AN03",
        "filename": "[ANi] 葬送的芙莉莲 - S01E01 [1080P][Baha][AVC].mp4",
        "category": "anime",
        "expected_title": "葬送的芙莉莲",
        "expected_year": None,
        "expected_season": 1,
        "expected_episode": 1,
    },
    {
        "id": "AN04",
        "filename": "[桜都字幕组] 鬼灭之刃 柱稽古编 - 01 [1080P].mp4",
        "category": "anime",
        "expected_title": "鬼灭之刃 柱稽古编 01",
        "expected_year": None,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "AN05",
        "filename": "[SubGroup] Jujutsu.Kaisen.S02E01.1080p.WEB-DL.x264.mkv",
        "category": "anime",
        "expected_title": "Jujutsu Kaisen",
        "expected_year": None,
        "expected_season": 2,
        "expected_episode": 1,
    },

    # ============================================================
    # Category 7: Documentaries (3)
    # ============================================================
    {
        "id": "DC01",
        "filename": "Planet.Earth.II.S01E01.2016.2160p.UHD.BluRay.REMUX.mkv",
        "category": "documentary",
        "expected_title": "Planet Earth II",
        "expected_year": 2016,
        "expected_season": 1,
        "expected_episode": 1,
    },
    {
        "id": "DC02",
        "filename": "Our.Planet.2019.S01.1080p.WEB-DL.x264.mkv",
        "category": "documentary",
        "expected_title": "Our Planet",
        "expected_year": 2019,
        "expected_season": 1,
        "expected_episode": None,
    },
    {
        "id": "DC03",
        "filename": "The.Blue.Planet.2001.1080p.BluRay.x264-HALCYON.mkv",
        "category": "documentary",
        "expected_title": "The Blue Planet",
        "expected_year": 2001,
        "expected_season": None,
        "expected_episode": None,
    },

    # ============================================================
    # Category 8: Special Editions (5)
    # ============================================================
    {
        "id": "SE01",
        "filename": "Blade.Runner.2049.2017.Directors.Cut.1080p.BluRay.x264.mkv",
        "category": "special_edition",
        "expected_title": "Blade Runner 2049",
        "expected_year": 2017,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "SE02",
        "filename": "The.Lord.of.the.Rings.The.Fellowship.of.the.Ring.2001.Extended.Edition.1080p.BluRay.mkv",
        "category": "special_edition",
        "expected_title": "The Lord of the Rings The Fellowship of the Ring",
        "expected_year": 2001,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "SE03",
        "filename": "Alien.1979.Directors.Cut.1080p.BluRay.x264-HDDEVILS.mkv",
        "category": "special_edition",
        "expected_title": "Alien",
        "expected_year": 1979,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "SE04",
        "filename": "Terminator.2.Judgment.Day.1991.4K.REMASTERED.IMAX.Edition.2160p.mkv",
        "category": "special_edition",
        "expected_title": "Terminator 2 Judgment Day",
        "expected_year": 1991,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "SE05",
        "filename": "Fight.Club.1999.10th.Anniversary.Edition.1080p.BluRay.x264.mkv",
        "category": "special_edition",
        "expected_title": "Fight Club",
        "expected_year": 1999,
        "expected_season": None,
        "expected_episode": None,
    },

    # ============================================================
    # Category 9: Subtitle Files (5)
    # ============================================================
    {
        "id": "SUB01",
        "filename": "Inception.2010.1080p.BluRay.x264-SPARKS.zh.srt",
        "category": "subtitle",
        "expected_title": "Inception",
        "expected_year": 2010,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "SUB02",
        "filename": "Breaking.Bad.S01E01.720p.BluRay.eng.srt",
        "category": "subtitle",
        "expected_title": "Breaking Bad",
        "expected_year": None,
        "expected_season": 1,
        "expected_episode": 1,
    },
    {
        "id": "SUB03",
        "filename": "Game.of.Thrones.S08E01.cht&eng.srt",
        "category": "subtitle",
        "expected_title": "Game of Thrones",
        "expected_year": None,
        "expected_season": 8,
        "expected_episode": 1,
    },
    {
        "id": "SUB04",
        "filename": "三体.Three-Body.S01E01.2023.1080p.WEB-DL.chs&eng.ass",
        "category": "subtitle_cjk",
        "expected_title": "Three Body",
        "expected_year": 2023,
        "expected_season": 1,
        "expected_episode": 1,
        "expected_cjk_title": "三体",
    },
    {
        "id": "SUB05",
        "filename": "The.Matrix.1999.1080p.BluRay.zh-cn.srt",
        "category": "subtitle",
        "expected_title": "The Matrix",
        "expected_year": 1999,
        "expected_season": None,
        "expected_episode": None,
    },

    # ============================================================
    # Category 10: Edge Cases & Various Formats (7)
    # ============================================================
    {
        "id": "E01",
        "filename": "www.example.com-电影资源.教父.The.Godfather.1972.1080p.BluRay.mkv",
        "category": "edge",
        "expected_title": "The Godfather",
        "expected_year": 1972,
        "expected_season": None,
        "expected_episode": None,
        "expected_cjk_title": "教父",
    },
    {
        "id": "E02",
        "filename": "Seinfeld.S01E01E02.720p.DVDRip.XviD.avi",
        "category": "edge",
        "expected_title": "Seinfeld",
        "expected_year": None,
        "expected_season": 1,
        "expected_episode": 1,
    },
    {
        "id": "E03",
        "filename": "Kill.Bill.Vol.1.2003.1080p.BluRay.rmvb",
        "category": "edge",
        "expected_title": "Kill Bill Vol 1",
        "expected_year": 2003,
        "expected_season": None,
        "expected_episode": None,
    },
    {
        "id": "E04",
        "filename": "Chernobyl.S01.COMPLETE.1080p.WEB-DL.x264-TB.mkv",
        "category": "edge",
        "expected_title": "Chernobyl",
        "expected_year": None,
        "expected_season": 1,
        "expected_episode": None,
    },
    {
        "id": "E05",
        "filename": "The.Sopranos.S01.1080p.BluRay.x264-ROVERS.mkv",
        "category": "edge",
        "expected_title": "The Sopranos",
        "expected_year": None,
        "expected_season": 1,
        "expected_episode": None,
    },
    {
        "id": "E06",
        "filename": "[FRDS] 隐秘的角落 The.Bad.Kids.S01E01.2020.1080p.WEB-DL.mkv",
        "category": "edge",
        "expected_title": "The Bad Kids",
        "expected_year": 2020,
        "expected_season": 1,
        "expected_episode": 1,
        "expected_cjk_title": "隐秘的角落",
    },
    {
        "id": "E07",
        "filename": "Batman.Begins.(2005).1080p.BluRay.HEVC.DTS-HD.MA.5.1.mkv",
        "category": "edge",
        "expected_title": "Batman Begins",
        "expected_year": 2005,
        "expected_season": None,
        "expected_episode": None,
    },
]


class TestDefFilenamePatterns(unittest.TestCase):
    def setUp(self):
        self.cleaner = FilenameCleaner()

    def test_all_filenames_parse(self):
        for tc in FILENAME_TEST_CASES:
            with self.subTest(id=tc["id"], filename=tc["filename"]):
                result = self.cleaner.clean(tc["filename"])
                self.assertIsNotNone(result.clean_title, f"{tc['id']}: clean_title should not be None")
                self.assertTrue(len(result.clean_title) > 0, f"{tc['id']}: clean_title should not be empty")

    def test_movie_titles(self):
        movies = [tc for tc in FILENAME_TEST_CASES if tc["category"] == "movie"]
        for tc in movies:
            with self.subTest(id=tc["id"], filename=tc["filename"]):
                result = self.cleaner.clean(tc["filename"])
                self.assertEqual(result.clean_title, tc["expected_title"])
                self.assertEqual(result.year, tc["expected_year"])
                self.assertIsNone(result.season)
                self.assertIsNone(result.episode)

    def test_cjk_movie_titles(self):
        movies = [tc for tc in FILENAME_TEST_CASES if tc["category"] == "movie_cjk"]
        for tc in movies:
            with self.subTest(id=tc["id"], filename=tc["filename"]):
                result = self.cleaner.clean(tc["filename"])
                self.assertEqual(result.clean_title, tc["expected_title"])
                self.assertEqual(result.year, tc["expected_year"])
                if "expected_cjk_title" in tc:
                    self.assertEqual(result.cjk_title, tc["expected_cjk_title"])

    def test_tv_series_breaking_bad(self):
        episodes = [tc for tc in FILENAME_TEST_CASES if tc["id"].startswith("TV0")]
        for tc in episodes:
            with self.subTest(id=tc["id"], filename=tc["filename"]):
                result = self.cleaner.clean(tc["filename"])
                self.assertEqual(result.clean_title, tc["expected_title"])
                self.assertEqual(result.season, tc["expected_season"])
                self.assertEqual(result.episode, tc["expected_episode"])

    def test_tv_series_three_body(self):
        episodes = [tc for tc in FILENAME_TEST_CASES if tc["id"].startswith("TV1")]
        for tc in episodes:
            with self.subTest(id=tc["id"], filename=tc["filename"]):
                result = self.cleaner.clean(tc["filename"])
                self.assertEqual(result.clean_title, tc["expected_title"])
                self.assertEqual(result.year, tc["expected_year"])
                self.assertEqual(result.season, tc["expected_season"])
                self.assertEqual(result.episode, tc["expected_episode"])
                if "expected_cjk_title" in tc:
                    self.assertEqual(result.cjk_title, tc["expected_cjk_title"])

    def test_anime_filenames(self):
        anime = [tc for tc in FILENAME_TEST_CASES if tc["category"] == "anime"]
        for tc in anime:
            with self.subTest(id=tc["id"], filename=tc["filename"]):
                result = self.cleaner.clean(tc["filename"])
                self.assertIsNotNone(result.clean_title)
                self.assertTrue(len(result.clean_title) > 0)
                if tc.get("expected_season") is not None:
                    self.assertEqual(result.season, tc["expected_season"])
                if tc.get("expected_episode") is not None:
                    self.assertEqual(result.episode, tc["expected_episode"])

    def test_documentary_filenames(self):
        docs = [tc for tc in FILENAME_TEST_CASES if tc["category"] == "documentary"]
        for tc in docs:
            with self.subTest(id=tc["id"], filename=tc["filename"]):
                result = self.cleaner.clean(tc["filename"])
                self.assertEqual(result.clean_title, tc["expected_title"])
                self.assertEqual(result.year, tc["expected_year"])
                if tc.get("expected_season") is not None:
                    self.assertEqual(result.season, tc["expected_season"])

    def test_special_edition_filenames(self):
        editions = [tc for tc in FILENAME_TEST_CASES if tc["category"] == "special_edition"]
        for tc in editions:
            with self.subTest(id=tc["id"], filename=tc["filename"]):
                result = self.cleaner.clean(tc["filename"])
                self.assertEqual(result.clean_title, tc["expected_title"])
                self.assertEqual(result.year, tc["expected_year"])

    def test_subtitle_filenames(self):
        subs = [tc for tc in FILENAME_TEST_CASES if tc["category"].startswith("subtitle")]
        for tc in subs:
            with self.subTest(id=tc["id"], filename=tc["filename"]):
                result = self.cleaner.clean(tc["filename"])
                self.assertEqual(result.clean_title, tc["expected_title"])
                if tc.get("expected_year") is not None:
                    self.assertEqual(result.year, tc["expected_year"])
                if tc.get("expected_season") is not None:
                    self.assertEqual(result.season, tc["expected_season"])
                if tc.get("expected_episode") is not None:
                    self.assertEqual(result.episode, tc["expected_episode"])

    def test_edge_case_filenames(self):
        edges = [tc for tc in FILENAME_TEST_CASES if tc["category"] == "edge"]
        for tc in edges:
            with self.subTest(id=tc["id"], filename=tc["filename"]):
                result = self.cleaner.clean(tc["filename"])
                self.assertEqual(result.clean_title, tc["expected_title"])
                if tc.get("expected_year") is not None:
                    self.assertEqual(result.year, tc["expected_year"])
                if tc.get("expected_season") is not None:
                    self.assertEqual(result.season, tc["expected_season"])

    def test_total_count(self):
        self.assertGreaterEqual(len(FILENAME_TEST_CASES), 50,
                                f"Expected at least 50 test filenames, got {len(FILENAME_TEST_CASES)}")

    def test_tv_episodes_have_season_and_episode(self):
        tv_cases = [tc for tc in FILENAME_TEST_CASES
                    if tc["category"] in ("tv", "tv_cjk")]
        for tc in tv_cases:
            with self.subTest(id=tc["id"]):
                self.assertIsNotNone(tc.get("expected_season"),
                                     f"{tc['id']}: TV series should have expected_season")
                self.assertIsNotNone(tc.get("expected_episode"),
                                     f"{tc['id']}: TV series should have expected_episode")

    def test_categories_summary(self):
        categories = {}
        for tc in FILENAME_TEST_CASES:
            cat = tc["category"]
            categories[cat] = categories.get(cat, 0) + 1
        self.assertGreaterEqual(len(FILENAME_TEST_CASES), 50)


if __name__ == "__main__":
    unittest.main()

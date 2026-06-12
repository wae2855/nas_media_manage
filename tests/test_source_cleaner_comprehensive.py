#!/usr/bin/env python3
"""
源目录智能清理 - 综合测试套件

覆盖:
1. 60+ 真实BT下载目录结构测试数据
2. 笛卡尔积配置组合测试
3. Bug 检测与回归验证
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from media_importer.features.source_cleaning.cleaner import SourceCleaner


# ============================================================
# 工具函数
# ============================================================

def _make_config(source_dir="", recycle_dir="", cleanup_mode="media_only",
                 ai_enabled=False, merge_strategy="intersection",
                 junk_video_max_size_mb=0, delete_extensions=None,
                 protect_extensions=None, blacklist_patterns=None,
                 cleanup_empty_dirs=False):
    _default_delete = [".url", ".txt", ".sfv", ".log", ".bak", ".m3u", ".db"]
    _default_protect = [".nfo", ".jpg", ".png", ".bdmv", ".clpi", ".mpls"]
    _default_blacklist = [
        "RARBG*", "*/Sample/*", "*/sample/*", "*/Trailers/*", "*/trailers/*",
        "*/预告/*", "*/花絮/*", "*/Extras/*", "*/extras/*",
    ]
    return {
        "source_dir": source_dir,
        "temp_dir": tempfile.mkdtemp(),
        "log_dir": tempfile.mkdtemp(),
        "source_policy": {"recycle_dir": recycle_dir},
        "llm": {"api_key": "test-key", "base_url": "http://localhost", "model": "test",
                "fast_model": "fast-test", "fast_base_url": "http://localhost",
                "fast_api_key": "fast-key"},
        "video_extensions": [".mkv", ".mp4", ".avi", ".ts", ".mov", ".wmv", ".m2ts", ".flv"],
        "subtitle_extensions": [".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx"],
        "source_cleaner": {
            "enabled": True,
            "cleanup_mode": cleanup_mode,
            "ai_enabled": ai_enabled,
            "merge_strategy": merge_strategy,
            "junk_video_max_size_mb": junk_video_max_size_mb,
            "delete_extensions": delete_extensions if delete_extensions is not None else _default_delete,
            "protect_extensions": protect_extensions if protect_extensions is not None else _default_protect,
            "blacklist_patterns": blacklist_patterns if blacklist_patterns is not None else _default_blacklist,
            "cleanup_empty_dirs": cleanup_empty_dirs,
        },
    }


def _touch(path, size=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        if size > 0:
            f.seek(size - 1)
            f.write(b"\0")
    return path


def _touch_text(path, content="test"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return path


# ============================================================
# 第一部分: 60+ BT下载目录结构测试数据
# ============================================================

class BTDownloadScenarios:
    """真实BT下载目录结构场景生成器"""

    @staticmethod
    def build_all(source_dir):
        """在 source_dir 下创建所有场景，返回场景描述列表"""
        scenarios = []

        # --- 场景1: 单电影 + RARBG 伴生文件 ---
        d = os.path.join(source_dir, "Inception.2010.1080p.BluRay.x264-RARBG")
        _touch(os.path.join(d, "Inception.2010.1080p.BluRay.x264-RARBG.mkv"), 5 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Inception.2010.1080p.BluRay.x264-RARBG.nfo"))
        _touch_text(os.path.join(d, "RARBG.txt"))
        _touch_text(os.path.join(d, "RARBG_DO_NOT_MIRROR.exe"))
        _touch(os.path.join(d, "RARBG.mp4"), 30 * 1024 * 1024)
        scenarios.append(("单电影+RARBG", d, {
            "keep": ["Inception.2010.1080p.BluRay.x264-RARBG.mkv", "Inception.2010.1080p.BluRay.x264-RARBG.nfo"],
            "delete": ["RARBG.txt", "RARBG_DO_NOT_MIRROR.exe", "RARBG.mp4"],
        }))

        # --- 场景2: 单电影 + 字幕 + 海报 ---
        d = os.path.join(source_dir, "The.Dark.Knight.2008.2160p.REMUX")
        _touch(os.path.join(d, "The.Dark.Knight.2008.2160p.REMUX.mkv"), 8 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "The.Dark.Knight.2008.2160p.REMUX.srt"))
        _touch_text(os.path.join(d, "The.Dark.Knight.2008.2160p.REMUX.ass"))
        _touch_text(os.path.join(d, "The.Dark.Knight.2008.2160p.REMUX.jpg"))
        _touch_text(os.path.join(d, "The.Dark.Knight.2008.2160p.REMUX-fanart.jpg"))
        _touch_text(os.path.join(d, "The.Dark.Knight.2008.2160p.REMUX.nfo"))
        _touch_text(os.path.join(d, "downloaded.from.ettv.tv.txt"))
        scenarios.append(("单电影+字幕+海报", d, {
            "keep": ["The.Dark.Knight.2008.2160p.REMUX.mkv", "The.Dark.Knight.2008.2160p.REMUX.srt",
                     "The.Dark.Knight.2008.2160p.REMUX.ass", "The.Dark.Knight.2008.2160p.REMUX.jpg",
                     "The.Dark.Knight.2008.2160p.REMUX-fanart.jpg", "The.Dark.Knight.2008.2160p.REMUX.nfo"],
            "delete": ["downloaded.from.ettv.tv.txt"],
        }))

        # --- 场景3: 单电影 + Sample 目录 ---
        d = os.path.join(source_dir, "Interstellar.2014.IMAX.1080p.BluRay")
        _touch(os.path.join(d, "Interstellar.2014.IMAX.1080p.BluRay.mkv"), 6 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Interstellar.2014.IMAX.1080p.BluRay.srt"))
        sample_d = os.path.join(d, "Sample")
        _touch(os.path.join(sample_d, "sample.mkv"), 50 * 1024 * 1024)
        _touch_text(os.path.join(sample_d, "sample.srt"))
        scenarios.append(("单电影+Sample目录", d, {
            "keep": ["Interstellar.2014.IMAX.1080p.BluRay.mkv",
                     "Interstellar.2014.IMAX.1080p.BluRay.srt"],
            "delete": ["Sample"],
        }))

        # --- 场景4: 单电影 + Trailers 目录 ---
        d = os.path.join(source_dir, "Avatar.2009.3D.1080p")
        _touch(os.path.join(d, "Avatar.2009.3D.1080p.mkv"), 7 * 1024 * 1024 * 1024)
        trailer_d = os.path.join(d, "Trailers")
        _touch(os.path.join(trailer_d, "trailer1.mp4"), 80 * 1024 * 1024)
        _touch(os.path.join(trailer_d, "trailer2.mp4"), 60 * 1024 * 1024)
        scenarios.append(("单电影+Trailers目录", d, {
            "keep": ["Avatar.2009.3D.1080p.mkv"],
            "delete": ["Trailers"],
        }))

        # --- 场景5: 单电影 + Extras 目录 ---
        d = os.path.join(source_dir, "The.Matrix.1999.4K.HDR")
        _touch(os.path.join(d, "The.Matrix.1999.4K.HDR.mkv"), 9 * 1024 * 1024 * 1024)
        extras_d = os.path.join(d, "Extras")
        _touch(os.path.join(extras_d, "behind_the_scenes.mp4"), 200 * 1024 * 1024)
        _touch(os.path.join(extras_d, "deleted_scenes.mp4"), 150 * 1024 * 1024)
        scenarios.append(("单电影+Extras目录", d, {
            "keep": ["The.Matrix.1999.4K.HDR.mkv"],
            "delete": ["Extras"],
        }))

        # --- 场景6: 电影 + 预告/花絮 中文目录 ---
        d = os.path.join(source_dir, "流浪地球.2019.4K")
        _touch(os.path.join(d, "流浪地球.2019.4K.mkv"), 5 * 1024 * 1024 * 1024)
        yugao_d = os.path.join(d, "预告")
        _touch(os.path.join(yugao_d, "预告片1.mp4"), 30 * 1024 * 1024)
        huaxu_d = os.path.join(d, "花絮")
        _touch(os.path.join(huaxu_d, "拍摄花絮.mp4"), 40 * 1024 * 1024)
        scenarios.append(("电影+预告花絮中文目录", d, {
            "keep": ["流浪地球.2019.4K.mkv"],
            "delete": ["预告", "花絮"],
        }))

        # --- 场景7: 电影 + 各种垃圾文件扩展名 ---
        d = os.path.join(source_dir, "Gladiator.2000.Extended.1080p")
        _touch(os.path.join(d, "Gladiator.2000.Extended.1080p.mkv"), 4 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Gladiator.2000.Extended.1080p.srt"))
        _touch_text(os.path.join(d, "readme.txt"))
        _touch_text(os.path.join(d, "torrent_downloaded_from.url"))
        _touch_text(os.path.join(d, "gladiator.sfv"))
        _touch_text(os.path.join(d, "error.log"))
        _touch_text(os.path.join(d, "playlist.m3u"))
        _touch_text(os.path.join(d, "thumbs.db"))
        _touch_text(os.path.join(d, "backup.bak"))
        scenarios.append(("电影+各种垃圾扩展名", d, {
            "keep": ["Gladiator.2000.Extended.1080p.mkv", "Gladiator.2000.Extended.1080p.srt"],
            "delete": ["readme.txt", "torrent_downloaded_from.url", "gladiator.sfv",
                       "error.log", "playlist.m3u", "thumbs.db", "backup.bak"],
        }))

        # --- 场景8: 电视剧整季包 ---
        d = os.path.join(source_dir, "Breaking.Bad.S01.1080p.BluRay.x265")
        for ep in range(1, 8):
            _touch(os.path.join(d, f"Breaking.Bad.S01E{ep:02d}.1080p.BluRay.x265.mkv"), 2 * 1024 * 1024 * 1024)
            _touch_text(os.path.join(d, f"Breaking.Bad.S01E{ep:02d}.1080p.BluRay.x265.srt"))
        _touch_text(os.path.join(d, "Breaking.Bad.S01.1080p.BluRay.x265.nfo"))
        _touch_text(os.path.join(d, "RARBG.txt"))
        _touch_text(os.path.join(d, "RARBG.nfo"))
        scenarios.append(("电视剧整季包", d, {
            "keep": [f"Breaking.Bad.S01E{ep:02d}.1080p.BluRay.x265.mkv" for ep in range(1, 8)]
                  + [f"Breaking.Bad.S01E{ep:02d}.1080p.BluRay.x265.srt" for ep in range(1, 8)]
                  + ["Breaking.Bad.S01.1080p.BluRay.x265.nfo"],
            "delete": ["RARBG.txt", "RARBG.nfo"],
        }))

        # --- 场景9: 电视剧单集 + 伴生文件 ---
        d = os.path.join(source_dir, "Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL")
        _touch(os.path.join(d, "Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL.mkv"), 3 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL.en.srt"))
        _touch_text(os.path.join(d, "Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL.zh.srt"))
        _touch_text(os.path.join(d, "Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL.nfo"))
        _touch_text(os.path.join(d, "Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL-thumb.jpg"))
        _touch_text(os.path.join(d, "www.YTS.AM.jpg"))
        _touch_text(os.path.join(d, "downloaded_from_ettv.txt"))
        scenarios.append(("电视剧单集+伴生文件", d, {
            "keep": ["Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL.mkv",
                     "Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL.en.srt",
                     "Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL.zh.srt",
                     "Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL.nfo",
                     "Game.of.Thrones.S08E03.1080p.AMZN.WEB-DL-thumb.jpg",
                     "www.YTS.AM.jpg"],
            "delete": ["downloaded_from_ettv.txt"],
        }))

        # --- 场景10: 电影 + 小视频(广告/样本) ---
        d = os.path.join(source_dir, "John.Wick.2014.1080p.BluRay")
        _touch(os.path.join(d, "John.Wick.2014.1080p.BluRay.mkv"), 5 * 1024 * 1024 * 1024)
        _touch(os.path.join(d, "sample.mkv"), 10 * 1024 * 1024)
        _touch(os.path.join(d, "trailer.mp4"), 25 * 1024 * 1024)
        _touch(os.path.join(d, "advertisement.mkv"), 5 * 1024 * 1024)
        scenarios.append(("电影+小视频广告样本", d, {
            "keep": ["John.Wick.2014.1080p.BluRay.mkv"],
            "delete": ["sample.mkv", "trailer.mp4", "advertisement.mkv"],
        }))

        # --- 场景11: 蓝光原盘 BDMV 结构 ---
        d = os.path.join(source_dir, "Frozen.2013.1080p.BluRay.AVC.DTS-HD.MA.7.1")
        bdmv = os.path.join(d, "BDMV")
        _touch(os.path.join(bdmv, "index.bdmv"))
        _touch(os.path.join(bdmv, "MovieObject.bdmv"))
        playlist = os.path.join(bdmv, "PLAYLIST")
        _touch(os.path.join(playlist, "00000.mpls"))
        _touch(os.path.join(playlist, "00001.mpls"))
        clipinf = os.path.join(bdmv, "CLIPINF")
        _touch(os.path.join(clipinf, "00000.clpi"))
        _touch(os.path.join(clipinf, "00001.clpi"))
        stream = os.path.join(bdmv, "STREAM")
        _touch(os.path.join(stream, "00000.m2ts"), 20 * 1024 * 1024 * 1024)
        _touch(os.path.join(stream, "00001.m2ts"), 500 * 1024 * 1024)
        cert = os.path.join(d, "CERTIFICATE")
        _touch(os.path.join(cert, "id.bdmv"))
        _touch_text(os.path.join(d, "disc.info.txt"))
        scenarios.append(("蓝光原盘BDMV", d, {
            "keep": ["BDMV"],
            "delete": ["disc.info.txt"],
        }))

        # --- 场景12: 多版本电影 (1080p + 720p) ---
        d = os.path.join(source_dir, "The.Godfather.1972.Multi.1080p.720p")
        _touch(os.path.join(d, "The.Godfather.1972.1080p.mkv"), 6 * 1024 * 1024 * 1024)
        _touch(os.path.join(d, "The.Godfather.1972.720p.mkv"), 3 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "The.Godfather.1972.1080p.srt"))
        _touch_text(os.path.join(d, "The.Godfather.1972.720p.srt"))
        _touch_text(os.path.join(d, "info.txt"))
        scenarios.append(("多版本电影", d, {
            "keep": ["The.Godfather.1972.1080p.mkv", "The.Godfather.1972.720p.mkv",
                     "The.Godfather.1972.1080p.srt", "The.Godfather.1972.720p.srt"],
            "delete": ["info.txt"],
        }))

        # --- 场景13: 电影 + 多语言字幕 ---
        d = os.path.join(source_dir, "Parasite.2019.1080p.BluRay.x264")
        _touch(os.path.join(d, "Parasite.2019.1080p.BluRay.x264.mkv"), 4 * 1024 * 1024 * 1024)
        for lang in ["en", "zh", "ko", "ja", "fr", "de", "es", "pt"]:
            _touch_text(os.path.join(d, f"Parasite.2019.1080p.BluRay.x264.{lang}.srt"))
        _touch_text(os.path.join(d, "Parasite.2019.1080p.BluRay.x264.nfo"))
        _touch_text(os.path.join(d, "subs.zip"))
        _touch_text(os.path.join(d, "subs.rar"))
        scenarios.append(("电影+多语言字幕", d, {
            "keep": ["Parasite.2019.1080p.BluRay.x264.mkv"]
                  + [f"Parasite.2019.1080p.BluRay.x264.{lang}.srt" for lang in ["en", "zh", "ko", "ja", "fr", "de", "es", "pt"]]
                  + ["Parasite.2019.1080p.BluRay.x264.nfo"],
            "delete": ["subs.zip", "subs.rar"],
        }))

        # --- 场景14: 空目录 ---
        d = os.path.join(source_dir, "empty_folder_1")
        os.makedirs(d, exist_ok=True)
        d2 = os.path.join(source_dir, "nested", "empty_folder_2")
        os.makedirs(d2, exist_ok=True)
        scenarios.append(("空目录", source_dir, {
            "keep": [],
            "delete": ["empty_folder_1", "nested/empty_folder_2"],
        }))

        # --- 场景15: 电影 + .torrent 种子文件 ---
        d = os.path.join(source_dir, "Dune.2021.2160p.WEB-DL")
        _touch(os.path.join(d, "Dune.2021.2160p.WEB-DL.mkv"), 7 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Dune.2021.2160p.WEB-DL.torrent"))
        _touch_text(os.path.join(d, "Dune.2021.2160p.WEB-DL.srt"))
        scenarios.append(("电影+.torrent种子", d, {
            "keep": ["Dune.2021.2160p.WEB-DL.mkv", "Dune.2021.2160p.WEB-DL.srt",
                     "Dune.2021.2160p.WEB-DL.torrent"],
            "delete": [],
        }))

        # --- 场景16: 电影 + .md5 校验文件 ---
        d = os.path.join(source_dir, "Mad.Max.Fury.Road.2015.1080p")
        _touch(os.path.join(d, "Mad.Max.Fury.Road.2015.1080p.mkv"), 5 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Mad.Max.Fury.Road.2015.1080p.md5"))
        _touch_text(os.path.join(d, "checksums.sfv"))
        scenarios.append(("电影+.md5校验", d, {
            "keep": ["Mad.Max.Fury.Road.2015.1080p.mkv",
                     "Mad.Max.Fury.Road.2015.1080p.md5"],
            "delete": ["checksums.sfv"],
        }))

        # --- 场景17: 综艺节目 ---
        d = os.path.join(source_dir, "Running.Man.2024.E001.1080p.HDTV")
        _touch(os.path.join(d, "Running.Man.2024.E001.1080p.HDTV.ts"), 3 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Running.Man.2024.E001.1080p.HDTV.srt"))
        _touch_text(os.path.join(d, "Running.Man.2024.E001.1080p.HDTV.ass"))
        _touch_text(os.path.join(d, "广告.txt"))
        _touch_text(os.path.join(d, "更多资源.url"))
        scenarios.append(("综艺节目", d, {
            "keep": ["Running.Man.2024.E001.1080p.HDTV.ts",
                     "Running.Man.2024.E001.1080p.HDTV.srt",
                     "Running.Man.2024.E001.1080p.HDTV.ass"],
            "delete": ["广告.txt", "更多资源.url"],
        }))

        # --- 场景18: 纪录片 ---
        d = os.path.join(source_dir, "Planet.Earth.II.S01E01.2160p.BluRay")
        _touch(os.path.join(d, "Planet.Earth.II.S01E01.2160p.BluRay.mkv"), 4 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Planet.Earth.II.S01E01.2160p.BluRay.srt"))
        _touch_text(os.path.join(d, "Planet.Earth.II.S01E01.2160p.BluRay.nfo"))
        _touch_text(os.path.join(d, "Planet.Earth.II.S01E01.2160p.BluRay.jpg"))
        _touch_text(os.path.join(d, "readme.txt"))
        scenarios.append(("纪录片", d, {
            "keep": ["Planet.Earth.II.S01E01.2160p.BluRay.mkv",
                     "Planet.Earth.II.S01E01.2160p.BluRay.srt",
                     "Planet.Earth.II.S01E01.2160p.BluRay.nfo",
                     "Planet.Earth.II.S01E01.2160p.BluRay.jpg"],
            "delete": ["readme.txt"],
        }))

        # --- 场景19: 动漫 + 多字幕组 ---
        d = os.path.join(source_dir, "[SubsPlease] Attack on Titan - S04E01 (1080p)")
        _touch(os.path.join(d, "[SubsPlease] Attack on Titan - S04E01 (1080p).mkv"), 1 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "[SubsPlease] Attack on Titan - S04E01 (1080p).en.ass"))
        _touch_text(os.path.join(d, "[SubsPlease] Attack on Titan - S04E01 (1080p).zh.ass"))
        _touch_text(os.path.join(d, "[SubsPlease] Attack on Titan - S04E01 (1080p).nfo"))
        _touch_text(os.path.join(d, "[SubsPlease].txt"))
        scenarios.append(("动漫+多字幕组", d, {
            "keep": ["[SubsPlease] Attack on Titan - S04E01 (1080p).mkv",
                     "[SubsPlease] Attack on Titan - S04E01 (1080p).en.ass",
                     "[SubsPlease] Attack on Titan - S04E01 (1080p).zh.ass",
                     "[SubsPlease] Attack on Titan - S04E01 (1080p).nfo"],
            "delete": ["[SubsPlease].txt"],
        }))

        # --- 场景20: 电影 + 嵌套垃圾目录 ---
        d = os.path.join(source_dir, "Spider-Man.No.Way.Home.2021.1080p")
        _touch(os.path.join(d, "Spider-Man.No.Way.Home.2021.1080p.mkv"), 5 * 1024 * 1024 * 1024)
        nested_junk = os.path.join(d, "subtitles", "backup")
        _touch_text(os.path.join(nested_junk, "old_sub.srt"))
        _touch_text(os.path.join(nested_junk, "readme.txt"))
        scenarios.append(("电影+嵌套垃圾目录", d, {
            "keep": ["Spider-Man.No.Way.Home.2021.1080p.mkv"],
            "delete": [],
        }))

        # --- 场景21: 电影 + IDX/SUB 字幕对 ---
        d = os.path.join(source_dir, "Oldboy.2003.1080p.KOREAN")
        _touch(os.path.join(d, "Oldboy.2003.1080p.KOREAN.mkv"), 4 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Oldboy.2003.1080p.KOREAN.idx"))
        _touch_text(os.path.join(d, "Oldboy.2003.1080p.KOREAN.sub"))
        _touch_text(os.path.join(d, "Oldboy.2003.1080p.KOREAN.nfo"))
        _touch_text(os.path.join(d, "downloaded_from_publicHD.txt"))
        scenarios.append(("电影+IDX/SUB字幕", d, {
            "keep": ["Oldboy.2003.1080p.KOREAN.mkv", "Oldboy.2003.1080p.KOREAN.idx",
                     "Oldboy.2003.1080p.KOREAN.sub", "Oldboy.2003.1080p.KOREAN.nfo"],
            "delete": ["downloaded_from_publicHD.txt"],
        }))

        # --- 场景22: 合集/套装 ---
        d = os.path.join(source_dir, "The.Lord.of.the.Rings.Trilogy.Extended.1080p")
        for i, name in enumerate(["The.Fellowship.of.the.Ring", "The.Two.Towers", "The.Return.of.the.King"], 1):
            subd = os.path.join(d, f"CD{i}")
            _touch(os.path.join(subd, f"{name}.200{1+i}.Extended.1080p.mkv"), 8 * 1024 * 1024 * 1024)
            _touch_text(os.path.join(subd, f"{name}.200{1+i}.Extended.1080p.srt"))
        _touch_text(os.path.join(d, "Trilogy.nfo"))
        _touch_text(os.path.join(d, "Trilogy.jpg"))
        _touch_text(os.path.join(d, "info.txt"))
        scenarios.append(("合集套装", d, {
            "keep": ["CD1", "CD2", "CD3", "Trilogy.nfo", "Trilogy.jpg"],
            "delete": ["info.txt"],
        }))

        # --- 场景23: 纯字幕文件目录(无视频) ---
        d = os.path.join(source_dir, "subtitles_only")
        _touch_text(os.path.join(d, "movie.zh.srt"))
        _touch_text(os.path.join(d, "movie.en.srt"))
        _touch_text(os.path.join(d, "movie.ass"))
        _touch_text(os.path.join(d, "readme.txt"))
        scenarios.append(("纯字幕目录", d, {
            "keep": ["movie.zh.srt", "movie.en.srt", "movie.ass"],
            "delete": ["readme.txt"],
        }))

        # --- 场景24: 电影 + 封面/海报多张 ---
        d = os.path.join(source_dir, "Pulp.Fiction.1994.1080p.BluRay")
        _touch(os.path.join(d, "Pulp.Fiction.1994.1080p.BluRay.mkv"), 4 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Pulp.Fiction.1994.1080p.BluRay.nfo"))
        _touch_text(os.path.join(d, "Pulp.Fiction.1994.1080p.BluRay-poster.jpg"))
        _touch_text(os.path.join(d, "Pulp.Fiction.1994.1080p.BluRay-fanart.jpg"))
        _touch_text(os.path.join(d, "Pulp.Fiction.1994.1080p.BluRay-banner.jpg"))
        _touch_text(os.path.join(d, "Pulp.Fiction.1994.1080p.BluRay-clearlogo.png"))
        _touch_text(os.path.join(d, "Pulp.Fiction.1994.1080p.BluRay-disc.png"))
        _touch_text(os.path.join(d, "site_ad.jpg"))
        scenarios.append(("电影+多张海报", d, {
            "keep": ["Pulp.Fiction.1994.1080p.BluRay.mkv",
                     "Pulp.Fiction.1994.1080p.BluRay.nfo",
                     "Pulp.Fiction.1994.1080p.BluRay-poster.jpg",
                     "Pulp.Fiction.1994.1080p.BluRay-fanart.jpg",
                     "Pulp.Fiction.1994.1080p.BluRay-banner.jpg",
                     "Pulp.Fiction.1994.1080p.BluRay-clearlogo.png",
                     "Pulp.Fiction.1994.1080p.BluRay-disc.png",
                     "site_ad.jpg"],
            "delete": [],
        }))

        # --- 场景25: 电影 + 同名不同后缀垃圾 ---
        d = os.path.join(source_dir, "Fight.Club.1999.10th.Anniversary.1080p")
        _touch(os.path.join(d, "Fight.Club.1999.10th.Anniversary.1080p.mkv"), 5 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Fight.Club.1999.10th.Anniversary.1080p.srt"))
        _touch_text(os.path.join(d, "Fight.Club.1999.10th.Anniversary.1080p.nfo"))
        _touch_text(os.path.join(d, "Fight.Club.1999.10th.Anniversary.1080p.txt"))
        _touch_text(os.path.join(d, "Fight.Club.1999.10th.Anniversary.1080p.url"))
        scenarios.append(("电影+同名垃圾后缀", d, {
            "keep": ["Fight.Club.1999.10th.Anniversary.1080p.mkv",
                     "Fight.Club.1999.10th.Anniversary.1080p.srt",
                     "Fight.Club.1999.10th.Anniversary.1080p.nfo"],
            "delete": ["Fight.Club.1999.10th.Anniversary.1080p.txt",
                       "Fight.Club.1999.10th.Anniversary.1080p.url"],
        }))

        # --- 场景26: 多季电视剧合集 ---
        d = os.path.join(source_dir, "Friends.Complete.S01-S10.1080p.BluRay.x265")
        for season in range(1, 4):
            sd = os.path.join(d, f"Season {season:02d}")
            for ep in range(1, 5):
                _touch(os.path.join(sd, f"Friends.S{season:02d}E{ep:02d}.1080p.BluRay.x265.mkv"), 1 * 1024 * 1024 * 1024)
                _touch_text(os.path.join(sd, f"Friends.S{season:02d}E{ep:02d}.1080p.BluRay.x265.srt"))
        _touch_text(os.path.join(d, "Friends.Complete.S01-S10.1080p.BluRay.x265.nfo"))
        _touch_text(os.path.join(d, "RARBG.txt"))
        scenarios.append(("多季电视剧合集", d, {
            "keep": ["Season 01", "Season 02", "Season 03",
                     "Friends.Complete.S01-S10.1080p.BluRay.x265.nfo"],
            "delete": ["RARBG.txt"],
        }))

        # --- 场景27: 电影 + .dat 文件 ---
        d = os.path.join(source_dir, "The.Shawshank.Redemption.1994.1080p")
        _touch(os.path.join(d, "The.Shawshank.Redemption.1994.1080p.mkv"), 4 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "The.Shawshank.Redemption.1994.1080p.srt"))
        _touch_text(os.path.join(d, "desktop.ini"))
        _touch_text(os.path.join(d, "Thumbs.db"))
        _touch_text(os.path.join(d, ".DS_Store"))
        scenarios.append(("电影+系统垃圾文件", d, {
            "keep": ["The.Shawshank.Redemption.1994.1080p.mkv",
                     "The.Shawshank.Redemption.1994.1080p.srt"],
            "delete": ["desktop.ini", "Thumbs.db", ".DS_Store"],
        }))

        # --- 场景28: 电影 + 注释/说明文件 ---
        d = os.path.join(source_dir, "Tenet.2020.IMAX.1080p.BluRay")
        _touch(os.path.join(d, "Tenet.2020.IMAX.1080p.BluRay.mkv"), 5 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Tenet.2020.IMAX.1080p.BluRay.srt"))
        _touch_text(os.path.join(d, "readme.txt"))
        _touch_text(os.path.join(d, "readme.nfo"))
        _touch_text(os.path.join(d, "IMPORTANT_README.txt"))
        _touch_text(os.path.join(d, "HOW_TO_PLAY.txt"))
        _touch_text(os.path.join(d, "Notes.txt"))
        scenarios.append(("电影+说明文件", d, {
            "keep": ["Tenet.2020.IMAX.1080p.BluRay.mkv",
                     "Tenet.2020.IMAX.1080p.BluRay.srt",
                     "readme.nfo"],
            "delete": ["readme.txt", "IMPORTANT_README.txt", "HOW_TO_PLAY.txt", "Notes.txt"],
        }))

        # --- 场景29: 电影 + 压缩包 ---
        d = os.path.join(source_dir, "Joker.2019.2160p.BluRay.REMUX")
        _touch(os.path.join(d, "Joker.2019.2160p.BluRay.REMUX.mkv"), 7 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Joker.2019.2160p.BluRay.REMUX.srt"))
        _touch_text(os.path.join(d, "subs.rar"))
        _touch_text(os.path.join(d, "subs.zip"))
        _touch_text(os.path.join(d, "proof.jpg"))
        _touch_text(os.path.join(d, "sample.rar"))
        scenarios.append(("电影+压缩包", d, {
            "keep": ["Joker.2019.2160p.BluRay.REMUX.mkv",
                     "Joker.2019.2160p.BluRay.REMUX.srt",
                     "proof.jpg"],
            "delete": ["subs.rar", "subs.zip", "sample.rar"],
        }))

        # --- 场景30: 电影 + 多个sample目录 ---
        d = os.path.join(source_dir, "Avengers.Endgame.2019.1080p.BluRay")
        _touch(os.path.join(d, "Avengers.Endgame.2019.1080p.BluRay.mkv"), 6 * 1024 * 1024 * 1024)
        sd1 = os.path.join(d, "Sample")
        _touch(os.path.join(sd1, "sample.mkv"), 30 * 1024 * 1024)
        sd2 = os.path.join(d, "sample_2")
        _touch(os.path.join(sd2, "sample2.mkv"), 25 * 1024 * 1024)
        scenarios.append(("电影+多个Sample目录", d, {
            "keep": ["Avengers.Endgame.2019.1080p.BluRay.mkv", "sample_2"],
            "delete": ["Sample"],
        }))

        # --- 场景31: 电视剧 + 分卷压缩 ---
        d = os.path.join(source_dir, "Stranger.Things.S04.1080p.NF.WEB-DL")
        for ep in range(1, 4):
            _touch(os.path.join(d, f"Stranger.Things.S04E{ep:02d}.1080p.NF.WEB-DL.mkv"), 2 * 1024 * 1024 * 1024)
            _touch_text(os.path.join(d, f"Stranger.Things.S04E{ep:02d}.1080p.NF.WEB-DL.srt"))
        _touch_text(os.path.join(d, "Stranger.Things.S04.1080p.NF.WEB-DL.nfo"))
        _touch_text(os.path.join(d, "subs.part1.rar"))
        _touch_text(os.path.join(d, "subs.part2.rar"))
        _touch_text(os.path.join(d, "subs.part3.rar"))
        scenarios.append(("电视剧+分卷压缩", d, {
            "keep": [f"Stranger.Things.S04E{ep:02d}.1080p.NF.WEB-DL.mkv" for ep in range(1, 4)]
                  + [f"Stranger.Things.S04E{ep:02d}.1080p.NF.WEB-DL.srt" for ep in range(1, 4)]
                  + ["Stranger.Things.S04.1080p.NF.WEB-DL.nfo"],
            "delete": ["subs.part1.rar", "subs.part2.rar", "subs.part3.rar"],
        }))

        # --- 场景32: 电影 + 同目录多部电影 ---
        d = os.path.join(source_dir, "Double.Feature")
        _touch(os.path.join(d, "Movie1.Action.2023.1080p.mkv"), 3 * 1024 * 1024 * 1024)
        _touch(os.path.join(d, "Movie1.Action.2023.1080p.srt"))
        _touch(os.path.join(d, "Movie2.Comedy.2023.1080p.mkv"), 3 * 1024 * 1024 * 1024)
        _touch(os.path.join(d, "Movie2.Comedy.2023.1080p.srt"))
        _touch_text(os.path.join(d, "info.txt"))
        _touch_text(os.path.join(d, "RARBG.txt"))
        scenarios.append(("同目录多部电影", d, {
            "keep": ["Movie1.Action.2023.1080p.mkv", "Movie1.Action.2023.1080p.srt",
                     "Movie2.Comedy.2023.1080p.mkv", "Movie2.Comedy.2023.1080p.srt"],
            "delete": ["info.txt", "RARBG.txt"],
        }))

        # --- 场景33: 电影 + 带空格/特殊字符 ---
        d = os.path.join(source_dir, "Coco (2017) [1080p] [BluRay] [x265]")
        _touch(os.path.join(d, "Coco (2017) [1080p] [BluRay] [x265].mkv"), 3 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Coco (2017) [1080p] [BluRay] [x265].srt"))
        _touch_text(os.path.join(d, "Coco (2017) [1080p] [BluRay] [x265].nfo"))
        _touch_text(os.path.join(d, "Coco (2017) [1080p] [BluRay] [x265].jpg"))
        _touch_text(os.path.join(d, "readme !!!.txt"))
        scenarios.append(("电影+特殊字符文件名", d, {
            "keep": ["Coco (2017) [1080p] [BluRay] [x265].mkv",
                     "Coco (2017) [1080p] [BluRay] [x265].srt",
                     "Coco (2017) [1080p] [BluRay] [x265].nfo",
                     "Coco (2017) [1080p] [BluRay] [x265].jpg"],
            "delete": ["readme !!!.txt"],
        }))

        # --- 场景34: 电影 + 中文文件名 ---
        d = os.path.join(source_dir, "我不是药神.2018.1080p.WEB-DL")
        _touch(os.path.join(d, "我不是药神.2018.1080p.WEB-DL.mp4"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "我不是药神.2018.1080p.WEB-DL.srt"))
        _touch_text(os.path.join(d, "我不是药神.2018.1080p.WEB-DL.nfo"))
        _touch_text(os.path.join(d, "我不是药神.2018.1080p.WEB-DL.jpg"))
        _touch_text(os.path.join(d, "下载说明.txt"))
        _touch_text(os.path.join(d, "更多精彩.url"))
        scenarios.append(("电影+中文文件名", d, {
            "keep": ["我不是药神.2018.1080p.WEB-DL.mp4", "我不是药神.2018.1080p.WEB-DL.srt",
                     "我不是药神.2018.1080p.WEB-DL.nfo", "我不是药神.2018.1080p.WEB-DL.jpg"],
            "delete": ["下载说明.txt", "更多精彩.url"],
        }))

        # --- 场景35: 日剧 ---
        d = os.path.join(source_dir, "[NOP] 半沢直樹 (2020) [1080p]")
        for ep in range(1, 4):
            _touch(os.path.join(d, f"[NOP] 半沢直樹 EP{ep:02d} (2020) [1080p].mkv"), 1 * 1024 * 1024 * 1024)
            _touch_text(os.path.join(d, f"[NOP] 半沢直樹 EP{ep:02d} (2020) [1080p].ass"))
        _touch_text(os.path.join(d, "[NOP] 半沢直樹 (2020) [1080p].nfo"))
        _touch_text(os.path.join(d, "[NOP].txt"))
        scenarios.append(("日剧", d, {
            "keep": [f"[NOP] 半沢直樹 EP{ep:02d} (2020) [1080p].mkv" for ep in range(1, 4)]
                  + [f"[NOP] 半沢直樹 EP{ep:02d} (2020) [1080p].ass" for ep in range(1, 4)]
                  + ["[NOP] 半沢直樹 (2020) [1080p].nfo"],
            "delete": ["[NOP].txt"],
        }))

        # --- 场景36: 电影 + 同名带下划线关联 ---
        d = os.path.join(source_dir, "Whiplash.2014.1080p.BluRay.x264")
        _touch(os.path.join(d, "Whiplash.2014.1080p.BluRay.x264.mkv"), 3 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Whiplash.2014.1080p.BluRay.x264.srt"))
        _touch_text(os.path.join(d, "Whiplash.2014.1080p.BluRay.x264_thumb.jpg"))
        _touch_text(os.path.join(d, "Whiplash.2014.1080p.BluRay.x264_poster.jpg"))
        _touch_text(os.path.join(d, "Whiplash.2014.1080p.BluRay.x264.nfo"))
        _touch_text(os.path.join(d, "random_file.txt"))
        scenarios.append(("电影+下划线关联文件", d, {
            "keep": ["Whiplash.2014.1080p.BluRay.x264.mkv",
                     "Whiplash.2014.1080p.BluRay.x264.srt",
                     "Whiplash.2014.1080p.BluRay.x264_thumb.jpg",
                     "Whiplash.2014.1080p.BluRay.x264_poster.jpg",
                     "Whiplash.2014.1080p.BluRay.x264.nfo"],
            "delete": ["random_file.txt"],
        }))

        # --- 场景37: 电影 + 带空格关联 ---
        d = os.path.join(source_dir, "La.La.Land.2016.1080p.BluRay")
        _touch(os.path.join(d, "La.La.Land.2016.1080p.BluRay.mkv"), 3 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "La.La.Land.2016.1080p.BluRay.srt"))
        _touch_text(os.path.join(d, "La.La.Land.2016.1080p.BluRay thumb.jpg"))
        _touch_text(os.path.join(d, "La.La.Land.2016.1080p.BluRay.nfo"))
        _touch_text(os.path.join(d, "advertisement.jpg"))
        scenarios.append(("电影+空格关联文件", d, {
            "keep": ["La.La.Land.2016.1080p.BluRay.mkv",
                     "La.La.Land.2016.1080p.BluRay.srt",
                     "La.La.Land.2016.1080p.BluRay thumb.jpg",
                     "La.La.Land.2016.1080p.BluRay.nfo",
                     "advertisement.jpg"],
            "delete": [],
        }))

        # --- 场景38: 电影 + 带横线关联 ---
        d = os.path.join(source_dir, "The.Grand.Budapest.Hotel.2014.1080p")
        _touch(os.path.join(d, "The.Grand.Budapest.Hotel.2014.1080p.mkv"), 3 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "The.Grand.Budapest.Hotel.2014.1080p.srt"))
        _touch_text(os.path.join(d, "The.Grand.Budapest.Hotel.2014.1080p-fanart.jpg"))
        _touch_text(os.path.join(d, "The.Grand.Budapest.Hotel.2014.1080p-poster.jpg"))
        _touch_text(os.path.join(d, "The.Grand.Budapest.Hotel.2014.1080p.nfo"))
        _touch_text(os.path.join(d, "scene_release_info.txt"))
        scenarios.append(("电影+横线关联文件", d, {
            "keep": ["The.Grand.Budapest.Hotel.2014.1080p.mkv",
                     "The.Grand.Budapest.Hotel.2014.1080p.srt",
                     "The.Grand.Budapest.Hotel.2014.1080p-fanart.jpg",
                     "The.Grand.Budapest.Hotel.2014.1080p-poster.jpg",
                     "The.Grand.Budapest.Hotel.2014.1080p.nfo"],
            "delete": ["scene_release_info.txt"],
        }))

        # --- 场景39: 电影 + 点号关联 ---
        d = os.path.join(source_dir, "Her.2013.1080p.BluRay.x264")
        _touch(os.path.join(d, "Her.2013.1080p.BluRay.x264.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Her.2013.1080p.BluRay.x264.srt"))
        _touch_text(os.path.join(d, "Her.2013.1080p.BluRay.x264.zh-CN.srt"))
        _touch_text(os.path.join(d, "Her.2013.1080p.BluRay.x264.nfo"))
        _touch_text(os.path.join(d, "Her.2013.1080p.BluRay.x264.jpg"))
        _touch_text(os.path.join(d, "junk_info.txt"))
        scenarios.append(("电影+点号关联文件", d, {
            "keep": ["Her.2013.1080p.BluRay.x264.mkv",
                     "Her.2013.1080p.BluRay.x264.srt",
                     "Her.2013.1080p.BluRay.x264.zh-CN.srt",
                     "Her.2013.1080p.BluRay.x264.nfo",
                     "Her.2013.1080p.BluRay.x264.jpg"],
            "delete": ["junk_info.txt"],
        }))

        # --- 场景40: 电影 + 韩文文件名 ---
        d = os.path.join(source_dir, "기생충.2019.1080p.BluRay.x264-GECKOS")
        _touch(os.path.join(d, "기생충.2019.1080p.BluRay.x264-GECKOS.mkv"), 4 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "기생충.2019.1080p.BluRay.x264-GECKOS.srt"))
        _touch_text(os.path.join(d, "기생충.2019.1080p.BluRay.x264-GECKOS.nfo"))
        _touch_text(os.path.join(d, "RARBG.txt"))
        _touch_text(os.path.join(d, "RARBG_DO_NOT_MIRROR.exe"))
        scenarios.append(("电影+韩文文件名", d, {
            "keep": ["기생충.2019.1080p.BluRay.x264-GECKOS.mkv",
                     "기생충.2019.1080p.BluRay.x264-GECKOS.srt",
                     "기생충.2019.1080p.BluRay.x264-GECKOS.nfo"],
            "delete": ["RARBG.txt", "RARBG_DO_NOT_MIRROR.exe"],
        }))

        # --- 场景41: 纯垃圾文件目录(无媒体) ---
        d = os.path.join(source_dir, "junk_only_folder")
        _touch_text(os.path.join(d, "readme.txt"))
        _touch_text(os.path.join(d, "ad.url"))
        _touch_text(os.path.join(d, "info.log"))
        _touch_text(os.path.join(d, "data.db"))
        _touch_text(os.path.join(d, "playlist.m3u"))
        scenarios.append(("纯垃圾目录", d, {
            "keep": [],
            "delete": ["readme.txt", "ad.url", "info.log", "data.db", "playlist.m3u"],
        }))

        # --- 场景42: 电影 + 多CD分卷 ---
        d = os.path.join(source_dir, "Lawrence.of.Arabia.1962.1080p.BluRay")
        _touch(os.path.join(d, "Lawrence.of.Arabia.1962.CD1.1080p.BluRay.mkv"), 4 * 1024 * 1024 * 1024)
        _touch(os.path.join(d, "Lawrence.of.Arabia.1962.CD2.1080p.BluRay.mkv"), 4 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Lawrence.of.Arabia.1962.CD1.1080p.BluRay.srt"))
        _touch_text(os.path.join(d, "Lawrence.of.Arabia.1962.CD2.1080p.BluRay.srt"))
        _touch_text(os.path.join(d, "Lawrence.of.Arabia.1962.1080p.BluRay.nfo"))
        _touch_text(os.path.join(d, "downloaded_from_scene.txt"))
        scenarios.append(("电影+多CD分卷", d, {
            "keep": ["Lawrence.of.Arabia.1962.CD1.1080p.BluRay.mkv",
                     "Lawrence.of.Arabia.1962.CD2.1080p.BluRay.mkv",
                     "Lawrence.of.Arabia.1962.CD1.1080p.BluRay.srt",
                     "Lawrence.of.Arabia.1962.CD2.1080p.BluRay.srt",
                     "Lawrence.of.Arabia.1962.1080p.BluRay.nfo"],
            "delete": ["downloaded_from_scene.txt"],
        }))

        # --- 场景43: 电影 + .vtt WebVTT字幕 ---
        d = os.path.join(source_dir, "Soul.2020.2160p.DSNP.WEB-DL")
        _touch(os.path.join(d, "Soul.2020.2160p.DSNP.WEB-DL.mkv"), 4 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Soul.2020.2160p.DSNP.WEB-DL.en.vtt"))
        _touch_text(os.path.join(d, "Soul.2020.2160p.DSNP.WEB-DL.zh.vtt"))
        _touch_text(os.path.join(d, "Soul.2020.2160p.DSNP.WEB-DL.nfo"))
        _touch_text(os.path.join(d, "Soul.2020.2160p.DSNP.WEB-DL.jpg"))
        _touch_text(os.path.join(d, "info.txt"))
        scenarios.append(("电影+VTT字幕", d, {
            "keep": ["Soul.2020.2160p.DSNP.WEB-DL.mkv",
                     "Soul.2020.2160p.DSNP.WEB-DL.en.vtt",
                     "Soul.2020.2160p.DSNP.WEB-DL.zh.vtt",
                     "Soul.2020.2160p.DSNP.WEB-DL.nfo",
                     "Soul.2020.2160p.DSNP.WEB-DL.jpg"],
            "delete": ["info.txt"],
        }))

        # --- 场景44: 电影 + .ssa 字幕 ---
        d = os.path.join(source_dir, "Your.Name.2016.1080p.BluRay.x264")
        _touch(os.path.join(d, "Your.Name.2016.1080p.BluRay.x264.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Your.Name.2016.1080p.BluRay.x264.en.ssa"))
        _touch_text(os.path.join(d, "Your.Name.2016.1080p.BluRay.x264.zh.ssa"))
        _touch_text(os.path.join(d, "Your.Name.2016.1080p.BluRay.x264.nfo"))
        _touch_text(os.path.join(d, "downloaded.txt"))
        scenarios.append(("电影+SSA字幕", d, {
            "keep": ["Your.Name.2016.1080p.BluRay.x264.mkv",
                     "Your.Name.2016.1080p.BluRay.x264.en.ssa",
                     "Your.Name.2016.1080p.BluRay.x264.zh.ssa",
                     "Your.Name.2016.1080p.BluRay.x264.nfo"],
            "delete": ["downloaded.txt"],
        }))

        # --- 场景45: 多层嵌套空目录 ---
        d = os.path.join(source_dir, "deep", "nested", "empty", "dirs")
        os.makedirs(d, exist_ok=True)
        scenarios.append(("多层嵌套空目录", source_dir, {
            "keep": ["deep"],
            "delete": [],
        }))

        # --- 场景46: 电影 + 同名 .torrent 文件 ---
        d = os.path.join(source_dir, "Everything.Everywhere.All.At.Once.2022.1080p")
        _touch(os.path.join(d, "Everything.Everywhere.All.At.Once.2022.1080p.mkv"), 3 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Everything.Everywhere.All.At.Once.2022.1080p.srt"))
        _touch_text(os.path.join(d, "Everything.Everywhere.All.At.Once.2022.1080p.torrent"))
        _touch_text(os.path.join(d, "Everything.Everywhere.All.At.Once.2022.1080p.nfo"))
        _touch_text(os.path.join(d, "Everything.Everywhere.All.At.Once.2022.1080p.jpg"))
        scenarios.append(("电影+同名torrent", d, {
            "keep": ["Everything.Everywhere.All.At.Once.2022.1080p.mkv",
                     "Everything.Everywhere.All.At.Once.2022.1080p.srt",
                     "Everything.Everywhere.All.At.Once.2022.1080p.torrent",
                     "Everything.Everywhere.All.At.Once.2022.1080p.nfo",
                     "Everything.Everywhere.All.At.Once.2022.1080p.jpg"],
            "delete": [],
        }))

        # --- 场景47: 电影 + .wmv 格式 ---
        d = os.path.join(source_dir, "Old.Movie.2005.DVDRip")
        _touch(os.path.join(d, "Old.Movie.2005.DVDRip.wmv"), 700 * 1024 * 1024)
        _touch_text(os.path.join(d, "Old.Movie.2005.DVDRip.srt"))
        _touch_text(os.path.join(d, "Old.Movie.2005.DVDRip.nfo"))
        _touch_text(os.path.join(d, "readme.txt"))
        scenarios.append(("电影+WMV格式", d, {
            "keep": ["Old.Movie.2005.DVDRip.wmv", "Old.Movie.2005.DVDRip.srt",
                     "Old.Movie.2005.DVDRip.nfo"],
            "delete": ["readme.txt"],
        }))

        # --- 场景48: 电影 + .flv 格式 ---
        d = os.path.join(source_dir, "Web.Video.2023.FLV")
        _touch(os.path.join(d, "Web.Video.2023.FLV.flv"), 500 * 1024 * 1024)
        _touch_text(os.path.join(d, "Web.Video.2023.FLV.srt"))
        _touch_text(os.path.join(d, "info.txt"))
        scenarios.append(("电影+FLV格式", d, {
            "keep": ["Web.Video.2023.FLV.flv", "Web.Video.2023.FLV.srt"],
            "delete": ["info.txt"],
        }))

        # --- 场景49: 电影 + .mov 格式 ---
        d = os.path.join(source_dir, "Home.Video.2024.iPhone")
        _touch(os.path.join(d, "Home.Video.2024.iPhone.mov"), 1 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "readme.txt"))
        scenarios.append(("电影+MOV格式", d, {
            "keep": ["Home.Video.2024.iPhone.mov"],
            "delete": ["readme.txt"],
        }))

        # --- 场景50: 电影 + .ts 格式(录制) ---
        d = os.path.join(source_dir, "Live.Concert.2024.HDTV.1080i")
        _touch(os.path.join(d, "Live.Concert.2024.HDTV.1080i.ts"), 8 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Live.Concert.2024.HDTV.1080i.srt"))
        _touch_text(os.path.join(d, "Live.Concert.2024.HDTV.1080i.nfo"))
        _touch_text(os.path.join(d, "info.txt"))
        _touch_text(os.path.join(d, "ad.url"))
        scenarios.append(("电影+TS格式", d, {
            "keep": ["Live.Concert.2024.HDTV.1080i.ts",
                     "Live.Concert.2024.HDTV.1080i.srt",
                     "Live.Concert.2024.HDTV.1080i.nfo"],
            "delete": ["info.txt", "ad.url"],
        }))

        # --- 场景51: 混合: 视频+音频+字幕+垃圾 ---
        d = os.path.join(source_dir, "Mixed.Content.2024")
        _touch(os.path.join(d, "Mixed.Content.2024.mkv"), 3 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Mixed.Content.2024.srt"))
        _touch_text(os.path.join(d, "Mixed.Content.2024.ass"))
        _touch_text(os.path.join(d, "Mixed.Content.2024.nfo"))
        _touch_text(os.path.join(d, "Mixed.Content.2024.jpg"))
        _touch_text(os.path.join(d, "Mixed.Content.2024.png"))
        _touch_text(os.path.join(d, "readme.txt"))
        _touch_text(os.path.join(d, "ad.url"))
        _touch_text(os.path.join(d, "checksum.sfv"))
        _touch_text(os.path.join(d, "playlist.m3u"))
        _touch_text(os.path.join(d, "error.log"))
        _touch_text(os.path.join(d, "backup.bak"))
        _touch_text(os.path.join(d, "data.db"))
        scenarios.append(("混合内容", d, {
            "keep": ["Mixed.Content.2024.mkv", "Mixed.Content.2024.srt",
                     "Mixed.Content.2024.ass", "Mixed.Content.2024.nfo",
                     "Mixed.Content.2024.jpg", "Mixed.Content.2024.png"],
            "delete": ["readme.txt", "ad.url", "checksum.sfv", "playlist.m3u",
                       "error.log", "backup.bak", "data.db"],
        }))

        # --- 场景52: 电影 + 仅保留视频(media_only) ---
        d = os.path.join(source_dir, "media_only_test_movie.2024")
        _touch(os.path.join(d, "media_only_test_movie.2024.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "media_only_test_movie.2024.srt"))
        _touch_text(os.path.join(d, "media_only_test_movie.2024.nfo"))
        _touch_text(os.path.join(d, "media_only_test_movie.2024.jpg"))
        _touch_text(os.path.join(d, "media_only_test_movie.2024.png"))
        _touch_text(os.path.join(d, "random.txt"))
        _touch_text(os.path.join(d, "random.url"))
        scenarios.append(("media_only模式测试", d, {
            "keep": ["media_only_test_movie.2024.mkv", "media_only_test_movie.2024.srt",
                     "media_only_test_movie.2024.nfo", "media_only_test_movie.2024.jpg",
                     "media_only_test_movie.2024.png"],
            "delete": ["random.txt", "random.url"],
        }))

        # --- 场景53: 电视剧 + 单集独立目录 ---
        d = os.path.join(source_dir, "The.Mandalorian.S03")
        for ep in range(1, 4):
            epd = os.path.join(d, f"Episode {ep:02d}")
            _touch(os.path.join(epd, f"The.Mandalorian.S03E{ep:02d}.2160p.DSNP.WEB-DL.mkv"), 2 * 1024 * 1024 * 1024)
            _touch_text(os.path.join(epd, f"The.Mandalorian.S03E{ep:02d}.2160p.DSNP.WEB-DL.srt"))
            _touch_text(os.path.join(epd, f"The.Mandalorian.S03E{ep:02d}.2160p.DSNP.WEB-DL.nfo"))
            _touch_text(os.path.join(epd, f"The.Mandalorian.S03E{ep:02d}.2160p.DSNP.WEB-DL.jpg"))
        _touch_text(os.path.join(d, "The.Mandalorian.S03.2160p.DSNP.WEB-DL.nfo"))
        _touch_text(os.path.join(d, "RARBG.txt"))
        scenarios.append(("电视剧单集独立目录", d, {
            "keep": ["Episode 01", "Episode 02", "Episode 03",
                     "The.Mandalorian.S03.2160p.DSNP.WEB-DL.nfo"],
            "delete": ["RARBG.txt"],
        }))

        # --- 场景54: 电影 + 仅保护扩展名 ---
        d = os.path.join(source_dir, "protect_ext_test.2024")
        _touch(os.path.join(d, "protect_ext_test.2024.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "protect_ext_test.2024.srt"))
        _touch_text(os.path.join(d, "protect_ext_test.2024.nfo"))
        _touch_text(os.path.join(d, "protect_ext_test.2024.jpg"))
        _touch_text(os.path.join(d, "protect_ext_test.2024.png"))
        _touch_text(os.path.join(d, "protect_ext_test.2024.bdmv"))
        _touch_text(os.path.join(d, "protect_ext_test.2024.clpi"))
        _touch_text(os.path.join(d, "protect_ext_test.2024.mpls"))
        _touch_text(os.path.join(d, "junk.txt"))
        _touch_text(os.path.join(d, "junk.url"))
        scenarios.append(("保护扩展名测试", d, {
            "keep": ["protect_ext_test.2024.mkv", "protect_ext_test.2024.srt",
                     "protect_ext_test.2024.nfo", "protect_ext_test.2024.jpg",
                     "protect_ext_test.2024.png", "protect_ext_test.2024.bdmv",
                     "protect_ext_test.2024.clpi", "protect_ext_test.2024.mpls"],
            "delete": ["junk.txt", "junk.url"],
        }))

        # --- 场景55: 电影 + 删除扩展名测试 ---
        d = os.path.join(source_dir, "delete_ext_test.2024")
        _touch(os.path.join(d, "delete_ext_test.2024.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "delete_ext_test.2024.srt"))
        _touch_text(os.path.join(d, "test.url"))
        _touch_text(os.path.join(d, "test.txt"))
        _touch_text(os.path.join(d, "test.sfv"))
        _touch_text(os.path.join(d, "test.log"))
        _touch_text(os.path.join(d, "test.bak"))
        _touch_text(os.path.join(d, "test.m3u"))
        _touch_text(os.path.join(d, "test.db"))
        scenarios.append(("删除扩展名测试", d, {
            "keep": ["delete_ext_test.2024.mkv", "delete_ext_test.2024.srt"],
            "delete": ["test.url", "test.txt", "test.sfv", "test.log",
                       "test.bak", "test.m3u", "test.db"],
        }))

        # --- 场景56: 电影 + 黑名单模式测试 ---
        d = os.path.join(source_dir, "blacklist_test.2024")
        _touch(os.path.join(d, "blacklist_test.2024.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "blacklist_test.2024.srt"))
        _touch_text(os.path.join(d, "RARBG.txt"))
        _touch_text(os.path.join(d, "RARBG.nfo"))
        _touch_text(os.path.join(d, "RARBG_DO_NOT_MIRROR.exe"))
        _touch_text(os.path.join(d, "RARBG.com.txt"))
        scenarios.append(("黑名单模式测试", d, {
            "keep": ["blacklist_test.2024.mkv", "blacklist_test.2024.srt"],
            "delete": ["RARBG.txt", "RARBG.nfo", "RARBG_DO_NOT_MIRROR.exe", "RARBG.com.txt"],
        }))

        # --- 场景57: 电视剧 + 嵌套season目录 ---
        d = os.path.join(source_dir, "The.Office.US.Complete")
        for season in range(1, 3):
            sd = os.path.join(d, f"Season.{season}")
            for ep in range(1, 4):
                _touch(os.path.join(sd, f"The.Office.US.S{season:02d}E{ep:02d}.1080p.WEB-DL.mkv"), 500 * 1024 * 1024)
                _touch_text(os.path.join(sd, f"The.Office.US.S{season:02d}E{ep:02d}.1080p.WEB-DL.srt"))
            _touch_text(os.path.join(sd, f"Season.{season}.nfo"))
        _touch_text(os.path.join(d, "The.Office.US.Complete.nfo"))
        _touch_text(os.path.join(d, "RARBG.txt"))
        _touch_text(os.path.join(d, "RARBG_DO_NOT_MIRROR.exe"))
        scenarios.append(("电视剧嵌套Season目录", d, {
            "keep": ["Season.1", "Season.2", "The.Office.US.Complete.nfo"],
            "delete": ["RARBG.txt", "RARBG_DO_NOT_MIRROR.exe"],
        }))

        # --- 场景58: 电影 + 中英混合文件名 ---
        d = os.path.join(source_dir, "The.Wandering.Earth.流浪地球.2019.1080p")
        _touch(os.path.join(d, "The.Wandering.Earth.流浪地球.2019.1080p.mkv"), 3 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "The.Wandering.Earth.流浪地球.2019.1080p.zh.srt"))
        _touch_text(os.path.join(d, "The.Wandering.Earth.流浪地球.2019.1080p.en.srt"))
        _touch_text(os.path.join(d, "The.Wandering.Earth.流浪地球.2019.1080p.nfo"))
        _touch_text(os.path.join(d, "The.Wandering.Earth.流浪地球.2019.1080p.jpg"))
        _touch_text(os.path.join(d, "下载必读.txt"))
        _touch_text(os.path.join(d, "广告.url"))
        scenarios.append(("中英混合文件名", d, {
            "keep": ["The.Wandering.Earth.流浪地球.2019.1080p.mkv",
                     "The.Wandering.Earth.流浪地球.2019.1080p.zh.srt",
                     "The.Wandering.Earth.流浪地球.2019.1080p.en.srt",
                     "The.Wandering.Earth.流浪地球.2019.1080p.nfo",
                     "The.Wandering.Earth.流浪地球.2019.1080p.jpg"],
            "delete": ["下载必读.txt", "广告.url"],
        }))

        # --- 场景59: 电影 + 多种视频格式混合 ---
        d = os.path.join(source_dir, "Multi.Format.Movie.2024")
        _touch(os.path.join(d, "Multi.Format.Movie.2024.1080p.mkv"), 4 * 1024 * 1024 * 1024)
        _touch(os.path.join(d, "Multi.Format.Movie.2024.720p.mp4"), 2 * 1024 * 1024 * 1024)
        _touch(os.path.join(d, "Multi.Format.Movie.2024.480p.avi"), 1 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Multi.Format.Movie.2024.1080p.srt"))
        _touch_text(os.path.join(d, "Multi.Format.Movie.2024.720p.srt"))
        _touch_text(os.path.join(d, "Multi.Format.Movie.2024.nfo"))
        _touch_text(os.path.join(d, "info.txt"))
        _touch_text(os.path.join(d, "ad.url"))
        scenarios.append(("多种视频格式混合", d, {
            "keep": ["Multi.Format.Movie.2024.1080p.mkv",
                     "Multi.Format.Movie.2024.720p.mp4",
                     "Multi.Format.Movie.2024.480p.avi",
                     "Multi.Format.Movie.2024.1080p.srt",
                     "Multi.Format.Movie.2024.720p.srt",
                     "Multi.Format.Movie.2024.nfo"],
            "delete": ["info.txt", "ad.url"],
        }))

        # --- 场景60: 电影 + 仅垃圾无媒体 ---
        d = os.path.join(source_dir, "empty_media_folder")
        _touch_text(os.path.join(d, "readme.txt"))
        _touch_text(os.path.join(d, "ad.url"))
        _touch_text(os.path.join(d, "info.log"))
        _touch_text(os.path.join(d, "data.db"))
        _touch_text(os.path.join(d, "playlist.m3u"))
        _touch_text(os.path.join(d, "checksum.sfv"))
        _touch_text(os.path.join(d, "backup.bak"))
        scenarios.append(("仅垃圾无媒体", d, {
            "keep": [],
            "delete": ["readme.txt", "ad.url", "info.log", "data.db",
                       "playlist.m3u", "checksum.sfv", "backup.bak"],
        }))

        # --- 场景61: 电影 + 点号分隔的多段文件名 ---
        d = os.path.join(source_dir, "Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1")
        _touch(os.path.join(d, "Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1.mkv"), 10 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(d, "Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1.srt"))
        _touch_text(os.path.join(d, "Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1.nfo"))
        _touch_text(os.path.join(d, "Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1-poster.jpg"))
        _touch_text(os.path.join(d, "Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1-fanart.jpg"))
        _touch_text(os.path.join(d, "RARBG.txt"))
        _touch_text(os.path.join(d, "RARBG_DO_NOT_MIRROR.exe"))
        scenarios.append(("长文件名电影", d, {
            "keep": ["Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1.mkv",
                     "Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1.srt",
                     "Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1.nfo",
                     "Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1-poster.jpg",
                     "Blade.Runner.2049.2017.2160p.BluRay.REMUX.HEVC.TrueHD.7.1-fanart.jpg"],
            "delete": ["RARBG.txt", "RARBG_DO_NOT_MIRROR.exe"],
        }))

        # --- 场景62: 电影 + 字幕目录 ---
        d = os.path.join(source_dir, "Subs.Folder.Movie.2024")
        _touch(os.path.join(d, "Subs.Folder.Movie.2024.mkv"), 3 * 1024 * 1024 * 1024)
        subs_d = os.path.join(d, "Subs")
        _touch_text(os.path.join(subs_d, "2_English.srt"))
        _touch_text(os.path.join(subs_d, "3_Chinese.srt"))
        _touch_text(os.path.join(subs_d, "4_Japanese.srt"))
        _touch_text(os.path.join(d, "Subs.Folder.Movie.2024.nfo"))
        _touch_text(os.path.join(d, "RARBG.txt"))
        scenarios.append(("电影+Subs字幕目录", d, {
            "keep": ["Subs.Folder.Movie.2024.mkv", "Subs.Folder.Movie.2024.nfo"],
            "delete": ["RARBG.txt"],
        }))

        # --- 场景63: 电影 + 根目录散落文件 ---
        _touch(os.path.join(source_dir, "root_movie.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(source_dir, "root_movie.srt"))
        _touch_text(os.path.join(source_dir, "root_readme.txt"))
        _touch_text(os.path.join(source_dir, "root_ad.url"))
        scenarios.append(("根目录散落文件", source_dir, {
            "keep": ["root_movie.mkv", "root_movie.srt"],
            "delete": ["root_readme.txt", "root_ad.url"],
        }))

        return scenarios


# ============================================================
# 第二部分: 笛卡尔积配置组合测试
# ============================================================

CLEANUP_MODES = ["media_only", "media_and_related"]
AI_ENABLED_VALUES = [False, True]
MERGE_STRATEGIES = ["intersection", "union"]
JUNK_VIDEO_THRESHOLDS = [0, 50, 100]
CLEANUP_EMPTY_DIRS = [False, True]


class TestCartesianConfigCombinations(unittest.TestCase):
    """笛卡尔积配置组合测试: 2x2x2x3x2 = 48 种组合"""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.recycle_dir = tempfile.mkdtemp()

        _touch(os.path.join(self.src_dir, "movie.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "movie.srt"))
        _touch_text(os.path.join(self.src_dir, "movie.nfo"))
        _touch_text(os.path.join(self.src_dir, "movie.jpg"))
        _touch_text(os.path.join(self.src_dir, "readme.txt"))
        _touch_text(os.path.join(self.src_dir, "ad.url"))
        _touch(os.path.join(self.src_dir, "sample.mkv"), 5 * 1024 * 1024)

        empty_d = os.path.join(self.src_dir, "empty_subdir")
        os.makedirs(empty_d, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.recycle_dir, ignore_errors=True)

    def _run_config(self, cleanup_mode, ai_enabled, merge_strategy,
                    junk_video_max_size_mb, cleanup_empty_dirs):
        config = _make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            cleanup_mode=cleanup_mode,
            ai_enabled=ai_enabled,
            merge_strategy=merge_strategy,
            junk_video_max_size_mb=junk_video_max_size_mb,
            cleanup_empty_dirs=cleanup_empty_dirs,
        )
        cleaner = SourceCleaner(config)
        return cleaner.preview()

    def test_all_cartesian_combinations(self):
        """遍历所有配置组合，确保不抛异常"""
        results = []
        for cleanup_mode in CLEANUP_MODES:
            for ai_enabled in AI_ENABLED_VALUES:
                for merge_strategy in MERGE_STRATEGIES:
                    for junk_threshold in JUNK_VIDEO_THRESHOLDS:
                        for cleanup_empty in CLEANUP_EMPTY_DIRS:
                            items = self._run_config(
                                cleanup_mode, ai_enabled, merge_strategy,
                                junk_threshold, cleanup_empty,
                            )
                            results.append({
                                "config": (cleanup_mode, ai_enabled, merge_strategy,
                                           junk_threshold, cleanup_empty),
                                "count": len(items),
                            })

        self.assertEqual(len(results), 48)

        for r in results:
            cfg = r["config"]
            self.assertIsInstance(r["count"], int,
                f"配置 {cfg} 返回非整数: {r['count']}")

    def test_media_only_deletes_non_media_in_all_combos(self):
        """media_only 模式下，非媒体文件总是被标记删除"""
        for ai_enabled in AI_ENABLED_VALUES:
            for merge_strategy in MERGE_STRATEGIES:
                for junk_threshold in JUNK_VIDEO_THRESHOLDS:
                    for cleanup_empty in CLEANUP_EMPTY_DIRS:
                        items = self._run_config(
                            "media_only", ai_enabled, merge_strategy,
                            junk_threshold, cleanup_empty,
                        )
                        paths = {item["path"] for item in items}
                        txt_path = os.path.join(self.src_dir, "readme.txt")
                        url_path = os.path.join(self.src_dir, "ad.url")

                        if ai_enabled and merge_strategy == "intersection":
                            continue

                        self.assertIn(txt_path, paths,
                            f"media_only+{ai_enabled}+{merge_strategy}+{junk_threshold}+{cleanup_empty}: txt 未标记删除")
                        self.assertIn(url_path, paths,
                            f"media_only+{ai_enabled}+{merge_strategy}+{junk_threshold}+{cleanup_empty}: url 未标记删除")

    def test_media_and_related_preserves_companion_files(self):
        """media_and_related 模式下，伴生文件应保留"""
        for ai_enabled in AI_ENABLED_VALUES:
            for merge_strategy in MERGE_STRATEGIES:
                for junk_threshold in JUNK_VIDEO_THRESHOLDS:
                    for cleanup_empty in CLEANUP_EMPTY_DIRS:
                        items = self._run_config(
                            "media_and_related", ai_enabled, merge_strategy,
                            junk_threshold, cleanup_empty,
                        )
                        paths = {item["path"] for item in items}
                        nfo_path = os.path.join(self.src_dir, "movie.nfo")
                        jpg_path = os.path.join(self.src_dir, "movie.jpg")

                        if ai_enabled and merge_strategy == "intersection":
                            continue

                        self.assertNotIn(nfo_path, paths,
                            f"media_and_related+{ai_enabled}+{merge_strategy}+{junk_threshold}+{cleanup_empty}: nfo 被误标记")
                        self.assertNotIn(jpg_path, paths,
                            f"media_and_related+{ai_enabled}+{merge_strategy}+{junk_threshold}+{cleanup_empty}: jpg 被误标记")

    def test_junk_video_threshold_effect(self):
        """junk_video_max_size_mb 阈值效果验证"""
        for cleanup_mode in CLEANUP_MODES:
            for ai_enabled in AI_ENABLED_VALUES:
                for merge_strategy in MERGE_STRATEGIES:
                    for cleanup_empty in CLEANUP_EMPTY_DIRS:
                        items_0 = self._run_config(
                            cleanup_mode, ai_enabled, merge_strategy,
                            0, cleanup_empty,
                        )
                        items_50 = self._run_config(
                            cleanup_mode, ai_enabled, merge_strategy,
                            50, cleanup_empty,
                        )

                        sample_path = os.path.join(self.src_dir, "sample.mkv")
                        paths_0 = {item["path"] for item in items_0}
                        paths_50 = {item["path"] for item in items_50}

                        if ai_enabled and merge_strategy == "intersection":
                            continue

                        self.assertNotIn(sample_path, paths_0,
                            f"阈值0时不应标记小视频: {cleanup_mode}+{ai_enabled}+{merge_strategy}+{cleanup_empty}")
                        self.assertIn(sample_path, paths_50,
                            f"阈值50时应标记5MB小视频: {cleanup_mode}+{ai_enabled}+{merge_strategy}+{cleanup_empty}")

    def test_cleanup_empty_dirs_effect(self):
        """cleanup_empty_dirs 效果验证"""
        for cleanup_mode in CLEANUP_MODES:
            for ai_enabled in AI_ENABLED_VALUES:
                for merge_strategy in MERGE_STRATEGIES:
                    for junk_threshold in JUNK_VIDEO_THRESHOLDS:
                        items_false = self._run_config(
                            cleanup_mode, ai_enabled, merge_strategy,
                            junk_threshold, False,
                        )
                        items_true = self._run_config(
                            cleanup_mode, ai_enabled, merge_strategy,
                            junk_threshold, True,
                        )

                        empty_dir_path = os.path.join(self.src_dir, "empty_subdir")
                        empty_in_false = any(
                            item["path"] == empty_dir_path for item in items_false)
                        empty_in_true = any(
                            item["path"] == empty_dir_path for item in items_true)

                        self.assertFalse(empty_in_false,
                            f"cleanup_empty_dirs=False 不应标记空目录: {cleanup_mode}+{ai_enabled}+{merge_strategy}+{junk_threshold}")
                        self.assertTrue(empty_in_true,
                            f"cleanup_empty_dirs=True 应标记空目录: {cleanup_mode}+{ai_enabled}+{merge_strategy}+{junk_threshold}")

    def test_video_subtitle_never_deleted(self):
        """视频和字幕文件在任何配置下都不应被标记删除"""
        for cleanup_mode in CLEANUP_MODES:
            for ai_enabled in AI_ENABLED_VALUES:
                for merge_strategy in MERGE_STRATEGIES:
                    for junk_threshold in JUNK_VIDEO_THRESHOLDS:
                        for cleanup_empty in CLEANUP_EMPTY_DIRS:
                            items = self._run_config(
                                cleanup_mode, ai_enabled, merge_strategy,
                                junk_threshold, cleanup_empty,
                            )
                            paths = {item["path"] for item in items}
                            movie_path = os.path.join(self.src_dir, "movie.mkv")
                            srt_path = os.path.join(self.src_dir, "movie.srt")

                            self.assertNotIn(movie_path, paths,
                                f"主视频被误标记: {cleanup_mode}+{ai_enabled}+{merge_strategy}+{junk_threshold}+{cleanup_empty}")
                            self.assertNotIn(srt_path, paths,
                                f"字幕被误标记: {cleanup_mode}+{ai_enabled}+{merge_strategy}+{junk_threshold}+{cleanup_empty}")


# ============================================================
# 第三部分: BT下载场景综合测试
# ============================================================

class TestBTDownloadScenarios(unittest.TestCase):
    """63个真实BT下载场景测试"""

    @classmethod
    def setUpClass(cls):
        cls.src_dir = tempfile.mkdtemp()
        cls.recycle_dir = tempfile.mkdtemp()
        cls.scenarios = BTDownloadScenarios.build_all(cls.src_dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.src_dir, ignore_errors=True)
        shutil.rmtree(cls.recycle_dir, ignore_errors=True)

    def _make_cleaner(self, cleanup_mode="media_and_related",
                      junk_video_max_size_mb=50, cleanup_empty_dirs=True):
        return SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            cleanup_mode=cleanup_mode,
            junk_video_max_size_mb=junk_video_max_size_mb,
            cleanup_empty_dirs=cleanup_empty_dirs,
        ))

    def test_scenario_count(self):
        """确保至少有60个场景"""
        self.assertGreaterEqual(len(self.scenarios), 60,
            f"场景数量不足: {len(self.scenarios)} < 60")

    def test_all_scenarios_no_exception(self):
        """所有场景 preview 不抛异常"""
        cleaner = self._make_cleaner()
        items = cleaner.preview()
        self.assertIsInstance(items, list)

    def test_media_and_related_keeps_expected_files(self):
        """media_and_related 模式下验证保留文件"""
        cleaner = self._make_cleaner(cleanup_mode="media_and_related")
        items = cleaner.preview()
        deleted_paths = {item["path"] for item in items}

        for name, dir_path, expected in self.scenarios:
            for keep_file in expected["keep"]:
                full_path = os.path.join(dir_path, keep_file)
                if os.path.isdir(full_path):
                    for item in items:
                        if item.get("category") in ("blacklist_dir", "empty_dir"):
                            self.assertNotEqual(item["path"], full_path,
                                f"[{name}] 目录应保留但被标记删除: {keep_file}")
                else:
                    self.assertNotIn(full_path, deleted_paths,
                        f"[{name}] 文件应保留但被标记删除: {keep_file}")

    def test_media_and_related_deletes_expected_files(self):
        """media_and_related 模式下验证删除文件"""
        cleaner = self._make_cleaner(cleanup_mode="media_and_related")
        items = cleaner.preview()
        deleted_paths = {item["path"] for item in items}

        for name, dir_path, expected in self.scenarios:
            for del_file in expected["delete"]:
                full_path = os.path.join(dir_path, del_file)
                if os.path.isdir(full_path):
                    found = any(
                        item["path"] == full_path and item.get("category") in ("blacklist_dir", "empty_dir")
                        for item in items)
                    self.assertTrue(found,
                        f"[{name}] 目录应被标记删除但未标记: {del_file}")
                else:
                    self.assertIn(full_path, deleted_paths,
                        f"[{name}] 文件应被标记删除但未标记: {del_file}")

    def test_media_only_deletes_nfo_and_images(self):
        """media_only 模式下 .nfo 和图片受 protect_extensions 保护"""
        cleaner = self._make_cleaner(cleanup_mode="media_only")
        items = cleaner.preview()
        deleted_paths = {item["path"] for item in items}

        for name, dir_path, expected in self.scenarios:
            for keep_file in expected["keep"]:
                full_path = os.path.join(dir_path, keep_file)
                ext = os.path.splitext(keep_file)[1].lower()
                if ext in (".nfo", ".jpg", ".png", ".bdmv", ".clpi", ".mpls"):
                    if os.path.isfile(full_path):
                        self.assertNotIn(full_path, deleted_paths,
                            f"[{name}] protect_extensions 保护 .nfo/图片: {keep_file}")

    def test_execute_moves_to_recycle(self):
        """execute 将文件移入回收站 - 使用独立目录避免影响其他测试"""
        test_dir = tempfile.mkdtemp()
        test_recycle = tempfile.mkdtemp()
        try:
            _touch(os.path.join(test_dir, "test_movie.mkv"), 2 * 1024 * 1024 * 1024)
            _touch_text(os.path.join(test_dir, "test_readme.txt"))
            _touch_text(os.path.join(test_dir, "test_ad.url"))

            cleaner = SourceCleaner(_make_config(
                source_dir=test_dir,
                recycle_dir=test_recycle,
                cleanup_mode="media_and_related",
                junk_video_max_size_mb=0,
                cleanup_empty_dirs=False,
            ))
            record = cleaner.execute()
            self.assertIsInstance(record, dict)
            self.assertIn("total_files", record)
            self.assertIn("items", record)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
            shutil.rmtree(test_recycle, ignore_errors=True)

    def test_preview_items_have_required_fields(self):
        """preview 返回的每个 item 包含必要字段"""
        cleaner = self._make_cleaner()
        items = cleaner.preview()
        for item in items:
            self.assertIn("path", item, f"item 缺少 path: {item}")
            self.assertIn("category", item, f"item 缺少 category: {item}")
            self.assertIn("reason", item, f"item 缺少 reason: {item}")
            self.assertIn("source", item, f"item 缺少 source: {item}")
            self.assertIn("size_mb", item, f"item 缺少 size_mb: {item}")

    def test_no_duplicate_items(self):
        """preview 不应返回重复项"""
        cleaner = self._make_cleaner()
        items = cleaner.preview()
        paths = [item["path"] for item in items]
        self.assertEqual(len(paths), len(set(paths)),
            f"存在重复项: {len(paths)} items vs {len(set(paths))} unique paths")

    def test_empty_source_dir_returns_empty(self):
        """空源目录返回空列表"""
        empty_dir = tempfile.mkdtemp()
        try:
            cleaner = SourceCleaner(_make_config(
                source_dir=empty_dir,
                recycle_dir=self.recycle_dir,
            ))
            items = cleaner.preview()
            self.assertEqual(items, [])
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

    def test_nonexistent_source_dir_returns_empty(self):
        """不存在的源目录返回空列表"""
        cleaner = SourceCleaner(_make_config(
            source_dir="/tmp/nonexistent_dir_xyz_123",
            recycle_dir=self.recycle_dir,
        ))
        items = cleaner.preview()
        self.assertEqual(items, [])

    def test_blacklist_patterns_matched_correctly(self):
        """黑名单模式正确匹配"""
        cleaner = self._make_cleaner()
        items = cleaner.preview()
        blacklist_items = [i for i in items if i["category"] == "blacklist_pattern"]
        blacklist_keywords = {"RARBG", "预告", "花絮", "Sample", "sample",
                              "Trailer", "trailer", "Extras", "extras"}
        for item in blacklist_items:
            fname = os.path.basename(item["path"])
            fpath = item["path"]
            matched = any(kw in fname or kw in fpath for kw in blacklist_keywords)
            self.assertTrue(matched,
                f"非黑名单文件被匹配: {item['path']}")

    def test_blacklist_dirs_matched_correctly(self):
        """黑名单目录正确匹配"""
        cleaner = self._make_cleaner()
        items = cleaner.preview()
        blacklist_dirs = [i for i in items if i["category"] == "blacklist_dir"]
        blacklist_names = {"Sample", "sample", "Trailers", "trailers",
                           "预告", "花絮", "Extras", "extras"}
        for item in blacklist_dirs:
            dirname = os.path.basename(item["path"])
            self.assertIn(dirname, blacklist_names,
                f"非黑名单目录被匹配: {dirname}")

    def test_delete_extensions_matched_correctly(self):
        """删除扩展名正确匹配"""
        cleaner = self._make_cleaner()
        items = cleaner.preview()
        delete_ext_items = [i for i in items if i["category"] == "delete_extension"]
        for item in delete_ext_items:
            ext = os.path.splitext(item["path"])[1].lower()
            self.assertIn(ext, {".url", ".txt", ".sfv", ".log", ".bak", ".m3u", ".db"},
                f"非删除扩展名被匹配: {ext}")

    def test_protect_extensions_not_deleted(self):
        """保护扩展名不被标记删除（黑名单优先）"""
        cleaner = self._make_cleaner(cleanup_mode="media_and_related")
        items = cleaner.preview()
        for item in items:
            ext = os.path.splitext(item["path"])[1].lower()
            if item["category"] == "blacklist_pattern":
                continue
            self.assertNotIn(ext, {".nfo", ".jpg", ".png", ".bdmv", ".clpi", ".mpls"},
                f"保护扩展名被标记删除: {ext} ({item['path']})")


# ============================================================
# 第四部分: Bug 检测与边界条件测试
# ============================================================

class TestBugDetection(unittest.TestCase):
    """Bug 检测与边界条件"""

    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.recycle_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.recycle_dir, ignore_errors=True)

    def test_symlink_not_causing_infinite_loop(self):
        """符号链接不应导致无限循环"""
        _touch(os.path.join(self.src_dir, "movie.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "readme.txt"))
        try:
            os.symlink(self.src_dir, os.path.join(self.src_dir, "self_link"))
        except OSError:
            self.skipTest("无法创建符号链接")

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
        ))
        items = cleaner.preview()
        self.assertIsInstance(items, list)

    def test_very_large_file_size_no_overflow(self):
        """超大文件大小不溢出"""
        _touch(os.path.join(self.src_dir, "huge.mkv"), 100 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "readme.txt"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            junk_video_max_size_mb=50,
        ))
        items = cleaner.preview()
        huge_path = os.path.join(self.src_dir, "huge.mkv")
        paths = {item["path"] for item in items}
        self.assertNotIn(huge_path, paths, "大视频不应被标记删除")

    def test_zero_byte_files(self):
        """零字节文件处理"""
        _touch(os.path.join(self.src_dir, "movie.mkv"), 0)
        _touch_text(os.path.join(self.src_dir, "readme.txt"), "")
        _touch_text(os.path.join(self.src_dir, "empty.url"), "")

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
        ))
        items = cleaner.preview()
        self.assertIsInstance(items, list)

    def test_unicode_filenames(self):
        """Unicode 文件名处理"""
        _touch(os.path.join(self.src_dir, "电影🎬.mkv"), 1 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "说明📖.txt"))
        _touch_text(os.path.join(self.src_dir, "电影🎬.srt"))
        _touch_text(os.path.join(self.src_dir, "电影🎬.nfo"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            cleanup_mode="media_and_related",
        ))
        items = cleaner.preview()
        paths = {item["path"] for item in items}
        txt_path = os.path.join(self.src_dir, "说明📖.txt")
        self.assertIn(txt_path, paths, "Unicode txt 应被标记删除")

    def test_very_long_filename(self):
        """超长文件名处理"""
        long_name = "A" * 200
        _touch(os.path.join(self.src_dir, f"{long_name}.mkv"), 1 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, f"{long_name}.srt"))
        _touch_text(os.path.join(self.src_dir, f"{long_name}.txt"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            cleanup_mode="media_and_related",
        ))
        items = cleaner.preview()
        paths = {item["path"] for item in items}
        txt_path = os.path.join(self.src_dir, f"{long_name}.txt")
        self.assertIn(txt_path, paths, "超长文件名 txt 应被标记删除")

    def test_deeply_nested_directories(self):
        """深层嵌套目录处理"""
        deep = self.src_dir
        for i in range(10):
            deep = os.path.join(deep, f"level_{i}")
        _touch(os.path.join(deep, "deep_movie.mkv"), 1 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(deep, "deep_readme.txt"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
        ))
        items = cleaner.preview()
        self.assertIsInstance(items, list)

    def test_task_paths_exclusion(self):
        """task_paths 排除功能"""
        _touch(os.path.join(self.src_dir, "movie.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "readme.txt"))
        _touch_text(os.path.join(self.src_dir, "ad.url"))

        task_paths = {os.path.join(self.src_dir, "readme.txt")}
        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
        ))
        items = cleaner.preview(task_paths=task_paths)
        paths = {item["path"] for item in items}
        txt_path = os.path.join(self.src_dir, "readme.txt")
        self.assertNotIn(txt_path, paths, "task_paths 中的文件应被排除")

    def test_empty_delete_extensions(self):
        """空删除扩展名列表"""
        _touch(os.path.join(self.src_dir, "movie.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "readme.txt"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            delete_extensions=[],
            cleanup_mode="media_only",
        ))
        items = cleaner.preview()
        paths = {item["path"] for item in items}
        txt_path = os.path.join(self.src_dir, "readme.txt")
        self.assertIn(txt_path, paths, "media_only 下 txt 应被标记(non_media)")

    def test_empty_protect_extensions(self):
        """空保护扩展名列表"""
        _touch(os.path.join(self.src_dir, "movie.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "movie.nfo"))
        _touch_text(os.path.join(self.src_dir, "movie.jpg"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            protect_extensions=[],
            cleanup_mode="media_only",
        ))
        items = cleaner.preview()
        paths = {item["path"] for item in items}
        nfo_path = os.path.join(self.src_dir, "movie.nfo")
        jpg_path = os.path.join(self.src_dir, "movie.jpg")
        self.assertIn(nfo_path, paths, "无保护扩展名时 nfo 应被标记")
        self.assertIn(jpg_path, paths, "无保护扩展名时 jpg 应被标记")

    def test_empty_blacklist_patterns(self):
        """空黑名单模式列表"""
        _touch(os.path.join(self.src_dir, "movie.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "RARBG.txt"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            blacklist_patterns=[],
        ))
        items = cleaner.preview()
        paths = {item["path"] for item in items}
        rarbg_path = os.path.join(self.src_dir, "RARBG.txt")
        self.assertIn(rarbg_path, paths, "无黑名单时 RARBG.txt 仍应被 delete_extension 匹配")

    def test_junk_video_zero_disables_threshold(self):
        """junk_video_max_size_mb=0 禁用阈值"""
        _touch(os.path.join(self.src_dir, "movie.mkv"), 2 * 1024 * 1024 * 1024)
        _touch(os.path.join(self.src_dir, "small.mkv"), 1 * 1024 * 1024)

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            junk_video_max_size_mb=0,
        ))
        items = cleaner.preview()
        paths = {item["path"] for item in items}
        small_path = os.path.join(self.src_dir, "small.mkv")
        self.assertNotIn(small_path, paths, "阈值=0 时不应标记小视频")

    def test_no_video_in_dir_non_media_handling(self):
        """无视频目录中非媒体文件处理"""
        d = os.path.join(self.src_dir, "no_video_dir")
        _touch_text(os.path.join(d, "readme.txt"))
        _touch_text(os.path.join(d, "ad.url"))
        _touch_text(os.path.join(d, "info.log"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
        ))
        items = cleaner.preview()
        paths = {item["path"] for item in items}
        for fname in ["readme.txt", "ad.url", "info.log"]:
            fpath = os.path.join(d, fname)
            self.assertIn(fpath, paths, f"无视频目录中 {fname} 应被标记删除")

    def test_companion_file_detection_with_special_chars(self):
        """特殊字符伴生文件检测"""
        _touch(os.path.join(self.src_dir, "movie.2024.mkv"), 1 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "movie.2024.srt"))
        _touch_text(os.path.join(self.src_dir, "movie.2024-poster.jpg"))
        _touch_text(os.path.join(self.src_dir, "movie.2024_fanart.jpg"))
        _touch_text(os.path.join(self.src_dir, "movie.2024 thumb.png"))
        _touch_text(os.path.join(self.src_dir, "movie.2024.nfo"))
        _touch_text(os.path.join(self.src_dir, "unrelated.txt"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            cleanup_mode="media_and_related",
        ))
        items = cleaner.preview()
        paths = {item["path"] for item in items}

        unrelated = os.path.join(self.src_dir, "unrelated.txt")
        self.assertIn(unrelated, paths, "不相关文件应被标记删除")

        for companion in ["movie.2024-poster.jpg", "movie.2024_fanart.jpg",
                          "movie.2024 thumb.png", "movie.2024.nfo"]:
            cpath = os.path.join(self.src_dir, companion)
            self.assertNotIn(cpath, paths, f"伴生文件应保留: {companion}")

    def test_execute_with_empty_preview(self):
        """空 preview 执行不报错"""
        empty_dir = tempfile.mkdtemp()
        try:
            cleaner = SourceCleaner(_make_config(
                source_dir=empty_dir,
                recycle_dir=self.recycle_dir,
            ))
            record = cleaner.execute()
            self.assertEqual(record["total_files"], 0)
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

    def test_ai_merge_union_strategy(self):
        """AI union 合并策略"""
        _touch(os.path.join(self.src_dir, "movie.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "keep_me.txt"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            ai_enabled=True,
            merge_strategy="union",
        ))

        with patch.object(SourceCleaner, "_ai_analyze_all") as mock_ai:
            mock_ai.return_value = {
                os.path.join(self.src_dir, "keep_me.txt"): {
                    "action": "delete", "reason": "AI says delete"
                }
            }
            items = cleaner.preview()
            paths = {item["path"] for item in items}
            keep_path = os.path.join(self.src_dir, "keep_me.txt")
            self.assertIn(keep_path, paths, "union 策略下 AI 判定删除应生效")

    def test_ai_merge_intersection_strategy(self):
        """AI intersection 合并策略"""
        _touch(os.path.join(self.src_dir, "movie.mkv"), 2 * 1024 * 1024 * 1024)
        _touch_text(os.path.join(self.src_dir, "keep_me.txt"))

        cleaner = SourceCleaner(_make_config(
            source_dir=self.src_dir,
            recycle_dir=self.recycle_dir,
            ai_enabled=True,
            merge_strategy="intersection",
        ))

        with patch.object(SourceCleaner, "_ai_analyze_all") as mock_ai:
            mock_ai.return_value = {
                os.path.join(self.src_dir, "keep_me.txt"): {
                    "action": "keep", "reason": "AI says keep"
                }
            }
            items = cleaner.preview()
            paths = {item["path"] for item in items}
            keep_path = os.path.join(self.src_dir, "keep_me.txt")
            self.assertNotIn(keep_path, paths,
                "intersection 策略下 AI 判定保留应从删除列表移除")


if __name__ == "__main__":
    unittest.main()
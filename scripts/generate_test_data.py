#!/usr/bin/env python3
"""影音库AI智能整理 — 全流程测试数据生成脚本"""
import os
import shutil

BASE = "/tmp/nas_media_test"
SOURCE = os.path.join(BASE, "source")

MP4_HEADER = bytes.fromhex("00000020667479706D703432000000006D70343269736F6D0000000000000000")
MKV_HEADER = bytes.fromhex("1A45DFA3934282886D6174726F736B61428781014285810118538067010000000000000000")

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def write_file(path, content):
    ensure_dir(os.path.dirname(path))
    if isinstance(content, str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        with open(path, "wb") as f:
            f.write(content)

def make_video(path, fmt="mkv"):
    header = MKV_HEADER if fmt == "mkv" else MP4_HEADER
    write_file(path, header)

def make_junk(path, content="junk data"):
    write_file(path, content)

def make_srt(path, lines):
    write_file(path, "\n".join(lines))

def make_vtt(path, lines):
    write_file(path, "WEBVTT\n\n" + "\n".join(lines))

def clean():
    print("==> 清理旧测试数据...")
    for d in [SOURCE, f"{BASE}/temp", f"{BASE}/recycle", f"{BASE}/logs", f"{BASE}/resources", f"{BASE}/影视"]:
        if os.path.exists(d):
            shutil.rmtree(d)
    ensure_dir(SOURCE)
    ensure_dir(f"{BASE}/temp")
    ensure_dir(f"{BASE}/recycle")
    ensure_dir(f"{BASE}/logs")
    ensure_dir(f"{BASE}/resources/thumbnail")
    for sub in ["电影", "电影-R", "纪录片", "动漫", "动漫电影", "电视剧", "TV-R", "未分类", "其他"]:
        ensure_dir(f"{BASE}/影视/{sub}")

# ============================================================
# 场景 1-11: 覆盖全部 10 条 path_rules
# ============================================================

def s01_normal_movies():
    d = f"{SOURCE}/Movies"
    make_video(f"{d}/Inception.2010.1080p.BluRay.x264-DTS.mkv")
    make_srt(f"{d}/Inception.2010.1080p.BluRay.x264-DTS.eng.srt", ["1","00:00:01,000 --> 00:00:05,000","Hello"])
    make_srt(f"{d}/Inception.2010.1080p.BluRay.x264-DTS.chs.srt", ["1","00:00:01,000 --> 00:00:05,000","你好"])
    make_video(f"{d}/The.Dark.Knight.2008.2160p.REMUX.HEVC.DTS-HD.MA.mkv")
    make_video(f"{d}/Avatar.2009.1080p.BluRay.3D.HSBS.DTS.x264.mkv")
    print("  [OK] 场景1: 3部普通电影 + 2字幕 -> 预期 /影视/电影/{year}/")

def s02_r_rated_movies():
    d = f"{SOURCE}/R_Rated_Movies"
    make_video(f"{d}/Deadpool.2016.1080p.BluRay.x264-SPARKS.mkv")
    make_video(f"{d}/Joker.2019.2160p.WEB-DL.HDR.DDP5.1.Atmos.x265.mkv")
    print("  [OK] 场景2: 2部限制级电影 -> 预期 /影视/电影-R/{year}/")

def s03_documentary():
    d = f"{SOURCE}/Documentaries"
    make_video(f"{d}/March.of.the.Penguins.2005.1080p.BluRay.x264.mkv")
    make_video(f"{d}/舌尖上的中国.2012.S01E01.1080p.WEB-DL.H264.mkv")
    print("  [OK] 场景3: 2部纪录片 -> 预期 /影视/纪录片/")

def s04_anime_movies():
    d = f"{SOURCE}/Anime_Movies"
    make_video(f"{d}/Spirited.Away.2001.1080p.BluRay.x264.mkv")
    make_video(f"{d}/Your.Name.2016.1080p.BluRay.x264.mkv")
    print("  [OK] 场景4: 2部动漫电影 -> 预期 /影视/动漫电影/")

def s05_anime_tv_family():
    d = f"{SOURCE}/Anime_TV/Pokemon"
    make_video(f"{d}/Pokemon.S01E01.1080p.WEB-DL.x264.mkv")
    make_video(f"{d}/Pokemon.S01E02.1080p.WEB-DL.x264.mkv")
    print("  [OK] 场景5: 2集宝可梦 -> 预期 /影视/动漫/家庭向/ （规则1: 0-6|7-12）")

def s06_anime_tv_teen():
    d = f"{SOURCE}/Anime_TV/Attack_on_Titan"
    make_video(f"{d}/Attack.on.Titan.S01E01.1080p.BluRay.x264.mkv")
    make_video(f"{d}/Attack.on.Titan.S01E02.1080p.BluRay.x264.mkv")
    print("  [OK] 场景6: 2集进击的巨人 -> 预期 /影视/动漫/青少年向/ （规则2: 17+）")

def s07_anime_tv_general():
    d = f"{SOURCE}/Anime_TV/One_Piece"
    make_video(f"{d}/One.Piece.S01E01.1080p.WEB-DL.x264.mkv")
    make_video(f"{d}/One.Piece.S01E02.1080p.WEB-DL.x264.mkv")
    print("  [OK] 场景7: 2集海贼王 -> 预期 /影视/动漫/ （规则3: 通用）")

def s08_r_rated_tv():
    d = f"{SOURCE}/TV_Shows/Game_of_Thrones"
    make_video(f"{d}/Game.of.Thrones.S01E01.1080p.BluRay.x264.mkv")
    make_video(f"{d}/Game.of.Thrones.S01E02.1080p.BluRay.x264.mkv")
    make_srt(f"{d}/Game.of.Thrones.S01E01.1080p.BluRay.x264.eng.srt", ["1","00:00:01,000 --> 00:00:05,000","Winter is coming"])
    print("  [OK] 场景8: 2集权游 + 1字幕 -> 预期 /影视/TV-R/ （规则4: 17+）")

def s09_normal_tv():
    d = f"{SOURCE}/TV_Shows/Friends"
    make_video(f"{d}/Friends.S01E01.1080p.WEB-DL.x264.mp4", fmt="mp4")
    make_video(f"{d}/Friends.S01E02.1080p.WEB-DL.x264.mp4", fmt="mp4")
    print("  [OK] 场景9: 2集老友记 -> 预期 /影视/电视剧/ （规则5: 通用）")

def s10_chinese_movies():
    d = f"{SOURCE}/Chinese_Movies"
    make_video(f"{d}/流浪地球.2019.1080p.BluRay.x264.mkv")
    make_video(f"{d}/你好李焕英.2021.1080p.WEB-DL.H265.mkv")
    print("  [OK] 场景10: 2部中文电影 -> 预期 /影视/电影/{year}/ （规则9: 电影）")

def s11_fallback():
    d = f"{SOURCE}/Unknown"
    make_video(f"{d}/Some.Random.Indie.Film.2023.1080p.WEBRip.x264.mkv")
    print("  [OK] 场景11: 1部未知影片 -> 预期 /影视/其他/ （规则10: 兜底）")

# ============================================================
# 场景 12-20: 源清理器 + 边缘情况
# ============================================================

def s12_bt_download_cleaner():
    d = f"{SOURCE}/BT_Downloads/The.Matrix.1999.1080p.BluRay.x264-SPARKS"
    make_video(f"{d}/The.Matrix.1999.1080p.BluRay.x264-SPARKS.mkv")
    make_srt(f"{d}/Subs/eng.srt", ["1","00:00:01,000 --> 00:00:05,000","Wake up Neo"])
    make_srt(f"{d}/Subs/chs.srt", ["1","00:00:01,000 --> 00:00:05,000","wake up"])
    make_junk(f"{d}/Subs/chs.ass", "subtitle")
    make_junk(f"{d}/movie.nfo", "<movie><title>The Matrix</title></movie>")
    make_junk(f"{d}/poster.jpg", "fake-jpeg")
    make_junk(f"{d}/fanart.jpg", "fake-jpeg")
    make_junk(f"{d}/clearart.png", "fake-png")
    make_junk(f"{d}/readme.txt", "Thanks for downloading from RARBG")
    make_junk(f"{d}/proof.sfv", "matrix.mkv ABCDEF01")
    make_junk(f"{d}/torrent_downloader.log", "downloaded at 2024-01-01")
    make_junk(f"{d}/thumbs.db", "binary")
    make_junk(f"{d}/playlist.m3u", "#EXTM3U")
    make_junk(f"{d}/RARBG.txt", "RARBG - The Best Torrent Site")
    make_junk(f"{d}/RARBG_DO_NOT_MIRROR.exe", "fake-exe")
    make_video(f"{d}/Sample/sample.mkv")
    make_junk(f"{d}/old_script.bak", "backup")
    make_junk(f"{d}/The.Matrix.1999.1080p.BluRay.x264-SPARKS.torrent", "torrent-data")
    make_junk(f"{d}/下载说明_download.url", "[InternetShortcut]")
    print("  [OK] 场景12: BT下载目录（1视频+3字幕+4伴生+12垃圾 -> 预期保留8个）")

def s13_multi_season():
    d = f"{SOURCE}/Multi_Season/Breaking_Bad"
    make_video(f"{d}/Breaking.Bad.S01E01.1080p.BluRay.x264.mkv")
    make_video(f"{d}/Breaking.Bad.S01E02.1080p.BluRay.x264.mkv")
    make_video(f"{d}/Breaking.Bad.S01E03.1080p.BluRay.x264.mkv")
    make_video(f"{d}/Breaking.Bad.S02E01.1080p.BluRay.x264.mkv")
    make_junk(f"{d}/Breaking.Bad.S01E01.1080p.BluRay.x264.eng.ass", "ass subtitle")
    make_junk(f"{d}/Breaking.Bad.S01E01.1080p.BluRay.x264.chs.ssa", "ssa subtitle")
    make_vtt(f"{d}/Breaking.Bad.S01E01.1080p.BluRay.x264.cht.vtt", ["1","00:00:01.000 --> 00:00:05.000","sub"])
    make_junk(f"{d}/Breaking.Bad.S01E01.1080p.BluRay.x264.jpn.sub", "sub subtitle")
    print("  [OK] 场景13: 多季剧集（4集 + 4种字幕格式 ass/ssa/vtt/sub）")

def s14_multi_format():
    d = f"{SOURCE}/Multi_Format"
    make_video(f"{d}/Old.Movie.2000.DVDrip.XviD.avi", fmt="mkv")
    make_video(f"{d}/TV.Recording.2024.HDTV.ts", fmt="mkv")
    make_video(f"{d}/Home.Video.2023.iPhone.mov", fmt="mp4")
    make_video(f"{d}/Legacy.Clip.2010.WMV9.wmv", fmt="mkv")
    make_video(f"{d}/BluRay.Remux.2022.m2ts", fmt="mkv")
    make_video(f"{d}/Web.Stream.2024.flv", fmt="mp4")
    print("  [OK] 场景14: 6种视频格式（avi/ts/mov/wmv/m2ts/flv）")

def s15_chinese_tv():
    d = f"{SOURCE}/Chinese_TV"
    make_video(f"{d}/庆余年.S01E01.2019.1080p.WEB-DL.H265.mkv")
    make_video(f"{d}/庆余年.S01E02.2019.1080p.WEB-DL.H265.mkv")
    make_video(f"{d}/三体.2023.E01.2160p.WEB-DL.H265.mkv")
    make_video(f"{d}/三体.2023.E02.2160p.WEB-DL.H265.mkv")
    print("  [OK] 场景15: 4集中文电视剧")

def s16_cleaner_blacklist_dirs():
    d = f"{SOURCE}/Cleaner_Test/Movie_With_Extras"
    make_video(f"{d}/Test.Movie.2024.1080p.mkv")
    make_video(f"{d}/花絮/behind_the_scenes.mkv")
    make_video(f"{d}/花絮/interview.mkv")
    make_video(f"{d}/预告/trailer1.mkv")
    make_video(f"{d}/预告/trailer2.mkv")
    make_video(f"{d}/Extras/deleted_scenes.mkv")
    make_video(f"{d}/Trailers/official_trailer.mkv")
    make_junk(f"{d}/README.txt", "readme")
    make_junk(f"{d}/index.bdmv", "BDMV")
    make_junk(f"{d}/MovieObject.bdmv", "BDMV")
    print("  [OK] 场景16: 含花絮/预告/Extras目录（7视频+3垃圾，黑名单应删除子目录）")

def s17_junk_video_size():
    d = f"{SOURCE}/Cleaner_Test/Junk_Videos"
    make_video(f"{d}/Real.Feature.Film.2024.1080p.mkv")
    make_video(f"{d}/advertisement_sample.mp4", fmt="mp4")
    make_junk(f"{d}/info.txt", "sample info")
    print("  [OK] 场景17: 小体积视频（应被清理器识别为垃圾视频，<50MB）")

def s18_empty_dirs():
    d = f"{SOURCE}/Cleaner_Test/Empty_Dirs"
    ensure_dir(f"{d}/empty_subdir_1")
    ensure_dir(f"{d}/empty_subdir_2/sub_subdir")
    make_junk(f"{d}/keep_this_file.txt", "not empty dir")
    print("  [OK] 场景18: 空目录（清理后应删除空目录，保留非空目录）")

def s19_duplicate_detection():
    d = f"{SOURCE}/Duplicate_Test"
    make_video(f"{d}/Interstellar.2014.1080p.BluRay.x264.mkv")
    make_video(f"{d}/Interstellar.2014.2160p.REMUX.HEVC.mkv")
    print("  [OK] 场景19: 重复文件检测（2个同名不同分辨率版本）")

def s20_bdmv_structure():
    d = f"{SOURCE}/BDMV_Test/Movie_BDMV"
    make_junk(f"{d}/index.bdmv", "BDMV index")
    make_junk(f"{d}/MovieObject.bdmv", "BDMV object")
    ensure_dir(f"{d}/BDMV/BACKUP")
    ensure_dir(f"{d}/BDMV/CLIPINF")
    ensure_dir(f"{d}/BDMV/PLAYLIST")
    ensure_dir(f"{d}/BDMV/STREAM")
    make_junk(f"{d}/BDMV/CLIPINF/00001.clpi", "clip info")
    make_junk(f"{d}/BDMV/PLAYLIST/00000.mpls", "playlist")
    make_video(f"{d}/BDMV/STREAM/00001.m2ts")
    ensure_dir(f"{d}/CERTIFICATE")
    make_junk(f"{d}/CERTIFICATE/id.bin", "cert")
    print("  [OK] 场景20: BDMV蓝光原盘结构（protect_extensions保护 .bdmv/.clpi/.mpls）")

def print_summary():
    total_files = 0
    total_dirs = 0
    for _root, dirs, files in os.walk(SOURCE):
        total_dirs += len(dirs)
        total_files += len(files)
    print("\n" + "=" * 60)
    print("  测试数据生成完成！")
    print("=" * 60)
    print(f"  源目录: {SOURCE}")
    print(f"  总目录数: {total_dirs}")
    print(f"  总文件数: {total_files}")
    print("  测试场景: 20 个")
    print()
    print("  覆盖的功能节点:")
    print("    [扫描] 8种视频格式 + 5种字幕格式 + 递归扫描 + 去重")
    print("    [刮削] 英文/中文电影 + 电视剧 + 动漫 + 纪录片")
    print("    [分类] 全部 10 条 path_rules (电影/电影-R/纪录片/动漫电影/动漫/电视剧/TV-R/兜底)")
    print("    [入库] 文件移动 + 回收站 + 目录结构创建")
    print("    [清理] 源清理器(垃圾文件/黑名单/伴生文件/空目录/BDMV)")
    print("    [边缘] 重复检测/多格式/多季/中文剧集/兜底规则")

# 主流程
if __name__ == "__main__":
    clean()
    print("\n==> 生成测试文件...")
    s01_normal_movies()
    s02_r_rated_movies()
    s03_documentary()
    s04_anime_movies()
    s05_anime_tv_family()
    s06_anime_tv_teen()
    s07_anime_tv_general()
    s08_r_rated_tv()
    s09_normal_tv()
    s10_chinese_movies()
    s11_fallback()
    s12_bt_download_cleaner()
    s13_multi_season()
    s14_multi_format()
    s15_chinese_tv()
    s16_cleaner_blacklist_dirs()
    s17_junk_video_size()
    s18_empty_dirs()
    s19_duplicate_detection()
    s20_bdmv_structure()
    print_summary()

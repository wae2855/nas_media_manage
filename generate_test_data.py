#!/usr/bin/env python3
"""生成模拟 BT 下载的测试数据。

用法:
    python generate_test_data.py               # 在默认位置生成
    python generate_test_data.py --count 30    # 指定生成数量
    python generate_test_data.py --clean       # 先清理再生成

生成内容:
    - 约 20 个影视项目（电影+电视剧）
    - 涵盖字幕、视频、种子、海报、图片、广告、URL等文件类型
    - 模拟真实 BT 下载目录结构
"""

import argparse
import os
import random
from pathlib import Path
from datetime import datetime

# 影视数据
MOVIES = [
    ("肖申克的救赎", "The Shawshank Redemption", 1994, "1080p", "BluRay"),
    ("阿甘正传", "Forrest Gump", 1994, "1080p", "BluRay"),
    ("盗梦空间", "Inception", 2010, "1080p", "WEB-DL"),
    ("星际穿越", "Interstellar", 2014, "2160p", "BluRay"),
    ("霸王别姬", "Farewell My Concubine", 1993, "1080p", "BluRay"),
    ("泰坦尼克号", "Titanic", 1997, "1080p", "HDTV"),
    ("千与千寻", "Spirited Away", 2001, "1080p", "BluRay"),
    ("疯狂动物城", "Zootopia", 2016, "1080p", "WEB-DL"),
    ("寄生虫", "Parasite", 2019, "1080p", "BluRay"),
    ("沙丘", "Dune", 2021, "2160p", "WEB-DL"),
]

TV_SERIES = [
    ("老友记", "Friends", 1994, 10, "1080p", "BluRay"),
    ("权力的游戏", "Game of Thrones", 2011, 8, "1080p", "WEB-DL"),
    ("绝命毒师", "Breaking Bad", 2008, 5, "1080p", "BluRay"),
    ("怪奇物语", "Stranger Things", 2016, 5, "2160p", "WEB-DL"),
    ("西部世界", "Westworld", 2016, 4, "1080p", "HDTV"),
    ("鱿鱼游戏", "Squid Game", 2021, 2, "2160p", "WEB-DL"),
    ("进击的巨人", "Attack on Titan", 2013, 4, "1080p", "BluRay"),
    ("咒术回战", "Jujutsu Kaisen", 2020, 2, "1080p", "WEB-DL"),
]

SUBTITLE_LANGS = ["zh", "en", "zh-Hans", "ja", "ko", "fr", "de", "es"]
VIDEO_EXTS = [".mkv", ".mp4", ".avi", ".ts", ".mov"]
IMAGE_EXTS = [".jpg", ".png"]

# BT 下载常见文件
BT_FILES = [
    ("RARBG.txt", "txt", "RARBG DO NOT MIRROR"),
    ("RARBG_DO_NOT_MIRROR.exe", "exe", ""),
    ("sample.mp4", "video_small", ""),
    ("trailer.mp4", "video_small", ""),
    ("电影天堂.url", "url", "http://www.dytt8.net"),
    ("BT天堂.url", "url", "http://www.bttiantang.com"),
    ("说明.txt", "txt", "请使用完美解码播放"),
    ("NFO.nfo", "nfo", "MediaInfo"),
    ("校验.md5", "md5", "hash"),
    ("playlist.m3u", "m3u", ""),
    ("Thumbs.db", "db", ""),
    ("desktop.ini", "ini", ""),
]


def parse_args():
    parser = argparse.ArgumentParser(description="生成 BT 下载测试数据")
    parser.add_argument("--count", type=int, default=20, help="生成影视项目数量")
    parser.add_argument("--clean", action="store_true", help="先清理现有数据")
    parser.add_argument("--source-dir", help="源目录路径（默认从配置读取）")
    return parser.parse_args()


def load_config():
    config_path = Path("config/config.yaml")
    if not config_path.exists():
        return {}
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}


def get_source_dir(args, cfg):
    if args.source_dir:
        return Path(args.source_dir)
    source_dir = cfg.get("source_dir")
    if source_dir:
        return Path(source_dir)
    return Path("/tmp/nas_media_test/source")


def create_small_file(path, content=""):
    """创建小文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        with open(path, "wb") as f:
            f.write(os.urandom(random.randint(100, 10000)))


def create_video_file(path, size_mb=50):
    """创建视频文件（使用稀疏文件）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    size_bytes = size_mb * 1024 * 1024
    with open(path, "wb") as f:
        f.seek(size_bytes - 1)
        f.write(b"\x00")


def generate_movie(project_dir, movie, variant=0):
    """生成电影目录结构。"""
    title_cn, title_en, year, resolution, quality = movie
    
    # 目录名变体
    dir_name_variants = [
        f"{title_cn} ({year})",
        f"{title_en} ({year}) {resolution} {quality}",
        f"{title_cn}.{title_en}.{year}.{resolution}.{quality}",
    ]
    dir_name = dir_name_variants[variant % len(dir_name_variants)]
    movie_dir = project_dir / dir_name
    movie_dir.mkdir(parents=True, exist_ok=True)
    
    # 主视频文件
    ext = random.choice(VIDEO_EXTS)
    video_name = f"{title_cn}.{resolution}.{quality}{ext}"
    create_video_file(movie_dir / video_name, size_mb=random.randint(400, 2000))
    
    # 字幕文件（2-4个）
    num_subs = random.randint(2, 4)
    selected_langs = random.sample(SUBTITLE_LANGS, num_subs)
    for lang in selected_langs:
        sub_name = f"{title_cn}.{lang}.srt"
        create_small_file(movie_dir / sub_name, f"1\n00:00:01,000 --> 00:00:05,000\n字幕内容\n")
    
    # 海报/封面
    poster_name = random.choice(["cover", "poster", "folder"] + [title_en, title_cn])
    poster_ext = random.choice(IMAGE_EXTS)
    create_small_file(movie_dir / f"{poster_name}{poster_ext}")
    
    # NFO 文件
    create_small_file(movie_dir / f"{title_cn}.nfo", f"<movie><title>{title_cn}</title><year>{year}</year></movie>")
    
    # BT 种子
    create_small_file(movie_dir / f"{title_cn}.torrent")
    
    # 随机添加其他 BT 文件
    num_extra = random.randint(1, 3)
    extra_files = random.sample(BT_FILES, num_extra)
    for name, ftype, content in extra_files:
        if ftype == "video_small":
            create_video_file(movie_dir / name, size_mb=random.randint(5, 30))
        else:
            create_small_file(movie_dir / name, content)
    
    # Sample 目录
    if random.random() < 0.3:
        sample_dir = movie_dir / "Sample"
        sample_dir.mkdir(exist_ok=True)
        create_video_file(sample_dir / f"{title_cn}_Sample.mp4", size_mb=random.randint(20, 80))
    
    return movie_dir


def generate_tv_series(project_dir, series, variant=0):
    """生成电视剧目录结构。"""
    title_cn, title_en, year, num_seasons, resolution, quality = series
    
    # 目录名变体
    dir_name_variants = [
        f"{title_cn}",
        f"{title_en} ({year})",
        f"{title_cn}.{title_en}.{year}",
    ]
    dir_name = dir_name_variants[variant % len(dir_name_variants)]
    series_dir = project_dir / dir_name
    series_dir.mkdir(parents=True, exist_ok=True)
    
    # 海报
    create_small_file(series_dir / "poster.jpg")
    
    # NFO 文件
    create_small_file(series_dir / "series.nfo", f"<tvshow><title>{title_cn}</title><year>{year}</year></tvshow>")
    
    # 种子文件
    create_small_file(series_dir / f"{title_cn}.torrent")
    
    # 生成季目录
    num_seasons_to_gen = min(num_seasons, random.randint(1, 3))
    for season in range(1, num_seasons_to_gen + 1):
        season_dir = series_dir / f"Season {season:02d}"
        season_dir.mkdir(exist_ok=True)
        
        # 每季集数
        num_episodes = random.randint(6, 24)
        
        # 生成集文件
        for episode in range(1, num_episodes + 1):
            ext = random.choice(VIDEO_EXTS)
            ep_name = f"{title_cn}.S{season:02d}E{episode:02d}.{resolution}.{quality}{ext}"
            create_video_file(season_dir / ep_name, size_mb=random.randint(300, 1500))
            
            # 字幕
            if random.random() < 0.8:
                lang = random.choice(SUBTITLE_LANGS)
                sub_name = f"{title_cn}.S{season:02d}E{episode:02d}.{lang}.srt"
                create_small_file(season_dir / sub_name, f"1\n00:00:01,000 --> 00:00:05,000\n字幕\n")
        
        # 季海报
        create_small_file(season_dir / f"Season{season:02d}.jpg")
    
    # 随机添加其他文件
    num_extra = random.randint(1, 2)
    extra_files = random.sample(BT_FILES, num_extra)
    for name, ftype, content in extra_files:
        create_small_file(series_dir / name, content)
    
    return series_dir


def generate_mixed_folder(project_dir):
    """生成混合内容文件夹（模拟下载不完全或杂乱的情况）。"""
    mixed_names = [
        "未分类影视",
        "临时下载",
        "合集",
        "蓝光原盘",
        "纪录片合集",
    ]
    folder_name = random.choice(mixed_names)
    mixed_dir = project_dir / folder_name
    mixed_dir.mkdir(parents=True, exist_ok=True)
    
    # 添加各种类型文件
    for _ in range(random.randint(3, 8)):
        if random.random() < 0.4:
            # 视频文件
            name = f"Video_{random.randint(1, 999)}{random.choice(VIDEO_EXTS)}"
            create_video_file(mixed_dir / name, size_mb=random.randint(100, 500))
        elif random.random() < 0.6:
            # 字幕
            name = f"Subtitle_{random.randint(1, 99)}.srt"
            create_small_file(mixed_dir / name)
        else:
            # 其他文件
            name, ftype, content = random.choice(BT_FILES)
            create_small_file(mixed_dir / name, content)
    
    return mixed_dir


def main():
    args = parse_args()
    cfg = load_config()
    source_dir = get_source_dir(args, cfg)
    
    # 清理现有数据
    if args.clean:
        import shutil
        if source_dir.exists():
            shutil.rmtree(source_dir)
            print(f"已清理目录: {source_dir}")
    
    source_dir.mkdir(parents=True, exist_ok=True)
    print(f"生成测试数据到: {source_dir}")
    
    # 生成项目
    projects_generated = 0
    movie_idx = 0
    series_idx = 0
    variant = 0
    
    while projects_generated < args.count:
        # 随机选择类型
        if random.random() < 0.5 or series_idx >= len(TV_SERIES):
            # 生成电影
            if movie_idx < len(MOVIES):
                movie = MOVIES[movie_idx % len(MOVIES)]
                generate_movie(source_dir, movie, variant)
                movie_idx += 1
                projects_generated += 1
                print(f"[{projects_generated}] 电影: {movie[0]}")
        else:
            # 生成电视剧
            if series_idx < len(TV_SERIES):
                series = TV_SERIES[series_idx % len(TV_SERIES)]
                generate_tv_series(source_dir, series, variant)
                series_idx += 1
                projects_generated += 1
                print(f"[{projects_generated}] 电视剧: {series[0]}")
        
        variant += 1
    
    # 生成一些混合文件夹
    for _ in range(random.randint(1, 3)):
        generate_mixed_folder(source_dir)
        print(f"[混合] 生成混合内容文件夹")
    
    print(f"\n✅ 生成完成！共 {projects_generated} 个影视项目")
    
    # 统计文件数
    total_files = 0
    for root, dirs, files in os.walk(source_dir):
        total_files += len(files)
    print(f"📁 总文件数: {total_files}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
测试刮削结果 - 使用指定的文件名测试 AI 和 TMDB+AI 两种刮削方式
"""
import os
import sys
import tempfile
import json
import types

# 参考 test_dimensions.py 的导入方式
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'media_importer'))

import db as db_module
from config_loader import load_config
from llm_scraper import LLMScraper
from metadata_scraper import MetadataScraper
from tmdb_client import TMDbClient

# 构建 media_importer 包
media_importer_pkg = types.ModuleType('media_importer')
media_importer_pkg.__path__ = [os.path.join(os.path.dirname(__file__), '..', 'media_importer')]
sys.modules['media_importer'] = media_importer_pkg
sys.modules['media_importer.db'] = db_module


TEST_FILES = [
    "2024.1080p.mkv",
    "Joker.2019.1080p.BluRay.mkv",
    "Your.Name.2016.1080p.BluRay.mkv",
    "Wuthering.Heights.2024.1080p.BluRay.x264.mkv",
    "Game.of.Thrones.S01E01.Winter.Is.Coming.1080p.mkv",
    "Stranger.Things.S01E01.720p.WEB.mkv",
    "Breaking.Bad.S01E02.Mr.Chips.720p.BluRay.mkv",
]


def print_separator(title=""):
    print("\n" + "="*80)
    if title:
        print(f"  {title}")
        print("="*80)


def print_result(label, result):
    print(f"\n{label}:")
    print("-" * 40)
    print(f"  标题: {result.get('title_cn')} / {result.get('title_en')}")
    print(f"  年份: {result.get('year')}")
    print(f"  类型: {result.get('type')}")
    if result.get('season'):
        print(f"  季集: S{result.get('season')}E{result.get('episode')}")
    print(f"  分辨率: {result.get('resolution')}")
    print(f"  置信度: {result.get('confidence')}")
    if 'dimensions' in result:
        print(f"  维度:")
        dims = result['dimensions']
        if isinstance(dims, dict):
            for k, v in dims.items():
                if isinstance(v, dict):
                    print(f"    {k}: {v.get('value', v)}")
                else:
                    print(f"    {k}: {v}")


def main():
    print_separator("影视刮削结果测试")
    
    # 加载配置
    config = load_config()
    
    # 创建临时数据库
    tmpdir = tempfile.mkdtemp(prefix="test_scrape_")
    db_path = os.path.join(tmpdir, "test.db")
    conn = db_module.init_db(db_path)
    
    # 初始化各个组件
    llm_scraper = LLMScraper(config)
    llm_scraper.load_dimensions_from_db(conn)
    metadata_scraper = MetadataScraper(config)
    
    # 先检查 TMDB 配置是否可用
    tmdb_config = config.get("metadata", {}).get("tmdb", {})
    if tmdb_config.get("enabled") and tmdb_config.get("api_key"):
        print(f"  ✓ TMDB 配置有效: API Key 配置已启用")
    else:
        print(f"  ⚠️  TMDB 配置未启用或缺少 API Key，仅测试 AI 刮削")
    
    for filename in TEST_FILES:
        print_separator(f"测试文件: {filename}")
        
        # 方式1: 纯 AI 刮削
        print("\n[1/2] 纯 AI 刮削...")
        try:
            ai_result = llm_scraper.scrape(filename, [], conn)
            print_result("纯 AI 刮削结果", ai_result)
        except Exception as e:
            print(f"  ❌ 纯 AI 刮削失败: {e}")
            import traceback
            traceback.print_exc()
            ai_result = None
        
        # 方式2: TMDB+AI 刮削
        print("\n[2/2] TMDB+AI 刮削...")
        try:
            # 直接使用 metadata_scraper 的公开方法
            tmdb_ai_result = metadata_scraper.scrape(filename, [], conn)
            print_result("TMDB+AI 刮削结果", tmdb_ai_result)
        except Exception as e:
            print(f"  ❌ TMDB+AI 刮削失败: {e}")
            import traceback
            traceback.print_exc()
    
    conn.close()
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    print_separator("测试完成")


if __name__ == "__main__":
    main()

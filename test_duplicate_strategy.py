#!/usr/bin/env python3
"""
同名文件处理策略测试脚本
测试策略: skip, replace, rename, quality
"""
import os
import sys
import shutil
from media_importer.dedup_checker import check_duplicate, compare_quality, parse_filename_info

def setup_test_files():
    """创建测试文件"""
    os.makedirs('/tmp/res_test', exist_ok=True)
    os.makedirs('/tmp/test_quality', exist_ok=True)
    os.makedirs('/tmp/test_rename', exist_ok=True)
    os.makedirs('/tmp/test_replace', exist_ok=True)
    
    # 创建不同分辨率的测试文件
    with open('/tmp/res_test/movie.720p.mkv', 'w') as f:
        f.write('720p file content')
    with open('/tmp/res_test/movie.1080p.mkv', 'w') as f:
        f.write('1080p file content')
    with open('/tmp/res_test/movie.2160p.mkv', 'w') as f:
        f.write('2160p file content')
    with open('/tmp/res_test/movie.nores.mkv', 'w') as f:
        f.write('no resolution file')

def cleanup_test_files():
    """清理测试文件"""
    for dir in ['/tmp/res_test', '/tmp/test_quality', '/tmp/test_rename', '/tmp/test_replace']:
        if os.path.exists(dir):
            shutil.rmtree(dir)

def test_quality_comparison():
    """测试质量比较函数"""
    print("\n=== 质量比较函数测试 ===")
    
    test_cases = [
        ('movie.1080p.mkv', 'movie.720p.mkv', '1080p', '更高分辨率', 'replace'),
        ('movie.720p.mkv', 'movie.1080p.mkv', '720p', '更低分辨率', 'keep_existing'),
        ('movie.2160p.mkv', 'movie.1080p.mkv', '2160p', '4K vs 1080p', 'replace'),
        ('movie.1080p.mkv', 'movie.2160p.mkv', '1080p', '1080p vs 4K', 'keep_existing'),
        ('movie.1440p.mkv', 'movie.1080p.mkv', '1440p', '2K vs 1080p', 'replace'),
    ]
    
    all_passed = True
    for new_file, existing_file, new_res, desc, expected in test_cases:
        result = compare_quality(
            f'/tmp/res_test/{new_file}',
            f'/tmp/res_test/{existing_file}',
            {'resolution': new_res}
        )
        status = "✓" if result == expected else "✗"
        if result != expected:
            all_passed = False
        print(f"  {status} {desc}: {new_res} -> {parse_filename_info(existing_file).get('resolution') or 'unknown'} -> {result}")
    
    return all_passed

def test_quality_strategy():
    """测试质量优先策略"""
    print("\n=== 质量优先策略测试 ===")
    
    # 创建测试场景
    shutil.copy('/tmp/res_test/movie.720p.mkv', '/tmp/test_quality/Inception.2010.720p.mkv')
    
    scraped_info = {
        'title_cn': '盗梦空间',
        'title_en': 'Inception',
        'year': '2010',
        'type': 'movie',
        'video_file': 'Inception.2010.1080p.mkv'
    }
    
    # 场景1: 新文件分辨率更高
    scraped_info['resolution'] = '1080p'
    result = check_duplicate('/tmp/test_quality', scraped_info, 'quality', '/tmp/res_test/movie.1080p.mkv')
    assert result['is_duplicate'] == True
    assert result['quality_decision'] == 'replace'
    print("  ✓ 场景1: 新文件分辨率更高 -> replace")
    
    # 场景2: 新文件分辨率更低
    scraped_info['resolution'] = '480p'
    result = check_duplicate('/tmp/test_quality', scraped_info, 'quality', '/tmp/res_test/movie.nores.mkv')
    assert result['is_duplicate'] == True
    assert result['quality_decision'] == 'keep_existing'
    print("  ✓ 场景2: 新文件分辨率更低 -> keep_existing")
    
    return True

def test_rename_strategy():
    """测试重命名策略"""
    print("\n=== 重命名策略测试 ===")
    
    open('/tmp/test_rename/盗梦空间.2010.mkv', 'w').close()
    
    scraped_info = {
        'title_cn': '盗梦空间',
        'title_en': 'Inception',
        'year': '2010',
        'type': 'movie',
        'video_file': 'Inception.2010.mkv'
    }
    
    result = check_duplicate('/tmp/test_rename', scraped_info, 'rename')
    assert result['is_duplicate'] == True
    assert result['suggested_filename'] is not None
    assert 'copy1' in result['suggested_filename']
    print(f"  ✓ 生成重命名文件名: {os.path.basename(result['suggested_filename'])}")
    
    open('/tmp/test_rename/盗梦空间_2010_copy1.mkv', 'w').close()
    result2 = check_duplicate('/tmp/test_rename', scraped_info, 'rename')
    assert 'copy2' in result2['suggested_filename']
    print(f"  ✓ 已有copy1时生成: {os.path.basename(result2['suggested_filename'])}")
    
    return True

def test_replace_strategy():
    """测试替换策略"""
    print("\n=== 替换策略测试 ===")
    
    open('/tmp/test_replace/盗梦空间.2010.mkv', 'w').close()
    
    scraped_info = {
        'title_cn': '盗梦空间',
        'title_en': 'Inception',
        'year': '2010',
        'type': 'movie'
    }
    
    result = check_duplicate('/tmp/test_replace', scraped_info, 'replace')
    assert result['is_duplicate'] == True
    assert '替换已存在文件' in result['skip_message']
    print(f"  ✓ 替换消息正确: {result['skip_message']}")
    
    return True

def test_skip_strategy():
    """测试跳过策略"""
    print("\n=== 跳过策略测试 ===")
    
    scraped_info = {
        'title_cn': '盗梦空间',
        'year': '2010',
        'type': 'movie'
    }
    
    result = check_duplicate('/tmp/test_replace', scraped_info, 'skip')
    assert result['is_duplicate'] == True
    assert '同名文件已存在' in result['skip_message']
    print(f"  ✓ 跳过消息正确: {result['skip_message']}")
    
    return True

def test_filename_parsing():
    """测试文件名解析"""
    print("\n=== 文件名解析测试 ===")
    
    test_files = [
        'Inception.2010.1080p.BluRay.mkv',
        'Breaking.Bad.S01E01.720p.WEB-DL.mkv',
        '盗梦空间.Inception.2010.2160p.mkv',
        'Westworld.S01E02.1080p.BluRay.mkv',
    ]
    
    for filename in test_files:
        info = parse_filename_info(filename)
        print(f"  ✓ {filename}:")
        print(f"    - 中文标题: {info['title_cn']}")
        print(f"    - 英文标题: {info['title_en']}")
        print(f"    - 年份: {info['year']}")
        print(f"    - 分辨率: {info['resolution']}")
        print(f"    - 季/集: S{info['season']}E{info['episode']}" if info['season'] else "")
    
    return True

def test_all():
    """运行所有测试"""
    print("=" * 60)
    print("  同名文件处理策略测试")
    print("=" * 60)
    
    setup_test_files()
    
    results = []
    try:
        results.append(("质量比较", test_quality_comparison()))
        results.append(("质量策略", test_quality_strategy()))
        results.append(("重命名策略", test_rename_strategy()))
        results.append(("替换策略", test_replace_strategy()))
        results.append(("跳过策略", test_skip_strategy()))
        results.append(("文件名解析", test_filename_parsing()))
    finally:
        cleanup_test_files()
    
    print("\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("  所有测试通过!")
    else:
        print("  部分测试失败!")
    print("=" * 60)
    
    return all_passed

if __name__ == "__main__":
    success = test_all()
    sys.exit(0 if success else 1)

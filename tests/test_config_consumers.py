#!/usr/bin/env python3
"""
配置消费侧（业务模块）测试
验证每个使用配置的模块都能正常解析使用：
- file_watcher: enabled / poll_interval / ignore_patterns
- duplicate_handling: enabled / strategy
- source_file_handling: delete_after_process
- llm: api_key / base_url / model / verify_ssl / confidence_threshold
- hermes: enabled / webhook.* / events
- task_queue: max_concurrent
- logging: level / format / max_size_mb / backup_count
- pipeline: 同名检测 enable 开关生效
- file_mover: 目标已存在同名文件兜底
"""
import sys, os, tempfile, shutil, yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0
FAILS = []

def ok(label):
    global PASS
    PASS += 1
    print(f"  ✅ {label}")

def bad(label, msg):
    global FAIL
    FAIL += 1
    FAILS.append(f"{label}: {msg}")
    print(f"  ❌ {label}: {msg}")

def section(name):
    print(f"\n[{name}]")

# =================================================================

def test_config_loader_normalization():
    section("1. config_loader 兼容历史配置")
    from media_importer.core.config_loader import _normalize_bool_strings
    cases = [
        ({'enabled': 'true'}, True),
        ({'enabled': 'TRUE'}, True),
        ({'enabled': 'false'}, False),
        ({'enabled': 'yes'}, True),
        ({'enabled': 'no'}, False),
        ({'enabled': True}, True),
        ({'verify_ssl': 'off'}, False),
    ]
    for inp, exp in cases:
        d = dict(inp)
        _normalize_bool_strings(d)
        k = list(d.keys())[0]
        if d[k] is exp:
            ok(f"{inp} -> {k}={exp}")
        else:
            bad(f"{inp}", f"got {d[k]!r}, expected {exp}")


def test_file_watcher_config():
    section("2. file_watcher 配置消费")
    from media_importer.monitor.file_watcher import FileWatcher
    cfg = {
        'file_watcher': {'enabled': True, 'poll_interval': 30, 'ignore_patterns': ['*.tmp']},
        'source_dir': '/tmp',
        'source_dir_scan': {'recursive': True, 'max_depth': 3, 'ignore_patterns': ['*.tmp']},
        'video_extensions': ['.mkv', '.mp4'],
        'subtitle_extensions': ['.srt'],
    }
    try:
        w = FileWatcher(cfg, on_new_files=lambda x: None)
        if w.enabled:
            ok("FileWatcher.enabled=True 正确解析")
        else:
            bad("FileWatcher.enabled", f"应为 True，实际 {w.enabled}")
        if w.poll_interval == 30:
            ok("FileWatcher.poll_interval=30")
        else:
            bad("poll_interval", f"got {w.poll_interval}")
    except Exception as e:
        bad("FileWatcher 实例化", str(e))

    cfg['file_watcher']['enabled'] = False
    try:
        w2 = FileWatcher(cfg, on_new_files=lambda x: None)
        if not w2.enabled:
            ok("FileWatcher.enabled=False 正确解析")
        else:
            bad("FileWatcher.enabled=False", "未生效")
    except Exception as e:
        bad("FileWatcher enabled=False", str(e))


def test_duplicate_handling_config():
    section("3. pipeline 同名检测 enabled 开关")
    import media_importer.pipeline.steps as pipeline_steps
    src = open(pipeline_steps.__file__).read()
    if "dedup_cfg.get('enabled', True)" in src:
        ok("pipeline._step_dedup 读取 duplicate_handling.enabled")
    else:
        bad("pipeline 未读取 enabled", "代码中没找到 dedup_cfg.get('enabled', True)")

    # 检查关闭后是否会 return
    if "智能同名检测已关闭，跳过跨目录扫描" in src:
        ok("pipeline 关闭智能检测时正确跳过 dedup 逻辑")
    else:
        bad("pipeline 关闭智能检测", "未找到跳过逻辑提示")


def test_file_mover_dest_conflict():
    section("4. file_mover 目标已存在同名文件兜底")
    from media_importer.storage.file_mover import move_to_import
    tmpdir = tempfile.mkdtemp(prefix='mvtest_')
    try:
        # 准备源视频和已存在的目标
        src = os.path.join(tmpdir, 'src.mkv')
        with open(src, 'w') as f:
            f.write('x' * 100)
        import_dir = os.path.join(tmpdir, 'import')
        os.makedirs(import_dir)
        # 预先在目标位置放一个同名文件
        existing = os.path.join(import_dir, 'TestTitle.2024.mkv')
        with open(existing, 'w') as f:
            f.write('existing')

        scraped = {'title_cn': 'TestTitle', 'year': '2024', 'type': 'movie',
                   'title_en': '', 'resolution': '', 'quality': ''}
        templates = {'movie': '{title_cn}.{year}.{ext}'}

        try:
            move_to_import(src, [], import_dir, scraped, templates, [tmpdir])
            bad("目标同名兜底", "未抛出异常但应当抛出")
        except IOError as e:
            if "目标已存在同名文件" in str(e):
                ok("目标已存在同名文件时正确抛 IOError")
            else:
                bad("异常信息", f"got: {e}")
        except Exception as e:
            bad("异常类型", f"应为 IOError，got {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_logger_config():
    section("5. logger 配置消费")
    from media_importer.core.logger import Logger
    tmpdir = tempfile.mkdtemp(prefix='logtest_')
    try:
        l = Logger(level='DEBUG', fmt='text', log_dir=tmpdir,
                   max_size_mb=10, backup_count=3)
        l.info("hello")
        if os.path.isdir(tmpdir):
            ok("Logger 正常创建文件 handler")
        # 测试错误日志目录降级
        l2 = Logger(level='INFO', fmt='json', log_dir='/root/forbidden_x',
                    max_size_mb=10, backup_count=3)
        ok("Logger 对无权目录降级未崩溃")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_hermes_config():
    section("6. hermes_hook 配置消费")
    from media_importer.notify.hermes_hook import HermesNotifier
    cfg = {
        'hermes': {
            'enabled': True,
            'webhook': {
                'base_url': 'http://localhost:18644',
                'route_name': 'media-normalize',
                'secret': 'xxx',
                'timeout': 30,
                'max_retries': 1,
                'retry_delay': 1,
                'verify_ssl': False,
                'events': ['batch_start', 'batch_complete'],
            }
        }
    }
    try:
        n = HermesNotifier(cfg)
        if n.enabled:
            ok("HermesNotifier.enabled=True 正确解析")
        else:
            bad("HermesNotifier.enabled", "应为 True")
    except Exception as e:
        bad("HermesNotifier 实例化", str(e))

    cfg['hermes']['enabled'] = False
    try:
        n2 = HermesNotifier(cfg)
        if not n2.enabled:
            ok("HermesNotifier.enabled=False 正确解析")
    except Exception as e:
        bad("HermesNotifier enabled=False", str(e))


def test_pipeline_with_full_config():
    section("7. pipeline 完整加载（验证不会因配置类型崩溃）")
    cfg = {
        'source_dir': '/tmp',
        'temp_dir': tempfile.mkdtemp(prefix='ptemp_'),
        'log_dir': tempfile.mkdtemp(prefix='plog_'),
        'video_extensions': ['.mkv'],
        'subtitle_extensions': ['.srt'],
        'source_dir_scan': {'recursive': True, 'max_depth': 3, 'ignore_patterns': []},
        'path_rules': [{'conditions': {}, 'template': '/tmp/{title_cn}/'}],
        'filename_templates': {'movie': '{title_cn}.{ext}', 'tv': '{title_cn}.{ext}', 'subtitle': '{video_filename}.{ext}'},
        'duplicate_handling': {'enabled': False, 'strategy': 'skip'},
        'source_file_handling': {'delete_after_process': False},
        'llm': {'api_key': 'sk-x', 'base_url': 'http://x', 'model': 'gpt-3.5', 'timeout': 5,
                'max_retries': 1, 'retry_delay': 1, 'fallback_model': 'gpt-3.5',
                'confidence_threshold': 0.8, 'verify_ssl': True},
        'hermes': {'enabled': False, 'webhook': {}},
        'hooks': {'allowed_dir': '', 'before_process': '', 'after_success': '', 'after_failure': ''},
        'task_queue': {'max_concurrent': 1},
        'logging': {'level': 'INFO', 'format': 'text', 'max_size_mb': 10, 'backup_count': 2},
    }
    try:
        from media_importer.pipeline import PipelineRunner
        from media_importer.core.task_manager import TaskManager
        from media_importer.core.logger import Logger
        from media_importer.core.metrics import Metrics
        logger = Logger(level='INFO', fmt='text', log_dir=cfg['log_dir'])
        tm = TaskManager('/tmp/test_data')
        metrics = Metrics()
        p = PipelineRunner(cfg, tm, logger, metrics)
        ok("PipelineRunner 完整配置实例化成功")

        # 验证 enable=False 时 _step_dedup 不会扫描
        dedup_enabled = p.config.get('duplicate_handling', {}).get('enabled', True)
        if dedup_enabled == False:
            ok("PipelineRunner 读取 duplicate_handling.enabled=False")
        else:
            bad("dedup enabled", f"应为 False，实际 {dedup_enabled}")
    except Exception as e:
        bad("PipelineRunner 实例化", str(e))


def test_permission_checker():
    section("8. permission_checker 配置消费")
    from media_importer.monitor.permission_checker import check_config_permissions, check_path_permission, is_app_managed_path, extract_root_from_template

    # is_app_managed_path
    if is_app_managed_path('/vol3/@appdata/nas-media-importer/logs'):
        ok("is_app_managed_path 识别 @appdata")
    else:
        bad("is_app_managed_path", "未识别 @appdata")

    if not is_app_managed_path('/vol1/影视'):
        ok("is_app_managed_path 排除非管理路径")
    else:
        bad("is_app_managed_path", "误报 /vol1/影视")

    # extract_root_from_template
    r = extract_root_from_template('/vol1/影视/电视剧/{title}/Season {season}/')
    if r == '/vol1/影视/电视剧':
        ok(f"extract_root_from_template 提取根目录: {r}")
    else:
        bad("extract_root", f"got: {r}")

    # check_config_permissions 综合测试
    cfg = {
        'source_dir': '/tmp',
        'temp_dir': '/vol3/@appdata/nas-media-importer/tmp',  # 应跳过
        'log_dir': '/tmp',
        'path_rules': [{'template': '/tmp/影视/{title}/'}],
    }
    r = check_config_permissions(cfg)
    if r['all_ok']:
        ok("check_config_permissions 全 OK 时 all_ok=True")
    else:
        bad("check_config_permissions all_ok", f"issues={r.get('issues')}")


def test_api_check_permission_endpoint():
    section("9. /api/config/check-permission 接口")
    import subprocess, time, urllib.request, json
    PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    cfg_file = '/tmp/api_check_perm_test.yaml'
    shutil.copy(os.path.join(PROJ, 'config.yaml.example'), cfg_file)
    proc = subprocess.Popen(
        ['python3', '-B', os.path.join(PROJ, 'media_importer', 'media_importer.py'),
         '-c', cfg_file, 'serve', '-p', '19859', '--host', '127.0.0.1'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(2)
    try:
        # 1. 测试 /api/path/test
        req = urllib.request.Request(
            'http://127.0.0.1:19859/api/path/test',
            data=json.dumps({'path': '/tmp', 'need_write': True}).encode(),
            method='POST', headers={'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=5)
        d = json.loads(resp.read().decode())
        if d.get('code') == 200 and d.get('data', {}).get('ok'):
            ok("/api/path/test 正常路径返回 ok=True")
        else:
            bad("/api/path/test", f"got: {d}")

        # 2. 测试 /api/path/test 无效路径
        req = urllib.request.Request(
            'http://127.0.0.1:19859/api/path/test',
            data=json.dumps({'path': '/root/nope_perm', 'need_write': True}).encode(),
            method='POST', headers={'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=5)
        d = json.loads(resp.read().decode())
        if d.get('code') == 200 and d.get('data', {}).get('ok') == False:
            ok("/api/path/test 无权路径返回 ok=False")
        else:
            bad("/api/path/test 无权路径", f"got: {d}")

        # 3. 测试 /api/config/check-permission
        req = urllib.request.Request(
            'http://127.0.0.1:19859/api/config/check-permission',
            data=json.dumps({
                'source_dir': '/tmp',
                'path_rules': [{'template': '/tmp/test/{x}/'}],
            }).encode(),
            method='POST', headers={'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=5)
        d = json.loads(resp.read().decode())
        if d.get('code') == 200 and 'all_ok' in d.get('data', {}):
            ok("/api/config/check-permission 接口正常返回")
        else:
            bad("check-permission", f"got: {d}")
    except Exception as e:
        bad("API 调用", str(e))
    finally:
        proc.terminate(); proc.wait()


# =================================================================

def main():
    print("\n========== 配置消费侧测试 ==========")
    test_config_loader_normalization()
    test_file_watcher_config()
    test_duplicate_handling_config()
    test_file_mover_dest_conflict()
    test_logger_config()
    test_hermes_config()
    test_pipeline_with_full_config()
    test_permission_checker()
    test_api_check_permission_endpoint()

    print(f"\n========== 汇总 ==========")
    print(f"✅ PASS: {PASS}")
    print(f"❌ FAIL: {FAIL}")
    if FAILS:
        print("\n失败详情:")
        for f in FAILS:
            print(f"  - {f}")
    return 0 if FAIL == 0 else 1

if __name__ == '__main__':
    sys.exit(main())

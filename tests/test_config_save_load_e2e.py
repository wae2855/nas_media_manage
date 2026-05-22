#!/usr/bin/env python3
"""
配置保存/读取端到端测试
覆盖：所有配置字段的保存→重载→使用
验证：bool/int/float/str/list/dict 各类型都不被破坏
"""
import sys, os, json, shutil, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'media_importer'))

import yaml
from ruamel.yaml import YAML

PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEST_DIR = '/tmp/cfg_test_e2e'
TEST_CONFIG = os.path.join(TEST_DIR, 'config.yaml')
PORT = 19858

PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES = []

def setup():
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR)
    shutil.copy(os.path.join(PROJ, 'config.yaml.example'), TEST_CONFIG)
    print(f"[setup] 测试目录: {TEST_DIR}")

def start_server():
    proc = subprocess.Popen(
        ['python3', '-B', os.path.join(PROJ, 'media_importer', 'media_importer.py'),
         '-c', TEST_CONFIG, 'serve', '-p', str(PORT), '--host', '127.0.0.1'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(2)
    return proc

API_KEY = None

def call_api(method, endpoint, body=None):
    import urllib.request
    url = f'http://127.0.0.1:{PORT}/api{endpoint}'
    data = None
    headers = {'Content-Type': 'application/json'}
    if API_KEY:
        headers['Authorization'] = f'Bearer {API_KEY}'
    if body is not None:
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        try:
            return json.loads(body)
        except Exception:
            return {'code': e.code, 'message': body}
    except Exception as e:
        return {'code': 500, 'message': str(e)}

def assert_eq(label, got, exp):
    global PASS_COUNT, FAIL_COUNT
    if got == exp:
        PASS_COUNT += 1
        print(f"  ✅ {label}")
        return True
    else:
        FAIL_COUNT += 1
        msg = f"❌ {label}\n     got: {got!r}\n     exp: {exp!r}"
        FAILURES.append(msg)
        print(f"  {msg}")
        return False

def assert_type(label, got, exp_type):
    global PASS_COUNT, FAIL_COUNT
    if isinstance(got, exp_type):
        PASS_COUNT += 1
        print(f"  ✅ {label} (类型: {exp_type.__name__})")
        return True
    else:
        FAIL_COUNT += 1
        msg = f"❌ {label} 类型错误\n     got: {type(got).__name__}={got!r}\n     exp type: {exp_type.__name__}"
        FAILURES.append(msg)
        print(f"  {msg}")
        return False

def load_yaml_raw(path):
    """读取 yaml 文件保留原始字符串（不解析）"""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def load_yaml_parsed(path):
    """安全解析 yaml"""
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def _check_bool_pollution(raw):
    lines = raw.split('\n')
    in_dimensions = False
    bad = []
    for i, line in enumerate(lines):
        if line.startswith('dimensions:'):
            in_dimensions = True; continue
        if in_dimensions and line and not line.startswith(' ') and not line.startswith('-') and not line.startswith('#') and not line.startswith('\t'):
            in_dimensions = False
        if in_dimensions:
            continue
        if (": 'true'" in line or ": 'false'" in line
            or "- 'true'" in line or "- 'false'" in line):
            bad.append((i+1, line))
    return bad


# =========================================================
# 主测试流程
# =========================================================
def main():
    global PASS_COUNT, FAIL_COUNT, API_KEY
    print("\n========== 配置保存/读取端到端测试 ==========\n")
    setup()
    proc = start_server()

    try:
        # ---------- 阶段1: 健康检查 ----------
        print("\n[阶段1] 服务启动验证")
        r = call_api('GET', '/health')
        assert_eq("/api/health 返回 200", r.get('code'), 200)

        # ---------- 阶段2: 读取初始配置 ----------
        print("\n[阶段2] 读取初始配置 GET /api/config")
        r = call_api('GET', '/config')
        assert_eq("/api/config 返回 200", r.get('code'), 200)
        initial = r.get('data', {}).get('config', {})
        assert_type("file_watcher.enabled 应为 bool", initial.get('file_watcher', {}).get('enabled'), bool)
        assert_eq("file_watcher.enabled 初值 true", initial.get('file_watcher', {}).get('enabled'), True)
        assert_type("file_watcher.poll_interval 应为 int", initial.get('file_watcher', {}).get('poll_interval'), int)
        assert_type("source_dir 应为 str", initial.get('source_dir'), str)
        assert_type("duplicate_handling.enabled 应为 bool", initial.get('duplicate_handling', {}).get('enabled'), bool)
        assert_type("hermes.enabled 应为 bool", initial.get('hermes', {}).get('enabled'), bool)
        assert_type("hermes.webhook.events 应为 list", initial.get('hermes', {}).get('webhook', {}).get('events'), list)

        # ---------- 阶段3: 全量字段保存测试 ----------
        print("\n[阶段3] 全量保存 → POST /api/config（含各种类型）")
        full_config = {
            # bool 多处
            'file_watcher': {
                'enabled': False,                     # bool false
                'poll_interval': 120,                 # int
                'ignore_patterns': ['*.tmp', '*.crdownload'],   # list[str]
            },
            'server': {
                'host': '0.0.0.0',
                'port': 9855,
                'api_key': 'test_key_abc123',
            },
            'source_dir': '/tmp/cfg_test_e2e/source',
            'temp_dir': '/tmp/cfg_test_e2e/tmp',
            'log_dir': '/tmp/cfg_test_e2e/logs',
            'source_dir_scan': {
                'recursive': True,
                'max_depth': 7,
                'ignore_patterns': ['*.tmp'],
            },
            'video_extensions': ['.mkv', '.mp4'],
            'subtitle_extensions': ['.srt', '.ass'],
            'dimensions': initial.get('dimensions', []),
            'path_rules': [
                {'conditions': {'media_type': 'tv'}, 'template': '/tmp/cfg_test_e2e/TV/{title}/'},
                {'conditions': {'media_type': 'movie'}, 'template': '/tmp/cfg_test_e2e/Movie/{title}/'},
            ],
            'filename_templates': {
                'movie': '{title_cn}.{year}.{ext}',
                'tv': '{title_cn}.S{season:02d}E{episode:02d}.{ext}',
                'subtitle': '{video_filename}.{lang}.{ext}',
            },
            'duplicate_handling': {
                'enabled': False,                     # 关键 - 之前出 bug 的字段
                'strategy': 'replace',
            },
            'source_file_handling': {
                'delete_after_process': False,         # bool false
            },
            'llm': {
                'provider': 'openai',
                'api_key': 'sk-test',
                'base_url': 'https://api.openai.com/v1',
                'model': 'gpt-4',
                'timeout': 60,
                'max_retries': 3,
                'retry_delay': 5,
                'fallback_model': 'gpt-3.5-turbo',
                'confidence_threshold': 0.9,           # float
                'verify_ssl': False,                   # bool false
            },
            'hermes': {
                'enabled': True,                       # bool true
                'webhook': {
                    'base_url': 'http://localhost:8644',
                    'route_name': 'test-route',
                    'secret': 'xxx',
                    'timeout': 30,
                    'max_retries': 3,
                    'retry_delay': 5,
                    'verify_ssl': True,                # bool true
                    'events': ['batch_start', 'batch_complete'],
                }
            },
            'task_queue': {
                'persistence_path': '/tmp/cfg_test_e2e/tasks.json',
                'max_concurrent': 2,
            },
            'hooks': {
                'allowed_dir': '/tmp/cfg_test_e2e/hooks',
                'before_process': '',
                'after_success': '',
                'after_failure': '',
            },
            'logging': {
                'level': 'DEBUG',
                'format': 'text',
                'max_size_mb': 50,
                'backup_count': 10,
            },
        }
        r = call_api('POST', '/config', full_config)
        assert_eq("POST /api/config 返回 200", r.get('code'), 200)
        API_KEY = 'test_key_abc123'

        # ---------- 阶段4: 文件原始内容验证（无 'true' 等字符串污染） ----------
        print("\n[阶段4] YAML 文件原始内容验证")
        raw = load_yaml_raw(TEST_CONFIG)
        # 不应该出现 'true'/'false' 字符串包装（排除 dimensions 中的合法字符串值）
        # dimensions 段中的 values 故意定义为字符串 'true'/'false'，那是分类标签
        lines = raw.split('\n')
        in_dimensions = False
        bad_lines = []
        for i, line in enumerate(lines):
            if line.startswith('dimensions:'):
                in_dimensions = True
                continue
            # dimensions 段结束：遇到下一个顶层字段
            if in_dimensions and line and not line.startswith(' ') and not line.startswith('-') and not line.startswith('#') and not line.startswith('\t'):
                in_dimensions = False
            if in_dimensions:
                continue
            if (": 'true'" in line or ": 'false'" in line
                or "- 'true'" in line or "- 'false'" in line):
                bad_lines.append((i+1, line))
        if bad_lines:
            FAIL_COUNT += 1
            msg = "❌ YAML 中出现 bool 字符串污染:"
            for ln, line in bad_lines:
                msg += f"\n     L{ln}: {line.strip()}"
            FAILURES.append(msg)
            print(f"  {msg}")
        else:
            PASS_COUNT += 1
            print(f"  ✅ YAML 中所有 bool 都是真布尔，无 'true'/'false' 字符串污染")

        # ---------- 阶段5: yaml.safe_load 反序列化验证 ----------
        print("\n[阶段5] yaml.safe_load 反序列化验证")
        parsed = load_yaml_parsed(TEST_CONFIG)
        assert_eq("file_watcher.enabled", parsed['file_watcher']['enabled'], False)
        assert_type("file_watcher.enabled 是 bool", parsed['file_watcher']['enabled'], bool)
        assert_eq("file_watcher.poll_interval", parsed['file_watcher']['poll_interval'], 120)
        assert_type("file_watcher.poll_interval 是 int", parsed['file_watcher']['poll_interval'], int)
        assert_eq("file_watcher.ignore_patterns", parsed['file_watcher']['ignore_patterns'], ['*.tmp', '*.crdownload'])
        assert_eq("source_dir", parsed['source_dir'], '/tmp/cfg_test_e2e/source')
        assert_eq("source_dir_scan.recursive", parsed['source_dir_scan']['recursive'], True)
        assert_type("source_dir_scan.recursive 是 bool", parsed['source_dir_scan']['recursive'], bool)
        assert_eq("duplicate_handling.enabled", parsed['duplicate_handling']['enabled'], False)
        assert_type("duplicate_handling.enabled 是 bool", parsed['duplicate_handling']['enabled'], bool)
        assert_eq("duplicate_handling.strategy", parsed['duplicate_handling']['strategy'], 'replace')
        assert_eq("source_file_handling.delete_after_process", parsed['source_file_handling']['delete_after_process'], False)
        assert_type("source_file_handling.delete_after_process 是 bool", parsed['source_file_handling']['delete_after_process'], bool)
        assert_eq("llm.verify_ssl", parsed['llm']['verify_ssl'], False)
        assert_type("llm.verify_ssl 是 bool", parsed['llm']['verify_ssl'], bool)
        assert_eq("llm.confidence_threshold", parsed['llm']['confidence_threshold'], 0.9)
        assert_type("llm.confidence_threshold 是 float", parsed['llm']['confidence_threshold'], float)
        assert_eq("hermes.enabled", parsed['hermes']['enabled'], True)
        assert_eq("hermes.webhook.verify_ssl", parsed['hermes']['webhook']['verify_ssl'], True)
        assert_eq("hermes.webhook.events", parsed['hermes']['webhook']['events'], ['batch_start', 'batch_complete'])
        assert_eq("path_rules[0].template", parsed['path_rules'][0]['template'], '/tmp/cfg_test_e2e/TV/{title}/')
        assert_eq("path_rules count", len(parsed['path_rules']), 2)
        assert_eq("filename_templates.movie", parsed['filename_templates']['movie'], '{title_cn}.{year}.{ext}')
        assert_eq("task_queue.max_concurrent", parsed['task_queue']['max_concurrent'], 2)
        assert_eq("logging.level", parsed['logging']['level'], 'DEBUG')
        assert_eq("logging.max_size_mb", parsed['logging']['max_size_mb'], 50)
        assert_type("logging.max_size_mb 是 int", parsed['logging']['max_size_mb'], int)

        # ---------- 阶段6: API 重新读取验证 ----------
        print("\n[阶段6] GET /api/config 读回验证类型保持")
        r = call_api('GET', '/config')
        rd = r.get('data', {}).get('config', {})
        assert_type("read-back file_watcher.enabled 是 bool", rd['file_watcher']['enabled'], bool)
        assert_eq("read-back file_watcher.enabled = False", rd['file_watcher']['enabled'], False)
        assert_type("read-back duplicate_handling.enabled 是 bool", rd['duplicate_handling']['enabled'], bool)
        assert_eq("read-back duplicate_handling.enabled = False", rd['duplicate_handling']['enabled'], False)
        assert_type("read-back llm.confidence_threshold 是 float", rd['llm']['confidence_threshold'], float)
        assert_eq("read-back hermes.webhook.events", rd['hermes']['webhook']['events'], ['batch_start', 'batch_complete'])

        # ---------- 阶段7: 再次保存（往返一致性）----------
        print("\n[阶段7] 二次保存（往返一致性）")
        r2 = call_api('POST', '/config', rd)
        assert_eq("二次 POST /api/config 返回 200", r2.get('code'), 200)
        raw2 = load_yaml_raw(TEST_CONFIG)
        bad2 = _check_bool_pollution(raw2)
        if bad2:
            FAIL_COUNT += 1
            msg = "❌ 二次保存后出现 bool 字符串污染: " + str(bad2)
            FAILURES.append(msg)
            print(f"  {msg}")
        else:
            PASS_COUNT += 1
            print(f"  ✅ 二次保存后仍无 bool 字符串污染")

        # ---------- 阶段8: 验证字段位置不会错位 ----------
        print("\n[阶段8] 字段位置验证（重点：不能错位到下一段）")
        # 找 duplicate_handling 段，确保 enabled 在它内部
        in_dup = False
        dup_section_lines = []
        for line in raw2.split('\n'):
            if line.startswith('duplicate_handling:'):
                in_dup = True
                dup_section_lines.append(line)
                continue
            if in_dup:
                if line.startswith('source_file_handling:') or line.startswith('#'):
                    if line.startswith('source_file_handling:'):
                        break
                    if not line.strip():
                        continue
                    if line.startswith('# ---') or line.startswith('# 6.'):
                        continue
                if line and not line.startswith(' ') and not line.startswith('#') and not line.startswith('\t'):
                    break
                dup_section_lines.append(line)
        dup_block = '\n'.join(dup_section_lines)
        if 'enabled' in dup_block and 'strategy' in dup_block:
            PASS_COUNT += 1
            print(f"  ✅ duplicate_handling 块内同时包含 enabled 和 strategy")
        else:
            FAIL_COUNT += 1
            msg = f"❌ duplicate_handling 块缺字段，块内容:\n{dup_block}"
            FAILURES.append(msg)
            print(f"  {msg}")

        # ---------- 阶段9: 配置兼容性 — 模拟历史 'true' 字符串读入 ----------
        print("\n[阶段9] 兼容性 — 处理历史 'true'/'false' 字符串配置")
        # 写入一份带历史字符串污染的 config
        legacy_config = """
file_watcher:
  enabled: 'true'
  poll_interval: 60
  ignore_patterns: []
server:
  host: "0.0.0.0"
  port: 9855
  api_key: ""
source_dir: "/tmp/cfg_test_e2e/source"
temp_dir: "/tmp/cfg_test_e2e/tmp"
log_dir: "/tmp/cfg_test_e2e/logs"
source_dir_scan:
  recursive: 'true'
  max_depth: 5
  ignore_patterns: []
video_extensions: [".mkv"]
subtitle_extensions: [".srt"]
dimensions: []
path_rules: []
filename_templates:
  movie: ""
  tv: ""
  subtitle: ""
duplicate_handling:
  enabled: 'false'
  strategy: "skip"
source_file_handling:
  delete_after_process: 'true'
llm:
  api_key: ""
  base_url: ""
  model: ""
  verify_ssl: 'false'
  confidence_threshold: 0.8
hermes:
  enabled: 'true'
  webhook:
    verify_ssl: 'false'
    events: []
task_queue:
  persistence_path: ""
  max_concurrent: 1
hooks:
  allowed_dir: ""
logging:
  level: "INFO"
"""
        with open(TEST_CONFIG, 'w') as f:
            f.write(legacy_config)
        # 重启服务读取（旧字符串应能被识别）
        proc.terminate(); proc.wait()
        time.sleep(0.5)
        proc = start_server()
        API_KEY = None  # legacy_config 没有 api_key

        r = call_api('GET', '/config')
        rd = r.get('data', {}).get('config', {})
        # 旧字符串 'true' 应在 GET 时被 _normalize_bool_strings 处理（在 config_loader 加载时已转换）
        # 后端使用层应能识别字符串 'true' 等同于 True
        from config_loader import _normalize_bool_strings, BOOL_TRUE_STRINGS, BOOL_FALSE_STRINGS, BOOL_KEYS

        test_cases = [
            ({'enabled': 'true'}, True),
            ({'enabled': 'false'}, False),
            ({'enabled': 'yes'}, True),
            ({'enabled': 'no'}, False),
            ({'enabled': 'on'}, True),
            ({'enabled': 'off'}, False),
            ({'enabled': True}, True),
            ({'enabled': False}, False),
            ({'verify_ssl': 'TRUE'}, True),
            ({'delete_after_process': 'False'}, False),
            ({'recursive': 'yes'}, True),
        ]
        for input_dict, expected in test_cases:
            d = dict(input_dict)
            _normalize_bool_strings(d)
            key = list(d.keys())[0]
            assert_eq(f"_normalize_bool_strings({input_dict!r}) -> {key}={d[key]!r}", d[key], expected)

        nested = {'hermes': {'enabled': 'yes', 'webhook': {'verify_ssl': 'off'}}}
        _normalize_bool_strings(nested)
        assert_eq("嵌套兼容 hermes.enabled='yes' -> True", nested['hermes']['enabled'], True)
        assert_eq("嵌套兼容 hermes.webhook.verify_ssl='off' -> False",
                  nested['hermes']['webhook']['verify_ssl'], False)

        # ---------- 阶段10: 再次保存后字符串污染会被洗掉 ----------
        print("\n[阶段10] 老污染配置经一次保存后被洗成真布尔")
        r3 = call_api('POST', '/config', rd)
        assert_eq("POST 清洗保存 返回 200", r3.get('code'), 200)
        raw3 = load_yaml_raw(TEST_CONFIG)
        bad3 = _check_bool_pollution(raw3)
        if bad3:
            FAIL_COUNT += 1
            msg = "❌ 老污染配置保存后仍残留: " + str(bad3)
            FAILURES.append(msg)
            print(f"  {msg}")
        else:
            PASS_COUNT += 1
            print(f"  ✅ 老污染配置经一次保存后所有 bool 被洗成真布尔")

    finally:
        proc.terminate()
        proc.wait()

    # ---------- 汇总 ----------
    print(f"\n========== 测试汇总 ==========")
    print(f"✅ PASS: {PASS_COUNT}")
    print(f"❌ FAIL: {FAIL_COUNT}")
    if FAILURES:
        print(f"\n失败详情:")
        for f in FAILURES:
            print(f"  {f}")
    return 0 if FAIL_COUNT == 0 else 1

if __name__ == '__main__':
    sys.exit(main())

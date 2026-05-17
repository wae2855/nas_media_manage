#!/usr/bin/env python3
"""
端到端全流程测试 — 使用真实 LLM API + 真实文件操作 + Hermes 通知

测试环境: tests/fixtures/ 目录模拟 NAS 目录结构
  - source/   → 挂载网盘源目录（含14个视频+17个字幕）
  - temp/     → 临时目录
  - import/   → 入库目标目录
  - logs/     → 日志目录

运行方式:
  python3 tests/e2e_test.py
  python3 tests/e2e_test.py --skip-hermes    # 跳过 Hermes 通知测试
"""
import json
import os
import sys
import time
import shutil
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'media_importer'))

from config_loader import load_config
from task_manager import TaskManager
from pipeline import PipelineRunner, PIPELINE_STEPS
from metrics import Metrics, get_metrics
from logger import get_logger
from hermes_hook import HermesNotifier
from file_scanner import scan_source_dir

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_DIR = os.path.join(PROJECT_ROOT, "tests", "fixtures")
API_BASE = "http://127.0.0.1:9855"

RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
CYAN = '\033[0;36m'
NC = '\033[0m'


def log_step(step_num, message):
    print(f"\n{CYAN}{'='*60}")
    print(f"  Step {step_num}: {message}")
    print(f"{'='*60}{NC}")


def log_pass(message):
    print(f"  {GREEN}✅ {message}{NC}")


def log_fail(message):
    print(f"  {RED}❌ {message}{NC}")


def log_info(message):
    print(f"  {YELLOW}ℹ️  {message}{NC}")


def api_request(method, path, body=None):
    url = f"{API_BASE}{path}"
    headers = {}
    data = None
    if body and method in ("POST", "DELETE"):
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return e.code, {"raw": raw.decode("utf-8", errors="replace")}
    except Exception as e:
        return 0, {"error": str(e)}


def check_server_running():
    status, body = api_request("GET", "/api/health")
    return status == 200


def prepare_test_env():
    source_dir = os.path.join(FIXTURES_DIR, "source")
    temp_dir = os.path.join(FIXTURES_DIR, "temp")
    import_dir = os.path.join(FIXTURES_DIR, "import")
    log_dir = os.path.join(FIXTURES_DIR, "logs")

    for d in [temp_dir, import_dir, log_dir]:
        if os.path.exists(d):
            for item in os.listdir(d):
                item_path = os.path.join(d, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    if item != "media_importer.log" and not item.endswith(".json"):
                        os.remove(item_path)
        os.makedirs(d, exist_ok=True)

    tasks_json = os.path.join(PROJECT_ROOT, "tasks.json")
    if os.path.exists(tasks_json):
        os.remove(tasks_json)

    return source_dir, temp_dir, import_dir, log_dir


def step_1_check_server():
    log_step(1, "检查 API 服务状态")
    if not check_server_running():
        log_fail("API 服务未运行，请先启动: ./start.sh")
        return False

    status, body = api_request("GET", "/api/health")
    log_pass(f"服务运行中，状态: {body['data']['status']}")
    for name, result in body['data']['checks'].items():
        icon = "✅" if result == "ok" else "⚠️"
        print(f"    {icon} {name}: {result}")
    return True


def step_2_scan_source():
    log_step(2, "扫描源目录 — 验证文件发现能力")
    config = load_config(os.path.join(PROJECT_ROOT, "media_importer", "config.yaml"))
    groups = scan_source_dir(config.get("source_dir", ""), config)

    log_pass(f"扫描到 {len(groups)} 个视频文件组")
    for g in groups:
        sub_count = len(g.get('subtitles', []))
        print(f"    📹 {os.path.basename(g['video'])} ({sub_count} 字幕)")

    expected_videos = 14
    if len(groups) == expected_videos:
        log_pass(f"视频数量正确 ({expected_videos})")
    else:
        log_fail(f"视频数量不符: 期望 {expected_videos}, 实际 {len(groups)}")

    return len(groups)


def step_3_trigger_batch():
    log_step(3, "触发批量处理 — POST /api/run")
    status, body = api_request("POST", "/api/run")
    if status == 202:
        log_pass(f"批量处理已触发: {body['message']}")
    else:
        log_fail(f"触发失败: status={status}, body={body}")
    return status == 202


def step_4_wait_and_monitor():
    log_step(4, "等待处理完成 — 轮询任务状态")
    max_wait = 300
    start = time.time()

    while time.time() - start < max_wait:
        status, body = api_request("GET", "/api/tasks")
        if status != 200:
            time.sleep(3)
            continue

        tasks = body['data']['tasks']
        total = body['data']['total']
        if total == 0:
            time.sleep(3)
            continue

        processing = [t for t in tasks if t['status'] == 'PROCESSING']
        pending = [t for t in tasks if t['status'] == 'PENDING']
        success = [t for t in tasks if t['status'] == 'SUCCESS']
        failed = [t for t in tasks if t['status'] == 'FAILED']
        skipped = [t for t in tasks if t['status'] == 'SKIPPED']

        elapsed = int(time.time() - start)
        print(f"\r    [{elapsed}s] 总={total} 处理中={len(processing)} "
              f"待处理={len(pending)} 成功={len(success)} "
              f"失败={len(failed)} 跳过={len(skipped)}", end="", flush=True)

        if len(processing) == 0 and len(pending) == 0 and total > 0:
            print()
            log_pass(f"全部任务完成! 成功={len(success)} 失败={len(failed)} 跳过={len(skipped)}")
            return True

        time.sleep(5)

    print()
    log_fail(f"等待超时 ({max_wait}s)")
    return False


def step_5_check_task_details():
    log_step(5, "检查任务详情 — GET /api/tasks/{id}")
    status, body = api_request("GET", "/api/tasks")
    if status != 200:
        log_fail("获取任务列表失败")
        return

    tasks = body['data']['tasks']
    for task in tasks[:3]:
        tid = task['task_id']
        s, b = api_request("GET", f"/api/tasks/{tid}")
        if s == 200:
            d = b['data']
            log_pass(f"任务 {tid}: {d['video_file']} → {d['status']} "
                     f"({d['current_step']}/{d['total_steps']} {d['step_name']})")
            if d.get('import_path'):
                print(f"       入库路径: {d['import_path']}")
            if d.get('error_message'):
                print(f"       错误信息: {d['error_message']}")


def step_6_check_import_dir(import_dir):
    log_step(6, "检查入库目录 — 验证文件已正确入库")
    if not os.path.exists(import_dir):
        log_fail(f"入库目录不存在: {import_dir}")
        return

    imported_files = []
    for root, dirs, files in os.walk(import_dir):
        for f in files:
            imported_files.append(os.path.join(root, f))

    log_pass(f"入库目录中共有 {len(imported_files)} 个文件")
    for f in imported_files[:10]:
        print(f"    📄 {os.path.relpath(f, import_dir)}")
    if len(imported_files) > 10:
        print(f"    ... 还有 {len(imported_files) - 10} 个文件")


def step_7_check_logs(log_dir):
    log_step(7, "检查日志输出 — 验证日志格式和内容")
    log_file = os.path.join(log_dir, "media_importer.log")
    if not os.path.exists(log_file):
        log_fail(f"日志文件不存在: {log_file}")
        return

    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    log_pass(f"日志文件 {len(lines)} 行")

    json_lines = 0
    text_lines = 0
    error_lines = 0
    for line in lines[-50:]:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
            json_lines += 1
            if obj.get('level') == 'ERROR':
                error_lines += 1
        except json.JSONDecodeError:
            text_lines += 1

    print(f"    JSON 日志: {json_lines} 行, 文本日志: {text_lines} 行, 错误: {error_lines} 行")

    if error_lines > 0:
        log_info("最近错误日志:")
        for line in lines[-20:]:
            try:
                obj = json.loads(line.strip())
                if obj.get('level') == 'ERROR':
                    print(f"      {obj.get('message', '')[:100]}")
            except Exception:
                pass


def step_8_check_metrics():
    log_step(8, "检查运行指标 — GET /api/metrics")
    status, body = api_request("GET", "/api/metrics")
    if status == 200:
        d = body['data']
        log_pass(f"总任务: {d['total_tasks']}, 成功: {d['success_tasks']}, "
                 f"失败: {d['failed_tasks']}, 跳过: {d['skipped_tasks']}")
        log_pass(f"成功率: {d['success_rate']*100:.1f}%, "
                 f"平均耗时: {d['avg_processing_time_seconds']:.1f}s, "
                 f"运行时间: {d['uptime']}")
    else:
        log_fail(f"获取指标失败: {status}")


def step_9_hermes_interaction(skip_hermes=False):
    log_step(9, "Hermes Skill 交互测试")
    if skip_hermes:
        log_info("跳过 Hermes 测试 (--skip-hermes)")
        log_info("请在 Hermes 对话中手动测试以下命令:")
        print("    1. 查询任务列表: \"帮我看看NAS入库任务状态\"")
        print("    2. 查看失败任务: \"有没有失败的任务\"")
        print("    3. 查看健康状态: \"NAS入库系统健康吗\"")
        print("    4. 查看指标: \"入库系统运行指标\"")
        return

    log_info("请在 Hermes 对话中执行以下测试，观察返回结果:")
    print()
    print("  测试1: 查询任务列表")
    print("    命令: \"帮我看看NAS入库任务状态\"")
    print("    预期: 返回任务列表，包含状态/文件名/进度")
    print()
    print("  测试2: 查看失败任务")
    print("    命令: \"有没有失败的任务\"")
    print("    预期: 列出 FAILED 状态的任务及错误原因")
    print()
    print("  测试3: 健康检查")
    print("    命令: \"NAS入库系统健康吗\"")
    print("    预期: 返回各组件状态 (source_dir/temp_dir/llm_api/hermes/disk_space)")
    print()
    print("  测试4: 运行指标")
    print("    命令: \"入库系统运行指标\"")
    print("    预期: 返回成功率/平均耗时/LLM调用次数等")
    print()
    print("  测试5: 通知验证")
    print("    预期: 飞书应收到 task_complete/task_failed/task_skipped/batch_complete 通知")
    print()

    input("  完成后按 Enter 继续...")


def step_10_retry_failed():
    log_step(10, "重试失败任务 — POST /api/queue/retry-all")
    status, body = api_request("GET", "/api/tasks?status=FAILED")
    if status != 200:
        log_fail("获取失败任务失败")
        return

    failed_tasks = body['data']['tasks']
    if not failed_tasks:
        log_pass("没有失败任务需要重试")
        return

    log_info(f"发现 {len(failed_tasks)} 个失败任务")
    for t in failed_tasks:
        print(f"    ❌ {t['video_file']}: {t.get('error_message', '未知错误')[:80]}")

    status, body = api_request("POST", "/api/queue/retry-all")
    if status == 200:
        log_pass(f"已重试 {body['data']['retried_count']} 个失败任务")
    else:
        log_fail(f"重试失败: {status}")


def step_11_permission_test():
    log_step(11, "权限异常测试 — 验证无权限场景的处理")
    source_dir = os.path.join(FIXTURES_DIR, "source")

    test_file = os.path.join(source_dir, "_perm_test.mkv")
    with open(test_file, 'w') as f:
        f.write("permission test")
    os.chmod(test_file, 0o000)

    status, body = api_request("POST", "/api/run/file",
                               {"path": test_file})
    log_info(f"处理无权限文件: status={status}")

    os.chmod(test_file, 0o644)
    os.remove(test_file)

    log_pass("权限测试完成（无权限文件应被标记为 FAILED）")


def step_12_duplicate_test():
    log_step(12, "同名文件测试 — 验证跳过逻辑")
    status, body = api_request("GET", "/api/tasks?status=SKIPPED")
    if status == 200:
        skipped = body['data']['tasks']
        if skipped:
            log_pass(f"发现 {len(skipped)} 个跳过任务（同名文件）")
            for t in skipped[:3]:
                print(f"    ⏭️ {t['video_file']}: {t.get('error_message', '')[:80]}")
        else:
            log_info("无跳过任务（可能首次运行，无同名文件）")
    else:
        log_fail(f"查询跳过任务失败: {status}")


def step_13_summary():
    log_step(13, "测试总结")
    status, body = api_request("GET", "/api/tasks")
    if status != 200:
        log_fail("获取任务列表失败")
        return

    tasks = body['data']['tasks']
    total = body['data']['total']
    success = len([t for t in tasks if t['status'] == 'SUCCESS'])
    failed = len([t for t in tasks if t['status'] == 'FAILED'])
    skipped = len([t for t in tasks if t['status'] == 'SKIPPED'])

    print(f"\n  📊 任务统计:")
    print(f"     总任务:   {total}")
    print(f"     成功:     {success} ✅")
    print(f"     失败:     {failed} ❌")
    print(f"     跳过:     {skipped} ⏭️")
    if total > 0:
        print(f"     成功率:   {success/total*100:.1f}%")

    s, m = api_request("GET", "/api/metrics")
    if s == 200:
        print(f"\n  📈 运行指标:")
        print(f"     LLM 调用:  {m['data']['total_llm_calls']} (失败 {m['data']['llm_failures']})")
        print(f"     运行时间:  {m['data']['uptime']}")

    log_file = os.path.join(FIXTURES_DIR, "logs", "media_importer.log")
    if os.path.exists(log_file):
        size_kb = os.path.getsize(log_file) / 1024
        print(f"\n  📝 日志文件: {size_kb:.1f} KB")

    tasks_json = os.path.join(PROJECT_ROOT, "tasks.json")
    if os.path.exists(tasks_json):
        size_kb = os.path.getsize(tasks_json) / 1024
        print(f"  💾 任务持久化: {size_kb:.1f} KB")


def main():
    skip_hermes = "--skip-hermes" in sys.argv

    print(f"\n{'='*60}")
    print(f"  NAS影视自动化入库系统 — 端到端全流程测试")
    print(f"  测试环境: {FIXTURES_DIR}")
    print(f"  API 地址: {API_BASE}")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    if not step_1_check_server():
        sys.exit(1)

    source_dir, temp_dir, import_dir, log_dir = prepare_test_env()
    log_pass("测试环境已准备（temp/import/logs 已清空）")

    step_2_scan_source()
    step_3_trigger_batch()
    step_4_wait_and_monitor()
    step_5_check_task_details()
    step_6_check_import_dir(import_dir)
    step_7_check_logs(log_dir)
    step_8_check_metrics()
    step_9_hermes_interaction(skip_hermes)
    step_10_retry_failed()
    step_11_permission_test()
    step_12_duplicate_test()
    step_13_summary()

    print(f"\n{'='*60}")
    print(f"  端到端测试完成!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

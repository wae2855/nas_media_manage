#!/usr/bin/env python3
import argparse
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from media_importer.features.configuration import load_config, mask_sensitive
from media_importer.features.tasks import TaskManager
from media_importer.features.import_flow import PipelineRunner
from media_importer.core.metrics import get_metrics
from media_importer.core.logger import get_logger
from media_importer.notify.hermes_hook import HermesNotifier


def _get_data_dir(config):
    return config.get("_data_dir",
        os.path.join(os.path.dirname(__file__), "..", "data"))


def _build_components(config):
    data_dir = _get_data_dir(config)
    os.makedirs(data_dir, exist_ok=True)

    task_manager = TaskManager(data_dir, config)
    metrics = get_metrics()
    logger = get_logger(config)

    notifier = None
    hermes_cfg = config.get("hermes", {})
    if hermes_cfg.get("enabled", False):
        try:
            notifier = HermesNotifier(config)
        except Exception:
            pass

    pipeline = PipelineRunner(
        config=config,
        task_manager=task_manager,
        metrics=metrics,
        logger=logger,
        notifier=notifier
    )
    return pipeline, task_manager, metrics, logger


def cmd_serve(args):
    config = _load_config(args)
    host = args.host or config.get("server", {}).get("host", "0.0.0.0")
    port = args.port or config.get("server", {}).get("port", 9855)
    from media_importer.api.handler import start_server
    start_server(host, port, config)


def cmd_run(args):
    config = _load_config(args)
    pipeline, task_manager, metrics, logger = _build_components(config)

    if args.dry_run:
        logger.info("Dry-run: 扫描源目录")
        from media_importer.features.import_flow import scan_source_dir
        groups = scan_source_dir(config.get("source_dir", ""), config)
        logger.info(f"扫描到 {len(groups)} 个视频文件组")
        for group in groups:
            logger.info(f"  - {group['video_path']}")
        return

    logger.info("开始批量处理")

    def run_in_background():
        pipeline.run_all()

    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()
    logger.info("批量处理已在后台启动")


def cmd_list(args):
    config = _load_config(args)
    data_dir = _get_data_dir(config)
    task_manager = TaskManager(data_dir, config)

    status_map = {
        "all": None,
        "pending": "PENDING",
        "processing": "PROCESSING",
        "success": "SUCCESS",
        "failed": "FAILED",
        "skipped": "SKIPPED"
    }
    status = status_map.get(args.status, None)
    tasks = task_manager.list_tasks(status=status, limit=args.limit)

    print(f"\n{'状态':<12} {'任务ID':<14} {'文件':<40} {'进度':<8} {'重试'}")
    print("-" * 100)
    for task in tasks:
        pct = f"{task.percentage}%"
        print(f"{task.status:<12} {task.task_id:<14} {task.video_file:<40} {pct:<8} {task.retry_count}x")

    counts = task_manager.count_by_status()
    print(f"\n统计: PENDING={counts.get('PENDING',0)} PROCESSING={counts.get('PROCESSING',0)} "
          f"SUCCESS={counts.get('SUCCESS',0)} FAILED={counts.get('FAILED',0)} SKIPPED={counts.get('SKIPPED',0)}")


def cmd_show(args):
    config = _load_config(args)
    data_dir = _get_data_dir(config)
    task_manager = TaskManager(data_dir, config)
    task = task_manager.get_task(args.task_id)

    if task is None:
        print(f"任务不存在: {args.task_id}")
        return

    print(f"\n{'='*60}")
    print(f"任务ID:   {task.task_id}")
    print(f"状态:     {task.status}")
    print(f"文件:     {task.video_file}")
    print(f"路径:     {task.video_path}")
    print(f"大小:     {task.file_size_mb:.2f} MB")
    print(f"入库路径: {task.import_path}")
    print(f"目标文件: {task.final_filename}")
    print(f"进度:     {task.current_step}/{task.total_steps} - {task.step_name} ({task.percentage}%)")
    print(f"创建时间: {task.created_at}")
    if task.started_at:
        print(f"开始时间: {task.started_at}")
    if task.completed_at:
        print(f"完成时间: {task.completed_at}")
    print(f"重试次数: {task.retry_count}")
    if task.error_message:
        print(f"错误信息: {task.error_message}")
    if task.scraped_info:
        print(f"刮削信息:")
        for k, v in task.scraped_info.items():
            print(f"  {k}: {v}")
    print(f"{'='*60}\n")


def cmd_retry(args):
    config = _load_config(args)
    data_dir = _get_data_dir(config)
    task_manager = TaskManager(data_dir, config)

    if args.task_id:
        task = task_manager.retry_task(args.task_id)
        if task:
            print(f"任务已重试: {task.task_id}")
        else:
            print(f"任务不存在或无法重试: {args.task_id}")
    else:
        retried = task_manager.retry_all_failed()
        print(f"已重试 {len(retried)} 个失败任务")


def cmd_queue(args):
    config = _load_config(args)
    data_dir = _get_data_dir(config)
    task_manager = TaskManager(data_dir, config)
    counts = task_manager.count_by_status()
    print("\n队列状态:")
    print(f"  PENDING:    {counts.get('PENDING', 0)}")
    print(f"  PROCESSING: {counts.get('PROCESSING', 0)}")
    print(f"  SUCCESS:    {counts.get('SUCCESS', 0)}")
    print(f"  FAILED:     {counts.get('FAILED', 0)}")
    print(f"  SKIPPED:    {counts.get('SKIPPED', 0)}")


def cmd_clear(args):
    config = _load_config(args)
    data_dir = _get_data_dir(config)
    task_manager = TaskManager(data_dir, config)

    status_map = {
        "all": None,
        "pending": "PENDING",
        "processing": "PROCESSING",
        "success": "SUCCESS",
        "failed": "FAILED",
        "skipped": "SKIPPED"
    }
    status = status_map.get(args.status, None)
    task_manager.clear_tasks(status=status)
    print(f"任务已清空: {args.status}")


def cmd_log(args):
    config = _load_config(args)
    log_dir = config.get("log_dir", "logs")
    log_file = os.path.join(log_dir, "media_importer.log")

    if not os.path.exists(log_file):
        print(f"日志文件不存在: {log_file}")
        return

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"读取日志失败: {e}")
        return

    if args.task_id:
        lines = [l for l in lines if args.task_id in l]

    display_lines = lines[-args.tail:] if args.tail else lines

    if args.follow:
        print(f"跟踪日志: {log_file} (Ctrl+C 退出)")
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if not line:
                        import time
                        time.sleep(0.5)
                        continue
                    if args.task_id is None or args.task_id in line:
                        print(line.rstrip())
        except KeyboardInterrupt:
            pass
    else:
        for line in display_lines:
            print(line.rstrip())


def cmd_health(args):
    config = _load_config(args)

    checks = {}
    overall = "ok"

    source_dir = config.get("source_dir", "")
    checks["source_dir"] = "ok" if os.path.isdir(source_dir) else "error"

    temp_dir = config.get("temp_dir", "")
    checks["temp_dir"] = "ok" if os.path.isdir(temp_dir) else "error"

    llm_cfg = config.get("llm", {})
    checks["llm_api"] = "ok" if llm_cfg.get("api_key") else "missing_api_key"

    hermes_cfg = config.get("hermes", {})
    checks["hermes"] = "ok" if hermes_cfg.get("enabled") else "disabled"

    try:
        disk_dir = temp_dir or "/tmp"
        stat = os.statvfs(disk_dir)
        free_gb = stat.f_bavail * stat.f_frsize / (1024**3)
        checks["disk_space"] = "ok" if free_gb > 1 else "low"
    except Exception:
        checks["disk_space"] = "unknown"

    if "error" in checks.values():
        overall = "degraded"

    print(f"\n健康检查: {overall}")
    for name, status in checks.items():
        icon = "✅" if status == "ok" else "❌" if "error" in status else "⚠️"
        print(f"  {icon} {name}: {status}")
    print()


def cmd_metrics(args):
    config = _load_config(args)
    data_dir = _get_data_dir(config)
    task_manager = TaskManager(data_dir, config)
    metrics = get_metrics()
    counts = task_manager.count_by_status()

    print("\n运行指标:")
    print(f"  总任务:     {metrics._counters['total']}")
    print(f"  成功:       {metrics._counters['success']}")
    print(f"  失败:       {metrics._counters['failed']}")
    print(f"  跳过:       {metrics._counters['skipped']}")
    print(f"  成功率:     {metrics.success_rate*100:.1f}%")
    print(f"  平均耗时:   {metrics.avg_processing_time:.1f}s")
    print(f"  LLM调用:   {metrics._llm_calls} (失败 {metrics._llm_failures})")
    print(f"  运行时间:   {metrics.uptime}")
    print(f"\n队列状态:")
    print(f"  待处理:     {counts.get('PENDING', 0)}")
    print(f"  处理中:     {counts.get('PROCESSING', 0)}")
    print()


def cmd_config(args):
    config = _load_config(args)
    masked = mask_sensitive(config)
    import yaml
    print(yaml.dump(masked, allow_unicode=True, default_flow_style=False, sort_keys=False))


def _load_config(args):
    config_path = getattr(args, "config", None)
    if config_path:
        return load_config(config_path)
    return load_config()


def main():
    parser = argparse.ArgumentParser(
        prog="media_importer",
        description="影音库AI智能整理 - 自动刮削、分类、入库影视文件"
    )
    parser.add_argument("-c", "--config", help="配置文件路径 (默认: config/config.yaml)")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    serve_parser = subparsers.add_parser("serve", help="启动HTTP API服务")
    serve_parser.add_argument("-p", "--port", type=int, default=None, help="服务端口")
    serve_parser.add_argument("--host", default=None, help="监听地址")

    run_parser = subparsers.add_parser("run", help="执行一次批量处理")
    run_parser.add_argument("--dry-run", action="store_true", help="仅扫描不实际处理")

    list_parser = subparsers.add_parser("list", help="列出任务列表")
    list_parser.add_argument("--status", choices=["all", "pending", "processing", "success", "failed", "skipped"],
                            default="all", help="按状态过滤")
    list_parser.add_argument("--limit", type=int, default=50, help="显示数量限制")

    show_parser = subparsers.add_parser("show", help="显示任务详情")
    show_parser.add_argument("task_id", help="任务ID")

    retry_parser = subparsers.add_parser("retry", help="重试失败任务")
    retry_parser.add_argument("task_id", nargs="?", help="任务ID (省略则重试所有失败任务)")

    queue_parser = subparsers.add_parser("queue", help="查看队列状态")

    clear_parser = subparsers.add_parser("clear", help="清空任务队列")
    clear_parser.add_argument("--status", choices=["all", "pending", "processing", "success", "failed", "skipped"],
                             default="all", help="清空指定状态")

    log_parser = subparsers.add_parser("log", help="查看日志")
    log_parser.add_argument("-f", "--follow", action="store_true", help="实时跟踪")
    log_parser.add_argument("--tail", type=int, default=100, help="显示最后N行")
    log_parser.add_argument("--task", dest="task_id", default=None, help="任务ID过滤")

    subparsers.add_parser("health", help="检查系统健康状态")
    subparsers.add_parser("metrics", help="显示运行指标")
    subparsers.add_parser("config", help="显示当前配置")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    cmd_map = {
        "serve": cmd_serve,
        "run": cmd_run,
        "list": cmd_list,
        "show": cmd_show,
        "retry": cmd_retry,
        "queue": cmd_queue,
        "clear": cmd_clear,
        "log": cmd_log,
        "health": cmd_health,
        "metrics": cmd_metrics,
        "config": cmd_config
    }

    handler = cmd_map.get(args.command)
    if handler:
        try:
            handler(args)
        except Exception as e:
            print(f"命令执行失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()

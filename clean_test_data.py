#!/usr/bin/env python3
"""清理所有测试数据，恢复干净环境。

用法:
    python clean_test_data.py               # 交互式确认后清理
    python clean_test_data.py --force        # 跳过确认直接清理
    python clean_test_data.py --dry-run      # 仅列出将清理的内容，不操作

清理范围:
    - 源目录、入库目录、回收站、资源目录、日志目录下的所有文件
    - tasks.db 数据库（清空 tasks / task_subtitles / cleaner_records 表）
    - __pycache__ 缓存目录

安全约束:
    - 默认只支持清理 /tmp/nas_media_test/ 下的目录（测试环境）
    - 额外目录需通过 --ext-dir 显式指定
    - 不允许清理 /、/etc、/home 等系统关键路径
"""

import argparse
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger("clean_test_data")

CONFIG_PATH = Path("config/config.yaml")
PROJECT_ROOT = Path(__file__).resolve().parent

# 仅允许清理这些前缀下的目录（安全围栏）
ALLOWED_DIR_PREFIXES = [
    "/tmp/nas_media_test/",
    "/private/tmp/nas_media_test/",
]

# 系统保护路径 — 绝对不允许清理
PROTECTED_PATHS = {
    "/", "/etc", "/var", "/home", "/root", "/Users",
    "/System", "/Applications", "/Library",
}


def parse_args():
    parser = argparse.ArgumentParser(description="清理 NAS 媒体管理系统测试数据")
    parser.add_argument("--force", action="store_true", help="跳过确认直接清理")
    parser.add_argument("--dry-run", action="store_true", help="仅列出将清理的内容，不执行")
    parser.add_argument(
        "--ext-dir", action="append", default=[],
        help="额外清理的目录（默认只清理 /tmp/nas_media_test/ 下目录）"
    )
    parser.add_argument("--db-path", help="数据库路径（默认从 config 读取）")
    return parser.parse_args()


def load_config():
    """加载 YAML 配置，返回字典。"""
    if not CONFIG_PATH.exists():
        logger.warning("未找到 %s，使用空配置", CONFIG_PATH)
        return {}
    try:
        # 优先用项目的 venv 中的 yaml
        sys.path.insert(0, str(PROJECT_ROOT))
        import yaml
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        logger.warning("PyYAML 未安装，尝试 python3 -m yaml...")
        return {}


def get_db_path(cfg, cli_db_path=None):
    """获取数据库路径。"""
    if cli_db_path:
        return Path(cli_db_path)

    # 环境变量覆盖
    data_dir = os.environ.get("NAS_MEDIA_IMPORTER_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "tasks.db"

    # config 中的 _data_dir
    cfg_data_dir = cfg.get("_data_dir")
    if cfg_data_dir:
        return Path(cfg_data_dir) / "tasks.db"

    # 默认
    return PROJECT_ROOT / "data" / "tasks.db"


def collect_dirs(cfg, ext_dirs):
    """收集所有需要清理的目录。

    返回 (dirs, extra_notes) — 目录列表和额外说明。
    """
    dirs = {}
    notes = []

    # 基础配置目录
    key_map = {
        "源目录": cfg.get("source_dir"),
        "日志目录": cfg.get("log_dir"),
        "回收站目录": cfg.get("source_policy", {}).get("recycle_dir"),
        "资源目录": cfg.get("resource_dir"),
        "回退入库目录": cfg.get("fallback_dir"),
    }
    for label, path in key_map.items():
        if path:
            dirs[label] = Path(path)

    # 解析入库规则模板，收集入库根目录
    import_roots = set()
    for rule in cfg.get("path_rules", []):
        template = rule.get("template", "")
        for prefix in ALLOWED_DIR_PREFIXES:
            if template.startswith(prefix):
                # 取到第一个 { 之前的路径作为根
                brace_idx = template.find("{")
                if brace_idx > 0:
                    root = template[:brace_idx].rstrip("/")
                    if root:
                        import_roots.add(root)
                break
    if import_roots:
        dirs["入库目录"] = [Path(r) for r in sorted(import_roots)]
        notes.append(f"入库子目录数: {len(import_roots)}")

    # 额外目录
    for ed in ext_dirs:
        dirs[f"额外({ed})"] = Path(ed)

    # 数据库所在目录的 wal/shm 文件
    db_path = get_db_path(cfg)
    if db_path.exists():
        for suffix in ("-wal", "-shm"):
            p = db_path.with_suffix(db_path.suffix + suffix)
            if p.exists():
                notes.append(f"数据库附属文件: {p.name}")

    return dirs, notes


def validate_path_safety(path, label=""):
    """检查路径是否安全可清理。

    返回 True 表示安全，False 表示拒绝。
    """
    resolved = path.resolve()
    spath = str(resolved)

    # 检查是否是保护路径
    if spath.rstrip("/") in PROTECTED_PATHS:
        logger.error("❌ 拒绝清理保护路径: %s (%s)", spath, label)
        return False

    # 检查父路径是否是保护路径
    for protected in PROTECTED_PATHS:
        if spath.startswith(protected + "/") or spath == protected:
            logger.error("❌ 拒绝清理保护路径: %s (%s)", spath, label)
            return False

    # 检查是否在允许前缀内
    for prefix in ALLOWED_DIR_PREFIXES:
        if spath.startswith(prefix):
            return True

    logger.warning("⚠️  路径不在默认安全范围内: %s (%s)", spath, label)
    return False


def confirm_cleanup(all_dirs, notes, db_path, force=False):
    """向用户展示清理清单并确认。"""
    print()
    print("=" * 60)
    print("  测试数据清理计划")
    print("=" * 60)
    print()

    for label, path in sorted(all_dirs.items()):
        if isinstance(path, list):
            print(f"  📁 {label}:")
            for p in path:
                print(f"       {p}")
        else:
            if path.exists():
                exists = "存在"
            else:
                exists = "不存在"
            print(f"  📁 {label}: {path}  ({exists})")

    print(f"  🗄️  数据库: {db_path}")
    for note in notes:
        print(f"  📌 {note}")

    print()
    print("  将执行的操作:")
    print("    1. 删除所有目录下的文件（目录本身保留）")
    print("    2. 清空 tasks / task_subtitles / cleaner_records 表")
    print("    3. 清空 __pycache__")
    print()

    if force:
        logger.info("--force 已指定，跳过确认")
        return True

    response = input("  确认清理以上所有测试数据? [y/N] ").strip().lower()
    return response in ("y", "yes")


def clean_directory(path, label="", dry_run=False):
    """清理一个目录的内容（保留目录本身）。"""
    if not path.exists():
        logger.info("  - %s: 不存在，跳过", label)
        return 0

    count = 0
    if dry_run:
        for _entry in path.iterdir():
            count += 1
        logger.info("  - %s: 将删除 %d 项", label, count)
        return count

    for entry in path.iterdir():
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink()
            count += 1
        except OSError as e:
            logger.error("  - 删除失败 %s: %s", entry.name, e)

    logger.info("  - %s: 已清理 %d 项", label, count)
    return count


def reset_database(db_path, dry_run=False):
    """重置数据库中的测试数据。"""
    if not db_path.exists():
        logger.info("  - 数据库不存在: %s", db_path)
        return

    if dry_run:
        logger.info("  - 数据库: 将清空 tasks / task_subtitles / cleaner_records")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    tables = ["tasks", "task_subtitles", "cleaner_records"]

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        cursor.execute(f"DELETE FROM {table}")
        logger.info("  - %s: 已清空 %d 条记录", table, count)

    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    logger.info("  - VACUUM 完成")


def clean_pycache(dry_run=False):
    """清理项目中的 __pycache__ 目录（跳过 .venv 和数据目录）。"""
    skip_prefixes = (
        str(PROJECT_ROOT / ".venv"),
        str(PROJECT_ROOT / "data"),
    )
    count = 0
    for root, dirs, _ in os.walk(PROJECT_ROOT):
        if any(root.startswith(p) for p in skip_prefixes):
            continue
        for d in dirs:
            if d == "__pycache__":
                full = Path(root) / d
                if dry_run:
                    count += 1
                else:
                    shutil.rmtree(full, ignore_errors=True)
                    count += 1
    logger.info("  - __pycache__: 已清理 %d 个目录", count)
    return count


def main():
    args = parse_args()

    if args.dry_run:
        logger.setLevel(logging.INFO)
        logger.info("🧪 干跑模式 — 不会执行任何删除操作\n")

    cfg = load_config()
    db_path = get_db_path(cfg, args.db_path)

    # 收集目录
    all_dirs, notes = collect_dirs(cfg, args.ext_dir)

    # 验证所有路径安全
    safe_dirs = {}
    unsafe_found = False
    for label, path in sorted(all_dirs.items()):
        if isinstance(path, list):
            validated = []
            for p in path:
                if validate_path_safety(p, label):
                    validated.append(p)
                else:
                    unsafe_found = True
            if validated:
                safe_dirs[label] = validated
        else:
            if validate_path_safety(path, label):
                safe_dirs[label] = path
            else:
                unsafe_found = True

    if unsafe_found:
        logger.error("存在不安全路径，终止清理")
        sys.exit(1)

    if not safe_dirs:
        logger.warning("没有找到需要清理的目录")
        return

    # 干跑模式不确认
    if args.dry_run:
        confirm = True
    else:
        confirm = confirm_cleanup(safe_dirs, notes, db_path, force=args.force)

    if not confirm:
        print("  已取消")
        sys.exit(0)

    # 执行清理
    print()
    print("=" * 60)
    print("  开始清理...")
    print("=" * 60)
    print()

    total = 0
    for label, path in sorted(safe_dirs.items()):
        if isinstance(path, list):
            for i, p in enumerate(path):
                sub = f"{label}[{i}]"
                total += clean_directory(p, sub, dry_run=args.dry_run)
        else:
            total += clean_directory(path, label, dry_run=args.dry_run)

    reset_database(db_path, dry_run=args.dry_run)
    total += clean_pycache(dry_run=args.dry_run)

    print()
    print("=" * 60)
    if args.dry_run:
        print(f"  🧪 干跑完成 — 将清理约 {total} 项")
    else:
        print(f"  ✅ 清理完成 — 共处理 {total} 项")
    print("=" * 60)


if __name__ == "__main__":
    main()

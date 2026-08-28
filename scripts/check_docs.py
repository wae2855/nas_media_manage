#!/usr/bin/env python3
"""文档健康检查：断链、行数超限、front-matter 缺失、ADR 编号。

零第三方依赖，只用标准库。exit 0 = 全部通过。

用法：
    python scripts/check_docs.py           # 全量检查
    python scripts/check_docs.py --quiet   # 只输出错误
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 跳过的目录（归档/生成物/虚拟环境/运行时配置示例）
SKIP_DIRS = {
    ".git", ".venv", "node_modules", "_archive", "__pycache__",
    ".pytest_cache", ".playwright-mcp", ".agent-browser", ".trae",
    "data", "logs", "build", "screenshots", "deploy", "config",
}

MAX_DOC_LINES = 500
STATUS_ENUM = {"draft", "approved", "in-progress", "complete", "superseded", "pending-review"}
VALID_TYPES = {"plan", "proposal", "brainstorm"}

# 强制 front-matter 的目录（documentation.md 规范只约束这三类过程文档）
FRONT_MATTER_DIRS = {"plans", "proposals", "brainstorms"}

# 行数豁免清单（重写/拆分待简洁化评估统一处理，勿新增）
LONG_DOC_EXEMPT = {
    "README.md": "人类入口，简洁化评估时重写",
    "docs/standards/ai-prompt-design.md": "567 行微超，拆分待简洁化评估",
    "docs/plans/2026-06-10-test-plan-systematic.md": "冻结待重估文档",
}

LINK_RE = re.compile(r"(?<!\!)\]\(([^)#\s]+)(?:#[^)]*)?\)")
FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def iter_md_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*.md"):
        rel = path.relative_to(REPO_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append(rel)
    return sorted(files)


def strip_code_blocks(text: str) -> str:
    """移除 fenced code blocks，避免其中的链接/行数误报。"""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def strip_front_matter(text: str) -> str:
    if text.startswith("---"):
        m = FM_RE.match(text)
        if m:
            return text[m.end():]
    return text


def check_broken_links(rel: Path, text: str, errors: list[str]) -> None:
    body = strip_code_blocks(text)
    base = rel.parent
    for m in LINK_RE.finditer(body):
        link = m.group(1)
        if link.startswith(("http://", "https://", "mailto:", "file://")):
            continue
        target = (base / link).resolve()
        try:
            target.relative_to(REPO_ROOT)
        except ValueError:
            continue  # 仓库外链接不检查
        if not target.exists():
            errors.append(f"{rel}: 断链 -> {link}")


def check_line_count(rel: Path, text: str, errors: list[str]) -> None:
    rel_str = rel.as_posix()
    if rel_str in LONG_DOC_EXEMPT:
        return
    n = len(text.splitlines())
    if n > MAX_DOC_LINES:
        errors.append(f"{rel}: {n} 行超过 {MAX_DOC_LINES} 行上限（standards/documentation.md）")


def check_front_matter(rel: Path, text: str, errors: list[str]) -> None:
    if rel.parts[0] not in FRONT_MATTER_DIRS:
        return
    m = FM_RE.match(text)
    if not m:
        errors.append(f"{rel}: 缺少 YAML front-matter（documentation.md 规范）")
        return
    fm = m.group(1)
    status_m = re.search(r"^status:\s*(\S+)", fm, re.MULTILINE)
    type_m = re.search(r"^type:\s*(\S+)", fm, re.MULTILINE)
    if type_m and type_m.group(1) in VALID_TYPES:
        if not status_m:
            errors.append(f"{rel}: plan/proposal/brainstorm 必须有 status 字段")
        elif status_m.group(1) not in STATUS_ENUM:
            errors.append(f"{rel}: 非法 status '{status_m.group(1)}'（允许：{sorted(STATUS_ENUM)}）")


def check_adr_numbering(errors: list[str]) -> None:
    adr_dir = REPO_ROOT / "docs" / "decisions"
    if not adr_dir.is_dir():
        return
    seen: dict[int, list[str]] = {}
    for f in sorted(adr_dir.glob("*.md")):
        m = re.match(r"^(\d{4})-", f.name)
        if m:
            seen.setdefault(int(m.group(1)), []).append(f.name)
    for num, names in seen.items():
        if len(names) > 1:
            errors.append(f"docs/decisions: ADR 编号 {num} 重号 -> {names}")


RETIRED_UI_TERMS = (
    "三级匹配", "AI上下文", "AI辅助匹配", "AI联网", "联网搜索",
    "AI 判定", "Hermes", "飞书", "MCP 联网",
)


def check_no_retired_ui_terms(errors: list[str]) -> None:
    """活跃前端文件不得出现退役功能文案（ADR-0010 / Hermes 移除后）。"""
    webui = REPO_ROOT / "media_importer" / "webui"
    if not webui.is_dir():
        return
    for path in webui.rglob("*"):
        if path.suffix not in {".js", ".html", ".css"}:
            continue
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for term in RETIRED_UI_TERMS:
            if term in text:
                rel = path.relative_to(REPO_ROOT)
                errors.append(
                    f"{rel}: 退役文案 '{term}'（ADR-0010 后不得出现在活跃 UI）"
                )


def check_no_nested_plan_archive(errors: list[str]) -> None:
    nested = REPO_ROOT / "docs" / "plans" / "_archive"
    if nested.exists():
        errors.append("docs/plans/_archive/ 不允许存在（归档统一进 docs/_archive/）")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    files = iter_md_files()

    for rel in files:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        body = strip_front_matter(text)
        check_broken_links(rel, body, errors)
        check_line_count(rel, body, errors)
        check_front_matter(rel, text, errors)

    check_adr_numbering(errors)
    check_no_nested_plan_archive(errors)
    check_no_retired_ui_terms(errors)

    if errors:
        print(f"FAIL: {len(errors)} 个问题")
        for e in errors:
            print(f"  - {e}")
        return 1
    if not args.quiet:
        print(f"OK: {len(files)} 个活跃 md 文件检查通过（断链/行数/front-matter/ADR 编号）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""总 guard：禁止旧历史兼容入口出现在运行时代码。

扫描范围：
- `media_importer/**` 运行时代码
- `tests/**` 单元/集成测试

不扫描：
- `docs/_archive/**` 历史归档目录
- guard 自身

执行原则（按 docs/plans/2026-06-13-refactor-remove-legacy-compatibility-plan.md）：
- 删除优先于兼容；不要新增 shim/alias/fallback
- 业务 fallback 不属于历史兼容：`fallback_dir`、图片 fallback、
  Provider 语言 fallback (`fallback_language`)、Provider 搜索 fallback 保留
- 文档标记 "向后兼容" / "历史兼容" / "已废弃" 仍属 legacy 入口（不在生产代码出现）
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


SCAN_ROOTS = (
    REPO_ROOT / "media_importer",
    REPO_ROOT / "tests",
)


EXEMPT_PATHS = (
    REPO_ROOT / "docs" / "_archive",
)


EXEMPT_FILE_PATTERNS = (
    re.compile(r"tests/test_no_legacy_compat_surface\.py$"),
    re.compile(r"tests/test_no_legacy_confidence_surface\.py$"),
    re.compile(r"tests/test_no_legacy_confidence_behavior\.py$"),
    re.compile(r".*/webui/legacy-config\.html$"),
)


# 业务能力白名单：扫描时跳过命中这些正则的行
# 目的是：避免把业务能力误判为历史兼容入口
BUSINESS_FALLBACK_LINE_PATTERNS = (
    re.compile(r"\bai_only_count\b"),
    re.compile(r"\bfallback_dir\b"),
    re.compile(r"\bfallback_language\b"),
)


# 运行时代码中的 legacy 入口：匹配任意一条即视为 RED
LEGACY_TERMS = {
    # Phase 1: 旧 AI 提示词体系
    "scraper_prompts": "旧 AI 刮削提示词文件名",
    "tmdb_prompts": "旧 TMDB 提示词文件名",
    "scraper_prompts.md": "旧 AI 刮削提示词文件路径",
    "scraper_prompts.example.md": "旧 AI 刮削提示词示例文件",
    "tmdb_prompts.md": "旧 TMDB 提示词文件路径",
    "prompt-config": "旧高级配置 > AI刮削提示词导航 ID",
    "prompt-tmdb": "旧 TMDB 提示词编辑器 ID",
    "_load_prompts_from_file": "旧文件 prompt loader",
    "_load_provider_prompts_from_files": "旧文件 prompt loader",
    "_load_tmdb_prompts_from_file": "旧文件 prompt loader",

    # Phase 2: 旧 preview 同步接口
    "provider_ai": "旧 preview 双模式名",
    "ai_only": "旧刮削模式（scrape_mode 双模式已收敛）",

    # Phase 3: 旧置信度体系
    "ConfidenceEngine": "旧置信度引擎类",
    "ConfidenceResult": "旧置信度结果数据类",
    "scrape_confidence": "旧置信度 DB/API 字段",
    "confidence_engine": "旧置信度引擎模块",
    "confidence_detail": "旧置信度 trace 字段",
    "final_confidence": "旧置信度数值",
    "data_gate": "旧置信度组件",
    "_calc_R": "旧 R 公式函数",
    "_aggregate": "旧置信度聚合函数",

    # Phase 4: 旧 LLMConfig dataclass 及字段
    "LLMConfig": "旧 LLM 配置 dataclass",
    "fallback_model": "旧 llm.fallback_model 字段",
    "source_cleaner_model": "旧 llm.source_cleaner_model 字段",
    "confidence_threshold": "旧 llm.confidence_threshold 字段",

    # Phase 5: 旧 Provider 配置结构（metadata.<ptype> 单 key 模式已删除）

    # Phase 6: 旧 type/media_type 双字段兼容已删除
    #   （"or result.get(\"type\")" 等模式已收口到 media_type）

    # Phase 7: 旧任务状态别名
    "STATUS_PROCESSING": "旧任务状态别名（已统一到 STATUS_PENDING）",
    "STATUS_CONFIRMING": "旧任务状态别名（已统一到 STATUS_PENDING）",
    "STATUS_NEEDS_REVIEW": "旧任务状态别名（已统一到 STATUS_PENDING）",

    # Phase 9: DB 迁移 v1/v2 历史链已 squash
}


# 旧 preview 同步接口：路由和 helper
LEGACY_PREVIEW_TERMS = {
    "/api/scrape/preview\"": "旧同步 preview 路由",
    "_scrape_preview(": "旧同步 preview handler",
    "_decorate_scrape_preview_mode": "旧 preview 装饰 helper",
    "_build_scrape_preview_recommendation": "旧 preview 推荐 helper",
    "_resolve_import_paths": "旧 preview 入库路径 helper",
}


# CRIT-1: 旧 llm 配置运行入口 - 任何运行时读 llm 配置的方式都禁止
LEGACY_LLM_CONFIG_ACCESS_TERMS = {
    'get("llm"': '运行时读 llm 配置（CRIT-1）',
    "get('llm'": '运行时读 llm 配置（CRIT-1）',
    '_get_real_config_value("llm"': '_get_real_config_value 读 llm 配置（CRIT-1）',
    "_get_real_config_value('llm'": '_get_real_config_value 读 llm 配置（CRIT-1）',
    '["llm"]': '运行时通过键 llm 索引（CRIT-1）',
    "['llm']": '运行时通过键 llm 索引（CRIT-1）',
}


# CRIT-2: 旧 storage wrapper 已删除
LEGACY_STORAGE_TERMS = {
    "media_importer.storage": "旧 storage wrapper 已删除（CRIT-2）",
    "from media_importer.storage": "旧 storage wrapper 已删除（CRIT-2）",
}


# MAJ-1: 旧 API 路由 flag 已删除
LEGACY_API_FLAG_TERMS = {
    "body_before_params": "API 路由 flag body_before_params 已删除（MAJ-1）",
    "pass_self": "API 路由 flag pass_self 已删除（MAJ-1）",
    "pass_body": "API 路由 flag pass_body 已删除（MAJ-1）",
    "body_delete_files": "API 路由 flag body_delete_files 已删除（MAJ-1）",
    "pass_query": "API 路由 flag pass_query 已删除（MAJ-1）",
}


# 文档标记：注释、docstring 中描述性 legacy 字样
LEGACY_DOC_MARKERS = (
    "历史兼容",
    "历史兼容占位",
    "历史兼容层",
    "向后兼容",
    "已废弃",
    "deprecated",
)


# MAJ-2: 旧 DB migration 历史说明性字样
LEGACY_MIGRATION_DOC_TERMS = (
    "v1 =",
    "v2 =",
    "v3 =",
    "v1=",
    "v2=",
    "v3=",
    "needs_migrate",
    "old_keys",
    "旧配置",
    "历史配置",
    "backward",
    "compat",
)


def _iter_python_text_files(root: Path):
    """Yield (path, line, line_no) for all source files under root."""
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith(".py"):
                continue
            p = Path(dirpath) / name
            rel = p.relative_to(REPO_ROOT)
            if any(rel.is_relative_to(exempt.relative_to(REPO_ROOT)) for exempt in EXEMPT_PATHS):
                continue
            if any(pat.match(str(rel)) for pat in EXEMPT_FILE_PATTERNS):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                yield rel, line, line_no


def _is_exempt_line(line: str) -> bool:
    for pat in BUSINESS_FALLBACK_LINE_PATTERNS:
        if pat.search(line):
            return True
    return False


class LegacyCompatSurfaceGuardTests(unittest.TestCase):

    def _scan(self, root: Path, term_map: dict, prefix: str, exempt_line_check: bool = True):
        offenders = []
        for rel, line, line_no in _iter_python_text_files(root):
            if exempt_line_check and _is_exempt_line(line):
                continue
            for term, reason in term_map.items():
                if term in line:
                    offenders.append((str(rel), line_no, term, reason, line.strip()))
        if offenders:
            msg = [prefix]
            for path, ln, term, reason, snippet in offenders[:50]:
                msg.append(f"  {path}:{ln}  [{term}] {reason}\n    > {snippet[:160]}")
            self.fail("\n".join(msg))

    def test_runtime_code_has_no_legacy_compat_terms(self):
        self._scan(REPO_ROOT / "media_importer", LEGACY_TERMS, "发现 legacy 兼容入口：")

    def test_runtime_code_has_no_legacy_preview_endpoint(self):
        self._scan(REPO_ROOT / "media_importer", LEGACY_PREVIEW_TERMS, "发现旧 preview 同步接口：")

    def test_runtime_code_has_no_legacy_provider_config_terms(self):
        self._scan(REPO_ROOT / "media_importer", dict(), "发现旧 Provider 配置兼容：")

    def test_runtime_code_has_no_legacy_llm_config_access(self):
        """CRIT-1: 任何运行时读 llm 配置的方式都禁止。"""
        self._scan(REPO_ROOT / "media_importer", LEGACY_LLM_CONFIG_ACCESS_TERMS, "发现旧 llm 配置运行入口（CRIT-1）：")

    def test_runtime_code_has_no_legacy_storage_imports(self):
        """CRIT-2: media_importer.storage wrapper 已删除。"""
        self._scan(REPO_ROOT / "media_importer", LEGACY_STORAGE_TERMS, "发现旧 storage wrapper import（CRIT-2）：")

    def test_runtime_code_has_no_legacy_api_flags(self):
        """MAJ-1: 旧 API 路由 flag 已删除。"""
        self._scan(REPO_ROOT / "media_importer", LEGACY_API_FLAG_TERMS, "发现旧 API 路由 flag（MAJ-1）：")

    def test_runtime_code_has_no_legacy_doc_markers(self):
        """注释/docstring 中描述性 legacy 字样禁止出现在运行时代码。"""
        offenders = []
        for rel, line, line_no in _iter_python_text_files(REPO_ROOT / "media_importer"):
            if _is_exempt_line(line):
                continue
            for marker in LEGACY_DOC_MARKERS:
                if marker in line:
                    offenders.append((str(rel), line_no, marker, line.strip()))
        if offenders:
            msg = ["发现 legacy 描述性字样："]
            for path, ln, marker, snippet in offenders[:50]:
                msg.append(f"  {path}:{ln}  [{marker}]\n    > {snippet[:160]}")
            self.fail("\n".join(msg))

    def test_runtime_code_has_no_legacy_migration_doc_terms(self):
        """MAJ-2: 旧 DB migration 历史说明性字样禁止出现在运行时代码。"""
        offenders = []
        for rel, line, line_no in _iter_python_text_files(REPO_ROOT / "media_importer"):
            if _is_exempt_line(line):
                continue
            for term in LEGACY_MIGRATION_DOC_TERMS:
                if re.search(r"(?<![A-Za-z0-9_])" + re.escape(term) + r"(?![A-Za-z0-9_])", line):
                    offenders.append((str(rel), line_no, term, line.strip()))
        if offenders:
            msg = ["发现旧 DB migration 字样（MAJ-2）："]
            for path, ln, term, snippet in offenders[:50]:
                msg.append(f"  {path}:{ln}  [{term}]\n    > {snippet[:160]}")
            self.fail("\n".join(msg))


if __name__ == "__main__":
    unittest.main()

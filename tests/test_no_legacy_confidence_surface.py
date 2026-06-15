"""旧置信度展示面 guard 测试。

历史背景：旧版 final_confidence = T × R × data_gate 公式已被 ADR-0005 三级匹配策略替代。
当前事实：系统界面、API 与 import_flow 不再展示或写入旧置信度解释字段。
本测试扫描源码禁止位置，禁止用户可见的旧公式与文案再次出现。
"""

from pathlib import Path

import pytest


FORBIDDEN_RUNTIME_PATTERNS = [
    "T × R",
    "T x R",
    "最终置信度",
    "置信度计算详情",
    "best_confidence",
    "confidence_data_gate",
    "confidence_search",
    "confidence_gate_blocked",
    "confidence_reason",
    "low_confidence",
    "search_conf = T",
    "final_confidence",
    "data_gate",
    'mapping.get("confidence"',
    "mapping.get('confidence'",
    "T=",
    '"confidence":',
    "'confidence':",
    "置信度",
    "confidence-sim",
    "confidence-simulator",
    "confidence-kicker",
    "btn-confidence",
    "confidence-detail",
    "showConfidence",
    "confidence =",
]

# 如果某个测试文件必须 mock 才会用到某些禁止模式，
# 在此处按文件名声明豁免，避免 guard 误报。
# key: forbidden pattern, value: set of exempted file names (basename)
PATTERN_FILE_EXEMPTIONS = {
    "T=": {
        "test_match_engine.py",
    },
}


SEARCH_ROOTS = [
    Path("media_importer/api"),
    Path("media_importer/webui"),
    Path("media_importer/features"),
    Path("media_importer/scraper"),
    Path("media_importer/notify"),
    Path("media_importer/monitor"),
    Path("tests"),
]

# Guard 测试文件自身豁免（允许出现禁止词用于定义和说明）
GUARD_TEST_FILES = frozenset({
    "test_no_legacy_confidence_surface.py",
    "test_no_legacy_confidence_behavior.py",
    "test_no_legacy_compat_surface.py",
})


def _is_exempt(path: Path) -> bool:
    """判断文件是否应整体豁免（不参与任何 pattern 检查）。"""
    text = str(path).replace("\\", "/")
    if "/docs/_archive/" in text:
        return True
    if text.endswith("/docs/decisions/0005-three-tier-matching.md"):
        return True
    if text.endswith("media_importer/scraper/title_matcher.py"):
        return True
    return False


def _is_pattern_exempt(path: Path, pattern: str) -> bool:
    """判断特定 pattern 对该文件是否豁免。"""
    exemptions = PATTERN_FILE_EXEMPTIONS.get(pattern)
    if not exemptions:
        return False
    return path.name in exemptions


def _iter_source_files(root: Path):
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.suffix not in {".py", ".js", ".html", ".css"}:
            continue
        if path.name in GUARD_TEST_FILES:
            continue
        if _is_exempt(path):
            continue
        yield path


def test_no_legacy_confidence_surface_in_runtime():
    violations = []
    for root in SEARCH_ROOTS:
        for path in _iter_source_files(root):
            text = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_RUNTIME_PATTERNS:
                if pattern in text and not _is_pattern_exempt(path, pattern):
                    violations.append(f"{path}: forbidden pattern '{pattern}'")
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize("root_path", [str(p) for p in SEARCH_ROOTS])
def test_no_legacy_pattern_per_root(root_path: str):
    """每个目录单独扫描，方便定位。"""
    root = Path(root_path)
    violations = []
    for path in _iter_source_files(root):
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_RUNTIME_PATTERNS:
            if pattern in text and not _is_pattern_exempt(path, pattern):
                violations.append(f"{path}: '{pattern}'")
    assert not violations, "\n".join(violations)


def test_webui_directory_has_no_legacy_config_html():
    """运行期 webui 目录不应包含 legacy-config.html（已迁移至 docs/_archive）。"""
    legacy = Path("media_importer/webui/legacy-config.html")
    assert not legacy.exists(), (
        f"{legacy} 已从运行期 webui 移除；如需历史对照请放至 docs/_archive/legacy-webui/"
    )

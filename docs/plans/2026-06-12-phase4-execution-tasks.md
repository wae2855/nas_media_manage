# 阶段 4 执行文档：清理移除

> 本文档供 deepseek-v4flash / minimax-m3 等模型直接执行。
> 每个任务都是原子操作，包含精确的文件路径、代码骨架和验证步骤。
> **严格按任务编号顺序执行**，不可跳步。
> **前置条件**：阶段 1-3 全部完成，三级匹配引擎已正常工作，前端已适配。

---

## 任务 4.1：将 `confidence_engine.py` 改为薄 re-export 兼容层

**文件**：`media_importer/features/scraping/confidence_engine.py`

**操作**：替换整个文件内容为薄兼容层，保留 `__all__` 导出，确保旧代码 `from media_importer.features.scraping.confidence_engine import ConfidenceEngine` 不报错。

**替换整个文件内容为**：

```python
"""置信度引擎兼容层。

原始置信度引擎已被三级匹配引擎（match_engine.py）替代。
此文件保留为薄 re-export 兼容层，确保旧代码不报错。
新代码应直接使用 match_engine.MatchEngine。
"""

import logging
from typing import Optional, List, Dict, Any, Set

from media_importer.features.scraping.confidence_models import (
    DEFAULT_CONFIDENCE_CONFIG,
    CleanResult,
    MatchResult,
    ConfidenceResult,
)
from media_importer.scraper.filename_cleaner import FilenameCleaner
from media_importer.scraper.title_matcher import TitleMatcher
from media_importer.scraper.trace_builder import ScrapeTraceBuilder

logger = logging.getLogger(__name__)


class ConfidenceEngine:
    """置信度引擎兼容层。

    所有计算逻辑已迁移到 match_engine.MatchEngine。
    此类保留接口兼容，内部委托给新引擎或返回默认值。
    """

    def __init__(self, config: dict = None):
        self._config = {**DEFAULT_CONFIDENCE_CONFIG}
        if config:
            self._config.update(config)
        self._cleaner = FilenameCleaner()
        self._matcher = TitleMatcher(self._config)
        self._trace_builder = ScrapeTraceBuilder()

    @property
    def cleaner(self):
        return self._cleaner

    @property
    def matcher(self):
        return self._matcher

    def calculate(self, scrape_result, provider_search_info, clean_result,
                  ai_clean_result=None, match_result=None,
                  llm_raw_confidence=None, enabled_dims=None):
        """兼容方法：返回默认 ConfidenceResult。

        新代码应使用 match_engine.MatchEngine.match() 获取 MatchResult。
        """
        T = match_result.T if match_result else 0.0
        return ConfidenceResult(
            final_confidence=T,
            search_conf=T,
            data_conf=1.0,
            data_gate=1.0,
            gate_blocked=None,
            veto=None,
            llm_raw_confidence=llm_raw_confidence,
            dimensions={},
            scrape_trace={},
            confidence_detail={
                "formula": "兼容层：已迁移到三级匹配引擎",
                "T": round(T, 4),
                "final_confidence": round(T, 4),
            },
        )

    def calculate_ai_only(self, scrape_result, clean_result,
                          llm_raw_confidence=None, enabled_dims=None,
                          ai_clean_result=None, provider_fallback_reasons=None):
        """兼容方法：返回默认 ConfidenceResult。"""
        return ConfidenceResult(
            final_confidence=0.5,
            search_conf=0.5,
            data_conf=1.0,
            data_gate=1.0,
            gate_blocked=None,
            dimensions={},
            scrape_trace={},
            confidence_detail={
                "formula": "兼容层：已迁移到三级匹配引擎",
                "final_confidence": 0.5,
            },
        )

    def get_confidence_level(self, final_confidence, gate_blocked=None):
        """兼容方法：将置信度数值映射为 match_level。

        旧代码可能仍调用此方法，映射规则：
        - >= 0.8 → PASS (对应 AUTO_PASS)
        - >= 0.5 → CONFIRMING (对应 NEEDS_CONFIRM)
        - >= 0.3 → NEEDS_REVIEW (对应 NEEDS_CONFIRM)
        - < 0.3 → FAILED (对应 NEEDS_CONFIRM)
        """
        if gate_blocked:
            return "NEEDS_REVIEW"
        if final_confidence >= self._config.get("pass_threshold", 0.8):
            return "PASS"
        elif final_confidence >= self._config.get("confirm_threshold", 0.5):
            return "CONFIRMING"
        elif final_confidence >= self._config.get("review_threshold", 0.3):
            return "NEEDS_REVIEW"
        else:
            return "FAILED"


__all__ = [
    "ConfidenceEngine",
    "FilenameCleaner",
    "TitleMatcher",
    "ScrapeTraceBuilder",
    "CleanResult",
    "MatchResult",
    "ConfidenceResult",
    "DEFAULT_CONFIDENCE_CONFIG",
]
```

**验证**：
```bash
cd /Users/wangwei/Documents/code/nas_media_manage
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/features/scraping/confidence_engine.py
```

验证旧代码仍可导入：
```bash
python -c "from media_importer.features.scraping.confidence_engine import ConfidenceEngine; e = ConfidenceEngine(); print('OK:', type(e))"
```

---

## 任务 4.2：移除 `confidence_models.py` 中不再使用的函数

**文件**：`media_importer/features/scraping/confidence_models.py`

**操作**：移除 `_calc_R` 和 `_aggregate` 函数，简化 `DEFAULT_CONFIDENCE_CONFIG`

### 替换 1：移除 `_calc_R` 函数

找到（第 105-119 行）：

```python
def _calc_R(total_results: int, formula: str, cap: int, min_val: float) -> float:
    N = min(total_results, cap) if cap > 0 else total_results
    if N <= 0:
        return 1.0
    if formula == "inverse":
        R = 1.0 / N
    elif formula == "log":
        R = 1.0 / math.log2(N + 1)
    elif formula == "sqrt":
        R = 1.0 / math.sqrt(N)
    elif formula == "flat":
        R = 1.0
    else:
        R = 1.0 / math.log2(N + 1)
    return max(R, min_val)
```

替换为：

```python
def _calc_R(total_results: int, formula: str = "log", cap: int = 10, min_val: float = 0.1) -> float:
    """兼容保留：R 值计算已不再使用，返回 1.0。"""
    return 1.0
```

### 替换 2：移除 `_aggregate` 函数

找到（第 122-139 行）：

```python
def _aggregate(values: List[float], weights: List[float], method: str = "geometric_mean") -> float:
    if not values:
        return 1.0
    if method == "product":
        result = 1.0
        for v in values:
            result *= v
        return result
    if method == "min":
        return min(values)
    weighted_product = 1.0
    total_weight = 0.0
    for v, w in zip(values, weights):
        weighted_product *= v ** w
        total_weight += w
    if total_weight <= 0:
        return 1.0
    return weighted_product ** (1.0 / total_weight)
```

替换为：

```python
def _aggregate(values: List[float], weights: List[float], method: str = "geometric_mean") -> float:
    """兼容保留：聚合计算已不再使用，返回 1.0。"""
    return 1.0
```

### 替换 3：简化 `DEFAULT_CONFIDENCE_CONFIG`

找到（第 7-30 行）：

```python
DEFAULT_CONFIDENCE_CONFIG = {
    "provider_match_threshold": 0.85,
    "title_exact_with_year": 1.0,
    "title_exact_with_season": 0.9,
    "title_exact_no_year": 0.7,
    "title_exact_year_mismatch": 0.4,
    "title_fuzzy_year_coeff": 0.7,
    "title_min_similarity": 0.3,
    "R_formula": "log",
    "R_max_results_cap": 10,
    "R_min_value": 0.1,
    "R_T_floor": 1.0,
    "R_T_curve": 1.5,
    "source_priority": ["tmdb", "ai", "file"],
    "ai_cap_high_similarity": 0.7,
    "ai_cap_low_similarity": 0.3,
    "ai_cap_no_title": 0.3,
    "ai_cap_no_match": 0.2,
    "ai_cap_low_coeff": 0.5,
    "pass_threshold": 0.8,
    "confirm_threshold": 0.5,
    "review_threshold": 0.3,
    "dimensions": {},
}
```

替换为：

```python
DEFAULT_CONFIDENCE_CONFIG = {
    # TitleMatcher 仍使用的阈值（保留）
    "provider_match_threshold": 0.85,
    "title_exact_with_year": 1.0,
    "title_exact_with_season": 0.9,
    "title_exact_no_year": 0.7,
    "title_exact_year_mismatch": 0.4,
    "title_fuzzy_year_coeff": 0.7,
    "title_min_similarity": 0.3,
    # 兼容保留（不再实际使用）
    "pass_threshold": 0.8,
    "confirm_threshold": 0.5,
    "review_threshold": 0.3,
    "source_priority": ["tmdb", "ai", "file"],
    "dimensions": {},
}
```

**注意**：`_calc_R` 和 `_aggregate` 函数保留为兼容桩（返回 1.0），因为 `confidence_engine.py` 的 `__init__.py` 可能仍有导入。如果确认无外部引用，可以完全删除。

**验证**：
```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/features/scraping/confidence_models.py
python -c "from media_importer.features.scraping.confidence_models import _calc_R, _aggregate, DEFAULT_CONFIDENCE_CONFIG; print('OK:', _calc_R(5), _aggregate([0.5], [1.0]))"
```

---

## 任务 4.3：移除 `title_matcher.py` 中的 config 参数依赖

**文件**：`media_importer/scraper/title_matcher.py`

**操作**：`TitleMatcher` 仍然使用 `DEFAULT_CONFIDENCE_CONFIG` 中的阈值参数（`title_exact_with_year` 等），这些参数在任务 4.2 中已保留。因此 `title_matcher.py` 不需要修改。

**验证**：
```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/scraper/title_matcher.py
```

---

## 任务 4.4：移除旧版 `tasks.js` 中的置信度相关代码

**文件**：`media_importer/webui/js/tasks.js`

**操作**：已在阶段 3 任务 3.10 中完成。确认 `tasks.js` 中不再包含 `置信度` 关键字。

**验证**：
```bash
grep -c "置信度" media_importer/webui/js/tasks.js
# 预期输出：0
```

---

## 任务 4.5：移除旧测试类

**文件**：`tests/test_confidence_engine.py`

**操作**：移除以下 4 个测试类，保留其他测试类（如 `TestFilenameCleaner`、`TestTitleMatcher` 如果存在）

### 步骤 1：读取文件，确认要移除的测试类

需要移除的测试类：
- `TestCalcR` — 测试 `_calc_R` 函数
- `TestAggregate` — 测试 `_aggregate` 函数
- `TestConfidenceEngineCalculate` — 测试 `ConfidenceEngine.calculate()`
- `TestConfidenceEngineAiOnly` — 测试 `ConfidenceEngine.calculate_ai_only()`

### 步骤 2：逐个删除这些类

找到每个类的定义行（如 `class TestCalcR(unittest.TestCase):`），删除从该行到下一个 `class` 定义之前的所有内容。

**精确替换指令**：

1. 找到 `class TestCalcR` 开头，删除到 `class TestAggregate` 之前
2. 找到 `class TestAggregate` 开头，删除到 `class TestConfidenceEngineCalculate` 之前
3. 找到 `class TestConfidenceEngineCalculate` 开头，删除到 `class TestConfidenceEngineAiOnly` 之前
4. 找到 `class TestConfidenceEngineAiOnly` 开头，删除到下一个 `class` 或 `if __name__` 之前

**验证**：
```bash
python -m pytest tests/test_confidence_engine.py -v
# 预期：剩余测试类全部 GREEN，已移除的类不再出现
```

---

## 任务 4.6：移除 Feature Flag

**文件**：`media_importer/features/import_flow/steps/scrape.py`

**操作**：移除 `use_new_match_engine` feature flag，使新匹配引擎成为默认且唯一路径

### 替换 1：移除 feature flag 变量

找到（阶段 1 任务 1.7 添加的代码）：

```python
        # Feature flag: 使用新匹配引擎
        use_new_engine = self.config.get("features", {}).get("use_new_match_engine", True)
```

替换为：

```python
```

### 替换 2：移除 feature flag 条件分支

找到（阶段 1 任务 1.7 添加的代码）：

```python
        # 如果使用新匹配引擎，从 result 中提取 match_level
        if use_new_engine and 'match_level' not in result:
            # 旧 scraper 不返回 match_level，用 confidence 映射
            confidence = result.get('confidence', 0)
            if confidence >= 0.8:
                result['match_level'] = 'AUTO_PASS'
            elif confidence >= 0.5:
                result['match_level'] = 'NEEDS_CONFIRM'
            else:
                result['match_level'] = 'NEEDS_CONFIRM'
            result['match_concerns'] = []
```

替换为：

```python
        # 新匹配引擎：确保 match_level 存在
        if 'match_level' not in result:
            # 旧 scraper 不返回 match_level，用 confidence 映射
            confidence = result.get('confidence', 0)
            if confidence >= 0.8:
                result['match_level'] = 'AUTO_PASS'
            elif confidence >= 0.5:
                result['match_level'] = 'NEEDS_CONFIRM'
            else:
                result['match_level'] = 'NEEDS_CONFIRM'
            result['match_concerns'] = []
```

### 替换 3：移除配置中的 feature flag

**文件**：`config/config.yaml`（如果存在）

搜索 `use_new_match_engine`，如果找到则删除该行。

**验证**：
```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/features/import_flow/steps/scrape.py
grep -r "use_new_match_engine" media_importer/ config/
# 预期：无结果
```

---

## 任务 4.7：更新 API 文档

**文件**：`docs/architecture/api.md`

**操作**：在 API 文档中更新 `_scrape_preview` 端点的返回结构说明

找到 `_scrape_preview` 或 `/scrape/preview` 相关的 API 文档区域，添加以下字段说明：

```markdown
### 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| match_level | string | 匹配级别：AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM |
| match_concerns | array | 匹配疑虑原因列表，每项包含 code/message/detail |
| match_trace | object | 三级匹配路径追踪 |

### 已废弃字段

| 字段 | 类型 | 说明 |
|------|------|------|
| confidence | float | 已废弃，保留兼容。新代码应使用 match_level |
| scrape_confidence | float | 已废弃，保留兼容。新代码应使用 match_level |
```

**文件**：`docs/standards/api.md`

**操作**：同步更新 API 标准文档中的相关字段说明。

**验证**：
- 确认文档中包含 `match_level` 字段说明

---

## 任务 4.8：最终全量回归验证

**执行**：

```bash
# 1. 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests

# 2. 非 UI 全量测试
python -m pytest tests/ \
  --ignore=tests/test_*_ui.py \
  --ignore=tests/test_frontend_*.py \
  --ignore=tests/test_scrape_ui.py \
  -v

# 3. 架构护栏
python -m pytest tests/test_architecture_guards.py -v

# 4. 新增测试全部运行
python -m pytest tests/test_match_engine.py tests/test_match_pipeline_integration.py tests/test_scrape_preview_api.py tests/test_review_decision_v2.py tests/test_config_migration_v3.py -v

# 5. 置信度引擎兼容层验证
python -c "
from media_importer.features.scraping.confidence_engine import ConfidenceEngine
e = ConfidenceEngine()
level = e.get_confidence_level(0.9)
print(f'get_confidence_level(0.9) = {level}')
result = e.calculate({}, {}, None)
print(f'calculate() = {result.final_confidence}')
print('兼容层验证通过')
"

# 6. 确认旧代码导入正常
python -c "
from media_importer.features.scraping.confidence_engine import ConfidenceEngine, FilenameCleaner, TitleMatcher
from media_importer.features.scraping.confidence_models import _calc_R, _aggregate, DEFAULT_CONFIDENCE_CONFIG
from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.features.scraping.match_models import MatchResult, MatchConcern
print('所有导入正常')
"
```

**预期**：
- 编译检查：0 errors
- 非 UI 测试无新增失败
- `test_confidence_engine.py` 中 `TestCalcR`、`TestAggregate`、`TestConfidenceEngineCalculate`、`TestConfidenceEngineAiOnly` 已移除
- 兼容层验证通过
- 所有导入正常

---

## 阶段 4 完成标准

- [ ] `confidence_engine.py` 改为薄兼容层，旧代码导入不报错
- [ ] `confidence_models.py` 中 `_calc_R` 和 `_aggregate` 改为兼容桩
- [ ] `DEFAULT_CONFIDENCE_CONFIG` 已简化，移除不再使用的参数
- [ ] `title_matcher.py` 编译通过（无需修改）
- [ ] `tasks.js` 中无置信度关键字
- [ ] `test_confidence_engine.py` 中旧测试类已移除
- [ ] `use_new_match_engine` feature flag 已移除
- [ ] API 文档已更新
- [ ] 全量回归验证通过
- [ ] 兼容层导入验证通过

---

## 全项目完成标准（阶段 1-4 汇总）

- [ ] 三级匹配引擎（match_engine.py）完整实现：Tier1 精确匹配 → Tier2 上下文辅助 → Tier3 用户确认
- [ ] AI 辅助判断（tier2_judge）正常工作
- [ ] ReviewDecisionService 基于 match_level 判断
- [ ] DB 新增 match_level / match_concerns / match_trace 字段
- [ ] 配置迁移 v2→v3 正常
- [ ] 前端展示三级匹配标签，移除置信度 UI
- [ ] 模拟运行展示三级匹配路径
- [ ] 待确认任务展示疑虑原因
- [ ] 旧代码兼容层正常工作
- [ ] Feature flag 已移除
- [ ] 全量回归测试通过

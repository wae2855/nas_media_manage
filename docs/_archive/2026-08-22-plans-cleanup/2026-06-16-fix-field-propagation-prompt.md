# 修复任务：信息架构字段传递断裂

你是一名**执行型开发者**。本任务是上一个重构计划（已完成）的补丁，修复 review 中发现的 3 个严重问题。

---

## 一、任务背景

上一个计划"刮削信息职责拆分"已完成（Phase A-R + 5.1），将 `confirm_reason` 万能胶拆成 6 层独立字段（L1 match_level/match_tier、L2 tier_short_reason、L3 ai_reason、L4 selected_candidate、L5 concerns、L6 trace_steps）。

但 review 发现在**正式任务流程**中，新字段没有被正确传递，导致：
- 模拟器刮削结果有 `selected_candidate`、`tier_short_reason`、`ai_reason`
- **正式任务**的 `scrape_result` 中这些字段**全是空的**
- 前端任务卡片/列表/详情显示空白

**根本原因**：模拟器走 `scrape_preview_job.py`（已透传字段），正式任务走 `scrape.py`（漏了透传）。

---

## 二、需修复的 3 个问题

### 问题 1（P0）：scrape.py 未透传新字段

**文件**：`media_importer/features/import_flow/steps/scrape.py`

**当前代码**（约 L51-53）：

```python
match_dict = match_result.to_dict()
result['match_level'] = match_dict['match_level']
result['match_concerns'] = match_dict['concerns']
result['match_trace'] = match_dict
```

**问题**：`match_dict` 包含 `selected_candidate` / `tier_short_reason` / `ai_reason` / `match_tier`，但只有前三个字段被取出，新字段全丢了。

**修复**：在 `result['match_trace'] = match_dict` 后追加 4 行：

```python
match_dict = match_result.to_dict()
result['match_level'] = match_dict['match_level']
result['match_concerns'] = match_dict['concerns']
result['match_trace'] = match_dict
# 新增：透传 L1/L2/L3/L4 字段到 scrape_result（与 scrape_preview_job.py 保持一致）
result['match_tier'] = match_dict.get('match_tier', 0)
result['tier_short_reason'] = match_dict.get('tier_short_reason', '')
result['ai_reason'] = match_dict.get('ai_reason', '')
result['selected_candidate'] = match_dict.get('selected_candidate')
```

---

### 问题 2（P0）：_confirm_reason 未赋值

**文件**：`media_importer/features/import_flow/runner.py` 第 185 行

**当前代码**：

```python
if task.get("_needs_confirm"):
    tier_short = task.get("_confirm_reason", TierShortReason.UNKNOWN)
    db_update_task(self.task_manager.conn, tid,
                   **mark_confirming(ctx, tier_short))
```

**问题**：`scrape.py` 设了 `task["_needs_confirm"] = True`，但**从未设** `task["_confirm_reason"]`。所以 `tier_short` 永远是 `TierShortReason.UNKNOWN`（"匹配结果未知"），所有 NEEDS_CONFIRM 任务的失败原因都显示这句话。

**修复方案**：不要再用 `_confirm_reason` 这个独立字段（容易再次出现赋值遗漏）。改为**直接从 `scrape_result.tier_short_reason` 读取**（问题 1 修复后这个字段就有值了）。

把 runner.py 第 184-185 行改为：

```python
if task.get("_needs_confirm"):
    scrape_result = task.get("scrape_result", {})
    tier_short = scrape_result.get('tier_short_reason') or TierShortReason.UNKNOWN
    db_update_task(self.task_manager.conn, tid,
                   **mark_confirming(ctx, tier_short))
```

**清理**：搜索 `"_confirm_reason"` 字符串，如果其他地方还有引用，也一并清理。预期只在 runner.py 第 185 行出现。

---

### 问题 3（P1）：review.py 仍用万能胶拼接

**文件**：`media_importer/features/import_flow/services/review.py`

**当前问题**：`_build_confirm_reason` 方法把 concerns、ai_reasons、缺字段提示、候选提示全用 `；` 拼成一个长字符串。这个字符串最后被 `scrape.py:228` 塞进 `concerns[].message`，污染了 L5 关注点列表。

**目标**：把 `_build_confirm_reason` 重构为 `_build_concerns`，返回结构化 concerns 列表，不再拼接字符串。

**步骤 3.1**：修改 `ReviewDecision` dataclass（review.py 顶部）

**当前**（约 L5-9）：

```python
@dataclass
class ReviewDecision:
    action: str
    reason: str = ""
    warnings: list = field(default_factory=list)
```

**改为**：

```python
@dataclass
class ReviewDecision:
    action: str
    concerns: list = field(default_factory=list)  # 结构化关注点（新增）
    warnings: list = field(default_factory=list)
    # reason 字段删除（不再需要拼接串）
```

**步骤 3.2**：修改 `evaluate` 方法，把所有 `reason=...` 改为 `concerns=[...]`

**当前**（约 L12-40）：

```python
def evaluate(self, scraped: dict) -> ReviewDecision:
    if not scraped:
        return ReviewDecision(action="failed", reason="刮削结果为空，无法验证")

    match_level = scraped.get("match_level", "NEEDS_CONFIRM")
    concerns = scraped.get("match_concerns", [])
    missing_fields, warnings = self._validate_required_fields(scraped)

    if missing_fields:
        reason = self._build_confirm_reason(scraped, missing_fields, concerns)
        return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

    if match_level == "AUTO_PASS":
        return ReviewDecision(action="continue", warnings=warnings)

    if match_level == "CONTEXT_PASS":
        return ReviewDecision(action="continue", warnings=warnings)

    if match_level == "NEEDS_CONFIRM":
        reason = self._build_confirm_reason(scraped, missing_fields, concerns)
        return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

    return ReviewDecision(action="failed", reason="匹配失败，无法识别", warnings=warnings)
```

**改为**：

```python
def evaluate(self, scraped: dict) -> ReviewDecision:
    if not scraped:
        return ReviewDecision(
            action="failed",
            concerns=[{"code": "EMPTY_RESULT", "message": "刮削结果为空，无法验证", "detail": ""}],
        )

    match_level = scraped.get("match_level", "NEEDS_CONFIRM")
    existing_concerns = scraped.get("match_concerns", [])
    missing_fields, warnings = self._validate_required_fields(scraped)

    if missing_fields:
        new_concerns = self._build_concerns(scraped, missing_fields, existing_concerns)
        return ReviewDecision(action="confirm", concerns=new_concerns, warnings=warnings)

    if match_level == "AUTO_PASS":
        return ReviewDecision(action="continue", warnings=warnings)

    if match_level == "CONTEXT_PASS":
        return ReviewDecision(action="continue", warnings=warnings)

    if match_level == "NEEDS_CONFIRM":
        new_concerns = self._build_concerns(scraped, missing_fields, existing_concerns)
        return ReviewDecision(action="confirm", concerns=new_concerns, warnings=warnings)

    return ReviewDecision(
        action="failed",
        concerns=[{"code": "MATCH_FAILED", "message": "匹配失败，无法识别", "detail": ""}],
        warnings=warnings,
    )
```

**步骤 3.3**：把 `_build_confirm_reason` 方法整体替换为 `_build_concerns`

**当前**（约 L40-72，整个 `_build_confirm_reason` 函数）：

删除这个函数，替换为：

```python
def _build_concerns(self, scraped: dict, missing_fields: list, existing_concerns: list) -> list:
    """构建结构化关注点列表（不再拼接字符串）"""
    new_concerns = []

    # 1. 保留已有 concerns（来自匹配阶段）
    for concern in existing_concerns or []:
        if isinstance(concern, dict) and concern.get("message"):
            new_concerns.append(concern)

    # 2. 缺字段 → 结构化 concern
    if missing_fields:
        suggestions = self._build_suggestions(missing_fields, scraped)
        detail = "建议补充或核对：" + "、".join(suggestions) if suggestions else ""
        new_concerns.append({
            "code": "MISSING_FIELDS",
            "message": "缺失字段需人工确认",
            "detail": detail,
        })

    # 3. 无 provider_id → 结构化 concern
    provider_id = scraped.get("provider_id") or ""
    if not provider_id:
        new_concerns.append({
            "code": "NO_PROVIDER_MATCH",
            "message": "未匹配到可直接入库的 Provider 结果",
            "detail": "",
        })

    # 4. 候选列表提示
    candidates = (scraped.get("match_trace") or {}).get("candidates") or []
    if candidates:
        new_concerns.append({
            "code": "CANDIDATES_AVAILABLE",
            "message": "已默认加载候选列表中排序最靠前的结果，请检查后确认",
            "detail": "",
        })

    return new_concerns
```

**步骤 3.4**：检查 `_collect_ai_reasons` 方法是否还被其他地方调用

```bash
grep -rn "_collect_ai_reasons" media_importer/ --include="*.py"
```

如果只在已删除的 `_build_confirm_reason` 里被调用，一并删除这个辅助方法。如果还有其他调用方，保留。

**步骤 3.5**：修改 `scrape.py` 调用方，适配新的 `decision.concerns`

**当前代码**（`media_importer/features/import_flow/steps/scrape.py` 约 L225-235）：

```python
decision = ReviewDecisionService().evaluate(scraped)

if decision.action == "confirm":
    task["_needs_confirm"] = True
    if decision.reason:
        concerns = scraped.get('match_concerns', [])
        concerns.append({
            "message": decision.reason,
            "code": "VALIDATE_CONFIRM",
            "detail": "",
        })
    self._log("warn", decision.reason, task, "validate")
    return
```

**改为**：

```python
decision = ReviewDecisionService().evaluate(scraped)

if decision.action == "confirm":
    task["_needs_confirm"] = True
    # 把 review 阶段生成的结构化 concerns 合并到 scrape_result
    if decision.concerns:
        existing = scraped.get('match_concerns', [])
        # 避免重复（按 code+message 去重）
        existing_keys = {(c.get('code', ''), c.get('message', '')) for c in existing if isinstance(c, dict)}
        for c in decision.concerns:
            key = (c.get('code', ''), c.get('message', ''))
            if key not in existing_keys:
                existing.append(c)
        scraped['match_concerns'] = existing
        # 摘要日志（不要把整个 concerns 拼起来，只记录数量）
        self._log("warn", f"需要人工确认，共 {len(existing)} 条关注点", task, "validate")
    else:
        self._log("warn", "需要人工确认", task, "validate")
    return

if decision.action == "needs_review":
    task["skip_reason"] = "需要人工审核"  # 不再用 decision.reason
    task["_needs_review"] = True
    self._log("warn", "需要人工审核", task, "validate")
    return

if decision.action == "failed":
    task["_force_fail"] = True
    fail_reason = "匹配失败，无法识别"  # 不再用 decision.reason
    task["_fail_reason"] = fail_reason
    self._log("warn", fail_reason, task, "validate")
    return
```

**注意**：搜索 `scrape.py` 中所有 `decision.reason` 的引用，全部清理或替换。预期在 L228、L232、L235、L239、L241、L246 附近有多处。

---

## 三、次要清理（可选，建议一起做）

### 清理 1：`MatchResult.provider_id` 类型统一

**文件**：`media_importer/features/scraping/match_models.py` 约 L54

**当前**：`provider_id: Optional[int] = None`

**问题**：实际使用中 `provider_id` 多为字符串（来自 `str(item.item_id)`），类型注解和实际不一致。

**改为**：`provider_id: Optional[str] = None`

**验证**：跑测试，确保没有类型错误。

### 清理 2：删除 `dimension_resolution.py` 死字段

**文件**：`media_importer/features/scraping/dimension_resolution.py`

搜索 `confirm_reason_parts`，应该在 L22、L59、L78 三处。这是 Phase E 之前的残留。

**验证先确认无人调用**：

```bash
grep -rn "confirm_reason_parts" media_importer/ --include="*.py"
```

如果只在 `dimension_resolution.py` 内部出现（定义和默认值），删除这三处引用。如果外部还有调用，**保留不删**。

---

## 四、测试要求

### 新建测试文件：`tests/test_formal_flow_field_propagation.py`

**目标**：端到端验证正式任务流程能正确把新字段写到 `scrape_result` JSON。

```python
"""测试正式任务流程的字段传递（修复 scrape.py 透传断裂）"""
import json
import unittest
from unittest.mock import MagicMock, patch


class TestScrapeResultFieldPropagation(unittest.TestCase):
    """验证 scrape.py 把 match_result 的 L1-L4 字段透传到 scrape_result"""

    def test_scrape_result_contains_selected_candidate(self):
        """scrape_result 应包含 selected_candidate 字段"""
        # 模拟 match_result 返回结构化数据
        mock_match_result = MagicMock()
        mock_match_result.to_dict.return_value = {
            "match_level": "CONTEXT_PASS",
            "match_tier": 2,
            "tier_short_reason": "AI 高确定性匹配通过",
            "ai_reason": "AI 推理内容",
            "selected_candidate": {
                "provider_type": "tmdb",
                "provider_id": "637",
                "title": "美丽人生",
                "year": 1997,
                "media_type": "movie",
                "why_selected": "ai_suggestion",
                "score": 8.5,
            },
            "concerns": [],
            "trace": [],
            "candidates": [],
        }
        
        # 模拟 scraper.scrape 返回的 result
        result = {
            "title_cn": "美丽人生",
            "year": 1997,
            "media_type": "movie",
            "provider_type": "tmdb",
            "provider_id": "637",
        }
        
        # 复现 scrape.py 的字段透传逻辑
        match_dict = mock_match_result.to_dict()
        result['match_level'] = match_dict['match_level']
        result['match_concerns'] = match_dict['concerns']
        result['match_trace'] = match_dict
        # 这是修复后应该有的 4 行
        result['match_tier'] = match_dict.get('match_tier', 0)
        result['tier_short_reason'] = match_dict.get('tier_short_reason', '')
        result['ai_reason'] = match_dict.get('ai_reason', '')
        result['selected_candidate'] = match_dict.get('selected_candidate')
        
        # 断言
        self.assertEqual(result['match_tier'], 2)
        self.assertEqual(result['tier_short_reason'], "AI 高确定性匹配通过")
        self.assertEqual(result['ai_reason'], "AI 推理内容")
        self.assertIsNotNone(result['selected_candidate'])
        self.assertEqual(result['selected_candidate']['provider_id'], "637")
        self.assertEqual(result['selected_candidate']['why_selected'], "ai_suggestion")


class TestRunnerReadsTierShortReason(unittest.TestCase):
    """验证 runner.py 从 scrape_result 读 tier_short_reason（不再依赖 _confirm_reason）"""

    def test_runner_reads_tier_short_from_scrape_result(self):
        """_confirm_reason 未设时，runner 应从 scrape_result 兜底"""
        task = {
            "_needs_confirm": True,
            "scrape_result": {
                "tier_short_reason": "AI 建议候选，需确认",
            },
            # 注意：不设 _confirm_reason（模拟 scrape.py 的 bug 场景）
        }
        
        from media_importer.features.scraping.match_enums import TierShortReason
        scrape_result = task.get("scrape_result", {})
        tier_short = scrape_result.get('tier_short_reason') or TierShortReason.UNKNOWN
        
        self.assertEqual(tier_short, "AI 建议候选，需确认")

    def test_runner_fallback_when_no_tier_short(self):
        """scrape_result 没有 tier_short_reason 时兜底为 UNKNOWN"""
        task = {
            "_needs_confirm": True,
            "scrape_result": {},
        }
        
        from media_importer.features.scraping.match_enums import TierShortReason
        scrape_result = task.get("scrape_result", {})
        tier_short = scrape_result.get('tier_short_reason') or TierShortReason.UNKNOWN
        
        self.assertEqual(tier_short, TierShortReason.UNKNOWN)


class TestReviewDecisionStructuredConcerns(unittest.TestCase):
    """验证 ReviewDecision 返回结构化 concerns 而非字符串 reason"""

    def test_review_decision_has_concerns_not_reason(self):
        """ReviewDecision 应有 concerns 字段，不应有 reason"""
        from media_importer.features.import_flow.services.review import ReviewDecision
        import inspect
        
        # 验证字段定义
        src = inspect.getsource(ReviewDecision)
        self.assertIn("concerns", src)
        # reason 字段应该被删除（或至少不再被 evaluate 使用）
        
    def test_missing_fields_generates_structured_concern(self):
        """缺字段时应生成 MISSING_FIELDS 结构化 concern，不是拼接串"""
        from media_importer.features.import_flow.services.review import ReviewDecisionService
        
        service = ReviewDecisionService()
        scraped = {
            "match_level": "NEEDS_CONFIRM",
            "match_concerns": [],
            "provider_id": "637",
            "match_trace": {"candidates": []},
            # 模拟缺字段
        }
        
        # 模拟 _validate_required_fields 返回缺字段
        with patch.object(service, '_validate_required_fields', return_value=(["year"], [])):
            decision = service.evaluate(scraped)
        
        self.assertEqual(decision.action, "confirm")
        self.assertTrue(len(decision.concerns) > 0)
        # 应有 MISSING_FIELDS 类型的 concern
        codes = [c.get("code") for c in decision.concerns]
        self.assertIn("MISSING_FIELDS", codes)
        # 每个 concern 应有 code/message/detail 结构
        for c in decision.concerns:
            self.assertIn("code", c)
            self.assertIn("message", c)
            self.assertIn("detail", c)

    def test_no_provider_match_generates_structured_concern(self):
        """无 provider_id 时应生成 NO_PROVIDER_MATCH concern"""
        from media_importer.features.import_flow.services.review import ReviewDecisionService
        
        service = ReviewDecisionService()
        scraped = {
            "match_level": "NEEDS_CONFIRM",
            "match_concerns": [],
            "provider_id": "",  # 空
            "match_trace": {"candidates": []},
        }
        
        with patch.object(service, '_validate_required_fields', return_value=([], [])):
            decision = service.evaluate(scraped)
        
        codes = [c.get("code") for c in decision.concerns]
        self.assertIn("NO_PROVIDER_MATCH", codes)

    def test_concerns_message_not_long_concatenated_string(self):
        """concern message 不应是 ；
        确保每个 concern 的 message 是短句，不是拼接串"""
        from media_importer.features.import_flow.services.review import ReviewDecisionService
        
        service = ReviewDecisionService()
        scraped = {
            "match_level": "NEEDS_CONFIRM",
            "match_concerns": [
                {"code": "AI_UNCERTAIN", "message": "AI 中等确定性", "detail": ""},
            ],
            "provider_id": "",
            "match_trace": {"candidates": [{"id": "1"}]},
        }
        
        with patch.object(service, '_validate_required_fields', return_value=(["year"], [])):
            decision = service.evaluate(scraped)
        
        for c in decision.concerns:
            # 单个 message 不应超过 50 字（拼接串通常 100+ 字）
            self.assertLess(len(c.get("message", "")), 50,
                            f"message 过长，可能是拼接串: {c.get('message')}")


if __name__ == "__main__":
    unittest.main()
```

**说明**：`test_scrape_result_contains_selected_candidate` 通过复现 scrape.py 的字段透传逻辑来验证（因为完整集成测试需要 mock 整个 scraper，太复杂）。如果你能写真正的端到端测试（mock scraper.scrape 返回 + 跑完整 scrape step），更好。

---

## 五、硬性规则

### 1. Python 缓存陷阱（重要！）

本项目用 `.pyc` 缓存。**每次改 Python 代码后**必须执行：

```bash
find /Users/wangwei/Documents/code/nas_media_manage -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /Users/wangwei/Documents/code/nas_media_manage -name "*.pyc" -delete 2>/dev/null
pkill -9 -f "python.*media_importer" 2>/dev/null
sleep 2
source /Users/wangwei/Documents/code/nas_media_manage/.venv/bin/activate
PYTHONPATH="/Users/wangwei/Documents/code/nas_media_manage" python -m media_importer.media_importer -c /Users/wangwei/Documents/code/nas_media_manage/config/config.yaml serve -p 9855 --host 0.0.0.0 > /tmp/nas_media_server.log 2>&1 &
sleep 5
```

### 2. 测试先行

每个问题修复后跑：

```bash
cd /Users/wangwei/Documents/code/nas_media_manage
source .venv/bin/activate
python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"
```

### 3. 不要做计划外改动

- 不要重构其他无关代码
- 不要"顺手"修复既有的 LSP 错误（如 `scenario: str` 接收 None、mixin 类属性）
- 遇到歧义停下来问

### 4. 提交规范

3 个问题分开提交：
- `修复: scrape.py 透传 L1-L4 字段到 scrape_result（问题 1）`
- `修复: runner.py 从 scrape_result 读 tier_short_reason（问题 2）`
- `重构: review.py 改为结构化 concerns，不再拼接字符串（问题 3）`

---

## 六、验收清单

### 修复后必须通过：

#### 自动化测试

```bash
# 1. 新增测试通过
python -m pytest tests/test_formal_flow_field_propagation.py -q

# 2. 既有测试不回归
python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"

# 3. 架构守卫不破坏
python -m pytest tests/test_architecture_guards.py -q

# 4. 编译通过
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests
```

#### 残留检查

```bash
# 1. _confirm_reason 不再被引用（runner.py 改读 scrape_result）
grep -rn "_confirm_reason" media_importer/ --include="*.py"
# 预期：无输出（或只在注释里）

# 2. _build_confirm_reason 函数已删除
grep -rn "_build_confirm_reason" media_importer/ --include="*.py"
# 预期：无输出

# 3. ReviewDecision 不再有 reason 字段
grep -A 5 "class ReviewDecision" media_importer/features/import_flow/services/review.py
# 预期：不含 "reason: str"

# 4. scrape.py 的 result 包含 4 个新字段
grep -A 4 "result\['match_trace'\] = match_dict" media_importer/features/import_flow/steps/scrape.py
# 预期：看到 match_tier / tier_short_reason / ai_reason / selected_candidate 4 行
```

#### 端到端验证（模拟器对比正式任务）

启动服务器后，用 Playwright 或手动验证：

1. **模拟器**跑 `爱神.mkv` → 任务详情的"最终用了"区块显示 `爱神 (2004) · AI 建议`
2. **正式任务**（实际投递一个文件入库）→ 任务卡片的"最终用了"区块也显示同样的结构化内容
3. **NEEDS_CONFIRM 正式任务** → 列表行副标题显示 `tier_short_reason`（不再是"匹配结果未知"）
4. **失败任务** → 卡片显示具体原因（不是 UNKNOWN）

---

## 七、实施顺序

1. **先修复问题 1**（scrape.py 透传）—— 简单，4 行代码
2. **再修复问题 2**（runner.py 读取）—— 简单，2 行代码
3. **最后修复问题 3**（review.py 重构）—— 复杂，需要改 3 个地方（ReviewDecision 定义、evaluate 方法、_build_concerns 替换）+ 适配 scrape.py 调用方
4. **跑全部测试**
5. **做次要清理**（provider_id 类型、dimension_resolution 死字段）—— 如果时间允许
6. **验证端到端**

---

## 八、完成后报告

完成所有修复后，向用户报告：

1. 3 个问题是否都已修复（是/否）
2. 新增测试用例数量
3. 全部测试是否通过（数量）
4. 端到端验证结果（模拟器和正式任务字段一致性）
5. 是否做了次要清理（provider_id 类型、死字段）

---

**开始执行。先从问题 1 开始。**

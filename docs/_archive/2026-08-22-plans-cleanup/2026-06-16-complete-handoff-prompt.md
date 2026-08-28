# 影音库刮削系统重构 - 开发执行提示词

你是一名**执行型开发者**，按照本提示词逐步实施一个名为"刮削信息职责拆分"的重构计划。所有架构决策、字段定义、提示词、测试边界都已设计好，你的职责是按 Phase 顺序逐步实施并验证。

---

## 一、项目背景

**仓库**：`/Users/wangwei/Documents/code/nas_media_manage`  
**技术栈**：Python 3.12 + 原生 HTTP API + 原生 HTML/CSS/JS + SQLite  
**运行环境**：飞牛 fnOS NAS  
**预估工作量**：约 24 小时，分 15 个 Phase

**业务背景**：这是个 NAS 影视库自动整理系统。用户扔一堆视频文件进来，系统通过三级匹配（Provider 精确匹配 → AI 辅助匹配 → 用户确认）识别影视信息，按规则分类入库。

**本次重构要解决的问题**：
1. **信息职责混乱**：所有刮削描述糊在一个 `confirm_reason` 字符串里，列表/卡片/详情视图无法各取所需
2. **候选数据丢失**：Tier 1 找到的候选被丢弃，Tier 2/3 重新搜索结果不一致
3. **垃圾文件浪费资源**：AI 无法识别的文件名仍会走完整流程
4. **字段名 bug**：追踪弹窗显示"-"因为前后端字段名对不上

---

## 二、硬性规则

### 1. 你的角色边界

✅ **按 Phase 顺序逐步实施**，每个 Phase 完成后跑测试验证  
✅ **遇到歧义停止并问**，不要自己拍板  
✅ **每个 Phase 单独提交**，提交信息格式 `Phase X: 简述`  
✅ **修改前先读相关文件**，理解上下文  

❌ **不要做架构决策**（如改字段名、改枚举值、调整 Phase 顺序）  
❌ **不要删除计划外的代码**（除非计划明确要求）  
❌ **不要跳过测试**（每个 Phase 都有验证清单）  
❌ **不要修改 `docs/` 目录的文档**  
❌ **不要修既有的 LSP 错误**（详见规则 5）

### 2. 测试先行

每个 Phase 完成后**必须**运行：

```bash
cd /Users/wangwei/Documents/code/nas_media_manage
source .venv/bin/activate
python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"
```

测试通过才能进入下一 Phase。新增功能必须同步写单元测试。

### 3. 文件操作规范

- **修改前必须先读文件**（用 Read 工具）
- **优先用 edit 工具**做精确替换，不要用 write 重写整个文件
- **复杂改动用 morph_edit**（多个分散位置）
- **新建文件用 write**

### 4. Python 缓存陷阱（重要！）

本项目用 `.pyc` 缓存，改了代码但服务器没重启会看到旧行为。**每次改 Python 代码后**必须执行：

```bash
find /Users/wangwei/Documents/code/nas_media_manage -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /Users/wangwei/Documents/code/nas_media_manage -name "*.pyc" -delete 2>/dev/null
pkill -9 -f "python.*media_importer" 2>/dev/null
sleep 2
source /Users/wangwei/Documents/code/nas_media_manage/.venv/bin/activate
PYTHONPATH="/Users/wangwei/Documents/code/nas_media_manage" python -m media_importer.media_importer -c /Users/wangwei/Documents/code/nas_media_manage/config/config.yaml serve -p 9855 --host 0.0.0.0 > /tmp/nas_media_server.log 2>&1 &
sleep 5
```

### 5. LSP 错误处理

本项目有**既有的 LSP 类型错误**（如 `scenario: str` 接收 None、mixin 类属性未声明、`sync_playwright` 可能未绑定）。这些是**已有的技术债**，不要修。只关注你**新增代码**引入的 LSP 错误。

### 6. 提交规范

- 每个 Phase 单独提交
- 提交信息：`Phase X: 简述`（如 `Phase A: 新建 match_enums.py 枚举定义`）
- 不要批量提交多个 Phase

---

## 三、核心数据模型设计（不要偏离）

### 字段语义定义

| 字段 | 取值 | 含义 |
|------|------|------|
| `match_level` | `AUTO_PASS` / `CONTEXT_PASS` / `NEEDS_CONFIRM` / `FAILED` | 匹配状态 |
| `match_tier` | 1 / 2 / 3 | 1=Provider 精确匹配，2=AI 辅助，3=AI 不可用降级 |
| `is_valid` | `true` / `false` | 文件名是否含可识别影视信息（false → FAILED） |
| `certainty` | `high` / `medium` | AI 把握度（`low` 不应出现，兜底为 medium） |
| `why_selected` | `unique_match` / `top_rated` / `ai_suggestion` / `first_candidate` / `user_pick` | 候选选择依据 |

### 信息职责 6 层模型

| Layer | 字段 | 定位 | 展示位置 |
|-------|------|------|---------|
| L1 | `match_level` / `match_tier` | 匹配状态 | 所有视图状态标签 |
| L2 | `tier_short_reason`（≤30字） | 一句话原因 | 列表行副标题、卡片摘要 |
| L3 | `ai_reason` | AI 原始推理 | 卡片"AI 怎么说"、详情 Tier 2 步骤 |
| L4 | `selected_candidate`（结构化） | 最终选择+原因 | 卡片"最终用了"、详情刮削结果 |
| L5 | `concerns[]` | 关注点列表 | 详情"注意事项"、深度追踪 |
| L6 | `trace_steps[].{reason, ai_reason}` | 过程追踪 | 详情时间轴、追踪弹窗 |

### is_valid 判定边界（Phase P 核心）

| 文件名示例 | is_valid | 理由 |
|-----------|:---:|------|
| `123uyyt.mkv` | false | 随机字符 |
| `消防员.mkv`（候选 5 部同名） | false | 通用词歧义 |
| `消防员.mkv`（候选唯一⭐7+） | true | 候选确定 |
| `泰坦尼克号.mkv` | true | 知名片名 |
| `Movie.2023.mkv` | false | 占位词 |
| `美丽人生.mkv` | true | 同名多版但片名明确 |

**候选数量规则**：≥3 部同名 → 倾向 false；唯一且高分 → 倾向 true。

---

## 四、实施顺序（严格按此顺序）

### 阶段 1：数据模型基础

#### Phase A：新建枚举文件

**新建文件**：`media_importer/features/scraping/match_enums.py`

**完整内容**：

```python
"""刮削匹配相关的枚举定义"""


class TierShortReason:
    """L2: 一句话原因枚举（程序兜底，AI 应优先返回 ≤30 字）"""
    # Tier 1
    TIER1_UNIQUE = "唯一精确匹配"
    TIER1_TOP_RATED = "同名{count}部，自动选评分最高"
    TIER1_MULTI = "{count}部同名作品，需确认"
    TIER1_FUZZY = "标题不完全匹配"
    TIER1_NO_RESULT = "Provider 无结果"
    # Tier 2
    TIER2_HIGH_PASS = "AI 高确定性匹配通过"
    TIER2_MEDIUM = "AI 建议候选，需确认"
    TIER2_LOW = "AI 低确定性，需确认"
    TIER2_AI_FAILED = "AI 不可用，降级到候选列表"
    TIER2_INVALID = "文件名无可识别影视信息"
    # Tier 3
    TIER3_FALLBACK = "AI 不可用，候选列表供选择"
    # 兜底
    UNKNOWN = "匹配结果未知"


class WhySelected:
    """L4: 最终候选选择原因枚举"""
    UNIQUE_MATCH = "unique_match"           # 唯一精确匹配
    TOP_RATED = "top_rated"                 # 评分打破平局
    AI_SUGGESTION = "ai_suggestion"         # AI 建议（含年份纠正等）
    FIRST_CANDIDATE = "first_candidate"     # Provider 排序第一（AI 不可用降级）
    USER_PICK = "user_pick"                 # 用户人工选择（review 后写入）


class MatchTier:
    """L1: match_tier 枚举（明确语义）"""
    TIER1 = 1  # Provider 精确匹配
    TIER2 = 2  # AI 辅助匹配
    TIER3 = 3  # 用户确认降级
```

**验证**：

```bash
cd /Users/wangwei/Documents/code/nas_media_manage
source .venv/bin/activate
python -c "from media_importer.features.scraping.match_enums import TierShortReason, WhySelected, MatchTier; print('OK')"
```

---

#### Phase B：扩展 MatchResult dataclass

**修改文件**：`media_importer/features/scraping/match_models.py`

**改动**：

1. 新建 `SelectedCandidate` dataclass
2. `MatchResult` 新增 3 个字段：`tier_short_reason` / `ai_reason` / `selected_candidate`
3. `to_dict()` 输出新字段，**不再输出 `confirm_reason`**
4. **保留** `confirm_reason` 字段定义（避免编译错误），但默认空字符串

**完整新增/修改代码**：

```python
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SelectedCandidate:
    """L4: 最终选中的候选信息（结构化）"""
    provider_type: str = ""
    provider_id: str = ""
    title: str = ""
    year: Optional[int] = None
    media_type: str = ""
    why_selected: str = ""  # WhySelected 枚举值
    score: Optional[float] = None  # 评分（若适用）

    def to_dict(self) -> dict:
        return {
            "provider_type": self.provider_type,
            "provider_id": self.provider_id,
            "title": self.title,
            "year": self.year,
            "media_type": self.media_type,
            "why_selected": self.why_selected,
            "score": self.score,
        }


@dataclass
class MatchResult:
    # 已有字段（保留）
    match_level: str
    match_tier: int = 0
    provider_id: Optional[str] = None
    provider_title: str = ""
    concerns: List["MatchConcern"] = field(default_factory=list)
    trace_steps: List["MatchTraceStep"] = field(default_factory=list)
    candidates: List[dict] = field(default_factory=list)
    confirm_reason: str = ""  # 废弃，保留字段以便编译，但不再写入新值

    # 新增字段
    tier_short_reason: str = ""           # L2
    ai_reason: str = ""                   # L3
    selected_candidate: Optional[SelectedCandidate] = None  # L4

    def to_dict(self) -> dict:
        return {
            "match_level": self.match_level,
            "match_tier": self.match_tier,
            "provider_id": self.provider_id,
            "provider_title": self.provider_title,
            "concerns": [c.to_dict() for c in self.concerns],
            "trace": [t.to_dict() for t in self.trace_steps],
            "candidates": self.candidates,
            # 新字段
            "tier_short_reason": self.tier_short_reason,
            "ai_reason": self.ai_reason,
            "selected_candidate": self.selected_candidate.to_dict() if self.selected_candidate else None,
            # confirm_reason 废弃，不再输出
        }
```

**注意**：保留 `MatchConcern` 和 `MatchTraceStep` 原有定义不变，只改 `MatchResult` 和新增 `SelectedCandidate`。

**新建测试文件**：`tests/test_match_result_fields.py`

```python
import unittest
from media_importer.features.scraping.match_models import MatchResult, SelectedCandidate
from media_importer.features.scraping.match_enums import TierShortReason, WhySelected


class TestMatchResultFields(unittest.TestCase):
    def test_to_dict_includes_new_fields(self):
        r = MatchResult(
            match_level="AUTO_PASS",
            match_tier=1,
            tier_short_reason=TierShortReason.TIER1_UNIQUE,
            ai_reason="AI推理",
            selected_candidate=SelectedCandidate(
                provider_type="tmdb", provider_id="637",
                title="美丽人生", year=1997, media_type="movie",
                why_selected=WhySelected.UNIQUE_MATCH, score=8.5,
            ),
        )
        d = r.to_dict()
        self.assertEqual(d["tier_short_reason"], "唯一精确匹配")
        self.assertEqual(d["ai_reason"], "AI推理")
        self.assertEqual(d["selected_candidate"]["why_selected"], "unique_match")
        self.assertNotIn("confirm_reason", d)

    def test_confirm_reason_not_in_output(self):
        r = MatchResult(match_level="NEEDS_CONFIRM")
        d = r.to_dict()
        self.assertNotIn("confirm_reason", d)

    def test_selected_candidate_none(self):
        r = MatchResult(match_level="FAILED")
        d = r.to_dict()
        self.assertIsNone(d["selected_candidate"])


if __name__ == "__main__":
    unittest.main()
```

**验证**：

```bash
python -m pytest tests/test_match_result_fields.py -q
```

---

#### Phase C：Tier 1/2/3 字段生成

**修改文件**：`media_importer/features/scraping/_match_tiers_impl.py`

**目标**：在每个 `MatchResult(...)` 构造点添加新字段。

**改动清单**（每个返回点）：

| 函数 | match_level | tier_short_reason | selected_candidate.why_selected |
|------|-------------|-------------------|--------------------------------|
| `_tier1_exact_match_impl` 单匹配成功 (~L80) | AUTO_PASS | `TierShortReason.TIER1_UNIQUE` | `UNIQUE_MATCH` |
| `_tier1_exact_match_impl` 评分打破平局 (~L127) | AUTO_PASS | `TierShortReason.TIER1_TOP_RATED.format(count=N)` | `TOP_RATED` |
| `_tier2_high_certainty_impl` 成功 (~L208) | CONTEXT_PASS | `TierShortReason.TIER2_HIGH_PASS` | `AI_SUGGESTION` |
| `_tier2_medium_certainty_impl` (~L256) | NEEDS_CONFIRM | `TierShortReason.TIER2_MEDIUM` | `AI_SUGGESTION`（若候选非空） |
| `_tier3_user_confirm_impl` (~L467) | NEEDS_CONFIRM | `TierShortReason.TIER3_FALLBACK` | `FIRST_CANDIDATE` |

**示例改动（Tier 1 单匹配成功）**：

```python
from media_importer.features.scraping.match_enums import TierShortReason, WhySelected
from media_importer.features.scraping.match_models import SelectedCandidate

# 在每个 MatchResult(...) 构造点：
return MatchResult(
    match_level="AUTO_PASS",
    provider_id=item.item_id,
    provider_title=item.title,
    match_tier=1,
    trace_steps=trace_steps,
    candidates=[{...}],
    confirm_reason="",  # ← 不再设置（保留字段）
    tier_short_reason=TierShortReason.TIER1_UNIQUE,
    selected_candidate=SelectedCandidate(
        provider_type=item.provider_type,
        provider_id=item.item_id,
        title=item.title,
        year=item.year,
        media_type=item.media_type,
        why_selected=WhySelected.UNIQUE_MATCH,
        score=item.vote_average,
    ),
)
```

**关键点**：
- 所有 `confirm_reason="..."` 改为 `confirm_reason=""`
- `tier_short_reason` 用 `TierShortReason` 枚举
- `selected_candidate` 用 `SelectedCandidate(...)` 构造
- 候选为空时（如 Tier 2 medium 无候选）`selected_candidate=None`

**验证**：跑全部测试，已有 tier2 测试可能因 `confirm_reason` 不再输出而失败，更新断言。

---

### 阶段 2：后端流程改造

#### Phase D：AI 提示词基础改造

**修改文件**：`media_importer/scraper/_llm_match_assist.py`

**目标**：让 AI 返回 `short_reason` 字段（≤30字）。

**改动 1**：修改 `_tier2_correct_impl` 的 user_parts，输出要求新增 short_reason 字段说明：

```python
user_parts = [
    # ... 已有内容 ...
    "",
    "## 输出要求",
    "返回 JSON，不要包含任何其他文字：",
    '{"corrected_title": "纠正后的标题", "corrected_year": 年份或null, "media_type_hint": "movie|tv|null", "certainty": "high|medium|low", "reason": "详细判断理由（200字内）", "short_reason": "≤30字的一句话总结，供列表显示用，必须简洁", "suggestion": "建议的搜索关键词"}',
]
```

**改动 2**：解析时兜底：

```python
result.setdefault("short_reason", "")

# 程序兜底：若 AI 未返回 short_reason 或超长，从 reason 截前 30 字
if not result.get("short_reason"):
    full_reason = result.get("reason", "")
    result["short_reason"] = full_reason[:30] + ("..." if len(full_reason) > 30 else "")
elif len(result["short_reason"]) > 33:
    result["short_reason"] = result["short_reason"][:30] + "..."
```

**改动 3**：在 `_tier2_context_match_impl` 中传递 short_reason 给子函数：

```python
ai_short_reason = ai_result.get("short_reason", "")
# 调用子函数时多传一个参数
return _tier2_high_certainty_impl(
    self, corrected_title, corrected_year, media_type_hint,
    providers, ai_reason, ai_short_reason, concerns, trace_steps,
)
```

子函数中：

```python
# 若 AI 返回了 short_reason，优先用；否则用枚举兜底
tier_short = ai_short_reason or TierShortReason.TIER2_HIGH_PASS
return MatchResult(..., tier_short_reason=tier_short, ...)
```

**注意**：Phase P 会进一步大改提示词（加 is_valid、selected_candidate_id），但 Phase D 先做基础 short_reason 支持。

---

#### Phase E：正式流程清理

**目标**：删除所有覆盖 `confirm_reason` 的代码，改为往 `concerns[]` 追加结构化 `MatchConcern`。

**文件 1**：`media_importer/features/import_flow/steps/scrape.py`

删除 ~L313 附近追加 `confirm_reason` 的逻辑（形如 `{source_label}识别的「{dim_name}={val}」已配置为不信任`）。改为：

```python
concerns.append(MatchConcern(
    code="DIM_TRUST_DOWNGRADE",
    message=f"{dim_name} 来源不被信任，需人工确认",
))
```

**文件 2**：`media_importer/features/import_flow/steps/review.py`

删除所有覆盖 `confirm_reason` 的逻辑（L38/L60/L62/L66/L71）。改为往 `concerns[]` 追加。若用户在 review 中手动选择了候选，写入 `selected_candidate.why_selected = WhySelected.USER_PICK`。

**文件 3**：`media_importer/features/import_flow/runner.py`

删除 ~L169 默认 `confirm_reason = "刮削信息不足"` 的兜底。改为：

```python
tier_short_reason = TierShortReason.UNKNOWN
```

---

#### Phase F：scrape_preview_job.py 透传

**修改文件**：`media_importer/api/scrape_preview_job.py`

**目标**：所有构造 `scrape_result` 的位置（共 7 处）加新字段透传，删除 `confirm_reason` 输出。

**改动模板**（应用到每个 scrape_result 字典）：

```python
scrape_result = {
    "title_cn": ...,
    "year": ...,
    # ... 已有字段 ...
    "match_level": match_level,
    "match_tier": match_result.match_tier,
    # 新字段透传
    "tier_short_reason": match_dict.get("tier_short_reason", ""),
    "ai_reason": match_dict.get("ai_reason", ""),
    "selected_candidate": match_dict.get("selected_candidate"),
    # confirm_reason 字段删除
}
```

**删除函数**：`_confirm_reason_from_match`（~L39-56）及其所有调用点。

---

### 阶段 3：前端基础

#### Phase G：新建统一数据装配器

**新建文件**：`media_importer/webui/js/build-match-path-data.js`

**完整内容**：

```javascript
/**
 * 把任务对象装配成 renderMatchPathPreview 所需的数据格式
 * 所有视图（详情、追踪弹窗）都应使用此函数，禁止各自拼装
 */
function buildMatchPathData(task) {
  const scrapeResult = task.scrape_result || {};
  const matchTrace = task.match_trace || scrapeResult.match_trace || {};
  const scrapeTrace = task.scrape_trace || {};
  const scrapeDimensions = task.scrape_dimensions || scrapeResult.dimensions || {};

  // L6: trace_steps
  let traceSteps = [];
  if (Array.isArray(matchTrace.trace)) {
    traceSteps = matchTrace.trace;
  } else if (Array.isArray(matchTrace.trace_steps)) {
    traceSteps = matchTrace.trace_steps;
  }

  // L5: concerns
  let concerns = [];
  if (Array.isArray(matchTrace.concerns)) {
    concerns = matchTrace.concerns;
  } else if (Array.isArray(task.match_concerns)) {
    concerns = task.match_concerns;
  }

  // L4: selected_candidate
  const selected = scrapeResult.selected_candidate || null;

  return {
    filename: task.source_filename || "",
    clean_result: scrapeResult.clean_result || {},
    match_result: {
      match_level: scrapeResult.match_level || matchTrace.match_level || "NEEDS_CONFIRM",
      match_tier: scrapeResult.match_tier || matchTrace.match_tier || 0,
      tier_short_reason: scrapeResult.tier_short_reason || matchTrace.tier_short_reason || "",
      ai_reason: scrapeResult.ai_reason || matchTrace.ai_reason || "",
      selected_candidate: selected,
      concerns: concerns,
      trace: traceSteps,
      candidates: matchTrace.candidates || [],
    },
    scrape_result: {
      ...scrapeResult,
      dimensions: scrapeDimensions,
    },
    import_path: {
      import_path: task.import_path || task.import_dir || "",
      used_fallback: task.used_fallback || false,
      matched_rule: task.matched_rule || null,
    },
  };
}
```

**修改文件**：`media_importer/webui/index.html`

在 `cinema-config-simulator.js` 引入之前加：

```html
<script src="js/build-match-path-data.js?v=1"></script>
```

---

### 阶段 4：候选数据完整性

#### Phase M：Tier 1 候选保留

**目标**：Tier 1 找到的候选不再丢弃，跨 Tier 复用。

**修改文件 1**：`media_importer/features/scraping/match_engine.py`

`MatchEngine.__init__` 加：

```python
self._pending_candidates = []  # Tier 1 找到但未自动通过的候选
```

**修改文件 2**：`media_importer/features/scraping/_match_tiers_impl.py`

在 `_tier1_exact_match_impl` 多匹配分支（~L141）保存候选：

```python
elif len(exact_matches) > 1:
    # 新增：保存候选到 self._pending_candidates
    self._pending_candidates = [
        {
            "id": item.item_id,
            "title": item.title,
            "original_title": getattr(item, 'original_title', '') or '',
            "year": item.year,
            "media_type": item.media_type,
            "provider_type": item.provider_type,
            "vote_average": item.vote_average,
            "popularity": item.raw_data.get("popularity", 0) if item.raw_data else 0,
            "vote_count": item.raw_data.get("vote_count", 0) if item.raw_data else 0,
            "poster_url": getattr(item, 'poster_url', '') or '',
        }
        for item, _ in exact_matches
    ]
    # ... 已有的评分打破平局 / concern 记录逻辑保留 ...
```

在 `_tier2_context_match_impl`（~L327）优先复用 Tier 1 候选：

```python
def _tier2_context_match_impl(self, ...):
    # ... AI 调用 ...
    
    tier1_candidates = self._pending_candidates or []
    
    if certainty == "high":
        return _tier2_high_certainty_impl(
            self, corrected_title, corrected_year, media_type_hint,
            providers, ai_reason, ai_short_reason, concerns, trace_steps,
            tier1_candidates=tier1_candidates,
        )
    # ... 其他分支同理 ...
```

子函数 `_tier2_high_certainty_impl` / `_tier2_medium_certainty_impl` 接收 `tier1_candidates` 参数：

```python
def _tier2_high_certainty_impl(
    self, corrected_title, corrected_year, media_type_hint,
    providers, ai_reason, ai_short_reason, concerns, trace_steps,
    tier1_candidates=None,
):
    candidates = []
    if tier1_candidates:
        candidates = [
            c for c in tier1_candidates
            if (not corrected_year or c.get("year") == corrected_year)
        ]
    if not candidates:
        candidates = _search_providers_impl(
            self.title_matcher, corrected_title, corrected_year, providers
        )
    # ... 后续逻辑不变 ...
```

---

#### Phase N：候选补可信度字段

**修改文件**：`media_importer/features/scraping/_match_tiers_impl.py`

**改动**：`_search_providers_impl`（~L291-308）候选字典加可信度字段：

```python
def _extract_year_from_raw(raw_data: dict):
    """从 TMDB 原始数据兜底提取年份"""
    if not raw_data:
        return None
    for key in ("release_date", "first_air_date"):
        val = raw_data.get(key, "")
        if val and len(val) >= 4:
            try:
                return int(val[:4])
            except ValueError:
                pass
    return None


def _search_providers_impl(title_matcher, title, year, providers):
    candidates = []
    for provider in providers:
        try:
            search_result = provider.search(title, year=year)
            if search_result and search_result.items:
                for item in search_result.items[:5]:
                    candidates.append({
                        "id": item.item_id,
                        "title": item.title,
                        "original_title": getattr(item, 'original_title', '') or item.title,
                        "year": item.year or _extract_year_from_raw(item.raw_data),
                        "media_type": item.media_type,
                        "provider_type": item.provider_type,
                        "poster_url": getattr(item, 'poster_url', '') or '',
                        # 新增可信度字段
                        "vote_average": item.vote_average or 0,
                        "vote_count": item.raw_data.get("vote_count", 0) if item.raw_data else 0,
                        "popularity": item.raw_data.get("popularity", 0) if item.raw_data else 0,
                    })
        except Exception as e:
            logger.warning(f"Provider {provider.__class__.__name__} 搜索失败: {e}")
            continue
    return candidates
```

同步修改 AUTO_PASS 候选字典（~L86-95）和评分打破平局候选字典（~L133-142），加同样的字段。

---

### 阶段 5：AI 提示词大改（Phase P 核心）

#### Phase P：完整提示词重设计

**修改文件**：`media_importer/scraper/_llm_match_assist.py`

**目标**：
1. AI 收到 Step 1 Provider 候选列表
2. AI 返回 `is_valid` 字段区分"非影视文件"和"猜不出"
3. AI 可直接 `selected_candidate_id` 指定候选

**改动 1**：`_tier2_correct_impl` 的 user_parts 完整替换为：

```python
# 新增：渲染 Step 1 候选列表
candidates_text = "无"
if path_context.get("provider_candidates"):
    lines = []
    for idx, c in enumerate(path_context["provider_candidates"][:5], 1):
        score = f"⭐{c.get('vote_average', 0)}"
        pop = f"热度{int(c.get('popularity', 0))}"
        title_parts = [c.get("title", "")]
        if c.get("original_title") and c["original_title"] != c.get("title"):
            title_parts.append(f"/ {c['original_title']}")
        year_part = f" ({c['year']})" if c.get("year") else ""
        media_part = f" · {c.get('media_type', '')}"
        id_part = f" · id:{c.get('id', '')}"
        lines.append(f"{idx}. {' '.join(title_parts)}{year_part}{media_part} · {score} · {pop}{id_part}")
    candidates_text = "\n".join(lines)

user_parts = [
    "## 待匹配文件信息",
    f"- 原始文件名: {original_filename}",
    f"- 正则参考标题: {clean_title or '无'}",
    f"- 正则参考年份: {year or '未知'}",
    "",
    "## 目录上下文",
    f"- 上级文件夹: {path_context.get('parent_folder', '无')}",
    f"- 上两级文件夹: {path_context.get('grandparent_folder', '无')}",
    f"- 路径段: {', '.join(path_context.get('path_segments', [])) if path_context.get('path_segments') else '无'}",
    f"- 同级文件: {', '.join(path_context.get('sibling_files', [])) if path_context.get('sibling_files') else '无'}",
    "",
    "## Provider 候选（Step 1 已找到，供你参考）",
    candidates_text,
    "",
    "## 判定规则",
    "",
    "### 第一步：判断 is_valid（文件名是否包含可识别影视信息）",
    "",
    "返回 false 的情况（宁可保守）：",
    "1. 文件名为随机字符或乱码：如 123uyyt、asdfgh、855、yyu",
    "2. 文件名为纯通用名词，对应影视过多无法具体指向：",
    '   - 单字词："消防"、"大楼"、"飞机"、"爱情"',
    '   - 通用短语："我的女神"、"那些日子"（对应几十部作品）',
    '3. 文件名明显非影视内容：如 "新建文件夹"、"未命名"、"sample"',
    "",
    "返回 true 的情况：",
    "- 包含具体片名（中文译名或原文）",
    "- 含影视特征任一：年份(2024)、季集(S01E01)、画质(1080p)、人名",
    "",
    "候选数量影响：",
    "- 同名候选 ≥ 3 部 → 倾向 is_valid=false（歧义太大）",
    "- 同名候选唯一且高分 → 倾向 is_valid=true + certainty=high",
    "",
    "### 第二步：若 is_valid=true，判断 certainty",
    "",
    "- high: 高度确信是某部具体作品（明确译名、含年份+片名、候选首位完美匹配）",
    "- medium: 有合理猜测但无法 100% 确定（同名多版本缺年份、翻译有歧义）",
    "- low: 不应出现。若 is_valid=true 但完全无法推测，应该返回 is_valid=false",
    "",
    "### 第三步：候选利用规则",
    "",
    "- 若 Step 1 候选中已有完美匹配项：填 selected_candidate_id（候选的 provider_id），程序直接采用",
    "- 若候选都不匹配但你能推测：填 corrected_title + corrected_year，程序重新搜 Provider",
    "- 若 is_valid=false：所有其他字段留空/null",
    "",
    "## 输出要求",
    "返回 JSON，不要包含任何其他文字：",
    '{"is_valid": true, "certainty": "high", "corrected_title": "...", "corrected_year": 2024, "media_type_hint": "movie", "selected_candidate_id": "637", "reason": "详细理由(200字内)", "short_reason": "≤30字总结"}',
    "",
    "若 is_valid=false：",
    '{"is_valid": false, "certainty": "", "corrected_title": "", "corrected_year": null, "media_type_hint": null, "selected_candidate_id": null, "reason": "判定理由", "short_reason": "≤30字"}',
]
```

**改动 2**：JSON 解析后扩展字段：

```python
result.setdefault("is_valid", True)  # 兜底：AI 未返回时默认 True
result.setdefault("selected_candidate_id", None)
result.setdefault("short_reason", "")

# 防御：is_valid=false 时强制清空其他字段
if not result.get("is_valid"):
    result["certainty"] = ""
    result["corrected_title"] = ""
    result["corrected_year"] = None
    result["media_type_hint"] = None
    result["selected_candidate_id"] = None

# 防御：is_valid=true 但 certainty 异常
if result.get("is_valid"):
    if result.get("certainty") not in ("high", "medium"):
        result["certainty"] = "medium"

# short_reason 长度兜底
if result.get("short_reason") and len(result["short_reason"]) > 33:
    result["short_reason"] = result["short_reason"][:30] + "..."
elif not result.get("short_reason") and result.get("reason"):
    full = result["reason"]
    result["short_reason"] = full[:30] + ("..." if len(full) > 30 else "")
```

**改动 3**：在 `_tier2_context_match_impl` 把 Tier 1 候选塞入 path_context：

```python
context["provider_candidates"] = self._pending_candidates
```

---

### 阶段 6：业务语义变更（Phase Q）

#### Phase Q：FAILED 状态

**目标**：`is_valid=false` → 任务失败，不搜 Provider。

**修改文件 1**：`media_importer/features/scraping/_match_tiers_impl.py`

在 `_tier2_context_match_impl` 解析 AI 结果后，新增 is_valid=false 分支：

```python
is_valid = ai_result.get("is_valid", True)
if not is_valid:
    concerns.append(MatchConcern(
        code="INVALID_FILENAME",
        message="AI 判定文件名无可识别影视信息",
        detail=ai_result.get("reason", ""),
    ))
    trace_steps.append(MatchTraceStep(
        tier=2,
        name="AI 辅助匹配",
        matched=False,
        reason=f"AI 判定为非影视文件: {ai_result.get('short_reason', '')}",
        ai_reason=ai_result.get("reason", ""),
    ))
    self._pending_concerns = concerns
    self._pending_trace = trace_steps
    return MatchResult(
        match_level="FAILED",
        match_tier=2,
        concerns=concerns,
        trace_steps=trace_steps,
        tier_short_reason=ai_result.get("short_reason") or "文件名无可识别影视信息",
        ai_reason=ai_result.get("reason", ""),
        selected_candidate=None,
    )
```

**修改文件 2**：`_tier2_high_certainty_impl` / `_tier2_medium_certainty_impl` 支持 `selected_candidate_id`：

```python
def _tier2_high_certainty_impl(
    self, corrected_title, corrected_year, media_type_hint,
    providers, ai_reason, ai_short_reason, concerns, trace_steps,
    selected_candidate_id=None,
    tier1_candidates=None,
):
    # 优先用 AI 指定的候选，不用重搜
    candidates = []
    if selected_candidate_id and tier1_candidates:
        candidates = [c for c in tier1_candidates if str(c.get("id")) == str(selected_candidate_id)]
    
    if not candidates:
        candidates = _search_providers_impl(
            self.title_matcher, corrected_title, corrected_year, providers
        )
    
    if candidates:
        selected = candidates[0]
        return MatchResult(
            match_level="CONTEXT_PASS",
            ...
            selected_candidate=SelectedCandidate(
                provider_type=selected.get("provider_type", ""),
                provider_id=str(selected.get("id", "")),
                title=selected.get("title", ""),
                year=selected.get("year"),
                media_type=selected.get("media_type", ""),
                why_selected=WhySelected.AI_SUGGESTION,
                score=selected.get("vote_average"),
            ),
        )
```

**修改文件 3**：`media_importer/features/import_flow/runner.py`

处理 `match_level="FAILED"`：

```python
if result.match_level == "FAILED":
    task.status = "FAILED"
    task.error_message = result.tier_short_reason or "AI 判定为非影视文件"
    task.ai_reason = result.ai_reason
    # 不进入入库流程
    return
```

**修改文件 4**：`media_importer/api/scrape_preview_job.py`

新增 FAILED 分支：

```python
if match_level == "FAILED":
    scrape_result = {
        "title_cn": clean_result.clean_title or "",
        "year": None,
        "media_type": "",
        "match_level": "FAILED",
        "match_tier": match_result.match_tier,
        "tier_short_reason": match_dict.get("tier_short_reason", ""),
        "ai_reason": match_dict.get("ai_reason", ""),
        "selected_candidate": None,
        "dimensions": {},
    }
    _preview_add_step(job, "scrape", "刮削结果", "done", "AI 判定非影视文件，任务失败")
    return scrape_result
```

**验证**：用 `123uyyt.mkv` 测试应得到 `match_level=FAILED`。

---

### 阶段 7：前端视图改造

#### Phase H：列表行 tier_short_reason

**修改文件**：`media_importer/webui/js/tasks-list.js`

**改动**：`buildScrapeCell()` 函数新增 L2 一句话原因显示：

```javascript
function buildScrapeCell(task) {
  // ... 已有逻辑 ...

  const scrapeResult = task.scrape_result || {};
  const shortReason = scrapeResult.tier_short_reason || "";
  if (shortReason && (task.status === "AWAIT_REVIEW" || task.status === "NEEDS_CONFIRM")) {
    html += `<div class="task-short-reason" style="
      font-size: 11px;
      color: var(--muted);
      margin-top: 2px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 200px;
    " title="${escapeHtml(shortReason)}">${escapeHtml(shortReason)}</div>`;
  }

  return html;
}
```

---

#### Phase I：任务卡片重写

**修改文件**：`media_importer/webui/js/cinema-task-list.js`

**改动**：完全重写 `renderTaskScrapeProcess`，实现 AI 怎么说 / 最终用了 / 维度三块：

```javascript
function renderTaskScrapeProcess(task) {
  const scrapeResult = task.scrape_result || {};
  const aiReason = scrapeResult.ai_reason || "";
  const selected = scrapeResult.selected_candidate || null;
  const dimSources = task.dim_sources || {};

  // L3: AI 怎么说
  let aiBlock = "";
  if (aiReason) {
    aiBlock = `
      <div class="task-ai-reason-block" style="margin-bottom: 10px;">
        <div style="font-size: 11px; color: var(--muted); margin-bottom: 4px;">🤖 AI 怎么说</div>
        <div style="font-size: 12px; line-height: 1.5; color: var(--ink);
                    padding: 8px; background: rgba(255,255,255,0.04);
                    border-left: 2px solid var(--gold, #eabf63);
                    border-radius: 4px;">${escapeHtml(aiReason)}</div>
      </div>`;
  }

  // L4: 最终用了
  let selectedBlock = "";
  if (selected && selected.title) {
    const whyMap = {
      unique_match: "唯一精确匹配",
      top_rated: `评分最高${selected.score ? '(' + selected.score + ')' : ''}`,
      ai_suggestion: "AI 建议",
      first_candidate: "Provider 排序第一",
      user_pick: "用户选择",
    };
    const whyText = whyMap[selected.why_selected] || selected.why_selected || "";
    selectedBlock = `
      <div class="task-selected-block" style="margin-bottom: 10px;">
        <div style="font-size: 11px; color: var(--muted); margin-bottom: 4px;">✅ 最终用了</div>
        <div style="font-size: 13px; color: var(--ink);">
          ${escapeHtml(selected.title)}
          ${selected.year ? '<span style="color: var(--muted)">(' + selected.year + ')</span>' : ''}
          ${whyText ? '<span style="font-size: 11px; color: var(--muted); margin-left: 6px;">· ' + escapeHtml(whyText) + '</span>' : ''}
        </div>
      </div>`;
  }

  const dimBlock = renderDimSourcesWithValues(task);
  return aiBlock + selectedBlock + dimBlock;
}

function renderDimSourcesWithValues(task) {
  const dims = task.scrape_dimensions || {};
  const dimSources = task.dim_sources || {};
  const dimDefs = (window._dimensionsData || []).concat(window.currentEnabledDimensions || []);

  if (Object.keys(dims).length === 0) {
    return '<div style="font-size: 11px; color: var(--muted);">暂无维度记录</div>';
  }

  const sourceLabels = {
    tmdb: "Provider", ai_assist: "AI辅助", ai_search: "AI搜索", file: "文件",
  };

  let html = '<div class="task-dim-grid" style="display: flex; flex-wrap: wrap; gap: 6px;">';
  for (const [name, value] of Object.entries(dims)) {
    const dimDef = dimDefs.find(d => d.name === name);
    const label = dimDef ? (dimDef.label || name) : name;
    let valLabel = String(value);
    if (dimDef && Array.isArray(dimDef.value_list)) {
      const matched = dimDef.value_list.find(v => String(v.value) === String(value));
      if (matched) valLabel = matched.label || valLabel;
    }
    const source = dimSources[name] || "";
    const sourceTag = source ? `<span style="font-size: 9px; padding: 1px 4px; border-radius: 3px; background: rgba(234,191,99,0.1); color: var(--gold, #eabf63); margin-left: 4px;">${sourceLabels[source] || source}</span>` : "";
    html += `<span style="font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,0.04); border-left: 2px solid ${dimDef?.color || 'rgba(234,191,99,0.3)'};">${escapeHtml(label)}：${escapeHtml(valLabel)}${sourceTag}</span>`;
  }
  html += '</div>';
  return html;
}
```

**删除**：当前 `renderTaskScrapeProcess` 中所有基于 `confirm_reason` 的渲染逻辑。

---

#### Phase J：任务详情复用装配器

**修改文件**：`media_importer/webui/js/cinema-task-detail.js`

**改动**：`buildScrapeTraceSection` 改用 `buildMatchPathData`：

```javascript
function buildScrapeTraceSection(task) {
  const data = buildMatchPathData(task);
  let timelineHtml = "";
  try {
    timelineHtml = renderMatchPathPreview(data);
  } catch (e) {
    console.error("buildMatchPathData render error:", e);
    timelineHtml = '<div class="cinema-modal-hint">刮削流程数据不完整。</div>';
  }

  return `
    <div class="cinema-modal-block">
      <h4>决策路径</h4>
      <div class="cinema-detail-trace-inline">${timelineHtml}</div>
    </div>`;
}
```

`taskToMatchPathData` 改为别名：

```javascript
function taskToMatchPathData(task) {
  return buildMatchPathData(task);
}
```

---

#### Phase K：追踪弹窗字段名修复

**修改文件**：`media_importer/webui/js/match-trace-detail.js`

**Bug 位置**：~L210-222

**当前代码**：

```javascript
escapeHtml(step.result || step.message || "-")
```

**改为**：

```javascript
escapeHtml(step.reason || step.ai_reason || step.result || step.message || "-")
```

---

#### Phase L：模拟器适配

**修改文件**：`media_importer/webui/js/cinema-config-simulator.js`

**改动 1**：`explainSimulatedQueue` 优先用 `tier_short_reason`：

```javascript
function explainSimulatedQueue(matchResult) {
  const tier = matchResult.match_tier || 0;
  const level = matchResult.match_level;
  const shortReason = matchResult.tier_short_reason || "";

  if (shortReason) {
    return shortReason;
  }

  if (level === "AUTO_PASS") return "标题精确匹配，自动通过。";
  if (level === "CONTEXT_PASS") return "AI 辅助匹配通过。";
  if (level === "NEEDS_CONFIRM") {
    const concerns = matchResult.concerns || [];
    if (concerns.length > 0) {
      return "需要人工确认：" + concerns.map(c => c.message).join("；") + "。";
    }
    return "需要人工确认匹配结果。";
  }
  if (level === "FAILED") return "AI 判定为非影视文件，任务失败。";
  return "匹配结果未知。";
}
```

**改动 2**：删除 `preview_selected_candidate` 逻辑，改读 `selected_candidate.why_selected`：

```javascript
const selected = scrapeRes.selected_candidate;
if (selected && selected.why_selected) {
  const whyMap = {
    unique_match: "唯一精确匹配",
    top_rated: "评分最高",
    ai_suggestion: "AI 建议",
    first_candidate: "Provider 排序第一",
    user_pick: "用户选择",
  };
  const whyText = whyMap[selected.why_selected] || selected.why_selected;
  html += `<div class="sim-warning">已加载第一候选（${escapeHtml(whyText)}），请检查后确认。</div>`;
}
```

---

#### Phase O：候选列表展示可信度

**修改文件**：`media_importer/webui/js/cinema-config-simulator.js` + `match-trace-detail.js`

**改动**：候选列表按 popularity 排序，显示 ⭐评分、票数、热度。

在 `cinema-config-simulator.js` 步骤 3（三级匹配）渲染候选列表：

```javascript
const candidates = matchResult.candidates || [];
if (candidates.length > 0) {
  html += '<div class="sim-candidates" style="margin-top: 8px;">';
  html += '<div style="font-size: 11px; color: var(--muted); margin-bottom: 4px;">候选列表（按可信度）</div>';
  
  const sorted = [...candidates].sort((a, b) => (b.popularity || 0) - (a.popularity || 0));
  
  sorted.forEach((c, idx) => {
    const stars = c.vote_average ? `⭐ ${c.vote_average.toFixed(1)}` : "";
    const votes = c.vote_count ? `(${c.vote_count}票` : "";
    const pop = c.popularity ? ` · 热度${Math.round(c.popularity)}` : "";
    const year = c.year ? `(${c.year})` : "";
    const origTitle = c.original_title && c.original_title !== c.title 
      ? ` / ${escapeHtml(c.original_title)}` : "";
    
    html += `<div style="font-size: 12px; padding: 4px 8px; margin: 2px 0;
                            background: rgba(255,255,255,0.04); border-radius: 4px;">
      ${idx === 0 ? '✅' : '○'} ${escapeHtml(c.title)} ${year}${origTitle}
      <span style="color: var(--muted); font-size: 11px;">${stars} ${votes}${pop}</span>
    </div>`;
  });
  html += '</div>';
}
```

---

### 阶段 8：失败任务 UX

#### Phase R：前端失败任务交互

**修改文件 1**：`media_importer/webui/js/cinema-task-list.js`

新增 `renderFailedTaskBlock`：

```javascript
function renderFailedTaskBlock(task) {
  if (task.status !== "FAILED") return "";
  const scrapeResult = task.scrape_result || {};
  const aiReason = scrapeResult.ai_reason || "";
  const shortReason = scrapeResult.tier_short_reason || "刮削失败";
  
  return `
    <div class="task-failed-block" style="
      padding: 10px;
      background: rgba(217, 79, 69, 0.08);
      border-left: 3px solid var(--red, #d94f45);
      border-radius: 4px;
      margin-bottom: 10px;
    ">
      <div style="font-size: 12px; color: var(--red, #d94f45); font-weight: 600; margin-bottom: 4px;">
        ❌ ${escapeHtml(shortReason)}
      </div>
      ${aiReason ? `
        <div style="font-size: 11px; color: var(--muted); margin-bottom: 8px; line-height: 1.5;">
          ${escapeHtml(aiReason)}
        </div>` : ''}
      <button class="btn btn-secondary btn-sm" onclick="rescrapeTask(${task.id})" style="font-size: 11px;">
        🔄 重新刮削
      </button>
    </div>`;
}
```

在 `renderTaskCard` 中调用（放在 scrapeProcess 之前）：

```javascript
function renderTaskCard(task) {
  // ... 已有逻辑 ...
  const failedBlock = renderFailedTaskBlock(task);
  // failedBlock 放在卡片顶部
}
```

**修改文件 2**：`media_importer/webui/js/cinema-task-utils.js`

新增 `rescrapeTask`：

```javascript
async function rescrapeTask(taskId) {
  const newFilename = prompt("可选：输入新文件名（留空则用原文件名重试）", "");
  if (newFilename === null) return;
  
  try {
    const body = newFilename ? { new_filename: newFilename } : {};
    const result = await requestApi("POST", `/tasks/${taskId}/rescrape`, body);
    if (result.code === 200) {
      alert("已加入刮削队列");
      location.reload();
    } else {
      alert("重新刮削失败: " + (result.message || "未知错误"));
    }
  } catch (e) {
    alert("请求失败: " + e.message);
  }
}
```

**修改文件 3**：`media_importer/api/task_handlers.py`

新增 `POST /api/tasks/{id}/rescrape` 端点：

```python
def rescrape_task(self, task_id):
    """重新刮削失败任务。可选 body: {"new_filename": "新文件名.mkv"}"""
    task = get_task(globals._global_task_manager.conn, task_id)
    if task.status != "FAILED":
        json_error(self, 400, message="只有失败任务可以重新刮削")
        return
    
    new_filename = self.body.get("new_filename") if hasattr(self, 'body') else None
    if new_filename:
        task.source_filename = new_filename
    
    task.status = "PENDING"
    task.error_message = ""
    update_task(globals._global_task_manager.conn, task)
    globals._global_task_manager.enqueue(task.id)
    json_response(self, 200, data={"task_id": task_id, "status": "PENDING"})
```

---

### 阶段 9：清理

#### Phase 5.1：confirm_reason 全清理

**搜索所有引用**：

```bash
grep -rn "confirm_reason" media_importer/ --include="*.py" --include="*.js"
```

逐个删除。后端 `MatchResult.confirm_reason` 字段定义保留（避免编译错误），但所有赋值点改为 `""`，`to_dict()` 不输出。

---

## 五、关键设计原则（不要偏离）

### 1. 前后端字段一致性

`scrape_preview_job.py` 和 `scrape.py` 必须输出**完全相同**的 `scrape_result` 字段结构。前端 `buildMatchPathData` 是唯一装配器，不要在各视图里自己拼。

### 2. 字段语义不要混淆

- `match_level`：`AUTO_PASS` / `CONTEXT_PASS` / `NEEDS_CONFIRM` / `FAILED`
- `match_tier`：1（Provider）/ 2（AI）/ 3（AI 不可用降级）
- `certainty`：`high` / `medium`（`low` 不应出现，兜底为 medium）
- `is_valid`：`true` / `false`（false 时其他字段全空）
- `why_selected`：`unique_match` / `top_rated` / `ai_suggestion` / `first_candidate` / `user_pick`

### 3. is_valid 判定严格

返回 false 的情况（宁可保守）：
1. 随机字符或乱码（123uyyt、asdfgh）
2. 纯通用名词对应影视过多（消防、大楼、飞机）
3. 明显非影视内容（新建文件夹、sample）

候选数量影响：≥3 部同名 → 倾向 false；唯一且高分 → 倾向 true。

---

## 六、测试用例

### 新建测试文件 1：`tests/test_match_result_fields.py`

（见 Phase B 中的完整代码）

### 新建测试文件 2：`tests/test_phase_pqr.py`

```python
import unittest
from unittest.mock import MagicMock, patch
from media_importer.features.scraping.match_models import MatchResult, SelectedCandidate
from media_importer.features.scraping.match_enums import TierShortReason, WhySelected


class TestPhaseP_IsValidParsing(unittest.TestCase):
    """Phase P: is_valid 字段解析"""
    
    def test_is_valid_false_clears_other_fields(self):
        """AI 返回 is_valid=false 时，其他字段被强制清空"""
        # 模拟 AI 返回 is_valid=false 但带了一堆其他字段
        # 验证解析后其他字段全空
        ...
    
    def test_is_valid_true_with_valid_certainty(self):
        """is_valid=true 时 certainty 必须是 high/medium"""
        ...
    
    def test_certainty_low_falls_back_to_medium(self):
        """is_valid=true 但 certainty=low 时，兜底为 medium"""
        ...
    
    def test_short_reason_truncation(self):
        """short_reason 超过 30 字会被截断"""
        ...


class TestPhaseQ_FailedState(unittest.TestCase):
    """Phase Q: FAILED 状态处理"""
    
    def test_is_valid_false_returns_failed_match_level(self):
        """is_valid=false 时 match_level=FAILED"""
        ...
    
    def test_failed_match_result_has_no_selected_candidate(self):
        """FAILED 状态下 selected_candidate=None"""
        ...
    
    def test_failed_match_result_has_invalid_filename_concern(self):
        """FAILED 状态下 concerns 含 INVALID_FILENAME"""
        ...
    
    def test_runner_handles_failed_match_level(self):
        """runner 遇到 FAILED 不进入入库流程"""
        ...


class TestPhaseP_SelectedCandidateId(unittest.TestCase):
    """Phase P: selected_candidate_id 字段"""
    
    def test_selected_candidate_id_skips_provider_search(self):
        """AI 指定 selected_candidate_id 时不重搜 Provider"""
        ...
    
    def test_selected_candidate_id_not_in_tier1_falls_back_to_search(self):
        """selected_candidate_id 在 Tier1 候选中找不到时，回退到搜索"""
        ...


if __name__ == "__main__":
    unittest.main()
```

**说明**：`...` 处需要你根据具体实现补全测试逻辑。参考现有 `tests/test_tier2_match_engine.py` 的测试风格。

---

## 七、验收场景（最终交付前必须全部通过）

### 后端场景测试

启动服务器（每次改完代码后）：

```bash
find /Users/wangwei/Documents/code/nas_media_manage -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /Users/wangwei/Documents/code/nas_media_manage -name "*.pyc" -delete 2>/dev/null
pkill -9 -f "python.*media_importer" 2>/dev/null
sleep 2
source /Users/wangwei/Documents/code/nas_media_manage/.venv/bin/activate
PYTHONPATH="/Users/wangwei/Documents/code/nas_media_manage" python -m media_importer.media_importer -c /Users/wangwei/Documents/code/nas_media_manage/config/config.yaml serve -p 9855 --host 0.0.0.0 > /tmp/nas_media_server.log 2>&1 &
sleep 5
```

测试各场景：

```bash
for f in "Dune.Part.Two.2024.1080p.mkv" "美丽人生.mkv" "速度与激情.mkv" "爱神.mkv" "123uyyt.mkv" "消防员.mkv" "Movie.2023.mkv"; do
  JOB=$(curl -s -X POST http://localhost:9855/api/scrape/preview/start -H 'Content-Type: application/json' -d "{\"filename\":\"$f\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['job_id'])")
  sleep 30
  echo "=== $f ==="
  curl -s "http://localhost:9855/api/scrape/preview/status/$JOB" | python3 -c "
import sys,json
d = json.load(sys.stdin)['data']['result']
sr = d['scrape_result']
print(f\"  match_level: {sr.get('match_level')}\")
print(f\"  tier_short: {sr.get('tier_short_reason','')}\")
print(f\"  ai_reason: {sr.get('ai_reason','')[:80]}\")
"
done
```

### 期望结果

| 文件名 | match_level | tier_short_reason 含 |
|--------|-------------|----------------------|
| `Dune.Part.Two.2024.1080p.mkv` | AUTO_PASS 或 CONTEXT_PASS | "唯一精确匹配" 或 "Dune 2" |
| `美丽人生.mkv` | NEEDS_CONFIRM | "同名多版" |
| `速度与激情.mkv` | CONTEXT_PASS | "AI 高确定性" |
| `爱神.mkv` | NEEDS_CONFIRM | "AI 建议候选" |
| `123uyyt.mkv` | **FAILED** | "无可识别影视信息" |
| `消防员.mkv` | **FAILED** 或 NEEDS_CONFIRM | 取决于 Provider 返回候选数 |
| `Movie.2023.mkv` | **FAILED** | "占位词" |

### 前端验证

1. **任务列表行**：NEEDS_CONFIRM 任务显示一句话原因
2. **任务卡片**：显示"🤖 AI 怎么说"+"✅ 最终用了"+"🏷️ 维度"三块
3. **任务详情**：6 步时间轴完整渲染，每步都有内容（不是"-"）
4. **失败任务卡片**：显示 ❌ + ai_reason + 🔄 重新刮削按钮
5. **点击重新刮削**：任务状态变为 PENDING

---

## 八、遇到问题时

### 1. 改了代码但行为没变
**原因**：Python `.pyc` 缓存未清  
**解决**：执行"Python 缓存陷阱"中的清缓存+重启命令

### 2. 测试失败
**第一步**：读测试断言，判断是测试过时还是代码 bug  
**第二步**：如果是测试过时（如断言 `confirm_reason` 字段），更新测试  
**第三步**：如果是代码 bug，修复后重跑

### 3. 计划有歧义
**不要自己拍板**。停下来问用户，引用本提示词的具体章节请求澄清。

### 4. LSP 错误
本项目有既有 LSP 错误（如 `scenario: str` 接收 None、mixin 类属性未声明、`sync_playwright` 可能未绑定）。这些是已有的，不要修。只关注**你新增代码**的 LSP 错误。

---

## 九、完成交付物清单

完成后，仓库应包含：

### 新建文件
- [ ] `media_importer/features/scraping/match_enums.py`
- [ ] `media_importer/webui/js/build-match-path-data.js`
- [ ] `tests/test_match_result_fields.py`
- [ ] `tests/test_phase_pqr.py`

### 修改文件（按 Phase 顺序）
- [ ] `media_importer/features/scraping/match_models.py`（Phase B）
- [ ] `media_importer/features/scraping/_match_tiers_impl.py`（Phase C/M/N/P/Q）
- [ ] `media_importer/features/scraping/match_engine.py`（Phase M）
- [ ] `media_importer/scraper/_llm_match_assist.py`（Phase D/P）
- [ ] `media_importer/features/import_flow/steps/scrape.py`（Phase E）
- [ ] `media_importer/features/import_flow/steps/review.py`（Phase E）
- [ ] `media_importer/features/import_flow/runner.py`（Phase E/Q）
- [ ] `media_importer/api/scrape_preview_job.py`（Phase F/Q）
- [ ] `media_importer/api/task_handlers.py`（Phase R）
- [ ] `media_importer/webui/index.html`（Phase G）
- [ ] `media_importer/webui/js/tasks-list.js`（Phase H）
- [ ] `media_importer/webui/js/cinema-task-list.js`（Phase I/R）
- [ ] `media_importer/webui/js/cinema-task-detail.js`（Phase J）
- [ ] `media_importer/webui/js/match-trace-detail.js`（Phase K/O）
- [ ] `media_importer/webui/js/cinema-config-simulator.js`（Phase L/O）
- [ ] `media_importer/webui/js/cinema-task-utils.js`（Phase R）

### Git 提交
- [ ] 每个 Phase 一个提交，提交信息 `Phase X: 简述`

---

## 十、最终交付确认

全部 Phase 完成后：

1. 跑完整测试套件：`python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"`
2. 跑架构守卫：`python -m pytest tests/test_architecture_guards.py -q`
3. 跑编译检查：`PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests`
4. 执行"验收场景"中的 7 个文件名测试
5. 向用户报告完成状态

**不要自行决定"完成"。必须所有验收场景通过后才能宣告完成。**

---

**开始执行。从 Phase A 开始。**

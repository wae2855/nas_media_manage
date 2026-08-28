# 刮削信息职责拆分计划

**日期**：2026-06-16  
**类型**：架构重构 + 数据契约修复  
**前置条件**：测试环境数据可全部清空，无需迁移  
**目标**：把"万能胶"`confirm_reason` 拆成 6 类职责字段，每层视图读自己该读的字段。

---

## 一、目标与背景

### 当前问题
所有刮削描述最终汇入一个 `confirm_reason` 字符串，用 `；` 拼接 4 类不同性质的信息（匹配层级原因、Provider 搜索情况、系统结论、AI 原始推理）。导致：
- 列表行拿到 4 句话拼接，无法用作"一句话原因"
- 详情页想分步展示，数据已糊在一起拆不开
- `trace_steps[].reason` 和 `ai_reason` 字段存了但前端从不读
- 5 套视图（列表/卡片/详情/追踪弹窗/模拟器）各显示不同字段子集

### 目标职责模型（6 层）

| Layer | 字段 | 定位 | 展示位置 |
|-------|------|------|---------|
| L1 | `match_level` / `match_tier` | 匹配状态 | 所有视图的状态标签 |
| L2 | `tier_short_reason`（新增） | 一句话原因（≤30字） | 列表行副标题、卡片摘要 |
| L3 | `ai_reason`（独立存储） | AI 原始推理 | 卡片"AI 怎么说"区块、详情 Tier 2 步骤 |
| L4 | `selected_candidate`（新增结构化） | 最终选择+原因 | 卡片"最终用了"、详情刮削结果 |
| L5 | `concerns[]`（已有，独立存储） | 关注点列表 | 详情"注意事项"、深度追踪 |
| L6 | `trace_steps[].{reason, ai_reason}` | 过程追踪 | 详情时间轴、深度追踪弹窗 |

---

## 二、数据模型定义

### 2.1 新增枚举（新建 `media_importer/features/scraping/match_enums.py`）

```python
"""刮削匹配相关的枚举定义"""

# L2: 一句话原因枚举（程序兜底，AI 应优先返回 ≤30 字）
class TierShortReason:
    # Tier 1
    TIER1_UNIQUE = "唯一精确匹配"
    TIER1_TOP_RATED = "同名{count}部，自动选评分最高"  # 含 {count} 占位
    TIER1_MULTI = "{count}部同名作品，需确认"
    TIER1_FUZZY = "标题不完全匹配"
    TIER1_NO_RESULT = "Provider 无结果"
    # Tier 2
    TIER2_HIGH_PASS = "AI 高确定性匹配通过"
    TIER2_MEDIUM = "AI 建议候选，需确认"
    TIER2_LOW = "AI 低确定性，需确认"
    TIER2_AI_FAILED = "AI 不可用，降级到候选列表"
    # Tier 3
    TIER3_FALLBACK = "AI 不可用，候选列表供选择"
    # 兜底
    UNKNOWN = "匹配结果未知"


# L4: 最终候选选择原因枚举
class WhySelected:
    UNIQUE_MATCH = "unique_match"           # 唯一精确匹配
    TOP_RATED = "top_rated"                 # 评分打破平局
    AI_SUGGESTION = "ai_suggestion"         # AI 建议（含年份纠正等）
    FIRST_CANDIDATE = "first_candidate"     # Provider 排序第一（AI 不可用降级）
    USER_PICK = "user_pick"                 # 用户人工选择（review 后写入）


# L1: match_tier 枚举（已有，明确语义）
class MatchTier:
    TIER1 = 1  # Provider 精确匹配
    TIER2 = 2  # AI 辅助匹配
    TIER3 = 3  # 用户确认降级
```

### 2.2 新增 dataclass 字段（修改 `media_importer/features/scraping/match_models.py`）

```python
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
    # 已有字段保留
    match_level: str
    match_tier: int = 0
    provider_id: Optional[str] = None
    provider_title: str = ""
    concerns: List[MatchConcern] = field(default_factory=list)
    trace_steps: List[MatchTraceStep] = field(default_factory=list)
    candidates: List[dict] = field(default_factory=list)
    confirm_reason: str = ""  # ← 废弃，保留字段以便编译，但不再写入新值
    
    # 新增字段
    tier_short_reason: str = ""           # L2: 一句话原因（≤30字）
    ai_reason: str = ""                   # L3: AI 原始推理（独立存储）
    selected_candidate: Optional[SelectedCandidate] = None  # L4: 最终选择

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

---

## 三、后端实施

### 3.1 Phase A：修改 Tier 1（`_match_tiers_impl.py`）

**目标**：每个返回点设置 `tier_short_reason` 和 `selected_candidate`。

| 函数 | 行号 | match_level | tier_short_reason | selected_candidate.why_selected |
|------|------|-------------|-------------------|--------------------------------|
| `_tier1_exact_match_impl` 单匹配成功 | ~L80 | AUTO_PASS | `TierShortReason.TIER1_UNIQUE` | `UNIQUE_MATCH` |
| `_tier1_exact_match_impl` 评分打破平局 | ~L127（新增代码） | AUTO_PASS | `TierShortReason.TIER1_TOP_RATED.format(count=N)` | `TOP_RATED` |
| `_tier1_exact_match_impl` 多匹配无打破 | ~L143 | None（fallthrough） | 不设置（Tier 2 接管） | 不设置 |
| `_tier1_exact_match_impl` 模糊无匹配 | ~L157 | None | 不设置 | 不设置 |
| `_tier1_exact_match_impl` 全无结果 | ~L171 | None | 不设置 | 不设置 |

**示例改动（单匹配成功分支，~L80）**：

```python
return MatchResult(
    match_level="AUTO_PASS",
    provider_id=item.item_id,
    provider_title=item.title,
    match_tier=1,
    trace_steps=trace_steps,
    candidates=[{...}],
    confirm_reason="",  # ← 不再设置
    tier_short_reason=TierShortReason.TIER1_UNIQUE,  # ← 新增
    selected_candidate=SelectedCandidate(
        provider_type=item.provider_type,
        provider_id=item.item_id,
        title=item.title,
        year=item.year,
        media_type=item.media_type,
        why_selected=WhySelected.UNIQUE_MATCH,
        score=item.vote_average,
    ),  # ← 新增
)
```

**示例改动（评分打破平局分支，~L127）**：

```python
return MatchResult(
    match_level="AUTO_PASS",
    provider_id=top_item.item_id,
    provider_title=top_item.title,
    match_tier=1,
    trace_steps=trace_steps,
    candidates=[{...}],
    confirm_reason="",  # ← 不再设置
    tier_short_reason=TierShortReason.TIER1_TOP_RATED.format(count=len(exact_matches)),  # ← 新增
    selected_candidate=SelectedCandidate(
        provider_type=top_item.provider_type,
        provider_id=top_item.item_id,
        title=top_item.title,
        year=top_item.year,
        media_type=top_item.media_type,
        why_selected=WhySelected.TOP_RATED,
        score=top_score,
    ),  # ← 新增
)
```

### 3.2 Phase B：修改 Tier 2（`_match_tiers_impl.py`）

| 函数 | match_level | tier_short_reason | ai_reason 来源 | selected_candidate.why_selected |
|------|-------------|-------------------|---------------|--------------------------------|
| `_tier2_high_certainty_impl` 成功 | CONTEXT_PASS | `TIER2_HIGH_PASS` | `ai_reason` 参数 | `AI_SUGGESTION` |
| `_tier2_high_certainty_impl` 降级 medium | NEEDS_CONFIRM | `TIER2_MEDIUM`（继承） | `ai_reason` 参数 | 不设置（继承下游） |
| `_tier2_medium_certainty_impl` | NEEDS_CONFIRM | `TIER2_MEDIUM` | `ai_reason` 参数 | `AI_SUGGESTION`（若候选非空） |
| `_tier2_low_certainty_impl`（已改为调 medium） | NEEDS_CONFIRM | `TIER2_LOW` | `ai_reason` 参数 | `AI_SUGGESTION`（若候选非空） |
| `_tier2_context_match_impl` AI 异常 | None（fallthrough） | 不设置 | 不设置 | 不设置 |

**示例改动（`_tier2_high_certainty_impl` 成功分支，~L208）**：

```python
return MatchResult(
    match_level="CONTEXT_PASS",
    provider_id=selected.get("id"),
    provider_title=selected.get("title", ""),
    match_tier=2,
    concerns=concerns,
    trace_steps=trace_steps,
    candidates=candidates[:5],
    confirm_reason="",  # ← 不再设置
    tier_short_reason=TierShortReason.TIER2_HIGH_PASS,  # ← 新增
    ai_reason=ai_reason,  # ← 新增（独立存储）
    selected_candidate=SelectedCandidate(
        provider_type=selected.get("provider_type", ""),
        provider_id=str(selected.get("id", "")),
        title=selected.get("title", ""),
        year=selected.get("year"),
        media_type=selected.get("media_type", ""),
        why_selected=WhySelected.AI_SUGGESTION,
    ),  # ← 新增
)
```

**`_tier2_medium_certainty_impl` 类似改动**：
- `tier_short_reason=TierShortReason.TIER2_MEDIUM`
- `ai_reason=ai_reason`
- `selected_candidate`：若 `candidates` 非空，设置 `why_selected=WhySelected.AI_SUGGESTION`，`title=candidates[0]["title"]` 等

**`_tier2_context_match_impl` 顶层改动（~L360-381）**：

把 `ai_reason` 从 `ai_result` 取出后，传递给所有子函数（high/medium/low），保证子函数能独立存储。

### 3.3 Phase C：修改 Tier 3（`_match_tiers_impl.py`）

**`_tier3_user_confirm_impl`（~L467）**：

```python
return MatchResult(
    match_level="NEEDS_CONFIRM",
    match_tier=3,
    concerns=concerns,
    trace_steps=trace_steps,
    candidates=candidates[:5],
    confirm_reason="",  # ← 不再设置
    tier_short_reason=TierShortReason.TIER3_FALLBACK,  # ← 新增
    selected_candidate=SelectedCandidate(
        provider_type=candidates[0].get("provider_type", "") if candidates else "",
        provider_id=str(candidates[0].get("id", "")) if candidates else "",
        title=candidates[0].get("title", "") if candidates else "",
        year=candidates[0].get("year"),
        media_type=candidates[0].get("media_type", ""),
        why_selected=WhySelected.FIRST_CANDIDATE,
    ) if candidates else None,  # ← 新增
)
```

### 3.4 Phase D：修改 AI 提示词（`_llm_match_assist.py`）

**目标**：让 AI 在 JSON 中直接返回 ≤30 字的 `tier_short_reason`（当 AI 有判断时）。

**修改 `_tier2_correct_impl` 的 user_content（~L60）**：

```python
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
    "## 输出要求",
    "返回 JSON，不要包含任何其他文字：",
    '{'
    '"corrected_title": "纠正后的标题", '
    '"corrected_year": 年份或null, '
    '"media_type_hint": "movie|tv|null", '
    '"certainty": "high|medium|low", '
    '"reason": "详细判断理由（200字内）", '
    '"short_reason": "≤30字的一句话总结，供列表显示用，必须简洁", '
    '"suggestion": "建议的搜索关键词"'
    '}',
    "",
    "## short_reason 示例",
    '- "1997年意大利电影《美丽人生》"',
    '- "王家卫2004年合集电影《爱神》"',
    '- "标题通用，无法确定具体版本"',
]
```

**修改结果解析（~L107）**：

```python
result.setdefault("short_reason", "")
# ... 已有逻辑 ...

# 程序兜底：若 AI 未返回 short_reason 或超长，截断
if not result.get("short_reason"):
    # 从 reason 截前 30 字
    full_reason = result.get("reason", "")
    result["short_reason"] = full_reason[:30] + ("..." if len(full_reason) > 30 else "")
elif len(result["short_reason"]) > 33:  # 30 + "..."
    result["short_reason"] = result["short_reason"][:30] + "..."
```

**在 `_tier2_context_match_impl` 中传递 short_reason**：

```python
ai_short_reason = ai_result.get("short_reason", "")
# ... 调用子函数时多传一个参数 ...
return _tier2_high_certainty_impl(
    self, corrected_title, corrected_year, media_type_hint,
    providers, ai_reason, ai_short_reason, concerns, trace_steps,
)
```

子函数中：

```python
# 若 AI 返回了 short_reason，优先用；否则用枚举兜底
tier_short = ai_short_reason or TierShortReason.TIER2_HIGH_PASS
return MatchResult(
    ...,
    tier_short_reason=tier_short,
    ...
)
```

### 3.5 Phase E：修改正式入库流程

**文件：`media_importer/features/import_flow/steps/scrape.py`**

- **删除** ~L313 追加 `confirm_reason` 的逻辑（`{source_label}识别的「...」已配置为不信任`）
- 改为：往 `concerns[]` 追加一条 `MatchConcern(code="DIM_TRUST_DOWNGRADE", message=f"{dim_name} 来源不被信任，需人工确认")`

**文件：`media_importer/features/import_flow/steps/review.py`**

- **删除** 所有覆盖 `confirm_reason` 的逻辑（L38/L60/L62/L66/L71）
- 改为：往 `concerns[]` 追加结构化 concern，不碰 `confirm_reason`
- 若用户在 review 中手动选择了候选，写入 `selected_candidate.why_selected = WhySelected.USER_PICK`

**文件：`media_importer/features/import_flow/runner.py`**

- **删除** L169 默认 `confirm_reason = "刮削信息不足"` 的兜底
- 改为：`tier_short_reason = TierShortReason.UNKNOWN`

### 3.6 Phase F：修改 scrape_preview_job.py

**目标**：把新字段透传到前端。

**所有构造 `scrape_result` 的位置（共 7 处）**：

```python
scrape_result = {
    "title_cn": ...,
    "year": ...,
    # ... 已有字段 ...
    "match_level": match_level,
    "match_tier": match_result.match_tier,  # ← 已有，确保所有分支都有
    # 新字段
    "tier_short_reason": match_dict.get("tier_short_reason", ""),
    "ai_reason": match_dict.get("ai_reason", ""),
    "selected_candidate": match_dict.get("selected_candidate"),
    # confirm_reason 字段删除
}
```

**删除**：`_confirm_reason_from_match` 函数（~L39-56）及其所有调用点。

---

## 四、前端实施

### 4.1 Phase G：新建统一数据装配器

**新建文件：`media_importer/webui/js/build-match-path-data.js`**

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
      dimensions: scrapeDimensions,  // ← 关键：把 scrape_dimensions 映射到 dimensions
    },
    import_path: {
      import_path: task.import_path || task.import_dir || "",
      used_fallback: task.used_fallback || false,
      matched_rule: task.matched_rule || null,
    },
  };
}
```

**在 `index.html` 中引入**（在 `cinema-config-simulator.js` 之前）：

```html
<script src="js/build-match-path-data.js?v=1"></script>
```

### 4.2 Phase H：任务列表行改造（`tasks-list.js`）

**目标**：`NEEDS_CONFIRM` 任务显示一句话原因。

**修改 `buildScrapeCell()` 函数**，在 match_level 标签后追加：

```javascript
function buildScrapeCell(task) {
  // ... 已有逻辑 ...

  // 新增：L2 一句话原因
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

### 4.3 Phase I：任务卡片改造（`cinema-task-list.js`）

**目标**：卡片新增"AI 怎么说"和"最终用了"两个区块。

**修改 `renderTaskCard()` 函数**，在现有 `<details>` 区块内重写 `renderTaskScrapeProcess`：

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

  // 维度（已有逻辑保留，补值显示）
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

### 4.4 Phase J：任务详情改造

**目标**：复用 `renderMatchPathPreview`，数据来自 `buildMatchPathData`。

**修改 `cinema-task-detail.js` 的 `buildScrapeTraceSection()`（~L160）**：

```javascript
function buildScrapeTraceSection(task) {
  const data = buildMatchPathData(task);  // ← 使用统一装配器
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

**修改 `taskToMatchPathData()`（~L186）**：直接删除函数体，改为 `return buildMatchPathData(window._currentTask);`（或保留函数名作为别名，内部调用 `buildMatchPathData`）。

### 4.5 Phase K：匹配追踪弹窗字段名修复（`match-trace-detail.js`）

**Bug 位置**：~L210-222

**当前代码**：
```javascript
escapeHtml(step.result || step.message || "-")
```

**改为**：
```javascript
escapeHtml(step.reason || step.ai_reason || step.result || step.message || "-")
```

这样后端 `trace_steps[].reason` 和 `ai_reason` 字段就能正确显示。

### 4.6 Phase L：模拟器适配（`cinema-config-simulator.js`）

**修改 `renderMatchPathPreview()`**：

- 步骤 4（刮削结果）：删除 `preview_selected_candidate` 警告逻辑，改为读取 `selected_candidate.why_selected` 显示对应标签
- 步骤 6（最终入库）：`explainSimulatedQueue()` 优先用 `tier_short_reason`，不再从 `confirm_reason` 反推

**修改 `explainSimulatedQueue()`**：

```javascript
function explainSimulatedQueue(matchResult) {
  const tier = matchResult.match_tier || 0;
  const level = matchResult.match_level;
  const shortReason = matchResult.tier_short_reason || "";

  // 优先用 tier_short_reason
  if (shortReason) {
    return shortReason;
  }

  // 兜底：按 match_level 显示固定文案
  if (level === "AUTO_PASS") return "标题精确匹配，自动通过。";
  if (level === "CONTEXT_PASS") return "AI 辅助匹配通过。";
  if (level === "NEEDS_CONFIRM") {
    const concerns = matchResult.concerns || [];
    if (concerns.length > 0) {
      return "需要人工确认：" + concerns.map(c => c.message).join("；") + "。";
    }
    return "需要人工确认匹配结果。";
  }
  return "匹配结果未知。";
}
```

**删除**：所有 `preview_selected_candidate` 相关的"已按 AI 辅助建议..."分支（~L178-184），改为：

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

## 五、清理与废弃

### 5.1 废弃 `confirm_reason`

**搜索所有引用**：

```bash
grep -rn "confirm_reason" media_importer/ --include="*.py" --include="*.js"
```

**后端**：
- 删除 `_match_tiers_impl.py` 所有 `confirm_reason=...` 参数
- 删除 `scrape_preview_job.py` 的 `_confirm_reason_from_match` 函数
- 删除 `review.py` 所有 `confirm_reason` 赋值
- 删除 `runner.py` 的默认 `confirm_reason` 兜底

**前端**：
- 删除 `cinema-task-list.js` 读取 `confirm_reason` 的代码
- 删除 `cinema-task-utils.js` 组装 `confirm_reason` 的 `taskDescription` 逻辑
- 删除 `cinema-config-simulator.js` 的 `confirm_reason` 显示

**保留 MatchResult.confirm_reason 字段定义**（避免编译错误），但所有赋值点改为空字符串 `""`。

### 5.2 合并详情模态框（可选，建议本计划外执行）

遗留版 `tasks-detail.js` 与 Cinema 版 `cinema-task-detail-open.js` 并存。建议本计划完成后，另开任务删除遗留版（前提：Cinema 版已迁移所有缺失字段，如文件大小、分辨率、去重等）。

---

## 六、验证清单

### 6.1 后端单测（新增）

**新建 `tests/test_match_result_fields.py`**：

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
        self.assertNotIn("confirm_reason", d)  # 废弃

    def test_confirm_reason_not_in_output(self):
        r = MatchResult(match_level="NEEDS_CONFIRM")
        d = r.to_dict()
        self.assertNotIn("confirm_reason", d)
```

### 6.2 集成测试

**新建 `tests/test_scrape_info_split.py`**：

- 用 "美丽人生.mkv" 跑刮削，验证返回的 `match_result` 包含所有 6 层字段
- 用 "爱神.mkv" 跑刮削，验证 `ai_reason` 和 `tier_short_reason` 都有内容
- 验证 `selected_candidate.why_selected` 是合法枚举值

### 6.3 前端手动验证（Playwright）

**清单**：

1. **任务列表行**：`NEEDS_CONFIRM` 任务下方显示 ≤30 字的 `tier_short_reason`
2. **任务卡片**：
   - 显示"🤖 AI 怎么说"区块，内容是 `ai_reason`
   - 显示"✅ 最终用了"区块，含 `title + year + why_selected 中文`
   - 维度标签显示 `label：value [来源]`
3. **任务详情**：
   - 时间轴 6 步全部渲染（不是"-"）
   - Tier 1 步骤显示 `trace_steps[0].reason`
   - Tier 2 步骤显示 `reason` + `ai_reason`
4. **匹配追踪弹窗**：步骤显示真实文本，不是"-"
5. **模拟器**：
   - 步骤 4 警告显示"已加载第一候选（AI 建议）"
   - 步骤 6 摘要显示 `tier_short_reason`

---

## 七、实施顺序与依赖

```
Phase A/B/C（后端 Tier 1/2/3 字段生成）
    ↓ 依赖
Phase D（AI 提示词改造，产出 short_reason）
    ↓
Phase E（正式流程 scrape.py/review.py/runner.py 清理）
    ↓
Phase F（scrape_preview_job.py 透传）
    ↓ 依赖
Phase G（前端 buildMatchPathData 装配器）  ← 前端基础
    ↓ 依赖
Phase H（列表行）/ Phase I（卡片）/ Phase J（详情）/ Phase L（模拟器）
    ↓ 并行可做
Phase K（追踪弹窗字段名修复）  ← 独立 bug fix，可并行
    ↓
Phase 5.1（confirm_reason 清理）  ← 最后做
```

**预估工作量**：
- Phase A-F（后端）：约 4 小时
- Phase G-L（前端）：约 6 小时
- 清理与测试：约 2 小时
- **合计：约 12 小时**

---

## 八、风险与注意事项

1. **AI 不返回 `short_reason`**：兜底逻辑从 `reason` 截前 30 字。若 AI 也不返回 `reason`，使用枚举默认值。
2. **DB 中老数据**：用户已确认测试环境可清空，无需迁移。新数据写入新字段，老数据的 `confirm_reason` 仍可在 DB 中存在但前端不再读取。
3. **`MatchResult.confirm_reason` 字段保留**：避免编译错误，但 `to_dict()` 不再输出此字段。
4. **遗留详情模态框 `tasks-detail.js`**：本计划不删除，但 Cinema 版完善后应另开任务清理。
5. **模拟器与正式任务数据一致性**：`scrape_preview_job.py` 与 `scrape.py` 必须输出相同的字段结构，否则前端两套逻辑分叉。

---

## 九、验收标准

完成后，用以下场景验证：

| 场景 | 文件名 | 期望 tier_short_reason | 期望 selected_candidate.why_selected |
|------|--------|------------------------|--------------------------------------|
| Tier 1 唯一匹配 | "Dune.Part.Two.2024.1080p.mkv" | "唯一精确匹配" | unique_match |
| Tier 1 评分打破 | "美丽人生.mkv"（7部同名） | "同名7部，自动选评分最高" | top_rated |
| Tier 2 AI 高 | "速度与激情.mkv" | "AI 高确定性匹配通过" 或 AI 返回的 short_reason | ai_suggestion |
| Tier 2 AI 中 | "爱神.mkv" | "AI 建议候选，需确认" 或 AI 返回的 short_reason | ai_suggestion |
| Tier 3 降级 | AI 不可用时任意文件 | "AI 不可用，候选列表供选择" | first_candidate |

每个场景下，验证：
- [ ] 列表行显示 tier_short_reason
- [ ] 卡片显示 ai_reason 和 selected_candidate
- [ ] 详情时间轴每步都有内容（不是"-"）
- [ ] 不存在任何 `confirm_reason` 字符串拼接

---

## 十、扩展：Phase P / Q / R（用户方案合并）

本节为用户决策后追加的扩展，涉及 **AI 提示词重设计** + **业务语义变更** + **失败任务 UX**。

### 10.1 Phase P：AI 提示词重设计（扩展原 Phase D）

**目标**：
1. AI 收到 Step 1 Provider 候选列表（前 5 个含评分/热度）
2. AI 返回 `is_valid` 字段区分"非影视文件"和"猜不出"
3. AI 可直接 `selected_candidate_id` 指定候选，避免 Provider 重搜

#### 10.1.1 数据契约扩展

**`_tier2_correct_impl` 返回值新增字段**：

```python
{
  "is_valid": True/False,           # 新增：文件名是否含可识别影视信息
  "certainty": "high|medium|",      # 仅 is_valid=True 时有意义，low 不应出现
  "corrected_title": "...",
  "corrected_year": 2024 or None,
  "media_type_hint": "movie|tv|null",
  "selected_candidate_id": "xxx",   # 新增：从 Step 1 候选中选定的 provider_id
  "reason": "...",                  # 详细理由
  "short_reason": "≤30字",          # 一句话总结
  "suggestion": "..."               # 保留但弱化（仅 corrected_title 为空时辅助）
}
```

#### 10.1.2 `is_valid` 判定规则（必须严格执行）

返回 `is_valid=False` 的情况：

1. **随机字符/乱码**：`123uyyt`、`asdfgh`、`855`、`yyu`
2. **纯通用名词，对应影视过多**：
   - 单字词：`消防`、`大楼`、`飞机`、`爱情`、`战争`
   - 通用短语：`我的女神`、`那些日子`（这些短语对应几十部作品）
3. **明显非影视内容**：`新建文件夹`、`未命名`、`sample`、`test`

返回 `is_valid=True` 的情况：
- 具体片名（中文译名或原文）
- 含影视特征任一：年份、季集编号（S01E01）、画质标签（1080p）、人名

**候选数量影响判定**（重要边界）：
- 同名候选 ≥ 3 部 → 倾向 `is_valid=False`（歧义太大）
- 同名候选唯一且高分 → 倾向 `is_valid=True` + `certainty=high`

#### 10.1.3 完整 user_content 模板

修改 `_llm_match_assist.py` 中 `_tier2_correct_impl` 的 `user_parts`：

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
    "- 若 Step 1 候选中已有完美匹配项：填 selected_candidate_id（候选的 provider_id），程序直接采用，无需重新搜索",
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

#### 10.1.4 解析逻辑扩展

在 `_tier2_correct_impl` 的 JSON 解析后追加：

```python
result.setdefault("is_valid", True)  # 兜底：AI 未返回时默认 True（向后兼容）
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
        result["certainty"] = "medium"  # 兜底为 medium

# short_reason 长度兜底
if result.get("short_reason") and len(result["short_reason"]) > 33:
    result["short_reason"] = result["short_reason"][:30] + "..."
elif not result.get("short_reason") and result.get("reason"):
    full = result["reason"]
    result["short_reason"] = full[:30] + ("..." if len(full) > 30 else "")
```

#### 10.1.5 Step 1 候选传递

修改 `_tier2_context_match_impl`，在调用 LLM 前把 Tier 1 候选塞入 `path_context`：

```python
context["provider_candidates"] = self._pending_candidates  # 来自 Phase M
```

### 10.2 Phase Q：业务语义变更（FAILED 状态）

**目标**：`is_valid=false` → 任务失败，不搜 Provider，不进入入库流程。

#### 10.2.1 新增 match_level 枚举值

`MatchResult.match_level` 新增合法值 `"FAILED"`，表示任务因文件名不可识别而失败。

#### 10.2.2 `_tier2_context_match_impl` 改造

在解析 AI 结果后，新增分支：

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

#### 10.2.3 `_tier2_high_certainty_impl` / `_tier2_medium_certainty_impl` 改造：支持 selected_candidate_id

```python
def _tier2_high_certainty_impl(
    self, corrected_title, corrected_year, media_type_hint,
    providers, ai_reason, ai_short_reason, concerns, trace_steps,
    selected_candidate_id=None,  # 新参数
    tier1_candidates=None,
):
    # 优先用 AI 指定的候选，不用重搜
    candidates = []
    if selected_candidate_id and tier1_candidates:
        candidates = [c for c in tier1_candidates if str(c.get("id")) == str(selected_candidate_id)]
    
    if not candidates:
        # 重搜 Provider
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
    # ... 降级逻辑 ...
```

#### 10.2.4 任务状态机改造

**`media_importer/features/import_flow/runner.py`**：处理 `match_level="FAILED"`：

```python
if result.match_level == "FAILED":
    task.status = "FAILED"
    task.error_message = result.tier_short_reason or "AI 判定为非影视文件"
    task.ai_reason = result.ai_reason
    # 不进入入库流程，不创建移动任务
    return
```

**`media_importer/core/db/constants.py`**：确认 `VALID_STATUSES` 已包含 `"FAILED"`（已有，无需改动）。

#### 10.2.5 scrape_preview_job.py 改造

新增 `match_level == "FAILED"` 分支：

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
    # 跳过维度推导和入库路径预估（已失败）
    _preview_add_step(job, "scrape", "刮削结果", "done", "AI 判定非影视文件，任务失败")
    return scrape_result  # 提前返回
```

### 10.3 Phase R：前端失败任务 UX

**目标**：失败任务清晰展示原因，提供"重新刮削"入口。

#### 10.3.1 任务卡片失败状态展示（`cinema-task-list.js`）

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

在 `renderTaskCard` 中调用：

```javascript
function renderTaskCard(task) {
  // ... 已有逻辑 ...
  const failedBlock = renderFailedTaskBlock(task);
  // failedBlock 放在卡片顶部，scrapeProcess 之前
}
```

#### 10.3.2 重新刮削 API（后端）

新增 `POST /api/tasks/{id}/rescrape`：

```python
# media_importer/api/task_handlers.py
def rescrape_task(self, task_id):
    """重新刮削失败任务。可选 body: {"new_filename": "新文件名.mkv"}"""
    task = get_task(globals._global_task_manager.conn, task_id)
    if task.status != "FAILED":
        json_error(self, 400, message="只有失败任务可以重新刮削")
        return
    
    new_filename = self.body.get("new_filename") if hasattr(self, 'body') else None
    if new_filename:
        # 改名后重搜
        task.source_filename = new_filename
    
    task.status = "PENDING"
    task.error_message = ""
    update_task(globals._global_task_manager.conn, task)
    # 触发任务管理器重新处理
    globals._global_task_manager.enqueue(task.id)
    json_response(self, 200, data={"task_id": task_id, "status": "PENDING"})
```

#### 10.3.3 前端重新刮削交互（`cinema-task-utils.js`）

```javascript
async function rescrapeTask(taskId) {
  const newFilename = prompt("可选：输入新文件名（留空则用原文件名重试）", "");
  if (newFilename === null) return;  // 用户取消
  
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

### 10.4 Phase P/Q/R 测试用例

#### 10.4.1 单元测试（`tests/test_phase_pqr.py` 新建）

```python
import unittest
from unittest.mock import MagicMock, patch
from media_importer.features.scraping.match_models import MatchResult, SelectedCandidate
from media_importer.features.scraping.match_enums import TierShortReason, WhySelected


class TestPhaseP_IsValidParsing(unittest.TestCase):
    """Phase P: is_valid 字段解析"""
    
    def test_is_valid_false_clears_other_fields(self):
        """AI 返回 is_valid=false 时，其他字段被强制清空"""
        from media_importer.scraper._llm_match_assist import _tier2_correct_impl
        # 模拟 AI 返回
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
```

#### 10.4.2 集成测试场景

| 场景 | 文件名 | 期望 match_level | 期望 tier_short_reason 含 |
|------|--------|-----------------|-------------------------|
| 随机字符 | `123uyyt.mkv` | FAILED | "无可识别影视信息" |
| 通用词（候选多） | `消防员.mkv`（Provider 返回 5 部同名） | FAILED | "无可识别影视信息" |
| 通用词（候选唯一） | `消防员.mkv`（Provider 返回 1 部⭐7.0+） | CONTEXT_PASS 或 NEEDS_CONFIRM | "AI 建议..." |
| 知名片无歧义 | `泰坦尼克号.mkv` | CONTEXT_PASS | "1997版，候选首位匹配" |
| 同名多版本 | `美丽人生.mkv` | NEEDS_CONFIRM | "同名多版，倾向1997需确认" |
| 英文+年份 | `Dune.Part.Two.2024.1080p.mkv` | CONTEXT_PASS | "Dune 2 (2024) 候选首位匹配" |
| 占位词 | `Movie.2023.mkv` | FAILED | "占位词，无具体片名" |

#### 10.4.3 前端验证（Playwright）

```javascript
// tests/test_phase_r_ui.py
def test_failed_task_shows_reason_and_rescrape_button(self):
    """失败任务卡片显示原因和重新刮削按钮"""
    # 1. 创建 FAILED 任务
    # 2. 访问任务列表
    # 3. 验证卡片显示 ❌ + ai_reason + 🔄按钮
    
def test_rescrape_button_changes_status_to_pending(self):
    """点击重新刮削后任务状态变为 PENDING"""
    # 1. 点击 🔄 按钮
    # 2. 确认弹窗
    # 3. 验证任务状态变为 PENDING
```

### 10.5 Phase P/Q/R 实施顺序

```
Phase M (Tier 1 候选保留) 
    ↓
Phase P (AI 提示词重设计 + is_valid + selected_candidate_id)
    ↓
Phase Q (FAILED 状态 + runner 处理 + preview_job 处理)
    ↓
Phase N (候选补可信度字段，依赖 Phase M 候选结构)
    ↓
Phase R (前端失败任务 UX + 重新刮削 API)
```

### 10.6 工作量更新

| Phase | 工作量 |
|-------|--------|
| Phase P（AI 提示词 + 解析 + 候选传递） | 3 小时 |
| Phase Q（FAILED 状态 + 后端处理） | 2 小时 |
| Phase R（前端失败 UX + 重新刮削 API） | 2 小时 |
| 测试用例（单元 + 集成 + UI） | 2 小时 |
| **合计新增** | **9 小时** |

**计划总量更新**：原 15 小时 + 新增 9 小时 = **约 24 小时**

---

**扩展计划完毕。等待执行。**

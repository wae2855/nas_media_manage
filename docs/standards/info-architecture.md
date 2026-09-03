# 信息架构标准

**事实源**：本文件定义刮削结果信息的职责分层、字段契约、各视图密度规范。代码实现必须遵循。  
**适用范围**：`media_importer/features/scraping/`、`media_importer/api/`、`media_importer/webui/js/`  
**相关文档**：
- 三级匹配：[scrape-matching.md](scrape-matching.md)
- AI 提示词：[ai-prompt-design.md](ai-prompt-design.md)
- 决策记录：[../decisions/0007-information-responsibility-split.md](../decisions/0007-information-responsibility-split.md)

---

## 一、核心原则：6 层职责模型

刮削描述按**职责**拆成 6 层，每层有**唯一的数据源**和**展示位置**。禁止多层共用一个字段（"万能胶"反模式）。

| Layer | 字段 | 回答的问题 | 展示位置 |
|:-----:|------|-----------|---------|
| **L1** | `match_level` / `match_tier` | 这是什么状态？ | 所有视图的状态标签 |
| **L2** | `tier_short_reason`（≤30字） | 为什么是这个状态？（通用一句话） | 列表行副标题、卡片摘要 |
| **L3** | `ai_reason` | AI 是怎么判断的？ | 卡片"AI 怎么说"区块、详情 Tier 2 步骤 |
| **L4** | `selected_candidate`（结构化） | 最后用了什么？为什么选这个？ | 卡片"最终用了"、详情刮削结果 |
| **L5** | `concerns[]` | 有什么需要留意的？ | 详情"注意事项"、深度追踪 |
| **L6** | `trace_steps[].{reason, ai_reason}` | 完整决策路径，每步发生什么？ | 详情时间轴、追踪弹窗 |

`match_trace.identity_evidence` 是 L6 的结构化附件，保存 `provider_ids`、`nfo_identities`、`ignored_directories` 和 `identity_resolution`。它只用于解释“身份从哪里来、解析到哪个 Provider ID、为何冲突或降级”，不得替代 L1-L5 字段。

---

## 二、字段定义

### 2.1 L1: 状态层

```python
match_level: str       # AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM / FAILED
match_tier: int        # 1 / 2 / 3
```

详见 [scrape-matching.md](scrape-matching.md) 第一节。

### 2.2 L2: 一句话原因

```python
tier_short_reason: str  # ≤30 字
```

**生成规则**：
- Tier 2 优先用 AI 返回的 `short_reason` 字段
- AI 未返回或为空时，用 `TierShortReason` 枚举兜底（见 `match_enums.py`）
- 程序层兜底截断到 30 字 + "..."

**示例**：
- `"唯一精确匹配"`
- `"同名7部，自动选评分最高"`
- `"AI 建议候选，需确认"`
- `"文件名无可识别影视信息"`

### 2.3 L3: AI 原始推理

```python
ai_reason: str  # AI 返回的完整 reason 字段，无长度限制
```

**用途**：详情页深度展示，让用户理解 AI 的判断逻辑。

**示例**：
> "文件名'爱神'为中文通用名称，最知名的是2004年王家卫等人参与的合集电影《Eros》/《爱神》，但无法确定具体匹配项"

**独立存储原则**：不再混入 confirm_reason 拼接串。前端直接读字段。

### 2.4 L4: 最终选择（结构化）

```python
selected_candidate: Optional[SelectedCandidate]
```

`SelectedCandidate` 字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `provider_type` | str | "tmdb" 等 |
| `provider_id` | str | Provider 内部 ID |
| `title` | str | 最终选中标题 |
| `year` | Optional[int] | 年份 |
| `media_type` | str | "movie" / "tv" |
| `why_selected` | str | WhySelected 枚举值（见下表） |
| `score` | Optional[float] | 评分（若适用） |

**why_selected 枚举**：

| 枚举值 | 中文展示 | 触发场景 |
|--------|---------|---------|
| `unique_match` | 唯一精确匹配 | Tier 1 单匹配 |
| `top_rated` | 评分最高(8.5) | Tier 1 评分打破平局 |
| `ai_suggestion` | AI 建议 | Tier 2 高/中确定性 |
| `first_candidate` | Provider 排序第一 | Tier 3 降级 |
| `user_pick` | 用户选择 | Review 后写入 |
| `explicit_provider_id` | 文件名身份编号 | 文件名中的 TMDB/IMDb/TVDB ID 经 Provider 校验通过 |
| `nfo_provider_id` | NFO 身份编号 | 相邻受控 NFO 的 ID 经 Provider 校验通过 |

### 2.5 L5: 关注点列表

```python
concerns: List[MatchConcern]
```

每个 `MatchConcern` 结构：

```python
{
    "code": str,      # 机器可读，如 "NO_YEAR_MULTI_MATCH"
    "message": str,   # 用户可读短文案（≤50字，禁止拼接串）
    "detail": str,    # 详细技术说明（可空）
}
```

**标准 code 取值**：

| code | 触发场景 |
|------|---------|
| `NO_TITLE` | 文件名清洗后无有效标题 |
| `NO_YEAR_MULTI_MATCH` | 多个精确匹配（无年份） |
| `FUZZY_TITLE` | 标题不完全匹配 |
| `NO_PROVIDER_RESULT` | Provider 无结果 |
| `AI_UNCERTAIN` | AI 中/低确定性 |
| `INVALID_FILENAME` | AI 判定文件名无可识别影视信息（FAILED） |
| `MISSING_FIELDS` | Review 阶段缺必填字段 |
| `NO_PROVIDER_MATCH` | Review 阶段无 provider_id |
| `CANDIDATES_AVAILABLE` | 已加载候选列表第一项 |
| `IDENTITY_CONFLICT` | 显式/NFO ID 指向多个作品或与明确年份、类型冲突 |
| `CLOSE_CANDIDATES` | 第一、第二候选身份证据差距不足 |
| `DIM_TRUST_DOWNGRADE` | 维度来源不被信任 |
| `VALIDATE_CONFIRM` | （已废弃，不再使用） |

### 2.6 L6: 过程追踪

```python
trace_steps: List[MatchTraceStep]
```

每个 `MatchTraceStep` 结构：

```python
{
    "tier": int,             # 1 / 2 / 3
    "name": str,             # 步骤名（如 "Provider精确匹配"）
    "matched": bool,         # 本级是否匹配成功
    "search_query": str,     # 搜索查询（若有）
    "match_level": str,      # TitleMatcher L1-L7 级别
    "reason": str,           # 匹配/未匹配原因
    "ai_reason": str,        # AI 判断理由（仅 Tier 2）
}
```

**前端字段读取规则**（重要，曾有 bug）：

```javascript
// 正确：按优先级读取
escapeHtml(step.reason || step.ai_reason || step.result || step.message || "-")

// 错误：字段名不匹配会显示 "-"
escapeHtml(step.result || step.message || "-")
```

---

## 三、各视图信息密度分层

### 3.1 视图密度递进图

```
列表行 (L1+L2) ⊂ 卡片 (L1+L2+L3+L4) ⊂ 详情 (L1-L6) ⊂ 追踪弹窗 (全量)
   ↓                ↓                   ↓                 ↓
 扫一眼            站着看 10s           坐着看 2min        调试用
```

**核心原则**：每一层是上一层的**超集**（增加信息），不是子集（减少信息）。

### 3.2 列表行（最薄）

**回答**：这个为什么需要我？

**必备字段**：L1（match_level 标签）+ L2（tier_short_reason）

**渲染规范**：
- 状态标签：颜色编码
  - AUTO_PASS：绿色
  - CONTEXT_PASS：蓝色（AI 辅助）
  - NEEDS_CONFIRM：橙色（待确认）
  - FAILED：红色
- 一句话原因：≤30 字，超出截断，title 属性显示完整

**禁止**：显示 ai_reason 长文本、显示完整 concerns、显示候选列表

### 3.3 任务卡片（中等密度）

**回答**：AI/Provider 各贡献了什么？

**必备字段**：L1 + L2 + L3 + L4 + 维度标签

**三块结构**（标准布局）：

```
┌──────────────────────────────────────┐
│ 🤖 AI 怎么说                          │
│ ┌──────────────────────────────────┐ │
│ │ {ai_reason}                      │ │ ← L3
│ └──────────────────────────────────┘ │
├──────────────────────────────────────┤
│ ✅ 最终用了                           │
│ {title} ({year}) · {why_selected 中文}│ ← L4
├──────────────────────────────────────┤
│ 🏷️ 维度                              │
│ [是否动漫：否 Provider] [题材：动作...] │
└──────────────────────────────────────┘
```

**渲染规范**：
- AI 怎么说：金色左边框，柔和背景
- 最终用了：why_selected 枚举转中文展示
- 维度标签：每个维度自带颜色（dimDef.color），含来源徽章

### 3.4 任务详情（最厚）

**回答**：完整决策路径，哪里要改？

**必备字段**：L1-L6 全部

**6 步时间轴**（与模拟器一致）：

1. **文件名输入** — 原始文件名
2. **规则清洗（REGEX）** — 清洗方法、移除项、clean_title、year、season/episode
3. **三级匹配路径（MATCH）** — 每个 Tier 的 name + matched + reason + ai_reason + concerns 标签
4. **刮削结果（SCRAPE）** — title_cn、title_en、year、类型、provider_type+provider_id
5. **维度推导（DIMS）** — 每个维度值 + 来源徽章
6. **最终入库判断（RESULT）** — 最终标题、入库目录、规则/兜底标签

**渲染规范**：
- 必须复用 `renderMatchPathPreview`（来自 `cinema-config-simulator.js`）
- 数据必须来自 `buildMatchPathData(task)` 统一装配器
- 禁止各视图自己拼装数据

### 3.5 追踪弹窗（调试用）

**回答**：技术细节

**必备字段**：trace_steps 全量 + candidates[] + dim_sources 表格 + 原始 JSON

**定位**：开发者/高级用户调试，普通用户用不到。

---

## 四、前后端字段契约

### 4.1 scrape_result JSON 必须字段

**正式任务（`scrape.py`）和模拟器（`scrape_preview_job.py`）输出必须完全一致**。

```python
{
    # 基本信息
    "title_cn": str,
    "title_en": str,
    "year": Optional[int],
    "media_type": str,
    "season": Optional[int],
    "episode": Optional[int],
    
    # Provider 信息
    "provider_type": str,
    "provider_id": str,
    "poster_url": str,
    "overview": str,
    
    # 匹配信息（L1-L4）
    "match_level": str,
    "match_tier": int,
    "tier_short_reason": str,
    "ai_reason": str,
    "selected_candidate": Optional[dict],
    
    # 维度（L5 相关）
    "dimensions": dict,  # {dim_name: {value, source}} 或 {dim_name: value}
    
    # 追踪（L5+L6）
    "match_concerns": List[dict],  # [{code, message, detail}]
    "match_trace": dict,           # MatchResult.to_dict() 完整输出
    
    # 模拟器特有
    "preview_selected_candidate": bool,  # 仅模拟器，标记是否预览选中
    
    # FAILED 任务特有
    # 其他字段为空，仅 match_level="FAILED" + tier_short_reason + ai_reason 有效
}
```

### 4.2 禁止字段

**`confirm_reason`**：已废弃。dataclass 中保留字段仅供编译安全，但：
- `MatchResult.to_dict()` 不输出此字段
- 任何业务代码不得读取或赋值
- 任何前端代码不得引用

**反模式**（禁止）：

```python
# ❌ 万能胶拼接
confirm_reason = f"找到{len(matches)}部；AI说：{ai_reason}；缺字段：{missing}"
```

```javascript
// ❌ 前端从拼接串反向解析
const reason = data.confirm_reason;
if (reason.includes("AI")) { /* 显示 AI 区块 */ }
```

### 4.3 前端唯一装配器

**`buildMatchPathData(task)`** 是所有视图获取数据的唯一入口。

**位置**：`media_importer/webui/js/build-match-path-data.js`

**使用规则**：
- 详情视图（`cinema-task-detail.js`）：`buildScrapeTraceSection` 必须用此装配器
- 追踪弹窗（如有）：必须用此装配器
- 模拟器（`cinema-config-simulator.js`）：自身已有数据，可不用装配器，但渲染逻辑必须复用 `renderMatchPathPreview`

**禁止**：各视图自己从 task 对象拼装字段。

---

## 五、UI 视觉规范

### 5.1 状态标签颜色

| 状态 | 颜色 | 用途 |
|------|------|------|
| AUTO_PASS | 绿色 (#22C55E) | 自动通过 |
| CONTEXT_PASS | 蓝色 (#3B82F6) | AI 辅助通过 |
| NEEDS_CONFIRM | 橙色 (#F59E0B) | 待确认 |
| FAILED | 红色 (#D94F45) | 失败 |
| SUCCESS | 绿色 (#22C55E) | 入库成功 |

### 5.2 维度来源徽章

| 来源 | 标签 | 颜色 |
|------|------|------|
| `tmdb` | Provider | 青色 (#43C7B7) |
| `ai_assist` | AI辅助 | 紫色 (#A78BFA) |
| `ai_search` | AI搜索 | 亮青 (#22D3EE) |
| `file` | 文件 | 灰色 (#9B927F) |

### 5.3 维度标签样式

- 背景：`rgba(255,255,255,0.04)`（深色主题半透明）
- 左边框：维度颜色（dimDef.color 或 fallbackColors 循环）
- 标签名：`var(--muted)`（柔和金色）
- 标签值：`var(--ink)`（亮色文字）
- 来源徽章：右上角小标签

---

## 六、不变量（Invariant）

以下规则不可违反：

1. **6 层职责不得混用**：每个字段只回答一个问题，禁止万能胶拼接
2. **L2 长度 ≤30 字**：超出由后端兜底截断
3. **L5 单条 message ≤50 字**：拼接串由 review.py 改为结构化 concerns
4. **模拟器与正式任务字段结构一致**：前端不应区分数据源
5. **前端禁止从拼接串反解析**：所有信息读结构化字段
6. **buildMatchPathData 是唯一装配器**：禁止各视图自己拼
7. **FAILED 状态下 selected_candidate 必为 None**
8. **trace_steps 字段名 reason/ai_reason 不可改名**（前端有依赖）

---

## 七、废弃字段清单

| 字段 | 状态 | 处理 |
|------|------|------|
| `confirm_reason`（MatchResult dataclass） | 保留字段，不输出 | 编译安全用，业务不读写 |
| `confirm_reason`（DB tasks 列） | 本计划退役(Phase 3) | 详见 [优化项计划](../_archive/2026-08-22-plans-cleanup/2026-06-16-optimization-items-plan.md) |
| `_confirm_reason`（task dict 键） | 已删除 | runner.py 改读 scrape_result.tier_short_reason |
| `_build_confirm_reason`（review.py 方法） | 已删除 | 改为 `_build_concerns` 返回结构化 |
| `preview_selected_candidate`（前端分支） | 已重构 | 改读 `selected_candidate.why_selected` |

---

## 八、相关测试

| 测试文件 | 覆盖点 |
|---------|--------|
| `tests/test_match_result_fields.py` | MatchResult 字段输出契约 |
| `tests/test_formal_flow_field_propagation.py` | 正式流程字段传递不回归 |
| `tests/test_phase_pqr.py` | L4 selected_candidate + L1 FAILED 状态 |

---

**本标准由 [plan](../_archive/2026-08-22-plans-cleanup/2026-06-16-scrape-info-responsibility-split-plan.md) 落地，任何字段/视图变更须先更新本文件。**

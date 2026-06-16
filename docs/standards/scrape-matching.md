# 三级匹配标准

**事实源**：本文件定义刮削流程的三级匹配行为契约。代码实现必须遵循，新增/修改字段需先更新本文件。  
**适用范围**：`media_importer/features/scraping/`、`media_importer/features/import_flow/steps/scrape.py`、`media_importer/api/scrape_preview_job.py`  
**相关文档**：
- 架构：[../architecture/scraping.md](../architecture/scraping.md)
- 信息职责：[info-architecture.md](info-architecture.md)
- AI 提示词：[ai-prompt-design.md](ai-prompt-design.md)
- 决策记录：[../decisions/0005-three-tier-matching.md](../decisions/0005-three-tier-matching.md)

---

## 一、匹配级别语义

### 1.1 match_level 四个取值

| match_level | 含义 | 任务流转 | 入库 |
|-------------|------|---------|------|
| `AUTO_PASS` | Tier 1 Provider 精确匹配唯一确定 | 直接进入分类入库 | ✅ 自动 |
| `CONTEXT_PASS` | Tier 2 AI 辅助高确定性匹配 | 直接进入分类入库 | ✅ 自动 |
| `NEEDS_CONFIRM` | 匹配存在但需用户确认（Tier 2 中/低或 Tier 3） | 进入 AWAIT_REVIEW 状态 | ❌ 等确认 |
| `FAILED` | 文件名无可识别影视信息（is_valid=false） | 任务失败，不进入入库 | ❌ 用户重试 |

### 1.2 match_tier 三个取值

| match_tier | 触发 Tier | 说明 |
|:---:|---------|------|
| 1 | Tier 1 | Provider 精确匹配（不调用 AI） |
| 2 | Tier 2 | AI 辅助匹配（调用 LLM） |
| 3 | Tier 3 | AI 不可用降级（纯 Provider 候选） |

### 1.3 certainty 语义（仅 Tier 2）

| certainty | 含义 | 转向 match_level |
|-----------|------|------------------|
| `high` | 高度确信某部具体作品 | `CONTEXT_PASS` |
| `medium` | 有合理猜测但无法 100% 确定 | `NEEDS_CONFIRM` |
| `low` | **不应出现**。若 is_valid=true 但 AI 完全无法推测，应返回 is_valid=false | 防御性兜底为 medium |

---

## 二、完整决策树

```
入口：clean_title + cjk_title + year + path_context
  │
  ▼
┌─ Tier 1: Provider 精确匹配 ─────────────────────────────┐
│  遍历 providers × search_titles 调用 provider.search()  │
│  对每个 result 调用 title_matcher.match_standard()       │
│                                                          │
│  ├─ 恰好 1 个 L1/L2 匹配，或 1 个 L3+无年份              │
│  │    → match_level=AUTO_PASS, tier=1                    │
│  │    → why_selected=unique_match                        │
│  │                                                       │
│  ├─ 多个精确匹配（≥2）                                   │
│  │    → 按热度+评分排序，预选第一，限制 10 条              │
│  │    → match_level=NEEDS_CONFIRM, tier=1                  │
│  │    → why_selected=top_rated                             │
│  │    → 不进入 Tier 2（标题已精确匹配，AI 无增量信息）     │
│  │                                                         │
│  ├─ 模糊匹配（无 L1/L2/L3 精确）                          │
│  │    → 返回 None（fallthrough 到 Tier 2）                 │
│  │                                                         │
│  └─ 所有 Provider 无结果                                  │
│       → 返回 None（fallthrough 到 Tier 2）                 │
└──────────────────────────────────────────────────────────┘
  │ (Tier 1 返回 None)
  ▼
┌─ Tier 2: AI 辅助匹配 ───────────────────────────────────┐
│  收集 path_context（含 Tier 1 候选 provider_candidates）  │
│  调用 LLMScraper.tier2_correct()                         │
│                                                          │
│  AI 返回 JSON:                                           │
│    {is_valid, certainty, corrected_title,                │
│     corrected_year, selected_candidate_id,               │
│     reason, short_reason}                                │
│                                                          │
│  ├─ is_valid=false（垃圾文件/通用词歧义）                 │
│  │    → match_level=FAILED, tier=2                       │
│  │    → 任务失败，不进入入库                              │
│  │                                                       │
│  ├─ is_valid=true + certainty=high                       │
│  │    ├─ 优先用 AI 指定的 selected_candidate_id          │
│  │    │   （从 Tier 1 候选中查找，避免重搜）              │
│  │    ├─ 否则用 corrected_title+year 搜 Provider          │
│  │    │                                                   │
│  │    ├─ 搜到结果                                         │
│  │    │    → match_level=CONTEXT_PASS, tier=2             │
│  │    │    → why_selected=ai_suggestion                  │
│  │    │                                                   │
│  │    └─ 搜不到结果                                       │
│  │         → 降级走 medium 分支                           │
│  │                                                       │
│  ├─ is_valid=true + certainty=medium                     │
│  │    → 搜 Provider（用 corrected_title+year）            │
│  │    → match_level=NEEDS_CONFIRM, tier=2                 │
│  │    → 若有候选，why_selected=ai_suggestion              │
│  │                                                       │
│  └─ AI 调用异常（网络/配置）                              │
│       → 返回 None（fallthrough 到 Tier 3）                │
└──────────────────────────────────────────────────────────┘
  │ (Tier 2 返回 None，即 AI 异常)
  ▼
┌─ Tier 3: 用户确认降级 ──────────────────────────────────┐
│  不调用 AI，纯 Provider 搜索（用原始 clean_title）        │
│  返回最多 5 个候选                                        │
│                                                          │
│  → match_level=NEEDS_CONFIRM, tier=3                     │
│  → 若有候选，why_selected=first_candidate                │
└──────────────────────────────────────────────────────────┘
```

---

## 三、Tier 1 详细规则

### 3.1 精确匹配级别

依赖 `TitleMatcher.match_standard()` 返回的 level：

| Level | 含义 | 视为精确匹配 |
|-------|------|:---:|
| L1 | 完全匹配（含年份） | ✅ |
| L2 | 标题完全相同，年份近似 | ✅ |
| L3 | 标题高度相似（≥0.9） | ✅（仅当 year=None 时） |
| L4-L7 | 模糊匹配 | ❌ |

### 3.2 多匹配处理规则

**规则**：多个精确匹配（≥2）一律 NEEDS_CONFIRM，不自动通过，不进入 Tier 2 AI。

**理由**：
- 标题已精确匹配，AI 无增量信息（不需要 AI 再猜一遍）
- 评分差距大 ≠ 用户想要那个版本（7 个同名作品歧义严重）
- 用户对歧义场景有最终决定权

**处理流程**：

```python
# 1. 保存所有精确匹配候选
self._pending_candidates = [{...} for item, _ in exact_matches]

# 2. 若无季/集信息，用路径上下文推断 media_type（见 3.4 节）
if year is None:
    preferred_type = _infer_media_type_from_path(path_context)
    if preferred_type:
        filtered = [c for c in self._pending_candidates if c.get("media_type") == preferred_type]
        if filtered:
            self._pending_candidates = filtered

# 3. 按热度+评分排序，限制 10 条
self._pending_candidates = _sort_candidates_by_trust(self._pending_candidates)
self._pending_candidates = self._pending_candidates[:10]

# 4. 取第一作为 selected_candidate
top = self._pending_candidates[0]

# 5. 返回 NEEDS_CONFIRM
return MatchResult(
    match_level="NEEDS_CONFIRM",
    match_tier=1,
    selected_candidate=SelectedCandidate(
        title=top["title"], year=top.get("year"),
        why_selected=WhySelected.TOP_RATED,
        score=top.get("vote_average"),
    ),
    candidates=self._pending_candidates[:5],
    tier_short_reason=TierShortReason.TIER1_MULTI.format(count=len(exact_matches)),
)
```

**示例**：
- 美丽人生（7 个同名）→ 按热度排序，1997 版排第一 → NEEDS_CONFIRM（预选 1997 版）
- 速度与激情（3 个同名）→ 按热度排序，2001 版排第一 → NEEDS_CONFIRM

**旧规则（已废弃）**：评分差距 ≥1.5 且 top ≥6.0 时自动通过。废弃原因：评分差距大 ≠ 用户想要那个版本。

### 3.3 候选保留与跨 Tier 复用

**规则**：Tier 1 的候选按场景使用：

| 场景 | 候选用途 |
|------|---------|
| 多个精确匹配 | 直接返回 NEEDS_CONFIRM（tier=1），候选列表供用户选择 |
| 无精确匹配 | 保存到 `_pending_candidates`，供 Tier 2 AI 参考 |

**目的**：
- 多匹配时：用户从候选列表直接确认，不经过 AI
- 无匹配时：AI 能看到 Tier 1 的搜索结果，决策更准

保存后必须立即排序和限制数量：

```python
self._pending_candidates = _sort_candidates_by_trust(self._pending_candidates)
self._pending_candidates = self._pending_candidates[:10]
```

**Tier 2 使用规则**：
- 优先从 `_pending_candidates` 中按 `selected_candidate_id` 查找
- 若未指定 ID 或 ID 不在候选中，按 `corrected_year` 过滤候选
- 都不满足才重新搜索 Provider

---

## 四、Tier 2 详细规则

### 4.1 AI 输入数据契约

调用 `LLMScraper.tier2_correct()` 时传入：

| 字段 | 来源 | 用途 |
|------|------|------|
| `original_filename` | 视频文件名 | 主输入 |
| `clean_title` | FilenameCleaner 输出 | 正则参考标题 |
| `year` | FilenameCleaner 输出 | 正则参考年份 |
| `path_context.parent_folder` | 上级目录名 | 上下文线索 |
| `path_context.grandparent_folder` | 上两级目录名 | 上下文线索 |
| `path_context.path_segments` | 路径段列表 | 上下文线索 |
| `path_context.sibling_files` | 同级文件列表 | 上下文线索 |
| `path_context.provider_candidates` | Tier 1 候选 | **关键**：让 AI 不用猜 |

详细提示词规范见 [ai-prompt-design.md](ai-prompt-design.md)。

### 4.2 AI 输出 JSON 字段

```json
{
  "is_valid": true,
  "certainty": "high",
  "corrected_title": "美丽人生",
  "corrected_year": 1997,
  "media_type_hint": "movie",
  "selected_candidate_id": "637",
  "reason": "详细判断理由（200字内）",
  "short_reason": "≤30字总结"
}
```

字段语义详见 [ai-prompt-design.md](ai-prompt-design.md)。

### 4.3 is_valid=false 触发条件

返回 `is_valid=false` 的情况（宁可保守）：

1. **随机字符或乱码**：`123uyyt`、`asdfgh`、`855`、`yyu`
2. **纯通用名词，对应影视过多**：
   - 单字词：`消防`、`大楼`、`飞机`、`爱情`
   - 通用短语：`我的女神`、`那些日子`（对应几十部作品）
3. **明显非影视内容**：`新建文件夹`、`未命名`、`sample`、`test`

**候选数量影响判定**：
- 同名候选 ≥ 3 部 → 倾向 `is_valid=false`（歧义太大）
- 同名候选唯一且高分 → 倾向 `is_valid=true` + `certainty=high`

### 4.4 防御性兜底

代码层对 AI 返回值的防御处理：

```python
result.setdefault("is_valid", True)  # AI 未返回时默认 True

# is_valid=false 强制清空其他字段
if not result.get("is_valid"):
    result["certainty"] = ""
    result["corrected_title"] = ""
    result["corrected_year"] = None
    result["media_type_hint"] = None
    result["selected_candidate_id"] = None

# certainty=low 不应出现，兜底为 medium
if result.get("is_valid") and result.get("certainty") not in ("high", "medium"):
    result["certainty"] = "medium"

# short_reason 长度兜底（≤30字）
if len(result.get("short_reason", "")) > 33:
    result["short_reason"] = result["short_reason"][:30] + "..."
elif not result.get("short_reason") and result.get("reason"):
    result["short_reason"] = result["reason"][:30] + "..."
```

### 4.5 年份提取（兜底）

AI 经常把年份写在 `reason` 字段（如"2004年王家卫..."）但 `corrected_year` 返回 null。代码层做兜底：

```python
if not result["corrected_year"]:
    search_text = f"{result['reason']} {result['suggestion']}"
    year_match = re.search(r'(\d{4})\s*年|[\s\"](\d{4})[\s\"]|^(\d{4})$', search_text)
    if year_match:
        result["corrected_year"] = int(year_match.group(1) or year_match.group(2) or year_match.group(3))
```

---

## 五、FAILED 状态处理

### 5.1 触发条件

唯一触发：Tier 2 的 AI 返回 `is_valid=false`。

### 5.2 行为契约

- `match_level = "FAILED"`
- `match_tier = 2`
- `selected_candidate = None`
- 任务状态置为 `FAILED`
- **不**调用 Provider 重搜
- **不**进入入库流程
- concerns 中追加 `{code: "INVALID_FILENAME", message: "AI 判定文件名无可识别影视信息"}`

### 5.3 用户挽回路径

任务卡片显示 ❌ + ai_reason + 🔄 重新刮削按钮。用户可：
1. 直接重试（同样文件名）
2. 改名后重试（提供 new_filename）

API：`POST /api/tasks/{id}/rescrape`，body 可选 `{"new_filename": "新文件名.mkv"}`。

---

## 六、Tier 3 降级触发条件

**唯一触发**：Tier 2 AI 调用抛异常（网络/配置/超时）。

**不触发的情况**：AI 调用成功但返回 is_valid=false → 直接 FAILED，**不进入 Tier 3**。

**Tier 3 行为**：
- 不调用 AI
- 用原始 clean_title 搜 Provider
- 返回最多 5 个候选
- `match_level = NEEDS_CONFIRM`，`match_tier = 3`
- 若有候选，`why_selected = first_candidate`

---

## 七、字段输出契约

### 7.1 MatchResult.to_dict() 必须输出

```python
{
    "match_level": str,           # AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM / FAILED
    "match_tier": int,            # 1 / 2 / 3
    "provider_id": Optional[str],
    "provider_title": str,
    "concerns": List[dict],       # [{code, message, detail}, ...]
    "trace": List[dict],          # [{tier, name, matched, reason, ai_reason, ...}, ...]
    "candidates": List[dict],
    "tier_short_reason": str,     # L2 一句话原因
    "ai_reason": str,             # L3 AI 原始推理
    "selected_candidate": Optional[dict],  # L4 结构化
}
```

**禁止输出**：`confirm_reason`（已废弃，保留 dataclass 字段仅供编译安全）

### 7.2 SelectedCandidate.to_dict() 字段

```python
{
    "provider_type": str,
    "provider_id": str,
    "title": str,
    "year": Optional[int],
    "media_type": str,
    "why_selected": str,   # WhySelected 枚举值
    "score": Optional[float],
}
```

### 7.3 why_selected 枚举

| 枚举值 | 触发场景 |
|--------|---------|
| `unique_match` | Tier 1 唯一精确匹配 |
| `top_rated` | Tier 1 评分打破平局 |
| `ai_suggestion` | Tier 2 AI 建议（高/中确定性） |
| `first_candidate` | Tier 3 Provider 排序第一（AI 不可用降级） |
| `user_pick` | 用户在 review 中手动选择 |

---

## 八、Tier 1 候选字典标准结构

跨 Tier 传递的候选字典必须包含：

```python
{
    "id": str,                    # provider_id
    "title": str,
    "original_title": str,        # 空则回退为 title
    "year": Optional[int],        # 空则从 raw_data.release_date 兜底
    "media_type": str,            # "movie" / "tv"
    "provider_type": str,         # "tmdb" / ...
    "poster_url": str,
    "vote_average": float,        # 评分（0 表示无）
    "vote_count": int,            # 投票数
    "popularity": float,          # 热度
}
```

前端候选列表按 `popularity` 降序展示，显示 ⭐评分 + 票数 + 热度。

### 8.1 排序规则

所有 Provider 搜索返回的候选列表，**必须**经过 `_sort_candidates_by_trust()` 排序：

排序 key（降序）：popularity → vote_average → vote_count

适用范围：
- `_search_providers_impl` 返回前
- `_pending_candidates` 保存后
- 任何从 Provider 搜索获取的候选列表

---

## 九、不变量（Invariant）

以下规则不可违反，违反即为 bug：

1. **is_valid=false → match_level 必为 FAILED**，不能是 NEEDS_CONFIRM
2. **certainty=low 不应出现在最终结果中**，防御性兜底为 medium
3. **Tier 1 候选必须保留到 _pending_candidates**，不能丢弃
4. **Tier 2 优先复用 Tier 1 候选**，避免重搜
5. **selected_candidate.why_selected 必须是 WhySelected 枚举值之一**
6. **模拟器（scrape_preview_job）与正式任务（scrape.py）输出的 scrape_result 字段结构必须完全一致**
7. **confirm_reason 字段不再写入任何业务值**（保留仅供编译安全）

---

## 十、相关测试

| 测试文件 | 覆盖点 |
|---------|--------|
| `tests/test_match_engine.py` | Tier 1/2/3 决策树 |
| `tests/test_tier2_match_engine.py` | Tier 2 各 certainty 分支 |
| `tests/test_match_result_fields.py` | MatchResult 字段输出契约 |
| `tests/test_phase_pqr.py` | is_valid / selected_candidate_id / FAILED |
| `tests/test_formal_flow_field_propagation.py` | 正式流程字段传递不回归 |

---

**本标准由 [plan](../plans/2026-06-16-scrape-info-responsibility-split-plan.md) 落地，任何字段/行为变更须先更新本文件。**

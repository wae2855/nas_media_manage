# ADR-0007: Scrape Information Responsibility Split

Date: 2026-06-16
Status: Accepted
Related: [0005-three-tier-matching.md](0005-three-tier-matching.md)
Plan: [2026-06-16-scrape-info-responsibility-split-plan.md](../_archive/2026-08-22-plans-cleanup/2026-06-16-scrape-info-responsibility-split-plan.md)

## Context

ADR-0005 落地三级匹配策略后，刮削流程产出大量描述信息（AI 推理、匹配原因、关注点、Provider 候选等）。这些信息最初全部汇入一个 `confirm_reason` 字符串字段，用 `；` 拼接 4 类不同性质的内容：

```
confirm_reason 示例：
"找到 3 部同名作品；搜索 '爱神' 返回 3 条精确匹配；
 AI 无法确定标题，需要人工确认；文件名'爱神'为中文通用名称，
 最知名的是2004年王家卫等人参与的合集电影《Eros》/《爱神》"
```

这导致：

1. **列表视图无法取出"一句话原因"**：拿到了 4 句话拼接，无法用作副标题
2. **详情视图无法分步展示**：数据已糊在一起，无法按 Tier 拆分
3. **AI 推理文本丢失**：`trace_steps[].reason` 和 `ai_reason` 字段被持久化但前端从不读
4. **5 套 UI 视图各显示不同子集**：列表/卡片/详情/追踪弹窗/模拟器互不一致
5. **前后端字段名 bug**：追踪弹窗读 `step.result` 但后端输出 `step.reason`，所有步骤显示"-"

同时 Tier 1 找到的候选被丢弃、Tier 2/3 重新搜索导致结果不稳定；垃圾文件名（如 `123uyyt.mkv`）仍走完整流程浪费 API 调用。

## Decision

### 决策 1：信息按 6 层职责拆分

将所有刮削描述按**职责**拆成 6 层，每层有唯一数据源和展示位置：

| Layer | 字段 | 定位 |
|:---:|------|------|
| L1 | `match_level` / `match_tier` | 所有视图的状态标签 |
| L2 | `tier_short_reason`（≤30字） | 列表行副标题、卡片摘要 |
| L3 | `ai_reason` | 卡片"AI 怎么说"、详情 Tier 2 步骤 |
| L4 | `selected_candidate`（结构化） | 卡片"最终用了"、详情刮削结果 |
| L5 | `concerns[]` | 详情"注意事项"、深度追踪 |
| L6 | `trace_steps[].{reason, ai_reason}` | 详情时间轴、追踪弹窗 |

详见 [../standards/info-architecture.md](../standards/info-architecture.md)。

### 决策 2：Tier 1 候选保留与跨 Tier 复用

Tier 1 找到的候选不再丢弃，保存到 `self._pending_candidates`。Tier 2 AI 收到候选列表后：
- 优先用 `selected_candidate_id` 指定（不重搜 Provider）
- 或按 `corrected_year` 过滤候选
- 都不满足才重新搜索

详见 [../standards/scrape-matching.md](../standards/scrape-matching.md) 第三节。

### 决策 3：is_valid 与 certainty 双字段分离

AI 输出用两个字段承载"有效性"和"确定性"：

- `is_valid=false`（垃圾文件/通用词歧义）→ match_level=FAILED，不搜 Provider
- `certainty=high/medium`（仅 is_valid=true 时有意义）→ 决定是否自动入库

`certainty=low` 不应出现；若 is_valid=true 但 AI 完全无法推测，应返回 is_valid=false。

详见 [../standards/ai-prompt-design.md](../standards/ai-prompt-design.md)。

### 决策 4：FAILED 状态作为终态

新增 `match_level="FAILED"` 表示任务因文件名不可识别而失败：
- 不进入入库流程
- 任务卡片显示 ❌ + ai_reason + 🔄 重新刮削按钮
- 用户可改名后重试（`POST /api/tasks/{id}/rescrape`）

### 决策 5：前端统一数据装配器

新建 `buildMatchPathData(task)` 作为所有视图获取数据的唯一入口，禁止各视图自己从 task 对象拼装字段。渲染统一通过 `renderMatchPathPreview`。

### 决策 6：废弃 confirm_reason 万能胶

- `MatchResult.confirm_reason` 字段保留（编译安全），但 `to_dict()` 不输出
- 任何业务代码不得读取或赋值
- 前端不得引用
- DB `tasks.confirm_reason` 列待清理（见 [../plans/2026-06-16-optimization-items-plan.md](../_archive/2026-08-22-plans-cleanup/2026-06-16-optimization-items-plan.md)）

## Consequences

### 正面

- **列表/卡片/详情各取所需**：每层视图读自己该读的字段，不再"一改全改"
- **AI 推理文本恢复**：`ai_reason` 独立存储后，卡片能直接展示
- **字段名 bug 修复**：追踪弹窗步骤不再显示"-"
- **数据不再丢失**：Tier 1 候选保留，跨 Tier 复用，结果更稳定
- **垃圾文件快速失败**：不浪费 Provider API 调用
- **模拟器与正式任务一致**：前端 `buildMatchPathData` 统一处理

### 负面

- **数据模型扩展**：`MatchResult` 新增 3 个字段 + `SelectedCandidate` 新 dataclass
- **AI 提示词增长**：从 ~300 字涨到 ~700 字（含规则和示例），token 成本略增
- **DB schema 待清理**：`confirm_reason` 列仍存在但无读写（低风险）

### 风险与缓解

| 风险 | 缓解 |
|------|------|
| AI 误判垃圾文件导致任务失败 | 失败任务保留"重新刮削"入口，用户改名后可重试 |
| `certainty=low` 边界模糊 | 提示词明确"宁可返回 is_valid=false"，代码层兜底改 medium |
| 候选数量影响 is_valid 判定 | 标准文档固化边界规则（≥3 部歧义 / 唯一+高分） |

## Compliance

以下测试验证本决策的落地：

| 测试 | 覆盖点 |
|------|--------|
| `tests/test_match_result_fields.py` | MatchResult 字段输出契约 |
| `tests/test_phase_pqr.py` | is_valid / selected_candidate_id / FAILED 流转 |
| `tests/test_formal_flow_field_propagation.py` | 正式流程字段传递不回归 |

## Alternatives Considered

### 备选 1：保留 confirm_reason，前端反向解析

拒绝原因：LLM 产出文本结构不稳定，正则解析容易碎。且违反"字段职责单一"原则。

### 备选 2：低确定性仍搜 Provider（兜底）

拒绝原因：用户明确决策"垃圾文件直接失败，不浪费 API"。`certainty=low` 在新模型中不应出现。

### 备选 3：不新增 selected_candidate，仍用 candidates[0]

拒绝原因：无法区分"AI 指定"vs"Provider 排序第一"，前端无法展示准确的选择原因。

## References

- 实施 Plan：[2026-06-16-scrape-info-responsibility-split-plan.md](../_archive/2026-08-22-plans-cleanup/2026-06-16-scrape-info-responsibility-split-plan.md)
- 字段传递修复：[2026-06-16-fix-field-propagation-prompt.md](../_archive/2026-08-22-plans-cleanup/2026-06-16-fix-field-propagation-prompt.md)
- 行为标准：[../standards/scrape-matching.md](../standards/scrape-matching.md)
- 信息架构：[../standards/info-architecture.md](../standards/info-architecture.md)
- AI 提示词：[../standards/ai-prompt-design.md](../standards/ai-prompt-design.md)
- 前置决策：[0005-three-tier-matching.md](0005-three-tier-matching.md)

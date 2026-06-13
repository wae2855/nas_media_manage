---
title: "refactor: 三级匹配策略重构 — 替代置信度公式体系"
type: plan
date: 2026-06-12
status: complete
confidence: high
requirement: REQ-20260612-THREE-TIER-MATCH
adr: docs/decisions/0005-three-tier-matching.md
---

# 三级匹配策略重构方案

**需求编号**：REQ-20260612-THREE-TIER-MATCH
**架构决策**：[ADR-0005: 三级匹配策略](file:///Users/wangwei/Documents/code/nas_media_manage/docs/decisions/0005-three-tier-matching.md)
**需求看板**：注册于 [requirements-board.md](file:///Users/wangwei/Documents/code/nas_media_manage/docs/tracking/requirements-board.md)

## 一句话摘要

用离散的三级匹配策略（Provider精确匹配 → 上下文辅助匹配 → 用户确认）替代当前的数学公式化置信度体系（T×R×data_gate），大幅简化配置、代码和用户认知负担。

## 问题陈述

当前置信度系统是一个过度工程的数学模型：

1. **配置爆炸** — `DEFAULT_CONFIDENCE_CONFIG` 有 20+ 参数，每个维度还有独立的 sources/trusted/source_confidence/veto_threshold/weight 配置，用户无法理解
2. **过度量化** — 把「匹配/不匹配」的离散判断伪装成连续概率，L1=1.0/L2=0.9/L3=0.7 等数值没有真实概率含义
3. **data_gate 杀伤力过大** — 任一维度来源不信任就归零，太粗暴
4. **R 值（结果数惩罚）意义存疑** — 标题+年份已经能唯一定位，搜索返回多少条不影响判断
5. **前端展示复杂** — 置信度数值（0.83）、阈值条（拖拽调节）、维度来源信任配置、R值公式选择、置信度详情弹窗，认知负担极大
6. **维护成本高** — 5 个核心文件 ~800 行代码，改一个匹配策略要同时改 confidence_engine、title_matcher、confidence_models、config、trace_builder、前端

## 目标终态

1. 匹配判断简化为三级：精确匹配（自动通过）→ 上下文辅助（AI判断）→ 用户确认
2. 置信度配置页面移除，用户不需要理解任何数值参数
3. 维度体系保留，但来源策略简化：TMDB → 确定性映射 → AI补齐（含联网搜索）
4. 分辨率等文件维度独立于刮削，由 ffprobe 直接检测
5. 任务卡片展示匹配状态标签，而非置信度数值
6. 用户确认时展示明确的「匹配疑虑原因」，帮助用户快速决策
7. 模拟运行改为展示三级匹配路径，不再是双模式对比+置信度

## 范围与非目标

**范围内：**

- 后端：`confidence_engine.py` 重写为 `match_engine.py`（三级匹配策略）
- 后端：`confidence_models.py` 简化（去掉 R/aggregate/gate 模型）
- 后端：`metadata_scrape_flow.py` 适配新匹配流程
- 后端：`review.py` 审核决策逻辑简化
- 后端：`_scrape_preview` API 返回结构适配
- 后端：配置系统简化（去掉 confidence 区块大部分参数）
- 前端：移除置信度配置面板
- 前端：模拟运行重写为三级匹配展示
- 前端：任务卡片匹配状态展示 + 疑虑原因提示
- 前端：置信度详情弹窗替换为匹配路径展示
- DB：`scrape_confidence` 字段改为 `match_level` 枚举

**非目标：**

- 不改变 Provider 抽象（TMDB 客户端保持不变）
- 不改变维度定义和映射逻辑（`dimension_manager.py` 保持不变）
- 不改变文件名清洗器（`filename_cleaner.py` 的正则+CJK分离逻辑是亮点）
- 不改变文件操作/入库流程
- 不改变任务状态机（QUEUED/RUNNING/AWAIT_REVIEW/SUCCESS/FAILED 保持不变）
- 不改变分辨率检测（`file_analyzer.py` / ffprobe 保持不变）
- 不在本次重构中重新设计前端整体布局

## 方案详述

### 一、三级匹配模型

#### 第一级：Provider 精确匹配

```
文件名清洗 → 提取中文名/英文名/年份/季/集
        │
        ├── 用中文名+年份查 Provider
        │     → 精确匹配到唯一结果 → ★ AUTO_PASS
        │
        ├── 用英文名+年份查 Provider
        │     → 精确匹配到唯一结果 → ★ AUTO_PASS
        │
        ├── 无年份，只用名字查
        │     → 唯一精确匹配 → ★ AUTO_PASS
        │     → 多个精确匹配 → 进入第二级（原因：无年份导致多个同名结果）
        │
        └── 无精确匹配 → 进入第二级
```

**精确匹配定义**（复用现有 TitleMatcher L1 逻辑）：
- 清洗后标题与 Provider 返回标题（original_title 或 title）归一化后完全相等
- 年份精确一致（如果文件名有年份）
- 或者无年份但搜索结果只返回 1 条精确标题匹配

**关键简化**：不再需要 R 值惩罚。精确匹配就是精确，不需要用搜索结果数量来打折。

#### 第二级：上下文辅助匹配

```
收集上下文信息：
  ├── 同级目录文件名列表（同一文件夹下的其他视频）
  ├── 上级文件夹名
  ├── 文件名中提取的其他信息（分辨率、制作组等）
  │
  将以下信息交给 AI：
  ├── 文件名清洗结果（标题/年份/季集）
  ├── Provider 搜索候选列表（Top 5-10，含标题/年份/简介）
  ├── 目录上下文
  │
  AI 辅助判断（无需联网搜索增强）：
  ├── 能确定匹配 → ★ AUTO_PASS（附 AI 判断理由）
  └── 无法确定 → 进入第三级（附 AI 不确定的原因）
```

**关键设计**：
- AI 此时不需要联网搜索，因为候选列表已由 Provider 提供
- AI 只需要从候选列表中选出正确的那个，并给出理由
- 如果目录上下文足够（如文件夹名就是剧名），AI 几乎 100% 能判断

**上下文收集的具体逻辑**：

```python
def _collect_context(self, video_path: str) -> dict:
    """收集目录上下文信息"""
    context = {}

    # 1. 上级文件夹名
    parent_dir = os.path.basename(os.path.dirname(video_path))
    if parent_dir and parent_dir not in (".", "..", "/"):
        context["parent_folder"] = parent_dir

    # 2. 同级目录文件名列表（限制最多 20 个，避免过长）
    dir_path = os.path.dirname(video_path)
    try:
        siblings = [
            f for f in os.listdir(dir_path)
            if f != os.path.basename(video_path)
            and any(f.endswith(ext) for ext in (".mkv", ".mp4", ".avi", ".ts", ".wmv", ".flv"))
        ][:20]
        if siblings:
            context["sibling_files"] = siblings
    except OSError:
        pass

    # 3. 上两级文件夹名（如 /series/Breaking Bad/Season 01/）
    grandparent = os.path.basename(os.path.dirname(os.path.dirname(video_path)))
    if grandparent and grandparent not in (".", "..", "/"):
        context["grandparent_folder"] = grandparent

    return context
```

**AI 辅助判断 Prompt 模板**：

```
你是一个影视元数据匹配助手。根据以下信息，从候选列表中选出最匹配的结果。

## 待匹配文件信息
- 文件名: {original_filename}
- 清洗标题: {clean_title}
- 年份: {year 或 "未知"}
- 季: {season 或 "未知"}
- 集: {episode 或 "未知"}

## 目录上下文
- 上级文件夹: {parent_folder 或 "无"}
- 上两级文件夹: {grandparent_folder 或 "无"}
- 同级文件: {sibling_files 或 "无"}

## 候选列表
{candidates_json}

## 输出要求
返回 JSON:
{
  "selected_index": 0,       // 选中的候选索引，从 0 开始
  "confidence": 0.9,         // 判断置信度 0-1
  "reason": "标题精确匹配，且上级文件夹名一致"
}

如果你无法确定，设置 confidence < 0.7 并说明原因。
如果没有任何候选匹配，设置 selected_index = -1。
```

**"AI 不确定"的判定规则**：
- AI 返回 `confidence < 0.7` → 不确定
- AI 返回 `selected_index = -1` → 无匹配
- AI 返回格式错误/调用失败 → 降级

**AI 调用成本估算**：

| 假设条件 | 数值 |
|----------|------|
| 用户平均文件数 | 1000 个 |
| 第一级精确匹配率 | 85% |
| 走第二级的文件数 | 150 个（15%） |
| 每次调用 token 估算 | ~800 输入 + ~100 输出 |
| 模型单价（参考智谱） | ~0.002 元/次 |
| 总成本估算 | ~0.3 元（1000 文件） |

成本极低，不构成瓶颈。延迟方面每次调用约 1-3 秒，可批量并发。

**第二级降级策略**：

当 AI 不可用（未配置 LLM / 调用失败 / 超时）时：
```
第二级 AI 不可用 → 跳过第二级 → 直接进入第三级
疑虑原因附加: AI_UNCERTAIN + "AI 辅助不可用，降级为人工确认"
```

降级后不直接失败，用户体验只是多了确认步骤。

#### 第三级：用户确认

```
准备用户确认数据：
  ├── Provider 搜索结果 Top 5（按热度排序，默认选中第 1 个）
  ├── 匹配疑虑原因（为什么无法自动匹配）
  ├── 已提取的文件信息（标题/年份/季集）
  │
  展示给用户：
  ├── 疑虑原因标签（如"无年份，同名作品3部"）
  ├── 候选列表（可切换选择）
  └── 确认入库按钮
```

### 二、匹配疑虑原因体系

这是新方案的核心用户体验改进。每个进入用户确认的任务必须携带明确的疑虑原因：

| 疑虑类型 | reason_code | 展示文案 | 示例 |
|----------|-------------|----------|------|
| 无年份多同名 | `NO_YEAR_MULTI_MATCH` | 「无年份信息，找到 N 部同名作品」 | "Inception" 无年份 → 2010 版 vs 其他 |
| 年份不匹配 | `YEAR_MISMATCH` | 「文件名年份与搜索结果不一致」 | 文件名 2023，搜索结果只有 2022 版 |
| 标题模糊匹配 | `FUZZY_TITLE` | 「标题不完全匹配，相似度 N%」 | 文件名 "Wandering Earth"，TMDB 是 "The Wandering Earth" |
| Provider 无结果 | `NO_PROVIDER_RESULT` | 「刮削源未找到匹配作品」 | 极小众影片 |
| 标题缺失 | `NO_TITLE` | 「无法从文件名提取有效标题」 | 文件名全是乱码 |
| 多信息冲突 | `CONFLICTING_INFO` | 「文件名信息与目录结构信息冲突」 | 文件名暗示电影，目录结构暗示剧集 |
| AI 不确定 | `AI_UNCERTAIN` | 「AI 辅助判断后仍无法确定」 | 候选列表中有两个非常接近的结果 |

**疑虑原因数据结构**：

```python
@dataclass
class MatchConcern:
    code: str              # reason_code
    message: str           # 用户可读文案
    detail: str            # 详细技术说明
    candidates: list       # 候选列表（用于第三级展示）
```

### 三、维度处理策略（与匹配解耦）

维度判断和匹配判断**彻底解耦**。

#### 维度确认三级流程

每个维度的值来源按优先级逐级尝试：

**第一级：Provider 直接映射**
- Provider 结构化数据通过确定性规则映射为维度值，100% 信任
- `media_type`：由搜索端点硬编码（`/search/movie` → movie, `/search/tv` → tv），不需要AI辅助
- `documentary`：`genre_ids=99` → true
- `animation`：`genre_ids=16` → true
- `region`：`origin_country` 直接映射
- `origin_lang`：`original_language` 直接映射
- `broad_genre`：`genre_ids` 映射（优先级复杂时降级到第二级）
- 多 Provider 兼容：`provider_mappings` 按 Provider 分组，`map_provider_to_dimension()` 按 `provider_type` 选择映射规则
- 来源标记：`provider:tmdb` / `provider:douban`

**第二级：AI 辅助模型分析（不需要联网搜索）**
- Provider 有数据但映射复杂时，AI 辅助模型分析判断
- `restricted_level`：TMDB 有 `release_dates` 但各国分级体系不同，AI 将 MPAA/BBFC/中国分级映射到统一的 0-6/7-12/13-16/17+
- `broad_genre`：genre_ids 映射优先级复杂时，AI 替代复杂映射
- 来源标记：`ai_assist`

**第三级：AI 联网搜索增强（需开关启用）**
- Provider 和 AI 辅助都无法获取的维度，AI 联网搜索补充
- 仅用于维度补全，不再作为刮削器搜不到时的兜底
- 需要启用开关（`ai_search.enabled`）
- 来源标记：`ai_search`

**其他维度**：
- `resolution_tier`：ffprobe 文件检测，与刮削无关，来源标记 `file`

#### 维度信任配置

每个维度新增两个独立信任开关：

| 开关 | 字段 | 默认值 | 含义 |
|------|------|--------|------|
| 信任AI辅助映射 | `trust_ai_assist` | 1（信任） | AI辅助模型分析给出的维度值是否直接采纳 |
| 信任AI联网搜索 | `trust_ai_search` | 0（不信任） | AI联网搜索增强给出的维度值是否直接采纳 |

不信任的AI来源维度值需要人工确认，自动生成 `confirm_reason`。

#### 维度来源追踪

每个维度值记录来源，用于展示和确认判定：

| 来源 | 格式 | 图标 | 含义 |
|------|------|------|------|
| TMDB直接映射 | `provider:tmdb` | 🗄️ | 来自 TMDB 直接映射 |
| 豆瓣直接映射 | `provider:douban` | 📚 | 来自豆瓣直接映射 |
| AI辅助映射 | `ai_assist` | 🤖 | 来自 AI辅助模型映射 |
| AI联网搜索 | `ai_search` | 🔍 | 来自 AI联网搜索增强 |
| 文件分析 | `file` | 📄 | 来自文件分析（如分辨率） |

### 四、配置规划

#### 移除的配置

```yaml
# 以下配置全部移除，不再需要用户配置
confidence:
  provider_match_threshold: 0.85    # 移除
  title_exact_with_year: 1.0        # 移除
  title_exact_with_season: 0.9      # 移除
  title_exact_no_year: 0.7          # 移除
  title_exact_year_mismatch: 0.4    # 移除
  title_fuzzy_year_coeff: 0.7       # 移除
  title_min_similarity: 0.3         # 移除
  R_formula: "log"                  # 移除
  R_max_results_cap: 10             # 移除
  R_min_value: 0.1                  # 移除
  R_T_floor: 1.0                    # 移除
  R_T_curve: 1.5                    # 移除
  source_priority: [...]            # 移除
  ai_cap_high_similarity: 0.7       # 移除
  ai_cap_low_similarity: 0.3        # 移除
  ai_cap_no_title: 0.3              # 移除
  ai_cap_no_match: 0.2              # 移除
  ai_cap_low_coeff: 0.5             # 移除
  pass_threshold: 0.8               # 移除
  confirm_threshold: 0.5            # 移除
  review_threshold: 0.3             # 移除
  dimensions:                       # 移除（每个维度的 sources/trusted/veto 等子配置）
    media_type: {...}
    documentary: {...}
    ...

llm:
  confidence_threshold: 0.8         # 移除
```

#### 保留的配置（预置，用户一般不需修改）

```yaml
metadata:
  scrape_mode: "provider_first"     # 保留为唯一模式（见下方 ai_only 迁移策略）

manual_review:
  enabled: false                    # 保留，强制所有任务走用户确认
```

#### ai_only 模式迁移策略

当前 `scrape_mode` 支持 `provider_first` 和 `ai_only` 两种模式。新方案中：

- `provider_first` 保留为唯一刮削模式（因为第二级上下文辅助已内置 AI 辅助能力）
- `ai_only` 模式不再需要单独存在，因为新流程已将 AI 辅助嵌入三级匹配

**迁移规则**：

| 旧配置 | 迁移后 | 处理方式 |
|--------|--------|----------|
| `scrape_mode: "provider_first"` | 不变 | 无需处理 |
| `scrape_mode: "ai_only"` | `scrape_mode: "provider_first"` | 自动迁移 + 启动日志告警 |
| `scrape_mode: "hybrid"` | `scrape_mode: "provider_first"` | 已废弃的旧值，自动迁移 |

**未配置 Provider 的情况**：

如果用户原来使用 `ai_only` 是因为未配置 TMDB API Key：

1. 启动时检测：`scrape_mode=provider_first` 但无可用 Provider
2. 在日志中打印 WARNING：「未配置元数据 Provider（TMDB），刮削将降级为 AI-only 模式」
3. 自动降级为第二级跳过第一级，所有文件走第二级（AI辅助）→ 第三级（用户确认）
4. 前端配置页的 Provider 区块展示提示：「建议配置 TMDB API Key 以获得更精确的自动匹配」

**这样做的理由**：新方案的第二级 AI 辅助本质上已经覆盖了 `ai_only` 的能力，但多了目录上下文辅助，效果更好。保留 Provider 优先是因为 TMDB 数据是结构化的确定性来源，比纯 AI 判断更可靠。

**前端刮削模式选择器处理**：

- 移除 `ai_only` / `hybrid` 选项
- 如果配置文件中是旧值，前端显示时映射为 `provider_first`
- 配置页不再展示"刮削模式"选择器（因为只有一个模式），减少用户困惑

#### 新增的配置（可选）

```yaml
matching:
  # 以下全部有合理默认值，高级用户可调
  exact_match_t_threshold: 1.0      # 第一级精确匹配的 T 值阈值，默认 1.0（即必须精确）
  context_match_enabled: true       # 是否启用第二级上下文辅助，默认 true
  max_candidates_for_user: 5        # 用户确认时展示的最大候选数，默认 5
```

**设计原则**：绝大多数用户不需要改任何配置。`matching` 区块甚至可以不出现，全部用默认值。

### 五、前端改造

#### 5.1 移除的组件

| 组件 | 文件 | 处理方式 |
|------|------|----------|
| 置信度配置面板 | `cinema-confidence.js` (404行) | **整个文件移除** |
| 置信度配置样式 | `cinema-confidence.css` | **整个文件移除** |
| 维度置信度配置样式 | `cinema-confidence-dimensions.css` | **整个文件移除** |
| 置信度详情弹窗 | `confidence-detail.js` (409行) | **整个文件移除**，替换为匹配路径展示 |
| 配置页中的置信度区块 | `cinema-config.js` 中的 confidence 相关函数 | 移除 `saveConfidenceConfig()`、`getConfidenceConfig()` 等 |
| 配置页中的置信度模拟按钮 | `index.html` 中的 `#btn-confidence-simulate` | 移除 |

#### 5.2 改造的组件

**模拟运行（cinema-config.js）**

改造前：双模式（provider_first vs ai_only）对比 + 置信度分解
改造后：三级匹配路径展示

```
展示流程：
  ┌─ 文件名输入 ─────────────────────────────────────┐
  │  原始文件名: [Inception.2010.1080p.BluRay.mkv]    │
  └──────────────────────────────────────────────────┘
         │
  ┌─ 清洗结果 ───────────────────────────────────────┐
  │  标题: Inception  年份: 2010  季: -  集: -       │
  └──────────────────────────────────────────────────┘
         │
  ┌─ 第一级：Provider 精确匹配 ──────────────────────┐
  │  ✅ TMDB 精确匹配成功                             │
  │  匹配: Inception (2010)                          │
  │  T=1.0 精确匹配 + 年份一致                        │
  └──────────────────────────────────────────────────┘
         │
  ┌─ 维度映射结果 ───────────────────────────────────┐
  │  类型: 电影  纪录片: 否  限制级: 13-16            │
  │  来源: TMDB                                       │
  └──────────────────────────────────────────────────┘
         │
  ┌─ 最终结果 ───────────────────────────────────────┐
  │  匹配级别: ★ 自动通过                              │
  │  预估入库: /电影/Inception (2010)/...             │
  └──────────────────────────────────────────────────┘
```

或者当第一级未匹配时：

```
  ┌─ 第一级：Provider 精确匹配 ──────────────────────┐
  │  ⚠️ 未精确匹配                                    │
  │  原因: 标题模糊匹配(相似度 0.72)                   │
  └──────────────────────────────────────────────────┘
         │
  ┌─ 第二级：上下文辅助匹配 ─────────────────────────┐
  │  目录信息: /media/series/Breaking Bad/             │
  │  同级文件: S01E01.mkv, S01E02.mkv, ...            │
  │  ✅ AI 辅助判断: Breaking Bad (2008)              │
  │  理由: 文件夹名+文件命名模式确认                    │
  └──────────────────────────────────────────────────┘
         │
  ┌─ 最终结果 ───────────────────────────────────────┐
  │  匹配级别: ★ 自动通过（AI辅助）                    │
  └──────────────────────────────────────────────────┘
```

**任务卡片（cinema-tasks.js）**

改造前：
```
封面图 | 标题           | 状态徽章
       | 描述           | 电影 · 2010 · 置信度 0.83
       | [详情] [去确认]
```

改造后：
```
封面图 | 标题           | 状态徽章
       | 描述           | 电影 · 2010 · ✅ 自动匹配
       | [详情] [去确认]
```

待确认任务增加疑虑标签：
```
封面图 | 标题           | ⚠️ 待确认
       | 描述           | 电影 · 2010
       | ⚠️ 无年份，同名作品3部
       | [详情] [去确认]
```

**`taskMeta()` 函数改造**：

```javascript
// 改造前
if (confidence !== undefined) bits.push(`置信度 ${value.toFixed(2)}`);

// 改造后
const matchLevel = task.match_level || task.scrape_match_level;
if (matchLevel === "AUTO_PASS") bits.push("✅ 自动匹配");
else if (matchLevel === "CONTEXT_PASS") bits.push("🤖 AI辅助匹配");
else if (matchLevel === "NEEDS_CONFIRM") bits.push("⚠️ 需确认");
```

**`taskDescription()` 函数改造**：

```javascript
// 待确认任务的描述增加疑虑原因
if (status === "PENDING" && stage === "AWAIT_REVIEW") {
    const concerns = task.match_concerns || [];
    if (concerns.length > 0) {
        return concerns.map(c => c.message).join("；");
    }
    return "需要你确认最终匹配结果。";
}
```

**任务详情弹窗改造**：

改造前：置信度详情弹窗（`showConfidenceDetailModal`）展示时间线计算步骤
改造后：匹配路径展示

```
┌─ 匹配路径 ────────────────────────────────────────┐
│                                                    │
│  ① 文件名清洗                                      │
│     Inception.2010.1080p.BluRay → Inception (2010) │
│                                                    │
│  ② Provider 搜索                                   │
│     TMDB 搜索 "Inception" + year=2010              │
│     → 1 条精确匹配                                  │
│                                                    │
│  ③ 匹配结果: ✅ 精确匹配                             │
│     Inception (2010) - T=1.0                       │
│                                                    │
│  ④ 维度映射: TMDB 直接提供                          │
│     类型=电影 纪录片=否 限制级=13-16                 │
│                                                    │
└────────────────────────────────────────────────────┘
```

#### 5.3 配置页改造

移除置信度配置区块（整个 `data-section="confidence"` 面板），保留其他配置：
- 入库名称规范
- 源目录配置
- Provider 配置
- AI 模型配置
- 人工审核开关
- 维度配置（维度管理页签保持不变，但移除来源信任配置）

模拟运行按钮从置信度配置区移到独立位置或入口页。

#### 5.4 维度配置页签改造

改造前：每个维度卡片中有「来源信任」配置（trusted_sources / source_confidence / veto_threshold）
改造后：移除所有来源信任配置，维度来源策略改为固定的「TMDB优先 → AI补齐」

维度卡片只保留：
- 维度名称 + 标签
- 是否启用开关
- 值列表（可选值管理）
- 描述说明

### 六、后端改造

#### 6.1 新增/重写文件

**`features/scraping/match_engine.py`**（替代 `confidence_engine.py`）

```python
@dataclass
class MatchConcern:
    code: str
    message: str
    detail: str

@dataclass
class MatchResult:
    level: str           # AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM
    provider_id: int     # 匹配到的 Provider 条目 ID
    provider_title: str
    confidence_reason: str  # 为什么匹配成功或失败
    concerns: List[MatchConcern]  # 疑虑原因列表
    trace: dict          # 匹配路径追踪

class MatchEngine:
    def match(self, filename, clean_result, providers, conn) -> MatchResult:
        # 第一级：Provider 精确匹配
        result = self._tier1_exact_match(clean_result, providers)
        if result:
            return result

        # 第二级：上下文辅助匹配
        result = self._tier2_context_match(clean_result, providers, filename)
        if result:
            return result

        # 第三级：用户确认
        return self._tier3_user_confirm(clean_result, providers)

    def _tier1_exact_match(self, clean_result, providers):
        """用中文名/英文名+年份精确搜索 Provider"""
        ...

    def _tier2_context_match(self, clean_result, providers, filename):
        """收集目录上下文 + Provider候选 + AI辅助判断"""
        ...

    def _tier3_user_confirm(self, clean_result, providers):
        """返回 NEEDS_CONFIRM + 疑虑原因 + 候选列表"""
        ...
```

**`features/scraping/match_models.py`**（替代 `confidence_models.py`）

精简的数据模型，只保留：
- `CleanResult`（文件名清洗结果，保持不变）
- `MatchResult`（新的匹配结果，替代旧的 `MatchResult` + `ConfidenceResult`）
- `MatchConcern`（疑虑原因）
- 移除：`_calc_R()`、`_aggregate()`、R 值公式、聚合方法、所有阈值参数

#### 6.2 改造的文件

**`features/import_flow/services/review.py`**

```python
class ReviewDecisionService:
    def evaluate(self, scraped: dict) -> ReviewDecision:
        match_level = scraped.get("match_level", "NEEDS_CONFIRM")
        concerns = scraped.get("match_concerns", [])

        if match_level == "AUTO_PASS":
            return ReviewDecision(action="continue")

        if match_level == "CONTEXT_PASS":
            return ReviewDecision(action="continue")

        if match_level == "NEEDS_CONFIRM":
            reason = "；".join(c["message"] for c in concerns) if concerns else "需要人工确认"
            return ReviewDecision(action="confirm", reason=reason, concerns=concerns)

        return ReviewDecision(action="failed", reason="匹配失败，无法识别")
```

**`features/import_flow/steps/scrape.py`**

- `_step_scrape()` 中调用 `MatchEngine.match()` 替代旧的 Provider搜索+置信度计算
- `_step_validate()` 直接读取 `match_level` 判断流向，不再调用 `confidence_engine.get_confidence_level()`

**`scraper/metadata_scrape_flow.py`**

- `scrape_metadata()` 简化为单一流程，不再有 `provider_first` / `ai_only` 模式分支
- 第一级和第二级匹配后，统一调用维度映射 + AI补齐

**`api/tmdb_handlers.py`**

- `_scrape_preview()` 不再并发双模式，改为单一三级匹配路径
- 返回结构从 `modes_result + recommendation` 改为 `match_result + trace`

#### 6.5 `_scrape_preview` API 兼容性

**当前 API 响应结构**：

```json
{
  "modes": {
    "provider_first": { "confidence": 0.85, "confidence_detail": {...}, "dimensions": {...} },
    "ai_only": { "confidence": 0.72, "confidence_detail": {...}, "dimensions": {...} }
  },
  "recommendation": { "mode": "provider_first", "reason": "..." }
}
```

**新 API 响应结构**：

```json
{
  "match_result": {
    "match_level": "AUTO_PASS",
    "provider_id": 27205,
    "provider_title": "Inception",
    "match_tier": 1,
    "concerns": [],
    "trace": {
      "tier1": { "search_query": "Inception", "year": 2010, "match_level": "L1", "matched": true },
      "tier2": null,
      "tier3": null
    }
  },
  "dimensions": { "media_type": "movie", ... },
  "import_path": "/mnt/sdb/电影/Inception (2010)/..."
}
```

**API 版本策略**：不使用版本号，直接替换响应结构。因为该 API 目前仅供前端模拟运行使用（无第三方消费者），前端同步改造即可。

#### 6.3 DB 改造

```sql
-- 新增字段
ALTER TABLE tasks ADD COLUMN match_level TEXT DEFAULT NULL;       -- AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM
ALTER TABLE tasks ADD COLUMN match_concerns TEXT DEFAULT NULL;    -- JSON array of MatchConcern
ALTER TABLE tasks ADD COLUMN match_trace TEXT DEFAULT NULL;       -- JSON 匹配路径追踪

-- scrape_confidence 字段保留，不删除，兼容历史数据
```

**历史数据展示策略**：

| 任务状态 | scrape_confidence | match_level | 前端展示 |
|----------|-------------------|-------------|----------|
| 新任务（重构后） | NULL | AUTO_PASS | "✅ 自动匹配" |
| 新任务（重构后） | NULL | NEEDS_CONFIRM | "⚠️ 需确认" + 疑虑原因 |
| 历史任务（旧引擎） | 0.85 | NULL | "✅ 已入库"（不展示置信度数值） |
| 历史任务（旧引擎） | 0.45 | NULL | 按当前状态展示（SUCCESS/FAILED 等） |

**前端兼容逻辑**：

```javascript
function getMatchLabel(task) {
    const level = task.match_level;
    if (level === "AUTO_PASS") return { icon: "✅", text: "自动匹配" };
    if (level === "CONTEXT_PASS") return { icon: "🤖", text: "AI辅助匹配" };
    if (level === "NEEDS_CONFIRM") return { icon: "⚠️", text: "需确认" };
    // 历史数据：无 match_level 但有 scrape_confidence
    if (task.status === "SUCCESS" && !level) return { icon: "✅", text: "已入库" };
    return { icon: "", text: "" };
}
```

**不迁移旧数据**的理由：
- 旧 `scrape_confidence` 是连续值，无法准确映射到离散的 `AUTO_PASS/CONTEXT_PASS/NEEDS_CONFIRM`
- 历史任务已经是终态（SUCCESS/FAILED），不需要再改变展示方式
- 前端对终态任务不展示匹配级别，只展示结果状态（已入库/失败）

**`scrape_confidence` 字段最终命运**：
- 阶段 1-3：保留，新任务不写入
- 阶段 4：评估是否删除字段（如果所有历史任务已处理完，可在后续版本删除）

#### 6.4 配置迁移

```python
def _migrate_confidence_v2_to_v3(config):
    """移除 confidence 区块，迁移 ai_only 模式，保留 manual_review"""
    config.pop("confidence", None)
    config.get("llm", {}).pop("confidence_threshold", None)

    # 迁移 scrape_mode
    metadata = config.get("metadata", {})
    if metadata.get("scrape_mode") in ("ai_only", "hybrid"):
        metadata["scrape_mode"] = "provider_first"

    return config
```

### 七、文件级变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `features/scraping/match_engine.py` | **新增** | 三级匹配引擎核心 |
| `features/scraping/match_models.py` | **新增** | 匹配数据模型 |
| `features/scraping/confidence_engine.py` | **重写** | 变为薄 re-export 兼容层，最终移除 |
| `features/scraping/confidence_models.py` | **简化** | 保留 `CleanResult`，移除 R/aggregate/gate 相关 |
| `scraper/title_matcher.py` | **保留** | L1-L7 匹配逻辑继续使用，第一级依赖它 |
| `scraper/filename_cleaner.py` | **保留** | 不变 |
| `scraper/metadata_scrape_flow.py` | **改造** | 简化为单一三级匹配流程 |
| `features/scraping/metadata_scraper.py` | **改造** | 适配 MatchEngine |
| `features/import_flow/services/review.py` | **重写** | 基于 match_level 判断，不再依赖置信度数值 |
| `features/import_flow/steps/scrape.py` | **改造** | 使用 MatchEngine，写入 match_level/match_concerns |
| `api/tmdb_handlers.py` | **改造** | `_scrape_preview` 简化 |
| `core/config_loader.py` | **改造** | 移除 confidence 默认值设置 |
| `core/config_migrations.py` | **新增** | `v2_to_v3` 迁移 |
| `core/config_validator.py` | **简化** | 移除 confidence 参数校验 |
| `core/db/constants.py` | **改造** | 新增 match_level/match_concerns/match_trace 字段 |
| `core/db/task_repo.py` | **改造** | 查询和写入新字段 |
| `webui/js/cinema-confidence.js` | **移除** | 置信度配置面板 |
| `webui/js/confidence-detail.js` | **移除** → 替换为匹配路径展示 | 新 JS 文件或合并到 cinema-tasks.js |
| `webui/css/cinema-confidence.css` | **移除** | |
| `webui/css/cinema-confidence-dimensions.css` | **移除** | |
| `webui/js/cinema-config.js` | **改造** | 移除置信度相关函数，模拟运行改为三级匹配展示 |
| `webui/js/cinema-tasks.js` | **改造** | 卡片展示 match_level + concerns |
| `webui/js/cinema-app.js` | **改造** | 移除置信度相关事件绑定 |
| `webui/js/dimensions.js` | **改造** | 移除维度来源信任配置 UI |

### 八、测试策略

本次重构改动面大，测试必须先行且贯穿每个阶段。按项目测试规范（`docs/standards/testing.md`），分三层覆盖。

#### 8.1 现有测试资产盘点

重构前必须理解的现有测试文件，哪些保留、哪些需要重写、哪些需要移除：

| 测试文件 | 类型 | 处理方式 |
|----------|------|----------|
| `tests/test_confidence_engine.py` | 单元测试 | **重写** — `TestCalcR`、`TestAggregate` 移除；`TestFilenameCleaner`、`TestTitleMatcher` 保留迁移 |
| `tests/test_scrape_mode.py` | 单元测试 | **重写** — 模式分派逻辑完全改变，维度完整性检查保留 |
| `tests/test_feature_task_review.py` | 单元测试 | **改造** — 确认/重新分类的 API 测试保留，断言逻辑从置信度改为 match_level |
| `tests/test_classify_preview.py` | 单元+集成 | **保留** — 分类预览逻辑不变 |
| `tests/test_confidence_v2_ui.py` | UI 测试 | **移除** — 置信度配置面板整体移除 |
| `tests/test_confidence_ui.py` | UI 测试 | **移除** — 置信度配置 UI 不再存在 |
| `tests/test_confidence_config_ui.py` | UI 测试 | **移除** — 置信度保存/来源配置 UI 不再存在 |
| `tests/test_scrape_ui.py` | UI 测试 | **改造** — 移除置信度相关测试，保留 Provider 配置/刮削预览测试 |
| `tests/test_scrape_preview_ui.py` | UI 测试 | **重写** — 模拟运行从双模式对比改为三级匹配展示 |
| `tests/test_architecture_guards.py` | 护栏测试 | **保留** — 验证旧入口不被重新引用 |

#### 8.2 新增单元测试

##### 8.2.1 `tests/test_match_engine.py` — 核心匹配引擎测试

这是本次重构最重要的新测试文件，覆盖三级匹配全部逻辑。

**第一级精确匹配测试（TestTier1ExactMatch）**

| 测试用例 | 输入 | 期望输出 |
|----------|------|----------|
| 英文名+年份精确匹配 | `clean("Inception.2010.1080p.mkv")` → title="Inception", year=2010 | `match_level=AUTO_PASS`, provider_id=对应TMDB ID |
| 中文名+年份精确匹配 | `clean("流浪地球.2019.mkv")` → cjk_title="流浪地球", year=2019 | `match_level=AUTO_PASS` |
| 无年份唯一精确匹配 | title="Inception", year=None, TMDB 只返回 1 条精确 | `match_level=AUTO_PASS` |
| 无年份多同名 | title="Spider-Man", year=None, TMDB 返回多条 | `match_level=NEEDS_CONFIRM`, concerns 含 `NO_YEAR_MULTI_MATCH` |
| 年份不匹配 | title="Inception", year=2020, TMDB 只有 2010 版 | `match_level=NEEDS_CONFIRM`, concerns 含 `YEAR_MISMATCH` |
| 无精确匹配 | title="AbcdefgRandomMovie", TMDB 返回空或全部模糊 | 进入第二级 |
| 季集+标题精确 | title="Breaking Bad", season=1, TMDB 精确匹配 | `match_level=AUTO_PASS` |
| CJK标题优先匹配中文TMDB | cjk_title="功夫", clean_title="Kung Fu", year=2004 | TMDB 中文标题精确匹配优先 |
| TMDB搜索返回多条但只有一条精确 | title="Dune", year=2021, 多条Dune但只有一条年份=2021 | `match_level=AUTO_PASS` |
| Provider 搜索异常/超时 | Provider.search() 抛异常 | 进入第二级，不直接失败 |

**疑虑原因生成测试（TestConcernGeneration）**

| 测试用例 | 场景 | 期望 concern.code |
|----------|------|-------------------|
| 无年份多同名 | title 精确但 year=None 且结果 > 1 | `NO_YEAR_MULTI_MATCH` |
| 年份不匹配 | title 精确但 year ≠ TMDB year | `YEAR_MISMATCH` |
| 标题模糊匹配 | title 相似但非精确 | `FUZZY_TITLE` |
| Provider 无结果 | Provider 搜索返回空 | `NO_PROVIDER_RESULT` |
| 标题缺失 | 清洗后 title 为空 | `NO_TITLE` |
| 多信息冲突 | 文件名/目录信息矛盾 | `CONFLICTING_INFO` |
| 多种疑虑叠加 | 无年份+模糊标题 | concerns 列表包含多个 code |

**第二级上下文辅助测试（TestTier2ContextMatch）**

| 测试用例 | 输入 | 期望输出 |
|----------|------|----------|
| 文件夹名匹配剧名 | 上级目录 "Breaking Bad/", 同级文件含 S01E* | `match_level=CONTEXT_PASS` 或 `AUTO_PASS` |
| 同级文件名辅助 | 同级有 "Inception.2010.1080p.mkv" | AI 能利用上下文确认 |
| AI 确定匹配 | AI 返回确定结果 | `match_level=CONTEXT_PASS` |
| AI 不确定 | AI 返回不确定 | `match_level=NEEDS_CONFIRM`, concerns 含 `AI_UNCERTAIN` |
| AI 调用失败 | LLM 超时/异常 | 降级为第三级，不直接失败 |
| 上下文为空（根目录文件） | 无上级文件夹信息 | 仅依赖 Provider 候选，不崩溃 |

**第三级用户确认测试（TestTier3UserConfirm）**

| 测试用例 | 输入 | 期望输出 |
|----------|------|----------|
| 返回候选列表 | 前两级都未匹配 | `match_level=NEEDS_CONFIRM`, candidates 非空 |
| 候选按热度排序 | TMDB 返回多条 | candidates 按 popularity 降序 |
| 疑虑原因完整 | 各种未匹配场景 | 每条 concern 有 code + message + detail |
| 完全无法搜索 | Provider 不可用 | `match_level=NEEDS_CONFIRM`, concerns 含 `NO_PROVIDER_RESULT` |

**端到端匹配路径测试（TestMatchEngineEndToEnd）**

| 测试用例 | 文件名 | 期望匹配级别 | 期望命中的级别 |
|----------|--------|-------------|---------------|
| 典型电影第一级通过 | `Inception.2010.1080p.BluRay.mkv` | AUTO_PASS | 第一级 |
| 典型剧集第一级通过 | `Breaking.Bad.S01E01.720p.mkv` | AUTO_PASS | 第一级 |
| 边缘案例第二级通过 | `The.Matrix.1080p.mkv`（无年份） | CONTEXT_PASS | 第二级 |
| 疑难案例第三级 | `Movie.2023.mkv`（标题太泛） | NEEDS_CONFIRM | 第三级 |

##### 8.2.2 `tests/test_review_decision_v2.py` — 审核决策测试

**ReviewDecisionService 逻辑测试**

| 测试用例 | 输入 | 期望 action |
|----------|------|-------------|
| AUTO_PASS | match_level="AUTO_PASS" | continue |
| CONTEXT_PASS | match_level="CONTEXT_PASS" | continue |
| NEEDS_CONFIRM 有疑虑 | match_level="NEEDS_CONFIRM", concerns=[{code:"NO_YEAR_MULTI_MATCH",...}] | confirm, reason 包含疑虑文案 |
| NEEDS_CONFIRM 无疑虑 | match_level="NEEDS_CONFIRM", concerns=[] | confirm, reason="需要人工确认" |
| 无匹配结果 | match_level=None | failed |
| 必填字段缺失 | title_cn/title_en 都为空 | confirm（缺失字段检查不变） |
| 年份缺失有标题 | title_cn="流浪地球", year=None | continue（年份缺失可接受） |

##### 8.2.3 `tests/test_config_migration_v3.py` — 配置迁移测试

| 测试用例 | 输入 | 期望输出 |
|----------|------|----------|
| v2 配置完整迁移 | 含 confidence 区块 + llm.confidence_threshold | 移除 confidence，移除 confidence_threshold，保留其他 |
| v1 配置先迁移到 v2 再到 v3 | 旧格式扁平配置 | 连续迁移无报错 |
| 空 confidence 迁移 | 无 confidence 区块 | 无报错，配置不变 |
| manual_review 保留 | 含 manual_review.enabled=false | manual_review 不受影响 |

##### 8.2.4 保留测试的迁移

| 源文件 | 迁移到 | 内容 |
|--------|--------|------|
| `test_confidence_engine.py` → `TestFilenameCleaner` | 新 `test_match_engine.py` 或独立 `test_filename_cleaner.py` | 保持现有测试用例不变 |
| `test_confidence_engine.py` → `TestTitleMatcher` | 新 `test_match_engine.py` 或独立 `test_title_matcher.py` | 保持现有测试用例不变 |
| `test_scrape_mode.py` → `TestCheckDimensionCompleteness` | 新 `test_dimension_completeness.py` | 维度完整性检查逻辑保留 |

#### 8.3 集成测试

##### 8.3.1 `tests/test_match_pipeline_integration.py` — 匹配+刮削流水线集成

**不 mock Provider，使用真实 TMDB API 或录制响应（按项目现有模式）。**

| 测试用例 | 端到端流程 | 验证点 |
|----------|-----------|--------|
| 完整电影匹配入库 | 文件名 → 清洗 → 匹配 → 维度映射 → 分类 → 入库路径 | match_level=AUTO_PASS, 入库路径正确 |
| 完整剧集匹配入库 | 剧集文件名 → 匹配 → 维度映射 → 入库 | season/episode 正确传递 |
| 匹配到确认流程 | 文件名匹配失败 → AWAIT_REVIEW → 用户确认 → 入库 | confirm API 正常工作 |
| 维度补齐触发 | TMDB 无分级信息 → AI 补齐 restricted_level | AI 被调用，维度值被写入 |
| 维度补齐不触发 | TMDB 分级信息完整 | AI 不被调用 |
| 重新分类 | 确认后修改维度 → reclassify → 入库路径变更 | reclassify API 正常工作 |
| DB 新字段读写 | 匹配后读取 task 的 match_level/match_concerns/match_trace | 字段值正确持久化 |

##### 8.3.2 `tests/test_scrape_preview_api.py` — 刮削预览 API 集成

| 测试用例 | API 调用 | 验证点 |
|----------|----------|--------|
| 预览返回三级路径 | POST /api/scrape/preview | 返回 match_level + trace + concerns |
| 预览不含置信度 | POST /api/scrape/preview | 响应中无 confidence/confidence_detail 字段 |
| 预览含维度映射 | POST /api/scrape/preview | dimensions 来自 TMDB 映射 |
| 文件名为空 | POST /api/scrape/preview {filename: ""} | 返回 400 错误 |

##### 8.3.3 `tests/test_task_api_match_level.py` — 任务 API 字段兼容性

| 测试用例 | 操作 | 验证点 |
|----------|------|--------|
| 历史任务兼容 | 读取旧任务（有 scrape_confidence 无 match_level） | 前端展示不崩溃 |
| 新任务字段 | 创建新刮削任务 | match_level/match_concerns/match_trace 写入正确 |
| 任务列表过滤 | AWAIT_REVIEW 过滤 | 状态过滤逻辑不变 |

#### 8.4 回归测试

##### 8.4.1 不变模块的回归验证

以下模块**完全不改动**，每次阶段完成后必须验证其行为不变：

| 模块 | 验证方式 |
|------|----------|
| 文件名清洗器（FilenameCleaner） | 现有 `TestFilenameCleaner` 用例全部通过 |
| 标题匹配器（TitleMatcher L1-L7） | 现有 `TestTitleMatcher` 用例全部通过 |
| 维度映射（DimensionManager） | `test_scrape_mode.py` 中维度完整性用例通过 |
| 分辨率检测（FileAnalyzer） | ffprobe 分辨率分级结果不变 |
| 维度 CRUD（DimensionsService） | 维度启用/禁用/更新 API 不变 |
| 去重规则（DedupRules） | 质量比较逻辑不变 |
| 文件操作（FileOperations） | 入库文件名模板渲染不变 |
| 入库流程（ConfirmMixin） | 确认入库文件操作不变 |

##### 8.4.2 全量回归测试矩阵

每个阶段完成后执行：

```bash
# 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests

# 非 UI 测试（核心回归）
python -m pytest tests/ \
  --ignore=tests/test_*_ui.py \
  --ignore=tests/test_frontend_*.py \
  --ignore=tests/test_scrape_ui.py \
  -v

# 架构护栏
python -m pytest tests/test_architecture_guards.py tests/test_feature_entrypoints.py -v
```

##### 8.4.3 前端回归检查点

阶段 3（前端适配）完成后手动或 Playwright 验证：

| 检查点 | 验证方式 |
|--------|----------|
| 配置页无置信度区块 | 页面无 `[data-section="confidence"]` 元素 |
| 配置页模拟运行正常 | 输入文件名 → 展示三级匹配路径 |
| 任务卡片无置信度数值 | 无 "置信度 0.XX" 文本 |
| 任务卡片有匹配状态标签 | 有 "自动匹配" / "AI辅助匹配" / "需确认" 标签 |
| 待确认任务有疑虑原因 | 卡片上有疑虑原因文案 |
| 维度配置页签无来源信任 | 无 trusted/source_confidence/veto 输入 |
| 旧版 tasks.js 页面不崩溃 | 旧版任务表格仍可展示（兼容旧数据） |

##### 8.4.4 边界案例回归清单

以下是历史上容易出问题的边界场景，必须每次回归都跑：

| 场景 | 文件名示例 | 期望行为 |
|------|-----------|----------|
| 多年份文件名 | `Movie.(2023).(2024).mkv` | year_suspect 处理正确 |
| CJK 混合标题 | `流浪地球 The Wandering Earth.2019.mkv` | cjk_title 和 clean_title 分离正确 |
| 特殊字符标题 | `Spider-Man: Across the Spider-Verse.2023.mkv` | 冒号/连字符处理正确 |
| 完全无意义文件名 | `video.mkv` | NEEDS_CONFIRM + NO_TITLE |
| 空文件名 | `""` | 400 错误 |
| 超长文件名 | 200+ 字符 | 不崩溃 |
| Unicode 文件名 | `七人の侍.1954.mkv` | CJK 标题正确提取 |
| 多季集标记 | `Show.S01E01E02E03.mkv` | 季集正确提取 |
| 制作组标签混淆 | `[SubGroup] Show Name - 01 [1080p].mkv` | 制作组被正确移除 |

#### 8.5 测试执行计划与各阶段对应关系

##### 阶段 1（后端核心替换）

**先写测试，再写实现（TDD）**：

```
1. 编写 test_match_engine.py 中 TestTier1ExactMatch 全部用例（RED）
2. 编写 test_match_engine.py 中 TestConcernGeneration 全部用例（RED）
3. 编写 test_review_decision_v2.py 全部用例（RED）
4. 编写 test_config_migration_v3.py 全部用例（RED）
5. 迁移 TestFilenameCleaner 和 TestTitleMatcher 到新文件（GREEN - 应直接通过）
6. 实现 match_engine.py tier1（使 TestTier1ExactMatch 变 GREEN）
7. 实现 match_models.py（使 TestConcernGeneration 变 GREEN）
8. 改造 review.py（使 test_review_decision_v2.py 变 GREEN）
9. 实现配置迁移（使 test_config_migration_v3.py 变 GREEN）
10. 运行全量回归 → 所有非 UI 测试通过
```

**阶段 1 退出测试标准**：
- `test_match_engine.py` 全部 GREEN
- `test_review_decision_v2.py` 全部 GREEN
- `test_config_migration_v3.py` 全部 GREEN
- 迁移的 `TestFilenameCleaner` / `TestTitleMatcher` GREEN
- `test_feature_task_review.py` 改造后 GREEN
- `test_architecture_guards.py` GREEN
- 现有 `test_scrape_mode.py` 中维度完整性相关 GREEN

##### 阶段 2（上下文辅助匹配）

```
1. 编写 test_match_engine.py 中 TestTier2ContextMatch 全部用例（RED）
2. 编写 test_match_engine.py 中 TestTier3UserConfirm 全部用例（RED）
3. 编写 test_match_engine.py 中 TestMatchEngineEndToEnd 全部用例（RED）
4. 实现 tier2 + tier3（使测试变 GREEN）
5. 编写 test_match_pipeline_integration.py 集成测试（GREEN）
6. 编写 test_scrape_preview_api.py 集成测试（GREEN）
7. 运行全量回归 → 所有非 UI 测试通过
```

**阶段 2 退出测试标准**：
- `test_match_engine.py` 全部 GREEN（含 tier1+tier2+tier3+端到端）
- `test_match_pipeline_integration.py` 全部 GREEN
- `test_scrape_preview_api.py` 全部 GREEN
- 边界案例回归清单全部通过

##### 阶段 3（前端适配）

```
1. 移除 test_confidence_v2_ui.py、test_confidence_ui.py、test_confidence_config_ui.py
2. 重写 test_scrape_preview_ui.py（三级匹配展示）
3. 改造 test_scrape_ui.py（移除置信度相关断言）
4. 编写 test_task_card_match_level_ui.py（前端卡片展示测试）
5. 执行前端回归检查点
6. 运行全量回归（含 UI 测试）
```

**阶段 3 退出测试标准**：
- 前端无置信度相关测试失败
- 新 UI 测试全部 GREEN
- 前端回归检查点全部通过

##### 阶段 4（清理）

```
1. 确认移除旧测试后无引用断链
2. 运行全量回归 → 全部通过
3. 最终回归：编译检查 + 非 UI 全量 + UI 全量 + 架构护栏
```

**阶段 4 退出测试标准**：
- 全部测试 GREEN
- 无遗留的 `test_confidence_*` 文件（已移除或重写）
- 无遗留的置信度公式计算代码引用

### 九、实施阶段

#### 阶段 1：后端核心替换（保持前端兼容）

目标：替换匹配引擎，但前端暂时兼容旧数据格式

**测试先行：**
- [ ] 编写 `tests/test_match_engine.py` — TestTier1ExactMatch（10 个用例）
- [ ] 编写 `tests/test_match_engine.py` — TestConcernGeneration（7 个用例）
- [ ] 编写 `tests/test_review_decision_v2.py` — ReviewDecisionService（7 个用例）
- [ ] 编写 `tests/test_config_migration_v3.py` — 配置迁移（4 个用例）
- [ ] 迁移 TestFilenameCleaner / TestTitleMatcher 到新文件（保持现有用例）

**实现：**
- [ ] 创建 `match_engine.py` 和 `match_models.py`
- [ ] 实现 `_tier1_exact_match()`（复用现有 TitleMatcher）
- [ ] 实现 `_tier3_user_confirm()`（收集候选+生成疑虑原因）
- [ ] 改造 `review.py` 基于 `match_level` 判断
- [ ] 改造 `scrape.py` 使用 MatchEngine
- [ ] DB 新增字段 + 兼容层
- [ ] 配置迁移 v2→v3

**验证：**
- [ ] 新测试全部 GREEN
- [ ] `test_feature_task_review.py` 改造后 GREEN
- [ ] `test_architecture_guards.py` GREEN
- [ ] 全量回归通过

**阶段退出标准**：新匹配引擎工作正常，任务能正确进入 AUTO_PASS 或 NEEDS_CONFIRM 状态

#### 阶段 2：上下文辅助匹配（第二级）

目标：实现 AI 辅助判断

**测试先行：**
- [ ] 编写 `tests/test_match_engine.py` — TestTier2ContextMatch（6 个用例）
- [ ] 编写 `tests/test_match_engine.py` — TestTier3UserConfirm（4 个用例）
- [ ] 编写 `tests/test_match_engine.py` — TestMatchEngineEndToEnd（4 个用例）
- [ ] 编写 `tests/test_match_pipeline_integration.py`（7 个用例）
- [ ] 编写 `tests/test_scrape_preview_api.py`（4 个用例）

**实现：**
- [ ] 实现 `_tier2_context_match()`
- [ ] 收集同级目录文件名 + 上级文件夹名
- [ ] 构建 AI 辅助判断 prompt（候选列表 + 上下文 → 选出正确结果或返回不确定）
- [ ] 在 `metadata_scrape_flow.py` 中集成

**验证：**
- [ ] 新测试全部 GREEN
- [ ] 边界案例回归清单全部通过
- [ ] 全量回归通过

**阶段退出标准**：第二级匹配能在目录上下文辅助下正确判断大部分边缘案例

#### 阶段 3：前端适配

目标：前端全面适配新匹配模型

**测试先行：**
- [ ] 移除 `test_confidence_v2_ui.py`、`test_confidence_ui.py`、`test_confidence_config_ui.py`
- [ ] 重写 `test_scrape_preview_ui.py`（三级匹配展示）
- [ ] 改造 `test_scrape_ui.py`（移除置信度相关断言）
- [ ] 编写 `test_task_card_match_level_ui.py`（卡片匹配状态测试）

**实现：**
- [ ] 移除置信度配置面板（JS + CSS）
- [ ] 改造模拟运行为三级匹配展示
- [ ] 改造任务卡片展示 match_level + concerns
- [ ] 替换置信度详情弹窗为匹配路径展示
- [ ] 改造维度配置页签（移除来源信任配置）
- [ ] 移除配置页中的置信度区块

**验证：**
- [ ] 新 UI 测试 GREEN
- [ ] 前端回归检查点全部通过
- [ ] 全量回归（含 UI）通过

**阶段退出标准**：前端不再展示任何置信度数值，全部改为状态标签+疑虑原因

#### 阶段 4：清理和移除

目标：移除所有旧代码

- [ ] 将 `confidence_engine.py` 改为 re-export 兼容层（如果还有其他引用）
- [ ] 移除 `DEFAULT_CONFIDENCE_CONFIG` 中不再需要的参数
- [ ] 移除 `_calc_R()`、`_aggregate()` 等不再使用的函数
- [ ] 移除旧版 `tasks.js` 中的置信度相关代码
- [ ] 移除旧测试文件中不再需要的测试类（`TestCalcR`、`TestAggregate`）
- [ ] 更新 API 文档
- [ ] 更新用户文档

**最终验证：**
- [ ] 编译检查通过
- [ ] `python -m pytest tests/` 全部 GREEN（含 UI）
- [ ] `test_architecture_guards.py` + `test_feature_entrypoints.py` GREEN
- [ ] 无遗留置信度公式计算代码

**阶段退出标准**：代码库中无任何置信度公式计算逻辑

## 决策理由

### 为什么选择离散三级而非优化现有公式

1. **用户认知**：Plex/Jellyfin/Kodi/Emby/TMM 全部使用离散判断（匹配/不匹配），没有用连续概率值
2. **实际效果**：当前 85%+ 的文件在第一级就能精确匹配，公式化只在边缘场景有意义，而边缘场景用上下文辅助更有效
3. **维护成本**：三级匹配的代码量预计是现有置信度系统的 1/3

### 为什么保留 TitleMatcher 的 L1-L7 体系

L1-L7 本质上是「精确/模糊/不匹配」的细分，第一级匹配只关心 L1（精确+年份一致），逻辑清晰，不需要改动。只是不再用 T 值做乘法，而是用 level 做离散判断。

#### TitleMatcher 与配置解耦方案

当前 `TitleMatcher` 的 `match_standard()` 方法返回 `MatchResult(level, T, similarity, year_match, reason)`，其中 T 值从 `DEFAULT_CONFIDENCE_CONFIG` 读取：

```python
# 当前实现（title_matcher.py）
T_map = {
    "L1": config.get("title_exact_with_year", 1.0),
    "L2": config.get("title_exact_with_season", 0.9),
    "L3": config.get("title_exact_no_year", 0.7),
    "L4": config.get("title_exact_year_mismatch", 0.4),
}
```

**改造方案**：TitleMatcher 不再读取配置，改为内部硬编码默认 T 值，并在返回结果中只暴露 `level` 和 `similarity`：

```python
# 改造后（title_matcher.py）
_L1_L7_T_DEFAULTS = {
    "L1": 1.0,   # 精确匹配 + 年份一致
    "L2": 0.9,   # 精确匹配 + 有季号
    "L3": 0.7,   # 精确匹配 + 无年份/季号
    "L4": 0.4,   # 精确匹配 + 年份不匹配
    "L5": None,  # 模糊匹配 + 年份精确 → T = similarity 原值
    "L6": None,  # 模糊匹配 + 无/不匹配年份 → T = similarity * 0.7
    "L7": 0.0,   # 低于最低相似度
}

def match_standard(self, clean_title, search_item, year, season):
    # ... 现有匹配逻辑不变 ...
    T = _L1_L7_T_DEFAULTS.get(level) or (similarity if level == "L5" else similarity * 0.7)
    return MatchResult(level=level, T=T, similarity=similarity, year_match=year_match, reason=reason)
```

**MatchEngine 消费方式**：

```python
# match_engine.py 只关心 level，不关心 T 值的具体数值
def _tier1_exact_match(self, clean_result, providers):
    result = self.title_matcher.match_standard(...)
    if result.level in ("L1", "L2"):
        return MatchResult(level="AUTO_PASS", ...)
    elif result.level == "L3" and year is None:
        # 无年份但精确匹配 → 检查是否唯一
        ...
```

**影响范围**：
- `title_matcher.py`：移除 config 参数依赖，硬编码 T 值默认值
- `confidence_models.py`：移除 `DEFAULT_CONFIDENCE_CONFIG` 中 title 相关的 6 个参数
- `match_engine.py`：只使用 `result.level`，不使用 `result.T` 做乘法
- **T 值保留但不对外暴露**：T 值仍计算（内部可用于排序/调试日志），但不再是匹配决策的乘法因子

### 为什么维度判断和匹配判断解耦

这是最重要的设计决策。匹配判断回答「这个文件是哪部作品」，维度判断回答「这部作品属于什么分类」。两者生命周期不同：
- 匹配在刮削时一次性完成
- 维度可能在用户确认后还会修改（重新分类）
- 分辨率根本不是刮削的事，是文件分析的事

### 为什么 AI 补齐维度需要联网搜索增强

匹配判断不需要联网（因为 Provider 已提供候选列表），但维度补齐可能需要：
- 新上映影片（AI 训练数据不含）
- 限制级分级（依赖各国官方数据，TMDB 可能缺失）
- 地区/语言判断（需要查证制作信息）

## 假设

| 假设 | 状态 | 证据 |
|------|------|------|
| 名字+年份能 99%+ 唯一定位影视作品 | 验证 | TMDB 数据验证，同同年同名的极端案例极少 |
| 现有 TitleMatcher L1 逻辑足够判断精确匹配 | 验证 | 代码审查确认 L1 = 归一化标题相等 + 年份一致 |
| 同级目录文件名和上级文件夹名能提供有效上下文 | 验证 | NAS 用户通常按 影视名/季/ 结构组织文件 |
| AI 不联网也能从候选列表中选出正确结果 | 待验证 | 需要在第二级实现后用实际案例验证 |
| 绝大多数用户不需要调整匹配配置 | 验证 | Plex/Jellyfin 均无匹配配置项，用户无抱怨 |

## 风险分析

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| CJK 标题匹配率低于预期 | 第一级精确匹配率下降，更多任务进入第二级 | 中 | 保留 CJK 分离逻辑，中文标题匹配 TMDB 中文标题 |
| 第二级 AI 误判 | 错误匹配自动入库 | 低 | AI 返回置信度，低于阈值时仍进入第三级 |
| 前端改动面大导致回归 | UI 功能缺失 | 中 | 分阶段改造，每阶段独立测试 |
| 配置迁移导致旧数据不兼容 | 历史任务数据展示异常 | 低 | DB 字段新增不删除，兼容层处理旧格式 |
| 移除置信度后部分高级用户不满 | 功能降级感知 | 低 | 疑虑原因体系提供比置信度更透明的决策信息 |
| 新匹配引擎线上故障 | 所有刮削任务失败 | 低 | 见下方回滚策略 |

### 回滚策略

本次重构涉及 ~3367 行代码变更，跨越 9+ 个文件。采用 **Feature Flag + 分阶段移除** 策略确保可回滚：

**阶段 1-3 回滚（双引擎并存期）**：

```yaml
# config.yaml 新增 feature flag（仅开发/调试用，不暴露给前端）
features:
  use_new_match_engine: true   # false → 回退到旧 confidence_engine
```

实现方式：
```python
# scrape.py 中的入口
def _step_scrape(self, task):
    if self.config.get("features", {}).get("use_new_match_engine", True):
        result = self.match_engine.match(...)
    else:
        result = self.confidence_engine.calculate(...)
```

- 阶段 1-3 期间，旧的 `confidence_engine.py` **完整保留**，不做 re-export
- 通过 flag 可一键切回旧引擎，回滚成本极低
- 每个阶段完成后确认稳定，下一阶段开始时才考虑移除旧代码

**阶段 4（清理期）回滚**：

- 阶段 4 才真正删除旧代码（`_calc_R`、`_aggregate` 等）
- 删除前确认：全量测试通过 + 至少一次完整的端到端手动验证
- 如需回滚阶段 4，通过 git revert 恢复被删除的文件
- DB 新增字段（`match_level` 等）不回滚，因为字段是新增的，旧代码忽略即可

**不可回滚的部分**：
- DB schema 变更（新增字段）— 向后兼容，旧代码忽略新字段
- 配置迁移（v2→v3）— 迁移会删除 confidence 区块，但旧代码启动时自动补充默认值

### 基准测试数据集

为验证"第一级精确匹配率 >= 80%"的验收标准，准备以下基准数据集：

**数据集来源**：从用户实际 NAS 文件名中抽样 + 手工补充边界案例

**基准文件**：`tests/fixtures/match_benchmark.jsonl`

```jsonl
{"filename": "Inception.2010.1080p.BluRay.x264.mkv", "expected_title": "Inception", "expected_year": 2010, "expected_level": "AUTO_PASS"}
{"filename": "流浪地球.2019.1080p.WEB-DL.mkv", "expected_title": "The Wandering Earth", "expected_year": 2019, "expected_level": "AUTO_PASS"}
{"filename": "Breaking.Bad.S01E01.720p.BluRay.mkv", "expected_title": "Breaking Bad", "expected_year": 2008, "expected_level": "AUTO_PASS", "expected_season": 1, "expected_episode": 1}
{"filename": "The.Matrix.1999.4K.UHD.BluRay.mkv", "expected_title": "The Matrix", "expected_year": 1999, "expected_level": "AUTO_PASS"}
{"filename": "Movie.mkv", "expected_title": null, "expected_year": null, "expected_level": "NEEDS_CONFIRM"}
{"filename": "[SubGroup] 进击的巨人 S04E01 [1080p].mkv", "expected_title": "Attack on Titan", "expected_year": null, "expected_level": "AUTO_PASS"}
{"filename": "七人の侍.1954.1080p.Criterion.mkv", "expected_title": "Seven Samurai", "expected_year": 1954, "expected_level": "AUTO_PASS"}
{"filename": "Spider-Man.2002.1080p.mkv", "expected_title": "Spider-Man", "expected_year": 2002, "expected_level": "AUTO_PASS"}
{"filename": "Dune.mkv", "expected_title": "Dune", "expected_year": null, "expected_level": "NEEDS_CONFIRM"}
{"filename": "Interstellar.2014.1080p.BluRay.x264-YTS.mkv", "expected_title": "Interstellar", "expected_year": 2014, "expected_level": "AUTO_PASS"}
```

**验证脚本**：`tests/test_match_benchmark.py`

```python
# 对基准数据集中的每条记录，运行完整的匹配引擎
# 输出：通过率 / 各级别分布 / 失败案例详情
# 验收标准：第一级 AUTO_PASS 率 >= 80%
```

目标收集 **100+ 条**真实文件名样本，覆盖：
- 50 条典型英文电影/剧集名
- 20 条中文/CJK 文件名
- 10 条无年份文件名
- 10 条模糊/边界案例
- 10 条极端/异常文件名

## 十、验收标准

### 功能验收

1. **第一级精确匹配率 >= 80%** — 对现有文件批量测试，至少 80% 的文件在第一级自动通过
2. **配置页无置信度相关控件** — 配置页面不再展示任何数值阈值、R值公式、维度来源信任配置
3. **任务卡片展示匹配状态** — 使用状态标签（自动匹配/AI辅助/需确认）替代置信度数值
4. **用户确认时展示疑虑原因** — 每个待确认任务至少有一个疑虑原因标签
5. **模拟运行展示三级路径** — 清晰展示每级的匹配过程和结果
6. **维度映射不受影响** — TMDB genre_ids → 维度的确定性映射完全不变
7. **分辨率检测不受影响** — ffprobe 分辨率检测逻辑完全不变

### 测试验收

8. **新增测试全部通过** — `test_match_engine.py`、`test_review_decision_v2.py`、`test_config_migration_v3.py`、`test_match_pipeline_integration.py`、`test_scrape_preview_api.py` 全部 GREEN
9. **现有测试无回归** — 编译检查 + 非 UI 全量测试 + 架构护栏全部通过
10. **测试覆盖三级匹配全路径** — 每一级的匹配成功和匹配失败都有对应测试用例
11. **疑虑原因体系完整覆盖** — 7 种 concern.code 都有对应测试用例
12. **边界案例回归清单通过** — 9 个历史边界场景全部正确处理
13. **前端回归检查点通过** — 7 个前端检查点全部满足
14. **无遗留旧代码引用** — `test_architecture_guards.py` 确认旧入口不被引用
15. **测试先行原则** — 每个阶段的测试在实现之前编写，提交记录可追溯 TDD 流程

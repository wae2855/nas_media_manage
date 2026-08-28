
# 刮削与 AI 配置界面重设计 —— 方案 v6

> 核心原则：**用户只需填 URL 和 Key，其他自动搞定**
> AI辅助：改为用户输入模型URL+模型ID+API Key，不做厂商映射
> AI联网搜索增强：新增开关功能，仅用于维度补全
> 维度信任配置：拆分为"信任AI辅助映射"和"信任AI联网搜索"两个独立开关
> 维度确认流程：三级（Provider映射 → AI辅助分析 → AI联网搜索增强）
> AI提示词管理：高级选项中可维护各场景提示词
> 模拟刮削：展示每个维度的来源路径
> 任务卡片：点击可查看刮削过程

---

## 0. 开发状态（2026-06-13）

**Phase 1 ✅**：配置结构 + DB 变更 —— 已完成
**Phase 2 ✅**：UI 重写 —— 已完成（前端控件齐全，后端数据源待连通）
**Phase 3 ⚠️**：刮削逻辑切换 —— 部分完成，待 Hot Fix 修复

**待修复 P0/P1 问题**：
- HF-1：llm_scraper.py 仍读旧 llm 字段 → 新配置不生效
- HF-2：confirm_reason 未写入 DB → 重启后丢失
- HF-3：dim_sources 未构造和写入 DB → 任务卡片来源展示为空
- HF-4：validate_config 强制要求旧 llm.api_key → 新用户报错

**待实现 P2/P3**：
- trust_ai_assist/trust_ai_search 判断逻辑接入 review/match_engine
- 第二级匹配改为"AI 建议关键词 → 循环回第一级"（可选，当前 AI 选候选已比旧版强）
- 正式维度三级来源逻辑（T3.4，已知 HF-3 为临时兜底）
- ai_only 残留代码清理
- 迁移幂等性增强

---

## 1. 完整刮削流程

### 1.1 流程总览

```
文件名输入
  │
  ├─ Step 1: 标题清洗（可能循环）
  │   ├─ 正则规则清洗 → clean_title / cjk_title / year / season / episode
  │   ├─ 年份存疑时 → AI辅助模型清洗
  │   └─ 输出：清洗后的标题+年份
  │
  ├─ Step 2: 匹配路径（三级匹配引擎，可能循环回 Step 1）
  │   │
  │   ├─ 第一级：Provider 精确匹配
  │   │   ├─ L1/L2 唯一精确匹配 → AUTO_PASS ✅
  │   │   └─ 无精确匹配 → 进入第二级
  │   │
  │   ├─ 第二级：上下文辅助匹配（AI辅助模型）
  │   │   ├─ AI建议新关键词 → 回到第一级重新搜索
  │   │   ├─ 精确匹配成功 → AUTO_PASS ✅
  │   │   └─ 仍无精确匹配 → 取排名第一 + 疑虑标记 → 第三级
  │   │
  │   └─ 第三级：用户确认
  │       └─ NEEDS_CONFIRM ⚠️
  │
  ├─ Step 3: 元数据刮削 + 维度确认流程（三级）
  │   │
  │   ├─ 维度来源第一级：Provider 直接映射
  │   │   ├─ 有确定性映射规则 → 直接取值，百分百信任 ✅
  │   │   │   例：genre_ids=99 → documentary=true
  │   │   │   例：origin_country=["JP"] → region=jp
  │   │   │   例：original_language="ja" → origin_lang=ja
  │   │   └─ 无映射或映射失败 → 进入第二级
  │   │
  │   ├─ 维度来源第二级：AI辅助模型分析（不需要联网搜索）
  │   │   ├─ Provider有数据但映射复杂 → AI辅助模型分析判断
  │   │   │   例：restricted_level — TMDB有release_dates但各国分级不同，
  │   │   │       AI辅助模型将 MPAA/BBFC/中国分级 映射到统一的 0-6/7-12/13-16/17+
  │   │   │   例：media_type — TMDB无直接字段，AI辅助模型根据标题+季集判断
  │   │   │   例：broad_genre — TMDB genre_ids映射优先级复杂，AI辅助模型可替代
  │   │   ├─ AI辅助模型给出结果 → 标记来源为"ai_assist"
  │   │   └─ AI辅助模型也无法判断 → 进入第三级
  │   │
  │   └─ 维度来源第三级：AI联网搜索增强（需开关启用）
  │       ├─ 基于清洗后的文件名+已有信息 → AI联网搜索获取
  │       ├─ AI联网搜索增强给出结果 → 标记来源为"ai_search"
  │       └─ 仍无法获取 → 维度值为空
  │
  ├─ Step 4: 维度完整性判定
  │   ├─ 所有维度有值且可信 → 自动入库 ✅
  │   ├─ 有维度值来自AI且不信任AI → 待确认 ⚠️
  │   └─ 有维度值为空 → 待确认 ⚠️
  │
  └─ Step 5: 入库
      ├─ 自动入库 → 移动文件 + 更新媒体库
      └─ 待确认 → 进入人工复核队列（带 confirm_reason）
```

### 1.2 维度确认流程详解

每个维度的值来源按优先级逐级尝试：

```
维度: restricted_level（限制级分类）
  │
  ├─ 第一级: Provider映射
  │   TMDB release_dates → certification
  │   问题: 各国分级体系不同
  │   US: G/PG/PG-13/R/NC-17
  │   UK: U/PG/12A/12/15/18
  │   CN: 普遍级/辅导级/限制级
  │   → 映射规则复杂，无法用简单规则覆盖
  │   → 降级到第二级
  │
  ├─ 第二级: AI辅助模型分析
  │   输入: TMDB release_dates 原始数据 + 影片标题 + 简介
  │   输出: 映射到统一的 0-6/7-12/13-16/17+
  │   → 标记来源: ai_assist
  │
  └─ 第三级: AI联网搜索增强（如果第二级也无法判断）
      输入: 影片标题 + 年份
      输出: 联网搜索官方分级信息
      → 标记来源: ai_search
```

```
维度: media_type（影视类型）
  │
  ├─ 第一级: Provider映射
  │   TMDB 搜索端点区分 /search/movie 和 /search/tv
  │   搜索结果本身不包含 media_type 字段
  │   → 代码根据调用的搜索端点硬编码: movie / tv
  │   → 标记来源: provider
  │
  └─ 第二级: 不需要（搜索端点已100%确定类型）
```

### 1.3 各维度来源分析

| 维度 | Provider映射能力 | 第二级AI辅助 | 第三级AI联网搜索 | 典型来源 |
|---|---|---|---|---|
| media_type | ✅ TMDB搜索端点区分movie/tv，代码硬编码 | 不需要 | 不需要 | provider |
| documentary | ✅ genre_ids=99 | ✅ TMDB漏标时补充 | ✅ 极少数冷门片 | provider |
| restricted_level | ⚠️ 有数据但各国体系不同 | ✅ 将各国分级映射到统一体系 | ✅ TMDB无分级时联网查 | ai_assist/ai_search |
| animation | ✅ genre_ids=16 | ✅ TMDB漏标时补充 | 不需要 | provider |
| region | ✅ origin_country | ✅ 合拍片判断 | 不需要 | provider |
| origin_lang | ✅ original_language | ✅ 罕见需补充 | 不需要 | provider |
| resolution_tier | ✅ ffprobe检测 | 不需要 | 不需要 | file |
| broad_genre | ⚠️ genre_ids映射优先级复杂 | ✅ AI替代复杂映射 | 不需要 | provider/ai_assist |

**关键发现**：`restricted_level` 的 Provider 映射最复杂——TMDB 有 `release_dates` 字段，但各国分级体系不同，无法用简单规则映射到统一的 0-6/7-12/13-16/17+。这正是 AI 辅助模型最适合替代的工作。

---

## 2. 刮削逻辑展示卡

**纯信息展示，无输入控件，默认折叠。**

```
┌─ 刮削与匹配逻辑 ▸ ─────────────────────────────────────────┐
│                                                              │
│  ① 标题清洗                                                  │
│     └─ 辅助模型 + 正则规则提取影视标题和年份                  │
│                                                              │
│  ② 匹配路径（三级，可能循环）                                │
│     ├─ 第一级：Provider 精确匹配 → 自动入库                  │
│     ├─ 第二级：AI辅助建议关键词 → 重新搜索                   │
│     └─ 第三级：用户确认（取模糊匹配排名第一）                │
│                                                              │
│  ③ 维度确认（三级）                                          │
│     ├─ Provider 直接映射 → ✅ 完全信任                       │
│     ├─ AI辅助模型分析 → 替代复杂映射规则                     │
│     └─ AI联网搜索增强 → 补充缺失维度（需启用）              │
│                                                              │
│  ④ 维度完整性判定                                            │
│     ├─ 所有维度有值且可信 → ✅ 自动入库                      │
│     └─ 维度缺失或AI补充不信任 → ⚠️ 待确认                   │
│                                                              │
│  ⑤ 人工复核                                                  │
│     └─ 可在复核界面手动触发 AI 搜索                           │
│                                                              │
└──────────────────────────────────────────────────────────┘
```

---

## 3. AI 辅助（区块一）

### 3.1 界面布局

```
┌─ AI 辅助 ──────────────────────────────────────────────────┐
│  [保存]                                                      │
│                                                              │
│  ▸ 使用说明（手风琴，默认折叠）                               │
│                                                              │
│  模型URL：   [https://open.bigmodel.cn/api/paas/v4/  ]      │
│  模型ID：    [glm-4-flash                              ]     │
│  API Key：   [••••••••]                                      │
│                                                              │
│  [AI 辅助测试]                                               │
│                                                              │
│  ▾ 高级选项                                                  │
│    超时时间：  [30] 秒                                       │
│    最大重试：  [2] 次                                        │
│    重试间隔：  [3] 秒                                        │
│    验证 SSL：  [✓]                                           │
└──────────────────────────────────────────────────────────────┘
```

**关键变化**：不再做厂商下拉映射，改为用户直接输入模型URL和模型ID。

**理由**：
- 不同厂商还分订阅计划和API模式，映射工作量大
- 用户自己知道用什么URL和模型，不需要我们映射
- 减少维护成本（厂商URL和模型列表经常变化）

### 3.2 使用说明

```
AI 辅助模型用于以下轻量任务（不需要联网搜索）：

① 标题清洗 — 从文件名提取影视标题和年份
② 匹配辅助 — 分析目录上下文，建议更准确的搜索关键词
③ 维度分析 — 将Provider返回的复杂数据映射为维度值
   （如将各国分级标准映射为统一的年龄分级）
④ 数据整理 — Provider 返回数据的格式化和清洗
⑤ 源目录清理 — AI 辅助判断垃圾文件

推荐速度快、成本低的模型，如 glm-4-flash、qwen-turbo 等。
模型URL请填写厂商提供的 OpenAI 兼容 API 地址。
```

### 3.3 配置字段

```yaml
ai_assist:
  base_url: "https://open.bigmodel.cn/api/paas/v4/"   # 模型URL
  model: "glm-4-flash"                                  # 模型ID
  api_key: ""
  timeout: 30            # 高级选项
  max_retries: 2         # 高级选项
  retry_delay: 3         # 高级选项
  verify_ssl: true       # 高级选项
```

---

## 4. AI联网搜索增强（区块二）

### 4.1 作用定义

**AI联网搜索增强仅用于维度补全。**

### 4.2 界面布局

```
┌─ AI联网搜索增强 ──────────────────────────────────────────┐
│  [保存]                                                      │
│                                                              │
│  [开关] 启用 AI联网搜索增强                                  │
│  关闭后系统仅使用 Provider 映射和 AI辅助模型补充维度          │
│                                                              │
│  ▸ 使用说明（手风琴，默认折叠）                               │
│                                                              │
│  模型厂商：    [智谱 GLM ▼]                                  │
│  模型：        [glm-4-flash ▼]                               │
│  搜索类型：    [标准搜索 ▼]                                   │
│  API Key：     [••••••••]                                    │
│                                                              │
│  [测试连通性]  [AI联网搜索增强测试]                           │
│                                                              │
│  ▾ 高级选项                                                  │
│    接口地址：  [自动填充]                                     │
│    超时时间：  [30] 秒                                       │
│    最大重试：  [2] 次                                        │
│    重试间隔：  [3] 秒                                        │
│    验证 SSL：  [✓]                                           │
└──────────────────────────────────────────────────────────────┘
```

**关键变化**：
- **新增开关**：启用/禁用 AI联网搜索增强
- 关闭后，维度补全只走 Provider映射 + AI辅助模型分析
- AI联网搜索增强保留厂商下拉（因为搜索类型需要厂商映射）

### 4.3 使用说明

```
AI联网搜索增强用于维度补全（需要联网搜索能力）：

当 Provider 映射和 AI辅助模型都无法获取某些维度值时，
AI联网搜索增强会联网搜索补充缺失的维度信息。

⚠ 必须选择支持网络搜索功能的模型厂商和模型。
  后续版本将支持独立的搜索服务，届时可选择更多模型。

当前支持联网搜索的厂商：智谱 GLM、通义千问、Kimi/Moonshot
暂不支持联网搜索：DeepSeek（可作为辅助模型使用）
```

### 4.4 搜索类型分析

| 厂商 | 搜索类型 | API 参数 |
|---|---|---|
| **智谱 GLM** | 标准搜索 | `tools.web_search.search_type: "search_std"` |
| **智谱 GLM** | 增强搜索 | `tools.web_search.search_type: "search_pro"` |
| **通义千问** | 标准搜索 | `enable_search: true` |
| **通义千问** | 强制搜索 | `enable_search: true, search_options: {forced_search: true}` |
| **Kimi/Moonshot** | 联网搜索 | `tools: [{type: "builtin_function", function: {name: "$web_search"}}]` |
| **DeepSeek** | — | 不支持联网搜索 |

### 4.5 配置字段

```yaml
ai_search:
  enabled: true                          # 开关
  provider: "zhipu"                      # 厂商（下拉选择，用于搜索类型映射）
  model: "glm-4-flash"                   # 模型ID
  search_type: "search_std"              # 搜索类型
  api_key: ""
  base_url: ""                           # 高级选项，自动填充
  timeout: 30                            # 高级选项
  max_retries: 2                         # 高级选项
  retry_delay: 3                         # 高级选项
  verify_ssl: true                       # 高级选项
```

---

## 5. 维度信任配置

### 5.1 设计思路

每个维度新增两个独立信任开关：

- **信任AI辅助映射**（`trust_ai_assist`）：AI辅助模型分析给出的维度值是否直接采纳
- **信任AI联网搜索**（`trust_ai_search`）：AI联网搜索增强给出的维度值是否直接采纳

**组合效果**：

| trust_ai_assist | trust_ai_search | AI辅助映射结果 | AI联网搜索结果 |
|---|---|---|---|
| ✅ | ✅ | 直接采纳 | 直接采纳 |
| ✅ | ❌ | 直接采纳 | 需人工确认 |
| ❌ | ✅ | 需人工确认 | 直接采纳 |
| ❌ | ❌ | 需人工确认 | 需人工确认 |

**典型场景**：
- `restricted_level`：信任AI辅助映射 ✅（AI将各国分级映射到统一体系，比规则更准），不信任AI联网搜索 ❌（联网搜索结果可能不准确）
- `region`：信任AI辅助映射 ✅（AI判断合拍片地区比规则更准），信任AI联网搜索 ✅（地区信息通常准确）
- `media_type`：不需要AI辅助（搜索端点已确定类型），不需要AI联网搜索

### 5.2 界面

```
┌─ 维度：限制级分类 ────────────────────────────────────────┐
│  标签：限制级分类                                            │
│  AI提示词：请判断该影视内容的年龄分级...                     │
│  值列表：0-6 / 7-12 / 13-16 / 17+                           │
│                                                              │
│  信任AI辅助映射：[✓]   信任AI联网搜索：[  ]                 │
│  ↑ 关闭后，该来源的维度值需要人工确认                        │
└──────────────────────────────────────────────────────────────┘
```

### 5.3 DB 变更

```sql
-- 替代原来的 trust_ai 单字段
ALTER TABLE dimensions ADD COLUMN trust_ai_assist INTEGER NOT NULL DEFAULT 1;
ALTER TABLE dimensions ADD COLUMN trust_ai_search INTEGER NOT NULL DEFAULT 0;
-- 1 = 信任（默认），0 = 不信任
-- trust_ai_assist 默认信任（AI辅助映射通常比规则更准）
-- trust_ai_search 默认不信任（联网搜索结果需确认更安全）
```

[constants.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/db/constants.py) 中 `DEFAULT_DIMENSIONS` 每项新增 `"trust_ai_assist": 1, "trust_ai_search": 0`。

### 5.4 多 Provider 维度映射兼容

当前代码已有完整的多 Provider 映射架构（[dimension_manager.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/scraping/dimension_manager.py)）：

- 维度配置的 `provider_mappings` 字段按 Provider 分组存储映射规则
- `map_provider_to_dimension(dim_config, provider_data, release_dates, provider_type)` 按 Provider 类型选择映射规则
- Provider 基类有 `map_dimensions()` 抽象方法，每个 Provider 各自实现

**维度确认流程中的多 Provider 处理**：

```
维度确认第一级：Provider 直接映射
  │
  ├─ 遍历所有已配置的 Provider（按优先级排序）
  │   ├─ Provider 1（TMDB）→ map_dimensions() → 有值？取值
  │   ├─ Provider 2（豆瓣）→ map_dimensions() → 有值？取值
  │   └─ ...
  │
  ├─ 合并策略：
  │   ├─ 第一个有值的 Provider 结果优先（Provider 优先级由配置决定）
  │   └─ 标记来源为 "provider:tmdb" 或 "provider:douban"
  │
  └─ 所有 Provider 都无映射 → 进入第二级（AI辅助映射）
```

**维度配置中的 provider_mappings 结构**（已有，无需改动）：

```json
{
  "tmdb": {
    "match_type": "genre_ids",
    "match_rules": {
      "true": {"ids": [99]},
      "false": {"ids": []}
    }
  },
  "douban": {
    "match_type": "genre_names",
    "match_rules": {
      "true": {"names": ["纪录片"]},
      "false": {"names": []}
    }
  }
}
```

**维度来源图标扩展**（支持多 Provider）：

| 来源 | 图标 | 含义 |
|---|---|---|
| provider:tmdb | 🗄️ | 来自 TMDB 直接映射 |
| provider:douban | 📚 | 来自豆瓣直接映射 |
| ai_assist | 🤖 | 来自 AI辅助模型映射 |
| ai_search | 🔍 | 来自 AI联网搜索增强 |
| file | 📄 | 来自文件分析 |

**前端展示**：维度来源显示具体 Provider 名，如 `🗄️ TMDB` 或 `📚 豆瓣`

### 5.5 刮削流程中的影响

```python
def _determine_match_level(result: dict, enabled_dims: list, dim_sources: dict) -> tuple:
    """基于维度完整性和信任配置判定匹配级别。

    Returns:
        (match_level, confirm_reason)
    """
    reasons = []
    missing_dims = []
    untrusted_ai_dims = []

    for dim in enabled_dims:
        dim_name = dim["name"]
        dim_label = dim.get("label", dim_name)
        value = result.get(dim_name)
        source = dim_sources.get(dim_name, "unknown")
        trust_ai_assist = dim.get("trust_ai_assist", 1)
        trust_ai_search = dim.get("trust_ai_search", 0)

        if value is None or value == "" or value == "unknown":
            missing_dims.append(dim_label)
            continue

        # AI辅助映射 + 不信任AI辅助
        if source == "ai_assist" and not trust_ai_assist:
            untrusted_ai_dims.append(f"{dim_label}(AI辅助)")
        # AI联网搜索 + 不信任AI联网搜索
        elif source == "ai_search" and not trust_ai_search:
            untrusted_ai_dims.append(f"{dim_label}(AI联网搜索)")

    if missing_dims:
        reasons.append(f"维度缺失: {', '.join(missing_dims)}")
    if untrusted_ai_dims:
        reasons.append(f"AI补充需确认: {', '.join(untrusted_ai_dims)}")

    if not reasons:
        return "AUTO_PASS", ""
    return "NEEDS_CONFIRM", "；".join(reasons)
```

---

## 6. 维度来源图标标识

在任务卡片和刮削详情中，每个维度值旁边显示来源图标：

| 来源 | 图标 | 含义 |
|---|---|---|
| provider | 🗄️ | 来自 Provider 直接映射，完全信任 |
| ai_assist | 🤖 | 来自 AI辅助模型分析 |
| ai_search | 🔍 | 来自 AI联网搜索增强 |
| file | 📄 | 来自文件分析（如分辨率） |
| 空 | — | 维度值缺失 |

**示例**：

```
┌─ 刮削结果 ─────────────────────────────────────────────────┐
│  影视类型:  movie      🗄️ TMDB搜索端点映射                    │
│  是否纪录片: false     🗄️ TMDB genre映射                    │
│  限制级分类: 13-16     🤖 AI辅助映射各国分级                 │
│  是否动漫:   false     🗄️ TMDB genre映射                    │
│  地区:       jp        🗄️ TMDB origin_country映射           │
│  分辨率:     1080p     📄 ffprobe检测                       │
│  题材类型:   动作/冒险  🗄️ TMDB genre映射                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 7. AI 提示词管理

### 7.1 新方案下提示词去留分析

| 当前提示词 | 位置 | 新方案下 | 原因 |
|---|---|---|---|
| 刮削系统提示词（DEFAULT_SYSTEM_PROMPT） | [prompt_builder.py:17-79](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/prompts/prompt_builder.py#L17-L79) | **保留但重命名** → "维度映射提示词" | 新方案中AI不再做全量刮削，这个提示词改为专用于维度映射（将Provider复杂数据映射为维度值） |
| 第二级匹配提示词（tier2_judge） | [llm_scraper.py:412-414](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/llm_scraper.py#L412-L414) | **需重写** → "匹配辅助提示词" | 旧版是"从候选中选出"，新版改为"分析上下文建议新搜索关键词" |
| 标题清洗提示词（ai_clean） | [filename_cleaner.py:142-147](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/filename_cleaner.py#L142-L147) | **保留** | 标题清洗逻辑不变 |
| 源目录清理提示词（AI_SYSTEM_PROMPT） | [cleaner.py:15-40](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/source_cleaning/cleaner.py#L15-L40) | **保留** | 源目录清理逻辑不变 |
| 各维度 ai_prompt | [constants.py:108-339](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/db/constants.py#L108-L339) | **保留** | 维度配置界面可编辑，不变 |
| 维度判断提示词（旧版） | [llm_scraper.py:48-56](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/llm_scraper.py#L48-L56) | **删除** | 旧版兼容代码，新版用 DB dimensions.ai_prompt |
| — | — | **新增** → "缺失维度搜索提示词" | AI联网搜索增强补充缺失维度时的指令，当前无独立提示词 |

**最终提示词清单（5 个可配置 + 8 个维度提示词）**：

| 提示词 | 归属 | 用途 | 默认值来源 |
|---|---|---|---|
| 标题清洗 | AI辅助 | 从文件名提取影视标题和年份 | [filename_cleaner.py:142-147](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/filename_cleaner.py#L142-L147) |
| 匹配辅助 | AI辅助 | 第二级匹配时AI分析上下文建议关键词 | **需新写**（旧版 tier2_judge 需重写） |
| 维度映射 | AI辅助 | 将Provider复杂数据映射为维度值 | [prompt_builder.py:17-79](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/prompts/prompt_builder.py#L17-L79)（精简，去掉全量刮削相关内容） |
| 源目录清理 | AI辅助 | AI判断源目录中哪些是垃圾文件 | [cleaner.py:15-40](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/source_cleaning/cleaner.py#L15-L40) |
| 缺失维度搜索 | AI联网搜索增强 | AI联网搜索补充缺失维度时的指令 | **需新写** |
| 各维度 ai_prompt ×8 | 维度配置界面 | 每个维度的AI判断提示词 | DB dimensions 表 |

### 7.2 默认提示词存储方案

**问题**：用户点击"恢复默认"时，默认提示词从哪里来？

**方案**：默认提示词存储在后端 Python 代码中，通过 API 暴露给前端。

```
存储位置：media_importer/features/prompts/defaults.py

class PromptDefaults:
    """所有场景的默认提示词，作为恢复默认的唯一来源。"""

    TITLE_CLEAN = "从以下视频文件名中提取影视作品的标题和上映年份..."
    MATCH_ASSIST = "你是一个影视元数据匹配助手。根据目录上下文和候选列表..."
    DIMENSION_MAPPING = "你是一个专业的影视信息分析助手。根据Provider返回的数据..."
    SOURCE_CLEAN = "你是"影音库AI智能整理"系统的源目录清理助手..."
    DIMENSION_SUPPLEMENT = "你是一个影视信息搜索助手。根据提供的影视作品信息..."

    @classmethod
    def get_all(cls) -> dict:
        return {
            "title_clean": cls.TITLE_CLEAN,
            "match_assist": cls.MATCH_ASSIST,
            "dimension_mapping": cls.DIMENSION_MAPPING,
            "source_clean": cls.SOURCE_CLEAN,
            "dimension_supplement": cls.DIMENSION_SUPPLEMENT,
        }
```

**API**：`GET /api/config/prompt-defaults` → 返回所有默认提示词

```json
{
  "title_clean": "从以下视频文件名中提取...",
  "match_assist": "你是一个影视元数据匹配助手...",
  "dimension_mapping": "你是一个专业的影视信息分析助手...",
  "source_clean": "你是"影音库AI智能整理"系统...",
  "dimension_supplement": "你是一个影视信息搜索助手..."
}
```

**优先级**：
```
1. 用户在高级选项中配置的自定义提示词（最高优先级）
2. config/scraper_prompts.md 文件中的提示词（兼容旧方式，仅 dimension_mapping）
3. PromptDefaults 代码常量（兜底，"恢复默认"的目标）
```

### 7.3 前端交互：分页签设计

**AI 辅助高级选项 → 提示词配置**：

```
  ▾ 高级选项
    超时时间：  [30] 秒
    最大重试：  [2] 次
    重试间隔：  [3] 秒
    验证 SSL：  [✓]

    ── 提示词配置 ──────────────────────────────
    [标题清洗] [匹配辅助] [维度映射] [源目录清理]  ← 页签切换
    ┌──────────────────────────────────────────────┐
    │ 从以下视频文件名中提取影视作品的标题和上映年份。│
    │ 注意：文件名可能包含制作组名、分辨率、编码信息 │
    │ 等干扰项，年份可能是标题的一部分而非上映年份。 │
    │ 请按以下JSON格式返回，不要返回其他内容：       │
    │ {"title": "标题", "year": 年份或null}         │
    │                                               │
    └──────────────────────────────────────────────┘
    [恢复默认]
```

**AI联网搜索增强高级选项 → 提示词配置**：

```
  ▾ 高级选项
    接口地址：  [自动填充]
    超时时间：  [30] 秒
    最大重试：  [2] 次
    重试间隔：  [3] 秒
    验证 SSL：  [✓]

    ── 提示词配置 ──────────────────────────────
    [缺失维度搜索]                                  ← 单页签
    ┌──────────────────────────────────────────────┐
    │ 你是一个影视信息搜索助手。根据提供的影视作品   │
    │ 信息，联网搜索补充缺失的维度值。               │
    │                                               │
    └──────────────────────────────────────────────┘
    [恢复默认]
```

**交互规则**：
- 页签切换时，当前编辑内容自动保存到内存（不写入配置文件，点"保存"才持久化）
- "恢复默认"：清空当前页签的 textarea，从 `/api/config/prompt-defaults` 获取默认值填入
- 页签上显示修改状态：已修改显示 `•` 标记，如 `标题清洗 •`
- textarea 高度自适应内容，最小 200px

### 7.4 配置字段

```yaml
ai_assist:
  base_url: "https://open.bigmodel.cn/api/paas/v4/"
  model: "glm-4-flash"
  api_key: ""
  timeout: 30
  max_retries: 2
  retry_delay: 3
  verify_ssl: true
  # 提示词（高级选项，留空使用默认值）
  prompt_title_clean: ""          # 标题清洗
  prompt_match_assist: ""         # 匹配辅助
  prompt_dimension_mapping: ""    # 维度映射
  prompt_source_clean: ""         # 源目录清理

ai_search:
  enabled: true
  provider: "zhipu"
  model: "glm-4-flash"
  search_type: "search_std"
  api_key: ""
  base_url: ""
  timeout: 30
  max_retries: 2
  retry_delay: 3
  verify_ssl: true
  # 提示词（高级选项，留空使用默认值）
  prompt_dimension_supplement: ""  # 缺失维度搜索
```

### 7.5 需新写的提示词

#### 匹配辅助提示词（重写）

旧版（tier2_judge）：让 AI 从候选列表中选出最匹配的结果
新版：让 AI 分析上下文，建议新的搜索关键词

```
你是一个影视元数据匹配助手。当前正在为一个视频文件匹配影视元数据，
但 Provider（TMDB等）搜索后未找到精确匹配结果。

请根据以下信息，分析该文件可能对应的影视作品，建议更准确的搜索关键词。

分析策略：
1. 优先从上级文件夹名推断影视标题（文件夹名通常比文件名更准确）
2. 从同级文件名中寻找关联信息（如季集编号、系列名）
3. 如果文件名含年份但搜索无结果，尝试去掉年份重新搜索
4. 如果文件名是英文缩写，尝试展开完整名称

输出要求：
返回 JSON:
{"suggested_query": "建议的搜索关键词", "confidence": 0.8, "reason": "判断理由"}

如果无法建议有效关键词，设置 confidence < 0.5 并说明原因。
```

#### 缺失维度搜索提示词（新增）

```
你是一个影视信息搜索助手。根据提供的影视作品信息，联网搜索补充缺失的维度值。

重要原则：
1. 只补充明确缺失的维度，不要修改已有值
2. 搜索结果应来自权威数据源（豆瓣、TMDB、IMDb、维基百科）
3. 如果搜索后仍无法确定，将该维度设为空字符串 ""
4. 不要猜测或编造信息

输出要求：
返回 JSON，只包含需要补充的维度:
{"维度名": "值或空字符串", ...}
```

---

## 8. 模拟刮削流程图

### 8.1 模拟刮削展示

模拟刮削应展示**每个维度的来源路径**：

```
┌─ 模拟刮削 ─────────────────────────────────────────────────┐
│                                                              │
│  文件名: Inception.2010.1080p.BluRay.mkv                     │
│                                                              │
│  ── 标题清洗 ──                                              │
│  标题: Inception  年份: 2010  季: -  集: -                   │
│                                                              │
│  ── 匹配路径 ──                                              │
│  第一级: TMDB 搜索 "Inception" + year=2010                   │
│  → ✅ 精确匹配: Inception (2010)                             │
│                                                              │
│  ── 维度确认 ──                                              │
│  影视类型:   movie      🗄️ TMDB搜索端点硬编码                 │
│  是否纪录片: false     🗄️ TMDB genre_ids 无99                │
│  限制级分类: 13-16     🤖 AI辅助（MPAA=PG-13 → 13-16）      │
│  是否动漫:   false     🗄️ TMDB genre_ids 无16                │
│  地区:       us        🗄️ TMDB origin_country=["US"]        │
│  原始语言:   en        🗄️ TMDB original_language="en"       │
│  分辨率:     1080p     📄 ffprobe检测                        │
│  题材类型:   科幻/奇幻  🗄️ TMDB genre_ids=[878,12]          │
│                                                              │
│  ── 最终结果 ──                                              │
│  匹配级别: ✅ 自动入库                                       │
│  预估路径: /电影/科幻奇幻/Inception (2010)/...               │
└──────────────────────────────────────────────────────────────┘
```

### 8.2 任务卡片刮削过程展示

已完成的任务卡片，点击"刮削过程"可展开查看：

```
┌─ 任务卡片 ─────────────────────────────────────────────────┐
│  🎬 Inception.2010.BluRay.mkv                    ✅ 已入库  │
│  电影 · 2010 · 1080p                                        │
│  [详情] [刮削过程 ▾]                                        │
│                                                              │
│  ▾ 刮削过程                                                  │
│  匹配: 第一级精确匹配 ✅                                     │
│  ── 维度来源 ──                                              │
│  影视类型: movie 🤖  纪录片: false 🗄️                       │
│  限制级: 13-16 🤖  动漫: false 🗄️                           │
│  地区: us 🗄️  语言: en 🗄️  分辨率: 1080p 📄                │
│  题材: 科幻/奇幻 🗄️                                         │
└──────────────────────────────────────────────────────────────┘
```

---

## 9. 配置 YAML 结构

```yaml
ai_assist:
  base_url: "https://open.bigmodel.cn/api/paas/v4/"
  model: "glm-4-flash"
  api_key: ""
  timeout: 30
  max_retries: 2
  retry_delay: 3
  verify_ssl: true

ai_search:
  enabled: true
  provider: "zhipu"
  model: "glm-4-flash"
  search_type: "search_std"
  api_key: ""
  base_url: ""
  timeout: 30
  max_retries: 2
  retry_delay: 3
  verify_ssl: true
```

### 字段映射（旧 → 新）

| 旧字段 | 新字段 | 说明 |
|---|---|---|
| `llm.fast_model` | `ai_assist.model` | |
| `llm.fast_api_key` | `ai_assist.api_key` | |
| `llm.fast_base_url` | `ai_assist.base_url` | |
| `llm.source_cleaner_model` | `ai_assist.model` | 合并 |
| `llm.api_key` | `ai_search.api_key` | |
| `llm.base_url` | `ai_search.base_url` | 高级选项 |
| `llm.model` | `ai_search.model` | |
| `llm.web_search.provider` | `ai_search.provider` | |
| `llm.fallback_model` | — | **删除** |
| `llm.confidence_threshold` | — | **删除** |
| `llm.enabled` | — | **删除** |
| `metadata.scrape_mode` | — | **删除** |
| — | `ai_search.enabled` | **新增** 开关 |
| — | `ai_search.provider` | **新增** |
| — | `ai_search.search_type` | **新增** |
| — | `dimensions.trust_ai_assist` | **新增** DB字段 |
| — | `dimensions.trust_ai_search` | **新增** DB字段 |

---

## 10. 影响评估

### 9.1 前端改动

| 文件 | 改动点 |
|---|---|
| [index.html](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/index.html) | ① 替换 scrape-mode-card 为展示卡 ② AI辅助：模型URL+模型ID+API Key ③ AI联网搜索增强：开关+厂商下拉+模型下拉+搜索类型+API Key ④ 两个区块各自加使用说明手风琴+高级选项 ⑤ 维度配置区域新增"信任AI"开关 |
| [cinema-config.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/cinema-config.js) | ① buildLlmConfigPayload → buildAiAssistPayload + buildAiSearchPayload ② saveScrapeModeConfig 删除 ③ 新增 onProviderChange 联动 ④ 新增 onAdvancedToggle ⑤ 维度保存逻辑新增 trust_ai ⑥ **模拟刮削重写**：展示每个维度来源路径 |
| [cinema-config.css](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/css/cinema-config.css) | ① 展示卡样式 ② 手风琴样式 ③ 高级选项折叠样式 ④ 维度来源图标样式 |
| [cinema-dimensions.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/cinema-dimensions.js) | ① 维度卡片新增"信任AI"开关 ② 保存时包含 trust_ai |
| [cinema-tasks.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/cinema-tasks.js) | ① 任务卡片展示 confirm_reason ② **新增"刮削过程"展开区域**：展示每个维度来源+图标 |

### 9.2 后端改动

| 文件 | 改动点 |
|---|---|
| [config_view.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/config_view.py) | ① 新增 AiAssistConfig / AiSearchConfig dataclass ② LLMConfig 标记 legacy |
| [application_service.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/configuration/application_service.py) | ① SECTION_FIELD_MAP 新增 "ai_assist" / "ai_search" |
| [config_loader.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/config_loader.py) | ① 迁移逻辑：llm → ai_assist + ai_search |
| [llm_scraper.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/llm_scraper.py) | ① 构造函数优先读 ai_search/ai_assist ② _inject_search 新增 search_type ③ fast_model 来源改为 ai_assist.model |
| [web_search_config.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/scraping/web_search_config.py) | ① 新增 doubao/openai/self_hosted ② 新增 search_type 字段 |
| [metadata_scrape_flow.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/metadata_scrape_flow.py) | ① 删除 ai_only 分支 ② 维度确认流程三级 ③ 维度值来源追踪 ④ 生成 confirm_reason ⑤ 第二级改为循环清洗+重新搜索 |
| [match_engine.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/scraping/match_engine.py) | ① MatchResult 新增 confirm_reason ② concerns 新增 AI_SUPPLEMENTED_UNTRUSTED ③ 第二级改为AI建议关键词+循环回第一级 ④ 模糊匹配取排名第一 |
| [match_models.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/scraping/match_models.py) | ① MatchResult 新增 confirm_reason ② MatchConcern code 新增 AI_SUPPLEMENTED_UNTRUSTED |
| [review.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/import_flow/services/review.py) | ① evaluate() 改为基于 match_level + confirm_reason |
| [scrape.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/import_flow/steps/scrape.py) | ① _step_scrape 保存 confirm_reason + dim_sources 到 task 和 DB |
| [dimension_repo.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/db/dimension_repo.py) | ① 新增 trust_ai 字段读写 |
| [constants.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/db/constants.py) | ① DEFAULT_DIMENSIONS 新增 trust_ai: 1 |
| [connection.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/db/connection.py) | ① DB schema 新增 trust_ai 列 |
| [task_repo.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/db/task_repo.py) | ① 新增 confirm_reason / dim_sources 字段读写 |
| [config_handlers.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/api/config_handlers.py) | ① 支持 ai_assist / ai_search section |
| [connectivity_handlers.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/api/connectivity_handlers.py) | ① AI 测试参数来源切换 |
| [tmdb_handlers.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/api/tmdb_handlers.py) | ① _scrape_preview 返回结构包含每个维度的来源 |

### 9.3 DB 变更

| 表 | 变更 |
|---|---|
| `dimensions` | 新增 `trust_ai_assist INTEGER NOT NULL DEFAULT 1` |
| `dimensions` | 新增 `trust_ai_search INTEGER NOT NULL DEFAULT 0` |
| `tasks` | 新增 `confirm_reason TEXT DEFAULT ''` |
| `tasks` | 新增 `dim_sources TEXT DEFAULT NULL`（JSON，维度值来源追踪） |

### 9.4 模拟刮削 API 变更

`_scrape_preview` 返回结构新增维度来源：

```json
{
  "match_result": {
    "match_level": "AUTO_PASS",
    "match_tier": 1,
    "concerns": [],
    "confirm_reason": ""
  },
  "dimensions": {
    "media_type": {"value": "movie", "source": "provider", "source_label": "TMDB搜索端点"},
    "documentary": {"value": "false", "source": "provider", "source_label": "TMDB genre映射"},
    "restricted_level": {"value": "13-16", "source": "ai_assist", "source_label": "AI辅助映射(MPAA=PG-13)"},
    "animation": {"value": "false", "source": "provider", "source_label": "TMDB genre映射"},
    "region": {"value": "us", "source": "provider", "source_label": "TMDB origin_country"},
    "resolution_tier": {"value": "1080p", "source": "file", "source_label": "ffprobe检测"}
  },
  "import_path": "/电影/科幻奇幻/Inception (2010)/..."
}
```

---

## 11. 与旧计划的差异对照

| 项 | 旧计划 | 本方案（v6） |
|---|---|---|
| AI辅助配置 | 厂商下拉+模型下拉 | **模型URL+模型ID**，不做厂商映射 |
| AI联网搜索增强作用 | 刮削器搜不到时兜底+维度补全 | **仅维度补全** |
| AI联网搜索增强开关 | 无 | **新增 enabled 开关** |
| 维度确认流程 | Provider映射→AI补齐 | **三级**：Provider映射→AI辅助分析→AI联网搜索增强 |
| 维度信任配置 | 无 | **拆分为两个**：trust_ai_assist + trust_ai_search |
| 维度来源展示 | 无 | **图标标识** 🗄️🤖🔍📄 |
| AI提示词管理 | 代码写死 | **高级选项中可维护**，5个提示词可配置 |
| 模拟刮削 | 双模式对比+置信度 | **展示每个维度来源路径** |
| 任务卡片 | 置信度数值 | **刮削过程展开区**：维度来源+图标 |
| 第二级匹配 | AI从候选中选出 | AI建议关键词→循环回第一级 |
| 确认原因 | 无 | 新增 confirm_reason |

---

## 12. 实施顺序

```
Phase 1 — 配置结构 + DB 变更
  ① 新增 AiAssistConfig / AiSearchConfig dataclass
  ② SECTION_FIELD_MAP 注册 "ai_assist" / "ai_search"
  ③ config_loader 迁移逻辑
  ④ web_search_config.py 新增 search_type + 新厂商
  ⑤ DB: dimensions 新增 trust_ai, tasks 新增 confirm_reason + dim_sources

Phase 2 — UI 重写
  ⑥ 重写 index.html 的 AI 辅助 + AI联网搜索增强区块
  ⑦ 重写 cinema-config.js 的保存与联动逻辑
  ⑧ 新增展示卡和手风琴样式
  ⑨ 维度配置新增"信任AI"开关
  ⑩ 测试按钮联动更新
  ⑪ 任务卡片展示 confirm_reason + 刮削过程展开区
  ⑫ 模拟刮削重写：展示每个维度来源路径

Phase 3 — 刮削逻辑切换
  ⑬ llm_scraper.py 初始化改为优先读 ai_search / ai_assist
  ⑭ _inject_search() 新增 search_type 参数
  ⑮ 第二级匹配改为AI建议关键词+循环回第一级
  ⑯ 维度确认流程三级实现
  ⑰ 维度值来源追踪（dim_sources）
  ⑱ 生成 confirm_reason
  ⑲ 删除 _scrape_ai_only() 分支
  ⑳ review.py 改为基于 match_level + confirm_reason
```

---

## 13. 验收标准

- [ ] 配置页面不再有"刮削模式"下拉
- [ ] AI 辅助区块：模型URL + 模型ID + API Key → 保存
- [ ] AI联网搜索增强区块：开关 + 厂商下拉 + 模型下拉 + 搜索类型 + API Key → 保存
- [ ] AI联网搜索增强关闭后，维度补全只走 Provider映射 + AI辅助模型
- [ ] AI联网搜索增强**仅用于维度补全**
- [ ] 维度确认流程三级：Provider映射 → AI辅助分析 → AI联网搜索增强
- [ ] 维度来源图标：🗄️TMDB / 📚豆瓣 / 🤖AI辅助 / 🔍AI联网搜索 / 📄文件分析
- [ ] 维度来源支持多 Provider（provider:tmdb / provider:douban 格式）
- [ ] 模拟刮削展示每个维度的来源路径
- [ ] 任务卡片点击"刮削过程"可展开查看维度来源
- [ ] 维度配置区域新增"信任AI辅助映射"和"信任AI联网搜索"两个独立开关
- [ ] 第二级匹配使用辅助模型，AI建议关键词后循环回第一级
- [ ] 标题清洗与匹配支持循环（最多 2 次）
- [ ] 匹配失败时取模糊匹配排名第一的结果刮削，让用户确认
- [ ] 匹配结果判定基于维度完整性 + 信任配置
- [ ] 待确认任务返回 confirm_reason
- [ ] 维度值来源可追踪（provider:tmdb/provider:douban/ai_assist/ai_search/file）
- [ ] 不信任AI辅助的维度被AI辅助补充后自动标记待确认
- [ ] 不信任AI联网搜索的维度被AI联网搜索补充后自动标记待确认
- [ ] AI辅助高级选项中提示词用分页签展示（标题清洗/匹配辅助/维度映射/源目录清理）
- [ ] AI联网搜索增强高级选项中提示词用分页签展示（缺失维度搜索）
- [ ] "恢复默认"按钮从 /api/config/prompt-defaults 获取默认值填入
- [ ] 默认提示词存储在 media_importer/features/prompts/defaults.py
- [ ] 页签上显示修改状态标记（已修改显示 •）
- [ ] 提示词留空时使用默认值
- [ ] 老用户的 llm 配置能自动迁移

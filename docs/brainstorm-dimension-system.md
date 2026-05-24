---
title: "维度体系扩展设计"
type: brainstorm
date: 2026-05-24
participants: [用户, AI助手]
related:
  - docs/brainstorm-metadata-api-integration.md
  - docs/implementation-plan-metadata-api.md
---

# 维度体系扩展设计

## Problem Statement

当前系统硬编码 4 个维度（media_type、documentary、animation、restricted_level），无法满足用户按地区、语言、分辨率、类型等维度分拣入库的需求。维度扩展的核心矛盾是：**哪些分类形式适合做维度？** 系列、年份等穷举型分类不适合，而地区、语言、分辨率等值域有界的分类才是维度的正确形态。

## Context

- 当前 4 维度全部依赖 AI 判断，有误判风险
- TMDB API 提供了 `origin_country`、`original_language`、`genres` 等确定性字段
- 视频文件本身包含分辨率元数据（可通过 ffprobe 读取）
- 文件名解析分辨率不可靠（依赖命名规范）
- 前端维度信息硬编码在 path-rules.js、tasks.js、tasks.css 中（约 150 行）
- 维度相关信息散落在 7 个文件中，加一个维度要改 7 处
- 系统为 NAS 本地部署，非 C/S 架构，会员权限需离线验证

## Chosen Approach

**数据库驱动的菜单式维度体系**：8 个内置维度存储在数据库 `dimensions` 表中，3 个默认启用（media_type、documentary、restricted_level），其余 5 个需用户手动添加（部分高级维度需会员权限）。维度分三种来源（AI/TMDB/文件），统一存储在 dimensions 字典中。前端从 API 动态读取维度定义，消除硬编码。配置界面开辟独立的维度配置页签。

## Why This Approach

- **菜单式 vs 启用/禁用**：维度就是标签，全部打上，用户在 path_rules 中选用即可。
- **统一存储 vs 分类存储**：不同来源的维度统一存入 `dimensions` 字典，path_rules 无需关心来源差异。
- **内置菜单 vs 自定义维度**：自定义维度增加复杂度和配置门槛，内置 8 维度覆盖 80-90% 场景。
- **数据库 vs 配置文件**：维度定义含映射规则、AI 提示词、UI 颜色等复杂结构，数据库存储便于 UI 编辑和动态读取。加维度 = 加一行数据，不改代码。config.yaml 中删除 dimensions 段。
- **3 默认 + 5 可选**：降低新用户认知负担，高级维度按需添加。

## Key Design Decisions

### Q1: 维度来源模式 — RESOLVED
**Decision:** 混合模式 — TMDB 命中时确定性取值（置信度 1.0），TMDB 未命中时 AI 兜底
**Rationale:** TMDB 字段是确定性数据，不应让 AI 重新判断。但 TMDB 不总是可用，需要 AI 兜底。

### Q2: 维度存储方式 — RESOLVED
**Decision:** 分类来源、统一存储 — 不同来源的维度统一存入 `dimensions` 字典
**Rationale:** path_rules 只需关心维度值，不需要知道来源。简化分类器逻辑。

### Q3: 维度数量策略 — RESOLVED
**Decision:** 菜单式可选 — 3 个默认启用，5 个需用户手动添加
**Rationale:** 降低新用户认知负担。默认 3 个（media_type、documentary、restricted_level）覆盖最基础需求，高级维度按需添加。

### Q4: genre 处理 — RESOLVED
**Decision:** 优先级映射 — TMDB 多 genre 按优先级取最高，优先级可配置
**Rationale:** 一部作品多个 genre 是常态，优先级机制让风格鲜明的作品归入正确类别。

### Q5: 自定义维度 — RESOLVED
**Decision:** 不支持自定义维度，内置菜单覆盖 80-90% 场景
**Rationale:** 自定义维度增加复杂度和配置门槛，收益有限。

### Q6: 分辨率来源 — RESOLVED
**Decision:** 使用 ffprobe 从视频文件元数据读取分辨率，不依赖文件名解析
**Rationale:** 文件名解析不可靠，ffprobe 读取视频流信息是确定性方法。fnOS 应预装 ffmpeg，但需做好依赖检测和自动安装。

### Q7: 维度定义存储 — RESOLVED
**Decision:** 数据库单表存储（dimensions 表 + JSON value_list 列），config.yaml 删除 dimensions 段
**Rationale:** 一个维度一行，所有信息都在。前端从 API 读取渲染下拉框。config.yaml 不再保存维度定义。

### Q8: 默认维度选择 — RESOLVED
**Decision:** 3 个默认（media_type、documentary、restricted_level），不考虑老用户升级
**Rationale:** 用户明确要求。animation 等维度需用户手动添加。

### Q9: 会员权限预留 — RESOLVED
**Decision:** dimensions 表增加 `required_tier` 字段预留权限层级，代码预留权限检查点，暂不实现完整许可证系统
**Rationale:** 非C/S架构，传统登录验证不适用。预留字段和检查点，未来可实现许可证密钥或在线激活。

### Q10: 前端维度配置 — RESOLVED
**Decision:** 配置界面开辟独立的"维度配置"页签，用户在此添加/移除维度、编辑映射规则和AI提示词
**Rationale:** 维度配置是独立概念，不应和 LLM 配置、TMDB 配置混在一起。入库规则页签只显示用户已添加的维度。

## 数据库表设计

### dimensions 表

```sql
CREATE TABLE dimensions (
    name           TEXT PRIMARY KEY,           -- 维度标识: media_type, region, ...
    label          TEXT NOT NULL,              -- 显示名: 影视类型, 地区, ...
    source_type    TEXT NOT NULL DEFAULT 'ai', -- 来源: ai / tmdb / tmdb_ai / file
    sort_order     INTEGER DEFAULT 0,          -- 显示顺序
    ai_prompt      TEXT,                       -- AI 判断提示词
    tmdb_field     TEXT,                       -- TMDB API 字段名（tmdb/tmdb_ai 类型使用）
    value_list     TEXT NOT NULL,              -- JSON: 值域定义（含标签、映射规则）
    color          TEXT DEFAULT '#6c757d',     -- UI 显示颜色
    is_system      INTEGER DEFAULT 1,          -- 系统维度不可删除
    is_enabled     INTEGER DEFAULT 0,          -- 是否启用（1=启用，0=未添加）
    required_tier  TEXT DEFAULT 'free',        -- 所需权限层级: free / pro / premium
    description    TEXT DEFAULT ''              -- 维度说明（配置界面展示）
);
```

### value_list JSON 结构（按 source_type 不同）

**AI 类型**（documentary, animation, restricted_level）：
```json
[
  {"value": "true",  "label": "是"},
  {"value": "false", "label": "否"}
]
```

**TMDB 类型**（region, origin_lang）：
```json
[
  {"value": "asia",     "label": "亚洲", "tmdb_codes": ["CN","HK","TW","JP","KR"]},
  {"value": "western",  "label": "欧美", "tmdb_codes": ["US","CA","AU","NZ","GB","IE"]},
  {"value": "european", "label": "欧洲", "tmdb_codes": ["FR","DE","IT","ES","RU","PL","NL","SE","NO","DK","FI","AT","BE","CH","PT","GR","CZ","HU","RO","BG","HR","SK","SI","LT","LV","EE","RS","UA"]},
  {"value": "other",    "label": "其他"}
]
```

**TMDB+AI 类型**（broad_genre）：
```json
[
  {"value": "horror",  "label": "恐怖", "tmdb_genre_ids": [27, 9648, 53],         "priority": 1},
  {"value": "scifi",   "label": "科幻", "tmdb_genre_ids": [878, 14],              "priority": 2},
  {"value": "action",  "label": "动作", "tmdb_genre_ids": [28, 12, 10752, 10759],  "priority": 3},
  {"value": "comedy",  "label": "喜剧", "tmdb_genre_ids": [35],                    "priority": 4},
  {"value": "drama",   "label": "剧情", "tmdb_genre_ids": [18, 10749, 80, 36, 10751, 10766, 10770], "priority": 5},
  {"value": "other",   "label": "其他", "tmdb_genre_ids": [10402, 10763, 10764, 10767], "priority": 6}
]
```

**文件推导类型**（resolution_tier）：
```json
[
  {"value": "4k",    "label": "4K",    "min_width": 3840},
  {"value": "1080p", "label": "1080P", "min_width": 1920},
  {"value": "720p",  "label": "720P",  "min_width": 1280},
  {"value": "sd",    "label": "标清",  "min_width": 0}
]
```

### 8 个维度完整默认数据

| name | label | source_type | is_enabled | required_tier | tmdb_field | color | description |
|------|-------|-------------|------------|---------------|------------|-------|-------------|
| media_type | 影视类型 | tmdb_ai | 1 | free | - | #3b82f6 | 区分电影和电视剧，决定目录结构形态 |
| documentary | 是否纪录片 | ai | 1 | free | - | #f59e0b | 将纪录片从虚构作品中分离 |
| restricted_level | 限制级分类 | ai | 1 | free | - | #ec4899 | 按年龄分级隔离成人内容 |
| animation | 是否动漫 | ai | 0 | free | - | #8b5cf6 | 将动漫/动画从真人作品中分离 |
| region | 地区 | tmdb | 0 | pro | origin_country | #10b981 | 按制片地区分拣（亚洲/欧美/欧洲） |
| origin_lang | 原始语言 | tmdb | 0 | pro | original_language | #06b6d4 | 按原始语言分拣（中/英/日/韩） |
| resolution_tier | 分辨率等级 | file | 0 | pro | - | #f97316 | 按视频分辨率分拣（4K/1080P/720P） |
| broad_genre | 类型 | tmdb_ai | 0 | premium | genres | #ef4444 | 按影视类型分拣（恐怖/科幻/动作/喜剧/剧情） |

### 权限层级设计

| 层级 | 可用维度 | 说明 |
|------|---------|------|
| free | media_type, documentary, restricted_level, animation | 基础分类，免费使用 |
| pro | + region, origin_lang, resolution_tier | 高级分拣，需 Pro 许可 |
| premium | + broad_genre | 完整功能，需 Premium 许可 |

## TMDB 标准 Genre ID 映射表

### Movie Genres

| TMDB ID | 英文名 | 中文名 | → broad_genre |
|---------|--------|--------|---------------|
| 28 | Action | 动作 | action |
| 12 | Adventure | 冒险 | action |
| 16 | Animation | 动画 | *(由 animation 维度处理)* |
| 35 | Comedy | 喜剧 | comedy |
| 80 | Crime | 犯罪 | drama |
| 99 | Documentary | 纪录片 | *(由 documentary 维度处理)* |
| 18 | Drama | 剧情 | drama |
| 10751 | Family | 家庭 | drama |
| 14 | Fantasy | 奇幻 | scifi |
| 36 | History | 历史 | drama |
| 27 | Horror | 恐怖 | horror |
| 10402 | Music | 音乐 | other |
| 9648 | Mystery | 悬疑 | horror |
| 10749 | Romance | 爱情 | drama |
| 878 | Science Fiction | 科幻 | scifi |
| 10770 | TV Movie | 电视电影 | drama |
| 53 | Thriller | 惊悚 | horror |
| 10752 | War | 战争 | action |
| 37 | Western | 西部 | action |

### TV Genres（Movie 之外新增的）

| TMDB ID | 英文名 | 中文名 | → broad_genre |
|---------|--------|--------|---------------|
| 10759 | Action & Adventure | 动作冒险 | action |
| 10762 | Kids | 儿童 | *(不映射)* |
| 10763 | News | 新闻 | other |
| 10764 | Reality | 真人秀 | other |
| 10765 | Sci-Fi & Fantasy | 科幻奇幻 | scifi |
| 10766 | Soap | 肥皂剧 | drama |
| 10767 | Talk | 脱口秀 | other |
| 10768 | War & Politics | 战争政治 | action |

### 映射优先级（从高到低）

```
1. horror  ← TMDB: Horror(27), Mystery(9648), Thriller(53)
2. scifi   ← TMDB: Science Fiction(878), Fantasy(14), Sci-Fi & Fantasy(10765)
3. action  ← TMDB: Action(28), Adventure(12), War(10752), Western(37), Action & Adventure(10759), War & Politics(10768)
4. comedy  ← TMDB: Comedy(35)
5. drama   ← TMDB: Drama(18), Romance(10749), Crime(80), History(36), Family(10751), Soap(10766), TV Movie(10770)
6. other   ← TMDB: Music(10402), News(10763), Reality(10764), Talk(10767)
```

取值策略：TMDB 返回的 genres 列表中，按优先级从高到低，第一个匹配到的 broad_genre 值即为结果。

示例：
- 林正英僵尸片 → TMDB: [Comedy(35), Horror(27)] → horror 优先级 > comedy → **horror**
- 星际穿越 → TMDB: [Drama(18), Science Fiction(878)] → scifi 优先级 > drama → **scifi**
- 泰坦尼克号 → TMDB: [Drama(18), Romance(10749)] → drama → **drama**

## 维度 AI 提示词设计

每个维度在数据库中存储独立的 AI 提示词，AI 刮削时动态拼接。

### media_type（影视类型）
```
请判断这是电影（movie）还是电视剧（tv）。如果有季集信息（S01E01格式）则为电视剧；如果是完整独立故事则为电影。
```

### documentary（是否纪录片）
```
请判断是否为纪录片（true/false）。纪录片是以真实事件、人物、自然为主题的非虚构影视作品，包括自然纪录片、历史纪录片、社会纪录片等。
```

### animation（是否动漫）
```
请判断是否为动漫/动画作品（true/false）。包括日本动画、中国动画、欧美动画电影等。以动画形式制作的作品均属于此类。
```

### restricted_level（限制级分类）
```
请判断内容的年龄分级：0-6（幼儿/儿童内容）、7-12（家庭向，适合全家观看）、13-15（青少年向，可能含轻微暴力或恐怖）、17+（成人内容，含明显暴力、色情或恐怖元素）。
```

### region（地区）— TMDB 未命中时 AI 兜底
```
请判断该影视作品的主要制片地区：asia（中日韩等亚洲地区）、western（美英澳等英语国家）、european（法德意西俄等欧洲国家）、other（其他地区）。根据标题语言、制作方、内容风格等综合判断。
```

### origin_lang（原始语言）— TMDB 未命中时 AI 兜底
```
请判断该影视作品的原始语言：zh（中文）、en（英语）、ja（日语）、ko（韩语）、other（其他语言）。根据标题和内容判断。
```

### broad_genre（类型）— TMDB 未命中时 AI 兜底
```
请判断该影视作品的主要类型：horror（恐怖/惊悚）、scifi（科幻/奇幻）、action（动作/冒险/战争）、comedy（喜剧）、drama（剧情/爱情/犯罪/历史）、other（其他）。如果同时属于多个类型，选择风格最鲜明突出的那个。
```

## 维度数据消费者

| 消费者 | 需要读的字段 | 当前从哪读 | 改造要点 |
|--------|-------------|-----------|----------|
| **llm_scraper.py** | name, values, ai_prompt, is_enabled | config.yaml + 代码硬编码 | 从 DB 读已启用维度，动态拼接 AI 提示词 |
| **metadata_scraper.py** | name, source_type, tmdb_field, value_list | 代码硬编码映射 | 从 DB 读映射规则，动态做 TMDB→维度值转换 |
| **file_analyzer.py**（新增） | name, source_type='file', value_list | 不存在 | 新模块，ffprobe 读分辨率，按 min_width 分桶 |
| **classifier.py** | name | config.yaml | 已支持任意维度名，零改动 |
| **pipeline.py** | 调用上述模块 | - | 协调三个来源的维度填充顺序 |
| **api_server.py** | 全部字段 | 分散 | 新增 GET/PUT /api/dimensions 端点 |
| **前端 path-rules.js** | name, label, values | 硬编码 FIXED_DIMENSIONS | 从 API 动态读取已启用维度 |
| **前端 tasks.js** | name, label, value labels, color | 硬编码 DIMENSION_LABELS | 从 API 动态读取 |
| **前端 tasks.css** | color | 硬编码颜色类 | 动态生成样式或用 inline style |
| **config_validator.py** | name（白名单） | 硬编码 EXPECTED_DIMENSION_NAMES | 从 DB 读取，消除白名单 |

## 维度填充流程（改造后）

```
文件进入流水线
  │
  ├─ Step 1: file_analyzer 分析文件元数据
  │    → resolution_tier (ffprobe 读取，确定性，仅当维度已启用时执行)
  │
  ├─ Step 2: TMDB 查询（如果启用）
  │    → region (origin_country 映射，仅当维度已启用时)
  │    → origin_lang (original_language 取值，仅当维度已启用时)
  │    → broad_genre (genres 优先级映射，仅当维度已启用时)
  │    → media_type (movie/tv 判断)
  │
  ├─ Step 3: AI 刮削（填充 TMDB 未覆盖的已启用维度）
  │    → documentary (AI 判断)
  │    → restricted_level (AI 判断)
  │    → animation (AI 判断，仅当维度已启用时)
  │    → TMDB 未命中的已启用维度由 AI 兜底
  │
  └─ 合并所有维度 → dimensions dict → classifier 匹配 path_rules
```

## 维度 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/dimensions | 获取所有维度定义（含未启用的） |
| GET | /api/dimensions/enabled | 获取已启用的维度定义 |
| GET | /api/dimensions/{name} | 获取单个维度定义 |
| PUT | /api/dimensions/{name} | 更新维度定义（AI 提示词、映射规则、颜色等） |
| POST | /api/dimensions/{name}/enable | 启用维度（检查 required_tier 权限） |
| POST | /api/dimensions/{name}/disable | 禁用维度 |

## 会员权限预留设计

### 数据库预留

```sql
-- dimensions 表的 required_tier 字段
required_tier TEXT DEFAULT 'free'  -- free / pro / premium

-- 未来可新增的许可证表（暂不实现）
-- CREATE TABLE license (
--     key_hash TEXT PRIMARY KEY,     -- 许可证密钥哈希
--     tier TEXT NOT NULL,            -- free / pro / premium
--     device_id TEXT,                -- 绑定设备指纹
--     activated_at TEXT,
--     expires_at TEXT,
--     features TEXT DEFAULT '{}'     -- JSON: 额外功能开关
-- );
```

### 代码预留检查点

```python
# 权限检查函数（暂全部返回 True，未来实现许可证验证）
def check_tier_access(required_tier: str) -> bool:
    # TODO: 实现许可证验证
    # 1. 读取本地许可证文件或数据库
    # 2. 验证密钥有效性
    # 3. 检查是否过期
    # 4. 返回是否有权访问
    return True  # 预留阶段全部放行
```

### API 预留

```python
# 启用维度时检查权限
@api_route('/dimensions/<name>/enable', methods=['POST'])
def enable_dimension(name):
    dim = get_dimension(name)
    if dim['required_tier'] != 'free':
        if not check_tier_access(dim['required_tier']):
            return {'code': 403, 'message': f'该维度需要 {dim["required_tier"]} 许可'}
    # ... 启用逻辑
```

### 前端预留

- 维度配置页签中，非 free 层级的维度显示锁图标和所需层级标签
- 点击启用时，如果权限不足，弹出升级提示（暂不实现跳转）
- 预留 `window.__TIER__` 全局变量，存储当前用户层级

### 许可证方案候选（未来选择）

| 方案 | 原理 | 适用场景 |
|------|------|---------|
| 许可证密钥 | 购买后获得密钥，输入系统激活 | 简单直接，离线可用 |
| 在线激活码 | 密钥 + 首次联网绑定设备指纹 | 防止密钥分享 |
| 功能加密密钥 | 密钥内含加密的功能权限，本地解密 | 离线可用，无需服务器 |

## 前端维度配置页签设计

### 页签结构

```
┌─────────────────────────────────────────────────┐
│ 维度配置                                          │
├─────────────────────────────────────────────────┤
│                                                   │
│ ┌─ 已启用维度 ──────────────────────────────────┐ │
│ │  ✅ 影视类型 (media_type)     [编辑] [禁用]   │ │
│ │  ✅ 是否纪录片 (documentary)  [编辑] [禁用]   │ │
│ │  ✅ 限制级分类 (restricted)   [编辑] [禁用]   │ │
│ └───────────────────────────────────────────────┘ │
│                                                   │
│ ┌─ 可添加维度 ──────────────────────────────────┐ │
│ │  ➕ 是否动漫 (animation)      [添加]          │ │
│ │  🔒 地区 (region)            PRO [添加]      │ │
│ │  🔒 原始语言 (origin_lang)   PRO [添加]      │ │
│ │  🔒 分辨率等级 (resolution)  PRO [添加]      │ │
│ │  🔒 类型 (broad_genre)       PREMIUM [添加]  │ │
│ └───────────────────────────────────────────────┘ │
│                                                   │
│ ┌─ 维度编辑面板（点击编辑后展开）────────────────┐ │
│ │  影视类型 - AI 提示词:                         │ │
│ │  ┌──────────────────────────────────────────┐ │ │
│ │  │ 请判断这是电影还是电视剧...                │ │ │
│ │  └──────────────────────────────────────────┘ │ │
│ │  值域: movie / tv                             │ │
│ │  来源: AI + TMDB                              │ │
│ └───────────────────────────────────────────────┘ │
│                                                   │
│ ┌─ 映射配置（TMDB 类型维度展开）────────────────┐ │
│ │  地区映射:                                     │ │
│ │  亚洲 ← CN, HK, TW, JP, KR  [+添加国家]      │ │
│ │  欧美 ← US, CA, AU, NZ, GB   [+添加国家]      │ │
│ │  欧洲 ← FR, DE, IT, ...      [+添加国家]      │ │
│ │  其他 ← (兜底)                                │ │
│ └───────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### 入库规则页签联动

- 入库规则页签的维度条件选择器只显示已启用的维度
- 维度值从 API 动态获取（下拉框枚举）
- 任务列表卡片的维度标签只显示已启用的维度

## config.yaml 迁移

- 删除 `dimensions` 段，所有维度定义从数据库读取
- `path_rules` 保留在 config.yaml 中（条件和模板不变）
- 首次启动时，`init_db()` 中 seed 8 个维度默认数据
- 已有 config.yaml 中的 dimensions 配置不再读取

## Open Questions

1. **ffprobe 依赖检测**：启动时检测 ffprobe 是否可用，不可用时尝试自动安装（apt-get install ffmpeg），安装失败则 resolution_tier 维度标记为不可用
2. **genre 映射配置 UI**：TMDB genre → broad_genre 映射关系在配置界面的编辑交互设计
3. **region 映射配置 UI**：国家代码 → region 的映射关系编辑交互设计
4. **会员许可证实现时机**：当前预留 required_tier 字段和检查点，完整许可证系统何时实现
5. **维度禁用影响**：禁用维度后，已有 path_rules 中引用该维度的规则如何处理（忽略？报错？）
6. **TMDB 未命中时的 AI 提示词**：TMDB 类型维度在 TMDB 未命中时的 AI 兜底提示词效果如何

## Out of Scope

- 自定义维度（用户自定义维度名+值域+提示词）
- 片源类型维度（BluRay/WEB-DL/HDTV）— 从文件名解析不可靠
- 系列维度（漫威宇宙等）— 穷举型，不适合做维度
- 年份/评分/导演/演员等连续值或穷举型分类
- 维度组合推荐（根据用户已有 path_rules 推荐缺失规则）
- 完整许可证系统实现（仅预留）

## Next Steps

- `/plan` 创建实施计划
- 优先实现数据库表 + seed 数据 + API 端点
- 前端维度配置页签开发
- 前端维度动态化重构（消除硬编码）
- 新增 file_analyzer 模块（ffprobe 分辨率检测）
- 改造 metadata_scraper 支持 TMDB 维度映射
- 改造 llm_scraper 从 DB 动态读取维度提示词

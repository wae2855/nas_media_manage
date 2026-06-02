# 置信度计算引擎 — 完整技术文档

> 本文档详细描述 影音库AI智能整理的置信度计算逻辑、完整计算过程、配置参数说明和计算示例。
> 对应源码：`media_importer/scraper/confidence_engine.py`、`media_importer/scraper/metadata_scraper.py`

---

## 1. 整体架构

### 1.1 设计理念

置信度分数的核心是**搜索置信度**——即「系统找到的 TMDB 条目是否是正确的那个」。

数据置信度简化为**二元判断**：用户信任该来源的维度 → 1.0（不干预），不信任 → 0（标记需人工审核）。

```
final = search_conf × data_gate

search_conf = T × R_dynamic          （搜索置信度：标题匹配 × 结果数惩罚）
data_gate   = 全部信任 ? 1.0 : 0     （数据门控：任一维度来源不信任则拦截）
```

- `data_gate = 1.0`：所有维度来源都被用户信任，置信度分数 = search_conf
- `data_gate = 0`：有维度来源不被信任，任务标记为 `NEEDS_REVIEW`

### 1.2 两种计算模式

| 模式 | 触发条件 | 计算公式 | 说明 |
|------|----------|----------|------|
| **TMDB+AI 模式** | TMDB 搜索有结果且 T ≥ tmdb_match_threshold | `final = search_conf × data_gate` | 主路径，TMDB 提供结构化数据 |
| **纯 AI 模式** | TMDB 搜索无结果，或 T 始终低于阈值 | `final = objective_cap × data_gate` | 兜底路径，AI 独立刮削 |

### 1.3 完整计算流程

```
文件名输入
  │
  ▼
① 正则清洗 (FilenameCleaner.clean)
  │  输出: clean_title, year, season, episode
  │
  ▼
② TMDB 搜索 (_search_tmdb_with_match)
  │  用 clean_title + year 搜索 TMDB
  │  对每个结果计算 T 值，取 T 最高的
  │  若年份过滤导致无结果，自动去掉年份重试
  │
  ├─ T ≥ 0.85 (tmdb_match_threshold) ──→ 走 TMDB+AI 模式
  │
  ├─ 0 < T < 0.85 ──→ ③ AI Fallback (低匹配)
  │                    │  调用 AI 清洗文件名
  │                    │  用 AI 清洗后的标题 + 原年份重新搜索 TMDB
  │                    │  取 T 更高的结果
  │                    │
  │                    ├─ 新 T ≥ 0.85 ──→ 走 TMDB+AI 模式
  │                    └─ 新 T < 0.85 ──→ 走纯 AI 模式
  │
  └─ T = 0 (无结果) ──→ ③ AI Fallback (无结果)
                         │  调用 AI 清洗文件名
                         │  用 AI 清洗后的标题 + 不带年份搜索 TMDB
                         │
                         ├─ T ≥ 0.85 ──→ 走 TMDB+AI 模式
                         └─ T < 0.85 或无结果 ──→ 走纯 AI 模式
```

### 1.4 AI Fallback 机制

AI Fallback 在两种场景下触发：

**场景 A：TMDB 有结果但匹配不够（T < 0.85）**

1. 调用 `FilenameCleaner.ai_clean()` 让 LLM 从文件名提取标题
2. 用 AI 提取的标题 + 原始年份重新搜索 TMDB
3. 如果新搜索的 T 值更高，采用新结果
4. 如果 T 值仍然不够，放弃 TMDB，走纯 AI 刮削路径

**场景 B：TMDB 完全无结果（T = 0）**

1. 调用 `FilenameCleaner.ai_clean()` 让 LLM 从文件名提取标题
2. 用 AI 提取的标题、**不带年份**（避免错误年份过滤）重新搜索 TMDB
3. 如果找到匹配且 T ≥ 0.85，走 TMDB+AI 模式
4. 否则走纯 AI 刮削路径

**设计意图**：
- 场景 A 处理正则清洗不够精确的情况（如模糊匹配）
- 场景 B 处理正则清洗导致错误的情况（如年份误提取），去年份重搜可以绕过错误过滤
- 阈值 0.85 比较积极触发 AI，避免低质量匹配直接进入计算

---

## 2. 文件名清洗 (FilenameCleaner)

### 2.1 行业参考

专业影视管理软件的标题提取策略：

| 软件 | 策略 | 优势 | 局限 |
|------|------|------|------|
| **Kodi** | 依赖文件夹结构 + NFO 文件。推荐格式 `Movie Name (Year)/Movie Name (Year).mkv`，支持 TMDB ID 内嵌 `{tmdb=335984}` | 最精确，完全避免解析 | 需要用户预先整理目录结构 |
| **TinyMediaManager** | 正则提取 + 目录结构辅助。先按目录名识别，目录名不明确时按文件名正则提取。支持 NFO 优先 | 多层回退，实用性强 | 依赖目录规范 |
| **Infuse** | 内建智能解析器。结合目录结构 + 文件名模式匹配 + 在线数据库查询验证 | 对非标准命名有较好容错 | 闭源，无法参考实现 |
| **Plex** | 类似策略，目录结构优先，文件名正则辅助 | 成熟稳定 | 同上 |

**我们的差异化定位**：

与上述软件不同，我们的系统面向的是**未经整理的源目录**——文件名混杂各种格式（发布组、编码信息、广告等），没有标准目录结构。因此我们的清洗必须更激进：

1. **正则清洗**（步骤 1-16）：处理标准场景，速度快
2. **AI 清洗**（Fallback）：处理正则无法覆盖的非标准场景，更智能

### 2.2 清洗顺序

清洗按以下固定顺序执行，顺序很重要（例如发布组提取必须在编解码器移除之前）：

| 步骤 | 操作 | 正则/方法 | 说明 |
|------|------|-----------|------|
| 1 | 移除扩展名 | `_EXTENSION_PATTERN` | `.mkv`, `.mp4` 等 |
| 2 | 移除制作组标签 | `_RELEASE_GROUP_START` | `[EPSiLON]` 等方括号开头 |
| 3 | **提取发布组** | `-\s*([A-Za-z0-9_...]+)$` | 在编解码器移除之前提取 `-FGT` 等 |
| 4 | 移除多集标记 | `_MULTI_EP` | `S01E01E02` |
| 5 | 移除季集标记 | `_SEASON_EPISODE` | `S01E01`，同时提取 season/episode |
| 6 | 提取独立季号 | `_SEASON_ONLY` | `S05`（不带 E），提取 season |
| 7 | 提取括号年份 | `_YEAR_PAREN` | `(1994)`，优先于点号年份 |
| 8 | 提取点号年份 | `_YEAR_PATTERN` | `.1999.` 或 `_1999_` |
| 9 | 移除分辨率 | `_RESOLUTION_PATTERNS` | `1080p`, `2160p`, `4K` 等 |
| 10 | 移除源/编解码器 | `_SOURCE_CODEC_PATTERNS` | `BluRay`, `x264`, `DTS-HD.MA.5.1` 等 |
| 11 | 移除版本标签 | `_EDITION_PATTERN` | `25th.Anniversary.Edition` 等 |
| 12 | 移除完整广告 | `_AD_FULL_PATTERN` | `www.movie.com-加群123456` |
| 13 | 移除广告标记 | `_AD_PATTERN` | `.com`, `.net`, `.org` |
| 14 | 移除方括号内容 | `_BRACKET_CONTENT` | 残留的 `[...]` |
| 15 | 移除尾部发布组 | `_RELEASE_GROUP_TAIL` | 大写缩写如 `EVOLVE` |
| 16 | 整理空格 | 替换分隔符为空格 | `[.\s_-]+` → 空格 |

### 2.3 发布组提取的关键逻辑

发布组提取在步骤 3（编解码器移除之前）执行，原因：

- 编解码器正则的前缀 `[.\s_-]` 会吃掉 `-` 前面的分隔符
- 如果先移除编解码器，`-FGT` 变成 `FGT` 无法被尾部发布组正则匹配

**防误判机制**：

- `_CODEC_PREFIX_RE`：防止编解码器名称被误判为发布组（如 `-DTS`, `-Atmos`）
- `_AD_FULL_PATTERN`：防止广告域名后的内容被误判为发布组（如 `-加群123456`）

### 2.4 清洗示例

| 输入文件名 | clean_title | year | season | episode | 去除项 |
|-----------|-------------|------|--------|---------|--------|
| `The.Matrix.1999.1080p.BluRay.x264.DTS-FGT.mkv` | `The Matrix` | 1999 | — | — | 发布组=FGT, 年份=1999, 1080p, BluRay, x264, DTS |
| `Game.of.Thrones.S01E01.720p.HDTV.x264-EVOLVE.mkv` | `Game of Thrones` | — | 1 | 1 | 季集=S01E01, 720p, HDTV, x264, 发布组=EVOLVE |
| `Breaking.Bad.S05.Complete.1080p.BluRay.x264-FGT.mkv` | `Breaking Bad` | — | 5 | — | 季=S05, Complete, 1080p, BluRay, x264, 发布组=FGT |
| `肖申克的救赎 (1994).1080p.BluRay.FLAC.2.0.mkv` | `肖申克的救赎` | 1994 | — | — | 年份=1994, 1080p, BluRay, FLAC.2.0 |
| `Blade.Runner.2049.2017.1080p.BluRay.FLAC.2.0.mkv` | `Blade Runner 2017` | **2049**⚠️ | — | — | 年份=2049⚠️, 1080p, BluRay, FLAC.2.0 |

> ⚠️ `Blade.Runner.2049` 中 `2049` 是电影名的一部分，但正则会优先提取第一个匹配的年份值。`2017`（实际年份）残留在 clean_title 中。这种场景通过 AI Fallback 场景 B 处理。

### 2.5 标题清洗的优化方向（未来改进）

当前清洗基于 16 步正则，覆盖大部分标准场景。可能的改进方向：

1. **优先目录名**：如果文件所在目录名比文件名更干净（如 `The Matrix (1999)/The.Matrix.1999.mkv`），优先用目录名做标题提取。这是 Kodi/TMM 推荐的方式。
2. **NFO 优先**：如果同目录有 `.nfo` 文件，直接从中读取 TMDB ID，跳过整个清洗和搜索流程。
3. **年份验证**：提取年份后，检查年份是否在合理范围（1888~当前年+2），过滤掉标题中误识别的数字（如 `2049`）。

---

## 3. 标题匹配分 T (TitleMatcher)

### 3.1 匹配级别

T 值表示「清洗后的标题与 TMDB 返回标题的匹配程度」，分为 7 个级别：

| 级别 | 条件 | T 值 | 配置键 | 默认值 |
|------|------|------|--------|--------|
| **L1** | 精确匹配 + 年份一致 | 固定值 | `title_exact_with_year` | 1.0 |
| **L2** | 精确匹配 + 有季号 | 固定值 | `title_exact_with_season` | 0.9 |
| **L3** | 精确匹配 + 无年份/季号 | 固定值 | `title_exact_no_year` | 0.7 |
| **L4** | 精确匹配 + 年份不匹配 | 固定值 | `title_exact_year_mismatch` | 0.4 |
| **L5** | 模糊匹配 + 年份一致 | `best_sim` | — | 相似度值 |
| **L6** | 模糊匹配 + 无年份/年份不匹配 | `best_sim × fuzzy_coeff` | `title_fuzzy_year_coeff` | 0.7 |
| **L7** | 相似度低于阈值 | 0.0 | `title_min_similarity` | 0.3 |

### 3.2 匹配逻辑流程

```
normalize(clean_title) vs normalize(tmdb_title/original_title)
  │
  ├─ 精确匹配 (normalized 相等)?
  │   ├─ 有年份?
  │   │   ├─ 年份一致 → L1 (T=1.0)
  │   │   └─ 年份不一致 → L4 (T=0.4)
  │   ├─ 有季号? → L2 (T=0.9)
  │   └─ 无年份无季号 → L3 (T=0.7)
  │
  └─ 模糊匹配 (SequenceMatcher)
      ├─ 相似度 < 0.3 → L7 (T=0.0, 无匹配)
      ├─ 有年份且一致 → L5 (T=best_sim)
      └─ 无年份或年份不一致 → L6 (T=best_sim × 0.7)
```

### 3.3 标题规范化

匹配前对标题进行规范化处理，去除空格、点号、连字符、下划线，并转为小写：

```python
def _normalize_title(title):
    return title.lower().replace(' ', '').replace('.', '').replace('-', '').replace('_', '')
```

### 3.4 相似度计算

使用 Python 标准库 `difflib.SequenceMatcher` 计算规范化后标题的相似度比值，取与 TMDB `title` 和 `original_title` 中较高的值。

### 3.5 L2 级别的设计意图

剧集（TV）通常没有年份信息（TMDB 的 `first_air_date` 可能缺失或不准确），但有季号。L2 级别让「精确匹配 + 有季号」的剧集获得 0.9 的 T 值，高于 L3（0.7），低于 L1（1.0），合理反映其匹配可信度。

---

## 4. 搜索结果数惩罚 R

### 4.1 基础公式

R 值表示「搜索结果数量对匹配可信度的影响」。结果越多，说明搜索词越模糊，匹配越不确定。

| 公式 | 表达式 | N=1 | N=3 | N=5 | N=10 |
|------|--------|-----|-----|-----|------|
| inverse | `R = 1/N` | 1.0 | 0.33 | 0.2 | 0.1 |
| **log** (默认) | `R = 1/log₂(N+1)` | 1.0 | 0.5 | 0.39 | 0.29 |
| sqrt | `R = 1/√N` | 1.0 | 0.58 | 0.45 | 0.32 |
| flat | `R = 1.0` | 1.0 | 1.0 | 1.0 | 1.0 |

其中 N = min(total_results, R_max_results_cap)，受 `R_min_value` 下限保护。

### 4.2 动态 R 调节

**核心思想**：匹配质量越高，结果数惩罚越轻；匹配质量越低，惩罚越重。

当 T 值超过 `R_T_floor`（默认 0.5）时，R 不再是纯粹的基础值，而是向 1.0 方向动态提升：

```
α = ((T - R_T_floor) / (1 - R_T_floor)) ^ R_T_curve

R_dynamic = R_base × (1 - α) + α
```

**参数说明**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `R_T_floor` | 0.5 | T 值超过此值时开始动态提升 R |
| `R_T_curve` | 1.5 | 调节陡度。1.0=线性，1.5=适中，2.0=激进 |

**直觉理解**：

- 当 T = R_T_floor 时，α = 0，R = R_base（无提升）
- 当 T = 1.0 时，α = 1，R = 1.0（完全提升，消除结果数惩罚）
- 当 T 在两者之间时，α 在 0~1 之间，R 在 R_base~1.0 之间

**示例**（R_base = 0.39，即 log 公式 N=5）：

| T 值 | α (curve=1.5) | R_dynamic | 说明 |
|------|---------------|-----------|------|
| 0.4 | 0 (T < floor) | 0.39 | 不提升 |
| 0.5 | 0 (T = floor) | 0.39 | 刚好不提升 |
| 0.7 | 0.24 | 0.54 | 轻微提升 |
| 0.9 | 0.64 | 0.75 | 显著提升 |
| 1.0 | 1.0 | 1.0 | 完全消除惩罚 |

### 4.3 search_conf 计算

```
search_conf = T × R_dynamic
```

---

## 5. 数据门控 data_gate

### 5.1 设计思路

**简化原则**：数据置信度不再做复杂的聚合计算。用户只关心两件事：

1. **搜索是否正确** → 由 `search_conf` 回答
2. **维度数据是否可信** → 由用户按来源直接决定

`data_gate` 是一个**二元门控**：

| data_gate | 含义 | 结果 |
|-----------|------|------|
| **1.0** | 所有维度来源都被用户信任 | `final = search_conf`（置信度分数 = 搜索质量） |
| **0** | 至少一个维度来源不被信任 | 任务标记为 `NEEDS_REVIEW`（需人工审核） |

### 5.2 维度来源

每个维度的数据可能来自不同来源：

| 来源 | 说明 | 示例 |
|------|------|------|
| `tmdb` | TMDB API 结构化字段映射 | genres → animation, media_type → movie |
| `ai` | LLM 刮削判断 | AI 返回的 restricted_level |
| `file` | 从视频文件本身分析 | 分辨率、编码格式 |
| `douban` | 豆瓣 API（未来） | 中文评分、评论 |
| `missing` | 维度值缺失 | 没有任何来源提供数据 |

### 5.3 来源信任配置

用户在「维度来源信任」配置界面为每个维度的每个来源设置是否信任：

```yaml
confidence:
  dimensions:
    media_type:
      trusted_sources: ["tmdb", "ai"]     # 信任 TMDB 和 AI 的 media_type 判断
    restricted_level:
      trusted_sources: ["tmdb"]            # 只信任 TMDB，AI 判断的需审核
    animation:
      trusted_sources: ["tmdb"]            # 只信任 TMDB 的动画判断
    region:
      trusted_sources: ["tmdb", "ai"]      # TMDB 和 AI 都信任
```

**计算逻辑**：

```python
for dim_name, dim_value in dimensions.items():
    source = get_source(dim_value)          # 获取该维度值的来源
    trusted = source in dim_config.trusted_sources
    
    if not trusted:
        data_gate = 0                        # 标记需人工审核
        untrusted_dims.append((dim_name, source))
        break                                # 任一不信任即拦截
```

### 5.4 按维度独立配置来源优先级与信任

每个维度独立配置自己的来源列表，列表同时表达两项信息：**优先级**（顺序）和**信任**（trusted 字段）。

#### 5.4.1 配置结构

```yaml
confidence:
  dimensions:
    media_type:
      sources:
        - source: "tmdb"
          trusted: true
        - source: "ai"
          trusted: true
        - source: "file"
          trusted: true
    restricted_level:
      sources:
        - source: "tmdb"
          trusted: true
        - source: "ai"
          trusted: false
        - source: "file"
          trusted: false
```

**取值逻辑**：

1. 按该维度的 `sources` 列表顺序（优先级从高到低）逐个检查
2. 跳过不可信（`trusted: false`）的来源
3. 取第一个**可信且有数据**的来源作为该维度的值
4. 如果所有可信来源都无数据，取值来源为 `missing`，触发门控拦截
5. 如果最高优先级的可信来源有数据，使用该来源，判断信任 → 通过

#### 5.4.2 优先级与信任的关系

优先级决定「用谁的数据」，信任决定「这个数据能不能自动通过」。两者在同一列表中配合工作：

```
restricted_level:
  sources:
    - source: "tmdb"    trusted: true     ← 优先用，且信任
    - source: "ai"      trusted: false    ← 不可信，跳过
    - source: "file"    trusted: false    ← 不可信，跳过

取值流程：
┌──────────┬────────────┬──────────────────────────────────────┐
│ TMDB 数据 │ 最终取值    │ 信任判断                              │
├──────────┼────────────┼──────────────────────────────────────┤
│ ✅ 有     │ TMDB(优先)  │ 信任 ✅ → data_gate=1                 │
│ ❌ 无     │ missing     │ 无可信来源有数据 → 需审核 ⚠️ gate=0    │
└──────────┴────────────┴──────────────────────────────────────┘
```

**不可信来源有数据时**：

```
media_type:
  sources:
    - source: "tmdb"    trusted: true     ← 优先用，且信任
    - source: "ai"      trusted: true     ← 第二优先，也信任
    - source: "file"    trusted: false    ← 不可信，跳过

┌──────────┬──────────┬────────────┬──────────────────────────────┐
│ TMDB 数据 │ AI 数据   │ 最终取值    │ 信任判断                      │
├──────────┼──────────┼────────────┼──────────────────────────────┤
│ ✅ 有     │ ✅ 有     │ TMDB(优先)  │ 信任 ✅                       │
│ ❌ 无     │ ✅ 有     │ AI          │ 信任 ✅                       │
│ ❌ 无     │ ❌ 无     │ missing     │ 无可信数据 → 需审核 ⚠️ gate=0  │
└──────────┴──────────┴────────────┴──────────────────────────────┘
```

#### 5.4.3 多来源场景示例

**场景：用户接入了 TMDB + 豆瓣**

```yaml
confidence:
  dimensions:
    media_type:
      sources:
        - source: "tmdb"
          trusted: true
        - source: "douban"
          trusted: true
        - source: "ai"
          trusted: true
    restricted_level:
      sources:
        - source: "tmdb"
          trusted: true
        - source: "douban"
          trusted: false
        - source: "ai"
          trusted: false
    region:
      sources:
        - source: "douban"
          trusted: true
        - source: "tmdb"
          trusted: true
        - source: "ai"
          trusted: true
    genres:
      sources:
        - source: "tmdb"
          trusted: true
        - source: "douban"
          trusted: true
        - source: "ai"
          trusted: true
```

- `media_type`：TMDB 优先，豆瓣次之，AI 再次 — 全部可信
- `restricted_level`：只信 TMDB 的分级，豆瓣/AI 提供的分级跳过不取
- `region`：豆瓣优先于 TMDB（用户更信任豆瓣的产地信息），两者都可信
- `genres`：TMDB 优先，豆瓣和 AI 也都可信

#### 5.4.4 未来扩展来源

新增来源只需一步：在各维度的 `sources` 列表中添加新来源条目。

系统自动处理：新来源的数据在 `dimension_manager` 中映射后，按各维度的优先级参与取值。

| 来源标识 | 说明 | 接入状态 |
|---------|------|---------|
| `tmdb` | TMDB API 结构化字段 | ✅ 已接入 |
| `ai` | LLM 刮削判断 | ✅ 已接入 |
| `file` | 视频文件分析（分辨率等） | ✅ 已接入 |
| `douban` | 豆瓣 API | 🔜 未来 |
| `imdb` | IMDb API | 🔜 未来 |
| `missing` | 维度值缺失 | — 特殊值 |

### 5.5 缺失维度处理

如果维度值缺失（所有来源都没有提供数据）：

- 维度在 `trusted_sources` 中不包含 `"missing"` → 需审核
- 维度在 `trusted_sources` 中包含 `"missing"` → 信任（通常不建议）

---

## 6. 纯 AI 模式

### 6.1 触发条件

- TMDB 搜索完全无结果
- TMDB 搜索有结果但 T < 0.85，且 AI Fallback 后 T 仍 < 0.85

### 6.2 objective_cap 计算

纯 AI 模式下，搜索置信度被替换为 `objective_cap`（客观上限），基于 AI 标题与文件名的相似度：

```
sim = similarity(clean_title, llm_title)

if sim ≥ ai_cap_high_similarity (0.7):
    objective_cap = sim                    # 高相似度，直接用相似度值
elif sim ≥ ai_cap_low_similarity (0.3):
    objective_cap = sim × ai_cap_low_coeff # 低相似度，打折
else:
    objective_cap = ai_cap_no_match (0.2)  # 完全不匹配
```

如果 LLM 未返回标题：`objective_cap = ai_cap_no_title (0.3)`

### 6.3 最终计算

```
final = objective_cap × data_gate
```

纯 AI 模式下 `data_gate` 逻辑不变：如果 AI 来源不被信任，直接标记需审核。

---

## 7. 决策判定

### 7.1 判定规则

| 条件 | 状态 | 说明 |
|------|------|------|
| data_gate = 0 | **NEEDS_REVIEW** | 有维度来源不被信任，必须人工审核 |
| final ≥ pass_threshold (0.8) | **PASS** | 自动通过，无需人工干预 |
| final ≥ confirm_threshold (0.5) | **CONFIRMING** | 需人工确认后入库 |
| final ≥ review_threshold (0.3) | **NEEDS_REVIEW** | 需审核 |
| final < review_threshold (0.3) | **FAILED** | 失败 |

### 7.2 判定优先级

1. **先检查 data_gate**：如果不信任，直接 `NEEDS_REVIEW`
2. **再检查 search_conf/objective_cap**：按阈值区间判定

---

## 8. 完整配置参数一览

### 8.1 决策阈值

| 参数 | 配置键 | 默认值 | 说明 |
|------|--------|--------|------|
| 自动通过 | `pass_threshold` | 0.8 | ≥ 此值自动通过 |
| 需确认 | `confirm_threshold` | 0.5 | ≥ 此值需人工确认 |
| 需审核 | `review_threshold` | 0.3 | ≥ 此值需审核，低于此值失败 |

### 8.2 搜索置信度

| 参数 | 配置键 | 默认值 | 说明 |
|------|--------|--------|------|
| TMDB 最低匹配阈值 | `tmdb_match_threshold` | 0.85 | T 低于此值触发 AI Fallback |
| L1 精确+年份 | `title_exact_with_year` | 1.0 | 标题精确匹配且年份一致 |
| L2 精确+季号 | `title_exact_with_season` | 0.9 | 标题精确匹配且含季号 |
| L3 精确无年份 | `title_exact_no_year` | 0.7 | 标题精确但无年份/季号 |
| L4 精确年份不匹配 | `title_exact_year_mismatch` | 0.4 | 标题精确但年份不一致 |
| L5/L6 模糊年份系数 | `title_fuzzy_year_coeff` | 0.7 | 模糊匹配时年份系数 |
| L7 最低相似度 | `title_min_similarity` | 0.3 | 低于此值判为无匹配 |
| R 公式 | `R_formula` | log | inverse/log/sqrt/flat |
| R 结果数上限 | `R_max_results_cap` | 10 | N 超过此值不再增加惩罚 |
| R 下限 | `R_min_value` | 0.1 | R 的最低值 |
| R 动态调节下限 | `R_T_floor` | 0.5 | T 超过此值时 R 开始动态提升 |
| R 动态调节曲线 | `R_T_curve` | 1.5 | 调节陡度 |

### 8.3 数据门控

| 参数 | 配置键 | 默认值 | 说明 |
|------|--------|--------|------|
| 维度来源配置 | `dimensions.<name>.sources` | `[{source:"tmdb",trusted:true}, ...]` | 每个维度独立的来源列表，顺序=优先级，trusted=是否信任 |
| 全局默认优先级 | `source_priority` | `["tmdb", "ai", "file"]` | 维度未配置 sources 时的默认优先级和信任（全部可信） |

> **移除的配置**：`aggregation_method`、`tmdb_dim_confidence`、`file_dim_confidence`、`dim_missing_confidence`、维度 `weight`、维度 `veto_threshold`、维度 `source_confidence` 覆盖、维度 `trusted_sources`（已迁移为 `sources` 列表）。这些在简化方案中不再需要。

> **扩展说明**：未来接入豆瓣等新来源后，各维度的 `sources` 列表中增加 `{source: "douban", trusted: true/false}` 条目即可。系统根据已注册的来源动态生成 UI 标签。

### 8.4 纯 AI 模式参数

| 参数 | 配置键 | 默认值 | 说明 |
|------|--------|--------|------|
| 高相似度上限 | `ai_cap_high_similarity` | 0.7 | AI 标题与文件名高相似度时 |
| 低相似度上限 | `ai_cap_low_similarity` | 0.3 | AI 标题与文件名低相似度时 |
| AI 无标题上限 | `ai_cap_no_title` | 0.3 | LLM 未返回标题时 |
| AI 无匹配上限 | `ai_cap_no_match` | 0.2 | 完全无匹配时 |
| 低相似度衰减系数 | `ai_cap_low_coeff` | 0.5 | 低相似度时的衰减系数 |

---

## 9. 计算示例

### 示例 1：The.Matrix.1999.1080p.BluRay.x264.DTS-FGT.mkv

**步骤 1：文件名清洗**

| 项目 | 值 |
|------|-----|
| 原始文件名 | `The.Matrix.1999.1080p.BluRay.x264.DTS-FGT.mkv` |
| 去除扩展名 | `.mkv` |
| 提取发布组 | `FGT`（在编解码器移除之前） |
| 提取年份 | `1999` |
| 移除分辨率 | `1080p` |
| 移除编解码器 | `BluRay`, `x264`, `DTS` |
| **clean_title** | `The Matrix` |
| **year** | 1999 |
| **season** | — |
| **episode** | — |

**步骤 2：TMDB 搜索**

搜索 `The Matrix` + year=1999，返回 3 个结果，第一个是正确匹配。

| 项目 | 值 |
|------|-----|
| TMDB 标题 | `The Matrix` |
| TMDB 年份 | 1999 |
| total_results | 3 |

**步骤 3：标题匹配 T**

| 项目 | 值 |
|------|-----|
| normalize("The Matrix") | `thematrix` |
| normalize("The Matrix") | `thematrix` |
| 精确匹配 | ✅ |
| 年份一致 | ✅ (1999 = 1999) |
| **级别** | **L1** |
| **T** | **1.0** |

**步骤 4：搜索结果数惩罚 R**

| 项目 | 值 |
|------|-----|
| N | 3 |
| R_base (log) | 1/log₂(4) = 0.5 |
| T > R_T_floor (0.5)? | ✅ |
| α = ((1.0 - 0.5) / (1.0 - 0.5))^1.5 | 1.0 |
| R_dynamic = 0.5 × (1 - 1.0) + 1.0 | **1.0** |

**步骤 5：search_conf**

```
search_conf = T × R = 1.0 × 1.0 = 1.0
```

**步骤 6：data_gate**

所有维度来源都在 trusted_sources 中 → **data_gate = 1.0**

**步骤 7：最终置信度**

```
final = 1.0 × 1.0 = 1.0 → PASS ✅
```

---

### 示例 2：Game.of.Thrones.S01E01.720p.HDTV.x264-EVOLVE.mkv

**步骤 1：文件名清洗**

| 项目 | 值 |
|------|-----|
| clean_title | `Game of Thrones` |
| year | — |
| season | 1 |
| episode | 1 |

**步骤 2：TMDB 搜索**

搜索 `Game of Thrones`（无年份），返回 5 个结果。

**步骤 3：标题匹配 T**

| 项目 | 值 |
|------|-----|
| 精确匹配 | ✅ |
| 有年份? | ❌ |
| 有季号? | ✅ (season=1) |
| **级别** | **L2** |
| **T** | **0.9** |

**步骤 4：搜索结果数惩罚 R**

| 项目 | 值 |
|------|-----|
| N | 5 |
| R_base (log) | 1/log₂(6) = 0.387 |
| T > R_T_floor? | ✅ (0.9 > 0.5) |
| α = ((0.9 - 0.5) / 0.5)^1.5 | 0.8^1.5 = 0.716 |
| R_dynamic = 0.387 × (1 - 0.716) + 0.716 | **0.826** |

**步骤 5：search_conf**

```
search_conf = 0.9 × 0.826 = 0.743
```

**步骤 6：data_gate**

所有维度来源都在 trusted_sources 中 → **data_gate = 1.0**

**步骤 7：最终置信度**

```
final = 0.743 × 1.0 = 0.743 → CONFIRMING (需确认)
```

> 剧集无年份，T=0.9，5个搜索结果导致 R 有一定惩罚，最终落入需确认区间。置信度分数直接反映搜索匹配质量。

---

### 示例 3：Blade.Runner.2049.2017.1080p.BluRay.FLAC.2.0.mkv

**步骤 1：文件名清洗**

| 项目 | 值 |
|------|-----|
| 原始文件名 | `Blade.Runner.2049.2017.1080p.BluRay.FLAC.2.0.mkv` |
| 提取年份 | `2049`（⚠️ 误提取！2049 是电影名的一部分） |
| 移除分辨率 | `1080p` |
| 移除编解码器 | `BluRay`, `FLAC.2.0` |
| **clean_title** | `Blade Runner 2017`（2017 残留在标题中） |
| **year** | **2049**（错误） |

**步骤 2：TMDB 搜索**

搜索 `Blade Runner 2017` + year=2049 → TMDB 无结果。

搜索方法内部自动去掉年份重搜：搜索 `Blade Runner 2017`（无年份）→ 返回若干结果，但匹配度低，best_T < 0.85。

**步骤 3：AI Fallback（场景 B）**

AI 清洗 → 提取标题 `Blade Runner 2049` → 不带年份搜索 TMDB → 找到正确匹配。

**步骤 4：标题匹配 T**

| 项目 | 值 |
|------|-----|
| 精确匹配 | ✅ |
| 搜索时未传年份 | → L3 |
| **T** | **0.7** |

T=0.7 < 0.85 → 走纯 AI 模式。

**步骤 5：纯 AI 模式**

```
sim = similarity("Blade Runner 2017", "Blade Runner 2049") ≈ 0.85
sim ≥ 0.7 → objective_cap = 0.85
```

**步骤 6：data_gate**

所有维度来源都在 trusted_sources 中 → **data_gate = 1.0**

**步骤 7：最终置信度**

```
final = 0.85 × 1.0 = 0.85 → PASS ✅
```

> 通过 AI Fallback 场景 B 成功绕过年份误提取，最终通过。

---

### 示例 4：data_gate 拦截场景

假设用户配置 `restricted_level` 的 `trusted_sources` 只包含 `["tmdb"]`，但本次刮削 TMDB 没有返回分级数据（`restricted_level` 来自 AI 判断）。

```
search_conf = 0.9 × 1.0 = 0.9  （搜索匹配很好）
objective_cap = 0.9

但是：restricted_level 的来源是 "ai"，不在 trusted_sources ["tmdb"] 中
→ data_gate = 0
→ final = 0.9 × 0 = 0 → NEEDS_REVIEW（需人工审核分级信息）
```

> 置信度分数（0.9）仍然显示在界面上，让用户了解搜索匹配质量。但任务状态被标记为 `NEEDS_REVIEW`，提示用户手动检查不被信任的维度。

---

## 10. 前端 UI 变更

### 10.1 移除的配置区域

| 区域 | 原位置 | 说明 |
|------|--------|------|
| 数据置信度 | 置信度配置第 3 区块 | 聚合方式卡片、来源默认置信度输入框 — 全部移除 |
| 维度敏感度 | 置信度配置第 5 区块 | weight/veto_threshold/source_confidence — 全部移除 |

### 10.2 新增的配置区域

**维度来源信任**（替代原"维度敏感度"）：

- 为每个已启用维度显示一个可展开的卡片
- 卡片内包含来源配置表格，每行一个来源：
  - 拖拽手柄：调整优先级（越靠前优先级越高）
  - 来源标签：TMDB / AI / FILE（未来可扩展豆瓣等）
  - 说明：来源的简要描述
  - 可信开关：toggle 切换是否信任该来源
- 来源标签仅显示当前已接入的（如当前只显示 `TMDB`、`AI`、`FILE`），未来接入豆瓣后自动增加标签
- 默认：所有已接入来源都信任，优先级顺序为 TMDB > AI > FILE（向后兼容）
- UI 示意：
  ```
  media_type ▼
  ┌────┬──────┬──────────────────┬──────┐
  │ ⠿  │ TMDB │ TMDB结构化字段映射 │  ✓   │
  │ ⠿  │ AI   │ AI判断           │  ✓   │
  │ ⠿  │ FILE │ 文件名分析推导    │  ✓   │
  └────┴──────┴──────────────────┴──────┘

  restricted_level ▼
  ┌────┬──────┬──────────────────┬──────┐
  │ ⠿  │ TMDB │ TMDB结构化字段映射 │  ✓   │
  │ ⠿  │ AI   │ AI判断           │  ✗   │
  │ ⠿  │ FILE │ 文件名分析推导    │  ✗   │
  └────┴──────┴──────────────────┴──────┘
  ```

**移除的配置区域**：

- 全局来源优先级（不再需要，每个维度独立配置）
- 数据置信度区域（聚合方式 + 来源置信度输入框）

### 10.3 公式预览调整

```
置信度分数 = search_conf（搜索置信度）
           = T（标题匹配分）× R_dynamic（结果数惩罚）

如果任一维度来源不被信任 → 任务标记为「需人工审核」

TMDB+AI 模式：final = T × R_dynamic
纯 AI 模式：  final = objective_cap（基于 AI 标题与文件名相似度）
```

---

## 11. 刮削追踪 (ScrapeTrace)

每次置信度计算都会生成完整的追踪记录 `scrape_trace`，包含：

| 字段 | 说明 |
|------|------|
| `mode` | 计算模式：`tmdb_ai` 或 `ai` |
| `filename_clean` | 清洗结果：原始文件名、clean_title、year、season、episode、去除项 |
| `ai_clean` | AI 清洗结果（如有） |
| `tmdb_search` | TMDB 搜索信息：搜索词、结果数、选中结果 |
| `confidence_calc.search_conf` | T 值、R 值、R_base、动态调整信息 |
| `confidence_calc.data_gate` | 1.0 或 0，以及不信任的维度列表 |
| `confidence_calc.final_confidence` | 最终置信度 |

前端「置信度计算详情」弹窗基于此追踪记录渲染。

---

## 12. 已知边界 Case

| Case | 原因 | 当前处理 | 是否需要修复 |
|------|------|----------|-------------|
| Blade Runner 2049 年份误提取 | `2049` 被误识别为年份，`2017` 残留标题 | TMDB 无结果 → AI Fallback 场景 B → AI 清洗出正确标题 | 已通过 AI Fallback 正确处理 |
| 中文标题 + 广告残留 | 正则无法完全清洗中文广告 | TMDB 无结果 → AI Fallback 场景 B | 不需要，AI 兜底 |
| 中英双语标题 | TMDB 可能只有一种语言 | 模糊匹配 → CONFIRMING | 可接受，需人工确认 |
| 标题含数字被误提取为年份 | 如 `2001太空漫游` | 可能误提取 `2001` | AI Fallback 场景 B 兜底 |

---

## 13. 方案变更记录

### v2 — 简化数据置信度（当前版本）

**核心变更**：数据置信度从「多来源聚合计算」简化为「二元信任门控」

| 项目 | v1（旧） | v2（新） |
|------|----------|----------|
| data_conf 计算 | 多维度加权聚合（geometric_mean/product/min） | 二元门控：信任=1.0，不信任=0 |
| 聚合方式配置 | product/geometric_mean/min 三选一 | **移除** |
| 来源默认置信度 | tmdb=1.0, file=1.0, ai=0.9, missing=0.5 | **移除**，改为信任/不信任 |
| 维度敏感度 | weight + veto_threshold + source_confidence 覆盖 | **移除**，改为按维度 sources 列表（优先级+信任合一） |
| 维度否决 | dim_confidence < veto_threshold → NEEDS_REVIEW | 来源不在 trusted → NEEDS_REVIEW |
| 多来源优先级 | 无 | 新增按维度独立 sources 列表（优先级+信任合一） |
| 最终公式 | `final = search_conf × data_conf` | `final = search_conf × data_gate` |
| 置信度含义 | 搜索质量 × 数据可信度的综合分 | 纯搜索质量分，数据可信度是独立门控 |

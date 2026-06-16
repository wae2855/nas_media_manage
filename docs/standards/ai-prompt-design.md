# AI 提示词设计规范

**事实源**：本文件定义 Tier 2 AI 辅助匹配的提示词输入/输出契约、边界判定规则、防御性兜底。代码实现必须遵循。  
**适用范围**：`media_importer/scraper/_llm_match_assist.py`、`media_importer/features/scraping/_match_tiers_impl.py`  
**相关文档**：
- 三级匹配：[scrape-matching.md](scrape-matching.md)
- 信息职责：[info-architecture.md](info-architecture.md)

---

## 一、设计原则

### 1.1 双字段分离原则

AI 的输出必须用**两个字段**承载"有效性"和"确定性"，不能塞进一个 certainty：

| 字段 | 含义 | 影响 |
|------|------|------|
| `is_valid` | 文件名是否包含可识别影视信息 | `false` → 任务 FAILED（不搜 Provider） |
| `certainty` | AI 对具体作品的把握度（仅 is_valid=true 时有意义） | `high` → 自动入库；`medium` → 待确认 |

**关键约束**：`certainty=low` 在最终结果中**不应出现**。如果 `is_valid=true` 但 AI 完全无法推测，应该返回 `is_valid=false`。

### 1.2 候选利用原则

AI 收到 Tier 1 的 Provider 候选列表后，优先从中选择，而不是凭空推测：

- 若候选中有完美匹配 → 填 `selected_candidate_id`，程序不重搜
- 若候选都不匹配但能推测 → 填 `corrected_title+year`，程序重搜
- 若 is_valid=false → 所有其他字段留空

---

## 二、输入数据契约

### 2.1 调用方传入字段

`LLMScraper.tier2_correct()` 接收：

```python
{
    "original_filename": str,        # 原始文件名（必填）
    "clean_title": str,              # FilenameCleaner 输出（参考）
    "year": Optional[int],           # FilenameCleaner 输出（参考）
    "path_context": {
        "parent_folder": str,        # 上级目录名
        "grandparent_folder": str,   # 上两级目录名
        "path_segments": List[str],  # 路径段列表
        "sibling_files": List[str],  # 同级文件列表
        "provider_candidates": List[dict],  # Tier 1 候选（关键）
        "tier1_search_info": {       # Tier 1 搜索结果（v2 新增）
            "searched_title": str,   # 实际搜索词
            "searched_year": Optional[int],
            "candidate_type": str,   # "exact" / "fuzzy" / "none"
            "candidate_count": int,
            "provider_results": str, # 人类可读描述
        },
    }
}
```

### 2.2 provider_candidates 字段结构

每个候选字典必须包含（来自 Tier 1 候选保留）：

```python
{
    "id": str,                # provider_id（AI 用作 selected_candidate_id）
    "title": str,
    "original_title": str,
    "year": Optional[int],
    "media_type": str,        # "movie" / "tv"
    "vote_average": float,    # 评分
    "vote_count": int,
    "popularity": float,
}
```

### 2.3 渲染到提示词的格式

候选列表渲染为编号文本（最多 5 个）：

```
## Provider 候选（Step 1 已找到，供你参考）
1. 爱神 (2004) · 电影 · ⭐6.8 · 热度15 · id:39850
2. 爱神 (2026) · 电视剧 · ⭐5.2 · 热度3 · id:273129
3. Eros (2004) · 电影 · ⭐7.1 · 热度8 · id:9603
```

无候选时显示 `无`。

### 2.4 tier1_search_info 渲染规则

根据 `candidate_type` 动态生成提示：

**none（0 条结果）**：
```
Step 1 已用 "大汉王朝" 搜索 Provider，结果：0 条结果。这意味着 Provider 数据库里没有这个标题的作品。如果你认为文件名确实包含影视信息，请给出你认为正确的标题（可能是英文原名、别名或更准确的译名），程序会用你给的 corrected_title 重新搜索。如果你也找不到替代标题，应返回 is_valid=false。
```

**exact（精确匹配）**：
```
Step 1 已用 "美丽人生" 搜索 Provider，结果：7 条精确匹配。
```

**fuzzy（模糊匹配）**：
```
Step 1 已用 "大汉王朝" 搜索 Provider，结果：5 条模糊匹配（标题不完全一致）。这些是标题不完全匹配的模糊结果，可能包含同名但不同年份/类型的作品。请结合文件名和目录上下文判断哪条最可能匹配，填 selected_candidate_id 直接采用；若都不匹配但你能推测正确标题，填 corrected_title 让程序重新搜索。
```

---

## 三、输出 JSON 契约

### 3.1 is_valid=true 的输出

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

### 3.2 is_valid=false 的输出

```json
{
  "is_valid": false,
  "certainty": "",
  "corrected_title": "",
  "corrected_year": null,
  "media_type_hint": null,
  "selected_candidate_id": null,
  "reason": "判定为非有效影视文件名的理由",
  "short_reason": "≤30字总结"
}
```

### 3.3 字段详细规范

| 字段 | 类型 | is_valid=true 时 | is_valid=false 时 |
|------|------|------------------|-------------------|
| `is_valid` | bool | true | false |
| `certainty` | str | "high" 或 "medium"（"low" 不应出现） | ""（空） |
| `corrected_title` | str | 纠正后的标题（可与原 clean_title 相同） | ""（空） |
| `corrected_year` | int/null | 推测的年份，无则 null | null |
| `media_type_hint` | str/null | "movie" / "tv" / null | null |
| `selected_candidate_id` | str/null | 从候选中选定时填 provider_id；否则 null | null |
| `reason` | str | 详细理由，≤200 字 | 判定理由 |
| `short_reason` | str | ≤30 字总结（供列表显示） | ≤30 字总结 |

---

## 四、is_valid 判定规则

### 4.1 返回 false 的情况（宁可保守）

#### 情况 1：随机字符或乱码

```
123uyyt.mkv       → false
asdfgh.mkv        → false
855.mkv           → false
yyu.mkv           → false
```

#### 情况 2：纯通用名词，对应影视过多

**单字词**：
```
消防 → false（含"消防员"的电影数十部）
大楼 → false
飞机 → false
爱情 → false
战争 → false
```

**通用短语**：
```
我的女神 → false（对应几十部作品）
那些日子 → false
```

#### 情况 3：明显非影视内容

```
新建文件夹 → false
未命名     → false
sample     → false
test       → false
```

### 4.2 返回 true 的情况

- 包含**具体片名**（中文译名或原文）：
  ```
  美丽人生 → true
  Dune → true
  La vita è bella → true
  ```

- 含**影视特征任一**：
  - 年份：`...2024...`
  - 季集：`S01E01`、`第3季`
  - 画质：`1080p`、`4K`、`BluRay`
  - 人名（导演/演员）

### 4.3 候选数量影响判定（重要边界）

| 候选情况 | 倾向判定 |
|---------|---------|
| 同名候选 ≥ 3 部 | `is_valid=false`（歧义太大） |
| 同名候选唯一且高分（⭐≥7.0） | `is_valid=true` + `certainty=high` |
| 同名候选 2 部且都低分 | `is_valid=true` + `certainty=medium` |

**示例边界**：

| 文件名 | 候选情况 | 预期判定 |
|--------|---------|---------|
| `消防员.mkv` | 5 部同名 | `is_valid=false`（歧义） |
| `消防员.mkv` | 1 部 ⭐7.5 | `is_valid=true` + `high` |
| `消防员.mkv` | 2 部 ⭐5.x | `is_valid=true` + `medium` |

---

## 五、certainty 判定规则

### 5.1 high（高确定性）

- 知名电影的**明确中文译名**，无歧义
  - "泰坦尼克号" → 几乎只指引 1997 卡梅隆电影
- 文件名含**明确年份+片名**
  - "Dune.Part.Two.2024.1080p.mkv"
- Provider 候选**第一位完美匹配**

### 5.2 medium（中确定性）

- 同名作品多版本，缺年份
  - "美丽人生" 可能是 1997 电影或 2000 电视剧
- 片名翻译有歧义
  - "爱神" 可能是 Eros 2004 或其他同名作
- 上下文不足，但有明确的推测方向

### 5.3 low（不应出现）

**不应返回 low**。若 `is_valid=true` 但完全无法推测，应返回 `is_valid=false`。

代码层防御：若 AI 返回 `certainty=low`，兜底改为 `medium`。

### 5.4 输出完整性要求

以下要求在提示词中强约束：

- 无论 certainty 是 high 还是 medium，都必须填写 corrected_title 和 corrected_year
- corrected_title 至少应等于 clean_title（不要空着）
- 若 reason 中提到具体年份，corrected_year 必须填写该年份，不能留 null
- certainty 只决定"是否自动入库"，不是"能不能给出建议"

### 5.5 Tier 2 跳过规则

以下场景不调用 Tier 2 AI（标题已精确匹配，AI 无增量信息）：

| Tier 1 结果 | 行为 | match_level | match_tier |
|------------|------|-------------|:---:|
| 唯一精确匹配 | 直接通过 | AUTO_PASS | 1 |
| 多个精确匹配（≥2） | 预选热度最高，人工确认 | NEEDS_CONFIRM | 1 |
| 无精确匹配 | 进入 Tier 2 AI | — | — |

**Tier 2 仅在 Tier 1 无精确匹配时触发。**

---

## 六、完整提示词模板

### 6.1 user_parts 完整结构

```
## 待匹配文件信息
- 原始文件名: {original_filename}
- 正则参考标题: {clean_title or '无'}
- 正则参考年份: {year or '未知'}

## 目录上下文
- 上级文件夹: {parent_folder or '无'}
- 上两级文件夹: {grandparent_folder or '无'}
- 路径段: {path_segments or '无'}
- 同级文件: {sibling_files or '无'}

## Provider 候选（Step 1 已找到，供你参考）
{candidates_text}  # 渲染后的候选列表，或"无"

## Step 1 搜索结果
{tier1_hint}  # 动态生成：告知 AI 搜索词和结果数，0 结果时提示换名字

## 网络搜索优先
如果你具备联网搜索能力，请优先通过网络搜索验证标题和年份信息，
而不是仅凭记忆或训练数据猜测。特别是以下场景：
- Step 1 Provider 返回 0 条结果时，先搜一下这个标题对应哪部作品
- 同名多版本时，结合文件名中的线索（年份、季集、画质标注）搜索确认
- 不确定 corrected_title 的准确译名时，搜索确认标准译名
网络搜索得出的结论比记忆猜测更可靠，可以提高 certainty 等级。

## 判定规则

### 第一步：判断 is_valid（文件名是否包含可识别影视信息）

返回 false 的情况（宁可保守）：
1. 文件名为随机字符或乱码：如 123uyyt、asdfgh、855、yyu
2. 文件名为纯通用名词，对应影视过多无法具体指向：
   - 单字词："消防"、"大楼"、"飞机"、"爱情"
   - 通用短语："我的女神"、"那些日子"（对应几十部作品）
3. 文件名明显非影视内容：如 "新建文件夹"、"未命名"、"sample"

返回 true 的情况：
- 包含具体片名（中文译名或原文）
- 含影视特征任一：年份(2024)、季集(S01E01)、画质(1080p)、人名

候选数量影响：
- 同名候选 ≥ 3 部 → 倾向 is_valid=false（歧义太大）
- 同名候选唯一且高分 → 倾向 is_valid=true + certainty=high

### 第二步：若 is_valid=true，判断 certainty

- high: 高度确信是某部具体作品（明确译名、含年份+片名、候选首位完美匹配）
- medium: 有合理猜测但无法 100% 确定（同名多版本缺年份、翻译有歧义）
- low: 不应出现。若 is_valid=true 但完全无法推测，应该返回 is_valid=false

### 第三步：候选利用规则

- 若 Step 1 候选中已有完美匹配项：填 selected_candidate_id（候选的 provider_id），程序直接采用
- 若候选都不匹配但你能推测：填 corrected_title + corrected_year，程序重新搜 Provider
- 若 is_valid=false：所有其他字段留空/null

## 关键要求
- 无论 certainty 是 high 还是 medium，都必须填写 corrected_title 和 corrected_year
- corrected_title 至少应等于 clean_title（不要空着）
- 如果 reason 中提到具体年份（如'2004年王家卫'），corrected_year 必须填写该年份，不能留 null
- certainty 只决定'是否自动入库'，不是你'能不能给出建议'
- 即使同时匹配多部同名作品（medium），也要给出你认为最可能的标题和年份

## 输出要求
返回 JSON，不要包含任何其他文字：
{"is_valid": true, "certainty": "high", "corrected_title": "...", "corrected_year": 2024, "media_type_hint": "movie", "selected_candidate_id": "637", "reason": "详细理由(200字内)", "short_reason": "≤30字总结"}

若 is_valid=false：
{"is_valid": false, "certainty": "", "corrected_title": "", "corrected_year": null, "media_type_hint": null, "selected_candidate_id": null, "reason": "判定理由", "short_reason": "≤30字"}
```

---

## 七、防御性兜底（代码层）

AI 返回值必须经过以下防御处理：

### 7.1 默认值

```python
result.setdefault("is_valid", True)           # 未返回时默认 True
result.setdefault("selected_candidate_id", None)
result.setdefault("short_reason", "")
```

### 7.2 is_valid=false 强制清空

```python
if not result.get("is_valid"):
    result["certainty"] = ""
    result["corrected_title"] = ""
    result["corrected_year"] = None
    result["media_type_hint"] = None
    result["selected_candidate_id"] = None
```

### 7.3 certainty 异常兜底

```python
if result.get("is_valid"):
    if result.get("certainty") not in ("high", "medium"):
        result["certainty"] = "medium"  # low 或异常值 → medium
```

### 7.4 short_reason 长度兜底

```python
# 超长截断
if result.get("short_reason") and len(result["short_reason"]) > 33:
    result["short_reason"] = result["short_reason"][:30] + "..."

# 空则从 reason 截前 30 字
elif not result.get("short_reason") and result.get("reason"):
    full = result["reason"]
    result["short_reason"] = full[:30] + ("..." if len(full) > 30 else "")
```

### 7.5 年份提取（兜底）

AI 经常把年份写在 `reason` 但 `corrected_year` 返回 null。代码层兜底：

```python
if not result["corrected_year"]:
    search_text = f"{result['reason']} {result['suggestion']}"
    year_match = re.search(r'(\d{4})\s*年|[\s\"](\d{4})[\s\"]|^(\d{4})$', search_text)
    if year_match:
        result["corrected_year"] = int(year_match.group(1) or year_match.group(2) or year_match.group(3))
```

---

## 八、标准示例

### 8.1 知名片无歧义（high）

**输入**：
```
原始文件名: 泰坦尼克号.mkv
候选: [泰坦尼克号(1997)⭐8.4热度120, 泰坦尼克号(1996)⭐6.0热度3]
```

**输出**：
```json
{
  "is_valid": true,
  "certainty": "high",
  "corrected_title": "泰坦尼克号",
  "corrected_year": 1997,
  "media_type_hint": "movie",
  "selected_candidate_id": "597",
  "reason": "中文译名几乎只指引 1997 卡梅隆电影，候选第一位热度远超其他",
  "short_reason": "1997版，候选首位完美匹配"
}
```

### 8.2 同名多版本（medium）

**输入**：
```
原始文件名: 美丽人生.mkv
候选: [美丽人生(1997)⭐8.5, 美丽人生(2000)⭐6.0]
```

**输出**：
```json
{
  "is_valid": true,
  "certainty": "medium",
  "corrected_title": "美丽人生",
  "corrected_year": null,
  "media_type_hint": "movie",
  "selected_candidate_id": null,
  "reason": "片名明确但同名多版本，无年份无法 100% 确定；倾向 1997 版但需用户确认",
  "short_reason": "同名多版，倾向1997需确认"
}
```

### 8.3 随机乱码（FAILED）

**输入**：
```
原始文件名: 123uyyt.mkv
候选: 无
```

**输出**：
```json
{
  "is_valid": false,
  "certainty": "",
  "corrected_title": "",
  "corrected_year": null,
  "media_type_hint": null,
  "selected_candidate_id": null,
  "reason": "文件名为随机字符'123uyyt'，无可识别影视信息",
  "short_reason": "随机字符，无法识别"
}
```

### 8.4 通用词歧义（FAILED）

**输入**：
```
原始文件名: 消防员.mkv
候选: [消防员(2006)⭐6.8, 消防员的故事(2014)⭐5.5, ...5 部同名]
```

**输出**：
```json
{
  "is_valid": false,
  "certainty": "",
  "corrected_title": "",
  "corrected_year": null,
  "media_type_hint": null,
  "selected_candidate_id": null,
  "reason": "'消防员'为通用名词，对应影视数十部无法具体指向；候选列表也说明歧义严重",
  "short_reason": "通用词歧义大，需用户明确"
}
```

### 8.5 英文片名+年份（high）

**输入**：
```
原始文件名: Dune.Part.Two.2024.1080p.mkv
候选: [Dune: Part Two (2024)⭐8.1热度95]
```

**输出**：
```json
{
  "is_valid": true,
  "certainty": "high",
  "corrected_title": "Dune: Part Two",
  "corrected_year": 2024,
  "media_type_hint": "movie",
  "selected_candidate_id": "438631",
  "reason": "英文片名+年份明确，候选首位完美匹配",
  "short_reason": "Dune 2 (2024) 候选首位匹配"
}
```

### 8.6 占位词（FAILED）

**输入**：
```
原始文件名: Movie.2023.mkv
候选: 无
```

**输出**：
```json
{
  "is_valid": false,
  "reason": "文件名虽含年份但无具体片名，'Movie' 为占位词非实际标题",
  "short_reason": "占位词，无具体片名"
}
```

---

## 九、不变量（Invariant）

1. **is_valid=false 时，certainty 必为空字符串**（不是 "low"）
2. **is_valid=false 时，所有其他字段必为空/null**
3. **certainty=low 不应出现在最终结果中**，防御兜底为 medium
4. **short_reason 长度 ≤ 33 字符**（30 + "..."）
5. **selected_candidate_id 必须来自 Tier 1 候选**，AI 不能凭空发明 ID
6. **is_valid=true 但 corrected_year=null 时**，代码层会尝试从 reason 提取年份

---

## 十、相关测试

| 测试文件 | 覆盖点 |
|---------|--------|
| `tests/test_phase_pqr.py` | is_valid 解析、selected_candidate_id、FAILED 流转 |
| `tests/test_tier2_match_engine.py` | Tier 2 各 certainty 分支 |
| `tests/test_ai_call_logging.py` | AI 调用日志 |

---

**本标准由 [plan](../plans/2026-06-16-scrape-info-responsibility-split-plan.md) 落地，提示词模板/边界规则变更须先更新本文件。**

# 多匹配行为修正 + 剧集识别补全

你是一名执行型开发者。本任务修正三级匹配的评分打破平局规则，并补全中文电视剧命名识别。

仓库：/Users/wangwei/Documents/code/nas_media_manage
基线 commit：7a893e7

---

## 一、改动概览

| # | 改动 | 影响 |
|---|------|------|
| 1 | 多精确匹配 → NEEDS_CONFIRM（不再 AUTO_PASS，跳过 Tier 2 AI） | 美丽人生(7个同名)→待确认 |
| 2 | 扩展季/集检测（中文格式 + 纯数字结尾 2-3 位） | 大汉王朝01 → 识别为电视剧 |
| 3 | 路径上下文推断 media_type | 上级目录含电视剧→优先 TV 候选 |
| 4 | 标准文档同步更新 | scrape-matching / ai-prompt-design |

---

## 二、硬性规则

1. 修改前必须先读文件
2. 每个改动完成后跑测试
3. Python 缓存陷阱：每次改 .py 文件后执行清缓存+重启
4. 不要修既有的 LSP 错误
5. 提交信息格式：修复: 简述

---

## 三、改动 1：多精确匹配 → NEEDS_CONFIRM

### 3.1 删除评分打破平局的 AUTO_PASS

文件：media_importer/features/scraping/_match_tiers_impl.py

位置：_tier1_exact_match_impl 函数中 elif len(exact_matches) > 1: 分支

找到 elif len(exact_matches) > 1: 分支，把从 matches_with_score = [] 到 self._pending_concerns.append(MatchConcern(...)) 的整个块（包括评分打破平局的 AUTO_PASS return）替换为以下代码。

关键变化：
- match_level：AUTO_PASS → NEEDS_CONFIRM
- match_tier：保持 1（Provider 精确匹配，不调用 AI）
- 不再 fallthrough 到 Tier 2（标题已精确匹配，AI 无增量信息）
- why_selected：TOP_RATED（按热度+评分预选）

替换代码见文件末尾附录 B。

### 3.2 更新枚举文案

文件：media_importer/features/scraping/match_enums.py

改前：TIER1_TOP_RATED = "同名{count}部，自动选评分最高"
改后：TIER1_TOP_RATED = "同名{count}部，预选热度最高，请确认"

### 3.3 更新测试

文件：tests/test_match_engine.py 和 tests/test_tier2_match_engine.py

搜索 AUTO_PASS 且上下文包含 exact_matches 或 top_rated 的测试断言，改为 NEEDS_CONFIRM。

---

## 四、改动 2：扩展季/集检测

### 4.1 新增正则

文件：media_importer/features/scraping/confidence_models.py

在现有 _SEASON_EPISODE / _SEASON_ONLY 之后追加：

_CN_SEASON_EPISODE = re.compile(r"第\s*(\d+)\s*季\s*第\s*(\d+)\s*集")
_CN_SEASON = re.compile(r"第\s*(\d+)\s*季")
_CN_EPISODE = re.compile(r"第\s*(\d+)\s*集")
_BARE_EPISODE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf](\d{2,3})$")

### 4.2 修改 FilenameCleaner

文件：media_importer/scraper/filename_cleaner.py

在现有 _SEASON_ONLY 匹配之后（约 L59），追加中文格式检测代码（见附录 C）。

注意：_BARE_EPISODE 匹配的是 name（已清洗过的），不是 filename。

### 4.3 验证

python3 -c "from media_importer.scraper.filename_cleaner import FilenameCleaner; ..."

期望：大汉王朝01 → season=1 ep=1, 大汉王朝22 → season=1 ep=22, 甄嬛传123 → season=1 ep=123, 美丽人生 → season=None

---

## 五、改动 3：路径上下文推断 media_type

### 5.1 新增推断函数

文件：media_importer/features/scraping/_match_tiers_impl.py

在 _sort_candidates_by_trust 函数附近新增 _infer_media_type_from_path 函数（见附录 D）。

### 5.2 传递 path_context 到 Tier 1

文件：media_importer/features/scraping/match_engine.py

match() 方法中 _tier1_exact_match() 调用处追加 path_context=context 参数。

### 5.3 Tier 1 接收参数

文件：media_importer/features/scraping/_match_tiers_impl.py

_tier1_exact_match_impl 函数签名加 path_context=None。

---

## 六、标准文档同步更新

### 6.1 docs/standards/scrape-matching.md

第 3.2 节标题改为多匹配处理规则，内容替换为：

规则：多个精确匹配（≥2）一律 NEEDS_CONFIRM，不自动通过，不进入 Tier 2 AI。

理由：
- 标题已精确匹配，AI 无增量信息
- 评分差距大 ≠ 用户想要那个版本
- 用户对歧义场景有最终决定权

处理流程：
1. 保存所有精确匹配候选
2. 若无季/集信息，用路径上下文推断 media_type
3. 按热度+评分排序，限制 10 条
4. 取第一作为 selected_candidate（why_selected=top_rated）
5. 返回 NEEDS_CONFIRM

新增第 3.4 节：路径上下文推断 media_type（关键词表见附录 E）。

### 6.2 docs/standards/ai-prompt-design.md

第五节末尾追加 Tier 2 跳过规则：
- Tier 1 多个精确匹配 → 直接返回 NEEDS_CONFIRM（tier=1），跳过 AI
- Tier 1 唯一精确匹配 → 直接返回 AUTO_PASS（tier=1），跳过 AI
- Tier 2 仅在 Tier 1 无精确匹配时触发

---

## 七、验证清单

### 期望行为

| 文件名 | match_level | match_tier | 说明 |
|--------|-------------|:---:|------|
| 美丽人生.mkv | NEEDS_CONFIRM | 1 | 7个同名，预选1997版 |
| 速度与激情.mkv | NEEDS_CONFIRM | 1 | 多个同名，预选热度最高 |
| Dune.Part.Two.2024.mkv | AUTO_PASS | 1 | 唯一精确匹配 |
| 大汉王朝01.mkv | NEEDS_CONFIRM | 1 | 识别为电视剧 |
| 123uyyt.mkv | FAILED | 2 | 垃圾文件 |

### 全部测试

python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"
python -m pytest tests/test_architecture_guards.py -q
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests

---

## 附录 A：清缓存+重启

find /Users/wangwei/Documents/code/nas_media_manage -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
find /Users/wangwei/Documents/code/nas_media_manage -name *.pyc -delete 2>/dev/null
pkill -9 -f python.*media_importer 2>/dev/null
sleep 2
source /Users/wangwei/Documents/code/nas_media_manage/.venv/bin/activate
PYTHONPATH=/Users/wangwei/Documents/code/nas_media_manage python -m media_importer.media_importer -c /Users/wangwei/Documents/code/nas_media_manage/config/config.yaml serve -p 9855 --host 0.0.0.0 > /tmp/nas_media_server.log 2>&1 &
sleep 5

---

开始执行。从改动 1 开始。


---
## 附录 B：改动 1 替换代码

将 `elif len(exact_matches) > 1:` 分支的整个块替换为：

```python
            elif len(exact_matches) > 1:
                # 多个精确匹配 → 按热度排序预选，人工确认
                # 不再尝试评分打破平局（评分差距大 ≠ 用户想要那个版本）
                # 不再 fallthrough 到 Tier 2 AI（标题已精确匹配，AI 无增量信息）

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

                # 路径上下文推断 media_type（改动 3）
                if year is None:
                    preferred_type = _infer_media_type_from_path(path_context)
                    if preferred_type:
                        filtered = [c for c in self._pending_candidates if c.get("media_type") == preferred_type]
                        if filtered:
                            self._pending_candidates = filtered

                self._pending_candidates = _sort_candidates_by_trust(self._pending_candidates)
                self._pending_candidates = self._pending_candidates[:10]

                top = self._pending_candidates[0]

                self._pending_concerns.append(MatchConcern(
                    code="NO_YEAR_MULTI_MATCH",
                    message=f"找到 {len(exact_matches)} 部同名作品",
                    detail=f"已按热度预选: {top['title']} ({top.get('year', '')})",
                ))

                trace_steps.append(MatchTraceStep(
                    tier=1,
                    name="Provider精确匹配",
                    matched=False,
                    search_query=f"{search_title} (year={year})",
                    reason=f"多个精确匹配({len(exact_matches)}条)，已预选: {top['title']} ({top.get('year', '')})",
                ))

                return MatchResult(
                    match_level="NEEDS_CONFIRM",
                    provider_id=top["id"],
                    provider_title=top["title"],
                    match_tier=1,
                    concerns=self._pending_concerns,
                    trace_steps=trace_steps,
                    candidates=self._pending_candidates[:5],
                    tier_short_reason=TierShortReason.TIER1_MULTI.format(count=len(exact_matches)),
                    selected_candidate=SelectedCandidate(
                        provider_type=top["provider_type"],
                        provider_id=str(top["id"]),
                        title=top["title"],
                        year=top.get("year"),
                        media_type=top.get("media_type", ""),
                        why_selected=WhySelected.TOP_RATED,
                        score=top.get("vote_average"),
                    ),
                )
```

---
## 附录 C：改动 2 FilenameCleaner 追加代码

在 `filename_cleaner.py` 的 `clean()` 方法中，现有 `_SEASON_ONLY` 匹配之后（约 L59），追加：

```python
        # 新增：中文季/集格式
        if season is None:
            cn_se_match = _CN_SEASON_EPISODE.search(_EXTENSION_PATTERN.sub('', filename))
            if cn_se_match:
                season = int(cn_se_match.group(1))
                episode = int(cn_se_match.group(2))
                removed.append(f"季集=S{season:02d}E{episode:02d}")

        if season is None:
            cn_s_match = _CN_SEASON.search(_EXTENSION_PATTERN.sub('', filename))
            if cn_s_match:
                season = int(cn_s_match.group(1))
                removed.append(f"季=S{season:02d}")

        if episode is None:
            cn_e_match = _CN_EPISODE.search(_EXTENSION_PATTERN.sub('', filename))
            if cn_e_match:
                episode = int(cn_e_match.group(1))
                removed.append(f"集=E{episode:02d}")

        # 新增：纯数字结尾（大汉王朝01、甄嬛传22）
        # 排除年份(19xx/20xx)和分辨率(720/1080/2160)
        if season is None and episode is None:
            bare_match = _BARE_EPISODE.search(name)
            if bare_match:
                num = int(bare_match.group(1))
                if not (1900 <= num <= 2099) and num not in (720, 1080, 2160):
                    episode = num
                    season = 1
                    removed.append(f"集=E{episode:02d}")
```

---
## 附录 D：改动 3 _infer_media_type_from_path 函数

在 `_match_tiers_impl.py` 文件顶部，`_sort_candidates_by_trust` 函数附近新增：

```python
def _infer_media_type_from_path(path_context: dict) -> str:
    """从路径上下文推断 media_type。
    
    规则：
    - 上级/上两级目录含电视剧关键词 → "tv"
    - 上级/上两级目录含电影关键词 → "movie"  
    - 无明确信号 → ""（不推断）
    """
    if not path_context:
        return ""
    
    tv_keywords = ("电视剧", "TV", "Series", "剧集", "国产剧", "日剧", "韩剧", "美剧", "动漫")
    movie_keywords = ("电影", "Movie", "Film", "Movies", "Films")
    
    parent = (path_context.get("parent_folder") or "").lower()
    grandparent = (path_context.get("grandparent_folder") or "").lower()
    combined = f"{parent} {grandparent}"
    
    for kw in tv_keywords:
        if kw.lower() in combined:
            return "tv"
    
    for kw in movie_keywords:
        if kw.lower() in combined:
            return "movie"
    
    return ""
```

---
## 附录 E：标准文档更新内容

### E.1 scrape-matching.md 第 3.2 节替换

将第 3.2 节"评分打破平局规则"整节替换为：

```
### 3.2 多匹配处理规则

**规则**：多个精确匹配（≥2）一律 NEEDS_CONFIRM，不自动通过，不进入 Tier 2 AI。

**理由**：
- 标题已精确匹配，AI 无增量信息（不需要 AI 再猜一遍）
- 评分差距大 ≠ 用户想要那个版本（7 个同名作品歧义严重）
- 用户对歧义场景有最终决定权

**处理流程**：
1. 保存所有精确匹配候选
2. 若无季/集信息，用路径上下文推断 media_type（见 3.4 节）
3. 按热度+评分排序，限制 10 条
4. 取第一作为 selected_candidate（why_selected=top_rated）
5. 返回 NEEDS_CONFIRM，候选列表供用户选择

**旧规则（已废弃）**：评分差距 ≥1.5 且 top ≥6.0 时自动通过。
废弃原因：见上述理由。
```

### E.2 scrape-matching.md 新增第 3.4 节

```
### 3.4 路径上下文推断 media_type

当文件名无季/集信息（season=None）时，从路径上下文推断媒体类型：

| 路径关键词 | 推断 media_type | 效果 |
|-----------|:---:|------|
| 电视剧/TV/Series/剧集/国产剧/日剧/韩剧/美剧/动漫 | tv | 多匹配时优先 TV 候选 |
| 电影/Movie/Film | movie | 多匹配时优先电影候选 |
| 无明确信号 | 不推断 | 不过滤 |

推断仅在候选过滤阶段生效（缩小候选范围），不影响 Provider 搜索。
```

### E.3 ai-prompt-design.md 第五节末尾追加

```
### 5.5 Tier 2 跳过规则

以下场景不调用 Tier 2 AI（标题已精确匹配，AI 无增量信息）：

- Tier 1 多个精确匹配 → 直接返回 NEEDS_CONFIRM（tier=1），跳过 AI
- Tier 1 唯一精确匹配 → 直接返回 AUTO_PASS（tier=1），跳过 AI

Tier 2 仅在 Tier 1 无精确匹配时触发。
```

# 刮削流程行为规范化修复

你是一名**执行型开发者**。本任务在上一个重构（刮削信息职责拆分）的基础上，修复 6 个行为层面的缺口，对标已固化的标准文档。**不要做架构决策**，按本提示词的精确代码改动逐步实施。

**仓库**：`/Users/wangwei/Documents/code/nas_media_manage`

---

## 一、背景

上一个计划"刮削信息职责拆分"已将 `confirm_reason` 万能胶拆成 6 层独立字段（L1-L6），并在 `docs/standards/` 下固化了三份行为标准。本任务修复以下 6 个缺口：

| # | 缺口 | 严重度 |
|---|------|:---:|
| 1 | `_search_providers_impl` 不排序，返回 Provider 原始顺序 | P1 |
| 2 | Tier 1 候选传给 AI 时不排序、不限制 10 条 | P1 |
| 3 | AI 提示词未强约束"medium 也必须给 corrected_title+year" | P1 |
| 4 | Tier 2 TraceStep 缺少 `search_query`（用户看不到用什么搜的） | P1 |
| 5 | 前端时间轴不按 match_level 区分步数（FAILED 还显示 6 步） | P1 |
| 6 | 前端 Tier 2 步骤不显示可信度徽章（高/中/低） | P2 |

---

## 二、硬性规则

1. **修改前必须先读文件**（用 Read 工具）
2. **每个修复完成后跑测试**：`python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"`
3. **Python 缓存陷阱**：每次改 `.py` 文件后执行清缓存+重启（见附录 A）
4. **不要修既有的 LSP 错误**（如 `scenario: str` 接收 None、mixin 类属性）
5. 提交信息格式：`修复: 简述（如"修复: _search_providers_impl 统一按热度排序"）`

---

## 三、修复详情

### 修复 1：通用排序函数

**文件**：`media_importer/features/scraping/_match_tiers_impl.py`

**位置**：文件顶部 `import` 语句之后，第一个函数定义之前

**新增代码**：

```python
def _sort_candidates_by_trust(candidates: list) -> list:
    """按可信度排序：popularity DESC → vote_average DESC → vote_count DESC"""
    return sorted(candidates, key=lambda c: (
        c.get("popularity", 0) or 0,
        c.get("vote_average", 0) or 0,
        c.get("vote_count", 0) or 0,
    ), reverse=True)
```

**改动 1b**：在 `_search_providers_impl` 函数**末尾**的 `return candidates` 之前加一行：

```python
    # 在 return candidates 之前：
    candidates = _sort_candidates_by_trust(candidates)
    return candidates
```

**改动 1c**：在 `_tier2_high_certainty_impl` 和 `_tier2_medium_certainty_impl` 中，`_search_providers_impl` 调用返回后（已有排序，无需额外改动），但在取 `candidates[0]` 作为 `selected_candidate` 时：
- `why_selected` 当前用 `WhySelected.AI_SUGGESTION` 或 `WhySelected.FIRST_CANDIDATE`
- 因为现在排序已统一，`AI_SUGGESTION` 语义正确（AI 建议 + 排序后第一），**无需改**

**验证**：写一个快速测试确认排序函数工作：

```bash
python -c "
from media_importer.features.scraping._match_tiers_impl import _sort_candidates_by_trust
cands = [
    {'popularity': 10, 'vote_average': 7.0, 'vote_count': 100},
    {'popularity': 5, 'vote_average': 9.0, 'vote_count': 10},
    {'popularity': 10, 'vote_average': 8.0, 'vote_count': 50},
]
sorted_cands = _sort_candidates_by_trust(cands)
# 期望顺序：popularity 10+vote 8.0 第一，popularity 10+vote 7.0 第二，popularity 5 第三
assert sorted_cands[0]['vote_average'] == 8.0
assert sorted_cands[1]['vote_average'] == 7.0
assert sorted_cands[2]['vote_average'] == 9.0  # popularity 低，排最后
print('OK')
"
```

---

### 修复 2：Tier 1 候选排序+限制 10 条

**文件**：`media_importer/features/scraping/_match_tiers_impl.py`

**位置**：`_tier1_exact_match_impl` 函数中，`self._pending_candidates = [...]` 赋值块之后

**改动**：在 `self._pending_candidates = [...]` 的 `]` 之后（即列表赋值完成后），追加排序和截断：

```python
                self._pending_candidates = [
                    {
                        "id": item.item_id,
                        "title": item.title,
                        # ... 已有字段 ...
                    }
                    for item, _ in exact_matches
                ]
                # 新增：排序 + 限制 10 条
                self._pending_candidates = _sort_candidates_by_trust(self._pending_candidates)
                self._pending_candidates = self._pending_candidates[:10]
```

**注意**：确保 `[:10]` 是**在** `self._pending_candidates` 被 `_tier2_context_match_impl` 取用之前完成。

---

### 修复 3：AI 提示词追加"medium 也必须给"

**文件**：`media_importer/scraper/_llm_match_assist.py`

**位置**：`user_parts` 列表中，"### 第三步：候选利用规则" 之后，"## 输出要求" 之前

**在两者之间插入**：

```python
    "",
    "## 关键要求",
    "- 无论 certainty 是 high 还是 medium，都必须填写 corrected_title 和 corrected_year",
    "- corrected_title 至少应等于 clean_title（不要空着）",
    "- 如果 reason 中提到具体年份（如'2004年王家卫'），corrected_year 必须填写该年份，不能留 null",
    "- certainty 只决定'是否自动入库'，不是你'能不能给出建议'",
    "- 即使同时匹配多部同名作品（medium），也要给出你认为最可能的标题和年份",
```

---

### 修复 4：Tier 2 TraceStep 补 `search_query`

**文件**：`media_importer/features/scraping/_match_tiers_impl.py`

**改动 4a**：`_tier2_high_certainty_impl` 成功匹配的分支（~L198-215）

**搜索** `trace_steps.append(MatchTraceStep(` 在 `_tier2_high_certainty_impl` 中

**在** `reason=f"AI高确定性纠正后搜索结果: {selected.get('title', '')}",` 之前，**插入**：

```python
                search_query=f"AI 纠正后搜索词: {corrected_title}" + (f" ({corrected_year}年)" if corrected_year else ""),
```

**改动 4b**：`_tier2_medium_certainty_impl` 的 TraceStep（~L245-255）

**搜索** `trace_steps.append(MatchTraceStep(` 在 `_tier2_medium_certainty_impl` 中

**在** `reason=f"AI中确定性，提供候选列表供确认: {ai_reason[:100]}",` 前后**确保有**：

```python
                search_query=f"AI 建议搜索词: {corrected_title}" + (f" ({corrected_year}年)" if corrected_year else ""),
```

**改动 4c**：`_tier2_low_certainty_impl`（如果仍被低确定性分支调用）

同上，确保 `search_query` 字段有值。

---

### 修复 5：前端时间轴按 match_level 分化

**文件**：`media_importer/webui/js/cinema-config-simulator.js`

**目标**：
- FAILED → 步骤 1-3 正常，步骤 4 显示"刮削失败"，步骤 5-6 不显示
- NEEDS_CONFIRM → 步骤 1-5 正常，步骤 6 显示"待人工确认，不入库"
- AUTO_PASS / CONTEXT_PASS → 步骤 1-6 完整显示

**步骤 5.1**：找到函数 `renderMatchPathPreview(data)`（约 L44）

**步骤 5.2**：在函数内部找到以下结构（约 L340-410 的步骤 4-6 渲染区），替换为：

```javascript
  // --- timeline step 4: 刮削结果 ---
  html += _renderStep4Scrape(data);

  const matchLevel = data.match_result?.match_level || "NEEDS_CONFIRM";

  // FAILED：步骤 5-6 不显示
  if (matchLevel === "FAILED") {
    return html;
  }

  // --- timeline step 5: 维度推导 ---
  html += _renderStep5Dimensions(data);

  // NEEDS_CONFIRM：步骤 6 显示"待确认"
  if (matchLevel === "NEEDS_CONFIRM") {
    html += '<div class="sim-step">';
    html += '<div class="sim-step-rail">';
    html += '<div class="sim-step-dot" style="background:#F59E0B18;color:#F59E0B">6</div>';
    html += '<div class="sim-step-line" style="background:transparent"></div>';
    html += '</div>';
    html += '<div class="sim-step-content">';
    html += '<div class="sim-step-header"><span class="sim-step-title" style="color:#F59E0B">待人工确认</span><span class="sim-step-tag" style="background:#F59E0B18;color:#F59E0B">CONFIRM</span></div>';
    html += '<div class="sim-alert">确认后才能入库。</div>';
    html += '</div></div>';
    return html;
  }

  // --- timeline step 6: 最终入库判断（仅 AUTO_PASS / CONTEXT_PASS）---
```

**步骤 5.3**：步骤 4（刮削结果）的渲染中，如果 `match_level === "FAILED"`，需要特殊处理。找到当前步骤 4 的渲染（约 L154-195），在开头加一个条件：

```javascript
// 在步骤 4 渲染的开头（步骤编号行之前）
const scrapeMatchLevel = scrapeRes.match_level || "NEEDS_CONFIRM";

// 如果是 FAILED，步骤 4 显示为"刮削失败"
if (scrapeMatchLevel === "FAILED") {
  const failReason = scrapeRes.tier_short_reason || "AI 判定无可识别影视信息";
  html += '<div class="sim-step">';
  html += '<div class="sim-step-rail">';
  html += '<div class="sim-step-dot" style="background:#D94F4518;color:#D94F45">4</div>';
  html += '<div class="sim-step-line" style="background:transparent"></div>';
  html += '</div>';
  html += '<div class="sim-step-content">';
  html += '<div class="sim-step-header"><span class="sim-step-title" style="color:#D94F45">刮削失败</span><span class="sim-step-tag" style="background:#D94F4518;color:#D94F45">FAILED</span></div>';
  html += `<div class="sim-alert">${escapeHtml(failReason)}</div>`;
  html += '</div></div>';
  return html;  // FAILED 直接返回，不继续后续步骤
}
```

**注意**：`_renderStep4Scrape` 和 `_renderStep5Dimensions` 目前是内联代码，不是独立函数。你可以选择：
- 方案 A：抽取为独立函数（推荐，与步骤 6 风格一致）
- 方案 B：在步骤 4 开头和步骤 6 前加条件判断

推荐方案 A，但实现细节你自行判断。关键是渲染结果符合上述 3 个 match_level 的步数差异。

---

### 修复 6：前端 Tier 2 步骤显示可信度徽章

**文件**：`media_importer/webui/js/cinema-config-simulator.js`

**位置**：`renderMatchPathPreview` 函数中渲染 trace_steps 的循环（约 L130-155）

**当前** trace_steps 渲染类似：

```javascript
trace.forEach(step => {
    html += `<div>${step.name}</div>`;
    html += `<div>${step.reason || ''}</div>`;
});
```

**改为**：在每个 Tier 2 步骤的 name 旁边，加一个可信度徽章：

```javascript
trace.forEach(step => {
    const tierLabel = step.tier === 1 ? "T1" : step.tier === 2 ? "T2" : "T3";
    
    // 可信度徽章（仅 Tier 2）
    let certaintyTag = "";
    if (step.tier === 2) {
        const reason = step.reason || "";
        if (reason.includes("高确定性")) {
            certaintyTag = '<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:rgba(34,197,94,0.12);color:#22C55E;margin-left:4px;">高</span>';
        } else if (reason.includes("中确定性")) {
            certaintyTag = '<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:rgba(245,158,11,0.12);color:#F59E0B;margin-left:4px;">中</span>';
        } else if (reason.includes("低确定性")) {
            certaintyTag = '<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:rgba(217,79,69,0.12);color:#D94F45;margin-left:4px;">低</span>';
        }
    }
    
    // search_query 展示（Tier 2 关键信息）
    let searchInfo = "";
    if (step.search_query) {
        searchInfo = `<div style="font-size:11px;color:var(--muted);margin-top:2px;">🔍 ${escapeHtml(step.search_query)}</div>`;
    }
    
    // ... 已有渲染逻辑 + certaintyTag + searchInfo ...
});
```

---

## 四、标准文档同步更新

### 4.1 更新 `docs/standards/scrape-matching.md`

**第 3.3 节候选保留与跨 Tier 复用**，在"保存候选到 `self._pending_candidates`"后追加：

```
保存后必须立即排序和限制数量：

self._pending_candidates = _sort_candidates_by_trust(self._pending_candidates)
self._pending_candidates = self._pending_candidates[:10]
```

**第八节候选字典标准结构**，在字段表后追加：

```
### 8.1 排序规则

所有 Provider 搜索返回的候选列表，**必须**经过 `_sort_candidates_by_trust()` 排序：

排序 key（降序）：popularity → vote_average → vote_count

适用范围：
- _search_providers_impl 返回前
- _pending_candidates 保存后
- 任何从 Provider 搜索获取的候选列表
```

### 4.2 更新 `docs/standards/ai-prompt-design.md`

**第五节 certainty 判定规则**，在"medium"定义后追加：

```
### 5.4 输出完整性要求

以下要求在提示词中强约束：

- 无论 certainty 是 high 还是 medium，都必须填写 corrected_title 和 corrected_year
- corrected_title 至少应等于 clean_title（不要空着）
- 若 reason 中提到具体年份，corrected_year 必须填写该年份，不能留 null
- certainty 只决定"是否自动入库"，不是"能不能给出建议"
```

---

## 五、验证清单

### 后端验证

```bash
# 启动服务器
find /Users/wangwei/Documents/code/nas_media_manage -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /Users/wangwei/Documents/code/nas_media_manage -name "*.pyc" -delete 2>/dev/null
pkill -9 -f "python.*media_importer" 2>/dev/null
sleep 2
source /Users/wangwei/Documents/code/nas_media_manage/.venv/bin/activate
PYTHONPATH="/Users/wangwei/Documents/code/nas_media_manage" python -m media_importer.media_importer -c /Users/wangwei/Documents/code/nas_media_manage/config/config.yaml serve -p 9855 --host 0.0.0.0 > /tmp/nas_media_server.log 2>&1 &
sleep 5

# 测试各场景
for f in "速度与激情.mkv" "爱神.mkv" "123uyyt.mkv" "美丽人生.mkv"; do
  JOB=$(curl -s -X POST http://localhost:9855/api/scrape/preview/start -H 'Content-Type: application/json' -d "{\"filename\":\"$f\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['job_id'])")
  sleep 30
  echo "=== $f ==="
  curl -s "http://localhost:9855/api/scrape/preview/status/$JOB" | python3 -c "
import sys,json
d = json.load(sys.stdin)['data']['result']
sr = d['scrape_result']
mr = d['match_result']
print(f\"  match_level: {sr.get('match_level')}\")
print(f\"  candidates: {len(mr.get('candidates',[]))}\")
# 验证 candidates 是否按 popularity 排序
cands = mr.get('candidates', [])
if len(cands) >= 2:
    print(f\"  first pop: {cands[0].get('popularity',0):.1f}, second pop: {cands[1].get('popularity',0):.1f}\")
if sr.get('selected_candidate'):
    sc = sr['selected_candidate']
    print(f\"  selected: {sc.get('title')} ({sc.get('year')}) why={sc.get('why_selected')}\")
print(f\"  trace search_query: {[t.get('search_query','') for t in mr.get('trace',[]) if t.get('search_query')]}\")
"
done
```

### 期望行为

| 文件名 | 验证点 |
|--------|--------|
| `速度与激情.mkv` | candidates 按 popularity 降序；Tier 2 TraceStep 有 search_query |
| `爱神.mkv` | corrected_year 不为 null（AI 给出 2004）；selected_candidate.why_selected=ai_suggestion |
| `123uyyt.mkv` | match_level=FAILED；前端步骤 4 显示"刮削失败" |
| `美丽人生.mkv` | candidates 排序正确（1997 版排第一） |

### 全部测试

```bash
python -m pytest tests/ -q --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_recycle.py --ignore=tests/test_scrape_preview_ui.py -k "not test_ai_config_ui"
python -m pytest tests/test_architecture_guards.py -q
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests
```

---

## 六、实施顺序

```
修复 1 (通用排序) → 修复 2 (Tier1 限制10条)
    ↓
修复 3 (AI 提示词)
    ↓
修复 4 (TraceStep search_query) → 依赖修复 1 的排序
    ↓
修复 5 (前端流程分化) ↕ 可并行
修复 6 (前端 certainty 徽章) ↕ 可并行
    ↓
标准文档更新
    ↓
全部测试 + 验收场景
```

---

## 七、完成报告

完成后向我报告：
1. 6 个修复是否全部完成
2. 全部测试通过数量
3. 验收场景测试结果（"速度与激情"、"爱神"、"123uyyt"、"美丽人生"）
4. 是否有未预期的行为变更

---

## 附录 A：清缓存+重启命令

```bash
find /Users/wangwei/Documents/code/nas_media_manage -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /Users/wangwei/Documents/code/nas_media_manage -name "*.pyc" -delete 2>/dev/null
pkill -9 -f "python.*media_importer" 2>/dev/null
sleep 2
source /Users/wangwei/Documents/code/nas_media_manage/.venv/bin/activate
PYTHONPATH="/Users/wangwei/Documents/code/nas_media_manage" python -m media_importer.media_importer -c /Users/wangwei/Documents/code/nas_media_manage/config/config.yaml serve -p 9855 --host 0.0.0.0 > /tmp/nas_media_server.log 2>&1 &
sleep 5
```

---

**开始执行。从修复 1 开始。**

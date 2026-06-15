# 2026-06-14 模拟测试/源目录清理/任务卡片/刮削决策 五项修复计划

## 0. 背景

本次修复用户提出的 5 个问题，覆盖模拟测试结果展示、源目录清理配置、任务卡片排版、刮削决策逻辑、任务卡片匹配路径展示。所有改动基于现有代码事实源，不引入新架构。

**执行原则**：
- 不考虑旧字段兼容，一次性按新方案落地
- 每个任务标注影响范围和验收点
- 任务之间相互独立，可并行执行（除任务 4 的 DB 迁移依赖任务 4.1）
- 完成后跑 `python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py -x` 确保无回归

---

## 任务 1：模拟测试结果流程界面标识 AI 模型类型

### 1.1 问题定位

用户报：模拟测试完成后的"结果流程界面"里，三级匹配步骤显示 `第2级：上下文辅助匹配 · ✗ 未匹配 / AI 未给出高确定性选择`，没说清"AI"是 🤖 AI辅助 还是 🔍 AI联网搜索。

**入口**：基础配置 → 运行模拟 → 输入文件名 → 完成后渲染的结果界面
**渲染函数**：`media_importer/webui/js/cinema-config.js:1783` 的 `renderSimulatorPreview(data)`
**关键代码**：第 1853-1890 行渲染三级匹配步骤的循环

### 1.2 改动

**前端 `media_importer/webui/js/cinema-config.js`（约 1853-1890 行）**

在 `step.name` 之前根据 `step.tier` 加图标：
- 第 1 级：`🗄️ ` 前缀（Provider 精确匹配）
- 第 2 级：`🤖 ` 前缀（AI辅助 关键词回搜，走 ai_assist 模型）
- 第 3 级：`👤 ` 前缀（用户确认）

修改 step.reason 之前的标题行：
```js
// 旧
'<div style="font-weight:600;color:' + color + ';font-size:13px">第' +
step.tier + "级：" + escapeHtml(step.name || "") + " · " + ...

// 新
var tierIcon = step.tier === 1 ? "🗄️ " : step.tier === 2 ? "🤖 " : step.tier === 3 ? "👤 " : "";
'<div style="font-weight:600;color:' + color + ';font-size:13px">第' +
step.tier + "级：" + tierIcon + escapeHtml(step.name || "") + " · " + ...
```

同时在 AI reason 行（第 1884-1888 行）的 `AI:` 前缀前加 `🤖 AI辅助:` 让用户明确：
```js
// 旧
'<div ...>AI: ' + escapeHtml(step.ai_reason) + "</div>";

// 新（第二级用 🤖 AI辅助，其他级别不变）
var aiPrefix = step.tier === 2 ? "🤖 AI辅助: " : "AI: ";
'<div ...>' + aiPrefix + escapeHtml(step.ai_reason) + "</div>";
```

**模拟测试 trace 步骤的 label（`media_importer/api/tmdb_handlers.py:154,161,166`）保持不变**（已经是 `第2级：🤖 AI辅助关键词回搜`），那是过程展示，与结果展示不同。

### 1.3 验收

1. 在模拟测试输入 `美丽人生.mkv`，跑完后结果流程界面应显示：
   - `第2级：🤖 上下文辅助匹配 · ✗ 未匹配`
   - 第二级失败时下方 reason 行显示 `🤖 AI辅助: <AI 给出的原因>`
2. 第一级 / 第三级显示对应图标

---

## 任务 2：源目录清理重命名 + 提示词归一化 + 间距修复

### 2.1 问题定位

**问题 A（命名）**：源目录清理界面的"🤖 AI辅助判断"+"启用 AI 联合判断"语义模糊，应改为"AI辅助清理"。

**问题 B（提示词重叠）**：当前代码里存在两个源目录清理提示词字段：
- `source_cleaner.ai_prompt` —— 真正生效（`features/source_cleaning/cleaner.py:59,334,343`）
- `ai_assist.prompt_source_clean` —— 死字段（仅 `PromptResolver` 提供 getter，无人调用）

**用户决策**：保留 `ai_assist.prompt_source_clean` 作为唯一提示词来源，删除 `source_cleaner.ai_prompt`。源目录清理界面不再提供"AI清理提示词"按钮，改为说明文字。

**问题 C（间距）**：合并策略区域（`index.html:395-419` 的 `cleaner-grid`）和上方 `cleaner-card` 间距过大。

### 2.2 改动

#### 2.2.1 后端：源目录清理改用 ai_assist.prompt_source_clean

**文件 `media_importer/features/source_cleaning/cleaner.py`**

第 59 行：
```python
# 旧
self.ai_prompt = cleaner.ai_prompt or AI_SYSTEM_PROMPT

# 新
ai_assist_cfg = self.view.ai_assist
self.ai_prompt = ai_assist_cfg.prompt_source_clean or AI_SYSTEM_PROMPT
```

#### 2.2.2 后端：删除 source_cleaner.ai_prompt 字段

**文件 `media_importer/core/config_view.py`**
- 第 142 行 `ai_prompt: str = ""` 删除（SourceCleanerConfig dataclass）
- 第 253 行 `ai_prompt=source_cleaner.get("ai_prompt", ""),` 删除

**文件 `media_importer/core/db/migrations.py`**
- 检查 `source_cleaner.ai_prompt` 的迁移初始化逻辑（grep `ai_prompt` in migrations），删除相关行

**文件 `media_importer/core/config_loader.py`**
- 如果有 `source_cleaner.setdefault("ai_prompt", ...)`，删除

**文件 `media_importer/api/config_handlers.py` 和 `media_importer/features/configuration/application_service.py`**
- 检查 sensitive_fields 列表和 section_field_map，确保不再引用 `source_cleaner.ai_prompt`

#### 2.2.3 前端：源目录清理界面改造

**文件 `media_importer/webui/index.html`（第 379-394 行）**

旧：
```html
<article class="cleaner-card cleaner-card-full">
    <span>🤖 AI辅助判断</span>
    <label class="toggle-row-inline">
        <input id="cfg-source_cleaner-ai_enabled-inline" type="checkbox" />
        <b>启用 🤖 AI 联合判断</b>
    </label>
    <p>使用 AI辅助模型 联合识别规则无法覆盖的垃圾文件。</p>
    <div class="cleaner-inline-actions" id="sc-ai-actions-inline">
        <button class="btn btn-secondary btn-sm" type="button" id="btn-sc-prompt-inline">🤖 AI清理提示词</button>
    </div>
</article>
```

新：
```html
<article class="cleaner-card cleaner-card-full">
    <span>🤖 AI辅助清理</span>
    <label class="toggle-row-inline">
        <input id="cfg-source_cleaner-ai_enabled-inline" type="checkbox" />
        <b>启用 🤖 AI 辅助清理</b>
    </label>
    <p>使用 AI辅助模型 联合识别规则无法覆盖的垃圾文件。</p>
    <p class="cleaner-hint-text">AI 提示词在 AI 配置 → AI 辅助 → 提示词 tab「源目录清理」中配置。</p>
</article>
```

**注意**：保留 `cfg-source_cleaner-ai_enabled-inline` checkbox 的 id 不变，避免 JS 绑定失效。

#### 2.2.4 前端：删除 source_cleaner.ai_prompt 相关 JS 代码

**文件 `media_importer/webui/js/cinema-config.js`（第 86-87 行）**
- 删除 `buildSourceCleanerPayload` 中 `ai_prompt: ...cfg-source_cleaner-ai_prompt-inline...` 字段

**文件 `media_importer/webui/js/cinema-app.js`（第 893-895 行）**
- 删除 `loadDirectoryConfig` 中对 `cfg-source_cleaner-ai_prompt-inline` 的赋值

**文件 `media_importer/webui/js/cinema-app.js`（第 1189-1192 行附近）**
- 删除对 `btn-sc-prompt-inline` 的事件绑定（grep 该 id 找到所有引用）

#### 2.2.5 前端：旧版 config.js 也同步删除

**文件 `media_importer/webui/js/config.js`**
- 删除第 376-377 行（aiPromptEl 相关）
- 删除第 737-738 行（ai_prompt payload 字段）
- 删除第 1444 行（默认提示词生成逻辑）

#### 2.2.6 CSS：合并策略间距修复

**文件 `media_importer/webui/css/cinema-pages.css`**

定位 `.cleaner-grid`（第 1651 行）和上方 `.cleaner-card` 的间距：
```css
/* 检查现有规则，应该有 margin-top: 16px 或更大 */
.cleaner-grid { 
    /* 添加或修改：缩小上方间距 */
    margin-top: 8px;
}
```

实际改动需要先读现有 CSS 上下文（第 1645-1700 行），找到造成大间距的属性（可能是 margin-top 或 padding），改成与同区域其他 card 之间间距一致（推荐 8px）。

### 2.3 验收

1. 源目录清理界面卡片标题显示"🤖 AI辅助清理"，开关文案"启用 🤖 AI 辅助清理"
2. 不再有"🤖 AI清理提示词"按钮，改为说明文字
3. AI 配置 → AI 辅助 → 提示词 tab「源目录清理」中的内容修改后保存，触发源目录清理时使用此提示词（用日志或断点验证 cleaner.py:59 取到的是 ai_assist.prompt_source_clean）
4. 合并策略区域和上方间距与其他卡片间距一致
5. `grep -r "source_cleaner.ai_prompt\|cfg-source_cleaner-ai_prompt" media_importer/` 无结果

---

## 任务 3：任务卡片第三行排版区分

### 3.1 问题定位

**位置**：`media_importer/webui/js/cinema-tasks.js:229`
```js
<div class="task-meta"><span>${escapeHtml(filename)}</span><span>${escapeHtml(taskMeta(item))}</span></div>
```

两个 span 相邻无分隔，无视觉差异；`.task-meta` 在 CSS 中无规则定义。

### 3.2 改动

#### 3.2.1 HTML 结构调整

**文件 `media_importer/webui/js/cinema-tasks.js:229`**

```js
// 旧
<div class="task-meta"><span>${escapeHtml(filename)}</span><span>${escapeHtml(taskMeta(item))}</span></div>

// 新
<div class="task-meta">
    <span class="task-meta-file">📄 ${escapeHtml(filename)}</span>
    <span class="task-meta-sep">·</span>
    <span class="task-meta-info">${escapeHtml(taskMeta(item))}</span>
</div>
```

#### 3.2.2 CSS 样式定义

**文件 `media_importer/webui/css/cinema-pages.css`**（在 `.task-top` 规则附近，第 990 行后追加）

```css
.task-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 6px;
    font-size: 12px;
    line-height: 1.4;
    flex-wrap: wrap;
}
.task-meta-file {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--text-secondary, #94A3B8);
    max-width: 60%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.task-meta-sep {
    color: var(--text-muted, #64748B);
}
.task-meta-info {
    color: var(--text-primary, #CBD5E1);
    font-weight: 500;
}
```

### 3.3 验收

1. 任务列表的每个卡片第三行：filename 显示为等宽字体 + 灰色 + 带文件图标，后面跟 `·` 分隔符，再显示 taskMeta（电影 · 2023 · 🤖 AI辅助匹配 等）
2. 两者视觉上明显区分，不再是粘在一起的同色同字体文字
3. 长 filename 不撑破卡片（ellipsis 截断）

---

## 任务 4：刮削失败原因和改进建议清晰化

### 4.1 _build_minimal_result 功能说明

**位置**：`media_importer/scraper/metadata_scrape_flow.py:79-99`

**作用**：在 Provider 完全搜不到任何候选时（例如文件名"美丽人生.mkv"在 TMDB 搜不到匹配作品），构建一个"最小结果"返回，避免整个刮削流程异常。当前最小结果只设置了 `title`（来自 clean_title），没有 `title_cn`/`title_en`，且 `match_level` 未显式设置（默认后续会被 MatchEngine 设为 NEEDS_CONFIRM）。

**用户痛点**：
1. Provider 无结果时，`title_cn`/`title_en` 字段确实为空 → `ReviewDecisionService` 报"中文名和英文名都缺失"，但 clean_title 其实有值，提示不准确
2. 失败原因太机械，没把 AI 给出的判断（如"无年份无法区分 1997 vs 2020"）作为原因展示
3. 走第三级用户确认时，没默认选中第一个候选（按热度排序），让用户每次都要手动选

### 4.2 改动

#### 4.2.1 _build_minimal_result 字段修复

**文件 `media_importer/scraper/metadata_scrape_flow.py:79-99`**

```python
def _build_minimal_result(clean_result, enabled_dims_set=None,
                          provider_fallback_reasons=None, ai_clean_result=None,
                          scrape_mode="provider_first", ai_invoke_reason=None):
    """Build a minimal result dict when no provider match and no AI available.

    Provider 完全无候选时的兜底返回。字段对齐 review 校验期望，
    避免被误判为"中文名和英文名都缺失"。
    """
    # clean_title 作为中文标题候选（可能本身就是英文，review 不强制区分）
    title_cn = clean_result.clean_title or ""
    result = {
        "title": title_cn,
        "title_cn": title_cn,                      # 新增：避免 review 误判
        "title_en": "",                            # 新增：显式声明无英文标题
        "year": clean_result.year,
        "season": clean_result.season,
        "episode": clean_result.episode,
        "media_type": "tv" if clean_result.season else "movie",
        "provider_type": "",
        "provider_id": "",
        "scrape_trace": {},
    }
    if provider_fallback_reasons:
        result["scrape_trace"]["provider_fallback_reasons"] = provider_fallback_reasons
    _inject_trace_fields(result, scrape_mode, ai_invoked=False, ai_invoke_reason=ai_invoke_reason)
    return result
```

#### 4.2.2 review.py 失败原因改为可执行建议

**文件 `media_importer/features/import_flow/services/review.py`**

把 `_validate_required_fields` 和 `evaluate` 的失败原因改为可执行建议，并把 AI 给出的判断（在 `scraped.match_concerns` 或 `scraped.scrape_trace` 中）作为原因一部分。

```python
class ReviewDecisionService:
    def evaluate(self, scraped: dict) -> ReviewDecision:
        if not scraped:
            return ReviewDecision(action="failed", reason="刮削结果为空，无法验证")

        match_level = scraped.get("match_level", "NEEDS_CONFIRM")
        concerns = scraped.get("match_concerns", [])
        confirm_reason_parts = []

        # 1. 收集 AI / MatchEngine 给出的问题（来自 concerns）
        for c in concerns:
            msg = c.get("message", "")
            if msg:
                confirm_reason_parts.append(msg)

        # 2. 收集 AI 辅助判断给出的具体 reason（来自 scrape_trace.ai_reason 或 match_trace）
        scrape_trace = scraped.get("scrape_trace", {}) or {}
        match_trace = scraped.get("match_trace", {}) or {}
        ai_reasons = self._collect_ai_reasons(match_trace)
        confirm_reason_parts.extend(ai_reasons)

        # 3. 字段校验：只校验真正缺失的关键字段
        missing_fields, warnings = self._validate_required_fields(scraped)
        if missing_fields:
            # 不再机械说"刮削信息不足"，改为可执行建议
            suggestions = self._build_suggestions(missing_fields, scraped)
            reason = "未匹配到 Provider 候选。建议补充：" + "；".join(suggestions)
            if confirm_reason_parts:
                reason += "。AI 判断：" + "；".join(confirm_reason_parts)
            return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

        if match_level == "AUTO_PASS":
            return ReviewDecision(action="continue", warnings=warnings)

        if match_level == "CONTEXT_PASS":
            return ReviewDecision(action="continue", warnings=warnings)

        if match_level == "NEEDS_CONFIRM":
            if confirm_reason_parts:
                reason = "；".join(confirm_reason_parts)
            else:
                reason = "需要人工确认"
            return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

        return ReviewDecision(action="failed", reason="匹配失败，无法识别", warnings=warnings)

    def _collect_ai_reasons(self, match_trace: dict) -> list:
        """从 match_trace.trace_steps 中收集 AI 给出的 reason 字段。"""
        reasons = []
        steps = match_trace.get("trace_steps") or match_trace.get("trace") or []
        if not isinstance(steps, list):
            return reasons
        for step in steps:
            ai_reason = step.get("ai_reason") if isinstance(step, dict) else None
            if ai_reason and isinstance(ai_reason, str) and ai_reason.strip():
                reasons.append(ai_reason.strip())
        return reasons

    def _build_suggestions(self, missing_fields: list, scraped: dict) -> list:
        """根据缺失字段生成可执行的改进建议。"""
        suggestions = []
        has_title_cn = bool(scraped.get("title_cn"))
        has_title_en = bool(scraped.get("title_en"))

        for field in missing_fields:
            if "title" in field.lower():
                if not has_title_cn and not has_title_en:
                    suggestions.append("精确的中文或英文标题（当前两者都缺失）")
                elif not has_title_cn:
                    suggestions.append("中文标题")
                elif not has_title_en:
                    suggestions.append("英文标题")
            elif "year" in field.lower():
                suggestions.append("上映年份（用于区分同名作品）")
            elif "type" in field.lower() or "media" in field.lower():
                suggestions.append("影视类型（电影/电视剧）")
        return suggestions

    def _validate_required_fields(self, scraped: dict):
        """校验必填字段。title_cn 和 title_en 至少一个有值即视为有标题。"""
        missing_fields = []
        warnings = []

        title_cn = scraped.get("title_cn")
        title_en = scraped.get("title_en")
        title = scraped.get("title")  # 兜底
        year = scraped.get("year")
        media_type = scraped.get("media_type")

        has_title = bool(title_cn or title_en or title)
        has_type = bool(media_type)
        has_year = bool(year)

        if not has_title:
            missing_fields.append("title")
        if not has_type:
            missing_fields.append("media_type")
        if not has_year:
            if has_title and has_type:
                title_for_warn = title_cn or title_en or title
                warnings.append(f"年份缺失(可接受，标题已识别: {title_for_warn})")
            else:
                missing_fields.append("year")

        if year:
            try:
                parsed_year = int(year)
                if parsed_year < 1900 or parsed_year > 2030:
                    warnings.append(f"年份异常: {year}")
                    missing_fields.append(f"年份异常: {year}")
            except (ValueError, TypeError):
                warnings.append(f"年份格式异常: {year}")

        return missing_fields, warnings
```

#### 4.2.3 第三级用户确认默认选中第一个候选

**位置**：`media_importer/features/scraping/match_engine.py` 的 `_tier3_user_confirm`

确认现状：第 175-180 行（tmdb_handlers.py 模拟测试的 tier3 处理）已经设置了 `preview_selected_candidate=True`，并取 `candidates[0]`。但 **真实入库流程**走 `MatchEngine._tier3_user_confirm`，需要确认是否也默认选中第一个。

**文件 `media_importer/features/scraping/match_engine.py`**

读 `_tier3_user_confirm` 方法，确认 `MatchResult.candidates` 是按 Provider 返回顺序（通常 TMDB 已经按 popularity 排序）保存。无需额外排序，只需在前端展示时默认选中第一个。

**前端文件 `media_importer/webui/js/cinema-tasks.js`**

找到任务详情弹窗中候选列表的渲染（grep `candidates` in cinema-tasks.js），确认是否默认选中第一个候选 radio/option。如果未选中，加上 `checked` 或 `selected`。

### 4.3 验收

1. 输入 `美丽人生.mkv`，模拟测试结果显示：
   - 不再出现"刮削信息不足，需要人工确认。缺失字段: 中文名和英文名都缺失；年份缺失"
   - 改为出现类似"未匹配到 Provider 候选。建议补充：精确的中文或英文标题（当前两者都缺失）；上映年份（用于区分同名作品）。AI 判断：<AI 给出的原因>"
2. 第三级用户确认时，候选列表第一个默认被选中
3. 真实入库流程（不是模拟测试）同样表现

---

## 任务 5：任务卡片"查看匹配路径"与模拟测试展示统一

### 5.1 问题定位

**现状**：
- 模拟测试用 `renderSimulatorPreview`（`cinema-config.js:1783`）渲染：时间线步骤样式 + KV 表
- 任务卡片"查看匹配路径"用 `showMatchTraceDetailModal`（`match-trace-detail.js:76`）渲染：步骤卡片样式

两者样式完全不同。用户希望统一。

**数据现状**：task 已经持久化了 `scrape_result / match_trace / scrape_trace / dim_sources / scrape_title_cn/en/year/...` 等字段（见 `features/import_flow/steps/scrape.py:161-180`），不需要改 DB schema。

### 5.2 改动

#### 5.2.1 抽取 renderSimulatorPreview 为公共函数

**文件 `media_importer/webui/js/cinema-config.js`**

把 `renderSimulatorPreview(data)` 重命名为 `renderMatchPathPreview(data, mountEl)`，并允许指定挂载点：

```js
// 旧：function renderSimulatorPreview(data) { ... result.innerHTML = html; }
// 新
function renderMatchPathPreview(data) {
    // 返回 HTML 字符串，不直接挂载
    const clean = data.clean_result || {};
    const matchResult = data.match_result || {};
    // ...（保持原渲染逻辑）
    return html;
}

// 保留旧函数名作为薄包装，避免破坏现有调用
function renderSimulatorPreview(data) {
    const result = document.getElementById("match-preview-result");
    if (!result) return;
    result.innerHTML = renderMatchPathPreview(data);
}
```

#### 5.2.2 任务详情"查看匹配路径"改用统一渲染

**文件 `media_importer/webui/js/cinema-tasks.js:612-634`**（`buildScrapeTraceSection`）

把当前的"查看匹配路径"按钮替换为：点击后弹出一个 modal，modal 内容调用 `renderMatchPathPreview`，数据从 task 字段构造。

```js
function buildScrapeTraceSection(task) {
    var scrapeTrace = task.scrape_trace;
    if (!scrapeTrace || typeof scrapeTrace !== "object") return "";

    var filename = task.source_filename || "";

    var searchBadge = "";
    if (scrapeTrace.search_enhanced === true) {
        searchBadge = '<span style="...">🔍 AI联网搜索增强</span>';
    } else if (scrapeTrace.search_enhanced === false) {
        searchBadge = '<span style="...">📴 纯本地分析</span>';
    }

    // 把 task 字段构造成 renderMatchPathPreview 期望的 data 结构
    var previewData = taskToMatchPathData(task);

    // 把 data 编码进 data-attr，点击时解码传给 modal
    var dataJson = encodeURIComponent(JSON.stringify(previewData));

    return `
        <div class="cinema-modal-block">
            <h4>决策路径${searchBadge}</h4>
            <div class="cinema-modal-hint" style="margin-bottom:8px">展示刮削过程中的完整匹配路径。</div>
            <button class="btn btn-secondary btn-sm" onclick="showMatchPathModalFromData(this.getAttribute('data-preview'))" data-preview="${dataJson}" data-filename="${escapeHtml(filename)}">查看匹配路径</button>
        </div>`;
}

function taskToMatchPathData(task) {
    return {
        filename: task.source_filename || "",
        clean_result: task.scrape_trace?.filename_clean || {
            clean_title: task.scrape_title_cn || task.scrape_title_en || "",
            year: task.scrape_year,
            season: task.scrape_season,
            episode: task.scrape_episode,
        },
        scrape_result: task.scrape_result || {},
        match_result: typeof task.match_trace === "string"
            ? JSON.parse(task.match_trace || "{}")
            : (task.match_trace || {}),
        import_path: {
            import_path: task.import_video_path || "",
            used_fallback: false,
            matched_rule: null,
        },
    };
}

function showMatchPathModalFromData(dataJson) {
    var data = JSON.parse(decodeURIComponent(dataJson));
    var overlay = document.createElement("div");
    overlay.className = "conf-detail-overlay";
    overlay.innerHTML = `
        <div class="conf-detail-modal" style="max-width:900px">
            <div class="conf-detail-header">
                <h3 style="margin:0;font-size:16px">匹配路径详情</h3>
                <button onclick="this.closest('.conf-detail-overlay').remove()" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:20px;padding:4px 8px">&times;</button>
            </div>
            <div class="conf-detail-body" style="padding:16px;max-height:80vh;overflow-y:auto">
                ${renderMatchPathPreview(data)}
            </div>
        </div>`;
    overlay.addEventListener("click", function (e) {
        if (e.target === overlay) overlay.remove();
    });
    document.body.appendChild(overlay);
}
```

#### 5.2.3 兼容旧版 tasks.js 的同名按钮

**文件 `media_importer/webui/js/tasks.js:1558-1574`** 也用相同方式替换。

#### 5.2.4 删除或保留 match-trace-detail.js

**可选**：`media_importer/webui/js/match-trace-detail.js` 整个文件可以删除（其 `showMatchTraceDetailModal` 不再被调用）。

但为了减少回归风险，保留文件，只是不再从 cinema-tasks.js / tasks.js 调用。如果确认无其他引用，可以删除文件 + 删除 index.html 中的 `<script>` 引用。

**验证**：`grep -r "showMatchTraceDetailModal\|match-trace-detail" media_importer/webui/` 确认无残留调用后删除。

### 5.3 验收

1. 模拟测试完成后的结果展示样式 与 任务详情"查看匹配路径"弹窗样式 **完全一致**
2. 任务详情弹窗能正确显示该任务当时的 clean_result / 三级匹配步骤 / scrape_result / 入库路径
3. 不需要重新跑模拟测试，直接点开历史任务就能看到完整路径

---

## 任务 6：综合验收（执行人完成所有改动后做）

### 6.1 编译 / 测试

```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py -x
```

### 6.2 端到端验收

启动服务后：
1. **任务 1**：基础配置 → 运行模拟 → 输入 `美丽人生.mkv` → 结果流程界面里第二级显示 🤖 图标
2. **任务 2**：源目录清理界面标题为"🤖 AI辅助清理"；开关为"启用 🤖 AI 辅助清理"；无"AI清理提示词"按钮；合并策略间距正常
3. **任务 3**：任务列表卡片第三行：filename 等宽字体灰色 + 文件图标 + `·` 分隔符 + taskMeta 加粗
4. **任务 4**：模拟测试 `美丽人生.mkv` 的失败原因展示可执行建议（"建议补充：..."）+ AI 判断原因
5. **任务 5**：任务详情"查看匹配路径"弹窗样式 与 模拟测试结果样式 一致

### 6.3 残留检查

```bash
grep -r "source_cleaner.ai_prompt\|cfg-source_cleaner-ai_prompt\|btn-sc-prompt-inline" media_importer/
# 应无结果

grep -r "showMatchTraceDetailModal" media_importer/webui/js/cinema-tasks.js media_importer/webui/js/tasks.js
# 应无结果（已改为 showMatchPathModalFromData）
```

---

## 执行顺序建议

1. **任务 2**（源目录清理命名 + 死字段清理 + 间距）—— 独立，先做
2. **任务 3**（任务卡片第三行排版）—— 独立，可并行
3. **任务 1**（模拟测试结果展示加模型图标）—— 独立，可并行
4. **任务 4**（review.py + _build_minimal_result）—— 独立，可并行
5. **任务 5**（匹配路径展示统一）—— 依赖任务 1 的 renderSimulatorPreview（因为要做样式对齐），最后做
6. **任务 6**（综合验收）

---

## 风险提示

- **任务 2** 删除 `source_cleaner.ai_prompt` 后，存量 config.yaml 里如果用户已经填了该字段，需要忽略该字段（不报错）。loader 通常对未知字段容忍，但要在测试中确认。
- **任务 4** 的 review.py 改动影响所有入库流程的失败提示，需要在改完后跑 `tests/test_review_decision_v2.py` 和相关的 review 测试用例，必要时同步更新测试 fixture。
- **任务 5** 抽取 `renderMatchPathPreview` 时要确保不破坏 `renderSimulatorPreview` 的现有行为，改完后跑模拟测试确认渲染正常。

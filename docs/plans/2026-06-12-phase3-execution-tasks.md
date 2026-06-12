# 阶段 3 执行文档：前端适配

> 本文档供 deepseek-v4flash / minimax-m3 等模型直接执行。
> 每个任务都是原子操作，包含精确的文件路径、代码骨架和验证步骤。
> **严格按任务编号顺序执行**，不可跳步。
> **前置条件**：阶段 1 和阶段 2 全部完成，后端 `match_level` / `match_concerns` 字段已可用。

---

## 任务 3.1：移除 `cinema-confidence.js` 和 `cinema-confidence.css` 引用

**文件**：`media_importer/webui/index.html`

**操作**：删除 CSS link 和 JS script 标签

### 替换 1：删除 CSS 引用（第 15-16 行）

找到：

```html
    <link rel="stylesheet" href="css/cinema-confidence.css?v=1">
    <link rel="stylesheet" href="css/cinema-confidence-dimensions.css?v=1">
```

替换为（空行，即删除这两行）：

```html
```

### 替换 2：删除 JS 引用（第 860 行区域）

找到：

```html
    <script src="js/cinema-confidence.js?v=2"></script>
```

替换为（空行，即删除这一行）：

```html
```

**验证**：
- 在浏览器中打开页面，确认页面正常加载，无 JS 控制台报错
- 确认置信度配置面板不再显示

---

## 任务 3.2：移除 `confidence-detail.js` 引用

**文件**：`media_importer/webui/index.html`

**操作**：删除 JS script 标签

找到：

```html
    <script src="js/confidence-detail.js?v=3"></script>
```

替换为（空行，即删除这一行）：

```html
```

**验证**：
- 页面正常加载，无 JS 控制台报错

---

## 任务 3.3：移除 `cinema-confidence-dimensions.css` 引用

**文件**：`media_importer/webui/index.html`

**操作**：已在任务 3.1 中一并删除。确认第 16 行的 `<link rel="stylesheet" href="css/cinema-confidence-dimensions.css?v=1">` 已被移除。

**验证**：
- 搜索 `index.html` 中不再包含 `cinema-confidence` 和 `cinema-confidence-dimensions` 关键字

---

## 任务 3.4：改造 `cinema-tasks.js` 中的 `taskMeta()` 函数

**文件**：`media_importer/webui/js/cinema-tasks.js`

**操作**：替换 `taskMeta()` 函数中的置信度数值展示为 match_level 标签

找到（第 76-94 行）：

```javascript
function taskMeta(task) {
    const bits = [];
    const status = String(task.status || "").toUpperCase();
    const scrape = task.scrape_result || {};
    const confidence = task.scrape_confidence ?? scrape.confidence;
    const mediaType = task.scrape_media_type || scrape.type;
    const year = task.scrape_year || scrape.year;
    if (mediaType === "movie") bits.push("电影");
    if (mediaType === "tv") bits.push("剧集");
    if (year) bits.push(String(year));
    if (confidence !== undefined && confidence !== null && confidence !== "") {
        const value = Number(confidence);
        if (!Number.isNaN(value)) bits.push(`置信度 ${value.toFixed(2)}`);
    }
    if (status === "FAILED" && task.error_message) bits.push("查看失败原因");
    if (["SUCCESS", "SKIPPED", "CANCELLED"].includes(status) && task.completed_at) bits.push(formatActivityTime(task.completed_at));
    if (bits.length === 0 && task.created_at) bits.push(formatActivityTime(task.created_at));
    return bits.join(" · ") || "等待处理";
}
```

替换为：

```javascript
function taskMeta(task) {
    const bits = [];
    const status = String(task.status || "").toUpperCase();
    const scrape = task.scrape_result || {};
    const matchLevel = task.match_level || task.scrape_match_level || scrape.match_level;
    const mediaType = task.scrape_media_type || scrape.type;
    const year = task.scrape_year || scrape.year;
    if (mediaType === "movie") bits.push("电影");
    if (mediaType === "tv") bits.push("剧集");
    if (year) bits.push(String(year));
    if (matchLevel === "AUTO_PASS") bits.push("自动匹配");
    else if (matchLevel === "CONTEXT_PASS") bits.push("AI辅助匹配");
    else if (matchLevel === "NEEDS_CONFIRM") bits.push("需确认");
    if (status === "FAILED" && task.error_message) bits.push("查看失败原因");
    if (["SUCCESS", "SKIPPED", "CANCELLED"].includes(status) && task.completed_at) bits.push(formatActivityTime(task.completed_at));
    if (bits.length === 0 && task.created_at) bits.push(formatActivityTime(task.created_at));
    return bits.join(" · ") || "等待处理";
}
```

**验证**：
- 在浏览器中查看任务卡片，确认显示"自动匹配"/"AI辅助匹配"/"需确认"标签，而非"置信度 0.83"

---

## 任务 3.5：改造 `cinema-tasks.js` 中的任务描述

**文件**：`media_importer/webui/js/cinema-tasks.js`

**操作**：在 `taskDescription()` 函数中，为待确认任务增加疑虑原因展示

找到（第 48-74 行）：

```javascript
function taskDescription(task) {
    const status = String(task.status || "").toUpperCase();
    const stage = String(task.stage || "").toUpperCase();
    const scrape = task.scrape_result || {};
    if (task.error_message) return task.error_message;
    if (task.skip_reason) return task.skip_reason;
    if (status === "PENDING" && stage === "AWAIT_REVIEW") {
        return "AI 已给出候选结果，等待你确认最终入库方向。";
    }
```

替换为：

```javascript
function taskDescription(task) {
    const status = String(task.status || "").toUpperCase();
    const stage = String(task.stage || "").toUpperCase();
    const scrape = task.scrape_result || {};
    if (task.error_message) return task.error_message;
    if (task.skip_reason) return task.skip_reason;
    if (status === "PENDING" && stage === "AWAIT_REVIEW") {
        const concerns = task.match_concerns || scrape.match_concerns || [];
        if (Array.isArray(concerns) && concerns.length > 0) {
            const concernMessages = concerns.map(c => c.message || (typeof c === "string" ? c : "")).filter(Boolean);
            if (concernMessages.length > 0) {
                return concernMessages.join("；") + "。等待你确认最终入库方向。";
            }
        }
        return "需要你确认最终匹配结果。";
    }
```

**验证**：
- 查看待确认任务的描述，确认显示疑虑原因（如"找到3部同名作品；标题不完全匹配。等待你确认最终入库方向。"）

---

## 任务 3.6：改造 `cinema-config.js` 中的模拟运行函数

**文件**：`media_importer/webui/js/cinema-config.js`

**操作**：将 `renderSimulatorPreview()` 函数从双模式对比改为三级匹配展示

### 替换 1：`explainSimulatedQueue` 函数（第 1305-1314 行）

找到：

```javascript
function explainSimulatedQueue(score, confidence) {
    const pass = Number(confidence?.pass_threshold ?? 0.8);
    const confirm = Number(confidence?.confirm_threshold ?? 0.5);
    const review = Number(confidence?.review_threshold ?? 0.3);
    if (!Number.isFinite(score)) return "当前结果未返回可用置信度，请结合标题和 Provider 命中情况手动判断。";
    if (score >= pass) return `命中自动通过阈值 ${pass.toFixed(2)}，会优先进入自动入库队列。`;
    if (score >= confirm) return `低于自动通过阈值但高于确认阈值 ${confirm.toFixed(2)}，建议进入待确认队列。`;
    if (score >= review) return `低于确认阈值但高于审核阈值 ${review.toFixed(2)}，建议先人工审核再继续。`;
    return `低于审核阈值 ${review.toFixed(2)}，更适合先停在失败/人工处理链路。`;
}
```

替换为：

```javascript
function explainSimulatedQueue(matchLevel, concerns) {
    if (matchLevel === "AUTO_PASS") return "标题精确匹配，自动通过，直接进入入库队列。";
    if (matchLevel === "CONTEXT_PASS") return "AI 辅助匹配通过，上下文信息支持自动入库。";
    if (matchLevel === "NEEDS_CONFIRM") {
        const concernMessages = (concerns || []).map(c => c.message || "").filter(Boolean);
        if (concernMessages.length > 0) {
            return "需要人工确认：" + concernMessages.join("；") + "。";
        }
        return "需要人工确认匹配结果。";
    }
    return "匹配结果未知，请结合标题和 Provider 命中情况手动判断。";
}
```

### 替换 2：`renderSimulatorPreview` 函数中的模式对比部分

找到 `renderSimulatorPreview` 函数中第 1331-1335 行区域：

```javascript
    const currentRes = (modes[currentMode] || {}).result || {};
    const currentScore = Number(currentRes.confidence);
    const currentTitle = currentRes.title_cn || currentRes.title_en || currentRes.title || clean.clean_title || data.filename;
    const currentType = currentRes.type || currentRes.media_type || "—";
    const queueExplanation = explainSimulatedQueue(currentScore, getConfidenceConfig());
```

替换为：

```javascript
    const currentRes = (modes[currentMode] || {}).result || {};
    const currentScore = Number(currentRes.confidence);
    const currentMatchLevel = currentRes.match_level || (currentScore >= 0.8 ? "AUTO_PASS" : currentScore >= 0.5 ? "NEEDS_CONFIRM" : "NEEDS_CONFIRM");
    const currentTitle = currentRes.title_cn || currentRes.title_en || currentRes.title || clean.clean_title || data.filename;
    const currentType = currentRes.type || currentRes.media_type || "—";
    const currentConcerns = currentRes.match_concerns || [];
    const queueExplanation = explainSimulatedQueue(currentMatchLevel, currentConcerns);
```

### 替换 3：最终置信度展示改为匹配级别展示

在 `renderSimulatorPreview` 函数中，找到最终置信度展示区域（约第 1465 行）：

```javascript
    html += `<div class="sim-kv"><span class="sim-k">最终置信度</span><span class="sim-v sim-v-score" style="color:${_simConfColor(currentScore)}">${Number.isFinite(currentScore) ? currentScore.toFixed(3) : "--"}</span></div>`;
```

替换为：

```javascript
    const matchLevelLabel = currentMatchLevel === "AUTO_PASS" ? "自动匹配" : currentMatchLevel === "CONTEXT_PASS" ? "AI辅助匹配" : "需确认";
    const matchLevelColor = currentMatchLevel === "AUTO_PASS" ? "#22C55E" : currentMatchLevel === "CONTEXT_PASS" ? "#06B6D4" : "#F59E0B";
    html += `<div class="sim-kv"><span class="sim-k">匹配级别</span><span class="sim-v sim-v-score" style="color:${matchLevelColor}">${matchLevelLabel}</span></div>`;
```

### 替换 4：队列决策展示区域

找到（约第 1472 行）：

```javascript
    html += `<div class="sim-queue-decision" style="border-color:${_simConfColor(currentScore)}30;background:${_simConfColor(currentScore)}08;color:${_simConfColor(currentScore)}">${escapeHtml(queueExplanation)}</div>`;
```

替换为：

```javascript
    const queueColor = currentMatchLevel === "AUTO_PASS" ? "#22C55E" : currentMatchLevel === "CONTEXT_PASS" ? "#06B6D4" : "#F59E0B";
    html += `<div class="sim-queue-decision" style="border-color:${queueColor}30;background:${queueColor}08;color:${queueColor}">${escapeHtml(queueExplanation)}</div>`;
```

**验证**：
- 在配置页面点击"运行模拟"，确认展示三级匹配标签而非置信度数值

---

## 任务 3.7：移除 `cinema-config.js` 中的置信度相关函数

**文件**：`media_importer/webui/js/cinema-config.js`

**操作**：删除 `saveConfidenceConfig` 函数

找到（第 374-384 行）：

```javascript
async function saveConfidenceConfig() {
    const payload = { confidence: typeof getConfidenceConfig === "function" ? getConfidenceConfig() : {} };
    const result = await requestApi("POST", "/config/section", {
        section: "confidence",
        data: payload,
    });
    showToast(result.message || "置信度配置已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
}
```

替换为（空行，即删除整个函数）：

```javascript
```

**注意**：`getConfidenceConfig` 函数定义在 `cinema-confidence.js` 中（已在任务 3.1 中移除引用），不需要单独处理。如果 `renderSimulatorPreview` 中仍有对 `getConfidenceConfig` 的调用，需确认已在任务 3.6 中替换。

**验证**：
- 搜索 `cinema-config.js` 中不再包含 `saveConfidenceConfig` 和 `getConfidenceConfig` 关键字

---

## 任务 3.8：移除 `cinema-app.js` 中的置信度事件绑定

**文件**：`media_importer/webui/js/cinema-app.js`

**操作**：移除 3 处置信度相关代码

### 替换 1：STICKY_HERO_VIEWS 中的 confidence-config（第 45 行）

找到：

```javascript
    "confidence-config",
```

替换为（删除此行）：

```javascript
```

### 替换 2：置信度模拟按钮事件（第 686-689 行区域）

找到：

```javascript
        if (event.target.closest("#btn-confidence-simulate")) {
            runConfigSimulator();
            return;
        }
```

替换为：

```javascript
```

### 替换 3：置信度详情按钮事件（第 690-697 行区域）

找到：

```javascript
        const confidenceDetailAction = event.target.closest("[data-confidence-detail-action=\"open\"]");
        if (confidenceDetailAction) {
            const trace = confidenceDetailAction.dataset.trace;
            const filename = confidenceDetailAction.dataset.filename || "";
            if (trace && typeof showConfidenceDetailModal === "function") {
                showConfidenceDetailModal(JSON.parse(trace), filename);
            }
            return;
        }
```

替换为：

```javascript
```

### 替换 4：configSave actionMap 中的 confidence（第 772 行区域）

找到：

```javascript
                confidence: saveConfidenceConfig,
```

替换为（删除此行）：

```javascript
```

### 替换 5：input 事件中的阈值条更新（第 873 行区域）

找到：

```javascript
        if (event.target.closest('[data-section="confidence"] input[data-key]')) updateThresholdBar();
```

替换为：

```javascript
```

**验证**：
- 搜索 `cinema-app.js` 中不再包含 `confidence` 关键字（`cfg-llm_confidence_threshold` 除外，这是 AI 配置中的字段，保留）
- 页面正常加载，无 JS 控制台报错

---

## 任务 3.9：改造 `dimensions.js`（移除来源信任配置 UI）

**文件**：`media_importer/webui/js/dimensions.js`

**操作**：搜索并移除来源信任相关 UI 代码

在 `dimensions.js` 中搜索以下关键字，如果找到则删除相关代码块：
- `trusted` / `来源信任` / `source_trust` / `trust`

**当前状态**：经搜索，`dimensions.js` 中不包含来源信任配置相关代码，无需修改。

**验证**：
- 确认 `dimensions.js` 中无 `trusted` / `来源信任` / `source_trust` 关键字

---

## 任务 3.10：改造 `tasks.js` 旧版（移除置信度展示）

**文件**：`media_importer/webui/js/tasks.js`

**操作**：移除旧版任务表格中的置信度展示

### 替换 1：任务列表中的置信度展示（第 245-246 行区域）

找到：

```javascript
    if (task.scrape_confidence != null && task.scrape_confidence !== '') {
        var conf = Number(task.scrape_confidence);
```

以及后续的置信度格式化展示代码，将整个 if 块替换为 match_level 展示：

找到（约第 245-246 行开始的置信度展示块）：

```javascript
    if (task.scrape_confidence != null && task.scrape_confidence !== '') {
        var conf = Number(task.scrape_confidence);
```

将其及后续的置信度展示代码（到该 if 块结束）替换为：

```javascript
    var matchLevel = task.match_level || task.scrape_match_level || '';
    if (matchLevel === 'AUTO_PASS') {
        bits.push('<span class="match-tag match-auto">自动匹配</span>');
    } else if (matchLevel === 'CONTEXT_PASS') {
        bits.push('<span class="match-tag match-context">AI辅助匹配</span>');
    } else if (matchLevel === 'NEEDS_CONFIRM') {
        bits.push('<span class="match-tag match-confirm">需确认</span>');
    }
```

### 替换 2：任务详情中的置信度展示（第 544-552 行区域）

找到：

```javascript
        if (scrapeResult.confidence !== undefined) {
            var conf = Number(scrapeResult.confidence);
```

以及后续的置信度展示代码，将整个 if 块替换为 match_level 展示：

```javascript
        var detailMatchLevel = scrapeResult.match_level || task.match_level || '';
        if (detailMatchLevel === 'AUTO_PASS') {
            scrapeFields.push(['匹配级别', '<span class="match-tag match-auto">自动匹配</span>']);
        } else if (detailMatchLevel === 'CONTEXT_PASS') {
            scrapeFields.push(['匹配级别', '<span class="match-tag match-context">AI辅助匹配</span>']);
        } else if (detailMatchLevel === 'NEEDS_CONFIRM') {
            scrapeFields.push(['匹配级别', '<span class="match-tag match-confirm">需确认</span>']);
        }
```

### 替换 3：trace 详情中的置信度计算展示（第 1023-1131 行区域）

找到 trace 渲染中所有 `confidence_calc` / `search_conf` / `final_confidence` 相关的展示代码，将其替换为三级匹配路径展示。

找到（约第 1023 行开始）：

```javascript
    var cc = trace.confidence_calc;
```

将其到该函数块结束的整个置信度计算展示区域替换为：

```javascript
    // 三级匹配路径展示
    var matchTrace = trace;
    if (matchTrace && typeof matchTrace === 'object') {
        var traceSteps = matchTrace.trace || [];
        if (Array.isArray(traceSteps) && traceSteps.length > 0) {
            var traceHtml = '<div class="trace-timeline">';
            for (var si = 0; si < traceSteps.length; si++) {
                var step = traceSteps[si];
                var stepColor = step.matched ? '#22C55E' : '#94A3B8';
                var stepIcon = step.matched ? '✓' : '✗';
                traceHtml += '<div class="trace-step">';
                traceHtml += '<div class="trace-step-dot" style="background:' + stepColor + '18;color:' + stepColor + '">' + stepIcon + '</div>';
                traceHtml += '<div class="trace-step-content">';
                traceHtml += '<div class="trace-step-title" style="color:' + stepColor + '">第' + step.tier + '级：' + _escapeHtml(step.name || '') + '</div>';
                if (step.reason) traceHtml += '<div class="trace-step-reason">' + _escapeHtml(step.reason) + '</div>';
                if (step.ai_reason) traceHtml += '<div class="trace-step-ai-reason">AI: ' + _escapeHtml(step.ai_reason) + '</div>';
                traceHtml += '</div></div>';
            }
            traceHtml += '</div>';
            html += traceHtml;
        }
    }
```

### 替换 4：trace 查看按钮（第 1153 行区域）

找到：

```javascript
    html += '<button class="btn btn-secondary btn-sm" onclick="showConfidenceDetailModal(JSON.parse(decodeURIComponent(this.getAttribute(\'data-trace\'))),this.getAttribute(\'data-filename\'))" data-trace="' + encodeURIComponent(JSON.stringify(trace)) + '" data-filename="' + escapeHtml(filename || '') + '">查看置信度计算过程</button>';
```

替换为：

```javascript
    html += '<button class="btn btn-secondary btn-sm" onclick="showMatchTraceModal(JSON.parse(decodeURIComponent(this.getAttribute(\'data-trace\'))),this.getAttribute(\'data-filename\'))" data-trace="' + encodeURIComponent(JSON.stringify(trace)) + '" data-filename="' + escapeHtml(filename || '') + '">查看匹配路径</button>';
```

并在 `tasks.js` 文件末尾添加 `showMatchTraceModal` 函数：

```javascript
function showMatchTraceModal(trace, filename) {
    var html = '<div class="match-trace-modal">';
    html += '<h3>匹配路径详情</h3>';
    html += '<p class="match-trace-filename">文件：' + escapeHtml(filename || '') + '</p>';
    var steps = trace.trace || [];
    if (Array.isArray(steps) && steps.length > 0) {
        html += '<div class="match-trace-steps">';
        for (var i = 0; i < steps.length; i++) {
            var step = steps[i];
            var color = step.matched ? '#22C55E' : '#94A3B8';
            html += '<div class="match-trace-step">';
            html += '<div class="match-trace-step-tier" style="color:' + color + '">第' + step.tier + '级</div>';
            html += '<div class="match-trace-step-name">' + escapeHtml(step.name || '') + '</div>';
            html += '<div class="match-trace-step-status" style="color:' + color + '">' + (step.matched ? '匹配成功' : '未匹配') + '</div>';
            if (step.reason) html += '<div class="match-trace-step-reason">' + escapeHtml(step.reason) + '</div>';
            if (step.ai_reason) html += '<div class="match-trace-step-ai">AI判断: ' + escapeHtml(step.ai_reason) + '</div>';
            html += '</div>';
        }
        html += '</div>';
    } else {
        html += '<p>无匹配路径信息</p>';
    }
    html += '</div>';
    // 使用现有的模态框展示
    if (typeof showAppModal === 'function') {
        showAppModal({ title: '匹配路径', body: html, actions: [{ label: '关闭', className: 'btn btn-secondary' }] });
    } else {
        alert(html.replace(/<[^>]+>/g, '\n'));
    }
}
```

**验证**：
- 搜索 `tasks.js` 中不再包含 `置信度` 关键字
- 页面正常加载

---

## 任务 3.11：移除 UI 测试文件

**操作**：删除以下 3 个文件

1. `tests/test_confidence_v2_ui.py`
2. `tests/test_confidence_ui.py`
3. `tests/test_confidence_config_ui.py`

**执行**：

```bash
rm tests/test_confidence_v2_ui.py
rm tests/test_confidence_ui.py
rm tests/test_confidence_config_ui.py
```

**验证**：
```bash
ls tests/test_confidence_*_ui.py 2>&1 | grep "No such file"
```

---

## 任务 3.12：重写 `test_scrape_preview_ui.py`

**文件**：`tests/test_scrape_preview_ui.py`

**操作**：替换整个文件内容

```python
"""scrape preview UI 测试 — 验证三级匹配展示。

需要本地服务运行和 Playwright 安装。
"""

import unittest


class TestScrapePreviewUI(unittest.TestCase):
    """scrape preview 页面 UI 测试。"""

    def test_preview_response_structure(self):
        """验证 preview 响应包含 match_level 字段（非 UI 测试，无需 Playwright）"""
        response = {
            "code": 200,
            "data": {
                "filename": "Inception.2010.1080p.BluRay.mkv",
                "clean_result": {
                    "clean_title": "Inception",
                    "year": 2010,
                },
                "modes": {
                    "provider_first": {
                        "result": {
                            "title_cn": "盗梦空间",
                            "title_en": "Inception",
                            "year": 2010,
                            "type": "movie",
                            "confidence": 0.95,
                            "match_level": "AUTO_PASS",
                            "match_concerns": [],
                        },
                    },
                },
            },
        }
        mode_result = response["data"]["modes"]["provider_first"]["result"]
        self.assertIn("match_level", mode_result)
        self.assertEqual(mode_result["match_level"], "AUTO_PASS")
        self.assertIn("match_concerns", mode_result)

    def test_preview_needs_confirm_has_concerns(self):
        """NEEDS_CONFIRM 模式包含疑虑原因"""
        response = {
            "code": 200,
            "data": {
                "filename": "Spider-Man.mkv",
                "modes": {
                    "provider_first": {
                        "result": {
                            "match_level": "NEEDS_CONFIRM",
                            "match_concerns": [
                                {"code": "NO_YEAR_MULTI_MATCH", "message": "找到3部同名作品", "detail": "..."},
                            ],
                        },
                    },
                },
            },
        }
        mode_result = response["data"]["modes"]["provider_first"]["result"]
        self.assertEqual(mode_result["match_level"], "NEEDS_CONFIRM")
        self.assertEqual(len(mode_result["match_concerns"]), 1)

    def test_preview_context_pass(self):
        """CONTEXT_PASS 模式"""
        response = {
            "code": 200,
            "data": {
                "filename": "Test.2020.mkv",
                "modes": {
                    "provider_first": {
                        "result": {
                            "match_level": "CONTEXT_PASS",
                            "match_concerns": [],
                        },
                    },
                },
            },
        }
        mode_result = response["data"]["modes"]["provider_first"]["result"]
        self.assertEqual(mode_result["match_level"], "CONTEXT_PASS")


if __name__ == "__main__":
    unittest.main()
```

**验证**：
```bash
python -m pytest tests/test_scrape_preview_ui.py -v
```

---

## 任务 3.13：改造 `test_scrape_ui.py`

**文件**：`tests/test_scrape_ui.py`

**操作**：在测试中验证 match_level 字段的存在和值

读取当前文件内容，在涉及 `confidence` 字段断言的测试用例中，添加对 `match_level` 字段的断言。

在每个检查 `scrape_result` 的测试方法中，添加：

```python
        # 验证 match_level 字段
        self.assertIn("match_level", scrape_result)
        self.assertIn(scrape_result["match_level"], ("AUTO_PASS", "CONTEXT_PASS", "NEEDS_CONFIRM"))
```

**具体操作**：

1. 读取 `tests/test_scrape_ui.py` 文件
2. 找到所有检查 `confidence` 字段的断言
3. 在每个这样的断言附近添加 `match_level` 字段断言
4. 如果文件中有检查置信度数值范围的断言（如 `self.assertGreaterEqual(confidence, 0.5)`），在其后添加 `match_level` 断言

**验证**：
```bash
python -m pytest tests/test_scrape_ui.py -v
```

---

## 任务 3.14：前端回归验证

**执行**：

```bash
# 1. 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests

# 2. 非 UI 测试
python -m pytest tests/ \
  --ignore=tests/test_*_ui.py \
  --ignore=tests/test_frontend_*.py \
  --ignore=tests/test_scrape_ui.py \
  -v

# 3. 在浏览器中手动验证
# - 打开首页，确认页面正常加载
# - 进入任务页，确认任务卡片显示"自动匹配"/"AI辅助匹配"/"需确认"标签
# - 进入配置页，点击"运行模拟"，确认展示三级匹配标签
# - 确认置信度配置面板不再显示
# - 确认无 JS 控制台报错
```

**预期**：
- 编译检查：0 errors
- 非 UI 测试无新增失败
- 浏览器中页面正常，无 JS 报错
- 置信度相关 UI 元素已移除
- 三级匹配标签正确展示

---

## 阶段 3 完成标准

- [ ] `index.html` 中 `cinema-confidence.js`、`cinema-confidence.css`、`cinema-confidence-dimensions.css`、`confidence-detail.js` 引用已移除
- [ ] `cinema-tasks.js` 中 `taskMeta()` 展示 match_level 标签而非置信度数值
- [ ] `cinema-tasks.js` 中 `taskDescription()` 展示疑虑原因
- [ ] `cinema-config.js` 中模拟运行展示三级匹配标签
- [ ] `cinema-config.js` 中 `saveConfidenceConfig` 函数已移除
- [ ] `cinema-app.js` 中置信度事件绑定已移除
- [ ] `dimensions.js` 中无来源信任配置代码
- [ ] `tasks.js` 中置信度展示已替换为 match_level 标签
- [ ] `test_confidence_v2_ui.py`、`test_confidence_ui.py`、`test_confidence_config_ui.py` 已删除
- [ ] `test_scrape_preview_ui.py` 已重写
- [ ] `test_scrape_ui.py` 已添加 match_level 断言
- [ ] 前端回归验证通过

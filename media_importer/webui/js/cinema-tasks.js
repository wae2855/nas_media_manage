// cinema-tasks.js — 任务列表渲染与操作

function getTaskStatusText(status, stage) {
    const s = String(status || "").toUpperCase();
    const st = String(stage || "").toUpperCase();
    if (s === "PENDING") {
        if (st === "QUEUED") return "排队中";
        if (st === "RUNNING") return "处理中";
        if (st === "AWAIT_REVIEW") return "待确认";
        return "待处理";
    }
    const map = {
        FAILED: "失败",
        SUCCESS: "已完成",
        SKIPPED: "已跳过",
        CANCELLED: "已取消",
    };
    return map[s] || "未知状态";
}

function getTaskTone(task) {
    const status = String(task.status || "").toUpperCase();
    const stage = String(task.stage || "").toUpperCase();
    if (status === "FAILED") return "red";
    if (status === "PENDING" && stage === "AWAIT_REVIEW") return "cyan";
    if (status === "SUCCESS" || status === "SKIPPED") return "gold";
    return "gold";
}

function taskFileName(task) {
    return task.source_filename
        || task.final_filename
        || (task.source_path ? String(task.source_path).split("/").pop().split("\\").pop() : "")
        || "未命名任务";
}

function taskDisplayTitle(task) {
    const scrape = task.scrape_result || {};
    return (
        task.scrape_title_cn
        || scrape.title_cn
        || task.scrape_title_en
        || scrape.title_en
        || taskFileName(task)
    );
}

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
    if (status === "FAILED") {
        return "本次处理未完成，可以先查看原因，再决定是否重试。";
    }
    if (status === "SUCCESS") {
        const title = scrape.title_cn || scrape.title_en || task.scrape_title_cn || task.scrape_title_en;
        return title ? `已完成识别并入库：${title}` : "任务已完成并写入目标片库。";
    }
    if (status === "SKIPPED") {
        return "该任务已被跳过，可按需要重新投入处理。";
    }
    if (status === "CANCELLED") {
        return task.error_message || "该任务已取消，可按需要重新投入处理。";
    }
    if (status === "PENDING" && stage === "RUNNING") {
        return "系统正在扫描、识别和整理这个文件。";
    }
    return "文件已经进入队列，等待系统开始扫描与识别。";
}

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

function taskPrimaryAction(task) {
    const status = String(task.status || "").toUpperCase();
    const stage = String(task.stage || "").toUpperCase();
    if (status === "PENDING" && stage === "AWAIT_REVIEW") return { key: "confirm", label: "去确认" };
    if (status === "FAILED" || status === "SKIPPED") return { key: "retry-task", label: "去重试" };
    if (status === "CANCELLED") return { key: "retry-task", label: "重新投入" };
    if (status === "PENDING" && stage === "QUEUED") return { key: "cancel-task", label: "取消" };
    return null;
}

function taskSecondaryAction(task) {
    const status = String(task.status || "").toUpperCase();
    if (status === "FAILED") return { key: "delete-task", label: "移入回收" };
    return null;
}

function formatFileSizeMb(valueMb) {
    const size = Number(valueMb || 0);
    if (size <= 0) return "0 MB";
    if (size >= 1024) return `${(size / 1024).toFixed(1)} GB`;
    return `${size.toFixed(size >= 100 ? 0 : 1)} MB`;
}

function renderTaskSummary(task) {
    const title = taskDisplayTitle(task);
    const filename = taskFileName(task);
    const lines = [
        `任务：${title}`,
        `状态：${getTaskStatusText(task.status)}`,
        `源文件：${filename}`,
    ];
    if (task.source_path) lines.push(`源路径：${task.source_path}`);
    if (task.import_video_path) lines.push(`入库路径：${task.import_video_path}`);
    const desc = taskDescription(task);
    if (desc) lines.push(`说明：${desc}`);
    return lines.join("\n");
}

function renderTaskCard(item, index = 0) {
    const status = String(item.status || "").toUpperCase();
    const stage = String(item.stage || "").toUpperCase();
    const isAwaitReview = status === "PENDING" && stage === "AWAIT_REVIEW";
    const isFailed = status === "FAILED";
    const danger = isFailed || isAwaitReview ? " danger" : "";
    const primaryAction = taskPrimaryAction(item);
    const secondaryAction = taskSecondaryAction(item);
    const title = taskDisplayTitle(item);
    const filename = taskFileName(item);
    const taskId = String(item.task_id || "");
    const checked = selectedTaskIds.has(taskId) ? "checked" : "";
    const scrape = item.scrape_result || {};
    const thumbnailPath = item.thumbnail_path || "";
    const posterUrl = scrape.poster_url || "";
    const toneClass = `cover-${getTaskTone(item)}`;
    let coverClass, coverContent;
    if (thumbnailPath) {
        const thumbFilename = thumbnailPath.split("/").pop().split("\\").pop();
        const thumbUrl = `/api/thumbnails/${encodeURIComponent(thumbFilename)}`;
        coverClass = "cover cover-img";
        coverContent = `<img src="${escapeHtml(thumbUrl)}" alt="" loading="lazy" data-fallback="${escapeHtml(posterUrl)}" onerror="var d=this.parentNode;var pu=this.dataset.fallback;if(pu){d.className='cover cover-img';this.src=pu;}else{d.className='cover ${toneClass}';this.remove();}" />`;
    } else if (posterUrl) {
        coverClass = "cover cover-img";
        coverContent = `<img src="${escapeHtml(posterUrl)}" alt="" loading="lazy" onerror="this.parentNode.className='cover ${toneClass}';this.remove();" />`;
    } else {
        coverClass = `cover ${toneClass}`;
        coverContent = "";
    }
    return `
        <article class="task-card" data-task-row="${escapeHtml(taskId)}" style="--card-index: ${index}">
            <input type="checkbox" class="task-select-checkbox" data-task-select="${escapeHtml(taskId)}" ${checked} aria-label="选择任务" onclick="event.stopPropagation()" />
            <div class="${coverClass}" aria-hidden="true">${coverContent}</div>
            <div class="task-body">
                <div class="task-top"><h3>${escapeHtml(title)}</h3><span class="badge${danger}">${escapeHtml(getTaskStatusText(item.status, item.stage))}</span></div>
                <p>${escapeHtml(taskDescription(item))}</p>
                <div class="task-meta"><span>${escapeHtml(filename)}</span><span>${escapeHtml(taskMeta(item))}</span></div>
                <small class="task-row-hint">点击卡片选中 · 点击"详情"查看编辑</small>
            </div>
            <div class="task-actions">
                <button class="btn-ghost" data-task-action="view-task" data-task-id="${escapeHtml(taskId)}" aria-label="查看详情">详情</button>
                ${primaryAction ? `<button data-task-action="${escapeHtml(primaryAction.key)}" data-task-id="${escapeHtml(item.task_id || "")}">${escapeHtml(primaryAction.label)}</button>` : ""}
                ${secondaryAction ? `<button data-task-action="${escapeHtml(secondaryAction.key)}" data-task-id="${escapeHtml(item.task_id || "")}">${escapeHtml(secondaryAction.label)}</button>` : ""}
            </div>
        </article>`;
}

function renderTaskList() {
    const meta = TASK_FILTER_META[currentTaskFilter] || TASK_FILTER_META.all;
    document.getElementById("task-panel-title").textContent = meta.title;
    document.getElementById("task-panel-copy").textContent = meta.copy;
    /* 刷新首页轮盘 */
    if (typeof loadReelWheelFromTasks === "function") loadReelWheelFromTasks();
    const host = document.getElementById("task-list");
    if (!host) return;
    const countEl = document.getElementById("task-panel-count");
    if (!Array.isArray(currentTaskRecords) || currentTaskRecords.length === 0) {
        const emptyHint = currentTaskFilter === "all"
            ? "你可以先回到首页发起扫描，或等待新文件进入源目录。"
            : `当前「${meta.title}」筛选下没有匹配的任务。`;
        host.innerHTML = `
            <div class="task-empty-state">
                <div class="task-empty-icon">
                    <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
                </div>
                <h3>无此状态数据</h3>
                <p>${emptyHint}</p>
                <div class="task-empty-actions">
                    <button class="btn btn-secondary" data-task-action="refresh-tasks">重新加载</button>
                    <button class="btn btn-secondary" data-nav="home" data-view-target="dashboard">回到首页</button>
                </div>
            </div>`;
        if (countEl) countEl.textContent = "0 / 0 项";
        setBatchToolbarVisibility();
        updateBatchToolbar();
        return;
    }
    const cardsHtml = currentTaskRecords.map((item, index) => renderTaskCard(item, index)).join("");
    const loadMoreHtml = currentTaskHasMore
        ? `<div class="task-load-more">
                <button class="btn btn-secondary" data-task-action="load-more-tasks">加载更多（已显示 ${currentTaskRecords.length} / 共 ${currentTaskTotal} 项）</button>
            </div>`
        : "";
    host.innerHTML = cardsHtml + loadMoreHtml;
    if (countEl) {
        const loaded = currentTaskRecords.length;
        countEl.textContent = currentTaskHasMore
            ? `${loaded} / ${currentTaskTotal} 项`
            : `${loaded} 项`;
    }
    setBatchToolbarVisibility();
    updateBatchToolbar();
}

function renderStaticLists() {
    renderTaskList();
    currentRecycleRecords = [];
    renderRecycleList();
}

function setTaskFilter(filter) {
    currentTaskFilter = filter;
    currentTaskPage = 1;
    selectedTaskIds.clear();
    document.querySelectorAll("[data-task-filter-chip]").forEach((chip) => {
        chip.classList.toggle("active", chip.dataset.taskFilterChip === filter);
    });
    loadTaskList(false);
}

async function listTasksByStatuses(params, page = 1, pageSize = 20) {
    const baseQuery = { page, limit: pageSize };
    if (!params || Object.keys(params).length === 0) {
        const result = await requestApi("GET", "/tasks", baseQuery);
        if (result.code !== 200 || !result.data) return { code: result.code, message: result.message, tasks: [], total: 0, total_pages: 1 };
        return {
            code: 200,
            tasks: result.data.tasks || [],
            total: result.data.total || 0,
            total_pages: result.data.total_pages || 1,
        };
    }
    // Handle array status by making separate requests and merging
    if (params.status && Array.isArray(params.status)) {
        const allTasks = [];
        let totalSum = 0;
        let anyError = false;
        for (const s of params.status) {
            const query = { ...baseQuery, status: s };
            if (params.stage) query.stage = params.stage;
            const result = await requestApi("GET", "/tasks", query);
            if (result.code !== 200 || !result.data) { anyError = true; continue; }
            allTasks.push(...(result.data.tasks || []));
            totalSum += result.data.total || 0;
        }
        if (anyError && allTasks.length === 0) return { code: 500, message: "请求失败", tasks: [], total: 0, total_pages: 1 };
        const mergedPageSize = pageSize * params.status.length;
        return {
            code: 200,
            tasks: allTasks,
            total: totalSum,
            total_pages: Math.max(1, Math.ceil(totalSum / mergedPageSize)),
        };
    }
    const query = { ...baseQuery };
    if (params.status) query.status = params.status;
    if (params.stage) query.stage = params.stage;
    const result = await requestApi("GET", "/tasks", query);
    if (result.code !== 200 || !result.data) return { code: result.code, message: result.message, tasks: [], total: 0, total_pages: 1 };
    return {
        code: 200,
        tasks: result.data.tasks || [],
        total: result.data.total || 0,
        total_pages: result.data.total_pages || 1,
    };
}

async function loadTaskList(append = false) {
    if (currentTaskLoading) return;
    currentTaskLoading = true;
    try {
        const meta = TASK_FILTER_META[currentTaskFilter] || TASK_FILTER_META.all;
        document.getElementById("task-panel-title").textContent = meta.title;
        document.getElementById("task-panel-copy").textContent = meta.copy;
        if (!append) {
            currentTaskPage = 1;
            currentTaskRecords = [];
            document.getElementById("task-panel-count").textContent = "加载中";
            const host = document.getElementById("task-list");
            if (host) {
                host.innerHTML = `
                    <article class="task-card">
                        <div class="cover cover-gold"></div>
                        <div class="task-body">
                            <div class="task-top"><h3>正在读取任务队列</h3><span class="badge">加载中</span></div>
                            <p>正在把真实任务列表同步到新版任务工作台。</p>
                            <div class="task-meta"><span>任务工作台</span></div>
                        </div>
                    </article>`;
            }
        }
        const result = await listTasksByStatuses(
            TASK_FILTER_PARAMS[currentTaskFilter],
            currentTaskPage,
            currentTaskPageSize
        );
        if (result.code === 401) {
            currentTaskRecords = [];
            currentTaskTotal = 0;
            currentTaskHasMore = false;
            renderTaskList();
            return;
        }
        if (result.code !== 200) {
            currentTaskRecords = [];
            currentTaskTotal = 0;
            currentTaskHasMore = false;
            renderErrorState(result.message || "请稍后重试。");
            return;
        }
        if (append) {
            currentTaskRecords = currentTaskRecords.concat(result.tasks || []);
        } else {
            currentTaskRecords = result.tasks || [];
        }
        currentTaskTotal = result.total || 0;
        currentTaskHasMore = currentTaskRecords.length < currentTaskTotal;
        renderTaskList();
    } finally {
        currentTaskLoading = false;
    }
}

function renderErrorState(message) {
    const host = document.getElementById("task-list");
    if (!host) return;
    host.innerHTML = `
        <article class="task-card">
            <div class="cover cover-red"></div>
            <div class="task-body">
                <div class="task-top"><h3>任务列表加载失败</h3><span class="badge danger">失败</span></div>
                <p>${escapeHtml(message)}</p>
                <div class="task-meta"><span>任务工作台</span></div>
            </div>
            <div class="task-actions">
                <button data-task-action="refresh-tasks">重新加载</button>
            </div>
        </article>`;
    document.getElementById("task-panel-count").textContent = "--";
    setBatchToolbarVisibility();
    updateBatchToolbar();
}

function findTaskRecord(taskId) {
    return currentTaskRecords.find((item) => item.task_id === taskId);
}

function extractDimValue(raw) {
    if (raw == null) return "";
    if (typeof raw === "string") return raw;
    if (typeof raw === "object") {
        if (raw.value != null) return String(raw.value);
        if (raw.sources && typeof raw.sources === "object") {
            const keys = Object.keys(raw.sources);
            for (const k of keys) {
                const sv = raw.sources[k];
                if (sv != null) return typeof sv === "object" ? String(sv.value || "") : String(sv);
            }
        }
    }
    return String(raw);
}

const MULTI_SELECT_DIMS = ['restricted_level', 'broad_genre'];

function isMultiSelectDim(dimName) {
    return MULTI_SELECT_DIMS.indexOf(dimName) >= 0;
}

function buildTaskDimensionsForm(task, editable, enabled = editable) {
    const dimensions = currentEnabledDimensions.length ? currentEnabledDimensions : [];
    const source = task.scrape_dimensions || task.dimensions || {};
    if (!dimensions.length) {
        return '<div class="cinema-modal-hint">当前还没有启用的分类维度。</div>';
    }
    return dimensions.map((dim) => {
        const rawValue = source[dim.name];
        const value = extractDimValue(rawValue);
        const options = Array.isArray(dim.value_list) ? dim.value_list : [];
        const multi = isMultiSelectDim(dim.name);

        // 只读模式
        if (!editable) {
            const displayValue = multi
                ? formatMultiValue(value, options)
                : (() => { const m = options.find((item) => item.value === value); return m ? (m.label || m.value) : value; })();
            return `
                <label class="cinema-modal-field">
                    <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                    <span class="cinema-modal-readonly-value">${escapeHtml(displayValue || "—")}</span>
                </label>`;
        }

        const disabledAttr = enabled ? "" : " disabled";

        // 多选维度 → checkbox group
        if (multi && options.length > 0) {
            const selectedVals = value.split("|").map(s => s.trim()).filter(Boolean);
            const checkboxHtml = options.map((item) => {
                const checked = selectedVals.indexOf(item.value) >= 0 ? " checked" : "";
                return `<label class="rule-condition-checkbox-label">
                    <input type="checkbox" value="${escapeHtml(item.value)}"${checked}${disabledAttr} data-task-dim="${escapeHtml(dim.name)}">
                    <span>${escapeHtml(item.label || item.value)}</span>
                </label>`;
            }).join("");
            return `
                <div class="cinema-modal-field">
                    <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                    <div class="cinema-modal-checkbox-group">${checkboxHtml}</div>
                </div>`;
        }

        // 单选有值域 → select
        if (options.length > 0) {
            const matchedOption = options.find((item) => item.value === value);
            const emptyStateHtml = value
                ? `<option value="${escapeHtml(value)}" selected>${escapeHtml(matchedOption ? (matchedOption.label || matchedOption.value) : value)}</option>`
                : `<option value="" selected disabled>无</option>`;
            const optionHtml = options.map((item) => {
                const selected = item.value === value ? " selected" : "";
                return `<option value="${escapeHtml(item.value)}"${selected}>${escapeHtml(item.label || item.value)}</option>`;
            }).join("");
            return `
                <label class="cinema-modal-field">
                    <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                    <select data-task-dim="${escapeHtml(dim.name)}" class="cinema-modal-select"${disabledAttr}>
                        ${emptyStateHtml}
                        ${optionHtml}
                    </select>
                </label>`;
        }

        // 无值域 → 自由文本
        return `
            <label class="cinema-modal-field">
                <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                <input type="text" data-task-dim="${escapeHtml(dim.name)}" value="${escapeHtml(value)}" placeholder="${value ? '' : '无'}"${disabledAttr} />
            </label>`;
    }).join("");
}

function formatMultiValue(value, options) {
    const parts = String(value || "").split("|").map(s => s.trim()).filter(Boolean);
    if (!parts.length) return "";
    return parts.map(v => {
        const m = options.find(o => o.value === v);
        return m ? (m.label || m.value) : v;
    }).join("、");
}

function getTaskEditPermission(task) {
    const status = String(task.status || "").toUpperCase();
    const stage = String(task.stage || "").toUpperCase();
    const isAwaitReview = status === "PENDING" && stage === "AWAIT_REVIEW";
    const isQueued = status === "PENDING" && stage === "QUEUED";
    const isFailed = status === "FAILED";
    const isCancelled = status === "CANCELLED";

    return {
        canEditFilename: isAwaitReview,
        canEditDimensions: isAwaitReview,
        canSave: isAwaitReview,
        stateLabel: isAwaitReview
            ? "待确认 — 可修改文件名和维度后确认入库"
            : isQueued
            ? "排队中 — 只读，不可编辑"
            : isFailed
            ? "失败 — 只读，可重试"
            : isCancelled
            ? "已取消 — 只读，可重新投入"
            : status === "SUCCESS"
            ? "已完成 — 只读"
            : status === "SKIPPED"
            ? "已跳过 — 只读"
            : stage === "RUNNING"
            ? "处理中 — 不可编辑"
            : "只读",
    };
}

function buildScrapeTraceSection(task) {
    var scrapeTrace = task.scrape_trace;
    if (!scrapeTrace || typeof scrapeTrace !== "object") return "";

    var traceJson = encodeURIComponent(JSON.stringify(scrapeTrace));
    var filename = task.source_filename || "";

    var searchBadge = "";
    if (scrapeTrace.search_enhanced === true) {
        searchBadge = '<span style="font-size:11px;padding:2px 8px;border-radius:999px;background:rgba(6,182,212,0.15);color:#06B6D4;font-weight:600;margin-left:8px">🔍 AI联网搜索增强</span>';
    } else if (scrapeTrace.search_enhanced === false) {
        searchBadge = '<span style="font-size:11px;padding:2px 8px;border-radius:999px;background:rgba(148,163,184,0.12);color:#94A3B8;font-weight:600;margin-left:8px">📴 纯本地分析</span>';
    }

    return `
        <div class="cinema-modal-block">
            <h4>决策路径${searchBadge}</h4>
            <div class="cinema-modal-hint" style="margin-bottom:8px">查看刮削过程中的匹配路径详情。</div>
            <button class="btn btn-secondary btn-sm" onclick="showMatchTraceModal(JSON.parse(decodeURIComponent(this.getAttribute('data-trace'))),this.getAttribute('data-filename'))" data-trace="${traceJson}" data-filename="${escapeHtml(filename)}">查看匹配路径</button>
        </div>`;
}

function buildSubtitleTable(subtitles) {
    if (!Array.isArray(subtitles) || subtitles.length === 0) {
        return '<div class="cinema-modal-hint">这个任务当前没有字幕记录。</div>';
    }
    const rows = subtitles.map((item) => `
        <tr>
            <td>${escapeHtml(item.source_filename || "-")}</td>
            <td>${escapeHtml(item.lang || "-")}</td>
            <td>${escapeHtml(getTaskStatusText(item.status || "PENDING"))}</td>
            <td>${escapeHtml(item.import_path || "-")}</td>
        </tr>`).join("");
    return `
        <table class="cinema-inline-table">
            <thead><tr><th>文件名</th><th>语言</th><th>状态</th><th>入库路径</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
}

function classifyErrorMessage(message) {
    const text = String(message || "").trim();
    if (!text) return { tone: "default", hint: "" };
    const lower = text.toLowerCase();
    if (/(timeout|timed out|连接超时|网络|network|unreachable|reset)/i.test(lower)) {
        return { tone: "warn", hint: "网络或服务暂时不可用，稍后重试或检查 Provider 配置。" };
    }
    if (/(rate.?limit|too many|429|quota|限流|额度)/i.test(lower)) {
        return { tone: "warn", hint: "Provider 或 LLM 调用触发限流，请稍后重试。" };
    }
    if (/(file not found|no such file|enoent|missing|文件不存在|找不到|无法读取|permission)/i.test(lower)) {
        return { tone: "danger", hint: "源文件可能已被移动或删除，请检查源目录或重新入库。" };
    }
    if (/(no match|not found|无匹配|无结果|unknown media|unrecognized)/i.test(lower)) {
        return { tone: "warn", hint: "未找到匹配的影视信息，可尝试手动指定标题或重命名后再重试。" };
    }
    if (/(auth|401|403|unauthorized|forbidden|api.?key|invalid)/i.test(lower)) {
        return { tone: "danger", hint: "Provider 或 LLM 鉴权失败，请检查 API Key 配置。" };
    }
    return { tone: "danger", hint: "" };
}

function buildScrapeResultSection(task) {
    const scrape = task.scrape_result || {};
    const matchLevel = scrape.match_level || task.match_level || "";
    const hasAny = scrape.title_cn || scrape.title_en || scrape.year || scrape.type || scrape.overview || scrape.poster_url || matchLevel;
    if (!hasAny) {
        return `
            <div class="cinema-modal-block">
                <h4>刮削结果</h4>
                <div class="cinema-modal-hint">本次未产生刮削结果，可能是首次扫描或 Provider 命中失败。</div>
            </div>`;
    }
    const titleCn = scrape.title_cn || task.scrape_title_cn || "";
    const titleEn = scrape.title_en || task.scrape_title_en || "";
    const year = scrape.year || task.scrape_year || "";
    const type = scrape.type || task.scrape_media_type || "";
    const overview = scrape.overview || "";
    const poster = scrape.poster_url || "";
    const typeLabel = type === "movie" ? "电影" : type === "tv" ? "剧集" : (type || "—");
    let matchLabel = "";
    if (matchLevel === "AUTO_PASS") matchLabel = '<span class="badge" style="background:rgba(34,197,94,0.15);color:#22C55E">自动匹配</span>';
    else if (matchLevel === "CONTEXT_PASS") matchLabel = '<span class="badge" style="background:rgba(6,182,212,0.15);color:#06B6D4">AI辅助匹配</span>';
    else if (matchLevel === "NEEDS_CONFIRM") matchLabel = '<span class="badge" style="background:rgba(245,158,11,0.15);color:#F59E0B">需确认</span>';
    return `
        <div class="cinema-modal-block">
            <h4>刮削结果</h4>
            <div class="task-detail-scrape">
                ${poster ? `<div class="task-detail-poster"><img src="${escapeHtml(poster)}" alt="海报" loading="lazy" onerror="this.parentNode.style.display='none'"/></div>` : ""}
                <div class="task-detail-scrape-meta">
                    <div class="task-detail-scrape-line"><b>${escapeHtml(titleCn || titleEn || "—")}</b>${titleCn && titleEn ? `<span>${escapeHtml(titleEn)}</span>` : ""}</div>
                    <div class="task-detail-scrape-tags">
                        <span class="badge">${escapeHtml(typeLabel)}</span>
                        ${year ? `<span class="badge">${escapeHtml(String(year))}</span>` : ""}
                        ${matchLabel ? matchLabel : ""}
                    </div>
                    ${overview ? `<p class="task-detail-scrape-overview">${escapeHtml(overview)}</p>` : ""}
                </div>
            </div>
        </div>`;
}

function buildFailureSection(task) {
    const status = String(task.status || "").toUpperCase();
    const message = String(task.error_message || task.skip_reason || "").trim();
    if (status !== "FAILED" || !message) return "";
    const classified = classifyErrorMessage(message);
    return `
        <div class="cinema-modal-block task-detail-failure">
            <h4>失败原因</h4>
            <div class="task-detail-failure-box task-detail-failure-${classified.tone}">
                <div class="task-detail-failure-text">${escapeHtml(message)}</div>
                ${classified.hint ? `<div class="task-detail-failure-hint">${escapeHtml(classified.hint)}</div>` : ""}
            </div>
        </div>`;
}

function buildRenamePreview(originalFilename) {
    const original = String(originalFilename || "");
    return `
        <div class="task-detail-rename-preview" id="task-rename-preview">
            <small class="task-detail-rename-from">原文件名：<span>${escapeHtml(original)}</span></small>
            <small class="task-detail-rename-to">新文件名：<span data-rename-target>${escapeHtml(original)}</span></small>
        </div>`;
}

function updateRenamePreview(inputEl) {
    if (!inputEl) return;
    const target = document.querySelector("#task-rename-preview [data-rename-target]");
    if (!target) return;
    const value = String(inputEl.value || "").trim();
    target.textContent = value || "（空）";
    const original = String(inputEl.dataset.renameOriginal || "").trim();
    const preview = document.getElementById("task-rename-preview");
    if (preview) {
        const changed = value && value !== original;
        preview.classList.toggle("is-changed", changed);
    }
    if (inputEl.classList) {
        inputEl.classList.toggle("is-empty", !value);
    }
}

function openTaskDetail(taskId) {
    return openTaskDetailImpl(taskId, true);
}

async function openTaskDetailImpl(taskId, refreshListAfter) {
    const detailResult = await requestApi("GET", `/tasks/${encodeURIComponent(taskId)}`);
    if (detailResult.code !== 200 || !detailResult.data?.task) {
        showToast(detailResult.message || "获取任务详情失败");
        return;
    }
    const task = detailResult.data.task;
    const subtitleResult = await requestApi("GET", `/tasks/${encodeURIComponent(taskId)}/subtitles`);
    const subtitles = subtitleResult.code === 200 && subtitleResult.data ? (subtitleResult.data.subtitles || []) : [];
    const originalFilename = taskFileName(task);
    const status = String(task.status || "").toUpperCase();
    const stage = String(task.stage || "").toUpperCase();
    const isAwaitReview = status === "PENDING" && stage === "AWAIT_REVIEW";
    const isFilenameEditable = isAwaitReview;

    const perm = getTaskEditPermission(task);
    const editable = perm.canSave;

    const renameSection = perm.canEditFilename
        ? `<div class="cinema-modal-block">
                <div class="cinema-modal-section-head">
                    <h4>文件名</h4>
                </div>
                <label class="cinema-modal-field">
                    <span>文件名 <small>（可修改，不含路径）</small></span>
                    <input type="text" id="task-rename-input" value="${escapeHtml(originalFilename)}" data-rename-original="${escapeHtml(originalFilename)}" />
                </label>
                ${buildRenamePreview(originalFilename)}
            </div>`
        : `<div class="cinema-modal-block">
                <h4>文件名</h4>
                <div class="cinema-modal-readonly-line">${escapeHtml(originalFilename)}</div>
            </div>`;

    const dimActionsHtml = perm.canEditDimensions
        ? `<div class="cinema-modal-section-actions">
                ${isAwaitReview ? `<button id="btn-preview-classify" type="button" class="btn btn-sm btn-outline">预览入库规则</button>` : ""}
           </div>`
        : "";

    const dimSectionHtml = perm.canEditDimensions
        ? `<div class="cinema-modal-block">
                <div class="cinema-modal-section-head">
                    <h4>分类维度</h4>
                    ${dimActionsHtml}
                </div>
                <div class="cinema-modal-grid">${buildTaskDimensionsForm(task, true, true)}</div>
                <div id="preview-classify-result" class="cinema-modal-preview" style="display:none"></div>
           </div>`
        : `<div class="cinema-modal-block">
                <h4>分类维度</h4>
                <div class="cinema-modal-grid">${buildTaskDimensionsForm(task, false)}</div>
           </div>`;

    const filenameSaveHtml = perm.canEditFilename
        ? `<div class="cinema-modal-block">
                <div class="cinema-modal-save-row">
                    <button id="btn-save-filename" type="button" class="btn btn-primary">保存文件名</button>
                    <div id="filename-error-area" class="modal-error-area" style="display:none"></div>
                </div>
           </div>`
        : "";

    const dimSaveHtml = perm.canEditDimensions
        ? `<div class="cinema-modal-block">
                <div class="cinema-modal-save-row">
                    <button id="btn-save-dims" type="button" class="btn btn-primary">保存分类</button>
                    <div id="dims-error-area" class="modal-error-area" style="display:none"></div>
                </div>
           </div>`
        : "";

    const stateHintHtml = `<div class="cinema-modal-save-bar">
            <small class="task-permission-hint">${escapeHtml(perm.stateLabel)}</small>
       </div>`;

    const body = `
        <div class="cinema-modal-stack">
            <div class="cinema-modal-summary">
                <div><strong>${escapeHtml(taskDisplayTitle(task))}</strong><span>${escapeHtml(getTaskStatusText(task.status, task.stage))}</span></div>
                <p>${escapeHtml(taskDescription(task))}</p>
                <small>源文件：${escapeHtml(originalFilename)}</small>
                ${task.source_path ? `<small>源路径：${escapeHtml(task.source_path)}</small>` : ""}
                ${task.import_video_path ? `<small>入库路径：${escapeHtml(task.import_video_path)}</small>` : ""}
            </div>
            ${buildFailureSection(task)}
            ${buildScrapeResultSection(task)}
            ${buildScrapeTraceSection(task)}
            ${renameSection}
            ${filenameSaveHtml}
            ${dimSectionHtml}
            ${dimSaveHtml}
            <div class="cinema-modal-block">
                <h4>字幕记录</h4>
                ${buildSubtitleTable(subtitles)}
            </div>
            ${stateHintHtml}
        </div>`;

    const actions = [
        { label: "关闭", className: "btn btn-secondary" },
    ];

    showAppModal({
        title: "任务详情",
        body,
        actions,
    });

    const renameInput = document.getElementById("task-rename-input");
    if (renameInput) {
        renameInput.addEventListener("input", () => updateRenamePreview(renameInput));
    }

    function setErrorArea(areaId, msg) {
        const errEl = document.getElementById(areaId);
        if (!errEl) return;
        if (!msg) {
            errEl.style.display = "none";
            errEl.textContent = "";
            return;
        }
        errEl.style.display = "block";
        errEl.textContent = msg;
    }

    function setSavingBtn(btnEl, saving) {
        if (!btnEl) return;
        if (saving) {
            btnEl.disabled = true;
            btnEl.dataset.prevText = btnEl.textContent;
            btnEl.textContent = "保存中...";
        } else {
            btnEl.disabled = false;
            btnEl.textContent = btnEl.dataset.prevText || btnEl.textContent;
        }
    }

    async function handleSaveFilename(btnEl) {
        const inputEl = document.getElementById("task-rename-input");
        const newFilename = String(inputEl?.value || "").trim();
        if (!newFilename) {
            showToast("文件名不能为空");
            setErrorArea("filename-error-area", "文件名不能为空");
            return;
        }
        setSavingBtn(btnEl, true);
        setErrorArea("filename-error-area", "");
        try {
            const result = await requestApi("POST", `/tasks/${encodeURIComponent(taskId)}/rename`, {
                new_filename: newFilename,
            });
            if (result.code === 200) {
                showToast("文件名已保存");
                removeAppModal();
                await openTaskDetailImpl(taskId, true);
                await Promise.all([loadTaskList(), loadDashboardOverview()]);
                return;
            }
            const errMsg = result.message || "保存文件名失败，请稍后重试";
            setErrorArea("filename-error-area", errMsg);
            showToast(errMsg);
        } finally {
            setSavingBtn(btnEl, false);
        }
    }

    async function handleSaveDims(btnEl) {
        const dims = {};
        const multiDimNames = {};
        // 收集多选 checkbox 值
        document.querySelectorAll("input[type=checkbox][data-task-dim]").forEach((cb) => {
            const dimName = cb.dataset.taskDim;
            if (!multiDimNames[dimName]) multiDimNames[dimName] = [];
            if (cb.checked) multiDimNames[dimName].push(cb.value);
        });
        for (const [dimName, vals] of Object.entries(multiDimNames)) {
            if (vals.length) dims[dimName] = vals.join("|");
        }
        // 收集单选 select/input 值（排除 checkbox）
        document.querySelectorAll("select[data-task-dim], input[type=text][data-task-dim]").forEach((input) => {
            const nextValue = parseRuleConditionValue(input.value);
            if (nextValue) dims[input.dataset.taskDim] = nextValue;
        });
        if (Object.keys(dims).length === 0) {
            showToast("请至少填写一个维度值");
            setErrorArea("dims-error-area", "请至少填写一个维度值");
            return;
        }
        // diff 模式：只发送与原始值不同的字段
        const origDims = task.scrape_dimensions || task.dimensions || {};
        const changedDims = {};
        let hasChanged = false;
        for (const [key, newVal] of Object.entries(dims)) {
            const origVal = parseRuleConditionValue(String(origDims[key] || ""));
            if (newVal !== origVal) {
                changedDims[key] = newVal;
                hasChanged = true;
            }
        }
        if (!hasChanged) {
            showToast("维度值未做修改");
            return;
        }
        setSavingBtn(btnEl, true);
        setErrorArea("dims-error-area", "");
        try {
            const result = await requestApi("POST", `/tasks/${encodeURIComponent(taskId)}/reclassify`, {
                dimensions: changedDims,
            });
            if (result.code === 200) {
                showToast("分类已保存");
                removeAppModal();
                await openTaskDetailImpl(taskId, true);
                await Promise.all([loadTaskList(), loadDashboardOverview()]);
                return;
            }
            const errMsg = result.message || "保存分类失败，请稍后重试";
            setErrorArea("dims-error-area", errMsg);
            showToast(errMsg);
        } finally {
            setSavingBtn(btnEl, false);
        }
    }

    const btnSaveFilename = document.getElementById("btn-save-filename");
    if (btnSaveFilename) {
        btnSaveFilename.addEventListener("click", () => handleSaveFilename(btnSaveFilename));
    }
    const btnSaveDims = document.getElementById("btn-save-dims");
    if (btnSaveDims) {
        btnSaveDims.addEventListener("click", () => handleSaveDims(btnSaveDims));
    }

    const previewBtn = document.getElementById("btn-preview-classify");
    if (previewBtn) {
        previewBtn.addEventListener("click", async () => {
            const dims = {};
            document.querySelectorAll("[data-task-dim]").forEach((input) => {
                const v = input.value?.trim();
                if (v) { dims[input.dataset.taskDim] = v; }
            });
            try {
                const result = await requestApi("POST", `/tasks/${encodeURIComponent(taskId)}/classify-preview`, {
                    dimensions: dims,
                    filename: document.getElementById("task-rename-input")?.value?.trim() || originalFilename,
                });
                const previewDiv = document.getElementById("preview-classify-result");
                if (result.code === 200 && result.data) {
                    const d = result.data;
                    previewDiv.style.display = "block";
                    const hasPath = d.import_path && d.full_path;
                    let html = "";
                    if (hasPath) {
                        html = `<div class="preview-path"><span class="preview-label">入库目录：</span><code>${escapeHtml(d.import_path || "")}</code></div>
                            <div class="preview-path"><span class="preview-label">最终文件：</span><code>${escapeHtml(d.full_path || "")}</code></div>`;
                    }
                    if (d.warnings?.length) {
                        html += `<div class="preview-warning">${escapeHtml(d.warnings.join("; "))}</div>`;
                    }
                    if (!hasPath && d.rules_description) {
                        html += `<div class="preview-info"><span class="preview-label">已配置规则：</span>${escapeHtml(d.rules_description)}</div>`;
                    }
                    if (!hasPath && d.dimensions_text) {
                        html += `<div class="preview-info"><span class="preview-label">当前维度：</span>${escapeHtml(d.dimensions_text)}</div>`;
                    }
                    previewDiv.innerHTML = html || `<div class="preview-warning">无法生成入库路径</div>`;
                } else {
                    previewDiv.style.display = "block";
                    previewDiv.innerHTML = `<div class="preview-warning">预览失败: ${result.message || "未知错误"}</div>`;
                }
            } catch (e) {
                const previewDiv = document.getElementById("preview-classify-result");
                if (previewDiv) {
                    previewDiv.style.display = "block";
                    previewDiv.innerHTML = `<div class="preview-warning">请求异常: ${e.message || e}</div>`;
                }
            }
        });
    }
}

async function performTaskAction(action, taskId) {
    if (action === "refresh-tasks") {
        await loadTaskList(false);
        return;
    }
    if (action === "load-more-tasks") {
        currentTaskPage += 1;
        await loadTaskList(true);
        return;
    }
    const task = findTaskRecord(taskId);
    if (!task) {
        showToast("当前任务数据已过期，请重新加载");
        return;
    }
    if (action === "view-task") {
        await openTaskDetail(taskId);
        return;
    }
    if (action === "confirm") {
        showConfirm("确认入库", `确定将「${taskFileName(task)}」按当前结果继续入库吗？`, async () => {
            const result = await requestApi("POST", `/tasks/${encodeURIComponent(taskId)}/confirm`);
            showToast(result.message || "确认请求已发送");
            if (result.code === 200) {
                await Promise.all([loadTaskList(), loadDashboardOverview()]);
            }
        });
        return;
    }
    if (action === "retry-task") {
        const result = await requestApi("POST", `/tasks/${encodeURIComponent(taskId)}/retry`);
        showToast(result.message || "重试请求已发送");
        if (result.code === 200) {
            await Promise.all([loadTaskList(), loadDashboardOverview()]);
        }
        return;
    }
    if (action === "ignore-task") {
        showConfirm("忽略任务", `确定忽略「${taskFileName(task)}」吗？`, async () => {
            const result = await requestApi("POST", `/tasks/${encodeURIComponent(taskId)}/ignore`);
            showToast(result.message || "忽略请求已发送");
            if (result.code === 200) {
                await Promise.all([loadTaskList(), loadDashboardOverview()]);
            }
        });
        return;
    }
    if (action === "delete-task") {
        showConfirm("移入回收", `确定将「${taskFileName(task)}」移出当前任务流吗？\n\n如果后端允许，将按现有安全规则进入回收流程。`, async () => {
            const result = await requestApi("POST", `/tasks/${encodeURIComponent(taskId)}/delete`, {
                delete_files: false,
            });
            showToast(result.message || "移入回收请求已发送");
            if (result.code === 200) {
                await Promise.all([loadTaskList(), loadDashboardOverview()]);
            }
        });
        return;
    }
    if (action === "edit-task") {
        await openTaskDetail(taskId);
        return;
    }
    if (action === "cancel-task") {
        showConfirm("取消任务", `确定取消「${taskFileName(task)}」吗？取消后任务将变为已取消状态，可在"已取消"筛选中找到，需要时可用于重新投入。`, async () => {
            const result = await requestApi("POST", `/tasks/${encodeURIComponent(taskId)}/cancel`);
            showToast(result.message || "取消请求已发送");
            if (result.code === 200) {
                await Promise.all([loadTaskList(), loadDashboardOverview()]);
            }
        });
        return;
    }
}

/* B1: 任务页批量动作 */

function taskStatusOf(task) {
    return String(task?.status || "").toUpperCase();
}

function taskStageOf(task) {
    return String(task?.stage || "").toUpperCase();
}

function isBatchableStatus(status) {
    return ["FAILED", "SKIPPED", "PENDING"].includes(status);
}

function getSelectedTaskRecords() {
    return currentTaskRecords.filter((task) => selectedTaskIds.has(String(task.task_id || "")));
}

function updateBatchToolbar() {
    const toolbar = document.getElementById("task-batch-toolbar");
    if (!toolbar) return;
    const selectedRecords = getSelectedTaskRecords();
    const count = selectedRecords.length;
    toolbar.hidden = false;
    const counter = document.getElementById("task-batch-count");
    if (counter) counter.textContent = `已选 ${count} 项`;
    const selectAll = document.getElementById("task-select-all");
    const visibleIds = currentTaskRecords.map((item) => String(item.task_id || ""));
    if (selectAll) {
        const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedTaskIds.has(id));
        const someSelected = visibleIds.some((id) => selectedTaskIds.has(id));
        selectAll.checked = allSelected;
        selectAll.indeterminate = !allSelected && someSelected;
    }
    const retryBtn = document.getElementById("task-batch-retry");
    const confirmBtn = document.getElementById("task-batch-confirm");
    const ignoreBtn = document.getElementById("task-batch-ignore");
    const deleteBtn = document.getElementById("task-batch-delete");
    const hasFailedOrSkipped = selectedRecords.some((t) => ["FAILED", "SKIPPED", "CANCELLED"].includes(taskStatusOf(t)));
    const hasAwaitReview = selectedRecords.some((t) => taskStatusOf(t) === "PENDING" && taskStageOf(t) === "AWAIT_REVIEW");
    const hasProcessable = selectedRecords.some((t) => isBatchableStatus(taskStatusOf(t)));
    if (retryBtn) retryBtn.hidden = !(count > 0 && hasFailedOrSkipped);
    if (confirmBtn) confirmBtn.hidden = !(count > 0 && hasAwaitReview);
    if (ignoreBtn) ignoreBtn.hidden = !(count > 0 && (hasAwaitReview || hasFailedOrSkipped));
    if (deleteBtn) deleteBtn.hidden = !(count > 0 && hasProcessable);
    const actionButtons = [retryBtn, confirmBtn, ignoreBtn, deleteBtn].filter(Boolean);
    actionButtons.forEach((btn) => { btn.disabled = count === 0; });
}

function toggleTaskSelect(taskId) {
    const id = String(taskId || "");
    if (!id) return;
    if (selectedTaskIds.has(id)) selectedTaskIds.delete(id);
    else selectedTaskIds.add(id);
    const checkbox = document.querySelector(`[data-task-select="${CSS.escape(id)}"]`);
    if (checkbox) checkbox.checked = selectedTaskIds.has(id);
    updateBatchToolbar();
}

function selectAllVisibleTasks() {
    const selectAll = document.getElementById("task-select-all");
    const visibleIds = currentTaskRecords.map((item) => String(item.task_id || "")).filter(Boolean);
    const shouldSelectAll = !(visibleIds.length > 0 && visibleIds.every((id) => selectedTaskIds.has(id)));
    currentTaskRecords.forEach((item) => {
        const id = String(item.task_id || "");
        if (!id) return;
        if (shouldSelectAll) selectedTaskIds.add(id);
        else selectedTaskIds.delete(id);
    });
    if (selectAll) selectAll.checked = shouldSelectAll;
    renderTaskList();
}

function clearTaskSelection() {
    selectedTaskIds.clear();
    renderTaskList();
}

function setBatchToolbarVisibility() {
    const toolbar = document.getElementById("task-batch-toolbar");
    if (!toolbar) return;
    toolbar.hidden = !Array.isArray(currentTaskRecords) || currentTaskRecords.length === 0;
}

async function performBatchTaskAction(action) {
    const records = getSelectedTaskRecords();
    if (records.length === 0) {
        showToast("请先选择要操作的任务");
        return;
    }
    if (records.length > 50) {
        showToast(`当前选中 ${records.length} 项，超过单次批量 50 项上限，请分批操作`);
        return;
    }
    if (action === "batch-clear") {
        clearTaskSelection();
        return;
    }
    if (action === "batch-confirm") {
        showConfirm("批量确认", `确定确认「${records.length}」项任务吗？`, async () => {
            const result = await requestApi("POST", "/tasks/confirm-all");
            showToast(result.message || `批量确认请求已发送，共 ${records.length} 项`);
            clearTaskSelection();
            await Promise.all([loadTaskList(), loadDashboardOverview()]);
        });
        return;
    }
    if (action === "batch-retry") {
        const eligible = records.filter((t) => ["FAILED", "SKIPPED", "CANCELLED"].includes(taskStatusOf(t)));
        if (eligible.length === 0) {
            showToast("当前选中项中没有可重试的任务");
            return;
        }
        showConfirm("批量重试", `确定对「${eligible.length}」项失败/已跳过/已取消任务发起重试吗？`, async () => {
            const settled = await Promise.allSettled(
                eligible.map((t) => requestApi("POST", `/tasks/${encodeURIComponent(t.task_id)}/retry`)),
            );
            const ok = settled.filter((r) => r.status === "fulfilled" && r.value && r.value.code === 200).length;
            const fail = settled.length - ok;
            showToast(`批量重试完成：成功 ${ok} 项，失败 ${fail} 项`);
            clearTaskSelection();
            await Promise.all([loadTaskList(), loadDashboardOverview()]);
        });
        return;
    }
    if (action === "batch-ignore") {
        const eligible = records.filter((t) => isBatchableStatus(taskStatusOf(t)));
        if (eligible.length === 0) {
            showToast("当前选中项中没有可忽略的任务");
            return;
        }
        showConfirm("批量忽略", `确定忽略「${eligible.length}」项任务吗？`, async () => {
            const settled = await Promise.allSettled(
                eligible.map((t) => requestApi("POST", `/tasks/${encodeURIComponent(t.task_id)}/ignore`)),
            );
            const ok = settled.filter((r) => r.status === "fulfilled" && r.value && r.value.code === 200).length;
            const fail = settled.length - ok;
            showToast(`批量忽略完成：成功 ${ok} 项，失败 ${fail} 项`);
            clearTaskSelection();
            await Promise.all([loadTaskList(), loadDashboardOverview()]);
        });
        return;
    }
    if (action === "batch-delete") {
        const eligible = records.filter((t) => isBatchableStatus(taskStatusOf(t)));
        if (eligible.length === 0) {
            showToast("当前选中项中没有可移入回收的任务");
            return;
        }
        showConfirm("批量移入回收", `确定将「${eligible.length}」项任务移入回收站吗？\n\n任务不会立即物理删除，可在回收页恢复。`, async () => {
            const settled = await Promise.allSettled(
                eligible.map((t) => requestApi("POST", `/tasks/${encodeURIComponent(t.task_id)}/delete`, { delete_files: false })),
            );
            const ok = settled.filter((r) => r.status === "fulfilled" && r.value && r.value.code === 200).length;
            const fail = settled.length - ok;
            showToast(`批量移入回收完成：成功 ${ok} 项，失败 ${fail} 项`);
            clearTaskSelection();
            await Promise.all([loadTaskList(), loadDashboardOverview()]);
        });
    }
}

function showMatchTraceModal(trace, filename) {
    let html = '<div class="match-trace-modal" style="padding:16px;background:rgba(255,255,255,0.02);border-radius:8px">';
    html += '<h3 style="margin-top:0">匹配路径详情</h3>';
    html += '<p style="color:#94A3B8;font-size:12px;margin:8px 0 16px">文件：' + escapeHtml(filename || "") + '</p>';
    var steps = (trace && typeof trace === 'object' && trace.trace) || [];
    if (Array.isArray(steps) && steps.length > 0) {
        html += '<div style="display:flex;flex-direction:column;gap:12px">';
        for (var i = 0; i < steps.length; i++) {
            var step = steps[i];
            var color = step.matched ? "#22C55E" : (step.tier === 3 ? "#F59E0B" : "#94A3B8");
            html += '<div style="border:1px solid ' + color + '20;background:' + color + '08;padding:12px 16px;border-radius:8px">';
            html += '<div style="font-weight:600;color:' + color + '">第' + step.tier + '级：' + escapeHtml(step.name || "") + ' &nbsp;·&nbsp; ' + (step.matched ? "✓ 匹配" : "✗ 未匹配") + '</div>';
            if (step.reason) html += '<div style="margin-top:8px;font-size:13px;line-height:1.6;color:#CBD5E1">' + escapeHtml(step.reason) + '</div>';
            if (step.ai_reason) html += '<div style="margin-top:8px;font-size:13px;line-height:1.6;color:#06B6D4;border-left:2px solid #06B6D420;padding-left:12px">AI: ' + escapeHtml(step.ai_reason) + '</div>';
            html += '</div>';
        }
        html += '</div>';
    } else {
        html += '<p style="color:#94A3B8">无匹配路径信息</p>';
    }
    html += '</div>';
    if (typeof showAppModal === 'function') {
        showAppModal({ title: '匹配路径', body: html, actions: [{ label: '关闭', className: 'btn btn-secondary' }] });
    } else {
        alert(html.replace(/<[^>]+>/g, '\n'));
    }
}

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
        return "AI 已给出候选结果，等待你确认最终入库方向。";
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
    if (status === "PENDING" && stage === "RUNNING") {
        return "系统正在扫描、识别和整理这个文件。";
    }
    return "文件已经进入队列，等待系统开始扫描与识别。";
}

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
    if ((status === "SUCCESS" || status === "SKIPPED") && task.completed_at) bits.push(formatActivityTime(task.completed_at));
    if (bits.length === 0 && task.created_at) bits.push(formatActivityTime(task.created_at));
    return bits.join(" · ") || "等待处理";
}

function taskPrimaryAction(task) {
    const status = String(task.status || "").toUpperCase();
    const stage = String(task.stage || "").toUpperCase();
    if (status === "PENDING" && stage === "AWAIT_REVIEW") return { key: "confirm", label: "去确认" };
    if (status === "FAILED" || status === "SKIPPED") return { key: "retry-task", label: "去重试" };
    if (status === "SUCCESS") return { key: "view-task", label: "查看结果" };
    return { key: "view-task", label: "查看" };
}

function taskSecondaryAction(task) {
    const status = String(task.status || "").toUpperCase();
    const stage = String(task.stage || "").toUpperCase();
    if (status === "PENDING" && stage === "AWAIT_REVIEW") return { key: "edit-task", label: "修改" };
    if (status === "FAILED") return { key: "delete-task", label: "移入回收" };
    if (status === "PENDING" && stage === "QUEUED") return { key: "delete-task", label: "移入回收" };
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
    return `
        <article class="task-card" data-task-row="${escapeHtml(taskId)}" style="--card-index: ${index}">
            <input type="checkbox" class="task-select-checkbox" data-task-select="${escapeHtml(taskId)}" ${checked} aria-label="选择任务" />
            <div class="cover cover-${getTaskTone(item)}"></div>
            <div class="task-body">
                <div class="task-top"><h3>${escapeHtml(title)}</h3><span class="badge${danger}">${escapeHtml(getTaskStatusText(item.status, item.stage))}</span></div>
                <p>${escapeHtml(taskDescription(item))}</p>
                <div class="task-meta"><span>${escapeHtml(filename)}</span><span>${escapeHtml(taskMeta(item))}</span></div>
            </div>
            <div class="task-actions">
                <button data-task-action="${escapeHtml(primaryAction.key)}" data-task-id="${escapeHtml(item.task_id || "")}">${escapeHtml(primaryAction.label)}</button>
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
        document.getElementById("task-panel-count").textContent = "0 项";
        setBatchToolbarVisibility();
        updateBatchToolbar();
        return;
    }
    host.innerHTML = currentTaskRecords.map((item, index) => renderTaskCard(item, index)).join("");
    document.getElementById("task-panel-count").textContent = `${currentTaskRecords.length} 项`;
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
    selectedTaskIds.clear();
    document.querySelectorAll("[data-task-filter-chip]").forEach((chip) => {
        chip.classList.toggle("active", chip.dataset.taskFilterChip === filter);
    });
    loadTaskList();
}

async function listTasksByStatuses(params) {
    if (!params || Object.keys(params).length === 0) {
        const result = await requestApi("GET", "/tasks", { limit: 20 });
        if (result.code !== 200 || !result.data) return { code: result.code, message: result.message, tasks: [] };
        return { code: 200, tasks: result.data.tasks || [], total: result.data.total || 0 };
    }
    const query = {};
    if (params.status) {
        if (Array.isArray(params.status)) {
            query.status = params.status[0];
        } else {
            query.status = params.status;
        }
    }
    if (params.stage) query.stage = params.stage;
    const result = await requestApi("GET", "/tasks", query);
    if (result.code !== 200 || !result.data) return { code: result.code, message: result.message, tasks: [] };
    return { code: 200, tasks: result.data.tasks || [], total: result.data.total || 0 };
}

async function loadTaskList() {
    const meta = TASK_FILTER_META[currentTaskFilter] || TASK_FILTER_META.all;
    document.getElementById("task-panel-title").textContent = meta.title;
    document.getElementById("task-panel-copy").textContent = meta.copy;
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
    const result = await listTasksByStatuses(TASK_FILTER_PARAMS[currentTaskFilter]);
    if (result.code === 401) {
        currentTaskRecords = [];
        if (host) {
            host.innerHTML = `
                <article class="task-card">
                    <div class="cover cover-cyan"></div>
                    <div class="task-body">
                        <div class="task-top"><h3>需要先完成认证</h3><span class="badge danger">未认证</span></div>
                        <p>输入 API Key 后，这里才会显示真实任务、筛选统计和任务操作。</p>
                        <div class="task-meta"><span>任务工作台</span></div>
                    </div>
                </article>`;
        }
        document.getElementById("task-panel-count").textContent = "--";
        return;
    }
    if (result.code !== 200) {
        currentTaskRecords = [];
        if (host) {
            host.innerHTML = `
                <article class="task-card">
                    <div class="cover cover-red"></div>
                    <div class="task-body">
                        <div class="task-top"><h3>任务列表加载失败</h3><span class="badge danger">失败</span></div>
                        <p>${escapeHtml(result.message || "请稍后重试。")}</p>
                        <div class="task-meta"><span>任务工作台</span></div>
                    </div>
                    <div class="task-actions">
                        <button data-task-action="refresh-tasks">重新加载</button>
                    </div>
                </article>`;
        }
        document.getElementById("task-panel-count").textContent = "--";
        return;
    }
    currentTaskRecords = result.tasks || [];
    renderTaskList();
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

function buildTaskDimensionsForm(task, editable) {
    const dimensions = currentEnabledDimensions.length ? currentEnabledDimensions : [];
    const source = task.scrape_dimensions || task.dimensions || {};
    if (!dimensions.length) {
        return '<div class="cinema-modal-hint">当前还没有启用的分类维度。</div>';
    }
    return dimensions.map((dim) => {
        const rawValue = source[dim.name];
        const value = extractDimValue(rawValue);
        const options = Array.isArray(dim.value_list) ? dim.value_list : [];
        if (!editable) {
            const matchLabel = options.find((item) => item.value === value);
            const displayValue = matchLabel ? matchLabel.label || matchLabel.value : value || "—";
            return `
                <label class="cinema-modal-field">
                    <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                    <span class="cinema-modal-readonly-value">${escapeHtml(displayValue)}</span>
                </label>`;
        }
        if (options.length > 0) {
            const optionHtml = options.map((item) => {
                const selected = item.value === value ? " selected" : "";
                return `<option value="${escapeHtml(item.value)}"${selected}>${escapeHtml(item.label || item.value)}</option>`;
            }).join("");
            return `
                <label class="cinema-modal-field">
                    <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                    <select data-task-dim="${escapeHtml(dim.name)}" class="cinema-modal-select">
                        <option value="">（不修改）</option>
                        ${optionHtml}
                    </select>
                </label>`;
        }
        return `
            <label class="cinema-modal-field">
                <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                <input type="text" data-task-dim="${escapeHtml(dim.name)}" value="${escapeHtml(value)}" placeholder="留空表示不修改" />
            </label>`;
    }).join("");
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
    const hasAny = scrape.title_cn || scrape.title_en || scrape.year || scrape.type || scrape.overview || scrape.poster_url || scrape.confidence !== undefined;
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
    const confidence = scrape.confidence ?? task.scrape_confidence;
    const overview = scrape.overview || "";
    const poster = scrape.poster_url || "";
    const typeLabel = type === "movie" ? "电影" : type === "tv" ? "剧集" : (type || "—");
    const confidenceText = confidence !== undefined && confidence !== null && confidence !== "" ? Number(confidence).toFixed(2) : "—";
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
                        <span class="badge">置信度 ${escapeHtml(confidenceText)}</span>
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
    const isEditable = !["SUCCESS", "SKIPPED"].includes(status);

    const renameSection = isEditable
        ? `<div class="cinema-modal-block">
                <h4>文件名微调</h4>
                <label class="cinema-modal-field">
                    <span>新文件名</span>
                    <input type="text" id="task-rename-input" value="${escapeHtml(originalFilename)}" data-rename-original="${escapeHtml(originalFilename)}" />
                    <small>只填写新的文件名，不包含路径。</small>
                </label>
                ${buildRenamePreview(originalFilename)}
            </div>`
        : "";

    const dimSection = `<div class="cinema-modal-block">
            <h4>分类维度${isEditable ? "微调" : ""}</h4>
            ${isEditable ? '<button id="btn-preview-classify" class="btn btn-sm btn-outline" style="float:right;margin-top:-28px">入库预览</button>' : ""}
            <div class="cinema-modal-grid">${buildTaskDimensionsForm(task, isEditable)}</div>
            ${isEditable ? '<div id="preview-classify-result" class="cinema-modal-preview" style="display:none"></div>' : ""}
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
            ${renameSection}
            ${dimSection}
            <div class="cinema-modal-block">
                <h4>字幕记录</h4>
                ${buildSubtitleTable(subtitles)}
            </div>
        </div>`;

    const actions = [
        { label: "关闭", className: "btn btn-secondary" },
    ];

    if (isEditable) {
        actions.push({
            label: "保存新文件名",
            className: "btn btn-secondary",
            closeOnClick: false,
            onClick: async () => {
                const inputEl = document.getElementById("task-rename-input");
                const newFilename = String(inputEl?.value || "").trim();
                if (!newFilename) {
                    showToast("文件名不能为空");
                    return;
                }
                const result = await requestApi("POST", `/tasks/${encodeURIComponent(taskId)}/rename`, {
                    new_filename: newFilename,
                });
                showToast(result.message || "文件名已更新");
                if (result.code === 200) {
                    removeAppModal();
                    await openTaskDetailImpl(taskId, true);
                    await Promise.all([loadTaskList(), loadDashboardOverview()]);
                }
            },
        });
        actions.push({
            label: "应用分类微调",
            className: "btn btn-secondary",
            closeOnClick: false,
            onClick: async () => {
                const dims = {};
                document.querySelectorAll("[data-task-dim]").forEach((input) => {
                    const nextValue = parseRuleConditionValue(input.value);
                    if (nextValue) dims[input.dataset.taskDim] = nextValue;
                });
                if (Object.keys(dims).length === 0) {
                    showToast("请至少填写一个维度值");
                    return;
                }
                const result = await requestApi("POST", `/tasks/${encodeURIComponent(taskId)}/reclassify`, {
                    dimensions: dims,
                });
                showToast(result.message || "重新分类请求已发送");
                if (result.code === 200) {
                    removeAppModal();
                    await openTaskDetailImpl(taskId, true);
                    await Promise.all([loadTaskList(), loadDashboardOverview()]);
                }
            },
        });
    }

    showAppModal({
        title: "任务详情",
        body,
        actions,
    });

    // 入库预览按钮事件绑定
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
                    previewDiv.innerHTML = `<div class="preview-path"><span class="preview-label">入库目录：</span><code>${escapeHtml(d.import_path || "")}</code></div>
                        <div class="preview-path"><span class="preview-label">最终文件：</span><code>${escapeHtml(d.full_path || "")}</code></div>
                        ${d.warnings?.length ? `<div class="preview-warning">${escapeHtml(d.warnings.join("; "))}</div>` : ""}`;
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
        await loadTaskList();
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
    const hasFailedOrSkipped = selectedRecords.some((t) => ["FAILED", "SKIPPED"].includes(taskStatusOf(t)));
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
        const eligible = records.filter((t) => ["FAILED", "SKIPPED"].includes(taskStatusOf(t)));
        if (eligible.length === 0) {
            showToast("当前选中项中没有可重试的任务");
            return;
        }
        showConfirm("批量重试", `确定对「${eligible.length}」项失败/已跳过任务发起重试吗？`, async () => {
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

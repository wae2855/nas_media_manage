const DASHBOARD_REFRESH_MS = 15000;

const TASK_FILTER_META = {
    all: { title: "当前队列", copy: "先从待确认和失败项开始，会更快把主流程跑顺。" },
    pending: { title: "等待系统继续处理", copy: "这些文件已经进入队列，下一步会开始扫描、识别和判断。" },
    confirm: { title: "等待你来确认", copy: "先处理这些不确定条目，能最快减少后续误判和卡住的任务。" },
    failed: { title: "等待重试或排错", copy: "先看失败原因，再决定重试、调整配置或手动处理。" },
    success: { title: "今天已完成的入库", copy: "这里是已经跑通的结果，可以快速回看最终入库状态。" },
};

const TASK_FILTER_STATUS_MAP = {
    all: [],
    pending: ["PENDING", "PROCESSING"],
    confirm: ["CONFIRMING", "NEEDS_REVIEW"],
    failed: ["FAILED"],
    success: ["SUCCESS", "SKIPPED"],
};

let currentTaskFilter = "all";
let currentConfigStage = "source";
let currentConfigSnapshot = null;
let currentCleanerTab = "delete";
let dashboardRefreshTimer = null;
let currentTaskRecords = [];
let currentRecycleRecords = [];
let currentProviderDefinitions = [];
let currentEnabledDimensions = [];
let selectedTaskIds = new Set();
let selectedRecycleIds = new Set();
const STICKY_HERO_VIEWS = new Set([
    "advanced-config",
    "config-simulator",
    "naming-config",
    "dimensions-config",
    "prompt-config",
    "confidence-config",
    "security-config",
    "hermes-config",
    "system-settings",
]);

function setView(view, navKey = view) {
    document.querySelectorAll(".page-view").forEach((page) => {
        page.classList.toggle("active", page.dataset.view === view);
    });
    document.querySelectorAll(".nav-item").forEach((item) => {
        item.classList.toggle("active", item.dataset.nav === navKey);
    });
    updateStickyHeroState();
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => toast.classList.remove("show"), 2400);
}

function maskValue(value) {
    if (!value) return "未配置";
    return value;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

async function requestApi(method, endpoint, body = null) {
    if (typeof apiRequest === "function") {
        return apiRequest(method, endpoint, body);
    }
    return { code: 500, message: "API helper unavailable" };
}

function normalizePathValue(value) {
    const raw = String(value ?? "").trim();
    if (!raw || raw === "未配置") return "";
    return raw.replace(/\/+$/, "") || "/";
}

function parseMultilineValue(id) {
    const field = document.getElementById(id);
    if (!field) return [];
    return String(field.value || "")
        .split(/[\n,]+/)
        .map((item) => item.trim())
        .filter(Boolean);
}

function showPathTestFeedback(result, label) {
    if (!result || result.code !== 200 || !result.data) {
        showToast(result?.message || `${label} 权限测试失败`);
        return;
    }
    if (result.data.ok) {
        showToast(`${label}：${result.data.message || "权限正常"}`);
        return;
    }
    buildPermissionIssueDialog([
        {
            field: label,
            path: result.data.path,
            message: result.data.message,
            hint: result.data.hint,
        },
    ], `${label} 权限不足`);
}

function currentPathSnapshot() {
    return {
        source_dir: normalizePathValue(document.getElementById("cfg-source-inline")?.value),
        temp_dir: normalizePathValue(document.getElementById("cfg-temp-inline")?.value),
        recycle_dir: normalizePathValue(document.getElementById("cfg-recycle-inline")?.value),
        fallback_dir: normalizePathValue(document.getElementById("cfg-fallback-inline")?.value),
    };
}

function validateDirectoryConflicts(paths) {
    const conflicts = [];
    if (paths.source_dir && paths.temp_dir && paths.source_dir === paths.temp_dir) conflicts.push("源目录与中转目录不能相同");
    if (paths.source_dir && paths.recycle_dir && paths.source_dir === paths.recycle_dir) conflicts.push("源目录与回收目录不能相同");
    if (paths.temp_dir && paths.recycle_dir && paths.temp_dir === paths.recycle_dir) conflicts.push("中转目录与回收目录不能相同");
    return conflicts;
}

function statusCount(source, ...keys) {
    return keys.reduce((total, key) => total + Number(source?.[key] || 0), 0);
}

function formatActivityTime(value) {
    if (!value) return "刚刚";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "刚刚";
    const diffMs = Date.now() - parsed.getTime();
    const diffMinutes = Math.max(0, Math.floor(diffMs / 60000));
    if (diffMinutes < 1) return "刚刚";
    if (diffMinutes < 60) return `${diffMinutes} 分钟前`;
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours} 小时前`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} 天前`;
}

function activityIcon(level) {
    const normalized = String(level || "").toUpperCase();
    if (normalized === "ERROR") return "alert";
    if (normalized === "WARNING" || normalized === "WARN") return "clock";
    return "check";
}

function activityTone(level) {
    const normalized = String(level || "").toUpperCase();
    if (normalized === "ERROR") return " danger";
    if (normalized === "WARNING" || normalized === "WARN") return " warning";
    return "";
}

function renderActivityRows(items) {
    const host = document.getElementById("activity-list");
    if (!host) return;
    if (!Array.isArray(items) || items.length === 0) {
        host.innerHTML = '<div class="activity-row"><div class="state"><svg class="icon icon-sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-clock"></use></svg></div><div><b>当前还没有新的活动记录</b><small>系统启动后，这里会滚动显示扫描、识别和入库过程。</small></div><span class="time">刚刚</span></div>';
        return;
    }
    host.innerHTML = items.map((item) => `
        <div class="activity-row">
            <div class="state${activityTone(item.level)}"><svg class="icon icon-sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-${activityIcon(item.level)}"></use></svg></div>
            <div><b>${escapeHtml(item.title || "最新活动")}</b><small>${escapeHtml(item.copy || "")}</small></div>
            <span class="time">${escapeHtml(formatActivityTime(item.timestamp))}</span>
        </div>
    `).join("");
}

function setDashboardQueueStrip(text, ratio = 0) {
    const title = document.getElementById("current-job");
    const progress = document.querySelector(".now-strip .progress span");
    if (title) title.textContent = text;
    if (progress) {
        if (ratio <= 0) {
            progress.style.width = "0%";
        } else {
            progress.style.width = `${Math.max(6, Math.min(100, Math.round(ratio * 100)))}%`;
        }
    }
}

async function loadHtmlPartial(targetId, url) {
    const host = document.getElementById(targetId);
    if (!host) return;
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`加载片段失败: ${url}`);
    host.innerHTML = await response.text();
}

async function runAction(action, trigger) {
    if (action === "clear-expired-recycle") {
        const expiredItems = currentRecycleRecords.filter((item) => !item.restorable).map((item) => item.recycle_path || item.id).filter(Boolean);
        if (expiredItems.length === 0) {
            showToast("当前没有待清理的过期回收项");
            return;
        }
        showConfirm("清理过期项", `确定清理当前 ${expiredItems.length} 个待清理回收项吗？`, async () => {
            const result = await requestApi("POST", "/recycle/delete", { items: expiredItems });
            showToast(result.message || "过期回收项清理请求已发送");
            if (result.code === 200 || result.code === 207) await loadRecycleData();
        });
        return;
    }
    const endpointByAction = { scan: "/run", pause: "/queue/pause", retry: "/queue/retry-all" };
    if (!endpointByAction[action]) {
        console.warn(`[cinema-app] 未识别的操作：${action}`);
        showToast("未识别的操作，请检查入口是否已接线");
        return;
    }
    const queueSnapshot = await fetchQueueSnapshot();
    if (action === "pause" && queueSnapshot.paused) {
        showToast("队列已经处于暂停状态，无需重复操作");
        return;
    }
    if (action === "retry" && queueSnapshot.failed === 0) {
        showToast("当前没有失败任务，先去扫描或等系统处理新文件吧");
        return;
    }
    if (action === "scan" && queueSnapshot.totalOpen > 0) {
        showToast(`当前已有 ${queueSnapshot.totalOpen} 个任务在处理中，请等待或前往任务工作台查看进度`);
    }
    if (trigger) trigger.disabled = true;
    const result = await requestApi("POST", endpointByAction[action]);
    if (trigger) trigger.disabled = false;
    const friendly = {
        scan: result.code === 200 ? "扫描已启动，任务入队后会自动出现在工作台" : (result.message || "扫描请求已发送"),
        pause: result.code === 200 ? "处理已暂停，新文件不会自动入库" : (result.message || "暂停请求已发送"),
        retry: result.code === 200 ? "正在批量重试失败任务" : (result.message || "重试请求已发送"),
    };
    showToast(friendly[action] || result.message || "请求已发送");
    if (result.code === 200 || result.code === 202) {
        await loadDashboardOverview();
    }
}

async function fetchQueueSnapshot() {
    try {
        const result = await requestApi("GET", "/queue/status");
        if (result.code !== 200 || !result.data) {
            return { paused: false, totalOpen: 0, failed: 0 };
        }
        const byStatus = result.data.by_status || {};
        const pending = statusCount(byStatus, "PENDING", "pending");
        const processing = statusCount(byStatus, "PROCESSING", "processing");
        const confirm = statusCount(byStatus, "CONFIRMING", "confirming", "NEEDS_REVIEW", "needs_review");
        const failed = statusCount(byStatus, "FAILED", "failed");
        return {
            paused: !!result.data.paused,
            totalOpen: pending + processing + confirm + failed,
            failed,
        };
    } catch (e) {
        return { paused: false, totalOpen: 0, failed: 0 };
    }
}

function setConfigStage(stage) {
    currentConfigStage = stage;
    document.querySelectorAll("[data-config-stage]").forEach((card) => {
        card.classList.toggle("active", card.dataset.configStage === stage);
    });
    document.querySelectorAll("[data-config-panel]").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.configPanel === stage);
    });
}

function setCleanerTab(tab) {
    currentCleanerTab = tab;
    document.querySelectorAll("[data-cleaner-tab]").forEach((item) => {
        item.classList.toggle("active", item.dataset.cleanerTab === tab);
    });
    document.querySelectorAll("[data-cleaner-panel]").forEach((item) => {
        item.classList.toggle("active", item.dataset.cleanerPanel === tab);
    });
}

function toggleAdvancedDisclosure(name) {
    const button = document.querySelector(`[data-advanced-disclosure="${name}"]`);
    const panel = document.querySelector(`[data-advanced-panel="${name}"]`);
    if (!button || !panel) return;
    const next = !button.classList.contains("active");
    button.classList.toggle("active", next);
    panel.classList.toggle("active", next);
}

function toggleHermesInlineFields() {
    const toggle = document.getElementById("cfg-hermes_enabled-inline");
    const fields = document.getElementById("hermes-inline-fields");
    if (!toggle || !fields) return;
    fields.style.display = toggle.checked ? "grid" : "none";
}

function toggleCleanerPrompt(open) {
    const editor = document.getElementById("sc-prompt-inline-editor");
    const next = typeof open === "boolean" ? open : !editor.classList.contains("active");
    editor.classList.toggle("active", next);
}

function toggleSourceCleanerUi() {
    const enabled = document.getElementById("cfg-source-cleaner-enabled-inline").checked;
    const aiEnabled = enabled && document.getElementById("cfg-source_cleaner-ai_enabled-inline").checked;
    document.getElementById("source-cleaner-panel").classList.toggle("active", enabled);
    document.getElementById("sc-ai-actions-inline").classList.toggle("active", aiEnabled);
    document.getElementById("sc-merge-inline-card").classList.toggle("active", aiEnabled);
    if (!enabled || !aiEnabled) toggleCleanerPrompt(false);
}

function toggleSourceDepthField() {
    const enabled = document.getElementById("cfg-source-recursive-toggle-inline").checked;
    document.getElementById("cfg-source-depth-group-inline").classList.toggle("active", enabled);
}

function toggleFileWatcherPollGroup() {
    const enabled = document.getElementById("cfg-file_watcher-enabled-inline").checked;
    const group = document.getElementById("cfg-file_watcher-poll-group-inline");
    if (group) group.classList.toggle("active", enabled);
}

function updateStickyHeroState() {
    document.querySelectorAll(".page-hero.is-condensed").forEach((hero) => hero.classList.remove("is-condensed"));
    const activePage = document.querySelector(".page-view.active");
    if (!activePage || !STICKY_HERO_VIEWS.has(activePage.dataset.view)) return;
    const hero = activePage.querySelector(".page-hero");
    if (!hero) return;
    hero.classList.toggle("is-condensed", window.scrollY > 56);
}

function setFieldValue(id, value) {
    const field = document.getElementById(id);
    if (!field) return;
    field.value = value;
}

async function loadDashboardMetrics() {
    const result = await requestApi("GET", "/metrics");
    if (result.code === 401) {
        setDashboardQueueStrip("请先完成 API Key 认证后查看当前队列", 0);
        return;
    }
    if (result.code !== 200 || !result.data) {
        setDashboardQueueStrip("暂时无法读取首页状态，请稍后重试", 0);
        return;
    }
    const queue = result.data.queue_by_status || {};
    document.getElementById("metric-pending").textContent = queue.PENDING || queue.pending || 0;
    document.getElementById("metric-confirm").textContent = statusCount(queue, "CONFIRMING", "confirming", "NEEDS_REVIEW", "needs_review");
    document.getElementById("metric-success").textContent = queue.SUCCESS || queue.success || 0;
}

async function loadDashboardQueueStatus() {
    const result = await requestApi("GET", "/queue/status");
    if (result.code === 401) {
        setDashboardQueueStrip("请先完成 API Key 认证后查看当前队列", 0);
        return;
    }
    if (result.code !== 200 || !result.data) {
        setDashboardQueueStrip("暂时无法读取当前队列", 0);
        return;
    }
    const byStatus = result.data.by_status || {};
    const pending = statusCount(byStatus, "PENDING", "pending");
    const processing = statusCount(byStatus, "PROCESSING", "processing");
    const confirm = statusCount(byStatus, "CONFIRMING", "confirming", "NEEDS_REVIEW", "needs_review");
    const failed = statusCount(byStatus, "FAILED", "failed");
    const totalOpen = pending + processing + confirm + failed;
    if (result.data.paused) {
        setDashboardQueueStrip(`队列已暂停，仍有 ${totalOpen} 项待继续处理`, totalOpen > 0 ? 0.28 : 0);
        return;
    }
    if (processing > 0) {
        setDashboardQueueStrip(`当前有 ${processing} 项正在处理中，后面还有 ${Math.max(0, totalOpen - processing)} 项等待`, totalOpen > 0 ? processing / totalOpen : 0.52);
        return;
    }
    if (confirm > 0) {
        setDashboardQueueStrip(`当前有 ${confirm} 项等待确认，建议优先处理这些条目`, totalOpen > 0 ? confirm / totalOpen : 0.34);
        return;
    }
    if (failed > 0) {
        setDashboardQueueStrip(`当前有 ${failed} 项处理失败，可直接发起重试`, totalOpen > 0 ? failed / totalOpen : 0.24);
        return;
    }
    if (pending > 0) {
        setDashboardQueueStrip(`当前有 ${pending} 项等待系统开始扫描与识别`, totalOpen > 0 ? pending / totalOpen : 0.18);
        return;
    }
    setDashboardQueueStrip("等待新影片进入队列", 0);
}

async function loadDashboardActivity() {
    const result = await requestApi("GET", "/logs?limit=6");
    if (result.code === 401) {
        renderActivityRows([
            {
                title: "需要先完成认证",
                copy: "输入 API Key 后，这里会显示真实扫描、识别和入库过程。",
                level: "WARNING",
                timestamp: new Date().toISOString(),
            },
        ]);
        return;
    }
    if (result.code !== 200 || !result.data) {
        renderActivityRows([
            {
                title: "暂时无法读取最近活动",
                copy: result.message || "请稍后重试，或检查服务连接状态。",
                level: "ERROR",
                timestamp: new Date().toISOString(),
            },
        ]);
        return;
    }
    const logs = Array.isArray(result.data.logs) ? result.data.logs : [];
    const items = logs.slice().reverse().map((log) => ({
        title: log.message || "最新活动",
        copy: [log.task_id ? `任务 ${log.task_id}` : "", log.step ? `步骤 ${log.step}` : ""].filter(Boolean).join(" · ") || "系统正在持续记录处理过程。",
        level: log.level || "INFO",
        timestamp: log.timestamp || log.time,
    }));
    renderActivityRows(items);
}

async function loadDashboardOverview() {
    await Promise.all([
        loadDashboardMetrics(),
        loadDashboardQueueStatus(),
        loadDashboardActivity(),
    ]);
}

function startDashboardAutoRefresh() {
    if (dashboardRefreshTimer) window.clearInterval(dashboardRefreshTimer);
    dashboardRefreshTimer = window.setInterval(() => {
        loadDashboardOverview();
    }, DASHBOARD_REFRESH_MS);
}

async function loadDirectoryConfig() {
    const result = await requestApi("GET", "/config");
    if (result.code !== 200 || !result.data) {
        const providerHost = document.getElementById("provider-inline-stack");
        if (providerHost) {
            providerHost.innerHTML = `<article class="provider-inline-empty">${result.code === 401 ? "请先完成 API Key 认证后加载 Provider 配置" : "配置加载失败，请稍后重试"}</article>`;
        }
        return;
    }
    const rawConfig = result.data.config || result.data;
    const promptsData = result.data.prompts || {};
    currentConfigSnapshot = rawConfig;
    const metadata = rawConfig.metadata || {};
    const llm = rawConfig.llm || {};
    const sourcePolicy = rawConfig.source_policy || {};
    const sourceCleaner = rawConfig.source_cleaner || {};
    const paths = {
        source_dir: rawConfig.source_dir || "",
        temp_dir: rawConfig.temp_dir || "",
        recycle_dir: sourcePolicy.recycle_dir || sourcePolicy.quarantine_dir || "",
    };
    setFieldValue("cfg-source-inline", paths.source_dir);
    setFieldValue("cfg-temp-inline", paths.temp_dir);
    setFieldValue("cfg-recycle-inline", paths.recycle_dir);
    document.getElementById("cfg-source-recursive-toggle-inline").checked = (sourcePolicy.scan_recursive ?? true);
    setFieldValue("cfg-source-depth-inline", sourcePolicy.scan_max_depth || 5);
    setFieldValue("cfg-recycle-retention-inline", sourcePolicy.recycle_retention_days || 30);
    setFieldValue("cfg-fallback-inline", rawConfig.fallback_dir || "");
    setFieldValue("cfg-filename_templates-movie-inline", ((rawConfig.filename_templates || {}).movie) || "");
    setFieldValue("cfg-filename_templates-tv-inline", ((rawConfig.filename_templates || {}).tv) || "");
    setFieldValue("cfg-filename_templates-subtitle-inline", ((rawConfig.filename_templates || {}).subtitle) || "");
    setFieldValue("cfg-duplicate_handling-strategy-inline", ((rawConfig.duplicate_handling || {}).strategy) || "skip");
    setFieldValue("prompt-system", promptsData.system_prompt || "");
    setFieldValue("cfg-server_api_key-inline", ((rawConfig.server || {}).api_key) || "");
    setFieldValue("cfg-server_port-inline", ((rawConfig.server || {}).port) || 9855);
    setFieldValue("cfg-log_dir-inline", rawConfig.log_dir || "");
    setFieldValue("cfg-resource_dir-inline", rawConfig.resource_dir || rawConfig.resources_dir || "");
    setFieldValue("cfg-task_queue-max_concurrent-inline", ((rawConfig.task_queue || {}).max_concurrent) || 1);
    const watcherCfg = rawConfig.file_watcher || {};
    document.getElementById("cfg-file_watcher-enabled-inline").checked = !!watcherCfg.enabled;
    setFieldValue("cfg-file_watcher-poll_interval-inline", watcherCfg.poll_interval || 60);
    toggleFileWatcherPollGroup();
    setFieldValue("cfg-video_extensions-inline", (rawConfig.video_extensions || []).join("\n"));
    setFieldValue("cfg-subtitle_extensions-inline", (rawConfig.subtitle_extensions || []).join("\n"));
    setFieldValue("cfg-llm_provider-inline", llm.provider || "openai");
    setFieldValue("cfg-llm_api_key-inline", llm.api_key || "");
    setFieldValue("cfg-llm_base_url-inline", llm.base_url || "");
    setFieldValue("cfg-llm_model-inline", llm.model || "");
    setFieldValue("cfg-llm_fallback_model-inline", llm.fallback_model || "");
    setFieldValue("cfg-llm_fast_model-inline", llm.fast_model || "");
    setFieldValue("cfg-llm_timeout-inline", llm.timeout || 30);
    setFieldValue("cfg-llm_max_retries-inline", llm.max_retries || 2);
    setFieldValue("cfg-llm_retry_delay-inline", llm.retry_delay || 3);
    setFieldValue("cfg-llm_confidence_threshold-inline", llm.confidence_threshold || 0.8);
    document.getElementById("cfg-llm_verify_ssl-inline").checked = !!llm.verify_ssl;
    document.getElementById("cfg-source-cleaner-enabled-inline").checked = !!sourceCleaner.enabled;
    document.getElementById("cfg-hermes_enabled-inline").checked = !!((rawConfig.hermes || {}).enabled);
    setFieldValue("cfg-hermes_webhook_base_url-inline", (((rawConfig.hermes || {}).webhook || {}).base_url) || "");
    setFieldValue("cfg-hermes_webhook_route_name-inline", (((rawConfig.hermes || {}).webhook || {}).route_name) || "");
    setFieldValue("cfg-hermes_webhook_secret-inline", (((rawConfig.hermes || {}).webhook || {}).secret) || "");
    setFieldValue("cfg-hermes_webhook_timeout-inline", (((rawConfig.hermes || {}).webhook || {}).timeout) || 30);
    setFieldValue("cfg-hermes_webhook_max_retries-inline", (((rawConfig.hermes || {}).webhook || {}).max_retries) || 3);
    setFieldValue("cfg-hermes_webhook_retry_delay-inline", (((rawConfig.hermes || {}).webhook || {}).retry_delay) || 5);
    const hermesEvents = (((rawConfig.hermes || {}).webhook || {}).events) || [];
    document.getElementById("cfg-hermes_webhook_verify_ssl-inline").checked = !!((((rawConfig.hermes || {}).webhook || {}).verify_ssl));
    document.getElementById("cfg-hermes_event_batch_start-inline").checked = hermesEvents.includes("batch_start");
    document.getElementById("cfg-hermes_event_batch_complete-inline").checked = hermesEvents.includes("batch_complete");
    document.getElementById("cfg-hermes_event_program_error-inline").checked = hermesEvents.includes("program_error");
    document.querySelectorAll('input[name="cfg-source_cleaner-cleanup_mode_inline"]').forEach((radio) => {
        radio.checked = radio.value === (sourceCleaner.cleanup_mode || "media_only");
    });
    document.getElementById("cfg-source_cleaner-ai_enabled-inline").checked = !!sourceCleaner.ai_enabled;
    setFieldValue("cfg-source_cleaner-merge_strategy-inline", sourceCleaner.merge_strategy || "intersection");
    setFieldValue("cfg-source_cleaner-delete_extensions-inline", (sourceCleaner.delete_extensions || []).join("\n"));
    setFieldValue("cfg-source_cleaner-protect_extensions-inline", (sourceCleaner.protect_extensions || []).join("\n"));
    setFieldValue("cfg-source_cleaner-blacklist_patterns-inline", (sourceCleaner.blacklist_patterns || []).join("\n"));
    setFieldValue("cfg-source_cleaner-junk_video_max_size_mb-inline", sourceCleaner.junk_video_max_size_mb != null ? sourceCleaner.junk_video_max_size_mb : 0);
    document.getElementById("cfg-source_cleaner-cleanup_empty_dirs-inline").checked = !!sourceCleaner.cleanup_empty_dirs;
    setFieldValue("cfg-source_cleaner-schedule-inline", sourceCleaner.schedule || "");
    setFieldValue("cfg-source_cleaner-ai_prompt-inline", sourceCleaner.ai_prompt || "");
    renderRuleList(rawConfig.path_rules || []);
    updateConfigStageStatus(rawConfig, paths, rawConfig.path_rules || []);
    loadCinemaConfidenceConfig(rawConfig);
    await loadInlineProviderConfigs(metadata);
    toggleSourceDepthField();
    toggleSourceCleanerUi();
    toggleHermesInlineFields();
    if (typeof loadDimensions === "function") await loadDimensions();
    await loadDimensionVars();
    await loadTmdbPromptConfig();
}

async function loadTmdbPromptConfig() {
    const result = await requestApi("GET", "/providers/tmdb/prompts");
    if (result.code !== 200 || !result.data) return;
    setFieldValue("prompt-tmdb", result.data.system_prompt || "");
}

function bindEvents() {
    document.addEventListener("click", (event) => {
        const nav = event.target.closest("[data-nav]");
        if (nav) {
            setView(nav.dataset.viewTarget || nav.dataset.nav, nav.dataset.nav);
            if (nav.dataset.taskFilter) setTaskFilter(nav.dataset.taskFilter);
        }
        const promptAction = event.target.closest("[data-prompt-action]");
        if (promptAction) {
            const actionMap = {
                "save-all": () => performPromptAction("save-all"),
                "reset-system": () => performPromptAction("reset-system"),
                "preview-system": () => performPromptAction("preview-system"),
                "reset-tmdb": () => performPromptAction("reset-tmdb"),
                "preview-tmdb": () => performPromptAction("preview-tmdb"),
            };
            const handler = actionMap[promptAction.dataset.promptAction];
            if (handler) handler();
            return;
        }
        const taskFilterChip = event.target.closest("[data-task-filter-chip]");
        if (taskFilterChip) setTaskFilter(taskFilterChip.dataset.taskFilterChip);
        const configStage = event.target.closest("[data-config-stage]");
        if (configStage) setConfigStage(configStage.dataset.configStage);
        const stageJump = event.target.closest("[data-config-stage-jump]");
        if (stageJump) setConfigStage(stageJump.dataset.configStageJump);
        const cleanerTab = event.target.closest("[data-cleaner-tab]");
        if (cleanerTab) setCleanerTab(cleanerTab.dataset.cleanerTab);
        const varGroup = event.target.closest("[data-var-group]");
        if (varGroup) toggleVarGroup(varGroup.dataset.varGroup);
        const advancedDisclosure = event.target.closest("[data-advanced-disclosure]");
        if (advancedDisclosure) toggleAdvancedDisclosure(advancedDisclosure.dataset.advancedDisclosure);
        if (event.target.closest("#btn-sc-prompt-inline")) toggleCleanerPrompt();
        if (event.target.closest("#btn-sc-prompt-close-inline")) toggleCleanerPrompt(false);
        if (event.target.closest("#btn-confidence-simulate")) {
            runConfigSimulator();
            return;
        }
        const ruleAction = event.target.closest("[data-rule-action]");
        if (ruleAction) {
            const index = Number(ruleAction.dataset.ruleIndex || -1);
            if (ruleAction.dataset.ruleAction === "add") openRuleEditor();
            if (ruleAction.dataset.ruleAction === "edit") openRuleEditor(index);
            if (ruleAction.dataset.ruleAction === "delete") deleteInlineRule(index);
            return;
        }
        const taskAction = event.target.closest("[data-task-action]");
        if (taskAction) {
            performTaskAction(taskAction.dataset.taskAction, taskAction.dataset.taskId || "");
            return;
        }
        const taskSelect = event.target.closest("[data-task-select]");
        if (taskSelect) {
            toggleTaskSelect(taskSelect.dataset.taskSelect);
            return;
        }
        const taskRow = event.target.closest("[data-task-row]");
        if (taskRow && !event.target.closest("button, input, a, select, textarea")) {
            openTaskDetail(taskRow.dataset.taskRow || "");
            return;
        }
        const batchTaskAction = event.target.closest("[data-batch-task-action]");
        if (batchTaskAction) {
            performBatchTaskAction(batchTaskAction.dataset.batchTaskAction);
            return;
        }
        const recycleAction = event.target.closest("[data-recycle-action]");
        if (recycleAction) {
            performRecycleAction(recycleAction.dataset.recycleAction, recycleAction.dataset.recycleId || "");
            return;
        }
        const recycleSelect = event.target.closest("[data-recycle-select]");
        if (recycleSelect) {
            toggleRecycleSelect(recycleSelect.dataset.recycleSelect);
            return;
        }
        const batchRecycleAction = event.target.closest("[data-batch-recycle-action]");
        if (batchRecycleAction) {
            performBatchRecycleAction(batchRecycleAction.dataset.batchRecycleAction);
            return;
        }
        const providerAction = event.target.closest("[data-provider-action]");
        if (providerAction) {
            const providerType = providerAction.dataset.providerType || "";
            const actionMap = {
                save: () => saveProvidersConfig(providerType),
                test: () => testProviderConnection(providerType),
                preview: () => previewProvider(providerType),
            };
            const handler = actionMap[providerAction.dataset.providerAction];
            if (handler) handler();
            return;
        }
        const configSave = event.target.closest("[data-config-save]");
        if (configSave) {
            const actionMap = {
                source: saveSourceConfig,
                temp: saveTempConfig,
                recycle: saveRecycleConfig,
                rules: saveRulesConfig,
                scrape: () => saveProvidersConfig(""),
                ai: saveLlmConfig,
                naming: saveImportOptionsConfig,
                confidence: saveConfidenceConfig,
                security: saveSecurityConfig,
                hermes: saveHermesConfig,
                system: saveAdvancedSystemConfig,
            };
            const handler = actionMap[configSave.dataset.configSave];
            if (handler) handler();
            return;
        }
        const pathTest = event.target.closest("[data-path-test]");
        if (pathTest) {
            testConfigPath(pathTest.dataset.pathTest);
            return;
        }
        const rulesTest = event.target.closest("[data-rules-test]");
        if (rulesTest) {
            testAllRulePermissions();
            return;
        }
        const llmTest = event.target.closest("[data-llm-test]");
        if (llmTest) {
            testLlmConnection();
            return;
        }
        const hermesTest = event.target.closest("[data-hermes-test]");
        if (hermesTest) {
            testHermesConnection();
            return;
        }
        const action = event.target.closest("[data-action]");
        if (action) runAction(action.dataset.action, action);
    });
    document.addEventListener("input", (event) => {
        if (event.target.closest('[data-section="confidence"] input[data-key]')) updateThresholdBar();
        if (event.target.id === "task-rename-input") updateRenamePreview(event.target);
    });
    document.addEventListener("change", (event) => {
        const taskSelectAll = event.target.closest("[data-task-select-all]");
        if (taskSelectAll) {
            selectAllVisibleTasks();
            return;
        }
        const recycleSelectAll = event.target.closest("[data-recycle-select-all]");
        if (recycleSelectAll) {
            selectAllVisibleRecycle();
            return;
        }
        const providerToggle = event.target.closest("[data-provider-toggle]");
        if (!providerToggle) return;
        const card = providerToggle.closest("[data-provider-card]");
        if (card) card.classList.toggle("is-disabled", !providerToggle.checked);
    });
    document.getElementById("cfg-source-cleaner-enabled-inline").addEventListener("change", toggleSourceCleanerUi);
    document.getElementById("cfg-source_cleaner-ai_enabled-inline").addEventListener("change", toggleSourceCleanerUi);
    document.getElementById("cfg-source-recursive-toggle-inline").addEventListener("change", toggleSourceDepthField);
    const watcherToggle = document.getElementById("cfg-file_watcher-enabled-inline");
    if (watcherToggle) watcherToggle.addEventListener("change", toggleFileWatcherPollGroup);
    const hermesToggle = document.getElementById("cfg-hermes_enabled-inline");
    if (hermesToggle) hermesToggle.addEventListener("change", toggleHermesInlineFields);
    window.addEventListener("scroll", updateStickyHeroState, { passive: true });
    window.addEventListener("resize", updateStickyHeroState);
}

/* ===== 首页胶卷轮转 ===== */
function initReelWheel() {
    const wheel = document.getElementById("reel-wheel");
    const emptyState = document.getElementById("reel-empty-state");
    if (!wheel) return;

    function getTranslateZ(count) {
        if (count <= 1) return 320;
        const angleRad = (2 * Math.PI) / count;
        const halfFrame = 75;
        /* 3.2 倍间距系数，帧与帧之间空隙更大 */
        const minR = (halfFrame + halfFrame * Math.tan(angleRad / 2)) * 3.2;
        return Math.max(320, Math.ceil(minR));
    }

    window.buildReelWheel = function buildReelWheel(items) {
        wheel.innerHTML = "";
        if (!items || items.length === 0) {
            wheel.parentElement.style.display = "none";
            if (emptyState) emptyState.style.display = "flex";
            return;
        }
        wheel.parentElement.style.display = "";
        if (emptyState) emptyState.style.display = "none";

        const count = items.length;
        const tz = getTranslateZ(count);
        const angleStep = 360 / count;

        for (let i = 0; i < count; i++) {
            const angle = i * angleStep;
            const item = items[i];
            const frame = document.createElement("div");
            frame.className = "reel-frame";
            frame.style.transform = `rotateY(${angle}deg) translateZ(${tz}px)`;

            let imgHtml = "";
            if (item.image) {
                imgHtml = `<img src="${item.image}" alt="${item.title || '影片'}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"><div class="reel-frame-placeholder" style="display:none;width:100%;height:100%;border-radius:3px;background:linear-gradient(150deg,#19100a,#eabf63);align-items:center;justify-content:center;"><span style="font-size:22px;opacity:0.3;">🎬</span></div>`;
            } else {
                const tone = item.tone || "gold";
                const gradientMap = {
                    gold: "linear-gradient(150deg, #19100a, #eabf63)",
                    red: "linear-gradient(150deg, #210d0b, #a43228)",
                    cyan: "linear-gradient(150deg, #061818, #43c7b7)",
                };
                const grad = gradientMap[tone] || gradientMap.gold;
                imgHtml = `<div style="width:100%;height:100%;border-radius:3px;background:${grad};display:flex;align-items:center;justify-content:center;"><span style="font-size:22px;opacity:0.3;">🎬</span></div>`;
            }

            frame.innerHTML = `
                <div class="reel-frame-img">${imgHtml}</div>
                <span class="reel-badge">${String(i + 1).padStart(2, "0")}</span>
            `;
            wheel.appendChild(frame);
        }
    };

    /* 初始空状态 */
    window.buildReelWheel([]);
}

/* 缩略图缓存：避免重复请求 */
let _cachedThumbnails = null;
let _thumbnailCacheTime = 0;
const THUMBNAIL_CACHE_TTL = 30000; // 30秒缓存

function loadReelWheelFromTasks() {
    /* 只使用 Thumbnail 文件夹的图片，没有图片时显示空状态 */
    const now = Date.now();
    const useCache = _cachedThumbnails && (now - _thumbnailCacheTime < THUMBNAIL_CACHE_TTL);

    function buildWheel(thumbnails) {
        let items = [];

        /* 如果有缩略图，用缩略图填充轮盘 */
        if (thumbnails && thumbnails.length > 0) {
            items = thumbnails.map((t, i) => ({
                title: t.name || `影片 ${i + 1}`,
                tone: "gold",
                image: t.url,
            }));
        }
        /* 没有缩略图时，保持空状态，不回退到任务封面色 */

        if (typeof buildReelWheel === "function") buildReelWheel(items);
    }

    if (useCache) {
        buildWheel(_cachedThumbnails);
        return;
    }

    /* 从后端获取缩略图列表 */
    fetch("/api/thumbnails")
        .then(r => r.ok ? r.json() : null)
        .then(data => {
            if (data && data.data && data.data.thumbnails) {
                _cachedThumbnails = data.data.thumbnails;
                _thumbnailCacheTime = Date.now();
                buildWheel(_cachedThumbnails);
            } else {
                _cachedThumbnails = [];
                _thumbnailCacheTime = Date.now();
                buildWheel([]);
            }
        })
        .catch(() => {
            buildWheel(null);
        });
}

document.addEventListener("DOMContentLoaded", async () => {
    await loadHtmlPartial("advanced-pages-slot", "partials/advanced-pages.html");
    bindEvents();
    renderStaticLists();
    initReelWheel();
    setTaskFilter("all");
    await loadTaskList();
    await loadRecycleData();
    setConfigStage("start");
    setCleanerTab("delete");
    updateStickyHeroState();
    loadDashboardOverview();
    loadReelWheelFromTasks();
    startDashboardAutoRefresh();
    loadDirectoryConfig();
    if (typeof checkApiKeyRequired === "function") checkApiKeyRequired();
});

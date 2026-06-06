const DEMO_TASKS = [
    { title: "沙丘 2", status: "已入库", filter: "success", desc: "TMDB 命中 · 字幕已重命名 · 1080p / BluRay", meta: "置信度 96%", tone: "gold" },
    { title: "Unknown.Movie.2024", status: "待确认", filter: "confirm", desc: "AI 识别不确定，需要选择电影/剧集并确认标题。", meta: "置信度 62%", tone: "red" },
    { title: "银河护卫队 S01E03", status: "失败", filter: "failed", desc: "Provider 连接超时，保留临时文件等待重试。", meta: "重试 1 次", tone: "cyan" },
    { title: "流浪地球 3 预告片", status: "待处理", filter: "pending", desc: "文件已进入队列，等待扫描与元数据识别。", meta: "新任务", tone: "gold" },
];

const DEMO_RECYCLE = [
    { title: "沙丘.旧版本.mkv", status: "可恢复", desc: "来源：入库覆盖 · 原路径 /movies/Dune/", meta: "18.4GB", tone: "red" },
    { title: "Sample.AD.trailer.mp4", status: "源清理", desc: "来源：源目录清理 · 判断为广告/样片。", meta: "840MB", tone: "gold" },
];

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

function showConfirm(title, message, onConfirm) {
    if (window.confirm(`${title}\n\n${message}`)) {
        if (typeof onConfirm === "function") onConfirm();
    }
}

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

function buildPermissionIssueDialog(issues, title = "权限不足") {
    const overlay = document.createElement("div");
    overlay.className = "perm-dialog-overlay";
    const body = (Array.isArray(issues) ? issues : []).map((item) => `
        <div class="perm-issue-item">
            <div class="perm-issue-field">字段: ${escapeHtml(item.field || "-")}</div>
            <div class="perm-issue-path">路径: ${escapeHtml(item.path || "-")}</div>
            ${item.rule_template ? `<div style="font-size:12px;color:#64748b;margin-top:2px;">所属规则模板: ${escapeHtml(item.rule_template)}</div>` : ""}
            <div style="margin-top:6px;color:#991b1b;">${escapeHtml(item.message || "")}</div>
            ${item.hint ? `<div class="perm-issue-hint">${escapeHtml(item.hint)}</div>` : ""}
        </div>
    `).join("");
    overlay.innerHTML = `
        <div class="perm-dialog">
            <div class="perm-dialog-header">⚠️ ${escapeHtml(title)}</div>
            <div class="perm-dialog-body">
                <div style="margin-bottom:12px;color:#475569;">请按下列提示完成授权或修正路径后，再重新保存或测试。</div>
                ${body}
            </div>
            <div class="perm-dialog-footer">
                <button class="btn btn-primary" type="button">我知道了</button>
            </div>
        </div>`;
    overlay.querySelector("button")?.addEventListener("click", () => overlay.remove());
    document.body.appendChild(overlay);
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

function buildSourceConfigPayload() {
    const sourceCleanerMode = document.querySelector('input[name="cfg-source_cleaner-cleanup_mode_inline"]:checked')?.value || "media_only";
    return {
        source_dir: normalizePathValue(document.getElementById("cfg-source-inline")?.value),
        source_policy: {
            scan_recursive: !!document.getElementById("cfg-source-recursive-toggle-inline")?.checked,
            scan_max_depth: Number(document.getElementById("cfg-source-depth-inline")?.value || 5) || 5,
        },
        source_cleaner: {
            enabled: !!document.getElementById("cfg-source-cleaner-enabled-inline")?.checked,
            cleanup_mode: sourceCleanerMode,
            ai_enabled: !!document.getElementById("cfg-source_cleaner-ai_enabled-inline")?.checked,
            merge_strategy: document.getElementById("cfg-source_cleaner-merge_strategy-inline")?.value || "intersection",
            delete_extensions: parseMultilineValue("cfg-source_cleaner-delete_extensions-inline"),
            protect_extensions: parseMultilineValue("cfg-source_cleaner-protect_extensions-inline"),
            blacklist_patterns: parseMultilineValue("cfg-source_cleaner-blacklist_patterns-inline"),
            junk_video_max_size_mb: Number(document.getElementById("cfg-source_cleaner-junk_video_max_size_mb-inline")?.value || 0) || 0,
            cleanup_empty_dirs: !!document.getElementById("cfg-source_cleaner-cleanup_empty_dirs-inline")?.checked,
            schedule: String(document.getElementById("cfg-source_cleaner-schedule-inline")?.value || "").trim(),
            ai_prompt: String(document.getElementById("cfg-source_cleaner-ai_prompt-inline")?.value || ""),
        },
    };
}

function buildTempConfigPayload() {
    return {
        temp_dir: normalizePathValue(document.getElementById("cfg-temp-inline")?.value),
    };
}

function buildRecycleConfigPayload() {
    return {
        source_policy: {
            recycle_dir: normalizePathValue(document.getElementById("cfg-recycle-inline")?.value),
            recycle_retention_days: Number(document.getElementById("cfg-recycle-retention-inline")?.value || 0) || 0,
        },
    };
}

function buildRulesConfigPayload() {
    return {
        path_rules: Array.isArray(currentConfigSnapshot?.path_rules) ? currentConfigSnapshot.path_rules : [],
        fallback_dir: normalizePathValue(document.getElementById("cfg-fallback-inline")?.value),
    };
}

function getProviderDefinition(providerType) {
    return currentProviderDefinitions.find((item) => item.type === providerType);
}

function inferProviderFieldValue(field, providerType) {
    const inputId = `cfg-provider-inline-${providerType}-${field.key}`;
    const element = document.getElementById(inputId);
    if (!element) return undefined;
    if (field.type === "checkbox") return !!element.checked;
    if (field.type === "number") return Number(element.value || field.default || 0) || 0;
    const raw = String(element.value || "");
    return raw;
}

function buildSingleProviderConfig(providerType) {
    const definition = getProviderDefinition(providerType);
    const existingProviders = Array.isArray(currentConfigSnapshot?.metadata?.providers) ? currentConfigSnapshot.metadata.providers : [];
    const existing = existingProviders.find((item) => item.type === providerType) || {};
    const config = {
        ...existing,
        type: providerType,
        enabled: !!document.querySelector(`[data-provider-toggle="${providerType}"]`)?.checked,
    };
    const fields = Array.isArray(definition?.config_schema?.fields) ? definition.config_schema.fields : [];
    fields.forEach((field) => {
        const value = inferProviderFieldValue(field, providerType);
        if (value === undefined) return;
        if (field.key === "api_key") {
            if (!value) {
                if (existing.api_key) config.api_key = existing.api_key;
                else config.api_key = "***";
                return;
            }
        }
        config[field.key] = value;
    });
    return config;
}

function buildAllProvidersPayload() {
    const existingProviders = Array.isArray(currentConfigSnapshot?.metadata?.providers) ? currentConfigSnapshot.metadata.providers : [];
    const providerTypes = Array.from(new Set([
        ...currentProviderDefinitions.map((item) => item.type),
        ...existingProviders.map((item) => item.type).filter(Boolean),
    ]));
    const providers = providerTypes.map((providerType) => buildSingleProviderConfig(providerType));
    return { metadata: { providers } };
}

function buildProvidersPayloadFor(providerType) {
    const existingProviders = Array.isArray(currentConfigSnapshot?.metadata?.providers) ? currentConfigSnapshot.metadata.providers : [];
    const nextProvider = buildSingleProviderConfig(providerType);
    const merged = [];
    let replaced = false;
    existingProviders.forEach((provider) => {
        if (provider.type === providerType) {
            merged.push(nextProvider);
            replaced = true;
        } else {
            merged.push(provider);
        }
    });
    if (!replaced) merged.push(nextProvider);
    return { metadata: { providers: merged } };
}

function buildLlmConfigPayload() {
    const currentLlm = currentConfigSnapshot?.llm || {};
    const apiKeyValue = String(document.getElementById("cfg-llm_api_key-inline")?.value || "").trim();
    return {
        llm: {
            provider: document.getElementById("cfg-llm_provider-inline")?.value || "openai",
            api_key: apiKeyValue || currentLlm.api_key || "***",
            base_url: String(document.getElementById("cfg-llm_base_url-inline")?.value || "").trim(),
            model: String(document.getElementById("cfg-llm_model-inline")?.value || "").trim(),
            fallback_model: String(document.getElementById("cfg-llm_fallback_model-inline")?.value || "").trim(),
            fast_model: String(document.getElementById("cfg-llm_fast_model-inline")?.value || "").trim(),
            timeout: Number(document.getElementById("cfg-llm_timeout-inline")?.value || 30) || 30,
            max_retries: Number(document.getElementById("cfg-llm_max_retries-inline")?.value || 2) || 2,
            retry_delay: Number(document.getElementById("cfg-llm_retry_delay-inline")?.value || 3) || 3,
            confidence_threshold: Number(document.getElementById("cfg-llm_confidence_threshold-inline")?.value || 0.8) || 0.8,
            verify_ssl: !!document.getElementById("cfg-llm_verify_ssl-inline")?.checked,
        },
    };
}

async function saveConfigPayload(payload, successText) {
    const result = await requestApi("POST", "/config", payload);
    showToast(result.message || successText || "配置已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
    return result;
}

async function saveSourceConfig() {
    const payload = buildSourceConfigPayload();
    const paths = currentPathSnapshot();
    if (!payload.source_dir) {
        showToast("源目录路径为必填项");
        return;
    }
    const conflicts = validateDirectoryConflicts(paths);
    if (conflicts.length) {
        showToast(conflicts.join("；"));
        return;
    }
    await saveConfigPayload(payload, "源目录配置已保存");
}

async function saveTempConfig() {
    const payload = buildTempConfigPayload();
    const paths = currentPathSnapshot();
    if (!payload.temp_dir) {
        showToast("中转目录路径为必填项");
        return;
    }
    const conflicts = validateDirectoryConflicts(paths);
    if (conflicts.length) {
        showToast(conflicts.join("；"));
        return;
    }
    await saveConfigPayload(payload, "中转目录配置已保存");
}

async function saveRecycleConfig() {
    const payload = buildRecycleConfigPayload();
    const paths = currentPathSnapshot();
    if (!payload.source_policy.recycle_dir) {
        showToast("回收目录路径为必填项");
        return;
    }
    const conflicts = validateDirectoryConflicts(paths);
    if (conflicts.length) {
        showToast(conflicts.join("；"));
        return;
    }
    await saveConfigPayload(payload, "回收目录配置已保存");
}

async function saveRulesConfig() {
    const payload = buildRulesConfigPayload();
    if (!Array.isArray(payload.path_rules) || payload.path_rules.length === 0) {
        showToast("当前还没有可保存的入库规则，请先在旧版配置中维护规则内容");
        return;
    }
    await saveConfigPayload(payload, "入库规则配置已保存");
}

async function saveProvidersConfig(providerType = "") {
    const payload = providerType ? buildProvidersPayloadFor(providerType) : buildAllProvidersPayload();
    const result = await requestApi("POST", "/config/section", {
        section: "metadata.providers",
        data: payload,
    });
    showToast(result.message || "Provider 配置已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
}

async function saveLlmConfig() {
    const payload = buildLlmConfigPayload();
    if (!payload.llm.base_url) {
        showToast("接口地址为必填项");
        return;
    }
    if (!payload.llm.model) {
        showToast("主要模型ID为必填项");
        return;
    }
    const result = await requestApi("POST", "/config/section", {
        section: "llm",
        data: payload,
    });
    showToast(result.message || "AI 配置已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
}

async function testConfigPath(kind) {
    const paths = currentPathSnapshot();
    const mapping = {
        source: {
            label: "源目录",
            path: paths.source_dir,
            need_write: !!document.getElementById("cfg-source-cleaner-enabled-inline")?.checked,
        },
        temp: { label: "中转目录", path: paths.temp_dir, need_write: true },
        recycle: { label: "回收目录", path: paths.recycle_dir, need_write: true },
        fallback: { label: "兜底入库目录", path: paths.fallback_dir, need_write: true },
    };
    const target = mapping[kind];
    if (!target) return;
    if (!target.path) {
        showToast(`${target.label} 还未填写`);
        return;
    }
    showToast(`正在测试 ${target.label} 权限...`);
    const result = await requestApi("POST", "/path/test", {
        path: target.path,
        need_write: target.need_write,
    });
    showPathTestFeedback(result, target.label);
}

async function testAllRulePermissions() {
    const pathRules = Array.isArray(currentConfigSnapshot?.path_rules) ? currentConfigSnapshot.path_rules : [];
    if (pathRules.length === 0) {
        showToast("当前还没有可测试的入库规则");
        return;
    }
    showToast("正在检查全部入库规则目录权限...");
    const result = await requestApi("POST", "/config/check-permission", {
        source_dir: "",
        temp_dir: "",
        log_dir: "",
        path_rules: pathRules,
    });
    if (result.code !== 200 || !result.data) {
        showToast(result.message || "入库规则目录权限检查失败");
        return;
    }
    if (Array.isArray(result.data.issues) && result.data.issues.length > 0) {
        buildPermissionIssueDialog(result.data.issues, "入库规则目录权限不足");
        return;
    }
    showToast("所有入库规则目录权限正常");
}

async function testProviderConnection(providerType) {
    showToast("正在测试 Provider 连通性...");
    const result = await requestApi("POST", `/providers/${encodeURIComponent(providerType)}/test`, {});
    const data = result.data || {};
    showToast(data.message || result.message || "Provider 测试已完成");
}

async function previewProvider(providerType) {
    const query = window.prompt("输入一个影视名称，用于快速预览当前 Provider 的搜索与详情能力");
    if (!query) return;
    const mediaType = /S\d{1,2}E\d{1,2}|第\d+季|第\d+集/i.test(query) ? "tv" : "movie";
    showToast("正在生成 Provider 预览...");
    const result = await requestApi("POST", `/providers/${encodeURIComponent(providerType)}/preview`, {
        query,
        type: mediaType,
    });
    if (result.code !== 200 || !result.data) {
        showToast(result.message || "Provider 预览失败");
        return;
    }
    if (!result.data.found) {
        showToast(result.data.message || "未找到匹配结果");
        return;
    }
    const preview = result.data;
    const lines = [
        `标题：${preview.title || "-"}`,
        `原标题：${preview.original_title || "-"}`,
        `年份：${preview.year || "-"}`,
        `类型：${preview.type || "-"}`,
        `评分：${preview.vote_average ?? "-"}`,
        "",
        `${preview.overview || "暂无简介"}`,
    ];
    window.alert(lines.join("\n"));
}

async function testLlmConnection() {
    const payload = buildLlmConfigPayload().llm;
    if (!payload.base_url) {
        showToast("请先填写接口地址");
        return;
    }
    if (!payload.model) {
        showToast("请先填写主要模型ID");
        return;
    }
    showToast("正在测试 LLM 连通性...");
    const result = await requestApi("POST", "/config/test-llm", {
        provider: payload.provider,
        api_key: payload.api_key,
        base_url: payload.base_url,
        model: payload.model,
    });
    const data = result.data || {};
    showToast(data.message || result.message || "LLM 测试已完成");
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

function setDashboardQueueStrip(text, ratio = 0.12) {
    const title = document.getElementById("current-job");
    const progress = document.querySelector(".now-strip .progress span");
    if (title) title.textContent = text;
    if (progress) progress.style.width = `${Math.max(6, Math.min(100, Math.round(ratio * 100)))}%`;
}

function getTaskStatusText(status) {
    const map = {
        PENDING: "待处理",
        PROCESSING: "处理中",
        CONFIRMING: "待确认",
        NEEDS_REVIEW: "待确认",
        FAILED: "失败",
        SUCCESS: "已完成",
        SKIPPED: "已跳过",
    };
    return map[String(status || "").toUpperCase()] || "未知状态";
}

function getTaskTone(task) {
    const status = String(task.status || "").toUpperCase();
    if (status === "FAILED") return "red";
    if (status === "CONFIRMING" || status === "NEEDS_REVIEW") return "cyan";
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
    const scrape = task.scrape_result || {};
    if (task.error_message) return task.error_message;
    if (task.skip_reason) return task.skip_reason;
    if (status === "CONFIRMING" || status === "NEEDS_REVIEW") {
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
    if (status === "PROCESSING") {
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
    if (status === "CONFIRMING" || status === "NEEDS_REVIEW") return { key: "confirm", label: "去确认" };
    if (status === "FAILED" || status === "SKIPPED") return { key: "retry-task", label: "去重试" };
    if (status === "SUCCESS") return { key: "view-task", label: "查看结果" };
    return { key: "view-task", label: "查看" };
}

function taskSecondaryAction(task) {
    const status = String(task.status || "").toUpperCase();
    if (status === "CONFIRMING" || status === "NEEDS_REVIEW") return { key: "ignore-task", label: "忽略" };
    if (status === "FAILED") return { key: "delete-task", label: "移入回收" };
    if (status === "PENDING" || status === "PROCESSING") return { key: "delete-task", label: "移入回收" };
    return { key: "view-task", label: "查看详情" };
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

async function loadHtmlPartial(targetId, url) {
    const host = document.getElementById(targetId);
    if (!host) return;
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`加载片段失败: ${url}`);
    host.innerHTML = await response.text();
}

async function runAction(action, trigger) {
    const endpointByAction = { scan: "/run", pause: "/queue/pause", retry: "/queue/retry-all" };
    if (!endpointByAction[action]) {
        showToast("该操作将在后续接线完成后开放");
        return;
    }
    if (trigger) trigger.disabled = true;
    const result = await requestApi("POST", endpointByAction[action]);
    if (trigger) trigger.disabled = false;
    showToast(result.message || "请求已发送");
    if (result.code === 200 || result.code === 202) {
        await loadDashboardOverview();
    }
}

function renderTaskCard(item) {
    const danger = String(item.status || "").includes("失败") || String(item.status || "").includes("确认") ? " danger" : "";
    const primaryAction = taskPrimaryAction(item);
    const secondaryAction = taskSecondaryAction(item);
    const title = taskDisplayTitle(item);
    const filename = taskFileName(item);
    return `
        <article class="task-card">
            <div class="cover cover-${getTaskTone(item)}"></div>
            <div class="task-body">
                <div class="task-top"><h3>${escapeHtml(title)}</h3><span class="badge${danger}">${escapeHtml(getTaskStatusText(item.status))}</span></div>
                <p>${escapeHtml(taskDescription(item))}</p>
                <div class="task-meta"><span>${escapeHtml(filename)}</span><span>${escapeHtml(taskMeta(item))}</span></div>
            </div>
            <div class="task-actions">
                <button data-task-action="${escapeHtml(primaryAction.key)}" data-task-id="${escapeHtml(item.task_id || "")}">${escapeHtml(primaryAction.label)}</button>
                <button data-task-action="${escapeHtml(secondaryAction.key)}" data-task-id="${escapeHtml(item.task_id || "")}">${escapeHtml(secondaryAction.label)}</button>
            </div>
        </article>`;
}

function renderRecycleCard(item) {
    const status = item.restorable ? "可恢复" : "待清理";
    const primaryAction = item.restorable
        ? { key: "restore-recycle", label: "立即恢复" }
        : { key: "view-recycle", label: "查看原因" };
    const secondaryAction = item.restorable
        ? { key: "view-recycle", label: "查看来源" }
        : { key: "delete-recycle", label: "去清理" };
    const title = item.original_path
        ? String(item.original_path).split("/").pop().split("\\").pop()
        : (item.recycle_path ? String(item.recycle_path).split("/").pop().split("\\").pop() : "回收文件");
    const description = item.restorable
        ? `来源：${item.partition || item.zone_name || "回收站"} · ${item.reason || "等待恢复"}`
        : `来源：${item.partition || item.zone_name || "回收站"} · ${item.reason || "需要人工处理"}`;
    const meta = `${formatFileSizeMb(item.file_size_mb || (Number(item.size || 0) / 1024 / 1024))} · ${formatActivityTime(item.moved_at)}`;
    return `
        <article class="task-card">
            <div class="cover cover-${item.restorable ? "gold" : "red"}"></div>
            <div class="task-body">
                <div class="task-top"><h3>${escapeHtml(title)}</h3><span class="badge">${escapeHtml(status)}</span></div>
                <p>${escapeHtml(description)}</p>
                <div class="task-meta"><span>${escapeHtml(item.original_path || item.recycle_path || "回收站")}</span><span>${escapeHtml(meta)}</span></div>
            </div>
            <div class="task-actions">
                <button data-recycle-action="${escapeHtml(primaryAction.key)}" data-recycle-id="${escapeHtml(item.id || item.recycle_path || "")}">${escapeHtml(primaryAction.label)}</button>
                <button data-recycle-action="${escapeHtml(secondaryAction.key)}" data-recycle-id="${escapeHtml(item.id || item.recycle_path || "")}">${escapeHtml(secondaryAction.label)}</button>
            </div>
        </article>`;
}

function renderTaskList() {
    const meta = TASK_FILTER_META[currentTaskFilter] || TASK_FILTER_META.all;
    document.getElementById("task-panel-title").textContent = meta.title;
    document.getElementById("task-panel-copy").textContent = meta.copy;
    const host = document.getElementById("task-list");
    if (!host) return;
    if (!Array.isArray(currentTaskRecords) || currentTaskRecords.length === 0) {
        host.innerHTML = `
            <article class="task-card">
                <div class="cover cover-gold"></div>
                <div class="task-body">
                    <div class="task-top"><h3>当前筛选下还没有任务</h3><span class="badge">空队列</span></div>
                    <p>你可以先回到首页发起扫描，或切换其他状态筛选查看已经入队的条目。</p>
                    <div class="task-meta"><span>任务工作台</span><span>等待新任务</span></div>
                </div>
                <div class="task-actions">
                    <button data-nav="home" data-view-target="dashboard">回到首页</button>
                    <button data-task-action="refresh-tasks">重新加载</button>
                </div>
            </article>`;
        document.getElementById("task-panel-count").textContent = "0 项";
        return;
    }
    host.innerHTML = currentTaskRecords.map(renderTaskCard).join("");
    document.getElementById("task-panel-count").textContent = `${currentTaskRecords.length} 项`;
}

function renderStaticLists() {
    renderTaskList();
    currentRecycleRecords = DEMO_RECYCLE;
    renderRecycleList();
}

function setTaskFilter(filter) {
    currentTaskFilter = filter;
    document.querySelectorAll("[data-task-filter-chip]").forEach((chip) => {
        chip.classList.toggle("active", chip.dataset.taskFilterChip === filter);
    });
    loadTaskList();
}

async function listTasksByStatuses(statuses) {
    const normalized = Array.isArray(statuses) ? statuses : [];
    if (normalized.length === 0) {
        const result = await requestApi("GET", "/tasks?limit=20");
        if (result.code !== 200 || !result.data) return { code: result.code, message: result.message, tasks: [] };
        return { code: 200, tasks: result.data.tasks || [], total: result.data.total || 0 };
    }
    const responses = await Promise.all(
        normalized.map((status) => requestApi("GET", `/tasks?limit=20&status=${encodeURIComponent(status)}`)),
    );
    const failed = responses.find((result) => result.code !== 200 || !result.data);
    if (failed) return { code: failed.code, message: failed.message, tasks: [] };
    const tasks = responses.flatMap((result) => result.data.tasks || []);
    tasks.sort((a, b) => {
        const ta = a.completed_at || a.started_at || a.created_at || "";
        const tb = b.completed_at || b.started_at || b.created_at || "";
        return tb.localeCompare(ta);
    });
    const unique = [];
    const seen = new Set();
    tasks.forEach((task) => {
        if (seen.has(task.task_id)) return;
        seen.add(task.task_id);
        unique.push(task);
    });
    return {
        code: 200,
        tasks: unique,
        total: responses.reduce((sum, result) => sum + Number(result.data.total || 0), 0),
    };
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
    const result = await listTasksByStatuses(TASK_FILTER_STATUS_MAP[currentTaskFilter]);
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
        window.alert(renderTaskSummary(task));
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
    }
}

function renderRecycleList() {
    const host = document.getElementById("recycle-list");
    if (!host) return;
    if (!Array.isArray(currentRecycleRecords) || currentRecycleRecords.length === 0) {
        host.innerHTML = `
            <article class="task-card">
                <div class="cover cover-gold"></div>
                <div class="task-body">
                    <div class="task-top"><h3>当前回收站还是空的</h3><span class="badge">空</span></div>
                    <p>危险操作进入回收流程后，这里会显示可恢复文件和待清理项目。</p>
                    <div class="task-meta"><span>安全回收区</span></div>
                </div>
                <div class="task-actions">
                    <button data-recycle-action="refresh-recycle">重新加载</button>
                </div>
            </article>`;
        return;
    }
    host.innerHTML = currentRecycleRecords.map(renderRecycleCard).join("");
}

async function loadRecycleData() {
    const host = document.getElementById("recycle-list");
    if (host) {
        host.innerHTML = `
            <article class="task-card">
                <div class="cover cover-gold"></div>
                <div class="task-body">
                    <div class="task-top"><h3>正在读取回收站</h3><span class="badge">加载中</span></div>
                    <p>正在把真实回收列表同步到新版安全回收区。</p>
                    <div class="task-meta"><span>安全回收区</span></div>
                </div>
            </article>`;
    }
    const result = await requestApi("GET", "/recycle/list?limit=20");
    if (result.code === 401) {
        currentRecycleRecords = [];
        if (host) {
            host.innerHTML = `
                <article class="task-card">
                    <div class="cover cover-cyan"></div>
                    <div class="task-body">
                        <div class="task-top"><h3>需要先完成认证</h3><span class="badge danger">未认证</span></div>
                        <p>输入 API Key 后，这里才会显示真实回收文件、恢复入口和清理动作。</p>
                        <div class="task-meta"><span>安全回收区</span></div>
                    </div>
                </article>`;
        }
        document.getElementById("recycle-recoverable-count").textContent = "--";
        document.getElementById("recycle-cleanup-count").textContent = "--";
        document.getElementById("recycle-size").textContent = "--";
        return;
    }
    if (result.code !== 200 || !result.data) {
        currentRecycleRecords = [];
        if (host) {
            host.innerHTML = `
                <article class="task-card">
                    <div class="cover cover-red"></div>
                    <div class="task-body">
                        <div class="task-top"><h3>回收站加载失败</h3><span class="badge danger">失败</span></div>
                        <p>${escapeHtml(result.message || "请稍后重试。")}</p>
                        <div class="task-meta"><span>安全回收区</span></div>
                    </div>
                    <div class="task-actions">
                        <button data-recycle-action="refresh-recycle">重新加载</button>
                    </div>
                </article>`;
        }
        return;
    }
    currentRecycleRecords = result.data.items || [];
    document.getElementById("recycle-recoverable-count").textContent = String(currentRecycleRecords.filter((item) => item.restorable).length);
    document.getElementById("recycle-cleanup-count").textContent = String(currentRecycleRecords.filter((item) => !item.restorable).length);
    document.getElementById("recycle-size").textContent = formatFileSizeMb(result.data.total_size_mb || (Number(result.data.total_size || 0) / 1024 / 1024));
    renderRecycleList();
}

function findRecycleRecord(id) {
    return currentRecycleRecords.find((item) => (item.id || item.recycle_path) === id);
}

async function performRecycleAction(action, recycleId) {
    if (action === "refresh-recycle") {
        await loadRecycleData();
        return;
    }
    const item = findRecycleRecord(recycleId);
    if (!item) {
        showToast("当前回收记录已过期，请重新加载");
        return;
    }
    if (action === "view-recycle") {
        const summary = [
            `原路径：${item.original_path || "-"}`,
            `回收位置：${item.recycle_path || "-"}`,
            `来源分区：${item.partition || item.zone_name || "-"}`,
            `原因：${item.reason || "-"}`,
            `移动时间：${item.moved_at || "-"}`,
        ].join("\n");
        window.alert(summary);
        return;
    }
    if (action === "restore-recycle") {
        showConfirm("恢复文件", `确定恢复「${item.original_path || item.recycle_path || "回收文件"}」吗？`, async () => {
            const result = await requestApi("POST", "/recycle/restore", {
                items: [item.recycle_path || recycleId],
                conflict_mode: "skip",
            });
            showToast(result.message || "恢复请求已发送");
            if (result.code === 200 || result.code === 207) {
                await loadRecycleData();
            }
        });
        return;
    }
    if (action === "delete-recycle") {
        showConfirm("清理回收项", `确定永久清理「${item.original_path || item.recycle_path || "回收文件"}」吗？`, async () => {
            const result = await requestApi("POST", "/recycle/delete", {
                items: [item.recycle_path || recycleId],
            });
            showToast(result.message || "清理请求已发送");
            if (result.code === 200 || result.code === 207) {
                await loadRecycleData();
            }
        });
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

function buildProviderField(providerType, field, rawValue) {
    const value = rawValue ?? field.default ?? "";
    const id = `cfg-provider-inline-${providerType}-${field.key}`;
    const hint = field.description || field.help_text || field.placeholder || "";
    if (field.type === "select") {
        const options = (field.options || []).map((option) => {
            const selected = option.value === value ? " selected" : "";
            return `<option value="${escapeHtml(option.value)}"${selected}>${escapeHtml(option.label)}</option>`;
        }).join("");
        return `
            <label class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <select id="${id}">${options}</select>
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </label>`;
    }
    if (field.type === "number") {
        return `
            <label class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <input id="${id}" type="number" value="${escapeHtml(value)}" />
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </label>`;
    }
    if (field.type === "password") {
        const placeholder = field.key === "api_key" && value === "***" ? "已保存，留空保持不变" : (field.placeholder || field.label || "");
        const val = value === "***" ? "" : value;
        return `
            <label class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <input id="${id}" type="password" value="${escapeHtml(val)}" placeholder="${escapeHtml(placeholder)}" />
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </label>`;
    }
    if (field.type === "checkbox") {
        return `
            <article class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <label class="toggle-row-inline">
                    <input id="${id}" type="checkbox"${value ? " checked" : ""} />
                    <b>${escapeHtml(field.checkbox_label || "启用")}</b>
                </label>
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </article>`;
    }
    return `
        <label class="form-card">
            <span>${escapeHtml(field.label || field.key)}</span>
            <input id="${id}" type="text" value="${escapeHtml(value)}" placeholder="${escapeHtml(field.placeholder || "")}" />
            ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
        </label>`;
}

function renderInlineProviderConfigs(providerDefs, savedProviders) {
    const host = document.getElementById("provider-inline-stack");
    if (!host) return;
    if (!Array.isArray(providerDefs) || providerDefs.length === 0) {
        host.innerHTML = '<article class="provider-inline-empty">当前没有可用的 Provider</article>';
        return;
    }
    currentProviderDefinitions = providerDefs;
    host.innerHTML = providerDefs.map((provider) => {
        const savedConfig = (savedProviders || []).find((item) => item.type === provider.type) || {};
        const enabled = savedConfig.enabled !== false && provider.enabled !== false;
        const mergedConfig = { ...(provider.config || {}), ...(savedConfig || {}) };
        const fields = ((provider.config_schema || {}).fields || []).map((field) => buildProviderField(provider.type, field, mergedConfig[field.key])).join("");
        return `
            <article class="provider-inline-card${enabled ? "" : " is-disabled"}" data-provider-card="${escapeHtml(provider.type)}">
                <div class="provider-inline-head">
                    <div>
                        <strong>${escapeHtml(provider.display_name || provider.type)}</strong>
                        <p>${escapeHtml(provider.description || "配置元数据源地址、凭据和连接参数。")}</p>
                    </div>
                    <label class="toggle-pill">
                        <input type="checkbox"${enabled ? " checked" : ""} data-provider-toggle="${escapeHtml(provider.type)}" />
                        <span class="toggle-pill-ui"></span>
                    </label>
                </div>
                <div class="provider-inline-grid">
                    ${fields || '<article class="provider-inline-empty">该 Provider 暂无可配置字段</article>'}
                </div>
                <div class="provider-inline-actions">
                    <button class="btn btn-primary btn-sm" type="button" data-provider-action="save" data-provider-type="${escapeHtml(provider.type)}">保存当前 Provider</button>
                    <button class="btn btn-secondary btn-sm" type="button" data-provider-action="test" data-provider-type="${escapeHtml(provider.type)}">测试连接</button>
                    <button class="btn btn-secondary btn-sm" type="button" data-provider-action="preview" data-provider-type="${escapeHtml(provider.type)}">刮削预览</button>
                </div>
            </article>`;
    }).join("");
}

async function loadInlineProviderConfigs(metadata) {
    const host = document.getElementById("provider-inline-stack");
    if (!host) return;
    host.innerHTML = '<article class="provider-inline-empty">正在加载 Provider 配置...</article>';
    try {
        const result = await requestApi("GET", "/providers");
        if (result.code !== 200 || !result.data || !Array.isArray(result.data.providers)) {
            host.innerHTML = '<article class="provider-inline-empty">Provider 配置加载失败</article>';
            return;
        }
        renderInlineProviderConfigs(result.data.providers, metadata.providers || []);
    } catch (error) {
        host.innerHTML = '<article class="provider-inline-empty">Provider 配置加载失败</article>';
    }
}

function renderRuleList(pathRules) {
    const list = document.getElementById("rules-inline-list");
    if (!list) return;
    if (!Array.isArray(pathRules) || pathRules.length === 0) {
        list.innerHTML = '<button class="rule-inline-empty rule-inline-add" data-action="placeholder">+</button>';
        return;
    }
    list.innerHTML = pathRules.map((rule, index) => {
        const template = rule.template || "未设置模板";
        const conditions = Object.entries(rule.conditions || {});
        const conditionText = conditions.length
            ? conditions.map(([key, value]) => `${key}=${Array.isArray(value) ? value.join("/") : value}`).join(" · ")
            : "无条件，作为通用规则";
        return `
            <article class="rule-inline-item">
                <div>
                    <strong>规则 ${index + 1}</strong>
                    <small>${template}</small>
                    <p>${conditionText}</p>
                </div>
                <div class="rule-inline-meta">
                    <b>${conditions.length} 个条件</b>
                    <span>命中即止</span>
                </div>
            </article>`;
    }).join("");
}

function renderDimensionVarList(dimensions) {
    const container = document.getElementById("rules-dimension-vars");
    if (!container) return;
    if (!Array.isArray(dimensions) || dimensions.length === 0) {
        container.innerHTML = '<div class="rule-inline-empty">暂无启用的维度变量</div>';
        return;
    }
    container.innerHTML = dimensions.map((dim) => {
        const label = dim.label || dim.display_name || dim.name || "未命名维度";
        const options = Array.isArray(dim.options) ? dim.options : [];
        const valuesHint = options
            .filter((item) => item && item.value !== "")
            .map((item) => item.label || item.value)
            .join(" / ");
        return `<div class="var-token-line"><code>{dimension.${dim.name}}</code><span>${label}${valuesHint ? `（${valuesHint}）` : ""}</span></div>`;
    }).join("");
}

async function loadDimensionVars() {
    const result = await requestApi("GET", "/dimensions/enabled");
    if (result.code !== 200 || !result.data) {
        renderDimensionVarList([]);
        return;
    }
    renderDimensionVarList(result.data.dimensions || []);
}

function toggleVarGroup(group) {
    const button = document.querySelector(`[data-var-group="${group}"]`);
    const panel = document.querySelector(`[data-var-panel="${group}"]`);
    if (!button || !panel) return;
    const next = !button.classList.contains("active");
    button.classList.toggle("active", next);
    panel.classList.toggle("active", next);
}

function updateConfigStageStatus(config, paths, pathRules) {
    const hasSource = Boolean(paths.source_dir);
    const hasTemp = Boolean(paths.temp_dir);
    const hasRecycle = Boolean(paths.recycle_dir);
    const hasRules = Array.isArray(pathRules) && pathRules.length > 0;
    const metadata = config.metadata || {};
    const llm = config.llm || {};
    const hasScrape = Object.keys(metadata).length > 0;
    const hasAi = Boolean(llm.base_url || llm.model || llm.api_key);
    const states = [
        ["source", hasSource],
        ["temp", hasTemp],
        ["recycle", hasRecycle],
        ["rules", hasRules],
        ["scrape", hasScrape],
        ["ai", hasAi],
    ];
    states.forEach(([stage, valid]) => {
        const card = document.querySelector(`[data-config-stage="${stage}"]`);
        if (!card) return;
        card.dataset.state = valid ? "valid" : "invalid";
    });
}

async function loadDashboardMetrics() {
    const result = await requestApi("GET", "/metrics");
    if (result.code === 401) {
        setDashboardQueueStrip("请先完成 API Key 认证后查看当前队列", 0.08);
        return;
    }
    if (result.code !== 200 || !result.data) {
        setDashboardQueueStrip("暂时无法读取首页状态，请稍后重试", 0.08);
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
        setDashboardQueueStrip("请先完成 API Key 认证后查看当前队列", 0.08);
        return;
    }
    if (result.code !== 200 || !result.data) {
        setDashboardQueueStrip("暂时无法读取当前队列", 0.08);
        return;
    }
    const byStatus = result.data.by_status || {};
    const pending = statusCount(byStatus, "PENDING", "pending");
    const processing = statusCount(byStatus, "PROCESSING", "processing");
    const confirm = statusCount(byStatus, "CONFIRMING", "confirming", "NEEDS_REVIEW", "needs_review");
    const failed = statusCount(byStatus, "FAILED", "failed");
    const totalOpen = pending + processing + confirm + failed;
    if (result.data.paused) {
        setDashboardQueueStrip(`队列已暂停，仍有 ${totalOpen} 项待继续处理`, totalOpen > 0 ? 0.28 : 0.12);
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
    setDashboardQueueStrip("等待新影片进入队列", 0.08);
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
    currentConfigSnapshot = result.data;
    const metadata = result.data.metadata || {};
    const llm = result.data.llm || {};
    const sourcePolicy = result.data.source_policy || {};
    const sourceCleaner = result.data.source_cleaner || {};
    const paths = {
        source_dir: result.data.source_dir || "",
        temp_dir: result.data.temp_dir || "",
        recycle_dir: sourcePolicy.recycle_dir || sourcePolicy.quarantine_dir || "",
    };
    setFieldValue("cfg-source-inline", paths.source_dir);
    setFieldValue("cfg-temp-inline", paths.temp_dir);
    setFieldValue("cfg-recycle-inline", paths.recycle_dir);
    document.getElementById("cfg-source-recursive-toggle-inline").checked = (sourcePolicy.scan_recursive ?? true);
    setFieldValue("cfg-source-depth-inline", sourcePolicy.scan_max_depth || 5);
    setFieldValue("cfg-recycle-retention-inline", sourcePolicy.recycle_retention_days || 30);
    setFieldValue("cfg-fallback-inline", result.data.fallback_dir || "");
    setFieldValue("cfg-filename_templates-movie-inline", ((result.data.filename_templates || {}).movie) || "");
    setFieldValue("cfg-filename_templates-tv-inline", ((result.data.filename_templates || {}).tv) || "");
    setFieldValue("cfg-filename_templates-subtitle-inline", ((result.data.filename_templates || {}).subtitle) || "");
    setFieldValue("cfg-duplicate_handling-strategy-inline", ((result.data.duplicate_handling || {}).strategy) || "skip");
    setFieldValue("prompt-system", ((result.data.prompts || {}).system_prompt) || "");
    setFieldValue("cfg-server_api_key-inline", ((result.data.server || {}).api_key) || "");
    setFieldValue("cfg-server_port-inline", ((result.data.server || {}).port) || 9855);
    setFieldValue("cfg-log_dir-inline", result.data.log_dir || "");
    setFieldValue("cfg-resource_dir-inline", result.data.resource_dir || result.data.resources_dir || "");
    setFieldValue("cfg-task_queue-max_concurrent-inline", ((result.data.task_queue || {}).max_concurrent) || 1);
    setFieldValue("cfg-video_extensions-inline", (result.data.video_extensions || []).join("\n"));
    setFieldValue("cfg-subtitle_extensions-inline", (result.data.subtitle_extensions || []).join("\n"));
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
    document.getElementById("cfg-hermes_enabled-inline").checked = !!((result.data.hermes || {}).enabled);
    setFieldValue("cfg-hermes_webhook_base_url-inline", (((result.data.hermes || {}).webhook || {}).base_url) || "");
    setFieldValue("cfg-hermes_webhook_route_name-inline", (((result.data.hermes || {}).webhook || {}).route_name) || "");
    setFieldValue("cfg-hermes_webhook_secret-inline", (((result.data.hermes || {}).webhook || {}).secret) || "");
    setFieldValue("cfg-hermes_webhook_timeout-inline", (((result.data.hermes || {}).webhook || {}).timeout) || 30);
    setFieldValue("cfg-hermes_webhook_max_retries-inline", (((result.data.hermes || {}).webhook || {}).max_retries) || 3);
    setFieldValue("cfg-hermes_webhook_retry_delay-inline", (((result.data.hermes || {}).webhook || {}).retry_delay) || 5);
    const hermesEvents = (((result.data.hermes || {}).webhook || {}).events) || [];
    document.getElementById("cfg-hermes_webhook_verify_ssl-inline").checked = !!((((result.data.hermes || {}).webhook || {}).verify_ssl));
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
    renderRuleList(result.data.path_rules || []);
    updateConfigStageStatus(result.data, paths, result.data.path_rules || []);
    loadCinemaConfidenceConfig(result.data);
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
        if (event.target.closest("#btn-confidence-simulate")) simulateConfidenceDecision();
        const taskAction = event.target.closest("[data-task-action]");
        if (taskAction) {
            performTaskAction(taskAction.dataset.taskAction, taskAction.dataset.taskId || "");
            return;
        }
        const recycleAction = event.target.closest("[data-recycle-action]");
        if (recycleAction) {
            performRecycleAction(recycleAction.dataset.recycleAction, recycleAction.dataset.recycleId || "");
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
        const action = event.target.closest("[data-action]");
        if (action) runAction(action.dataset.action, action);
    });
    document.addEventListener("input", (event) => {
        if (event.target.closest('[data-section="confidence"] input[data-key]')) updateThresholdBar();
    });
    document.addEventListener("change", (event) => {
        const providerToggle = event.target.closest("[data-provider-toggle]");
        if (!providerToggle) return;
        const card = providerToggle.closest("[data-provider-card]");
        if (card) card.classList.toggle("is-disabled", !providerToggle.checked);
    });
    document.getElementById("cfg-source-cleaner-enabled-inline").addEventListener("change", toggleSourceCleanerUi);
    document.getElementById("cfg-source_cleaner-ai_enabled-inline").addEventListener("change", toggleSourceCleanerUi);
    document.getElementById("cfg-source-recursive-toggle-inline").addEventListener("change", toggleSourceDepthField);
    const hermesToggle = document.getElementById("cfg-hermes_enabled-inline");
    if (hermesToggle) hermesToggle.addEventListener("change", toggleHermesInlineFields);
    window.addEventListener("scroll", updateStickyHeroState, { passive: true });
    window.addEventListener("resize", updateStickyHeroState);
}

document.addEventListener("DOMContentLoaded", async () => {
    await loadHtmlPartial("advanced-pages-slot", "partials/advanced-pages.html");
    bindEvents();
    renderStaticLists();
    setTaskFilter("all");
    await loadTaskList();
    await loadRecycleData();
    setConfigStage("start");
    setCleanerTab("delete");
    updateStickyHeroState();
    loadDashboardOverview();
    startDashboardAutoRefresh();
    loadDirectoryConfig();
    if (typeof checkApiKeyRequired === "function") checkApiKeyRequired();
});

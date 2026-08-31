// cinema-app-state.js - global state and core utility functions
const DASHBOARD_REFRESH_MS = 15000;

const TASK_FILTER_META = {
  all: {
    title: "当前队列",
    copy: "先从待确认和失败项开始，会更快把主流程跑顺。",
  },
  queued: {
    title: "等待系统继续处理",
    copy: "这些文件已经进入队列，下一步会开始扫描、识别和判断。",
  },
  running: {
    title: "系统正在处理中",
    copy: "系统正在处理这批文件，目前不需要你操作。",
  },
  review: {
    title: "等待你来确认",
    copy: "先处理这些不确定条目，能最快减少后续误判和卡住的任务。",
  },
  failed: {
    title: "等待重试或排错",
    copy: "先看失败原因，再决定重试、调整配置或手动处理。",
  },
  success: {
    title: "今天已完成的入库",
    copy: "这里是已经跑通的结果，可以快速回看最终入库状态。",
  },
  cancelled: {
    title: "已取消的任务",
    copy: "这些任务已被主动取消，可按需要重新投入处理。",
  },
};

const TASK_FILTER_PARAMS = {
  all: {},
  queued: { status: "PENDING", stage: "QUEUED" },
  running: { status: "PENDING", stage: "RUNNING" },
  review: { status: "PENDING", stage: "AWAIT_REVIEW" },
  failed: { status: "FAILED" },
  success: { status: ["SUCCESS", "SKIPPED"] },
  cancelled: { status: "CANCELLED" },
};

let currentTaskFilter = "all";
let currentConfigStage = "source";
let currentConfigSnapshot = null;
let currentConfigRevision = "";
let currentCleanerTab = "delete";
let dashboardRefreshTimer = null;
let currentTaskRecords = [];
let currentTaskTotal = 0;
let currentTaskPage = 1;
let currentTaskPageSize = 20;
let currentTaskHasMore = false;
let currentTaskLoading = false;
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
  "system-settings",
]);

function setView(view, navKey = view) {
  document.querySelectorAll(".page-view").forEach((page) => {
    const isActive = page.dataset.view === view;
    if (isActive && !page.classList.contains("active")) {
      // Force re-trigger fade-in animation by removing class, forcing reflow, then adding
      page.style.animation = "none";
      page.offsetHeight; // force reflow
      page.style.animation = "";
    }
    page.classList.toggle("active", isActive);
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

async function requestApi(method, endpoint, body = null, options = {}) {
  if (typeof apiRequest === "function") {
    return apiRequest(method, endpoint, body, options);
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
  buildPermissionIssueDialog(
    [
      {
        field: label,
        path: result.data.path,
        message: result.data.message,
        hint: result.data.hint,
      },
    ],
    `${label} 权限不足`,
  );
}

function currentPathSnapshot() {
  return {
    source_dir: normalizePathValue(
      document.getElementById("cfg-source-inline")?.value || currentConfigSnapshot?.source_dir,
    ),
    temp_dir: normalizePathValue(
      document.getElementById("cfg-temp-inline")?.value || currentConfigSnapshot?.temp_dir,
    ),
    recycle_dir: normalizePathValue(
      document.getElementById("cfg-recycle-inline")?.value || currentConfigSnapshot?.source_policy?.recycle_dir,
    ),
    library_root: normalizePathValue(
      libraryRootById(defaultLibraryRootId())?.path || "",
    ),
    fallback_dir: normalizePathValue(
      document.getElementById("cfg-fallback-inline")?.value,
    ),
  };
}

function validateDirectoryConflicts(paths) {
  const conflicts = [];
  if (paths.source_dir && paths.temp_dir && paths.source_dir === paths.temp_dir)
    conflicts.push("源目录与中转目录不能相同");
  if (
    paths.source_dir &&
    paths.recycle_dir &&
    paths.source_dir === paths.recycle_dir
  )
    conflicts.push("源目录与回收目录不能相同");
  if (
    paths.temp_dir &&
    paths.recycle_dir &&
    paths.temp_dir === paths.recycle_dir
  )
    conflicts.push("中转目录与回收目录不能相同");
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
  if (normalized === "ERROR" || normalized === "DANGER") return "alert";
  if (normalized === "WARNING" || normalized === "WARN" || normalized === "RUNNING") return "clock";
  return "check";
}

function activityTone(level) {
  const normalized = String(level || "").toUpperCase();
  if (normalized === "ERROR" || normalized === "DANGER") return " danger";
  if (normalized === "WARNING" || normalized === "WARN") return " warning";
  if (normalized === "RUNNING") return " running";
  if (normalized === "MUTED" || normalized === "QUEUED") return " muted";
  return "";
}

function renderActivityRows(items) {
  const host = document.getElementById("activity-list");
  if (!host) return;
  if (!Array.isArray(items) || items.length === 0) {
    host.innerHTML =
      '<div class="activity-row"><div class="state"><svg class="icon icon-sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-clock"></use></svg></div><div><b>当前还没有新的活动记录</b><small>系统启动后，这里会滚动显示扫描、识别和入库过程。</small></div><span class="time">刚刚</span></div>';
    return;
  }
  host.innerHTML = items.slice(0, 5)
    .map(
      (item) => `
        <div class="activity-row">
            <div class="state${activityTone(item.level)}"><svg class="icon icon-sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-${activityIcon(item.level)}"></use></svg></div>
            <div><b>${escapeHtml(item.title || "最新活动")}</b><small>${escapeHtml(item.copy || "")}</small></div>
            <span class="time">${escapeHtml(formatActivityTime(item.timestamp))}</span>
        </div>
    `,
    )
    .join("");
}

function setDashboardQueueStrip(text, options = {}) {
  const title = document.getElementById("current-job");
  const detail = document.getElementById("current-job-detail");
  const strip = document.getElementById("dashboard-state-strip");
  const progressWrap = document.getElementById("dashboard-progress");
  const progress = document.querySelector(".now-strip .progress span");
  const action = document.getElementById("dashboard-state-action");
  const percent = Number.isFinite(options.progress) ? Math.max(0, Math.min(100, Math.round(options.progress))) : null;
  if (title) title.textContent = text;
  if (detail) detail.textContent = options.detail || "";
  if (strip) strip.dataset.state = options.state || "idle";
  if (progressWrap) {
    progressWrap.hidden = percent === null;
    progressWrap.setAttribute("aria-valuenow", String(percent || 0));
  }
  if (progress) {
    progress.style.width = percent === null ? "0%" : `${percent}%`;
  }
  if (action) {
    action.hidden = !options.actionLabel;
    action.textContent = options.actionLabel || "去处理";
    if (options.filter) action.dataset.taskFilter = options.filter;
    else delete action.dataset.taskFilter;
  }
}

async function loadHtmlPartial(targetId, url) {
  const host = document.getElementById(targetId);
  if (!host) return;
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`加载片段失败: ${url}`);
  host.innerHTML = await response.text();
}

function attachAdvancedFilmNavigation() {
  const source = document.getElementById("config-stage-strip");
  if (!source) return;
  document
    .querySelectorAll("#advanced-pages-slot > .page-view[data-view]")
    .forEach((page) => {
      if (page.querySelector(".advanced-film-context")) return;
      const context = document.createElement("section");
      context.className = "advanced-film-context";
      context.innerHTML = '<div><b>仍在片库搭建流程中</b><span>选择胶片返回对应的基础配置步骤</span></div>';
      const strip = source.cloneNode(true);
      strip.removeAttribute("id");
      strip.querySelectorAll("[data-config-stage]").forEach((button) => {
        button.dataset.advancedReturnStage = button.dataset.configStage;
        button.removeAttribute("data-config-stage");
        button.classList.remove("active");
      });
      context.appendChild(strip);
      page.prepend(context);
    });
}

function mountAdvancedSettingsInTrack() {
  const host = document.getElementById("advanced-track-host");
  if (!host) return;
  const groups = [
    {
      view: "naming-config",
      title: "入库名称规范",
      copy: "电影、剧集、字幕和重名文件的命名方式。",
      save: "naming",
    },
    {
      view: "dimensions-config",
      title: "影视分类维度",
      copy: "参与分类判断、目录变量和映射的维度。",
    },
    {
      view: "system-settings",
      title: "系统设置",
      copy: "日志、资源、并发数和文件识别范围。",
      save: "system",
    },
  ];
  host.innerHTML = "";
  groups.forEach((group) => {
    const page = document.querySelector(`[data-view="${group.view}"]`);
    const panel = page?.querySelector(".config-panel");
    if (!page || !panel) return;
    const details = document.createElement("details");
    details.className = "advanced-track-group";
    details.innerHTML = `<summary><div><b>${escapeHtml(group.title)}</b><span>${escapeHtml(group.copy)}</span></div><i aria-hidden="true">+</i></summary>`;
    panel.classList.add("advanced-track-panel");
    details.appendChild(panel);
    if (group.save) {
      const actions = document.createElement("div");
      actions.className = "advanced-track-actions";
      actions.innerHTML = `<button class="btn btn-primary" type="button" data-config-save="${group.save}">保存${escapeHtml(group.title)}</button>`;
      details.appendChild(actions);
    }
    host.appendChild(details);
    page.hidden = true;
  });
  const legacyHome = document.querySelector('[data-view="advanced-config"]');
  if (legacyHome) legacyHome.hidden = true;
}

async function runAction(action, trigger) {
  if (action === "clear-expired-recycle") {
    const expiredItems = currentRecycleRecords
      .filter((item) => !item.restorable)
      .map((item) => item.recycle_path || item.id)
      .filter(Boolean);
    if (expiredItems.length === 0) {
      showToast("当前没有待清理的过期回收项");
      return;
    }
    showConfirm(
      "清理过期项",
      `确定清理当前 ${expiredItems.length} 个待清理回收项吗？`,
      async () => {
        const result = await requestApi("POST", "/recycle/delete", {
          items: expiredItems,
        });
        showToast(result.message || "过期回收项清理请求已发送");
        if (result.code === 200 || result.code === 207) await loadRecycleData();
      },
    );
    return;
  }
  const endpointByAction = {
    scan: "/run",
    pause: "/queue/pause",
    retry: "/queue/retry-all",
  };
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
    showToast(
      `当前已有 ${queueSnapshot.totalOpen} 个任务在处理中，请等待或前往任务工作台查看进度`,
    );
  }
  if (trigger) trigger.disabled = true;
  const result = await requestApi("POST", endpointByAction[action]);
  if (trigger) trigger.disabled = false;
  const friendly = {
    scan:
      result.code === 200
        ? "扫描已启动，任务入队后会自动出现在工作台"
        : result.message || "扫描请求已发送",
    pause:
      result.code === 200
        ? "处理已暂停，新文件不会自动入库"
        : result.message || "暂停请求已发送",
    retry:
      result.code === 200
        ? "正在批量重试失败任务"
        : result.message || "重试请求已发送",
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
    const failed = statusCount(byStatus, "FAILED", "failed");
    return {
      paused: !!result.data.paused,
      totalOpen: pending + failed,
      failed,
    };
  } catch (e) {
    return { paused: false, totalOpen: 0, failed: 0 };
  }
}

function setConfigStage(stage) {
  currentConfigStage = stage;
  const cards = Array.from(document.querySelectorAll("[data-config-stage]"));
  cards.forEach((card) => {
    card.classList.toggle("active", card.dataset.configStage === stage);
  });
  document.querySelectorAll("[data-config-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.configPanel === stage);
  });
  const activeIndex = cards.findIndex((card) => card.dataset.configStage === stage);
  const activeCard = activeIndex >= 0 ? cards[activeIndex] : null;
  const mobileStatus = document.getElementById("config-stage-mobile-status");
  if (mobileStatus && activeCard) {
    const label = activeCard.querySelector(".config-stage-label")?.textContent?.trim() || stage;
    const current = mobileStatus.querySelector("span");
    if (current) current.textContent = `${activeIndex + 1} / ${cards.length} · ${label}`;
  }
  if (activeCard && window.innerWidth <= 760) {
    activeCard.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }
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

function toggleSourceCleanerUi() {
  const enabledToggle = document.getElementById(
    "cfg-source-cleaner-enabled-inline",
  );
  if (!enabledToggle) return;
  const aiToggle = document.getElementById(
    "cfg-source_cleaner-ai_enabled-inline",
  );
  const enabled = enabledToggle.checked;
  const aiEnabled = enabled && !!(aiToggle && aiToggle.checked);
  const panel = document.getElementById("source-cleaner-panel");
  const aiActions = document.getElementById("sc-ai-actions-inline");
  const mergeCard = document.getElementById("sc-merge-inline-card");
  if (panel) panel.classList.toggle("active", enabled);
  if (aiActions) aiActions.classList.toggle("active", aiEnabled);
  if (mergeCard) mergeCard.classList.toggle("active", aiEnabled);
}

function placeLlmSettingsUnderSourcePolicy() {
  const card = document.getElementById("llm-connection-card");
  const oldDisclosure = document.getElementById("automation-llm-disclosure");
  if (oldDisclosure) oldDisclosure.hidden = true;
  // Saving LLM settings reloads configuration while the modal is still open.
  // Keep the card inside that modal until its close callback restores it.
  if (card?.closest(".cinema-modal-overlay")) return;
  let host = document.getElementById("llm-settings-host");
  if (!host) {
    host = document.createElement("div");
    host.id = "llm-settings-host";
    host.hidden = true;
    document.getElementById("source-cleaner-block")?.appendChild(host);
  }
  if (card && host && card.parentElement !== host) host.appendChild(card);
}

function placeSourceCleanerUnderModeChoice() {
  const child = document.getElementById("source-cleaner-mode-child");
  const block = document.getElementById("source-cleaner-block");
  if (child && block && block.parentElement !== child) child.appendChild(block);
}

function toggleSourceModeUi() {
  const mode =
    document.querySelector('input[name="cfg-source-after-done"]:checked')
      ?.value || "preserve_all";
  const cleanerBlock = document.getElementById("source-cleaner-block");
  const cleanerChild = document.getElementById("source-cleaner-mode-child");
  const cleanerToggle = document.getElementById(
    "cfg-source-cleaner-enabled-inline",
  );
  if (cleanerBlock) cleanerBlock.hidden = mode !== "preserve_media";
  if (cleanerChild) cleanerChild.hidden = mode !== "preserve_media";
  document.querySelectorAll("[data-source-mode-card]").forEach((card) => {
    card.classList.toggle("is-selected", card.dataset.sourceModeCard === mode);
  });
  if (cleanerToggle) cleanerToggle.checked = mode === "preserve_media";
  toggleSourceCleanerUi();
}

function openSourceCleanerRulesModal() {
  const fields = document.getElementById("source-cleaner-rules-fields");
  const home = document.getElementById("source-cleaner-panel");
  if (!fields || !home) return;
  fields.hidden = false;
  const overlay = showAppModal({
    title: "详细删除规则",
    tone: "wide",
    dismissOnBackdrop: false,
    body: '<div id="source-cleaner-rules-modal-host"></div>',
    actions: [{ label: "完成", className: "btn btn-primary" }],
    onClose: () => {
      fields.hidden = true;
      home.appendChild(fields);
    },
  });
  overlay.querySelector("#source-cleaner-rules-modal-host")?.appendChild(fields);
}

function openLlmConfigModal() {
  const card = document.getElementById("llm-connection-card");
  const home = document.getElementById("llm-settings-host");
  if (!card || !home) return;
  card.classList.add("open");
  const previousResult = document.getElementById("llm-test-result");
  if (previousResult) previousResult.hidden = true;
  const overlay = showAppModal({
    title: "配置 LLM 辅助清理",
    tone: "wide",
    dismissOnBackdrop: false,
    body: '<div class="cinema-modal-hint">LLM 只用于判断规则无法确定的垃圾文件，不参与影视识别。</div><div id="llm-settings-modal-host"></div>',
    actions: [{ label: "完成", className: "btn btn-primary" }],
    onClose: () => home.appendChild(card),
  });
  overlay.querySelector("#llm-settings-modal-host")?.appendChild(card);
  setTimeout(() => document.getElementById("cfg-llm-base_url")?.focus(), 50);
}

function promptLlmSetup() {
  openLlmConfigModal();
}

function toggleSourceDepthField() {
  const enabled = document.getElementById(
    "cfg-source-recursive-toggle-inline",
  ).checked;
  document
    .getElementById("cfg-source-depth-group-inline")
    .classList.toggle("active", enabled);
}

function toggleFileWatcherPollGroup() {
  const toggle = document.getElementById("cfg-file_watcher-enabled-inline");
  if (!toggle) return;
  const enabled = toggle.checked;
  const group = document.getElementById("cfg-file_watcher-poll-group-inline");
  if (group) group.classList.toggle("active", enabled);
}

function syncAutomationToggleCopy() {
  const toggle = document.getElementById("cfg-auto-watcher-enabled");
  const label = document.getElementById("cfg-auto-watcher-label");
  if (!toggle || !label) return;
  label.textContent = toggle.checked
    ? "后台自动整理已开启"
    : "后台自动整理已关闭";
}

function updateStickyHeroState() {
  document
    .querySelectorAll(".page-hero.is-condensed")
    .forEach((hero) => hero.classList.remove("is-condensed"));
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

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
  "security-config",
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
      document.getElementById("cfg-source-inline")?.value,
    ),
    temp_dir: normalizePathValue(
      document.getElementById("cfg-temp-inline")?.value,
    ),
    recycle_dir: normalizePathValue(
      document.getElementById("cfg-recycle-inline")?.value,
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
    host.innerHTML =
      '<div class="activity-row"><div class="state"><svg class="icon icon-sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-clock"></use></svg></div><div><b>当前还没有新的活动记录</b><small>系统启动后，这里会滚动显示扫描、识别和入库过程。</small></div><span class="time">刚刚</span></div>';
    return;
  }
  host.innerHTML = items
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

function toggleSourceDepthField() {
  const enabled = document.getElementById(
    "cfg-source-recursive-toggle-inline",
  ).checked;
  document
    .getElementById("cfg-source-depth-group-inline")
    .classList.toggle("active", enabled);
}

function toggleFileWatcherPollGroup() {
  const enabled = document.getElementById(
    "cfg-file_watcher-enabled-inline",
  ).checked;
  const group = document.getElementById("cfg-file_watcher-poll-group-inline");
  if (group) group.classList.toggle("active", enabled);
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

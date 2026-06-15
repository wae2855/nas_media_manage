// cinema-reel.js - reel wheel and status update functions
function initReelWheel() {
  const wheel = document.getElementById("reel-wheel");
  const emptyState = document.getElementById("reel-empty-state");
  if (!wheel) return;

  let activeIndex = 0;
  let rotateTimer = null;

  function getRelativeSlot(index, total) {
    let slot = index - activeIndex;
    if (slot > total / 2) slot -= total;
    if (slot < -total / 2) slot += total;
    if (slot > 3) return 4;
    if (slot < -3) return -4;
    return slot;
  }

  function paintSlots() {
    const frames = Array.from(wheel.querySelectorAll(".reel-frame"));
    const total = frames.length;
    frames.forEach((frame, index) => {
      const slot = getRelativeSlot(index, total);
      frame.dataset.slot = String(slot);
      frame.classList.toggle("is-active", slot === 0);
      frame.style.zIndex = String(20 - Math.abs(slot));
    });
  }

  function scheduleRotation(total) {
    if (rotateTimer) clearInterval(rotateTimer);
    if (total <= 1) return;
    rotateTimer = setInterval(() => {
      activeIndex = (activeIndex + 1) % total;
      paintSlots();
    }, 2800);
  }

  window.buildReelWheel = function buildReelWheel(items) {
    wheel.innerHTML = "";
    activeIndex = 0;
    if (rotateTimer) clearInterval(rotateTimer);

    if (!items || items.length === 0) {
      wheel.parentElement.style.display = "none";
      if (emptyState) emptyState.style.display = "flex";
      return;
    }
    wheel.parentElement.style.display = "";
    if (emptyState) emptyState.style.display = "none";

    const visibleItems = items.slice(0, 12);
    visibleItems.forEach((item, index) => {
      const frame = document.createElement("button");
      frame.type = "button";
      frame.className = "reel-frame";
      frame.setAttribute("aria-label", item.title || `影片 ${index + 1}`);
      frame.addEventListener("click", () => {
        activeIndex = index;
        paintSlots();
        scheduleRotation(visibleItems.length);
      });

      const imageWrap = document.createElement("span");
      imageWrap.className = "reel-frame-img";

      if (item.image) {
        const img = document.createElement("img");
        img.src = item.image;
        img.alt = item.title || "影片";
        img.loading = "lazy";
        img.addEventListener("error", () => {
          img.style.display = "none";
          placeholder.style.display = "flex";
        });
        imageWrap.appendChild(img);
      }

      const placeholder = document.createElement("span");
      placeholder.className = "reel-frame-placeholder";
      placeholder.style.display = item.image ? "none" : "flex";
      placeholder.textContent = "🎬";
      imageWrap.appendChild(placeholder);

      const badge = document.createElement("span");
      badge.className = "reel-badge";
      badge.textContent = String(index + 1).padStart(2, "0");

      frame.appendChild(imageWrap);
      frame.appendChild(badge);
      wheel.appendChild(frame);
    });

    paintSlots();
    scheduleRotation(visibleItems.length);
  };

  window.buildReelWheel([]);
}

/* 缩略图缓存：避免重复请求 */
let _cachedThumbnails = null;
let _thumbnailCacheTime = 0;
const THUMBNAIL_CACHE_TTL = 30000; // 30秒缓存

async function loadReelWheelFromTasks() {
  /* 只使用 Thumbnail 文件夹的图片，没有图片时显示空状态 */
  const now = Date.now();
  const useCache =
    _cachedThumbnails && now - _thumbnailCacheTime < THUMBNAIL_CACHE_TTL;

  function buildWheel(thumbnails) {
    let items = [];

    /* 如果有缩略图，用缩略图填充轮盘 */
    if (thumbnails && thumbnails.length > 0) {
      const apiBase = typeof getApiBase === "function" ? getApiBase() : "";
      items = thumbnails.map((t, i) => ({
        title: t.name || `影片 ${i + 1}`,
        tone: "gold",
        image: t.url && t.url.startsWith("/api/") ? apiBase + t.url : t.url,
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
  try {
    const result = await requestApi("GET", "/thumbnails");
    if (
      result &&
      result.code === 200 &&
      result.data &&
      result.data.thumbnails
    ) {
      _cachedThumbnails = result.data.thumbnails;
      _thumbnailCacheTime = Date.now();
      buildWheel(_cachedThumbnails);
    } else {
      _cachedThumbnails = [];
      _thumbnailCacheTime = Date.now();
      buildWheel([]);
    }
  } catch (_e) {
    buildWheel(null);
  }
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
  initHelpAccordions();
  if (typeof bindAiConfigInteractions === "function")
    bindAiConfigInteractions();
  loadDirectoryConfig();
  if (typeof checkApiKeyRequired === "function") checkApiKeyRequired();
});

function updateScrapeModeHint() {
  const select = document.getElementById("cfg-metadata_scrape_mode");
  const hint = document.getElementById("cfg-scrape-mode-hint");
  if (!select || !hint) return;
  const hints = {
    provider_first:
      "Provider 权威，维度缺失时优先使用 AI 搜索增强补缺（降级 AI 辅助）",
  };
  hint.textContent = hints[select.value] || hints.provider_first;
}

function updateWebSearchSupport() {
  const supportInfo = document.getElementById("ai-search-support-text");
  if (!supportInfo) return;

  const baseUrl = String(
    document.getElementById("cfg-llm_base_url")?.value || "",
  )
    .trim()
    .toLowerCase();
  const supportedProviders = {
    "bigmodel.cn": "智谱 GLM",
    zhipu: "智谱 GLM",
    dashscope: "通义千问",
    aliyun: "通义千问",
    moonshot: "Kimi / Moonshot",
  };

  let detected = null;
  for (const [keyword, name] of Object.entries(supportedProviders)) {
    if (baseUrl.includes(keyword)) {
      detected = name;
      break;
    }
  }

  if (detected) {
    supportInfo.innerHTML =
      '<small style="color:var(--success-fg,#155724);">✓ 检测到 <b>' +
      detected +
      "</b>，支持AI联网搜索增强</small>";
  } else if (baseUrl) {
    supportInfo.innerHTML =
      '<small style="color:var(--warning-fg,#856404);">✗ 当前接口地址暂不支持联网搜索。支持的厂商：智谱 GLM、通义千问、Kimi/Moonshot。</small>';
  } else {
    supportInfo.innerHTML =
      "<small>填写接口地址后，系统自动检测是否支持联网搜索。</small>";
  }
}

function updateAiConfigStatus() {
  const searchEnabled = !!document.getElementById("cfg-ai_search-enabled")
    ?.checked;
  const searchModel = String(
    document.getElementById("cfg-ai_search-model")?.value || "",
  ).trim();
  const searchProvider = String(
    document.getElementById("cfg-ai_search-provider")?.value || "",
  ).trim();
  const searchKey = String(
    document.getElementById("cfg-ai_search-api_key")?.value || "",
  ).trim();
  const searchConfigured =
    searchEnabled && searchProvider && searchModel && searchKey;
  const scrapeStatus = document.getElementById("ai-scrape-status");
  if (scrapeStatus) {
    if (!searchEnabled) {
      scrapeStatus.textContent = "已关闭";
      scrapeStatus.className = "config-collapse-status";
    } else if (searchConfigured) {
      scrapeStatus.textContent = "已配置";
      scrapeStatus.className = "config-collapse-status status-configured";
    } else {
      scrapeStatus.textContent = "未配置";
      scrapeStatus.className = "config-collapse-status status-unconfigured";
    }
  }

  const assistModel = String(
    document.getElementById("cfg-ai_assist-model")?.value || "",
  ).trim();
  const assistKey = String(
    document.getElementById("cfg-ai_assist-api_key")?.value || "",
  ).trim();
  const assistBaseUrl = String(
    document.getElementById("cfg-ai_assist-base_url")?.value || "",
  ).trim();
  const assistConfigured = assistModel && assistKey && assistBaseUrl;
  const assistStatus = document.getElementById("ai-assist-status");
  if (assistStatus) {
    if (assistConfigured) {
      assistStatus.textContent = "已配置";
      assistStatus.className = "config-collapse-status status-configured";
    } else {
      assistStatus.textContent = "未配置";
      assistStatus.className = "config-collapse-status status-unconfigured";
    }
  }

  const scrapeModeStatus = document.getElementById("scrape-mode-status");
  if (scrapeModeStatus) {
    scrapeModeStatus.textContent = "Provider 优先";
    scrapeModeStatus.className = "config-collapse-status status-configured";
  }
}

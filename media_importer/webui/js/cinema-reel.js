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
  mountAdvancedSettingsInTrack();
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
  loadDirectoryConfig();
  if (typeof checkApiKeyRequired === "function") checkApiKeyRequired();

  try {
    const configResult = await requestApi("GET", "/config");
    if (configResult.code === 200 && configResult.data) {
      const rawConfig = configResult.data.config || configResult.data;
      const metadata = rawConfig.metadata || {};
      await loadInlineProviderConfigs(metadata);
    }
  } catch (e) {
    console.warn("独立加载 Provider 配置失败", e);
  }

  if (typeof loadDimensions === "function") {
    try {
      await loadDimensions();
    } catch (e) {
      console.warn("独立加载维度定义失败", e);
    }
  }

  try {
    await loadDimensionVars();
  } catch (e) {
    console.warn("独立加载已启用维度失败", e);
  }
});

function updateLlmConfigStatus() {
  const baseUrl = String(
    document.getElementById("cfg-llm-base_url")?.value || "",
  ).trim();
  const model = String(
    document.getElementById("cfg-llm-model")?.value || "",
  ).trim();
  const apiKey = String(
    document.getElementById("cfg-llm-api_key")?.value || "",
  ).trim();
  const configured = baseUrl && model && apiKey;
  const status = document.getElementById("llm-connection-status");
  if (status) {
    status.textContent = configured ? "已配置" : "未配置";
    status.className = configured
      ? "config-collapse-status status-configured"
      : "config-collapse-status status-unconfigured";
  }
}

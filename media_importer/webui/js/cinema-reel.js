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
  // T2.6 plan: 按 3 个 card（ai-apikey / ai-prompts / ai-scene-strategy）分别更新状态徽章

  // 1) API Key 区：ai_assist 或 ai_search 任一配置完整即视为已配置
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

  const searchModel = String(
    document.getElementById("cfg-ai_search-model")?.value || "",
  ).trim();
  const searchProvider = String(
    document.getElementById("cfg-ai_search-provider")?.value || "",
  ).trim();
  const searchKey = String(
    document.getElementById("cfg-ai_search-api_key")?.value || "",
  ).trim();
  const searchConfigured = searchProvider && searchModel && searchKey;

  const apikeyConfigured = assistConfigured || searchConfigured;
  const apikeyStatus = document.getElementById("ai-apikey-status");
  if (apikeyStatus) {
    if (apikeyConfigured) {
      apikeyStatus.textContent = "已配置";
      apikeyStatus.className = "config-collapse-status status-configured";
    } else {
      apikeyStatus.textContent = "未配置";
      apikeyStatus.className = "config-collapse-status status-unconfigured";
    }
  }

  // 2) 提示词区：5 个 prompt 任一非默认（用户填过）即视为已配置
  const promptFields = [
    "cfg-ai_assist-prompt_title_clean",
    "cfg-ai_assist-prompt_match_assist",
    "cfg-ai_assist-prompt_dimension_mapping",
    "cfg-ai_assist-prompt_source_clean",
    "cfg-ai_search-prompt_dimension_supplement",
  ];
  const promptsConfigured = promptFields.some((id) => {
    const el = document.getElementById(id);
    return el && String(el.value || "").trim() !== "";
  });
  const promptsStatus = document.getElementById("ai-prompts-status");
  if (promptsStatus) {
    if (promptsConfigured) {
      promptsStatus.textContent = "已自定义";
      promptsStatus.className = "config-collapse-status status-configured";
    } else {
      promptsStatus.textContent = "使用默认";
      promptsStatus.className = "config-collapse-status status-unconfigured";
    }
  }

  // 3) 场景策略区：5 个场景 primary 都已配置
  const scenes = [
    "dimension_supplement",
    "dimension_mapping",
    "title_clean",
    "match_assist",
    "source_clean",
  ];
  const strategyConfigured = scenes.every((scene) => {
    const el = document.querySelector(`[data-scene-primary="${scene}"]`);
    return el && String(el.value || "").trim() !== "";
  });
  const strategyStatus = document.getElementById("ai-scene-strategy-status");
  if (strategyStatus) {
    if (strategyConfigured) {
      strategyStatus.textContent = "已配置";
      strategyStatus.className = "config-collapse-status status-configured";
    } else {
      strategyStatus.textContent = "未配置";
      strategyStatus.className = "config-collapse-status status-unconfigured";
    }
  }

  // 兼容旧 id（保留 scrape-mode-status）
  const scrapeModeStatus = document.getElementById("scrape-mode-status");
  if (scrapeModeStatus) {
    scrapeModeStatus.textContent = "Provider 优先";
    scrapeModeStatus.className = "config-collapse-status status-configured";
  }
}

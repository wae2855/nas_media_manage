// cinema-config-ai.js - extracted from cinema-config.js

function syncAiSearchEnabledState() {
  const enabled = !!document.getElementById("cfg-ai_search-enabled")?.checked;
  const fields = document.querySelectorAll(
    '#cfg-ai_search-provider, #cfg-ai_search-model, #cfg-ai_search-search_type, ' +
    '#cfg-ai_search-api_key, #cfg-ai_search-base_url, #cfg-ai_search-timeout, ' +
    '#cfg-ai_search-max_retries, #cfg-ai_search-retry_delay, #cfg-ai_search-verify_ssl'
  );
  fields.forEach((el) => {
    if (el.closest('.config-collapse-card, .cinema-config-section')) {
      const card = el.closest('.config-collapse-card, .cinema-config-section');
      if (card) card.style.opacity = enabled ? '' : '0.5';
    }
    el.disabled = !enabled;
  });
}

function syncAiSearchOptions(clearModel) {
  const provider = document.getElementById("cfg-ai_search-provider")?.value || "";
  const modelSelect = document.getElementById("cfg-ai_search-model");
  const searchTypeSelect = document.getElementById("cfg-ai_search-search_type");
  const baseUrlInput = document.getElementById("cfg-ai_search-base_url");

  // Update model options based on provider
  if (modelSelect && typeof PROVIDER_MODEL_MAP !== "undefined" && PROVIDER_MODEL_MAP[provider]) {
    const currentModel = modelSelect.value;
    const models = PROVIDER_MODEL_MAP[provider];
    modelSelect.innerHTML = '<option value="">选择模型</option>' +
      models.map(m => `<option value="${m.value}">${m.label}</option>`).join("");
    if (!clearModel && currentModel) {
      modelSelect.value = currentModel;
    }
  }

  // Update search type options based on provider
  if (searchTypeSelect && typeof SEARCH_TYPE_MAP !== "undefined" && SEARCH_TYPE_MAP[provider]) {
    const currentType = searchTypeSelect.value;
    const types = SEARCH_TYPE_MAP[provider];
    searchTypeSelect.innerHTML = '<option value="">选择搜索类型</option>' +
      types.map(t => `<option value="${t.value}">${t.label}</option>`).join("");
    if (currentType) searchTypeSelect.value = currentType;
  } else if (searchTypeSelect) {
    searchTypeSelect.innerHTML = '<option value="">选择搜索类型</option>';
  }

  // Auto-fill base URL based on provider
  if (baseUrlInput && typeof PROVIDER_BASE_URL_MAP !== "undefined" && PROVIDER_BASE_URL_MAP[provider]) {
    if (!baseUrlInput.value.trim()) {
      baseUrlInput.value = PROVIDER_BASE_URL_MAP[provider];
    }
  }

  syncAiSearchEnabledState();
}

async function loadPromptDefaults() {
  if (window._promptDefaultsCache) return window._promptDefaultsCache;
  const result = await requestApi("GET", "/config/prompt-defaults");
  window._promptDefaultsCache = result.code === 200 ? result.data || {} : {};
  return window._promptDefaultsCache;
}

async function resetActivePrompt(group) {
  const defaults = await loadPromptDefaults();
  const wrapper = document.querySelector(`[data-prompt-tabs="${group}"]`);
  const active =
    wrapper?.querySelector(".prompt-tab.active")?.dataset.promptTab;
  if (!active) return;
  const textarea = wrapper.querySelector(
    `#cfg-${group === "ai-assist" ? "ai_assist" : "ai_search"}-${active}`,
  );
  if (textarea) textarea.value = defaults[active] || "";
}

function bindAiConfigInteractions() {
  document
    .getElementById("cfg-ai_search-provider")
    ?.addEventListener("change", () => syncAiSearchOptions(true));
  document
    .getElementById("cfg-ai_search-enabled")
    ?.addEventListener("change", syncAiSearchEnabledState);
  document.querySelectorAll("[data-prompt-tabs]").forEach((wrapper) => {
    wrapper.addEventListener("click", (event) => {
      const tab = event.target.closest("[data-prompt-tab]");
      if (!tab) return;
      const key = tab.dataset.promptTab;
      wrapper
        .querySelectorAll(".prompt-tab")
        .forEach((item) => item.classList.toggle("active", item === tab));
      wrapper
        .querySelectorAll(".prompt-tab-panel")
        .forEach((panel) =>
          panel.classList.toggle("active", panel.id.endsWith(key)),
        );
    });
  });
  document.querySelectorAll("[data-prompt-reset]").forEach((btn) => {
    btn.addEventListener("click", () =>
      resetActivePrompt(btn.dataset.promptReset),
    );
  });
}

async function testLlmConnection() {
  const payload = buildAiSearchPayload().ai_search;
  if (!payload.base_url) {
    showToast("请先选择厂商或填写接口地址");
    return;
  }
  if (!payload.model) {
    showToast("请先选择模型ID");
    return;
  }
  showToast("正在测试 LLM 连通性...");
  const result = await requestApi("POST", "/config/test-llm", {
    api_key: payload.api_key,
    base_url: payload.base_url,
    model: payload.model,
    verify_ssl: payload.verify_ssl,
  });
  const data = result.data || {};
  showToast(data.message || result.message || "LLM 测试已完成");
}

function openAiScrapeDemoModal() {
  document.getElementById("ai-scrape-demo-modal").style.display = "flex";
  document.getElementById("ai-scrape-demo-result").style.display = "none";
  document.getElementById("ai-scrape-demo-loading").style.display = "none";
}

function closeAiScrapeDemoModal() {
  document.getElementById("ai-scrape-demo-modal").style.display = "none";
}

function openAiAssistDemoModal() {
  document.getElementById("ai-assist-demo-modal").style.display = "flex";
  document.getElementById("ai-assist-demo-result").style.display = "none";
  document.getElementById("ai-assist-demo-loading").style.display = "none";
}

function closeAiAssistDemoModal() {
  document.getElementById("ai-assist-demo-modal").style.display = "none";
}

async function runAiScrapeDemo(scenario, demoFile) {
  const resultArea = document.getElementById("ai-scrape-demo-result");
  const loadingEl = document.getElementById("ai-scrape-demo-loading");
  const resultTitle = document.getElementById("ai-scrape-demo-result-title");
  const resultElapsed = document.getElementById(
    "ai-scrape-demo-result-elapsed",
  );
  const resultBody = document.getElementById("ai-scrape-demo-result-body");

  resultArea.style.display = "none";
  loadingEl.style.display = "flex";

  const payload = buildAiConfigPayload();

  try {
    const result = await requestApi("POST", "/config/ai-demo", {
      scenario: scenario,
      demo_content: demoFile,
      config_override: payload,
    });
    const data = result.data || {};

    loadingEl.style.display = "none";
    resultArea.style.display = "block";

    const labels = { scrape: "电影刮削", series_scrape: "剧集刮削" };
    resultTitle.textContent = (labels[scenario] || scenario) + " · " + demoFile;

    let elapsedText = data.elapsed_ms != null ? data.elapsed_ms + "ms" : "";
    if (data.search_enhanced) {
      elapsedText += " 🔍 AI联网搜索增强";
    } else {
      elapsedText += " 📴 纯本地分析";
    }
    resultElapsed.textContent = elapsedText;

    if (data.success) {
      resultBody.textContent = JSON.stringify(data.result, null, 2);
    } else {
      resultBody.textContent = "执行失败: " + (data.message || "未知错误");
    }
  } catch (e) {
    loadingEl.style.display = "none";
    resultArea.style.display = "block";
    resultTitle.textContent = "执行异常";
    resultElapsed.textContent = "";
    resultBody.textContent = "请求异常: " + (e.message || e);
  }
}

async function runAiAssistDemo(scenario, demoFile) {
  const resultArea = document.getElementById("ai-assist-demo-result");
  const loadingEl = document.getElementById("ai-assist-demo-loading");
  const resultTitle = document.getElementById("ai-assist-demo-result-title");
  const resultElapsed = document.getElementById(
    "ai-assist-demo-result-elapsed",
  );
  const resultBody = document.getElementById("ai-assist-demo-result-body");

  resultArea.style.display = "none";
  loadingEl.style.display = "flex";

  const payload = buildAiConfigPayload();

  try {
    const result = await requestApi("POST", "/config/ai-demo", {
      scenario: scenario,
      demo_content: demoFile,
      config_override: payload,
    });
    const data = result.data || {};

    loadingEl.style.display = "none";
    resultArea.style.display = "block";

    const labels = { extract_title: "标题提取", source_cleaner: "源目录清理" };
    resultTitle.textContent = (labels[scenario] || scenario) + " · " + demoFile;
    resultElapsed.textContent =
      data.elapsed_ms != null ? data.elapsed_ms + "ms" : "";

    if (data.success) {
      resultBody.textContent = JSON.stringify(data.result, null, 2);
    } else {
      resultBody.textContent = "执行失败: " + (data.message || "未知错误");
    }
  } catch (e) {
    loadingEl.style.display = "none";
    resultArea.style.display = "block";
    resultTitle.textContent = "执行异常";
    resultElapsed.textContent = "";
    resultBody.textContent = "请求异常: " + (e.message || e);
  }
}


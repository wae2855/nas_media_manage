// cinema-directory-loader.js - loadDirectoryConfig

// Stub: confidence config UI not yet implemented
function loadCinemaConfidenceConfig(rawConfig) {
  // TODO: populate confidence threshold UI when implemented
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
  document.getElementById("cfg-source-recursive-toggle-inline").checked =
    sourcePolicy.scan_recursive ?? true;
  setFieldValue("cfg-source-depth-inline", sourcePolicy.scan_max_depth || 5);
  setFieldValue(
    "cfg-recycle-retention-inline",
    sourcePolicy.recycle_retention_days || 30,
  );
  setFieldValue("cfg-fallback-inline", rawConfig.fallback_dir || "");
  setFieldValue(
    "cfg-filename_templates-movie-inline",
    (rawConfig.filename_templates || {}).movie || "",
  );
  setFieldValue(
    "cfg-filename_templates-tv-inline",
    (rawConfig.filename_templates || {}).tv || "",
  );
  setFieldValue(
    "cfg-filename_templates-subtitle-inline",
    (rawConfig.filename_templates || {}).subtitle || "",
  );
  setFieldValue(
    "cfg-duplicate_handling-strategy-inline",
    (rawConfig.duplicate_handling || {}).strategy || "skip",
  );
  setFieldValue(
    "cfg-server_api_key-inline",
    (rawConfig.server || {}).api_key || "",
  );
  setFieldValue(
    "cfg-server_port-inline",
    (rawConfig.server || {}).port || 9855,
  );
  setFieldValue("cfg-log_dir-inline", rawConfig.log_dir || "");
  setFieldValue(
    "cfg-resource_dir-inline",
    rawConfig.resource_dir || rawConfig.resources_dir || "",
  );
  setFieldValue(
    "cfg-task_queue-max_concurrent-inline",
    (rawConfig.task_queue || {}).max_concurrent || 1,
  );
  const watcherCfg = rawConfig.file_watcher || {};
  document.getElementById("cfg-file_watcher-enabled-inline").checked =
    !!watcherCfg.enabled;
  setFieldValue(
    "cfg-file_watcher-poll_interval-inline",
    watcherCfg.poll_interval || 60,
  );
  toggleFileWatcherPollGroup();
  setFieldValue(
    "cfg-video_extensions-inline",
    (rawConfig.video_extensions || []).join("\n"),
  );
  setFieldValue(
    "cfg-subtitle_extensions-inline",
    (rawConfig.subtitle_extensions || []).join("\n"),
  );
  const aiAssist = rawConfig.ai_assist || {};
  const aiSearch = rawConfig.ai_search || {};
  setFieldValue(
    "cfg-ai_assist-base_url",
    aiAssist.base_url || llm.fast_base_url || llm.base_url || "",
  );
  setFieldValue(
    "cfg-ai_assist-model",
    aiAssist.model || llm.fast_model || llm.model || "",
  );
  setFieldValue(
    "cfg-ai_assist-api_key",
    aiAssist.api_key || llm.fast_api_key || "",
  );
  setFieldValue("cfg-ai_assist-timeout", aiAssist.timeout || llm.timeout || 30);
  setFieldValue(
    "cfg-ai_assist-max_retries",
    aiAssist.max_retries || llm.max_retries || 2,
  );
  setFieldValue(
    "cfg-ai_assist-retry_delay",
    aiAssist.retry_delay || llm.retry_delay || 3,
  );
  document.getElementById("cfg-ai_assist-verify_ssl").checked =
    aiAssist.verify_ssl !== false;
  setFieldValue(
    "cfg-ai_assist-prompt_title_clean",
    aiAssist.prompt_title_clean || "",
  );
  setFieldValue(
    "cfg-ai_assist-prompt_match_assist",
    aiAssist.prompt_match_assist || "",
  );
  setFieldValue(
    "cfg-ai_assist-prompt_dimension_mapping",
    aiAssist.prompt_dimension_mapping || "",
  );
  setFieldValue(
    "cfg-ai_assist-prompt_source_clean",
    aiAssist.prompt_source_clean || "",
  );
  document.getElementById("cfg-ai_search-enabled").checked =
    aiSearch.enabled !== false;
  setFieldValue(
    "cfg-ai_search-provider",
    aiSearch.provider || (llm.web_search || {}).provider || "",
  );
  setFieldValue(
    "cfg-ai_search-base_url",
    aiSearch.base_url || llm.base_url || "",
  );
  syncAiSearchOptions();
  setFieldValue("cfg-ai_search-model", aiSearch.model || llm.model || "");
  setFieldValue(
    "cfg-ai_search-search_type",
    aiSearch.search_type || (llm.web_search || {}).search_type || "",
  );
  setFieldValue("cfg-ai_search-api_key", aiSearch.api_key || llm.api_key || "");
  setFieldValue("cfg-ai_search-timeout", aiSearch.timeout || llm.timeout || 30);
  setFieldValue(
    "cfg-ai_search-max_retries",
    aiSearch.max_retries || llm.max_retries || 2,
  );
  setFieldValue(
    "cfg-ai_search-retry_delay",
    aiSearch.retry_delay || llm.retry_delay || 3,
  );
  document.getElementById("cfg-ai_search-verify_ssl").checked =
    aiSearch.verify_ssl !== false;
  setFieldValue(
    "cfg-ai_search-prompt_dimension_supplement",
    aiSearch.prompt_dimension_supplement || "",
  );
  syncAiSearchEnabledState();
  updateAiConfigStatus();
  document.getElementById("cfg-source-cleaner-enabled-inline").checked =
    !!sourceCleaner.enabled;
  document.getElementById("cfg-hermes_enabled-inline").checked = !!(
    rawConfig.hermes || {}
  ).enabled;
  setFieldValue(
    "cfg-hermes_webhook_base_url-inline",
    ((rawConfig.hermes || {}).webhook || {}).base_url || "",
  );
  setFieldValue(
    "cfg-hermes_webhook_route_name-inline",
    ((rawConfig.hermes || {}).webhook || {}).route_name || "",
  );
  setFieldValue(
    "cfg-hermes_webhook_secret-inline",
    ((rawConfig.hermes || {}).webhook || {}).secret || "",
  );
  setFieldValue(
    "cfg-hermes_webhook_timeout-inline",
    ((rawConfig.hermes || {}).webhook || {}).timeout || 30,
  );
  setFieldValue(
    "cfg-hermes_webhook_max_retries-inline",
    ((rawConfig.hermes || {}).webhook || {}).max_retries || 3,
  );
  setFieldValue(
    "cfg-hermes_webhook_retry_delay-inline",
    ((rawConfig.hermes || {}).webhook || {}).retry_delay || 5,
  );
  const hermesEvents = ((rawConfig.hermes || {}).webhook || {}).events || [];
  document.getElementById("cfg-hermes_webhook_verify_ssl-inline").checked = !!(
    (rawConfig.hermes || {}).webhook || {}
  ).verify_ssl;
  document.getElementById("cfg-hermes_event_batch_start-inline").checked =
    hermesEvents.includes("batch_start");
  document.getElementById("cfg-hermes_event_batch_complete-inline").checked =
    hermesEvents.includes("batch_complete");
  document.getElementById("cfg-hermes_event_program_error-inline").checked =
    hermesEvents.includes("program_error");
  document
    .querySelectorAll('input[name="cfg-source_cleaner-cleanup_mode_inline"]')
    .forEach((radio) => {
      radio.checked =
        radio.value === (sourceCleaner.cleanup_mode || "media_only");
    });
  document.getElementById("cfg-source_cleaner-ai_enabled-inline").checked =
    !!sourceCleaner.ai_enabled;
  setFieldValue(
    "cfg-source_cleaner-merge_strategy-inline",
    sourceCleaner.merge_strategy || "intersection",
  );
  setFieldValue(
    "cfg-source_cleaner-delete_extensions-inline",
    (sourceCleaner.delete_extensions || []).join("\n"),
  );
  setFieldValue(
    "cfg-source_cleaner-protect_extensions-inline",
    (sourceCleaner.protect_extensions || []).join("\n"),
  );
  setFieldValue(
    "cfg-source_cleaner-blacklist_patterns-inline",
    (sourceCleaner.blacklist_patterns || []).join("\n"),
  );
  setFieldValue(
    "cfg-source_cleaner-junk_video_max_size_mb-inline",
    sourceCleaner.junk_video_max_size_mb != null
      ? sourceCleaner.junk_video_max_size_mb
      : 0,
  );
  document.getElementById(
    "cfg-source_cleaner-cleanup_empty_dirs-inline",
  ).checked = !!sourceCleaner.cleanup_empty_dirs;
  setFieldValue(
    "cfg-source_cleaner-schedule-inline",
    sourceCleaner.schedule || "",
  );
  updateConfigStageStatus(rawConfig, paths, rawConfig.path_rules || []);
  try {
    loadCinemaConfidenceConfig(rawConfig);
  } catch (err) {
    console.warn("loadCinemaConfidenceConfig 失败,继续同步 UI 状态", err);
  }
  try {
    await loadInlineProviderConfigs(metadata);
  } catch (err) {
    console.warn("loadInlineProviderConfigs 失败,继续同步 UI 状态", err);
  }
  toggleSourceDepthField();
  toggleSourceCleanerUi();
  toggleHermesInlineFields();
  if (typeof loadDimensions === "function") {
    try {
      await loadDimensions();
    } catch (err) {
      console.warn("loadDimensions 失败,继续后续同步", err);
    }
  }
  try {
    await loadDimensionVars();
  } catch (err) {
    console.warn("loadDimensionVars 失败,继续后续同步", err);
  }
  try {
    renderRuleList(rawConfig.path_rules || []);
  } catch (err) {
    console.warn("renderRuleList 失败,继续后续同步", err);
  }
}


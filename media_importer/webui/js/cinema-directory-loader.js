// cinema-directory-loader.js - loadDirectoryConfig

// Stub: confidence config UI not yet implemented
function loadCinemaConfidenceConfig(rawConfig) {
  // TODO: populate confidence threshold UI when implemented
}

function formatStorageBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "容量未知";
  if (bytes >= 1024 ** 4) return `${(bytes / 1024 ** 4).toFixed(1)} TB`;
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
}

function renderStorageReadiness(readiness) {
  const host = document.getElementById("storage-readiness-grid");
  const locations = Array.isArray(readiness?.locations)
    ? readiness.locations
    : [];
  const roleLabels = {
    source: "文件来源",
    temp: "本地中转",
    recycle: "本地回收",
    target: "片库目标",
    log: "运行日志",
  };
  if (host) {
    host.innerHTML = locations.length
      ? locations
          .map((item) => {
            const capacity = item.capacity || {};
            const capacityText = item.status === "OFFLINE"
              ? "修复目录后重新读取容量"
              : capacity.known
              ? `可用 ${formatStorageBytes(capacity.free)} · 安全余量 ${formatStorageBytes(capacity.reserve)}`
              : "容量由远程挂载提供，运行时再次确认";
            const source = !item.identity
              ? "尚未验证"
              : item.identity.locality === "remote"
                ? "远程挂载"
                : "本地目录";
            return `<article class="storage-readiness-card is-${escapeHtml(item.level || "error")}">
              <div class="storage-card-head"><span class="storage-status-dot"></span><div><b>${escapeHtml(roleLabels[item.role] || item.role || "目录")}</b><small>${escapeHtml(source)}</small></div><strong>${item.level === "ok" ? "无需修改" : item.level === "warning" ? "请留意" : "需要处理"}</strong></div>
              <code title="${escapeHtml(item.path || "")}">${escapeHtml(item.path || "未配置")}</code>
              <p>${escapeHtml(item.message || "")}</p>
              <span class="storage-capacity">${escapeHtml(capacityText)}</span>
            </article>`;
          })
          .join("")
      : '<article class="storage-skeleton">还没有可检查的目录，请先完成 fnOS 目录选择。</article>';
  }

  const overall = document.getElementById("setup-overall-state");
  if (overall) {
    const ready = readiness?.state === "READY";
    overall.className = `setup-opening-state ${ready ? "is-ready" : "is-blocked"}`;
    overall.innerHTML = `<span class="setup-state-light" aria-hidden="true"></span><div><b>${ready ? "基础配置已就绪" : `还有 ${(readiness?.blocking || []).length} 项需要处理`}</b><small>${ready ? (readiness?.automatic_allowed ? "可以模拟或开启自动运行" : "可人工运行，自动运行暂缓") : "打开“存储检查”查看原因"}</small></div>`;
  }

  const finale = document.getElementById("setup-finale");
  if (finale) {
    const ready = readiness?.state === "READY";
    finale.classList.toggle("is-ready", ready);
    const mark = finale.querySelector(".setup-finale-mark");
    if (mark) mark.innerHTML = `<span>${ready ? "READY" : "HOLD"}</span><b>${ready ? "可以开始" : "暂不运行"}</b>`;
    const title = finale.querySelector("h3");
    const copy = finale.querySelector("p");
    if (title) title.textContent = ready ? "片库已经准备好开场" : "先解决阻塞项，再开始任务";
    if (copy) copy.textContent = ready
      ? "默认配置可以直接使用。建议先模拟一部影片，熟悉后再进入高级配置。"
      : "系统不会在目录离线、权限不足或空间不足时执行文件移动。";
  }
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
  const readiness = result.data.readiness || null;
  currentConfigRevision = result.data.revision || "";
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
  document
    .querySelectorAll('input[name="cfg-source-after-done"]')
    .forEach((radio) => {
      radio.checked =
        radio.value ===
        (sourcePolicy.cleanup_source_after_done === true ? "recycle" : "keep");
    });
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
  const automationToggle = document.getElementById("cfg-auto-watcher-enabled");
  if (automationToggle) automationToggle.checked = !!watcherCfg.enabled;
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
  setFieldValue("cfg-llm-base_url", llm.base_url || "");
  setFieldValue("cfg-llm-model", llm.model || "");
  setFieldValue("cfg-llm-api_key", llm.api_key || "");
  setFieldValue("cfg-llm-fallback_model", llm.fallback_model || "");
  setFieldValue("cfg-llm-timeout", llm.timeout || 30);
  setFieldValue("cfg-llm-max_retries", llm.max_retries || 2);
  setFieldValue("cfg-llm-retry_delay", llm.retry_delay || 3);
  const llmSsl = document.getElementById("cfg-llm-verify_ssl");
  if (llmSsl) llmSsl.checked = llm.verify_ssl !== false;
  updateLlmConfigStatus();
  document.getElementById("cfg-source-cleaner-enabled-inline").checked =
    !!sourceCleaner.enabled;
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
  renderStorageReadiness(readiness);
  updateConfigStageStatus(rawConfig, paths, rawConfig.path_rules || [], readiness);
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

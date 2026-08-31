// cinema-directory-loader.js - loadDirectoryConfig

let currentStorageReadinessSnapshot = null;

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

function renderStorageReadiness(readiness, config = currentConfigSnapshot, capability = currentFnosDirectoryCapability) {
  currentStorageReadinessSnapshot = readiness;
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
    resource: "海报与缓存",
  };
  if (host) {
    const targetRoots = normalizedLibraryRoots(config);
    const cards = locations.length
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
            const rootId = String(item.id || "").startsWith("target:") ? String(item.id).slice(7) : "";
            const root = rootId ? targetRoots.find((entry) => entry.id === rootId) : null;
            const editableRole = ["source", "temp", "recycle", "log", "resource"].includes(item.role);
            const authAction = capability?.enforced && editableRole
              ? `<button class="btn btn-secondary btn-sm" type="button" data-fnos-auth-role="${item.role}">${item.path ? "更改位置" : "选择并授权"}</button>`
              : editableRole
                ? `<button class="btn btn-secondary btn-sm" type="button" data-directory-pick="${item.role}">${item.path ? "更改位置" : "选择目录"}</button>`
                : "";
            const targetActions = root ? `${capability?.enforced ? `<button class="btn btn-secondary btn-sm" type="button" data-fnos-auth-role="library" data-fnos-auth-path="${escapeHtml(root.path)}">重新授权</button>` : ""}<button class="btn btn-secondary btn-sm" type="button" data-library-root-action="edit" data-library-root-id="${escapeHtml(root.id)}">编辑</button><button class="btn btn-secondary btn-sm" type="button" data-library-root-action="delete" data-library-root-id="${escapeHtml(root.id)}">移除</button>` : "";
            const guidance = {
              temp: "建议与主要目标片库放在同一磁盘，减少跨盘搬运；也可选择本地 SSD 提升高频读写速度。",
              log: "系统默认位置通常无需修改；更改后将在下次服务启动时写入新目录。",
              resource: "用于海报和缩略图缓存，系统默认位置通常无需修改。",
            }[item.role] || "";
            return `<article class="storage-readiness-card is-${escapeHtml(item.level || "error")}">
              <div class="storage-card-head"><span class="storage-status-dot"></span><div><b>${escapeHtml(item.label || roleLabels[item.role] || item.role || "目录")}</b><small>${escapeHtml(source)}${root?.id === defaultLibraryRootId(config) ? " · 默认片库" : ""}</small></div></div>
              <div class="storage-card-detail"><strong>${item.level === "ok" ? "可用" : item.level === "warning" ? "请留意" : "需要处理"}</strong><code title="${escapeHtml(item.path || "")}">${escapeHtml(item.path || "未配置")}</code><p>${escapeHtml(item.message || "")}${guidance ? `<small class="storage-role-guidance">${escapeHtml(guidance)}</small>` : ""}</p></div>
              <div class="storage-card-foot"><span class="storage-capacity">${escapeHtml(capacityText)}</span><div class="storage-card-actions">${authAction}${targetActions}</div></div>
            </article>`;
          })
          .join("")
      : "";
    const targetPickerAttribute = capability?.enforced ? 'data-fnos-auth-role="library"' : 'data-library-root-action="add"';
    const migrationDrafts = targetRoots.length
      ? `<div class="directory-migration-drafts">${targetRoots.map((root) => `<code>${escapeHtml(root.name)} · ${escapeHtml(root.path)}</code>`).join("")}</div>`
      : "";
    const migrationActive = Boolean(config?._library_migration_error);
    const migrationActions = targetRoots.length
      ? `<div class="directory-migration-actions"><button class="btn btn-secondary btn-sm" type="button" ${targetPickerAttribute}>继续添加片库</button><button class="btn btn-primary btn-sm" type="button" data-library-migration-action="commit">已选齐，确认关联（${targetRoots.length}）</button></div>`
      : `<div class="directory-migration-actions"><button class="btn btn-primary btn-sm" type="button" ${targetPickerAttribute}>选择片库根</button></div>`;
    const migration = migrationActive
      ? `<article class="directory-migration-callout"><span>保留规则待关联</span><div><b>${targetRoots.length ? `已暂存 ${targetRoots.length} 个片库根` : "检测到本设备保留的旧版入库规则"}</b><p>这通常发生在升级、保留数据后重装，或中途更换片库路径。这里只转换路径规则，不会移动、覆盖或删除片库中的任何影片。请先选齐影片所在的所有磁盘；任何规则无法覆盖时整次保存都会取消。</p>${migrationDrafts}<p class="library-migration-feedback" data-library-migration-feedback hidden></p></div>${migrationActions}</article>`
      : "";
    const addTarget = migrationActive
      ? ""
      : `<article class="storage-add-library"><div><span>TARGET LIBRARY · ${targetRoots.length}</span><b>${targetRoots.length ? "还有其他硬盘？继续添加" : "添加第一个目标片库"}</b><p>数量不设上限，每个目录独立授权、检查和命名。</p></div><button class="btn btn-primary btn-sm" type="button" ${targetPickerAttribute}>${targetRoots.length ? "添加目标片库" : capability?.enforced ? "选择并授权" : "添加片库"}</button></article>`;
    host.innerHTML = `${migration}${cards}${addTarget}`;
  }

  const overall = document.getElementById("setup-overall-state");
  if (overall) {
    const ready = readiness?.state === "READY";
    overall.className = `setup-opening-state ${ready ? "is-ready" : "is-blocked"}`;
    overall.innerHTML = `<span class="setup-state-light" aria-hidden="true"></span><div><b>${ready ? "基础配置已就绪" : `还有 ${(readiness?.blocking || []).length} 项需要处理`}</b><small>${ready ? (readiness?.automatic_allowed ? "可以模拟或开启自动运行" : "可人工运行，自动运行暂缓") : "打开“存储检查”查看原因"}</small></div>`;
  }

  resetStartupReadinessView();
}

function resetStartupReadinessView() {
  const finale = document.getElementById("setup-finale");
  const list = document.getElementById("startup-readiness-list");
  if (list) list.innerHTML = "";
  if (!finale) return;
  finale.classList.remove("is-ready", "is-blocked");
  const mark = finale.querySelector(".setup-finale-mark");
  if (mark) mark.innerHTML = "<span>CHECK</span><b>等待开场检查</b>";
}

function renderStartupReadiness(result) {
  const checks = Array.isArray(result?.checks) ? result.checks : [];
  const list = document.getElementById("startup-readiness-list");
  const finale = document.getElementById("setup-finale");
  if (list) {
    const statusPresentation = {
      PASS: { label: "正常", tone: "pass" },
      SKIPPED: { label: "无需检查", tone: "skipped" },
      WARN: { label: "需要留意", tone: "warn" },
      WARNING: { label: "需要留意", tone: "warn" },
      BLOCKED: { label: "需要处理", tone: "blocked" },
      FAIL: { label: "检查失败", tone: "blocked" },
      ERROR: { label: "检查失败", tone: "blocked" },
    };
    list.innerHTML = checks
      .map(
        (item) => {
          const status = String(item.status || "BLOCKED").toUpperCase();
          const presentation = statusPresentation[status] || {
            label: "尚未完成",
            tone: "blocked",
          };
          return `<article class="startup-check is-${presentation.tone}"><span>${presentation.label}</span><div><b>${escapeHtml(item.label || "检查项")}</b><p>${escapeHtml(item.message || "")}</p></div>${item.fix_target ? `<button class="btn btn-secondary btn-sm" type="button" data-readiness-fix="${escapeHtml(item.fix_target)}">去处理</button>` : ""}</article>`;
        },
      )
      .join("");
  }
  if (!finale) return;
  const passed = result?.state === "PASS";
  finale.classList.toggle("is-ready", passed);
  finale.classList.toggle("is-blocked", !passed);
  const mark = finale.querySelector(".setup-finale-mark");
  if (mark) mark.innerHTML = `<span>${passed ? "READY" : "HOLD"}</span><b>${passed ? "可以开始" : "暂不运行"}</b>`;
  const title = finale.querySelector("h3");
  const copy = finale.querySelector("p");
  if (title) title.textContent = passed ? "整套配置已通过开场检查" : "仍有阻塞项需要处理";
  if (copy) copy.textContent = passed
    ? "目录、外部能力与运行条件已确认；可以返回首页开始任务。"
    : "系统会保留现有文件，不会在关键条件不满足时开始自动文件操作。";
}

function renderStartupReadinessFailure(message) {
  const list = document.getElementById("startup-readiness-list");
  const finale = document.getElementById("setup-finale");
  const detail = String(message || "无法连接本地服务，请确认服务仍在运行后重试。");
  if (list) {
    list.innerHTML = `<article class="startup-check is-blocked"><span>检查失败</span><div><b>开场检查未完成</b><p>${escapeHtml(detail)}</p></div><button class="btn btn-secondary btn-sm" type="button" data-startup-readiness>重新检查</button></article>`;
  }
  if (!finale) return;
  finale.classList.remove("is-ready");
  finale.classList.add("is-blocked");
  const mark = finale.querySelector(".setup-finale-mark");
  if (mark) mark.innerHTML = "<span>失败</span><b>请重新检查</b>";
  const title = finale.querySelector("h3");
  const copy = finale.querySelector("p");
  if (title) title.textContent = "开场检查没有完成";
  if (copy) copy.textContent = "尚未执行任何自动文件操作；请确认本地服务正常后重新检查。";
}

async function runStartupReadiness() {
  const buttons = document.querySelectorAll("[data-startup-readiness]");
  buttons.forEach((button) => {
    button.disabled = true;
    button.dataset.originalLabel = button.textContent;
    button.textContent = "正在检查...";
  });
  showToast("正在检查目录、网络与外部能力...");
  try {
    const result = await requestApi("GET", "/config/startup-readiness");
    if (result.code !== 200 || !result.data) {
      const message = result.message || "开场检查失败，请稍后重试。";
      renderStartupReadinessFailure(message);
      showToast(message);
      return;
    }
    renderStartupReadiness(result.data);
    showToast(result.data.state === "PASS" ? "开场检查通过" : "开场检查发现阻塞项");
  } finally {
    buttons.forEach((button) => {
      button.disabled = false;
      button.textContent = button.dataset.originalLabel || "运行开场检查";
      delete button.dataset.originalLabel;
    });
  }
}

function requiredDirectorySetupStage(config) {
  const sourcePolicy = config?.source_policy || {};
  const roots = Array.isArray(config?.library_roots)
    ? config.library_roots.filter(
        (root) => root && root.enabled !== false && String(root.path || "").trim(),
      )
    : [];
  if (!String(config?.source_dir || "").trim()) return "temp";
  if (
    !String(
      sourcePolicy.recycle_dir || sourcePolicy.quarantine_dir || "",
    ).trim()
  ) {
    return "temp";
  }
  if (!roots.length && !String(config?.library_root || "").trim()) return "rules";
  return "";
}

function guideRequiredDirectorySetup(config) {
  const stage = requiredDirectorySetupStage(config);
  if (!stage) return false;
  setView("config", "config");
  setConfigStage(stage);
  showToast("首次使用：请先完成目录选择");
  return true;
}

async function loadDirectoryConfig(options = {}) {
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
  const directoryAuthorization = result.data.directory_authorization || currentFnosDirectoryCapability;
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
        (sourcePolicy.mode ||
          (sourcePolicy.cleanup_source_after_done === true
            ? "recycle_source_unit"
            : "preserve_all"));
    });
  document.getElementById("cfg-source-recursive-toggle-inline").checked =
    sourcePolicy.scan_recursive ?? true;
  setFieldValue("cfg-source-depth-inline", sourcePolicy.scan_max_depth || 5);
  setFieldValue("cfg-source-unit-settle", sourcePolicy.unit_settle_seconds || 120);
  setFieldValue(
    "cfg-source-unit-incomplete-patterns",
    (sourcePolicy.unit_incomplete_patterns || [
      "*.part", "*.partial", "*.aria2", "*.!qB", "*.crdownload",
    ]).join("\n"),
  );
  setFieldValue(
    "cfg-recycle-retention-inline",
    sourcePolicy.recycle_retention_days || 30,
  );
  setFieldValue("cfg-fallback-inline", rawConfig.fallback_dir || "");
  renderLibraryRootList(rawConfig);
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
    "confirm",
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
  const automationToggle = document.getElementById("cfg-auto-watcher-enabled");
  if (automationToggle) automationToggle.checked = !!watcherCfg.enabled;
  syncAutomationToggleCopy();
  setFieldValue(
    "cfg-auto-watcher-poll-interval",
    watcherCfg.poll_interval || 60,
  );
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
    (sourcePolicy.mode || "preserve_all") === "preserve_media";
  document
    .querySelectorAll('input[name="cfg-source_cleaner-cleanup_mode_inline"]')
    .forEach((radio) => {
      radio.checked =
        radio.value === (sourceCleaner.cleanup_mode || "media_and_related");
    });
  document.getElementById("cfg-source_cleaner-ai_enabled-inline").checked =
    (sourcePolicy.mode || "preserve_all") === "preserve_media" &&
    !!sourceCleaner.enabled &&
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
  currentFnosDirectoryCapability = directoryAuthorization;
  renderStorageReadiness(readiness, rawConfig, directoryAuthorization);
  updateConfigStageStatus(rawConfig, paths, rawConfig.path_rules || [], readiness);
  if (options.guideSetup === true) guideRequiredDirectorySetup(rawConfig);
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
  placeLlmSettingsUnderSourcePolicy();
  toggleSourceModeUi();
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

// cinema-config-save.js — 配置保存与测试函数
let automationSavePending = false;

function renderAutomationRuntimeStatus(tone, title, detail) {
  const status = document.getElementById("automation-runtime-status");
  const titleEl = document.getElementById("automation-runtime-title");
  const detailEl = document.getElementById("automation-runtime-detail");
  if (!status || !titleEl || !detailEl) return;
  status.className = `automation-runtime-status is-${tone || "off"}`;
  titleEl.textContent = title || "后台状态未知";
  detailEl.textContent = detail || "请稍后重新进入此页面查看。";
}

function setAutomationControlsPending(pending) {
  const toggle = document.getElementById("cfg-auto-watcher-enabled");
  const interval = document.getElementById("cfg-auto-watcher-poll-interval");
  if (toggle) toggle.disabled = pending;
  if (interval) interval.disabled = pending;
}

async function loadWatcherRuntimeStatus() {
  const configured = currentConfigSnapshot?.file_watcher || {};
  renderAutomationRuntimeStatus(
    "loading",
    "正在读取后台状态...",
    "状态来自 fnOS 后台服务，不依赖当前页面保持打开。",
  );
  const result = await requestApi("GET", "/watcher/status");
  if (result.code !== 200) {
    renderAutomationRuntimeStatus(
      "error",
      "暂时无法读取后台状态",
      result.message || "请检查服务状态后重试。",
    );
    return result;
  }
  const runtime = result.data || {};
  if (runtime.status === "running" && runtime.enabled === true) {
    const seconds = Number(runtime.poll_interval || configured.poll_interval || 300);
    renderAutomationRuntimeStatus(
      "running",
      "fnOS 后台服务正在自动整理",
      `每 ${seconds} 秒检查一次源目录；关闭桌面窗口或手机页面后仍会继续运行。`,
    );
  } else if (runtime.status === "blocked") {
    renderAutomationRuntimeStatus(
      "error",
      "设置已保存，但后台暂未运行",
      runtime.reason || "当前目录状态不允许后台自动整理。",
    );
  } else if (runtime.status === "not_started" || runtime.status === "stopped") {
    renderAutomationRuntimeStatus(
      "error",
      "后台监控尚未启动",
      runtime.reason || "请重新应用设置；如果仍未启动，请检查服务日志。",
    );
  } else if (!runtime.configured_enabled && !configured.enabled) {
    renderAutomationRuntimeStatus(
      "off",
      "后台自动整理已关闭",
      "系统不会定时扫描源目录，但仍可在任务页手动处理。",
    );
  } else {
    renderAutomationRuntimeStatus(
      "error",
      "后台状态异常",
      runtime.reason || "请重新进入此页面或检查 fnOS 服务状态。",
    );
  }
  return result;
}

async function saveConfigPayload(payload, successText) {
  const result = await requestApi("POST", "/config", {
    ...payload,
    _revision: currentConfigRevision,
  });
  showToast(result.message || successText || "配置已保存");
  if (result.code === 200) {
    await loadDirectoryConfig();
  }
  return result;
}

function confirmPermanentSourceDeletion() {
  return new Promise((resolve) => {
    let settled = false;
    const settle = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    const sourcePath = currentConfigSnapshot?.source_dir || "尚未读取来源目录";
    const overlay = showAppModal({
      title: "确认永久删除来源",
      tone: "default",
      dismissOnBackdrop: false,
      body: `
        <div class="source-delete-confirm">
          <div class="source-delete-confirm-alert"><b>删除后无法从本应用恢复</b><span>云盘服务商是否另有回收站由服务商决定，本应用不能保证。</span></div>
          <dl><dt>来源目录</dt><dd>${escapeHtml(sourcePath)}</dd><dt>不会删除</dt><dd>目标片库中的影片；替换旧片库文件仍必须进入本地回收区。</dd></dl>
          <label><input id="confirm-source-permanent-delete" type="checkbox" /><span>我理解来源垃圾或已完成来源单元会被永久删除，并且无法从本应用恢复。</span></label>
        </div>`,
      actions: [
        { label: "取消", className: "btn btn-secondary" },
        {
          label: "确认永久删除",
          className: "btn btn-danger",
          onClick: () => settle(true),
        },
      ],
      onClose: () => settle(false),
    });
    const checkbox = overlay.querySelector("#confirm-source-permanent-delete");
    const confirmButton = overlay.querySelector(".cinema-modal-footer .btn-danger");
    if (confirmButton) confirmButton.disabled = true;
    checkbox?.addEventListener("change", () => {
      if (confirmButton) confirmButton.disabled = !checkbox.checked;
    });
  });
}

async function saveSourceConfig() {
  const payload = buildSourceConfigPayload();
  const paths = currentPathSnapshot();
  if (!paths.source_dir) {
    showToast("请先到“存储检查”选择文件来源目录");
    return;
  }
  const conflicts = validateDirectoryConflicts(paths);
  if (conflicts.length) {
    showToast(conflicts.join("；"));
    return;
  }
  const nextPermanent =
    payload.source_policy.mode !== "preserve_all" &&
    payload.source_policy.disposal_mode === "permanent_delete";
  const currentPolicy = currentConfigSnapshot?.source_policy || {};
  const alreadyPermanent =
    ["preserve_media", "recycle_source_unit"].includes(currentPolicy.mode) &&
    currentPolicy.disposal_mode === "permanent_delete";
  if (nextPermanent && !alreadyPermanent) {
    const acknowledged = await confirmPermanentSourceDeletion();
    if (!acknowledged) {
      showToast("未保存：已取消永久删除来源");
      return;
    }
    payload._confirm_source_permanent_delete = true;
  }
  await saveConfigPayload(payload, "源目录配置已保存");
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

async function saveLibraryRootsConfig() {
  const roots = normalizedLibraryRoots();
  const defaultId = defaultLibraryRootId();
  return saveConfigPayload({
    library_roots: roots,
    default_library_root_id: defaultId,
    library_root: libraryRootById(defaultId)?.path || "",
  }, "目标片库已保存；请在片库整理中为规则选择目标片库");
}

async function saveRulesConfig() {
  const payload = buildRulesConfigPayload();
  if (!Array.isArray(payload.library_roots) || payload.library_roots.length === 0) {
    showToast("请先添加至少一个目标片库");
    return;
  }
  if (!Array.isArray(payload.path_rules) || payload.path_rules.length === 0) {
    showToast("当前还没有可保存的入库规则，请先新增至少一条规则");
    return;
  }
  const rootsById = new Map(payload.library_roots.map((root) => [root.id, root]));
  for (let index = 0; index < payload.path_rules.length; index += 1) {
    const rule = payload.path_rules[index] || {};
    const name = String(rule.name || `规则 ${index + 1}`).trim();
    const rootId = String(rule.library_root_id || "").trim();
    const root = rootsById.get(rootId);
    if (!rootId) {
      showToast(`第 ${index + 1} 条规则“${name}”尚未选择目标片库`);
      return;
    }
    if (!root) {
      showToast(`第 ${index + 1} 条规则“${name}”引用了不存在的片库：${rootId}`);
      return;
    }
    if (root.enabled === false) {
      showToast(`第 ${index + 1} 条规则“${name}”引用了已停用的片库：${rootId}`);
      return;
    }
  }
  const invalidRule = payload.path_rules.find((rule) => {
    const value = String(rule?.template || "").trim();
    return value.startsWith("/") || value.split(/[\\/]+/).includes("..");
  });
  if (invalidRule) {
    showToast("入库规则只能填写片库根目录下的相对子目录");
    return;
  }
  if (
    payload.fallback_dir.startsWith("/") ||
    payload.fallback_dir.split(/[\\/]+/).includes("..")
  ) {
    showToast("兜底目录只能填写片库根目录下的相对子目录");
    return;
  }
  if (payload.fallback_dir) {
    const fallbackRootId = String(payload.fallback_library_root_id || "").trim();
    const fallbackRoot = rootsById.get(fallbackRootId);
    if (!fallbackRootId) {
      showToast("兜底入库目录尚未选择目标片库");
      return;
    }
    if (!fallbackRoot) {
      showToast(`兜底目录引用了不存在的片库：${fallbackRootId}`);
      return;
    }
    if (fallbackRoot.enabled === false) {
      showToast(`兜底目录引用了已停用的片库：${fallbackRootId}`);
      return;
    }
  }
  await saveConfigPayload(payload, "入库规则配置已保存");
}

async function saveProvidersConfig(providerType = "") {
  const payload = providerType
    ? buildProvidersPayloadFor(providerType)
    : buildAllProvidersPayload();
  const result = await requestApi("POST", "/config/section", {
    section: "metadata.providers",
    data: payload,
    revision: currentConfigRevision,
  });
  showToast(result.message || "Provider 配置已保存");
  if (result.code === 200) {
    await loadDirectoryConfig();
  }
}

async function saveLlmConfig() {
  const payload = buildLlmPayload();
  const result = await requestApi("POST", "/config/section", {
    section: "llm",
    data: payload,
    revision: currentConfigRevision,
  });
  showToast(result.message || "LLM 配置已保存");
  if (result.code === 200) {
    await loadDirectoryConfig();
  }
}

async function saveAutomationConfig() {
  if (automationSavePending) return null;
  const watcher = currentConfigSnapshot?.file_watcher || {};
  const previousEnabled = !!watcher.enabled;
  const previousInterval = Number(watcher.poll_interval || 300);
  const toggle = document.getElementById("cfg-auto-watcher-enabled");
  const interval = document.getElementById("cfg-auto-watcher-poll-interval");
  const enabled = !!document.getElementById("cfg-auto-watcher-enabled")
    ?.checked;
  const pollInterval = Number(
    document.getElementById("cfg-auto-watcher-poll-interval")?.value || 300,
  );
  automationSavePending = true;
  setAutomationControlsPending(true);
  renderAutomationRuntimeStatus(
    "loading",
    enabled ? "正在启动后台自动整理..." : "正在停止后台自动整理...",
    "正在把设置应用到 fnOS 后台服务。",
  );
  try {
    const result = await requestApi("POST", "/config", {
      _revision: currentConfigRevision,
      file_watcher: {
        ...watcher,
        enabled,
        poll_interval: pollInterval,
        stability_window_seconds: Number(watcher.stability_window_seconds || 120),
      },
    });
    showToast(
      result.message ||
        (enabled ? "后台自动整理已开启" : "后台自动整理已关闭"),
    );
    if (result.code === 200) {
      await loadDirectoryConfig();
      await loadWatcherRuntimeStatus();
    } else {
      if (toggle) toggle.checked = previousEnabled;
      if (interval) interval.value = String(previousInterval);
      syncAutomationToggleCopy();
      renderAutomationRuntimeStatus(
        "error",
        "设置未生效",
        result.message || "请修复提示的问题后重试。",
      );
    }
    return result;
  } finally {
    automationSavePending = false;
    setAutomationControlsPending(false);
  }
}

async function saveImportOptionsConfig() {
  const payload = buildImportOptionsPayload();
  const result = await requestApi("POST", "/config/section", {
    section: "import_options",
    data: payload,
    revision: currentConfigRevision,
  });
  showToast(result.message || "入库名称规范已保存");
  if (result.code === 200) {
    await loadDirectoryConfig();
  }
}

async function saveAdvancedSystemConfig() {
  const payload = buildAdvancedSystemPayload();
  const result = await requestApi("POST", "/config", {
    ...payload,
    _revision: currentConfigRevision,
  });
  showToast(result.message || "系统设置已保存");
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
      need_write:
        document.querySelector('input[name="cfg-source-after-done"]:checked')
          ?.value !== "preserve_all",
    },
    recycle: { label: "回收目录", path: paths.recycle_dir, need_write: true },
    fallback: {
      label: "兜底入库目录",
      path: paths.library_root && paths.fallback_dir
        ? `${paths.library_root.replace(/\/$/, "")}/${paths.fallback_dir}`
        : paths.library_root,
      need_write: true,
    },
    library: { label: "默认片库", path: paths.library_root, need_write: true },
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
  const pathRules = Array.isArray(currentConfigSnapshot?.path_rules)
    ? currentConfigSnapshot.path_rules
    : [];
  if (pathRules.length === 0) {
    showToast("当前还没有可测试的入库规则");
    return;
  }
  const missingIndex = pathRules.findIndex((rule) => !String(rule?.library_root_id || "").trim());
  if (missingIndex >= 0) {
    showToast(`第 ${missingIndex + 1} 条规则尚未选择目标片库`);
    return;
  }
  const rootIds = Array.from(new Set(pathRules.map((rule) => rule.library_root_id)));
  for (const rootId of rootIds) {
    const root = libraryRootById(rootId);
    if (!root) {
      showToast(`有规则引用了不存在的片库：${rootId}`);
      return;
    }
    const result = await requestApi("POST", "/path/test", {
      path: root.path,
      need_write: true,
    });
    if (result.code !== 200 || !result.data?.ok) {
      showPathTestFeedback(result, root.name);
      return;
    }
  }
  showToast(`已检查 ${rootIds.length} 个规则目标片库，权限正常`);
}

async function testProviderConnection(providerType) {
  showToast("正在测试 Provider 连通性...");
  const result = await requestApi(
    "POST",
    `/providers/${encodeURIComponent(providerType)}/test`,
    {},
  );
  const data = result.data || {};
  showToast(data.message || result.message || "Provider 测试已完成");
}

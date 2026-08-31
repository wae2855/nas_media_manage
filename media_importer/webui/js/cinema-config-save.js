// cinema-config-save.js — 配置保存与测试函数
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
  await saveConfigPayload(payload, "源目录配置已保存");
}

async function saveTempConfig() {
  const payload = buildTempConfigPayload();
  const paths = currentPathSnapshot();
  if (!payload.temp_dir) {
    showToast("中转目录路径为必填项");
    return;
  }
  const conflicts = validateDirectoryConflicts(paths);
  if (conflicts.length) {
    showToast(conflicts.join("；"));
    return;
  }
  await saveConfigPayload(payload, "中转目录配置已保存");
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

async function saveLibraryRootsConfig({ migrateLegacy = false } = {}) {
  const roots = normalizedLibraryRoots();
  const defaultId = defaultLibraryRootId();
  return saveConfigPayload({
    _migrate_legacy_library_rules: migrateLegacy,
    library_roots: roots,
    default_library_root_id: defaultId,
    library_root: libraryRootById(defaultId)?.path || "",
  }, migrateLegacy ? "旧片库规则已迁移并保存" : "目标片库已保存");
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
  const watcher = currentConfigSnapshot?.file_watcher || {};
  const enabled = !!document.getElementById("cfg-auto-watcher-enabled")
    ?.checked;
  const pollInterval = Number(
    document.getElementById("cfg-auto-watcher-poll-interval")?.value || 60,
  );
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
  if (result.code === 200) await loadDirectoryConfig();
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
    temp: { label: "中转目录", path: paths.temp_dir, need_write: true },
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
  const rootIds = Array.from(new Set(
    pathRules.map((rule) => rule.library_root_id || defaultLibraryRootId()),
  ));
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

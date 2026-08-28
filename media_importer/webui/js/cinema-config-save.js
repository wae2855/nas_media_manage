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
  if (!payload.source_dir) {
    showToast("源目录路径为必填项");
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

async function saveRulesConfig() {
  const payload = buildRulesConfigPayload();
  if (!Array.isArray(payload.path_rules) || payload.path_rules.length === 0) {
    showToast("当前还没有可保存的入库规则，请先新增至少一条规则");
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
  const result = await requestApi("POST", "/config", {
    _revision: currentConfigRevision,
    file_watcher: {
      ...watcher,
      enabled,
      stability_window_seconds: Number(watcher.stability_window_seconds || 120),
    },
  });
  showToast(
    result.message || (enabled ? "自动运行已启用" : "自动运行保持关闭"),
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

async function saveSecurityConfig() {
  const payload = buildServerConfigPayload();
  const result = await requestApi("POST", "/config/section", {
    section: "server",
    data: payload,
    revision: currentConfigRevision,
  });
  showToast(result.message || "安全配置已保存");
  if (result.code === 200) {
    await loadDirectoryConfig();
  }
}

async function saveAdvancedSystemConfig() {
  const payload = buildAdvancedSystemPayload();
  if (!payload.log_dir) {
    showToast("日志目录不能为空");
    return;
  }
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
      need_write: !!document.getElementById("cfg-source-cleaner-enabled-inline")
        ?.checked,
    },
    temp: { label: "中转目录", path: paths.temp_dir, need_write: true },
    recycle: { label: "回收目录", path: paths.recycle_dir, need_write: true },
    fallback: {
      label: "兜底入库目录",
      path: paths.fallback_dir,
      need_write: true,
    },
    log: {
      label: "日志目录",
      path: normalizePathValue(
        document.getElementById("cfg-log_dir-inline")?.value,
      ),
      need_write: true,
    },
    resource: {
      label: "资源目录",
      path: normalizePathValue(
        document.getElementById("cfg-resource_dir-inline")?.value,
      ),
      need_write: true,
    },
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
  showToast("正在检查全部入库规则目录权限...");
  const result = await requestApi("POST", "/config/check-permission", {
    source_dir: "",
    temp_dir: "",
    log_dir: "",
    path_rules: pathRules,
  });
  if (result.code !== 200 || !result.data) {
    showToast(result.message || "入库规则目录权限检查失败");
    return;
  }
  if (Array.isArray(result.data.issues) && result.data.issues.length > 0) {
    buildPermissionIssueDialog(result.data.issues, "入库规则目录权限不足");
    return;
  }
  showToast("所有入库规则目录权限正常");
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

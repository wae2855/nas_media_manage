// cinema-config-payloads.js — 配置 payload 构建函数
// 从 cinema-config.js 提取的 payload 构建逻辑

function buildSourceConfigPayload() {
  const currentSourcePolicy = currentConfigSnapshot?.source_policy || {};
  const sourceMode =
    document.querySelector('input[name="cfg-source-after-done"]:checked')
      ?.value || "preserve_all";
  const sourceCleanerMode =
    document.querySelector(
      'input[name="cfg-source_cleaner-cleanup_mode_inline"]:checked',
    )?.value || "media_and_related";
  const unitPatternField = document.getElementById(
    "cfg-source-unit-incomplete-patterns",
  );
  return {
    source_policy: {
      mode: sourceMode,
      cleanup_source_after_done: sourceMode === "recycle_source_unit",
      scan_recursive: !!document.getElementById(
        "cfg-source-recursive-toggle-inline",
      )?.checked,
      scan_max_depth:
        Number(
          document.getElementById("cfg-source-depth-inline")?.value || 5,
        ) || 5,
      unit_settle_seconds:
        Number(
          document.getElementById("cfg-source-unit-settle")?.value ||
            currentSourcePolicy.unit_settle_seconds ||
            120,
        ) || 120,
      unit_incomplete_patterns: unitPatternField
        ? parseMultilineValue("cfg-source-unit-incomplete-patterns")
        : currentSourcePolicy.unit_incomplete_patterns || [
            "*.part",
            "*.partial",
            "*.aria2",
            "*.!qB",
            "*.crdownload",
          ],
    },
    source_cleaner: {
      enabled: sourceMode === "preserve_media",
      cleanup_mode: sourceCleanerMode,
      ai_enabled: sourceMode === "preserve_media" && !!document.getElementById(
        "cfg-source_cleaner-ai_enabled-inline",
      )?.checked,
      merge_strategy:
        document.getElementById("cfg-source_cleaner-merge_strategy-inline")
          ?.value || "intersection",
      delete_extensions: parseMultilineValue(
        "cfg-source_cleaner-delete_extensions-inline",
      ),
      protect_extensions: parseMultilineValue(
        "cfg-source_cleaner-protect_extensions-inline",
      ),
      blacklist_patterns: parseMultilineValue(
        "cfg-source_cleaner-blacklist_patterns-inline",
      ),
      junk_video_max_size_mb:
        Number(
          document.getElementById(
            "cfg-source_cleaner-junk_video_max_size_mb-inline",
          )?.value || 0,
        ) || 0,
      cleanup_empty_dirs: !!document.getElementById(
        "cfg-source_cleaner-cleanup_empty_dirs-inline",
      )?.checked,
      schedule: String(
        document.getElementById("cfg-source_cleaner-schedule-inline")?.value ||
          "",
      ).trim(),
    },
  };
}

function buildTempConfigPayload() {
  return {
    temp_dir: normalizePathValue(
      document.getElementById("cfg-temp-inline")?.value,
    ),
  };
}

function buildRecycleConfigPayload() {
  return {
    source_policy: {
      recycle_dir: normalizePathValue(
        document.getElementById("cfg-recycle-inline")?.value,
      ),
      recycle_retention_days:
        Number(
          document.getElementById("cfg-recycle-retention-inline")?.value || 0,
        ) || 0,
    },
  };
}

function buildRulesConfigPayload() {
  const roots = normalizedLibraryRoots();
  const defaultId = defaultLibraryRootId();
  return {
    library_roots: roots,
    default_library_root_id: defaultId,
    library_root: libraryRootById(defaultId)?.path || "",
    path_rules: Array.isArray(currentConfigSnapshot?.path_rules)
      ? currentConfigSnapshot.path_rules
      : [],
    fallback_library_root_id:
      document.getElementById("cfg-fallback-root-inline")?.value || defaultId,
    fallback_dir: normalizePathValue(
      document.getElementById("cfg-fallback-inline")?.value,
    ),
  };
}

function buildImportOptionsPayload() {
  return {
    manual_review: {
      enabled: !!document.getElementById("cfg-manual_review-enabled-inline")
        ?.checked,
    },
    duplicate_handling: {
      enabled: true,
      strategy: "confirm",
    },
    filename_templates: {
      movie: String(
        document.getElementById("cfg-filename_templates-movie-inline")?.value ||
          "",
      ).trim(),
      tv: String(
        document.getElementById("cfg-filename_templates-tv-inline")?.value ||
          "",
      ).trim(),
      subtitle: String(
        document.getElementById("cfg-filename_templates-subtitle-inline")
          ?.value || "",
      ).trim(),
    },
  };
}

function getProviderDefinition(providerType) {
  return currentProviderDefinitions.find((item) => item.type === providerType);
}

function inferProviderFieldValue(field, providerType) {
  const inputId = `cfg-provider-inline-${providerType}-${field.key}`;
  const element = document.getElementById(inputId);
  if (!element) return undefined;
  if (field.type === "checkbox") return !!element.checked;
  if (field.type === "number")
    return Number(element.value || field.default || 0) || 0;
  const raw = String(element.value || "");
  return raw;
}

function buildSingleProviderConfig(providerType) {
  const definition = getProviderDefinition(providerType);
  const existingProviders = Array.isArray(
    currentConfigSnapshot?.metadata?.providers,
  )
    ? currentConfigSnapshot.metadata.providers
    : [];
  const existing =
    existingProviders.find((item) => item.type === providerType) || {};
  const config = {
    ...existing,
    type: providerType,
    enabled: !!document.querySelector(
      `[data-provider-toggle="${providerType}"]`,
    )?.checked,
  };
  const fields = Array.isArray(definition?.config_schema?.fields)
    ? definition.config_schema.fields
    : [];
  fields.forEach((field) => {
    const value = inferProviderFieldValue(field, providerType);
    if (value === undefined) return;
    if (field.key === "api_key") {
      if (!value) {
        if (existing.api_key) config.api_key = existing.api_key;
        else config.api_key = "***";
        return;
      }
    }
    config[field.key] = value;
  });
  return config;
}

function buildAllProvidersPayload() {
  const existingProviders = Array.isArray(
    currentConfigSnapshot?.metadata?.providers,
  )
    ? currentConfigSnapshot.metadata.providers
    : [];
  const providerTypes = Array.from(
    new Set([
      ...currentProviderDefinitions.map((item) => item.type),
      ...existingProviders.map((item) => item.type).filter(Boolean),
    ]),
  );
  const providers = providerTypes.map((providerType) =>
    buildSingleProviderConfig(providerType),
  );
  return { metadata: { providers } };
}

function buildProvidersPayloadFor(providerType) {
  const existingProviders = Array.isArray(
    currentConfigSnapshot?.metadata?.providers,
  )
    ? currentConfigSnapshot.metadata.providers
    : [];
  const nextProvider = buildSingleProviderConfig(providerType);
  const merged = [];
  let replaced = false;
  existingProviders.forEach((provider) => {
    if (provider.type === providerType) {
      merged.push(nextProvider);
      replaced = true;
    } else {
      merged.push(provider);
    }
  });
  if (!replaced) merged.push(nextProvider);
  return { metadata: { providers: merged } };
}

function preserveApiKey(section, inputId) {
  const value = String(document.getElementById(inputId)?.value || "").trim();
  const saved = currentConfigSnapshot?.[section]?.api_key || "";
  return value || saved || "***";
}

// T2.6 plan: 新增 ai_prompts / ai_scene_strategy 两个 payload 函数
// (T2.10: buildAiApikeyPayload 已删除，复用 buildAiAssistPayload + buildAiSearchPayload)

function buildLlmPayload() {
  const preserved = preserveApiKey("llm", "cfg-llm-api_key");
  return {
    llm: {
      base_url: String(
        document.getElementById("cfg-llm-base_url")?.value || "",
      ).trim(),
      model: String(
        document.getElementById("cfg-llm-model")?.value || "",
      ).trim(),
      api_key: preserved,
      fallback_model: String(
        document.getElementById("cfg-llm-fallback_model")?.value || "",
      ).trim(),
      timeout:
        Number(document.getElementById("cfg-llm-timeout")?.value || 30) || 30,
      max_retries:
        Number(document.getElementById("cfg-llm-max_retries")?.value || 2) || 2,
      retry_delay:
        Number(document.getElementById("cfg-llm-retry_delay")?.value || 3) || 3,
      verify_ssl: !!document.getElementById("cfg-llm-verify_ssl")?.checked,
    },
  };
}

function buildAdvancedSystemPayload() {
  return {
    task_queue: {
      max_concurrent:
        Number(
          document.getElementById("cfg-task_queue-max_concurrent-inline")
            ?.value || 1,
        ) || 1,
    },
    video_extensions: parseMultilineValue("cfg-video_extensions-inline").map(
      (item) => (item.startsWith(".") ? item : `.${item}`),
    ),
    subtitle_extensions: parseMultilineValue(
      "cfg-subtitle_extensions-inline",
    ).map((item) => (item.startsWith(".") ? item : `.${item}`)),
  };
}

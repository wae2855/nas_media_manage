// cinema-config-payloads.js — 配置 payload 构建函数
// 从 cinema-config.js 提取的 payload 构建逻辑

function buildSourceConfigPayload() {
  const sourceCleanerMode =
    document.querySelector(
      'input[name="cfg-source_cleaner-cleanup_mode_inline"]:checked',
    )?.value || "media_only";
  return {
    source_dir: normalizePathValue(
      document.getElementById("cfg-source-inline")?.value,
    ),
    source_policy: {
      scan_recursive: !!document.getElementById(
        "cfg-source-recursive-toggle-inline",
      )?.checked,
      scan_max_depth:
        Number(
          document.getElementById("cfg-source-depth-inline")?.value || 5,
        ) || 5,
    },
    source_cleaner: {
      enabled: !!document.getElementById("cfg-source-cleaner-enabled-inline")
        ?.checked,
      cleanup_mode: sourceCleanerMode,
      ai_enabled: !!document.getElementById(
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
  return {
    path_rules: Array.isArray(currentConfigSnapshot?.path_rules)
      ? currentConfigSnapshot.path_rules
      : [],
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
      strategy:
        document.getElementById("cfg-duplicate_handling-strategy-inline")
          ?.value || "skip",
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

function buildAiAssistPayload() {
  return {
    ai_assist: {
      base_url: String(
        document.getElementById("cfg-ai_assist-base_url")?.value || "",
      ).trim(),
      model: String(
        document.getElementById("cfg-ai_assist-model")?.value || "",
      ).trim(),
      api_key: preserveApiKey("ai_assist", "cfg-ai_assist-api_key"),
      timeout:
        Number(document.getElementById("cfg-ai_assist-timeout")?.value || 30) ||
        30,
      max_retries:
        Number(
          document.getElementById("cfg-ai_assist-max_retries")?.value || 2,
        ) || 2,
      retry_delay:
        Number(
          document.getElementById("cfg-ai_assist-retry_delay")?.value || 3,
        ) || 3,
      verify_ssl: !!document.getElementById("cfg-ai_assist-verify_ssl")
        ?.checked,
      prompt_title_clean: String(
        document.getElementById("cfg-ai_assist-prompt_title_clean")?.value ||
          "",
      ),
      prompt_match_assist: String(
        document.getElementById("cfg-ai_assist-prompt_match_assist")?.value ||
          "",
      ),
      prompt_dimension_mapping: String(
        document.getElementById("cfg-ai_assist-prompt_dimension_mapping")
          ?.value || "",
      ),
      prompt_source_clean: String(
        document.getElementById("cfg-ai_assist-prompt_source_clean")?.value ||
          "",
      ),
    },
  };
}

function buildAiSearchPayload() {
  return {
    ai_search: {
      provider: String(
        document.getElementById("cfg-ai_search-provider")?.value || "",
      ).trim(),
      model: String(
        document.getElementById("cfg-ai_search-model")?.value || "",
      ).trim(),
      search_type: String(
        document.getElementById("cfg-ai_search-search_type")?.value || "",
      ).trim(),
      api_key: preserveApiKey("ai_search", "cfg-ai_search-api_key"),
      base_url: String(
        document.getElementById("cfg-ai_search-base_url")?.value || "",
      ).trim(),
      timeout:
        Number(document.getElementById("cfg-ai_search-timeout")?.value || 30) ||
        30,
      max_retries:
        Number(
          document.getElementById("cfg-ai_search-max_retries")?.value || 2,
        ) || 2,
      retry_delay:
        Number(
          document.getElementById("cfg-ai_search-retry_delay")?.value || 3,
        ) || 3,
      verify_ssl: !!document.getElementById("cfg-ai_search-verify_ssl")
        ?.checked,
      prompt_dimension_supplement: String(
        document.getElementById("cfg-ai_search-prompt_dimension_supplement")
          ?.value || "",
      ),
    },
  };
}

function buildAiConfigPayload() {
  return {
    ai_assist: buildAiAssistPayload().ai_assist,
    ai_search: buildAiSearchPayload().ai_search,
  };
}

// T2.6 plan: 新增 ai_prompts / ai_scene_strategy 两个 payload 函数
// (T2.10: buildAiApikeyPayload 已删除，复用 buildAiAssistPayload + buildAiSearchPayload)

function buildAiPromptsPayload() {
  return {
    ai_assist: {
      prompt_title_clean: String(
        document.getElementById("cfg-ai_assist-prompt_title_clean")?.value ||
          "",
      ),
      prompt_match_assist: String(
        document.getElementById("cfg-ai_assist-prompt_match_assist")?.value ||
          "",
      ),
      prompt_dimension_mapping: String(
        document.getElementById("cfg-ai_assist-prompt_dimension_mapping")
          ?.value || "",
      ),
      prompt_source_clean: String(
        document.getElementById("cfg-ai_assist-prompt_source_clean")?.value ||
          "",
      ),
    },
    ai_search: {
      prompt_dimension_supplement: String(
        document.getElementById("cfg-ai_search-prompt_dimension_supplement")
          ?.value || "",
      ),
    },
  };
}

function buildAiSceneStrategyPayload() {
  const scenes = [
    "dimension_supplement",
    "dimension_mapping",
    "title_clean",
    "match_assist",
    "source_clean",
  ];
  const data = {};
  scenes.forEach((scene) => {
    const primaryEl = document.querySelector(`[data-scene-primary="${scene}"]`);
    const fallbackEl = document.querySelector(
      `[data-scene-fallback="${scene}"]`,
    );
    data[scene] = {
      primary: String(primaryEl?.value || "").trim(),
      fallback: String(fallbackEl?.value || "").trim(),
    };
  });
  return data;
}

function buildServerConfigPayload() {
  const currentServer = currentConfigSnapshot?.server || {};
  const apiKeyValue = String(
    document.getElementById("cfg-server_api_key-inline")?.value || "",
  ).trim();
  return {
    server: {
      port:
        Number(
          document.getElementById("cfg-server_port-inline")?.value || 9855,
        ) || 9855,
      api_key: apiKeyValue || currentServer.api_key || "***",
    },
  };
}

function buildHermesConfigPayload() {
  const currentHermes = currentConfigSnapshot?.hermes?.webhook || {};
  const secretValue = String(
    document.getElementById("cfg-hermes_webhook_secret-inline")?.value || "",
  ).trim();
  const events = [];
  if (document.getElementById("cfg-hermes_event_batch_start-inline")?.checked)
    events.push("batch_start");
  if (
    document.getElementById("cfg-hermes_event_batch_complete-inline")?.checked
  )
    events.push("batch_complete");
  if (document.getElementById("cfg-hermes_event_program_error-inline")?.checked)
    events.push("program_error");
  return {
    hermes: {
      enabled: !!document.getElementById("cfg-hermes_enabled-inline")?.checked,
      webhook: {
        base_url: String(
          document.getElementById("cfg-hermes_webhook_base_url-inline")
            ?.value || "",
        ).trim(),
        route_name: String(
          document.getElementById("cfg-hermes_webhook_route_name-inline")
            ?.value || "",
        ).trim(),
        secret: secretValue || currentHermes.secret || "***",
        timeout:
          Number(
            document.getElementById("cfg-hermes_webhook_timeout-inline")
              ?.value || 30,
          ) || 30,
        max_retries:
          Number(
            document.getElementById("cfg-hermes_webhook_max_retries-inline")
              ?.value || 3,
          ) || 3,
        retry_delay:
          Number(
            document.getElementById("cfg-hermes_webhook_retry_delay-inline")
              ?.value || 5,
          ) || 5,
        verify_ssl: !!document.getElementById(
          "cfg-hermes_webhook_verify_ssl-inline",
        )?.checked,
        events,
      },
    },
  };
}

function buildAdvancedSystemPayload() {
  return {
    log_dir: normalizePathValue(
      document.getElementById("cfg-log_dir-inline")?.value,
    ),
    resource_dir: normalizePathValue(
      document.getElementById("cfg-resource_dir-inline")?.value,
    ),
    task_queue: {
      max_concurrent:
        Number(
          document.getElementById("cfg-task_queue-max_concurrent-inline")
            ?.value || 1,
        ) || 1,
    },
    file_watcher: {
      enabled: !!document.getElementById("cfg-file_watcher-enabled-inline")
        ?.checked,
      poll_interval:
        Number(
          document.getElementById("cfg-file_watcher-poll_interval-inline")
            ?.value || 60,
        ) || 60,
    },
    video_extensions: parseMultilineValue("cfg-video_extensions-inline").map(
      (item) => (item.startsWith(".") ? item : `.${item}`),
    ),
    subtitle_extensions: parseMultilineValue(
      "cfg-subtitle_extensions-inline",
    ).map((item) => (item.startsWith(".") ? item : `.${item}`)),
  };
}

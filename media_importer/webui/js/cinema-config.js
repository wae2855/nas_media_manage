// cinema-config.js — 配置页面构建、保存、测试与渲染

function buildSourceConfigPayload() {
    const sourceCleanerMode = document.querySelector('input[name="cfg-source_cleaner-cleanup_mode_inline"]:checked')?.value || "media_only";
    return {
        source_dir: normalizePathValue(document.getElementById("cfg-source-inline")?.value),
        source_policy: {
            scan_recursive: !!document.getElementById("cfg-source-recursive-toggle-inline")?.checked,
            scan_max_depth: Number(document.getElementById("cfg-source-depth-inline")?.value || 5) || 5,
        },
        source_cleaner: {
            enabled: !!document.getElementById("cfg-source-cleaner-enabled-inline")?.checked,
            cleanup_mode: sourceCleanerMode,
            ai_enabled: !!document.getElementById("cfg-source_cleaner-ai_enabled-inline")?.checked,
            merge_strategy: document.getElementById("cfg-source_cleaner-merge_strategy-inline")?.value || "intersection",
            delete_extensions: parseMultilineValue("cfg-source_cleaner-delete_extensions-inline"),
            protect_extensions: parseMultilineValue("cfg-source_cleaner-protect_extensions-inline"),
            blacklist_patterns: parseMultilineValue("cfg-source_cleaner-blacklist_patterns-inline"),
            junk_video_max_size_mb: Number(document.getElementById("cfg-source_cleaner-junk_video_max_size_mb-inline")?.value || 0) || 0,
            cleanup_empty_dirs: !!document.getElementById("cfg-source_cleaner-cleanup_empty_dirs-inline")?.checked,
            schedule: String(document.getElementById("cfg-source_cleaner-schedule-inline")?.value || "").trim(),
            ai_prompt: String(document.getElementById("cfg-source_cleaner-ai_prompt-inline")?.value || ""),
        },
    };
}

function buildTempConfigPayload() {
    return {
        temp_dir: normalizePathValue(document.getElementById("cfg-temp-inline")?.value),
    };
}

function buildRecycleConfigPayload() {
    return {
        source_policy: {
            recycle_dir: normalizePathValue(document.getElementById("cfg-recycle-inline")?.value),
            recycle_retention_days: Number(document.getElementById("cfg-recycle-retention-inline")?.value || 0) || 0,
        },
    };
}

function buildRulesConfigPayload() {
    return {
        path_rules: Array.isArray(currentConfigSnapshot?.path_rules) ? currentConfigSnapshot.path_rules : [],
        fallback_dir: normalizePathValue(document.getElementById("cfg-fallback-inline")?.value),
    };
}

function buildImportOptionsPayload() {
    return {
        manual_review: {
            enabled: !!document.getElementById("cfg-manual_review-enabled-inline")?.checked,
        },
        duplicate_handling: {
            strategy: document.getElementById("cfg-duplicate_handling-strategy-inline")?.value || "skip",
        },
        filename_templates: {
            movie: String(document.getElementById("cfg-filename_templates-movie-inline")?.value || "").trim(),
            tv: String(document.getElementById("cfg-filename_templates-tv-inline")?.value || "").trim(),
            subtitle: String(document.getElementById("cfg-filename_templates-subtitle-inline")?.value || "").trim(),
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
    if (field.type === "number") return Number(element.value || field.default || 0) || 0;
    const raw = String(element.value || "");
    return raw;
}

function buildSingleProviderConfig(providerType) {
    const definition = getProviderDefinition(providerType);
    const existingProviders = Array.isArray(currentConfigSnapshot?.metadata?.providers) ? currentConfigSnapshot.metadata.providers : [];
    const existing = existingProviders.find((item) => item.type === providerType) || {};
    const config = {
        ...existing,
        type: providerType,
        enabled: !!document.querySelector(`[data-provider-toggle="${providerType}"]`)?.checked,
    };
    const fields = Array.isArray(definition?.config_schema?.fields) ? definition.config_schema.fields : [];
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
    const existingProviders = Array.isArray(currentConfigSnapshot?.metadata?.providers) ? currentConfigSnapshot.metadata.providers : [];
    const providerTypes = Array.from(new Set([
        ...currentProviderDefinitions.map((item) => item.type),
        ...existingProviders.map((item) => item.type).filter(Boolean),
    ]));
    const providers = providerTypes.map((providerType) => buildSingleProviderConfig(providerType));
    return { metadata: { providers } };
}

function buildProvidersPayloadFor(providerType) {
    const existingProviders = Array.isArray(currentConfigSnapshot?.metadata?.providers) ? currentConfigSnapshot.metadata.providers : [];
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

function buildLlmConfigPayload() {
    const currentLlm = currentConfigSnapshot?.llm || {};
    const apiKeyValue = String(document.getElementById("cfg-llm_api_key-inline")?.value || "").trim();
    return {
        llm: {
            provider: document.getElementById("cfg-llm_provider-inline")?.value || "openai",
            api_key: apiKeyValue || currentLlm.api_key || "***",
            base_url: String(document.getElementById("cfg-llm_base_url-inline")?.value || "").trim(),
            model: String(document.getElementById("cfg-llm_model-inline")?.value || "").trim(),
            fallback_model: String(document.getElementById("cfg-llm_fallback_model-inline")?.value || "").trim(),
            fast_model: String(document.getElementById("cfg-llm_fast_model-inline")?.value || "").trim(),
            timeout: Number(document.getElementById("cfg-llm_timeout-inline")?.value || 30) || 30,
            max_retries: Number(document.getElementById("cfg-llm_max_retries-inline")?.value || 2) || 2,
            retry_delay: Number(document.getElementById("cfg-llm_retry_delay-inline")?.value || 3) || 3,
            confidence_threshold: Number(document.getElementById("cfg-llm_confidence_threshold-inline")?.value || 0.8) || 0.8,
            verify_ssl: !!document.getElementById("cfg-llm_verify_ssl-inline")?.checked,
        },
    };
}

function buildServerConfigPayload() {
    const currentServer = currentConfigSnapshot?.server || {};
    const apiKeyValue = String(document.getElementById("cfg-server_api_key-inline")?.value || "").trim();
    return {
        server: {
            port: Number(document.getElementById("cfg-server_port-inline")?.value || 9855) || 9855,
            api_key: apiKeyValue || currentServer.api_key || "***",
        },
    };
}

function buildHermesConfigPayload() {
    const currentHermes = currentConfigSnapshot?.hermes?.webhook || {};
    const secretValue = String(document.getElementById("cfg-hermes_webhook_secret-inline")?.value || "").trim();
    const events = [];
    if (document.getElementById("cfg-hermes_event_batch_start-inline")?.checked) events.push("batch_start");
    if (document.getElementById("cfg-hermes_event_batch_complete-inline")?.checked) events.push("batch_complete");
    if (document.getElementById("cfg-hermes_event_program_error-inline")?.checked) events.push("program_error");
    return {
        hermes: {
            enabled: !!document.getElementById("cfg-hermes_enabled-inline")?.checked,
            webhook: {
                base_url: String(document.getElementById("cfg-hermes_webhook_base_url-inline")?.value || "").trim(),
                route_name: String(document.getElementById("cfg-hermes_webhook_route_name-inline")?.value || "").trim(),
                secret: secretValue || currentHermes.secret || "***",
                timeout: Number(document.getElementById("cfg-hermes_webhook_timeout-inline")?.value || 30) || 30,
                max_retries: Number(document.getElementById("cfg-hermes_webhook_max_retries-inline")?.value || 3) || 3,
                retry_delay: Number(document.getElementById("cfg-hermes_webhook_retry_delay-inline")?.value || 5) || 5,
                verify_ssl: !!document.getElementById("cfg-hermes_webhook_verify_ssl-inline")?.checked,
                events,
            },
        },
    };
}

function buildAdvancedSystemPayload() {
    return {
        log_dir: normalizePathValue(document.getElementById("cfg-log_dir-inline")?.value),
        resource_dir: normalizePathValue(document.getElementById("cfg-resource_dir-inline")?.value),
        task_queue: {
            max_concurrent: Number(document.getElementById("cfg-task_queue-max_concurrent-inline")?.value || 1) || 1,
        },
        file_watcher: {
            enabled: !!document.getElementById("cfg-file_watcher-enabled-inline")?.checked,
            poll_interval: Number(document.getElementById("cfg-file_watcher-poll_interval-inline")?.value || 60) || 60,
        },
        video_extensions: parseMultilineValue("cfg-video_extensions-inline").map((item) => item.startsWith(".") ? item : `.${item}`),
        subtitle_extensions: parseMultilineValue("cfg-subtitle_extensions-inline").map((item) => item.startsWith(".") ? item : `.${item}`),
    };
}

async function saveConfigPayload(payload, successText) {
    const result = await requestApi("POST", "/config", payload);
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
    const payload = providerType ? buildProvidersPayloadFor(providerType) : buildAllProvidersPayload();
    const result = await requestApi("POST", "/config/section", {
        section: "metadata.providers",
        data: payload,
    });
    showToast(result.message || "Provider 配置已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
}

async function saveLlmConfig() {
    const payload = buildLlmConfigPayload();
    if (!payload.llm.base_url) {
        showToast("接口地址为必填项");
        return;
    }
    if (!payload.llm.model) {
        showToast("主要模型ID为必填项");
        return;
    }
    const result = await requestApi("POST", "/config/section", {
        section: "llm",
        data: payload,
    });
    showToast(result.message || "AI 配置已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
}

async function saveImportOptionsConfig() {
    const payload = buildImportOptionsPayload();
    const result = await requestApi("POST", "/config/section", {
        section: "import_options",
        data: payload,
    });
    showToast(result.message || "入库名称规范已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
}

async function saveConfidenceConfig() {
    const payload = { confidence: typeof getConfidenceConfig === "function" ? getConfidenceConfig() : {} };
    const result = await requestApi("POST", "/config/section", {
        section: "confidence",
        data: payload,
    });
    showToast(result.message || "置信度配置已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
}

async function saveSecurityConfig() {
    const payload = buildServerConfigPayload();
    const result = await requestApi("POST", "/config/section", {
        section: "server",
        data: payload,
    });
    showToast(result.message || "安全配置已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
}

async function saveHermesConfig() {
    const payload = buildHermesConfigPayload();
    const result = await requestApi("POST", "/config/section", {
        section: "hermes",
        data: payload,
    });
    showToast(result.message || "Hermes 通知配置已保存");
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
    const result = await requestApi("POST", "/config", payload);
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
            need_write: !!document.getElementById("cfg-source-cleaner-enabled-inline")?.checked,
        },
        temp: { label: "中转目录", path: paths.temp_dir, need_write: true },
        recycle: { label: "回收目录", path: paths.recycle_dir, need_write: true },
        fallback: { label: "兜底入库目录", path: paths.fallback_dir, need_write: true },
        log: {
            label: "日志目录",
            path: normalizePathValue(document.getElementById("cfg-log_dir-inline")?.value),
            need_write: true,
        },
        resource: {
            label: "资源目录",
            path: normalizePathValue(document.getElementById("cfg-resource_dir-inline")?.value),
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
    const pathRules = Array.isArray(currentConfigSnapshot?.path_rules) ? currentConfigSnapshot.path_rules : [];
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
    const result = await requestApi("POST", `/providers/${encodeURIComponent(providerType)}/test`, {});
    const data = result.data || {};
    showToast(data.message || result.message || "Provider 测试已完成");
}

async function previewProvider(providerType) {
    const query = await showPromptModal({
        title: "Provider 预览",
        message: "输入一个影视名称，用于快速预览当前 Provider 的搜索与详情能力。",
        placeholder: "例如：Dune.Part.Two.2024.1080p.mkv",
    });
    if (!query) return;
    const mediaType = /S\d{1,2}E\d{1,2}|第\d+季|第\d+集/i.test(query) ? "tv" : "movie";
    showToast("正在生成 Provider 预览...");
    const result = await requestApi("POST", `/providers/${encodeURIComponent(providerType)}/preview`, {
        query,
        type: mediaType,
    });
    if (result.code !== 200 || !result.data) {
        showToast(result.message || "Provider 预览失败");
        return;
    }
    if (!result.data.found) {
        showToast(result.data.message || "未找到匹配结果");
        return;
    }
    const preview = result.data;
    const lines = [
        `标题：${preview.title || "-"}`,
        `原标题：${preview.original_title || "-"}`,
        `年份：${preview.year || "-"}`,
        `类型：${preview.type || "-"}`,
        `评分：${preview.vote_average ?? "-"}`,
        "",
        `${preview.overview || "暂无简介"}`,
    ];
    showTextModal("Provider 预览结果", lines.join("\n"));
}

async function testLlmConnection() {
    const payload = buildLlmConfigPayload().llm;
    if (!payload.base_url) {
        showToast("请先填写接口地址");
        return;
    }
    if (!payload.model) {
        showToast("请先填写主要模型ID");
        return;
    }
    showToast("正在测试 LLM 连通性...");
    const result = await requestApi("POST", "/config/test-llm", {
        provider: payload.provider,
        api_key: payload.api_key,
        base_url: payload.base_url,
        model: payload.model,
    });
    const data = result.data || {};
    showToast(data.message || result.message || "LLM 测试已完成");
}

async function testHermesConnection() {
    const payload = buildHermesConfigPayload().hermes?.webhook || {};
    if (!payload.base_url) {
        showToast("请先填写 Webhook 地址");
        return;
    }
    if (!payload.route_name) {
        showToast("请先填写路由名称");
        return;
    }
    showToast("正在测试 Hermes 通知链路...");
    const result = await requestApi("POST", "/config/test-hermes", payload);
    const data = result.data || {};
    showToast(data.message || result.message || "Hermes 测试已完成");
}

function buildProviderField(providerType, field, rawValue) {
    const value = rawValue ?? field.default ?? "";
    const id = `cfg-provider-inline-${providerType}-${field.key}`;
    const hint = field.description || field.help_text || field.placeholder || "";
    if (field.type === "select") {
        const options = (field.options || []).map((option) => {
            const selected = option.value === value ? " selected" : "";
            return `<option value="${escapeHtml(option.value)}"${selected}>${escapeHtml(option.label)}</option>`;
        }).join("");
        return `
            <label class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <select id="${id}">${options}</select>
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </label>`;
    }
    if (field.type === "number") {
        return `
            <label class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <input id="${id}" type="number" value="${escapeHtml(value)}" />
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </label>`;
    }
    if (field.type === "password") {
        const placeholder = field.key === "api_key" && value === "***" ? "已保存，留空保持不变" : (field.placeholder || field.label || "");
        const val = value === "***" ? "" : value;
        return `
            <label class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <input id="${id}" type="password" value="${escapeHtml(val)}" placeholder="${escapeHtml(placeholder)}" />
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </label>`;
    }
    if (field.type === "checkbox") {
        return `
            <article class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <label class="toggle-row-inline">
                    <input id="${id}" type="checkbox"${value ? " checked" : ""} />
                    <b>${escapeHtml(field.checkbox_label || "启用")}</b>
                </label>
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </article>`;
    }
    return `
        <label class="form-card">
            <span>${escapeHtml(field.label || field.key)}</span>
            <input id="${id}" type="text" value="${escapeHtml(value)}" placeholder="${escapeHtml(field.placeholder || "")}" />
            ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
        </label>`;
}

function renderInlineProviderConfigs(providerDefs, savedProviders) {
    const host = document.getElementById("provider-inline-stack");
    if (!host) return;
    if (!Array.isArray(providerDefs) || providerDefs.length === 0) {
        host.innerHTML = '<article class="provider-inline-empty">当前没有可用的 Provider</article>';
        return;
    }
    currentProviderDefinitions = providerDefs;
    host.innerHTML = providerDefs.map((provider) => {
        const savedConfig = (savedProviders || []).find((item) => item.type === provider.type) || {};
        const enabled = savedConfig.enabled !== false && provider.enabled !== false;
        const mergedConfig = { ...(provider.config || {}), ...(savedConfig || {}) };
        const fields = ((provider.config_schema || {}).fields || []).map((field) => buildProviderField(provider.type, field, mergedConfig[field.key])).join("");
        return `
            <article class="provider-inline-card${enabled ? "" : " is-disabled"}" data-provider-card="${escapeHtml(provider.type)}">
                <div class="provider-inline-head">
                    <div>
                        <strong>${escapeHtml(provider.display_name || provider.type)}</strong>
                        <p>${escapeHtml(provider.description || "配置元数据源地址、凭据和连接参数。")}</p>
                    </div>
                    <label class="toggle-pill">
                        <input type="checkbox"${enabled ? " checked" : ""} data-provider-toggle="${escapeHtml(provider.type)}" />
                        <span class="toggle-pill-ui"></span>
                    </label>
                </div>
                <div class="provider-inline-grid">
                    ${fields || '<article class="provider-inline-empty">该 Provider 暂无可配置字段</article>'}
                </div>
                <div class="provider-inline-actions">
                    <button class="btn btn-primary btn-sm" type="button" data-provider-action="save" data-provider-type="${escapeHtml(provider.type)}">保存当前 Provider</button>
                    <button class="btn btn-secondary btn-sm" type="button" data-provider-action="test" data-provider-type="${escapeHtml(provider.type)}">测试连接</button>
                    <button class="btn btn-secondary btn-sm" type="button" data-provider-action="preview" data-provider-type="${escapeHtml(provider.type)}">刮削预览</button>
                </div>
            </article>`;
    }).join("");
}

async function loadInlineProviderConfigs(metadata) {
    const host = document.getElementById("provider-inline-stack");
    if (!host) return;
    host.innerHTML = '<article class="provider-inline-empty">正在加载 Provider 配置...</article>';
    try {
        const result = await requestApi("GET", "/providers");
        if (result.code !== 200 || !result.data || !Array.isArray(result.data.providers)) {
            host.innerHTML = '<article class="provider-inline-empty">Provider 配置加载失败</article>';
            return;
        }
        renderInlineProviderConfigs(result.data.providers, metadata.providers || []);
    } catch (error) {
        host.innerHTML = '<article class="provider-inline-empty">Provider 配置加载失败</article>';
    }
}

function renderRuleList(pathRules) {
    const list = document.getElementById("rules-inline-list");
    if (!list) return;
    if (!Array.isArray(pathRules) || pathRules.length === 0) {
        list.innerHTML = '<button class="rule-inline-empty rule-inline-add" type="button" data-rule-action="add">+</button>';
        return;
    }
    list.innerHTML = pathRules.map((rule, index) => {
        const template = rule.template || "未设置模板";
        const conditions = Object.entries(rule.conditions || {});
        const conditionText = conditions.length
            ? conditions.map(([key, value]) => `${key}=${Array.isArray(value) ? value.join("/") : value}`).join(" · ")
            : "无条件，作为通用规则";
        return `
            <article class="rule-inline-item">
                <div>
                    <strong>规则 ${index + 1}</strong>
                    <small>${template}</small>
                    <p>${conditionText}</p>
                </div>
                <div class="rule-inline-meta">
                    <b>${conditions.length} 个条件</b>
                    <span>命中即止</span>
                </div>
                <div class="rule-inline-actions">
                    <button class="btn btn-secondary btn-sm" type="button" data-rule-action="edit" data-rule-index="${index}">编辑</button>
                    <button class="btn btn-secondary btn-sm" type="button" data-rule-action="delete" data-rule-index="${index}">删除</button>
                </div>
            </article>`;
    }).join("") + '<button class="rule-inline-empty rule-inline-add" type="button" data-rule-action="add">+</button>';
}

function renderDimensionVarList(dimensions) {
    const container = document.getElementById("rules-dimension-vars");
    if (!container) return;
    if (!Array.isArray(dimensions) || dimensions.length === 0) {
        container.innerHTML = '<div class="rule-inline-empty">暂无启用的维度变量</div>';
        return;
    }
    container.innerHTML = dimensions.map((dim) => {
        const label = dim.label || dim.display_name || dim.name || "未命名维度";
        const options = Array.isArray(dim.options) ? dim.options : [];
        const valuesHint = options
            .filter((item) => item && item.value !== "")
            .map((item) => item.label || item.value)
            .join(" / ");
        return `<div class="var-token-line"><code>{dimension.${dim.name}}</code><span>${label}${valuesHint ? `（${valuesHint}）` : ""}</span></div>`;
    }).join("");
}

async function loadDimensionVars() {
    const result = await requestApi("GET", "/dimensions/enabled");
    if (result.code !== 200 || !result.data) {
        currentEnabledDimensions = [];
        renderDimensionVarList([]);
        return;
    }
    currentEnabledDimensions = result.data.dimensions || [];
    renderDimensionVarList(currentEnabledDimensions);
}

function toggleVarGroup(group) {
    const button = document.querySelector(`[data-var-group="${group}"]`);
    const panel = document.querySelector(`[data-var-panel="${group}"]`);
    if (!button || !panel) return;
    const next = !button.classList.contains("active");
    button.classList.toggle("active", next);
    panel.classList.toggle("active", next);
}

function getEditablePathRules() {
    return Array.isArray(currentConfigSnapshot?.path_rules) ? [...currentConfigSnapshot.path_rules] : [];
}

function parseRuleConditionValue(value) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    if (raw.includes("|")) return raw.split("|").map((item) => item.trim()).filter(Boolean).join("|");
    if (raw.includes(",")) return raw.split(",").map((item) => item.trim()).filter(Boolean).join("|");
    return raw;
}

function openRuleEditor(index = -1) {
    const pathRules = getEditablePathRules();
    const target = index >= 0 ? (pathRules[index] || {}) : {};
    const dimensions = currentEnabledDimensions.length ? currentEnabledDimensions : [];
    const fields = dimensions.map((dim) => {
        const value = target.conditions?.[dim.name] || "";
        const hint = Array.isArray(dim.value_list) && dim.value_list.length
            ? dim.value_list.map((item) => item.label || item.value).join(" / ")
            : "留空表示不限制";
        return `
            <label class="cinema-modal-field">
                <span>${escapeHtml(dim.label || dim.name)}</span>
                <input type="text" data-rule-dim="${escapeHtml(dim.name)}" value="${escapeHtml(value)}" placeholder="${escapeHtml(hint)}" />
                <small>${escapeHtml(dim.name)}${hint ? ` · ${hint}` : ""}</small>
            </label>`;
    }).join("");
    const overlay = showAppModal({
        title: index >= 0 ? `编辑规则 ${index + 1}` : "新增入库规则",
        body: `
            <div class="cinema-modal-stack">
                <label class="cinema-modal-field">
                    <span>入库路径模板</span>
                    <input type="text" id="rule-template-input" value="${escapeHtml(target.template || "")}" placeholder="/vol1/影视/电影/{year}/{title_cn}/" />
                    <small>命中后写入的目标目录模板。</small>
                </label>
                ${fields || '<div class="cinema-modal-hint">当前还没有启用的分类维度，先去"影视分类维度"启用后再补充条件。</div>'}
            </div>`,
        actions: [
            { label: "取消", className: "btn btn-secondary" },
            {
                label: index >= 0 ? "保存规则" : "新增规则",
                className: "btn btn-primary",
                closeOnClick: false,
                onClick: async () => {
                    const template = String(document.getElementById("rule-template-input")?.value || "").trim();
                    if (!template) {
                        showToast("入库路径模板不能为空");
                        return;
                    }
                    const conditions = {};
                    overlay.querySelectorAll("[data-rule-dim]").forEach((input) => {
                        const nextValue = parseRuleConditionValue(input.value);
                        if (nextValue) conditions[input.dataset.ruleDim] = nextValue;
                    });
                    const nextRule = { conditions, template };
                    if (index >= 0) pathRules[index] = nextRule;
                    else pathRules.push(nextRule);
                    currentConfigSnapshot = {
                        ...(currentConfigSnapshot || {}),
                        path_rules: pathRules,
                    };
                    renderRuleList(pathRules);
                    removeAppModal();
                    showToast(index >= 0 ? "规则已更新，记得点击保存" : "规则已新增，记得点击保存");
                },
            },
        ],
    });
    return overlay;
}

function deleteInlineRule(index) {
    const pathRules = getEditablePathRules();
    if (!pathRules[index]) return;
    showConfirm("删除规则", `确定删除规则 ${index + 1} 吗？`, () => {
        pathRules.splice(index, 1);
        currentConfigSnapshot = {
            ...(currentConfigSnapshot || {}),
            path_rules: pathRules,
        };
        renderRuleList(pathRules);
        showToast("规则已删除，记得点击保存");
    });
}

function explainSimulatedQueue(score, confidence) {
    const pass = Number(confidence.pass_threshold ?? 0.8);
    const confirm = Number(confidence.confirm_threshold ?? 0.5);
    const review = Number(confidence.review_threshold ?? 0.3);
    if (!Number.isFinite(score)) return "当前结果未返回可用置信度，请结合标题和 Provider 命中情况手动判断。";
    if (score >= pass) return `命中自动通过阈值 ${pass.toFixed(2)}，会优先进入自动入库队列。`;
    if (score >= confirm) return `低于自动通过阈值但高于确认阈值 ${confirm.toFixed(2)}，建议进入待确认队列。`;
    if (score >= review) return `低于确认阈值但高于审核阈值 ${review.toFixed(2)}，建议先人工审核再继续。`;
    return `低于审核阈值 ${review.toFixed(2)}，更适合先停在失败/人工处理链路。`;
}

function renderSimulatorPreview(data) {
    const result = document.getElementById("confidence-sim-result");
    const ai = data.ai_only || {};
    const provider = data.provider_ai || {};
    const aiScore = Number(ai.confidence);
    const providerScore = Number(provider.confidence);
    const finalScore = Number.isFinite(providerScore) ? providerScore : aiScore;
    const finalTitle = provider.title_cn || provider.title_en || ai.title_cn || ai.title_en || data.clean_result?.clean_title || data.filename;
    const finalType = provider.type || ai.type || "-";
    const lines = [
        `<strong>${escapeHtml(finalTitle || "未识别标题")}</strong>`,
        `${escapeHtml(finalType)} · 纯 AI ${Number.isFinite(aiScore) ? aiScore.toFixed(2) : "--"} · Provider+AI ${Number.isFinite(providerScore) ? providerScore.toFixed(2) : "--"}`,
        escapeHtml(explainSimulatedQueue(finalScore, getConfidenceConfig())),
    ];
    if (result) result.innerHTML = lines.join("<br>");
    const aiCopy = document.getElementById("simulator-ai-copy");
    if (aiCopy) {
        aiCopy.textContent = ai.error
            ? `纯 AI 预览失败：${ai.error}`
            : `纯 AI 识别为「${ai.title_cn || ai.title_en || data.clean_result?.clean_title || "未识别"}」，耗时 ${Number(data.ai_only_elapsed || 0).toFixed(2)} 秒。`;
    }
    const confidenceCopy = document.getElementById("simulator-confidence-copy");
    if (confidenceCopy) confidenceCopy.textContent = explainSimulatedQueue(finalScore, getConfidenceConfig());
    const rulesCopy = document.getElementById("simulator-rules-copy");
    if (rulesCopy) {
        const year = provider.year || ai.year || data.clean_result?.year || "";
        const cleanTitle = data.clean_result?.clean_title || finalTitle || "未识别标题";
        rulesCopy.textContent = `标题清洗得到「${cleanTitle}」${year ? `，年份 ${year}` : ""}。真实入库目录仍以当前规则与兜底目录匹配结果为准。`;
    }
}

async function runConfigSimulator() {
    const filename = String(document.getElementById("confidence-sim-filename")?.value || "").trim();
    if (!filename) {
        showToast("请先输入一个真实文件名");
        return;
    }
    const resultBox = document.getElementById("confidence-sim-result");
    if (resultBox) resultBox.textContent = "正在生成真实刮削预览...";
    const result = await requestApi("POST", "/scrape/preview", { filename });
    if (result.code !== 200 || !result.data) {
        if (resultBox) resultBox.textContent = result.message || "模拟测试失败，请检查 AI / Provider 配置。";
        showToast(result.message || "模拟测试失败");
        return;
    }
    renderSimulatorPreview(result.data);
    showToast("模拟测试已完成");
}

function updateConfigStageStatus(config, paths, pathRules) {
    const hasSource = Boolean(paths.source_dir);
    const hasTemp = Boolean(paths.temp_dir);
    const hasRecycle = Boolean(paths.recycle_dir);
    const hasRules = Array.isArray(pathRules) && pathRules.length > 0;
    const metadata = config.metadata || {};
    const llm = config.llm || {};
    const hasScrape = Object.keys(metadata).length > 0;
    const hasAi = Boolean(llm.base_url || llm.model || llm.api_key);
    const states = [
        ["source", hasSource],
        ["temp", hasTemp],
        ["recycle", hasRecycle],
        ["rules", hasRules],
        ["scrape", hasScrape],
        ["ai", hasAi],
    ];
    states.forEach(([stage, valid]) => {
        const card = document.querySelector(`[data-config-stage="${stage}"]`);
        if (!card) return;
        card.dataset.state = valid ? "valid" : "invalid";
    });
}

/* C2: 提示词 / 维度页壳层函数 */

async function loadPromptSectionConfig(section) {
    const result = await requestApi("GET", "/config");
    if (result.code !== 200 || !result.data) {
        showToast(result.message || "读取提示词配置失败");
        return null;
    }
    const config = result.data;
    if (section === "system") {
        return config.prompts || {};
    }
    if (section === "tmdb") {
        return config.tmdb_prompts || config.prompts_tmdb || {};
    }
    return config.prompts || {};
}

function collectPromptSectionTextarea(section) {
    const root = document.querySelector(`[data-prompt-section="${section}"]`);
    if (!root) return {};
    const values = {};
    root.querySelectorAll("[data-prompt-text]").forEach((node) => {
        const key = node.dataset.promptText;
        if (!key) return;
        values[key] = String(node.value || "");
    });
    return values;
}

async function savePromptSectionConfig(section) {
    const values = collectPromptSectionTextarea(section);
    if (Object.keys(values).length === 0) {
        showToast("当前没有可保存的提示词");
        return;
    }
    const fieldKey = section === "tmdb" ? "tmdb_prompts" : "prompts";
    const result = await requestApi("POST", "/config", { [fieldKey]: values });
    showToast(result.message || `${section === "tmdb" ? "TMDB" : "系统"}提示词已保存`);
}

function resetPromptSectionToDefault(section) {
    if (typeof window.__cinemaDefaultPrompts !== "object" || window.__cinemaDefaultPrompts === null) {
        showToast("默认提示词未加载，请刷新页面后再试");
        return;
    }
    const defaults = section === "tmdb"
        ? window.__cinemaDefaultPrompts.tmdb
        : window.__cinemaDefaultPrompts.system;
    if (!defaults) {
        showToast("默认提示词不存在");
        return;
    }
    const root = document.querySelector(`[data-prompt-section="${section}"]`);
    if (!root) return;
    root.querySelectorAll("[data-prompt-text]").forEach((node) => {
        const key = node.dataset.promptText;
        if (key in defaults) node.value = defaults[key];
    });
    showToast(`${section === "tmdb" ? "TMDB" : "系统"}提示词已恢复为默认值（记得保存）`);
}

async function previewPromptSection(section) {
    const values = collectPromptSectionTextarea(section);
    const text = Object.entries(values)
        .map(([key, value]) => `【${key}】\n${value}`)
        .join("\n\n");
    if (!text) {
        showToast("当前没有可预览的提示词");
        return;
    }
    showTextModal(
        section === "tmdb" ? "TMDB 提示词预览" : "系统提示词预览",
        text,
        "关闭",
    );
}

async function performPromptAction(action) {
    if (action === "save-all") {
        await savePromptSectionConfig("system");
        await savePromptSectionConfig("tmdb");
        return;
    }
    if (action === "reset-system") {
        resetPromptSectionToDefault("system");
        return;
    }
    if (action === "preview-system") {
        await previewPromptSection("system");
        return;
    }
    if (action === "reset-tmdb") {
        resetPromptSectionToDefault("tmdb");
        return;
    }
    if (action === "preview-tmdb") {
        await previewPromptSection("tmdb");
    }
}

async function loadDimensionsList() {
    const result = await requestApi("GET", "/dimensions/enabled");
    if (result.code !== 200 || !result.data) {
        return [];
    }
    return Array.isArray(result.data.dimensions) ? result.data.dimensions : [];
}

async function toggleDimensionEnabled(name, enabled) {
    const result = await requestApi("POST", `/dimensions/${encodeURIComponent(name)}/toggle`, { enabled });
    showToast(result.message || (enabled ? "已启用" : "已停用") + name);
    if (result.code === 200) {
        currentEnabledDimensions = await loadDimensionsList();
        renderEnabledDimensionBadges();
    }
}

function renderEnabledDimensionBadges() {
    const host = document.getElementById("enabled-dimension-badges");
    if (!host) return;
    if (!currentEnabledDimensions || currentEnabledDimensions.length === 0) {
        host.innerHTML = `<div class="cinema-modal-hint">暂未启用任何维度。</div>`;
        return;
    }
    host.innerHTML = currentEnabledDimensions.map((dim) => `
        <span class="badge">${escapeHtml(dim.label || dim.name)}</span>
    `).join("");
}

function collectDimensionOrder() {
    const root = document.getElementById("dimension-order-list");
    if (!root) return [];
    return Array.from(root.querySelectorAll("[data-dimension-order]"))
        .map((node) => node.dataset.dimensionOrder)
        .filter(Boolean);
}

async function saveDimensionOrder() {
    const order = collectDimensionOrder();
    if (order.length === 0) {
        showToast("当前没有可保存的维度顺序");
        return;
    }
    const result = await requestApi("POST", "/dimensions/order", { order });
    showToast(result.message || "维度顺序已保存");
}

async function performDimensionAction(action, name) {
    if (action === "toggle") {
        const enabled = !(name && currentEnabledDimensions.some((d) => d.name === name));
        await toggleDimensionEnabled(name, enabled);
        return;
    }
    if (action === "save-order") {
        await saveDimensionOrder();
    }
}

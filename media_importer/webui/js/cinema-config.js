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
    const apiKeyValue = String(document.getElementById("cfg-llm_api_key")?.value || "").trim();
    const fastApiKeyValue = String(document.getElementById("cfg-llm_fast_api_key")?.value || "").trim();
    const payload = {
        llm: {
            // `enabled` field is ignored since 2026-06; AI availability is
            // determined by api_key + base_url + model completeness.
            enabled: true,
            api_key: apiKeyValue || currentLlm.api_key || "***",
            fast_api_key: fastApiKeyValue || currentLlm.fast_api_key || "***",
            base_url: String(document.getElementById("cfg-llm_base_url")?.value || "").trim(),
            model: String(document.getElementById("cfg-llm_model")?.value || "").trim(),
            fallback_model: String(document.getElementById("cfg-llm_fallback_model")?.value || "").trim(),
            fast_model: String(document.getElementById("cfg-llm_fast_model")?.value || "").trim(),
            fast_base_url: String(document.getElementById("cfg-llm_fast_base_url")?.value || "").trim(),
            source_cleaner_model: String(document.getElementById("cfg-llm_source_cleaner_model")?.value || "").trim(),
            timeout: Number(document.getElementById("cfg-llm_timeout")?.value || 30) || 30,
            max_retries: Number(document.getElementById("cfg-llm_max_retries")?.value || 2) || 2,
            retry_delay: Number(document.getElementById("cfg-llm_retry_delay")?.value || 3) || 3,
            confidence_threshold: Number(document.getElementById("cfg-llm_confidence_threshold")?.value || 0.8) || 0.8,
            verify_ssl: !!document.getElementById("cfg-llm_verify_ssl")?.checked,
            web_search: {
                enabled: !!document.getElementById("cfg-llm_web_search_enabled")?.checked,
            },
        },
    };
    const sourceCleanerModel = document.getElementById("cfg-llm_source_cleaner_model")?.value?.trim();
    if (sourceCleanerModel) {
        payload.llm.source_cleaner_model = sourceCleanerModel;
    }
    return payload;
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
    if (!payload.llm.base_url && !payload.llm.model) {
        showToast("AI 刮削接口地址为必填项");
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

function buildScrapeModeConfigPayload() {
    return {
        metadata: {
            scrape_mode: String(document.getElementById("cfg-metadata_scrape_mode")?.value || "hybrid").trim(),
        },
    };
}

async function saveScrapeModeConfig() {
    const payload = buildScrapeModeConfigPayload();
    const result = await requestApi("POST", "/config/section", {
        section: "metadata.providers",
        data: payload,
    });
    showToast(result.message || "刮削模式已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
}

async function saveAiAssistConfig() {
    const payload = buildLlmConfigPayload();
    const fastModel = String(document.getElementById("cfg-llm_fast_model")?.value || "").trim();
    if (!fastModel) {
        showToast("辅助模型ID为必填项");
        return;
    }
    const result = await requestApi("POST", "/config/section", {
        section: "llm",
        data: payload,
    });
    showToast(result.message || "AI 辅助配置已保存");
    if (result.code === 200) {
        await loadDirectoryConfig();
    }
}

async function saveAiScrapeConfig() {
    const payload = buildLlmConfigPayload();
    const model = String(document.getElementById("cfg-llm_model")?.value || "").trim();
    const baseUrl = String(document.getElementById("cfg-llm_base_url")?.value || "").trim();
    if (!model || !baseUrl) {
        showToast("AI 刮削接口地址和模型ID为必填项");
        return;
    }
    const result = await requestApi("POST", "/config/section", {
        section: "llm",
        data: payload,
    });
    showToast(result.message || "AI 刮削配置已保存");
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

let _currentPreviewProviderType = "tmdb";
let _tmdbSelectedResultId = null;
let _tmdbSelectedResultType = null;

async function previewProvider(providerType) {
    _currentPreviewProviderType = providerType || "tmdb";
    const existing = document.getElementById("tmdb-preview-modal");
    if (existing) existing.remove();

    let lang = "zh-CN";
    const cfgLangEl = document.getElementById(`cfg-provider-inline-${_currentPreviewProviderType}-language`);
    if (cfgLangEl && cfgLangEl.value) lang = cfgLangEl.value;

    const providerDisplayName = _currentPreviewProviderType.toUpperCase();

    const overlay = document.createElement("div");
    overlay.id = "tmdb-preview-modal";
    overlay.className = "cinema-modal-overlay";
    overlay.innerHTML = `
        <div class="cinema-modal tmdb-preview-modal-content">
            <div class="cinema-modal-header">
                <h3>${escapeHtml(providerDisplayName)} 刮削预览</h3>
                <button type="button" class="cinema-modal-close" aria-label="关闭">×</button>
            </div>
            <div class="tmdb-preview-toolbar">
                <input type="text" id="tmdb-preview-query" placeholder="输入影视名称..." class="tmdb-preview-input" />
                <select id="tmdb-preview-type" class="tmdb-preview-select" style="width:100px;">
                    <option value="movie">电影</option>
                    <option value="tv">电视剧</option>
                </select>
                <select id="tmdb-preview-lang" class="tmdb-preview-select" style="width:130px;">
                    <option value="zh-CN"${lang === "zh-CN" ? " selected" : ""}>中文 (zh-CN)</option>
                    <option value="en-US"${lang === "en-US" ? " selected" : ""}>英文 (en-US)</option>
                    <option value="ja-JP"${lang === "ja-JP" ? " selected" : ""}>日文 (ja-JP)</option>
                    <option value="ko-KR"${lang === "ko-KR" ? " selected" : ""}>韩文 (ko-KR)</option>
                </select>
                <button class="btn btn-primary btn-sm" id="btn-tmdb-preview-search" type="button">搜索</button>
            </div>
            <div class="tmdb-preview-panels">
                <div class="tmdb-preview-left">
                    <div id="tmdb-search-results" class="tmdb-search-results"></div>
                </div>
                <div class="tmdb-preview-right">
                    <div id="tmdb-detail-container" class="tmdb-detail-container">
                        <div class="tmdb-preview-placeholder">点击左侧搜索结果查看详情</div>
                    </div>
                </div>
            </div>
        </div>
    `;
    overlay.addEventListener("click", (event) => {
        if (event.target === overlay) overlay.remove();
    });
    overlay.querySelector(".cinema-modal-close")?.addEventListener("click", () => overlay.remove());
    document.body.appendChild(overlay);

    const queryInput = document.getElementById("tmdb-preview-query");
    const searchBtn = document.getElementById("btn-tmdb-preview-search");
    queryInput?.focus();
    queryInput?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") doProviderPreviewSearch();
    });
    searchBtn?.addEventListener("click", doProviderPreviewSearch);
}

async function doProviderPreviewSearch() {
    const query = String(document.getElementById("tmdb-preview-query")?.value || "").trim();
    const type = document.getElementById("tmdb-preview-type")?.value || "movie";
    const langEl = document.getElementById("tmdb-preview-lang");
    const language = langEl ? langEl.value : "zh-CN";
    const resultsEl = document.getElementById("tmdb-search-results");
    const detailEl = document.getElementById("tmdb-detail-container");
    const btn = document.getElementById("btn-tmdb-preview-search");

    if (!query) {
        resultsEl.innerHTML = '<div class="tmdb-preview-error">请输入影视名称</div>';
        return;
    }

    btn.disabled = true;
    resultsEl.innerHTML = '<div class="tmdb-preview-loading">搜索中...</div>';
    detailEl.innerHTML = '<div class="tmdb-preview-placeholder">点击左侧搜索结果查看详情</div>';
    _tmdbSelectedResultId = null;
    _tmdbSelectedResultType = null;

    const result = await requestApi("POST", `/providers/${encodeURIComponent(_currentPreviewProviderType)}/search`, { query, type, language });
    btn.disabled = false;

    if (result.code !== 200 || !result.data) {
        resultsEl.innerHTML = `<div class="tmdb-preview-error">${escapeHtml(result.message || "请求失败")}</div>`;
        return;
    }

    const items = result.data.items || result.data.results || result.data || [];
    if (!items || items.length === 0) {
        resultsEl.innerHTML = '<div class="tmdb-preview-error">未找到结果</div>';
        return;
    }

    const maxItems = Math.min(items.length, 10);
    let html = "";
    for (let i = 0; i < maxItems; i++) {
        const item = items[i];
        const titleField = item.title || item.name || item.original_title || item.original_name || "";
        const origTitle = item.original_title || item.original_name || "";
        const year = item.year || (item.release_date || item.first_air_date || "").substring(0, 4) || "";
        const posterUrl = item.poster_url || (item.poster_path ? `https://image.tmdb.org/t/p/w92${item.poster_path}` : "");
        const rating = item.vote_average != null ? Number(item.vote_average).toFixed(1) : "--";
        let overview = item.overview || "";
        if (overview.length > 80) overview = overview.substring(0, 80) + "...";

        html += `<div class="tmdb-result-card" data-tmdb-id="${escapeHtml(String(item.id))}" data-tmdb-type="${escapeHtml(type)}">`;
        if (posterUrl) {
            html += `<img class="tmdb-result-poster" src="${escapeHtml(posterUrl)}" alt="" loading="lazy">`;
        } else {
            html += '<div class="tmdb-result-poster tmdb-result-poster-placeholder">无海报</div>';
        }
        html += '<div class="tmdb-result-info">';
        html += `<div class="tmdb-result-title">${escapeHtml(titleField || "未知")}</div>`;
        if (origTitle && origTitle !== titleField) {
            html += `<div class="tmdb-result-original-title">${escapeHtml(origTitle)}</div>`;
        }
        html += '<div class="tmdb-result-meta">';
        if (year) html += `<span>${escapeHtml(year)}</span>`;
        html += `<span class="tmdb-result-rating">★ ${escapeHtml(rating)}</span>`;
        html += '</div>';
        if (overview) {
            html += `<div class="tmdb-result-overview">${escapeHtml(overview)}</div>`;
        }
        html += '</div></div>';
    }

    resultsEl.innerHTML = html;
    resultsEl.querySelectorAll(".tmdb-result-card").forEach((card) => {
        card.addEventListener("click", () => selectProviderPreviewResult(card));
    });
}

async function selectProviderPreviewResult(cardEl) {
    const id = cardEl.getAttribute("data-tmdb-id");
    const type = cardEl.getAttribute("data-tmdb-type");
    const resultsEl = document.getElementById("tmdb-search-results");
    const detailEl = document.getElementById("tmdb-detail-container");

    resultsEl.querySelectorAll(".tmdb-result-card").forEach((c) => c.classList.remove("selected"));
    cardEl.classList.add("selected");

    _tmdbSelectedResultId = id;
    _tmdbSelectedResultType = type;

    detailEl.innerHTML = '<div class="tmdb-preview-loading">加载详情中...</div>';

    const result = await requestApi("POST", `/providers/${encodeURIComponent(_currentPreviewProviderType)}/details`, { id, type });

    if (result.code !== 200 || !result.data) {
        detailEl.innerHTML = `<div class="tmdb-preview-error">${escapeHtml(result.message || "加载详情失败")}</div>`;
        return;
    }

    const data = result.data.details || result.data;
    detailEl.innerHTML = renderProviderDetailsStructured(data, type);
}

function renderProviderDetailsStructured(data, type) {
    const fieldDict = (typeof PROVIDER_FIELD_DICTS !== "undefined" && PROVIDER_FIELD_DICTS[_currentPreviewProviderType]) ? PROVIDER_FIELD_DICTS[_currentPreviewProviderType] : {};
    const fieldGroups = (typeof PROVIDER_FIELD_GROUPS !== "undefined" && PROVIDER_FIELD_GROUPS[_currentPreviewProviderType]) ? PROVIDER_FIELD_GROUPS[_currentPreviewProviderType] : [];
    const statusDict = (typeof PROVIDER_STATUS_DICTS !== "undefined" && PROVIDER_STATUS_DICTS[_currentPreviewProviderType]) ? PROVIDER_STATUS_DICTS[_currentPreviewProviderType] : {};

    let html = '<div class="tmdb-detail-view">';
    html += '<div style="display:flex;justify-content:flex-end;margin-bottom:8px;">';
    html += '<button class="btn btn-secondary btn-sm" id="tmdb-detail-toggle-btn" type="button">查看原始 JSON</button>';
    html += '</div>';

    html += '<div id="tmdb-detail-structured">';
    for (let gi = 0; gi < fieldGroups.length; gi++) {
        const group = fieldGroups[gi];
        let hasField = false;
        for (let fi = 0; fi < group.fields.length; fi++) {
            if (data[group.fields[fi]] !== undefined && data[group.fields[fi]] !== null) {
                hasField = true;
                break;
            }
        }
        if (!hasField) continue;

        html += '<div class="tmdb-detail-group">';
        html += `<div class="tmdb-detail-group-header"><span>${escapeHtml(group.label)}</span><span class="tmdb-detail-group-arrow">▼</span></div>`;
        html += '<div class="tmdb-detail-group-body">';

        for (let fj = 0; fj < group.fields.length; fj++) {
            const key = group.fields[fj];
            const val = data[key];
            if (val === undefined || val === null) continue;

            const label = fieldDict[key] || key;
            html += '<div class="tmdb-detail-row">';
            html += `<span class="tmdb-detail-key">${escapeHtml(label)}</span>`;
            html += `<span class="tmdb-detail-val">${renderProviderFieldValue(key, val, statusDict)}</span>`;
            html += '</div>';
        }

        html += '</div></div>';
    }
    html += '</div>';

    html += '<div id="tmdb-detail-raw" style="display:none;">';
    html += `<pre class="tmdb-detail-raw-pre">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
    html += '</div>';

    html += '</div>';
    return html;
}

function renderProviderFieldValue(key, val, statusDict) {
    if (key === "poster_path" || key === "backdrop_path") {
        if (typeof val === "string" && val) {
            return `<img src="https://image.tmdb.org/t/p/w300${escapeHtml(val)}" alt="" style="max-width:200px;border-radius:6px;" loading="lazy">`;
        }
        return escapeHtml(String(val));
    }

    if (key === "status" && typeof val === "string" && statusDict) {
        const statusLabel = statusDict[val];
        if (statusLabel) return escapeHtml(statusLabel);
        return escapeHtml(val);
    }

    if (typeof val === "boolean") {
        return val ? "是" : "否";
    }

    if (typeof val === "string" || typeof val === "number") {
        return escapeHtml(String(val));
    }

    if (Array.isArray(val)) {
        if (val.length === 0) return '<span style="color:var(--muted);">-</span>';

        const firstItem = val[0];
        if (typeof firstItem === "string" || typeof firstItem === "number") {
            return val.map((v) => escapeHtml(String(v))).join("、");
        }

        if (typeof firstItem === "object" && firstItem !== null) {
            let tags = "";
            for (let j = 0; j < val.length; j++) {
                const nameVal = val[j].name || val[j].title || val[j].iso_3166_1 || val[j].iso_639_1 || val[j].english_name || "";
                if (nameVal) {
                    tags += `<span class="tmdb-preview-tag">${escapeHtml(String(nameVal))}</span>`;
                }
            }
            return tags || '<span style="color:var(--muted);">-</span>';
        }

        return escapeHtml(JSON.stringify(val));
    }

    if (typeof val === "object" && val !== null) {
        let subHtml = "";
        const subKeys = Object.keys(val);
        const fieldDict = (typeof PROVIDER_FIELD_DICTS !== "undefined" && PROVIDER_FIELD_DICTS[_currentPreviewProviderType]) ? PROVIDER_FIELD_DICTS[_currentPreviewProviderType] : {};
        for (let k = 0; k < subKeys.length; k++) {
            const subKey = subKeys[k];
            const subVal = val[subKey];
            if (subVal === undefined || subVal === null) continue;
            const subLabel = fieldDict[subKey] || subKey;
            subHtml += '<div class="tmdb-detail-row tmdb-detail-sub-row">';
            subHtml += `<span class="tmdb-detail-key">${escapeHtml(subLabel)}</span>`;
            subHtml += `<span class="tmdb-detail-val">${renderProviderFieldValue(subKey, subVal, statusDict)}</span>`;
            subHtml += '</div>';
        }
        return subHtml || '<span style="color:var(--muted);">-</span>';
    }

    return escapeHtml(String(val));
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
        api_key: payload.api_key,
        base_url: payload.base_url,
        model: payload.model,
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
    const resultElapsed = document.getElementById("ai-scrape-demo-result-elapsed");
    const resultBody = document.getElementById("ai-scrape-demo-result-body");

    resultArea.style.display = "none";
    loadingEl.style.display = "flex";

    const payload = buildLlmConfigPayload();

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

        let elapsedText = data.elapsed_ms != null ? (data.elapsed_ms + "ms") : "";
        if (data.search_enhanced) {
            elapsedText += " 🔍 联网搜索增强";
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
    const resultElapsed = document.getElementById("ai-assist-demo-result-elapsed");
    const resultBody = document.getElementById("ai-assist-demo-result-body");

    resultArea.style.display = "none";
    loadingEl.style.display = "flex";

    const payload = buildLlmConfigPayload();

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
        resultElapsed.textContent = data.elapsed_ms != null ? (data.elapsed_ms + "ms") : "";

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
        const defaultCollapsed = String(provider.type || "").toLowerCase() === "tmdb";
        const collapsedClass = defaultCollapsed ? " is-collapsed" : "";
        const mergedConfig = { ...(provider.config || {}), ...(savedConfig || {}) };
        const fields = ((provider.config_schema || {}).fields || []).map((field) => buildProviderField(provider.type, field, mergedConfig[field.key])).join("");
        const statusText = enabled ? "已启用" : "未启用";
        const statusClass = enabled ? "is-enabled" : "is-disabled-status";
        return `
            <article class="provider-inline-card${enabled ? "" : " is-disabled"}${collapsedClass}" data-provider-card="${escapeHtml(provider.type)}">
                <div class="provider-inline-head" data-toggle-provider-card="${escapeHtml(provider.type)}">
                    <div class="provider-inline-head-main">
                        <div class="provider-inline-title-row">
                            <strong>${escapeHtml(provider.display_name || provider.type)}</strong>
                            <span class="provider-inline-status ${statusClass}" data-provider-status="${escapeHtml(provider.type)}">${statusText}</span>
                            <label class="toggle-pill provider-inline-toggle" title="启用或停用该 Provider">
                                <input type="checkbox"${enabled ? " checked" : ""} data-provider-toggle="${escapeHtml(provider.type)}" />
                                <span class="toggle-pill-ui"></span>
                            </label>
                        </div>
                        <p>${escapeHtml(provider.description || "配置元数据源地址、凭据和连接参数。")}</p>
                    </div>
                    <div class="provider-inline-head-right">
                        <span class="provider-inline-chevron" aria-hidden="true"></span>
                        <button class="btn btn-primary btn-xs" type="button" data-provider-action="save" data-provider-type="${escapeHtml(provider.type)}">保存</button>
                    </div>
                </div>
                <div class="provider-inline-grid">
                    ${fields || '<article class="provider-inline-empty">该 Provider 暂无可配置字段</article>'}
                </div>
                <div class="provider-inline-actions">
                    <button class="btn btn-secondary btn-sm" type="button" data-provider-action="test" data-provider-type="${escapeHtml(provider.type)}">测试连接</button>
                    <button class="btn btn-secondary btn-sm" type="button" data-provider-action="preview" data-provider-type="${escapeHtml(provider.type)}">刮削预览</button>
                </div>
            </article>`;
    }).join("");
    bindProviderCardToggles(host);
}

function bindProviderCardToggles(host) {
    if (!host || host.dataset.toggleBound === "1") return;
    host.dataset.toggleBound = "1";
    host.addEventListener("click", (event) => {
        const toggle = event.target.closest("[data-toggle-provider-card]");
        if (!toggle) return;
        if (event.target.closest("label, input, button, select, textarea, [data-provider-toggle], [data-provider-action]")) return;
        const card = toggle.closest(".provider-inline-card");
        if (!card) return;
        card.classList.toggle("is-collapsed");
    });
    host.addEventListener("change", (event) => {
        const input = event.target.closest("[data-provider-toggle]");
        if (!input) return;
        const providerType = input.getAttribute("data-provider-toggle");
        const card = input.closest(".provider-inline-card");
        const status = host.querySelector(`[data-provider-status="${providerType}"]`);
        const enabled = !!input.checked;
        if (card) {
            card.classList.toggle("is-disabled", !enabled);
        }
        if (status) {
            status.textContent = enabled ? "已启用" : "未启用";
            status.classList.toggle("is-enabled", enabled);
            status.classList.toggle("is-disabled-status", !enabled);
        }
    });
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
    const dims = currentEnabledDimensions.length ? currentEnabledDimensions : [];
    const palette = [
        "#3b82f6", "#f59e0b", "#ec4899", "#8b5cf6",
        "#10b981", "#06b6d4", "#f97316", "#ef4444",
        "#14b8a6", "#a855f7", "#eab308", "#22c55e",
    ];
    list.innerHTML = pathRules.map((rule, index) => {
        const titleText = (rule.name && String(rule.name).trim()) || `规则 ${index + 1}`;
        const template = rule.template || "未设置模板";
        const conditions = rule.conditions || {};
        const entries = Object.entries(conditions);
        const templateChip = `<span class="rule-chip rule-chip--template" title="${escapeHtml(template)}">${escapeHtml(template)}</span>`;
        let conditionsHTML;
        if (entries.length === 0) {
            conditionsHTML = '<span class="rule-chip rule-chip--empty">无条件</span>';
        } else {
            conditionsHTML = entries.map(([key, value]) => {
                const dim = dims.find((d) => d.name === key);
                const dimLabel = dim ? (dim.label || dim.name) : key;
                const dimColor = dim && dim.color ? dim.color : palette[index % palette.length];
                const vals = String(value).split("|").map((v) => v.trim()).filter(Boolean);
                const valueChips = vals.length
                    ? vals.map((v) => {
                        const label = dim ? _dimValueToLabel(dim, v) : v;
                        return `<span class="rule-chip rule-chip--val" style="--chip-color:${escapeHtml(dimColor)}">${escapeHtml(label)}</span>`;
                    }).join("")
                    : '<span class="rule-chip rule-chip--val rule-chip--val-any" style="--chip-color:' + escapeHtml(dimColor) + '">(不限制)</span>';
                return `<span class="rule-chip-group">` +
                    `<span class="rule-chip rule-chip--key" style="--chip-color:${escapeHtml(dimColor)}" title="${escapeHtml(dim.name)}">${escapeHtml(dimLabel)}</span>` +
                    valueChips +
                    `</span>`;
            }).join("");
        }
        return `
            <article class="rule-inline-item">
                <div class="rule-inline-main">
                    <div class="rule-inline-title-row">
                        <strong>${escapeHtml(titleText)}</strong>
                        <span class="rule-inline-index">#${index + 1}</span>
                    </div>
                    <div class="rule-inline-rows">
                        <div class="rule-inline-row">
                            <span class="rule-inline-row-label">规则</span>
                            <div class="rule-inline-chips">${conditionsHTML}</div>
                        </div>
                        <div class="rule-inline-row">
                            <span class="rule-inline-row-label">入库目录</span>
                            <div class="rule-inline-chips">${templateChip}</div>
                        </div>
                    </div>
                </div>
                <div class="rule-inline-meta">
                    <b>${entries.length} 个条件</b>
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
        const valueList = Array.isArray(dim.value_list) ? dim.value_list : [];
        const valuesHint = valueList
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

// MULTI_SELECT_DIMS is declared in cinema-tasks.js; reuse the global

function _dimValueToLabel(dim, val) {
    const list = Array.isArray(dim.value_list) ? dim.value_list : [];
    for (const item of list) {
        if (item.value === val) return item.label || item.value;
    }
    return val;
}

function openRuleEditor(index = -1) {
    const pathRules = getEditablePathRules();
    const target = index >= 0 ? (pathRules[index] || {}) : {};
    const dimensions = currentEnabledDimensions.length ? currentEnabledDimensions : [];
    const fields = dimensions.map((dim) => {
        const value = target.conditions?.[dim.name] || "";
        const valueList = Array.isArray(dim.value_list) ? dim.value_list : [];
        const isMulti = MULTI_SELECT_DIMS.includes(dim.name);
        const dimLabel = escapeHtml(dim.label || dim.name);

        if (isMulti) {
            const selectedValues = value ? String(value).split("|").map((s) => s.trim()).filter(Boolean) : [];
            const checkboxes = valueList.map((item) => {
                const checked = selectedValues.includes(item.value) ? " checked" : "";
                return `<label class="rule-editor-checkbox-label"><input type="checkbox" data-rule-dim="${escapeHtml(dim.name)}" value="${escapeHtml(item.value)}"${checked} />${escapeHtml(item.label || item.value)}</label>`;
            }).join("");
            return `
                <label class="cinema-modal-field cinema-modal-field--multi">
                    <span>${dimLabel}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small>（可多选）</span>
                    <div class="rule-editor-checkbox-group">${checkboxes}</div>
                </label>`;
        }

        const options = ['<option value="">(不限制)</option>'].concat(
            valueList.map((item) => {
                const selected = value === item.value ? " selected" : "";
                return `<option value="${escapeHtml(item.value)}"${selected}>${escapeHtml(item.label || item.value)}</option>`;
            })
        ).join("");
        return `
            <label class="cinema-modal-field">
                <span>${dimLabel}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                <select data-rule-dim="${escapeHtml(dim.name)}">${options}</select>
            </label>`;
    }).join("");
    const ruleName = target.name || "";
    const overlay = showAppModal({
        title: index >= 0 ? `编辑规则 ${ruleName || index + 1}` : "新增入库规则",
        body: `
            <div class="cinema-modal-stack">
                <label class="cinema-modal-field">
                    <span>规则名称（可选）</span>
                    <input type="text" id="rule-name-input" value="${escapeHtml(ruleName)}" placeholder="如：家庭向动漫剧集" maxlength="40" />
                    <small>用于在卡片上区分多条规则，留空时回退显示"规则 N"。</small>
                </label>
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
                    const name = String(document.getElementById("rule-name-input")?.value || "").trim();
                    const conditions = {};
                    overlay.querySelectorAll("[data-rule-dim]").forEach((el) => {
                        if (el.tagName === "SELECT") {
                            const v = el.value;
                            if (v) conditions[el.dataset.ruleDim] = v;
                        } else if (el.type === "checkbox") {
                            if (!conditions[el.dataset.ruleDim]) conditions[el.dataset.ruleDim] = [];
                            if (el.checked) conditions[el.dataset.ruleDim].push(el.value);
                        }
                    });
                    Object.keys(conditions).forEach((key) => {
                        if (Array.isArray(conditions[key])) {
                            if (conditions[key].length) conditions[key] = conditions[key].join("|");
                            else delete conditions[key];
                        }
                    });
                    const nextRule = { conditions, template };
                    if (name) nextRule.name = name;
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
    if (index >= 0) {
        const nameInput = overlay.querySelector("#rule-name-input");
        const titleEl = overlay.querySelector(".cinema-modal-header h3");
        if (nameInput && titleEl) {
            nameInput.addEventListener("input", () => {
                const trimmed = nameInput.value.trim();
                titleEl.textContent = `编辑规则 ${trimmed || index + 1}`;
            });
        }
    }
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
    if (!result) return;

    const clean = data.clean_result || {};
    const modes = data.modes || {};
    const currentMode = data.current_mode || "hybrid";
    const recommendation = data.recommendation;
    const removedStr = (clean.removed_items && clean.removed_items.length > 0) ? clean.removed_items.join(" · ") : "—";

    let html = '<div class="sim-compare">';
    html += '<div class="sim-clean-summary">';
    html += '<div class="sim-clean-title">文件名清洗结果</div>';
    html += '<div class="sim-clean-grid">';
    html += `<div class="sim-clean-item"><span class="sim-clean-label">clean_title</span><span class="sim-clean-value">${escapeHtml(clean.clean_title || "—")}</span></div>`;
    html += `<div class="sim-clean-item"><span class="sim-clean-label">year</span><span class="sim-clean-value">${clean.year || "—"}</span></div>`;
    html += `<div class="sim-clean-item"><span class="sim-clean-label">season / episode</span><span class="sim-clean-value">${clean.season ? "S" + clean.season : "—"} / ${clean.episode ? "E" + clean.episode : "—"}</span></div>`;
    html += `<div class="sim-clean-item"><span class="sim-clean-label">method</span><span class="sim-clean-value">${escapeHtml(clean.method || "regex")}</span></div>`;
    html += `<div class="sim-clean-item sim-clean-full"><span class="sim-clean-label">去除项</span><span class="sim-clean-value">${escapeHtml(removedStr)}</span></div>`;
    html += '</div></div>';

    const modeDefs = [
        { key: "provider_first", label: "Provider 优先", mark: "PF", desc: "Provider 权威，AI 仅补缺", formula: "T × R × data_gate" },
        { key: "ai_only", label: "纯 AI 刮削", mark: "AI", desc: "完全依赖 LLM", formula: "objective_cap × data_gate" },
        { key: "hybrid", label: "Provider + AI 联合", mark: "HY", desc: "两者全量联合", formula: "T × R × data_gate" },
    ];

    html += '<div class="sim-modes-grid">';
    for (const def of modeDefs) {
        const modeData = modes[def.key] || {};
        const res = modeData.result || {};
        const hasError = Boolean(res.error);
        const isCurrent = def.key === currentMode;
        const score = Number(res.confidence);
        const hasScore = Number.isFinite(score);
        const detail = modeData.confidence_detail || res.confidence_detail || {};

        html += `<div class="sim-mode-card${isCurrent ? " sim-mode-current" : ""}${hasError ? " sim-mode-error" : ""}">`;
        html += '<div class="sim-mode-head">';
        html += `<span class="sim-mode-icon">${escapeHtml(def.mark)}</span>`;
        html += '<div class="sim-mode-head-text">';
        html += `<span class="sim-mode-label">${escapeHtml(def.label)}${isCurrent ? '<span class="sim-mode-badge">当前配置</span>' : ""}</span>`;
        html += `<span class="sim-mode-desc">${escapeHtml(def.desc)}</span>`;
        html += '</div></div>';

        if (hasError) {
            html += '<div class="sim-mode-body">';
            html += `<div class="sim-mode-error-msg">${escapeHtml(res.error)}</div>`;
            html += `<div class="sim-mode-elapsed">耗时 ${Number(modeData.elapsed || 0).toFixed(2)}s</div>`;
            html += '</div></div>';
            continue;
        }

        html += '<div class="sim-mode-body">';
        html += '<div class="sim-mode-result">';
        html += `<div class="sim-mode-field"><span class="sim-mode-fk">标题</span><span class="sim-mode-fv">${escapeHtml(res.title_cn || res.title_en || res.title || "—")}</span></div>`;
        if (res.title_en && res.title_cn && res.title_en !== res.title_cn) {
            html += `<div class="sim-mode-field"><span class="sim-mode-fk">英文</span><span class="sim-mode-fv sim-mode-fv-sub">${escapeHtml(res.title_en)}</span></div>`;
        }
        html += `<div class="sim-mode-field"><span class="sim-mode-fk">年份</span><span class="sim-mode-fv">${res.year || "—"}</span></div>`;
        html += `<div class="sim-mode-field"><span class="sim-mode-fk">类型</span><span class="sim-mode-fv">${escapeHtml(res.type || res.media_type || "—")}</span></div>`;
        if (modeData.provider_type || res.provider_type) {
            const providerText = `${modeData.provider_type || res.provider_type}${(modeData.provider_id || res.provider_id) ? " · " + (modeData.provider_id || res.provider_id) : ""}`;
            html += `<div class="sim-mode-field"><span class="sim-mode-fk">Provider</span><span class="sim-mode-fv">${escapeHtml(providerText)}</span></div>`;
        }
        if (res.dimensions) {
            html += `<div class="sim-mode-dims">${_renderSimDims(res.dimensions)}</div>`;
        }
        html += '</div>';

        html += '<div class="sim-mode-confidence">';
        html += `<span class="sim-mode-score" style="color:${_simConfColor(score)}">${hasScore ? score.toFixed(3) : "--"}</span>`;
        html += `<span class="sim-mode-decision" style="color:${_simConfColor(score)}">${_simDecisionLabel(score, res.confidence_gate_blocked)}</span>`;
        html += '</div>';

        html += '<div class="sim-mode-calc">';
        html += `<span class="sim-mode-formula">公式：${escapeHtml(detail.formula || def.formula)}</span>`;
        html += _simConfidenceBreakdown(detail, res);
        if (res.scrape_trace) {
            html += `<button class="btn btn-secondary btn-xs sim-mode-detail-btn" data-confidence-detail-action="open" data-trace="${escapeHtml(JSON.stringify(res.scrape_trace))}" data-filename="${escapeHtml(data.filename || "")}">查看完整计算过程</button>`;
        }
        html += '</div>';

        html += '<div class="sim-mode-ai-tags">';
        if (modeData.ai_invoked) {
            html += '<span class="sim-ai-tag sim-ai-tag-active">AI 已调用</span>';
            if (modeData.ai_invoke_reason) {
                html += `<span class="sim-ai-tag sim-ai-tag-reason">${escapeHtml(modeData.ai_invoke_reason)}</span>`;
            }
        } else {
            html += '<span class="sim-ai-tag sim-ai-tag-idle">AI 未调用</span>';
        }
        if (modeData.search_enhanced === true) {
            html += '<span class="sim-ai-tag sim-ai-tag-search">联网搜索增强</span>';
        } else if (modeData.search_enhanced === false && modeData.ai_invoked) {
            html += '<span class="sim-ai-tag sim-ai-tag-local">AI 本地刮削</span>';
        }
        html += '</div>';
        html += `<div class="sim-mode-elapsed">耗时 ${Number(modeData.elapsed || 0).toFixed(2)}s</div>`;
        html += '</div></div>';
    }
    html += '</div>';

    if (recommendation) {
        html += '<div class="sim-recommendation">';
        html += '<div class="sim-recommend-head">';
        html += `<span>推荐使用 <strong>${escapeHtml(_modeLabel(recommendation.best_mode))}</strong></span>`;
        html += '</div>';
        html += '<div class="sim-recommend-body">';
        html += `<span>置信度 ${Number(recommendation.best_confidence || 0).toFixed(3)} · ${escapeHtml(recommendation.reason || "")}</span>`;
        html += '</div></div>';
    }

    html += '</div>';
    result.innerHTML = html;
}

function _simDecisionLabel(score, gateBlocked) {
    if (gateBlocked) return "维度否决";
    if (score >= 0.8) return "自动入库";
    if (score >= 0.5) return "需确认";
    if (score >= 0.3) return "需审核";
    return "失败";
}

function _modeLabel(modeKey) {
    const map = {
        provider_first: "Provider 优先",
        ai_only: "纯 AI 刮削",
        hybrid: "Provider + AI 联合",
    };
    return map[modeKey] || modeKey || "—";
}

function _simConfidenceBreakdown(detail, result) {
    const d = detail || {};
    const source = d.detail && Object.keys(d.detail).length ? d.detail : d;
    const rows = [];
    if (source.T !== undefined || source.R !== undefined) {
        rows.push(`T=${_simFormatNumber(source.T)}`);
        rows.push(`R=${_simFormatNumber(source.R)}`);
        rows.push(`gate=${_simFormatNumber(source.data_gate ?? d.data_gate ?? result.confidence_data_gate)}`);
    } else if (source.objective_cap !== undefined) {
        rows.push(`cap=${_simFormatNumber(source.objective_cap)}`);
        rows.push(`gate=${_simFormatNumber(source.data_gate ?? d.data_gate ?? result.confidence_data_gate)}`);
    } else if (d.search_conf !== undefined || d.data_gate !== undefined) {
        rows.push(`search=${_simFormatNumber(d.search_conf)}`);
        rows.push(`gate=${_simFormatNumber(d.data_gate)}`);
    }
    if (!rows.length) return '';
    return `<span class="sim-mode-calc-row">${escapeHtml(rows.join(" · "))}</span>`;
}

function _simFormatNumber(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "—";
    return num.toFixed(3);
}

function _simConfColor(value) {
    if (value >= 0.8) return "#22C55E";
    if (value >= 0.5) return "#3B82F6";
    if (value >= 0.3) return "#F59E0B";
    return "#EF4444";
}

function _renderSimDims(dims) {
    if (!dims || typeof dims !== "object") return "";
    let html = '<div class="sim-dim-list">';
    for (const key in dims) {
        const val = dims[key];
        const displayVal = (typeof val === "object" && val !== null) ? (val.value || JSON.stringify(val)) : val;
        html += `<span class="sim-dim-tag">${escapeHtml(key)}=${escapeHtml(String(displayVal))}</span>`;
    }
    html += '</div>';
    return html;
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

let currentConfig = {};

var _currentConfigSubTab = 'import';

var _navStack = [{ view: 'home', breadcrumb: '配置' }];

var _viewConfig = {
    'home':              { section: null,   viewGroup: null,         breadcrumb: null },
    'dir-sub':           { section: null,   viewGroup: null,         breadcrumb: '目录配置' },
    'source':            { section: 'basic', viewGroup: 'source',     breadcrumb: '源目录' },
    'temp':              { section: 'basic', viewGroup: 'temp',       breadcrumb: '中转目录' },
    'recycle':           { section: 'basic', viewGroup: 'recycle',    breadcrumb: '回收站目录' },
    'source-cleaner':    { section: 'source_cleaner', viewGroup: null, breadcrumb: '源文件智能清理' },
    'path-rules':        { section: 'path_rules', viewGroup: null,    breadcrumb: '入库规则', showReviewToggle: true },
    'metadata-providers':{ section: 'metadata.providers', viewGroup: null, breadcrumb: '影视刮削配置' },
    'llm-config':        { section: 'llm',  viewGroup: 'llm-config', breadcrumb: 'AI配置' },
    'llm-prompt':        { section: 'llm',  viewGroup: 'llm-prompt', breadcrumb: 'AI刮削提示词' },
    'file-watcher':      { section: 'file_watcher', viewGroup: null,  breadcrumb: '定时任务' },
    'import-options':    { section: 'import_options', viewGroup: null, breadcrumb: '入库名称规范', hideReviewToggle: true },
    'dimensions':        { section: 'dimensions', viewGroup: null,    breadcrumb: '影视分类维度' },
    'confidence':        { section: 'confidence', viewGroup: null,    breadcrumb: '置信度计算配置' },
    'server':            { section: 'server', viewGroup: null,        breadcrumb: '安全配置' },
    'hermes':            { section: 'hermes', viewGroup: null,        breadcrumb: 'Hermes通知' },
    'advanced':          { section: 'advanced', viewGroup: null,      breadcrumb: '系统设置' }
};

function navTo(viewId) {
    var cfg = _viewConfig[viewId];
    if (!cfg) return;
    _navStack.push({ view: viewId, breadcrumb: cfg.breadcrumb || viewId });
    renderView(viewId);
    updateBreadcrumb();
}

function navBack() {
    if (_navStack.length <= 1) return;
    _navStack.pop();
    var top = _navStack[_navStack.length - 1];
    renderView(top.view);
    updateBreadcrumb();
}

function navToBreadcrumb(index) {
    if (index < 0 || index >= _navStack.length - 1) return;
    _navStack = _navStack.slice(0, index + 1);
    var top = _navStack[_navStack.length - 1];
    renderView(top.view);
    updateBreadcrumb();
}

function renderView(viewId) {
    var cfg = _viewConfig[viewId];
    if (!cfg) return;

    var cardsHome = document.getElementById('config-cards-home');
    var dirSub = document.getElementById('config-dir-sub-cards');
    var sectionsHost = document.getElementById('cfg-sections-host');

    if (cardsHome) cardsHome.classList.remove('active');
    if (dirSub) dirSub.classList.remove('active');

    if (viewId === 'home') {
        if (cardsHome) cardsHome.classList.add('active');
        if (sectionsHost) {
            sectionsHost.querySelectorAll('.config-section').forEach(function(s) {
                s.classList.add('collapsed-section');
            });
        }
        return;
    }

    if (viewId === 'dir-sub') {
        if (dirSub) dirSub.classList.add('active');
        if (sectionsHost) {
            sectionsHost.querySelectorAll('.config-section').forEach(function(s) {
                s.classList.add('collapsed-section');
            });
        }
        return;
    }

    if (sectionsHost) {
        sectionsHost.querySelectorAll('.config-section').forEach(function(sec) {
            var sectionName = sec.getAttribute('data-section');
            if (sectionName === cfg.section) {
                sec.classList.remove('collapsed-section');
                if (cfg.viewGroup) {
                    sec.querySelectorAll('[data-view-group]').forEach(function(fg) {
                        if (fg.getAttribute('data-view-group') === cfg.viewGroup) {
                            fg.classList.add('view-visible');
                        } else {
                            fg.classList.remove('view-visible');
                        }
                    });
                } else {
                    sec.querySelectorAll('[data-view-group]').forEach(function(fg) {
                        fg.classList.add('view-visible');
                    });
                }
            } else {
                sec.classList.add('collapsed-section');
                sec.querySelectorAll('[data-view-group]').forEach(function(fg) {
                    fg.classList.remove('view-visible');
                });
            }
        });
    }

    var reviewToggle = document.getElementById('cfg-manual_review-enabled');
    if (reviewToggle) {
        var reviewGroup = reviewToggle.closest('.form-group');
        if (reviewGroup) {
            if (cfg.showReviewToggle) {
                reviewGroup.style.display = '';
            } else if (cfg.hideReviewToggle) {
                reviewGroup.style.display = 'none';
            } else {
                reviewGroup.style.display = '';
            }
        }
    }

    if (cfg.section === 'dimensions' && typeof loadDimensions === 'function') {
        loadDimensions();
    }
}

function updateBreadcrumb() {
    var container = document.getElementById('config-breadcrumb');
    if (!container) return;
    var backBtn = container.querySelector('.back-btn');
    if (backBtn) {
        backBtn.style.display = _navStack.length > 1 ? '' : 'none';
    }
    var itemsHtml = '';
    for (var i = 0; i < _navStack.length; i++) {
        var item = _navStack[i];
        var isCurrent = (i === _navStack.length - 1);
        if (i > 0) {
            itemsHtml += '<span class="config-breadcrumb-separator">›</span>';
        }
        if (isCurrent) {
            itemsHtml += '<span class="config-breadcrumb-item current">' + item.breadcrumb + '</span>';
        } else {
            itemsHtml += '<span class="config-breadcrumb-item" onclick="navToBreadcrumb(' + i + ')">' + item.breadcrumb + '</span>';
        }
    }
    var existingItems = container.querySelectorAll('.config-breadcrumb-item, .config-breadcrumb-separator');
    existingItems.forEach(function(el) { el.remove(); });
    container.insertAdjacentHTML('beforeend', itemsHtml);
}

async function savePathRulesWithReview() {
    await saveSection('path_rules');
    await saveSection('import_options');
}

function switchTab(tabName) {
    var panels = document.querySelectorAll('.panel');
    var tabs = document.querySelectorAll('.tab-btn');

    panels.forEach(p => p.classList.remove('active'));
    tabs.forEach(t => t.classList.remove('active'));

    document.getElementById(`${tabName}-panel`).classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.add('active');

    if (tabName === 'tasks') {
        loadTasks();
        refreshLogs();
    }

    if (tabName === 'config') {
        var breadcrumb = document.getElementById('config-breadcrumb');
        if (breadcrumb) breadcrumb.style.display = '';
        if (_navStack.length <= 1) {
            navTo('home');
        } else {
            var top = _navStack[_navStack.length - 1];
            renderView(top.view);
            updateBreadcrumb();
        }
    } else {
        var breadcrumb = document.getElementById('config-breadcrumb');
        if (breadcrumb) breadcrumb.style.display = 'none';
    }

    if (tabName === 'recycle') {
        loadRecycleList();
    }
}


function _safeGet(obj) {
    var result = obj;
    for (var i = 1; i < arguments.length; i++) {
        if (result == null) return '';
        result = result[arguments[i]];
    }
    return result || '';
}

async function loadConfig() {
    try {
        var result = await apiRequest('GET', '/config');
        if (result.code !== 200 || !result.data || !result.data.config) {
            showToast('加载配置失败: ' + (result.message || '未知错误'), 'error');
            return;
        }
        currentConfig = result.data.config;
        var c = currentConfig;

        var server = c.server || {};
        document.getElementById('cfg-server_api_key').value = server.api_key || '';
        document.getElementById('cfg-server_port').value = server.port || 9855;

        document.getElementById('cfg-source_dir').value = c.source_dir || '';
        document.getElementById('cfg-temp_dir').value = c.temp_dir || '';
        document.getElementById('cfg-log_dir').value = c.log_dir || '';

        var sourcePolicy = c.source_policy || {};
        document.getElementById('cfg-source_policy-recycle_dir').value = sourcePolicy.recycle_dir || sourcePolicy.quarantine_dir || '';
        document.getElementById('cfg-source_policy-cleanup_source_after_done').checked = sourcePolicy.cleanup_source_after_done !== false;
        document.getElementById('cfg-source_policy-recycle_retention_days').value = sourcePolicy.recycle_retention_days != null ? sourcePolicy.recycle_retention_days : 0;

        var sourceCleaner = c.source_cleaner || {};
        document.getElementById('cfg-source_cleaner-enabled').checked = !!sourceCleaner.enabled;
        var cleanerModeRadios = document.querySelectorAll('input[name="cfg-source_cleaner-cleanup_mode"]');
        var cleanerMode = sourceCleaner.cleanup_mode || 'media_only';
        cleanerModeRadios.forEach(function(r) { r.checked = (r.value === cleanerMode); });
        document.getElementById('cfg-source_cleaner-ai_enabled').checked = !!sourceCleaner.ai_enabled;
        document.getElementById('cfg-source_cleaner-merge_strategy').value = sourceCleaner.merge_strategy || 'intersection';
        document.getElementById('cfg-source_cleaner-junk_video_max_size_mb').value = sourceCleaner.junk_video_max_size_mb != null ? sourceCleaner.junk_video_max_size_mb : 0;
        document.getElementById('cfg-source_cleaner-delete_extensions').value = (sourceCleaner.delete_extensions || []).join('\n');
        document.getElementById('cfg-source_cleaner-protect_extensions').value = (sourceCleaner.protect_extensions || []).join('\n');
        document.getElementById('cfg-source_cleaner-blacklist_patterns').value = (sourceCleaner.blacklist_patterns || []).join('\n');
        document.getElementById('cfg-source_cleaner-cleanup_empty_dirs').checked = !!sourceCleaner.cleanup_empty_dirs;
        document.getElementById('cfg-source_cleaner-schedule').value = sourceCleaner.schedule || '';
        var aiPromptEl = document.getElementById('cfg-source_cleaner-ai_prompt');
        if (aiPromptEl) aiPromptEl.value = sourceCleaner.ai_prompt || '';
        onSourceCleanerToggle();

        var metadata = c.metadata || {};
        loadProviderConfigUI(metadata);

        var llm = c.llm || {};
        document.getElementById('cfg-llm_provider').value = llm.provider || 'openai';
        document.getElementById('cfg-llm_api_key').value = llm.api_key || '';
        document.getElementById('cfg-llm_base_url').value = llm.base_url || '';
        document.getElementById('cfg-llm_model').value = llm.model || '';
        document.getElementById('cfg-llm_fallback_model').value = llm.fallback_model || '';
        document.getElementById('cfg-llm_fast_model').value = llm.fast_model || '';
        document.getElementById('cfg-llm_timeout').value = llm.timeout || 30;
        document.getElementById('cfg-llm_max_retries').value = llm.max_retries || 2;
        document.getElementById('cfg-llm_retry_delay').value = llm.retry_delay || 3;
        document.getElementById('cfg-llm_confidence_threshold').value = llm.confidence_threshold || 0.8;
        document.getElementById('cfg-llm_verify_ssl').checked = !!llm.verify_ssl;

        var watcher = c.file_watcher || {};
        document.getElementById('cfg-watcher_enabled').checked = !!watcher.enabled;
        document.getElementById('cfg-watcher_poll_interval').value = watcher.poll_interval || 30;
        document.getElementById('cfg-watcher_ignore_patterns').value =
            (watcher.ignore_patterns || []).join('\n');

        var hermes = c.hermes || {};
        var webhook = hermes.webhook || {};
        document.getElementById('cfg-hermes_enabled').checked = !!hermes.enabled;
        document.getElementById('cfg-hermes_webhook_base_url').value = webhook.base_url || '';
        document.getElementById('cfg-hermes_webhook_route_name').value = webhook.route_name || '';
        document.getElementById('cfg-hermes_webhook_secret').value = webhook.secret || '';
        document.getElementById('cfg-hermes_webhook_timeout').value = webhook.timeout || 30;
        document.getElementById('cfg-hermes_webhook_max_retries').value = webhook.max_retries || 3;
        document.getElementById('cfg-hermes_webhook_retry_delay').value = webhook.retry_delay || 5;
        document.getElementById('cfg-hermes_webhook_verify_ssl').checked = !!webhook.verify_ssl;

        var events = webhook.events || [];
        document.getElementById('cfg-hermes_event_batch_start').checked = events.indexOf('batch_start') >= 0;
        document.getElementById('cfg-hermes_event_batch_complete').checked = events.indexOf('batch_complete') >= 0;
        document.getElementById('cfg-hermes_event_program_error').checked = events.indexOf('program_error') >= 0;

        onHermesToggle();

        var scan = c.source_policy || {};
        document.getElementById('cfg-source_dir_scan-recursive').checked = scan.scan_recursive !== false;
        document.getElementById('cfg-source_dir_scan-max_depth').value = scan.scan_max_depth || 5;

        if (typeof loadEnabledDimensions === 'function') {
            await loadEnabledDimensions();
        }

        var pathRules = c.path_rules || [];
        renderPathRules(pathRules);

        document.getElementById('cfg-fallback_dir').value = c.fallback_dir || '';

        var ft = c.filename_templates || {};
        document.getElementById('cfg-filename_templates-movie').value = ft.movie || '';
        document.getElementById('cfg-filename_templates-tv').value = ft.tv || '';
        document.getElementById('cfg-filename_templates-subtitle').value = ft.subtitle || '';

        var dup = c.duplicate_handling || {};
        document.getElementById('cfg-duplicate_handling-strategy').value = dup.strategy || 'skip';

        var tq = c.task_queue || {};
        document.getElementById('cfg-task_queue-max_concurrent').value = tq.max_concurrent || 1;

        var videoExts = c.video_extensions || [];
        var subExts = c.subtitle_extensions || [];
        var videoExtEl = document.getElementById('cfg-video_extensions');
        var subExtEl = document.getElementById('cfg-subtitle_extensions');
        if (videoExtEl) videoExtEl.value = videoExts.join('\n');
        if (subExtEl) subExtEl.value = subExts.join('\n');

        var manualReview = c.manual_review || {};
        document.getElementById('cfg-manual_review-enabled').checked = !!manualReview.enabled;

        if (result.data && result.data.prompts) {
            var prompts = result.data.prompts;
            document.getElementById('prompt-system').value = prompts.system_prompt || '';
        }

        loadConfidenceConfig(c);
    } catch (e) {
        console.error('loadConfig error:', e);
        showToast('加载配置异常: ' + e.message, 'error');
    }
}

function isMaskedValue(value) {
    return !value || value.indexOf('***') !== -1;
}

var _cachedProviderSchemas = {};

async function loadProviderConfigUI(metadata) {
    var container = document.getElementById('provider-configs-container');
    if (!container) return;
    container.innerHTML = '';
    var providerList = metadata.providers || [];
    var allProviders = [];
    try {
        var result = await apiRequest('GET', '/providers');
        if (result.code === 200 && result.data && result.data.providers) {
            allProviders = result.data.providers;
            _cachedProviderSchemas = {};
            for (var i = 0; i < allProviders.length; i++) {
                var p = allProviders[i];
                _cachedProviderSchemas[p.type] = p.config_schema || { fields: [] };
            }
            for (var i = 0; i < allProviders.length; i++) {
                var p = allProviders[i];
                var savedConfig = null;
                for (var j = 0; j < providerList.length; j++) {
                    if (providerList[j].type === p.type) { savedConfig = providerList[j]; break; }
                }
                var card = renderProviderCard(p, savedConfig);
                container.appendChild(card);
            }
        }
    } catch (e) {
        container.innerHTML = '<div class="provider-empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><div class="provider-empty-state-title">加载 Provider 配置失败</div><div class="provider-empty-state-desc">请检查服务是否正常运行后刷新页面</div></div>';
    }
    if (allProviders.length === 0) {
        container.innerHTML = '<div class="provider-empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg><div class="provider-empty-state-title">暂无可用的 Provider</div><div class="provider-empty-state-desc">请检查后端服务配置</div></div>';
    }
    _loadProviderPromptTabs(allProviders || []);
}

function renderProviderCard(provider, savedConfig) {
    var card = document.createElement('div');
    var enabled = savedConfig ? (savedConfig.enabled !== false) : (provider.enabled !== false);
    card.className = 'provider-card' + (enabled ? '' : ' disabled-provider');
    var config = {};
    var providerConfig = provider.config || {};
    if (savedConfig) {
        for (var ck in savedConfig) { config[ck] = savedConfig[ck]; }
        for (var ck in providerConfig) {
            if (!(ck in config) || config[ck] === '' || config[ck] === '***') {
                config[ck] = providerConfig[ck];
            }
        }
    } else {
        config = providerConfig;
    }
    var schema = provider.config_schema || { fields: [] };
    var html = '<div class="provider-card-header" onclick="toggleProviderCard(this)">';
    html += '<span class="provider-name">' + _escapeHtml(provider.display_name) + '</span>';
    html += '<svg class="collapse-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><polyline points="6 9 12 15 18 9"/></svg>';
    html += '<label class="toggle-switch" onclick="event.stopPropagation()"><input type="checkbox" id="cfg-provider-' + provider.type + '-enabled"' + (enabled ? ' checked' : '') + ' onchange="onProviderToggle(\'' + provider.type + '\', this)"><label for="cfg-provider-' + provider.type + '-enabled"></label></label>';
    html += '</div>';
    html += '<div class="provider-card-body">';
    for (var i = 0; i < schema.fields.length; i++) {
        var f = schema.fields[i];
        var val = config[f.key];
        if (val === undefined || val === null) val = f.default || '';
        if (f.key === 'api_key' && val === '') val = '';
        html += '<div class="form-group">';
        html += '<label class="form-label">' + _escapeHtml(f.label) + '</label>';
        if (f.type === 'password') {
            var placeholder = _escapeHtml(f.label);
            if (f.key === 'api_key' && config.api_key && config.api_key !== '') {
                placeholder = '已保存，留空保持不变';
            }
            html += '<input type="password" id="cfg-provider-' + provider.type + '-' + f.key + '" class="form-input" value="' + _escapeHtml(String(val)) + '" placeholder="' + placeholder + '" onfocus="if(this.value===\'***\')this.value=\'\'" onblur="if(!this.value&&this.dataset.hadKey)this.value=\'***\'"';
            if (f.key === 'api_key' && val === '***') {
                html += ' data-had-key="true"';
            }
            html += '>';
        } else if (f.type === 'select') {
            html += '<select id="cfg-provider-' + provider.type + '-' + f.key + '" class="form-select">';
            for (var j = 0; j < f.options.length; j++) {
                var opt = f.options[j];
                html += '<option value="' + _escapeHtml(opt.value) + '"' + (opt.value === val ? ' selected' : '') + '>' + _escapeHtml(opt.label) + '</option>';
            }
            html += '</select>';
        } else if (f.type === 'number') {
            html += '<input type="number" id="cfg-provider-' + provider.type + '-' + f.key + '" class="form-input" value="' + _escapeHtml(String(val)) + '">';
        } else {
            html += '<input type="text" id="cfg-provider-' + provider.type + '-' + f.key + '" class="form-input" value="' + _escapeHtml(String(val)) + '">';
        }
        html += '</div>';
    }
    html += '<div class="section-actions">';
    html += '<button class="btn btn-primary btn-sm" id="btn-save-provider-' + provider.type + '" onclick="saveSection(\'metadata.providers\')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> 保存</button>';
    html += '<button class="btn btn-secondary btn-sm" id="btn-test-provider-' + provider.type + '" onclick="testProvider(\'' + provider.type + '\')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg> 测试连接</button>';
    html += '<span class="test-result" id="provider-test-result-' + provider.type + '" style="display:none;"></span>';
    html += '<button class="btn btn-secondary btn-sm" onclick="showProviderPreviewModal(\'' + provider.type + '\')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> 刮削预览</button>';
    html += '</div>';
    html += '</div>';
    card.innerHTML = html;
    return card;
}

function toggleProviderCard(headerEl) {
    var card = headerEl.closest('.provider-card');
    if (card) card.classList.toggle('collapsed');
}

function onProviderToggle(providerType, checkbox) {
    var card = checkbox.closest('.provider-card');
    if (!card) return;
    if (checkbox.checked) {
        card.classList.remove('disabled-provider');
    } else {
        card.classList.add('disabled-provider');
    }
}

async function _loadProviderPromptTabs(allProviders) {
    var tabsContainer = document.getElementById('prompt-tabs-container');
    var panelsContainer = document.getElementById('prompt-tab-panels-container');
    if (!tabsContainer || !panelsContainer) return;

    var existingTabs = tabsContainer.querySelectorAll('.prompt-tab');
    for (var i = 0; i < existingTabs.length; i++) {
        if (existingTabs[i].getAttribute('data-tab') !== 'llm') {
            existingTabs[i].remove();
        }
    }
    var existingPanels = panelsContainer.querySelectorAll('.prompt-tab-panel');
    for (var i = 0; i < existingPanels.length; i++) {
        if (existingPanels[i].id !== 'prompt-tab-llm') {
            existingPanels[i].remove();
        }
    }

    for (var i = 0; i < allProviders.length; i++) {
        var p = allProviders[i];
        if (!p.enabled) continue;

        var tabBtn = document.createElement('button');
        tabBtn.className = 'prompt-tab';
        tabBtn.setAttribute('data-tab', p.type);
        tabBtn.setAttribute('onclick', "switchPromptTab('" + p.type + "')");
        tabBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg><span class="prompt-tab-label">LLM+' + _escapeHtml(p.display_name) + '</span>';
        tabsContainer.appendChild(tabBtn);

        var panel = document.createElement('div');
        panel.className = 'prompt-tab-panel';
        panel.id = 'prompt-tab-' + p.type;
        var promptVal = '';
        try {
            var promptResult = await apiRequest('GET', '/providers/' + p.type + '/prompts');
            if (promptResult.code === 200 && promptResult.data) {
                promptVal = promptResult.data.system_prompt || '';
            }
        } catch (e) {}
        panel.innerHTML = '<textarea id="prompt-' + p.type + '" class="prompt-textarea" placeholder="LLM+' + _escapeHtml(p.display_name) + ' 系统提示词...">' + _escapeHtml(promptVal) + '</textarea>' +
            '<div class="prompt-actions">' +
            '<button class="btn btn-primary btn-sm" onclick="saveProviderPrompt(\'' + p.type + '\')">保存</button>' +
            '<button class="btn btn-secondary btn-sm" onclick="resetProviderPrompt(\'' + p.type + '\')">恢复默认</button>' +
            '<button class="btn btn-secondary btn-sm" onclick="previewProviderFullPrompt(\'' + p.type + '\')">预览完整提示词</button>' +
            '</div>';
        panelsContainer.appendChild(panel);
    }
}

async function saveProviderPrompt(providerType) {
    var textarea = document.getElementById('prompt-' + providerType);
    if (!textarea) return;
    var result = await apiRequest('POST', '/providers/' + providerType + '/prompts', {
        system_prompt: textarea.value
    });
    if (result.code === 200) {
        showToast('LLM+Provider 提示词已保存，重启服务后生效', 'success');
    } else {
        showToast(result.message || '保存失败', 'error');
    }
}

async function resetProviderPrompt(providerType) {
    showConfirm('恢复默认', '确定要恢复出厂默认提示词吗？当前修改将丢失。', async function() {
        var result = await apiRequest('POST', '/providers/' + providerType + '/prompts/reset', {});
        if (result.code === 200) {
            showToast('已恢复出厂默认提示词，重启服务后生效', 'success');
            var prompts = await apiRequest('GET', '/providers/' + providerType + '/prompts');
            if (prompts.code === 200 && prompts.data) {
                var textarea = document.getElementById('prompt-' + providerType);
                if (textarea) textarea.value = prompts.data.system_prompt || '';
            }
        } else {
            showToast(result.message || '恢复失败', 'error');
        }
    });
}

async function previewProviderFullPrompt(providerType) {
    var textarea = document.getElementById('prompt-' + providerType);
    if (!textarea) return;
    var userPrompt = textarea.value;
    var dims = await _loadPromptDimensions();
    var dimListText = _buildDimensionListText(dims);
    var dimSchema = _buildDimensionSchema(dims);
    var fullPart = '\n\n【维度判断】\n当前需要判断的维度：\n' + dimListText + '\n\n请严格按以下JSON格式返回，不要添加任何解释文字：\n';
    var schema = JSON.stringify({
        "title_cn": "string|null", "title_en": "string|null", "year": "int|null",
        "resolution": "string|null", "quality": "string|null", "language": "string|null",
        "type": "movie|tv", "season": "int|null", "episode": "int|null",
        "dimensions": dimSchema, "confidence": "float"
    }, null, 2);
    var full = userPrompt + fullPart + schema;
    var overlay = document.createElement('div');
    overlay.className = 'prompt-preview-overlay';
    overlay.innerHTML = '<div class="prompt-preview-dialog">' +
        '<div class="prompt-preview-header">' +
        '<span class="prompt-preview-title">LLM+Provider 刮削提示词预览</span>' +
        '<button class="prompt-preview-close" onclick="this.closest(\'.prompt-preview-overlay\').remove()">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
        '</button></div>' +
        '<div class="prompt-preview-body">' +
        '<pre class="prompt-preview-content">' + _escapeHtml(full) + '</pre>' +
        '</div></div>';
    overlay.addEventListener('click', function(e) { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
}

function _buildBasicData() {
    return {
        source_dir: document.getElementById('cfg-source_dir').value,
        temp_dir: document.getElementById('cfg-temp_dir').value,
        source_policy: {
            recycle_dir: document.getElementById('cfg-source_policy-recycle_dir').value,
            cleanup_source_after_done: document.getElementById('cfg-source_policy-cleanup_source_after_done').checked,
            recycle_retention_days: parseInt(document.getElementById('cfg-source_policy-recycle_retention_days').value) || 0,
            scan_recursive: document.getElementById('cfg-source_dir_scan-recursive').checked,
            scan_max_depth: parseInt(document.getElementById('cfg-source_dir_scan-max_depth').value) || 5
        }
    };
}

function _buildSourceCleanerData() {
    return {
        source_cleaner: {
            enabled: document.getElementById('cfg-source_cleaner-enabled').checked,
            cleanup_mode: (document.querySelector('input[name="cfg-source_cleaner-cleanup_mode"]:checked') || {}).value || 'media_only',
            ai_enabled: document.getElementById('cfg-source_cleaner-ai_enabled').checked,
            merge_strategy: document.getElementById('cfg-source_cleaner-merge_strategy').value || 'intersection',
            junk_video_max_size_mb: parseInt(document.getElementById('cfg-source_cleaner-junk_video_max_size_mb').value) || 0,
            delete_extensions: _parseMultiLineInput('cfg-source_cleaner-delete_extensions'),
            protect_extensions: _parseMultiLineInput('cfg-source_cleaner-protect_extensions'),
            blacklist_patterns: _parseMultiLineInput('cfg-source_cleaner-blacklist_patterns'),
            cleanup_empty_dirs: document.getElementById('cfg-source_cleaner-cleanup_empty_dirs').checked,
            schedule: document.getElementById('cfg-source_cleaner-schedule').value.trim(),
            ai_prompt: (document.getElementById('cfg-source_cleaner-ai_prompt') || {}).value || ''
        }
    };
}

function _parseMultiLineInput(id) {
    var el = document.getElementById(id);
    if (!el) return [];
    var raw = el.value || '';
    return raw.split(/[\n,]+/).map(function(s) { return s.trim(); }).filter(Boolean);
}

function _buildPathRulesData() {
    var rules = collectPathRulesFromDOM();
    var uncheckedRules = [];
    for (var i = 0; i < rules.length; i++) {
        var cond = rules[i].conditions || {};
        if (Object.keys(cond).length === 0) {
            uncheckedRules.push(i + 1);
        }
    }
    return {
        path_rules: rules,
        fallback_dir: document.getElementById('cfg-fallback_dir') ? document.getElementById('cfg-fallback_dir').value : '',
        _uncheckedRules: uncheckedRules
    };
}

function _buildImportOptionsData() {
    return {
        manual_review: {
            enabled: document.getElementById('cfg-manual_review-enabled').checked
        },
        duplicate_handling: {
            strategy: document.getElementById('cfg-duplicate_handling-strategy').value
        },
        filename_templates: {
            movie: document.getElementById('cfg-filename_templates-movie').value,
            tv: document.getElementById('cfg-filename_templates-tv').value,
            subtitle: document.getElementById('cfg-filename_templates-subtitle').value
        }
    };
}

function _buildProviderData() {
    var providers = [];
    var metadata = currentConfig.metadata || {};
    var providerList = metadata.providers || [];
    var allTypes = Object.keys(_cachedProviderSchemas);
    var seenTypes = {};
    for (var i = 0; i < providerList.length; i++) {
        var p = providerList[i];
        var ptype = p.type;
        seenTypes[ptype] = true;
        var providerData = {
            type: ptype,
            enabled: document.getElementById('cfg-provider-' + ptype + '-enabled') ? document.getElementById('cfg-provider-' + ptype + '-enabled').checked : (p.enabled !== false),
        };
        var schemaFields = (_cachedProviderSchemas[ptype] && _cachedProviderSchemas[ptype].fields) || [];
        for (var j = 0; j < schemaFields.length; j++) {
            var f = schemaFields[j];
            if (f.key === 'api_key') {
                var apiKeyInput = document.getElementById('cfg-provider-' + ptype + '-api_key');
                if (apiKeyInput) {
                    var val = apiKeyInput.value;
                    if (val && !isMaskedValue(val)) {
                        providerData[f.key] = val;
                    } else if (p.api_key && p.api_key !== '***') {
                        providerData[f.key] = p.api_key;
                    }
                }
            } else {
                var input = document.getElementById('cfg-provider-' + ptype + '-' + f.key);
                if (input) providerData[f.key] = input.value;
            }
        }
        providers.push(providerData);
    }
    for (var k = 0; k < allTypes.length; k++) {
        var t = allTypes[k];
        if (seenTypes[t]) continue;
        var providerData = {
            type: t,
            enabled: document.getElementById('cfg-provider-' + t + '-enabled') ? document.getElementById('cfg-provider-' + t + '-enabled').checked : false,
        };
        var schemaFields = (_cachedProviderSchemas[t] && _cachedProviderSchemas[t].fields) || [];
        for (var j = 0; j < schemaFields.length; j++) {
            var f = schemaFields[j];
            if (f.key === 'api_key') {
                var apiKeyInput = document.getElementById('cfg-provider-' + t + '-api_key');
                if (apiKeyInput) {
                    var val = apiKeyInput.value;
                    if (val && !isMaskedValue(val)) {
                        providerData[f.key] = val;
                    }
                }
            } else {
                var input = document.getElementById('cfg-provider-' + t + '-' + f.key);
                if (input) providerData[f.key] = input.value;
            }
        }
        providers.push(providerData);
    }
    return { metadata: { providers: providers } };
}
var _buildTmdbData = _buildProviderData;

function _buildLlmData() {
    var data = {
        llm: {
            provider: document.getElementById('cfg-llm_provider').value,
            base_url: document.getElementById('cfg-llm_base_url').value,
            model: document.getElementById('cfg-llm_model').value,
            fallback_model: document.getElementById('cfg-llm_fallback_model').value,
            fast_model: document.getElementById('cfg-llm_fast_model').value,
            timeout: parseInt(document.getElementById('cfg-llm_timeout').value) || 30,
            max_retries: parseInt(document.getElementById('cfg-llm_max_retries').value) || 2,
            retry_delay: parseInt(document.getElementById('cfg-llm_retry_delay').value) || 3,
            confidence_threshold: parseFloat(document.getElementById('cfg-llm_confidence_threshold').value) || 0.8,
            verify_ssl: document.getElementById('cfg-llm_verify_ssl').checked
        }
    };
    var apiKey = document.getElementById('cfg-llm_api_key').value;
    if (apiKey && !isMaskedValue(apiKey)) {
        data.llm.api_key = apiKey;
    } else if (currentConfig.llm && currentConfig.llm.api_key) {
        data.llm.api_key = currentConfig.llm.api_key;
    }
    return data;
}

function _buildServerData() {
    var data = {
        server: {
            port: parseInt(document.getElementById('cfg-server_port').value) || 9855
        }
    };
    var serverApiKey = document.getElementById('cfg-server_api_key').value;
    if (serverApiKey && !isMaskedValue(serverApiKey)) {
        data.server.api_key = serverApiKey;
    } else if (currentConfig.server && currentConfig.server.api_key) {
        data.server.api_key = currentConfig.server.api_key;
    }
    return data;
}

function _buildHermesData() {
    var data = {
        hermes: {
            enabled: document.getElementById('cfg-hermes_enabled').checked,
            webhook: {
                base_url: document.getElementById('cfg-hermes_webhook_base_url').value,
                route_name: document.getElementById('cfg-hermes_webhook_route_name').value,
                timeout: parseInt(document.getElementById('cfg-hermes_webhook_timeout').value) || 30,
                max_retries: parseInt(document.getElementById('cfg-hermes_webhook_max_retries').value) || 3,
                retry_delay: parseInt(document.getElementById('cfg-hermes_webhook_retry_delay').value) || 5,
                verify_ssl: document.getElementById('cfg-hermes_webhook_verify_ssl').checked
            }
        }
    };
    var secret = document.getElementById('cfg-hermes_webhook_secret').value;
    if (secret && !isMaskedValue(secret)) {
        data.hermes.webhook.secret = secret;
    } else if (currentConfig.hermes && currentConfig.hermes.webhook && currentConfig.hermes.webhook.secret) {
        data.hermes.webhook.secret = currentConfig.hermes.webhook.secret;
    }
    var hermesEvents = [];
    if (document.getElementById('cfg-hermes_event_batch_start').checked) hermesEvents.push('batch_start');
    if (document.getElementById('cfg-hermes_event_batch_complete').checked) hermesEvents.push('batch_complete');
    if (document.getElementById('cfg-hermes_event_program_error').checked) hermesEvents.push('program_error');
    data.hermes.webhook.events = hermesEvents;
    return data;
}

function _buildWatcherData() {
    return {
        file_watcher: {
            enabled: document.getElementById('cfg-watcher_enabled').checked,
            poll_interval: parseInt(document.getElementById('cfg-watcher_poll_interval').value),
            ignore_patterns: document.getElementById('cfg-watcher_ignore_patterns').value
                .split('\n').filter(line => line.trim())
        }
    };
}

function _buildAdvancedData() {
    var videoExtEl = document.getElementById('cfg-video_extensions');
    var subExtEl = document.getElementById('cfg-subtitle_extensions');
    var videoExts = [];
    var subExts = [];
    if (videoExtEl) {
        videoExts = videoExtEl.value.split('\n').map(function(s) {
            s = s.trim();
            if (s && !s.startsWith('.')) s = '.' + s;
            return s;
        }).filter(function(s) { return s; });
    }
    if (subExtEl) {
        subExts = subExtEl.value.split('\n').map(function(s) {
            s = s.trim();
            if (s && !s.startsWith('.')) s = '.' + s;
            return s;
        }).filter(function(s) { return s; });
    }
    return {
        log_dir: document.getElementById('cfg-log_dir').value,
        task_queue: {
            max_concurrent: parseInt(document.getElementById('cfg-task_queue-max_concurrent').value)
        },
        video_extensions: videoExts,
        subtitle_extensions: subExts
    };
}

var _sectionBuilders = {
    'basic': _buildBasicData,
    'source_cleaner': _buildSourceCleanerData,
    'path_rules': _buildPathRulesData,
    'import_options': _buildImportOptionsData,
    'metadata.providers': _buildProviderData,
    'llm': _buildLlmData,
    'server': _buildServerData,
    'hermes': _buildHermesData,
    'file_watcher': _buildWatcherData,
    'advanced': _buildAdvancedData,
    'confidence': _buildConfidenceData
};

async function saveSection(sectionName) {
    var builder = _sectionBuilders[sectionName];
    if (!builder) {
        showToast('未知的配置区块: ' + sectionName, 'error');
        return;
    }

    var data = builder();

    if (sectionName === 'basic') {
        var sourceDir = (data.source_dir || '').replace(/\/+$/, '');
        var tempDir = (data.temp_dir || '').replace(/\/+$/, '');
        var recycleDir = (data.source_policy && (data.source_policy.recycle_dir || data.source_policy.quarantine_dir) || '').replace(/\/+$/, '');

        var missing = [];
        if (!sourceDir) missing.push('源目录');
        if (!tempDir) missing.push('中转目录');
        if (!recycleDir) missing.push('回收站路径');
        if (missing.length > 0) {
            showToast(missing.join('、') + ' 为必填项', 'error');
            return;
        }

        var conflicts = [];
        if (sourceDir && tempDir && sourceDir === tempDir) conflicts.push('源目录与中转目录不能相同');
        if (sourceDir && recycleDir && sourceDir === recycleDir) conflicts.push('源目录与回收站目录不能相同');
        if (tempDir && recycleDir && tempDir === recycleDir) conflicts.push('中转目录与回收站目录不能相同');
        if (conflicts.length > 0) {
            showToast(conflicts.join('；'), 'error');
            return;
        }
    }

    if (sectionName === 'basic') {
        showToast('正在检查路径权限...', 'info');
        var permCheck = await apiRequest('POST', '/config/check-permission', {
            source_dir: data.source_dir,
            temp_dir: data.temp_dir,
            log_dir: currentConfig.log_dir || '',
            path_rules: currentConfig.path_rules || []
        });
        if (permCheck && permCheck.code === 200 && permCheck.data) {
            if (!permCheck.data.all_ok) {
                showPermissionDialog(permCheck.data.issues || []);
                return;
            }
        } else {
            showToast('权限检查接口异常，但仍可尝试保存', 'warning');
        }
    }

    if (sectionName === 'path_rules') {
        showToast('正在检查入库目录权限...', 'info');
        var permCheck2 = await apiRequest('POST', '/config/check-permission', {
            source_dir: '',
            temp_dir: '',
            log_dir: '',
            path_rules: data.path_rules || []
        });
        if (permCheck2 && permCheck2.code === 200 && permCheck2.data) {
            if (!permCheck2.data.all_ok) {
                showPermissionDialog(permCheck2.data.issues || []);
                return;
            }
        }
        if (data._uncheckedRules && data._uncheckedRules.length > 0) {
            var ruleList = data._uncheckedRules.join('、');
            if (!confirm('规则 #' + ruleList + ' 未设置任何维度条件，将匹配所有文件。\n\n如果这是兜底规则请确认保存，否则建议回到页面设置维度条件后再保存。\n\n点击"确定"保存，点击"取消"返回修改。')) {
                return;
            }
        }
    }

    if (sectionName === 'source_cleaner') {
        var cleanerData = data.source_cleaner || data;
        if (cleanerData.enabled) {
            showToast('正在检查路径权限...', 'info');
            var sourceDir = currentConfig.source_dir || '';
            var recycleDir = (currentConfig.source_policy || {}).recycle_dir || '';
            var permIssues = [];
            if (sourceDir) {
                var srcPerm = await apiRequest('POST', '/path/test', { path: sourceDir, need_write: true });
                if (!srcPerm || !srcPerm.data || !srcPerm.data.ok) {
                    permIssues.push({ field: 'source_dir', path: sourceDir, message: (srcPerm && srcPerm.data && srcPerm.data.message) || '源目录无写权限' });
                }
            }
            if (recycleDir) {
                var rclPerm = await apiRequest('POST', '/path/test', { path: recycleDir, need_write: true });
                if (!rclPerm || !rclPerm.data || !rclPerm.data.ok) {
                    permIssues.push({ field: 'recycle_dir', path: recycleDir, message: (rclPerm && rclPerm.data && rclPerm.data.message) || '回收站目录无写权限' });
                }
            }
            if (permIssues.length > 0) {
                showPermissionDialog(permIssues);
                return;
            }
        }
    }

    delete data._uncheckedRules;
    var result = await apiRequest('POST', '/config/section', {
        section: sectionName,
        data: data
    });

    if (result.code === 200) {
        showToast(result.message || '配置已保存。变更需重启服务才能完全生效。', 'success');
        loadConfig();
        loadHealth();
    } else {
        showToast(result.message || '保存失败', 'error');
    }
}

async function validateBasicSection() {
    var data = _buildBasicData();
    var sourceDir = (data.source_dir || '').replace(/\/+$/, '');
    var tempDir = (data.temp_dir || '').replace(/\/+$/, '');
    var recycleDir = (data.source_policy && (data.source_policy.recycle_dir || data.source_policy.quarantine_dir) || '').replace(/\/+$/, '');

    var missing = [];
    if (!sourceDir) missing.push('源目录');
    if (!tempDir) missing.push('中转目录');
    if (!recycleDir) missing.push('回收站路径');
    if (missing.length > 0) {
        showToast(missing.join('、') + ' 为必填项', 'error');
        return;
    }

    var conflicts = [];
    if (sourceDir && tempDir && sourceDir === tempDir) conflicts.push('源目录与中转目录不能相同');
    if (sourceDir && recycleDir && sourceDir === recycleDir) conflicts.push('源目录与回收站目录不能相同');
    if (tempDir && recycleDir && tempDir === recycleDir) conflicts.push('中转目录与回收站目录不能相同');
    if (conflicts.length > 0) {
        showToast(conflicts.join('；'), 'error');
        return;
    }

    showToast('正在检查路径权限...', 'info');
    var permCheck = await apiRequest('POST', '/config/check-permission', {
        source_dir: data.source_dir,
        temp_dir: data.temp_dir,
        log_dir: currentConfig.log_dir || '',
        path_rules: currentConfig.path_rules || []
    });
    if (permCheck && permCheck.code === 200 && permCheck.data) {
        if (!permCheck.data.all_ok) {
            showPermissionDialog(permCheck.data.issues || []);
        } else {
            showToast('路径权限验证通过！', 'success');
        }
    } else {
        showToast('权限检查接口异常', 'warning');
    }
}

async function testPathPermission(inputId, needWrite) {
    var input = document.getElementById(inputId);
    var resultEl = document.getElementById('perm-result-' + inputId);
    if (!input || !resultEl) return;

    var path = (input.value || '').trim();
    if (!path) {
        resultEl.className = 'perm-result perm-error';
        resultEl.textContent = '请先填写路径再测试';
        return;
    }

    resultEl.className = 'perm-result perm-loading';
    resultEl.textContent = '正在测试...';

    var result = await apiRequest('POST', '/path/test', { path: path, need_write: !!needWrite });
    if (result && result.code === 200 && result.data) {
        var d = result.data;
        if (d.ok) {
            resultEl.className = 'perm-result perm-ok';
            resultEl.innerHTML = '✅ ' + (d.message || '权限正常') + (d.user ? '（当前用户: ' + d.user + '）' : '');
        } else {
            resultEl.className = 'perm-result perm-error';
            resultEl.innerHTML = '❌ ' + (d.message || '权限测试失败') + (d.hint ? '<div style="margin-top:6px;white-space:pre-line;font-size:12px;">' + d.hint + '</div>' : '');
        }
    } else {
        resultEl.className = 'perm-result perm-error';
        resultEl.textContent = '测试失败: ' + ((result && result.message) || '未知错误');
    }
}

async function testAllImportPaths() {
    var resultEl = document.getElementById('perm-result-import-dirs');
    if (!resultEl) return;

    var path_rules = collectPathRulesFromDOM();
    if (!path_rules || path_rules.length === 0) {
        resultEl.className = 'perm-result perm-error';
        resultEl.textContent = '请先添加入库规则';
        return;
    }

    resultEl.className = 'perm-result perm-loading';
    resultEl.textContent = '正在测试所有入库目录...';

    var result = await apiRequest('POST', '/config/check-permission', {
        source_dir: '',
        temp_dir: '',
        log_dir: '',
        path_rules: path_rules
    });

    if (result && result.code === 200 && result.data) {
        var issues = result.data.issues || [];
        if (issues.length === 0) {
            resultEl.className = 'perm-result perm-ok';
            resultEl.textContent = '✅ 所有入库目录权限正常';
        } else {
            var html = '<div style="font-weight:600;margin-bottom:6px;">❌ 以下入库目录权限有问题：</div>';
            issues.forEach(function(it) {
                html += '<div style="margin-bottom:8px;">';
                html += '<div style="font-family:monospace;">' + it.path + '</div>';
                html += '<div style="margin-top:4px;font-size:12px;">' + (it.message || '') + '</div>';
                if (it.hint) {
                    html += '<div style="margin-top:4px;padding:6px;background:#fffbeb;border-radius:4px;color:#92400e;font-size:12px;white-space:pre-line;">' + it.hint + '</div>';
                }
                html += '</div>';
            });
            resultEl.className = 'perm-result perm-error';
            resultEl.innerHTML = html;
        }
    } else {
        resultEl.className = 'perm-result perm-error';
        resultEl.textContent = '测试失败: ' + ((result && result.message) || '未知错误');
    }
}

function parsePathRulesYaml(text) {
    var rules = [];
    var lines = text.split('\n');
    var current = null;
    var inConditions = false;
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        var trimmed = line.replace(/\s+$/, '');
        if (!trimmed.trim()) continue;
        if (/^\s*-\s+/.test(trimmed)) {
            if (current) rules.push(current);
            current = { conditions: {}, template: '' };
            inConditions = false;
            var rest = trimmed.replace(/^\s*-\s+/, '');
            if (rest.indexOf('conditions:') === 0) inConditions = true;
            continue;
        }
        if (!current) continue;
        var kvMatch = trimmed.match(/^\s*([a-zA-Z_]+)\s*:\s*(.*)$/);
        if (kvMatch) {
            var key = kvMatch[1];
            var val = kvMatch[2].trim().replace(/^['"]|['"]$/g, '');
            if (key === 'conditions') {
                inConditions = true;
                continue;
            }
            if (key === 'template') {
                inConditions = false;
                current.template = val;
                continue;
            }
            if (inConditions) {
                current.conditions[key] = val;
            }
        }
    }
    if (current) rules.push(current);
    return rules;
}

function showPermissionDialog(issues) {
    var overlay = document.createElement('div');
    overlay.className = 'perm-dialog-overlay';

    var html = '<div class="perm-dialog">';
    html += '<div class="perm-dialog-header">⚠️ 权限不足，无法保存配置</div>';
    html += '<div class="perm-dialog-body">';
    html += '<div style="margin-bottom:12px;color:#475569;">检测到以下路径权限不足，请按指引完成授权后重新保存：</div>';
    issues.forEach(function(it) {
        html += '<div class="perm-issue-item">';
        html += '<div class="perm-issue-field">字段: ' + (it.field || '-') + '</div>';
        html += '<div class="perm-issue-path">路径: ' + (it.path || '-') + '</div>';
        if (it.rule_template) {
            html += '<div style="font-size:12px;color:#64748b;margin-top:2px;">所属规则模板: ' + it.rule_template + '</div>';
        }
        html += '<div style="margin-top:6px;color:#991b1b;">' + (it.message || '') + '</div>';
        if (it.hint) {
            html += '<div class="perm-issue-hint">' + it.hint + '</div>';
        }
        html += '</div>';
    });
    html += '</div>';
    html += '<div class="perm-dialog-footer">';
    html += '<button class="btn btn-primary" onclick="this.closest(\'.perm-dialog-overlay\').remove()">我知道了</button>';
    html += '</div>';
    html += '</div>';

    overlay.innerHTML = html;
    document.body.appendChild(overlay);
}

function toggleAdvancedSection(headerEl) {
    var section = headerEl.closest('.config-section');
    if (!section) return;
    var body = section.querySelector('.config-section-body');
    if (!body) return;
    var isHidden = body.classList.contains('collapsed-section');
    if (isHidden) {
        body.classList.remove('collapsed-section');
    } else {
        body.classList.add('collapsed-section');
    }
    headerEl.classList.toggle('expanded', isHidden);
}

function onHermesToggle() {
    var checkbox = document.getElementById('cfg-hermes_enabled');
    var hermesSection = document.getElementById('hermes-config-section');
    if (!checkbox || !hermesSection) return;
    var enabled = checkbox.checked;
    var formGroups = hermesSection.querySelectorAll('.form-group');
    for (var i = 1; i < formGroups.length; i++) {
        if (enabled) {
            formGroups[i].classList.remove('collapsed-section');
        } else {
            formGroups[i].classList.add('collapsed-section');
        }
    }
    var formRows = hermesSection.querySelectorAll('.form-row');
    formRows.forEach(function(row) {
        if (enabled) {
            row.classList.remove('collapsed-section');
        } else {
            row.classList.add('collapsed-section');
        }
    });
}

function onSourceCleanerToggle() {
    var checkbox = document.getElementById('cfg-source_cleaner-enabled');
    if (!checkbox) return;
    var enabled = checkbox.checked;
    var fields = document.getElementById('source-cleaner-fields');
    if (fields) {
        fields.style.display = enabled ? '' : 'none';
    }
    var aiCheckbox = document.getElementById('cfg-source_cleaner-ai_enabled');
    var mergeGroup = document.getElementById('source-cleaner-merge-strategy-group');
    if (mergeGroup) {
        mergeGroup.style.display = (enabled && aiCheckbox && aiCheckbox.checked) ? '' : 'none';
    }
    var aiPromptRow = document.getElementById('sc-ai-prompt-row');
    if (aiPromptRow) {
        aiPromptRow.style.display = (enabled && aiCheckbox && aiCheckbox.checked) ? '' : 'none';
    }
}

function showSCAIPromptModal() {
    var modal = document.getElementById('sc-ai-prompt-modal');
    if (modal) modal.style.display = 'flex';
}

var SC_AI_DEFAULT_PROMPT = '你是"影音库AI智能整理"系统的源目录清理助手。你的任务是分析源目录中的文件，判断哪些是垃圾文件应该删除，哪些是影视相关文件应该保留。\n\n【分析原则】\n1. 整体视角：分析整个目录的文件构成，而非孤立判断单个文件\n2. 容量对比：同一目录下，视频文件大小差异显著时，小文件大概率是广告/样本/预告\n3. 命名模式：文件名含 sample、trailer、预告、花絮、广告等关键词的应删除\n4. 关联识别：与视频同名的 .nfo、.jpg、.png 等是影视元数据/海报，应保留\n5. 字幕文件：.srt、.ass 等字幕文件应保留\n6. 保守原则：无法确定时倾向于保留，避免误删\n\n【判断标准】\n- 主视频文件（通常最大的视频文件）→ 保留\n- 字幕文件 → 保留\n- 与主视频同名的元数据/海报 → 保留\n- 样本/预告/广告视频（明显小于主视频）→ 删除\n- BT下载附带的无用文件（.url, .txt说明, 下载站广告图）→ 删除\n- 无法判断的文件 → 保留\n\n【输出格式】\n请严格按以下JSON格式返回，不要添加任何解释文字：\n{\n    "analysis": "简要分析说明",\n    "decisions": {\n        "文件名": {"action": "keep或delete", "reason": "判断理由"}\n    }\n}';

function resetSCAIPrompt() {
    var el = document.getElementById('cfg-source_cleaner-ai_prompt');
    if (el) {
        el.value = SC_AI_DEFAULT_PROMPT;
        showToast('已恢复为默认提示词', 'success');
    }
}

function saveSCAIPrompt() {
    closeModal('sc-ai-prompt-modal');
    showToast('AI提示词已暂存，请点击保存按钮提交配置', 'info');
}

function switchSCTab(tabName) {
    var tabs = document.querySelectorAll('.sc-tab-btn');
    var panels = document.querySelectorAll('.sc-tab-panel');
    tabs.forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-sc-tab') === tabName);
    });
    panels.forEach(function(p) {
        p.classList.toggle('active', p.getAttribute('data-sc-panel') === tabName);
    });
}

function toggleSCAdvanced() {
    var toggle = document.querySelector('.sc-advanced-toggle');
    var body = document.getElementById('sc-advanced-body');
    if (!toggle || !body) return;
    var collapsed = body.classList.contains('collapsed-section');
    if (collapsed) {
        body.classList.remove('collapsed-section');
        toggle.classList.add('expanded');
    } else {
        body.classList.add('collapsed-section');
        toggle.classList.remove('expanded');
    }
}

async function testLLM() {
    var btn = document.getElementById('btn-test-llm');
    var resultEl = document.getElementById('llm-test-result');
    btn.disabled = true;
    resultEl.style.display = 'inline-block';
    resultEl.className = 'test-result loading';
    resultEl.textContent = '测试中...';

    var data = _buildLlmData();
    var llm = data.llm || {};
    var result = await apiRequest('POST', '/config/test-llm', {
        base_url: llm.base_url || '',
        api_key: llm.api_key || '',
        model: llm.model || '',
        provider: llm.provider || 'openai'
    });

    btn.disabled = false;
    if (result.code === 200 && result.data && result.data.success) {
        resultEl.className = 'test-result success';
        resultEl.textContent = '✓ ' + (result.data.message || '连通正常');
    } else {
        resultEl.className = 'test-result error';
        resultEl.textContent = '✗ ' + (result.data && result.data.message || result.message || '测试失败');
    }
}

async function testHermes() {
    var btn = document.getElementById('btn-test-hermes');
    var resultEl = document.getElementById('hermes-test-result');
    btn.disabled = true;
    resultEl.style.display = 'inline-block';
    resultEl.className = 'test-result loading';
    resultEl.textContent = '测试中...';

    var data = _buildHermesData();
    var hermes = data.hermes || {};
    var webhook = hermes.webhook || {};
    var result = await apiRequest('POST', '/config/test-hermes', {
        base_url: webhook.base_url || '',
        route_name: webhook.route_name || '',
        secret: webhook.secret || ''
    });

    btn.disabled = false;
    if (result.code === 200 && result.data && result.data.success) {
        resultEl.className = 'test-result success';
        resultEl.textContent = '✓ ' + (result.data.message || '通知发送成功');
    } else {
        resultEl.className = 'test-result error';
        resultEl.textContent = '✗ ' + (result.data && result.data.message || result.message || '测试失败');
    }
}

async function testProvider(providerType) {
    var btn = document.getElementById('btn-test-provider-' + providerType);
    var resultEl = document.getElementById('provider-test-result-' + providerType);
    if (!btn || !resultEl) return;
    btn.disabled = true;
    resultEl.style.display = 'inline-block';
    resultEl.className = 'test-result loading';
    resultEl.textContent = '测试中...';
    var result = await apiRequest('POST', '/providers/' + providerType + '/test', {});
    btn.disabled = false;
    if (result.code === 200 && result.data && result.data.success) {
        resultEl.className = 'test-result success';
        resultEl.textContent = '✓ ' + (result.data.message || '连通正常');
    } else {
        resultEl.className = 'test-result error';
        resultEl.textContent = '✗ ' + (result.data && result.data.message || result.message || '测试失败');
    }
}
var testTMDb = function() { testProvider('tmdb'); };

var _currentPreviewProviderType = 'tmdb';

function showProviderPreviewModal(providerType) {
    _currentPreviewProviderType = providerType || 'tmdb';
    var existing = document.getElementById('tmdb-preview-modal');
    if (existing) existing.remove();

    var lang = 'zh-CN';
    var cfgLangEl = document.getElementById('cfg-provider-' + _currentPreviewProviderType + '-language');
    if (cfgLangEl && cfgLangEl.value) lang = cfgLangEl.value;

    var providerDisplayName = _currentPreviewProviderType.toUpperCase();

    var modal = document.createElement('div');
    modal.id = 'tmdb-preview-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML =
        '<div class="modal tmdb-preview-modal-content">' +
            '<div class="modal-header">' +
                '<h3>' + _escapeHtml(providerDisplayName) + ' 刮削预览</h3>' +
                '<button class="modal-close" onclick="closeTmdbPreviewModal()">&times;</button>' +
            '</div>' +
            '<div class="tmdb-preview-toolbar">' +
                '<input type="text" id="tmdb-preview-query" placeholder="输入影视名称..." class="form-input" style="flex:1;" onkeydown="if(event.key===\'Enter\')doTmdbPreview()">' +
                '<select id="tmdb-preview-type" class="form-select" style="width:100px;">' +
                    '<option value="movie">电影</option>' +
                    '<option value="tv">电视剧</option>' +
                '</select>' +
                '<select id="tmdb-preview-lang" class="form-select" style="width:130px;">' +
                    '<option value="zh-CN"' + (lang === 'zh-CN' ? ' selected' : '') + '>中文 (zh-CN)</option>' +
                    '<option value="en-US"' + (lang === 'en-US' ? ' selected' : '') + '>英文 (en-US)</option>' +
                    '<option value="ja-JP"' + (lang === 'ja-JP' ? ' selected' : '') + '>日文 (ja-JP)</option>' +
                    '<option value="ko-KR"' + (lang === 'ko-KR' ? ' selected' : '') + '>韩文 (ko-KR)</option>' +
                '</select>' +
                '<button class="btn btn-primary" id="btn-tmdb-preview-search" onclick="doTmdbPreview()">搜索</button>' +
            '</div>' +
            '<div class="tmdb-preview-panels">' +
                '<div class="tmdb-preview-left">' +
                    '<div id="tmdb-search-results" class="tmdb-search-results"></div>' +
                '</div>' +
                '<div class="tmdb-preview-right">' +
                    '<div id="tmdb-detail-container" class="tmdb-detail-container"></div>' +
                '</div>' +
            '</div>' +
        '</div>';
    document.body.appendChild(modal);
    document.getElementById('tmdb-preview-query').focus();
}
var showTmdbPreviewModal = function() { showProviderPreviewModal('tmdb'); };

function closeTmdbPreviewModal() {
    var modal = document.getElementById('tmdb-preview-modal');
    if (modal) modal.remove();
}

var _tmdbSelectedResultId = null;
var _tmdbSelectedResultType = null;

async function doTmdbPreview() {
    var query = document.getElementById('tmdb-preview-query').value.trim();
    var type = document.getElementById('tmdb-preview-type').value;
    var langEl = document.getElementById('tmdb-preview-lang');
    var language = langEl ? langEl.value : 'zh-CN';
    var resultsEl = document.getElementById('tmdb-search-results');
    var detailEl = document.getElementById('tmdb-detail-container');
    var btn = document.getElementById('btn-tmdb-preview-search');

    if (!query) {
        resultsEl.innerHTML = '<div class="tmdb-preview-error">请输入影视名称</div>';
        return;
    }

    btn.disabled = true;
    resultsEl.innerHTML = '<div class="tmdb-preview-loading">搜索中...</div>';
    detailEl.innerHTML = '<div class="tmdb-preview-placeholder">点击左侧搜索结果查看详情</div>';
    _tmdbSelectedResultId = null;
    _tmdbSelectedResultType = null;

    var result = await apiRequest('POST', '/providers/' + _currentPreviewProviderType + '/search', { query: query, type: type, language: language });

    btn.disabled = false;

    if (result.code !== 200 || !result.data) {
        resultsEl.innerHTML = '<div class="tmdb-preview-error">' + _escapeHtml(result.message || '请求失败') + '</div>';
        return;
    }

    var items = result.data.items || result.data.results || result.data || [];
    if (!items || items.length === 0) {
        resultsEl.innerHTML = '<div class="tmdb-preview-error">未找到结果</div>';
        return;
    }

    var maxItems = items.length > 10 ? 10 : items.length;
    var html = '';
    for (var i = 0; i < maxItems; i++) {
        var item = items[i];
        var titleField = type === 'tv' ? (item.name || item.original_name) : (item.title || item.original_title);
        var origTitle = type === 'tv' ? item.original_name : item.original_title;
        var dateField = type === 'tv' ? item.first_air_date : item.release_date;
        var year = dateField ? dateField.substring(0, 4) : '';
        var posterUrl = item.poster_path ? ('https://image.tmdb.org/t/p/w92' + item.poster_path) : '';
        var rating = item.vote_average != null ? item.vote_average.toFixed(1) : '--';
        var overview = item.overview || '';
        if (overview.length > 80) overview = overview.substring(0, 80) + '...';

        html += '<div class="tmdb-result-card" data-tmdb-id="' + _escapeHtml(String(item.id)) + '" data-tmdb-type="' + _escapeHtml(type) + '" onclick="_selectTmdbResult(this)">';
        if (posterUrl) {
            html += '<img class="tmdb-result-poster" src="' + _escapeHtml(posterUrl) + '" alt="" loading="lazy">';
        } else {
            html += '<div class="tmdb-result-poster tmdb-result-poster-placeholder">无海报</div>';
        }
        html += '<div class="tmdb-result-info">';
        html += '<div class="tmdb-result-title">' + _escapeHtml(titleField || '未知') + '</div>';
        if (origTitle && origTitle !== titleField) {
            html += '<div class="tmdb-result-original-title">' + _escapeHtml(origTitle) + '</div>';
        }
        html += '<div class="tmdb-result-meta">';
        if (year) html += '<span>' + _escapeHtml(year) + '</span>';
        html += '<span class="tmdb-result-rating">★ ' + _escapeHtml(rating) + '</span>';
        html += '</div>';
        if (overview) {
            html += '<div class="tmdb-result-overview">' + _escapeHtml(overview) + '</div>';
        }
        html += '</div></div>';
    }

    resultsEl.innerHTML = html;
}

async function _selectTmdbResult(cardEl) {
    var id = cardEl.getAttribute('data-tmdb-id');
    var type = cardEl.getAttribute('data-tmdb-type');
    var resultsEl = document.getElementById('tmdb-search-results');
    var detailEl = document.getElementById('tmdb-detail-container');

    var cards = resultsEl.querySelectorAll('.tmdb-result-card');
    for (var i = 0; i < cards.length; i++) {
        cards[i].classList.remove('selected');
    }
    cardEl.classList.add('selected');

    _tmdbSelectedResultId = id;
    _tmdbSelectedResultType = type;

    detailEl.innerHTML = '<div class="tmdb-preview-loading">加载详情中...</div>';

    var result = await apiRequest('POST', '/providers/' + _currentPreviewProviderType + '/details', { id: id, type: type });

    if (result.code !== 200 || !result.data) {
        detailEl.innerHTML = '<div class="tmdb-preview-error">' + _escapeHtml(result.message || '加载详情失败') + '</div>';
        return;
    }

    var data = result.data.details || result.data;
    detailEl.innerHTML = _renderTmdbDetailsStructured(data, type);
}

function _renderTmdbDetailsStructured(data, type) {
    var html = '<div class="tmdb-detail-view">';
    html += '<div style="display:flex;justify-content:flex-end;margin-bottom:8px;">';
    html += '<button class="btn btn-secondary btn-sm" id="tmdb-detail-toggle-btn" onclick="_toggleTmdbDetailView()">查看原始 JSON</button>';
    html += '</div>';

    html += '<div id="tmdb-detail-structured">';
    for (var gi = 0; gi < TMDB_FIELD_GROUPS.length; gi++) {
        var group = TMDB_FIELD_GROUPS[gi];
        var hasField = false;
        for (var fi = 0; fi < group.fields.length; fi++) {
            if (data[group.fields[fi]] !== undefined && data[group.fields[fi]] !== null) {
                hasField = true;
                break;
            }
        }
        if (!hasField) continue;

        html += '<div class="tmdb-detail-group">';
        html += '<div class="tmdb-detail-group-header" onclick="this.parentElement.classList.toggle(\'collapsed\')">';
        html += '<span>' + _escapeHtml(group.label) + '</span>';
        html += '<span class="tmdb-detail-group-arrow">▼</span>';
        html += '</div>';
        html += '<div class="tmdb-detail-group-body">';

        for (var fj = 0; fj < group.fields.length; fj++) {
            var key = group.fields[fj];
            var val = data[key];
            if (val === undefined || val === null) continue;

            var label = getTmdbFieldLabel(key);
            html += '<div class="tmdb-detail-row">';
            html += '<span class="tmdb-detail-key">' + _escapeHtml(label) + '</span>';
            html += '<span class="tmdb-detail-val">' + _renderTmdbFieldValue(key, val) + '</span>';
            html += '</div>';
        }

        html += '</div></div>';
    }
    html += '</div>';

    html += '<div id="tmdb-detail-raw" style="display:none;">';
    html += '<pre class="tmdb-detail-raw-pre">' + _escapeHtml(JSON.stringify(data, null, 2)) + '</pre>';
    html += '</div>';

    html += '</div>';
    return html;
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _renderTmdbFieldValue(key, val) {
    if (key === 'poster_path' || key === 'backdrop_path') {
        if (typeof val === 'string' && val) {
            return '<img src="https://image.tmdb.org/t/p/w300' + _escapeHtml(val) + '" alt="" style="max-width:200px;border-radius:6px;" loading="lazy">';
        }
        return _escapeHtml(String(val));
    }

    if (key === 'status' && typeof val === 'string') {
        var statusLabel = TMDB_STATUS_DICT[val];
        if (statusLabel) return _escapeHtml(statusLabel);
        return _escapeHtml(val);
    }

    if (typeof val === 'boolean') {
        return val ? '是' : '否';
    }

    if (typeof val === 'string' || typeof val === 'number') {
        return _escapeHtml(String(val));
    }

    if (Array.isArray(val)) {
        if (val.length === 0) return '<span style="color:var(--text-secondary);">-</span>';

        var firstItem = val[0];
        if (typeof firstItem === 'string' || typeof firstItem === 'number') {
            var parts = [];
            for (var i = 0; i < val.length; i++) {
                parts.push(_escapeHtml(String(val[i])));
            }
            return parts.join('、');
        }

        if (typeof firstItem === 'object' && firstItem !== null) {
            var tags = '';
            for (var j = 0; j < val.length; j++) {
                var nameVal = val[j].name || val[j].title || val[j].iso_3166_1 || val[j].iso_639_1 || val[j].english_name || '';
                if (nameVal) {
                    tags += '<span class="tmdb-preview-tag">' + _escapeHtml(String(nameVal)) + '</span>';
                }
            }
            return tags || '<span style="color:var(--text-secondary);">-</span>';
        }

        return _escapeHtml(JSON.stringify(val));
    }

    if (typeof val === 'object' && val !== null) {
        var subHtml = '';
        var subKeys = Object.keys(val);
        for (var k = 0; k < subKeys.length; k++) {
            var subKey = subKeys[k];
            var subVal = val[subKey];
            if (subVal === undefined || subVal === null) continue;
            var subLabel = getTmdbFieldLabel(subKey);
            subHtml += '<div class="tmdb-detail-row tmdb-detail-sub-row">';
            subHtml += '<span class="tmdb-detail-key">' + _escapeHtml(subLabel) + '</span>';
            subHtml += '<span class="tmdb-detail-val">' + _renderTmdbFieldValue(subKey, subVal) + '</span>';
            subHtml += '</div>';
        }
        return subHtml || '<span style="color:var(--text-secondary);">-</span>';
    }

    return _escapeHtml(String(val));
}

function _toggleTmdbDetailView() {
    var structured = document.getElementById('tmdb-detail-structured');
    var raw = document.getElementById('tmdb-detail-raw');
    var btn = document.getElementById('tmdb-detail-toggle-btn');
    if (!structured || !raw || !btn) return;

    if (raw.style.display === 'none') {
        raw.style.display = 'block';
        structured.style.display = 'none';
        btn.textContent = '查看结构化';
    } else {
        raw.style.display = 'none';
        structured.style.display = 'block';
        btn.textContent = '查看原始 JSON';
    }
}

function _escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function bindPathPermissionAutoTest() {
    var bindings = [
        { id: 'cfg-source_dir', needWrite: false },
        { id: 'cfg-temp_dir',   needWrite: true  },
        { id: 'cfg-log_dir',    needWrite: true  },
        { id: 'cfg-source_policy-recycle_dir', needWrite: true }
    ];
    bindings.forEach(function(b) {
        var el = document.getElementById(b.id);
        if (!el) return;
        el.addEventListener('blur', function() {
            var v = (el.value || '').trim();
            if (v) testPathPermission(b.id, b.needWrite);
        });
    });
}

function toggleInfoPanel(panelId) {
    var panel = document.getElementById(panelId);
    var arrow = document.getElementById(panelId + '-arrow');
    if (!panel) return;
    var isHidden = panel.classList.contains('collapsed-section');
    if (isHidden) {
        panel.classList.remove('collapsed-section');
    } else {
        panel.classList.add('collapsed-section');
    }
    if (arrow) {
        arrow.textContent = isHidden ? '▼' : '▶';
    }
}

var _CONFIDENCE_DEFAULTS = {
    provider_match_threshold: 0.7,
    title_exact_with_year: 1.0,
    title_exact_with_season: 0.9,
    title_exact_no_year: 0.7,
    title_exact_year_mismatch: 0.4,
    title_fuzzy_year_coeff: 0.7,
    title_min_similarity: 0.3,
    R_formula: 'log',
    R_max_results_cap: 10,
    R_min_value: 0.1,
    R_T_floor: 0.5,
    R_T_curve: 1.5,
    source_priority: ['provider', 'ai', 'file'],
    ai_cap_high_similarity: 0.7,
    ai_cap_low_similarity: 0.3,
    ai_cap_no_title: 0.3,
    ai_cap_no_match: 0.2,
    ai_cap_low_coeff: 0.5,
    pass_threshold: 0.8,
    confirm_threshold: 0.5,
    review_threshold: 0.3,
    dimensions: {}
};

function _initSourcePriorityDrag(container) {
    var dragSrc = null;
    var items = container.querySelectorAll('.source-priority-item');
    items.forEach(function(item) {
        item.addEventListener('dragstart', function(e) {
            dragSrc = item;
            item.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', '');
        });
        item.addEventListener('dragend', function() {
            item.classList.remove('dragging');
            dragSrc = null;
        });
        item.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (dragSrc && dragSrc !== item) {
                var rect = item.getBoundingClientRect();
                var midY = rect.top + rect.height / 2;
                if (e.clientY < midY) {
                    container.insertBefore(dragSrc, item);
                } else {
                    container.insertBefore(dragSrc, item.nextSibling);
                }
            }
        });
    });
}

function _initDimSourceDrag(rootContainer) {
    var lists = rootContainer.querySelectorAll('.dim-source-list');
    lists.forEach(function(tbody) {
        var dragSrc = null;
        var rows = tbody.querySelectorAll('.dim-source-row');
        rows.forEach(function(row) {
            row.addEventListener('dragstart', function(e) {
                dragSrc = row;
                row.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', '');
            });
            row.addEventListener('dragend', function() {
                row.classList.remove('dragging');
                dragSrc = null;
            });
            row.addEventListener('dragover', function(e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                if (dragSrc && dragSrc !== row) {
                    var rect = row.getBoundingClientRect();
                    var midY = rect.top + rect.height / 2;
                    if (e.clientY < midY) {
                        tbody.insertBefore(dragSrc, row);
                    } else {
                        tbody.insertBefore(dragSrc, row.nextSibling);
                    }
                }
            });
        });
    });
}

function loadConfidenceConfig(config) {
    var conf = config.confidence || {};

    var section = document.querySelector('[data-section="confidence"]');
    if (!section) return;

    var inputs = section.querySelectorAll('input[data-key]');
    inputs.forEach(function(inp) {
        var key = inp.getAttribute('data-key');
        var val = conf[key];
        if (val !== undefined && val !== null) {
            inp.value = val;
        }
    });

    var rFormula = conf.R_formula || 'log';
    var rCards = section.querySelectorAll('.r-formula-card');
    rCards.forEach(function(card) {
        var f = card.getAttribute('onclick').match(/'(\w+)'/);
        if (f && f[1] === rFormula) {
            card.classList.add('selected');
        } else {
            card.classList.remove('selected');
        }
    });

    renderDimensionSourceTrustCards(conf);
    updateThresholdBar();
}

function saveConfidenceConfig() {
    var section = document.querySelector('[data-section="confidence"]');
    if (!section) return {};

    var conf = {};
    var inputs = section.querySelectorAll('input[data-key]');
    inputs.forEach(function(inp) {
        var key = inp.getAttribute('data-key');
        var val = inp.value.trim();
        if (val === '') return;
        var num = parseFloat(val);
        conf[key] = isNaN(num) ? val : num;
    });

    var selectedR = section.querySelector('.r-formula-card.selected');
    if (selectedR) {
        var match = selectedR.getAttribute('onclick').match(/'(\w+)'/);
        if (match) conf.R_formula = match[1];
    }

    var dimCards = document.querySelectorAll('#dim-source-trust-container .dim-card');
    var dims = {};
    dimCards.forEach(function(card) {
        var dimName = card.getAttribute('data-dim');
        if (!dimName) return;
        var rows = card.querySelectorAll('.dim-source-row');
        var sourcesList = [];
        rows.forEach(function(row) {
            var src = row.getAttribute('data-source');
            var toggle = row.querySelector('input[data-dim-field="trusted_source"]');
            var trusted = toggle ? toggle.checked : true;
            if (src) {
                sourcesList.push({ source: src, trusted: trusted });
            }
        });
        if (sourcesList.length > 0) {
            dims[dimName] = { sources: sourcesList };
        }
    });
    if (Object.keys(dims).length > 0) {
        conf.dimensions = dims;
    }

    return conf;
}

function _buildConfidenceData() {
    return {
        confidence: saveConfidenceConfig()
    };
}

function toggleCfgSection(header) {
    var section = header.closest('.cfg-section');
    if (!section) return;
    header.classList.toggle('open');
    var body = section.querySelector('.cfg-section-body');
    if (body) body.classList.toggle('open');
}

function selectRFormula(card, formula) {
    var section = document.querySelector('[data-section="confidence"]');
    if (!section) return;
    section.querySelectorAll('.r-formula-card').forEach(function(c) { c.classList.remove('selected'); });
    card.classList.add('selected');
}

function updateThresholdBar() {
    var section = document.querySelector('[data-section="confidence"]');
    if (!section) return;

    var passInput = section.querySelector('input[data-key="pass_threshold"]');
    var confirmInput = section.querySelector('input[data-key="confirm_threshold"]');
    var reviewInput = section.querySelector('input[data-key="review_threshold"]');

    var pass = parseFloat(passInput ? passInput.value : 0.8) || 0.8;
    var confirm = parseFloat(confirmInput ? confirmInput.value : 0.5) || 0.5;
    var review = parseFloat(reviewInput ? reviewInput.value : 0.3) || 0.3;

    pass = Math.min(1, Math.max(0, pass));
    confirm = Math.min(pass, Math.max(0, confirm));
    review = Math.min(confirm, Math.max(0, review));

    var failW = (review * 100).toFixed(1);
    var reviewW = ((confirm - review) * 100).toFixed(1);
    var confirmW = ((pass - confirm) * 100).toFixed(1);
    var passW = ((1 - pass) * 100).toFixed(1);

    var bar = document.getElementById('confidence-threshold-bar');
    if (bar) {
        bar.innerHTML =
            '<div class="threshold-segment seg-fail" style="width:' + failW + '%">FAILED</div>' +
            '<div class="threshold-segment seg-review" style="width:' + reviewW + '%">REVIEW</div>' +
            '<div class="threshold-segment seg-confirm" style="width:' + confirmW + '%">CONFIRM</div>' +
            '<div class="threshold-segment seg-pass" style="width:' + passW + '%">PASS</div>';
    }

    var labels = document.getElementById('confidence-threshold-labels');
    if (labels) {
        labels.innerHTML =
            '<span style="width:' + failW + '%">0</span>' +
            '<span style="width:' + reviewW + '%">' + review.toFixed(2) + '</span>' +
            '<span style="width:' + confirmW + '%">' + confirm.toFixed(2) + '</span>' +
            '<span style="width:' + passW + '%">' + pass.toFixed(2) + '</span>' +
            '<span>1.0</span>';
    }

    var passVal = document.getElementById('formula-pass-val');
    var confirmVal = document.getElementById('formula-confirm-val');
    var reviewVal = document.getElementById('formula-review-val');
    var reviewVal2 = document.getElementById('formula-review-val2');
    if (passVal) passVal.textContent = pass.toFixed(2);
    if (confirmVal) confirmVal.textContent = confirm.toFixed(2);
    if (reviewVal) reviewVal.textContent = review.toFixed(2);
    if (reviewVal2) reviewVal2.textContent = review.toFixed(2);

    var thresholdInput = section.querySelector('input[data-key="tmdb_match_threshold"]');
    var thresholdVal = thresholdInput ? (parseFloat(thresholdInput.value) || 0.85) : 0.85;
    var formulaThresholdVal = document.getElementById('formula-threshold-val');
    var formulaThresholdVal2 = document.getElementById('formula-threshold-val2');
    if (formulaThresholdVal) formulaThresholdVal.textContent = thresholdVal.toFixed(2);
    if (formulaThresholdVal2) formulaThresholdVal2.textContent = thresholdVal.toFixed(2);
}

async function renderDimensionSourceTrustCards(conf) {
    var container = document.getElementById('dim-source-trust-container');
    if (!container) return;

    var dimConfigs = conf.dimensions || {};
    var allSources;
    try {
        var provResult = await apiRequest('GET', '/providers');
        if (provResult.code === 200 && provResult.data && provResult.data.providers) {
            var enabledProviders = provResult.data.providers.filter(function(p) { return p.enabled; });
            allSources = enabledProviders.map(function(p) {
                return { key: p.type, label: p.display_name, tag: p.type, desc: p.display_name + ' 结构化字段映射' };
            });
        }
    } catch(e) {}
    if (!allSources) allSources = [];
    allSources.push({ key: 'ai', label: 'AI', tag: 'ai', desc: 'AI 判断' });
    allSources.push({ key: 'file', label: 'FILE', tag: 'file', desc: '文件名分析推导' });

    try {
        var result = await apiRequest('GET', '/dimensions');
        if (!result || result.code !== 200 || !result.data || !result.data.dimensions) {
            container.innerHTML = '<div style="padding:12px;color:var(--text-secondary);font-size:13px;">无法加载维度列表</div>';
            return;
        }

        var dimensions = result.data.dimensions;
        if (dimensions.length === 0) {
            container.innerHTML = '<div style="padding:12px;color:var(--text-secondary);font-size:13px;">暂无维度配置，请先在「影视分类配置」中添加维度</div>';
            return;
        }

        var html = '';
        dimensions.forEach(function(dim) {
            var name = dim.name || '';
            var label = dim.label || name;
            var enabled = dim.enabled !== false;
            var dimConf = dimConfigs[name] || {};
            var sourcesList = dimConf.sources || allSources.map(function(s) { return { source: s.key, trusted: true }; });

            var trustedLabels = [];
            sourcesList.forEach(function(s) {
                if (s.trusted) {
                    for (var i = 0; i < allSources.length; i++) {
                        if (allSources[i].key === s.source) { trustedLabels.push(allSources[i].label); break; }
                    }
                }
            });
            var summary = trustedLabels.length > 0 ? trustedLabels.join(', ') : '无可信来源';

            var disabledClass = enabled ? '' : ' dim-disabled';
            var disabledBadge = enabled ? '' : ' <span class="badge badge-disabled">已禁用</span>';

            html += '<div class="dim-card' + disabledClass + '" data-dim="' + _escapeHtml(name) + '">';
            html += '<div class="dim-card-header" onclick="toggleConfDimCard(this)">';
            html += '<span class="dim-card-name">' + _escapeHtml(label) + '<span class="dim-card-key">(' + _escapeHtml(name) + ')</span></span>';
            html += disabledBadge;
            html += '<span class="dim-card-summary">' + _escapeHtml(summary) + '</span>';
            html += '<span class="dim-card-arrow">▼</span>';
            html += '</div>';

            html += '<div class="conf-dim-card-body">';
            if (!enabled) {
                html += '<div style="padding:6px 0;font-size:12px;color:var(--text-secondary);margin-bottom:8px;">此维度已禁用，来源信任配置仍可编辑，但计算时自动跳过。启用维度后配置立即生效。</div>';
            }

            html += '<div style="font-size:12px;font-weight:600;margin:8px 0 4px;color:var(--text-secondary);">来源配置 <span class="help-trigger" data-tooltip="拖拽调整优先级（越靠前优先级越高），勾选可信表示信任该来源。系统按优先级取第一个可信且有数据的来源。" onclick="event.stopPropagation()">?</span></div>';
            html += '<table class="source-conf-table">';
            html += '<thead><tr><th style="width:24px;"></th><th>来源</th><th>说明</th><th>可信</th></tr></thead>';
            html += '<tbody class="dim-source-list" data-dim="' + _escapeHtml(name) + '">';

            sourcesList.forEach(function(srcEntry, idx) {
                var srcKey = srcEntry.source || '';
                var srcTrusted = srcEntry.trusted !== false;
                var srcInfo = null;
                for (var i = 0; i < allSources.length; i++) {
                    if (allSources[i].key === srcKey) { srcInfo = allSources[i]; break; }
                }
                if (!srcInfo) {
                    srcInfo = { key: srcKey, label: srcKey, tag: 'other', desc: '' };
                }
                var checked = srcTrusted ? ' checked' : '';
                var toggleId = 'trust-' + name + '-' + srcKey;
                html += '<tr class="dim-source-row" draggable="true" data-source="' + _escapeHtml(srcKey) + '">';
                html += '<td class="dim-source-drag" title="拖拽排序">⠿</td>';
                html += '<td><span class="source-tag ' + srcInfo.tag + '">' + _escapeHtml(srcInfo.label) + '</span></td>';
                html += '<td style="font-size:12px;color:var(--text-secondary);">' + _escapeHtml(srcInfo.desc) + '</td>';
                html += '<td><div class="toggle-switch"><input type="checkbox" id="' + toggleId + '"' + checked + ' data-dim-field="trusted_source" data-source="' + _escapeHtml(srcKey) + '"><label for="' + toggleId + '"></label></div></td>';
                html += '</tr>';
            });

            html += '</tbody></table>';
            html += '</div></div>';
        });

        container.innerHTML = html;
        _initDimSourceDrag(container);
    } catch (e) {
        container.innerHTML = '<div style="padding:12px;color:var(--text-secondary);font-size:13px;">加载维度失败: ' + e.message + '</div>';
    }
}

function toggleConfDimCard(header) {
    var card = header.closest('.dim-card');
    if (!card) return;
    header.classList.toggle('open');
    var body = card.querySelector('.conf-dim-card-body');
    if (body) body.classList.toggle('open');
}

function generateConsultPrompt() {
    var conf = saveConfidenceConfig();
    var userNeed = (document.getElementById('ai-consult-need').value || '').trim() || '（未填写具体需求，请根据默认场景给出建议）';

    var rFormula = conf.R_formula || 'log';
    var rFormulaDesc = { 'inverse': 'R = 1/N', 'log': 'R = 1/log2(N+1)', 'sqrt': 'R = 1/sqrt(N)', 'flat': 'R = 1.0（不惩罚）' };

    var dimLines = '';
    var dimCards = document.querySelectorAll('#dim-source-trust-container .dim-card');
    dimCards.forEach(function(card) {
        var dk = card.getAttribute('data-dim');
        if (!dk) return;
        var dimLabel = card.querySelector('.dim-card-name');
        var label = dimLabel ? dimLabel.textContent.replace(/\(.*\)/, '').trim() : dk;
        var rows = card.querySelectorAll('.dim-source-row');
        var srcParts = [];
        rows.forEach(function(row) {
            var src = row.getAttribute('data-source') || '';
            var toggle = row.querySelector('input[data-dim-field="trusted_source"]');
            var trusted = toggle ? toggle.checked : true;
            srcParts.push(src + (trusted ? '(✓可信)' : '(✗不可信)'));
        });
        dimLines += '  ' + dk + '(' + label + '): ' + srcParts.join(' > ') + '\n';
    });

    var prompt = '# 影音库AI智能整理 — 置信度配置咨询助手\n'
        + '\n你是"影音库AI智能整理"系统的配置顾问。你的任务是根据用户需求，给出精确的配置建议，让用户直接在 Web 界面上修改对应参数。\n'
        + '\n## 一、系统工作流程\n'
        + '\n影音库AI智能整理系统自动刮削视频文件元数据并分类入库。处理流程：\n'
        + '\n1. **文件名清洗**：用正则表达式从文件名中提取标题、年份、季集号。支持中英文标题自动拆分（如"蝙蝠侠：黑暗骑士.The.Dark.Knight.2008"会拆分为英文标题"The Dark Knight"）。如果年份可疑（如年份在未来、或清洗后标题残留年份），标记为 year_suspect，跳过直接搜索。\n'
        + '2. **Provider 搜索**：用清洗后的标题+年份搜索 Provider 数据库，获取匹配结果。如果第一次搜索无结果或匹配分低于阈值，会触发 AI 辅助清洗后重新搜索。\n'
        + '3. **AI 刮削**：调用 LLM 提取元数据（标题、年份、分辨率、维度信息等）。\n'
        + '4. **置信度计算**：根据 Provider 匹配质量和 AI 数据可信度计算最终置信度。\n'
        + '5. **决策判定**：根据置信度自动决定任务状态。\n'
        + '\n系统有两条独立的计算路径：\n'
        + '- **Provider+AI 路径**（Provider 启用时）：使用 Provider 搜索结果计算\n'
        + '- **纯 AI 路径**（Provider 未启用或无结果时）：仅依赖 AI 判断\n'
        + '\n## 二、置信度计算公式详解\n'
        + '\n### 路径 A：Provider+AI（推荐路径）\n'
        + '\n```\n'
        + '最终置信度 = search_conf × data_gate\n'
        + '\n'
        + 'search_conf = T × R\n'
        + '  T = 标题匹配分（L1~L7 七个等级，见下文）\n'
        + '  R = 搜索结果数惩罚因子（结果越多越不确定）\n'
        + '\n'
        + 'data_gate = 1.0（所有维度来源可信）或 0.0（有维度来源不可信 → 强制需审核）\n'
        + '```\n'
        + '\n#### T 值：标题匹配等级\n'
        + '\n系统将文件名清洗后的标题与 Provider 返回的标题做比较，分精确匹配和模糊匹配两种情况：\n'
        + '\n**精确匹配（标准化后完全相同）时：**\n'
        + '| 等级 | 条件 | T值参数名 | 当前值 | 说明 |\n'
        + '|------|------|-----------|--------|------|\n'
        + '| L1 | 标题精确 + 年份精确一致 | title_exact_with_year | ' + (conf.title_exact_with_year || 1.0) + ' | 最高置信，标题和年份都对上了 |\n'
        + '| L2 | 标题精确 + 有季号（无年份） | title_exact_with_season | ' + (conf.title_exact_with_season || 0.9) + ' | 剧集常见，用季号辅助确认 |\n'
        + '| L3 | 标题精确 + 无年份也无季号 | title_exact_no_year | ' + (conf.title_exact_no_year || 0.7) + ' | 标题对了但缺少时间锚定 |\n'
        + '| L4 | 标题精确 + 年份不匹配 | title_exact_year_mismatch | ' + (conf.title_exact_year_mismatch || 0.4) + ' | 可能是同名不同年作品 |\n'
        + '\n'
        + '**模糊匹配（相似度 ≥ title_min_similarity）时：**\n'
        + '| 等级 | 条件 | T值计算 | 说明 |\n'
        + '|------|------|---------|------|\n'
        + '| L5 | 模糊匹配 + 年份精确 | T = 相似度值 | 年份一致起到锚定作用，不加惩罚 |\n'
        + '| L6 | 模糊匹配 + 年份不匹配或无年份 | T = 相似度 × title_fuzzy_year_coeff | 缺少年份确认，打折扣 |\n'
        + '| L7 | 相似度 < title_min_similarity | T = 0.0 | 完全不匹配 |\n'
        + '\n'
        + '当前 title_fuzzy_year_coeff = ' + (conf.title_fuzzy_year_coeff || 0.7) + '，title_min_similarity = ' + (conf.title_min_similarity || 0.3) + '\n'
        + '\n'
        + '#### R 值：搜索结果数惩罚\n'
        + '\nProvider 搜索返回的结果越多，说明标题越不唯一，需要降低置信度。R 的计算分两步：\n'
        + '\n'
        + '**第一步：基础 R 值**（根据搜索结果总数 N 计算，N 上限为 R_max_results_cap）\n'
        + '- inverse: R = 1/N（线性衰减，只有1个结果时R=1.0）\n'
        + '- log: R = 1/log2(N+1)（对数衰减，推荐默认，温和惩罚）\n'
        + '- sqrt: R = 1/sqrt(N)（平方根衰减，中等惩罚）\n'
        + '- flat: R = 1.0（不惩罚，忽略结果数）\n'
        + '\n'
        + '当前公式: ' + rFormula + '（' + (rFormulaDesc[rFormula] || rFormula) + '），R_max_results_cap = ' + (conf.R_max_results_cap || 10) + '，R_min_value = ' + (conf.R_min_value || 0.1) + '\n'
        + '\n'
        + '**第二步：T 值自信任增强**（当 T > R_T_floor 时，R 向 1.0 方向调整）\n'
        + '```\n'
        + 'alpha = ((T - R_T_floor) / (1.0 - R_T_floor)) ^ R_T_curve\n'
        + 'R_adjusted = R_base × (1 - alpha) + alpha\n'
        + '```\n'
        + '含义：标题匹配度越高，搜索结果数量的惩罚越小。因为高 T 值说明结果已经很明确了。\n'
        + '当前 R_T_floor = ' + (conf.R_T_floor || 0.5) + '，R_T_curve = ' + (conf.R_T_curve || 1.5) + '\n'
        + '\n'
        + '#### data_gate：数据来源可信门控\n'
        + '\n每个维度（如影视类型、年龄分级等）的数据来源有多个 Provider、ai、file。系统按配置的优先级顺序选取第一个有数据的来源。如果选中的来源不在该维度的信任列表中，且没有其他可信来源可用，则 data_gate = 0，强制进入审核。\n'
        + '\n'
        + '**关键规则**：如果某个维度有数据来自不可信来源，但同时该维度也有来自可信来源的数据（即使优先级更低），系统会使用可信来源的数据，不会触发门控阻断。只有所有可用来源都不可信时才阻断。\n'
        + '\n'
        + '### 路径 B：纯 AI 模式\n'
        + '\n```\n'
        + '最终置信度 = objective_cap × data_gate\n'
        + '\n'
        + 'objective_cap 根据 AI 返回标题与清洗标题的相似度(sim)计算：\n'
        + '  sim >= ai_cap_high_similarity → cap = sim（AI标题高度一致，用相似度本身）\n'
        + '  sim >= ai_cap_low_similarity  → cap = sim × ai_cap_low_coeff（低相似度，衰减处理）\n'
        + '  sim < ai_cap_low_similarity   → cap = ai_cap_no_match（完全不匹配，兜底值）\n'
        + '  AI 无标题                      → cap = ai_cap_no_title（AI没返回标题，兜底值）\n'
        + '```\n'
        + '\n'
        + '当前 ai_cap_high_similarity = ' + (conf.ai_cap_high_similarity || 0.7) + '，ai_cap_low_similarity = ' + (conf.ai_cap_low_similarity || 0.3) + '，ai_cap_no_title = ' + (conf.ai_cap_no_title || 0.3) + '，ai_cap_no_match = ' + (conf.ai_cap_no_match || 0.2) + '，ai_cap_low_coeff = ' + (conf.ai_cap_low_coeff || 0.5) + '\n'
        + '\n'
        + '### 决策阈值\n'
        + '\n根据最终置信度判定任务状态：\n'
        + '| 置信度范围 | 状态 | 说明 |\n'
        + '|-----------|------|------|\n'
        + '| >= pass_threshold(' + (conf.pass_threshold || 0.8) + ') | PASS 自动通过 | 无需人工干预 |\n'
        + '| >= confirm_threshold(' + (conf.confirm_threshold || 0.5) + ') | CONFIRMING 需确认 | 建议人工确认 |\n'
        + '| >= review_threshold(' + (conf.review_threshold || 0.3) + ') | NEEDS_REVIEW 需审核 | 必须人工审核 |\n'
        + '| < review_threshold | FAILED 失败 | 自动拒绝 |\n'
        + '\n'
        + '**特殊规则**：data_gate = 0 时，无论置信度多高，状态强制为 NEEDS_REVIEW。\n'
        + '\n'
        + '### Provider 最低匹配阈值\n'
        + '\nprovider_match_threshold = ' + (conf.provider_match_threshold || 0.7) + '。当第一次 Provider 搜索的最佳匹配 T 值低于此阈值时，触发 AI 辅助清洗后重新搜索。\n'
        + '\n## 三、当前完整配置\n'
        + '\n```\n'
        + '决策阈值:\n'
        + '  自动通过(pass_threshold) = ' + (conf.pass_threshold || 0.8) + '\n'
        + '  需确认(confirm_threshold) = ' + (conf.confirm_threshold || 0.5) + '\n'
        + '  需审核(review_threshold) = ' + (conf.review_threshold || 0.3) + '\n'
        + '\n'
        + '标题匹配等级(T值):\n'
        + '  L1精确+年份精确(title_exact_with_year) = ' + (conf.title_exact_with_year || 1.0) + '\n'
        + '  L2精确+有季号(title_exact_with_season) = ' + (conf.title_exact_with_season || 0.9) + '\n'
        + '  L3精确无年份(title_exact_no_year) = ' + (conf.title_exact_no_year || 0.7) + '\n'
        + '  L4精确年份不匹配(title_exact_year_mismatch) = ' + (conf.title_exact_year_mismatch || 0.4) + '\n'
        + '  模糊年份系数(title_fuzzy_year_coeff) = ' + (conf.title_fuzzy_year_coeff || 0.7) + '\n'
        + '  最低相似度(title_min_similarity) = ' + (conf.title_min_similarity || 0.3) + '\n'
        + '  Provider最低匹配阈值(provider_match_threshold) = ' + (conf.provider_match_threshold || 0.7) + '\n'
        + '\n'
        + 'R值(搜索结果惩罚):\n'
        + '  公式(R_formula) = ' + rFormula + '（' + (rFormulaDesc[rFormula] || rFormula) + '）\n'
        + '  结果数上限(R_max_results_cap) = ' + (conf.R_max_results_cap || 10) + '\n'
        + '  下限(R_min_value) = ' + (conf.R_min_value || 0.1) + '\n'
        + '  自信任门槛(R_T_floor) = ' + (conf.R_T_floor || 0.5) + '\n'
        + '  自信任曲率(R_T_curve) = ' + (conf.R_T_curve || 1.5) + '\n'
        + '\n'
        + '纯AI模式参数:\n'
        + '  高相似度门槛(ai_cap_high_similarity) = ' + (conf.ai_cap_high_similarity || 0.7) + '\n'
        + '  低相似度门槛(ai_cap_low_similarity) = ' + (conf.ai_cap_low_similarity || 0.3) + '\n'
        + '  无标题上限(ai_cap_no_title) = ' + (conf.ai_cap_no_title || 0.3) + '\n'
        + '  无匹配上限(ai_cap_no_match) = ' + (conf.ai_cap_no_match || 0.2) + '\n'
        + '  低相似度衰减(ai_cap_low_coeff) = ' + (conf.ai_cap_low_coeff || 0.5) + '\n'
        + (dimLines ? '\n维度来源配置(每个维度的来源优先级和信任状态):\n' + dimLines : '')
        + '```\n'
        + '\n## 四、用户需求\n'
        + '\n' + userNeed + '\n'
        + '\n## 五、回答格式要求\n'
        + '\n请按以下三部分回答。用户会在 Web 界面上逐项修改，不是编辑配置文件。配置项名称要使用括号内的英文参数名，方便用户在界面上找到对应输入框。\n'
        + '\n### 第一部分：配置清单\n'
        + '\n只列出需要调整的参数。格式：`区域.参数名(英文名) = 建议值`。\n'
        + '\n格式示例：\n'
        + '```\n'
        + '决策阈值.自动通过(pass_threshold) = 0.85\n'
        + '标题匹配等级.精确无年份(title_exact_no_year) = 0.75\n'
        + '维度来源.年龄分级(restricted_level): 只信任provider\n'
        + '```\n'
        + '\n### 第二部分：调整原因\n'
        + '\n针对每个调整项，用 1-2 句话说明为什么要改、改了会有什么效果。\n'
        + '\n### 第三部分：示例计算\n'
        + '\n用 1-2 个文件名模拟完整计算过程，展示每一步的中间值和最终结果。让用户能直观理解"改了这个参数，置信度会怎么变"。示例应覆盖用户关心的场景。\n'
        + '\n---\n'
        + '\n要求：\n'
        + '1. **所有参数建议值必须在 0.0~1.0 范围内**。T值本质是置信度权重，最大为1.0；阈值也是0-1之间的概率值。没有参数可以超过1.0。R_max_results_cap 是唯一大于1的整数参数。\n'
        + '2. 阈值必须满足 pass > confirm > review\n'
        + '3. T 值等级应满足 L1 ≥ L2 ≥ L3 > L4\n'
        + '4. 如果用户需求不明确，给出两套方案并说明适用场景\n'
        + '5. 如果当前配置已经合理，明确告诉用户"当前配置适合您的场景，无需调整"\n'
        + '6. 严格模式不是靠提高T值超过1.0来实现，而是靠提高pass_threshold或降低L3/L4的T值来实现';

    document.getElementById('ai-consult-prompt').textContent = prompt;
    document.getElementById('ai-consult-output').style.display = 'block';
}

function copyConsultPrompt() {
    var promptEl = document.getElementById('ai-consult-prompt');
    if (!promptEl || !promptEl.textContent) {
        generateConsultPrompt();
    }
    var text = promptEl.textContent || '';
    navigator.clipboard.writeText(text).then(function() {
        showToast('已复制到剪贴板');
    }).catch(function() {
        showToast('复制失败', 'error');
    });
}

var _recycleListData = [];
var _pendingRestoreItems = [];

function _getZoneAttr(zoneName) {
    if (!zoneName) return 'other';
    if (zoneName.indexOf('清理器') >= 0) return 'cleaner';
    if (zoneName.indexOf('源目录') >= 0) return 'source';
    if (zoneName.indexOf('入库') >= 0) return 'import';
    return 'other';
}

async function loadRecycleList() {
    var partition = document.getElementById('recycle-filter-partition').value;
    var reason = document.getElementById('recycle-filter-reason').value;
    var params = [];
    if (partition) params.push('partition=' + encodeURIComponent(partition));
    if (reason) params.push('reason=' + encodeURIComponent(reason));
    var query = params.length > 0 ? '?' + params.join('&') : '';

    var result = await apiRequest('GET', '/recycle/list' + query);
    if (!result || result.code !== 200 || !result.data) {
        showToast('加载回收站列表失败: ' + (result ? result.message : '未知错误'), 'error');
        return;
    }

    var data = result.data;
    var items = data.items || [];
    _recycleListData = items;

    document.getElementById('recycle-total-count').textContent = data.total_count || data.total || items.length;
    document.getElementById('recycle-total-size').textContent = _formatFileSize(data.total_size || 0);

    var partitionStats = data.partition_stats || {};
    var statsHtml = '';
    var partitionKeys = Object.keys(partitionStats);
    for (var i = 0; i < partitionKeys.length; i++) {
        var pk = partitionKeys[i];
        var ps = partitionStats[pk];
        var count = (typeof ps === 'object') ? (ps.count || 0) : ps;
        var size = (typeof ps === 'object') ? (ps.size || 0) : 0;
        statsHtml += '<span class="recycle-stat-partition">' + _escapeHtml(pk) + ': ' + count + ' 文件' + (size > 0 ? ' / ' + _formatFileSize(size) : '') + '</span>';
    }
    document.getElementById('recycle-partition-stats').innerHTML = statsHtml;

    var partitionSelect = document.getElementById('recycle-filter-partition');
    var currentPartition = partitionSelect.value;
    var partitions = data.partitions || [];
    var optHtml = '<option value="">全部分区</option>';
    for (var i = 0; i < partitions.length; i++) {
        optHtml += '<option value="' + _escapeHtml(partitions[i]) + '"' + (partitions[i] === currentPartition ? ' selected' : '') + '>' + _escapeHtml(partitions[i]) + '</option>';
    }
    partitionSelect.innerHTML = optHtml;

    var reasonSelect = document.getElementById('recycle-filter-reason');
    var currentReason = reasonSelect.value;
    var reasons = data.reasons || [];
    var reasonHtml = '<option value="">全部原因</option>';
    for (var i = 0; i < reasons.length; i++) {
        reasonHtml += '<option value="' + _escapeHtml(reasons[i]) + '"' + (reasons[i] === currentReason ? ' selected' : '') + '>' + _escapeHtml(reasons[i]) + '</option>';
    }
    reasonSelect.innerHTML = reasonHtml;

    var tbody = document.getElementById('recycle-table-body');
    if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-row">暂无回收站数据</td></tr>';
        return;
    }

    var html = '';
    for (var i = 0; i < items.length; i++) {
        var item = items[i];
        var itemId = item.id || item.recycle_path || '';
        var zoneAttr = _getZoneAttr(item.partition || item.zone_name || '');
        var sizeBytes = item.size || (item.file_size_mb ? item.file_size_mb * 1024 * 1024 : 0);
        html += '<tr data-recycle-id="' + _escapeHtml(itemId) + '">';
        html += '<td><input type="checkbox" class="recycle-item-check" value="' + _escapeHtml(itemId) + '"></td>';
        html += '<td style="font-size:12px;word-break:break-all;">' + _escapeHtml(item.original_path || '') + '</td>';
        html += '<td><span class="recycle-zone-tag" data-zone="' + zoneAttr + '">' + _escapeHtml(item.partition || item.zone_name || '') + '</span></td>';
        html += '<td><span class="recycle-reason-tag" title="' + _escapeHtml(item.reason || '') + '">' + _escapeHtml(item.reason || '') + '</span></td>';
        html += '<td>' + _formatFileSize(sizeBytes) + '</td>';
        html += '<td style="font-size:12px;">' + _escapeHtml(item.moved_at || '') + '</td>';
        html += '<td><div class="recycle-action-btns">';
        html += '<button class="btn btn-primary btn-sm" onclick="restoreRecycleItem(\'' + _escapeJs(itemId) + '\')">';
        html += '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:12px;height:12px;"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>恢复</button>';
        html += '<button class="btn btn-danger btn-sm" onclick="deleteRecycleItem(\'' + _escapeJs(itemId) + '\')">';
        html += '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:12px;height:12px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>删除</button>';
        html += '</div></td>';
        html += '</tr>';
    }
    tbody.innerHTML = html;
}

function _escapeJs(s) {
    return String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function _formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB', 'TB'];
    var i = Math.floor(Math.log(bytes) / Math.log(1024));
    if (i >= units.length) i = units.length - 1;
    if (i < 0) i = 0;
    return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}

function toggleRecycleSelectAll() {
    var headerCheck = document.getElementById('recycle-header-check');
    var selectAllCheck = document.getElementById('recycle-select-all');
    var checked = headerCheck ? headerCheck.checked : (selectAllCheck ? selectAllCheck.checked : false);
    var checks = document.querySelectorAll('.recycle-item-check');
    checks.forEach(function(c) { c.checked = checked; });
    if (selectAllCheck) selectAllCheck.checked = checked;
    if (headerCheck) headerCheck.checked = checked;
}

function toggleRecycleInvert() {
    var checks = document.querySelectorAll('.recycle-item-check');
    checks.forEach(function(c) { c.checked = !c.checked; });
}

function _getSelectedRecycleIds() {
    var ids = [];
    var checks = document.querySelectorAll('.recycle-item-check:checked');
    checks.forEach(function(c) { ids.push(c.value); });
    return ids;
}

async function restoreRecycleItem(id) {
    _pendingRestoreItems = [id];
    _showRestoreConfirmModal([id]);
}

async function batchRestoreRecycleItems() {
    var ids = _getSelectedRecycleIds();
    if (ids.length === 0) {
        showToast('请先选择要恢复的文件', 'warning');
        return;
    }
    _pendingRestoreItems = ids;
    _showRestoreConfirmModal(ids);
}

function _showRestoreConfirmModal(ids) {
    var fileListHtml = '';
    for (var i = 0; i < ids.length; i++) {
        var item = null;
        for (var j = 0; j < _recycleListData.length; j++) {
            if (_recycleListData[j].id === ids[i] || _recycleListData[j].recycle_path === ids[i]) { item = _recycleListData[j]; break; }
        }
        if (item) {
            fileListHtml += '<div style="padding:4px 0;font-size:13px;border-bottom:1px solid var(--border-color);">' + _escapeHtml(item.original_path || item.id || item.recycle_path) + '</div>';
        }
    }
    document.getElementById('recycle-restore-file-list').innerHTML = fileListHtml;
    document.getElementById('recycle-restore-conflict-warning').style.display = 'none';
    document.getElementById('recycle-restore-modal').style.display = 'flex';
}

async function confirmRestoreRecycleItems() {
    var conflictMode = document.getElementById('recycle-restore-conflict-mode').value || 'skip';
    var result = await restoreRecycleItems(_pendingRestoreItems, conflictMode);
    if (result) {
        closeModal('recycle-restore-modal');
        loadRecycleList();
    }
}

async function restoreRecycleItems(items, conflictMode) {
    var result = await apiRequest('POST', '/recycle/restore', {
        items: items,
        conflict_mode: conflictMode || 'skip'
    });
    if (result.code === 200 || result.code === 207) {
        var data = result.data || {};
        var failed = data.failed || [];
        if (failed.length > 0 && result.code === 207) {
            var conflictList = document.getElementById('recycle-restore-conflict-list');
            var html = '';
            for (var i = 0; i < failed.length; i++) {
                html += '<div style="padding:4px 0;font-size:13px;color:var(--danger-color);">' + _escapeHtml(failed[i].message || failed[i].recycle_path || '') + '</div>';
            }
            conflictList.innerHTML = html;
            document.getElementById('recycle-restore-conflict-warning').style.display = 'block';
            showToast(result.message || '部分恢复失败', 'warning');
            return false;
        }
        showToast(result.message || '恢复成功', 'success');
        return true;
    } else {
        showToast(result.message || '恢复失败', 'error');
        return false;
    }
}

async function deleteRecycleItem(id) {
    showConfirm('永久删除', '确定要永久删除此文件吗？此操作不可恢复！', async function() {
        var result = await deleteRecycleItems([id]);
        if (result) loadRecycleList();
    });
}

async function batchDeleteRecycleItems() {
    var ids = _getSelectedRecycleIds();
    if (ids.length === 0) {
        showToast('请先选择要删除的文件', 'warning');
        return;
    }
    showConfirm('批量永久删除', '确定要永久删除选中的 ' + ids.length + ' 个文件吗？此操作不可恢复！', async function() {
        var result = await deleteRecycleItems(ids);
        if (result) loadRecycleList();
    });
}

async function deleteRecycleItems(items) {
    var result = await apiRequest('POST', '/recycle/delete', { items: items });
    if (result.code === 200) {
        showToast(result.message || '删除成功', 'success');
        return true;
    } else {
        showToast(result.message || '删除失败', 'error');
        return false;
    }
}

async function previewCleanerResult() {
    var resultEl = document.getElementById('cleaner-preview-result');
    resultEl.style.display = 'inline-block';
    resultEl.className = 'test-result loading';
    resultEl.textContent = '预览中...';

    var result = await apiRequest('GET', '/source-cleaner/preview');
    if (result.code === 200 && result.data) {
        var data = result.data;
        var items = data.items || [];
        var total = items.length;
        resultEl.className = 'test-result success';
        resultEl.textContent = '✓ 将清理 ' + total + ' 项';

        var summaryEl = document.getElementById('sc-preview-summary');
        var treeEl = document.getElementById('sc-preview-tree');

        var categories = {};
        var totalSize = 0;
        for (var i = 0; i < items.length; i++) {
            var cat = items[i].category || 'other';
            if (!categories[cat]) categories[cat] = {count: 0, size: 0, label: cat};
            categories[cat].count++;
            categories[cat].size += (items[i].size_mb || 0);
            totalSize += (items[i].size_mb || 0);
        }

        var catLabels = {
            'junk_video': '垃圾视频',
            'delete_extension': '删除后缀',
            'blacklist_pattern': '黑名单匹配',
            'blacklist_dir': '黑名单目录',
            'empty_dir': '空目录',
            'non_media': '非影视文件',
            'ai_delete': 'AI判定删除'
        };

        var summaryHtml = '<div class="sc-preview-stat"><span class="sc-preview-stat-num">' + total + '</span><span class="sc-preview-stat-label">项将清理</span></div>';
        summaryHtml += '<div class="sc-preview-stat"><span class="sc-preview-stat-num">' + totalSize.toFixed(1) + '</span><span class="sc-preview-stat-label">MB</span></div>';
        var catKeys = Object.keys(categories);
        for (var j = 0; j < catKeys.length; j++) {
            var c = categories[catKeys[j]];
            summaryHtml += '<div class="sc-preview-stat"><span class="sc-preview-stat-num">' + c.count + '</span><span class="sc-preview-stat-label">' + (catLabels[catKeys[j]] || catKeys[j]) + '</span></div>';
        }
        summaryEl.innerHTML = summaryHtml;

        var sourceDir = currentConfig.source_dir || '';

        var tree = buildDirTree(items, sourceDir);
        var rootName = sourceDir ? sourceDir.split('/').filter(function(s) { return s; }).pop() || sourceDir : '源目录';
        treeEl.innerHTML = '<div class="sc-tree-line sc-tree-root"><span class="sc-tree-folder">📂 ' + escapeHtml(rootName) + '</span></div>' + renderDirTree(tree, '');

        document.getElementById('sc-preview-modal').style.display = 'flex';
    } else {
        resultEl.className = 'test-result error';
        resultEl.textContent = '✗ ' + (result.message || '预览失败');
    }
}

function buildDirTree(items, sourceDir) {
    var root = {name: '', children: {}, items: []};
    for (var i = 0; i < items.length; i++) {
        var item = items[i];
        var path = item.path || '';
        var relPath = sourceDir && path.startsWith(sourceDir) ? path.substring(sourceDir.length) : path;
        relPath = relPath.replace(/^\/+/, '');
        var parts = relPath.split('/');

        var node = root;
        for (var p = 0; p < parts.length - 1; p++) {
            if (!node.children[parts[p]]) {
                node.children[parts[p]] = {name: parts[p], children: {}, items: []};
            }
            node = node.children[parts[p]];
        }
        node.items.push({
            name: parts[parts.length - 1],
            category: item.category,
            reason: item.reason,
            size_mb: item.size_mb,
            source: item.source
        });
    }
    return root;
}

var _scCategoryIcons = {
    'junk_video': '🎬',
    'delete_extension': '📄',
    'blacklist_pattern': '🚫',
    'blacklist_dir': '📁',
    'empty_dir': '📂',
    'non_media': '📎',
    'ai_delete': '🤖'
};

function renderDirTree(node, prefix) {
    var html = '';
    var childKeys = Object.keys(node.children).sort();
    var itemIdx = 0;

    for (var c = 0; c < childKeys.length; c++) {
        var key = childKeys[c];
        var child = node.children[key];
        var isLastDir = (c === childKeys.length - 1) && (node.items.length === 0);
        var connector = isLastDir ? '└── ' : '├── ';
        var childPrefix = isLastDir ? '    ' : '│   ';

        html += '<div class="sc-tree-line">';
        html += '<span class="sc-tree-indent">' + escapeHtml(prefix) + '</span>';
        html += '<span class="sc-tree-connector">' + connector + '</span>';
        html += '<span class="sc-tree-folder">📁 ' + escapeHtml(key) + '</span>';
        html += '</div>';

        html += renderDirTree(child, prefix + childPrefix);
    }

    for (var i = 0; i < node.items.length; i++) {
        var item = node.items[i];
        var isLast = (i === node.items.length - 1) && true;
        var conn = isLast ? '└── ' : '├── ';
        var icon = _scCategoryIcons[item.category] || '📄';

        html += '<div class="sc-tree-line" data-category="' + escapeHtml(item.category) + '">';
        html += '<span class="sc-tree-indent">' + escapeHtml(prefix) + '</span>';
        html += '<span class="sc-tree-connector">' + conn + '</span>';
        html += '<span class="sc-tree-icon">' + icon + '</span>';
        html += '<span class="sc-tree-file">' + escapeHtml(item.name) + '</span>';
        if (item.size_mb > 0) {
            html += '<span class="sc-tree-size">' + item.size_mb.toFixed(1) + 'MB</span>';
        }
        html += '<span class="sc-tree-reason">' + escapeHtml(item.reason || '') + '</span>';
        html += '</div>';
    }

    return html;
}


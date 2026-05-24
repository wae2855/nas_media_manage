let currentConfig = {};

var _currentConfigSubTab = 'import';

function switchTab(tabName) {
    const panels = document.querySelectorAll('.panel');
    const tabs = document.querySelectorAll('.tab-btn');

    panels.forEach(p => p.classList.remove('active'));
    tabs.forEach(t => t.classList.remove('active'));

    document.getElementById(`${tabName}-panel`).classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.add('active');

    var subTabBar = document.getElementById('config-sub-tab-bar');
    if (subTabBar) {
        subTabBar.style.display = (tabName === 'config') ? '' : 'none';
    }

    if (tabName === 'tasks') {
        loadTasks();
        refreshLogs();
    }

    if (tabName === 'config') {
        applyConfigSubTab(_currentConfigSubTab || 'import');
    }
}

function switchConfigSubTab(name) {
    _currentConfigSubTab = name;
    applyConfigSubTab(name);
}

function applyConfigSubTab(name) {
    var btns = document.querySelectorAll('.config-sub-tab-btn');
    btns.forEach(function(btn) { btn.classList.remove('active'); });
    var activeBtn = document.getElementById('cfg-subtab-' + name);
    if (activeBtn) activeBtn.classList.add('active');

    var sections = document.querySelectorAll('#cfg-sections-host .config-section');
    sections.forEach(function(sec) {
        var owner = sec.getAttribute('data-subtab') || '';
        sec.style.display = (owner === name) ? '' : 'none';
    });
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
        document.getElementById('cfg-source_policy-dedup_enabled').checked = sourcePolicy.dedup_enabled !== false;
        document.getElementById('cfg-source_policy-quarantine_dir').value = sourcePolicy.quarantine_dir || '';

        var metadata = c.metadata || {};
        var tmdb = metadata.tmdb || {};
        document.getElementById('cfg-metadata_tmdb_enabled').checked = tmdb.enabled !== false;
        document.getElementById('cfg-metadata_tmdb_api_key').value = tmdb.api_key || '';
        document.getElementById('cfg-metadata_tmdb_language').value = tmdb.language || 'zh-CN';
        document.getElementById('cfg-metadata_tmdb_fallback_language').value = tmdb.fallback_language || 'en-US';

        var llm = c.llm || {};
        document.getElementById('cfg-llm_provider').value = llm.provider || 'openai';
        document.getElementById('cfg-llm_api_key').value = llm.api_key || '';
        document.getElementById('cfg-llm_base_url').value = llm.base_url || '';
        document.getElementById('cfg-llm_model').value = llm.model || '';
        document.getElementById('cfg-llm_fallback_model').value = llm.fallback_model || '';
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

        var pathRules = c.path_rules || [];
        renderPathRules(pathRules);

        var ft = c.filename_templates || {};
        document.getElementById('cfg-filename_templates-movie').value = ft.movie || '';
        document.getElementById('cfg-filename_templates-tv').value = ft.tv || '';
        document.getElementById('cfg-filename_templates-subtitle').value = ft.subtitle || '';

        var dup = c.duplicate_handling || {};
        document.getElementById('cfg-duplicate_handling-strategy').value = dup.strategy || 'skip';

        var tq = c.task_queue || {};
        document.getElementById('cfg-task_queue-max_concurrent').value = tq.max_concurrent || 1;

        var manualReview = c.manual_review || {};
        document.getElementById('cfg-manual_review-enabled').checked = !!manualReview.enabled;

        if (result.data && result.data.prompts) {
            var prompts = result.data.prompts;
            document.getElementById('prompt-system').value = prompts.system_prompt || '';
        }
    } catch (e) {
        console.error('loadConfig error:', e);
        showToast('加载配置异常: ' + e.message, 'error');
    }
}

function isMaskedValue(value) {
    return !value || value.indexOf('***') !== -1;
}

function buildConfigFromForm() {
    const config = { ...currentConfig };

    config.server = config.server || {};
    const serverApiKey = document.getElementById('cfg-server_api_key').value;
    if (serverApiKey && !isMaskedValue(serverApiKey)) {
        config.server.api_key = serverApiKey;
    } else {
        delete config.server.api_key;
    }
    const serverPort = parseInt(document.getElementById('cfg-server_port').value);
    if (serverPort && serverPort >= 1024 && serverPort <= 65535) {
        config.server.port = serverPort;
    }

    config.source_dir = document.getElementById('cfg-source_dir').value;
    config.temp_dir = document.getElementById('cfg-temp_dir').value;
    config.log_dir = document.getElementById('cfg-log_dir').value;

    config.source_policy = {
        dedup_enabled: true,
        quarantine_dir: document.getElementById('cfg-source_policy-quarantine_dir').value,
        scan_recursive: document.getElementById('cfg-source_dir_scan-recursive').checked,
        scan_max_depth: parseInt(document.getElementById('cfg-source_dir_scan-max_depth').value) || 5
    };

    config.metadata = config.metadata || {};
    config.metadata.tmdb = config.metadata.tmdb || {};
    config.metadata.tmdb.enabled = document.getElementById('cfg-metadata_tmdb_enabled').checked;
    const tmdbApiKey = document.getElementById('cfg-metadata_tmdb_api_key').value;
    if (tmdbApiKey && !isMaskedValue(tmdbApiKey)) {
        config.metadata.tmdb.api_key = tmdbApiKey;
    } else if (currentConfig.metadata && currentConfig.metadata.tmdb && currentConfig.metadata.tmdb.api_key) {
        config.metadata.tmdb.api_key = currentConfig.metadata.tmdb.api_key;
    }
    config.metadata.tmdb.language = document.getElementById('cfg-metadata_tmdb_language').value;
    config.metadata.tmdb.fallback_language = document.getElementById('cfg-metadata_tmdb_fallback_language').value;

    config.llm = config.llm || {};
    config.llm.provider = document.getElementById('cfg-llm_provider').value;

    const apiKey = document.getElementById('cfg-llm_api_key').value;
    if (apiKey && !isMaskedValue(apiKey)) {
        config.llm.api_key = apiKey;
    } else {
        delete config.llm.api_key;
    }
    config.llm.base_url = document.getElementById('cfg-llm_base_url').value;
    config.llm.model = document.getElementById('cfg-llm_model').value;
    config.llm.fallback_model = document.getElementById('cfg-llm_fallback_model').value;
    config.llm.timeout = parseInt(document.getElementById('cfg-llm_timeout').value) || 30;
    config.llm.max_retries = parseInt(document.getElementById('cfg-llm_max_retries').value) || 2;
    config.llm.retry_delay = parseInt(document.getElementById('cfg-llm_retry_delay').value) || 3;
    config.llm.confidence_threshold = parseFloat(document.getElementById('cfg-llm_confidence_threshold').value) || 0.8;
    config.llm.verify_ssl = document.getElementById('cfg-llm_verify_ssl').checked;

    config.file_watcher = {
        enabled: document.getElementById('cfg-watcher_enabled').checked,
        poll_interval: parseInt(document.getElementById('cfg-watcher_poll_interval').value),
        ignore_patterns: document.getElementById('cfg-watcher_ignore_patterns').value
            .split('\n').filter(line => line.trim())
    };

    config.hermes = config.hermes || { webhook: {} };
    config.hermes.enabled = document.getElementById('cfg-hermes_enabled').checked;
    config.hermes.webhook = config.hermes.webhook || {};
    config.hermes.webhook.base_url = document.getElementById('cfg-hermes_webhook_base_url').value;
    config.hermes.webhook.route_name = document.getElementById('cfg-hermes_webhook_route_name').value;

    const secret = document.getElementById('cfg-hermes_webhook_secret').value;
    if (secret && !isMaskedValue(secret)) {
        config.hermes.webhook.secret = secret;
    } else {
        delete config.hermes.webhook.secret;
    }
    config.hermes.webhook.timeout = parseInt(document.getElementById('cfg-hermes_webhook_timeout').value) || 30;
    config.hermes.webhook.max_retries = parseInt(document.getElementById('cfg-hermes_webhook_max_retries').value) || 3;
    config.hermes.webhook.retry_delay = parseInt(document.getElementById('cfg-hermes_webhook_retry_delay').value) || 5;
    config.hermes.webhook.verify_ssl = document.getElementById('cfg-hermes_webhook_verify_ssl').checked;

    var hermesEvents = [];
    if (document.getElementById('cfg-hermes_event_batch_start').checked) hermesEvents.push('batch_start');
    if (document.getElementById('cfg-hermes_event_batch_complete').checked) hermesEvents.push('batch_complete');
    if (document.getElementById('cfg-hermes_event_program_error').checked) hermesEvents.push('program_error');
    config.hermes.webhook.events = hermesEvents;

    config.path_rules = collectPathRulesFromDOM();

    config.filename_templates = {
        movie: document.getElementById('cfg-filename_templates-movie').value,
        tv: document.getElementById('cfg-filename_templates-tv').value,
        subtitle: document.getElementById('cfg-filename_templates-subtitle').value
    };

    config.duplicate_handling = {
        strategy: document.getElementById('cfg-duplicate_handling-strategy').value
    };

    config.task_queue = {
        max_concurrent: parseInt(document.getElementById('cfg-task_queue-max_concurrent').value)
    };

    config.manual_review = {
        enabled: document.getElementById('cfg-manual_review-enabled').checked
    };

    return config;
}

async function saveConfig() {
    const config = buildConfigFromForm();

    var sourceDir = (config.source_dir || '').replace(/\/+$/, '');
    var tempDir = (config.temp_dir || '').replace(/\/+$/, '');
    var quarantineDir = (config.source_policy && config.source_policy.quarantine_dir || '').replace(/\/+$/, '');

    var missing = [];
    if (!sourceDir) missing.push('源目录');
    if (!tempDir) missing.push('中转目录');
    if (!quarantineDir) missing.push('隔离区路径');
    if (missing.length > 0) {
        showToast(missing.join('、') + ' 为必填项', 'error');
        return;
    }

    var conflicts = [];
    if (sourceDir && tempDir && sourceDir === tempDir) {
        conflicts.push('源目录与中转目录不能相同');
    }
    if (sourceDir && quarantineDir && sourceDir === quarantineDir) {
        conflicts.push('源目录与隔离区目录不能相同');
    }
    if (tempDir && quarantineDir && tempDir === quarantineDir) {
        conflicts.push('中转目录与隔离区目录不能相同');
    }
    if (conflicts.length > 0) {
        showToast(conflicts.join('；'), 'error');
        return;
    }

    showToast('正在检查路径权限...', 'info');
    var permCheck = await apiRequest('POST', '/config/check-permission', {
        source_dir: config.source_dir,
        temp_dir: config.temp_dir,
        log_dir: config.log_dir,
        path_rules: config.path_rules || []
    });

    if (permCheck && permCheck.code === 200 && permCheck.data) {
        if (!permCheck.data.all_ok) {
            showPermissionDialog(permCheck.data.issues || []);
            return;
        }
    } else {
        showToast('权限检查接口异常，但仍可尝试保存', 'warning');
    }

    const result = await apiRequest('POST', '/config', config);
    if (result.code === 200) {
        showToast(result.message || '配置已保存。配置变更需要重启服务才能完全生效，请到「概览」页点击「重启服务」按钮。', 'success');
        loadConfig();
        loadHealth();
    } else {
        showToast(result.message || '保存失败', 'error');
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
    var isHidden = body.style.display === 'none';
    body.style.display = isHidden ? 'block' : 'none';
    headerEl.classList.toggle('expanded', isHidden);
}

function onHermesToggle() {
    var checkbox = document.getElementById('cfg-hermes_enabled');
    var hermesSection = document.getElementById('hermes-config-section');
    if (!checkbox || !hermesSection) return;
    var enabled = checkbox.checked;
    var formGroups = hermesSection.querySelectorAll('.form-group');
    for (var i = 1; i < formGroups.length; i++) {
        formGroups[i].style.display = enabled ? 'block' : 'none';
    }
    var formRows = hermesSection.querySelectorAll('.form-row');
    formRows.forEach(function(row) {
        row.style.display = enabled ? 'flex' : 'none';
    });
}

async function validateConfig() {
    var result = await apiRequest('GET', '/config/validate');
    if (result.code === 200 && result.data) {
        var validation = result.data;
        var message = '';
        var type = 'success';

        if (validation.overall === 'ok') {
            message = '配置验证通过！基础配置项均正常。';
            type = 'success';
        } else {
            var details = validation.details || [];
            var errors = details.filter(function(d) { return d.status === 'error'; });
            var warnings = details.filter(function(d) { return d.status === 'warning'; });

            if (errors.length > 0) {
                message = '配置验证失败：\n\n';
                errors.forEach(function(e, i) {
                    message += (i + 1) + '. [' + (e.item || '未知项') + '] ' + (e.message || '未知错误') + '\n';
                });
                if (warnings.length > 0) {
                    message += '\n警告项：\n';
                    warnings.forEach(function(w, i) {
                        message += (i + 1) + '. [' + (w.item || '未知项') + '] ' + (w.message || '未知警告') + '\n';
                    });
                }
                type = 'error';
            } else if (warnings.length > 0) {
                message = '配置验证完成，有以下警告：\n\n';
                warnings.forEach(function(w, i) {
                    message += (i + 1) + '. [' + (w.item || '未知项') + '] ' + (w.message || '未知警告') + '\n';
                });
                type = 'warning';
            } else {
                message = '配置验证完成，无明显问题。';
                type = 'success';
            }
        }

        showToast(message, type);
    } else {
        showToast(result.message || '验证失败', 'error');
    }
}

async function testLLM() {
    var btn = document.getElementById('btn-test-llm');
    var resultEl = document.getElementById('llm-test-result');
    btn.disabled = true;
    resultEl.style.display = 'inline-block';
    resultEl.className = 'test-result loading';
    resultEl.textContent = '测试中...';

    var config = buildConfigFromForm();
    var llm = config.llm || {};
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

    var config = buildConfigFromForm();
    var hermes = config.hermes || {};
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

async function testTMDb() {
    var btn = document.getElementById('btn-test-tmdb');
    var resultEl = document.getElementById('tmdb-test-result');
    btn.disabled = true;
    resultEl.style.display = 'inline-block';
    resultEl.className = 'test-result loading';
    resultEl.textContent = '测试中...';

    var config = buildConfigFromForm();
    var metadata = config.metadata || {};
    var tmdb = metadata.tmdb || {};
    var result = await apiRequest('POST', '/config/test-tmdb', {
        api_key: tmdb.api_key || ''
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

function resetConfig() {
    if (confirm('确定要恢复默认配置吗？所有修改将丢失！')) {
        location.reload();
    }
}

function bindPathPermissionAutoTest() {
    var bindings = [
        { id: 'cfg-source_dir', needWrite: false },
        { id: 'cfg-temp_dir',   needWrite: true  },
        { id: 'cfg-log_dir',    needWrite: true  },
        { id: 'cfg-source_policy-quarantine_dir', needWrite: true }
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
    var isHidden = panel.style.display === 'none';
    panel.style.display = isHidden ? 'block' : 'none';
    if (arrow) {
        arrow.textContent = isHidden ? '▼' : '▶';
    }
}

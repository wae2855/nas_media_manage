let currentConfig = {};
let refreshInterval = null;

function getApiBase() {
    var path = window.location.pathname;
    var idx = path.indexOf('/index.cgi');
    if (idx >= 0) {
        return path.substring(0, idx + '/index.cgi'.length);
    }
    return '';
}

function getApiKey() {
    return localStorage.getItem('nas_api_key') || '';
}

function setApiKey(key) {
    localStorage.setItem('nas_api_key', key);
}

function promptApiKey() {
    const key = prompt('请输入 API Key（在配置文件 server.api_key 中设置）：');
    if (key !== null && key.trim()) {
        setApiKey(key.trim());
        location.reload();
    }
}

function switchTab(tabName) {
    const panels = document.querySelectorAll('.panel');
    const tabs = document.querySelectorAll('.tab-btn');
    
    panels.forEach(p => p.classList.remove('active'));
    tabs.forEach(t => t.classList.remove('active'));
    
    document.getElementById(`${tabName}-panel`).classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.add('active');
    
    if (tabName === 'tasks') {
        loadTasks();
        refreshLogs();
    }
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    const icon = document.getElementById('toast-icon');
    
    icon.innerHTML = '';
    icon.className = `toast-icon ${type}`;
    
    if (type === 'success') {
        icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>';
    } else if (type === 'error') {
        icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
    } else if (type === 'warning') {
        icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>';
    }
    
    document.getElementById('toast-message').textContent = message;
    toast.style.display = 'flex';
    
    setTimeout(() => {
        toast.style.display = 'none';
    }, 3000);
}

async function apiRequest(method, endpoint, body = null) {
    try {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        const apiKey = getApiKey();
        if (apiKey) {
            options.headers['Authorization'] = 'Bearer ' + apiKey;
        }
        
        if (body) {
            options.body = JSON.stringify(body);
        }
        
        const response = await fetch(getApiBase() + '/api' + endpoint, options);
        
        if (response.status === 401) {
            promptApiKey();
            return { code: 401, status: 'unauthorized', message: '认证失败' };
        }
        
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('API request failed:', error);
        return { code: 500, status: 'error', message: '网络请求失败' };
    }
}

async function loadHealth() {
    const result = await apiRequest('GET', '/health');
    if (result.code === 200 && result.data) {
        const checks = result.data.checks;
        
        updateStatus('status-source', checks.source_dir);
        updateStatus('status-temp', checks.temp_dir);
        updateStatus('status-llm', checks.llm_api);
        updateStatus('status-hermes', checks.hermes);

        var logDirEl = document.getElementById('val-log-dir');
        if (logDirEl && checks.log_dir_path) {
            logDirEl.textContent = checks.log_dir_path;
        }
        
        if (checks.disk_space) {
            document.getElementById('val-disk').textContent = checks.disk_space === 'ok' ? '正常' : '不足';
        }
    }
}

function updateStatus(elementId, value) {
    const element = document.getElementById(elementId);
    element.textContent = value === 'ok' ? '正常' : value === 'disabled' ? '已禁用' : '异常';
    element.className = `status-value status-${value === 'ok' ? 'ok' : value === 'disabled' ? 'disabled' : 'error'}`;
}

async function loadMetrics() {
    const result = await apiRequest('GET', '/metrics');
    if (result.code === 200 && result.data) {
        const queue = result.data.queue_by_status || {};
        document.getElementById('val-pending').textContent = queue.PENDING || queue.pending || 0;
        document.getElementById('val-success').textContent = queue.SUCCESS || queue.success || 0;
        document.getElementById('val-failed').textContent = queue.FAILED || queue.failed || 0;
    }
}

async function loadWatcherStatus() {
    const result = await apiRequest('GET', '/watcher/status');
    if (result.code === 200 && result.data) {
        const toggle = document.getElementById('watcher-toggle');
        toggle.checked = result.data.enabled;
        document.getElementById('watcher-status').textContent = result.data.enabled ? '已启用' : '已禁用';
        
        if (result.data.poll_interval) {
            document.getElementById('poll-interval').value = result.data.poll_interval;
        }
    }
}

async function toggleWatcher() {
    const enabled = document.getElementById('watcher-toggle').checked;
    const action = enabled ? 'resume' : 'pause';
    
    const result = await apiRequest('POST', `/watcher/control?action=${action}`);
    if (result.code === 200) {
        document.getElementById('watcher-status').textContent = enabled ? '已启用' : '已禁用';
        showToast(result.message || (enabled ? '监控已启用' : '监控已暂停'));
    } else {
        showToast(result.message || '操作失败', 'error');
        document.getElementById('watcher-toggle').checked = !enabled;
    }
}

async function runBatch() {
    const result = await apiRequest('POST', '/run');
    if (result.code === 202) {
        showToast(result.message || '批量处理已启动');
    } else {
        showToast(result.message || '启动失败', 'error');
    }
}

async function pauseQueue() {
    const result = await apiRequest('POST', '/queue/pause');
    if (result.code === 200) {
        showToast(result.message || '队列已暂停');
    } else {
        showToast(result.message || '操作失败', 'error');
    }
}

async function retryAllFailed() {
    const result = await apiRequest('POST', '/queue/retry-all');
    if (result.code === 200) {
        showToast(result.message || '重试已开始');
        loadTasks();
    } else {
        showToast(result.message || '操作失败', 'error');
    }
}

async function restartService() {
    if (!confirm('确定要重启服务吗？重启期间服务将短暂不可用。')) return;
    const result = await apiRequest('POST', '/restart');
    if (result.code === 200) {
        showToast('服务正在重启，请等待约5秒后刷新页面...');
        setTimeout(() => location.reload(), 5000);
    } else {
        showToast(result.message || '重启失败', 'error');
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
        
        // 初始化 Hermes 配置区域的显示/隐藏状态
        onHermesToggle();

        var scan = c.source_dir_scan || {};
        document.getElementById('cfg-source_dir_scan-recursive').checked = scan.recursive !== false;
        document.getElementById('cfg-source_dir_scan-max_depth').value = scan.max_depth || 5;

        var pathRules = c.path_rules || [];
        if (Array.isArray(pathRules)) {
            var yamlLines = [];
            for (var i = 0; i < pathRules.length; i++) {
                var rule = pathRules[i];
                yamlLines.push('- conditions:');
                var cond = rule.conditions || {};
                var keys = Object.keys(cond);
                for (var j = 0; j < keys.length; j++) {
                    yamlLines.push('    ' + keys[j] + ': ' + cond[keys[j]]);
                }
                yamlLines.push("  template: '" + (rule.template || '') + "'");
            }
            document.getElementById('cfg-path_rules').value = yamlLines.join('\n');
        } else {
            document.getElementById('cfg-path_rules').value = '';
        }

        var ft = c.filename_templates || {};
        document.getElementById('cfg-filename_templates-movie').value = ft.movie || '';
        document.getElementById('cfg-filename_templates-tv').value = ft.tv || '';
        document.getElementById('cfg-filename_templates-subtitle').value = ft.subtitle || '';

        var dup = c.duplicate_handling || {};
        var dupEnabled = (dup.enabled !== false);
        document.getElementById('cfg-duplicate_handling-enabled').checked = dupEnabled;
        document.getElementById('cfg-duplicate_handling-strategy').value = dup.strategy || 'skip';
        onDedupEnabledChange();

        var sfh = c.source_file_handling || {};
        document.getElementById('cfg-source_file_handling-delete_after_process').checked = !!sfh.delete_after_process;

        var fs = c.file_scraping || {};
        var fileScrapingEnabled = (fs.enabled !== false);
        document.getElementById('cfg-file_scraping_enabled').checked = fileScrapingEnabled;
        onFileScrapingToggle();

        var tq = c.task_queue || {};
        document.getElementById('cfg-task_queue-persistence_path').value = tq.persistence_path || '';
        document.getElementById('cfg-task_queue-max_concurrent').value = tq.max_concurrent || 1;
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
    
    config.source_dir_scan = {
        recursive: document.getElementById('cfg-source_dir_scan-recursive').checked,
        max_depth: parseInt(document.getElementById('cfg-source_dir_scan-max_depth').value)
    };
    
    // path_rules 使用 YAML 格式
    const pathRulesText = document.getElementById('cfg-path_rules').value;
    try {
        // 简单的 YAML 解析（只处理我们需要的格式）
        const rules = [];
        const lines = pathRulesText.trim().split('\n');
        let currentRule = null;
        
        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('- conditions:')) {
                if (currentRule) {
                    rules.push(currentRule);
                }
                currentRule = { conditions: {}, template: '' };
            } else if (currentRule && trimmed.startsWith('template:')) {
                currentRule.template = trimmed.replace(/^template:\s*/, '').replace(/['"]/g, '');
            } else if (currentRule && trimmed.length > 0 && !trimmed.startsWith('-')) {
                const parts = trimmed.split(':');
                if (parts.length >= 2) {
                    const key = parts[0].trim();
                    const value = parts.slice(1).join(':').trim().replace(/['"]/g, '');
                    currentRule.conditions[key] = value;
                }
            }
        }
        if (currentRule) {
            rules.push(currentRule);
        }
        config.path_rules = rules;
    } catch (e) {
        console.error('Invalid path_rules YAML:', e);
        config.path_rules = [];
    }

    config.filename_templates = {
        movie: document.getElementById('cfg-filename_templates-movie').value,
        tv: document.getElementById('cfg-filename_templates-tv').value,
        subtitle: document.getElementById('cfg-filename_templates-subtitle').value
    };
    
    config.duplicate_handling = {
        enabled: document.getElementById('cfg-duplicate_handling-enabled').checked,
        strategy: document.getElementById('cfg-duplicate_handling-strategy').value
    };
    
    config.source_file_handling = {
        delete_after_process: document.getElementById('cfg-source_file_handling-delete_after_process').checked
    };

    config.file_scraping = {
        enabled: document.getElementById('cfg-file_scraping_enabled').checked
    };
    
    config.task_queue = {
        persistence_path: document.getElementById('cfg-task_queue-persistence_path').value,
        max_concurrent: parseInt(document.getElementById('cfg-task_queue-max_concurrent').value)
    };
    
    return config;
}

async function saveConfig() {
    const config = buildConfigFromForm();

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

    var rulesText = (document.getElementById('cfg-path_rules').value || '').trim();
    if (!rulesText) {
        resultEl.className = 'perm-result perm-error';
        resultEl.textContent = '请先填写入库规则';
        return;
    }

    resultEl.className = 'perm-result perm-loading';
    resultEl.textContent = '正在测试所有入库目录...';

    var path_rules;
    try {
        path_rules = parsePathRulesYaml(rulesText);
    } catch (e) {
        resultEl.className = 'perm-result perm-error';
        resultEl.textContent = '入库规则解析失败: ' + e.message;
        return;
    }

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

function onDedupEnabledChange() {
    var checkbox = document.getElementById('cfg-duplicate_handling-enabled');
    var warning = document.getElementById('dedup-disabled-warning');
    var strategyGroup = document.getElementById('dedup-strategy-group');
    if (!checkbox) return;
    var enabled = checkbox.checked;
    if (warning) warning.style.display = enabled ? 'none' : 'block';
    if (strategyGroup) strategyGroup.style.display = enabled ? 'block' : 'none';
}

function onFileScrapingToggle() {
    var checkbox = document.getElementById('cfg-file_scraping_enabled');
    var llmSection = document.getElementById('llm-config-section');
    if (!checkbox || !llmSection) return;
    var enabled = checkbox.checked;
    llmSection.style.display = enabled ? 'block' : 'none';
}

function onHermesToggle() {
    var checkbox = document.getElementById('cfg-hermes_enabled');
    var hermesSection = document.getElementById('hermes-config-section');
    if (!checkbox || !hermesSection) return;
    var enabled = checkbox.checked;
    // 控制 Hermes 配置区域中除了第一个表单组外的其他元素显示/隐藏
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

function resetConfig() {
    if (confirm('确定要恢复默认配置吗？所有修改将丢失！')) {
        location.reload();
    }
}

async function loadTasks() {
    const result = await apiRequest('GET', '/tasks?all=true&limit=50');
    if (result.code === 200 && result.data) {
        const tasks = result.data.tasks || [];
        const tbody = document.getElementById('tasks-table-body');
        
        if (tasks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-row">暂无任务数据</td></tr>';
            return;
        }
        
        tbody.innerHTML = tasks.map(task => `
            <tr>
                <td title="${task.video_file}">${truncate(task.video_file, 30)}</td>
                <td><span class="status-value status-${getStatusClass(task.status)}">${getStatusText(task.status)}</span></td>
                <td>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${task.percentage || 0}%"></div>
                    </div>
                    ${task.percentage || 0}%
                </td>
                <td title="${getScrapedInfo(task)}">${truncate(getScrapedInfo(task), 25)}</td>
                <td title="${formatTimeDetail(task)}">${formatTimeBrief(task)}</td>
                <td title="${task.error_message || ''}">${truncate(task.error_message || '-', 20)}</td>
                <td>
                    ${task.status === 'FAILED' ? 
                        `<button class="btn btn-sm btn-primary" onclick="retryTask('${task.task_id}')">重试</button>` : ''}
                </td>
            </tr>
        `).join('');
    }
}

function formatTimeBrief(task) {
    if (!task.started_at) {
        return task.created_at ? task.created_at.substring(5, 16).replace('T', ' ') : '-';
    }
    var start = task.started_at.substring(5, 16).replace('T', ' ');
    if (task.completed_at) {
        var end = task.completed_at.substring(5, 16).replace('T', ' ');
        return start + ' ~ ' + end;
    }
    return start + ' ...';
}

function formatTimeDetail(task) {
    var parts = [];
    if (task.created_at) parts.push('创建: ' + task.created_at.replace('T', ' ').substring(0, 19));
    if (task.started_at) parts.push('开始: ' + task.started_at.replace('T', ' ').substring(0, 19));
    if (task.completed_at) parts.push('完成: ' + task.completed_at.replace('T', ' ').substring(0, 19));
    return parts.join('\n') || '-';
}

function getStatusClass(status) {
    const map = {
        'SUCCESS': 'ok',
        'FAILED': 'error',
        'PROCESSING': 'warning',
        'PENDING': 'warning',
        'SKIPPED': 'disabled'
    };
    return map[status] || 'unknown';
}

function getStatusText(status) {
    const map = {
        'SUCCESS': '成功',
        'FAILED': '失败',
        'PROCESSING': '处理中',
        'PENDING': '待处理',
        'SKIPPED': '跳过'
    };
    return map[status] || status;
}

function getScrapedInfo(task) {
    const info = task.scraped_info;
    if (!info) return '-';
    const title = info.title_cn || info.title_en || '未知';
    const year = info.year ? `(${info.year})` : '';
    return `${title}${year}`;
}

function truncate(text, length) {
    if (!text) return '-';
    return text.length > length ? text.substring(0, length) + '...' : text;
}

async function retryTask(taskId) {
    const result = await apiRequest('POST', `/tasks/${taskId}/retry`);
    if (result.code === 200) {
        showToast('任务已重试并开始执行');
        loadTasks();
    } else {
        showToast(result.message || '操作失败', 'error');
    }
}

async function refreshLogs() {
    const result = await apiRequest('GET', '/logs?limit=100');
    if (result.code === 200 && result.data) {
        const logs = result.data.logs || [];
        const container = document.getElementById('log-container');
        
        if (logs.length === 0) {
            container.innerHTML = '<div class="log-line">暂无日志</div>';
            return;
        }
        
        container.innerHTML = logs.map(log => {
            const timestamp = (log.time || '-').substring(11, 19);
            const level = log.level || 'INFO';
            const message = log.message || log.raw || JSON.stringify(log);
            const step = log.step || '';
            const taskId = log.task_id || '';
            
            var levelClass = 'log-level-info';
            if (level === 'ERROR') levelClass = 'log-level-error';
            else if (level === 'WARN' || level === 'WARNING') levelClass = 'log-level-warn';
            else if (level === 'DEBUG') levelClass = 'log-level-debug';
            
            var stepTag = step ? '<span class="log-step">' + step + '</span> ' : '';
            var taskTag = taskId ? '<span class="log-task">[' + taskId.substring(0, 8) + ']</span> ' : '';
            
            return '<div class="log-line">' +
                '<span class="log-time">' + timestamp + '</span> ' +
                '<span class="' + levelClass + '">' + level + '</span> ' +
                taskTag + stepTag +
                '<span class="log-msg">' + escapeHtml(message) + '</span>' +
                '</div>';
        }).join('');
        
        container.scrollTop = container.scrollHeight;
    }
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

function startAutoRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(function() {
        loadHealth();
        loadMetrics();
        refreshLogs();
    }, 5000);
}

document.addEventListener('DOMContentLoaded', function() {
    loadHealth();
    loadMetrics();
    loadConfig();
    refreshLogs();
    startAutoRefresh();
    bindPathPermissionAutoTest();
});

function bindPathPermissionAutoTest() {
    var bindings = [
        { id: 'cfg-source_dir', needWrite: false },
        { id: 'cfg-temp_dir',   needWrite: true  },
        { id: 'cfg-log_dir',    needWrite: true  }
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

window.addEventListener('beforeunload', () => {
    if (refreshInterval) clearInterval(refreshInterval);
});
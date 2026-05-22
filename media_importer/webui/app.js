let currentConfig = {};
let refreshInterval = null;

// 固定维度定义
const FIXED_DIMENSIONS = [
    { name: 'media_type', label: '影视类型', type: 'select', options: ['', 'movie', 'tv'] },
    { name: 'documentary', label: '是否纪录片', type: 'select', options: ['', 'true', 'false'] },
    { name: 'animation', label: '是否动漫', type: 'select', options: ['', 'true', 'false'] },
    { name: 'restricted_level', label: '限制级', type: 'multi-select', options: ['0-6', '7-12', '13-15', '17+'] }
];

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

// ==================== 配置面板子页签 ====================

var _currentConfigSubTab = 'import';

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
        renderPathRules(pathRules);

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

        var tq = c.task_queue || {};
        document.getElementById('cfg-task_queue-persistence_path').value = tq.persistence_path || '';
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
    
    config.path_rules = collectPathRulesFromDOM();

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

    config.task_queue = {
        persistence_path: document.getElementById('cfg-task_queue-persistence_path').value,
        max_concurrent: parseInt(document.getElementById('cfg-task_queue-max_concurrent').value)
    };

    config.manual_review = {
        enabled: document.getElementById('cfg-manual_review-enabled').checked
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

function onDedupEnabledChange() {
    var checkbox = document.getElementById('cfg-duplicate_handling-enabled');
    var warning = document.getElementById('dedup-disabled-warning');
    var strategyGroup = document.getElementById('dedup-strategy-group');
    if (!checkbox) return;
    var enabled = checkbox.checked;
    if (warning) warning.style.display = enabled ? 'none' : 'block';
    if (strategyGroup) strategyGroup.style.display = enabled ? 'block' : 'none';
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

// ==================== 任务列表变量 ====================
var _currentTaskPage = 1;
var _currentTaskStatus = 'all';
var _currentTaskTotalPages = 1;

async function loadTasks(page, status) {
    if (page !== undefined) _currentTaskPage = page;
    if (status !== undefined) _currentTaskStatus = status;
    var pageNum = _currentTaskPage || 1;
    var statusFilter = _currentTaskStatus || 'all';

    var url = '/tasks?page=' + pageNum + '&limit=20';
    if (statusFilter !== 'all') {
        url += '&status=' + encodeURIComponent(statusFilter);
    }

    var result = await apiRequest('GET', url);
    if (result.code === 200 && result.data) {
        var tasks = result.data.tasks || [];
        var total = result.data.total || 0;
        var totalPages = result.data.total_pages || 1;
        _currentTaskTotalPages = totalPages;

        renderTaskTable(tasks);
        renderPagination(totalPages, pageNum, total);
    } else {
        var tbody = document.getElementById('tasks-table-body');
        tbody.innerHTML = '<tr><td colspan="5" class="empty-row">加载失败: ' + (result.message || '未知错误') + '</td></tr>';
    }
}

function renderTaskTable(tasks) {
    var tbody = document.getElementById('tasks-table-body');
    if (!tasks || tasks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-row">暂无任务数据</td></tr>';
        return;
    }

    tbody.innerHTML = tasks.map(function(task) {
        var tid = task.task_id || '';
        var filename = task.source_filename || '-';
        var status = task.status || 'PENDING';
        var importPath = task.import_path || '';
        var subtitleInfo = buildSubtitleCell(task);
        var scrapeInfo = buildScrapeCell(task);
        var actionsHtml = buildActionButtons(task);

        return '<tr class="fade-in">' +
            '<td><div class="task-row-main">' +
                '<div class="task-row-title">' +
                    '<span class="task-filename" onclick="showTaskDetail(\'' + tid + '\')" title="点击查看详情">' + escapeHtml(filename) + '</span>' +
                '</div>' +
                '<div class="task-row-sub">' + scrapeInfo + '</div>' +
            '</div></td>' +
            '<td class="task-subtitle-cell">' + subtitleInfo + '</td>' +
            '<td><span class="status-badge status-badge-' + status + '">' + getStatusText(status) + '</span></td>' +
            '<td><span class="task-import-path" title="' + escapeHtml(importPath) + '">' + (importPath ? escapeHtml(truncate(importPath, 35)) : '-') + '</span></td>' +
            '<td><div class="task-actions">' + actionsHtml + '</div></td>' +
        '</tr>';
    }).join('');
}

function buildScrapeCell(task) {
    var parts = [];
    var titleCn = task.scrape_title_cn || '';
    var titleEn = task.scrape_title_en || '';
    var mediaType = task.scrape_media_type || '';
    var year = task.scrape_year || '';

    if (titleCn || titleEn) {
        var title = titleCn || titleEn;
        parts.push('<span class="task-scrape-chip' + (mediaType === 'movie' ? ' type-movie' : mediaType === 'tv' ? ' type-tv' : '') + '">' +
            escapeHtml(title) + (year ? ' (' + year + ')' : '') +
        '</span>');
    }

    if (mediaType) {
        parts.push('<span>' + (mediaType === 'movie' ? '电影' : mediaType === 'tv' ? '剧集' : mediaType) + '</span>');
    }

    if (task.scrape_season) {
        parts.push('<span>S' + String(task.scrape_season).padStart(2, '0') + '</span>');
    }
    if (task.scrape_episode) {
        parts.push('<span>E' + String(task.scrape_episode).padStart(2, '0') + '</span>');
    }

    if (task.skip_reason) {
        parts.push('<span style="color:var(--text-muted)">' + escapeHtml(truncate(task.skip_reason, 20)) + '</span>');
    } else if (task.error_message) {
        parts.push('<span style="color:var(--danger-color)">' + escapeHtml(truncate(task.error_message, 20)) + '</span>');
    }

    return parts.length > 0 ? parts.join(' ') : '<span style="color:var(--text-muted)">等待处理...</span>';
}

function buildSubtitleCell(task) {
    var subs = task.subtitle_files;
    if (!subs || subs.length === 0) {
        return '<span class="task-subtitle-count">无</span>';
    }
    var count = subs.length;
    return '<span class="task-subtitle-count has-subs" onclick="showSubtitleDetail(\'' + task.task_id + '\')">' +
        '字幕 x' + count +
    '</span>';
}

function buildActionButtons(task) {
    var tid = task.task_id || '';
    var status = task.status || '';
    var btns = [];

    btns.push('<button class="task-action-btn copy-path" onclick="copyPathToClipboard(\'' + escapeHtml(tid) + '\')" title="复制源路径到剪贴板">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>' +
    '</button>');

    btns.push('<button class="task-action-btn" onclick="showTaskDetail(\'' + escapeHtml(tid) + '\')" title="查看详情">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M22 12c0 5.52-4.48 10-10 10S2 17.52 2 12 6.48 2 12 2s10 4.48 10 10z"/></svg>' +
    '</button>');

    if (status === 'CONFIRMING') {
        btns.push('<button class="task-action-btn confirm" onclick="confirmTask(\'' + escapeHtml(tid) + '\')" title="确认入库">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>' +
        '</button>');
        btns.push('<button class="task-action-btn reclassify" onclick="showTaskDetail(\'' + escapeHtml(tid) + '\')" title="修改分类">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0-3-3m3 3 3-3M5 21h14"/></svg>' +
        '</button>');
        btns.push('<button class="task-action-btn rollback" onclick="confirmRollback(\'' + escapeHtml(tid) + '\')" title="回退到源目录">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>' +
        '</button>');
    }

    if (status === 'FAILED' || status === 'NEEDS_REVIEW') {
        btns.push('<button class="task-action-btn retry" onclick="retryTask(\'' + escapeHtml(tid) + '\')" title="重试">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>' +
        '</button>');
    }

    if (status === 'FAILED' || status === 'NEEDS_REVIEW' || status === 'ROLLBACK') {
        btns.push('<button class="task-action-btn ignore" onclick="ignoreTask(\'' + escapeHtml(tid) + '\')" title="忽略">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>' +
        '</button>');
    }

    return btns.join('');
}

function renderPagination(totalPages, currentPage, total) {
    var container = document.getElementById('pagination-controls');
    if (!container) return;

    if (totalPages <= 1) {
        container.innerHTML = '<span class="pagination-info">共 ' + (total || 0) + ' 条</span>';
        return;
    }

    var html = '';
    html += '<button class="pagination-btn" onclick="loadTasks(1)" ' + (currentPage <= 1 ? 'disabled' : '') + '>首页</button>';
    html += '<button class="pagination-btn" onclick="loadTasks(' + (currentPage - 1) + ')" ' + (currentPage <= 1 ? 'disabled' : '') + '>上一页</button>';

    var startPage = Math.max(1, currentPage - 2);
    var endPage = Math.min(totalPages, currentPage + 2);
    for (var p = startPage; p <= endPage; p++) {
        html += '<button class="pagination-btn ' + (p === currentPage ? 'active' : '') + '" onclick="loadTasks(' + p + ')">' + p + '</button>';
    }

    html += '<button class="pagination-btn" onclick="loadTasks(' + (currentPage + 1) + ')" ' + (currentPage >= totalPages ? 'disabled' : '') + '>下一页</button>';
    html += '<button class="pagination-btn" onclick="loadTasks(' + totalPages + ')" ' + (currentPage >= totalPages ? 'disabled' : '') + '>末页</button>';
    html += '<span class="pagination-info">第 ' + currentPage + '/' + totalPages + ' 页 (共 ' + (total || 0) + ' 条)</span>';

    container.innerHTML = html;
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

function getStatusText(status) {
    var map = {
        'SUCCESS': '成功',
        'FAILED': '失败',
        'PROCESSING': '处理中',
        'PENDING': '待处理',
        'SKIPPED': '跳过',
        'CONFIRMING': '确认中',
        'NEEDS_REVIEW': '需介入',
        'ROLLBACK': '已回退'
    };
    return map[status] || status || '未知';
}

function truncate(text, length) {
    if (!text) return '';
    return text.length > length ? text.substring(0, length) + '...' : text;
}

// ==================== 任务操作函数 ====================

async function retryTask(taskId) {
    var result = await apiRequest('POST', '/tasks/' + encodeURIComponent(taskId) + '/retry');
    if (result.code === 200) {
        showToast('任务已重试并开始执行');
        loadTasks();
    } else {
        showToast(result.message || '操作失败', 'error');
    }
}

async function confirmTask(taskId) {
    var result = await apiRequest('POST', '/tasks/' + encodeURIComponent(taskId) + '/confirm');
    if (result.code === 200) {
        showToast('任务确认入库成功');
        loadTasks();
    } else {
        showToast(result.message || '确认失败', 'error');
    }
}

async function reclassifyTask(taskId, dimensions) {
    var result = await apiRequest('POST', '/tasks/' + encodeURIComponent(taskId) + '/reclassify', {
        dimensions: dimensions
    });
    if (result.code === 200) {
        showToast('重新分类完成');
        loadTasks();
        closeModal('task-detail-modal');
    } else {
        showToast(result.message || '重新分类失败', 'error');
    }
}

async function rollbackTask(taskId) {
    var result = await apiRequest('POST', '/tasks/' + encodeURIComponent(taskId) + '/rollback');
    if (result.code === 200) {
        showToast('已回退到源目录');
        loadTasks();
        closeModal('rollback-confirm-modal');
        closeModal('task-detail-modal');
    } else {
        showToast(result.message || '回退失败', 'error');
    }
}

async function ignoreTask(taskId) {
    if (!confirm('确认忽略该任务？')) return;
    var result = await apiRequest('POST', '/tasks/' + encodeURIComponent(taskId) + '/ignore');
    if (result.code === 200) {
        showToast('任务已忽略');
        loadTasks();
    } else {
        showToast(result.message || '操作失败', 'error');
    }
}

function confirmRollback(taskId) {
    var modal = document.getElementById('rollback-confirm-modal');
    var btn = document.getElementById('rollback-confirm-btn');
    btn.onclick = function() { rollbackTask(taskId); };
    modal.style.display = 'flex';
}

async function copyPathToClipboard(taskId) {
    var result = await apiRequest('GET', '/tasks/' + encodeURIComponent(taskId));
    if (result.code === 200 && result.data && result.data.task) {
        var path = result.data.task.source_path || '';
        if (path) {
            try {
                await navigator.clipboard.writeText(path);
                showToast('路径已复制到剪贴板');
            } catch (e) {
                showToast('复制失败: ' + e.message, 'error');
            }
        } else {
            showToast('无源路径', 'warning');
        }
    } else {
        showToast('获取任务信息失败', 'error');
    }
}

// ==================== 详情弹窗 ====================

async function showTaskDetail(taskId) {
    var result = await apiRequest('GET', '/tasks/' + encodeURIComponent(taskId));
    if (result.code !== 200 || !result.data || !result.data.task) {
        showToast('获取任务详情失败', 'error');
        return;
    }
    var task = result.data.task;
    var body = document.getElementById('task-detail-body');
    var footer = document.getElementById('task-detail-footer');

    var dims = task.scrape_dimensions || {};
    var dimHtml = '';
    if (Object.keys(dims).length > 0) {
        dimHtml = '<div class="detail-field"><div class="detail-field-label">分类维度</div>' +
            '<div class="detail-dim-grid" id="detail-dim-grid">';
        for (var key in dims) {
            dimHtml += '<div class="detail-dim-item">' +
                '<span class="detail-dim-key">' + escapeHtml(key) + '</span>' +
                '<span class="detail-dim-val">' + escapeHtml(String(dims[key])) + '</span>' +
            '</div>';
        }
        dimHtml += '</div></div>';
    }

    var scrapeResult = task.scrape_result || {};
    var scrapeInfo = '';
    if (scrapeResult && typeof scrapeResult === 'object') {
        var title = scrapeResult.title_cn || scrapeResult.title_en || '';
        if (title) {
            scrapeInfo += '<div class="detail-field"><div class="detail-field-label">刮削标题</div><div class="detail-field-value">' + escapeHtml(title) + '</div></div>';
        }
        if (scrapeResult.year) {
            scrapeInfo += '<div class="detail-field"><div class="detail-field-label">年份</div><div class="detail-field-value">' + escapeHtml(scrapeResult.year) + '</div></div>';
        }
        if (scrapeResult.type) {
            scrapeInfo += '<div class="detail-field"><div class="detail-field-label">类型</div><div class="detail-field-value">' + escapeHtml(scrapeResult.type) + '</div></div>';
        }
        if (scrapeResult.confidence !== undefined) {
            scrapeInfo += '<div class="detail-field"><div class="detail-field-label">置信度</div><div class="detail-field-value">' + scrapeResult.confidence + '</div></div>';
        }
    }

    var dedupResult = task.dedup_result || {};
    var dedupInfo = '';
    if (dedupResult && dedupResult.is_duplicate) {
        dedupInfo += '<div class="detail-field"><div class="detail-field-label">查重结果 (重复)</div><div class="detail-field-value">已存在文件: ' + escapeHtml(dedupResult.existing_file || '') + '</div></div>';
    }

    body.innerHTML =
        '<div class="detail-field"><div class="detail-field-label">任务ID</div><div class="detail-field-value code">' + escapeHtml(task.task_id || '') + '</div></div>' +
        '<div class="detail-field"><div class="detail-field-label">源文件名</div><div class="detail-field-value">' + escapeHtml(task.source_filename || '') + '</div></div>' +
        '<div class="detail-field"><div class="detail-field-label">源路径</div><div class="detail-field-value code">' + escapeHtml(task.source_path || '') + '</div></div>' +
        '<div class="detail-field"><div class="detail-field-label">状态</div><div class="detail-field-value"><span class="status-badge status-badge-' + (task.status || 'PENDING') + '">' + getStatusText(task.status) + '</span></div></div>' +
        '<div class="detail-field"><div class="detail-field-label">时间</div><div class="detail-field-value">' + formatTimeDetail(task).replace(/\n/g, '<br>') + '</div></div>' +
        scrapeInfo +
        dimHtml +
        dedupInfo +
        '<div class="detail-field"><div class="detail-field-label">入库路径</div><div class="detail-field-value code">' + escapeHtml(task.import_path || '-') + '</div></div>' +
        (task.final_filename ? '<div class="detail-field"><div class="detail-field-label">最终文件名</div><div class="detail-field-value">' + escapeHtml(task.final_filename) + '</div></div>' : '') +
        (task.error_message ? '<div class="detail-field"><div class="detail-field-label">错误信息</div><div class="detail-field-value" style="color:var(--danger-color)">' + escapeHtml(task.error_message) + '</div></div>' : '') +
        (task.skip_reason ? '<div class="detail-field"><div class="detail-field-label">跳过原因</div><div class="detail-field-value" style="color:var(--text-muted)">' + escapeHtml(task.skip_reason) + '</div></div>' : '');

    footer.innerHTML = '';
    var status = task.status || '';

    if (status === 'CONFIRMING') {
        var reclassifyHtml = buildReclassifyForm(task);
        body.innerHTML += reclassifyHtml;

        footer.innerHTML =
            '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>' +
            '<button class="btn btn-warning" onclick="confirmRollback(\'' + escapeHtml(task.task_id) + '\')">回退</button>' +
            '<button class="btn btn-primary" onclick="confirmTask(\'' + escapeHtml(task.task_id) + '\')">确认入库</button>';
    } else if (status === 'FAILED' || status === 'NEEDS_REVIEW') {
        footer.innerHTML =
            '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>' +
            '<button class="btn btn-primary" onclick="retryTask(\'' + escapeHtml(task.task_id) + '\')">重试</button>';
    } else {
        footer.innerHTML =
            '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>';
    }

    var modal = document.getElementById('task-detail-modal');
    modal.style.display = 'flex';
}

function buildReclassifyForm(task) {
    var dims = task.scrape_dimensions || {};
    var pathRules = currentConfig.path_rules || [];
    var allDimKeys = new Set();
    pathRules.forEach(function(rule) {
        if (rule.conditions) {
            Object.keys(rule.conditions).forEach(function(k) { allDimKeys.add(k); });
        }
    });
    if (Object.keys(dims).length > 0) {
        Object.keys(dims).forEach(function(k) { allDimKeys.add(k); });
    }

    if (allDimKeys.size === 0) return '';

    var html = '<div class="detail-field"><div class="detail-field-label">修改分类维度</div><div class="detail-dim-grid" id="reclassify-dim-grid">';
    allDimKeys.forEach(function(key) {
        var currentVal = dims[key] || '';
        html += '<div class="detail-dim-item">' +
            '<span class="detail-dim-key">' + escapeHtml(key) + '</span>' +
            '<input type="text" class="detail-dim-select" id="reclassify-dim-' + escapeHtml(key) + '" value="' + escapeHtml(String(currentVal)) + '">' +
        '</div>';
    });
    html += '</div>' +
        '<button class="btn btn-sm btn-primary" style="margin-top:8px" onclick="submitReclassify(\'' + escapeHtml(task.task_id) + '\')">应用修改</button>' +
        '</div>';
    return html;
}

async function submitReclassify(taskId) {
    var grid = document.getElementById('reclassify-dim-grid');
    if (!grid) return;
    var inputs = grid.querySelectorAll('input');
    var dims = {};
    inputs.forEach(function(inp) {
        var key = inp.id.replace('reclassify-dim-', '');
        var val = inp.value.trim();
        if (val) dims[key] = val;
    });
    await reclassifyTask(taskId, dims);
}

// ==================== 字幕弹窗 ====================

async function showSubtitleDetail(taskId) {
    var result = await apiRequest('GET', '/tasks/' + encodeURIComponent(taskId) + '/subtitles');
    if (result.code !== 200 || !result.data) {
        showToast('获取字幕信息失败', 'error');
        return;
    }
    var subtitles = result.data.subtitles || [];
    var body = document.getElementById('subtitle-detail-body');

    if (subtitles.length === 0) {
        body.innerHTML = '<div class="empty-state"><div class="empty-state-text">无字幕记录</div></div>';
    } else {
        var html = '<table class="subtitle-table"><thead><tr>' +
            '<th>文件名</th><th>语言</th><th>状态</th><th>入库路径</th>' +
        '</tr></thead><tbody>';
        subtitles.forEach(function(sub) {
            html += '<tr>' +
                '<td>' + escapeHtml(sub.source_filename || '-') + '</td>' +
                '<td>' + escapeHtml(sub.lang || '-') + '</td>' +
                '<td><span class="status-badge status-badge-' + (sub.status || 'PENDING') + '">' + getStatusText(sub.status) + '</span></td>' +
                '<td class="task-import-path">' + (sub.import_path ? escapeHtml(truncate(sub.import_path, 30)) : '-') + '</td>' +
            '</tr>';
        });
        html += '</tbody></table>';
        body.innerHTML = html;
    }

    var modal = document.getElementById('subtitle-detail-modal');
    modal.style.display = 'flex';
}

// ==================== 弹窗控制 ====================

function closeModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) modal.style.display = 'none';
}

// 点击遮罩层关闭弹窗
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.style.display = 'none';
    }
});

// ==================== 状态筛选页签点击 ====================

document.addEventListener('click', function(e) {
    var tab = e.target.closest('.status-filter-tab');
    if (tab) {
        var tabs = document.querySelectorAll('.status-filter-tab');
        tabs.forEach(function(t) { t.classList.remove('active'); });
        tab.classList.add('active');
        var status = tab.getAttribute('data-status') || 'all';
        _currentTaskPage = 1;
        loadTasks(1, status);
    }
});

// ==================== 日志 ====================

async function refreshLogs() {
    var result = await apiRequest('GET', '/logs?limit=100');
    if (result.code === 200 && result.data) {
        var logs = result.data.logs || [];
        var container = document.getElementById('log-container');
        if (logs.length === 0) {
            container.innerHTML = '<div class="log-line">暂无日志</div>';
            return;
        }
        container.innerHTML = logs.map(function(log) {
            var timestamp = (log.time || '-').substring(11, 19);
            var level = log.level || 'INFO';
            var message = log.message || log.raw || JSON.stringify(log);
            var step = log.step || '';
            var taskId = log.task_id || '';
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
    if (text == null) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(String(text)));
    return div.innerHTML;
}

// ==================== 路径规则动态 UI ====================

function renderPathRules(rules) {
    const container = document.getElementById('path-rules-container');
    if (!container) return;
    if (!Array.isArray(rules)) rules = [];

    container.innerHTML = rules.map((rule, index) => createRuleCardHTML(rule, index, rules.length)).join('');

    if (rules.length === 1) {
        var firstCard = container.querySelector('.rule-card');
        if (firstCard) firstCard.classList.add('expanded');
    }

    bindPathRuleDrag();
}

function buildRuleSummary(rule) {
    var conditions = rule.conditions || {};
    var tagsHTML = '';
    var hasTag = false;
    for (var d = 0; d < FIXED_DIMENSIONS.length; d++) {
        var dim = FIXED_DIMENSIONS[d];
        var value = conditions[dim.name];
        if (value === undefined || value === null || value === '') continue;
        var displayValue;
        if (dim.type === 'multi-select') {
            displayValue = String(value).split('|').map(function(s) { return s.trim(); }).filter(Boolean).join(' / ');
            if (!displayValue) continue;
        } else {
            displayValue = String(value);
        }
        tagsHTML += '<span class="rule-summary-tag">' +
            '<span class="rule-summary-tag-key">' + escapeHtml(dim.label) + '</span>' +
            '<span class="rule-summary-tag-val">' + escapeHtml(displayValue) + '</span>' +
            '</span>';
        hasTag = true;
    }
    if (!hasTag) {
        tagsHTML = '<span class="rule-summary-tag rule-summary-tag-empty">无条件</span>';
    }

    var tpl = rule.template || '';
    var pathHTML;
    if (!tpl) {
        pathHTML = '<span class="rule-summary-path-empty">(未设置)</span>';
    } else {
        pathHTML = tpl.replace(/(\{[^}]+\})|([^{]+)/g, function(_, varToken, textToken) {
            if (varToken) {
                return '<span class="rule-summary-path-var">' + escapeHtml(varToken) + '</span>';
            }
            return '<span class="rule-summary-path-text">' + escapeHtml(textToken) + '</span>';
        });
    }

    return '<span class="rule-summary-tags">' + tagsHTML + '</span>' +
        '<span class="rule-summary-arrow">→</span>' +
        '<span class="rule-summary-path">' + pathHTML + '</span>';
}

function createRuleCardHTML(rule, index, total) {
    var conditions = rule.conditions || {};
    var summary = buildRuleSummary(rule);

    var conditionsHTML = '';
    for (var d = 0; d < FIXED_DIMENSIONS.length; d++) {
        var dim = FIXED_DIMENSIONS[d];
        var value = conditions[dim.name];
        if (dim.type === 'select') {
            conditionsHTML += '<div class="rule-condition-item">' +
                '<label class="rule-condition-label">' + dim.label + '</label>' +
                '<select class="rule-condition-select" data-dim="' + dim.name + '">' +
                dim.options.map(function(opt) {
                    return '<option value="' + opt + '" ' + (value === opt ? 'selected' : '') + '>' + (opt || '(不限制)') + '</option>';
                }).join('') +
                '</select></div>';
        } else if (dim.type === 'multi-select') {
            var selectedValues = typeof value === 'string' ? value.split('|').map(function(s) { return s.trim(); }).filter(Boolean) : [];
            conditionsHTML += '<div class="rule-condition-item">' +
                '<label class="rule-condition-label">' + dim.label + '（可多选）</label>' +
                '<div class="rule-condition-checkbox-group" data-dim="' + dim.name + '">' +
                dim.options.map(function(opt) {
                    return '<label class="rule-condition-checkbox-label">' +
                        '<input type="checkbox" value="' + opt + '" ' + (selectedValues.indexOf(opt) >= 0 ? 'checked' : '') + ' data-option="' + opt + '">' + opt +
                        '</label>';
                }).join('') +
                '</div></div>';
        }
    }

    return '<div class="rule-card" data-index="' + index + '" draggable="true">' +
        '<div class="rule-card-bar" onclick="toggleRuleCard(this.parentElement)">' +
            '<span class="rule-card-drag-handle" title="拖动调整匹配优先顺序" onclick="event.stopPropagation();">' +
                '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.4"/><circle cx="15" cy="6" r="1.4"/><circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/><circle cx="9" cy="18" r="1.4"/><circle cx="15" cy="18" r="1.4"/></svg>' +
            '</span>' +
            '<span class="rule-card-badge">#' + (index + 1) + '</span>' +
            '<span class="rule-card-summary">' + summary + '</span>' +
            '<div class="rule-card-actions">' +
                '<button class="rule-card-chevron" title="展开/折叠">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>' +
                '</button>' +
                '<button title="删除" class="rule-btn-delete" onclick="event.stopPropagation();deletePathRule(' + index + ')">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
                '</button>' +
            '</div>' +
        '</div>' +
        '<div class="rule-card-body">' +
            '<div class="rule-card-body-inner">' +
                '<div class="rule-conditions">' + conditionsHTML + '</div>' +
                '<div class="rule-template-row">' +
                    '<label class="rule-condition-label">入库路径模板</label>' +
                    '<input type="text" class="rule-template-input" placeholder="/vol1/影视/电影/{year}/{title_cn}/" value="' + (rule.template || '') + '">' +
                '</div>' +
            '</div>' +
        '</div>' +
    '</div>';
}

function toggleRuleCard(card) {
    if (!card) return;
    card.classList.toggle('expanded');
}

function collectPathRulesFromDOM() {
    const container = document.getElementById('path-rules-container');
    if (!container) return [];
    const cards = container.querySelectorAll('.rule-card');
    const rules = [];

    for (const card of cards) {
        const conditions = {};
        for (const dim of FIXED_DIMENSIONS) {
            if (dim.type === 'select') {
                const select = card.querySelector(`[data-dim="${dim.name}"]`);
                const value = select ? select.value : '';
                if (value) {
                    conditions[dim.name] = value;
                }
            } else if (dim.type === 'multi-select') {
                const group = card.querySelector(`[data-dim="${dim.name}"]`);
                if (group) {
                    const checked = Array.from(group.querySelectorAll('input[type="checkbox"]:checked')).map(cb => cb.value);
                    if (checked.length > 0) {
                        conditions[dim.name] = checked.join('|');
                    }
                }
            }
        }
        const template = card.querySelector('.rule-template-input');
        rules.push({
            conditions: conditions,
            template: template ? template.value : ''
        });
    }

    return rules;
}

function addPathRule() {
    var currentRules = collectPathRulesFromDOM();
    currentRules.push({ conditions: {}, template: '' });
    renderPathRules(currentRules);
    var cards = document.querySelectorAll('#path-rules-container .rule-card');
    if (cards.length > 0) {
        cards[cards.length - 1].classList.add('expanded');
    }
}

function deletePathRule(index) {
    const currentRules = collectPathRulesFromDOM();
    currentRules.splice(index, 1);
    renderPathRules(currentRules);
}

function movePathRuleUp(index) {
    if (index <= 0) return;
    const currentRules = collectPathRulesFromDOM();
    const temp = currentRules[index];
    currentRules[index] = currentRules[index - 1];
    currentRules[index - 1] = temp;
    renderPathRules(currentRules);
}

function movePathRuleDown(index) {
    const currentRules = collectPathRulesFromDOM();
    if (index >= currentRules.length - 1) return;
    const temp = currentRules[index];
    currentRules[index] = currentRules[index + 1];
    currentRules[index + 1] = temp;
    renderPathRules(currentRules);
}

// ==================== 路径规则拖拽排序 ====================

var _draggingRuleCard = null;

function bindPathRuleDrag() {
    var container = document.getElementById('path-rules-container');
    if (!container) return;
    var cards = container.querySelectorAll('.rule-card');
    cards.forEach(function(card) {
        card.addEventListener('dragstart', onRuleDragStart);
        card.addEventListener('dragend', onRuleDragEnd);
        card.addEventListener('dragover', onRuleDragOver);
        card.addEventListener('dragleave', onRuleDragLeave);
        card.addEventListener('drop', onRuleDrop);
    });
}

function onRuleDragStart(e) {
    _draggingRuleCard = this;
    this.classList.add('rule-card-dragging');
    if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = 'move';
        try { e.dataTransfer.setData('text/plain', this.getAttribute('data-index') || ''); } catch (err) {}
    }
}

function onRuleDragEnd() {
    this.classList.remove('rule-card-dragging');
    var container = document.getElementById('path-rules-container');
    if (container) {
        container.querySelectorAll('.rule-card-drop-before, .rule-card-drop-after').forEach(function(el) {
            el.classList.remove('rule-card-drop-before', 'rule-card-drop-after');
        });
    }
    _draggingRuleCard = null;
}

function onRuleDragOver(e) {
    if (!_draggingRuleCard || _draggingRuleCard === this) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    var rect = this.getBoundingClientRect();
    var isAfter = (e.clientY - rect.top) > rect.height / 2;
    this.classList.toggle('rule-card-drop-before', !isAfter);
    this.classList.toggle('rule-card-drop-after', isAfter);
}

function onRuleDragLeave() {
    this.classList.remove('rule-card-drop-before', 'rule-card-drop-after');
}

function onRuleDrop(e) {
    if (!_draggingRuleCard || _draggingRuleCard === this) return;
    e.preventDefault();
    e.stopPropagation();
    var rect = this.getBoundingClientRect();
    var isAfter = (e.clientY - rect.top) > rect.height / 2;

    var currentRules = collectPathRulesFromDOM();
    var fromIndex = parseInt(_draggingRuleCard.getAttribute('data-index'), 10);
    var toIndex = parseInt(this.getAttribute('data-index'), 10);
    if (isNaN(fromIndex) || isNaN(toIndex)) return;

    var moved = currentRules.splice(fromIndex, 1)[0];
    var insertIndex = toIndex;
    if (fromIndex < toIndex) insertIndex -= 1;
    if (isAfter) insertIndex += 1;
    if (insertIndex < 0) insertIndex = 0;
    if (insertIndex > currentRules.length) insertIndex = currentRules.length;
    currentRules.splice(insertIndex, 0, moved);

    this.classList.remove('rule-card-drop-before', 'rule-card-drop-after');
    renderPathRules(currentRules);
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
    applyConfigSubTab(_currentConfigSubTab);
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

// ==================== 提示词编辑 ====================

function togglePromptSection() {
    var panel = document.getElementById('prompt-panel');
    var toggleBtn = document.getElementById('btn-toggle-prompts');
    var arrow = document.getElementById('prompt-collapse-arrow');
    
    if (!panel) return;
    
    var isHidden = panel.style.display === 'none' || panel.style.display === '';
    
    if (isHidden) {
        panel.style.display = 'block';
        toggleBtn.classList.add('expanded');
        arrow.textContent = '▼';
    } else {
        panel.style.display = 'none';
        toggleBtn.classList.remove('expanded');
        arrow.textContent = '▶';
    }
}

async function savePrompts() {
    var systemPrompt = document.getElementById('prompt-system').value;
    
    var result = await apiRequest('POST', '/api/config/prompts', {
        system_prompt: systemPrompt
    });
    
    if (result.code === 200) {
        showToast(result.message || '提示词已保存，重启服务后生效', 'success');
    } else {
        showToast(result.message || '保存失败', 'error');
    }
}

async function resetPrompts() {
    if (!confirm('确定要恢复出厂默认提示词吗？当前修改将丢失。')) {
        return;
    }
    
    var result = await apiRequest('POST', '/api/config/prompts/reset');
    
    if (result.code === 200) {
        showToast(result.message || '已恢复出厂默认提示词，重启服务后生效', 'success');
        var prompts = await apiRequest('GET', '/api/config/prompts');
        if (prompts.code === 200 && prompts.data) {
            document.getElementById('prompt-system').value = prompts.data.system_prompt || '';
        }
    } else {
        showToast(result.message || '恢复失败', 'error');
    }
}

function previewFullPrompt() {
    var userPrompt = document.getElementById('prompt-system').value;
    
    var dimensionList = [
        '1. 影视类型（media_type）: [movie, tv]',
        '2. 是否纪录片（documentary）: [true, false]',
        '3. 是否动漫（animation）: [true, false]',
        '4. 限制级分类（restricted_level）: [0-6, 7-12, 13-15, 17+]'
    ];
    
    var fullPart = '\n\n【维度判断】\n当前需要判断的维度：\n' + 
        dimensionList.join('\n') + '\n\n请严格按以下JSON格式返回，不要添加任何解释文字：\n';
    
    var movieSchema = JSON.stringify({
        "title_cn": "string|null",
        "title_en": "string|null",
        "year": "int|null",
        "resolution": "string|null",
        "quality": "string|null",
        "language": "string|null",
        "type": "movie|tv",
        "season": "int|null",
        "episode": "int|null",
        "dimensions": {
            "media_type": "movie|tv|null",
            "documentary": "true|false|null",
            "animation": "true|false|null",
            "restricted_level": "0-6|7-12|13-15|17+|null"
        },
        "confidence": "float"
    }, null, 2);
    
    var tvSchema = JSON.stringify({
        "title_cn": "string|null",
        "title_en": "string|null",
        "year": "int|null",
        "type": "tv",
        "dimensions": {
            "media_type": "movie|tv|null",
            "documentary": "true|false|null",
            "animation": "true|false|null",
            "restricted_level": "0-6|7-12|13-15|17+|null"
        },
        "confidence": "float"
    }, null, 2);
    
    var fullMovie = userPrompt + fullPart + movieSchema;
    var fullTV = userPrompt + fullPart + tvSchema;
    
    var overlay = document.createElement('div');
    overlay.className = 'prompt-preview-overlay';
    overlay.innerHTML = '<div class="prompt-preview-dialog">' +
        '<div class="prompt-preview-header">' +
        '<span class="prompt-preview-title">完整提示词预览</span>' +
        '<button class="prompt-preview-close" onclick="this.closest(\'.prompt-preview-overlay\').remove()">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
        '</button>' +
        '</div>' +
        '<div class="prompt-preview-body">' +
        '<h4 style="color:var(--primary-color);margin:0 0 8px 0;">▶ 单视频刮削（movie/tv 均适用）</h4>' +
        '<pre class="prompt-preview-content" style="margin-bottom:16px;">' + escapeHtml(fullMovie) + '</pre>' +
        '<h4 style="color:var(--primary-color);margin:0 0 8px 0;">▶ 电视剧系列刮削</h4>' +
        '<pre class="prompt-preview-content">' + escapeHtml(fullTV) + '</pre>' +
        '</div>' +
        '</div>';
    
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            overlay.remove();
        }
    });
    
    document.body.appendChild(overlay);
}
var refreshInterval = null;

function switchToTaskFilter(status) {
    var taskTab = document.getElementById('tab-tasks');
    if (taskTab) taskTab.click();
    _currentTaskPage = 1;
    _currentTaskStatus = status;
    var tabs = document.querySelectorAll('.status-filter-tab');
    tabs.forEach(function(t) { t.classList.remove('active'); });
    var targetTab = document.querySelector('.status-filter-tab[data-status="' + status + '"]');
    if (targetTab) {
        targetTab.classList.add('active');
    } else {
        var allTab = document.querySelector('.status-filter-tab[data-status="all"]');
        if (allTab) allTab.classList.add('active');
    }
    setTimeout(function() { loadTasks(1, status); }, 100);
}

function toggleFlowDiagram() {
    var container = document.getElementById('flow-diagram-container');
    var toggle = document.getElementById('flow-toggle');
    if (container.style.display === 'none') {
        container.style.display = 'block';
        if (toggle) toggle.textContent = '▼';
    } else {
        container.style.display = 'none';
        if (toggle) toggle.textContent = '▶';
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

function showConfirm(title, message, onOk) {
    var modal = document.getElementById('generic-confirm-modal');
    var titleEl = document.getElementById('generic-confirm-title');
    var msgEl = document.getElementById('generic-confirm-message');
    var okBtn = document.getElementById('generic-confirm-ok');
    if (!modal || !titleEl || !msgEl || !okBtn) return;
    titleEl.textContent = title || '确认操作';
    msgEl.textContent = message || '';
    var newOk = okBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newOk, okBtn);
    newOk.id = 'generic-confirm-ok';
    newOk.addEventListener('click', function() {
        closeModal('generic-confirm-modal');
        if (typeof onOk === 'function') onOk();
    });
    modal.style.display = 'flex';
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

function startAutoRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(function() {
        loadHealth();
        loadMetrics();
        refreshLogs();
    }, 5000);
}

document.addEventListener('DOMContentLoaded', function() {
    checkApiKeyRequired();
    loadHealth();
    loadMetrics();
    loadConfig();
    refreshLogs();
    startAutoRefresh();
    bindPathPermissionAutoTest();
    applyConfigSubTab(_currentConfigSubTab);
});

window.addEventListener('beforeunload', () => {
    if (refreshInterval) clearInterval(refreshInterval);
});

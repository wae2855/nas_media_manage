var _currentTaskPage = 1;
var _currentTaskStatus = 'all';
var _currentTaskTotalPages = 1;

var _taskDimensionConfig = {};

async function loadTaskDimensionConfig() {
    try {
        var result = await apiRequest('GET', '/dimensions/enabled');
        if (result.code === 200 && result.data) {
            var dims = result.data.dimensions || [];
            _taskDimensionConfig = {};
            dims.forEach(function(d) {
                var valMap = {};
                (d.value_list || []).forEach(function(v) {
                    valMap[v.value] = v.label;
                });
                _taskDimensionConfig[d.name] = {
                    label: d.label,
                    valueLabels: valMap,
                    color: d.color || '#6c757d'
                };
            });
        }
    } catch (e) {}
}

function _getDimLabel(key) {
    return (_taskDimensionConfig[key] && _taskDimensionConfig[key].label) || key;
}

function _getDimValueLabel(key, value) {
    if (_taskDimensionConfig[key] && _taskDimensionConfig[key].valueLabels) {
        return _taskDimensionConfig[key].valueLabels[value] || value;
    }
    return value;
}

function _getDimColor(key) {
    return (_taskDimensionConfig[key] && _taskDimensionConfig[key].color) || '#6c757d';
}

var FILE_LOCATION_LABELS = {
    'source': '源目录',
    'temp': '中转目录',
    'import': '已入库',
    'recycle': '回收站',
    'deleted': '已删除'
};

var STATUS_GROUPS = {
    'queued': { status: 'PENDING', stage: 'QUEUED' },
    'running': { status: 'PENDING', stage: 'RUNNING' },
    'review': { status: 'PENDING', stage: 'AWAIT_REVIEW' },
    'failed': { status: 'FAILED' },
    'completed': { statuses: ['SUCCESS', 'SKIPPED'] }
};

async function loadTasks(page, status) {
    if (page !== undefined) _currentTaskPage = page;
    if (status !== undefined) _currentTaskStatus = status;
    var pageNum = _currentTaskPage || 1;

    if (Object.keys(_taskDimensionConfig).length === 0) {
        await loadTaskDimensionConfig();
    }
    var statusFilter = _currentTaskStatus || 'all';

    var groupConfig = STATUS_GROUPS[statusFilter];
    if (groupConfig) {
        var allTasks = [];
        var totalCount = 0;
        var totalPages = 1;

        if (groupConfig.statuses) {
            for (var gi = 0; gi < groupConfig.statuses.length; gi++) {
                var url = '/tasks?page=' + pageNum + '&limit=20&status=' + encodeURIComponent(groupConfig.statuses[gi]);
                var result = await apiRequest('GET', url);
                if (result.code === 200 && result.data) {
                    allTasks = allTasks.concat(result.data.tasks || []);
                    totalCount += result.data.total || 0;
                    totalPages = Math.max(totalPages, result.data.total_pages || 1);
                }
            }
        } else {
            var url = '/tasks?page=' + pageNum + '&limit=20';
            if (groupConfig.status) {
                url += '&status=' + encodeURIComponent(groupConfig.status);
            }
            if (groupConfig.stage) {
                url += '&stage=' + encodeURIComponent(groupConfig.stage);
            }
            var result = await apiRequest('GET', url);
            if (result.code === 200 && result.data) {
                allTasks = result.data.tasks || [];
                totalCount = result.data.total || 0;
                totalPages = result.data.total_pages || 1;
            }
        }
        allTasks.sort(function(a, b) {
            var ta = a.created_at || '';
            var tb = b.created_at || '';
            return ta > tb ? -1 : ta < tb ? 1 : 0;
        });
        _currentTaskTotalPages = totalPages;
        if (allTasks.length > 0) {
            console.log('[loadTasks] 第1条数据字段:', Object.keys(allTasks[0]).join(', '));
        }
        renderTaskTable(allTasks);
        renderPagination(totalPages, pageNum, totalCount);
    } else {
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
            if (tasks.length > 0) {
                console.log('[loadTasks] 第1条数据字段:', Object.keys(tasks[0]).join(', '));
                console.log('[loadTasks] 第1条 source_filename:', tasks[0].source_filename, 'source_path:', tasks[0].source_path);
            }
            renderTaskTable(tasks);
            renderPagination(totalPages, pageNum, total);
        } else {
            var tbody = document.getElementById('tasks-table-body');
            tbody.innerHTML = '<tr><td colspan="6" class="empty-row">加载失败: ' + (result.message || '未知错误') + '</td></tr>';
        }
    }
}

function renderTaskTable(tasks) {
    var tbody = document.getElementById('tasks-table-body');
    if (!tasks || tasks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-row"><div class="empty-state-container"><div class="empty-state-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div><div class="empty-state-title">暂无任务记录</div><div class="empty-state-desc">将视频文件放入源目录后，点击"立即扫描"即可开始处理</div><div class="empty-state-actions"><button class="btn btn-primary btn-sm" onclick="switchTab(\'overview\')">前往首页</button><button class="btn btn-secondary btn-sm" onclick="switchTab(\'config\')">配置源目录</button></div></div></td></tr>';
        return;
    }

    var pageNum = _currentTaskPage || 1;
    var pageSize = 20;
    var startIndex = (pageNum - 1) * pageSize;

    tbody.innerHTML = tasks.map(function(task, idx) {
        var tid = task.task_id || '';
        var filename = task.source_filename || (task.source_path ? task.source_path.split('/').pop().split('\\').pop() : '') || '-';
        var status = task.status || 'PENDING';
        var importPath = task.import_path || '';
        var locationPath = buildLocationCell(task, importPath);
        var subtitleInfo = buildSubtitleCell(task);
        var scrapeInfo = buildScrapeCell(task);
        var actionsHtml = buildActionButtons(task);
        var rowNum = startIndex + idx + 1;
        var completedTime = buildCompletedTime(task);

        return '<tr class="fade-in">' +
            '<td class="task-row-num">' + rowNum + '</td>' +
            '<td><div class="task-row-main">' +
                '<div class="task-row-title">' +
                    '<span class="task-filename" onclick="showTaskDetail(\'' + tid + '\')" data-tooltip="点击查看详情">' + escapeHtml(filename) + '</span>' +
                '</div>' +
                '<div class="task-row-sub">' + scrapeInfo + '</div>' +
            '</div></td>' +
            '<td class="task-subtitle-cell">' + subtitleInfo + '</td>' +
            '<td><span class="status-badge status-badge-' + status + '">' + getStatusText(status) + '</span></td>' +
            '<td>' + locationPath + '</td>' +
            '<td class="task-time-cell">' + completedTime + '</td>' +
            '<td><div class="task-actions">' + actionsHtml + '</div></td>' +
        '</tr>';
    }).join('');
}

function buildLocationCell(task, importPath) {
    var fileLocation = task.file_location || 'source';
    var locationLabel = FILE_LOCATION_LABELS[fileLocation] || fileLocation;
    var locationPath = '';

    if (fileLocation === 'import') {
        locationPath = task.import_video_path || importPath || '';
    } else if (fileLocation === 'temp') {
        locationPath = task.video_path || '';
    } else if (fileLocation === 'recycle') {
        locationPath = task.source_path || '';
    } else if (fileLocation === 'source') {
        locationPath = task.source_path || '';
    }

    if (locationPath) {
        return '<span class="task-import-path" data-tooltip="' + escapeHtml(locationPath) + '">' +
            '<span class="location-tag location-tag-' + fileLocation + '">' + locationLabel + '</span> ' +
            escapeHtml(truncate(locationPath, 24)) + '</span>';
    }
    return '<span class="task-import-path"><span class="location-tag location-tag-' + fileLocation + '">' + locationLabel + '</span></span>';
}

function buildCompletedTime(task) {
    if (task.completed_at) {
        return task.completed_at.substring(5, 16).replace('T', ' ');
    }
    if (task.status === 'PROCESSING') {
        return '<span class="processing-indicator">处理中...</span>';
    }
    if (task.status === 'PENDING') {
        return '-';
    }
    if (!task.started_at) {
        return '-';
    }
    var start = task.started_at.substring(5, 16).replace('T', ' ');
    return start + ' ...';
}

function buildScrapeCell(task) {
    var parts = [];
    var titleCn = task.scrape_title_cn || '';
    var titleEn = task.scrape_title_en || '';
    var mediaType = task.scrape_media_type || '';
    var year = task.scrape_year || '';

    if (task.file_size_mb != null && task.file_size_mb > 0) {
        var sizeStr = task.file_size_mb >= 1024 ? (task.file_size_mb / 1024).toFixed(1) + 'GB' : task.file_size_mb >= 1 ? task.file_size_mb.toFixed(0) + 'MB' : (task.file_size_mb * 1024).toFixed(0) + 'KB';
        parts.push('<span class="task-size-chip">' + sizeStr + '</span>');
    }

    if (titleCn || titleEn) {
        var title = titleCn || titleEn;
        parts.push('<span class="task-scrape-chip' + (mediaType === 'movie' ? ' type-movie' : mediaType === 'tv' ? ' type-tv' : '') + '">' +
            escapeHtml(title) + (year ? ' (' + year + ')' : '') +
        '</span>');
    }

    if (mediaType) {
        parts.push('<span>' + (mediaType === 'movie' ? '电影' : mediaType === 'tv' ? '剧集' : mediaType) + '</span>');
    }

    if (task.scrape_season && task.scrape_season !== 'null' && task.scrape_season !== 'None') {
        parts.push('<span>S' + String(task.scrape_season).padStart(2, '0') + '</span>');
    }
    if (task.scrape_episode && task.scrape_episode !== 'null' && task.scrape_episode !== 'None') {
        parts.push('<span>E' + String(task.scrape_episode).padStart(2, '0') + '</span>');
    }

    var matchLevel = task.match_level || task.scrape_match_level || '';
    if (matchLevel === 'AUTO_PASS') {
        parts.push('<span class="match-tag match-auto">自动匹配</span>');
    } else if (matchLevel === 'CONTEXT_PASS') {
        parts.push('<span class="match-tag match-context">AI辅助匹配</span>');
    } else if (matchLevel === 'NEEDS_CONFIRM') {
        parts.push('<span class="match-tag match-confirm">需确认</span>');
    } else if (task.scrape_confidence != null && task.scrape_confidence !== '') {
        var conf = Number(task.scrape_confidence);
        var confClass = conf >= 0.8 ? 'conf-high' : conf >= 0.5 ? 'conf-mid' : 'conf-low';
        parts.push('<span class="' + confClass + '">' + conf.toFixed(2) + '</span>');
    }

    if (task.skip_reason) {
        parts.push('<span style="color:var(--text-muted)">' + escapeHtml(truncate(task.skip_reason, 20)) + '</span>');
    } else if (task.error_message) {
        parts.push('<span style="color:var(--danger-color)">' + escapeHtml(truncate(task.error_message, 20)) + '</span>');
    }

    return parts.length > 0 ? parts.join(' ') : '<span style="color:var(--text-muted)">等待处理...</span>';
}

function buildSubtitleCell(task) {
    var total = task.subtitle_total || 0;
    var success = task.subtitle_success || 0;
    if (total === 0) {
        return '<span class="task-subtitle-count">无</span>';
    }
    var label = '字幕 x' + total;
    if (success > 0 && success < total) {
        label += ' (' + success + '/' + total + ' 成功)';
    } else if (success === total) {
        label += ' ✓';
    }
    return '<span class="task-subtitle-count has-subs" onclick="showSubtitleDetail(\'' + task.task_id + '\')">' +
        label +
    '</span>';
}

function buildActionButtons(task) {
    var tid = task.task_id || '';
    var status = task.status || '';
    var btns = [];

    btns.push('<button class="task-action-btn" onclick="showTaskDetail(\'' + escapeHtml(tid) + '\')" data-tooltip="查看详情">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M22 12c0 5.52-4.48 10-10 10S2 17.52 2 12 6.48 2 12 2s10 4.48 10 10z"/></svg>' +
    '</button>');

    if (status === 'CONFIRMING') {
        btns.push('<button class="task-action-btn confirm" onclick="confirmTask(\'' + escapeHtml(tid) + '\')" data-tooltip="确认入库">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>' +
        '</button>');
        btns.push('<button class="task-action-btn reclassify" onclick="showTaskDetail(\'' + escapeHtml(tid) + '\')" data-tooltip="修改分类">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0-3-3m3 3 3-3M5 21h14"/></svg>' +
        '</button>');
        btns.push('<button class="task-action-btn ignore" onclick="ignoreTask(\'' + escapeHtml(tid) + '\')" data-tooltip="忽略">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>' +
        '</button>');
    }

    if (status === 'FAILED') {
        btns.push('<button class="task-action-btn retry" onclick="retryTask(\'' + escapeHtml(tid) + '\')" data-tooltip="重试">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>' +
        '</button>');
        btns.push('<button class="task-action-btn ignore" onclick="ignoreTask(\'' + escapeHtml(tid) + '\')" data-tooltip="忽略">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>' +
        '</button>');
    }

    if (status === 'SKIPPED') {
        btns.push('<button class="task-action-btn retry" onclick="retryTask(\'' + escapeHtml(tid) + '\')" data-tooltip="重试">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>' +
        '</button>');
    }

    if (status !== 'PROCESSING') {
        btns.push('<button class="task-action-btn delete" onclick="showDeleteConfirm(\'' + escapeHtml(tid) + '\',\'' + escapeHtml(task.source_filename || '') + '\',\'' + escapeHtml(task.file_location || 'source') + '\')" data-tooltip="移入回收站">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
        '</button>');
    }

    return btns.join('');
}

function renderPagination(totalPages, currentPage, total) {
    var container = document.getElementById('pagination-controls');
    if (!container) return;

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
        'SUCCESS': '完成',
        'FAILED': '失败',
        'PROCESSING': '处理中',
        'PENDING': '待处理',
        'SKIPPED': '完成 · 跳过',
        'CONFIRMING': '处理中 · 需确认'
    };
    return map[status] || status || '未知';
}

function truncate(text, length) {
    if (!text) return '';
    return text.length > length ? text.substring(0, length) + '...' : text;
}

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

async function showTaskDetail(taskId) {
    var result = await apiRequest('GET', '/tasks/' + encodeURIComponent(taskId));
    if (result.code !== 200 || !result.data || !result.data.task) {
        showToast('获取任务详情失败', 'error');
        return;
    }
    var task = result.data.task;
    var body = document.getElementById('task-detail-body');
    var footer = document.getElementById('task-detail-footer');

    var status = task.status || 'PENDING';
    var scrapeResult = task.scrape_result || {};
    var titleCn = scrapeResult.title_cn || '';
    var titleEn = scrapeResult.title_en || '';
    var year = scrapeResult.year || '';
    var filename = task.source_filename || (task.source_path ? task.source_path.split('/').pop().split('\\').pop() : '') || '-';

    // ===== Header 区 =====
    var headerIcon = document.getElementById('detail-header-icon');
    var headerTitle = document.getElementById('detail-header-title');
    var headerSub = document.getElementById('detail-header-sub');

    // Icon: use scrape type or file extension
    var headerIconHtml = '';
    var scrapeType = scrapeResult.type || '';
    if (scrapeType === 'tv') {
        headerIconHtml = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><polyline points="8 21 12 17 16 21"/></svg>';
        headerIcon.style.background = 'rgba(139,92,246,0.15)';
        headerIcon.style.color = '#A78BFA';
    } else if (scrapeType === 'movie') {
        headerIconHtml = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="20" height="20" rx="2.18"/><polygon points="10 7 10 17 17 12 10 7"/></svg>';
        headerIcon.style.background = 'rgba(59,130,246,0.15)';
        headerIcon.style.color = '#93C5FD';
    } else {
        headerIconHtml = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>';
        headerIcon.style.background = 'rgba(100,116,139,0.15)';
        headerIcon.style.color = '#94A3B8';
    }
    headerIcon.innerHTML = headerIconHtml;

    var headerTitleText = titleCn || titleEn || filename;
    headerTitle.textContent = headerTitleText;
    headerTitle.title = headerTitleText;

    var headerSubParts = [];
    if (titleEn && titleEn !== headerTitleText) {
        headerSubParts.push(escapeHtml(titleEn));
    }
    headerSubParts.push(filename !== headerTitleText ? escapeHtml(filename) : '');
    headerSubParts.push('<span class="status-badge status-badge-' + status + '">' + getStatusText(status) + '</span>');
    headerSub.innerHTML = headerSubParts.filter(Boolean).join(' · ');

    // ===== Body 区 =====
    var sections = [];

    // Section: 基本信息
    var basicFields = [];
    basicFields.push(['任务ID', '<span class="detail-mono"><span class="detail-tid-text">' + escapeHtml(task.task_id || '-') + '</span><button class="detail-copy-btn" onclick="copyTaskId(this)" data-tid="' + escapeHtml(task.task_id || '') + '"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button></span>']);
    basicFields.push(['文件大小', task.file_size_mb != null && task.file_size_mb > 0 ? (task.file_size_mb >= 1024 ? (task.file_size_mb / 1024).toFixed(2) + ' GB' : task.file_size_mb >= 1 ? task.file_size_mb.toFixed(2) + ' MB' : (task.file_size_mb * 1024).toFixed(1) + ' KB') : (task.file_size_mb === 0 ? '0 KB' : '-')]);

    var fileLocation = task.file_location || 'source';
    var locationLabel = FILE_LOCATION_LABELS[fileLocation] || fileLocation;
    var currentPath = '';
    if (fileLocation === 'import') {
        currentPath = task.import_video_path || '';
    } else if (fileLocation === 'temp') {
        currentPath = task.video_path || '';
    } else {
        currentPath = task.source_path || '';
    }
    basicFields.push(['当前文件位置', '<span class="detail-location-tag detail-location-' + fileLocation + '">' + locationLabel + '</span>']);

    var canRename = fileLocation !== 'deleted' && currentPath;
    var filenameValue = '<span class="detail-filename-row" id="detail-filename-row">' +
        '<span class="detail-filename-text" id="detail-current-filename">' + escapeHtml(task.source_filename || '-') + '</span>';
    if (canRename) {
        filenameValue += '<button class="detail-rename-btn" onclick="startRename(\'' + escapeHtml(task.task_id || '') + '\')" data-tooltip="修改文件名">' +
            '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>' +
        '</button>';
    }
    filenameValue += '</span>';
    basicFields.push(['文件名', filenameValue]);

    basicFields.push(['源路径', '<span class="detail-mono">' + escapeHtml(task.source_path || '-') + '</span>']);
    if (fileLocation === 'temp' && task.video_path) {
        basicFields.push(['中转路径', '<span class="detail-mono">' + escapeHtml(task.video_path) + '</span>']);
    }
    if (task.import_path) {
        basicFields.push(['入库目录', '<span class="detail-mono">' + escapeHtml(task.import_path) + '</span>']);
    }
    if (task.import_video_path) {
        basicFields.push(['入库路径', '<span class="detail-mono">' + escapeHtml(task.import_video_path) + '</span>']);
    }
    if (task.final_filename) {
        basicFields.push(['最终文件名', escapeHtml(task.final_filename)]);
    }
    sections.push({ label: '基本信息', fields: basicFields });

    // Section: 刮削结果
    if (Object.keys(scrapeResult).length > 0) {
        var scrapeFields = [];
        if (scrapeResult.title_cn) scrapeFields.push(['中文标题', escapeHtml(scrapeResult.title_cn)]);
        if (scrapeResult.title_en) scrapeFields.push(['英文标题', escapeHtml(scrapeResult.title_en)]);
        if (scrapeResult.year) scrapeFields.push(['年份', escapeHtml(String(scrapeResult.year))]);
        var typeVal = scrapeResult.type;
        if (typeVal) {
            scrapeFields.push(['媒体类型', typeVal === 'movie' ? '<span class="detail-chip type-movie">电影</span>' : typeVal === 'tv' ? '<span class="detail-chip type-tv">剧集</span>' : escapeHtml(typeVal)]);
        }
        if (scrapeResult.season != null && scrapeResult.season !== 'null' && scrapeResult.season !== 'None') scrapeFields.push(['季', 'S' + String(scrapeResult.season).padStart(2, '0')]);
        if (scrapeResult.episode != null && scrapeResult.episode !== 'null' && scrapeResult.episode !== 'None') scrapeFields.push(['集', 'E' + String(scrapeResult.episode).padStart(2, '0')]);
        if (scrapeResult.resolution) scrapeFields.push(['分辨率', escapeHtml(String(scrapeResult.resolution))]);
        if (scrapeResult.quality) scrapeFields.push(['画质', escapeHtml(String(scrapeResult.quality))]);
        var detailMatchLevel = scrapeResult.match_level || task.match_level || '';
        if (detailMatchLevel === 'AUTO_PASS') {
            scrapeFields.push(['匹配级别', '<span class="detail-match detail-match-auto">自动匹配</span>']);
        } else if (detailMatchLevel === 'CONTEXT_PASS') {
            scrapeFields.push(['匹配级别', '<span class="detail-match detail-match-context">AI辅助匹配</span>']);
        } else if (detailMatchLevel === 'NEEDS_CONFIRM') {
            scrapeFields.push(['匹配级别', '<span class="detail-match detail-match-confirm">需确认</span>']);
        }
        if (scrapeResult.ai_reason) scrapeFields.push(['AI 判定依据', escapeHtml(String(scrapeResult.ai_reason))]);
        sections.push({ label: 'AI 刮削结果', fields: scrapeFields });
    }

    // Section: 维度
    var dims = task.scrape_dimensions || {};
    if (Object.keys(dims).length > 0) {
        var dimHtml = '<div class="detail-dim-grid">';
        for (var key in dims) {
            var dimLabel = _getDimLabel(key);
            var rawVal = String(dims[key]);
            var displayVal = _getDimValueLabel(key, rawVal);
            var dimColor = _getDimColor(key);
            dimHtml += '<div class="detail-dim-item" style="border-left-color:' + dimColor + ';background:' + dimColor + '15">' +
                '<span class="detail-dim-key" style="color:' + dimColor + '">' + escapeHtml(dimLabel) + '</span>' +
                '<span class="detail-dim-val">' + escapeHtml(displayVal) + '</span>' +
            '</div>';
        }
        dimHtml += '</div>';
        sections.push({ label: '分类维度', html: dimHtml });
    }

    // Section: 去重
    var dedupResult = task.dedup_result || {};
    if (dedupResult && dedupResult.is_duplicate) {
        var dedupFields = [];
        dedupFields.push(['查重结果', '<span style="color:#A78BFA;font-weight:500">入库目标有重复</span>']);
        if (dedupResult.existing_file) dedupFields.push(['已存在文件', escapeHtml(dedupResult.existing_file)]);
        if (dedupResult.quality_decision) dedupFields.push(['质量判定', escapeHtml(dedupResult.quality_decision === 'replace' ? '新文件更优，将替换' : '保留已存在文件')]);
        if (dedupResult.skip_message) dedupFields.push(['处理说明', escapeHtml(dedupResult.skip_message)]);
        sections.push({ label: '入库去重检测', fields: dedupFields });
    }

    // Section: 错误 / 跳过
    if (task.error_message) {
        sections.push({ label: '错误信息', html: '<div class="detail-alert detail-alert-error">' + escapeHtml(task.error_message) + '</div>' });
    }
    if (task.skip_reason) {
        sections.push({ label: '跳过原因', html: '<div class="detail-alert detail-alert-warn">' + escapeHtml(task.skip_reason) + '</div>' });
    }

    // Section: 时间
    var timeFields = [];
    if (task.created_at) timeFields.push(['创建时间', task.created_at.replace('T', ' ').substring(0, 19)]);
    if (task.started_at) timeFields.push(['开始时间', task.started_at.replace('T', ' ').substring(0, 19)]);
    if (task.completed_at) timeFields.push(['完成时间', task.completed_at.replace('T', ' ').substring(0, 19)]);
    sections.push({ label: '时间', fields: timeFields });

    var scrapeTrace = task.scrape_trace;
    if (scrapeTrace && typeof scrapeTrace === 'object') {
        var traceHtml = _renderScrapeTrace(scrapeTrace, filename);
        sections.push({ label: '决策路径', html: traceHtml });
    } else if (scrapeTrace && typeof scrapeTrace === 'string') {
        try {
            var parsedTrace = JSON.parse(scrapeTrace);
            var traceHtml = _renderScrapeTrace(parsedTrace, filename);
            sections.push({ label: '决策路径', html: traceHtml });
        } catch(e) {
            // ignore parse error
        }
    }

    // 渲染 section
    body.innerHTML = sections.map(function(sec) {
        var html = '<div class="detail-section"><div class="detail-section-title">' + escapeHtml(sec.label) + '</div>';
        if (sec.html) {
            html += sec.html;
        } else if (sec.fields) {
            html += '<div class="detail-grid">';
            sec.fields.forEach(function(f) {
                html += '<div class="detail-field"><div class="detail-field-label">' + escapeHtml(f[0]) + '</div><div class="detail-field-value">' + f[1] + '</div></div>';
            });
            html += '</div>';
        }
        html += '</div>';
        return html;
    }).join('');

    // ===== Footer =====
    var deleteBtn = '';
    if (status !== 'PROCESSING') {
        deleteBtn = '<button class="btn btn-danger" onclick="showDeleteConfirm(\'' + escapeHtml(task.task_id) + '\',\'' + escapeHtml(task.source_filename || '') + '\',\'' + escapeHtml(fileLocation) + '\')">移入回收站</button>';
    }
    footer.innerHTML = '';
    if (status === 'CONFIRMING') {
        var reclassifyHtml = buildReclassifyForm(task);
        body.innerHTML += reclassifyHtml;
        footer.innerHTML =
            '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>' +
            deleteBtn +
            '<button class="btn btn-warning" onclick="ignoreTask(\'' + escapeHtml(task.task_id) + '\')">忽略</button>' +
            '<button class="btn btn-primary" onclick="confirmTask(\'' + escapeHtml(task.task_id) + '\')">确认入库</button>';
    } else if (status === 'FAILED') {
        footer.innerHTML =
            '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>' +
            deleteBtn +
            '<button class="btn btn-warning" onclick="ignoreTask(\'' + escapeHtml(task.task_id) + '\')">忽略</button>' +
            '<button class="btn btn-primary" onclick="retryTask(\'' + escapeHtml(task.task_id) + '\')">重试</button>';
    } else if (status === 'SKIPPED') {
        footer.innerHTML =
            '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>' +
            deleteBtn +
            '<button class="btn btn-primary" onclick="retryTask(\'' + escapeHtml(task.task_id) + '\')">重试</button>';
    } else {
        footer.innerHTML =
            '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>' +
            deleteBtn;
    }

    var modal = document.getElementById('task-detail-modal');
    modal.style.display = 'flex';
}

function copyTaskId(el) {
    var tid = el.getAttribute('data-tid') || '';
    navigator.clipboard.writeText(tid).then(function() {
        showToast('任务ID已复制');
    }).catch(function() {
        showToast('复制失败', 'error');
    });
}

function startRename(taskId) {
    var row = document.getElementById('detail-filename-row');
    if (!row) return;
    var filenameEl = document.getElementById('detail-current-filename');
    var currentName = filenameEl ? filenameEl.textContent : '';
    row.innerHTML = '<input type="text" class="detail-rename-input" id="detail-rename-input" value="' + escapeHtml(currentName) + '">' +
        '<button class="detail-rename-confirm" onclick="submitRename(\'' + escapeHtml(taskId) + '\')"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg></button>' +
        '<button class="detail-rename-cancel" onclick="cancelRename(\'' + escapeHtml(taskId) + '\',\'' + escapeHtml(currentName) + '\')"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>';
    var input = document.getElementById('detail-rename-input');
    if (input) {
        var dotIdx = currentName.lastIndexOf('.');
        if (dotIdx > 0) {
            input.setSelectionRange(0, dotIdx);
        } else {
            input.select();
        }
        input.focus();
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') submitRename(taskId);
            if (e.key === 'Escape') cancelRename(taskId, currentName);
        });
    }
}

function cancelRename(taskId, originalName) {
    var row = document.getElementById('detail-filename-row');
    if (!row) return;
    row.innerHTML = '<span class="detail-filename-text" id="detail-current-filename">' + escapeHtml(originalName) + '</span>' +
        '<button class="detail-rename-btn" onclick="startRename(\'' + escapeHtml(taskId) + '\')" data-tooltip="修改文件名">' +
        '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>' +
        '</button>';
}

async function submitRename(taskId) {
    var input = document.getElementById('detail-rename-input');
    if (!input) return;
    var newFilename = input.value.trim();
    if (!newFilename) {
        showToast('文件名不能为空', 'error');
        return;
    }
    var result = await apiRequest('POST', '/tasks/' + encodeURIComponent(taskId) + '/rename', {
        new_filename: newFilename
    });
    if (result.code === 200) {
        showToast('文件重命名成功');
        showTaskDetail(taskId);
        loadTasks();
    } else {
        showToast(result.message || '重命名失败', 'error');
    }
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
        var dimLabel = _getDimLabel(key);
        html += '<div class="detail-dim-item">' +
            '<span class="detail-dim-key">' + escapeHtml(dimLabel) + '</span>' +
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

function closeModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) modal.style.display = 'none';
}

var _locationLabels = {
    'source': '源目录',
    'temp': '中转目录',
    'import': '入库目录',
    'recycle': '回收站',
    'deleted': '已删除'
};

var _locationFileLabels = {
    'source': '源文件',
    'temp': '中转文件',
    'import': '入库文件',
    'recycle': '回收站文件',
    'deleted': '文件'
};

var _locationWarnings = {
    'source': '源文件将移入回收站',
    'temp': '中转文件将移入回收站',
    'import': '⚠️ 已入库文件将移入回收站，请确认不再需要此影视文件',
    'recycle': '将永久删除回收站中的文件，删除后无法恢复',
    'deleted': ''
};

function showDeleteConfirm(taskId, filename, fileLocation) {
    var modal = document.getElementById('delete-confirm-modal');
    var nameEl = document.getElementById('delete-filename');
    var locEl = document.getElementById('delete-file-location');
    var fileCheckbox = document.getElementById('delete-with-files');
    var fileLabel = document.getElementById('delete-file-label');
    var warningEl = document.getElementById('delete-file-warning');

    nameEl.textContent = filename || '未知文件';
    var locText = _locationLabels[fileLocation] || fileLocation || '未知';
    var fileText = _locationFileLabels[fileLocation] || '文件';
    locEl.textContent = locText;

    var warningMsg = _locationWarnings[fileLocation] || '';
    if (warningMsg) {
        warningEl.textContent = warningMsg;
        warningEl.style.display = 'block';
    } else {
        warningEl.style.display = 'none';
    }

    if (fileLocation === 'import') {
        fileCheckbox.checked = false;
        fileLabel.textContent = '同时移入回收站（' + locText + '）';
    } else if (fileLocation === 'recycle') {
        fileCheckbox.checked = true;
        fileLabel.textContent = '同时永久删除回收站文件（' + locText + '）';
    } else if (fileLocation === 'temp') {
        fileCheckbox.checked = true;
        fileLabel.textContent = '同时移入回收站（' + locText + '）';
    } else if (fileLocation === 'source') {
        fileCheckbox.checked = false;
        fileLabel.textContent = '同时移入回收站（' + locText + '）';
    } else {
        fileCheckbox.checked = false;
        fileLabel.textContent = '同时移入回收站';
    }

    modal.setAttribute('data-task-id', taskId);
    modal.style.display = 'flex';
}

async function deleteTask() {
    var modal = document.getElementById('delete-confirm-modal');
    var taskId = modal.getAttribute('data-task-id');
    var deleteFiles = document.getElementById('delete-with-files').checked;

    if (!taskId) return;

    var result = await apiRequest('POST', '/tasks/' + taskId + '/delete', {
        delete_files: deleteFiles
    });

    if (result.code === 200) {
        closeModal('delete-confirm-modal');
        closeModal('task-detail-modal');
        loadTasks(_currentTaskPage, _currentTaskStatus);
        if (typeof refreshOverview === 'function') refreshOverview();
    } else {
        var message = '操作失败: ' + (result.message || '未知错误');
        if (typeof showToast === 'function') {
            showToast(message);
        } else {
            console.error(message);
        }
    }
}

document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.style.display = 'none';
    }
});

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

function _renderScrapeTrace(trace, filename) {
    if (!trace || typeof trace !== 'object') {
        return '<div style="padding:12px;color:var(--text-secondary);font-size:13px;">暂无决策路径数据</div>';
    }

    var html = '<div class="scrape-trace-timeline">';

    var steps = [];

    var fc = trace.filename_clean;
    if (fc) {
        steps.push({
            type: 'INPUT',
            label: '文件名输入',
            color: '#06B6D4',
            detail: fc.original || fc.clean_title || '-',
            sub: '清洗后: ' + (fc.clean_title || '-') + (fc.year ? ' (' + fc.year + ')' : '') + (fc.removed_items && fc.removed_items.length ? ' | 移除: ' + fc.removed_items.join(', ') : ''),
        });
    }

    if (trace.ai_clean) {
        steps.push({
            type: 'AI',
            label: 'AI 辅助清洗',
            color: '#F59E0B',
            detail: trace.ai_clean.clean_title || '-',
            sub: '方法: ' + (trace.ai_clean.method || 'ai'),
        });
    }

    var ts = trace.provider_search;
    if (ts) {
        var providerName = trace.provider_type || 'TMDb';
        steps.push({
            type: 'PROVIDER',
            label: providerName + ' 搜索',
            color: '#8B5CF6',
            detail: '查询: ' + (ts.query || '-'),
            sub: (ts.total_results || 0) + ' 个结果' + (ts.fallback_used ? ' (使用了英文回退)' : '') + ' | 匹配: ' + (ts.selected_title || '-'),
        });
    }

    var pfr = trace.provider_fallback_reasons;
    if (!ts && pfr && pfr.length > 0) {
        var fallbackRows = pfr.map(function(p) {
            var icon = '';
            var iconColor = '#94A3B8';
            if (p.status === 'error') { icon = '✗'; iconColor = '#EF4444'; }
            else if (p.status === 'no_results') { icon = '∅'; iconColor = '#F59E0B'; }
            else if (p.status === 'below_threshold') { icon = '↓'; iconColor = '#F59E0B'; }
            else if (p.status === 'details_error') { icon = '⚠'; iconColor = '#EF4444'; }
            else if (p.status === 'not_configured') { icon = '—'; iconColor = '#94A3B8'; }
            else { icon = '?'; iconColor = '#94A3B8'; }
            var name = p.display_name || p.provider_type || '未知';
            return '<div style="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid var(--border-color);font-size:12px;">' +
                '<span style="color:' + iconColor + ';font-weight:600;min-width:16px;text-align:center;">' + icon + '</span>' +
                '<span style="font-weight:500;color:var(--text-primary);">' + escapeHtml(name) + '</span>' +
                '<span style="color:var(--text-secondary);">' + escapeHtml(p.reason || '未知原因') + '</span>' +
            '</div>';
        });
        steps.push({
            type: 'WARN',
            label: 'Provider 降级为 AI-only',
            color: '#F59E0B',
            sub: '所有元数据源均不可用，降级为纯 AI 刮削',
            extra: fallbackRows.join(''),
        });
    }

    // 三级匹配路径显示
    var matchTrace = trace;
    if (matchTrace && typeof matchTrace === 'object') {
        var traceSteps = matchTrace.trace || [];
        if (Array.isArray(traceSteps) && traceSteps.length > 0) {
            for (var ti = 0; ti < traceSteps.length; ti++) {
                var mStep = traceSteps[ti];
                var stepColor = mStep.matched ? '#22C55E' : (mStep.tier === 3 ? '#F59E0B' : '#94A3B8');
                var stepType = mStep.matched ? 'MATCH' : 'INFO';
                steps.push({
                    type: stepType,
                    label: '第' + mStep.tier + '级：' + (mStep.name || ''),
                    color: stepColor,
                    detail: mStep.reason || '',
                    sub: mStep.ai_reason || '',
                });
            }
        } else {
            // 无匹配路径信息
            steps.push({
                type: 'INFO',
                label: '无匹配路径信息',
                color: '#94A3B8',
                detail: '',
            });
        }
    }

    steps.forEach(function(step, idx) {
        var isLast = idx === steps.length - 1;
        html += '<div class="scrape-trace-step">';
        html += '<div class="scrape-trace-dot" style="background:' + step.color + ';"></div>';
        if (!isLast) html += '<div class="scrape-trace-line"></div>';
        html += '<div class="scrape-trace-content">';
        html += '<div class="scrape-trace-label" style="color:' + step.color + ';">' + escapeHtml(step.label) + '</div>';
        if (step.detail) html += '<div class="scrape-trace-detail">' + escapeHtml(step.detail) + '</div>';
        if (step.sub) html += '<div class="scrape-trace-sub">' + escapeHtml(step.sub) + '</div>';
        if (step.extra) html += '<div class="scrape-trace-extra">' + step.extra + '</div>';
        html += '</div></div>';
    });

    html += '</div>';
    html += '<div style="margin-top:12px;text-align:center;">';
    html += '<button class="btn btn-secondary btn-sm" onclick="showMatchTraceModal(JSON.parse(decodeURIComponent(this.getAttribute(\'data-trace\'))),this.getAttribute(\'data-filename\'))" data-trace="' + encodeURIComponent(JSON.stringify(trace)) + '" data-filename="' + escapeHtml(filename || '') + '">查看匹配路径</button>';
    html += '</div>';
    return html;
}

function escapeHtml(text) {
    if (text == null) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(String(text)));
    return div.innerHTML;
}

function showMatchTraceModal(trace, filename) {
    var html = '<div style="padding:16px;background:rgba(255,255,255,0.02);border-radius:8px;">';
    html += '<h3 style="margin-top:0;">匹配路径详情</h3>';
    html += '<p style="color:#94A3B8;font-size:12px;margin:8px 0 16px;">文件：' + escapeHtml(filename || '') + '</p>';
    var steps = (trace && typeof trace === 'object' && trace.trace) || [];
    if (Array.isArray(steps) && steps.length > 0) {
        html += '<div style="display:flex;flex-direction:column;gap:12px;">';
        for (var i = 0; i < steps.length; i++) {
            var step = steps[i];
            var color = step.matched ? '#22C55E' : (step.tier === 3 ? '#F59E0B' : '#94A3B8');
            html += '<div style="border:1px solid ' + color + '20;background:' + color + '08;padding:12px 16px;border-radius:8px;">';
            html += '<div style="font-weight:600;color:' + color + ';">第' + step.tier + '级：' + escapeHtml(step.name || '') + ' &nbsp;·&nbsp; ' + (step.matched ? '✓ 匹配' : '✗ 未匹配') + '</div>';
            if (step.reason) html += '<div style="margin-top:8px;font-size:13px;line-height:1.6;color:#CBD5E1;">' + escapeHtml(step.reason) + '</div>';
            if (step.ai_reason) html += '<div style="margin-top:8px;font-size:13px;line-height:1.6;color:#06B6D4;border-left:2px solid #06B6D420;padding-left:12px;">AI: ' + escapeHtml(step.ai_reason) + '</div>';
            html += '</div>';
        }
        html += '</div>';
    } else {
        html += '<p style="color:#94A3B8;">无匹配路径信息</p>';
    }
    html += '</div>';
    if (typeof showAppModal === 'function') {
        showAppModal({ title: '匹配路径', body: html, actions: [{ label: '关闭', className: 'btn btn-secondary' }] });
    } else {
        alert(html.replace(/<[^>]+>/g, '\n'));
    }
}

// tasks-list.js - task state, loading, and table rendering
var _currentTaskPage = 1;
var _currentTaskStatus = "all";
var _currentTaskTotalPages = 1;

var _taskDimensionConfig = {};

async function loadTaskDimensionConfig() {
  try {
    var result = await apiRequest("GET", "/dimensions/enabled");
    if (result.code === 200 && result.data) {
      var dims = result.data.dimensions || [];
      _taskDimensionConfig = {};
      dims.forEach(function (d) {
        var valMap = {};
        (d.value_list || []).forEach(function (v) {
          valMap[v.value] = v.label;
        });
        _taskDimensionConfig[d.name] = {
          label: d.label,
          valueLabels: valMap,
          color: d.color || "#6c757d",
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
  return (
    (_taskDimensionConfig[key] && _taskDimensionConfig[key].color) || "#6c757d"
  );
}

var FILE_LOCATION_LABELS = {
  source: "源目录",
  temp: "中转目录",
  import: "已入库",
  recycle: "回收站",
  deleted: "已删除",
};

var STATUS_GROUPS = {
  queued: { status: "PENDING", stage: "QUEUED" },
  running: { status: "PENDING", stage: "RUNNING" },
  review: { status: "PENDING", stage: "AWAIT_REVIEW" },
  failed: { status: "FAILED" },
  completed: { statuses: ["SUCCESS", "SKIPPED"] },
};

async function loadTasks(page, status) {
  if (page !== undefined) _currentTaskPage = page;
  if (status !== undefined) _currentTaskStatus = status;
  var pageNum = _currentTaskPage || 1;

  if (Object.keys(_taskDimensionConfig).length === 0) {
    await loadTaskDimensionConfig();
  }
  var statusFilter = _currentTaskStatus || "all";

  var groupConfig = STATUS_GROUPS[statusFilter];
  if (groupConfig) {
    var allTasks = [];
    var totalCount = 0;
    var totalPages = 1;

    if (groupConfig.statuses) {
      for (var gi = 0; gi < groupConfig.statuses.length; gi++) {
        var url =
          "/tasks?page=" +
          pageNum +
          "&limit=20&status=" +
          encodeURIComponent(groupConfig.statuses[gi]);
        var result = await apiRequest("GET", url);
        if (result.code === 200 && result.data) {
          allTasks = allTasks.concat(result.data.tasks || []);
          totalCount += result.data.total || 0;
          totalPages = Math.max(totalPages, result.data.total_pages || 1);
        }
      }
    } else {
      var url = "/tasks?page=" + pageNum + "&limit=20";
      if (groupConfig.status) {
        url += "&status=" + encodeURIComponent(groupConfig.status);
      }
      if (groupConfig.stage) {
        url += "&stage=" + encodeURIComponent(groupConfig.stage);
      }
      var result = await apiRequest("GET", url);
      if (result.code === 200 && result.data) {
        allTasks = result.data.tasks || [];
        totalCount = result.data.total || 0;
        totalPages = result.data.total_pages || 1;
      }
    }
    allTasks.sort(function (a, b) {
      var ta = a.created_at || "";
      var tb = b.created_at || "";
      return ta > tb ? -1 : ta < tb ? 1 : 0;
    });
    _currentTaskTotalPages = totalPages;
    if (allTasks.length > 0) {
      console.log(
        "[loadTasks] 第1条数据字段:",
        Object.keys(allTasks[0]).join(", "),
      );
    }
    renderTaskTable(allTasks);
    renderPagination(totalPages, pageNum, totalCount);
  } else {
    var url = "/tasks?page=" + pageNum + "&limit=20";
    if (statusFilter !== "all") {
      url += "&status=" + encodeURIComponent(statusFilter);
    }
    var result = await apiRequest("GET", url);
    if (result.code === 200 && result.data) {
      var tasks = result.data.tasks || [];
      var total = result.data.total || 0;
      var totalPages = result.data.total_pages || 1;
      _currentTaskTotalPages = totalPages;
      if (tasks.length > 0) {
        console.log(
          "[loadTasks] 第1条数据字段:",
          Object.keys(tasks[0]).join(", "),
        );
        console.log(
          "[loadTasks] 第1条 source_filename:",
          tasks[0].source_filename,
          "source_path:",
          tasks[0].source_path,
        );
      }
      renderTaskTable(tasks);
      renderPagination(totalPages, pageNum, total);
    } else {
      var tbody = document.getElementById("tasks-table-body");
      tbody.innerHTML =
        '<tr><td colspan="6" class="empty-row">加载失败: ' +
        (result.message || "未知错误") +
        "</td></tr>";
    }
  }
}

function renderTaskTable(tasks) {
  var tbody = document.getElementById("tasks-table-body");
  if (!tasks || tasks.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="7" class="empty-row"><div class="empty-state-container"><div class="empty-state-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div><div class="empty-state-title">暂无任务记录</div><div class="empty-state-desc">将视频文件放入源目录后，点击"立即扫描"即可开始处理</div><div class="empty-state-actions"><button class="btn btn-primary btn-sm" onclick="switchTab(\'overview\')">前往首页</button><button class="btn btn-secondary btn-sm" onclick="switchTab(\'config\')">配置源目录</button></div></div></td></tr>';
    return;
  }

  var pageNum = _currentTaskPage || 1;
  var pageSize = 20;
  var startIndex = (pageNum - 1) * pageSize;

  tbody.innerHTML = tasks
    .map(function (task, idx) {
      var tid = task.task_id || "";
      var filename =
        task.source_filename ||
        (task.source_path
          ? task.source_path.split("/").pop().split("\\").pop()
          : "") ||
        "-";
      var status = task.status || "PENDING";
      var importPath = task.import_path || "";
      var locationPath = buildLocationCell(task, importPath);
      var subtitleInfo = buildSubtitleCell(task);
      var scrapeInfo = buildScrapeCell(task);
      var actionsHtml = buildActionButtons(task);
      var rowNum = startIndex + idx + 1;
      var completedTime = buildCompletedTime(task);

      return (
        '<tr class="fade-in">' +
        '<td class="task-row-num">' +
        rowNum +
        "</td>" +
        '<td><div class="task-row-main">' +
        '<div class="task-row-title">' +
        '<span class="task-filename" onclick="showTaskDetail(\'' +
        tid +
        '\')" data-tooltip="点击查看详情">' +
        escapeHtml(filename) +
        "</span>" +
        "</div>" +
        '<div class="task-row-sub">' +
        scrapeInfo +
        "</div>" +
        "</div></td>" +
        '<td class="task-subtitle-cell">' +
        subtitleInfo +
        "</td>" +
        '<td><span class="status-badge status-badge-' +
        status +
        '">' +
        getStatusText(status) +
        "</span></td>" +
        "<td>" +
        locationPath +
        "</td>" +
        '<td class="task-time-cell">' +
        completedTime +
        "</td>" +
        '<td><div class="task-actions">' +
        actionsHtml +
        "</div></td>" +
        "</tr>"
      );
    })
    .join("");
}

function buildLocationCell(task, importPath) {
  var fileLocation = task.file_location || "source";
  var locationLabel = FILE_LOCATION_LABELS[fileLocation] || fileLocation;
  var locationPath = "";

  if (fileLocation === "import") {
    locationPath = task.import_video_path || importPath || "";
  } else if (fileLocation === "temp") {
    locationPath = task.video_path || "";
  } else if (fileLocation === "recycle") {
    locationPath = task.source_path || "";
  } else if (fileLocation === "source") {
    locationPath = task.source_path || "";
  }

  if (locationPath) {
    return (
      '<span class="task-import-path" data-tooltip="' +
      escapeHtml(locationPath) +
      '">' +
      '<span class="location-tag location-tag-' +
      fileLocation +
      '">' +
      locationLabel +
      "</span> " +
      escapeHtml(truncate(locationPath, 24)) +
      "</span>"
    );
  }
  return (
    '<span class="task-import-path"><span class="location-tag location-tag-' +
    fileLocation +
    '">' +
    locationLabel +
    "</span></span>"
  );
}

function buildCompletedTime(task) {
  if (task.completed_at) {
    return task.completed_at.substring(5, 16).replace("T", " ");
  }
  if (task.status === "PROCESSING") {
    return '<span class="processing-indicator">处理中...</span>';
  }
  if (task.status === "PENDING") {
    return "-";
  }
  if (!task.started_at) {
    return "-";
  }
  var start = task.started_at.substring(5, 16).replace("T", " ");
  return start + " ...";
}

function buildScrapeCell(task) {
  var parts = [];
  var titleCn = task.scrape_title_cn || "";
  var titleEn = task.scrape_title_en || "";
  var mediaType = task.scrape_media_type || "";
  var year = task.scrape_year || "";

  if (task.file_size_mb != null && task.file_size_mb > 0) {
    var sizeStr =
      task.file_size_mb >= 1024
        ? (task.file_size_mb / 1024).toFixed(1) + "GB"
        : task.file_size_mb >= 1
          ? task.file_size_mb.toFixed(0) + "MB"
          : (task.file_size_mb * 1024).toFixed(0) + "KB";
    parts.push('<span class="task-size-chip">' + sizeStr + "</span>");
  }

  if (titleCn || titleEn) {
    var title = titleCn || titleEn;
    parts.push(
      '<span class="task-scrape-chip' +
        (mediaType === "movie"
          ? " type-movie"
          : mediaType === "tv"
            ? " type-tv"
            : "") +
        '">' +
        escapeHtml(title) +
        (year ? " (" + year + ")" : "") +
        "</span>",
    );
  }

  if (mediaType) {
    parts.push(
      "<span>" +
        (mediaType === "movie"
          ? "电影"
          : mediaType === "tv"
            ? "剧集"
            : mediaType) +
        "</span>",
    );
  }

  if (
    task.scrape_season &&
    task.scrape_season !== "null" &&
    task.scrape_season !== "None"
  ) {
    parts.push(
      "<span>S" + String(task.scrape_season).padStart(2, "0") + "</span>",
    );
  }
  if (
    task.scrape_episode &&
    task.scrape_episode !== "null" &&
    task.scrape_episode !== "None"
  ) {
    parts.push(
      "<span>E" + String(task.scrape_episode).padStart(2, "0") + "</span>",
    );
  }

  var matchLevel = task.match_level || task.scrape_match_level || "";
  if (matchLevel === "AUTO_PASS") {
    parts.push('<span class="match-tag match-auto">自动匹配</span>');
  } else if (matchLevel === "CONTEXT_PASS") {
    parts.push('<span class="match-tag match-context">🤖 AI辅助匹配</span>');
  } else if (matchLevel === "NEEDS_CONFIRM") {
    parts.push('<span class="match-tag match-confirm">需确认</span>');
  }

  if (task.skip_reason) {
    parts.push(
      '<span style="color:var(--text-muted)">' +
        escapeHtml(truncate(task.skip_reason, 20)) +
        "</span>",
    );
  } else if (task.error_message) {
    parts.push(
      '<span style="color:var(--danger-color)">' +
        escapeHtml(truncate(task.error_message, 20)) +
        "</span>",
    );
  }

  return parts.length > 0
    ? parts.join(" ")
    : '<span style="color:var(--text-muted)">等待处理...</span>';
}

function buildSubtitleCell(task) {
  var total = task.subtitle_total || 0;
  var success = task.subtitle_success || 0;
  if (total === 0) {
    return '<span class="task-subtitle-count">无</span>';
  }
  var label = "字幕 x" + total;
  if (success > 0 && success < total) {
    label += " (" + success + "/" + total + " 成功)";
  } else if (success === total) {
    label += " ✓";
  }
  return (
    '<span class="task-subtitle-count has-subs" onclick="showSubtitleDetail(\'' +
    task.task_id +
    "')\">" +
    label +
    "</span>"
  );
}

function buildActionButtons(task) {
  var tid = task.task_id || "";
  var status = task.status || "";
  var btns = [];

  btns.push(
    '<button class="task-action-btn" onclick="showTaskDetail(\'' +
      escapeHtml(tid) +
      '\')" data-tooltip="查看详情">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M22 12c0 5.52-4.48 10-10 10S2 17.52 2 12 6.48 2 12 2s10 4.48 10 10z"/></svg>' +
      "</button>",
  );

  if (status === "CONFIRMING") {
    btns.push(
      '<button class="task-action-btn confirm" onclick="confirmTask(\'' +
        escapeHtml(tid) +
        '\')" data-tooltip="确认入库">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>' +
        "</button>",
    );
    btns.push(
      '<button class="task-action-btn reclassify" onclick="showTaskDetail(\'' +
        escapeHtml(tid) +
        '\')" data-tooltip="修改分类">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0-3-3m3 3 3-3M5 21h14"/></svg>' +
        "</button>",
    );
    btns.push(
      '<button class="task-action-btn ignore" onclick="ignoreTask(\'' +
        escapeHtml(tid) +
        '\')" data-tooltip="忽略">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>' +
        "</button>",
    );
  }

  if (status === "FAILED") {
    btns.push(
      '<button class="task-action-btn retry" onclick="retryTask(\'' +
        escapeHtml(tid) +
        '\')" data-tooltip="重试">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>' +
        "</button>",
    );
    btns.push(
      '<button class="task-action-btn ignore" onclick="ignoreTask(\'' +
        escapeHtml(tid) +
        '\')" data-tooltip="忽略">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>' +
        "</button>",
    );
  }

  if (status === "SKIPPED") {
    btns.push(
      '<button class="task-action-btn retry" onclick="retryTask(\'' +
        escapeHtml(tid) +
        '\')" data-tooltip="重试">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>' +
        "</button>",
    );
  }

  if (status !== "PROCESSING") {
    btns.push(
      '<button class="task-action-btn delete" onclick="showDeleteConfirm(\'' +
        escapeHtml(tid) +
        "','" +
        escapeHtml(task.source_filename || "") +
        "','" +
        escapeHtml(task.file_location || "source") +
        '\')" data-tooltip="移入回收站">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
        "</button>",
    );
  }

  return btns.join("");
}


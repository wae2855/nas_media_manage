// tasks-detail.js - task detail modal
async function showTaskDetail(taskId) {
  var result = await apiRequest("GET", "/tasks/" + encodeURIComponent(taskId));
  if (result.code !== 200 || !result.data || !result.data.task) {
    showToast("获取任务详情失败", "error");
    return;
  }
  var task = result.data.task;
  var body = document.getElementById("task-detail-body");
  var footer = document.getElementById("task-detail-footer");

  var status = task.status || "PENDING";
  var scrapeResult = task.scrape_result || {};
  var titleCn = scrapeResult.title_cn || "";
  var titleEn = scrapeResult.title_en || "";
  var year = scrapeResult.year || "";
  var filename =
    task.source_filename ||
    (task.source_path
      ? task.source_path.split("/").pop().split("\\").pop()
      : "") ||
    "-";

  // ===== Header 区 =====
  var headerIcon = document.getElementById("detail-header-icon");
  var headerTitle = document.getElementById("detail-header-title");
  var headerSub = document.getElementById("detail-header-sub");

  // Icon: use scrape type or file extension
  var headerIconHtml = "";
  var scrapeType = scrapeResult.type || "";
  if (scrapeType === "tv") {
    headerIconHtml =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><polyline points="8 21 12 17 16 21"/></svg>';
    headerIcon.style.background = "rgba(139,92,246,0.15)";
    headerIcon.style.color = "#A78BFA";
  } else if (scrapeType === "movie") {
    headerIconHtml =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="20" height="20" rx="2.18"/><polygon points="10 7 10 17 17 12 10 7"/></svg>';
    headerIcon.style.background = "rgba(59,130,246,0.15)";
    headerIcon.style.color = "#93C5FD";
  } else {
    headerIconHtml =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>';
    headerIcon.style.background = "rgba(100,116,139,0.15)";
    headerIcon.style.color = "#94A3B8";
  }
  headerIcon.innerHTML = headerIconHtml;

  var headerTitleText = titleCn || titleEn || filename;
  headerTitle.textContent = headerTitleText;
  headerTitle.title = headerTitleText;

  var headerSubParts = [];
  if (titleEn && titleEn !== headerTitleText) {
    headerSubParts.push(escapeHtml(titleEn));
  }
  headerSubParts.push(filename !== headerTitleText ? escapeHtml(filename) : "");
  headerSubParts.push(
    '<span class="status-badge status-badge-' +
      status +
      '">' +
      getStatusText(status) +
      "</span>",
  );
  headerSub.innerHTML = headerSubParts.filter(Boolean).join(" · ");

  // ===== Body 区 =====
  var sections = [];

  // Section: 基本信息
  var basicFields = [];
  basicFields.push([
    "任务ID",
    '<span class="detail-mono"><span class="detail-tid-text">' +
      escapeHtml(task.task_id || "-") +
      '</span><button class="detail-copy-btn" onclick="copyTaskId(this)" data-tid="' +
      escapeHtml(task.task_id || "") +
      '"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button></span>',
  ]);
  basicFields.push([
    "文件大小",
    task.file_size_mb != null && task.file_size_mb > 0
      ? task.file_size_mb >= 1024
        ? (task.file_size_mb / 1024).toFixed(2) + " GB"
        : task.file_size_mb >= 1
          ? task.file_size_mb.toFixed(2) + " MB"
          : (task.file_size_mb * 1024).toFixed(1) + " KB"
      : task.file_size_mb === 0
        ? "0 KB"
        : "-",
  ]);

  var fileLocation = task.file_location || "source";
  var locationLabel = FILE_LOCATION_LABELS[fileLocation] || fileLocation;
  var currentPath = "";
  if (fileLocation === "import") {
    currentPath = task.import_video_path || "";
  } else if (fileLocation === "temp") {
    currentPath = task.video_path || "";
  } else {
    currentPath = task.source_path || "";
  }
  basicFields.push([
    "当前文件位置",
    '<span class="detail-location-tag detail-location-' +
      fileLocation +
      '">' +
      locationLabel +
      "</span>",
  ]);

  var canRename = fileLocation !== "deleted" && currentPath;
  var filenameValue =
    '<span class="detail-filename-row" id="detail-filename-row">' +
    '<span class="detail-filename-text" id="detail-current-filename">' +
    escapeHtml(task.source_filename || "-") +
    "</span>";
  if (canRename) {
    filenameValue +=
      '<button class="detail-rename-btn" onclick="startRename(\'' +
      escapeHtml(task.task_id || "") +
      '\')" data-tooltip="修改文件名">' +
      '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>' +
      "</button>";
  }
  filenameValue += "</span>";
  basicFields.push(["文件名", filenameValue]);

  basicFields.push([
    "源路径",
    '<span class="detail-mono">' +
      escapeHtml(task.source_path || "-") +
      "</span>",
  ]);
  if (fileLocation === "temp" && task.video_path) {
    basicFields.push([
      "中转路径",
      '<span class="detail-mono">' + escapeHtml(task.video_path) + "</span>",
    ]);
  }
  if (task.import_path) {
    basicFields.push([
      "入库目录",
      '<span class="detail-mono">' + escapeHtml(task.import_path) + "</span>",
    ]);
  }
  if (task.import_video_path) {
    basicFields.push([
      "入库路径",
      '<span class="detail-mono">' +
        escapeHtml(task.import_video_path) +
        "</span>",
    ]);
  }
  if (task.final_filename) {
    basicFields.push(["最终文件名", escapeHtml(task.final_filename)]);
  }
  sections.push({ label: "基本信息", fields: basicFields });

  // Section: 刮削结果
  if (Object.keys(scrapeResult).length > 0) {
    var scrapeFields = [];
    if (scrapeResult.title_cn)
      scrapeFields.push(["中文标题", escapeHtml(scrapeResult.title_cn)]);
    if (scrapeResult.title_en)
      scrapeFields.push(["英文标题", escapeHtml(scrapeResult.title_en)]);
    if (scrapeResult.year)
      scrapeFields.push(["年份", escapeHtml(String(scrapeResult.year))]);
    var typeVal = scrapeResult.type;
    if (typeVal) {
      scrapeFields.push([
        "媒体类型",
        typeVal === "movie"
          ? '<span class="detail-chip type-movie">电影</span>'
          : typeVal === "tv"
            ? '<span class="detail-chip type-tv">剧集</span>'
            : escapeHtml(typeVal),
      ]);
    }
    if (
      scrapeResult.season != null &&
      scrapeResult.season !== "null" &&
      scrapeResult.season !== "None"
    )
      scrapeFields.push([
        "季",
        "S" + String(scrapeResult.season).padStart(2, "0"),
      ]);
    if (
      scrapeResult.episode != null &&
      scrapeResult.episode !== "null" &&
      scrapeResult.episode !== "None"
    )
      scrapeFields.push([
        "集",
        "E" + String(scrapeResult.episode).padStart(2, "0"),
      ]);
    if (scrapeResult.resolution)
      scrapeFields.push([
        "分辨率",
        escapeHtml(String(scrapeResult.resolution)),
      ]);
    if (scrapeResult.quality)
      scrapeFields.push(["画质", escapeHtml(String(scrapeResult.quality))]);
    var detailMatchLevel = scrapeResult.match_level || task.match_level || "";
    if (detailMatchLevel === "AUTO_PASS") {
      scrapeFields.push([
        "匹配级别",
        '<span class="detail-match detail-match-auto">自动匹配</span>',
      ]);
    } else if (detailMatchLevel === "CONTEXT_PASS") {
      scrapeFields.push([
        "匹配级别",
        '<span class="detail-match detail-match-context">🤖 AI辅助匹配</span>',
      ]);
    } else if (detailMatchLevel === "NEEDS_CONFIRM") {
      scrapeFields.push([
        "匹配级别",
        '<span class="detail-match detail-match-confirm">需确认</span>',
      ]);
    }
    if (scrapeResult.ai_reason)
      scrapeFields.push([
        "AI 判定依据",
        escapeHtml(String(scrapeResult.ai_reason)),
      ]);
    sections.push({ label: "AI 刮削结果", fields: scrapeFields });
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
      dimHtml +=
        '<div class="detail-dim-item" style="border-left-color:' +
        dimColor +
        ";background:" +
        dimColor +
        '15">' +
        '<span class="detail-dim-key" style="color:' +
        dimColor +
        '">' +
        escapeHtml(dimLabel) +
        "</span>" +
        '<span class="detail-dim-val">' +
        escapeHtml(displayVal) +
        "</span>" +
        "</div>";
    }
    dimHtml += "</div>";
    sections.push({ label: "分类维度", html: dimHtml });
  }

  // Section: 去重
  var dedupResult = task.dedup_result || {};
  if (dedupResult && dedupResult.is_duplicate) {
    var dedupFields = [];
    dedupFields.push([
      "查重结果",
      '<span style="color:#A78BFA;font-weight:500">入库目标有重复</span>',
    ]);
    if (dedupResult.existing_file)
      dedupFields.push(["已存在文件", escapeHtml(dedupResult.existing_file)]);
    if (dedupResult.quality_decision)
      dedupFields.push([
        "质量判定",
        escapeHtml(
          dedupResult.quality_decision === "replace"
            ? "新文件更优，将替换"
            : "保留已存在文件",
        ),
      ]);
    if (dedupResult.skip_message)
      dedupFields.push(["处理说明", escapeHtml(dedupResult.skip_message)]);
    sections.push({ label: "入库去重检测", fields: dedupFields });
  }

  // Section: 错误 / 跳过
  if (task.error_message) {
    sections.push({
      label: "错误信息",
      html:
        '<div class="detail-alert detail-alert-error">' +
        escapeHtml(task.error_message) +
        "</div>",
    });
  }
  if (task.skip_reason) {
    sections.push({
      label: "跳过原因",
      html:
        '<div class="detail-alert detail-alert-warn">' +
        escapeHtml(task.skip_reason) +
        "</div>",
    });
  }

  // Section: 时间
  var timeFields = [];
  if (task.created_at)
    timeFields.push([
      "创建时间",
      task.created_at.replace("T", " ").substring(0, 19),
    ]);
  if (task.started_at)
    timeFields.push([
      "开始时间",
      task.started_at.replace("T", " ").substring(0, 19),
    ]);
  if (task.completed_at)
    timeFields.push([
      "完成时间",
      task.completed_at.replace("T", " ").substring(0, 19),
    ]);
  sections.push({ label: "时间", fields: timeFields });

  var scrapeTrace = task.scrape_trace;
  if (scrapeTrace && typeof scrapeTrace === "object") {
    var traceHtml = _renderScrapeTrace(scrapeTrace, filename);
    sections.push({ label: "决策路径", html: traceHtml });
  } else if (scrapeTrace && typeof scrapeTrace === "string") {
    try {
      var parsedTrace = JSON.parse(scrapeTrace);
      var traceHtml = _renderScrapeTrace(parsedTrace, filename);
      sections.push({ label: "决策路径", html: traceHtml });
    } catch (e) {
      // ignore parse error
    }
  }

  // 渲染 section
  body.innerHTML = sections
    .map(function (sec) {
      var html =
        '<div class="detail-section"><div class="detail-section-title">' +
        escapeHtml(sec.label) +
        "</div>";
      if (sec.html) {
        html += sec.html;
      } else if (sec.fields) {
        html += '<div class="detail-grid">';
        sec.fields.forEach(function (f) {
          html +=
            '<div class="detail-field"><div class="detail-field-label">' +
            escapeHtml(f[0]) +
            '</div><div class="detail-field-value">' +
            f[1] +
            "</div></div>";
        });
        html += "</div>";
      }
      html += "</div>";
      return html;
    })
    .join("");

  // ===== Footer =====
  var deleteBtn = "";
  if (status !== "PROCESSING") {
    deleteBtn =
      '<button class="btn btn-danger" onclick="showDeleteConfirm(\'' +
      escapeHtml(task.task_id) +
      "','" +
      escapeHtml(task.source_filename || "") +
      "','" +
      escapeHtml(fileLocation) +
      "')\">移入回收站</button>";
  }
  footer.innerHTML = "";
  if (status === "CONFIRMING") {
    var reclassifyHtml = buildReclassifyForm(task);
    body.innerHTML += reclassifyHtml;
    footer.innerHTML =
      '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>' +
      deleteBtn +
      '<button class="btn btn-warning" onclick="ignoreTask(\'' +
      escapeHtml(task.task_id) +
      "')\">忽略</button>" +
      '<button class="btn btn-primary" onclick="confirmTask(\'' +
      escapeHtml(task.task_id) +
      "')\">确认入库</button>";
  } else if (status === "FAILED") {
    footer.innerHTML =
      '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>' +
      deleteBtn +
      '<button class="btn btn-warning" onclick="ignoreTask(\'' +
      escapeHtml(task.task_id) +
      "')\">忽略</button>" +
      '<button class="btn btn-primary" onclick="retryTask(\'' +
      escapeHtml(task.task_id) +
      "')\">重试</button>";
  } else if (status === "SKIPPED") {
    footer.innerHTML =
      '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>' +
      deleteBtn +
      '<button class="btn btn-primary" onclick="retryTask(\'' +
      escapeHtml(task.task_id) +
      "')\">重试</button>";
  } else {
    footer.innerHTML =
      '<button class="btn btn-secondary" onclick="closeModal(\'task-detail-modal\')">关闭</button>' +
      deleteBtn;
  }

  var modal = document.getElementById("task-detail-modal");
  modal.style.display = "flex";
}


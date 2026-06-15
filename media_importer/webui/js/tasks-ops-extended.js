// tasks-ops-extended.js - delete, logs, trace
function showDeleteConfirm(taskId, filename, fileLocation) {
  var modal = document.getElementById("delete-confirm-modal");
  var nameEl = document.getElementById("delete-filename");
  var locEl = document.getElementById("delete-file-location");
  var fileCheckbox = document.getElementById("delete-with-files");
  var fileLabel = document.getElementById("delete-file-label");
  var warningEl = document.getElementById("delete-file-warning");

  nameEl.textContent = filename || "未知文件";
  var locText = _locationLabels[fileLocation] || fileLocation || "未知";
  var fileText = _locationFileLabels[fileLocation] || "文件";
  locEl.textContent = locText;

  var warningMsg = _locationWarnings[fileLocation] || "";
  if (warningMsg) {
    warningEl.textContent = warningMsg;
    warningEl.style.display = "block";
  } else {
    warningEl.style.display = "none";
  }

  if (fileLocation === "import") {
    fileCheckbox.checked = false;
    fileLabel.textContent = "同时移入回收站（" + locText + "）";
  } else if (fileLocation === "recycle") {
    fileCheckbox.checked = true;
    fileLabel.textContent = "同时永久删除回收站文件（" + locText + "）";
  } else if (fileLocation === "temp") {
    fileCheckbox.checked = true;
    fileLabel.textContent = "同时移入回收站（" + locText + "）";
  } else if (fileLocation === "source") {
    fileCheckbox.checked = false;
    fileLabel.textContent = "同时移入回收站（" + locText + "）";
  } else {
    fileCheckbox.checked = false;
    fileLabel.textContent = "同时移入回收站";
  }

  modal.setAttribute("data-task-id", taskId);
  modal.style.display = "flex";
}

async function deleteTask() {
  var modal = document.getElementById("delete-confirm-modal");
  var taskId = modal.getAttribute("data-task-id");
  var deleteFiles = document.getElementById("delete-with-files").checked;

  if (!taskId) return;

  var result = await apiRequest("POST", "/tasks/" + taskId + "/delete", {
    delete_files: deleteFiles,
  });

  if (result.code === 200) {
    closeModal("delete-confirm-modal");
    closeModal("task-detail-modal");
    loadTasks(_currentTaskPage, _currentTaskStatus);
    if (typeof refreshOverview === "function") refreshOverview();
  } else {
    var message = "操作失败: " + (result.message || "未知错误");
    if (typeof showToast === "function") {
      showToast(message);
    } else {
      console.error(message);
    }
  }
}

document.addEventListener("click", function (e) {
  if (e.target.classList.contains("modal-overlay")) {
    e.target.style.display = "none";
  }
});

document.addEventListener("click", function (e) {
  var tab = e.target.closest(".status-filter-tab");
  if (tab) {
    var tabs = document.querySelectorAll(".status-filter-tab");
    tabs.forEach(function (t) {
      t.classList.remove("active");
    });
    tab.classList.add("active");
    var status = tab.getAttribute("data-status") || "all";
    _currentTaskPage = 1;
    loadTasks(1, status);
  }
});

async function refreshLogs() {
  var result = await apiRequest("GET", "/logs?limit=100");
  if (result.code === 200 && result.data) {
    var logs = result.data.logs || [];
    var container = document.getElementById("log-container");
    if (logs.length === 0) {
      container.innerHTML = '<div class="log-line">暂无日志</div>';
      return;
    }
    container.innerHTML = logs
      .map(function (log) {
        var timestamp = (log.time || "-").substring(11, 19);
        var level = log.level || "INFO";
        var message = log.message || log.raw || JSON.stringify(log);
        var step = log.step || "";
        var taskId = log.task_id || "";
        var levelClass = "log-level-info";
        if (level === "ERROR") levelClass = "log-level-error";
        else if (level === "WARN" || level === "WARNING")
          levelClass = "log-level-warn";
        else if (level === "DEBUG") levelClass = "log-level-debug";
        var stepTag = step ? '<span class="log-step">' + step + "</span> " : "";
        var taskTag = taskId
          ? '<span class="log-task">[' + taskId.substring(0, 8) + "]</span> "
          : "";
        return (
          '<div class="log-line">' +
          '<span class="log-time">' +
          timestamp +
          "</span> " +
          '<span class="' +
          levelClass +
          '">' +
          level +
          "</span> " +
          taskTag +
          stepTag +
          '<span class="log-msg">' +
          escapeHtml(message) +
          "</span>" +
          "</div>"
        );
      })
      .join("");
    container.scrollTop = container.scrollHeight;
  }
}

function _renderScrapeTrace(trace, filename) {
  if (!trace || typeof trace !== "object") {
    return '<div style="padding:12px;color:var(--text-secondary);font-size:13px;">暂无决策路径数据</div>';
  }

  var html = '<div class="scrape-trace-timeline">';

  var steps = [];

  var fc = trace.filename_clean;
  if (fc) {
    steps.push({
      type: "INPUT",
      label: "文件名输入",
      color: "#06B6D4",
      detail: fc.original || fc.clean_title || "-",
      sub:
        "清洗后: " +
        (fc.clean_title || "-") +
        (fc.year ? " (" + fc.year + ")" : "") +
        (fc.removed_items && fc.removed_items.length
          ? " | 移除: " + fc.removed_items.join(", ")
          : ""),
    });
  }

  if (trace.ai_clean) {
    steps.push({
      type: "AI",
      label: "AI 辅助清洗",
      color: "#F59E0B",
      detail: trace.ai_clean.clean_title || "-",
      sub: "方法: " + (trace.ai_clean.method || "ai"),
    });
  }

  var ts = trace.provider_search;
  if (ts) {
    var providerName = trace.provider_type || "TMDb";
    steps.push({
      type: "PROVIDER",
      label: providerName + " 搜索",
      color: "#8B5CF6",
      detail: "查询: " + (ts.query || "-"),
      sub:
        (ts.total_results || 0) +
        " 个结果" +
        (ts.fallback_used ? " (使用了英文回退)" : "") +
        " | 匹配: " +
        (ts.selected_title || "-"),
    });
  }

  var pfr = trace.provider_fallback_reasons;
  if (!ts && pfr && pfr.length > 0) {
    var fallbackRows = pfr.map(function (p) {
      var icon = "";
      var iconColor = "#94A3B8";
      if (p.status === "error") {
        icon = "✗";
        iconColor = "#EF4444";
      } else if (p.status === "no_results") {
        icon = "∅";
        iconColor = "#F59E0B";
      } else if (p.status === "below_threshold") {
        icon = "↓";
        iconColor = "#F59E0B";
      } else if (p.status === "details_error") {
        icon = "⚠";
        iconColor = "#EF4444";
      } else if (p.status === "not_configured") {
        icon = "—";
        iconColor = "#94A3B8";
      } else {
        icon = "?";
        iconColor = "#94A3B8";
      }
      var name = p.display_name || p.provider_type || "未知";
      return (
        '<div style="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid var(--border-color);font-size:12px;">' +
        '<span style="color:' +
        iconColor +
        ';font-weight:600;min-width:16px;text-align:center;">' +
        icon +
        "</span>" +
        '<span style="font-weight:500;color:var(--text-primary);">' +
        escapeHtml(name) +
        "</span>" +
        '<span style="color:var(--text-secondary);">' +
        escapeHtml(p.reason || "未知原因") +
        "</span>" +
        "</div>"
      );
    });
    steps.push({
      type: "WARN",
      label: "Provider 不可用",
      color: "#F59E0B",
      sub: "所有元数据源均不可用，请人工确认候选或检查 Provider 配置",
      extra: fallbackRows.join(""),
    });
  }

  // 三级匹配路径显示
  var matchTrace = trace;
  if (matchTrace && typeof matchTrace === "object") {
    var traceSteps = matchTrace.trace || [];
    if (Array.isArray(traceSteps) && traceSteps.length > 0) {
      for (var ti = 0; ti < traceSteps.length; ti++) {
        var mStep = traceSteps[ti];
        var stepColor = mStep.matched
          ? "#22C55E"
          : mStep.tier === 3
            ? "#F59E0B"
            : "#94A3B8";
        var stepType = mStep.matched ? "MATCH" : "INFO";
        steps.push({
          type: stepType,
          label: "第" + mStep.tier + "级：" + (mStep.name || ""),
          color: stepColor,
          detail: mStep.reason || "",
          sub: mStep.ai_reason || "",
        });
      }
    } else {
      // 无匹配路径信息
      steps.push({
        type: "INFO",
        label: "无匹配路径信息",
        color: "#94A3B8",
        detail: "",
      });
    }
  }

  steps.forEach(function (step, idx) {
    var isLast = idx === steps.length - 1;
    html += '<div class="scrape-trace-step">';
    html +=
      '<div class="scrape-trace-dot" style="background:' +
      step.color +
      ';"></div>';
    if (!isLast) html += '<div class="scrape-trace-line"></div>';
    html += '<div class="scrape-trace-content">';
    html +=
      '<div class="scrape-trace-label" style="color:' +
      step.color +
      ';">' +
      escapeHtml(step.label) +
      "</div>";
    if (step.detail)
      html +=
        '<div class="scrape-trace-detail">' +
        escapeHtml(step.detail) +
        "</div>";
    if (step.sub)
      html +=
        '<div class="scrape-trace-sub">' + escapeHtml(step.sub) + "</div>";
    if (step.extra)
      html += '<div class="scrape-trace-extra">' + step.extra + "</div>";
    html += "</div></div>";
  });

  html += "</div>";
  html += '<div style="margin-top:12px;text-align:center;">';
  html +=
    '<button class="btn btn-secondary btn-sm" onclick="showMatchTraceModal(JSON.parse(decodeURIComponent(this.getAttribute(\'data-trace\'))),this.getAttribute(\'data-filename\'))" data-trace="' +
    encodeURIComponent(JSON.stringify(trace)) +
    '" data-filename="' +
    escapeHtml(filename || "") +
    '">查看匹配路径</button>';
  html += "</div>";
  return html;
}

function escapeHtml(text) {
  if (text == null) return "";
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(String(text)));
  return div.innerHTML;
}

function showMatchTraceModal(trace, filename) {
  var html =
    '<div style="padding:16px;background:rgba(255,255,255,0.02);border-radius:8px;">';
  html += '<h3 style="margin-top:0;">匹配路径详情</h3>';
  html +=
    '<p style="color:#94A3B8;font-size:12px;margin:8px 0 16px;">文件：' +
    escapeHtml(filename || "") +
    "</p>";
  var steps = (trace && typeof trace === "object" && trace.trace) || [];
  if (Array.isArray(steps) && steps.length > 0) {
    html += '<div style="display:flex;flex-direction:column;gap:12px;">';
    for (var i = 0; i < steps.length; i++) {
      var step = steps[i];
      var color = step.matched
        ? "#22C55E"
        : step.tier === 3
          ? "#F59E0B"
          : "#94A3B8";
      html +=
        '<div style="border:1px solid ' +
        color +
        "20;background:" +
        color +
        '08;padding:12px 16px;border-radius:8px;">';
      html +=
        '<div style="font-weight:600;color:' +
        color +
        ';">第' +
        step.tier +
        "级：" +
        escapeHtml(step.name || "") +
        " &nbsp;·&nbsp; " +
        (step.matched ? "✓ 匹配" : "✗ 未匹配") +
        "</div>";
      if (step.reason)
        html +=
          '<div style="margin-top:8px;font-size:13px;line-height:1.6;color:#CBD5E1;">' +
          escapeHtml(step.reason) +
          "</div>";
      if (step.ai_reason)
        html +=
          '<div style="margin-top:8px;font-size:13px;line-height:1.6;color:#06B6D4;border-left:2px solid #06B6D420;padding-left:12px;">AI: ' +
          escapeHtml(step.ai_reason) +
          "</div>";
      html += "</div>";
    }
    html += "</div>";
  } else {
    html += '<p style="color:#94A3B8;">无匹配路径信息</p>';
  }
  html += "</div>";
  if (typeof showAppModal === "function") {
    showAppModal({
      title: "匹配路径",
      body: html,
      actions: [{ label: "关闭", className: "btn btn-secondary" }],
    });
  } else {
    alert(html.replace(/<[^>]+>/g, "\n"));
  }
}

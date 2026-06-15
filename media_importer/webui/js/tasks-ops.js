// tasks-ops.js - rename, reclassify, delete, logs, trace
function copyTaskId(el) {
  var tid = el.getAttribute("data-tid") || "";
  navigator.clipboard
    .writeText(tid)
    .then(function () {
      showToast("任务ID已复制");
    })
    .catch(function () {
      showToast("复制失败", "error");
    });
}

function startRename(taskId) {
  var row = document.getElementById("detail-filename-row");
  if (!row) return;
  var filenameEl = document.getElementById("detail-current-filename");
  var currentName = filenameEl ? filenameEl.textContent : "";
  row.innerHTML =
    '<input type="text" class="detail-rename-input" id="detail-rename-input" value="' +
    escapeHtml(currentName) +
    '">' +
    '<button class="detail-rename-confirm" onclick="submitRename(\'' +
    escapeHtml(taskId) +
    '\')"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg></button>' +
    '<button class="detail-rename-cancel" onclick="cancelRename(\'' +
    escapeHtml(taskId) +
    "','" +
    escapeHtml(currentName) +
    '\')"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>';
  var input = document.getElementById("detail-rename-input");
  if (input) {
    var dotIdx = currentName.lastIndexOf(".");
    if (dotIdx > 0) {
      input.setSelectionRange(0, dotIdx);
    } else {
      input.select();
    }
    input.focus();
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") submitRename(taskId);
      if (e.key === "Escape") cancelRename(taskId, currentName);
    });
  }
}

function cancelRename(taskId, originalName) {
  var row = document.getElementById("detail-filename-row");
  if (!row) return;
  row.innerHTML =
    '<span class="detail-filename-text" id="detail-current-filename">' +
    escapeHtml(originalName) +
    "</span>" +
    '<button class="detail-rename-btn" onclick="startRename(\'' +
    escapeHtml(taskId) +
    '\')" data-tooltip="修改文件名">' +
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>' +
    "</button>";
}

async function submitRename(taskId) {
  var input = document.getElementById("detail-rename-input");
  if (!input) return;
  var newFilename = input.value.trim();
  if (!newFilename) {
    showToast("文件名不能为空", "error");
    return;
  }
  var result = await apiRequest(
    "POST",
    "/tasks/" + encodeURIComponent(taskId) + "/rename",
    {
      new_filename: newFilename,
    },
  );
  if (result.code === 200) {
    showToast("文件重命名成功");
    showTaskDetail(taskId);
    loadTasks();
  } else {
    showToast(result.message || "重命名失败", "error");
  }
}

function buildReclassifyForm(task) {
  var dims = task.scrape_dimensions || {};
  var pathRules = currentConfig.path_rules || [];
  var allDimKeys = new Set();
  pathRules.forEach(function (rule) {
    if (rule.conditions) {
      Object.keys(rule.conditions).forEach(function (k) {
        allDimKeys.add(k);
      });
    }
  });
  if (Object.keys(dims).length > 0) {
    Object.keys(dims).forEach(function (k) {
      allDimKeys.add(k);
    });
  }

  if (allDimKeys.size === 0) return "";

  var html =
    '<div class="detail-field"><div class="detail-field-label">修改分类维度</div><div class="detail-dim-grid" id="reclassify-dim-grid">';
  allDimKeys.forEach(function (key) {
    var currentVal = dims[key] || "";
    var dimLabel = _getDimLabel(key);
    html +=
      '<div class="detail-dim-item">' +
      '<span class="detail-dim-key">' +
      escapeHtml(dimLabel) +
      "</span>" +
      '<input type="text" class="detail-dim-select" id="reclassify-dim-' +
      escapeHtml(key) +
      '" value="' +
      escapeHtml(String(currentVal)) +
      '">' +
      "</div>";
  });
  html +=
    "</div>" +
    '<button class="btn btn-sm btn-primary" style="margin-top:8px" onclick="submitReclassify(\'' +
    escapeHtml(task.task_id) +
    "')\">应用修改</button>" +
    "</div>";
  return html;
}

async function submitReclassify(taskId) {
  var grid = document.getElementById("reclassify-dim-grid");
  if (!grid) return;
  var inputs = grid.querySelectorAll("input");
  var dims = {};
  inputs.forEach(function (inp) {
    var key = inp.id.replace("reclassify-dim-", "");
    var val = inp.value.trim();
    if (val) dims[key] = val;
  });
  await reclassifyTask(taskId, dims);
}

async function showSubtitleDetail(taskId) {
  var result = await apiRequest(
    "GET",
    "/tasks/" + encodeURIComponent(taskId) + "/subtitles",
  );
  if (result.code !== 200 || !result.data) {
    showToast("获取字幕信息失败", "error");
    return;
  }
  var subtitles = result.data.subtitles || [];
  var body = document.getElementById("subtitle-detail-body");

  if (subtitles.length === 0) {
    body.innerHTML =
      '<div class="empty-state"><div class="empty-state-text">无字幕记录</div></div>';
  } else {
    var html =
      '<table class="subtitle-table"><thead><tr>' +
      "<th>文件名</th><th>语言</th><th>状态</th><th>入库路径</th>" +
      "</tr></thead><tbody>";
    subtitles.forEach(function (sub) {
      html +=
        "<tr>" +
        "<td>" +
        escapeHtml(sub.source_filename || "-") +
        "</td>" +
        "<td>" +
        escapeHtml(sub.lang || "-") +
        "</td>" +
        '<td><span class="status-badge status-badge-' +
        (sub.status || "PENDING") +
        '">' +
        getStatusText(sub.status) +
        "</span></td>" +
        '<td class="task-import-path">' +
        (sub.import_path ? escapeHtml(truncate(sub.import_path, 30)) : "-") +
        "</td>" +
        "</tr>";
    });
    html += "</tbody></table>";
    body.innerHTML = html;
  }

  var modal = document.getElementById("subtitle-detail-modal");
  modal.style.display = "flex";
}

function closeModal(modalId) {
  var modal = document.getElementById(modalId);
  if (modal) modal.style.display = "none";
}

var _locationLabels = {
  source: "源目录",
  temp: "中转目录",
  import: "入库目录",
  recycle: "回收站",
  deleted: "已删除",
};

var _locationFileLabels = {
  source: "源文件",
  temp: "中转文件",
  import: "入库文件",
  recycle: "回收站文件",
  deleted: "文件",
};

var _locationWarnings = {
  source: "源文件将移入回收站",
  temp: "中转文件将移入回收站",
  import: "⚠️ 已入库文件将移入回收站，请确认不再需要此影视文件",
  recycle: "将永久删除回收站中的文件，删除后无法恢复",
  deleted: "",
};


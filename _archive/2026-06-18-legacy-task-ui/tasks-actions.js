// tasks-actions.js - task pagination and action buttons
function renderPagination(totalPages, currentPage, total) {
  var container = document.getElementById("pagination-controls");
  if (!container) return;

  var html = "";
  html +=
    '<button class="pagination-btn" onclick="loadTasks(1)" ' +
    (currentPage <= 1 ? "disabled" : "") +
    ">首页</button>";
  html +=
    '<button class="pagination-btn" onclick="loadTasks(' +
    (currentPage - 1) +
    ')" ' +
    (currentPage <= 1 ? "disabled" : "") +
    ">上一页</button>";

  var startPage = Math.max(1, currentPage - 2);
  var endPage = Math.min(totalPages, currentPage + 2);
  for (var p = startPage; p <= endPage; p++) {
    html +=
      '<button class="pagination-btn ' +
      (p === currentPage ? "active" : "") +
      '" onclick="loadTasks(' +
      p +
      ')">' +
      p +
      "</button>";
  }

  html +=
    '<button class="pagination-btn" onclick="loadTasks(' +
    (currentPage + 1) +
    ')" ' +
    (currentPage >= totalPages ? "disabled" : "") +
    ">下一页</button>";
  html +=
    '<button class="pagination-btn" onclick="loadTasks(' +
    totalPages +
    ')" ' +
    (currentPage >= totalPages ? "disabled" : "") +
    ">末页</button>";
  html +=
    '<span class="pagination-info">第 ' +
    currentPage +
    "/" +
    totalPages +
    " 页 (共 " +
    (total || 0) +
    " 条)</span>";

  container.innerHTML = html;
}

function formatTimeBrief(task) {
  if (!task.started_at) {
    return task.created_at
      ? task.created_at.substring(5, 16).replace("T", " ")
      : "-";
  }
  var start = task.started_at.substring(5, 16).replace("T", " ");
  if (task.completed_at) {
    var end = task.completed_at.substring(5, 16).replace("T", " ");
    return start + " ~ " + end;
  }
  return start + " ...";
}

function formatTimeDetail(task) {
  var parts = [];
  if (task.created_at)
    parts.push("创建: " + task.created_at.replace("T", " ").substring(0, 19));
  if (task.started_at)
    parts.push("开始: " + task.started_at.replace("T", " ").substring(0, 19));
  if (task.completed_at)
    parts.push("完成: " + task.completed_at.replace("T", " ").substring(0, 19));
  return parts.join("\n") || "-";
}

function getStatusText(status) {
  var map = {
    SUCCESS: "完成",
    FAILED: "失败",
    PROCESSING: "处理中",
    PENDING: "待处理",
    SKIPPED: "完成 · 跳过",
    CONFIRMING: "处理中 · 需确认",
  };
  return map[status] || status || "未知";
}

function truncate(text, length) {
  if (!text) return "";
  return text.length > length ? text.substring(0, length) + "..." : text;
}

async function retryTask(taskId) {
  var result = await apiRequest(
    "POST",
    "/tasks/" + encodeURIComponent(taskId) + "/retry",
  );
  if (result.code === 200) {
    showToast("任务已重试并开始执行");
    loadTasks();
  } else {
    showToast(result.message || "操作失败", "error");
  }
}

async function confirmTask(taskId) {
  var result = await apiRequest(
    "POST",
    "/tasks/" + encodeURIComponent(taskId) + "/confirm",
  );
  if (result.code === 200) {
    showToast("任务确认入库成功");
    loadTasks();
  } else {
    showToast(result.message || "确认失败", "error");
  }
}

async function reclassifyTask(taskId, dimensions) {
  var result = await apiRequest(
    "POST",
    "/tasks/" + encodeURIComponent(taskId) + "/reclassify",
    {
      dimensions: dimensions,
    },
  );
  if (result.code === 200) {
    showToast("重新分类完成");
    loadTasks();
    closeModal("task-detail-modal");
  } else {
    showToast(result.message || "重新分类失败", "error");
  }
}

async function ignoreTask(taskId) {
  if (!confirm("确认忽略该任务？")) return;
  var result = await apiRequest(
    "POST",
    "/tasks/" + encodeURIComponent(taskId) + "/ignore",
  );
  if (result.code === 200) {
    showToast("任务已忽略");
    loadTasks();
  } else {
    showToast(result.message || "操作失败", "error");
  }
}


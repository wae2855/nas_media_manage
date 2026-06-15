// config-recycle-list.js - recycle list and cleaner preview
async function loadRecycleList() {
  var partition = document.getElementById("recycle-filter-partition").value;
  var reason = document.getElementById("recycle-filter-reason").value;
  var params = [];
  if (partition) params.push("partition=" + encodeURIComponent(partition));
  if (reason) params.push("reason=" + encodeURIComponent(reason));
  var query = params.length > 0 ? "?" + params.join("&") : "";

  var result = await apiRequest("GET", "/recycle/list" + query);
  if (!result || result.code !== 200 || !result.data) {
    showToast(
      "加载回收站列表失败: " + (result ? result.message : "未知错误"),
      "error",
    );
    return;
  }

  var data = result.data;
  var items = data.items || [];
  _recycleListData = items;

  document.getElementById("recycle-total-count").textContent =
    data.total_count || data.total || items.length;
  document.getElementById("recycle-total-size").textContent = _formatFileSize(
    data.total_size || 0,
  );

  var partitionStats = data.partition_stats || {};
  var statsHtml = "";
  var partitionKeys = Object.keys(partitionStats);
  for (var i = 0; i < partitionKeys.length; i++) {
    var pk = partitionKeys[i];
    var ps = partitionStats[pk];
    var count = typeof ps === "object" ? ps.count || 0 : ps;
    var size = typeof ps === "object" ? ps.size || 0 : 0;
    statsHtml +=
      '<span class="recycle-stat-partition">' +
      _escapeHtml(pk) +
      ": " +
      count +
      " 文件" +
      (size > 0 ? " / " + _formatFileSize(size) : "") +
      "</span>";
  }
  document.getElementById("recycle-partition-stats").innerHTML = statsHtml;

  var partitionSelect = document.getElementById("recycle-filter-partition");
  var currentPartition = partitionSelect.value;
  var partitions = data.partitions || [];
  var optHtml = '<option value="">全部分区</option>';
  for (var i = 0; i < partitions.length; i++) {
    optHtml +=
      '<option value="' +
      _escapeHtml(partitions[i]) +
      '"' +
      (partitions[i] === currentPartition ? " selected" : "") +
      ">" +
      _escapeHtml(partitions[i]) +
      "</option>";
  }
  partitionSelect.innerHTML = optHtml;

  var reasonSelect = document.getElementById("recycle-filter-reason");
  var currentReason = reasonSelect.value;
  var reasons = data.reasons || [];
  var reasonHtml = '<option value="">全部原因</option>';
  for (var i = 0; i < reasons.length; i++) {
    reasonHtml +=
      '<option value="' +
      _escapeHtml(reasons[i]) +
      '"' +
      (reasons[i] === currentReason ? " selected" : "") +
      ">" +
      _escapeHtml(reasons[i]) +
      "</option>";
  }
  reasonSelect.innerHTML = reasonHtml;

  var tbody = document.getElementById("recycle-table-body");
  if (items.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="7" class="empty-row">暂无回收站数据</td></tr>';
    return;
  }

  var html = "";
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var itemId = item.id || item.recycle_path || "";
    var zoneAttr = _getZoneAttr(item.partition || item.zone_name || "");
    var sizeBytes =
      item.size || (item.file_size_mb ? item.file_size_mb * 1024 * 1024 : 0);
    html += '<tr data-recycle-id="' + _escapeHtml(itemId) + '">';
    html +=
      '<td><input type="checkbox" class="recycle-item-check" value="' +
      _escapeHtml(itemId) +
      '"></td>';
    html +=
      '<td style="font-size:12px;word-break:break-all;">' +
      _escapeHtml(item.original_path || "") +
      "</td>";
    html +=
      '<td><span class="recycle-zone-tag" data-zone="' +
      zoneAttr +
      '">' +
      _escapeHtml(item.partition || item.zone_name || "") +
      "</span></td>";
    html +=
      '<td><span class="recycle-reason-tag" title="' +
      _escapeHtml(item.reason || "") +
      '">' +
      _escapeHtml(item.reason || "") +
      "</span></td>";
    html += "<td>" + _formatFileSize(sizeBytes) + "</td>";
    html +=
      '<td style="font-size:12px;">' +
      _escapeHtml(item.moved_at || "") +
      "</td>";
    html += '<td><div class="recycle-action-btns">';
    html +=
      '<button class="btn btn-primary btn-sm" onclick="restoreRecycleItem(\'' +
      _escapeJs(itemId) +
      "')\">";
    html +=
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:12px;height:12px;"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>恢复</button>';
    html +=
      '<button class="btn btn-danger btn-sm" onclick="deleteRecycleItem(\'' +
      _escapeJs(itemId) +
      "')\">";
    html +=
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:12px;height:12px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>删除</button>';
    html += "</div></td>";
    html += "</tr>";
  }
  tbody.innerHTML = html;
}

function _escapeJs(s) {
  return String(s)
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"');
}

function _formatFileSize(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  var units = ["B", "KB", "MB", "GB", "TB"];
  var i = Math.floor(Math.log(bytes) / Math.log(1024));
  if (i >= units.length) i = units.length - 1;
  if (i < 0) i = 0;
  return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + " " + units[i];
}

function toggleRecycleSelectAll() {
  var headerCheck = document.getElementById("recycle-header-check");
  var selectAllCheck = document.getElementById("recycle-select-all");
  var checked = headerCheck
    ? headerCheck.checked
    : selectAllCheck
      ? selectAllCheck.checked
      : false;
  var checks = document.querySelectorAll(".recycle-item-check");
  checks.forEach(function (c) {
    c.checked = checked;
  });
  if (selectAllCheck) selectAllCheck.checked = checked;
  if (headerCheck) headerCheck.checked = checked;
}

function toggleRecycleInvert() {
  var checks = document.querySelectorAll(".recycle-item-check");
  checks.forEach(function (c) {
    c.checked = !c.checked;
  });
}

function _getSelectedRecycleIds() {
  var ids = [];
  var checks = document.querySelectorAll(".recycle-item-check:checked");
  checks.forEach(function (c) {
    ids.push(c.value);
  });
  return ids;
}

async function restoreRecycleItem(id) {
  _pendingRestoreItems = [id];
  _showRestoreConfirmModal([id]);
}

async function batchRestoreRecycleItems() {
  var ids = _getSelectedRecycleIds();
  if (ids.length === 0) {
    showToast("请先选择要恢复的文件", "warning");
    return;
  }
  _pendingRestoreItems = ids;
  _showRestoreConfirmModal(ids);
}

function _showRestoreConfirmModal(ids) {
  var fileListHtml = "";
  for (var i = 0; i < ids.length; i++) {
    var item = null;
    for (var j = 0; j < _recycleListData.length; j++) {
      if (
        _recycleListData[j].id === ids[i] ||
        _recycleListData[j].recycle_path === ids[i]
      ) {
        item = _recycleListData[j];
        break;
      }
    }
    if (item) {
      fileListHtml +=
        '<div style="padding:4px 0;font-size:13px;border-bottom:1px solid var(--border-color);">' +
        _escapeHtml(item.original_path || item.id || item.recycle_path) +
        "</div>";
    }
  }
  document.getElementById("recycle-restore-file-list").innerHTML = fileListHtml;
  document.getElementById("recycle-restore-conflict-warning").style.display =
    "none";
  document.getElementById("recycle-restore-modal").style.display = "flex";
}

async function confirmRestoreRecycleItems() {
  var conflictMode =
    document.getElementById("recycle-restore-conflict-mode").value || "skip";
  var result = await restoreRecycleItems(_pendingRestoreItems, conflictMode);
  if (result) {
    closeModal("recycle-restore-modal");
    loadRecycleList();
  }
}

async function restoreRecycleItems(items, conflictMode) {
  var result = await apiRequest("POST", "/recycle/restore", {
    items: items,
    conflict_mode: conflictMode || "skip",
  });
  if (result.code === 200 || result.code === 207) {
    var data = result.data || {};
    var failed = data.failed || [];
    if (failed.length > 0 && result.code === 207) {
      var conflictList = document.getElementById(
        "recycle-restore-conflict-list",
      );
      var html = "";
      for (var i = 0; i < failed.length; i++) {
        html +=
          '<div style="padding:4px 0;font-size:13px;color:var(--danger-color);">' +
          _escapeHtml(failed[i].message || failed[i].recycle_path || "") +
          "</div>";
      }
      conflictList.innerHTML = html;
      document.getElementById(
        "recycle-restore-conflict-warning",
      ).style.display = "block";
      showToast(result.message || "部分恢复失败", "warning");
      return false;
    }
    showToast(result.message || "恢复成功", "success");
    return true;
  } else {
    showToast(result.message || "恢复失败", "error");
    return false;
  }
}

async function deleteRecycleItem(id) {
  showConfirm(
    "永久删除",
    "确定要永久删除此文件吗？此操作不可恢复！",
    async function () {
      var result = await deleteRecycleItems([id]);
      if (result) loadRecycleList();
    },
  );
}

async function batchDeleteRecycleItems() {
  var ids = _getSelectedRecycleIds();
  if (ids.length === 0) {
    showToast("请先选择要删除的文件", "warning");
    return;
  }
  showConfirm(
    "批量永久删除",
    "确定要永久删除选中的 " + ids.length + " 个文件吗？此操作不可恢复！",
    async function () {
      var result = await deleteRecycleItems(ids);
      if (result) loadRecycleList();
    },
  );
}

async function deleteRecycleItems(items) {
  var result = await apiRequest("POST", "/recycle/delete", { items: items });
  if (result.code === 200) {
    showToast(result.message || "删除成功", "success");
    return true;
  } else {
    showToast(result.message || "删除失败", "error");
    return false;
  }
}

async function previewCleanerResult() {
  var resultEl = document.getElementById("cleaner-preview-result");
  resultEl.style.display = "inline-block";
  resultEl.className = "test-result loading";
  resultEl.textContent = "预览中...";

  var result = await apiRequest("GET", "/source-cleaner/preview");
  if (result.code === 200 && result.data) {
    var data = result.data;
    var items = data.items || [];
    var total = items.length;
    resultEl.className = "test-result success";
    resultEl.textContent = "✓ 将清理 " + total + " 项";

    var summaryEl = document.getElementById("sc-preview-summary");
    var treeEl = document.getElementById("sc-preview-tree");

    var categories = {};
    var totalSize = 0;
    for (var i = 0; i < items.length; i++) {
      var cat = items[i].category || "other";
      if (!categories[cat]) categories[cat] = { count: 0, size: 0, label: cat };
      categories[cat].count++;
      categories[cat].size += items[i].size_mb || 0;
      totalSize += items[i].size_mb || 0;
    }

    var catLabels = {
      junk_video: "垃圾视频",
      delete_extension: "删除后缀",
      blacklist_pattern: "黑名单匹配",
      blacklist_dir: "黑名单目录",
      empty_dir: "空目录",
      non_media: "非影视文件",
      ai_delete: "AI判定删除",
    };

    var summaryHtml =
      '<div class="sc-preview-stat"><span class="sc-preview-stat-num">' +
      total +
      '</span><span class="sc-preview-stat-label">项将清理</span></div>';
    summaryHtml +=
      '<div class="sc-preview-stat"><span class="sc-preview-stat-num">' +
      totalSize.toFixed(1) +
      '</span><span class="sc-preview-stat-label">MB</span></div>';
    var catKeys = Object.keys(categories);
    for (var j = 0; j < catKeys.length; j++) {
      var c = categories[catKeys[j]];
      summaryHtml +=
        '<div class="sc-preview-stat"><span class="sc-preview-stat-num">' +
        c.count +
        '</span><span class="sc-preview-stat-label">' +
        (catLabels[catKeys[j]] || catKeys[j]) +
        "</span></div>";
    }
    summaryEl.innerHTML = summaryHtml;

    var sourceDir = currentConfig.source_dir || "";

    var tree = buildDirTree(items, sourceDir);
    var rootName = sourceDir
      ? sourceDir
          .split("/")
          .filter(function (s) {
            return s;
          })
          .pop() || sourceDir
      : "源目录";
    treeEl.innerHTML =
      '<div class="sc-tree-line sc-tree-root"><span class="sc-tree-folder">📂 ' +
      escapeHtml(rootName) +
      "</span></div>" +
      renderDirTree(tree, "");

    document.getElementById("sc-preview-modal").style.display = "flex";
  } else {
    resultEl.className = "test-result error";
    resultEl.textContent = "✗ " + (result.message || "预览失败");
  }
}

function buildDirTree(items, sourceDir) {
  var root = { name: "", children: {}, items: [] };
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var path = item.path || "";
    var relPath =
      sourceDir && path.startsWith(sourceDir)
        ? path.substring(sourceDir.length)
        : path;
    relPath = relPath.replace(/^\/+/, "");
    var parts = relPath.split("/");

    var node = root;
    for (var p = 0; p < parts.length - 1; p++) {
      if (!node.children[parts[p]]) {
        node.children[parts[p]] = { name: parts[p], children: {}, items: [] };
      }
      node = node.children[parts[p]];
    }
    node.items.push({
      name: parts[parts.length - 1],
      category: item.category,
      reason: item.reason,
      size_mb: item.size_mb,
      source: item.source,
    });
  }
  return root;
}

var _scCategoryIcons = {
  junk_video: "🎬",
  delete_extension: "📄",
  blacklist_pattern: "🚫",
  blacklist_dir: "📁",
  empty_dir: "📂",
  non_media: "📎",
  ai_delete: "🤖",
};

function renderDirTree(node, prefix) {
  var html = "";
  var childKeys = Object.keys(node.children).sort();
  var itemIdx = 0;

  for (var c = 0; c < childKeys.length; c++) {
    var key = childKeys[c];
    var child = node.children[key];
    var isLastDir = c === childKeys.length - 1 && node.items.length === 0;
    var connector = isLastDir ? "└── " : "├── ";
    var childPrefix = isLastDir ? "    " : "│   ";

    html += '<div class="sc-tree-line">';
    html += '<span class="sc-tree-indent">' + escapeHtml(prefix) + "</span>";
    html += '<span class="sc-tree-connector">' + connector + "</span>";
    html += '<span class="sc-tree-folder">📁 ' + escapeHtml(key) + "</span>";
    html += "</div>";

    html += renderDirTree(child, prefix + childPrefix);
  }

  for (var i = 0; i < node.items.length; i++) {
    var item = node.items[i];
    var isLast = i === node.items.length - 1 && true;
    var conn = isLast ? "└── " : "├── ";
    var icon = _scCategoryIcons[item.category] || "📄";

    html +=
      '<div class="sc-tree-line" data-category="' +
      escapeHtml(item.category) +
      '">';
    html += '<span class="sc-tree-indent">' + escapeHtml(prefix) + "</span>";
    html += '<span class="sc-tree-connector">' + conn + "</span>";
    html += '<span class="sc-tree-icon">' + icon + "</span>";
    html += '<span class="sc-tree-file">' + escapeHtml(item.name) + "</span>";
    if (item.size_mb > 0) {
      html +=
        '<span class="sc-tree-size">' + item.size_mb.toFixed(1) + "MB</span>";
    }
    html +=
      '<span class="sc-tree-reason">' +
      escapeHtml(item.reason || "") +
      "</span>";
    html += "</div>";
  }

  return html;
}

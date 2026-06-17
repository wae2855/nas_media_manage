// cinema-task-detail-open.js - task detail modal opening
function openTaskDetail(taskId) {
  return openTaskDetailImpl(taskId, true);
}

async function openTaskDetailImpl(taskId, refreshListAfter) {
  const detailResult = await requestApi(
    "GET",
    `/tasks/${encodeURIComponent(taskId)}`,
  );
  if (detailResult.code !== 200 || !detailResult.data?.task) {
    showToast(detailResult.message || "获取任务详情失败");
    return;
  }
  const task = detailResult.data.task;
  const subtitleResult = await requestApi(
    "GET",
    `/tasks/${encodeURIComponent(taskId)}/subtitles`,
  );
  const subtitles =
    subtitleResult.code === 200 && subtitleResult.data
      ? subtitleResult.data.subtitles || []
      : [];
  const originalFilename = taskFileName(task);
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  const isAwaitReview = status === "PENDING" && stage === "AWAIT_REVIEW";

  const perm = getTaskEditPermission(task);
  const taskIdForClosure = taskId;

  // 分类维度（可编辑，去除预览按钮）
  const dimSectionHtml = perm.canEditDimensions
    ? `<div class="cinema-modal-block">
                <h4>分类维度</h4>
                <div class="cinema-modal-grid">${buildTaskDimensionsForm(task, true, true)}</div>
           </div>`
    : "";

  // 入库预览区（待确认时显示）
  const importPath = task.import_path || "";
  const finalFilename = task.final_filename || taskFileName(task);
  const importPreviewHtml = isAwaitReview
    ? `<div class="cinema-modal-block">
                <div class="cinema-modal-section-head">
                    <h4>入库预览</h4>
                </div>
                <div class="cinema-import-preview" id="import-preview-box">
                    <div class="sim-kv"><span class="sim-k">文件名</span><span class="sim-v sim-v-highlight">${escapeHtml(finalFilename)}</span></div>
                    ${importPath ? `<div class="sim-kv"><span class="sim-k">路径</span><span class="sim-v sim-v-highlight">${escapeHtml(importPath)}</span></div>` : ""}
                </div>
           </div>`
    : "";

  // 操作按钮区（待确认时显示）
  const actionHtml = isAwaitReview
    ? `<div class="cinema-modal-block">
                <div class="cinema-modal-save-row" style="flex-wrap:wrap;gap:8px">
                    <button id="btn-scrape-manual" type="button" class="btn btn-primary" style="background:var(--gold);border-color:var(--gold);color:#fff">手动刮削</button>
                    <div style="flex:1"></div>
                    <button id="btn-save-import" type="button" class="btn btn-primary">保存</button>
                    <button id="btn-confirm-import" type="button" class="btn btn-success">确认入库，开始移动文件</button>
                    <div id="import-error-area" class="modal-error-area" style="display:none;width:100%"></div>
                </div>
           </div>`
    : "";

  const stateHintHtml = `<div class="cinema-modal-save-bar">
            <span class="task-status-capsule" style="display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${escapeHtml(perm.statusColor)}18;color:${escapeHtml(perm.statusColor)}">${escapeHtml(perm.statusLabel)}</span>
            <small class="task-permission-hint">${escapeHtml(perm.stateLabel)}</small>
       </div>`;

  const body = `
        <div class="cinema-modal-stack">
            <div class="cinema-modal-summary">
                <div><strong>${escapeHtml(taskDisplayTitle(task))}</strong><span>${escapeHtml(getTaskStatusText(task.status, task.stage))}</span></div>
                <p>${escapeHtml(taskDescription(task))}</p>
                <small>源文件：${escapeHtml(originalFilename)}</small>
                ${task.source_path ? `<small>源路径：${escapeHtml(task.source_path)}</small>` : ""}
                ${task.import_video_path ? `<small>入库路径：${escapeHtml(task.import_video_path)}</small>` : ""}
            </div>
            ${buildFailureSection(task)}
            ${buildScrapeTraceSection(task)}
            ${dimSectionHtml}
            ${importPreviewHtml}
            ${actionHtml}
            <div class="cinema-modal-block">
                <h4>字幕记录</h4>
                ${buildSubtitleTable(subtitles)}
            </div>
            ${stateHintHtml}
        </div>`;

  const actions = [{ label: "关闭", className: "btn btn-secondary" }];

  showAppModal({
    title: "任务详情",
    body,
    actions,
  });

  // 手动刮削按钮
  const btnScrapeManual = document.getElementById("btn-scrape-manual");
  if (btnScrapeManual) {
    var scrapeRes = task.scrape_result || {};
    var cleanTitle =
      (scrapeRes.clean_result && scrapeRes.clean_result.clean_title) || "";
    btnScrapeManual.addEventListener("click", function () {
      openScrapeSearchModal(taskIdForClosure, cleanTitle);
    });
  }

  // 保存按钮 — 调 /preview 持久化后刷新详情
  const btnSaveImport = document.getElementById("btn-save-import");
  if (btnSaveImport) {
    btnSaveImport.addEventListener("click", async function () {
      setImportError("");
      var dims = getCurrentDimensionValues(task);
      var body = { dimensions: dims };
      try {
        var result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskIdForClosure)}/preview`,
          body,
        );
        if (result.code === 200) {
          showToast("已保存，入库预览已更新");
          removeAppModal();
          await openTaskDetailImpl(taskIdForClosure, true);
          await Promise.all([loadTaskList(), loadDashboardOverview()]);
        } else {
          setImportError(result.message || "保存失败");
        }
      } catch (e) {
        setImportError(e.message || "网络错误");
      }
    });
  }

  // 确认入库按钮 — 真实移动文件
  const btnConfirmImport = document.getElementById("btn-confirm-import");
  if (btnConfirmImport) {
    btnConfirmImport.addEventListener("click", async function () {
      setImportError("");
      var dims = getCurrentDimensionValues(task);
      // 先保存最新维度
      await requestApi(
        "POST",
        `/tasks/${encodeURIComponent(taskIdForClosure)}/preview`,
        { dimensions: dims },
      );
      // 再确认入库
      var result = await requestApi(
        "POST",
        `/tasks/${encodeURIComponent(taskIdForClosure)}/confirm`,
      );
      if (result.code === 200) {
        showToast("入库成功");
        removeAppModal();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
      } else {
        setImportError(result.message || "入库失败");
      }
    });
  }

  function setImportError(msg) {
    const errEl = document.getElementById("import-error-area");
    if (!errEl) return;
    if (!msg) {
      errEl.style.display = "none";
      errEl.textContent = "";
      return;
    }
    errEl.style.display = "block";
    errEl.textContent = msg;
  }

  // 收集当前表单维度值
  function getCurrentDimensionValues(task) {
    var dims = {};
    var multiDimNames = {};
    document
      .querySelectorAll("input[type=checkbox][data-task-dim]")
      .forEach(function (cb) {
        var dimName = cb.dataset.taskDim;
        if (!multiDimNames[dimName]) multiDimNames[dimName] = [];
        if (cb.checked) multiDimNames[dimName].push(cb.value);
      });
    for (var dimName in multiDimNames) {
      if (multiDimNames[dimName].length)
        dims[dimName] = multiDimNames[dimName].join("|");
    }
    document
      .querySelectorAll(
        "select[data-task-dim], input[type=text][data-task-dim]",
      )
      .forEach(function (input) {
        var val = parseRuleConditionValue(input.value);
        if (val) dims[input.dataset.taskDim] = val;
      });
    return dims;
  }
}

// 手动刮削弹窗 — 左列表 + 右详情（参考 TMDB 预览弹窗）
function openScrapeSearchModal(taskId, defaultQuery) {
  var existing = document.getElementById("scrape-search-overlay");
  if (existing) existing.remove();

  var overlay = document.createElement("div");
  overlay.id = "scrape-search-overlay";
  overlay.className = "cinema-modal-overlay";
  overlay.innerHTML =
    '<div class="cinema-modal tmdb-preview-modal-content" style="max-width:900px">' +
    '<div class="cinema-modal-header">' +
    "<h3>手动刮削</h3>" +
    '<button type="button" class="cinema-modal-close" aria-label="关闭">×</button>' +
    "</div>" +
    '<div class="tmdb-preview-toolbar">' +
    '<input type="text" id="scrape-search-query" placeholder="输入影视名称..." class="tmdb-preview-input" value="' +
    escapeHtml(defaultQuery || "") +
    '" />' +
    '<button class="btn btn-primary btn-sm" id="btn-scrape-search-exec" type="button">搜索</button>' +
    "</div>" +
    '<div class="tmdb-preview-panels">' +
    '<div class="tmdb-preview-left">' +
    '<div id="scrape-search-results" class="tmdb-search-results"></div>' +
    "</div>" +
    '<div class="tmdb-preview-right">' +
    '<div id="scrape-search-detail" class="tmdb-detail-container">' +
    '<div class="tmdb-preview-placeholder">点击左侧搜索结果查看详情</div>' +
    "</div>" +
    "</div>" +
    "</div>" +
    "</div>";

  overlay.addEventListener("click", function (event) {
    if (event.target === overlay) overlay.remove();
  });
  overlay
    .querySelector(".cinema-modal-close")
    .addEventListener("click", function () {
      overlay.remove();
    });
  document.body.appendChild(overlay);

  var queryInput = document.getElementById("scrape-search-query");
  var searchBtn = document.getElementById("btn-scrape-search-exec");
  queryInput.focus();
  queryInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") doScrapeSearch(taskId);
  });
  searchBtn.addEventListener("click", function () {
    doScrapeSearch(taskId);
  });

  // 如果预填了查询词，自动搜索
  if (defaultQuery && defaultQuery.trim()) {
    setTimeout(function () {
      doScrapeSearch(taskId);
    }, 200);
  }
}

async function doScrapeSearch(taskId) {
  var query = String(
    document.getElementById("scrape-search-query")?.value || "",
  ).trim();
  var resultsEl = document.getElementById("scrape-search-results");
  var detailEl = document.getElementById("scrape-search-detail");
  var btn = document.getElementById("btn-scrape-search-exec");

  if (!query) {
    resultsEl.innerHTML =
      '<div class="tmdb-preview-error">请输入影视名称</div>';
    return;
  }

  btn.disabled = true;
  resultsEl.innerHTML = '<div class="tmdb-preview-loading">搜索中...</div>';
  detailEl.innerHTML =
    '<div class="tmdb-preview-placeholder">点击左侧搜索结果查看详情</div>';

  var result = await requestApi(
    "POST",
    `/tasks/${encodeURIComponent(taskId)}/scrape-search`,
    {
      query: query,
    },
  );
  btn.disabled = false;

  if (result.code !== 200 || !result.data?.candidates?.length) {
    resultsEl.innerHTML =
      '<div class="tmdb-preview-error">' +
      escapeHtml(result.message || "未找到匹配结果") +
      "</div>";
    return;
  }

  var candidates = result.data.candidates;
  resultsEl.innerHTML = candidates
    .map(function (c, idx) {
      return (
        '<div class="tmdb-scrape-card" data-cidx="' +
        idx +
        "\" style=\"padding:10px;cursor:pointer;border-radius:6px;margin-bottom:4px;transition:background 120ms;border:1px solid transparent\" onmouseenter=\"this.style.background='rgba(255,255,255,0.06)'\" onmouseleave=\"var s=this.parentNode.querySelector('.tmdb-scrape-card--active'); if(s!==this){this.style.background='';this.style.borderColor='transparent'}\">" +
        "<div>" +
        '<span style="font-weight:600">' +
        escapeHtml(c.title) +
        " (" +
        (c.year || "?") +
        ")</span>" +
        '<span style="font-size:11px;color:var(--muted);margin-left:8px">' +
        escapeHtml(c.provider_type || "") +
        (c.vote_average ? " ★" + c.vote_average : "") +
        "</span>" +
        "</div>" +
        '<div style="font-size:12px;color:var(--text-secondary);margin-top:2px">' +
        escapeHtml(
          c.original_title && c.original_title !== c.title
            ? c.original_title
            : "",
        ) +
        "</div>" +
        "</div>"
      );
    })
    .join("");

  var selectedIdx = -1;
  resultsEl.querySelectorAll(".tmdb-scrape-card").forEach(function (card) {
    card.addEventListener("click", function () {
      var idx = parseInt(card.dataset.cidx);
      var c = candidates[idx];
      if (!c) return;

      // 高亮选中
      resultsEl.querySelectorAll(".tmdb-scrape-card").forEach(function (el) {
        el.classList.remove("tmdb-scrape-card--active");
        el.style.background = "";
        el.style.borderColor = "transparent";
      });
      card.classList.add("tmdb-scrape-card--active");
      card.style.background = "rgba(6,182,212,0.12)";
      card.style.borderColor = "rgba(6,182,212,0.4)";
      selectedIdx = idx;

      // 渲染右侧详情
      renderScrapeCandidateDetail(c, taskId);
    });
  });
}

function renderScrapeCandidateDetail(candidate, taskId) {
  var detailEl = document.getElementById("scrape-search-detail");
  if (!detailEl) return;

  detailEl.innerHTML =
    "<div>" +
    '<div class="tmdb-detail-group" style="margin-top:0">' +
    '<div class="tmdb-detail-group-header"><span class="tmdb-detail-group-arrow">▼</span> 基本信息</div>' +
    '<div class="tmdb-detail-group-body">' +
    '<div class="tmdb-detail-row"><span class="tmdb-detail-key">标题</span><span class="tmdb-detail-val">' +
    escapeHtml(candidate.title) +
    "</span></div>" +
    '<div class="tmdb-detail-row"><span class="tmdb-detail-key">原名</span><span class="tmdb-detail-val">' +
    escapeHtml(candidate.original_title || "—") +
    "</span></div>" +
    '<div class="tmdb-detail-row"><span class="tmdb-detail-key">年份</span><span class="tmdb-detail-val">' +
    escapeHtml(String(candidate.year || "—")) +
    "</span></div>" +
    '<div class="tmdb-detail-row"><span class="tmdb-detail-key">类型</span><span class="tmdb-detail-val">' +
    escapeHtml(candidate.media_type || "—") +
    "</span></div>" +
    '<div class="tmdb-detail-row"><span class="tmdb-detail-key">来源</span><span class="tmdb-detail-val">' +
    escapeHtml(candidate.provider_type || "—") +
    ' <span class="tmdb-preview-tag">★' +
    escapeHtml(String(candidate.vote_average || "—")) +
    "</span></span></div>" +
    "</div>" +
    "</div>" +
    '<div class="tmdb-detail-group">' +
    '<div class="tmdb-detail-group-header"><span class="tmdb-detail-group-arrow">▼</span> 简介</div>' +
    '<div class="tmdb-detail-group-body">' +
    '<div class="tmdb-detail-row"><span class="tmdb-detail-val">' +
    escapeHtml(candidate.overview || "暂无简介") +
    "</span></div>" +
    "</div>" +
    "</div>" +
    (candidate.poster_url
      ? '<div style="margin-top:12px"><img src="' +
        escapeHtml(candidate.poster_url) +
        '" style="max-width:200px;border-radius:6px" onerror="this.style.display=\'none\'"></div>'
      : "") +
    '<div style="margin-top:16px">' +
    '<button class="btn btn-primary" id="btn-confirm-candidate" style="width:100%">确定选择此条目</button>' +
    "</div>" +
    "</div>";

  // 折叠组切换
  detailEl
    .querySelectorAll(".tmdb-detail-group-header")
    .forEach(function (header) {
      header.addEventListener("click", function () {
        this.parentElement.classList.toggle("collapsed");
      });
    });

  // 确定按钮
  var confirmBtn = document.getElementById("btn-confirm-candidate");
  if (confirmBtn) {
    confirmBtn.addEventListener("click", async function () {
      confirmBtn.disabled = true;
      confirmBtn.textContent = "应用中...";
      try {
        var result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskId)}/preview`,
          {
            title_cn: candidate.title,
            title_en: candidate.original_title || "",
            year: String(candidate.year || ""),
          },
        );
        if (result.code === 200) {
          showToast("已应用刮削结果，请查看入库预览");
          var overlay = document.getElementById("scrape-search-overlay");
          if (overlay) overlay.remove();
          removeAppModal();
          await openTaskDetailImpl(taskId, true);
          await Promise.all([loadTaskList(), loadDashboardOverview()]);
        } else {
          showToast("应用失败: " + (result.message || "未知错误"), "error");
          confirmBtn.disabled = false;
          confirmBtn.textContent = "确定选择此条目";
        }
      } catch (e) {
        showToast("网络错误", "error");
        confirmBtn.disabled = false;
        confirmBtn.textContent = "确定选择此条目";
      }
    });
  }
}

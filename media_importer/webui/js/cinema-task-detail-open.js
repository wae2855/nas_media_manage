// cinema-task-detail-open.js - task detail modal opening
function openTaskDetail(taskId) {
  return openTaskDetailImpl(taskId, true);
}

function formatConflictBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes) return "未知";
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function buildTargetLibraryConflict(task) {
  const conflict = targetLibraryConflictOf(task);
  if (!conflict) return "";
  const reason =
    conflict.conflict_type === "target_path"
      ? "准备写入的位置已经有同名文件"
      : "识别到片库中已有同一影片";
  const fileCard = (label, file, path, size, resolution, tone) => `
    <article class="target-conflict-file target-conflict-file--${tone}">
      <span>${escapeHtml(label)}</span>
      <b>${escapeHtml(file || "未记录文件名")}</b>
      <code title="${escapeHtml(path || "")}">${escapeHtml(path || "路径未记录")}</code>
      <dl>
        <div><dt>大小</dt><dd>${escapeHtml(formatConflictBytes(size))}</dd></div>
        <div><dt>清晰度</dt><dd>${escapeHtml(resolution || "未知")}</dd></div>
      </dl>
    </article>`;
  return `<section class="cinema-modal-block target-conflict-block">
    <div class="target-conflict-assurance">
      <span aria-hidden="true">✓</span>
      <div><b>片库现有文件未发生任何改动</b><p>${escapeHtml(reason)}。系统已经暂停本任务，等待你决定。</p></div>
    </div>
    <div class="target-conflict-compare">
      ${fileCard("片库现有文件", conflict.existing_file, conflict.existing_path, conflict.existing_size, conflict.existing_resolution, "existing")}
      ${fileCard("本次待入库文件", conflict.new_file || task.source_filename, conflict.new_path || task.video_path, conflict.new_size, conflict.new_resolution, "incoming")}
    </div>
    <div class="target-conflict-actions" aria-label="选择冲突处理方式">
      <button id="btn-conflict-keep-existing" type="button" class="btn btn-secondary"><b>保留片库文件</b><small>跳过本次入库，来源文件保持不变</small></button>
      <button id="btn-conflict-keep-both" type="button" class="btn btn-primary"><b>两个都保留</b><small>新文件将命名为 ${escapeHtml(conflict.suggested_filename || "带编号的新文件")}</small></button>
      <button id="btn-conflict-replace" type="button" class="btn target-conflict-replace"><b>替换片库文件</b><small>旧文件先进入本地回收区，可恢复</small></button>
    </div>
    <div id="import-error-area" class="modal-error-area target-conflict-error" hidden></div>
  </section>`;
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
  const targetConflict = targetLibraryConflictOf(task);

  const perm = getTaskEditPermission(task);
  const taskIdForClosure = taskId;
  const summaryDescription = targetConflict
    ? "片库中已有同一影片，系统已暂停入库，请选择处理方式。"
    : taskDescription(task);

  // 分类维度（可编辑，去除预览按钮）
  const dimSectionHtml = perm.canEditDimensions && !targetConflict
    ? `<div class="cinema-modal-block">
                <h4>分类维度</h4>
                <div class="cinema-modal-grid">${buildTaskDimensionsForm(task, true, true)}</div>
           </div>`
    : "";

  // 入库预览区（待确认时显示）
  const importPath = task.import_path || "";
  const finalFilename = task.final_filename || taskFileName(task);
  const importPreviewHtml = isAwaitReview && !targetConflict
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
  const actionHtml = isAwaitReview && !targetConflict
    ? `<div class="cinema-modal-block">
                <div class="cinema-modal-save-row" style="flex-wrap:wrap;gap:8px">
                    <button id="btn-scrape-manual" type="button" class="btn" style="background:linear-gradient(135deg,#eabf63,#c4903a);color:#16100a;border-color:transparent;box-shadow:0 4px 16px rgba(234,191,99,0.2)">手动刮削</button>
                    <div id="import-error-area" class="modal-error-area" style="display:none;width:100%"></div>
                </div>
           </div>`
    : "";

  const stateHintHtml = `<div class="cinema-modal-save-bar">
            <span class="task-status-capsule" style="display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${escapeHtml(perm.statusColor)}18;color:${escapeHtml(perm.statusColor)}">${escapeHtml(perm.statusLabel)}</span>
            <small class="task-permission-hint">${escapeHtml(targetConflict ? "片库冲突待逐项处理，现有文件未改动" : perm.stateLabel)}</small>
       </div>`;

  const body = `
        <div class="cinema-modal-stack">
            <div class="cinema-modal-summary">
                <div><strong>${escapeHtml(taskDisplayTitle(task))}</strong><span class="task-status-capsule" style="display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${escapeHtml(perm.statusColor)}18;color:${escapeHtml(perm.statusColor)};white-space:nowrap">${escapeHtml(perm.statusLabel)}</span></div>
                <p>${escapeHtml(summaryDescription)}</p>
                <small>源文件：${escapeHtml(originalFilename)}</small>
                ${task.source_path ? `<small>源路径：${escapeHtml(task.source_path)}</small>` : ""}
                ${task.import_video_path ? `<small>入库路径：${escapeHtml(task.import_video_path)}</small>` : ""}
            </div>
            ${buildTargetLibraryConflict(task)}
            ${targetConflict ? "" : buildReviewReasonSection(task)}
            ${buildFailureSection(task)}
            ${targetConflict ? "" : buildScrapeTraceSection(task)}
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
  if (isAwaitReview && !targetConflict) {
    actions.push({
      label: "保存",
      className: "btn btn-primary",
      onClick: null,
      closeOnClick: false,
      key: "save",
    });
    actions.push({
      label: "确认入库，开始移动文件",
      className: "btn btn-success",
      onClick: null,
      closeOnClick: false,
      key: "confirm",
    });
  }

  const modal = showAppModal({
    title: "任务详情",
    body,
    actions,
    dismissOnBackdrop: false,
  });

  async function submitConflictAction(conflictAction) {
    setImportError("");
    const result = await requestApi(
      "POST",
      `/tasks/${encodeURIComponent(taskIdForClosure)}/confirm`,
      { conflict_action: conflictAction },
    );
    if (result.code === 200) {
      if (result.data?.requires_conflict_review) {
        showToast(result.message || "片库文件已发生变化，请重新查看后选择");
        removeAppModal();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
        await openTaskDetailImpl(taskIdForClosure, true);
        return;
      }
      const messages = {
        keep_existing: "已保留片库现有文件，来源文件未改动",
        keep_both: "两份文件均已保留",
        replace_existing: "替换完成，原片库文件已进入本地回收区",
      };
      showToast(messages[conflictAction] || result.message || "处理完成");
      removeAppModal();
      await Promise.all([loadTaskList(), loadDashboardOverview()]);
      return;
    }
    setImportError(result.message || "处理失败，现有片库文件未改动");
  }

  if (targetConflict) {
    document
      .getElementById("btn-conflict-keep-existing")
      ?.addEventListener("click", () => submitConflictAction("keep_existing"));
    document
      .getElementById("btn-conflict-keep-both")
      ?.addEventListener("click", () => submitConflictAction("keep_both"));
    document
      .getElementById("btn-conflict-replace")
      ?.addEventListener("click", () => {
        showConfirm(
          "确认替换片库文件",
          `将把片库现有文件「${targetConflict.existing_file || "未命名文件"}」先移入本地回收区，再写入本次文件。不会永久删除，可以从回收区恢复。确认继续吗？`,
          () => submitConflictAction("replace_existing"),
        );
      });
  }

  // 保存按钮 — 调 /preview 持久化后刷新详情
  if (isAwaitReview && !targetConflict) {
    const saveBtn = modal.querySelector(".cinema-modal-footer .btn-primary");
    if (saveBtn) {
      saveBtn.addEventListener("click", async function () {
        setImportError("");
        var dims = getCurrentDimensionValues(task);
        try {
          var result = await requestApi(
            "POST",
            `/tasks/${encodeURIComponent(taskIdForClosure)}/preview`,
            { dimensions: dims },
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
    const confirmBtn = modal.querySelector(".cinema-modal-footer .btn-success");
    if (confirmBtn) {
      confirmBtn.addEventListener("click", async function () {
        setImportError("");
        var dims = getCurrentDimensionValues(task);
        await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskIdForClosure)}/preview`,
          { dimensions: dims },
        );
        var result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskIdForClosure)}/confirm`,
        );
        if (result.code === 200) {
          showToast(result.message || "入库成功");
          removeAppModal();
          await Promise.all([loadTaskList(), loadDashboardOverview()]);
        } else {
          setImportError(result.message || "入库失败");
        }
      });
    }
  }

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

  function setImportError(msg) {
    const errEl = document.getElementById("import-error-area");
    if (!errEl) {
      if (msg) showToast(msg);
      return;
    }
    if (!msg) {
      errEl.hidden = true;
      errEl.style.display = "none";
      errEl.textContent = "";
      return;
    }
    errEl.hidden = false;
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

  // 从输入中提取年份（支持 "标题 2014" / "标题 (2014)" / "标题.2014"），
  // 避免整串含年份的 query 发给 Provider 导致搜不到
  var searchQuery = query;
  var year = "";
  var yearMatch = query.match(/(?:[.\s_([（]+|^)((?:19|20)\d{2})[)\]）]?\s*$/);
  if (yearMatch) {
    year = yearMatch[1];
    searchQuery = query
      .slice(0, yearMatch.index)
      .replace(/[.\s_([（]+$/, "")
      .trim();
    if (!searchQuery) {
      searchQuery = query;
      year = "";
    }
  }

  var result = await requestApi(
    "POST",
    `/tasks/${encodeURIComponent(taskId)}/scrape-search`,
    {
      query: searchQuery,
      year: year ? Number(year) : null,
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
          // 候选确认代表用户已经完成选片，直接沿用确认入库流程，避免再点一次。
          var importResult = await requestApi(
            "POST",
            `/tasks/${encodeURIComponent(taskId)}/confirm`,
          );
          var overlay = document.getElementById("scrape-search-overlay");
          if (overlay) overlay.remove();
          if (importResult.code === 200) {
            showToast("已刮削并入库");
            removeAppModal();
            await Promise.all([loadTaskList(), loadDashboardOverview()]);
          } else {
            showToast(importResult.message || "入库失败", "error");
            removeAppModal();
            await openTaskDetailImpl(taskId, true);
            await Promise.all([loadTaskList(), loadDashboardOverview()]);
          }
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

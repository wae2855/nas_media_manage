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

async function refreshTaskListAfterBackgroundAccept(taskId, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 400));
    const detail = await requestApi(
      "GET",
      `/tasks/${encodeURIComponent(taskId)}`,
    );
    const task = detail.code === 200 ? detail.data?.task : null;
    if (!task) return;
    const status = String(task.status || "").toUpperCase();
    const stage = String(task.stage || "").toUpperCase();
    if (!(status === "PENDING" && stage === "AWAIT_REVIEW")) {
      await Promise.all([loadTaskList(false, { silent: true }), loadDashboardOverview()]);
      return;
    }
  }
  // 后台操作可能正在进行长文件传输。最后同步一次，让 RUNNING 状态接管
  // 常规静默轮询；若仍待确认，用户仍可使用显式刷新，不伪造完成结果。
  await loadTaskList(false, { silent: true });
}

function buildTargetLibraryConflict(task) {
  const conflict = targetLibraryConflictOf(task);
  if (!conflict) return "";
  const isReorganization = task.task_kind === "REORGANIZE";
  const reason =
    conflict.conflict_type === "target_path"
      ? "准备写入的位置已经有同名文件"
      : "识别到片库中已有同一影片";
  const permanentDiscard = !isReorganization && taskPermanentDeleteEnabled()
    ? `<button id="btn-conflict-keep-existing-delete" type="button" class="btn target-conflict-delete"><b>保留片库，删除新资源</b><small>永久删除这次来源视频和字幕，不可恢复</small></button>`
    : "";
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
      <button id="btn-conflict-keep-existing" type="button" class="btn btn-secondary"><b>${isReorganization ? "保留现状，不再整理" : "保留片库，也保留新资源"}</b><small>${isReorganization ? "正式片库和待整理区的文件都保持原位" : "跳过本次入库，来源视频和字幕保持原位"}</small></button>
      ${isReorganization ? "" : `<button id="btn-conflict-keep-existing-recycle" type="button" class="btn btn-secondary"><b>保留片库，回收新资源</b><small>本次新资源进入本地回收区，以后仍可恢复</small></button>`}
      ${permanentDiscard}
      <button id="btn-conflict-keep-both" type="button" class="btn btn-primary"><b>两个都保留</b><small>新文件将命名为 ${escapeHtml(conflict.suggested_filename || "带编号的新文件")}</small></button>
      ${conflict.replace_allowed === false ? "" : `<button id="btn-conflict-replace" type="button" class="btn target-conflict-replace"><b>替换片库文件</b><small>旧文件先进入本地回收区，可恢复</small></button>`}
    </div>
    <div id="import-error-area" class="modal-error-area target-conflict-error" hidden></div>
  </section>`;
}

function buildOrganizationState(task) {
  if (
    String(task.status || "").toUpperCase() === "SUCCESS" &&
    task.organization_status === "FALLBACK_PENDING"
  ) {
    return `<section class="cinema-modal-block task-organization-panel">
      <div class="task-organization-panel-mark" aria-hidden="true">✓</div>
      <div><h4>影片已安全入库到待整理区</h4>
      <p>这条入库任务已经完成，影片可以正常保留和使用。重新整理会创建一条新任务，让你修改维度或重新刮削，再按正式规则移动影片和随片字幕；原任务不会被改写。</p></div>
    </section>`;
  }
  if (
    task.task_kind === "REORGANIZE" &&
    String(task.status || "").toUpperCase() === "PENDING"
  ) {
    return `<section class="cinema-modal-block task-organization-panel task-organization-panel--active">
      <div class="task-organization-panel-mark" aria-hidden="true">↗</div>
      <div><h4>正在准备重新整理</h4>
      <p>${escapeHtml(task.used_fallback ? "当前资料仍未匹配正式规则。请先修改维度或手动刮削；不会再次放回待整理区。" : "已经匹配到正式规则。确认后会整组移动影片和字幕，不会覆盖同名片库文件。")}</p></div>
    </section>`;
  }
  return "";
}

function buildSourceDispositionState(task) {
  const message = String(task.source_disposition_message || "").trim();
  if (!message) return "";
  const labels = {
    kept: "来源已保留",
    recycled: "来源已进入回收区",
    deleted: "来源已永久删除",
    missing: "来源已不存在",
    failed: "来源处理失败",
    pending: "来源等待处理",
  };
  const label = labels[task.source_disposition] || "来源处理结果";
  return `<section class="cinema-modal-block task-source-outcome">
    <h4>${escapeHtml(label)}</h4>
    <p>${escapeHtml(message)}</p>
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
  const isReorganization = task.task_kind === "REORGANIZE";
  const isFallbackPending =
    status === "SUCCESS" && task.organization_status === "FALLBACK_PENDING";

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
            ${buildTaskProgressSection(task)}
            ${buildSourceDispositionState(task)}
            ${buildOrganizationState(task)}
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
    if (!(isReorganization && task.used_fallback)) {
      actions.push({
        label: isReorganization
          ? "确认重新整理"
          : task.used_fallback
            ? "确认放入待整理区"
            : "确认入库，开始移动文件",
        className: "btn btn-success",
        onClick: null,
        closeOnClick: false,
        key: "confirm",
      });
    }
  }
  if (isFallbackPending) {
    actions.push({
      label: "创建重新整理任务",
      className: "btn btn-primary btn-reorganize-task",
      onClick: null,
      closeOnClick: false,
      key: "reorganize",
    });
  }
  if (taskCanHandleSource(task) && !task.cancel_requested) {
    actions.push({
      label:
        status === "PENDING" && stage === "RUNNING"
          ? "停止这次任务"
          : status === "SKIPPED" || status === "CANCELLED"
            ? "处理遗留来源"
            : "不再处理",
      className: "btn btn-secondary btn-end-task-detail",
      onClick: null,
      closeOnClick: false,
      key: "end-task",
    });
  }
  if (["SUCCESS", "FAILED", "SKIPPED", "CANCELLED"].includes(status)) {
    actions.push({
      label: "删除记录",
      className: "btn btn-secondary btn-delete-task-record",
      onClick: null,
      closeOnClick: false,
      key: "delete-record",
    });
  }

  const modal = showAppModal({
    title: "任务详情",
    body,
    actions,
    dismissOnBackdrop: false,
  });

  const reorganizeBtn = modal.querySelector(".btn-reorganize-task");
  if (reorganizeBtn) {
    reorganizeBtn.addEventListener("click", async function () {
      reorganizeBtn.disabled = true;
      reorganizeBtn.textContent = "正在创建...";
      const result = await requestApi(
        "POST",
        `/tasks/${encodeURIComponent(taskIdForClosure)}/reorganize`,
      );
      if ([200, 201].includes(result.code) && result.data?.task?.task_id) {
        showToast(result.message || "已创建重新整理任务");
        const childId = result.data.task.task_id;
        removeAppModal();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
        await openTaskDetailImpl(childId, true);
        return;
      }
      reorganizeBtn.disabled = false;
      reorganizeBtn.textContent = "创建重新整理任务";
      showToast(result.message || "创建重新整理任务失败");
    });
  }

  modal
    .querySelector(".btn-end-task-detail")
    ?.addEventListener("click", () => {
      removeAppModal();
      showTaskDispositionDialog([task], {
        title:
          status === "PENDING" && stage === "RUNNING"
            ? "安全停止这次任务"
            : "结束这次整理",
      });
    });

  modal
    .querySelector(".btn-delete-task-record")
    ?.addEventListener("click", () => {
      removeAppModal();
      performTaskAction("delete-record", taskIdForClosure);
    });

  async function submitConflictAction(conflictAction, sourceDisposition = "") {
    setImportError("");
    const result = await requestApi(
      "POST",
      `/tasks/${encodeURIComponent(taskIdForClosure)}/confirm`,
      {
        conflict_action: conflictAction,
        ...(sourceDisposition ? { source_disposition: sourceDisposition } : {}),
      },
    );
    if ([200, 202].includes(result.code)) {
      if (result.data?.requires_conflict_review) {
        showToast(result.message || "片库文件已发生变化，请重新查看后选择");
        removeAppModal();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
        await openTaskDetailImpl(taskIdForClosure, true);
        return;
      }
      const messages = {
        keep_existing:
          sourceDisposition === "local_recycle"
            ? "已保留片库现有文件，新资源正在进入本地回收区"
            : sourceDisposition === "permanent_delete"
              ? "已保留片库现有文件，新资源将永久删除"
              : "已保留片库现有文件，新资源仍在来源目录",
        keep_both: "两份文件均已保留",
        replace_existing: "替换完成，原片库文件已进入本地回收区",
      };
      showToast(result.message || messages[conflictAction] || "已加入后台队列");
      removeAppModal();
      await Promise.all([loadTaskList(), loadDashboardOverview()]);
      if (result.code === 202) {
        refreshTaskListAfterBackgroundAccept(taskIdForClosure);
      }
      return;
    }
    setImportError(result.message || "处理失败，现有片库文件未改动");
  }

  if (targetConflict) {
    document
      .getElementById("btn-conflict-keep-existing")
      ?.addEventListener("click", () =>
        submitConflictAction("keep_existing", "keep"),
      );
    document
      .getElementById("btn-conflict-keep-existing-recycle")
      ?.addEventListener("click", () =>
        submitConflictAction("keep_existing", "local_recycle"),
      );
    document
      .getElementById("btn-conflict-keep-existing-delete")
      ?.addEventListener("click", () => {
        showConfirm(
          "永久删除这次新资源",
          "片库现有文件会保持不变；这次来源视频和字幕将永久删除且无法恢复。确定继续吗？",
          () => submitConflictAction("keep_existing", "permanent_delete"),
        );
      });
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
        var previewResult = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskIdForClosure)}/preview`,
          { dimensions: dims },
        );
        if (previewResult.code !== 200) {
          setImportError(previewResult.message || "保存预览失败");
          return;
        }
        var latestTask = previewResult.data?.task || task;
        if (isReorganization && latestTask.used_fallback) {
          setImportError("当前仍未匹配正式入库规则，请调整维度或手动刮削后再确认");
          return;
        }
        var confirmBody = {};
        if (!isReorganization && latestTask.used_fallback) {
          confirmBody.fallback_acknowledged = true;
        }
        var result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskIdForClosure)}/confirm`,
          confirmBody,
        );
        if ([200, 202].includes(result.code)) {
          showToast(result.message || "已加入后台队列，关闭页面也会继续处理");
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
      openScrapeSearchModal(
        taskIdForClosure,
        cleanTitle,
        scrapeRes.media_type || task.scrape_media_type || "",
      );
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
function openScrapeSearchModal(taskId, defaultQuery, defaultMediaType) {
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
    '<div class="tmdb-preview-toolbar manual-scrape-toolbar">' +
    '<label class="manual-scrape-query"><span>作品名称</span><input type="text" id="scrape-search-query" placeholder="输入电影或剧集名称" class="tmdb-preview-input" value="' +
    escapeHtml(defaultQuery || "") +
    '" /></label>' +
    '<label><span>作品类型</span><select id="scrape-search-media-type" class="tmdb-preview-select">' +
    '<option value="">电影和剧集</option>' +
    '<option value="movie"' +
    (defaultMediaType === "movie" ? " selected" : "") +
    '>电影</option>' +
    '<option value="tv"' +
    (defaultMediaType === "tv" ? " selected" : "") +
    '>剧集</option></select></label>' +
    '<label><span>结果语言</span><select id="scrape-search-language" class="tmdb-preview-select">' +
    '<option value="zh-CN">中文</option><option value="en-US">英文</option>' +
    '<option value="ja-JP">日文</option><option value="ko-KR">韩文</option>' +
    '</select></label>' +
    '<label><span>年份（可选）</span><input id="scrape-search-year" class="tmdb-preview-input" type="number" min="1870" max="2100" inputmode="numeric" placeholder="如 2016" /></label>' +
    '<button class="btn btn-primary" id="btn-scrape-search-exec" type="button">搜索前 20 条</button>' +
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
  var mediaType = String(
    document.getElementById("scrape-search-media-type")?.value || "",
  );
  var language = String(
    document.getElementById("scrape-search-language")?.value || "zh-CN",
  );
  var explicitYear = String(
    document.getElementById("scrape-search-year")?.value || "",
  ).trim();

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
  var year = explicitYear;
  var yearMatch = query.match(/(?:[.\s_([（]+|^)((?:19|20)\d{2})[)\]）]?\s*$/);
  if (!year && yearMatch) {
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
      media_type: mediaType,
      language: language,
      limit: 20,
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
  resultsEl.innerHTML =
    '<div class="manual-scrape-result-count">找到 ' +
    candidates.length +
    " 条结果，选择后先更新资料，不会立即入库。</div>" +
    candidates
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
        " · " +
        (c.media_type === "tv" ? "剧集" : "电影") +
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
    '<button class="btn btn-primary" id="btn-confirm-candidate" style="width:100%">使用这份资料</button>' +
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
      confirmBtn.textContent = "检查同剧分集...";
      try {
        var relatedTaskIds = await chooseSeriesBatchTaskIds(candidate, taskId);
        if (relatedTaskIds === null) {
          return;
        }
        confirmBtn.textContent = "正在提交处理...";
        var result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskId)}/scrape-apply`,
          {
            provider_type: candidate.provider_type,
            item_id: candidate.id,
            media_type: candidate.media_type,
            language:
              document.getElementById("scrape-search-language")?.value ||
              "zh-CN",
            related_task_ids: relatedTaskIds,
          },
        );
        if (result.code === 200) {
          var overlay = document.getElementById("scrape-search-overlay");
          if (overlay) overlay.remove();
          showToast(result.message || "已按人工选择加入处理队列");
          await openTaskDetailImpl(taskId, true);
          await Promise.all([loadTaskList(), loadDashboardOverview()]);
        } else {
          showToast("应用失败: " + (result.message || "未知错误"), "error");
          renderScrapeCandidateDetail(candidate, taskId);
        }
      } catch (e) {
        showToast("网络错误", "error");
        renderScrapeCandidateDetail(candidate, taskId);
      }
    });
  }
}

async function chooseSeriesBatchTaskIds(candidate, taskId) {
  if (candidate.media_type !== "tv") return [];
  var preview = await requestApi(
    "POST",
    `/tasks/${encodeURIComponent(taskId)}/scrape-series-preview`,
    {
      provider_type: candidate.provider_type,
      item_id: candidate.id,
      media_type: candidate.media_type,
    },
  );
  var tasks = preview.code === 200 ? preview.data?.tasks || [] : [];
  if (tasks.length <= 1) return [];

  var detailEl = document.getElementById("scrape-search-detail");
  if (!detailEl) return [];
  var relatedCount = tasks.filter(function (item) {
    return !item.is_anchor;
  }).length;
  detailEl.innerHTML =
    '<div class="series-batch-preview">' +
    "<h3>发现同剧另外 " +
    relatedCount +
    " 个同剧任务</h3>" +
    "<p>待确认和排队分集会继承这次人工选择并进入处理队列；正在处理的分集仅展示，不会中途改写。每集始终保留自己的季集号。</p>" +
    '<div class="series-batch-list">' +
    tasks
      .map(function (item) {
        var episode =
          "S" +
          String(item.season).padStart(2, "0") +
          "E" +
          String(item.episode).padStart(2, "0");
        var handlingText = {
          queue_with_binding: "待确认 · 将重新排队",
          bind_queued: "排队中 · 将继承作品",
          processing_unchanged: "处理中 · 本次不改写",
        }[item.handling] || "本次不处理";
        var selectable = item.selectable !== false;
        var checked = selectable ? " checked" : "";
        var disabled = item.is_anchor || !selectable ? " disabled" : "";
        return (
          '<label class="series-batch-item' +
          (!selectable ? " is-processing" : "") +
          '">' +
          '<input type="checkbox" data-series-batch-task="' +
          escapeHtml(item.task_id) +
          '"' + checked + disabled + ">" +
          "<span><b>" +
          escapeHtml(item.source_filename) +
          "</b><small>" +
          episode +
          (item.is_anchor ? " · 当前集" : "") +
          " · " + handlingText +
          "</small></span></label>"
        );
      })
      .join("") +
    "</div>" +
    '<div class="series-batch-actions">' +
    '<button class="btn btn-secondary" id="btn-series-batch-back" type="button">返回候选</button>' +
    '<button class="btn btn-secondary" id="btn-series-current-only" type="button">仅应用当前集</button>' +
    '<button class="btn btn-primary" id="btn-series-batch-apply" type="button">应用所选 ' +
    tasks.filter(function (item) { return item.selectable !== false; }).length +
    " 集</button></div></div>";

  var applyBtn = document.getElementById("btn-series-batch-apply");
  function updateCount() {
    var count = detailEl.querySelectorAll(
      "[data-series-batch-task]:checked",
    ).length;
    if (applyBtn) applyBtn.textContent = `应用所选 ${count} 集`;
  }
  detailEl.querySelectorAll("[data-series-batch-task]").forEach(function (input) {
    input.addEventListener("change", updateCount);
  });

  function setBusy(count) {
    var panel = detailEl.querySelector(".series-batch-preview");
    if (panel) panel.setAttribute("aria-busy", "true");
    detailEl.querySelectorAll("button, input").forEach(function (control) {
      control.disabled = true;
    });
    if (applyBtn) {
      applyBtn.innerHTML =
        '<span class="spinner" aria-hidden="true"></span>正在应用并提交 ' +
        count +
        " 集...";
    }
  }

  return new Promise(function (resolve) {
    document
      .getElementById("btn-series-batch-back")
      ?.addEventListener("click", function () {
        renderScrapeCandidateDetail(candidate, taskId);
        resolve(null);
      });
    document
      .getElementById("btn-series-current-only")
      ?.addEventListener("click", function () {
        setBusy(1);
        resolve([]);
      });
    applyBtn?.addEventListener("click", function () {
      var selected = Array.from(
        detailEl.querySelectorAll("[data-series-batch-task]:checked:not(:disabled)"),
      ).map(function (input) {
        return input.dataset.seriesBatchTask;
      });
      setBusy(selected.length + 1);
      resolve(selected);
    });
  });
}

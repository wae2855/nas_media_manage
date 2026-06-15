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
  const isFilenameEditable = isAwaitReview;

  const perm = getTaskEditPermission(task);
  const editable = perm.canSave;

  const renameSection = perm.canEditFilename
    ? `<div class="cinema-modal-block">
                <div class="cinema-modal-section-head">
                    <h4>文件名</h4>
                </div>
                <label class="cinema-modal-field">
                    <span>文件名 <small>（可修改，不含路径）</small></span>
                    <input type="text" id="task-rename-input" value="${escapeHtml(originalFilename)}" data-rename-original="${escapeHtml(originalFilename)}" />
                </label>
                ${buildRenamePreview(originalFilename)}
            </div>`
    : `<div class="cinema-modal-block">
                <h4>文件名</h4>
                <div class="cinema-modal-readonly-line">${escapeHtml(originalFilename)}</div>
            </div>`;

  const dimActionsHtml = perm.canEditDimensions
    ? `<div class="cinema-modal-section-actions">
                ${isAwaitReview ? `<button id="btn-preview-classify" type="button" class="btn btn-sm btn-outline">预览入库规则</button>` : ""}
           </div>`
    : "";

  const dimSectionHtml = perm.canEditDimensions
    ? `<div class="cinema-modal-block">
                <div class="cinema-modal-section-head">
                    <h4>分类维度</h4>
                    ${dimActionsHtml}
                </div>
                <div class="cinema-modal-grid">${buildTaskDimensionsForm(task, true, true)}</div>
                <div id="preview-classify-result" class="cinema-modal-preview" style="display:none"></div>
           </div>`
    : `<div class="cinema-modal-block">
                <h4>分类维度</h4>
                <div class="cinema-modal-grid">${buildTaskDimensionsForm(task, false)}</div>
           </div>`;

  const filenameSaveHtml = perm.canEditFilename
    ? `<div class="cinema-modal-block">
                <div class="cinema-modal-save-row">
                    <button id="btn-save-filename" type="button" class="btn btn-primary">保存文件名</button>
                    <div id="filename-error-area" class="modal-error-area" style="display:none"></div>
                </div>
           </div>`
    : "";

  const dimSaveHtml = perm.canEditDimensions
    ? `<div class="cinema-modal-block">
                <div class="cinema-modal-save-row">
                    <button id="btn-save-dims" type="button" class="btn btn-primary">保存分类</button>
                    <div id="dims-error-area" class="modal-error-area" style="display:none"></div>
                </div>
           </div>`
    : "";

  const stateHintHtml = `<div class="cinema-modal-save-bar">
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
            ${buildScrapeResultSection(task)}
            ${buildScrapeTraceSection(task)}
            ${renameSection}
            ${filenameSaveHtml}
            ${dimSectionHtml}
            ${dimSaveHtml}
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

  const renameInput = document.getElementById("task-rename-input");
  if (renameInput) {
    renameInput.addEventListener("input", () =>
      updateRenamePreview(renameInput),
    );
  }

  function setErrorArea(areaId, msg) {
    const errEl = document.getElementById(areaId);
    if (!errEl) return;
    if (!msg) {
      errEl.style.display = "none";
      errEl.textContent = "";
      return;
    }
    errEl.style.display = "block";
    errEl.textContent = msg;
  }

  function setSavingBtn(btnEl, saving) {
    if (!btnEl) return;
    if (saving) {
      btnEl.disabled = true;
      btnEl.dataset.prevText = btnEl.textContent;
      btnEl.textContent = "保存中...";
    } else {
      btnEl.disabled = false;
      btnEl.textContent = btnEl.dataset.prevText || btnEl.textContent;
    }
  }

  async function handleSaveFilename(btnEl) {
    const inputEl = document.getElementById("task-rename-input");
    const newFilename = String(inputEl?.value || "").trim();
    if (!newFilename) {
      showToast("文件名不能为空");
      setErrorArea("filename-error-area", "文件名不能为空");
      return;
    }
    setSavingBtn(btnEl, true);
    setErrorArea("filename-error-area", "");
    try {
      const result = await requestApi(
        "POST",
        `/tasks/${encodeURIComponent(taskId)}/rename`,
        {
          new_filename: newFilename,
        },
      );
      if (result.code === 200) {
        showToast("文件名已保存");
        removeAppModal();
        await openTaskDetailImpl(taskId, true);
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
        return;
      }
      const errMsg = result.message || "保存文件名失败，请稍后重试";
      setErrorArea("filename-error-area", errMsg);
      showToast(errMsg);
    } finally {
      setSavingBtn(btnEl, false);
    }
  }

  async function handleSaveDims(btnEl) {
    const dims = {};
    const multiDimNames = {};
    // 收集多选 checkbox 值
    document
      .querySelectorAll("input[type=checkbox][data-task-dim]")
      .forEach((cb) => {
        const dimName = cb.dataset.taskDim;
        if (!multiDimNames[dimName]) multiDimNames[dimName] = [];
        if (cb.checked) multiDimNames[dimName].push(cb.value);
      });
    for (const [dimName, vals] of Object.entries(multiDimNames)) {
      if (vals.length) dims[dimName] = vals.join("|");
    }
    // 收集单选 select/input 值（排除 checkbox）
    document
      .querySelectorAll(
        "select[data-task-dim], input[type=text][data-task-dim]",
      )
      .forEach((input) => {
        const nextValue = parseRuleConditionValue(input.value);
        if (nextValue) dims[input.dataset.taskDim] = nextValue;
      });
    if (Object.keys(dims).length === 0) {
      showToast("请至少填写一个维度值");
      setErrorArea("dims-error-area", "请至少填写一个维度值");
      return;
    }
    // diff 模式：只发送与原始值不同的字段
    const origDims = task.scrape_dimensions || task.dimensions || {};
    const changedDims = {};
    let hasChanged = false;
    for (const [key, newVal] of Object.entries(dims)) {
      const origVal = parseRuleConditionValue(String(origDims[key] || ""));
      if (newVal !== origVal) {
        changedDims[key] = newVal;
        hasChanged = true;
      }
    }
    if (!hasChanged) {
      showToast("维度值未做修改");
      return;
    }
    setSavingBtn(btnEl, true);
    setErrorArea("dims-error-area", "");
    try {
      const result = await requestApi(
        "POST",
        `/tasks/${encodeURIComponent(taskId)}/reclassify`,
        {
          dimensions: changedDims,
        },
      );
      if (result.code === 200) {
        showToast("分类已保存");
        removeAppModal();
        await openTaskDetailImpl(taskId, true);
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
        return;
      }
      const errMsg = result.message || "保存分类失败，请稍后重试";
      setErrorArea("dims-error-area", errMsg);
      showToast(errMsg);
    } finally {
      setSavingBtn(btnEl, false);
    }
  }

  const btnSaveFilename = document.getElementById("btn-save-filename");
  if (btnSaveFilename) {
    btnSaveFilename.addEventListener("click", () =>
      handleSaveFilename(btnSaveFilename),
    );
  }
  const btnSaveDims = document.getElementById("btn-save-dims");
  if (btnSaveDims) {
    btnSaveDims.addEventListener("click", () => handleSaveDims(btnSaveDims));
  }

  const previewBtn = document.getElementById("btn-preview-classify");
  if (previewBtn) {
    previewBtn.addEventListener("click", async () => {
      const dims = {};
      document.querySelectorAll("[data-task-dim]").forEach((input) => {
        const v = input.value?.trim();
        if (v) {
          dims[input.dataset.taskDim] = v;
        }
      });
      try {
        const result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskId)}/classify-preview`,
          {
            dimensions: dims,
            filename:
              document.getElementById("task-rename-input")?.value?.trim() ||
              originalFilename,
          },
        );
        const previewDiv = document.getElementById("preview-classify-result");
        if (result.code === 200 && result.data) {
          const d = result.data;
          previewDiv.style.display = "block";
          const hasPath = d.import_path && d.full_path;
          let html = "";
          if (hasPath) {
            html = `<div class="preview-path"><span class="preview-label">入库目录：</span><code>${escapeHtml(d.import_path || "")}</code></div>
                            <div class="preview-path"><span class="preview-label">最终文件：</span><code>${escapeHtml(d.full_path || "")}</code></div>`;
          }
          if (d.warnings?.length) {
            html += `<div class="preview-warning">${escapeHtml(d.warnings.join("; "))}</div>`;
          }
          if (!hasPath && d.rules_description) {
            html += `<div class="preview-info"><span class="preview-label">已配置规则：</span>${escapeHtml(d.rules_description)}</div>`;
          }
          if (!hasPath && d.dimensions_text) {
            html += `<div class="preview-info"><span class="preview-label">当前维度：</span>${escapeHtml(d.dimensions_text)}</div>`;
          }
          previewDiv.innerHTML =
            html || `<div class="preview-warning">无法生成入库路径</div>`;
        } else {
          previewDiv.style.display = "block";
          previewDiv.innerHTML = `<div class="preview-warning">预览失败: ${result.message || "未知错误"}</div>`;
        }
      } catch (e) {
        const previewDiv = document.getElementById("preview-classify-result");
        if (previewDiv) {
          previewDiv.style.display = "block";
          previewDiv.innerHTML = `<div class="preview-warning">请求异常: ${e.message || e}</div>`;
        }
      }
    });
  }
}


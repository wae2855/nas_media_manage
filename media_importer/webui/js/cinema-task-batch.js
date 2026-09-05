// cinema-task-batch.js - task actions and batch operations
function taskPermanentDeleteEnabled() {
  const policy = currentConfigSnapshot?.source_policy || {};
  return (
    policy.disposal_mode === "permanent_delete" &&
    policy.mode !== "preserve_all"
  );
}

function taskCanHandleSource(task) {
  return (
    task?.task_kind !== "REORGANIZE" &&
    String(task?.status || "").toUpperCase() !== "SUCCESS"
  );
}

async function applyTaskDisposition(records, sourceDisposition) {
  const settled = await Promise.allSettled(
    records.map((task) =>
      requestApi(
        "POST",
        `/tasks/${encodeURIComponent(task.task_id)}/dispose`,
        { source_disposition: sourceDisposition },
      ),
    ),
  );
  const accepted = settled.filter(
    (item) =>
      item.status === "fulfilled" &&
      item.value &&
      [200, 202].includes(item.value.code),
  );
  const stopping = accepted.filter(
    (item) => item.status === "fulfilled" && item.value.code === 202,
  ).length;
  const failed = settled.length - accepted.length;
  return { accepted: accepted.length, stopping, failed, settled };
}

function showTaskDispositionDialog(records, { title = "结束处理" } = {}) {
  const actionable = records.filter(taskCanHandleSource);
  if (!actionable.length) {
    showToast("当前选择中没有可结束或处理来源的任务");
    return;
  }
  const running = actionable.filter(
    (task) => taskStatusOf(task) === "PENDING" && taskStageOf(task) === "RUNNING",
  ).length;
  const permanentOption = taskPermanentDeleteEnabled()
    ? `<label class="task-disposition-option task-disposition-option--danger">
        <input type="radio" name="task-source-disposition" value="permanent_delete" />
        <span><b>永久删除这次新资源</b><small>不可恢复；仅处理任务登记的来源视频和字幕，绝不会删除片库文件。</small></span>
      </label>`
    : "";
  const body = `<div class="task-disposition-dialog">
    <div class="task-disposition-assurance"><span>✓</span><div><b>目标片库受保护</b><small>本操作只结束这次整理，并处理新加入的来源资源；已有片库文件不会被删除或覆盖。</small></div></div>
    <p>已选择 ${actionable.length} 个任务。${running ? `其中 ${running} 个正在处理，会先安全停止，再执行下面的选择。` : "请选择这次新资源怎么处理："}</p>
    <div class="task-disposition-options">
      <label class="task-disposition-option">
        <input type="radio" name="task-source-disposition" value="keep" />
        <span><b>保留新资源</b><small>只结束任务，来源视频和字幕保持原位，以后仍可重新投入。</small></span>
      </label>
      <label class="task-disposition-option task-disposition-option--recommended">
        <input type="radio" name="task-source-disposition" value="local_recycle" checked />
        <span><b>移入本地回收区</b><small>推荐；不再整理这次新资源，但仍可以从回收页面恢复。</small></span>
      </label>
      ${permanentOption}
    </div>
    <div class="modal-error-area" data-task-disposition-error hidden></div>
  </div>`;
  let modal = null;
  const submit = async () => {
    const selected = modal?.querySelector(
      'input[name="task-source-disposition"]:checked',
    )?.value;
    if (!selected) return;
    const execute = async () => {
      const result = await applyTaskDisposition(actionable, selected);
      if (result.accepted) {
        removeAppModal();
        clearTaskSelection();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
        showToast(
          result.stopping
            ? `${result.stopping} 个任务正在安全停止，其余已处理`
            : `已处理 ${result.accepted} 个任务${result.failed ? `，${result.failed} 个未处理` : ""}`,
        );
        return;
      }
      const area = modal?.querySelector("[data-task-disposition-error]");
      if (area) {
        area.hidden = false;
        area.textContent = "操作未执行，请刷新任务状态后重试";
      } else {
        showToast("操作未执行，请刷新任务状态后重试");
      }
    };
    if (selected === "permanent_delete") {
      showConfirm(
        "确认永久删除新资源",
        "这次新资源将不可恢复。目标片库现有文件仍不会被删除。确定继续吗？",
        execute,
      );
      return;
    }
    await execute();
  };
  modal = showAppModal({
    title,
    body,
    dismissOnBackdrop: false,
    actions: [
      { label: "返回", className: "btn btn-secondary" },
      {
        label: running ? "安全停止并处理" : "确认处理",
        className: "btn btn-primary",
        onClick: submit,
        closeOnClick: false,
      },
    ],
  });
}

async function performTaskAction(action, taskId) {
  if (action === "refresh-tasks") {
    await loadTaskList(false);
    return;
  }
  if (action === "load-more-tasks") {
    currentTaskPage += 1;
    await loadTaskList(true);
    return;
  }
  const task = findTaskRecord(taskId);
  if (!task) {
    showToast("当前任务数据已过期，请重新加载");
    return;
  }
  if (action === "view-task") {
    await openTaskDetail(taskId);
    return;
  }
  if (action === "reorganize") {
    if (task.organization_status !== "FALLBACK_PENDING") {
      await openManualRelocationDialog(task);
      return;
    }
    const result = await requestApi(
      "POST",
      `/tasks/${encodeURIComponent(taskId)}/reorganize`,
    );
    if ([200, 201].includes(result.code) && result.data?.task?.task_id) {
      showToast(result.message || "已创建重新整理任务");
      await Promise.all([loadTaskList(), loadDashboardOverview()]);
      await openTaskDetail(result.data.task.task_id);
    } else {
      showToast(result.message || "创建重新整理任务失败");
    }
    return;
  }
  if (action === "confirm") {
    const scrape = task.scrape_result || {};
    const confirmedTitle = scrape.title_cn || task.scrape_title_cn || "";
    const originalFilename = task.source_filename || "";
    const matchLevel = scrape.match_level || "";

    // 判定是否换过元数据：
    // 1. 如果已有 override_source（详情面板填过），直接使用
    // 2. 如果 NEEDS_CONFIRM（刮削不自信）且文件名不含标题 → 标记为手动确认
    // 3. 否则（刮削自信或标题匹配文件名）→ 不标记
    let overrideSource = task.override_source || null;
    if (!overrideSource && confirmedTitle && originalFilename) {
      const titleInFilename = originalFilename
        .toLowerCase()
        .includes(confirmedTitle.substring(0, 3).toLowerCase());
      if (matchLevel === "NEEDS_CONFIRM" && !titleInFilename) {
        overrideSource = "manual";
      }
    }
    const usesFallback = Boolean(task.used_fallback);
    showConfirm(
      usesFallback ? "确认放入待整理区" : "确认入库",
      usesFallback
        ? `「${taskFileName(task)}」当前没有匹配正式规则。确认后会安全入库到待整理区并结束本任务，之后仍可创建独立任务重新整理。确认继续吗？`
        : `确定将「${taskFileName(task)}」按当前结果继续入库吗？`,
      async () => {
        const body = {};
        if (confirmedTitle) body.confirmed_title = confirmedTitle;
        if (overrideSource) body.override_source = overrideSource;
        if (usesFallback) body.fallback_acknowledged = true;
        const result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskId)}/confirm`,
          body,
        );
        showToast(result.message || "确认请求已发送");
        if ([200, 202].includes(result.code)) {
          await Promise.all([loadTaskList(), loadDashboardOverview()]);
        }
      },
    );
    return;
  }
  if (action === "retry-task") {
    const isAwaitReview =
      taskStatusOf(task) === "PENDING" && taskStageOf(task) === "AWAIT_REVIEW";
    const confirmMsg = isAwaitReview
      ? `确定重新处理「${taskFileName(task)}」吗？任务会从来源重新识别，全部确认后才写入片库。`
      : `确定重试「${taskFileName(task)}」吗？任务会从来源重新识别，全部确认后才写入片库。`;
    showConfirm("重试任务", confirmMsg, async () => {
      const result = await requestApi(
        "POST",
        `/tasks/${encodeURIComponent(taskId)}/retry`,
      );
      showToast(result.message || "重试请求已发送");
      if (result.code === 200) {
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
      }
    });
    return;
  }
  if (action === "ignore-task") {
    showConfirm(
      "忽略任务",
      `确定忽略「${taskFileName(task)}」吗？`,
      async () => {
        const result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskId)}/ignore`,
        );
        showToast(result.message || "忽略请求已发送");
        if (result.code === 200) {
          await Promise.all([loadTaskList(), loadDashboardOverview()]);
        }
      },
    );
    return;
  }
  if (action === "end-task" || action === "dispose-source") {
    showTaskDispositionDialog([task], {
      title: action === "end-task" ? "结束这次整理" : "处理遗留来源",
    });
    return;
  }
  if (action === "delete-record" || action === "delete-task") {
    showConfirm(
      "删除任务记录",
      `确定删除「${taskFileName(task)}」的任务记录吗？\n\n这只会移除历史记录，来源文件和目标片库文件都不会改动。`,
      async () => {
        const result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskId)}/delete`,
          {
            delete_files: false,
          },
        );
        showToast(result.message || "任务记录已删除");
        if (result.code === 200) {
          await Promise.all([loadTaskList(), loadDashboardOverview()]);
        }
      },
    );
    return;
  }
  if (action === "edit-task") {
    await openTaskDetail(taskId);
    return;
  }
  if (action === "cancel-task") {
    showConfirm(
      "取消任务",
      `确定取消「${taskFileName(task)}」吗？取消后任务将变为已取消状态，可在"已取消"筛选中找到，需要时可用于重新投入。`,
      async () => {
        const result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskId)}/cancel`,
        );
        showToast(result.message || "取消请求已发送");
        if (result.code === 200) {
          await Promise.all([loadTaskList(), loadDashboardOverview()]);
        }
      },
    );
    return;
  }
}

/* B1: 任务页批量动作 */

function taskStatusOf(task) {
  return String(task?.status || "").toUpperCase();
}

function taskStageOf(task) {
  return String(task?.stage || "").toUpperCase();
}

function isBatchableStatus(status) {
  return ["FAILED", "SKIPPED", "PENDING"].includes(status);
}

function isTerminalTask(task) {
  return ["SUCCESS", "FAILED", "SKIPPED", "CANCELLED"].includes(
    taskStatusOf(task),
  );
}

function getSelectedTaskRecords() {
  return currentTaskRecords.filter((task) =>
    selectedTaskIds.has(String(task.task_id || "")),
  );
}

function updateBatchToolbar() {
  const toolbar = document.getElementById("task-batch-toolbar");
  if (!toolbar) return;
  const selectedRecords = getSelectedTaskRecords();
  const count = selectedRecords.length;
  toolbar.hidden = count === 0;
  const counter = document.getElementById("task-batch-count");
  if (counter) counter.textContent = `已选 ${count} 项`;
  const selectAll = document.getElementById("task-select-all");
  const visibleIds = currentTaskRecords.map((item) =>
    String(item.task_id || ""),
  );
  if (selectAll) {
    const allSelected =
      visibleIds.length > 0 &&
      visibleIds.every((id) => selectedTaskIds.has(id));
    const someSelected = visibleIds.some((id) => selectedTaskIds.has(id));
    selectAll.checked = allSelected;
    selectAll.indeterminate = !allSelected && someSelected;
  }
  const retryBtn = document.getElementById("task-batch-retry");
  const confirmBtn = document.getElementById("task-batch-confirm");
  const endBtn = document.getElementById("task-batch-end");
  const deleteRecordBtn = document.getElementById("task-batch-delete-record");
  const hasReidentifiable = selectedRecords.some(
    (t) =>
      taskStatusOf(t) === "FAILED" ||
      (taskStatusOf(t) === "PENDING" && taskStageOf(t) === "AWAIT_REVIEW"),
  );
  const hasAwaitReview = selectedRecords.some(
    (t) =>
      taskStatusOf(t) === "PENDING" &&
      taskStageOf(t) === "AWAIT_REVIEW" &&
      !targetLibraryConflictOf(t) &&
      !t.used_fallback &&
      t.task_kind !== "REORGANIZE",
  );
  const hasEndable = selectedRecords.some(taskCanHandleSource);
  const hasTerminal = selectedRecords.some(isTerminalTask);
  if (retryBtn) retryBtn.hidden = !(count > 0 && hasReidentifiable);
  if (confirmBtn) confirmBtn.hidden = !(count > 0 && hasAwaitReview);
  if (endBtn) endBtn.hidden = !(count > 0 && hasEndable);
  if (deleteRecordBtn)
    deleteRecordBtn.hidden = !(count > 0 && hasTerminal);
  const actionButtons = [retryBtn, confirmBtn, endBtn, deleteRecordBtn].filter(
    Boolean,
  );
  actionButtons.forEach((btn) => {
    btn.disabled = count === 0;
  });
}

function toggleTaskSelect(taskId) {
  const id = String(taskId || "");
  if (!id) return;
  if (selectedTaskIds.has(id)) selectedTaskIds.delete(id);
  else selectedTaskIds.add(id);
  const checkbox = document.querySelector(
    `[data-task-select="${CSS.escape(id)}"]`,
  );
  if (checkbox) checkbox.checked = selectedTaskIds.has(id);
  updateBatchToolbar();
}

function selectAllVisibleTasks() {
  const selectAll = document.getElementById("task-select-all");
  const visibleIds = currentTaskRecords
    .map((item) => String(item.task_id || ""))
    .filter(Boolean);
  const shouldSelectAll = !(
    visibleIds.length > 0 && visibleIds.every((id) => selectedTaskIds.has(id))
  );
  currentTaskRecords.forEach((item) => {
    const id = String(item.task_id || "");
    if (!id) return;
    if (shouldSelectAll) selectedTaskIds.add(id);
    else selectedTaskIds.delete(id);
  });
  if (selectAll) selectAll.checked = shouldSelectAll;
  renderTaskList();
}

function clearTaskSelection() {
  selectedTaskIds.clear();
  renderTaskList();
}

function setBatchToolbarVisibility() {
  const toolbar = document.getElementById("task-batch-toolbar");
  if (!toolbar) return;
  toolbar.hidden =
    !Array.isArray(currentTaskRecords) ||
    currentTaskRecords.length === 0 ||
    selectedTaskIds.size === 0;
}

async function performBatchTaskAction(action) {
  const records = getSelectedTaskRecords();
  if (records.length === 0) {
    showToast("请先选择要操作的任务");
    return;
  }
  if (records.length > 50) {
    showToast(
      `当前选中 ${records.length} 项，超过单次批量 50 项上限，请分批操作`,
    );
    return;
  }
  if (action === "batch-clear") {
    clearTaskSelection();
    return;
  }
  if (action === "batch-confirm") {
    const eligible = records.filter(
      (task) =>
        taskStatusOf(task) === "PENDING" &&
        taskStageOf(task) === "AWAIT_REVIEW" &&
        !targetLibraryConflictOf(task) &&
        !task.used_fallback &&
        task.task_kind !== "REORGANIZE",
    );
    const protectedCount = records.length - eligible.length;
    if (!eligible.length) {
      showToast("片库冲突必须打开任务逐项处理，不能批量确认");
      return;
    }
    showConfirm(
      "批量入库",
      `确定将「${eligible.length}」项普通待确认任务按当前结果入库吗？${protectedCount ? ` 已排除 ${protectedCount} 项需要逐项处理的片库冲突。` : ""}`,
      async () => {
        const settled = await Promise.allSettled(
          eligible.map((task) =>
            requestApi(
              "POST",
              `/tasks/${encodeURIComponent(task.task_id)}/confirm`,
            ),
          ),
        );
        const ok = settled.filter(
          (item) =>
            item.status === "fulfilled" &&
            item.value &&
            item.value.code === 200,
        ).length;
        showToast(`批量入库完成：成功 ${ok} 项，失败 ${eligible.length - ok} 项`);
        clearTaskSelection();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
      },
    );
    return;
  }
  if (action === "batch-retry") {
    const eligible = records.filter(
      (t) =>
        taskStatusOf(t) === "FAILED" ||
        (taskStatusOf(t) === "PENDING" && taskStageOf(t) === "AWAIT_REVIEW"),
    );
    if (eligible.length === 0) {
      showToast("当前选中项中没有可重新识别的任务");
      return;
    }
    showConfirm(
      "批量重新识别",
      `确定对「${eligible.length}」项失败或待确认任务重新识别吗？将使用当前版本规则重新刮削，确认无误后才写入片库。`,
      async () => {
        const settled = await Promise.allSettled(
          eligible.map((t) =>
            requestApi("POST", `/tasks/${encodeURIComponent(t.task_id)}/retry`),
          ),
        );
        const ok = settled.filter(
          (r) => r.status === "fulfilled" && r.value && r.value.code === 200,
        ).length;
        const fail = settled.length - ok;
        showToast(`批量重新识别完成：成功 ${ok} 项，失败 ${fail} 项`);
        clearTaskSelection();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
      },
    );
    return;
  }
  if (action === "batch-end") {
    showTaskDispositionDialog(records, { title: "批量结束处理" });
    return;
  }
  if (action === "batch-delete-record") {
    const eligible = records.filter(isTerminalTask);
    if (eligible.length === 0) {
      showToast("当前选中项中没有可删除记录的已结束任务");
      return;
    }
    showConfirm(
      "批量删除任务记录",
      `确定删除「${eligible.length}」项已结束任务的记录吗？\n\n只删除记录，不会改动来源文件或目标片库文件。`,
      async () => {
        const settled = await Promise.allSettled(
          eligible.map((t) =>
            requestApi(
              "POST",
              `/tasks/${encodeURIComponent(t.task_id)}/delete`,
              { delete_files: false },
            ),
          ),
        );
        const ok = settled.filter(
          (r) => r.status === "fulfilled" && r.value && r.value.code === 200,
        ).length;
        const fail = settled.length - ok;
        showToast(`批量删除记录完成：成功 ${ok} 项，失败 ${fail} 项`);
        clearTaskSelection();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
      },
    );
  }
}

function showMatchTraceModal(trace, filename) {
  let html =
    '<div class="match-trace-modal" style="padding:16px;background:rgba(255,255,255,0.02);border-radius:8px">';
  html += '<h3 style="margin-top:0">匹配路径详情</h3>';
  html +=
    '<p style="color:#94A3B8;font-size:12px;margin:8px 0 16px">文件：' +
    escapeHtml(filename || "") +
    "</p>";
  var steps = (trace && typeof trace === "object" && trace.trace) || [];
  if (Array.isArray(steps) && steps.length > 0) {
    html += '<div style="display:flex;flex-direction:column;gap:12px">';
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
        '08;padding:12px 16px;border-radius:8px">';
      html +=
        '<div style="font-weight:600;color:' +
        color +
        '">第' +
        step.tier +
        "级：" +
        escapeHtml(step.name || "") +
        " &nbsp;·&nbsp; " +
        (step.matched ? "✓ 匹配" : "✗ 未匹配") +
        "</div>";
      if (step.reason)
        html +=
          '<div style="margin-top:8px;font-size:13px;line-height:1.6;color:#CBD5E1">' +
          escapeHtml(step.reason) +
          "</div>";
      html += "</div>";
    }
    html += "</div>";
  } else {
    html += '<p style="color:#94A3B8">无匹配路径信息</p>';
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

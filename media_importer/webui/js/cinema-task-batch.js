// cinema-task-batch.js - task actions and batch operations
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
    showConfirm(
      "确认入库",
      `确定将「${taskFileName(task)}」按当前结果继续入库吗？`,
      async () => {
        const body = {};
        if (confirmedTitle) body.confirmed_title = confirmedTitle;
        if (overrideSource) body.override_source = overrideSource;
        const result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskId)}/confirm`,
          body,
        );
        showToast(result.message || "确认请求已发送");
        if (result.code === 200) {
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
      ? `确定重试「${taskFileName(task)}」吗？将从刮削开始重新处理，维度会被重新刮削覆盖。`
      : `确定重试「${taskFileName(task)}」吗？`;
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
  if (action === "delete-task") {
    showConfirm(
      "移入回收",
      `确定将「${taskFileName(task)}」移出当前任务流吗？\n\n如果后端允许，将按现有安全规则进入回收流程。`,
      async () => {
        const result = await requestApi(
          "POST",
          `/tasks/${encodeURIComponent(taskId)}/delete`,
          {
            delete_files: false,
          },
        );
        showToast(result.message || "移入回收请求已发送");
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
  toolbar.hidden = false;
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
  const ignoreBtn = document.getElementById("task-batch-ignore");
  const deleteBtn = document.getElementById("task-batch-delete");
  const hasFailedOrSkipped = selectedRecords.some((t) =>
    ["FAILED", "SKIPPED", "CANCELLED"].includes(taskStatusOf(t)),
  );
  const hasAwaitReview = selectedRecords.some(
    (t) => taskStatusOf(t) === "PENDING" && taskStageOf(t) === "AWAIT_REVIEW",
  );
  const hasProcessable = selectedRecords.some((t) =>
    isBatchableStatus(taskStatusOf(t)),
  );
  if (retryBtn) retryBtn.hidden = !(count > 0 && hasFailedOrSkipped);
  if (confirmBtn) confirmBtn.hidden = !(count > 0 && hasAwaitReview);
  if (ignoreBtn)
    ignoreBtn.hidden = !(count > 0 && (hasAwaitReview || hasFailedOrSkipped));
  if (deleteBtn) deleteBtn.hidden = !(count > 0 && hasProcessable);
  const actionButtons = [retryBtn, confirmBtn, ignoreBtn, deleteBtn].filter(
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
    !Array.isArray(currentTaskRecords) || currentTaskRecords.length === 0;
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
    showConfirm(
      "批量入库",
      `确定将「${records.length}」项任务按当前结果入库吗？`,
      async () => {
        const result = await requestApi("POST", "/tasks/confirm-all");
        showToast(
          result.message || `批量确认请求已发送，共 ${records.length} 项`,
        );
        clearTaskSelection();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
      },
    );
    return;
  }
  if (action === "batch-retry") {
    const eligible = records.filter((t) =>
      ["FAILED", "SKIPPED", "CANCELLED"].includes(taskStatusOf(t)),
    );
    if (eligible.length === 0) {
      showToast("当前选中项中没有可重试的任务");
      return;
    }
    showConfirm(
      "批量重试",
      `确定对「${eligible.length}」项失败/已跳过/已取消任务发起重试吗？`,
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
        showToast(`批量重试完成：成功 ${ok} 项，失败 ${fail} 项`);
        clearTaskSelection();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
      },
    );
    return;
  }
  if (action === "batch-ignore") {
    const eligible = records.filter((t) => isBatchableStatus(taskStatusOf(t)));
    if (eligible.length === 0) {
      showToast("当前选中项中没有可忽略的任务");
      return;
    }
    showConfirm(
      "批量忽略",
      `确定忽略「${eligible.length}」项任务吗？`,
      async () => {
        const settled = await Promise.allSettled(
          eligible.map((t) =>
            requestApi(
              "POST",
              `/tasks/${encodeURIComponent(t.task_id)}/ignore`,
            ),
          ),
        );
        const ok = settled.filter(
          (r) => r.status === "fulfilled" && r.value && r.value.code === 200,
        ).length;
        const fail = settled.length - ok;
        showToast(`批量忽略完成：成功 ${ok} 项，失败 ${fail} 项`);
        clearTaskSelection();
        await Promise.all([loadTaskList(), loadDashboardOverview()]);
      },
    );
    return;
  }
  if (action === "batch-delete") {
    const eligible = records.filter((t) => isBatchableStatus(taskStatusOf(t)));
    if (eligible.length === 0) {
      showToast("当前选中项中没有可移入回收的任务");
      return;
    }
    showConfirm(
      "批量移入回收",
      `确定将「${eligible.length}」项任务移入回收站吗？\n\n任务不会立即物理删除，可在回收页恢复。`,
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
        showToast(`批量移入回收完成：成功 ${ok} 项，失败 ${fail} 项`);
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
      if (step.ai_reason)
        html +=
          '<div style="margin-top:8px;font-size:13px;line-height:1.6;color:#06B6D4;border-left:2px solid #06B6D420;padding-left:12px">AI: ' +
          escapeHtml(step.ai_reason) +
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

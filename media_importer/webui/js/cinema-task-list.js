// cinema-task-list.js - task list rendering
function renderTaskSummary(task) {
  const title = taskDisplayTitle(task);
  const filename = taskFileName(task);
  const lines = [
    `任务：${title}`,
    `状态：${getTaskStatusText(task.status)}`,
    `源文件：${filename}`,
  ];
  if (task.source_path) lines.push(`源路径：${task.source_path}`);
  if (task.import_video_path) lines.push(`入库路径：${task.import_video_path}`);
  const desc = taskDescription(task);
  if (desc) lines.push(`说明：${desc}`);
  return lines.join("\n");
}

function dimSourceMeta(source) {
  const src = String(source || "unknown");
  if (src === "provider:tmdb") return { icon: "🗄️", label: "TMDB直接映射" };
  if (src === "provider:douban") return { icon: "📚", label: "豆瓣直接映射" };
  if (src === "ai_assist") return { icon: "🤖", label: "AI辅助映射" };
  if (src === "ai_search") return { icon: "🔍", label: "AI联网搜索" };
  if (src === "file") return { icon: "📄", label: "文件分析" };
  return { icon: "—", label: "未记录来源" };
}

function renderTaskScrapeProcess(task) {
  const scrape = task.scrape_result || {};
  const dimSources = task.dim_sources || scrape.dim_sources || {};
  const entries = Object.entries(dimSources || {});
  if (entries.length === 0 && !(task.confirm_reason || scrape.confirm_reason))
    return `
        <details class="task-scrape-process" open>
            <summary>刮削结果</summary>
            <div class="task-confirm-reason" style="color:var(--text-muted)">暂无刮削记录，建议补充年份/中文名/英文名等信息以便精确匹配。</div>
        </details>`;
  const reason = task.confirm_reason || scrape.confirm_reason || "";
  const rows = entries
    .map(([name, source]) => {
      const meta = dimSourceMeta(source);
      return `<span class="task-dim-source"><i>${meta.icon}</i><b>${escapeHtml(name)}</b><em>${escapeHtml(meta.label)}</em></span>`;
    })
    .join("");
  return `
        <details class="task-scrape-process" open>
            <summary>刮削结果</summary>
            ${reason ? `<div class="task-confirm-reason">${escapeHtml(reason)}</div>` : ""}
            <div class="task-dim-source-grid">${rows || '<span class="task-dim-source"><i>—</i><b>维度来源</b><em>暂无记录</em></span>'}</div>
        </details>`;
}

function renderTaskCard(item, index = 0) {
  const status = String(item.status || "").toUpperCase();
  const stage = String(item.stage || "").toUpperCase();
  const isAwaitReview = status === "PENDING" && stage === "AWAIT_REVIEW";
  const isFailed = status === "FAILED";
  const danger = isFailed || isAwaitReview ? " danger" : "";
  const primaryAction = taskPrimaryAction(item);
  const secondaryAction = taskSecondaryAction(item);
  const title = taskDisplayTitle(item);
  const filename = taskFileName(item);
  const taskId = String(item.task_id || "");
  const checked = selectedTaskIds.has(taskId) ? "checked" : "";
  const scrape = item.scrape_result || {};
  const thumbnailPath = item.thumbnail_path || "";
  const posterUrl = scrape.poster_url || "";
  const toneClass = `cover-${getTaskTone(item)}`;
  let coverClass, coverContent;
  if (thumbnailPath) {
    const thumbFilename = thumbnailPath.split("/").pop().split("\\").pop();
    const thumbUrl = `/api/thumbnails/${encodeURIComponent(thumbFilename)}`;
    coverClass = "cover cover-img";
    coverContent = `<img src="${escapeHtml(thumbUrl)}" alt="" loading="lazy" data-fallback="${escapeHtml(posterUrl)}" onerror="var d=this.parentNode;var pu=this.dataset.fallback;if(pu){d.className='cover cover-img';this.src=pu;}else{d.className='cover ${toneClass}';this.remove();}" />`;
  } else if (posterUrl) {
    coverClass = "cover cover-img";
    coverContent = `<img src="${escapeHtml(posterUrl)}" alt="" loading="lazy" onerror="this.parentNode.className='cover ${toneClass}';this.remove();" />`;
  } else {
    coverClass = `cover ${toneClass}`;
    coverContent = "";
  }
  return `
        <article class="task-card" data-task-row="${escapeHtml(taskId)}" style="--card-index: ${index}">
            <input type="checkbox" class="task-select-checkbox" data-task-select="${escapeHtml(taskId)}" ${checked} aria-label="选择任务" onclick="event.stopPropagation()" />
            <div class="${coverClass}" aria-hidden="true">${coverContent}</div>
            <div class="task-body">
                <div class="task-top"><h3>${escapeHtml(title)}</h3><span class="badge${danger}">${escapeHtml(getTaskStatusText(item.status, item.stage))}</span></div>
                ${renderTaskScrapeProcess(item)}
                <div class="task-meta"><span class="task-meta-file">🎞️ ${escapeHtml(filename)}</span><span class="task-meta-sep">·</span><span class="task-meta-info">${escapeHtml(taskMeta(item))}</span></div>
                <small class="task-row-hint">点击卡片选中 · 点击"详情"查看编辑</small>
            </div>
            <div class="task-actions">
                <button class="btn-ghost" data-task-action="view-task" data-task-id="${escapeHtml(taskId)}" aria-label="查看详情">详情</button>
                ${primaryAction ? `<button data-task-action="${escapeHtml(primaryAction.key)}" data-task-id="${escapeHtml(item.task_id || "")}">${escapeHtml(primaryAction.label)}</button>` : ""}
                ${secondaryAction ? `<button data-task-action="${escapeHtml(secondaryAction.key)}" data-task-id="${escapeHtml(item.task_id || "")}">${escapeHtml(secondaryAction.label)}</button>` : ""}
            </div>
        </article>`;
}

function renderTaskList() {
  const meta = TASK_FILTER_META[currentTaskFilter] || TASK_FILTER_META.all;
  document.getElementById("task-panel-title").textContent = meta.title;
  document.getElementById("task-panel-copy").textContent = meta.copy;
  /* 刷新首页轮盘 */
  if (typeof loadReelWheelFromTasks === "function") loadReelWheelFromTasks();
  const host = document.getElementById("task-list");
  if (!host) return;
  const countEl = document.getElementById("task-panel-count");
  if (!Array.isArray(currentTaskRecords) || currentTaskRecords.length === 0) {
    const emptyHint =
      currentTaskFilter === "all"
        ? "你可以先回到首页发起扫描，或等待新文件进入源目录。"
        : `当前「${meta.title}」筛选下没有匹配的任务。`;
    host.innerHTML = `
            <div class="task-empty-state">
                <div class="task-empty-icon">
                    <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
                </div>
                <h3>无此状态数据</h3>
                <p>${emptyHint}</p>
                <div class="task-empty-actions">
                    <button class="btn btn-secondary" data-task-action="refresh-tasks">重新加载</button>
                    <button class="btn btn-secondary" data-nav="home" data-view-target="dashboard">回到首页</button>
                </div>
            </div>`;
    if (countEl) countEl.textContent = "0 / 0 项";
    setBatchToolbarVisibility();
    updateBatchToolbar();
    return;
  }
  const cardsHtml = currentTaskRecords
    .map((item, index) => renderTaskCard(item, index))
    .join("");
  const loadMoreHtml = currentTaskHasMore
    ? `<div class="task-load-more">
                <button class="btn btn-secondary" data-task-action="load-more-tasks">加载更多（已显示 ${currentTaskRecords.length} / 共 ${currentTaskTotal} 项）</button>
            </div>`
    : "";
  host.innerHTML = cardsHtml + loadMoreHtml;
  if (countEl) {
    const loaded = currentTaskRecords.length;
    countEl.textContent = currentTaskHasMore
      ? `${loaded} / ${currentTaskTotal} 项`
      : `${loaded} 项`;
  }
  setBatchToolbarVisibility();
  updateBatchToolbar();
}

function renderStaticLists() {
  renderTaskList();
  currentRecycleRecords = [];
  renderRecycleList();
}

function setTaskFilter(filter) {
  currentTaskFilter = filter;
  currentTaskPage = 1;
  selectedTaskIds.clear();
  document.querySelectorAll("[data-task-filter-chip]").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.taskFilterChip === filter);
  });
  loadTaskList(false);
}

async function listTasksByStatuses(params, page = 1, pageSize = 20) {
  const baseQuery = { page, limit: pageSize };
  if (!params || Object.keys(params).length === 0) {
    const result = await requestApi("GET", "/tasks", baseQuery);
    if (result.code !== 200 || !result.data)
      return {
        code: result.code,
        message: result.message,
        tasks: [],
        total: 0,
        total_pages: 1,
      };
    return {
      code: 200,
      tasks: result.data.tasks || [],
      total: result.data.total || 0,
      total_pages: result.data.total_pages || 1,
    };
  }
  // Handle array status by making separate requests and merging
  if (params.status && Array.isArray(params.status)) {
    const allTasks = [];
    let totalSum = 0;
    let anyError = false;
    for (const s of params.status) {
      const query = { ...baseQuery, status: s };
      if (params.stage) query.stage = params.stage;
      const result = await requestApi("GET", "/tasks", query);
      if (result.code !== 200 || !result.data) {
        anyError = true;
        continue;
      }
      allTasks.push(...(result.data.tasks || []));
      totalSum += result.data.total || 0;
    }
    if (anyError && allTasks.length === 0)
      return {
        code: 500,
        message: "请求失败",
        tasks: [],
        total: 0,
        total_pages: 1,
      };
    const mergedPageSize = pageSize * params.status.length;
    return {
      code: 200,
      tasks: allTasks,
      total: totalSum,
      total_pages: Math.max(1, Math.ceil(totalSum / mergedPageSize)),
    };
  }
  const query = { ...baseQuery };
  if (params.status) query.status = params.status;
  if (params.stage) query.stage = params.stage;
  const result = await requestApi("GET", "/tasks", query);
  if (result.code !== 200 || !result.data)
    return {
      code: result.code,
      message: result.message,
      tasks: [],
      total: 0,
      total_pages: 1,
    };
  return {
    code: 200,
    tasks: result.data.tasks || [],
    total: result.data.total || 0,
    total_pages: result.data.total_pages || 1,
  };
}

async function loadTaskList(append = false) {
  if (currentTaskLoading) return;
  currentTaskLoading = true;
  try {
    const meta = TASK_FILTER_META[currentTaskFilter] || TASK_FILTER_META.all;
    document.getElementById("task-panel-title").textContent = meta.title;
    document.getElementById("task-panel-copy").textContent = meta.copy;
    if (!append) {
      currentTaskPage = 1;
      currentTaskRecords = [];
      document.getElementById("task-panel-count").textContent = "加载中";
      const host = document.getElementById("task-list");
      if (host) {
        host.innerHTML = `
                    <article class="task-card">
                        <div class="cover cover-gold"></div>
                        <div class="task-body">
                            <div class="task-top"><h3>正在读取任务队列</h3><span class="badge">加载中</span></div>
                            <p>正在把真实任务列表同步到新版任务工作台。</p>
                            <div class="task-meta"><span>任务工作台</span></div>
                        </div>
                    </article>`;
      }
    }
    const result = await listTasksByStatuses(
      TASK_FILTER_PARAMS[currentTaskFilter],
      currentTaskPage,
      currentTaskPageSize,
    );
    if (result.code === 401) {
      currentTaskRecords = [];
      currentTaskTotal = 0;
      currentTaskHasMore = false;
      renderTaskList();
      return;
    }
    if (result.code !== 200) {
      currentTaskRecords = [];
      currentTaskTotal = 0;
      currentTaskHasMore = false;
      renderErrorState(result.message || "请稍后重试。");
      return;
    }
    if (append) {
      currentTaskRecords = currentTaskRecords.concat(result.tasks || []);
    } else {
      currentTaskRecords = result.tasks || [];
    }
    currentTaskTotal = result.total || 0;
    currentTaskHasMore = currentTaskRecords.length < currentTaskTotal;
    renderTaskList();
  } finally {
    currentTaskLoading = false;
  }
}

function renderErrorState(message) {
  const host = document.getElementById("task-list");
  if (!host) return;
  host.innerHTML = `
        <article class="task-card">
            <div class="cover cover-red"></div>
            <div class="task-body">
                <div class="task-top"><h3>任务列表加载失败</h3><span class="badge danger">失败</span></div>
                <p>${escapeHtml(message)}</p>
                <div class="task-meta"><span>任务工作台</span></div>
            </div>
            <div class="task-actions">
                <button data-task-action="refresh-tasks">重新加载</button>
            </div>
        </article>`;
  document.getElementById("task-panel-count").textContent = "--";
  setBatchToolbarVisibility();
  updateBatchToolbar();
}


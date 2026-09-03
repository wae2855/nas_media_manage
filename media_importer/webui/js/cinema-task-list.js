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
  if (src === "provider:tmdb") return { icon: "🗄️", label: "TMDB 映射" };
  if (src === "provider:douban") return { icon: "📚", label: "历史豆瓣映射" };
  if (src === "ai_assist") return { icon: "🕘", label: "历史 AI 辅助映射" };
  if (src === "ai_search") return { icon: "🕘", label: "历史 AI 搜索映射" };
  if (src === "default") return { icon: "⚙️", label: "默认值" };
  if (src === "file") return { icon: "📄", label: "文件分析" };
  return { icon: "—", label: "未记录来源" };
}

function renderTaskScrapeProcess(task) {
  const scrapeResult = task.scrape_result || {};
  const selected = scrapeResult.selected_candidate || null;
  const dimSources = task.dim_sources || scrapeResult.dim_sources || {};

  // L4: 最终用了
  let selectedBlock = "";
  if (selected && selected.title) {
    const whyMap = {
      unique_match: "唯一精确匹配",
      evidence_converged: "文件名与目录名指向同一作品",
      folder_rescue: "目录标题补足弱文件名",
      provider_alias: "命中影视资料官方别名",
      top_rated:
        "评分最高" + (selected.score ? "(" + selected.score + ")" : ""),
      ai_suggestion: "历史 AI 建议",
      first_candidate: "候选排名第一",
      user_pick: "用户选择",
      explicit_provider_id: "文件名身份编号精确命中",
      nfo_provider_id: "相邻 NFO 身份编号精确命中",
      folder_provider_id: "作品目录身份编号精确命中",
      historical_provider_binding: "历史身份绑定精确命中",
    };
    const whyText =
      whyMap[selected.why_selected] || selected.why_selected || "";
    selectedBlock = `
      <div class="task-selected-block" style="margin-bottom:10px;">
        <div style="font-size:11px;color:var(--muted);margin-bottom:4px;">✅ 刮削选中</div>
        <div style="font-size:13px;color:var(--ink);">
          ${escapeHtml(selected.title)}
          ${selected.year ? '<span style="color:var(--muted)">(' + selected.year + ")</span>" : ""}
          ${whyText ? '<span style="font-size:11px;color:var(--muted);margin-left:6px;">· ' + escapeHtml(whyText) + "</span>" : ""}
        </div>
      </div>`;
  }

  const tagBlock = `<div class="task-card-tags-above-dims">${taskMetaTags(task)
    .filter((tag) => tag.tone !== "time")
    .map(
      (tag) =>
        `<span class="task-tag task-tag--${escapeHtml(tag.tone)}">${escapeHtml(tag.text)}</span>`,
    )
    .join("")}</div>`;
  const dimBlock = renderDimSourcesWithValues(task);
  return selectedBlock + tagBlock + dimBlock;
}

// 待确认原因的业务化文案映射（concern code → 用户能看懂的标题）
const CONCERN_LABELS = {
  NO_YEAR_MULTI_MATCH: "存在多部同名作品",
  REQUIRED_DIM_MISSING: "必填维度缺失",
  MISSING_FIELDS: "关键字段不完整",
  NO_PROVIDER_MATCH: "未匹配到影视信息",
  CANDIDATES_AVAILABLE: "已预选候选结果待核对",
  FUZZY_TITLE: "标题无法自动确认",
  NO_TITLE: "无法从文件名提取标题",
  NO_PROVIDER_RESULT: "影视库中无相关结果",
  CONFLICTING_INFO: "多个标题或目录证据互相冲突",
  IDENTITY_CONFLICT: "身份编号与文件信息冲突",
  IDENTITY_LOOKUP_FAILED: "身份编号暂时无法验证",
  CLOSE_CANDIDATES: "存在难以自动区分的候选作品",
  FALLBACK_REORGANIZATION: "尚未匹配正式入库规则",
};

function concernLabel(code) {
  return CONCERN_LABELS[code] || code || "需要人工确认";
}

// 待确认原因摘要（列表卡片用，最多展示 2 条）
function renderReviewReasonRow(task) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  if (!(status === "PENDING" && stage === "AWAIT_REVIEW")) return "";
  const targetConflict = targetLibraryConflictOf(task);
  if (targetConflict) {
    const conflictLabel =
      targetConflict.conflict_type === "target_path"
        ? "目标位置已有同名文件"
        : "片库中已有同一影片";
    return `
      <div class="task-review-reason task-review-reason--library-conflict">
        <span class="task-review-reason-icon" aria-hidden="true">◆</span>
        <span class="task-review-reason-text">${escapeHtml(conflictLabel)}</span>
        <span class="task-review-reason-hint">现有文件未改动，请逐项选择</span>
      </div>`;
  }
  const concerns =
    task.match_concerns || (task.scrape_result || {}).match_concerns || [];
  const items = (Array.isArray(concerns) ? concerns : [])
    .filter((c) => c && (c.message || c.code))
    .slice(0, 2)
    .map((c) => concernLabel(c.code));
  if (!items.length) return "";
  const more =
    Array.isArray(concerns) && concerns.length > 2
      ? ` 等 ${concerns.length} 项`
      : "";
  return `
      <div class="task-review-reason">
        <span class="task-review-reason-icon" aria-hidden="true">⚠</span>
        <span class="task-review-reason-text">${escapeHtml(items.join("、"))}${escapeHtml(more)}</span>
        <span class="task-review-reason-hint">详情可查看具体原因并手动处理</span>
      </div>`;
}

function renderDimSourcesWithValues(task) {
  const dims =
    task.scrape_dimensions ||
    (task.scrape_result && task.scrape_result.dimensions) ||
    {};
  ensureDimDefsLoaded();

  if (Object.keys(dims).length === 0) {
    return '<div style="font-size:11px;color:var(--muted);">暂无维度记录</div>';
  }

  let html =
    '<div class="task-dim-grid" style="display:flex;flex-wrap:wrap;gap:6px;">';
  const entries = Object.entries(dims);
  for (const [index, [name, value]] of entries.entries()) {
    const label = dimLabelOf(name);
    // null/undefined 显示为空（代表未取到值），不再显示 "null" 字样
    let valLabel = value == null ? "" : String(value);
    const dimDef = (_dimensionsData || [])
      .concat(window.currentEnabledDimensions || [])
      .find((d) => d && d.name === name);
    if (dimDef && Array.isArray(dimDef.value_list)) {
      const matched = dimDef.value_list.find(
        (v) => String(v.value) === String(value),
      );
      if (matched) valLabel = matched.label || valLabel;
    }
    const missing = valLabel === "";
    html +=
      '<span class="task-dim-chip' +
      (missing ? " task-dim-chip--missing" : "") +
      (index >= 3 ? " task-dim-chip--mobile-extra" : "") +
      '" style="border-left-color:' +
      dimColorOf(name) +
      ';">' +
      escapeHtml(label) +
      (missing ? "" : "：" + escapeHtml(valLabel)) +
      "</span>";
  }
  if (entries.length > 3) {
    html += `<button type="button" class="task-dim-more" data-task-action="view-task" data-task-id="${escapeHtml(task.task_id || "")}">查看全部 ${entries.length} 项判断</button>`;
  }
  html += "</div>";
  return html;
}

function renderFailedTaskBlock(task) {
  if (task.status !== "FAILED") return "";
  const scrapeResult = task.scrape_result || {};
  const aiReason = scrapeResult.ai_reason || task.error_message || "";
  let shortReason = scrapeResult.tier_short_reason || "处理失败";
  if (task.bundle_state === "ROLLED_BACK") shortReason = "入库前中断";
  if (task.bundle_state === "RECOVERY_REQUIRED") shortReason = "需要人工检查";

  return `
    <div class="task-failed-block" style="padding:10px;background:rgba(217,79,69,0.08);border-left:3px solid var(--red,#d94f45);border-radius:4px;margin-bottom:10px;">
      <div style="font-size:12px;color:var(--red,#d94f45);font-weight:600;margin-bottom:4px;">
        ❌ ${escapeHtml(shortReason)}
      </div>
      ${aiReason ? '<div style="font-size:11px;color:var(--muted);margin-bottom:8px;line-height:1.5;">' + escapeHtml(aiReason) + "</div>" : ""}
      <button class="btn btn-secondary btn-sm" onclick="rescrapeTask(${task.id})" style="font-size:11px;">
        🔄 重新刮削
      </button>
    </div>`;
}

function renderOrganizationOutcome(task) {
  if (
    String(task.status || "").toUpperCase() !== "SUCCESS" ||
    task.organization_status !== "FALLBACK_PENDING"
  ) {
    return "";
  }
  return `<div class="task-organization-outcome">
    <span aria-hidden="true">✓</span>
    <div><b>已安全入库，等待整理</b><small>当前影片在待整理区，原任务已经完成；需要时可另建任务重新匹配正式规则。</small></div>
  </div>`;
}

function renderTaskCard(item, index = 0) {
  const status = String(item.status || "").toUpperCase();
  const stage = String(item.stage || "").toUpperCase();
  const isAwaitReview = status === "PENDING" && stage === "AWAIT_REVIEW";
  const isFailed = status === "FAILED";
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
  const renderKey = taskCardRenderKey(item, index);
  var statusLabel, statusColor;
  if (isAwaitReview) {
    statusLabel = "待确认";
    statusColor = "#F59E0B";
  } else if (isFailed) {
    statusLabel = "失败";
    statusColor = "#D94F45";
  } else if (status === "SUCCESS") {
    statusLabel = "已完成";
    statusColor = "#22C55E";
  } else if (status === "SKIPPED") {
    statusLabel = "已跳过";
    statusColor = "#8B5CF6";
  } else if (status === "CANCELLED") {
    statusLabel = "已取消";
    statusColor = "#6C757D";
  } else if (status === "PENDING" && stage === "QUEUED") {
    statusLabel = "排队中";
    statusColor = "#94A3B8";
  } else if (status === "PENDING" && stage === "RUNNING") {
    statusLabel = item.cancel_requested ? "正在停止" : "处理中";
    statusColor = "#06B6D4";
  } else {
    statusLabel = "未知";
    statusColor = "#6C757D";
  }
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
  const failedBlock = renderFailedTaskBlock(item);
  return `
        <article class="task-card" data-task-row="${escapeHtml(taskId)}" data-task-render-key="${renderKey}" style="--card-index: ${index}">
            <input type="checkbox" class="task-select-checkbox" data-task-select="${escapeHtml(taskId)}" ${checked} aria-label="选择任务" />
            <div class="${coverClass}" aria-hidden="true">${coverContent}</div>
            <div class="task-body">
                <div class="task-top"><h3>${escapeHtml(title)}</h3><span class="task-status-capsule" style="display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${statusColor}18;color:${statusColor};white-space:nowrap">${escapeHtml(statusLabel)}</span></div>
                ${failedBlock}
                ${renderOrganizationOutcome(item)}
                ${renderReviewReasonRow(item)}
                ${renderTaskLiveProgress(item)}
                ${isFailed ? "" : renderTaskScrapeProcess(item)}
                <div class="task-meta">
                    <span class="task-meta-file">🎞️ ${escapeHtml(filename)}</span>
                    <span class="task-meta-tags task-meta-tags--time">${taskMetaTags(
                      item,
                    )
                      .filter((tag) => tag.tone === "time")
                      .map(
                        (tag) =>
                          `<span class="task-tag task-tag--${escapeHtml(tag.tone)}">${escapeHtml(tag.text)}</span>`,
                      )
                      .join("")}</span>
                </div>
                <small class="task-row-hint">点击卡片选中 · 点击"详情"查看编辑</small>
            </div>
            <div class="task-actions">
                <button class="btn-ghost" data-task-action="view-task" data-task-id="${escapeHtml(taskId)}" aria-label="查看详情">详情</button>
                ${primaryAction ? `<button data-task-action="${escapeHtml(primaryAction.key)}" data-task-id="${escapeHtml(item.task_id || "")}">${escapeHtml(primaryAction.label)}</button>` : ""}
                ${secondaryAction ? `<button data-task-action="${escapeHtml(secondaryAction.key)}" data-task-id="${escapeHtml(item.task_id || "")}">${escapeHtml(secondaryAction.label)}</button>` : ""}
            </div>
        </article>`;
}

function taskCardRenderKey(item, index) {
  const taskId = String(item.task_id || "");
  const payload = JSON.stringify([
    item,
    index,
    selectedTaskIds.has(taskId),
  ]);
  let hash = 2166136261;
  for (let i = 0; i < payload.length; i += 1) {
    hash ^= payload.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function createTaskCardElement(item, index) {
  const template = document.createElement("template");
  template.innerHTML = renderTaskCard(item, index).trim();
  return template.content.firstElementChild;
}

function preserveTaskCardCover(previousCard, nextCard) {
  const previousCover = previousCard?.querySelector(".cover");
  const nextCover = nextCard?.querySelector(".cover");
  if (!previousCover || !nextCover || previousCover.className !== nextCover.className) return;
  const previousImage = previousCover.querySelector("img");
  const nextImage = nextCover.querySelector("img");
  if ((previousImage?.getAttribute("src") || "") !== (nextImage?.getAttribute("src") || "")) {
    return;
  }
  nextCover.replaceWith(previousCover);
}

function patchTaskListCards(host) {
  const existingCards = Array.from(host.querySelectorAll(":scope > article.task-card"));
  if (
    existingCards.length === 0 ||
    existingCards.some((card) => !card.dataset.taskRow)
  ) {
    return false;
  }

  const existingById = new Map(
    existingCards.map((card) => [String(card.dataset.taskRow || ""), card]),
  );
  const desiredIds = new Set();
  let cursor = host.firstElementChild;

  currentTaskRecords.forEach((item, index) => {
    const taskId = String(item.task_id || "");
    const renderKey = taskCardRenderKey(item, index);
    desiredIds.add(taskId);
    const previousCard = existingById.get(taskId);
    let nextCard = previousCard;

    if (!previousCard || previousCard.dataset.taskRenderKey !== renderKey) {
      nextCard = createTaskCardElement(item, index);
      if (previousCard) {
        const replacedCursor = previousCard === cursor;
        preserveTaskCardCover(previousCard, nextCard);
        previousCard.replaceWith(nextCard);
        if (replacedCursor) cursor = nextCard;
      }
    }

    if (nextCard !== cursor) host.insertBefore(nextCard, cursor);
    cursor = nextCard.nextElementSibling;
  });

  existingCards.forEach((card) => {
    if (!desiredIds.has(String(card.dataset.taskRow || "")) && card.isConnected) {
      card.remove();
    }
  });

  const existingLoadMore = host.querySelector(":scope > .task-load-more");
  if (!currentTaskHasMore) {
    existingLoadMore?.remove();
  } else {
    const label = `加载更多（已显示 ${currentTaskRecords.length} / 共 ${currentTaskTotal} 项）`;
    if (existingLoadMore) {
      const button = existingLoadMore.querySelector("button");
      if (button && button.textContent !== label) button.textContent = label;
      host.appendChild(existingLoadMore);
    } else {
      const wrap = document.createElement("div");
      wrap.className = "task-load-more";
      wrap.innerHTML = `<button class="btn btn-secondary" data-task-action="load-more-tasks">${escapeHtml(label)}</button>`;
      host.appendChild(wrap);
    }
  }
  return true;
}

function renderTaskList(options = {}) {
  const incremental = Boolean(options.incremental);
  const meta = TASK_FILTER_META[currentTaskFilter] || TASK_FILTER_META.all;
  document.getElementById("task-panel-title").textContent = meta.title;
  document.getElementById("task-panel-copy").textContent = meta.copy;
  /* 刷新首页轮盘 */
  if (!incremental && typeof loadReelWheelFromTasks === "function") {
    loadReelWheelFromTasks();
  }
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
  if (!incremental || !patchTaskListCards(host)) {
    host.innerHTML = cardsHtml + loadMoreHtml;
  }
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

// 维度定义补载完成后重渲列表（首次直出时用的是内置中文名兜底）
window.addEventListener("dim-defs-loaded", function () {
  if (document.getElementById("task-list")) renderTaskList();
});

function setTaskFilter(filter) {
  if (!TASK_FILTER_META[filter]) {
    console.warn("[setTaskFilter] 未知筛选值: " + filter + ", 回退到 all");
    filter = "all";
  }
  currentTaskFilter = filter;
  currentTaskPage = 1;
  selectedTaskIds.clear();
  document.querySelectorAll("[data-task-filter-chip]").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.taskFilterChip === filter);
    if (chip.dataset.taskFilterChip === filter && window.innerWidth <= 600) {
      chip.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    }
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

async function listVisibleTaskPages(params) {
  const visiblePages = Math.max(1, Number(currentTaskPage || 1));
  const tasks = [];
  let total = 0;
  let totalPages = 1;
  for (let page = 1; page <= visiblePages; page += 1) {
    const result = await listTasksByStatuses(params, page, currentTaskPageSize);
    if (result.code !== 200) return result;
    tasks.push(...(result.tasks || []));
    total = Number(result.total || 0);
    totalPages = Number(result.total_pages || 1);
    if (page >= totalPages) break;
  }
  return {
    code: 200,
    tasks: Array.from(
      new Map(tasks.map((task) => [String(task.task_id || ""), task])).values(),
    ),
    total,
    total_pages: totalPages,
  };
}

async function loadTaskList(append = false, options = {}) {
  if (currentTaskLoading) return;
  const silent = Boolean(options.silent);
  currentTaskLoading = true;
  if (!silent) setRefreshButtonState(true);
  try {
    const meta = TASK_FILTER_META[currentTaskFilter] || TASK_FILTER_META.all;
    document.getElementById("task-panel-title").textContent = meta.title;
    document.getElementById("task-panel-copy").textContent = meta.copy;
    if (!append && !silent) {
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
    const result = silent
      ? await listVisibleTaskPages(TASK_FILTER_PARAMS[currentTaskFilter])
      : await listTasksByStatuses(
          TASK_FILTER_PARAMS[currentTaskFilter],
          currentTaskPage,
          currentTaskPageSize,
        );
    if (result.code === 401) {
      if (silent) return;
      currentTaskRecords = [];
      currentTaskTotal = 0;
      currentTaskHasMore = false;
      renderTaskList();
      return;
    }
    if (result.code !== 200) {
      if (silent) return;
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
    renderTaskList({ incremental: silent });
  } finally {
    currentTaskLoading = false;
    if (!silent) setRefreshButtonState(false);
  }
}

function taskListHasRunningItem() {
  return currentTaskRecords.some(
    (task) =>
      String(task.status || "").toUpperCase() === "PENDING" &&
      String(task.stage || "").toUpperCase() === "RUNNING",
  );
}

function stopTaskProgressPolling() {
  if (taskProgressRefreshTimer) clearInterval(taskProgressRefreshTimer);
  taskProgressRefreshTimer = null;
}

function startTaskProgressPolling() {
  stopTaskProgressPolling();
  taskProgressRefreshTimer = setInterval(() => {
    const activeView = document.querySelector('.page-view.active[data-view="tasks"]');
    if (!activeView || document.hidden || currentTaskLoading) return;
    if (document.querySelector(".cinema-modal-overlay")) return;
    if (selectedTaskIds.size > 0 || !taskListHasRunningItem()) return;
    loadTaskList(false, { silent: true });
  }, 2500);
}

function setRefreshButtonState(loading) {
  const btn = document.getElementById("task-panel-refresh");
  if (!btn) return;
  if (loading) {
    btn.classList.add("is-loading");
    btn.disabled = true;
  } else {
    btn.classList.remove("is-loading");
    btn.disabled = false;
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

async function rescrapeTask(taskId) {
  if (!confirm("确定重新刮削此任务吗？将从刮削开始重新处理。")) return;
  try {
    const resp = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/retry`, {
      method: "POST",
    });
    const result = await resp.json();
    showToast(result.message || "重试请求已发送");
    if (result.code === 200) {
      await Promise.all([loadTaskList(), loadDashboardOverview()]);
    }
  } catch (e) {
    showToast("重试请求失败");
  }
}

// cinema-dashboard.js - business summary for the dashboard
function dashboardCount(data, key) {
  return Number((data && data.counts && data.counts[key]) || 0);
}

function setDashboardActionState(data) {
  const running = dashboardCount(data, "running");
  const failed = dashboardCount(data, "failed");
  document.querySelectorAll('[data-action="pause"]').forEach((button) => {
    button.disabled = running === 0 || !!data.paused;
    button.title = button.disabled
      ? data.paused
        ? "后台整理已经暂停"
        : "当前没有正在处理的任务"
      : "暂停当前后台处理";
  });
  document.querySelectorAll('[data-action="retry"]').forEach((button) => {
    button.disabled = failed === 0;
    button.title = failed === 0 ? "当前没有失败任务" : `重试 ${failed} 个失败任务`;
  });
}

function renderDashboardState(data) {
  const queued = dashboardCount(data, "queued");
  const running = dashboardCount(data, "running");
  const review = dashboardCount(data, "await_review");
  const failed = dashboardCount(data, "failed");
  const runtime = document.getElementById("runtime-status");
  const extras = [
    queued ? `${queued} 项排队` : "",
    review ? `${review} 项待确认` : "",
    failed ? `${failed} 项失败` : "",
  ].filter(Boolean);

  if (data.paused) {
    if (runtime) runtime.textContent = "后台整理已暂停";
    setDashboardQueueStrip("后台整理已暂停", {
      state: "paused",
      detail: extras.length ? extras.join(" · ") : "恢复后才会继续处理新任务。",
      actionLabel: review ? "去确认" : failed ? "查看失败项" : "查看任务",
      filter: review ? "review" : failed ? "failed" : "all",
    });
  } else if (running > 0) {
    if (runtime) runtime.textContent = "后台整理中";
    setDashboardQueueStrip(`正在处理 ${running} 项影片`, {
      state: "running",
      detail: extras.length ? extras.join(" · ") : "处理完成后会自动写入片库。",
      progress: Number(data.running_progress || 0),
    });
  } else if (review > 0) {
    if (runtime) runtime.textContent = "服务正常";
    setDashboardQueueStrip(`有 ${review} 项需要你确认`, {
      state: "review",
      detail: failed
        ? `另有 ${failed} 项处理失败；确认前不会继续入库。`
        : "识别或分类结果需要人工核对，确认前不会继续入库。",
      actionLabel: "去处理",
      filter: "review",
    });
  } else if (failed > 0) {
    if (runtime) runtime.textContent = "服务正常";
    setDashboardQueueStrip(`有 ${failed} 项处理失败`, {
      state: "failed",
      detail: "查看失败原因后可以重新尝试。",
      actionLabel: "查看失败项",
      filter: "failed",
    });
  } else if (queued > 0) {
    if (runtime) runtime.textContent = "服务正常";
    setDashboardQueueStrip(`${queued} 项已经排队`, {
      state: "queued",
      detail: "后台整理空闲后会依次开始处理。",
      actionLabel: "查看队列",
      filter: "queued",
    });
  } else {
    if (runtime) runtime.textContent = "服务正常";
    setDashboardQueueStrip("等待新影片进入队列", {
      state: "idle",
      detail: "服务正常，发现新影片后会自动更新。",
    });
  }
  setDashboardActionState(data);
}

function renderDashboardSummary(data) {
  document.getElementById("metric-pending").textContent = dashboardCount(data, "queued");
  document.getElementById("metric-confirm").textContent = dashboardCount(data, "await_review");
  document.getElementById("metric-success").textContent = Number(data.today_success || 0);
  renderDashboardState(data);
  renderActivityRows(
    (Array.isArray(data.activities) ? data.activities : []).map((item) => ({
      ...item,
      level: item.tone || "success",
    })),
  );
  if (typeof setReelMovies === "function") setReelMovies(data.recent_movies || []);
}

async function loadDashboardOverview() {
  const result = await requestApi("GET", "/dashboard/summary");
  if (result.code === 401) {
    setDashboardQueueStrip("请先完成 API Key 认证", {
      state: "warning",
      detail: "认证后才能读取片库和后台任务状态。",
    });
    return;
  }
  if (result.code !== 200 || !result.data) {
    setDashboardQueueStrip("暂时无法读取首页状态", {
      state: "failed",
      detail: result.message || "请稍后重试，或检查服务连接。",
    });
    return;
  }
  renderDashboardSummary(result.data);
}

function startDashboardAutoRefresh() {
  if (dashboardRefreshTimer) window.clearInterval(dashboardRefreshTimer);
  dashboardRefreshTimer = window.setInterval(loadDashboardOverview, DASHBOARD_REFRESH_MS);
}

function collectHelpItemsForGrid(grid) {
  const items = [];
  let current = null;
  const HELP_CLASSES = ["info-intro", "info-rows", "info-callout"];
  for (const el of Array.from(grid.children)) {
    const cls = HELP_CLASSES.find((candidate) => el.classList && el.classList.contains(candidate));
    if (!cls) {
      if (current) {
        items.push(current);
        current = null;
      }
      continue;
    }
    if (cls === "info-intro") {
      if (current) items.push(current);
      const label =
        el.querySelector(".info-label")?.textContent?.trim() ||
        el.querySelector("h4")?.textContent?.trim() ||
        "说明";
      current = { label, elements: [el] };
    } else if (current) {
      current.elements.push(el);
    } else {
      const label =
        el.querySelector("b")?.textContent?.trim() ||
        el.querySelector(".info-label")?.textContent?.trim() ||
        "提示";
      current = { label, elements: [el] };
    }
  }
  if (current) items.push(current);
  return items;
}

function buildHelpAccordion(items) {
  const container = document.createElement("div");
  container.className = "help-accordion form-card-full";
  const title = document.createElement("div");
  title.className = "help-accordion-title";
  title.textContent = "使用说明";
  container.appendChild(title);
  items.forEach((item) => {
    const wrap = document.createElement("div");
    wrap.className = "help-accordion-item";
    const header = document.createElement("button");
    header.type = "button";
    header.className = "help-accordion-header";
    header.innerHTML = `<span class="help-accordion-label">${escapeHtml(item.label)}</span><span class="help-accordion-chevron">▸</span>`;
    const body = document.createElement("div");
    body.className = "help-accordion-body";
    item.elements.forEach((element) => body.appendChild(element));
    header.addEventListener("click", () => {
      const willOpen = !wrap.classList.contains("open");
      container.querySelectorAll(".help-accordion-item.open").forEach((other) => {
        if (other !== wrap) other.classList.remove("open");
      });
      wrap.classList.toggle("open", willOpen);
    });
    wrap.appendChild(header);
    wrap.appendChild(body);
    container.appendChild(wrap);
  });
  return container;
}

function initHelpAccordions() {
  document.querySelectorAll(".config-stage-panel").forEach((panel) => {
    const grid = panel.querySelector(".config-form-grid");
    if (!grid) return;
    const items = collectHelpItemsForGrid(grid);
    if (items.length === 0) return;
    items.forEach((item) => item.elements.forEach((element) => element.remove()));
    grid.appendChild(buildHelpAccordion(items));
  });
}

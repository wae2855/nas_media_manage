// cinema-dashboard.js - dashboard metrics, queue, activity, help
async function loadDashboardMetrics() {
  const result = await requestApi("GET", "/metrics");
  if (result.code === 401) {
    setDashboardQueueStrip("请先完成 API Key 认证后查看当前队列", 0);
    return;
  }
  if (result.code !== 200 || !result.data) {
    setDashboardQueueStrip("暂时无法读取首页状态，请稍后重试", 0);
    return;
  }
  const queue = result.data.queue_by_status || {};
  const byStage = queue._by_stage || {};
  const pendingStage = byStage.PENDING || {};

  /* 排队中：PENDING + QUEUED（与任务工作台"排队中"筛选一致） */
  document.getElementById("metric-pending").textContent =
    pendingStage.QUEUED || 0;

  /* 需要确认：PENDING + AWAIT_REVIEW（与任务工作台"待确认"筛选一致） */
  document.getElementById("metric-confirm").textContent =
    pendingStage.AWAIT_REVIEW || 0;

  /* 今日入库：SUCCESS + SKIPPED（与任务工作台"已完成"筛选一致） */
  const success = queue.SUCCESS || queue.success || 0;
  const skipped = queue.SKIPPED || queue.skipped || 0;
  document.getElementById("metric-success").textContent = success + skipped;
}

async function loadDashboardQueueStatus() {
  const result = await requestApi("GET", "/queue/status");
  if (result.code === 401) {
    setDashboardQueueStrip("请先完成 API Key 认证后查看当前队列", 0);
    return;
  }
  if (result.code !== 200 || !result.data) {
    setDashboardQueueStrip("暂时无法读取当前队列", 0);
    return;
  }
  const byStatus = result.data.by_status || {};
  const pending = statusCount(byStatus, "PENDING", "pending");
  const failed = statusCount(byStatus, "FAILED", "failed");
  const totalOpen = pending + failed;
  if (result.data.paused) {
    setDashboardQueueStrip(
      `队列已暂停，仍有 ${totalOpen} 项待继续处理`,
      totalOpen > 0 ? 0.28 : 0,
    );
    return;
  }
  if (pending > 0) {
    setDashboardQueueStrip(
      `当前有 ${pending} 项等待处理或确认`,
      totalOpen > 0 ? pending / totalOpen : 0.52,
    );
    return;
  }
  if (failed > 0) {
    setDashboardQueueStrip(
      `当前有 ${failed} 项处理失败，可直接发起重试`,
      totalOpen > 0 ? failed / totalOpen : 0.24,
    );
    return;
  }
  setDashboardQueueStrip("等待新影片进入队列", 0);
}

async function loadDashboardActivity() {
  const result = await requestApi("GET", "/logs?limit=6");
  if (result.code === 401) {
    renderActivityRows([
      {
        title: "需要先完成认证",
        copy: "输入 API Key 后，这里会显示真实扫描、识别和入库过程。",
        level: "WARNING",
        timestamp: new Date().toISOString(),
      },
    ]);
    return;
  }
  if (result.code !== 200 || !result.data) {
    renderActivityRows([
      {
        title: "暂时无法读取最近活动",
        copy: result.message || "请稍后重试，或检查服务连接状态。",
        level: "ERROR",
        timestamp: new Date().toISOString(),
      },
    ]);
    return;
  }
  const logs = Array.isArray(result.data.logs) ? result.data.logs : [];
  const items = logs
    .slice()
    .reverse()
    .map((log) => ({
      title: log.message || "最新活动",
      copy:
        [
          log.task_id ? `任务 ${log.task_id}` : "",
          log.step ? `步骤 ${log.step}` : "",
        ]
          .filter(Boolean)
          .join(" · ") || "系统正在持续记录处理过程。",
      level: log.level || "INFO",
      timestamp: log.timestamp || log.time,
    }));
  renderActivityRows(items);
}

async function loadDashboardOverview() {
  await Promise.all([
    loadDashboardMetrics(),
    loadDashboardQueueStatus(),
    loadDashboardActivity(),
  ]);
}

function startDashboardAutoRefresh() {
  if (dashboardRefreshTimer) window.clearInterval(dashboardRefreshTimer);
  dashboardRefreshTimer = window.setInterval(() => {
    loadDashboardOverview();
  }, DASHBOARD_REFRESH_MS);
}

function collectHelpItemsForGrid(grid) {
  const items = [];
  let current = null;
  const HELP_CLASSES = ["info-intro", "info-rows", "info-callout"];
  for (const el of Array.from(grid.children)) {
    const cls = HELP_CLASSES.find(
      (c) => el.classList && el.classList.contains(c),
    );
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
    const labelEl = document.createElement("span");
    labelEl.className = "help-accordion-label";
    labelEl.textContent = item.label;
    const chevron = document.createElement("span");
    chevron.className = "help-accordion-chevron";
    chevron.textContent = "▸";
    header.appendChild(labelEl);
    header.appendChild(chevron);

    const body = document.createElement("div");
    body.className = "help-accordion-body";
    item.elements.forEach((el) => body.appendChild(el));

    header.addEventListener("click", () => {
      const willOpen = !wrap.classList.contains("open");
      container
        .querySelectorAll(".help-accordion-item.open")
        .forEach((other) => {
          if (other !== wrap) other.classList.remove("open");
        });
      if (willOpen) wrap.classList.add("open");
      else wrap.classList.remove("open");
    });

    wrap.appendChild(header);
    wrap.appendChild(body);
    container.appendChild(wrap);
  });

  return container;
}

function initHelpAccordions() {
  const panels = document.querySelectorAll(".config-stage-panel");
  panels.forEach((panel) => {
    const grid = panel.querySelector(".config-form-grid");
    if (!grid) return;
    const items = collectHelpItemsForGrid(grid);
    if (items.length === 0) return;
    items.forEach((item) => item.elements.forEach((el) => el.remove()));
    const accordion = buildHelpAccordion(items);
    grid.appendChild(accordion);
  });
}


// cinema-config-simulator-extra.js — 配置模拟器预览、进度、状态辅助函数
// 从 cinema-config-simulator.js 拆分，遵循文件 ≤500 行规范

function renderSimulatorPreview(data) {
  const result = document.getElementById("match-preview-result");
  if (!result) return;
  result.innerHTML = renderMatchPathPreview(data);
}

function _simDecisionLabel2(matchLevel, gateBlocked) {
  if (gateBlocked) return "维度否决";
  if (matchLevel === "AUTO_PASS") return "自动入库";
  if (matchLevel === "CONTEXT_PASS") return "历史 AI 匹配结果";
  if (matchLevel === "NEEDS_CONFIRM") return "待确认";
  return "未识别";
}

function _simFormatNumber(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return num.toFixed(3);
}

function _renderSimDims(dims) {
  const dimDefs = window.currentEnabledDimensions || [];
  const allDimDefs = window._dimensionsData || [];
  const sourceLabels = {
    tmdb: "Provider",
    file: "文件",
    default: "默认值",
  };
  const fallbackColors = [
    "#f59e0b",
    "#ec4899",
    "#8b5cf6",
    "#06b6d4",
    "#10b981",
    "#f97316",
    "#3b82f6",
    "#eab308",
  ];
  let colorIdx = 0;
  let html = '<div class="sim-dim-list">';

  // 遍历全部启用的维度，有值显示值，无值显示占位
  const dimValues = dims && typeof dims === "object" ? dims : {};
  const defs = dimDefs.length > 0 ? dimDefs : allDimDefs;

  for (const dimDef of defs) {
    const key = dimDef.name;
    const rawVal = dimValues[key];
    const isObj = typeof rawVal === "object" && rawVal !== null;
    const hasValue =
      rawVal != null && rawVal !== "" && (!isObj || rawVal.value != null);
    const displayVal = hasValue
      ? isObj
        ? rawVal.value || JSON.stringify(rawVal)
        : String(rawVal)
      : "—";
    const source = isObj ? rawVal.source || "" : "";
    const dimLabel = dimDef.label || dimDef.name;
    const dimColor =
      dimDef.color || fallbackColors[colorIdx++ % fallbackColors.length];

    let valLabel = String(displayVal);
    if (hasValue && dimDef.value_list && Array.isArray(dimDef.value_list)) {
      const matched = dimDef.value_list.find(
        (v) => String(v.value) === String(displayVal),
      );
      if (matched) valLabel = matched.label || String(displayVal);
    }

    const sourceBadge = source
      ? `<span class="sim-dim-source sim-dim-source--${escapeHtml(source)}">${escapeHtml(sourceLabels[source] || source)}</span>`
      : "";
    const missingClass = hasValue ? "" : ' style="opacity:0.45"';
    html += `<span class="sim-dim-tag"${missingClass} style="--dim-color:${escapeHtml(dimColor)}"><span class="sim-dim-label">${escapeHtml(dimLabel)}</span><span class="sim-dim-val">${escapeHtml(valLabel)}</span>${sourceBadge}</span>`;
  }
  html += "</div>";
  return html;
}

async function runConfigSimulator() {
  const filename = String(
    document.getElementById("match-preview-filename")?.value || "",
  ).trim();
  if (!filename) {
    showToast("请先输入一个真实文件名");
    return;
  }
  const resultBox = document.getElementById("match-preview-result");
  if (resultBox) {
    resultBox.innerHTML =
      '<div class="sim-preview-progress"><div class="sim-progress-title">正在启动模拟测试...</div><div class="sim-spinner"></div></div>';
  }
  const start = await requestApi("POST", "/scrape/preview/start", { filename });
  if (start.code !== 200 || !start.data?.job_id) {
    if (resultBox) resultBox.textContent = start.message || "模拟测试启动失败";
    showToast(start.message || "模拟测试启动失败");
    return;
  }
  await pollScrapePreviewJob(start.data.job_id);
}

async function pollScrapePreviewJob(jobId) {
  const resultBox = document.getElementById("match-preview-result");
  const startedAt = Date.now();
  const maxMs = 5 * 60 * 1000;
  var _seenStepKeys = [];
  while (Date.now() - startedAt < maxMs) {
    const status = await requestApi(
      "GET",
      `/scrape/preview/status/${encodeURIComponent(jobId)}`,
    );
    if (status.code !== 200 || !status.data) {
      if (resultBox)
        resultBox.textContent = status.message || "模拟测试状态读取失败";
      showToast(status.message || "模拟测试状态读取失败");
      return;
    }
    renderSimulatorProgress(status.data, _seenStepKeys);
    if (status.data.status === "done") {
      await new Promise(function (r) {
        return setTimeout(r, 400);
      });
      renderSimulatorPreview(status.data.result);
      showToast("模拟测试已完成");
      return;
    }
    if (status.data.status === "failed") {
      if (resultBox)
        resultBox.textContent = status.data.error || "模拟测试失败";
      showToast("模拟测试失败");
      return;
    }
    await new Promise(function (r) {
      return setTimeout(r, 200);
    });
  }
  if (resultBox) {
    resultBox.innerHTML =
      '<div class="sim-warning" style="margin-top:0">模拟测试超时，请检查 Provider 配置、网络或后端日志。</div>';
  }
  showToast("模拟测试超时，请检查 Provider 配置或后端日志");
}

function renderSimulatorProgress(job, _seenStepKeys) {
  var resultBox = document.getElementById("match-preview-result");
  if (!resultBox) return;
  var steps = Array.isArray(job.steps) ? job.steps : [];
  var html = '<div class="sim-preview-progress">';
  html +=
    '<div class="sim-progress-title">模拟测试进行中：' +
    escapeHtml(job.filename || "") +
    "</div>";
  if (steps.length === 0) {
    html += '<div class="sim-progress-step sim-progress-new">等待开始...</div>';
  }
  for (var i = 0; i < steps.length; i++) {
    var step = steps[i];
    var status = step.status || "running";
    var isNew = _seenStepKeys.indexOf(step.key + ":" + step.status) === -1;
    if (isNew) _seenStepKeys.push(step.key + ":" + step.status);
    var animClass = isNew ? " sim-progress-new" : "";
    html +=
      '<div class="sim-progress-step sim-progress-' +
      escapeHtml(status) +
      animClass +
      '">';
    html += '<div class="sim-progress-step-label">';
    if (status === "running")
      html += '<span class="sim-spinner-inline"></span>';
    html += escapeHtml(step.label || step.key || "") + "</div>";
    html +=
      '<div class="sim-progress-step-message">' +
      escapeHtml(step.message || "") +
      "</div>";
    if (step.elapsed != null) {
      var timeLabel;
      if (
        status === "done" &&
        step.step_elapsed != null &&
        step.step_elapsed > 0
      ) {
        timeLabel = "耗时 " + escapeHtml(String(step.step_elapsed)) + "s";
      } else if (status === "running") {
        timeLabel = escapeHtml(String(step.elapsed)) + "s";
      } else {
        timeLabel = escapeHtml(String(step.elapsed)) + "s";
      }
      html += '<div class="sim-progress-step-elapsed">' + timeLabel + "</div>";
    }
    html += "</div>";
  }
  html += "</div>";
  resultBox.innerHTML = html;
}

function updateConfigStageStatus(config, paths, pathRules, readiness = null) {
  const hasSource = Boolean(paths.source_dir);
  const hasTemp = Boolean(paths.temp_dir);
  const hasRecycle = Boolean(paths.recycle_dir);
  const hasRules = Array.isArray(pathRules) && pathRules.length > 0;
  const metadata = config.metadata || {};
  const hasScrape = Object.keys(metadata).length > 0;
  const storageReady = readiness?.state === "READY";
  const automationChosen = typeof config.file_watcher?.enabled === "boolean";
  const states = [
    ["source", hasSource],
    ["temp", storageReady || (hasTemp && hasRecycle)],
    ["recycle", storageReady && hasRules && hasScrape],
    ["rules", hasRules],
    ["scrape", hasScrape],
    ["ai", automationChosen],
  ];
  states.forEach(([stage, valid]) => {
    const card = document.querySelector(`[data-config-stage="${stage}"]`);
    if (!card) return;
    card.dataset.state = valid ? "valid" : "invalid";
  });
}

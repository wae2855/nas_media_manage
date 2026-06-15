// cinema-config-simulator.js - extracted from cinema-config.js
function explainSimulatedQueue(matchLevel, concerns) {
  if (matchLevel === "AUTO_PASS")
    return "标题精确匹配，自动通过，直接进入入库队列。";
  if (matchLevel === "CONTEXT_PASS")
    return "AI 辅助匹配通过，上下文信息支持自动入库。";
  if (matchLevel === "NEEDS_CONFIRM") {
    const concernMessages = (concerns || [])
      .map((c) => c.message || "")
      .filter(Boolean);
    if (concernMessages.length > 0) {
      return "需要人工确认：" + concernMessages.join("；") + "。";
    }
    return "需要人工确认匹配结果。";
  }
  return "匹配结果未知，请结合标题和 Provider 命中情况手动判断。";
}

function renderMatchPathPreview(data) {
  const clean = data.clean_result || {};
  const matchResult = data.match_result || {};
  const removedStr =
    clean.removed_items && clean.removed_items.length > 0
      ? clean.removed_items.join(" · ")
      : "—";

  const scrapeRes = data.scrape_result || {};
  const currentTitle =
    scrapeRes.title_cn ||
    scrapeRes.title_en ||
    scrapeRes.title ||
    clean.clean_title ||
    data.filename;
  const currentType = scrapeRes.type || scrapeRes.media_type || "—";
  const importPathInfo = data.import_path || {};

  const matchLevel = matchResult.match_level || "NEEDS_CONFIRM";
  const concerns = matchResult.concerns || [];
  const traceSteps = matchResult.trace || [];
  const queueExplanation = explainSimulatedQueue(matchLevel, concerns);

  let html = '<div class="sim-compare">';

  // --- timeline step 1: 文件名输入 ---
  html += '<div class="sim-timeline">';
  html += '<div class="sim-step">';
  html += '<div class="sim-step-rail">';
  html +=
    '<div class="sim-step-dot" style="background:#06B6D418;color:#06B6D4">1</div>';
  html += '<div class="sim-step-line" style="background:#06B6D430"></div>';
  html += "</div>";
  html += '<div class="sim-step-content">';
  html +=
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#06B6D4">文件名输入</span><span class="sim-step-tag" style="background:#06B6D418;color:#06B6D4">INPUT</span></div>';
  html += `<div class="sim-kv"><span class="sim-k">原始文件名</span><span class="sim-v">${escapeHtml(data.filename || "—")}</span></div>`;
  html += "</div></div>";

  // --- timeline step 2: 规则清洗 ---
  html += '<div class="sim-step">';
  html += '<div class="sim-step-rail">';
  html +=
    '<div class="sim-step-dot" style="background:#F59E0B18;color:#F59E0B">2</div>';
  html += '<div class="sim-step-line" style="background:#F59E0B30"></div>';
  html += "</div>";
  html += '<div class="sim-step-content">';
  html +=
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#F59E0B">规则清洗</span><span class="sim-step-tag" style="background:#F59E0B18;color:#F59E0B">REGEX</span></div>';
  html += `<div class="sim-kv"><span class="sim-k">清洗方法</span><span class="sim-v">${escapeHtml(clean.method || "regex")}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">去除项</span><span class="sim-v">${escapeHtml(removedStr)}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">clean_title</span><span class="sim-v sim-v-highlight">${escapeHtml(clean.clean_title || "—")}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">year</span><span class="sim-v sim-v-highlight">${clean.year || "—"}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">season / episode</span><span class="sim-v">${clean.season ? "S" + clean.season : "—"} / ${clean.episode ? "E" + clean.episode : "—"}</span></div>`;
  html += "</div></div>";

  // --- timeline step 3: 三级匹配路径 ---
  html += '<div class="sim-step">';
  html += '<div class="sim-step-rail">';
  html +=
    '<div class="sim-step-dot" style="background:#8B5CF618;color:#8B5CF6">3</div>';
  html += '<div class="sim-step-line" style="background:#8B5CF630"></div>';
  html += "</div>";
  html += '<div class="sim-step-content">';
  html +=
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#8B5CF6">三级匹配路径</span><span class="sim-step-tag" style="background:#8B5CF618;color:#8B5CF6">MATCH</span></div>';

  if (Array.isArray(traceSteps) && traceSteps.length > 0) {
    html +=
      '<div style="display:flex;flex-direction:column;gap:8px;margin-top:8px">';
    for (var si = 0; si < traceSteps.length; si++) {
      var step = traceSteps[si];
      var tierIcon =
        step.tier === 1
          ? "🗄️ "
          : step.tier === 2
            ? "🤖 "
            : step.tier === 3
              ? "👤 "
              : "";
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
        '08;padding:10px 14px;border-radius:8px">';
      html +=
        '<div style="font-weight:600;color:' +
        color +
        ';font-size:13px">第' +
        step.tier +
        "级：" +
        tierIcon +
        escapeHtml(step.name || "") +
        " · " +
        (step.matched ? "✓ 匹配" : "✗ 未匹配") +
        "</div>";
      if (step.reason)
        html +=
          '<div style="margin-top:6px;font-size:12px;line-height:1.5;color:#CBD5E1">' +
          escapeHtml(step.reason) +
          "</div>";
      if (step.ai_reason)
        html +=
          '<div style="margin-top:6px;font-size:12px;line-height:1.5;color:#06B6D4;border-left:2px solid #06B6D420;padding-left:10px">' +
          (step.tier === 2 ? "🤖 AI辅助: " : "AI: ") +
          escapeHtml(step.ai_reason) +
          "</div>";
      html += "</div>";
    }
    html += "</div>";
  } else {
    html +=
      '<div style="margin-top:8px;color:#94A3B8;font-size:13px">无匹配路径信息</div>';
  }

  if (concerns.length > 0) {
    html += '<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px">';
    for (var ci = 0; ci < concerns.length; ci++) {
      var c = concerns[ci];
      html +=
        '<span style="font-size:11px;padding:3px 10px;border-radius:999px;background:rgba(245,158,11,0.12);color:#F59E0B;font-weight:500">' +
        escapeHtml(c.message) +
        "</span>";
    }
    html += "</div>";
  }

  html += "</div></div>";

  // --- timeline step 4: 刮削结果 ---
  html += '<div class="sim-step">';
  html += '<div class="sim-step-rail">';
  html +=
    '<div class="sim-step-dot" style="background:#06B6D418;color:#06B6D4">4</div>';
  html += '<div class="sim-step-line" style="background:#06B6D430"></div>';
  html += "</div>";
  html += '<div class="sim-step-content">';
  html +=
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#06B6D4">刮削结果</span><span class="sim-step-tag" style="background:#06B6D418;color:#06B6D4">SCRAPE</span></div>';
  html +=
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">';
  html += `<div class="sim-kv"><span class="sim-k">中文标题</span><span class="sim-v sim-v-highlight">${escapeHtml(scrapeRes.title_cn || "—")}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">英文标题</span><span class="sim-v">${escapeHtml(scrapeRes.title_en || "—")}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">年份</span><span class="sim-v">${scrapeRes.year || "—"}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">类型</span><span class="sim-v">${escapeHtml(currentType)}</span></div>`;
  if (scrapeRes.provider_type) {
    html += `<div class="sim-kv"><span class="sim-k">Provider</span><span class="sim-v">${escapeHtml(scrapeRes.provider_type + (scrapeRes.provider_id ? " · " + scrapeRes.provider_id : ""))}</span></div>`;
  }
  if (scrapeRes.season != null)
    html += `<div class="sim-kv"><span class="sim-k">季</span><span class="sim-v">S${scrapeRes.season}</span></div>`;
  if (scrapeRes.episode != null)
    html += `<div class="sim-kv"><span class="sim-k">集</span><span class="sim-v">E${scrapeRes.episode}</span></div>`;
  html += "</div>";
  if (scrapeRes.dimensions) {
    html += `<div style="margin-top:8px">${_renderSimDims(scrapeRes.dimensions)}</div>`;
  }
  if (scrapeRes.preview_selected_candidate) {
    html +=
      '<div class="sim-warning">已按 Provider 返回排序默认加载第一候选生成预览结果，请检查后确认。</div>';
  }
  if (scrapeRes.confirm_reason) {
    html += `<div class="sim-warning">${escapeHtml(scrapeRes.confirm_reason)}</div>`;
  }
  html += "</div></div>";

  // --- timeline step 5: 最终入库判断 ---
  html += '<div class="sim-step">';
  html += '<div class="sim-step-rail">';
  html +=
    '<div class="sim-step-dot" style="background:#22C55E18;color:#22C55E">5</div>';
  html += '<div class="sim-step-line" style="background:transparent"></div>';
  html += "</div>";
  html += '<div class="sim-step-content">';
  html +=
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#22C55E">最终入库判断</span><span class="sim-step-tag" style="background:#22C55E18;color:#22C55E">RESULT</span></div>';
  html += `<div class="sim-kv"><span class="sim-k">最终标题</span><span class="sim-v sim-v-highlight">${escapeHtml(currentTitle || "未识别标题")}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">类型</span><span class="sim-v">${escapeHtml(currentType)}</span></div>`;
  const finalMatchLabel =
    matchLevel === "AUTO_PASS"
      ? "自动匹配"
      : matchLevel === "CONTEXT_PASS"
        ? "🤖 AI辅助匹配"
        : "待人工确认";
  const finalMatchColor =
    matchLevel === "AUTO_PASS"
      ? "#22C55E"
      : matchLevel === "CONTEXT_PASS"
        ? "#06B6D4"
        : "#F59E0B";
  html += `<div class="sim-kv"><span class="sim-k">匹配级别</span><span class="sim-v sim-v-score" style="color:${finalMatchColor}">${finalMatchLabel}</span></div>`;
  if (importPathInfo.import_path) {
    const pathLabel = importPathInfo.used_fallback
      ? "入库目录（兜底）"
      : importPathInfo.matched_rule
        ? `入库目录（规则 ${importPathInfo.matched_rule}）`
        : "入库目录";
    html += `<div class="sim-kv"><span class="sim-k">${escapeHtml(pathLabel)}</span><span class="sim-v sim-v-highlight">${escapeHtml(importPathInfo.import_path)}</span></div>`;
  } else {
    html += `<div class="sim-kv"><span class="sim-k">入库目录</span><span class="sim-v" style="color:var(--warning-fg,#856404)">未匹配规则且无兜底目录</span></div>`;
  }
  const queueColor =
    matchLevel === "AUTO_PASS"
      ? "#22C55E"
      : matchLevel === "CONTEXT_PASS"
        ? "#06B6D4"
        : "#F59E0B";
  html += `<div class="sim-queue-decision" style="border-color:${queueColor}30;background:${queueColor}08;color:${queueColor}">${escapeHtml(queueExplanation)}</div>`;
  html += "</div></div>";

  html += "</div>";
  html += "</div>";
  return html;
}

function renderSimulatorPreview(data) {
  const result = document.getElementById("match-preview-result");
  if (!result) return;
  result.innerHTML = renderMatchPathPreview(data);
}

function _simDecisionLabel2(matchLevel, gateBlocked) {
  if (gateBlocked) return "维度否决";
  if (matchLevel === "AUTO_PASS") return "自动入库";
  if (matchLevel === "CONTEXT_PASS") return "🤖 AI辅助入库";
  if (matchLevel === "NEEDS_CONFIRM") return "待确认";
  return "未识别";
}

function _simFormatNumber(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return num.toFixed(3);
}

function _renderSimDims(dims) {
  if (!dims || typeof dims !== "object") return "";
  let html = '<div class="sim-dim-list">';
  for (const key in dims) {
    const val = dims[key];
    const displayVal =
      typeof val === "object" && val !== null
        ? val.value || JSON.stringify(val)
        : val;
    html += `<span class="sim-dim-tag">${escapeHtml(key)}=${escapeHtml(String(displayVal))}</span>`;
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
      '<div class="sim-warning" style="margin-top:0">模拟测试超时，请检查 Provider / AI 配置或查看后端日志。</div>';
  }
  showToast("模拟测试超时，请检查 Provider / AI 配置");
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

function updateConfigStageStatus(config, paths, pathRules) {
  const hasSource = Boolean(paths.source_dir);
  const hasTemp = Boolean(paths.temp_dir);
  const hasRecycle = Boolean(paths.recycle_dir);
  const hasRules = Array.isArray(pathRules) && pathRules.length > 0;
  const metadata = config.metadata || {};
  const llm = config.llm || {};
  const hasScrape = Object.keys(metadata).length > 0;
  const hasAi = Boolean(llm.base_url || llm.model || llm.api_key);
  const states = [
    ["source", hasSource],
    ["temp", hasTemp],
    ["recycle", hasRecycle],
    ["rules", hasRules],
    ["scrape", hasScrape],
    ["ai", hasAi],
  ];
  states.forEach(([stage, valid]) => {
    const card = document.querySelector(`[data-config-stage="${stage}"]`);
    if (!card) return;
    card.dataset.state = valid ? "valid" : "invalid";
  });
}


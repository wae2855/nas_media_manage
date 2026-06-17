// cinema-config-simulator.js - extracted from cinema-config.js
function explainSimulatedQueue(matchResult) {
  const tier = matchResult.match_tier || 0;
  const level = matchResult.match_level;
  const shortReason = matchResult.tier_short_reason || "";

  if (shortReason) {
    return shortReason;
  }

  if (level === "AUTO_PASS") return "标题精确匹配，自动通过。";
  if (level === "CONTEXT_PASS") return "AI 辅助匹配通过。";
  if (level === "NEEDS_CONFIRM") {
    const concerns = matchResult.concerns || [];
    if (concerns.length > 0) {
      return (
        "需要人工确认：" + concerns.map((c) => c.message).join("；") + "。"
      );
    }
    return "需要人工确认匹配结果。";
  }
  if (level === "FAILED") return "AI 判定为非影视文件，任务失败。";
  return "匹配结果未知。";
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

  const matchLevel =
    matchResult.match_level || scrapeRes.match_level || "NEEDS_CONFIRM";
  const concerns = matchResult.concerns || [];
  const traceSteps = matchResult.trace || [];
  const queueExplanation = explainSimulatedQueue(matchResult);

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
      var certaintyTag = "";
      if (step.tier === 2) {
        var stepReason = step.reason || "";
        if (stepReason.includes("高确定性")) {
          certaintyTag =
            '<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:rgba(34,197,94,0.12);color:#22C55E;margin-left:4px;">高</span>';
        } else if (stepReason.includes("中确定性")) {
          certaintyTag =
            '<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:rgba(245,158,11,0.12);color:#F59E0B;margin-left:4px;">中</span>';
        } else if (stepReason.includes("低确定性")) {
          certaintyTag =
            '<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:rgba(217,79,69,0.12);color:#D94F45;margin-left:4px;">低</span>';
        }
      }
      var searchInfo = "";
      if (step.search_query) {
        searchInfo = `<div style="font-size:11px;color:var(--muted);margin-top:2px;">搜索：${escapeHtml(step.search_query)}</div>`;
      }
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
        certaintyTag +
        " · " +
        (step.matched ? "✓ 匹配" : "✗ 未匹配") +
        "</div>";
      if (searchInfo) html += searchInfo;
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

  // 候选列表（按可信度排序）
  var candidates = matchResult.candidates || [];
  if (candidates.length > 0) {
    html += '<div class="sim-candidates" style="margin-top:8px;">';
    html +=
      '<div style="font-size:11px;color:var(--muted);margin-bottom:4px;">候选列表（按可信度）</div>';

    var sorted = candidates.slice().sort(function (a, b) {
      return (b.popularity || 0) - (a.popularity || 0);
    });

    for (var ci = 0; ci < sorted.length; ci++) {
      var c = sorted[ci];
      var stars = c.vote_average ? "⭐ " + c.vote_average.toFixed(1) : "";
      var votes = c.vote_count ? "(" + c.vote_count + "票" : "";
      var pop = c.popularity ? " · 热度" + Math.round(c.popularity) : "";
      var year = c.year ? "(" + c.year + ")" : "";
      var origTitle =
        c.original_title && c.original_title !== c.title
          ? " / " + escapeHtml(c.original_title)
          : "";

      html +=
        '<div style="font-size:12px;padding:4px 8px;margin:2px 0;background:rgba(255,255,255,0.04);border-radius:4px;">';
      html +=
        (ci === 0 ? "✅" : "○") +
        " " +
        escapeHtml(c.title) +
        " " +
        year +
        origTitle;
      html +=
        '<span style="color:var(--muted);font-size:11px;">' +
        stars +
        " " +
        votes +
        pop +
        "</span>";
      html += "</div>";
    }
    html += "</div>";
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
  if (matchLevel === "FAILED") {
    const failReason =
      scrapeRes.tier_short_reason ||
      matchResult.tier_short_reason ||
      "AI 判定无可识别影视信息";
    html += '<div class="sim-step">';
    html += '<div class="sim-step-rail">';
    html +=
      '<div class="sim-step-dot" style="background:#D94F4518;color:#D94F45">4</div>';
    html += '<div class="sim-step-line" style="background:transparent"></div>';
    html += "</div>";
    html += '<div class="sim-step-content">';
    html +=
      '<div class="sim-step-header"><span class="sim-step-title" style="color:#D94F45">刮削失败</span><span class="sim-step-tag" style="background:#D94F4518;color:#D94F45">FAILED</span></div>';
    html += `<div class="sim-alert">${escapeHtml(failReason)}</div>`;
    html += "</div></div>";
    html += "</div>";
    html += "</div>";
    return html;
  }

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
  const selected = scrapeRes.selected_candidate;
  if (selected && selected.why_selected) {
    const whyMap = {
      unique_match: "唯一精确匹配",
      top_rated: "评分最高",
      ai_suggestion: "AI 建议",
      first_candidate: "Provider 排序第一",
      user_pick: "用户选择",
    };
    const whyText = whyMap[selected.why_selected] || selected.why_selected;
    html += `<div class="sim-warning">已加载第一候选（${escapeHtml(whyText)}），请检查后确认。</div>`;
  }
  html += "</div></div>";

  // --- timeline step 5: 维度推导 ---
  const hasDims =
    scrapeRes.dimensions && Object.keys(scrapeRes.dimensions).length > 0;
  html += '<div class="sim-step">';
  html += '<div class="sim-step-rail">';
  html +=
    '<div class="sim-step-dot" style="background:#8B5CF618;color:#8B5CF6">5</div>';
  html += '<div class="sim-step-line" style="background:#8B5CF630"></div>';
  html += "</div>";
  html += '<div class="sim-step-content">';
  html +=
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#8B5CF6">维度推导</span><span class="sim-step-tag" style="background:#8B5CF618;color:#8B5CF6">DIMS</span></div>';
  if (hasDims) {
    html += _renderSimDims(scrapeRes.dimensions);
  } else {
    html += '<div class="sim-alert">暂无维度推导结果。</div>';
  }
  html += "</div></div>";

  // 已入库任务：跳过 NEEDS_CONFIRM，直接显示入库结果
  if (data.status === "SUCCESS") {
    const confirmedOverride = data.confirmed_override ? 1 : 0;
    const confirmedTitle = data.confirmed_title || currentTitle || "";
    html += '<div class="sim-step">';
    html += '<div class="sim-step-rail">';
    html +=
      '<div class="sim-step-dot" style="background:#22C55E18;color:#22C55E">6</div>';
    html += '<div class="sim-step-line" style="background:transparent"></div>';
    html += "</div>";
    html += '<div class="sim-step-content">';
    if (confirmedOverride && confirmedTitle) {
      html +=
        '<div class="sim-step-header"><span class="sim-step-title" style="color:#22C55E">以《' +
        escapeHtml(confirmedTitle) +
        '》入库</span><span class="sim-step-tag" style="background:#22C55E18;color:#22C55E">IMPORTED</span></div>';
      html +=
        '<div class="sim-alert" style="background:#22C55E08;border-color:#22C55E30">用户选择了新的元数据后确认入库。</div>';
    } else {
      html +=
        '<div class="sim-step-header"><span class="sim-step-title" style="color:#22C55E">直接确认入库</span><span class="sim-step-tag" style="background:#22C55E18;color:#22C55E">IMPORTED</span></div>';
      html +=
        '<div class="sim-alert" style="background:#22C55E08;border-color:#22C55E30">用户确认刮削结果后直接入库。</div>';
    }
    if (importPathInfo.import_video_path) {
      html +=
        '<div class="sim-kv"><span class="sim-k">入库路径</span><span class="sim-v sim-v-highlight">' +
        escapeHtml(importPathInfo.import_video_path) +
        "</span></div>";
    }
    html += "</div></div>";
    html += "</div>";
    html += "</div>";
    return html;
  }

  // 待确认但 match_level 不是 NEEDS_CONFIRM（如 manual_review 全局开启）
  if (data.stage === "AWAIT_REVIEW" && matchLevel !== "NEEDS_CONFIRM") {
    html += '<div class="sim-step">';
    html += '<div class="sim-step-rail">';
    html +=
      '<div class="sim-step-dot" style="background:#F59E0B18;color:#F59E0B">6</div>';
    html += '<div class="sim-step-line" style="background:transparent"></div>';
    html += "</div>";
    html += '<div class="sim-step-content">';
    html +=
      '<div class="sim-step-header"><span class="sim-step-title" style="color:#F59E0B">待人工确认</span><span class="sim-step-tag" style="background:#F59E0B18;color:#F59E0B">CONFIRM</span></div>';
    html +=
      '<div class="sim-alert">系统开启了全局人工审核，确认后才能入库。</div>';
    html += "</div></div>";
    html += "</div>";
    html += "</div>";
    return html;
  }

  if (matchLevel === "NEEDS_CONFIRM") {
    html += '<div class="sim-step">';
    html += '<div class="sim-step-rail">';
    html +=
      '<div class="sim-step-dot" style="background:#F59E0B18;color:#F59E0B">6</div>';
    html += '<div class="sim-step-line" style="background:transparent"></div>';
    html += "</div>";
    html += '<div class="sim-step-content">';
    html +=
      '<div class="sim-step-header"><span class="sim-step-title" style="color:#F59E0B">待人工确认</span><span class="sim-step-tag" style="background:#F59E0B18;color:#F59E0B">CONFIRM</span></div>';
    html += '<div class="sim-alert">确认后才能入库。</div>';
    html += "</div></div>";
    html += "</div>";
    html += "</div>";
    return html;
  }

  // --- timeline step 6: 最终入库判断 ---
  html += '<div class="sim-step">';
  html += '<div class="sim-step-rail">';
  html +=
    '<div class="sim-step-dot" style="background:#22C55E18;color:#22C55E">6</div>';
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
  const dimDefs = window.currentEnabledDimensions || [];
  const allDimDefs = window._dimensionsData || [];
  const sourceLabels = {
    tmdb: "Provider",
    ai_assist: "AI辅助",
    ai_search: "AI搜索",
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
  for (const key in dims) {
    const val = dims[key];
    const isObj = typeof val === "object" && val !== null;
    const displayVal = isObj ? val.value || JSON.stringify(val) : val;
    const source = isObj ? val.source || "" : "";
    const dimDef =
      dimDefs.find((d) => d.name === key) ||
      allDimDefs.find((d) => d.name === key);
    const dimLabel = dimDef ? dimDef.label || dimDef.name : key;
    const dimColor =
      dimDef && dimDef.color
        ? dimDef.color
        : fallbackColors[colorIdx++ % fallbackColors.length];
    let valLabel = String(displayVal);
    if (dimDef && Array.isArray(dimDef.value_list)) {
      const matched = dimDef.value_list.find(
        (v) => String(v.value) === String(displayVal),
      );
      if (matched) valLabel = matched.label || String(displayVal);
    }
    const sourceBadge = source
      ? `<span class="sim-dim-source sim-dim-source--${escapeHtml(source)}">${escapeHtml(sourceLabels[source] || source)}</span>`
      : "";
    html += `<span class="sim-dim-tag" style="--dim-color:${escapeHtml(dimColor)}"><span class="sim-dim-label">${escapeHtml(dimLabel)}</span><span class="sim-dim-val">${escapeHtml(valLabel)}</span>${sourceBadge}</span>`;
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

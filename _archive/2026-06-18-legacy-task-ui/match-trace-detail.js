// 匹配路径详情：展示三级匹配路径、Provider 搜索、AI 辅助、候选列表、
// 最终 match_level 与 dim_sources。

function _levelColor(level) {
  if (level === "AUTO_PASS") return "#22C55E";
  if (level === "CONTEXT_PASS") return "#3B82F6";
  if (level === "NEEDS_CONFIRM") return "#F59E0B";
  return "#94A3B8";
}

function _levelLabel(level) {
  if (level === "AUTO_PASS") return "自动通过";
  if (level === "CONTEXT_PASS") return "🤖 AI 辅助通过";
  if (level === "NEEDS_CONFIRM") return "需人工确认";
  return "未知";
}

function _sourceTag(source) {
  if (source === "tmdb" || source === "provider")
    return '<span style="display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(139,92,246,0.12);color:#8B5CF6;font-weight:600">PROVIDER</span>';
  if (source === "ai")
    return '<span style="display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(239,68,68,0.1);color:#EF4444;font-weight:600">AI</span>';
  if (source === "ai_assist")
    return '<span style="display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(239,68,68,0.1);color:#EF4444;font-weight:600">AI辅助</span>';
  if (source === "ai_search")
    return '<span style="display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(6,182,212,0.12);color:#06B6D4;font-weight:600">AI搜索</span>';
  if (source === "file")
    return '<span style="display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(34,197,94,0.1);color:#22C55E;font-weight:600">FILE</span>';
  return '<span style="display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(148,163,184,0.1);color:#94A3B8;font-weight:600">缺失</span>';
}

function closeMatchTraceDetailModal() {
  var overlay = document.querySelector(".conf-detail-overlay");
  if (overlay) overlay.remove();
}

function _buildTraceStep(num, title, tag, color, contentHtml, isLast) {
  var lineStyle = isLast
    ? "background:transparent"
    : "background:" + color + "30";
  return (
    '<div class="conf-trace-step">' +
    '<div class="conf-trace-rail">' +
    '<div class="conf-trace-dot" style="background:' +
    color +
    "18;color:" +
    color +
    '">' +
    num +
    "</div>" +
    '<div class="conf-trace-line" style="' +
    lineStyle +
    '"></div>' +
    "</div>" +
    '<div class="conf-trace-content">' +
    '<div class="conf-step-header">' +
    '<span style="font-size:15px;font-weight:700;color:' +
    color +
    '">' +
    escapeHtml(title) +
    "</span>" +
    '<span class="conf-step-tag" style="background:' +
    color +
    "18;color:" +
    color +
    '">' +
    tag +
    "</span>" +
    "</div>" +
    contentHtml +
    "</div>" +
    "</div>"
  );
}

function showMatchTraceDetailModal(traceData, filename) {
  var existing = document.querySelector(".conf-detail-overlay");
  if (existing) existing.remove();

  var trace = traceData;
  if (typeof trace === "string") {
    try {
      trace = JSON.parse(trace);
    } catch (e) {
      return;
    }
  }
  if (!trace || typeof trace !== "object") return;

  var matchLevel = trace.match_level || trace.level || "NEEDS_CONFIRM";
  var matchConcerns = trace.match_concerns || trace.concerns || [];
  var dimSources = trace.dim_sources || {};
  var matchTraceSteps = trace.match_trace || trace.trace_steps || [];

  var matchColor = _levelColor(matchLevel);
  var matchLabel = _levelLabel(matchLevel);
  var fc = trace.filename_clean || {};

  var steps = [];

  steps.push({
    title: "文件名输入",
    tag: "INPUT",
    color: "#06B6D4",
    html:
      '<div class="conf-detail-card">' +
      '<div class="conf-kv"><span class="conf-k">原始文件名</span><span class="conf-v">' +
      escapeHtml(fc.original || filename || "-") +
      "</span></div>" +
      "</div>",
  });

  var cleanTitle = fc.clean_title || "-";
  var cleanYear = fc.year || null;
  var cleanSeason = fc.season || null;
  var cleanEpisode = fc.episode || null;
  var cleanMethod = fc.clean_method || "regex";
  var removedItems = fc.removed_items || [];
  var removedStr = removedItems.length > 0 ? removedItems.join(" ") : "-";

  steps.push({
    title: "规则清洗",
    tag: "REGEX",
    color: "#F59E0B",
    html:
      '<div class="conf-detail-card">' +
      '<div class="conf-kv"><span class="conf-k">清洗方法</span><span class="conf-v">' +
      escapeHtml(cleanMethod) +
      "</span></div>" +
      '<div class="conf-kv"><span class="conf-k">去除项</span><span class="conf-v">' +
      escapeHtml(removedStr) +
      "</span></div>" +
      '<div class="conf-kv"><span class="conf-k">clean_title</span><span class="conf-v" style="color:#06B6D4;font-weight:600">' +
      escapeHtml(cleanTitle) +
      "</span></div>" +
      '<div class="conf-kv"><span class="conf-k">year</span><span class="conf-v" style="color:#06B6D4;font-weight:600">' +
      (cleanYear !== null && cleanYear !== undefined
        ? escapeHtml(String(cleanYear))
        : "—") +
      "</span></div>" +
      '<div class="conf-kv"><span class="conf-k">season / episode</span><span class="conf-v">' +
      (cleanSeason !== null && cleanSeason !== undefined
        ? "S" + cleanSeason
        : "—") +
      " / " +
      (cleanEpisode !== null && cleanEpisode !== undefined
        ? "E" + cleanEpisode
        : "—") +
      "</span></div>" +
      "</div>",
  });

  if (trace.ai_clean) {
    steps.push({
      title: "AI 辅助清洗",
      tag: "AI",
      color: "#F59E0B",
      html:
        '<div class="conf-detail-card">' +
        '<div class="conf-kv"><span class="conf-k">AI 提取标题</span><span class="conf-v" style="color:#06B6D4;font-weight:600">' +
        escapeHtml(trace.ai_clean.clean_title || "-") +
        "</span></div>" +
        '<div class="conf-kv"><span class="conf-k">方法</span><span class="conf-v">' +
        escapeHtml(trace.ai_clean.method || "ai") +
        "</span></div>" +
        "</div>",
    });
  }

  var providerSearch = trace.provider_search || {};
  if (providerSearch && Object.keys(providerSearch).length) {
    var providerName = trace.provider_type || "tmdb";
    var providerLabel =
      providerName === "tmdb" || providerName === "provider"
        ? "Provider"
        : providerName.toUpperCase();
    steps.push({
      title: providerLabel + " 搜索",
      tag: providerLabel,
      color: "#8B5CF6",
      html:
        '<div class="conf-detail-card">' +
        '<div class="conf-kv"><span class="conf-k">搜索词</span><span class="conf-v">' +
        escapeHtml(providerSearch.query || "-") +
        (cleanYear ? " + year=" + cleanYear : "") +
        "</span></div>" +
        '<div class="conf-kv"><span class="conf-k">total_results</span><span class="conf-v" style="color:#06B6D4;font-weight:600">' +
        (providerSearch.total_results !== undefined
          ? providerSearch.total_results
          : "-") +
        "</span></div>" +
        '<div class="conf-kv"><span class="conf-k">匹配结果</span><span class="conf-v">' +
        escapeHtml(providerSearch.selected_title || "-") +
        (providerSearch.selected_year
          ? " (" + providerSearch.selected_year + ")"
          : "") +
        "</span></div>" +
        (providerSearch.selected_original_title
          ? '<div class="conf-kv"><span class="conf-k">original_title</span><span class="conf-v">' +
            escapeHtml(providerSearch.selected_original_title) +
            "</span></div>"
          : "") +
        "</div>",
    });
  }

  if (Array.isArray(matchTraceSteps) && matchTraceSteps.length) {
    var tierHtml = '<div class="conf-detail-card">';
    matchTraceSteps.forEach(function (step, index) {
      tierHtml +=
        '<div class="conf-kv">' +
        '<span class="conf-k">Tier ' +
        (index + 1) +
        " · " +
        escapeHtml(step.tier || step.name || "-") +
        "</span>" +
        '<span class="conf-v">' +
        escapeHtml(
          step.reason || step.ai_reason || step.result || step.message || "-",
        ) +
        "</span>" +
        "</div>";
    });
    tierHtml += "</div>";
    steps.push({
      title: "三级匹配路径",
      tag: "MATCH",
      color: "#A78BFA",
      html: tierHtml,
    });
  }

  if (matchConcerns.length) {
    var concernHtml = '<div class="conf-detail-card">';
    matchConcerns.forEach(function (c) {
      concernHtml +=
        '<div class="conf-kv">' +
        '<span class="conf-k">' +
        escapeHtml(c.code || "-") +
        "</span>" +
        '<span class="conf-v">' +
        escapeHtml(c.message || "-") +
        "</span>" +
        "</div>";
    });
    concernHtml += "</div>";
    steps.push({
      title: "待人工确认原因",
      tag: "CONCERN",
      color: "#F59E0B",
      html: concernHtml,
    });
  }

  var candidates = trace.candidates || [];
  if (candidates.length) {
    var sortedCands = candidates.slice(0, 5).sort(function (a, b) {
      return (b.popularity || 0) - (a.popularity || 0);
    });
    var candHtml = '<div class="conf-detail-card">';
    sortedCands.forEach(function (c, index) {
      var stars = c.vote_average
        ? "⭐ " + Number(c.vote_average).toFixed(1)
        : "";
      var votes = c.vote_count ? "票" + c.vote_count : "";
      var pop = c.popularity ? "热度" + Math.round(c.popularity) : "";
      var metaParts = [stars, votes, pop].filter(Boolean).join(" · ");
      candHtml +=
        '<div class="conf-kv">' +
        '<span class="conf-k">候选 ' +
        (index + 1) +
        "</span>" +
        '<span class="conf-v">' +
        escapeHtml(c.title || "-") +
        (c.year ? " (" + c.year + ")" : "") +
        (metaParts
          ? '<span style="color:var(--muted);font-size:10px;margin-left:6px;">' +
            escapeHtml(metaParts) +
            "</span>"
          : "") +
        "</span>" +
        "</div>";
    });
    candHtml += "</div>";
    steps.push({
      title: "候选列表",
      tag: "CAND",
      color: "#8B5CF6",
      html: candHtml,
    });
  }

  if (Object.keys(dimSources).length) {
    var dimTableHtml =
      '<div class="conf-detail-card"><div class="conf-dim-table">' +
      '<div class="conf-dim-row conf-dim-header">' +
      "<span>维度</span><span>来源</span>" +
      "</div>";
    Object.keys(dimSources).forEach(function (dimName) {
      dimTableHtml +=
        '<div class="conf-dim-row">' +
        "<span>" +
        escapeHtml(dimName) +
        "</span>" +
        "<span>" +
        _sourceTag(dimSources[dimName]) +
        "</span>" +
        "</div>";
    });
    dimTableHtml +=
      "</div>" +
      '<div style="font-size:11px;color:var(--text-secondary);margin-top:6px;line-height:1.4">dim_sources 记录每个维度的来源：Provider / AI 辅助 / AI 搜索 / 文件解析。被禁用的 AI 来源会触发 trust 降级。</div>' +
      "</div>";
    steps.push({
      title: "维度来源",
      tag: "DIM",
      color: "#3B82F6",
      html: dimTableHtml,
    });
  }

  var finalHtml =
    '<div class="conf-detail-card">' +
    '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">' +
    '<span style="font-size:13px;font-weight:700;padding:4px 12px;border-radius:999px;background:' +
    matchColor +
    "20;color:" +
    matchColor +
    '">' +
    matchLabel +
    "</span>" +
    '<span style="font-family:monospace;font-size:13px;color:' +
    matchColor +
    '">' +
    escapeHtml(matchLevel) +
    "</span>" +
    "</div>" +
    '<div style="font-size:11px;color:var(--text-secondary);margin-top:6px;line-height:1.4">匹配级别由三级匹配策略决定（自动通过/需确认）。</div>' +
    "</div>";
  steps.push({
    title: "最终匹配状态",
    tag: "RESULT",
    color: matchColor,
    html: finalHtml,
  });

  var stepsHtml = "";
  for (var i = 0; i < steps.length; i++) {
    var isLast = i === steps.length - 1;
    stepsHtml += _buildTraceStep(
      i + 1,
      steps[i].title,
      steps[i].tag,
      steps[i].color,
      steps[i].html,
      isLast,
    );
  }

  var overlay = document.createElement("div");
  overlay.className = "conf-detail-overlay";
  overlay.innerHTML =
    '<div class="conf-detail-modal">' +
    '<div class="conf-detail-header">' +
    '<div style="display:flex;align-items:center;gap:12px;flex:1;min-width:0">' +
    '<h3 style="margin:0;font-size:16px;white-space:nowrap">匹配路径详情</h3>' +
    '<span style="font-family:monospace;font-size:13px;color:#06B6D4;background:rgba(6,182,212,0.1);padding:4px 10px;border-radius:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' +
    escapeHtml(filename || "-") +
    "</span>" +
    "</div>" +
    '<div style="display:flex;align-items:center;gap:8px">' +
    '<span style="font-size:14px;font-weight:700;padding:4px 12px;border-radius:999px;background:' +
    matchColor +
    "20;color:" +
    matchColor +
    '">' +
    matchLabel +
    "</span>" +
    '<button style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:20px;padding:4px 8px" onclick="closeMatchTraceDetailModal()">&times;</button>' +
    "</div>" +
    "</div>" +
    '<div class="conf-detail-body">' +
    stepsHtml +
    "</div>" +
    "</div>";

  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) {
      closeMatchTraceDetailModal();
    }
  });

  document.body.appendChild(overlay);
}

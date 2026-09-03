// cinema-config-simulator.js - extracted from cinema-config.js
function explainSimulatedQueue(matchResult) {
  const tier = matchResult.match_tier || 0;
  const level = matchResult.match_level;
  const shortReason = matchResult.tier_short_reason || "";

  if (shortReason) {
    return shortReason;
  }

  if (level === "AUTO_PASS") return "标题精确匹配，自动通过。";
  if (level === "NEEDS_CONFIRM") {
    const concerns = matchResult.concerns || [];
    if (concerns.length > 0) {
      return (
        "需要人工确认：" + concerns.map((c) => c.message).join("；") + "。"
      );
    }
    return "需要人工确认匹配结果。";
  }
  if (level === "FAILED") return "未找到可用的影视信息，任务失败。";
  return "匹配结果未知。";
}

function mediaTypeLabel(value) {
  if (value === "movie") return "电影";
  if (value === "tv" || value === "series") return "剧集";
  return value || "—";
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
  const currentType = mediaTypeLabel(scrapeRes.type || scrapeRes.media_type);
  const importPathInfo = data.import_path || {};

  const matchLevel =
    matchResult.match_level || scrapeRes.match_level || "NEEDS_CONFIRM";
  const concerns = matchResult.concerns || [];
  const traceSteps = matchResult.trace || [];
  const identityEvidence = matchResult.identity_evidence || {};
  const identitySignals = Array.isArray(identityEvidence.signals)
    ? identityEvidence.signals
    : [];
  const folderSignal = identitySignals.find((item) => item.source === "folder");
  const ignoredDirectories = Array.isArray(identityEvidence.ignored_directories)
    ? identityEvidence.ignored_directories
    : [];
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
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#06B6D4">文件名输入</span><span class="sim-step-tag" style="background:#06B6D418;color:#06B6D4">文件识别</span></div>';
  html += `<div class="sim-kv"><span class="sim-k">原始文件名</span><span class="sim-v">${escapeHtml(data.filename || "—")}</span></div>`;
  if (folderSignal) {
    html += `<div class="sim-kv"><span class="sim-k">辅助目录名</span><span class="sim-v">${escapeHtml(folderSignal.raw_name || "—")}</span></div>`;
  } else if (ignoredDirectories.length > 0 && ignoredDirectories[0].name) {
    html += `<div class="sim-kv"><span class="sim-k">目录未参与</span><span class="sim-v">${escapeHtml(ignoredDirectories[0].reason || "不是有效片名目录")}</span></div>`;
  }
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
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#F59E0B">规则清洗</span><span class="sim-step-tag" style="background:#F59E0B18;color:#F59E0B">规则清洗</span></div>';
  html += `<div class="sim-kv"><span class="sim-k">清洗方法</span><span class="sim-v">${escapeHtml(clean.method === "regex" ? "规则识别" : clean.method || "规则识别")}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">去除项</span><span class="sim-v">${escapeHtml(removedStr)}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">清洗后标题</span><span class="sim-v sim-v-highlight">${escapeHtml(clean.clean_title || "—")}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">年份</span><span class="sim-v sim-v-highlight">${clean.year || "—"}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">季 / 集</span><span class="sim-v">${clean.season ? "S" + clean.season : "—"} / ${clean.episode ? "E" + clean.episode : "—"}</span></div>`;
  html += "</div></div>";

  // --- timeline step 3: 两级匹配路径 ---
  html += '<div class="sim-step">';
  html += '<div class="sim-step-rail">';
  html +=
    '<div class="sim-step-dot" style="background:#8B5CF618;color:#8B5CF6">3</div>';
  html += '<div class="sim-step-line" style="background:#8B5CF630"></div>';
  html += "</div>";
  html += '<div class="sim-step-content">';
  html +=
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#8B5CF6">两级匹配路径</span><span class="sim-step-tag" style="background:#8B5CF618;color:#8B5CF6">智能匹配</span></div>';

  if (Array.isArray(traceSteps) && traceSteps.length > 0) {
    html +=
      '<div style="display:flex;flex-direction:column;gap:8px;margin-top:8px">';
    for (var si = 0; si < traceSteps.length; si++) {
      var step = traceSteps[si];
      var tierIcon = step.tier === 1 ? "🗄️ " : step.tier === 2 ? "👤 " : "";
      var color = step.matched
        ? "#22C55E"
        : step.tier === 2
          ? "#F59E0B"
          : "#94A3B8";
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
        " · " +
        (step.matched ? "✓ 匹配" : "✗ 未匹配") +
        "</div>";
      if (searchInfo) html += searchInfo;
      if (step.reason)
        html +=
          '<div style="margin-top:6px;font-size:12px;line-height:1.5;color:#CBD5E1">' +
          escapeHtml(String(step.reason).replace(/^L\d+:\s*/, "")) +
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
      "未找到可用的影视信息";
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
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#06B6D4">刮削结果</span><span class="sim-step-tag" style="background:#06B6D418;color:#06B6D4">刮削</span></div>';
  html +=
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">';
  html += `<div class="sim-kv"><span class="sim-k">中文标题</span><span class="sim-v sim-v-highlight">${escapeHtml(scrapeRes.title_cn || "—")}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">英文标题</span><span class="sim-v">${escapeHtml(scrapeRes.title_en || "—")}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">年份</span><span class="sim-v">${scrapeRes.year || "—"}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">类型</span><span class="sim-v">${escapeHtml(currentType)}</span></div>`;
  if (scrapeRes.provider_type) {
    html += `<div class="sim-kv"><span class="sim-k">数据来源</span><span class="sim-v">${escapeHtml(scrapeRes.provider_type === "tmdb" ? "TMDB" : scrapeRes.provider_type)}</span></div>`;
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
      ai_suggestion: "历史 AI 建议",
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
    var traceInfo = data.scrape_trace || {};
    var srcParts = [];
    if (
      traceInfo.provider_dimensions &&
      Object.keys(traceInfo.provider_dimensions).length > 0
    ) {
      srcParts.push(
        '<span style="font-size:10px;padding:1px 6px;border-radius:999px;background:rgba(34,197,94,0.12);color:#22C55E">📡 Provider</span>',
      );
    }
    if (srcParts.length > 0) {
      html +=
        '<div style="margin-top:6px;display:flex;gap:4px;flex-wrap:wrap">' +
        srcParts.join("") +
        "</div>";
    }
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
    '<div class="sim-step-header"><span class="sim-step-title" style="color:#22C55E">最终入库判断</span><span class="sim-step-tag" style="background:#22C55E18;color:#22C55E">结果</span></div>';
  html += `<div class="sim-kv"><span class="sim-k">最终标题</span><span class="sim-v sim-v-highlight">${escapeHtml(currentTitle || "未识别标题")}</span></div>`;
  html += `<div class="sim-kv"><span class="sim-k">类型</span><span class="sim-v">${escapeHtml(currentType)}</span></div>`;
  const finalMatchLabel =
    matchLevel === "AUTO_PASS" ? "自动匹配" : "待人工确认";
  const finalMatchColor = matchLevel === "AUTO_PASS" ? "#22C55E" : "#F59E0B";
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
  const queueColor = matchLevel === "AUTO_PASS" ? "#22C55E" : "#F59E0B";
  html += `<div class="sim-queue-decision" style="border-color:${queueColor}30;background:${queueColor}08;color:${queueColor}">${escapeHtml(queueExplanation)}</div>`;
  html += "</div></div>";

  html += "</div>";
  html += "</div>";
  return html;
}

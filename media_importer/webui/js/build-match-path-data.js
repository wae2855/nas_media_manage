/**
 * 把任务对象装配成 renderMatchPathPreview 所需的数据格式
 * 所有视图（详情、追踪弹窗）都应使用此函数，禁止各自拼装
 */
function buildMatchPathData(task) {
  const scrapeResult = task.scrape_result || {};
  const matchTrace = task.match_trace || scrapeResult.match_trace || {};
  const scrapeTrace = task.scrape_trace || {};
  const scrapeDimensions =
    task.scrape_dimensions || scrapeResult.dimensions || {};

  // L6: trace_steps
  let traceSteps = [];
  if (Array.isArray(matchTrace.trace)) {
    traceSteps = matchTrace.trace;
  } else if (Array.isArray(matchTrace.trace_steps)) {
    traceSteps = matchTrace.trace_steps;
  }

  // L5: concerns
  let concerns = [];
  if (Array.isArray(matchTrace.concerns)) {
    concerns = matchTrace.concerns;
  } else if (Array.isArray(task.match_concerns)) {
    concerns = task.match_concerns;
  }

  // L4: selected_candidate
  const selected = scrapeResult.selected_candidate || null;

  return {
    filename: task.source_filename || "",
    clean_result: scrapeResult.clean_result || {},
    match_result: {
      match_level:
        scrapeResult.match_level || matchTrace.match_level || "NEEDS_CONFIRM",
      match_tier: scrapeResult.match_tier || matchTrace.match_tier || 0,
      tier_short_reason:
        scrapeResult.tier_short_reason || matchTrace.tier_short_reason || "",
      ai_reason: scrapeResult.ai_reason || matchTrace.ai_reason || "",
      selected_candidate: selected,
      concerns: concerns,
      trace: traceSteps,
      candidates: matchTrace.candidates || [],
    },
    scrape_result: {
      ...scrapeResult,
      dimensions: scrapeDimensions,
    },
    import_path: {
      import_path: task.import_path || task.import_dir || "",
      used_fallback: task.used_fallback || false,
      matched_rule: task.matched_rule || null,
    },
  };
}

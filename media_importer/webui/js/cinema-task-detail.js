// cinema-task-detail.js - task detail rendering
function findTaskRecord(taskId) {
  return currentTaskRecords.find((item) => item.task_id === taskId);
}

function extractDimValue(raw) {
  if (raw == null) return "";
  if (typeof raw === "string") return raw;
  if (typeof raw === "object") {
    if (raw.value != null) return String(raw.value);
    if (raw.sources && typeof raw.sources === "object") {
      const keys = Object.keys(raw.sources);
      for (const k of keys) {
        const sv = raw.sources[k];
        if (sv != null)
          return typeof sv === "object" ? String(sv.value || "") : String(sv);
      }
    }
  }
  return String(raw);
}

const MULTI_SELECT_DIMS = ["restricted_level", "broad_genre"];

function isMultiSelectDim(dimName) {
  return MULTI_SELECT_DIMS.indexOf(dimName) >= 0;
}

function buildTaskDimensionsForm(task, editable, enabled = editable) {
  const dimensions = currentEnabledDimensions.length
    ? currentEnabledDimensions
    : [];
  const source = task.scrape_dimensions || task.dimensions || {};
  if (!dimensions.length) {
    return '<div class="cinema-modal-hint">当前还没有启用的分类维度。</div>';
  }
  return dimensions
    .map((dim) => {
      const rawValue = source[dim.name];
      const value = extractDimValue(rawValue);
      const options = Array.isArray(dim.value_list) ? dim.value_list : [];
      const multi = isMultiSelectDim(dim.name);

      // 只读模式
      if (!editable) {
        const displayValue = multi
          ? formatMultiValue(value, options)
          : (() => {
              const m = options.find((item) => item.value === value);
              return m ? m.label || m.value : value;
            })();
        return `
                <label class="cinema-modal-field">
                    <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                    <span class="cinema-modal-readonly-value">${escapeHtml(displayValue || "—")}</span>
                </label>`;
      }

      const disabledAttr = enabled ? "" : " disabled";

      // 多选维度 → checkbox group
      if (multi && options.length > 0) {
        const selectedVals = value
          .split("|")
          .map((s) => s.trim())
          .filter(Boolean);
        const checkboxHtml = options
          .map((item) => {
            const checked =
              selectedVals.indexOf(item.value) >= 0 ? " checked" : "";
            return `<label class="rule-condition-checkbox-label">
                    <input type="checkbox" value="${escapeHtml(item.value)}"${checked}${disabledAttr} data-task-dim="${escapeHtml(dim.name)}">
                    <span>${escapeHtml(item.label || item.value)}</span>
                </label>`;
          })
          .join("");
        return `
                <div class="cinema-modal-field">
                    <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                    <div class="cinema-modal-checkbox-group">${checkboxHtml}</div>
                </div>`;
      }

      // 单选有值域 → select
      if (options.length > 0) {
        const matchedOption = options.find((item) => item.value === value);
        const emptyStateHtml = value
          ? `<option value="${escapeHtml(value)}" selected>${escapeHtml(matchedOption ? matchedOption.label || matchedOption.value : value)}</option>`
          : `<option value="" selected disabled>无</option>`;
        const optionHtml = options
          .map((item) => {
            const selected = item.value === value ? " selected" : "";
            return `<option value="${escapeHtml(item.value)}"${selected}>${escapeHtml(item.label || item.value)}</option>`;
          })
          .join("");
        return `
                <label class="cinema-modal-field">
                    <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                    <select data-task-dim="${escapeHtml(dim.name)}" class="cinema-modal-select"${disabledAttr}>
                        ${emptyStateHtml}
                        ${optionHtml}
                    </select>
                </label>`;
      }

      // 无值域 → 自由文本
      return `
            <label class="cinema-modal-field">
                <span>${escapeHtml(dim.label || dim.name)}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                <input type="text" data-task-dim="${escapeHtml(dim.name)}" value="${escapeHtml(value)}" placeholder="${value ? "" : "无"}"${disabledAttr} />
            </label>`;
    })
    .join("");
}

function formatMultiValue(value, options) {
  const parts = String(value || "")
    .split("|")
    .map((s) => s.trim())
    .filter(Boolean);
  if (!parts.length) return "";
  return parts
    .map((v) => {
      const m = options.find((o) => o.value === v);
      return m ? m.label || m.value : v;
    })
    .join("、");
}

function getTaskEditPermission(task) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  const isAwaitReview = status === "PENDING" && stage === "AWAIT_REVIEW";
  const isQueued = status === "PENDING" && stage === "QUEUED";
  const isFailed = status === "FAILED";
  const isCancelled = status === "CANCELLED";

  return {
    canEditFilename: isAwaitReview,
    canEditDimensions: isAwaitReview,
    canSave: isAwaitReview,
    stateLabel: isAwaitReview
      ? "待确认 — 可修改文件名和维度后确认入库"
      : isQueued
        ? "排队中 — 只读，不可编辑"
        : isFailed
          ? "失败 — 只读，可重试"
          : isCancelled
            ? "已取消 — 只读，可重新投入"
            : status === "SUCCESS"
              ? "已完成 — 只读"
              : status === "SKIPPED"
                ? "已跳过 — 只读"
                : stage === "RUNNING"
                  ? "处理中 — 不可编辑"
                  : "只读",
  };
}

function buildScrapeTraceSection(task, isAwaitReview, taskId) {
  var scrapeTrace = task.scrape_trace;
  if (!scrapeTrace || typeof scrapeTrace !== "object") {
    // 即使没有 scrape_trace，也能用 buildMatchPathData 渲染
  }

  var searchBadge = "";
  if (scrapeTrace && scrapeTrace.search_enhanced === true) {
    searchBadge =
      '<span style="font-size:11px;padding:2px 8px;border-radius:999px;background:rgba(6,182,212,0.15);color:#06B6D4;font-weight:600;margin-left:8px">🔍 AI联网搜索增强</span>';
  } else if (scrapeTrace && scrapeTrace.search_enhanced === false) {
    searchBadge =
      '<span style="font-size:11px;padding:2px 8px;border-radius:999px;background:rgba(148,163,184,0.12);color:#94A3B8;font-weight:600;margin-left:8px">📴 纯本地分析</span>';
  }

  var searchBtnHtml = "";
  if (isAwaitReview) {
    searchBtnHtml =
      '<button id="btn-scrape-search" type="button" class="btn btn-sm btn-outline" style="margin-left:8px">AI联网搜索</button>';
  }

  var data = buildMatchPathData(task);
  var timelineHtml = "";
  try {
    timelineHtml = renderMatchPathPreview(data);
  } catch (e) {
    console.error("buildMatchPathData render error:", e);
    timelineHtml = '<div class="cinema-modal-hint">刮削流程数据不完整。</div>';
  }

  return `
        <div class="cinema-modal-block">
            <h4 style="cursor:pointer" onclick="toggleScrapeTrace(this)">▶ 决策路径${searchBadge}${searchBtnHtml}</h4>
            <div class="cinema-detail-trace-inline" style="display:none">${timelineHtml}</div>
        </div>`;
}

function toggleScrapeTrace(headingEl) {
  var container = headingEl.parentNode;
  if (!container) return;
  var inline = container.querySelector(".cinema-detail-trace-inline");
  if (!inline) return;
  var collapsed = inline.style.display === "none";
  inline.style.display = collapsed ? "" : "none";
  headingEl.textContent = headingEl.textContent.replace(
    collapsed ? "▶" : "▼",
    collapsed ? "▼" : "▶",
  );
}

function taskToMatchPathData(task) {
  return buildMatchPathData(task);
}

function showMatchPathModalFromData(dataJson, filename) {
  var data = {};
  try {
    data = JSON.parse(decodeURIComponent(dataJson || "%7B%7D"));
  } catch (e) {
    data = {};
  }
  if (typeof renderMatchPathPreview !== "function") {
    showToast("匹配路径渲染组件未加载");
    return;
  }
  var existing = document.querySelector(".conf-detail-overlay");
  if (existing) existing.remove();
  var overlay = document.createElement("div");
  overlay.className = "conf-detail-overlay";
  overlay.innerHTML = `
        <div class="conf-detail-modal" style="max-width:920px">
            <div class="conf-detail-header">
                <div style="display:flex;align-items:center;gap:12px;flex:1;min-width:0">
                    <h3 style="margin:0;font-size:16px;white-space:nowrap">匹配路径详情</h3>
                    <span style="font-family:monospace;font-size:13px;color:#06B6D4;background:rgba(6,182,212,0.1);padding:4px 10px;border-radius:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(filename || data.filename || "-")}</span>
                </div>
                <button style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:20px;padding:4px 8px" onclick="this.closest('.conf-detail-overlay').remove()">&times;</button>
            </div>
            <div class="conf-detail-body" style="padding:16px;max-height:80vh;overflow:auto">
                ${renderMatchPathPreview(data)}
            </div>
        </div>`;
  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) overlay.remove();
  });
  document.body.appendChild(overlay);
}

function buildSubtitleTable(subtitles) {
  if (!Array.isArray(subtitles) || subtitles.length === 0) {
    return '<div class="cinema-modal-hint">这个任务当前没有字幕记录。</div>';
  }
  const rows = subtitles
    .map(
      (item) => `
        <tr>
            <td>${escapeHtml(item.source_filename || "-")}</td>
            <td>${escapeHtml(item.lang || "-")}</td>
            <td>${escapeHtml(getTaskStatusText(item.status || "PENDING"))}</td>
            <td>${escapeHtml(item.import_path || "-")}</td>
        </tr>`,
    )
    .join("");
  return `
        <table class="cinema-inline-table">
            <thead><tr><th>文件名</th><th>语言</th><th>状态</th><th>入库路径</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
}

function classifyErrorMessage(message) {
  const text = String(message || "").trim();
  if (!text) return { tone: "default", hint: "" };
  const lower = text.toLowerCase();
  if (
    /(timeout|timed out|连接超时|网络|network|unreachable|reset)/i.test(lower)
  ) {
    return {
      tone: "warn",
      hint: "网络或服务暂时不可用，稍后重试或检查 Provider 配置。",
    };
  }
  if (/(rate.?limit|too many|429|quota|限流|额度)/i.test(lower)) {
    return { tone: "warn", hint: "Provider 或 LLM 调用触发限流，请稍后重试。" };
  }
  if (
    /(file not found|no such file|enoent|missing|文件不存在|找不到|无法读取|permission)/i.test(
      lower,
    )
  ) {
    return {
      tone: "danger",
      hint: "源文件可能已被移动或删除，请检查源目录或重新入库。",
    };
  }
  if (
    /(no match|not found|无匹配|无结果|unknown media|unrecognized)/i.test(lower)
  ) {
    return {
      tone: "warn",
      hint: "未找到匹配的影视信息，可尝试手动指定标题或重命名后再重试。",
    };
  }
  if (/(auth|401|403|unauthorized|forbidden|api.?key|invalid)/i.test(lower)) {
    return {
      tone: "danger",
      hint: "Provider 或 LLM 鉴权失败，请检查 API Key 配置。",
    };
  }
  return { tone: "danger", hint: "" };
}

function buildScrapeResultSection(task) {
  const scrape = task.scrape_result || {};
  const matchLevel = scrape.match_level || task.match_level || "";
  const hasAny =
    scrape.title_cn ||
    scrape.title_en ||
    scrape.year ||
    scrape.type ||
    scrape.overview ||
    scrape.poster_url ||
    matchLevel;
  if (!hasAny) {
    return `
            <div class="cinema-modal-block">
                <h4>刮削结果</h4>
                <div class="cinema-modal-hint">本次未产生刮削结果，可能是首次扫描或 Provider 命中失败。</div>
            </div>`;
  }
  const titleCn = scrape.title_cn || task.scrape_title_cn || "";
  const titleEn = scrape.title_en || task.scrape_title_en || "";
  const year = scrape.year || task.scrape_year || "";
  const type = scrape.type || task.scrape_media_type || "";
  const overview = scrape.overview || "";
  const poster = scrape.poster_url || "";
  const typeLabel =
    type === "movie" ? "电影" : type === "tv" ? "剧集" : type || "—";
  let matchLabel = "";
  if (matchLevel === "AUTO_PASS")
    matchLabel =
      '<span class="badge" style="background:rgba(34,197,94,0.15);color:#22C55E">自动匹配</span>';
  else if (matchLevel === "CONTEXT_PASS")
    matchLabel =
      '<span class="badge" style="background:rgba(6,182,212,0.15);color:#06B6D4">🤖 AI辅助匹配</span>';
  else if (matchLevel === "NEEDS_CONFIRM")
    matchLabel =
      '<span class="badge" style="background:rgba(245,158,11,0.15);color:#F59E0B">需确认</span>';
  return `
        <div class="cinema-modal-block">
            <h4>刮削结果</h4>
            <div class="task-detail-scrape">
                ${poster ? `<div class="task-detail-poster"><img src="${escapeHtml(poster)}" alt="海报" loading="lazy" onerror="this.parentNode.style.display='none'"/></div>` : ""}
                <div class="task-detail-scrape-meta">
                    <div class="task-detail-scrape-line"><b>${escapeHtml(titleCn || titleEn || "—")}</b>${titleCn && titleEn ? `<span>${escapeHtml(titleEn)}</span>` : ""}</div>
                    <div class="task-detail-scrape-tags">
                        <span class="badge">${escapeHtml(typeLabel)}</span>
                        ${year ? `<span class="badge">${escapeHtml(String(year))}</span>` : ""}
                        ${matchLabel ? matchLabel : ""}
                    </div>
                    ${overview ? `<p class="task-detail-scrape-overview">${escapeHtml(overview)}</p>` : ""}
                </div>
            </div>
        </div>`;
}

function buildFailureSection(task) {
  const status = String(task.status || "").toUpperCase();
  const message = String(task.error_message || task.skip_reason || "").trim();
  if (status !== "FAILED" || !message) return "";
  const classified = classifyErrorMessage(message);
  return `
        <div class="cinema-modal-block task-detail-failure">
            <h4>失败原因</h4>
            <div class="task-detail-failure-box task-detail-failure-${classified.tone}">
                <div class="task-detail-failure-text">${escapeHtml(message)}</div>
                ${classified.hint ? `<div class="task-detail-failure-hint">${escapeHtml(classified.hint)}</div>` : ""}
            </div>
        </div>`;
}

function buildRenamePreview(originalFilename) {
  const original = String(originalFilename || "");
  return `
        <div class="task-detail-rename-preview" id="task-rename-preview">
            <small class="task-detail-rename-from">原文件名：<span>${escapeHtml(original)}</span></small>
            <small class="task-detail-rename-to">新文件名：<span data-rename-target>${escapeHtml(original)}</span></small>
        </div>`;
}

function updateRenamePreview(inputEl) {
  if (!inputEl) return;
  const target = document.querySelector(
    "#task-rename-preview [data-rename-target]",
  );
  if (!target) return;
  const value = String(inputEl.value || "").trim();
  target.textContent = value || "（空）";
  const original = String(inputEl.dataset.renameOriginal || "").trim();
  const preview = document.getElementById("task-rename-preview");
  if (preview) {
    const changed = value && value !== original;
    preview.classList.toggle("is-changed", changed);
  }
  if (inputEl.classList) {
    inputEl.classList.toggle("is-empty", !value);
  }
}

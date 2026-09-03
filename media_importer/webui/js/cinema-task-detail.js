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

// 维度来源标签（详情页展示，列表页不展示）
const DIM_SOURCE_BADGES = {
  tmdb: { icon: "🗄", label: "TMDB" },
  douban: { icon: "📚", label: "豆瓣" },
  ai_assist: { icon: "🕘", label: "历史 AI 辅助" },
  ai_search: { icon: "🕘", label: "历史 AI 搜索" },
  default: { icon: "⚙", label: "默认值" },
  file: { icon: "📄", label: "文件分析" },
  manual: { icon: "✍", label: "人工填写" },
};

function dimSourceBadge(task, dimName) {
  const sources = task.dim_sources || {};
  const raw = String(sources[dimName] || "");
  if (!raw) return "";
  const key = raw.replace(/^provider:/, "");
  const meta = DIM_SOURCE_BADGES[key];
  if (!meta) return "";
  return (
    '<span style="font-size:10px;padding:1px 6px;border-radius:3px;background:rgba(234,191,99,0.1);color:var(--gold,#eabf63);margin-left:6px;white-space:nowrap" title="该维度值的来源">' +
    meta.icon +
    " " +
    meta.label +
    "</span>"
  );
}

function dimMappingEvidenceHint(task, dimName) {
  const evidence = task.scrape_trace?.dimension_mapping_evidence?.[dimName];
  if (!evidence || !evidence.target) return "";
  const matched = evidence.matched_input;
  let raw = "";
  if (matched && typeof matched === "object") {
    raw = [matched.country, matched.certification].filter(Boolean).join(" / ");
  } else if (matched != null && matched !== "") {
    raw = String(matched);
  }
  const source = String(task.provider_type || "TMDB").toUpperCase();
  return `<small class="dimension-evidence-hint">依据：${escapeHtml(source)}${raw ? ` 返回 ${escapeHtml(raw)}` : ""}，按当前映射得出</small>`;
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
                    <span>${escapeHtml(dim.label || dim.name)}${dimSourceBadge(task, dim.name)}</span>
                    <span class="cinema-modal-readonly-value">${escapeHtml(displayValue || "—")}</span>
                    ${dimMappingEvidenceHint(task, dim.name)}
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
                    <span>${escapeHtml(dim.label || dim.name)}${dimSourceBadge(task, dim.name)}</span>
                    <div class="cinema-modal-checkbox-group">${checkboxHtml}</div>
                    ${dimMappingEvidenceHint(task, dim.name)}
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
                    <span>${escapeHtml(dim.label || dim.name)}${dimSourceBadge(task, dim.name)}</span>
                    <select data-task-dim="${escapeHtml(dim.name)}" class="cinema-modal-select"${disabledAttr}>
                        ${emptyStateHtml}
                        ${optionHtml}
                    </select>
                    ${dimMappingEvidenceHint(task, dim.name)}
                </label>`;
      }

      // 无值域 → 自由文本
      return `
            <label class="cinema-modal-field">
                <span>${escapeHtml(dim.label || dim.name)}${dimSourceBadge(task, dim.name)}</span>
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
  const isRunning = status === "PENDING" && stage === "RUNNING";
  const isFailed = status === "FAILED";
  const isCancelled = status === "CANCELLED";
  const isSuccess = status === "SUCCESS";
  const isSkipped = status === "SKIPPED";
  const isReorganization = task.task_kind === "REORGANIZE";

  var labelText, labelColor;
  if (isAwaitReview) {
    labelText = "待确认";
    labelColor = "#F59E0B";
  } else if (isQueued) {
    labelText = "排队中";
    labelColor = "#94A3B8";
  } else if (isRunning) {
    labelText = "处理中";
    labelColor = "#06B6D4";
  } else if (isSuccess) {
    labelText = "已完成";
    labelColor = "#22C55E";
  } else if (isFailed) {
    labelText = "失败";
    labelColor = "#D94F45";
  } else if (isCancelled) {
    labelText = "已取消";
    labelColor = "#6C757D";
  } else if (isSkipped) {
    labelText = "已跳过";
    labelColor = "#8B5CF6";
  } else {
    labelText = "未知";
    labelColor = "#6C757D";
  }

  return {
    canEditFilename: isAwaitReview,
    canEditDimensions: isAwaitReview,
    canSave: isAwaitReview,
    statusLabel: labelText,
    statusColor: labelColor,
    stateLabel: isAwaitReview
      ? isReorganization
        ? task.used_fallback
          ? "重新整理 — 先调整维度或手动刮削，匹配正式规则后才能继续"
          : "重新整理 — 已匹配正式规则，可核对后开始移动"
        : task.used_fallback
          ? "待确认 — 明确接受待整理区后才会继续入库"
          : "待确认 — 可修改文件名和维度后确认入库"
      : isQueued
        ? "排队中 — 只读，不可编辑"
        : isFailed
          ? "失败 — 只读，可重试"
          : isCancelled
            ? "已取消 — 只读，可重新投入"
            : isSuccess
              ? "已完成 — 只读"
              : isSkipped
                ? "已跳过 — 只读"
                : isRunning
                  ? "处理中 — 不可编辑"
                  : "只读",
  };
}

// 详情页：待确认原因区块（逐条列出业务化原因与说明）
function buildReviewReasonSection(task) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  if (!(status === "PENDING" && stage === "AWAIT_REVIEW")) return "";
  const scrape = task.scrape_result || {};
  const concerns = task.match_concerns || scrape.match_concerns || [];
  const isReorganization = task.task_kind === "REORGANIZE";
  const items = Array.isArray(concerns)
    ? concerns.filter(
        (c) =>
          c &&
          (c.message || c.code) &&
          !(
            isReorganization &&
            !task.used_fallback &&
            c.code === "FALLBACK_REORGANIZATION"
          ),
      )
    : [];
  const rows = items
    .map((c) => {
      const title =
        c.code === "MISSING_FIELDS" && c.message
          ? c.message
          : concernLabel(c.code);
      const detail = c.detail || "";
      return `
        <div class="review-reason-row">
            <span class="review-reason-title">⚠ ${escapeHtml(title)}</span>
            ${detail ? `<span class="review-reason-detail">${escapeHtml(detail)}</span>` : ""}
        </div>`;
    })
    .join("");
  const tip = isReorganization && task.used_fallback
    ? "当前仍落入待整理区。请修改维度或手动刮削，直到入库预览匹配正式规则。"
    : isReorganization
      ? "已匹配正式入库规则。请核对目标路径，确认后会整组移动影片和随片字幕。"
    : task.used_fallback
      ? "如果当前资料无法匹配正式规则，可以明确确认后先放入待整理区；原任务完成后仍可单独重新整理。"
      : "可在下方修改维度、手动刮削选片，确认无误后点击「确认入库」。";
  return `
        <div class="cinema-modal-block review-reason-block">
            <h4>待确认原因</h4>
            ${rows || `<div class="cinema-modal-hint">${escapeHtml(isReorganization ? "没有其他待确认问题。" : "需要人工核对刮削结果后确认入库。")}</div>`}
            <div class="review-reason-tip">${escapeHtml(tip)}</div>
        </div>`;
}

function buildScrapeTraceSection(task) {
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
            <div class="config-collapse-card" data-collapse-card>
                <div class="config-collapse-header" data-collapse-toggle style="cursor:pointer;display:flex;align-items:center;gap:6px;justify-content:flex-start">
                    <span class="config-collapse-chevron" style="display:inline-block;transition:transform 180ms;font-size:12px">▶</span>
                    <h4 style="margin:0">决策路径</h4>
                </div>
                <div class="config-collapse-body">
                    <div class="cinema-detail-trace-inline">${timelineHtml}</div>
                </div>
            </div>
        </div>`;
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

function subtitleLangLabel(lang) {
  const map = { zh: "中文", chs: "简中", cht: "繁中", en: "英文", ja: "日文", ko: "韩文", und: "未识别", unknown: "未识别" };
  const key = String(lang || "").toLowerCase();
  return map[key] || (lang && lang !== "-" ? lang : "未识别");
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
            <td>${escapeHtml(subtitleLangLabel(item.lang))}</td>
            <td>${escapeHtml(item.planned_filename || (item.import_path ? String(item.import_path).split(/[\\/]/).pop() : "等待生成"))}</td>
            <td>${escapeHtml(getTaskStatusText(item.status || "PENDING"))}</td>
            <td>${escapeHtml(item.import_path || "-")}</td>
        </tr>`,
    )
    .join("");
  return `
        <table class="cinema-inline-table">
            <thead><tr><th>源字幕</th><th>语言</th><th>计划文件名</th><th>状态</th><th>最终路径</th></tr></thead>
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

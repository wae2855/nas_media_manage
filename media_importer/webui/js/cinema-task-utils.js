// cinema-task-utils.js - task utility functions
function getTaskStatusText(status, stage) {
  const s = String(status || "").toUpperCase();
  const st = String(stage || "").toUpperCase();
  if (s === "PENDING") {
    if (st === "QUEUED") return "排队中";
    if (st === "RUNNING") return "处理中";
    if (st === "AWAIT_REVIEW") return "待确认";
    return "待处理";
  }
  const map = {
    FAILED: "失败",
    SUCCESS: "已完成",
    SKIPPED: "已跳过",
    CANCELLED: "已取消",
  };
  return map[s] || "未知状态";
}

function getTaskTone(task) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  if (status === "FAILED") return "red";
  if (status === "PENDING" && stage === "AWAIT_REVIEW") return "cyan";
  if (status === "SUCCESS" || status === "SKIPPED") return "gold";
  return "gold";
}

function taskFileName(task) {
  return (
    task.source_filename ||
    task.final_filename ||
    (task.source_path
      ? String(task.source_path).split("/").pop().split("\\").pop()
      : "") ||
    "未命名任务"
  );
}

function taskDisplayTitle(task) {
  const scrape = task.scrape_result || {};
  return (
    task.scrape_title_cn ||
    scrape.title_cn ||
    task.scrape_title_en ||
    scrape.title_en ||
    taskFileName(task)
  );
}

function taskDescription(task) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  const scrape = task.scrape_result || {};
  if (task.cancel_requested) {
    return "已收到停止请求，系统正在到达安全检查点；目标片库不会因此被删除或覆盖。";
  }
  if (status === "SUCCESS" && task.organization_status === "FALLBACK_PENDING") {
    return "影片已经安全入库到待整理区；可保留现状，也可以创建一条独立任务重新匹配正式入库规则。";
  }
  if (status === "SUCCESS" && task.task_kind === "REORGANIZE") {
    return "影片和随片字幕已经按正式规则重新整理完成。";
  }
  if (status === "SUCCESS") {
    const title =
      scrape.title_cn ||
      scrape.title_en ||
      task.scrape_title_cn ||
      task.scrape_title_en;
    return title ? `已完成识别并入库：${title}` : "任务已完成并写入目标片库。";
  }
  if (task.error_message) return task.error_message;
  if (task.skip_reason) return task.skip_reason;
  if (status === "PENDING" && stage === "AWAIT_REVIEW") {
    const prefix = scrape.tier_short_reason || "";
    const concerns = task.match_concerns || scrape.match_concerns || [];
    const concernMessages = Array.isArray(concerns)
      ? concerns
          .filter(
            (c) =>
              !(
                task.task_kind === "REORGANIZE" &&
                !task.used_fallback &&
                c &&
                c.code === "FALLBACK_REORGANIZATION"
              ),
          )
          .map((c) => c.message || (typeof c === "string" ? c : ""))
          .filter(Boolean)
      : [];
    if (concernMessages.length > 0) {
      return [prefix, concernMessages.join("；") + "。等待你确认最终入库方向。"]
        .filter(Boolean)
        .join(" · ");
    }
    if (task.task_kind === "REORGANIZE" && !task.used_fallback) {
      return "已经匹配正式入库规则，请核对入库预览后确认重新整理。";
    }
    return prefix || "需要你确认最终匹配结果。";
  }
  if (status === "FAILED") {
    return "本次处理未完成，可以先查看原因，再决定是否重试。";
  }
  if (status === "SKIPPED") {
    return "该任务已被跳过，可按需要重新投入处理。";
  }
  if (status === "CANCELLED") {
    return task.error_message || "该任务已取消，可按需要重新投入处理。";
  }
  if (status === "PENDING" && stage === "RUNNING") {
    return "系统正在扫描、识别和整理这个文件。";
  }
  return "文件已经进入队列，等待系统开始扫描与识别。";
}

// 任务元信息标签：返回 [{tone,text}] 供卡片渲染成徽标（不再裸拼字符串）
function taskMetaTags(task) {
  const tags = [];
  const status = String(task.status || "").toUpperCase();
  const scrape = task.scrape_result || {};
  const matchLevel =
    task.match_level || task.scrape_match_level || scrape.match_level;
  const mediaType = task.scrape_media_type || scrape.type;
  const season = task.scrape_season ?? scrape.season;
  const episode = task.scrape_episode ?? scrape.episode;
  if (mediaType === "movie") tags.push({ tone: "type", text: "电影" });
  if (mediaType === "tv") {
    tags.push({ tone: "type", text: "剧集" });
    if (season !== null && season !== undefined && season !== "")
      tags.push({ tone: "se", text: "S" + String(season).padStart(2, "0") });
    if (episode !== null && episode !== undefined && episode !== "")
      tags.push({ tone: "se", text: "E" + String(episode).padStart(2, "0") });
  }
  if (task.task_kind === "REORGANIZE")
    tags.push({ tone: "type", text: "重新整理" });
  if (status === "SUCCESS" && task.organization_status === "FALLBACK_PENDING")
    tags.push({ tone: "warn", text: "待整理" });
  if (
    matchLevel === "NEEDS_CONFIRM" &&
    status === "PENDING" &&
    String(task.stage || "").toUpperCase() === "AWAIT_REVIEW"
  )
    tags.push({ tone: "warn", text: "需确认" });
  if (status === "FAILED" && task.error_message)
    tags.push({ tone: "danger", text: "有失败原因" });
  const time =
    ["SUCCESS", "SKIPPED", "CANCELLED"].includes(status) && task.completed_at
      ? task.completed_at
      : task.started_at || task.created_at;
  if (time)
    tags.push({ tone: "time", text: "处理于 " + formatActivityTime(time) });
  return tags;
}

// 兼容旧调用：拼接纯文本（详情页 tooltip 等场景仍可用）
function taskMeta(task) {
  const text = taskMetaTags(task)
    .map((t) => t.text)
    .join(" · ");
  return text || "等待处理";
}

function targetLibraryConflictOf(task) {
  const conflict = task && task.dedup_result;
  if (
    conflict &&
    conflict.is_duplicate &&
    conflict.status === "awaiting_user"
  ) {
    return conflict;
  }
  return null;
}

function taskPrimaryAction(task) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  if (targetLibraryConflictOf(task))
    return { key: "view-task", label: "处理片库冲突" };
  if (status === "SUCCESS" && task.organization_status === "FALLBACK_PENDING")
    return { key: "reorganize", label: "重新整理" };
  if (
    status === "PENDING" &&
    stage === "AWAIT_REVIEW" &&
    task.task_kind === "REORGANIZE" &&
    task.used_fallback
  ) {
    return { key: "view-task", label: "设置整理规则" };
  }
  if (status === "PENDING" && stage === "AWAIT_REVIEW")
    return { key: "confirm", label: "入库" };
  if (status === "FAILED" || status === "SKIPPED")
    return { key: "retry-task", label: "重新刮削" };
  if (status === "CANCELLED") return { key: "retry-task", label: "重新投入" };
  if (status === "PENDING" && stage === "QUEUED")
    return { key: "end-task", label: "结束处理" };
  if (status === "PENDING" && stage === "RUNNING" && !task.cancel_requested)
    return { key: "end-task", label: "停止任务" };
  return null;
}

function taskSecondaryAction(task) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  if (status === "PENDING" && stage === "AWAIT_REVIEW") {
    const scrape = task.scrape_result || {};
    const hasTitle =
      task.scrape_title_cn ||
      scrape.title_cn ||
      task.scrape_title_en ||
      scrape.title_en;
    if (!hasTitle) {
      return { key: "end-task", label: "不再处理" };
    }
    return { key: "end-task", label: "不再处理" };
  }
  if (status === "FAILED") return { key: "end-task", label: "不再处理" };
  if (["SKIPPED", "CANCELLED"].includes(status))
    return { key: "dispose-source", label: "处理来源" };
  if (status === "SUCCESS") return { key: "delete-record", label: "删除记录" };
  return null;
}

function formatFileSizeMb(valueMb) {
  const size = Number(valueMb || 0);
  if (size <= 0) return "0 MB";
  if (size >= 1024) return `${(size / 1024).toFixed(1)} GB`;
  return `${size.toFixed(size >= 100 ? 0 : 1)} MB`;
}

const TASK_PROGRESS_LABELS = {
  scrape: ["获取影片资料", "正在查询并整理影片信息"],
  validate: ["检查识别结果", "正在判断是否需要人工确认"],
  classify: ["选择入库规则", "正在判断影片应进入哪个片库"],
  dedup: ["检查片库重名", "只检查冲突，不会自动覆盖片库文件"],
  rename: ["生成入库文件名", "正在按命名规则生成最终文件名"],
  import: ["写入目标片库", "识别、规则和重名检查均已完成，开始安全写入"],
  import_resume_check: ["准备安全写入", "正在确认目标临时文件状态"],
  import_transfer: ["写入目标片库", "正在把来源文件写入目标片库的任务暂存"],
  import_verify_source: ["校验待入库文件", "正在确认本次影片内容完整"],
  import_verify_target: ["校验片库新文件", "正在确认新文件写入完整"],
  import_publish: ["发布片库新文件", "校验通过后安全发布，不覆盖同名文件"],
  reorganize: ["重新整理影片", "正在把待整理区的影片和字幕移动到正式规则目录"],
  source_cleanup: ["处理来源文件", "影片已入库，正在按配置处理来源"],
  source_cleanup_resume_check: ["检查来源处理断点", "正在核对已进入回收区的内容"],
  source_cleanup_transfer: ["回收来源文件", "正在把来源整组移入本地回收区"],
  source_cleanup_verify_source: ["校验来源内容", "正在确认待回收内容完整"],
  source_cleanup_verify_target: ["校验回收区文件", "正在确认回收副本完整"],
  source_cleanup_publish: ["完成来源处理", "正在安全发布回收记录"],
  notify: ["发送完成通知", "核心文件处理已经完成"],
  record: ["记录处理结果", "正在保存本次处理结果"],
};

function formatTaskBytes(value) {
  const bytes = Math.max(0, Number(value || 0));
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${Math.round(bytes)} B`;
}

function taskFlowIndex(stepName) {
  const step = String(stepName || "");
  if (step === "scrape" || step === "validate") return 1;
  if (["classify", "dedup", "rename"].includes(step)) return 2;
  if (step.startsWith("import") || step.startsWith("reorganize")) return 3;
  if (step.startsWith("source_cleanup") || step === "notify" || step === "record") return 4;
  return 1;
}

function taskProgressView(task) {
  const stepName = String(task.step_name || "");
  const meta = [...(TASK_PROGRESS_LABELS[stepName] || ["正在处理", "系统正在推进当前任务"])];
  const completed = Math.max(0, Number(task.bytes_copied || 0));
  const total = Math.max(0, Number(task.total_bytes || 0));
  const bytePhase = /_(resume_check|transfer|verify_source|verify_target)$/.test(stepName);
  const hasBytes = bytePhase && total > 0;
  const phasePercent = hasBytes
    ? Math.max(0, Math.min(100, Math.round((completed / total) * 100)))
    : null;
  const itemName = String(task.progress_item_name || "");
  const itemKind = String(task.progress_item_kind || "") === "subtitle" ? "字幕" : "影片";
  const itemIndex = Math.max(0, Number(task.progress_item_index || 0));
  const itemTotal = Math.max(0, Number(task.progress_item_total || 0));
  const memberHint = itemName
    ? `正在处理${itemKind}${itemTotal ? ` ${itemIndex}/${itemTotal}` : ""}：${itemName}`
    : "";
  return {
    stepName,
    label: meta[0],
    hint: memberHint || meta[1],
    flowIndex: taskFlowIndex(stepName),
    completed,
    total,
    hasBytes,
    phasePercent,
  };
}

function renderTaskLiveProgress(task, compact = false) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  if (status !== "PENDING" || stage !== "RUNNING") return "";
  const progress = taskProgressView(task);
  const bytesText = progress.hasBytes
    ? `${formatTaskBytes(progress.completed)} / ${formatTaskBytes(progress.total)} · ${progress.phasePercent}%`
    : `流程第 ${progress.flowIndex} / 4 段`;
  return `<section class="task-live-progress${compact ? " task-live-progress--compact" : ""}" aria-label="当前处理进度">
    <div class="task-live-progress-head"><b>${escapeHtml(progress.label)}</b><span>${escapeHtml(bytesText)}</span></div>
    ${progress.hasBytes ? `<div class="task-live-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress.phasePercent}"><i style="width:${progress.phasePercent}%"></i></div>` : ""}
    <small>${escapeHtml(progress.hint)}</small>
  </section>`;
}

function buildTaskProgressSection(task) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  if (status !== "PENDING" || stage !== "RUNNING") return "";
  const progress = taskProgressView(task);
  const stages = ["获取资料", "匹配规则", "写入片库", "处理来源"];
  return `<section class="cinema-modal-block task-progress-detail">
    <div class="task-progress-detail-title"><h4>当前执行到：${escapeHtml(progress.label)}</h4><span>第 ${progress.flowIndex} / 4 段</span></div>
    ${renderTaskLiveProgress(task, true)}
    <ol class="task-progress-flow">${stages.map((label, index) => {
      const position = index + 1;
      const state = position < progress.flowIndex ? "done" : position === progress.flowIndex ? "active" : "pending";
      return `<li class="is-${state}"><i>${position < progress.flowIndex ? "✓" : position}</i><span>${escapeHtml(label)}</span></li>`;
    }).join("")}</ol>
  </section>`;
}

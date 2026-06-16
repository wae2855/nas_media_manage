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
  if (task.error_message) return task.error_message;
  if (task.skip_reason) return task.skip_reason;
  if (status === "PENDING" && stage === "AWAIT_REVIEW") {
    if (task.confirm_reason || scrape.confirm_reason) {
      return (
        (task.confirm_reason || scrape.confirm_reason) +
        "。等待你确认最终入库方向。"
      );
    }
    const concerns = task.match_concerns || scrape.match_concerns || [];
    if (Array.isArray(concerns) && concerns.length > 0) {
      const concernMessages = concerns
        .map((c) => c.message || (typeof c === "string" ? c : ""))
        .filter(Boolean);
      if (concernMessages.length > 0) {
        return concernMessages.join("；") + "。等待你确认最终入库方向。";
      }
    }
    return "需要你确认最终匹配结果。";
  }
  if (status === "FAILED") {
    return "本次处理未完成，可以先查看原因，再决定是否重试。";
  }
  if (status === "SUCCESS") {
    const title =
      scrape.title_cn ||
      scrape.title_en ||
      task.scrape_title_cn ||
      task.scrape_title_en;
    return title ? `已完成识别并入库：${title}` : "任务已完成并写入目标片库。";
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

function taskMeta(task) {
  const bits = [];
  const status = String(task.status || "").toUpperCase();
  const scrape = task.scrape_result || {};
  const matchLevel =
    task.match_level || task.scrape_match_level || scrape.match_level;
  const mediaType = task.scrape_media_type || scrape.type;
  const year = task.scrape_year || scrape.year;
  if (mediaType === "movie") bits.push("电影");
  if (mediaType === "tv") bits.push("剧集");
  if (year) bits.push(String(year));
  if (matchLevel === "AUTO_PASS") bits.push("自动匹配");
  else if (matchLevel === "CONTEXT_PASS") bits.push("🤖 AI辅助匹配");
  else if (matchLevel === "NEEDS_CONFIRM") bits.push("需确认");
  if (status === "FAILED" && task.error_message) bits.push("查看失败原因");
  if (["SUCCESS", "SKIPPED", "CANCELLED"].includes(status) && task.completed_at)
    bits.push(formatActivityTime(task.completed_at));
  if (bits.length === 0 && task.created_at)
    bits.push(formatActivityTime(task.created_at));
  return bits.join(" · ") || "等待处理";
}

function taskPrimaryAction(task) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  if (status === "PENDING" && stage === "AWAIT_REVIEW")
    return { key: "confirm", label: "入库" };
  if (status === "FAILED" || status === "SKIPPED")
    return { key: "retry-task", label: "重新刮削" };
  if (status === "CANCELLED") return { key: "retry-task", label: "重新投入" };
  if (status === "PENDING" && stage === "QUEUED")
    return { key: "cancel-task", label: "取消" };
  return null;
}

function taskSecondaryAction(task) {
  const status = String(task.status || "").toUpperCase();
  const stage = String(task.stage || "").toUpperCase();
  if (status === "PENDING" && stage === "AWAIT_REVIEW")
    return { key: "retry-task", label: "重试" };
  if (status === "FAILED") return { key: "delete-task", label: "移入回收" };
  return null;
}

function formatFileSizeMb(valueMb) {
  const size = Number(valueMb || 0);
  if (size <= 0) return "0 MB";
  if (size >= 1024) return `${(size / 1024).toFixed(1)} GB`;
  return `${size.toFixed(size >= 100 ? 0 : 1)} MB`;
}

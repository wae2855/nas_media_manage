// config-recycle.js - recycle list, cleaner preview
function _toggleTmdbDetailView() {
  var structured = document.getElementById("tmdb-detail-structured");
  var raw = document.getElementById("tmdb-detail-raw");
  var btn = document.getElementById("tmdb-detail-toggle-btn");
  if (!structured || !raw || !btn) return;

  if (raw.style.display === "none") {
    raw.style.display = "block";
    structured.style.display = "none";
    btn.textContent = "查看结构化";
  } else {
    raw.style.display = "none";
    structured.style.display = "block";
    btn.textContent = "查看原始 JSON";
  }
}

function _escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function bindPathPermissionAutoTest() {
  var bindings = [
    { id: "cfg-source_dir", needWrite: false },
    { id: "cfg-temp_dir", needWrite: true },
    { id: "cfg-log_dir", needWrite: true },
    { id: "cfg-source_policy-recycle_dir", needWrite: true },
  ];
  bindings.forEach(function (b) {
    var el = document.getElementById(b.id);
    if (!el) return;
    el.addEventListener("blur", function () {
      var v = (el.value || "").trim();
      if (v) testPathPermission(b.id, b.needWrite);
    });
  });
}

function toggleInfoPanel(panelId) {
  var panel = document.getElementById(panelId);
  var arrow = document.getElementById(panelId + "-arrow");
  if (!panel) return;
  var isHidden = panel.classList.contains("collapsed-section");
  if (isHidden) {
    panel.classList.remove("collapsed-section");
  } else {
    panel.classList.add("collapsed-section");
  }
  if (arrow) {
    arrow.textContent = isHidden ? "▼" : "▶";
  }
}

var _CONFIDENCE_DEFAULTS = {
  provider_match_threshold: 0.7,
  title_exact_with_year: 1.0,
  title_exact_with_season: 0.9,
  title_exact_no_year: 0.7,
  title_exact_year_mismatch: 0.4,
  title_fuzzy_year_coeff: 0.7,
  title_min_similarity: 0.3,
  R_formula: "log",
  R_max_results_cap: 10,
  R_min_value: 0.1,
  R_T_floor: 0.5,
  R_T_curve: 1.5,
  source_priority: ["provider", "ai", "file"],
  ai_cap_high_similarity: 0.7,
  ai_cap_low_similarity: 0.3,
  ai_cap_no_title: 0.3,
  ai_cap_no_match: 0.2,
  ai_cap_low_coeff: 0.5,
  pass_threshold: 0.8,
  confirm_threshold: 0.5,
  review_threshold: 0.3,
  dimensions: {},
};

function _initSourcePriorityDrag(container) {
  var dragSrc = null;
  var items = container.querySelectorAll(".source-priority-item");
  items.forEach(function (item) {
    item.addEventListener("dragstart", function (e) {
      dragSrc = item;
      item.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", "");
    });
    item.addEventListener("dragend", function () {
      item.classList.remove("dragging");
      dragSrc = null;
    });
    item.addEventListener("dragover", function (e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      if (dragSrc && dragSrc !== item) {
        var rect = item.getBoundingClientRect();
        var midY = rect.top + rect.height / 2;
        if (e.clientY < midY) {
          container.insertBefore(dragSrc, item);
        } else {
          container.insertBefore(dragSrc, item.nextSibling);
        }
      }
    });
  });
}

var _recycleListData = [];
var _pendingRestoreItems = [];

function _getZoneAttr(zoneName) {
  if (!zoneName) return "other";
  if (zoneName.indexOf("清理器") >= 0) return "cleaner";
  if (zoneName.indexOf("源目录") >= 0) return "source";
  if (zoneName.indexOf("入库") >= 0) return "import";
  return "other";
}


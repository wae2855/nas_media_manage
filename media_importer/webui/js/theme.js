var THEME_LIST = [
  { key: "", label: "默认", desc: "靛蓝渐变", color: "#6366F1" },
  { key: "A", label: "深海蓝黑", desc: "沉稳·专业", color: "#2563eb" },
  { key: "B", label: "暗夜青石", desc: "冷静·守护", color: "#0d9488" },
  { key: "C", label: "碳灰暖橙", desc: "影院·胶片", color: "#f97316" },
  { key: "D", label: "极光紫灰", desc: "神秘·高级", color: "#a78bfa" },
  { key: "E", label: "赛博霓虹", desc: "赛博·未来", color: "#22c55e" },
];

function initTheme() {
  var saved = localStorage.getItem("nas_theme") || "";
  applyTheme(saved);
  renderThemeSelector();
}

function applyTheme(key) {
  document.documentElement.setAttribute("data-theme", key || "");
}

function switchTheme(key) {
  localStorage.setItem("nas_theme", key);
  applyTheme(key);
  renderThemeSelector();
  showToast("已切换到「" + (getThemeLabel(key) || "默认") + "」主题");
}

function getThemeLabel(key) {
  var item = THEME_LIST.find(function (t) {
    return t.key === key;
  });
  return item ? item.label : "";
}

function renderThemeSelector() {
  var container = document.getElementById("theme-selector-container");
  if (!container) return;

  var currentKey = localStorage.getItem("nas_theme") || "";

  var html = '<div class="theme-selector">';
  html +=
    '<button class="header-icon-btn theme-trigger" onclick="toggleThemeDropdown(event)" title="切换主题">';
  html +=
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">';
  html +=
    '<circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 0 20"/><line x1="12" y1="2" x2="12" y2="22"/><path d="M2 12h2"/><path d="M18 12h4"/><path d="M7.05 4.93l1.41 1.41"/><path d="M15.55 17.66l1.42 1.42"/><path d="M7.05 19.07l1.41-1.41"/><path d="M15.55 6.34l1.42-1.42"/>';
  html += "</svg>";
  html += "</button>";
  html +=
    '<div class="theme-dropdown" id="theme-dropdown" style="display:none;">';
  THEME_LIST.forEach(function (t) {
    var isActive = t.key === currentKey;
    html +=
      '<button class="theme-option' +
      (isActive ? " active" : "") +
      '" onclick="switchTheme(\'' +
      t.key +
      "')\">";
    html +=
      '<span class="theme-swatch" style="background-color:' +
      t.color +
      '"></span>';
    html +=
      '<span class="theme-info"><span class="theme-name">' +
      t.label +
      "</span>";
    html += '<span class="theme-hint">' + t.desc + "</span></span>";
    html += isActive ? '<span class="theme-check">&#10003;</span>' : "";
    html += "</button>";
  });
  html += "</div></div>";

  container.innerHTML = html;
}

function toggleThemeDropdown(e) {
  e.stopPropagation();
  var dropdown = document.getElementById("theme-dropdown");
  if (!dropdown) return;
  dropdown.style.display = dropdown.style.display === "none" ? "block" : "none";
}

document.addEventListener("click", function (e) {
  var dropdown = document.getElementById("theme-dropdown");
  var trigger = document.querySelector(".theme-trigger");
  if (dropdown && trigger && dropdown.style.display !== "none") {
    if (!trigger.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.style.display = "none";
    }
  }
});

document.addEventListener("DOMContentLoaded", function () {
  initTheme();
});

// config-nav.js - navigation, config loading
let currentConfig = {};

var _currentConfigSubTab = "import";

var _advancedConfigExpanded = false;

function toggleAdvancedConfig() {
  var toggle = document.querySelector(".config-advanced-toggle");
  var container = document.getElementById("advanced-config-container");
  var wrapper = document.getElementById("config-cards-wrapper");

  _advancedConfigExpanded = !_advancedConfigExpanded;

  if (_advancedConfigExpanded) {
    toggle.classList.add("expanded");

    if (wrapper) {
      wrapper.style.transition =
        "transform 0.5s cubic-bezier(0.4, 0, 1, 1), opacity 0.4s ease-out";
      wrapper.style.transform = "translateY(-100px) scale(0.95)";
      wrapper.style.opacity = "0";
      setTimeout(() => {
        wrapper.style.display = "none";
      }, 450);
    }

    container.style.transform = "translateY(400px)";
    container.style.opacity = "0";

    setTimeout(() => {
      container.classList.add("open");
      container.classList.add("reveal");
      requestAnimationFrame(() => {
        container.style.transition =
          "transform 0.9s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.6s ease-out";
        container.style.transform = "";
        container.style.opacity = "";
      });
    }, 200);
  } else {
    container.classList.remove("open");
    container.classList.remove("reveal");
    container.style.transition =
      "transform 0.5s cubic-bezier(0.4, 0, 1, 1), opacity 0.4s ease-out";
    container.style.transform = "translateY(400px)";
    container.style.opacity = "0";

    setTimeout(() => {
      container.style.transform = "";
    }, 500);

    if (wrapper) {
      wrapper.style.display = "";
      wrapper.style.transform = "translateY(100px) scale(0.95)";
      wrapper.style.opacity = "0";

      setTimeout(() => {
        requestAnimationFrame(() => {
          wrapper.style.transition =
            "transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.4s ease-out";
          wrapper.style.transform = "";
          wrapper.style.opacity = "";
        });
      }, 100);
    }

    setTimeout(() => {
      toggle.classList.remove("expanded");
      container.style.opacity = "";
    }, 500);
  }
}

var _navStack = [{ view: "home", breadcrumb: "配置" }];

var _viewConfig = {
  home: { section: null, viewGroup: null, breadcrumb: null },
  "dir-sub": { section: null, viewGroup: null, breadcrumb: "目录配置" },
  source: { section: "basic", viewGroup: "source", breadcrumb: "源目录" },
  temp: { section: "basic", viewGroup: "temp", breadcrumb: "中转目录" },
  recycle: { section: "basic", viewGroup: "recycle", breadcrumb: "回收站目录" },
  "source-cleaner": {
    section: "source_cleaner",
    viewGroup: null,
    breadcrumb: "源文件智能清理",
  },
  "path-rules": {
    section: "path_rules",
    viewGroup: null,
    breadcrumb: "入库规则",
    showReviewToggle: true,
  },
  "metadata-providers": {
    section: "metadata.providers",
    viewGroup: null,
    breadcrumb: "影视刮削配置",
  },
  "llm-config": {
    section: "llm",
    viewGroup: "llm-config",
    breadcrumb: "AI配置",
  },
  "ai-prompt": {
    section: "llm",
    viewGroup: "ai-prompt",
    breadcrumb: "AI配置",
  },
  "file-watcher": {
    section: "file_watcher",
    viewGroup: null,
    breadcrumb: "定时任务",
  },
  "import-options": {
    section: "import_options",
    viewGroup: null,
    breadcrumb: "入库名称规范",
    hideReviewToggle: true,
  },
  dimensions: {
    section: "dimensions",
    viewGroup: null,
    breadcrumb: "影视分类维度",
  },
  server: { section: "server", viewGroup: null, breadcrumb: "安全配置" },
  hermes: { section: "hermes", viewGroup: null, breadcrumb: "Hermes通知" },
  advanced: { section: "advanced", viewGroup: null, breadcrumb: "系统设置" },
};

function navTo(viewId) {
  var cfg = _viewConfig[viewId];
  if (!cfg) return;
  _navStack.push({ view: viewId, breadcrumb: cfg.breadcrumb || viewId });
  renderView(viewId);
  updateBreadcrumb();
}

function navBack() {
  if (_navStack.length <= 1) return;
  _navStack.pop();
  var top = _navStack[_navStack.length - 1];
  renderView(top.view);
  updateBreadcrumb();
}

function navToBreadcrumb(index) {
  if (index < 0 || index >= _navStack.length - 1) return;
  _navStack = _navStack.slice(0, index + 1);
  var top = _navStack[_navStack.length - 1];
  renderView(top.view);
  updateBreadcrumb();
}

function renderView(viewId) {
  var cfg = _viewConfig[viewId];
  if (!cfg) return;

  var cardsHome = document.getElementById("config-cards-home");
  var dirSub = document.getElementById("config-dir-sub-cards");
  var sectionsHost = document.getElementById("cfg-sections-host");

  if (cardsHome) cardsHome.classList.remove("active");
  if (dirSub) dirSub.classList.remove("active");

  if (viewId === "home") {
    if (cardsHome) cardsHome.classList.add("active");
    if (sectionsHost) {
      sectionsHost.querySelectorAll(".config-section").forEach(function (s) {
        s.classList.add("collapsed-section");
      });
    }
    return;
  }

  if (viewId === "dir-sub") {
    if (dirSub) dirSub.classList.add("active");
    if (sectionsHost) {
      sectionsHost.querySelectorAll(".config-section").forEach(function (s) {
        s.classList.add("collapsed-section");
      });
    }
    return;
  }

  if (sectionsHost) {
    sectionsHost.querySelectorAll(".config-section").forEach(function (sec) {
      var sectionName = sec.getAttribute("data-section");
      if (sectionName === cfg.section) {
        sec.classList.remove("collapsed-section");
        if (cfg.viewGroup) {
          sec.querySelectorAll("[data-view-group]").forEach(function (fg) {
            if (fg.getAttribute("data-view-group") === cfg.viewGroup) {
              fg.classList.add("view-visible");
            } else {
              fg.classList.remove("view-visible");
            }
          });
        } else {
          sec.querySelectorAll("[data-view-group]").forEach(function (fg) {
            fg.classList.add("view-visible");
          });
        }
      } else {
        sec.classList.add("collapsed-section");
        sec.querySelectorAll("[data-view-group]").forEach(function (fg) {
          fg.classList.remove("view-visible");
        });
      }
    });
  }

  var reviewToggle = document.getElementById("cfg-manual_review-enabled");
  if (reviewToggle) {
    var reviewGroup = reviewToggle.closest(".form-group");
    if (reviewGroup) {
      if (cfg.showReviewToggle) {
        reviewGroup.style.display = "";
      } else if (cfg.hideReviewToggle) {
        reviewGroup.style.display = "none";
      } else {
        reviewGroup.style.display = "";
      }
    }
  }

  if (cfg.section === "dimensions" && typeof loadDimensions === "function") {
    loadDimensions();
  }
}

function updateBreadcrumb() {
  var container = document.getElementById("config-breadcrumb");
  if (!container) return;
  var backBtn = container.querySelector(".back-btn");
  if (backBtn) {
    backBtn.style.display = _navStack.length > 1 ? "" : "none";
  }
  var itemsHtml = "";
  for (var i = 0; i < _navStack.length; i++) {
    var item = _navStack[i];
    var isCurrent = i === _navStack.length - 1;
    if (i > 0) {
      itemsHtml += '<span class="config-breadcrumb-separator">›</span>';
    }
    if (isCurrent) {
      itemsHtml +=
        '<span class="config-breadcrumb-item current">' +
        item.breadcrumb +
        "</span>";
    } else {
      itemsHtml +=
        '<span class="config-breadcrumb-item" onclick="navToBreadcrumb(' +
        i +
        ')">' +
        item.breadcrumb +
        "</span>";
    }
  }
  var existingItems = container.querySelectorAll(
    ".config-breadcrumb-item, .config-breadcrumb-separator",
  );
  existingItems.forEach(function (el) {
    el.remove();
  });
  container.insertAdjacentHTML("beforeend", itemsHtml);
}

async function savePathRulesWithReview() {
  await saveSection("path_rules");
  await saveSection("import_options");
}

function switchTab(tabName) {
  var panels = document.querySelectorAll(".panel");
  var tabs = document.querySelectorAll(".tab-btn");

  panels.forEach((p) => p.classList.remove("active"));
  tabs.forEach((t) => t.classList.remove("active"));

  document.getElementById(`${tabName}-panel`).classList.add("active");
  document.getElementById(`tab-${tabName}`).classList.add("active");

  if (tabName === "tasks") {
    loadTasks();
    refreshLogs();
  }

  if (tabName === "config") {
    var breadcrumb = document.getElementById("config-breadcrumb");
    if (breadcrumb) breadcrumb.style.display = "";
    if (_navStack.length <= 1) {
      navTo("home");
    } else {
      var top = _navStack[_navStack.length - 1];
      renderView(top.view);
      updateBreadcrumb();
    }
  } else {
    var breadcrumb = document.getElementById("config-breadcrumb");
    if (breadcrumb) breadcrumb.style.display = "none";
  }

  if (tabName === "recycle") {
    loadRecycleList();
  }
}

function _safeGet(obj) {
  var result = obj;
  for (var i = 1; i < arguments.length; i++) {
    if (result == null) return "";
    result = result[arguments[i]];
  }
  return result || "";
}

async function loadConfig() {
  try {
    var result = await apiRequest("GET", "/config");
    if (result.code !== 200 || !result.data || !result.data.config) {
      showToast("加载配置失败: " + (result.message || "未知错误"), "error");
      return;
    }
    currentConfig = result.data.config;
    var c = currentConfig;

    var server = c.server || {};
    document.getElementById("cfg-server_api_key").value = server.api_key || "";
    document.getElementById("cfg-server_port").value = server.port || 9855;

    document.getElementById("cfg-source_dir").value = c.source_dir || "";
    document.getElementById("cfg-temp_dir").value = c.temp_dir || "";
    document.getElementById("cfg-log_dir").value = c.log_dir || "";

    var sourcePolicy = c.source_policy || {};
    document.getElementById("cfg-source_policy-recycle_dir").value =
      sourcePolicy.recycle_dir || sourcePolicy.quarantine_dir || "";
    document.getElementById(
      "cfg-source_policy-cleanup_source_after_done",
    ).checked = sourcePolicy.cleanup_source_after_done !== false;
    document.getElementById("cfg-source_policy-recycle_retention_days").value =
      sourcePolicy.recycle_retention_days != null
        ? sourcePolicy.recycle_retention_days
        : 0;

    var sourceCleaner = c.source_cleaner || {};
    document.getElementById("cfg-source_cleaner-enabled").checked =
      !!sourceCleaner.enabled;
    var cleanerModeRadios = document.querySelectorAll(
      'input[name="cfg-source_cleaner-cleanup_mode"]',
    );
    var cleanerMode = sourceCleaner.cleanup_mode || "media_only";
    cleanerModeRadios.forEach(function (r) {
      r.checked = r.value === cleanerMode;
    });
    document.getElementById("cfg-source_cleaner-ai_enabled").checked =
      !!sourceCleaner.ai_enabled;
    document.getElementById("cfg-source_cleaner-merge_strategy").value =
      sourceCleaner.merge_strategy || "intersection";
    document.getElementById("cfg-source_cleaner-junk_video_max_size_mb").value =
      sourceCleaner.junk_video_max_size_mb != null
        ? sourceCleaner.junk_video_max_size_mb
        : 0;
    document.getElementById("cfg-source_cleaner-delete_extensions").value = (
      sourceCleaner.delete_extensions || []
    ).join("\n");
    document.getElementById("cfg-source_cleaner-protect_extensions").value = (
      sourceCleaner.protect_extensions || []
    ).join("\n");
    document.getElementById("cfg-source_cleaner-blacklist_patterns").value = (
      sourceCleaner.blacklist_patterns || []
    ).join("\n");
    document.getElementById("cfg-source_cleaner-cleanup_empty_dirs").checked =
      !!sourceCleaner.cleanup_empty_dirs;
    document.getElementById("cfg-source_cleaner-schedule").value =
      sourceCleaner.schedule || "";
    onSourceCleanerToggle();

    var metadata = c.metadata || {};
    loadProviderConfigUI(metadata);

    updateAiConfigStatus();

    var watcher = c.file_watcher || {};
    document.getElementById("cfg-watcher_enabled").checked = !!watcher.enabled;
    document.getElementById("cfg-watcher_poll_interval").value =
      watcher.poll_interval || 30;
    document.getElementById("cfg-watcher_ignore_patterns").value = (
      watcher.ignore_patterns || []
    ).join("\n");

    var hermes = c.hermes || {};
    var webhook = hermes.webhook || {};
    document.getElementById("cfg-hermes_enabled").checked = !!hermes.enabled;
    document.getElementById("cfg-hermes_webhook_base_url").value =
      webhook.base_url || "";
    document.getElementById("cfg-hermes_webhook_route_name").value =
      webhook.route_name || "";
    document.getElementById("cfg-hermes_webhook_secret").value =
      webhook.secret || "";
    document.getElementById("cfg-hermes_webhook_timeout").value =
      webhook.timeout || 30;
    document.getElementById("cfg-hermes_webhook_max_retries").value =
      webhook.max_retries || 3;
    document.getElementById("cfg-hermes_webhook_retry_delay").value =
      webhook.retry_delay || 5;
    document.getElementById("cfg-hermes_webhook_verify_ssl").checked =
      !!webhook.verify_ssl;

    var events = webhook.events || [];
    document.getElementById("cfg-hermes_event_batch_start").checked =
      events.indexOf("batch_start") >= 0;
    document.getElementById("cfg-hermes_event_batch_complete").checked =
      events.indexOf("batch_complete") >= 0;
    document.getElementById("cfg-hermes_event_program_error").checked =
      events.indexOf("program_error") >= 0;

    onHermesToggle();

    var scan = c.source_policy || {};
    document.getElementById("cfg-source_dir_scan-recursive").checked =
      scan.scan_recursive !== false;
    document.getElementById("cfg-source_dir_scan-max_depth").value =
      scan.scan_max_depth || 5;

    if (typeof loadEnabledDimensions === "function") {
      await loadEnabledDimensions();
    }

    var pathRules = c.path_rules || [];
    renderPathRules(pathRules);

    document.getElementById("cfg-fallback_dir").value = c.fallback_dir || "";

    var ft = c.filename_templates || {};
    document.getElementById("cfg-filename_templates-movie").value =
      ft.movie || "";
    document.getElementById("cfg-filename_templates-tv").value = ft.tv || "";
    document.getElementById("cfg-filename_templates-subtitle").value =
      ft.subtitle || "";

    var dup = c.duplicate_handling || {};
    document.getElementById("cfg-duplicate_handling-strategy").value =
      dup.strategy || "skip";

    var tq = c.task_queue || {};
    document.getElementById("cfg-task_queue-max_concurrent").value =
      tq.max_concurrent || 1;

    var videoExts = c.video_extensions || [];
    var subExts = c.subtitle_extensions || [];
    var videoExtEl = document.getElementById("cfg-video_extensions");
    var subExtEl = document.getElementById("cfg-subtitle_extensions");
    if (videoExtEl) videoExtEl.value = videoExts.join("\n");
    if (subExtEl) subExtEl.value = subExts.join("\n");

    var manualReview = c.manual_review || {};
    document.getElementById("cfg-manual_review-enabled").checked =
      !!manualReview.enabled;
  } catch (e) {
    console.error("loadConfig error:", e);
    showToast("加载配置异常: " + e.message, "error");
  }
}

function isMaskedValue(value) {

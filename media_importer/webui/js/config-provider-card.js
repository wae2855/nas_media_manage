// config-provider-card.js - provider card rendering
function renderProviderCard(provider, savedConfig) {
  var card = document.createElement("div");
  var enabled = savedConfig
    ? savedConfig.enabled !== false
    : provider.enabled !== false;
  card.className = "provider-card" + (enabled ? "" : " disabled-provider");
  var config = {};
  var providerConfig = provider.config || {};
  if (savedConfig) {
    for (var ck in savedConfig) {
      config[ck] = savedConfig[ck];
    }
    for (var ck in providerConfig) {
      if (!(ck in config) || config[ck] === "" || config[ck] === "***") {
        config[ck] = providerConfig[ck];
      }
    }
  } else {
    config = providerConfig;
  }
  var schema = provider.config_schema || { fields: [] };
  var html =
    '<div class="provider-card-header" onclick="toggleProviderCard(this)">';
  html +=
    '<span class="provider-name">' +
    _escapeHtml(provider.display_name) +
    "</span>";
  html +=
    '<svg class="collapse-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><polyline points="6 9 12 15 18 9"/></svg>';
  html +=
    '<label class="toggle-switch" onclick="event.stopPropagation()"><input type="checkbox" id="cfg-provider-' +
    provider.type +
    '-enabled"' +
    (enabled ? " checked" : "") +
    " onchange=\"onProviderToggle('" +
    provider.type +
    '\', this)"><label for="cfg-provider-' +
    provider.type +
    '-enabled"></label></label>';
  html += "</div>";
  html += '<div class="provider-card-body">';
  for (var i = 0; i < schema.fields.length; i++) {
    var f = schema.fields[i];
    var val = config[f.key];
    if (val === undefined || val === null) val = f.default || "";
    if (f.key === "api_key" && val === "") val = "";
    html += '<div class="form-group">';
    html += '<label class="form-label">' + _escapeHtml(f.label) + "</label>";
    if (f.type === "password") {
      var placeholder = _escapeHtml(f.label);
      if (f.key === "api_key" && config.api_key && config.api_key !== "") {
        placeholder = "已保存，留空保持不变";
      }
      html +=
        '<input type="password" id="cfg-provider-' +
        provider.type +
        "-" +
        f.key +
        '" class="form-input" value="' +
        _escapeHtml(String(val)) +
        '" placeholder="' +
        placeholder +
        "\" onfocus=\"if(this.value==='***')this.value=''\" onblur=\"if(!this.value&&this.dataset.hadKey)this.value='***'\"";
      if (f.key === "api_key" && val === "***") {
        html += ' data-had-key="true"';
      }
      html += ">";
    } else if (f.type === "select") {
      html +=
        '<select id="cfg-provider-' +
        provider.type +
        "-" +
        f.key +
        '" class="form-select">';
      for (var j = 0; j < f.options.length; j++) {
        var opt = f.options[j];
        html +=
          '<option value="' +
          _escapeHtml(opt.value) +
          '"' +
          (opt.value === val ? " selected" : "") +
          ">" +
          _escapeHtml(opt.label) +
          "</option>";
      }
      html += "</select>";
    } else if (f.type === "number") {
      html +=
        '<input type="number" id="cfg-provider-' +
        provider.type +
        "-" +
        f.key +
        '" class="form-input" value="' +
        _escapeHtml(String(val)) +
        '">';
    } else {
      html +=
        '<input type="text" id="cfg-provider-' +
        provider.type +
        "-" +
        f.key +
        '" class="form-input" value="' +
        _escapeHtml(String(val)) +
        '">';
    }
    html += "</div>";
  }
  html += '<div class="section-actions">';
  html +=
    '<button class="btn btn-primary btn-sm" id="btn-save-provider-' +
    provider.type +
    '" onclick="saveSection(\'metadata.providers\')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> 保存</button>';
  html +=
    '<button class="btn btn-secondary btn-sm" id="btn-test-provider-' +
    provider.type +
    '" onclick="testProvider(\'' +
    provider.type +
    '\')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg> 测试连接</button>';
  html +=
    '<span class="test-result" id="provider-test-result-' +
    provider.type +
    '" style="display:none;"></span>';
  html +=
    '<button class="btn btn-secondary btn-sm" onclick="showProviderPreviewModal(\'' +
    provider.type +
    '\')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> 刮削预览</button>';
  html += "</div>";
  html += "</div>";
  card.innerHTML = html;
  return card;
}

function toggleProviderCard(headerEl) {
  var card = headerEl.closest(".provider-card");
  if (card) card.classList.toggle("collapsed");
}

function onProviderToggle(providerType, checkbox) {
  var card = checkbox.closest(".provider-card");
  if (!card) return;
  if (checkbox.checked) {
    card.classList.remove("disabled-provider");
  } else {
    card.classList.add("disabled-provider");
  }
}

function _buildBasicData() {
  return {
    source_dir: document.getElementById("cfg-source_dir").value,
    temp_dir: document.getElementById("cfg-temp_dir").value,
    source_policy: {
      recycle_dir: document.getElementById("cfg-source_policy-recycle_dir")
        .value,
      cleanup_source_after_done: document.getElementById(
        "cfg-source_policy-cleanup_source_after_done",
      ).checked,
      recycle_retention_days:
        parseInt(
          document.getElementById("cfg-source_policy-recycle_retention_days")
            .value,
        ) || 0,
      scan_recursive: document.getElementById("cfg-source_dir_scan-recursive")
        .checked,
      scan_max_depth:
        parseInt(
          document.getElementById("cfg-source_dir_scan-max_depth").value,
        ) || 5,
    },
  };
}

function _buildSourceCleanerData() {
  return {
    source_cleaner: {
      enabled: document.getElementById("cfg-source_cleaner-enabled").checked,
      cleanup_mode:
        (
          document.querySelector(
            'input[name="cfg-source_cleaner-cleanup_mode"]:checked',
          ) || {}
        ).value || "media_only",
      ai_enabled: document.getElementById("cfg-source_cleaner-ai_enabled")
        .checked,
      merge_strategy:
        document.getElementById("cfg-source_cleaner-merge_strategy").value ||
        "intersection",
      junk_video_max_size_mb:
        parseInt(
          document.getElementById("cfg-source_cleaner-junk_video_max_size_mb")
            .value,
        ) || 0,
      delete_extensions: _parseMultiLineInput(
        "cfg-source_cleaner-delete_extensions",
      ),
      protect_extensions: _parseMultiLineInput(
        "cfg-source_cleaner-protect_extensions",
      ),
      blacklist_patterns: _parseMultiLineInput(
        "cfg-source_cleaner-blacklist_patterns",
      ),
      cleanup_empty_dirs: document.getElementById(
        "cfg-source_cleaner-cleanup_empty_dirs",
      ).checked,
      schedule: document
        .getElementById("cfg-source_cleaner-schedule")
        .value.trim(),
    },
  };
}

function _parseMultiLineInput(id) {
  var el = document.getElementById(id);
  if (!el) return [];
  var raw = el.value || "";
  return raw
    .split(/[\n,]+/)
    .map(function (s) {
      return s.trim();
    })
    .filter(Boolean);
}

function _buildPathRulesData() {
  var rules = collectPathRulesFromDOM();
  var uncheckedRules = [];
  for (var i = 0; i < rules.length; i++) {
    var cond = rules[i].conditions || {};
    if (Object.keys(cond).length === 0) {
      uncheckedRules.push(i + 1);
    }
  }
  return {
    path_rules: rules,
    fallback_dir: document.getElementById("cfg-fallback_dir")
      ? document.getElementById("cfg-fallback_dir").value
      : "",
    _uncheckedRules: uncheckedRules,
  };
}

function _buildImportOptionsData() {
  return {
    manual_review: {
      enabled: document.getElementById("cfg-manual_review-enabled").checked,
    },
    duplicate_handling: {
      strategy: document.getElementById("cfg-duplicate_handling-strategy")
        .value,
    },
    filename_templates: {
      movie: document.getElementById("cfg-filename_templates-movie").value,
      tv: document.getElementById("cfg-filename_templates-tv").value,
      subtitle: document.getElementById("cfg-filename_templates-subtitle")
        .value,
    },
  };
}

function _buildProviderData() {
  var providers = [];
  var metadata = currentConfig.metadata || {};
  var providerList = metadata.providers || [];
  var allTypes = Object.keys(_cachedProviderSchemas);
  var seenTypes = {};
  for (var i = 0; i < providerList.length; i++) {
    var p = providerList[i];
    var ptype = p.type;
    seenTypes[ptype] = true;
    var providerData = {
      type: ptype,
      enabled: document.getElementById("cfg-provider-" + ptype + "-enabled")
        ? document.getElementById("cfg-provider-" + ptype + "-enabled").checked
        : p.enabled !== false,
    };
    var schemaFields =
      (_cachedProviderSchemas[ptype] && _cachedProviderSchemas[ptype].fields) ||
      [];
    for (var j = 0; j < schemaFields.length; j++) {
      var f = schemaFields[j];
      if (f.key === "api_key") {
        var apiKeyInput = document.getElementById(
          "cfg-provider-" + ptype + "-api_key",
        );
        if (apiKeyInput) {
          var val = apiKeyInput.value;
          if (val && !isMaskedValue(val)) {
            providerData[f.key] = val;
          } else if (p.api_key && p.api_key !== "***") {
            providerData[f.key] = p.api_key;
          }
        }
      } else {
        var input = document.getElementById(
          "cfg-provider-" + ptype + "-" + f.key,
        );
        if (input) providerData[f.key] = input.value;
      }
    }
    providers.push(providerData);
  }
  for (var k = 0; k < allTypes.length; k++) {
    var t = allTypes[k];
    if (seenTypes[t]) continue;
    var providerData = {
      type: t,
      enabled: document.getElementById("cfg-provider-" + t + "-enabled")
        ? document.getElementById("cfg-provider-" + t + "-enabled").checked
        : false,
    };
    var schemaFields =
      (_cachedProviderSchemas[t] && _cachedProviderSchemas[t].fields) || [];
    for (var j = 0; j < schemaFields.length; j++) {
      var f = schemaFields[j];
      if (f.key === "api_key") {
        var apiKeyInput = document.getElementById(
          "cfg-provider-" + t + "-api_key",
        );
        if (apiKeyInput) {
          var val = apiKeyInput.value;
          if (val && !isMaskedValue(val)) {
            providerData[f.key] = val;
          }
        }
      } else {
        var input = document.getElementById("cfg-provider-" + t + "-" + f.key);
        if (input) providerData[f.key] = input.value;
      }
    }
    providers.push(providerData);
  }
  return { metadata: { providers: providers } };
}
var _buildTmdbData = _buildProviderData;

function _buildServerData() {
  var data = {
    server: {
      port: parseInt(document.getElementById("cfg-server_port").value) || 9855,
    },
  };
  var serverApiKey = document.getElementById("cfg-server_api_key").value;
  if (serverApiKey && !isMaskedValue(serverApiKey)) {
    data.server.api_key = serverApiKey;
  } else if (currentConfig.server && currentConfig.server.api_key) {
    data.server.api_key = currentConfig.server.api_key;
  }
  return data;
}

function _buildHermesData() {
  var data = {
    hermes: {
      enabled: document.getElementById("cfg-hermes_enabled").checked,
      webhook: {
        base_url: document.getElementById("cfg-hermes_webhook_base_url").value,
        route_name: document.getElementById("cfg-hermes_webhook_route_name")
          .value,
        timeout:
          parseInt(
            document.getElementById("cfg-hermes_webhook_timeout").value,
          ) || 30,
        max_retries:
          parseInt(
            document.getElementById("cfg-hermes_webhook_max_retries").value,
          ) || 3,
        retry_delay:
          parseInt(
            document.getElementById("cfg-hermes_webhook_retry_delay").value,
          ) || 5,
        verify_ssl: document.getElementById("cfg-hermes_webhook_verify_ssl")
          .checked,
      },
    },
  };
  var secret = document.getElementById("cfg-hermes_webhook_secret").value;
  if (secret && !isMaskedValue(secret)) {
    data.hermes.webhook.secret = secret;
  } else if (
    currentConfig.hermes &&
    currentConfig.hermes.webhook &&
    currentConfig.hermes.webhook.secret
  ) {
    data.hermes.webhook.secret = currentConfig.hermes.webhook.secret;
  }
  var hermesEvents = [];
  if (document.getElementById("cfg-hermes_event_batch_start").checked)
    hermesEvents.push("batch_start");
  if (document.getElementById("cfg-hermes_event_batch_complete").checked)
    hermesEvents.push("batch_complete");
  if (document.getElementById("cfg-hermes_event_program_error").checked)
    hermesEvents.push("program_error");
  data.hermes.webhook.events = hermesEvents;
  return data;
}

function _buildWatcherData() {
  return {
    file_watcher: {
      enabled: document.getElementById("cfg-watcher_enabled").checked,
      poll_interval: parseInt(
        document.getElementById("cfg-watcher_poll_interval").value,
      ),
      ignore_patterns: document
        .getElementById("cfg-watcher_ignore_patterns")
        .value.split("\n")
        .filter((line) => line.trim()),
    },
  };
}

function _buildAdvancedData() {
  var videoExtEl = document.getElementById("cfg-video_extensions");
  var subExtEl = document.getElementById("cfg-subtitle_extensions");
  var videoExts = [];
  var subExts = [];
  if (videoExtEl) {
    videoExts = videoExtEl.value
      .split("\n")
      .map(function (s) {
        s = s.trim();
        if (s && !s.startsWith(".")) s = "." + s;
        return s;
      })
      .filter(function (s) {
        return s;
      });
  }
  if (subExtEl) {
    subExts = subExtEl.value
      .split("\n")
      .map(function (s) {
        s = s.trim();
        if (s && !s.startsWith(".")) s = "." + s;
        return s;
      })
      .filter(function (s) {
        return s;
      });
  }
  return {
    log_dir: document.getElementById("cfg-log_dir").value,
    task_queue: {
      max_concurrent: parseInt(
        document.getElementById("cfg-task_queue-max_concurrent").value,
      ),
    },
    video_extensions: videoExts,
    subtitle_extensions: subExts,
  };
}

var _sectionBuilders = {
  basic: _buildBasicData,
  source_cleaner: _buildSourceCleanerData,
  path_rules: _buildPathRulesData,
  import_options: _buildImportOptionsData,
  "metadata.providers": _buildProviderData,
  server: _buildServerData,
  hermes: _buildHermesData,
  file_watcher: _buildWatcherData,
  advanced: _buildAdvancedData,
  // 旧数值评分构建器已移除
};


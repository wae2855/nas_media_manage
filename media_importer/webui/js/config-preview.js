// config-preview.js - AI config, provider preview
var SC_AI_DEFAULT_PROMPT =
  '你是"影音库AI智能整理"系统的源目录清理助手。你的任务是分析源目录中的文件，判断哪些是垃圾文件应该删除，哪些是影视相关文件应该保留。\n\n【分析原则】\n1. 整体视角：分析整个目录的文件构成，而非孤立判断单个文件\n2. 容量对比：同一目录下，视频文件大小差异显著时，小文件大概率是广告/样本/预告\n3. 命名模式：文件名含 sample、trailer、预告、花絮、广告等关键词的应删除\n4. 关联识别：与视频同名的 .nfo、.jpg、.png 等是影视元数据/海报，应保留\n5. 字幕文件：.srt、.ass 等字幕文件应保留\n6. 保守原则：无法确定时倾向于保留，避免误删\n\n【判断标准】\n- 主视频文件（通常最大的视频文件）→ 保留\n- 字幕文件 → 保留\n- 与主视频同名的元数据/海报 → 保留\n- 样本/预告/广告视频（明显小于主视频）→ 删除\n- BT下载附带的无用文件（.url, .txt说明, 下载站广告图）→ 删除\n- 无法判断的文件 → 保留\n\n【输出格式】\n请严格按以下JSON格式返回，不要添加任何解释文字：\n{\n    "analysis": "简要分析说明",\n    "decisions": {\n        "文件名": {"action": "keep或delete", "reason": "判断理由"}\n    }\n}';

function switchSCTab(tabName) {
  var tabs = document.querySelectorAll(".sc-tab-btn");
  var panels = document.querySelectorAll(".sc-tab-panel");
  tabs.forEach(function (t) {
    t.classList.toggle("active", t.getAttribute("data-sc-tab") === tabName);
  });
  panels.forEach(function (p) {
    p.classList.toggle("active", p.getAttribute("data-sc-panel") === tabName);
  });
}

function toggleSCAdvanced() {
  var toggle = document.querySelector(".sc-advanced-toggle");
  var body = document.getElementById("sc-advanced-body");
  if (!toggle || !body) return;
  var collapsed = body.classList.contains("collapsed-section");
  if (collapsed) {
    body.classList.remove("collapsed-section");
    toggle.classList.add("expanded");
  } else {
    body.classList.add("collapsed-section");
    toggle.classList.remove("expanded");
  }
}

async function testHermes() {
  var btn = document.getElementById("btn-test-hermes");
  var resultEl = document.getElementById("hermes-test-result");
  btn.disabled = true;
  resultEl.style.display = "inline-block";
  resultEl.className = "test-result loading";
  resultEl.textContent = "测试中...";

  var data = _buildHermesData();
  var hermes = data.hermes || {};
  var webhook = hermes.webhook || {};
  var result = await apiRequest("POST", "/config/test-hermes", {
    base_url: webhook.base_url || "",
    route_name: webhook.route_name || "",
    secret: webhook.secret || "",
  });

  btn.disabled = false;
  if (result.code === 200 && result.data && result.data.success) {
    resultEl.className = "test-result success";
    resultEl.textContent = "✓ " + (result.data.message || "通知发送成功");
  } else {
    resultEl.className = "test-result error";
    resultEl.textContent =
      "✗ " +
      ((result.data && result.data.message) || result.message || "测试失败");
  }
}

async function testProvider(providerType) {
  var btn = document.getElementById("btn-test-provider-" + providerType);
  var resultEl = document.getElementById(
    "provider-test-result-" + providerType,
  );
  if (!btn || !resultEl) return;
  btn.disabled = true;
  resultEl.style.display = "inline-block";
  resultEl.className = "test-result loading";
  resultEl.textContent = "测试中...";
  var result = await apiRequest(
    "POST",
    "/providers/" + providerType + "/test",
    {},
  );
  btn.disabled = false;
  if (result.code === 200 && result.data && result.data.success) {
    resultEl.className = "test-result success";
    resultEl.textContent = "✓ " + (result.data.message || "连通正常");
  } else {
    resultEl.className = "test-result error";
    resultEl.textContent =
      "✗ " +
      ((result.data && result.data.message) || result.message || "测试失败");
  }
}
var testTMDb = function () {
  testProvider("tmdb");
};

var _currentPreviewProviderType = "tmdb";

function showProviderPreviewModal(providerType) {
  _currentPreviewProviderType = providerType || "tmdb";
  var existing = document.getElementById("tmdb-preview-modal");
  if (existing) existing.remove();

  var lang = "zh-CN";
  var cfgLangEl = document.getElementById(
    "cfg-provider-" + _currentPreviewProviderType + "-language",
  );
  if (cfgLangEl && cfgLangEl.value) lang = cfgLangEl.value;

  var providerDisplayName = _currentPreviewProviderType.toUpperCase();

  var modal = document.createElement("div");
  modal.id = "tmdb-preview-modal";
  modal.className = "modal-overlay";
  modal.innerHTML =
    '<div class="modal tmdb-preview-modal-content">' +
    '<div class="modal-header">' +
    "<h3>" +
    _escapeHtml(providerDisplayName) +
    " 刮削预览</h3>" +
    '<button class="modal-close" onclick="closeTmdbPreviewModal()">&times;</button>' +
    "</div>" +
    '<div class="tmdb-preview-toolbar">' +
    '<input type="text" id="tmdb-preview-query" placeholder="输入影视名称..." class="form-input" style="flex:1;" onkeydown="if(event.key===\'Enter\')doTmdbPreview()">' +
    '<select id="tmdb-preview-type" class="form-select" style="width:100px;">' +
    '<option value="movie">电影</option>' +
    '<option value="tv">电视剧</option>' +
    "</select>" +
    '<select id="tmdb-preview-lang" class="form-select" style="width:130px;">' +
    '<option value="zh-CN"' +
    (lang === "zh-CN" ? " selected" : "") +
    ">中文 (zh-CN)</option>" +
    '<option value="en-US"' +
    (lang === "en-US" ? " selected" : "") +
    ">英文 (en-US)</option>" +
    '<option value="ja-JP"' +
    (lang === "ja-JP" ? " selected" : "") +
    ">日文 (ja-JP)</option>" +
    '<option value="ko-KR"' +
    (lang === "ko-KR" ? " selected" : "") +
    ">韩文 (ko-KR)</option>" +
    "</select>" +
    '<button class="btn btn-primary" id="btn-tmdb-preview-search" onclick="doTmdbPreview()">搜索</button>' +
    "</div>" +
    '<div class="tmdb-preview-panels">' +
    '<div class="tmdb-preview-left">' +
    '<div id="tmdb-search-results" class="tmdb-search-results"></div>' +
    "</div>" +
    '<div class="tmdb-preview-right">' +
    '<div id="tmdb-detail-container" class="tmdb-detail-container"></div>' +
    "</div>" +
    "</div>" +
    "</div>";
  document.body.appendChild(modal);
  document.getElementById("tmdb-preview-query").focus();
}
var showTmdbPreviewModal = function () {
  showProviderPreviewModal("tmdb");
};

function closeTmdbPreviewModal() {
  var modal = document.getElementById("tmdb-preview-modal");
  if (modal) modal.remove();
}

var _tmdbSelectedResultId = null;
var _tmdbSelectedResultType = null;

async function doTmdbPreview() {
  var query = document.getElementById("tmdb-preview-query").value.trim();
  var type = document.getElementById("tmdb-preview-type").value;
  var langEl = document.getElementById("tmdb-preview-lang");
  var language = langEl ? langEl.value : "zh-CN";
  var resultsEl = document.getElementById("tmdb-search-results");
  var detailEl = document.getElementById("tmdb-detail-container");
  var btn = document.getElementById("btn-tmdb-preview-search");

  if (!query) {
    resultsEl.innerHTML =
      '<div class="tmdb-preview-error">请输入影视名称</div>';
    return;
  }

  btn.disabled = true;
  resultsEl.innerHTML = '<div class="tmdb-preview-loading">搜索中...</div>';
  detailEl.innerHTML =
    '<div class="tmdb-preview-placeholder">点击左侧搜索结果查看详情</div>';
  _tmdbSelectedResultId = null;
  _tmdbSelectedResultType = null;

  var result = await apiRequest(
    "POST",
    "/providers/" + _currentPreviewProviderType + "/search",
    { query: query, type: type, language: language },
  );

  btn.disabled = false;

  if (result.code !== 200 || !result.data) {
    resultsEl.innerHTML =
      '<div class="tmdb-preview-error">' +
      _escapeHtml(result.message || "请求失败") +
      "</div>";
    return;
  }

  var items = result.data.items || result.data.results || result.data || [];
  if (!items || items.length === 0) {
    resultsEl.innerHTML = '<div class="tmdb-preview-error">未找到结果</div>';
    return;
  }

  var maxItems = items.length > 10 ? 10 : items.length;
  var html = "";
  for (var i = 0; i < maxItems; i++) {
    var item = items[i];
    var titleField =
      type === "tv"
        ? item.name || item.original_name
        : item.title || item.original_title;
    var origTitle = type === "tv" ? item.original_name : item.original_title;
    var dateField = type === "tv" ? item.first_air_date : item.release_date;
    var year = dateField ? dateField.substring(0, 4) : "";
    var posterUrl = item.poster_path
      ? "https://image.tmdb.org/t/p/w92" + item.poster_path
      : "";
    var rating =
      item.vote_average != null ? item.vote_average.toFixed(1) : "--";
    var overview = item.overview || "";
    if (overview.length > 80) overview = overview.substring(0, 80) + "...";

    html +=
      '<div class="tmdb-result-card" data-tmdb-id="' +
      _escapeHtml(String(item.id)) +
      '" data-tmdb-type="' +
      _escapeHtml(type) +
      '" onclick="_selectTmdbResult(this)">';
    if (posterUrl) {
      html +=
        '<img class="tmdb-result-poster" src="' +
        _escapeHtml(posterUrl) +
        '" alt="" loading="lazy">';
    } else {
      html +=
        '<div class="tmdb-result-poster tmdb-result-poster-placeholder">无海报</div>';
    }
    html += '<div class="tmdb-result-info">';
    html +=
      '<div class="tmdb-result-title">' +
      _escapeHtml(titleField || "未知") +
      "</div>";
    if (origTitle && origTitle !== titleField) {
      html +=
        '<div class="tmdb-result-original-title">' +
        _escapeHtml(origTitle) +
        "</div>";
    }
    html += '<div class="tmdb-result-meta">';
    if (year) html += "<span>" + _escapeHtml(year) + "</span>";
    html +=
      '<span class="tmdb-result-rating">★ ' + _escapeHtml(rating) + "</span>";
    html += "</div>";
    if (overview) {
      html +=
        '<div class="tmdb-result-overview">' + _escapeHtml(overview) + "</div>";
    }
    html += "</div></div>";
  }

  resultsEl.innerHTML = html;
}

async function _selectTmdbResult(cardEl) {
  var id = cardEl.getAttribute("data-tmdb-id");
  var type = cardEl.getAttribute("data-tmdb-type");
  var resultsEl = document.getElementById("tmdb-search-results");
  var detailEl = document.getElementById("tmdb-detail-container");

  var cards = resultsEl.querySelectorAll(".tmdb-result-card");
  for (var i = 0; i < cards.length; i++) {
    cards[i].classList.remove("selected");
  }
  cardEl.classList.add("selected");

  _tmdbSelectedResultId = id;
  _tmdbSelectedResultType = type;

  detailEl.innerHTML = '<div class="tmdb-preview-loading">加载详情中...</div>';

  var result = await apiRequest(
    "POST",
    "/providers/" + _currentPreviewProviderType + "/details",
    { id: id, type: type },
  );

  if (result.code !== 200 || !result.data) {
    detailEl.innerHTML =
      '<div class="tmdb-preview-error">' +
      _escapeHtml(result.message || "加载详情失败") +
      "</div>";
    return;
  }

  var data = result.data.details || result.data;
  detailEl.innerHTML = _renderTmdbDetailsStructured(data, type);
}

function _renderTmdbDetailsStructured(data, type) {
  var html = '<div class="tmdb-detail-view">';
  html +=
    '<div style="display:flex;justify-content:flex-end;margin-bottom:8px;">';
  html +=
    '<button class="btn btn-secondary btn-sm" id="tmdb-detail-toggle-btn" onclick="_toggleTmdbDetailView()">查看原始 JSON</button>';
  html += "</div>";

  html += '<div id="tmdb-detail-structured">';
  for (var gi = 0; gi < TMDB_FIELD_GROUPS.length; gi++) {
    var group = TMDB_FIELD_GROUPS[gi];
    var hasField = false;
    for (var fi = 0; fi < group.fields.length; fi++) {
      if (
        data[group.fields[fi]] !== undefined &&
        data[group.fields[fi]] !== null
      ) {
        hasField = true;
        break;
      }
    }
    if (!hasField) continue;

    html += '<div class="tmdb-detail-group">';
    html +=
      '<div class="tmdb-detail-group-header" onclick="this.parentElement.classList.toggle(\'collapsed\')">';
    html += "<span>" + _escapeHtml(group.label) + "</span>";
    html += '<span class="tmdb-detail-group-arrow">▼</span>';
    html += "</div>";
    html += '<div class="tmdb-detail-group-body">';

    for (var fj = 0; fj < group.fields.length; fj++) {
      var key = group.fields[fj];
      var val = data[key];
      if (val === undefined || val === null) continue;

      var label = getTmdbFieldLabel(key);
      html += '<div class="tmdb-detail-row">';
      html += '<span class="tmdb-detail-key">' + _escapeHtml(label) + "</span>";
      html +=
        '<span class="tmdb-detail-val">' +
        _renderTmdbFieldValue(key, val) +
        "</span>";
      html += "</div>";
    }

    html += "</div></div>";
  }
  html += "</div>";

  html += '<div id="tmdb-detail-raw" style="display:none;">';
  html +=
    '<pre class="tmdb-detail-raw-pre">' +
    _escapeHtml(JSON.stringify(data, null, 2)) +
    "</pre>";
  html += "</div>";

  html += "</div>";
  return html;
}

function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _renderTmdbFieldValue(key, val) {
  if (key === "poster_path" || key === "backdrop_path") {
    if (typeof val === "string" && val) {
      return (
        '<img src="https://image.tmdb.org/t/p/w300' +
        _escapeHtml(val) +
        '" alt="" style="max-width:200px;border-radius:6px;" loading="lazy">'
      );
    }
    return _escapeHtml(String(val));
  }

  if (key === "status" && typeof val === "string") {
    var statusLabel = TMDB_STATUS_DICT[val];
    if (statusLabel) return _escapeHtml(statusLabel);
    return _escapeHtml(val);
  }

  if (typeof val === "boolean") {
    return val ? "是" : "否";
  }

  if (typeof val === "string" || typeof val === "number") {
    return _escapeHtml(String(val));
  }

  if (Array.isArray(val)) {
    if (val.length === 0)
      return '<span style="color:var(--text-secondary);">-</span>';

    var firstItem = val[0];
    if (typeof firstItem === "string" || typeof firstItem === "number") {
      var parts = [];
      for (var i = 0; i < val.length; i++) {
        parts.push(_escapeHtml(String(val[i])));
      }
      return parts.join("、");
    }

    if (typeof firstItem === "object" && firstItem !== null) {
      var tags = "";
      for (var j = 0; j < val.length; j++) {
        var nameVal =
          val[j].name ||
          val[j].title ||
          val[j].iso_3166_1 ||
          val[j].iso_639_1 ||
          val[j].english_name ||
          "";
        if (nameVal) {
          tags +=
            '<span class="tmdb-preview-tag">' +
            _escapeHtml(String(nameVal)) +
            "</span>";
        }
      }
      return tags || '<span style="color:var(--text-secondary);">-</span>';
    }

    return _escapeHtml(JSON.stringify(val));
  }

  if (typeof val === "object" && val !== null) {
    var subHtml = "";
    var subKeys = Object.keys(val);
    for (var k = 0; k < subKeys.length; k++) {
      var subKey = subKeys[k];
      var subVal = val[subKey];
      if (subVal === undefined || subVal === null) continue;
      var subLabel = getTmdbFieldLabel(subKey);
      subHtml += '<div class="tmdb-detail-row tmdb-detail-sub-row">';
      subHtml +=
        '<span class="tmdb-detail-key">' + _escapeHtml(subLabel) + "</span>";
      subHtml +=
        '<span class="tmdb-detail-val">' +
        _renderTmdbFieldValue(subKey, subVal) +
        "</span>";
      subHtml += "</div>";
    }
    return subHtml || '<span style="color:var(--text-secondary);">-</span>';
  }

  return _escapeHtml(String(val));
}


// cinema-config-provider.js - extracted from cinema-config.js
let _currentPreviewProviderType = "tmdb";
let _tmdbSelectedResultId = null;
let _tmdbSelectedResultType = null;

async function previewProvider(providerType) {
  _currentPreviewProviderType = providerType || "tmdb";
  const existing = document.getElementById("tmdb-preview-modal");
  if (existing) existing.remove();

  let lang = "zh-CN";
  const cfgLangEl = document.getElementById(
    `cfg-provider-inline-${_currentPreviewProviderType}-language`,
  );
  if (cfgLangEl && cfgLangEl.value) lang = cfgLangEl.value;

  const providerDisplayName = _currentPreviewProviderType.toUpperCase();

  const overlay = document.createElement("div");
  overlay.id = "tmdb-preview-modal";
  overlay.className = "cinema-modal-overlay";
  overlay.innerHTML = `
        <div class="cinema-modal tmdb-preview-modal-content">
            <div class="cinema-modal-header">
                <h3>${escapeHtml(providerDisplayName)} 刮削预览</h3>
                <button type="button" class="cinema-modal-close" aria-label="关闭">×</button>
            </div>
            <div class="tmdb-preview-toolbar">
                <input type="text" id="tmdb-preview-query" placeholder="输入影视名称..." class="tmdb-preview-input" />
                <select id="tmdb-preview-type" class="tmdb-preview-select" style="width:100px;">
                    <option value="movie">电影</option>
                    <option value="tv">电视剧</option>
                </select>
                <select id="tmdb-preview-lang" class="tmdb-preview-select" style="width:130px;">
                    <option value="zh-CN"${lang === "zh-CN" ? " selected" : ""}>中文 (zh-CN)</option>
                    <option value="en-US"${lang === "en-US" ? " selected" : ""}>英文 (en-US)</option>
                    <option value="ja-JP"${lang === "ja-JP" ? " selected" : ""}>日文 (ja-JP)</option>
                    <option value="ko-KR"${lang === "ko-KR" ? " selected" : ""}>韩文 (ko-KR)</option>
                </select>
                <button class="btn btn-primary btn-sm" id="btn-tmdb-preview-search" type="button">搜索</button>
            </div>
            <div class="tmdb-preview-panels">
                <div class="tmdb-preview-left">
                    <div id="tmdb-search-results" class="tmdb-search-results"></div>
                </div>
                <div class="tmdb-preview-right">
                    <div id="tmdb-detail-container" class="tmdb-detail-container">
                        <div class="tmdb-preview-placeholder">点击左侧搜索结果查看详情</div>
                    </div>
                </div>
            </div>
        </div>
    `;
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) overlay.remove();
  });
  overlay
    .querySelector(".cinema-modal-close")
    ?.addEventListener("click", () => overlay.remove());
  document.body.appendChild(overlay);

  const queryInput = document.getElementById("tmdb-preview-query");
  const searchBtn = document.getElementById("btn-tmdb-preview-search");
  queryInput?.focus();
  queryInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") doProviderPreviewSearch();
  });
  searchBtn?.addEventListener("click", doProviderPreviewSearch);
}

async function doProviderPreviewSearch() {
  const query = String(
    document.getElementById("tmdb-preview-query")?.value || "",
  ).trim();
  const type = document.getElementById("tmdb-preview-type")?.value || "movie";
  const langEl = document.getElementById("tmdb-preview-lang");
  const language = langEl ? langEl.value : "zh-CN";
  const resultsEl = document.getElementById("tmdb-search-results");
  const detailEl = document.getElementById("tmdb-detail-container");
  const btn = document.getElementById("btn-tmdb-preview-search");

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

  const result = await requestApi(
    "POST",
    `/providers/${encodeURIComponent(_currentPreviewProviderType)}/search`,
    { query, type, language },
  );
  btn.disabled = false;

  if (result.code !== 200 || !result.data) {
    resultsEl.innerHTML = `<div class="tmdb-preview-error">${escapeHtml(result.message || "请求失败")}</div>`;
    return;
  }

  const items = result.data.items || result.data.results || result.data || [];
  if (!items || items.length === 0) {
    resultsEl.innerHTML = '<div class="tmdb-preview-error">未找到结果</div>';
    return;
  }

  const maxItems = Math.min(items.length, 10);
  let html = "";
  for (let i = 0; i < maxItems; i++) {
    const item = items[i];
    const titleField =
      item.title ||
      item.name ||
      item.original_title ||
      item.original_name ||
      "";
    const origTitle = item.original_title || item.original_name || "";
    const year =
      item.year ||
      (item.release_date || item.first_air_date || "").substring(0, 4) ||
      "";
    const posterUrl =
      item.poster_url ||
      (item.poster_path
        ? `https://image.tmdb.org/t/p/w92${item.poster_path}`
        : "");
    const rating =
      item.vote_average != null ? Number(item.vote_average).toFixed(1) : "--";
    let overview = item.overview || "";
    if (overview.length > 80) overview = overview.substring(0, 80) + "...";

    html += `<div class="tmdb-result-card" data-tmdb-id="${escapeHtml(String(item.id))}" data-tmdb-type="${escapeHtml(type)}">`;
    if (posterUrl) {
      html += `<img class="tmdb-result-poster" src="${escapeHtml(posterUrl)}" alt="" loading="lazy">`;
    } else {
      html +=
        '<div class="tmdb-result-poster tmdb-result-poster-placeholder">无海报</div>';
    }
    html += '<div class="tmdb-result-info">';
    html += `<div class="tmdb-result-title">${escapeHtml(titleField || "未知")}</div>`;
    if (origTitle && origTitle !== titleField) {
      html += `<div class="tmdb-result-original-title">${escapeHtml(origTitle)}</div>`;
    }
    html += '<div class="tmdb-result-meta">';
    if (year) html += `<span>${escapeHtml(year)}</span>`;
    html += `<span class="tmdb-result-rating">★ ${escapeHtml(rating)}</span>`;
    html += "</div>";
    if (overview) {
      html += `<div class="tmdb-result-overview">${escapeHtml(overview)}</div>`;
    }
    html += "</div></div>";
  }

  resultsEl.innerHTML = html;
  resultsEl.querySelectorAll(".tmdb-result-card").forEach((card) => {
    card.addEventListener("click", () => selectProviderPreviewResult(card));
  });
}

async function selectProviderPreviewResult(cardEl) {
  const id = cardEl.getAttribute("data-tmdb-id");
  const type = cardEl.getAttribute("data-tmdb-type");
  const resultsEl = document.getElementById("tmdb-search-results");
  const detailEl = document.getElementById("tmdb-detail-container");

  resultsEl
    .querySelectorAll(".tmdb-result-card")
    .forEach((c) => c.classList.remove("selected"));
  cardEl.classList.add("selected");

  _tmdbSelectedResultId = id;
  _tmdbSelectedResultType = type;

  detailEl.innerHTML = '<div class="tmdb-preview-loading">加载详情中...</div>';

  const result = await requestApi(
    "POST",
    `/providers/${encodeURIComponent(_currentPreviewProviderType)}/details`,
    { id, type },
  );

  if (result.code !== 200 || !result.data) {
    detailEl.innerHTML = `<div class="tmdb-preview-error">${escapeHtml(result.message || "加载详情失败")}</div>`;
    return;
  }

  const data = result.data.details || result.data;
  detailEl.innerHTML = renderProviderDetailsStructured(data, type);
}

function renderProviderDetailsStructured(data, type) {
  const fieldDict =
    typeof PROVIDER_FIELD_DICTS !== "undefined" &&
    PROVIDER_FIELD_DICTS[_currentPreviewProviderType]
      ? PROVIDER_FIELD_DICTS[_currentPreviewProviderType]
      : {};
  const fieldGroups =
    typeof PROVIDER_FIELD_GROUPS !== "undefined" &&
    PROVIDER_FIELD_GROUPS[_currentPreviewProviderType]
      ? PROVIDER_FIELD_GROUPS[_currentPreviewProviderType]
      : [];
  const statusDict =
    typeof PROVIDER_STATUS_DICTS !== "undefined" &&
    PROVIDER_STATUS_DICTS[_currentPreviewProviderType]
      ? PROVIDER_STATUS_DICTS[_currentPreviewProviderType]
      : {};

  let html = '<div class="tmdb-detail-view">';
  html +=
    '<div style="display:flex;justify-content:flex-end;margin-bottom:8px;">';
  html +=
    '<button class="btn btn-secondary btn-sm" id="tmdb-detail-toggle-btn" type="button">查看原始 JSON</button>';
  html += "</div>";

  html += '<div id="tmdb-detail-structured">';
  for (let gi = 0; gi < fieldGroups.length; gi++) {
    const group = fieldGroups[gi];
    let hasField = false;
    for (let fi = 0; fi < group.fields.length; fi++) {
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
    html += `<div class="tmdb-detail-group-header"><span>${escapeHtml(group.label)}</span><span class="tmdb-detail-group-arrow">▼</span></div>`;
    html += '<div class="tmdb-detail-group-body">';

    for (let fj = 0; fj < group.fields.length; fj++) {
      const key = group.fields[fj];
      const val = data[key];
      if (val === undefined || val === null) continue;

      const label = fieldDict[key] || key;
      html += '<div class="tmdb-detail-row">';
      html += `<span class="tmdb-detail-key">${escapeHtml(label)}</span>`;
      html += `<span class="tmdb-detail-val">${renderProviderFieldValue(key, val, statusDict)}</span>`;
      html += "</div>";
    }

    html += "</div></div>";
  }
  html += "</div>";

  html += '<div id="tmdb-detail-raw" style="display:none;">';
  html += `<pre class="tmdb-detail-raw-pre">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
  html += "</div>";

  html += "</div>";
  return html;
}

function renderProviderFieldValue(key, val, statusDict) {
  if (key === "poster_path" || key === "backdrop_path") {
    if (typeof val === "string" && val) {
      return `<img src="https://image.tmdb.org/t/p/w300${escapeHtml(val)}" alt="" style="max-width:200px;border-radius:6px;" loading="lazy">`;
    }
    return escapeHtml(String(val));
  }

  if (key === "status" && typeof val === "string" && statusDict) {
    const statusLabel = statusDict[val];
    if (statusLabel) return escapeHtml(statusLabel);
    return escapeHtml(val);
  }

  if (typeof val === "boolean") {
    return val ? "是" : "否";
  }

  if (typeof val === "string" || typeof val === "number") {
    return escapeHtml(String(val));
  }

  if (Array.isArray(val)) {
    if (val.length === 0) return '<span style="color:var(--muted);">-</span>';

    const firstItem = val[0];
    if (typeof firstItem === "string" || typeof firstItem === "number") {
      return val.map((v) => escapeHtml(String(v))).join("、");
    }

    if (typeof firstItem === "object" && firstItem !== null) {
      let tags = "";
      for (let j = 0; j < val.length; j++) {
        const nameVal =
          val[j].name ||
          val[j].title ||
          val[j].iso_3166_1 ||
          val[j].iso_639_1 ||
          val[j].english_name ||
          "";
        if (nameVal) {
          tags += `<span class="tmdb-preview-tag">${escapeHtml(String(nameVal))}</span>`;
        }
      }
      return tags || '<span style="color:var(--muted);">-</span>';
    }

    return escapeHtml(JSON.stringify(val));
  }

  if (typeof val === "object" && val !== null) {
    let subHtml = "";
    const subKeys = Object.keys(val);
    const fieldDict =
      typeof PROVIDER_FIELD_DICTS !== "undefined" &&
      PROVIDER_FIELD_DICTS[_currentPreviewProviderType]
        ? PROVIDER_FIELD_DICTS[_currentPreviewProviderType]
        : {};
    for (let k = 0; k < subKeys.length; k++) {
      const subKey = subKeys[k];
      const subVal = val[subKey];
      if (subVal === undefined || subVal === null) continue;
      const subLabel = fieldDict[subKey] || subKey;
      subHtml += '<div class="tmdb-detail-row tmdb-detail-sub-row">';
      subHtml += `<span class="tmdb-detail-key">${escapeHtml(subLabel)}</span>`;
      subHtml += `<span class="tmdb-detail-val">${renderProviderFieldValue(subKey, subVal, statusDict)}</span>`;
      subHtml += "</div>";
    }
    return subHtml || '<span style="color:var(--muted);">-</span>';
  }

  return escapeHtml(String(val));
}


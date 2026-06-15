// dimension-genre.js - genre rendering and picker
async function loadDimensions() {
  _startBackgroundGenreLoad();
  var result = await apiRequest("GET", "/dimensions");
  if (result.code === 200 && result.data) {
    _dimensionsData = result.data.dimensions || [];
  } else {
    _dimensionsData = [];
  }
  renderDimensions();
}

function renderDimensions() {
  var enabledList = document.getElementById("dim-enabled-list");
  var availableList = document.getElementById("dim-available-list");
  if (!enabledList || !availableList) return;

  var enabled = _dimensionsData.filter(function (d) {
    return d.is_enabled;
  });
  var available = _dimensionsData.filter(function (d) {
    return !d.is_enabled;
  });

  enabledList.innerHTML = enabled.length
    ? enabled
        .map(function (d) {
          return _renderDimCard(d, true);
        })
        .join("")
    : '<div class="dim-empty">暂无已启用维度</div>';

  availableList.innerHTML = available.length
    ? available
        .map(function (d) {
          return _renderDimCard(d, false);
        })
        .join("")
    : '<div class="dim-empty">所有维度均已启用</div>';
}

function _renderDimCard(dim, isEnabled) {
  var sourceLabel = getSourceLabel(dim.source_type);
  var isExpanded = _expandedDim === dim.name;
  var expandedClass = isExpanded ? " dim-card-expanded" : "";

  var tierHtml = "";
  if (dim.required_tier === "pro") {
    tierHtml = '<span class="dim-card-tier dim-card-tier-pro">PRO</span>';
  } else if (dim.required_tier === "premium") {
    tierHtml =
      '<span class="dim-card-tier dim-card-tier-premium">PREMIUM</span>';
  }

  var barActionsHtml = isEnabled
    ? '<button class="dim-btn-disable" type="button" data-dimension-action="disable" data-dimension-name="' +
      dim.name +
      '">禁用</button>'
    : '<button class="dim-btn-enable" type="button" data-dimension-action="enable" data-dimension-name="' +
      dim.name +
      '">启用</button>';

  var bodyHtml = isExpanded ? _renderDimBody(dim) : "";

  return (
    '<div class="dim-card' +
    expandedClass +
    '" id="dim-card-' +
    dim.name +
    '">' +
    '<div class="dim-card-bar" data-dimension-action="toggle-card" data-dimension-name="' +
    dim.name +
    '">' +
    '<span class="dim-card-color-dot" style="background:' +
    dim.color +
    '"></span>' +
    '<span class="dim-card-name">' +
    _escapeHtml(dim.label) +
    "</span>" +
    '<span class="dim-card-source">' +
    _escapeHtml(sourceLabel) +
    "</span>" +
    tierHtml +
    '<span class="dim-card-desc">' +
    _escapeHtml(dim.description || "") +
    "</span>" +
    '<div class="dim-card-bar-actions">' +
    barActionsHtml +
    "</div>" +
    '<svg class="dim-card-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>' +
    "</div>" +
    '<div class="dim-card-body"><div class="dim-card-body-inner">' +
    bodyHtml +
    "</div></div>" +
    "</div>"
  );
}

function _renderDimBody(dim) {
  try {
    var valueList = _parseValueList(dim.value_list);
    var sourceLabel = getSourceLabel(dim.source_type);

    var valuesHtml = valueList
      .map(function (v) {
        return (
          '<span class="dim-value-tag">' +
          _escapeHtml(v.label || v.value) +
          "</span>"
        );
      })
      .join("");

    var mappingHtml = "";
    var hasGenreMapping = false;
    var hasRegionMapping = false;
    var hasLangMapping = false;
    if (dim.source_type === "ai+provider") {
      var pm = dim.provider_mappings;
      if (typeof pm === "string") {
        try {
          pm = JSON.parse(pm);
        } catch (e) {
          pm = null;
        }
      }
      if (pm && typeof pm === "object") {
        for (var pmKey in pm) {
          if (pm[pmKey] && pm[pmKey].field === "genres") hasGenreMapping = true;
          if (pm[pmKey] && pm[pmKey].field === "origin_country")
            hasRegionMapping = true;
          if (pm[pmKey] && pm[pmKey].field === "original_language")
            hasLangMapping = true;
        }
      }
      if (dim.tmdb_field === "genres") hasGenreMapping = true;
      if (dim.tmdb_field === "origin_country") hasRegionMapping = true;
      if (dim.tmdb_field === "original_language") hasLangMapping = true;
    }

    if (
      dim.source_type === "ai+provider" &&
      hasGenreMapping &&
      dim.name !== "documentary" &&
      dim.name !== "animation"
    ) {
      mappingHtml = _renderGenreEditable(dim.name, valueList);
    } else if (dim.source_type === "ai+provider") {
      if (hasRegionMapping) mappingHtml = _renderRegionMapping(valueList);
      else if (hasLangMapping) mappingHtml = _renderLangMapping(valueList);
    }

    var autoRuleHtml = "";
    if (dim.name === "documentary") {
      autoRuleHtml =
        '<div class="dim-auto-rule-info">' +
        '<div class="dim-auto-rule-title">⚙ 自动判定规则</div>' +
        '<div class="dim-auto-rule-desc">从 Provider 获取影视的 genres 列表，若包含 <strong>Genre(99) = Documentary</strong> 则判定为纪录片（true），否则为非纪录片（false）。无需手动配置映射。</div>' +
        "</div>";
    } else if (dim.name === "animation") {
      autoRuleHtml =
        '<div class="dim-auto-rule-info">' +
        '<div class="dim-auto-rule-title">⚙ 自动判定规则</div>' +
        '<div class="dim-auto-rule-desc">从 Provider 获取影视的 genres 列表，若包含 <strong>Genre(16) = Animation</strong> 则判定为动漫（true），否则不做判定。无需手动配置映射。</div>' +
        "</div>";
    } else if (dim.name === "restricted_level") {
      autoRuleHtml =
        '<div class="dim-auto-rule-info">' +
        '<div class="dim-auto-rule-title">⚙ 自动判定规则</div>' +
        '<div class="dim-auto-rule-desc">从 Provider 获取 <strong>release_dates</strong> 字段中的分级认证（certification），按国家优先级（US → GB → 其他）匹配 MPAA 分级标准映射到年龄区间：G/U → 0-6、PG → 7-12、PG-13/12A → 13-16、R/NC-17 → 17+。若 Provider 无分级数据，则由 AI 根据内容辅助判断。</div>' +
        "</div>";
    }

    var trustDisabled = dim.name === "media_type" ? " disabled" : "";
    var trustHtml =
      '<div class="dim-trust-panel">' +
      '<label><input type="checkbox" id="dim-edit-trust-ai-assist"' +
      (dim.trust_ai_assist !== 0 ? " checked" : "") +
      trustDisabled +
      "> <span>🤖 信任AI辅助映射</span><small>Provider 有数据但映射复杂时，AI辅助给出的结果是否直接采纳。</small></label>" +
      '<label><input type="checkbox" id="dim-edit-trust-ai-search"' +
      (dim.trust_ai_search ? " checked" : "") +
      trustDisabled +
      "> <span>🔍 信任AI联网搜索</span><small>AI联网搜索增强补出的维度值是否直接采纳，不信任则进入人工确认。</small></label>" +
      (dim.name === "media_type"
        ? '<div class="dim-media-type-note"><span style="font-size:16px;margin-right:6px">✕</span><strong>影视类型由 Provider 搜索端点直接确定，不经过 AI 判断，无需配置 AI 信任。</strong></div>'
        : "") +
      "</div>";

    var aiPromptHtml = "";
    if (dim.source_type !== "file") {
      aiPromptHtml =
        '<div class="dim-edit-field">' +
        '<label class="dim-edit-label">AI 提示词 <span style="font-weight:400;color:var(--text-muted);">（保存时自动生成）</span></label>' +
        '<textarea id="dim-edit-ai-prompt" class="form-textarea" rows="3">' +
        _escapeHtml(dim.ai_prompt || "") +
        "</textarea>" +
        "</div>";
    }

    return (
      '<div class="dim-card-body-content">' +
      '<div class="dim-edit-row">' +
      '<span class="dim-edit-label">标识</span>' +
      '<span class="dim-edit-value" style="font-family:ui-monospace,monospace;font-size:12px;color:var(--text-muted);">' +
      _escapeHtml(dim.name) +
      "</span>" +
      "</div>" +
      '<div class="dim-edit-row">' +
      '<span class="dim-edit-label">来源</span>' +
      '<span class="dim-edit-value">' +
      _escapeHtml(sourceLabel) +
      "</span>" +
      "</div>" +
      '<div class="dim-edit-row">' +
      '<span class="dim-edit-label">颜色</span>' +
      '<input type="color" id="dim-edit-color" value="' +
      dim.color +
      '" class="dim-color-picker">' +
      "</div>" +
      trustHtml +
      aiPromptHtml +
      '<div class="dim-edit-row">' +
      '<span class="dim-edit-label">值域</span>' +
      '<div class="dim-value-tags">' +
      valuesHtml +
      "</div>" +
      "</div>" +
      mappingHtml +
      autoRuleHtml +
      '<div class="dim-edit-actions">' +
      '<button class="btn btn-primary btn-sm" type="button" data-dimension-action="save" data-dimension-name="' +
      dim.name +
      '">保存</button>' +
      (hasGenreMapping && dim.name !== "documentary" && dim.name !== "animation"
        ? '<button class="btn btn-warning btn-sm" type="button" data-dimension-action="reset" data-dimension-name="' +
          dim.name +
          '">恢复默认</button>'
        : "") +
      '<button class="btn btn-secondary btn-sm" type="button" data-dimension-action="collapse" data-dimension-name="' +
      dim.name +
      '">收起</button>' +
      "</div>" +
      "</div>"
    );
  } catch (e) {
    console.error("_renderDimBody error:", e);
    return (
      '<div class="dim-card-body-content"><div style="color:var(--danger-color);font-size:13px;">渲染出错: ' +
      _escapeHtml(e.message) +
      "</div></div>"
    );
  }
}

function _renderRegionMapping(valueList) {
  var rows = valueList
    .map(function (v) {
      var codes = (v.tmdb_codes || []).join(", ");
      var isOther = v.value === "other";
      var codeDisplay = isOther
        ? '<span style="font-size:12px;color:var(--text-muted);">兜底匹配</span>'
        : '<span class="dim-mapping-codes">' + _escapeHtml(codes) + "</span>";

      return (
        '<div class="dim-mapping-row">' +
        '<span class="dim-mapping-value">' +
        _escapeHtml(v.label) +
        "</span>" +
        '<span class="dim-mapping-arrow">←</span>' +
        codeDisplay +
        "</div>"
      );
    })
    .join("");

  return (
    '<div class="dim-mapping-section">' +
    '<div class="dim-mapping-header-row">' +
    '<span class="dim-mapping-col-label">入库标签值</span>' +
    '<span class="dim-mapping-col-label">Provider获取值</span>' +
    "</div>" +
    rows +
    '<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">地区映射基于 ISO 3166-1 代码（origin_country），无需手动编辑</div>' +
    "</div>"
  );
}

function _renderGenreRowHTML(dimName, item, origIdx, displayOrderNum) {
  var isOther = item.value === "other";
  var ids = item.tmdb_genre_ids || [];
  var idsJson = JSON.stringify(ids);
  var genreNames = ids.length
    ? _genreIdToLabel(ids.slice(0, 4)) +
      (ids.length > 4 ? " +" + (ids.length - 4) : "")
    : "-";

  var dragHandleHtml = isOther
    ? '<span class="dim-drag-placeholder"></span>'
    : '<span class="dim-drag-handle" draggable="true" data-dimension-action="genre-drag-handle" data-dim-name="' +
      dimName +
      '" data-genre-idx="' +
      origIdx +
      '"></span>';

  var priorityHtml = isOther
    ? '<span class="dim-genre-priority dim-genre-priority-other">-</span>'
    : '<span class="dim-genre-priority">' + displayOrderNum + "</span>";

  var genrePickerHtml = isOther
    ? '<span style="font-size:12px;color:var(--text-muted);">所有未匹配的类型</span>'
    : _renderGenrePickerTrigger(dimName, origIdx, ids);

  var deleteHtml = isOther
    ? ""
    : '<button class="dim-genre-remove" type="button" data-dimension-action="remove-genre-value" data-dim-name="' +
      dimName +
      '" data-genre-idx="' +
      origIdx +
      '" title="删除此类型值">×</button>';

  return (
    '<tr class="dim-genre-row" id="dim-genre-row-' +
    dimName +
    "-" +
    origIdx +
    '"' +
    ' data-dim-name="' +
    dimName +
    '"' +
    ' data-genre-idx="' +
    origIdx +
    '"' +
    ' data-genre-value="' +
    _escapeHtml(item.value) +
    '"' +
    " data-genre-ids='" +
    idsJson +
    "'>" +
    '<td class="dim-genre-td-drag">' +
    dragHandleHtml +
    "</td>" +
    '<td class="dim-genre-td-priority">' +
    priorityHtml +
    "</td>" +
    '<td class="dim-genre-td-label"><span class="dim-genre-label-text">' +
    _escapeHtml(item.label) +
    "</span></td>" +
    '<td class="dim-genre-td-picker">' +
    genrePickerHtml +
    "</td>" +
    '<td class="dim-genre-td-preview"><span class="dim-genre-names-preview">' +
    _escapeHtml(genreNames) +
    "</span></td>" +
    '<td class="dim-genre-td-action">' +
    deleteHtml +
    "</td>" +
    "</tr>"
  );
}

function _renderGenreRows(dimName, valueList) {
  var withIdx = valueList.map(function (v, i) {
    return { item: v, origIdx: i };
  });
  withIdx.sort(function (a, b) {
    return (a.item.priority || 99) - (b.item.priority || 99);
  });

  return withIdx
    .map(function (wi, sortedPos) {
      return _renderGenreRowHTML(dimName, wi.item, wi.origIdx, sortedPos + 1);
    })
    .join("");
}

function _renderGenreEditable(dimName, valueList) {
  return (
    '<div class="dim-mapping-section dim-genre-section">' +
    '<div class="dim-mapping-header">' +
    '<div style="display:flex;align-items:center;gap:6px;">' +
    "<h5>类型映射规则</h5>" +
    '<span class="dim-help-trigger" data-dimension-action="toggle-genre-help" title="映射说明">?</span>' +
    "</div>" +
    '<span class="dim-mapping-hint">每行定义一个题材类型，选择它包含的 Provider 原始类型；拖拽 ≡ 调整优先级</span>' +
    "</div>" +
    '<div class="dim-help-panel" id="dim-genre-help" style="display:none;">' +
    '<div class="dim-help-content">' +
    "<strong>这是什么？</strong>" +
    '<p>系统从 Provider 获取影视的原始类型标签（如"恐怖""喜剧"），<br>' +
    '通过这张映射表归并为你自定义的大类（如"恐怖/悬疑""剧情/情感"）。</p>' +
    "<p><strong>优先级：</strong>一部影视可能同时匹配多个大类，排在前面的优先。<br>" +
    '<strong>举例：</strong>《僵尸肖恩》同时是恐怖和喜剧，若"恐怖/悬疑"排在前面则归入该类。</p>' +
    "</div>" +
    "</div>" +
    '<table class="dim-genre-table">' +
    '<thead class="dim-genre-thead">' +
    "<tr>" +
    '<th class="dim-genre-th-drag"></th>' +
    '<th class="dim-genre-th-priority"></th>' +
    '<th class="dim-genre-th-label">入库标签值</th>' +
    '<th class="dim-genre-th-picker">Provider影视分类</th>' +
    '<th class="dim-genre-th-preview">预览</th>' +
    '<th class="dim-genre-th-action"></th>' +
    "</tr>" +
    "</thead>" +
    '<tbody class="dim-genre-rows" id="dim-genre-rows-' +
    dimName +
    '">' +
    _renderGenreRows(dimName, valueList) +
    "</tbody>" +
    "</table>" +
    '<div class="dim-genre-add-row" id="dim-genre-add-row-' +
    dimName +
    '">' +
    '<button class="dim-genre-add-btn" type="button" data-dimension-action="start-add-genre" data-dim-name="' +
    dimName +
    '">+ 添加类型值</button>' +
    "</div>" +
    "</div>"
  );
}


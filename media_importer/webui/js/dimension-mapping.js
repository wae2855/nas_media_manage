// dimension-mapping.js - bounded Provider mapping editor (schema v2)
var _dimensionMappingState = null;
var _dimensionMappingSelectSequence = 0;

function _mappingValues(dim) {
  return _parseValueList(dim && dim.value_list);
}

function _mappingSelectHtml(options, selected, ariaLabel, attributes) {
  var selectedValue = String(selected == null ? "" : selected);
  var selectedItem = options.find(function (item) {
    return String(item.value) === selectedValue;
  }) || options[0] || { value: "", label: "请选择" };
  var panelId = "provider-map-select-" + String(++_dimensionMappingSelectSequence);
  var optionHtml = options
    .map(function (item) {
      var value = String(item.value);
      var isSelected = value === String(selectedItem.value);
      return (
        '<button type="button" class="provider-map-select-option' +
        (isSelected ? " is-selected" : "") +
        '" role="option" tabindex="-1" data-map-select-option data-value="' +
        _escapeHtml(value) +
        '" aria-selected="' +
        (isSelected ? "true" : "false") +
        '"><span>' +
        _escapeHtml(item.label || value) +
        '</span><i aria-hidden="true">✓</i></button>'
      );
    })
    .join("");
  return (
    '<div class="provider-map-select" data-map-select data-value="' +
    _escapeHtml(selectedItem.value) +
    '" ' +
    (attributes || "") +
    '><button type="button" class="provider-map-select-trigger" role="combobox" aria-haspopup="listbox" aria-expanded="false" aria-controls="' +
    panelId +
    '" aria-label="' +
    _escapeHtml(ariaLabel || "选择映射值") +
    '"><span data-map-select-label>' +
    _escapeHtml(selectedItem.label || selectedItem.value) +
    '</span><svg aria-hidden="true" viewBox="0 0 20 20"><path d="m5 7.5 5 5 5-5"/></svg></button>' +
    '<div class="provider-map-select-panel" id="' +
    panelId +
    '" role="listbox" hidden>' +
    optionHtml +
    "</div></div>"
  );
}

function _mappingTargetSelect(values, selected, ariaLabel) {
  return _mappingSelectHtml(
    values.map(function (item) {
      return { value: String(item.value), label: item.label || item.value };
    }),
    selected,
    ariaLabel,
    "",
  );
}

function _mappingTargetLabel(dim, value) {
  var item = _mappingValues(dim).find(function (candidate) {
    return String(candidate.value) === String(value);
  });
  return item ? item.label || item.value : value || "人工确认";
}

function _mappingOperatorLabel(operator) {
  return (
    {
      lookup: "按原始值匹配",
      contains_any: "命中任一值",
      first_lookup: "采用首个可识别值",
      ordered_input_lookup: "按 Provider 顺序采用首个命中值",
      certification_lookup: "按国家和分级认证匹配",
    }[operator] || operator
  );
}

function renderProviderMappingSummary(dim, providerType, mapping) {
  var inputCount = (mapping.rules || []).reduce(function (count, rule) {
    return count + (Array.isArray(rule.inputs) ? rule.inputs.length : 0);
  }, 0);
  var unmatched = mapping.unmatched || { action: "review" };
  var unmatchedText =
    unmatched.action === "value"
      ? "未命中归为「" + _mappingTargetLabel(dim, unmatched.target) + "」"
      : "未命中交给人工确认";
  return (
    '<section class="provider-map-summary" aria-label="Provider 维度映射">' +
    '<div class="provider-map-summary-copy">' +
    '<div class="provider-map-kicker">' +
    _escapeHtml(providerType.toUpperCase()) +
    " 映射 · 版本 " +
    _escapeHtml(mapping.schema_version) +
    "</div>" +
    '<strong>' +
    _escapeHtml(mapping.field) +
    " → " +
    _escapeHtml(_mappingOperatorLabel(mapping.operator)) +
    "</strong>" +
    '<small>' +
    inputCount +
    " 个 Provider 原始值 · " +
    _escapeHtml(unmatchedText) +
    "</small>" +
    "</div>" +
    '<button class="btn btn-secondary btn-sm" type="button" data-dimension-action="edit-provider-mapping" data-dimension-name="' +
    _escapeHtml(dim.name) +
    '" data-provider-type="' +
    _escapeHtml(providerType) +
    '">查看与调整映射</button>' +
    "</section>"
  );
}

function _mappingRulesHtml(dim, mapping) {
  var values = _mappingValues(dim);
  if (mapping.operator === "certification_lookup") {
    var countries = {};
    (mapping.rules || []).forEach(function (rule) {
      var country = rule.country || "通用";
      if (!countries[country]) countries[country] = [];
      (rule.inputs || []).forEach(function (input, index) {
        countries[country].push({
          id: rule.id + "-" + index,
          input: input,
          target: rule.target,
        });
      });
    });
    var priority = mapping.country_priority || Object.keys(countries);
    var orderedCountries = priority.concat(
      Object.keys(countries).filter(function (country) {
        return priority.indexOf(country) < 0;
      }),
    );
    return orderedCountries
      .filter(function (country) {
        return countries[country] && countries[country].length;
      })
      .map(function (country, countryIndex) {
        var rows = countries[country]
          .map(function (row) {
            return (
              '<div class="provider-map-rule" data-country="' +
              _escapeHtml(country) +
              '" data-input="' +
              _escapeHtml(row.input) +
              '" data-source-rule="' +
              _escapeHtml(row.id) +
              '">' +
              '<code>' +
              _escapeHtml(row.input) +
              "</code>" +
              '<span aria-hidden="true">归为</span>' +
              _mappingTargetSelect(
                values,
                row.target,
                country + " " + row.input + " 映射值",
              ) +
              "</div>"
            );
          })
          .join("");
        return (
          '<details class="provider-map-country"' +
          (countryIndex === 0 ? " open" : "") +
          ' data-country-group="' +
          _escapeHtml(country) +
          '">' +
          '<summary><span><b>' +
          _escapeHtml(country) +
          "</b><small>" +
          countries[country].length +
          " 个认证值</small></span>" +
          '<span class="provider-map-country-actions"><button type="button" data-map-country-move="up" aria-label="向前调整 ' +
          _escapeHtml(country) +
          '">↑</button><button type="button" data-map-country-move="down" aria-label="向后调整 ' +
          _escapeHtml(country) +
          '">↓</button></span></summary>' +
          '<div class="provider-map-rule-stack">' +
          rows +
          "</div></details>"
        );
      })
      .join("");
  }

  return (mapping.rules || [])
    .map(function (rule) {
      return (rule.inputs || [])
        .map(function (input, index) {
          return (
            '<div class="provider-map-rule" data-input="' +
            _escapeHtml(input) +
            '" data-source-rule="' +
            _escapeHtml(rule.id + "-" + index) +
            '"><code>' +
            _escapeHtml(input) +
            '</code><span aria-hidden="true">归为</span>' +
            _mappingTargetSelect(values, rule.target, input + " 映射值") +
            "</div>"
          );
        })
        .join("");
    })
    .join("");
}

function _providerMappingEditorBody(dim, providerType, mapping) {
  var unmatched = mapping.unmatched || { action: "review" };
  var unmatchedValue = unmatched.action === "value"
    ? "value:" + unmatched.target
    : "review";
  var unmatchedOptions = [
    { value: "review", label: "交给人工确认（推荐）" },
  ].concat(
    _mappingValues(dim).map(function (item) {
      return {
        value: "value:" + item.value,
        label: "统一归为：" + (item.label || item.value),
      };
    }),
  );
  return (
    '<div class="provider-map-editor" data-provider-map-editor>' +
    '<section class="provider-map-explain"><span>' +
    _escapeHtml(providerType.toUpperCase()) +
    " 提供原始值</span><b>" +
    _escapeHtml(mapping.field) +
    '</b><i aria-hidden="true">→</i><span>转成本产品的「' +
    _escapeHtml(dim.label) +
    "」</span></section>" +
    '<div class="provider-map-notice"><b>默认规则已可用</b><span>不熟悉各国分级时无需修改。只有命中的值才会自动归类，其他情况保守地交给人工确认。</span></div>' +
    '<div class="provider-map-meta"><span>匹配方式：' +
    _escapeHtml(_mappingOperatorLabel(mapping.operator)) +
    "</span><span>数据形态：" +
    _escapeHtml(mapping.shape) +
    "</span></div>" +
    '<section class="provider-map-rules"><div class="provider-map-section-title"><div><b>Provider 原始值映射</b><small>点开国家即可调整；上下箭头决定多国数据同时存在时先采用谁。</small></div></div>' +
    '<div data-provider-map-rules>' +
    _mappingRulesHtml(dim, mapping) +
    "</div></section>" +
    '<div class="provider-map-unmatched"><span><b>没有命中任何规则时</b><small>推荐人工确认，避免错分。</small></span>' +
    _mappingSelectHtml(
      unmatchedOptions,
      unmatchedValue,
      "没有命中规则时如何处理",
      "data-map-unmatched",
    ) +
    "</div>" +
    '<section class="provider-map-preview"><div><b>保存前试算</b><small>用内置样例验证映射，不会修改配置。</small></div><button class="btn btn-secondary btn-sm" type="button" data-map-preview>运行样例</button><div class="provider-map-preview-result" data-map-preview-result aria-live="polite">尚未试算</div></section>' +
    '<div class="provider-map-status" data-map-status aria-live="polite"></div>' +
    "</div>"
  );
}

function _collectProviderMappingDraft(overlay) {
  var mapping = JSON.parse(JSON.stringify(_dimensionMappingState.mapping));
  var rules = [];
  overlay.querySelectorAll(".provider-map-rule").forEach(function (row, index) {
    rules.push({
      id: "ui-" + String(index + 1),
      inputs: [row.dataset.input],
      target: row.querySelector("[data-map-select]").dataset.value,
      ...(row.dataset.country ? { country: row.dataset.country } : {}),
    });
  });
  mapping.rules = rules;
  if (mapping.operator === "certification_lookup") {
    mapping.country_priority = Array.from(
      overlay.querySelectorAll("[data-country-group]"),
    ).map(function (item) {
      return item.dataset.countryGroup;
    });
  }
  var unmatched = overlay.querySelector("[data-map-unmatched]").dataset.value;
  mapping.unmatched = unmatched === "review"
    ? { action: "review" }
    : { action: "value", target: unmatched.slice(6) };
  return mapping;
}

function _mappingPreviewPayload(mapping) {
  if (mapping.field === "release_dates") {
    return {
      provider_data: { title: "通天塔", adult: false },
      release_dates: [
        { iso_3166_1: "JP", rating: "PG12", release_dates: [] },
        { iso_3166_1: "US", rating: "R", release_dates: [] },
        { iso_3166_1: "GB", rating: "15", release_dates: [] },
      ],
    };
  }
  if (mapping.field === "adult") return { provider_data: { adult: true } };
  if (mapping.field === "genres") {
    return { provider_data: { genres: [{ id: 99 }, { id: 18 }] } };
  }
  if (mapping.field === "origin_country") {
    return { provider_data: { origin_country: ["CN", "US"] } };
  }
  if (mapping.field === "original_language") {
    return { provider_data: { original_language: "zh" } };
  }
  return { provider_data: {} };
}

function _setMapStatus(overlay, message, tone) {
  var target = overlay.querySelector("[data-map-status]");
  if (!target) return;
  target.className = "provider-map-status" + (tone ? " is-" + tone : "");
  target.textContent = message || "";
}

async function _previewProviderMapping(overlay) {
  var draft = _collectProviderMappingDraft(overlay);
  var resultTarget = overlay.querySelector("[data-map-preview-result]");
  resultTarget.textContent = "正在试算…";
  var payload = _mappingPreviewPayload(draft);
  payload.mapping = draft;
  var result = await apiRequest(
    "POST",
    "/dimensions/" + _dimensionMappingState.dimension.name +
      "/mappings/" + _dimensionMappingState.provider + "/preview",
    payload,
  );
  if (result.code !== 200) {
    resultTarget.textContent = result.message || "试算失败";
    resultTarget.className = "provider-map-preview-result is-error";
    return;
  }
  var evidence = result.data.mapping_evidence || {};
  var targetLabel = result.data.value == null
    ? "人工确认"
    : _mappingTargetLabel(_dimensionMappingState.dimension, result.data.value);
  resultTarget.className = "provider-map-preview-result is-success";
  resultTarget.textContent =
    "样例结果：" + targetLabel +
    (evidence.matched_input
      ? " · 命中 " +
        (evidence.matched_input.country
          ? evidence.matched_input.country + "/" + evidence.matched_input.certification
          : evidence.matched_input)
      : " · 未命中规则");
}

function _moveMappingCountry(overlay, button) {
  var details = button.closest("[data-country-group]");
  if (!details) return;
  if (button.dataset.mapCountryMove === "up" && details.previousElementSibling) {
    details.parentElement.insertBefore(details, details.previousElementSibling);
  }
  if (button.dataset.mapCountryMove === "down" && details.nextElementSibling) {
    details.parentElement.insertBefore(details.nextElementSibling, details);
  }
}

function _closeMappingSelects(overlay, except) {
  overlay.querySelectorAll("[data-map-select].is-open").forEach(function (control) {
    if (control === except) return;
    control.classList.remove("is-open");
    control.classList.remove("opens-up");
    var trigger = control.querySelector(".provider-map-select-trigger");
    var panel = control.querySelector(".provider-map-select-panel");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    if (panel) panel.hidden = true;
  });
}

function _setMappingSelectOpen(overlay, control, open, focusDirection) {
  if (!control) return;
  _closeMappingSelects(overlay, open ? control : null);
  var trigger = control.querySelector(".provider-map-select-trigger");
  var panel = control.querySelector(".provider-map-select-panel");
  control.classList.toggle("is-open", open);
  if (trigger) trigger.setAttribute("aria-expanded", open ? "true" : "false");
  if (panel) panel.hidden = !open;
  control.classList.remove("opens-up");
  if (open && trigger && panel) {
    var boundary = control.closest(".cinema-modal-body") || overlay;
    var boundaryRect = boundary.getBoundingClientRect();
    var triggerRect = trigger.getBoundingClientRect();
    var panelHeight = panel.offsetHeight;
    var spaceBelow = boundaryRect.bottom - triggerRect.bottom;
    var spaceAbove = triggerRect.top - boundaryRect.top;
    if (spaceBelow < panelHeight + 8 && spaceAbove > spaceBelow) {
      control.classList.add("opens-up");
    }
  }
  if (!open || !focusDirection) return;
  var options = Array.from(control.querySelectorAll("[data-map-select-option]"));
  if (!options.length) return;
  var selectedIndex = options.findIndex(function (item) {
    return item.getAttribute("aria-selected") === "true";
  });
  var index = focusDirection === "last"
    ? options.length - 1
    : selectedIndex >= 0 ? selectedIndex : 0;
  options[index].focus();
}

function _chooseMappingSelectOption(overlay, option) {
  var control = option.closest("[data-map-select]");
  if (!control) return;
  control.dataset.value = option.dataset.value;
  control.querySelectorAll("[data-map-select-option]").forEach(function (item) {
    var selected = item === option;
    item.classList.toggle("is-selected", selected);
    item.setAttribute("aria-selected", selected ? "true" : "false");
  });
  var label = control.querySelector("[data-map-select-label]");
  if (label) label.textContent = option.querySelector("span")?.textContent || "";
  _setMappingSelectOpen(overlay, control, false);
  control.querySelector(".provider-map-select-trigger")?.focus();
}

function _handleMappingSelectKeydown(overlay, event) {
  var trigger = event.target.closest(".provider-map-select-trigger");
  if (trigger) {
    var control = trigger.closest("[data-map-select]");
    if (["Enter", " ", "ArrowDown", "ArrowUp"].indexOf(event.key) >= 0) {
      event.preventDefault();
      var shouldOpen = !control.classList.contains("is-open");
      _setMappingSelectOpen(
        overlay,
        control,
        shouldOpen || event.key.indexOf("Arrow") === 0,
        event.key === "ArrowUp" ? "last" : "selected",
      );
    } else if (event.key === "Escape") {
      event.preventDefault();
      _setMappingSelectOpen(overlay, control, false);
    }
    return;
  }
  var option = event.target.closest("[data-map-select-option]");
  if (!option) return;
  var owner = option.closest("[data-map-select]");
  var options = Array.from(owner.querySelectorAll("[data-map-select-option]"));
  var index = options.indexOf(option);
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    _chooseMappingSelectOption(overlay, option);
  } else if (["ArrowDown", "ArrowUp", "Home", "End"].indexOf(event.key) >= 0) {
    event.preventDefault();
    var nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? options.length - 1
        : (index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
    options[nextIndex].focus();
  } else if (event.key === "Escape") {
    event.preventDefault();
    _setMappingSelectOpen(overlay, owner, false);
    owner.querySelector(".provider-map-select-trigger")?.focus();
  }
}

async function openProviderMappingEditor(dimensionName, providerType) {
  var dim = _dimensionsData.find(function (item) {
    return item.name === dimensionName;
  });
  if (!dim) return;
  var result = await apiRequest(
    "GET",
    "/dimensions/" + dimensionName + "/mappings/" + providerType,
  );
  if (result.code !== 200) {
    showToast(result.message || "无法读取 Provider 映射", "error");
    return;
  }
  _dimensionMappingState = {
    dimension: dim,
    provider: providerType,
    mapping: result.data.mapping,
    contentHash: result.data.content_hash,
  };
  var overlay = showAppModal({
    title: dim.label + " · " + providerType.toUpperCase() + " 映射",
    tone: "wide",
    dismissOnBackdrop: false,
    body: _providerMappingEditorBody(dim, providerType, result.data.mapping),
    actions: [
      { label: "取消", className: "btn btn-secondary" },
      {
        label: "保存映射",
        className: "btn btn-primary",
        closeOnClick: false,
        onClick: async function () {
          _setMapStatus(overlay, "正在校验并保存…");
          var saveResult = await apiRequest(
            "PUT",
            "/dimensions/" + dimensionName + "/mappings/" + providerType,
            {
              expected_hash: _dimensionMappingState.contentHash,
              mapping: _collectProviderMappingDraft(overlay),
            },
          );
          if (saveResult.code !== 200) {
            _setMapStatus(
              overlay,
              saveResult.message || "映射未保存，已保留当前填写内容",
              "error",
            );
            return;
          }
          _setMapStatus(overlay, "映射已保存", "success");
          showToast(saveResult.message || "Provider 映射已保存", "success");
          await loadDimensions();
          setTimeout(removeAppModal, 250);
        },
      },
    ],
  });
  overlay.addEventListener("click", function (event) {
    var selectOption = event.target.closest("[data-map-select-option]");
    if (selectOption) {
      _chooseMappingSelectOption(overlay, selectOption);
      return;
    }
    var selectTrigger = event.target.closest(".provider-map-select-trigger");
    if (selectTrigger) {
      var control = selectTrigger.closest("[data-map-select]");
      _setMappingSelectOpen(
        overlay,
        control,
        !control.classList.contains("is-open"),
      );
      return;
    }
    _closeMappingSelects(overlay);
    var preview = event.target.closest("[data-map-preview]");
    if (preview) {
      _previewProviderMapping(overlay);
      return;
    }
    var mover = event.target.closest("[data-map-country-move]");
    if (mover) {
      event.preventDefault();
      event.stopPropagation();
      _moveMappingCountry(overlay, mover);
    }
  });
  overlay.addEventListener("keydown", function (event) {
    _handleMappingSelectKeydown(overlay, event);
  });
}

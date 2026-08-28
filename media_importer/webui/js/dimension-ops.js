// dimension-ops.js - dimension toggle, enable, disable, reset, save
function toggleDimCard(name) {
  if (_expandedDim === name) {
    _expandedDim = null;
  } else {
    _expandedDim = name;
  }
  _openGenrePicker = null;
  _genreAdding = null;
  renderDimensions();
  if (_expandedDim) {
    setTimeout(function () {
      var card = document.getElementById("dim-card-" + name);
      if (card) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 50);
  }
}

async function enableDimension(name) {
  var result = await apiRequest("POST", "/dimensions/" + name + "/enable");
  if (result.code === 200) {
    showToast(result.message || "维度已启用", "success");
    await loadDimensions();
    if (typeof loadEnabledDimensions === "function") {
      await loadEnabledDimensions();
      if (typeof refreshPathRulesDisplay === "function")
        refreshPathRulesDisplay();
    }
  } else {
    showToast(result.message || "启用失败", "error");
  }
}

async function disableDimension(name) {
  if (
    typeof isDimensionUsedInRules === "function" &&
    isDimensionUsedInRules(name)
  ) {
    var dim = _dimensionsData.find(function (d) {
      return d.name === name;
    });
    var dimLabel = dim ? dim.label : name;
    showConfirm(
      "无法禁用",
      "维度「" + dimLabel + "」正在入库规则中使用，请先删除相关规则后再禁用。",
      function () {},
    );
    return;
  }
  var result = await apiRequest("POST", "/dimensions/" + name + "/disable");
  if (result.code === 200) {
    if (_expandedDim === name) _expandedDim = null;
    showToast(result.message || "维度已禁用", "success");
    await loadDimensions();
    if (typeof loadEnabledDimensions === "function") {
      await loadEnabledDimensions();
      if (typeof refreshPathRulesDisplay === "function")
        refreshPathRulesDisplay();
    }
  } else {
    showToast(result.message || "禁用失败", "error");
  }
}

async function resetDimension(name) {
  showConfirm(
    "恢复默认",
    '确定将"' + name + '"的所有映射配置恢复为默认值吗？',
    async function () {
      var result = await apiRequest("POST", "/dimensions/" + name + "/reset");
      if (result.code === 200) {
        showToast(result.message || "已恢复默认配置", "success");
        await loadDimensions();
      } else {
        showToast(result.message || "恢复失败", "error");
      }
    },
  );
}

function _renderLangMapping(valueList) {
  var rows = valueList
    .map(function (v) {
      return (
        '<div class="dim-mapping-row">' +
        '<span class="dim-mapping-value">' +
        _escapeHtml(v.label) +
        "</span>" +
        '<span class="dim-mapping-arrow">←</span>' +
        '<span class="dim-mapping-codes">' +
        _escapeHtml(v.value) +
        "</span>" +
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
    '<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">语言映射基于 ISO 639-1 代码（original_language），无需手动编辑</div>' +
    "</div>"
  );
}

async function saveDimensionEdit(name) {
  var dim = _dimensionsData.find(function (d) {
    return d.name === name;
  });
  if (!dim) return;

  var colorEl = document.getElementById("dim-edit-color");
  var data = {};
  if (colorEl) data.color = colorEl.value;

  var _hasGenreMapping = false;
  if (dim.source_type === "provider") {
    var _pm = dim.provider_mappings;
    if (typeof _pm === "string") {
      try {
        _pm = JSON.parse(_pm);
      } catch (e) {
        _pm = null;
      }
    }
    if (_pm && typeof _pm === "object") {
      for (var _pmKey in _pm) {
        if (_pm[_pmKey] && _pm[_pmKey].field === "genres") {
          _hasGenreMapping = true;
          break;
        }
      }
    }
    if (dim.tmdb_field === "genres") _hasGenreMapping = true;
  }

  if (_hasGenreMapping) {
    data.value_list = _collectGenreMappingData(name);
  } else {
    var mappingData = _collectMappingData();
    var mappingKeys = Object.keys(mappingData);
    if (mappingKeys.length > 0) {
      var origValueList = _parseValueList(dim.value_list);
      var newValueList = origValueList.slice();
      mappingKeys.forEach(function (idxStr) {
        var idx = parseInt(idxStr);
        if (idx < 0 || idx >= newValueList.length) return;
        var row = mappingData[idxStr];
        if (row.tmdb_codes !== undefined) {
          newValueList[idx].tmdb_codes = row.tmdb_codes
            ? row.tmdb_codes
                .split(",")
                .map(function (s) {
                  return s.trim();
                })
                .filter(Boolean)
            : [];
        }
      });
      data.value_list = JSON.stringify(newValueList);
    }
  }

  var result = await apiRequest("PUT", "/dimensions/" + name, data);
  if (result.code === 200) {
    showToast(result.message || "维度配置已更新", "success");
    _openGenrePicker = null;
    await loadDimensions();
  } else {
    showToast(result.message || "保存失败", "error");
  }
}

document.addEventListener("click", function (e) {
  var actionEl = e.target.closest("[data-dimension-action]");
  if (actionEl) {
    e.stopPropagation();
    var action = actionEl.getAttribute("data-dimension-action");
    var dimName =
      actionEl.getAttribute("data-dim-name") ||
      actionEl.getAttribute("data-dimension-name");
    var genreIdx = parseInt(
      actionEl.getAttribute("data-genre-idx") || "-1",
      10,
    );

    if (action === "enable" && dimName) {
      enableDimension(dimName);
      return;
    }
    if (action === "disable" && dimName) {
      disableDimension(dimName);
      return;
    }
    if ((action === "toggle-card" || action === "collapse") && dimName) {
      toggleDimCard(dimName);
      return;
    }
    if (action === "save" && dimName) {
      saveDimensionEdit(dimName);
      return;
    }
    if (action === "reset" && dimName) {
      resetDimension(dimName);
      return;
    }
    if (action === "toggle-genre-help") {
      toggleGenreHelp();
      return;
    }
    if (action === "start-add-genre" && dimName) {
      startAddGenre(dimName);
      return;
    }
    if (action === "cancel-add-genre" && dimName) {
      cancelAddGenre(dimName);
      return;
    }
    if (action === "confirm-add-genre" && dimName) {
      var labelInput = document.getElementById("dim-genre-add-label");
      var valueInput = document.getElementById("dim-genre-add-value");
      var label = labelInput ? labelInput.value.trim() : "";
      var value = valueInput ? valueInput.value.trim() : "";
      if (!label) return;
      if (!value)
        value =
          label
            .toLowerCase()
            .replace(/[\s\u4e00-\u9fff]+/g, "_")
            .replace(/_+/g, "_")
            .replace(/^_|_$/g, "") || label;
      confirmAddGenre(dimName, label, value);
      return;
    }
    if (action === "remove-genre-value" && dimName && genreIdx >= 0) {
      removeGenreValue(dimName, genreIdx);
      return;
    }
    if (action === "toggle-genre-picker" && dimName && genreIdx >= 0) {
      toggleGenrePicker(dimName, genreIdx);
      return;
    }
  }

  if (_openGenrePicker) {
    var picker = document.getElementById(_openGenrePicker);
    if (picker && !picker.parentElement.contains(e.target)) {
      picker.style.display = "none";
      picker.style.left = "";
      picker.style.top = "";
      _openGenrePicker = null;
    }
  }
});

document.addEventListener("dragstart", function (e) {
  var handle = e.target.closest('[data-dimension-action="genre-drag-handle"]');
  if (!handle) return;
  e.stopPropagation();
  var dimName = handle.getAttribute("data-dim-name");
  var genreIdx = parseInt(handle.getAttribute("data-genre-idx") || "-1", 10);
  if (!dimName || genreIdx < 0) return;
  genreDragStart(e, dimName, genreIdx);
});

document.addEventListener("dragend", function (e) {
  var handle = e.target.closest('[data-dimension-action="genre-drag-handle"]');
  if (!handle) return;
  genreDragEnd(e);
});

document.addEventListener("dragover", function (e) {
  var row = e.target.closest(".dim-genre-row");
  if (!row) return;
  genreDragOver(e);
});

document.addEventListener("dragleave", function (e) {
  var row = e.target.closest(".dim-genre-row");
  if (!row) return;
  genreDragLeave(e);
});

document.addEventListener("drop", function (e) {
  var row = e.target.closest(".dim-genre-row");
  if (!row) return;
  var dimName = row.getAttribute("data-dim-name");
  var genreIdx = parseInt(row.getAttribute("data-genre-idx") || "-1", 10);
  if (!dimName || genreIdx < 0) return;
  genreDrop(e, dimName, genreIdx);
});

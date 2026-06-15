// dimension-edit.js - genre drag, add, remove, and mapping
var _genreDragDim = null;
var _genreDragIdx = -1;

function genreDragStart(e, dimName, idx) {
  _genreDragDim = dimName;
  _genreDragIdx = idx;
  e.target.style.opacity = "0.4";
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", dimName + ":" + idx);
  }
}

function genreDragEnd(e) {
  e.target.style.opacity = "1";
  document
    .querySelectorAll(".dim-genre-row.dim-genre-drag-over")
    .forEach(function (el) {
      el.classList.remove("dim-genre-drag-over");
    });
  _genreDragDim = null;
  _genreDragIdx = -1;
}

function genreDragOver(e) {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
  var row = e.target.closest(".dim-genre-row");
  if (row) row.classList.add("dim-genre-drag-over");
}

function genreDragLeave(e) {
  var row = e.target.closest(".dim-genre-row");
  if (row) row.classList.remove("dim-genre-drag-over");
}

function genreDrop(e, dimName, targetIdx) {
  e.preventDefault();
  e.stopPropagation();
  var row = e.target.closest(".dim-genre-row");
  if (row) row.classList.remove("dim-genre-drag-over");
  if (
    !_genreDragDim ||
    _genreDragDim !== dimName ||
    _genreDragIdx === targetIdx
  )
    return;
  if (_genreDragIdx < 0 || targetIdx < 0) return;

  var currentRows = document.querySelectorAll(
    "#dim-genre-rows-" + dimName + " .dim-genre-row",
  );
  var fromRow = document.getElementById(
    "dim-genre-row-" + dimName + "-" + _genreDragIdx,
  );
  var toRow = document.getElementById(
    "dim-genre-row-" + dimName + "-" + targetIdx,
  );
  if (!fromRow || !toRow) return;

  var toIsOther = toRow.querySelector(".dim-genre-priority-other");
  var fromIsOther = fromRow.querySelector(".dim-genre-priority-other");
  if (fromIsOther || toIsOther) return;

  var rowDefs = [];
  currentRows.forEach(function (r) {
    var labelEl = r.querySelector(".dim-genre-label-text");
    var idsAttr = r.getAttribute("data-genre-ids") || "[]";
    var valAttr = r.getAttribute("data-genre-value") || "";
    var isOther = !!r.querySelector(".dim-genre-priority-other");
    var label = labelEl ? labelEl.textContent : "";
    rowDefs.push({
      label: label,
      value: valAttr,
      ids: idsAttr,
      isOther: isOther,
    });
  });

  var fromRowDef = rowDefs[_genreDragIdx];
  if (fromRowDef.isOther) return;

  var nonOther = rowDefs.filter(function (r) {
    return !r.isOther;
  });
  var otherDef = rowDefs.find(function (r) {
    return r.isOther;
  });

  var fromPos = nonOther.indexOf(fromRowDef);
  var toPos = rowDefs.indexOf(rowDefs[targetIdx]);
  var toNonOtherPos = nonOther.indexOf(rowDefs[targetIdx]);
  if (fromPos < 0 || toNonOtherPos < 0) return;

  nonOther.splice(fromPos, 1);
  nonOther.splice(toNonOtherPos, 0, fromRowDef);

  var valueList = [];
  nonOther.forEach(function (r, i) {
    var ids = [];
    try {
      ids = JSON.parse(r.ids);
    } catch (e) {}
    valueList.push({
      value: r.value || r.label.toLowerCase().replace(/\s+/g, "_"),
      label: r.label,
      tmdb_genre_ids: ids,
      priority: i + 1,
    });
  });
  if (otherDef) {
    var oIds = [];
    try {
      oIds = JSON.parse(otherDef.ids);
    } catch (e) {}
    valueList.push({
      value: "other",
      label: otherDef.label,
      tmdb_genre_ids: oIds,
      priority: valueList.length + 1,
    });
  }

  _updateGenreRowsFromData(dimName, valueList);
  _genreDragDim = null;
  _genreDragIdx = -1;
}

function _updateGenreRowsFromData(dimName, valueList) {
  var container = document.getElementById("dim-genre-rows-" + dimName);
  if (!container) return;
  container.innerHTML = _renderGenreRows(dimName, valueList);
}

function startAddGenre(dimName) {
  if (_genreAdding === dimName) return;
  _genreAdding = dimName;

  var addRow = document.getElementById("dim-genre-add-row-" + dimName);
  if (!addRow) return;

  addRow.innerHTML =
    '<div class="dim-genre-row dim-genre-add-row-active" style="display:flex;flex-wrap:wrap;padding:8px;">' +
    '<span class="dim-drag-placeholder"></span>' +
    '<span class="dim-genre-priority" style="color:var(--text-muted);">#</span>' +
    '<div class="dim-genre-add-fields">' +
    '<input type="text" class="dim-genre-add-input-val" id="dim-genre-add-value" placeholder="英文键值，如：music">' +
    '<input type="text" class="dim-genre-add-input" id="dim-genre-add-label" placeholder="中文名称，如：音乐">' +
    "</div>" +
    '<div class="dim-genre-add-btns">' +
    '<button class="dim-genre-add-confirm" type="button" data-dimension-action="confirm-add-genre" data-dim-name="' +
    dimName +
    '">✓</button>' +
    '<button class="dim-genre-remove" type="button" data-dimension-action="cancel-add-genre" data-dim-name="' +
    dimName +
    '" title="取消">×</button>' +
    "</div>" +
    "</div>";

  var labelInput = document.getElementById("dim-genre-add-label");
  var valueInput = document.getElementById("dim-genre-add-value");
  if (!labelInput || !valueInput) return;

  valueInput.focus();

  function doConfirm() {
    var label = labelInput.value.trim();
    var value = valueInput.value.trim();
    if (!label) {
      cancelAddGenre(dimName);
      return;
    }
    if (!value)
      value =
        label
          .toLowerCase()
          .replace(/[\s\u4e00-\u9fff]+/g, "_")
          .replace(/_+/g, "_")
          .replace(/^_|_$/g, "") || label;
    confirmAddGenre(dimName, label, value);
  }

  valueInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      labelInput.focus();
    }
    if (e.key === "Escape") cancelAddGenre(dimName);
  });
  labelInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      doConfirm();
    }
    if (e.key === "Escape") cancelAddGenre(dimName);
  });
  var blurTimer = null;
  valueInput.addEventListener("blur", function () {
    blurTimer = setTimeout(function () {
      if (_genreAdding === dimName) cancelAddGenre(dimName);
    }, 300);
  });
  labelInput.addEventListener("blur", function () {
    blurTimer = setTimeout(function () {
      if (_genreAdding === dimName) cancelAddGenre(dimName);
    }, 300);
  });
  valueInput.addEventListener("focus", function () {
    if (blurTimer) clearTimeout(blurTimer);
  });
  labelInput.addEventListener("focus", function () {
    if (blurTimer) clearTimeout(blurTimer);
  });
}

function confirmAddGenre(dimName, label, value) {
  if (!label || !label.trim()) {
    cancelAddGenre(dimName);
    return;
  }
  label = label.trim();
  if (!value || !value.trim()) {
    cancelAddGenre(dimName);
    return;
  }
  value = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");

  var currentRows = document.querySelectorAll(
    "#dim-genre-rows-" + dimName + " .dim-genre-row",
  );
  var existingLabels = [];
  var existingVals = [];
  currentRows.forEach(function (r) {
    var el = r.querySelector(".dim-genre-label-text");
    if (el) existingLabels.push(el.textContent.toLowerCase());
    var v = r.getAttribute("data-genre-value");
    if (v) existingVals.push(v.toLowerCase());
  });

  if (existingLabels.indexOf(label.toLowerCase()) >= 0) {
    showToast("类型名称已存在: " + label, "error");
    return;
  }
  if (existingVals.indexOf(value) >= 0) {
    showToast("英文键值已存在: " + value, "error");
    return;
  }

  var nonOtherCount = 0;
  var rowDefs = [];
  currentRows.forEach(function (r) {
    var labelEl = r.querySelector(".dim-genre-label-text");
    var idsAttr = r.getAttribute("data-genre-ids") || "[]";
    var valAttr = r.getAttribute("data-genre-value") || "";
    var isOther = !!r.querySelector(".dim-genre-priority-other");
    if (!isOther) nonOtherCount++;
    rowDefs.push({
      label: labelEl ? labelEl.textContent : "",
      value: valAttr,
      ids: idsAttr,
      isOther: isOther,
    });
  });

  var valueList = [];
  rowDefs
    .filter(function (r) {
      return !r.isOther;
    })
    .forEach(function (r, i) {
      var ids = [];
      try {
        ids = JSON.parse(r.ids);
      } catch (e) {}
      valueList.push({
        value: r.value || r.label.toLowerCase().replace(/\s+/g, "_"),
        label: r.label,
        tmdb_genre_ids: ids,
        priority: i + 1,
      });
    });

  var newPriority = valueList.length + 1;
  valueList.push({
    value: value,
    label: label,
    tmdb_genre_ids: [],
    priority: newPriority,
  });

  var otherDef = rowDefs.find(function (r) {
    return r.isOther;
  });
  if (otherDef) {
    var oIds = [];
    try {
      oIds = JSON.parse(otherDef.ids);
    } catch (e) {}
    valueList.push({
      value: "other",
      label: otherDef.label,
      tmdb_genre_ids: oIds,
      priority: valueList.length + 1,
    });
  }

  _genreAdding = null;
  _updateGenreRowsFromData(dimName, valueList);
  _resetAddRowButton(dimName);
}

function cancelAddGenre(dimName) {
  _genreAdding = null;
  _resetAddRowButton(dimName);
}

function _resetAddRowButton(dimName) {
  var addRow = document.getElementById("dim-genre-add-row-" + dimName);
  if (addRow) {
    addRow.innerHTML =
      '<button class="dim-genre-add-btn" type="button" data-dimension-action="start-add-genre" data-dim-name="' +
      dimName +
      '">+ 添加类型值</button>';
  }
}

function removeGenreValue(dimName, idx) {
  var currentRows = document.querySelectorAll(
    "#dim-genre-rows-" + dimName + " .dim-genre-row",
  );
  var rowDefs = [];
  currentRows.forEach(function (r, i) {
    var labelEl = r.querySelector(".dim-genre-label-text");
    var idsAttr = r.getAttribute("data-genre-ids") || "[]";
    var valAttr = r.getAttribute("data-genre-value") || "";
    var isOther = !!r.querySelector(".dim-genre-priority-other");
    rowDefs.push({
      idx: i,
      label: labelEl ? labelEl.textContent : "",
      value: valAttr,
      ids: idsAttr,
      isOther: isOther,
    });
  });

  if (idx >= rowDefs.length) return;
  var target = rowDefs[idx];
  if (target.isOther) return;

  showConfirm(
    "删除类型值",
    '确定删除类型值 "' + target.label + '" 吗？此操作不可撤销。',
    function () {
      var valueList = [];
      rowDefs
        .filter(function (r) {
          return r.idx !== idx && !r.isOther;
        })
        .forEach(function (r, i) {
          var ids = [];
          try {
            ids = JSON.parse(r.ids);
          } catch (e) {}
          valueList.push({
            value: r.value || r.label.toLowerCase().replace(/\s+/g, "_"),
            label: r.label,
            tmdb_genre_ids: ids,
            priority: i + 1,
          });
        });

      var otherDef = rowDefs.find(function (r) {
        return r.isOther;
      });
      if (otherDef) {
        var oIds = [];
        try {
          oIds = JSON.parse(otherDef.ids);
        } catch (e) {}
        valueList.push({
          value: "other",
          label: otherDef.label,
          tmdb_genre_ids: oIds,
          priority: valueList.length + 1,
        });
      }

      _openGenrePicker = null;
      _updateGenreRowsFromData(dimName, valueList);
    },
  );
}

function _generateGenrePrompt() {
  var container = document.getElementById("dim-genre-rows-" + _expandedDim);
  if (!container) return null;

  var parts = [];
  var rows = container.querySelectorAll(".dim-genre-row");
  rows.forEach(function (row) {
    var labelEl = row.querySelector(".dim-genre-label-text");
    var isOther = row.querySelector(".dim-genre-priority-other");
    if (!labelEl || isOther) return;
    var label = labelEl.textContent;
    var value =
      row.getAttribute("data-genre-value") ||
      label.toLowerCase().replace(/\s+/g, "_");
    parts.push(value + "（" + label + "）");
  });

  if (parts.length === 0) return null;

  return (
    "请判断该影视作品的主要类型：" +
    parts.join("、") +
    "、other（其他）。" +
    "如果同时属于多个类型，选择风格最鲜明突出的那个。"
  );
}

function _collectGenreMappingData(dimName) {
  var valueList = [];
  var rows = document.querySelectorAll(
    "#dim-genre-rows-" + dimName + " .dim-genre-row",
  );
  rows.forEach(function (row, posIdx) {
    var labelEl = row.querySelector(".dim-genre-label-text");
    var isOther = row.querySelector(".dim-genre-priority-other");
    var idsAttr = row.getAttribute("data-genre-ids") || "[]";
    var valAttr = row.getAttribute("data-genre-value") || "";

    var label = labelEl ? labelEl.textContent : "";
    var ids = [];
    try {
      ids = JSON.parse(idsAttr);
    } catch (e) {}

    var item = {
      value: isOther
        ? "other"
        : valAttr || label.toLowerCase().replace(/\s+/g, "_"),
      label: label,
      priority: isOther ? 99 : posIdx + 1,
      tmdb_genre_ids: ids,
    };
    valueList.push(item);
  });
  return JSON.stringify(valueList);
}

function _collectMappingData() {
  var inputs = document.querySelectorAll(".dim-mapping-input[data-map-idx]");
  var groups = {};
  inputs.forEach(function (inp) {
    var idx = parseInt(inp.getAttribute("data-map-idx"));
    var field = inp.getAttribute("data-map-field");
    if (!groups[idx]) groups[idx] = {};
    groups[idx][field] = inp.value.trim();
  });
  return groups;
}

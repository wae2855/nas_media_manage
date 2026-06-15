// dimension-genre-picker.js - genre picker UI and toggle
function _renderGenrePickerTrigger(dimName, idx, selectedIds) {
  var displayText = selectedIds.length
    ? selectedIds
        .map(function (id) {
          return _getGenreNameById(id);
        })
        .join(", ")
    : "点击选择 Provider 类型...";

  return (
    '<div class="dim-genre-picker-trigger" data-dimension-action="toggle-genre-picker" data-dim-name="' +
    dimName +
    '" data-genre-idx="' +
    idx +
    '">' +
    '<span class="dim-genre-picker-text">' +
    _escapeHtml(displayText) +
    "</span>" +
    '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>' +
    '<div class="dim-genre-picker-dropdown" id="dim-genre-picker-' +
    dimName +
    "-" +
    idx +
    '" style="display:none;"></div>' +
    "</div>"
  );
}

function _buildGenrePickerContent(idx, selectedIds) {
  var html = "";
  var combined =
    _cachedProviderGenres &&
    _cachedProviderGenres.combined &&
    _cachedProviderGenres.combined.length > 0
      ? _cachedProviderGenres.combined
      : null;

  if (combined) {
    var groups = {};
    combined.forEach(function (g) {
      var grp = g.group || "其他";
      if (!groups[grp]) groups[grp] = [];
      groups[grp].push(g);
    });
    var groupNames = Object.keys(groups);
    groupNames.forEach(function (grpName) {
      html += '<div class="dim-genre-check-group">';
      html +=
        '<div class="dim-genre-check-group-label">' +
        _escapeHtml(grpName) +
        "</div>";
      groups[grpName].forEach(function (g) {
        var checked = selectedIds.indexOf(g.id) >= 0 ? " checked" : "";
        html +=
          '<label class="dim-genre-check-item">' +
          '<input type="checkbox" value="' +
          g.id +
          '"' +
          checked +
          ">" +
          "<span>" +
          _escapeHtml(g.name) +
          "</span></label>";
      });
      html += "</div>";
    });
  } else {
    var fallbackGroups = {
      "动作/冒险": [28, 12, 10759, 37],
      "恐怖/悬疑": [27, 9648, 53, 10758],
      "科幻/奇幻": [878, 14, 10765],
      "战争/军事": [10752, 10768],
      喜剧: [35],
      "剧情/情感": [18, 10749, 80, 36, 10751, 10766, 10770],
      "纪录/纪实": [99],
      动画: [16],
      "音乐/演出": [10402],
      "儿童/家庭": [10762],
      电视节目: [10763, 10764, 10767],
      其他: [10760, 10769],
    };
    var grpNames = Object.keys(fallbackGroups);
    grpNames.forEach(function (grpName) {
      html += '<div class="dim-genre-check-group">';
      html +=
        '<div class="dim-genre-check-group-label">' +
        _escapeHtml(grpName) +
        "</div>";
      fallbackGroups[grpName].forEach(function (id) {
        var name = _FALLBACK_GENRE_MAP[id] || "#" + id;
        var checked = selectedIds.indexOf(id) >= 0 ? " checked" : "";
        html +=
          '<label class="dim-genre-check-item">' +
          '<input type="checkbox" value="' +
          id +
          '"' +
          checked +
          ">" +
          "<span>" +
          _escapeHtml(name) +
          "</span></label>";
      });
      html += "</div>";
    });
  }
  return html;
}

function toggleGenrePicker(dimName, idx) {
  var dropdownId = "dim-genre-picker-" + dimName + "-" + idx;
  var dropdown = document.getElementById(dropdownId);
  if (!dropdown) return;

  if (_openGenrePicker && _openGenrePicker !== dropdownId) {
    var prev = document.getElementById(_openGenrePicker);
    if (prev) {
      prev.style.display = "none";
      prev.style.left = "";
      prev.style.top = "";
    }
  }

  if (dropdown.style.display === "block") {
    dropdown.style.display = "none";
    dropdown.style.left = "";
    dropdown.style.top = "";
    _openGenrePicker = null;
    return;
  }

  var row = document.getElementById("dim-genre-row-" + dimName + "-" + idx);
  var idsJson = row ? row.getAttribute("data-genre-ids") : "[]";
  var selectedIds = [];
  try {
    selectedIds = JSON.parse(idsJson);
  } catch (e) {}

  dropdown.innerHTML = _buildGenrePickerContent(idx, selectedIds);

  var trigger = row ? row.querySelector(".dim-genre-picker-trigger") : null;
  if (trigger) {
    var rect = trigger.getBoundingClientRect();
    var dropdownH = 370;
    var spaceBelow = window.innerHeight - rect.bottom;
    dropdown.style.left = rect.left + "px";
    dropdown.style.width = Math.max(280, rect.width) + "px";
    if (spaceBelow >= dropdownH || rect.top < dropdownH) {
      dropdown.style.top = rect.bottom + 4 + "px";
    } else {
      dropdown.style.top = rect.top - dropdownH - 4 + "px";
    }
  }

  dropdown.style.display = "block";
  _openGenrePicker = dropdownId;

  dropdown
    .querySelectorAll(".dim-genre-check-item input")
    .forEach(function (cb) {
      cb.addEventListener("change", function () {
        var allChecked = dropdown.querySelectorAll(
          ".dim-genre-check-item input:checked",
        );
        var newIds = [];
        allChecked.forEach(function (c) {
          newIds.push(parseInt(c.value));
        });
        if (row) row.setAttribute("data-genre-ids", JSON.stringify(newIds));

        var textEl = trigger
          ? trigger.querySelector(".dim-genre-picker-text")
          : null;
        var previewEl = row
          ? row.querySelector(".dim-genre-names-preview")
          : null;
        if (textEl) {
          textEl.textContent = newIds.length
            ? newIds
                .map(function (id) {
                  return _getGenreNameById(id);
                })
                .join(", ")
            : "点击选择 Provider 类型...";
        }
        if (previewEl) {
          previewEl.textContent = newIds.length
            ? _genreIdToLabel(newIds.slice(0, 4)) +
              (newIds.length > 4 ? " +" + (newIds.length - 4) : "")
            : "-";
        }
      });
    });
}

function toggleGenreHelp() {
  var panel = document.getElementById("dim-genre-help");
  if (panel)
    panel.style.display = panel.style.display === "none" ? "block" : "none";
}


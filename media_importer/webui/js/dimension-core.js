// dimension-core.js - dimension state, core loading and rendering
var _dimensionsData = [];
var _expandedDim = null;
var _openGenrePicker = null;
var _genreAdding = null;
var _cachedProviderGenres = null;

// 内置维度业务名兜底：维度接口未加载时（如任务列表直出）也能显示中文业务名，
// 接口加载后由 _dimensionsData 的正式定义覆盖。
var DIM_LABEL_FALLBACK = {
  media_type: "影视类型",
  animation: "是否动漫",
  documentary: "是否纪录片",
  restricted_level: "观看分级",
  content_sensitivity: "成人电影标记",
  region: "地区",
  origin_lang: "原始语言",
  broad_genre: "题材类型",
  season: "季数",
  episode: "集数",
};

// 统一的维度业务名解析：接口定义优先，内置兜底次之，最后返回原名
function dimLabelOf(name) {
  var defs = (_dimensionsData || []).concat(
    window.currentEnabledDimensions || [],
  );
  for (var i = 0; i < defs.length; i++) {
    if (defs[i] && defs[i].name === name) return defs[i].label || name;
  }
  return DIM_LABEL_FALLBACK[name] || name;
}

// 维度业务色解析（用于标签左边框着色）
function dimColorOf(name) {
  var defs = (_dimensionsData || []).concat(
    window.currentEnabledDimensions || [],
  );
  for (var i = 0; i < defs.length; i++) {
    if (defs[i] && defs[i].name === name && defs[i].color) return defs[i].color;
  }
  return "rgba(234,191,99,0.35)";
}

// 按需补载维度定义（任务列表等页面直出时调用一次）
var _dimDefsLoading = false;
function ensureDimDefsLoaded() {
  if (_dimensionsData.length || _dimDefsLoading) return;
  _dimDefsLoading = true;
  apiRequest("GET", "/dimensions")
    .then(function (result) {
      if (result.code === 200 && result.data) {
        _dimensionsData = result.data.dimensions || [];
        // 通知已渲染的页面（任务列表等）用正式维度定义重渲
        window.dispatchEvent(new CustomEvent("dim-defs-loaded"));
      }
    })
    .catch(function () {})
    .finally(function () {
      _dimDefsLoading = false;
    });
}

var _FALLBACK_GENRE_MAP = {
  28: "动作 (Action)",
  12: "冒险 (Adventure)",
  16: "动画 (Animation)",
  35: "喜剧 (Comedy)",
  80: "犯罪 (Crime)",
  99: "纪录片 (Documentary)",
  18: "剧情 (Drama)",
  14: "奇幻 (Fantasy)",
  36: "历史 (History)",
  10402: "音乐 (Music)",
  878: "科幻 (Science Fiction)",
  10749: "爱情 (Romance)",
  53: "惊悚 (Thriller)",
  10752: "战争 (War)",
  37: "西部 (Western)",
  27: "恐怖 (Horror)",
  9648: "悬疑 (Mystery)",
  10759: "动作冒险 (Action & Adventure)",
  10765: "科幻/奇幻 (Sci-Fi & Fantasy)",
  10766: "肥皂剧 (Soap)",
  10768: "战争政治 (War & Politics)",
  10758: "恐怖/悬疑 (Horror & Suspense)",
  10762: "儿童 (Kids)",
  10763: "新闻 (News)",
  10764: "真人秀 (Reality)",
  10767: "脱口秀 (Talk)",
  10760: "短剧 (Mini-Series)",
  10769: "海外剧 (Foreign)",
  10770: "电视电影 (TV Movie)",
  10751: "家庭 (Family)",
};

function _escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function _parseValueList(raw) {
  if (Array.isArray(raw)) return raw;
  if (typeof raw === "string") {
    try {
      var p = JSON.parse(raw);
      if (Array.isArray(p)) return p;
    } catch (e) {}
  }
  return [];
}

function _genreIdToLabel(ids) {
  return (ids || [])
    .map(function (id) {
      return _getGenreNameById(id);
    })
    .join(", ");
}

function _getGenreNameById(id) {
  if (
    _cachedProviderGenres &&
    _cachedProviderGenres._idMap &&
    _cachedProviderGenres._idMap[id]
  ) {
    return _cachedProviderGenres._idMap[id];
  }
  if (_FALLBACK_GENRE_MAP[id]) {
    return _FALLBACK_GENRE_MAP[id];
  }
  return "#" + id;
}

async function loadProviderGenres(providerType) {
  providerType = providerType || "tmdb";
  if (
    _cachedProviderGenres &&
    _cachedProviderGenres._loaded &&
    _cachedProviderGenres._providerType === providerType
  )
    return _cachedProviderGenres;
  try {
    var result = await apiRequest(
      "GET",
      "/providers/" + providerType + "/genres",
    );
    if (result.code === 200 && result.data) {
      _cachedProviderGenres = result.data;
      _cachedProviderGenres._idMap = {};
      _cachedProviderGenres._loaded = true;
      _cachedProviderGenres._providerType = providerType;
      (_cachedProviderGenres.combined || []).forEach(function (g) {
        _cachedProviderGenres._idMap[g.id] = g.name;
      });
      return _cachedProviderGenres;
    }
  } catch (e) {
    console.warn("loadProviderGenres failed:", e);
  }
  _cachedProviderGenres = {
    movie: [],
    tv: [],
    combined: [],
    _idMap: {},
    _loaded: false,
    _providerType: providerType,
  };
  return _cachedProviderGenres;
}

function _startBackgroundGenreLoad() {
  if (_cachedProviderGenres && _cachedProviderGenres._loaded) return;
  loadProviderGenres().then(function () {
    _refreshGenreDisplay();
  });
}

function _refreshGenreDisplay() {
  document.querySelectorAll(".dim-genre-picker-text").forEach(function (el) {
    var trigger = el.closest(".dim-genre-picker-trigger");
    if (!trigger) return;
    var input = trigger.parentElement.querySelector("input[type=hidden]");
    if (!input) return;
    var ids = (input.value || "").split(",").filter(Boolean).map(Number);
    el.textContent = ids.length
      ? ids
          .map(function (id) {
            return _getGenreNameById(id);
          })
          .join(", ")
      : "点击选择 Provider 类型...";
  });
}

function getSourceLabel(sourceType) {
  var labels = {
    provider: "Provider 映射",
    file: "文件推导",
    // 兼容旧数据（migration 前的历史显示）
    ai: "历史 AI 判断",
    "ai+provider": "Provider 映射（历史 AI 配置）",
    "ai+provider": "Provider 映射",
  };
  return labels[sourceType] || sourceType;
}

var _dimensionsData = [];
var _expandedDim = null;
var _openGenrePicker = null;
var _genreAdding = null;
var _cachedProviderGenres = null;

var _FALLBACK_GENRE_MAP = {
    28: '动作 (Action)', 12: '冒险 (Adventure)', 16: '动画 (Animation)',
    35: '喜剧 (Comedy)', 80: '犯罪 (Crime)', 99: '纪录片 (Documentary)',
    18: '剧情 (Drama)', 14: '奇幻 (Fantasy)', 36: '历史 (History)',
    10402: '音乐 (Music)', 878: '科幻 (Science Fiction)', 10749: '爱情 (Romance)',
    53: '惊悚 (Thriller)', 10752: '战争 (War)', 37: '西部 (Western)',
    27: '恐怖 (Horror)', 9648: '悬疑 (Mystery)',
    10759: '动作冒险 (Action & Adventure)', 10765: '科幻/奇幻 (Sci-Fi & Fantasy)',
    10766: '肥皂剧 (Soap)', 10768: '战争政治 (War & Politics)',
    10758: '恐怖/悬疑 (Horror & Suspense)',
    10762: '儿童 (Kids)', 10763: '新闻 (News)', 10764: '真人秀 (Reality)',
    10767: '脱口秀 (Talk)', 10760: '短剧 (Mini-Series)',
    10769: '海外剧 (Foreign)', 10770: '电视电影 (TV Movie)', 10751: '家庭 (Family)',
};

function _escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function _parseValueList(raw) {
    if (Array.isArray(raw)) return raw;
    if (typeof raw === 'string') {
        try { var p = JSON.parse(raw); if (Array.isArray(p)) return p; } catch(e) {}
    }
    return [];
}

function _genreIdToLabel(ids) {
    return (ids || []).map(function(id) {
        return _getGenreNameById(id);
    }).join(', ');
}

function _getGenreNameById(id) {
    if (_cachedProviderGenres && _cachedProviderGenres._idMap && _cachedProviderGenres._idMap[id]) {
        return _cachedProviderGenres._idMap[id];
    }
    if (_FALLBACK_GENRE_MAP[id]) {
        return _FALLBACK_GENRE_MAP[id];
    }
    return '#' + id;
}

async function loadProviderGenres(providerType) {
    providerType = providerType || 'tmdb';
    if (_cachedProviderGenres && _cachedProviderGenres._loaded && _cachedProviderGenres._providerType === providerType) return _cachedProviderGenres;
    try {
        var result = await apiRequest('GET', '/providers/' + providerType + '/genres');
        if (result.code === 200 && result.data) {
            _cachedProviderGenres = result.data;
            _cachedProviderGenres._idMap = {};
            _cachedProviderGenres._loaded = true;
            _cachedProviderGenres._providerType = providerType;
            (_cachedProviderGenres.combined || []).forEach(function(g) {
                _cachedProviderGenres._idMap[g.id] = g.name;
            });
            return _cachedProviderGenres;
        }
    } catch(e) {
        console.warn('loadProviderGenres failed:', e);
    }
    _cachedProviderGenres = { movie: [], tv: [], combined: [], _idMap: {}, _loaded: false, _providerType: providerType };
    return _cachedProviderGenres;
}

function _startBackgroundGenreLoad() {
    if (_cachedProviderGenres && _cachedProviderGenres._loaded) return;
    loadProviderGenres().then(function() {
        _refreshGenreDisplay();
    });
}

function _refreshGenreDisplay() {
    document.querySelectorAll('.dim-genre-picker-text').forEach(function(el) {
        var trigger = el.closest('.dim-genre-picker-trigger');
        if (!trigger) return;
        var input = trigger.parentElement.querySelector('input[type=hidden]');
        if (!input) return;
        var ids = (input.value || '').split(',').filter(Boolean).map(Number);
        el.textContent = ids.length
            ? ids.map(function(id) { return _getGenreNameById(id); }).join(', ')
            : '点击选择 Provider 类型...';
    });
}

function getSourceLabel(sourceType) {
    var labels = {'ai': 'AI 判断', 'ai+provider': 'AI + Provider', 'file': '文件推导'};
    return labels[sourceType] || sourceType;
}

async function loadDimensions() {
    _startBackgroundGenreLoad();
    var result = await apiRequest('GET', '/dimensions');
    if (result.code === 200 && result.data) {
        _dimensionsData = result.data.dimensions || [];
    } else {
        _dimensionsData = [];
    }
    renderDimensions();
}

function renderDimensions() {
    var enabledList = document.getElementById('dim-enabled-list');
    var availableList = document.getElementById('dim-available-list');
    if (!enabledList || !availableList) return;

    var enabled = _dimensionsData.filter(function(d) { return d.is_enabled; });
    var available = _dimensionsData.filter(function(d) { return !d.is_enabled; });

    enabledList.innerHTML = enabled.length
        ? enabled.map(function(d) { return _renderDimCard(d, true); }).join('')
        : '<div class="dim-empty">暂无已启用维度</div>';

    availableList.innerHTML = available.length
        ? available.map(function(d) { return _renderDimCard(d, false); }).join('')
        : '<div class="dim-empty">所有维度均已启用</div>';
}

function _renderDimCard(dim, isEnabled) {
    var sourceLabel = getSourceLabel(dim.source_type);
    var isExpanded = _expandedDim === dim.name;
    var expandedClass = isExpanded ? ' dim-card-expanded' : '';

    var tierHtml = '';
    if (dim.required_tier === 'pro') {
        tierHtml = '<span class="dim-card-tier dim-card-tier-pro">PRO</span>';
    } else if (dim.required_tier === 'premium') {
        tierHtml = '<span class="dim-card-tier dim-card-tier-premium">PREMIUM</span>';
    }

    var barActionsHtml = isEnabled
        ? '<button class="dim-btn-disable" type="button" data-dimension-action="disable" data-dimension-name="' + dim.name + '">禁用</button>'
        : '<button class="dim-btn-enable" type="button" data-dimension-action="enable" data-dimension-name="' + dim.name + '">启用</button>';

    var bodyHtml = isExpanded ? _renderDimBody(dim) : '';

    return '<div class="dim-card' + expandedClass + '" id="dim-card-' + dim.name + '">' +
        '<div class="dim-card-bar" data-dimension-action="toggle-card" data-dimension-name="' + dim.name + '">' +
            '<span class="dim-card-color-dot" style="background:' + dim.color + '"></span>' +
            '<span class="dim-card-name">' + _escapeHtml(dim.label) + '</span>' +
            '<span class="dim-card-source">' + _escapeHtml(sourceLabel) + '</span>' +
            tierHtml +
            '<span class="dim-card-desc">' + _escapeHtml(dim.description || '') + '</span>' +
            '<div class="dim-card-bar-actions">' + barActionsHtml + '</div>' +
            '<svg class="dim-card-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>' +
        '</div>' +
        '<div class="dim-card-body"><div class="dim-card-body-inner">' + bodyHtml + '</div></div>' +
    '</div>';
}

function _renderDimBody(dim) {
    try {
        var valueList = _parseValueList(dim.value_list);
        var sourceLabel = getSourceLabel(dim.source_type);

        var valuesHtml = valueList.map(function(v) {
            return '<span class="dim-value-tag">' + _escapeHtml(v.label || v.value) + '</span>';
        }).join('');

        var mappingHtml = '';
        var hasGenreMapping = false;
        var hasRegionMapping = false;
        var hasLangMapping = false;
        if (dim.source_type === 'ai+provider') {
            var pm = dim.provider_mappings;
            if (typeof pm === 'string') { try { pm = JSON.parse(pm); } catch(e) { pm = null; } }
            if (pm && typeof pm === 'object') {
                for (var pmKey in pm) {
                    if (pm[pmKey] && pm[pmKey].field === 'genres') hasGenreMapping = true;
                    if (pm[pmKey] && pm[pmKey].field === 'origin_country') hasRegionMapping = true;
                    if (pm[pmKey] && pm[pmKey].field === 'original_language') hasLangMapping = true;
                }
            }
            if (dim.tmdb_field === 'genres') hasGenreMapping = true;
            if (dim.tmdb_field === 'origin_country') hasRegionMapping = true;
            if (dim.tmdb_field === 'original_language') hasLangMapping = true;
        }

        if (dim.source_type === 'ai+provider' && hasGenreMapping && dim.name !== 'documentary' && dim.name !== 'animation') {
            mappingHtml = _renderGenreEditable(dim.name, valueList);
        } else if (dim.source_type === 'ai+provider') {
            if (hasRegionMapping) mappingHtml = _renderRegionMapping(valueList);
            else if (hasLangMapping) mappingHtml = _renderLangMapping(valueList);
        }

        var autoRuleHtml = '';
        if (dim.name === 'documentary') {
            autoRuleHtml = '<div class="dim-auto-rule-info">' +
                '<div class="dim-auto-rule-title">⚙ 自动判定规则</div>' +
                '<div class="dim-auto-rule-desc">从 Provider 获取影视的 genres 列表，若包含 <strong>Genre(99) = Documentary</strong> 则判定为纪录片（true），否则为非纪录片（false）。无需手动配置映射。</div>' +
            '</div>';
        } else if (dim.name === 'animation') {
            autoRuleHtml = '<div class="dim-auto-rule-info">' +
                '<div class="dim-auto-rule-title">⚙ 自动判定规则</div>' +
                '<div class="dim-auto-rule-desc">从 Provider 获取影视的 genres 列表，若包含 <strong>Genre(16) = Animation</strong> 则判定为动漫（true），否则不做判定。无需手动配置映射。</div>' +
            '</div>';
        } else if (dim.name === 'restricted_level') {
            autoRuleHtml = '<div class="dim-auto-rule-info">' +
                '<div class="dim-auto-rule-title">⚙ 自动判定规则</div>' +
                '<div class="dim-auto-rule-desc">从 Provider 获取 <strong>release_dates</strong> 字段中的分级认证（certification），按国家优先级（US → GB → 其他）匹配 MPAA 分级标准映射到年龄区间：G/U → 0-6、PG → 7-12、PG-13/12A → 13-16、R/NC-17 → 17+。若 Provider 无分级数据，则由 AI 根据内容辅助判断。</div>' +
            '</div>';
        }

        var aiPromptHtml = '';
        if (dim.source_type !== 'file') {
            aiPromptHtml = '<div class="dim-edit-field">' +
                '<label class="dim-edit-label">AI 提示词 <span style="font-weight:400;color:var(--text-muted);">（保存时自动生成）</span></label>' +
                '<textarea id="dim-edit-ai-prompt" class="form-textarea" rows="3">' + _escapeHtml(dim.ai_prompt || '') + '</textarea>' +
            '</div>';
        }

        return '<div class="dim-card-body-content">' +
            '<div class="dim-edit-row">' +
                '<span class="dim-edit-label">标识</span>' +
                '<span class="dim-edit-value" style="font-family:ui-monospace,monospace;font-size:12px;color:var(--text-muted);">' + _escapeHtml(dim.name) + '</span>' +
            '</div>' +
            '<div class="dim-edit-row">' +
                '<span class="dim-edit-label">来源</span>' +
                '<span class="dim-edit-value">' + _escapeHtml(sourceLabel) + '</span>' +
            '</div>' +
            '<div class="dim-edit-row">' +
                '<span class="dim-edit-label">颜色</span>' +
                '<input type="color" id="dim-edit-color" value="' + dim.color + '" class="dim-color-picker">' +
            '</div>' +
            aiPromptHtml +
            '<div class="dim-edit-row">' +
                '<span class="dim-edit-label">值域</span>' +
                '<div class="dim-value-tags">' + valuesHtml + '</div>' +
            '</div>' +
            mappingHtml +
            autoRuleHtml +
            '<div class="dim-edit-actions">' +
                '<button class="btn btn-primary btn-sm" type="button" data-dimension-action="save" data-dimension-name="' + dim.name + '">保存</button>' +
                (hasGenreMapping && dim.name !== 'documentary' && dim.name !== 'animation' ? '<button class="btn btn-warning btn-sm" type="button" data-dimension-action="reset" data-dimension-name="' + dim.name + '">恢复默认</button>' : '') +
                '<button class="btn btn-secondary btn-sm" type="button" data-dimension-action="collapse" data-dimension-name="' + dim.name + '">收起</button>' +
            '</div>' +
        '</div>';
    } catch(e) {
        console.error('_renderDimBody error:', e);
        return '<div class="dim-card-body-content"><div style="color:var(--danger-color);font-size:13px;">渲染出错: ' + _escapeHtml(e.message) + '</div></div>';
    }
}

function _renderRegionMapping(valueList) {
    var rows = valueList.map(function(v) {
        var codes = (v.tmdb_codes || []).join(', ');
        var isOther = v.value === 'other';
        var codeDisplay = isOther
            ? '<span style="font-size:12px;color:var(--text-muted);">兜底匹配</span>'
            : '<span class="dim-mapping-codes">' + _escapeHtml(codes) + '</span>';

        return '<div class="dim-mapping-row">' +
            '<span class="dim-mapping-value">' + _escapeHtml(v.label) + '</span>' +
            '<span class="dim-mapping-arrow">←</span>' +
            codeDisplay +
        '</div>';
    }).join('');

    return '<div class="dim-mapping-section">' +
        '<div class="dim-mapping-header-row">' +
            '<span class="dim-mapping-col-label">入库标签值</span>' +
            '<span class="dim-mapping-col-label">Provider获取值</span>' +
        '</div>' +
        rows +
        '<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">地区映射基于 ISO 3166-1 代码（origin_country），无需手动编辑</div>' +
    '</div>';
}

function _renderGenreRowHTML(dimName, item, origIdx, displayOrderNum) {
    var isOther = item.value === 'other';
    var ids = item.tmdb_genre_ids || [];
    var idsJson = JSON.stringify(ids);
    var genreNames = ids.length ? _genreIdToLabel(ids.slice(0, 4)) + (ids.length > 4 ? ' +' + (ids.length - 4) : '') : '-';

    var dragHandleHtml = isOther
        ? '<span class="dim-drag-placeholder"></span>'
        : '<span class="dim-drag-handle" draggable="true" data-dimension-action="genre-drag-handle" data-dim-name="' + dimName + '" data-genre-idx="' + origIdx + '"></span>';

    var priorityHtml = isOther
        ? '<span class="dim-genre-priority dim-genre-priority-other">-</span>'
        : '<span class="dim-genre-priority">' + displayOrderNum + '</span>';

    var genrePickerHtml = isOther
        ? '<span style="font-size:12px;color:var(--text-muted);">所有未匹配的类型</span>'
        : _renderGenrePickerTrigger(dimName, origIdx, ids);

    var deleteHtml = isOther
        ? ''
        : '<button class="dim-genre-remove" type="button" data-dimension-action="remove-genre-value" data-dim-name="' + dimName + '" data-genre-idx="' + origIdx + '" title="删除此类型值">×</button>';

    return '<tr class="dim-genre-row" id="dim-genre-row-' + dimName + '-' + origIdx + '"' +
        ' data-dim-name="' + dimName + '"' +
        ' data-genre-idx="' + origIdx + '"' +
        ' data-genre-value="' + _escapeHtml(item.value) + '"' +
        ' data-genre-ids=\'' + idsJson + '\'>' +
        '<td class="dim-genre-td-drag">' + dragHandleHtml + '</td>' +
        '<td class="dim-genre-td-priority">' + priorityHtml + '</td>' +
        '<td class="dim-genre-td-label"><span class="dim-genre-label-text">' + _escapeHtml(item.label) + '</span></td>' +
        '<td class="dim-genre-td-picker">' + genrePickerHtml + '</td>' +
        '<td class="dim-genre-td-preview"><span class="dim-genre-names-preview">' + _escapeHtml(genreNames) + '</span></td>' +
        '<td class="dim-genre-td-action">' + deleteHtml + '</td>' +
    '</tr>';
}

function _renderGenreRows(dimName, valueList) {
    var withIdx = valueList.map(function(v, i) { return { item: v, origIdx: i }; });
    withIdx.sort(function(a, b) { return (a.item.priority || 99) - (b.item.priority || 99); });

    return withIdx.map(function(wi, sortedPos) {
        return _renderGenreRowHTML(dimName, wi.item, wi.origIdx, sortedPos + 1);
    }).join('');
}

function _renderGenreEditable(dimName, valueList) {
    return '<div class="dim-mapping-section dim-genre-section">' +
        '<div class="dim-mapping-header">' +
            '<div style="display:flex;align-items:center;gap:6px;">' +
                '<h5>类型映射规则</h5>' +
                '<span class="dim-help-trigger" data-dimension-action="toggle-genre-help" title="映射说明">?</span>' +
            '</div>' +
            '<span class="dim-mapping-hint">每行定义一个题材类型，选择它包含的 Provider 原始类型；拖拽 ≡ 调整优先级</span>' +
        '</div>' +
        '<div class="dim-help-panel" id="dim-genre-help" style="display:none;">' +
            '<div class="dim-help-content">' +
                '<strong>这是什么？</strong>' +
                '<p>系统从 Provider 获取影视的原始类型标签（如"恐怖""喜剧"），<br>' +
                '通过这张映射表归并为你自定义的大类（如"恐怖/悬疑""剧情/情感"）。</p>' +
                '<p><strong>优先级：</strong>一部影视可能同时匹配多个大类，排在前面的优先。<br>' +
                '<strong>举例：</strong>《僵尸肖恩》同时是恐怖和喜剧，若"恐怖/悬疑"排在前面则归入该类。</p>' +
            '</div>' +
        '</div>' +
        '<table class="dim-genre-table">' +
            '<thead class="dim-genre-thead">' +
                '<tr>' +
                    '<th class="dim-genre-th-drag"></th>' +
                    '<th class="dim-genre-th-priority"></th>' +
                    '<th class="dim-genre-th-label">入库标签值</th>' +
                    '<th class="dim-genre-th-picker">Provider影视分类</th>' +
                    '<th class="dim-genre-th-preview">预览</th>' +
                    '<th class="dim-genre-th-action"></th>' +
                '</tr>' +
            '</thead>' +
            '<tbody class="dim-genre-rows" id="dim-genre-rows-' + dimName + '">' + _renderGenreRows(dimName, valueList) + '</tbody>' +
        '</table>' +
        '<div class="dim-genre-add-row" id="dim-genre-add-row-' + dimName + '">' +
            '<button class="dim-genre-add-btn" type="button" data-dimension-action="start-add-genre" data-dim-name="' + dimName + '">+ 添加类型值</button>' +
        '</div>' +
    '</div>';
}

function _renderGenrePickerTrigger(dimName, idx, selectedIds) {
    var displayText = selectedIds.length
        ? selectedIds.map(function(id) { return _getGenreNameById(id); }).join(', ')
        : '点击选择 Provider 类型...';

    return '<div class="dim-genre-picker-trigger" data-dimension-action="toggle-genre-picker" data-dim-name="' + dimName + '" data-genre-idx="' + idx + '">' +
        '<span class="dim-genre-picker-text">' + _escapeHtml(displayText) + '</span>' +
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>' +
        '<div class="dim-genre-picker-dropdown" id="dim-genre-picker-' + dimName + '-' + idx + '" style="display:none;"></div>' +
    '</div>';
}

function _buildGenrePickerContent(idx, selectedIds) {
    var html = '';
    var combined = (_cachedProviderGenres && _cachedProviderGenres.combined && _cachedProviderGenres.combined.length > 0)
        ? _cachedProviderGenres.combined
        : null;

    if (combined) {
        var groups = {};
        combined.forEach(function(g) {
            var grp = g.group || '其他';
            if (!groups[grp]) groups[grp] = [];
            groups[grp].push(g);
        });
        var groupNames = Object.keys(groups);
        groupNames.forEach(function(grpName) {
            html += '<div class="dim-genre-check-group">';
            html += '<div class="dim-genre-check-group-label">' + _escapeHtml(grpName) + '</div>';
            groups[grpName].forEach(function(g) {
                var checked = selectedIds.indexOf(g.id) >= 0 ? ' checked' : '';
                html += '<label class="dim-genre-check-item">' +
                    '<input type="checkbox" value="' + g.id + '"' + checked + '>' +
                    '<span>' + _escapeHtml(g.name) + '</span></label>';
            });
            html += '</div>';
        });
    } else {
        var fallbackGroups = {
            '动作/冒险': [28, 12, 10759, 37],
            '恐怖/悬疑': [27, 9648, 53, 10758],
            '科幻/奇幻': [878, 14, 10765],
            '战争/军事': [10752, 10768],
            '喜剧': [35],
            '剧情/情感': [18, 10749, 80, 36, 10751, 10766, 10770],
            '纪录/纪实': [99],
            '动画': [16],
            '音乐/演出': [10402],
            '儿童/家庭': [10762],
            '电视节目': [10763, 10764, 10767],
            '其他': [10760, 10769],
        };
        var grpNames = Object.keys(fallbackGroups);
        grpNames.forEach(function(grpName) {
            html += '<div class="dim-genre-check-group">';
            html += '<div class="dim-genre-check-group-label">' + _escapeHtml(grpName) + '</div>';
            fallbackGroups[grpName].forEach(function(id) {
                var name = _FALLBACK_GENRE_MAP[id] || ('#' + id);
                var checked = selectedIds.indexOf(id) >= 0 ? ' checked' : '';
                html += '<label class="dim-genre-check-item">' +
                    '<input type="checkbox" value="' + id + '"' + checked + '>' +
                    '<span>' + _escapeHtml(name) + '</span></label>';
            });
            html += '</div>';
        });
    }
    return html;
}

function toggleGenrePicker(dimName, idx) {
    var dropdownId = 'dim-genre-picker-' + dimName + '-' + idx;
    var dropdown = document.getElementById(dropdownId);
    if (!dropdown) return;

    if (_openGenrePicker && _openGenrePicker !== dropdownId) {
        var prev = document.getElementById(_openGenrePicker);
        if (prev) { prev.style.display = 'none'; prev.style.left = ''; prev.style.top = ''; }
    }

    if (dropdown.style.display === 'block') {
        dropdown.style.display = 'none';
        dropdown.style.left = ''; dropdown.style.top = '';
        _openGenrePicker = null;
        return;
    }

    var row = document.getElementById('dim-genre-row-' + dimName + '-' + idx);
    var idsJson = row ? row.getAttribute('data-genre-ids') : '[]';
    var selectedIds = [];
    try { selectedIds = JSON.parse(idsJson); } catch(e) {}

    dropdown.innerHTML = _buildGenrePickerContent(idx, selectedIds);

    var trigger = row ? row.querySelector('.dim-genre-picker-trigger') : null;
    if (trigger) {
        var rect = trigger.getBoundingClientRect();
        var dropdownH = 370;
        var spaceBelow = window.innerHeight - rect.bottom;
        dropdown.style.left = rect.left + 'px';
        dropdown.style.width = Math.max(280, rect.width) + 'px';
        if (spaceBelow >= dropdownH || rect.top < dropdownH) {
            dropdown.style.top = rect.bottom + 4 + 'px';
        } else {
            dropdown.style.top = (rect.top - dropdownH - 4) + 'px';
        }
    }

    dropdown.style.display = 'block';
    _openGenrePicker = dropdownId;

    dropdown.querySelectorAll('.dim-genre-check-item input').forEach(function(cb) {
        cb.addEventListener('change', function() {
            var allChecked = dropdown.querySelectorAll('.dim-genre-check-item input:checked');
            var newIds = [];
            allChecked.forEach(function(c) { newIds.push(parseInt(c.value)); });
            if (row) row.setAttribute('data-genre-ids', JSON.stringify(newIds));

            var textEl = trigger ? trigger.querySelector('.dim-genre-picker-text') : null;
            var previewEl = row ? row.querySelector('.dim-genre-names-preview') : null;
            if (textEl) {
                textEl.textContent = newIds.length
                    ? newIds.map(function(id) { return _getGenreNameById(id); }).join(', ')
                    : '点击选择 Provider 类型...';
            }
            if (previewEl) {
                previewEl.textContent = newIds.length
                    ? _genreIdToLabel(newIds.slice(0, 4)) + (newIds.length > 4 ? ' +' + (newIds.length - 4) : '')
                    : '-';
            }
        });
    });
}

function toggleGenreHelp() {
    var panel = document.getElementById('dim-genre-help');
    if (panel) panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}

var _genreDragDim = null;
var _genreDragIdx = -1;

function genreDragStart(e, dimName, idx) {
    _genreDragDim = dimName;
    _genreDragIdx = idx;
    e.target.style.opacity = '0.4';
    if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', dimName + ':' + idx);
    }
}

function genreDragEnd(e) {
    e.target.style.opacity = '1';
    document.querySelectorAll('.dim-genre-row.dim-genre-drag-over').forEach(function(el) {
        el.classList.remove('dim-genre-drag-over');
    });
    _genreDragDim = null;
    _genreDragIdx = -1;
}

function genreDragOver(e) {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    var row = e.target.closest('.dim-genre-row');
    if (row) row.classList.add('dim-genre-drag-over');
}

function genreDragLeave(e) {
    var row = e.target.closest('.dim-genre-row');
    if (row) row.classList.remove('dim-genre-drag-over');
}

function genreDrop(e, dimName, targetIdx) {
    e.preventDefault();
    e.stopPropagation();
    var row = e.target.closest('.dim-genre-row');
    if (row) row.classList.remove('dim-genre-drag-over');
    if (!_genreDragDim || _genreDragDim !== dimName || _genreDragIdx === targetIdx) return;
    if (_genreDragIdx < 0 || targetIdx < 0) return;

    var currentRows = document.querySelectorAll('#dim-genre-rows-' + dimName + ' .dim-genre-row');
    var fromRow = document.getElementById('dim-genre-row-' + dimName + '-' + _genreDragIdx);
    var toRow = document.getElementById('dim-genre-row-' + dimName + '-' + targetIdx);
    if (!fromRow || !toRow) return;

    var toIsOther = toRow.querySelector('.dim-genre-priority-other');
    var fromIsOther = fromRow.querySelector('.dim-genre-priority-other');
    if (fromIsOther || toIsOther) return;

    var rowDefs = [];
    currentRows.forEach(function(r) {
        var labelEl = r.querySelector('.dim-genre-label-text');
        var idsAttr = r.getAttribute('data-genre-ids') || '[]';
        var valAttr = r.getAttribute('data-genre-value') || '';
        var isOther = !!r.querySelector('.dim-genre-priority-other');
        var label = labelEl ? labelEl.textContent : '';
        rowDefs.push({ label: label, value: valAttr, ids: idsAttr, isOther: isOther });
    });

    var fromRowDef = rowDefs[_genreDragIdx];
    if (fromRowDef.isOther) return;

    var nonOther = rowDefs.filter(function(r) { return !r.isOther; });
    var otherDef = rowDefs.find(function(r) { return r.isOther; });

    var fromPos = nonOther.indexOf(fromRowDef);
    var toPos = rowDefs.indexOf(rowDefs[targetIdx]);
    var toNonOtherPos = nonOther.indexOf(rowDefs[targetIdx]);
    if (fromPos < 0 || toNonOtherPos < 0) return;

    nonOther.splice(fromPos, 1);
    nonOther.splice(toNonOtherPos, 0, fromRowDef);

    var valueList = [];
    nonOther.forEach(function(r, i) {
        var ids = [];
        try { ids = JSON.parse(r.ids); } catch(e) {}
        valueList.push({
            value: r.value || r.label.toLowerCase().replace(/\s+/g, '_'),
            label: r.label,
            tmdb_genre_ids: ids,
            priority: i + 1
        });
    });
    if (otherDef) {
        var oIds = [];
        try { oIds = JSON.parse(otherDef.ids); } catch(e) {}
        valueList.push({
            value: 'other', label: otherDef.label,
            tmdb_genre_ids: oIds,
            priority: valueList.length + 1
        });
    }

    _updateGenreRowsFromData(dimName, valueList);
    _genreDragDim = null;
    _genreDragIdx = -1;
}

function _updateGenreRowsFromData(dimName, valueList) {
    var container = document.getElementById('dim-genre-rows-' + dimName);
    if (!container) return;
    container.innerHTML = _renderGenreRows(dimName, valueList);
}

function startAddGenre(dimName) {
    if (_genreAdding === dimName) return;
    _genreAdding = dimName;

    var addRow = document.getElementById('dim-genre-add-row-' + dimName);
    if (!addRow) return;

    addRow.innerHTML =
        '<div class="dim-genre-row dim-genre-add-row-active" style="display:flex;flex-wrap:wrap;padding:8px;">' +
            '<span class="dim-drag-placeholder"></span>' +
            '<span class="dim-genre-priority" style="color:var(--text-muted);">#</span>' +
            '<div class="dim-genre-add-fields">' +
                '<input type="text" class="dim-genre-add-input-val" id="dim-genre-add-value" placeholder="英文键值，如：music">' +
                '<input type="text" class="dim-genre-add-input" id="dim-genre-add-label" placeholder="中文名称，如：音乐">' +
            '</div>' +
            '<div class="dim-genre-add-btns">' +
                '<button class="dim-genre-add-confirm" type="button" data-dimension-action="confirm-add-genre" data-dim-name="' + dimName + '">✓</button>' +
                '<button class="dim-genre-remove" type="button" data-dimension-action="cancel-add-genre" data-dim-name="' + dimName + '" title="取消">×</button>' +
            '</div>' +
        '</div>';

    var labelInput = document.getElementById('dim-genre-add-label');
    var valueInput = document.getElementById('dim-genre-add-value');
    if (!labelInput || !valueInput) return;

    valueInput.focus();

    function doConfirm() {
        var label = labelInput.value.trim();
        var value = valueInput.value.trim();
        if (!label) { cancelAddGenre(dimName); return; }
        if (!value) value = label.toLowerCase().replace(/[\s\u4e00-\u9fff]+/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '') || label;
        confirmAddGenre(dimName, label, value);
    }

    valueInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); labelInput.focus(); }
        if (e.key === 'Escape') cancelAddGenre(dimName);
    });
    labelInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); doConfirm(); }
        if (e.key === 'Escape') cancelAddGenre(dimName);
    });
    var blurTimer = null;
    valueInput.addEventListener('blur', function() {
        blurTimer = setTimeout(function() {
            if (_genreAdding === dimName) cancelAddGenre(dimName);
        }, 300);
    });
    labelInput.addEventListener('blur', function() {
        blurTimer = setTimeout(function() {
            if (_genreAdding === dimName) cancelAddGenre(dimName);
        }, 300);
    });
    valueInput.addEventListener('focus', function() { if (blurTimer) clearTimeout(blurTimer); });
    labelInput.addEventListener('focus', function() { if (blurTimer) clearTimeout(blurTimer); });
}

function confirmAddGenre(dimName, label, value) {
    if (!label || !label.trim()) { cancelAddGenre(dimName); return; }
    label = label.trim();
    if (!value || !value.trim()) { cancelAddGenre(dimName); return; }
    value = value.trim().toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '');

    var currentRows = document.querySelectorAll('#dim-genre-rows-' + dimName + ' .dim-genre-row');
    var existingLabels = [];
    var existingVals = [];
    currentRows.forEach(function(r) {
        var el = r.querySelector('.dim-genre-label-text');
        if (el) existingLabels.push(el.textContent.toLowerCase());
        var v = r.getAttribute('data-genre-value');
        if (v) existingVals.push(v.toLowerCase());
    });

    if (existingLabels.indexOf(label.toLowerCase()) >= 0) {
        showToast('类型名称已存在: ' + label, 'error');
        return;
    }
    if (existingVals.indexOf(value) >= 0) {
        showToast('英文键值已存在: ' + value, 'error');
        return;
    }

    var nonOtherCount = 0;
    var rowDefs = [];
    currentRows.forEach(function(r) {
        var labelEl = r.querySelector('.dim-genre-label-text');
        var idsAttr = r.getAttribute('data-genre-ids') || '[]';
        var valAttr = r.getAttribute('data-genre-value') || '';
        var isOther = !!r.querySelector('.dim-genre-priority-other');
        if (!isOther) nonOtherCount++;
        rowDefs.push({ label: labelEl ? labelEl.textContent : '', value: valAttr, ids: idsAttr, isOther: isOther });
    });

    var valueList = [];
    rowDefs.filter(function(r) { return !r.isOther; }).forEach(function(r, i) {
        var ids = [];
        try { ids = JSON.parse(r.ids); } catch(e) {}
        valueList.push({
            value: r.value || r.label.toLowerCase().replace(/\s+/g, '_'),
            label: r.label, tmdb_genre_ids: ids, priority: i + 1
        });
    });

    var newPriority = valueList.length + 1;
    valueList.push({ value: value, label: label, tmdb_genre_ids: [], priority: newPriority });

    var otherDef = rowDefs.find(function(r) { return r.isOther; });
    if (otherDef) {
        var oIds = [];
        try { oIds = JSON.parse(otherDef.ids); } catch(e) {}
        valueList.push({ value: 'other', label: otherDef.label, tmdb_genre_ids: oIds, priority: valueList.length + 1 });
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
    var addRow = document.getElementById('dim-genre-add-row-' + dimName);
    if (addRow) {
        addRow.innerHTML = '<button class="dim-genre-add-btn" type="button" data-dimension-action="start-add-genre" data-dim-name="' + dimName + '">+ 添加类型值</button>';
    }
}

function removeGenreValue(dimName, idx) {
    var currentRows = document.querySelectorAll('#dim-genre-rows-' + dimName + ' .dim-genre-row');
    var rowDefs = [];
    currentRows.forEach(function(r, i) {
        var labelEl = r.querySelector('.dim-genre-label-text');
        var idsAttr = r.getAttribute('data-genre-ids') || '[]';
        var valAttr = r.getAttribute('data-genre-value') || '';
        var isOther = !!r.querySelector('.dim-genre-priority-other');
        rowDefs.push({ idx: i, label: labelEl ? labelEl.textContent : '', value: valAttr, ids: idsAttr, isOther: isOther });
    });

    if (idx >= rowDefs.length) return;
    var target = rowDefs[idx];
    if (target.isOther) return;

    showConfirm('删除类型值', '确定删除类型值 "' + target.label + '" 吗？此操作不可撤销。', function() {
        var valueList = [];
        rowDefs.filter(function(r) { return r.idx !== idx && !r.isOther; }).forEach(function(r, i) {
            var ids = [];
            try { ids = JSON.parse(r.ids); } catch(e) {}
            valueList.push({ value: r.value || r.label.toLowerCase().replace(/\s+/g, '_'), label: r.label, tmdb_genre_ids: ids, priority: i + 1 });
        });

        var otherDef = rowDefs.find(function(r) { return r.isOther; });
        if (otherDef) {
            var oIds = [];
            try { oIds = JSON.parse(otherDef.ids); } catch(e) {}
            valueList.push({ value: 'other', label: otherDef.label, tmdb_genre_ids: oIds, priority: valueList.length + 1 });
        }

        _openGenrePicker = null;
        _updateGenreRowsFromData(dimName, valueList);
    });
}

function _generateGenrePrompt() {
    var container = document.getElementById('dim-genre-rows-' + _expandedDim);
    if (!container) return null;

    var parts = [];
    var rows = container.querySelectorAll('.dim-genre-row');
    rows.forEach(function(row) {
        var labelEl = row.querySelector('.dim-genre-label-text');
        var isOther = row.querySelector('.dim-genre-priority-other');
        if (!labelEl || isOther) return;
        var label = labelEl.textContent;
        var value = row.getAttribute('data-genre-value') || label.toLowerCase().replace(/\s+/g, '_');
        parts.push(value + '（' + label + '）');
    });

    if (parts.length === 0) return null;

    return '请判断该影视作品的主要类型：' + parts.join('、') + '、other（其他）。' +
        '如果同时属于多个类型，选择风格最鲜明突出的那个。';
}

function _collectGenreMappingData(dimName) {
    var valueList = [];
    var rows = document.querySelectorAll('#dim-genre-rows-' + dimName + ' .dim-genre-row');
    rows.forEach(function(row, posIdx) {
        var labelEl = row.querySelector('.dim-genre-label-text');
        var isOther = row.querySelector('.dim-genre-priority-other');
        var idsAttr = row.getAttribute('data-genre-ids') || '[]';
        var valAttr = row.getAttribute('data-genre-value') || '';

        var label = labelEl ? labelEl.textContent : '';
        var ids = [];
        try { ids = JSON.parse(idsAttr); } catch(e) {}

        var item = {
            value: isOther ? 'other' : (valAttr || label.toLowerCase().replace(/\s+/g, '_')),
            label: label,
            priority: isOther ? 99 : (posIdx + 1),
            tmdb_genre_ids: ids
        };
        valueList.push(item);
    });
    return JSON.stringify(valueList);
}

function _collectMappingData() {
    var inputs = document.querySelectorAll('.dim-mapping-input[data-map-idx]');
    var groups = {};
    inputs.forEach(function(inp) {
        var idx = parseInt(inp.getAttribute('data-map-idx'));
        var field = inp.getAttribute('data-map-field');
        if (!groups[idx]) groups[idx] = {};
        groups[idx][field] = inp.value.trim();
    });
    return groups;
}

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
        setTimeout(function() {
            var card = document.getElementById('dim-card-' + name);
            if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 50);
    }
}

async function enableDimension(name) {
    var result = await apiRequest('POST', '/dimensions/' + name + '/enable');
    if (result.code === 200) {
        showToast(result.message || '维度已启用', 'success');
        await loadDimensions();
        if (typeof loadEnabledDimensions === 'function') {
            await loadEnabledDimensions();
            if (typeof refreshPathRulesDisplay === 'function') refreshPathRulesDisplay();
        }
    } else {
        showToast(result.message || '启用失败', 'error');
    }
}

async function disableDimension(name) {
    if (typeof isDimensionUsedInRules === 'function' && isDimensionUsedInRules(name)) {
        var dim = _dimensionsData.find(function(d) { return d.name === name; });
        var dimLabel = dim ? dim.label : name;
        showConfirm('无法禁用', '维度「' + dimLabel + '」正在入库规则中使用，请先删除相关规则后再禁用。', function() {});
        return;
    }
    var result = await apiRequest('POST', '/dimensions/' + name + '/disable');
    if (result.code === 200) {
        if (_expandedDim === name) _expandedDim = null;
        showToast(result.message || '维度已禁用', 'success');
        await loadDimensions();
        if (typeof loadEnabledDimensions === 'function') {
            await loadEnabledDimensions();
            if (typeof refreshPathRulesDisplay === 'function') refreshPathRulesDisplay();
        }
    } else {
        showToast(result.message || '禁用失败', 'error');
    }
}

async function resetDimension(name) {
    showConfirm('恢复默认', '确定将"' + name + '"的所有映射配置恢复为默认值吗？', async function() {
        var result = await apiRequest('POST', '/dimensions/' + name + '/reset');
        if (result.code === 200) {
            showToast(result.message || '已恢复默认配置', 'success');
            await loadDimensions();
        } else {
            showToast(result.message || '恢复失败', 'error');
        }
    });
}

function _renderLangMapping(valueList) {
    var rows = valueList.map(function(v) {
        return '<div class="dim-mapping-row">' +
            '<span class="dim-mapping-value">' + _escapeHtml(v.label) + '</span>' +
            '<span class="dim-mapping-arrow">←</span>' +
            '<span class="dim-mapping-codes">' + _escapeHtml(v.value) + '</span>' +
        '</div>';
    }).join('');

    return '<div class="dim-mapping-section">' +
        '<div class="dim-mapping-header-row">' +
            '<span class="dim-mapping-col-label">入库标签值</span>' +
            '<span class="dim-mapping-col-label">Provider获取值</span>' +
        '</div>' +
        rows +
        '<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">语言映射基于 ISO 639-1 代码（original_language），无需手动编辑</div>' +
    '</div>';
}

async function saveDimensionEdit(name) {
    var dim = _dimensionsData.find(function(d) { return d.name === name; });
    if (!dim) return;

    var colorEl = document.getElementById('dim-edit-color');
    var promptEl = document.getElementById('dim-edit-ai-prompt');
    var data = {};
    if (colorEl) data.color = colorEl.value;

    var _hasGenreMapping = false;
    if (dim.source_type === 'ai+provider') {
        var _pm = dim.provider_mappings;
        if (typeof _pm === 'string') { try { _pm = JSON.parse(_pm); } catch(e) { _pm = null; } }
        if (_pm && typeof _pm === 'object') {
            for (var _pmKey in _pm) {
                if (_pm[_pmKey] && _pm[_pmKey].field === 'genres') { _hasGenreMapping = true; break; }
            }
        }
        if (dim.tmdb_field === 'genres') _hasGenreMapping = true;
    }

    if (_hasGenreMapping) {
        var autoPrompt = _generateGenrePrompt();
        if (autoPrompt && promptEl) promptEl.value = autoPrompt;
        if (promptEl) data.ai_prompt = promptEl.value;
        data.value_list = _collectGenreMappingData(name);
    } else {
        if (promptEl) data.ai_prompt = promptEl.value;
        var mappingData = _collectMappingData();
        var mappingKeys = Object.keys(mappingData);
        if (mappingKeys.length > 0) {
            var origValueList = _parseValueList(dim.value_list);
            var newValueList = origValueList.slice();
            mappingKeys.forEach(function(idxStr) {
                var idx = parseInt(idxStr);
                if (idx < 0 || idx >= newValueList.length) return;
                var row = mappingData[idxStr];
                if (row.tmdb_codes !== undefined) {
                    newValueList[idx].tmdb_codes = row.tmdb_codes
                        ? row.tmdb_codes.split(',').map(function(s) { return s.trim(); }).filter(Boolean)
                        : [];
                }
            });
            data.value_list = JSON.stringify(newValueList);
        }
    }

    var result = await apiRequest('PUT', '/dimensions/' + name, data);
    if (result.code === 200) {
        showToast(result.message || '维度配置已更新', 'success');
        _openGenrePicker = null;
        await loadDimensions();
    } else {
        showToast(result.message || '保存失败', 'error');
    }
}

document.addEventListener('click', function(e) {
    var actionEl = e.target.closest('[data-dimension-action]');
    if (actionEl) {
        e.stopPropagation();
        var action = actionEl.getAttribute('data-dimension-action');
        var dimName = actionEl.getAttribute('data-dim-name') || actionEl.getAttribute('data-dimension-name');
        var genreIdx = parseInt(actionEl.getAttribute('data-genre-idx') || '-1', 10);

        if (action === 'enable' && dimName) { enableDimension(dimName); return; }
        if (action === 'disable' && dimName) { disableDimension(dimName); return; }
        if ((action === 'toggle-card' || action === 'collapse') && dimName) { toggleDimCard(dimName); return; }
        if (action === 'save' && dimName) { saveDimensionEdit(dimName); return; }
        if (action === 'reset' && dimName) { resetDimension(dimName); return; }
        if (action === 'toggle-genre-help') { toggleGenreHelp(); return; }
        if (action === 'start-add-genre' && dimName) { startAddGenre(dimName); return; }
        if (action === 'cancel-add-genre' && dimName) { cancelAddGenre(dimName); return; }
        if (action === 'confirm-add-genre' && dimName) {
            var labelInput = document.getElementById('dim-genre-add-label');
            var valueInput = document.getElementById('dim-genre-add-value');
            var label = labelInput ? labelInput.value.trim() : '';
            var value = valueInput ? valueInput.value.trim() : '';
            if (!label) return;
            if (!value) value = label.toLowerCase().replace(/[\s\u4e00-\u9fff]+/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '') || label;
            confirmAddGenre(dimName, label, value);
            return;
        }
        if (action === 'remove-genre-value' && dimName && genreIdx >= 0) { removeGenreValue(dimName, genreIdx); return; }
        if (action === 'toggle-genre-picker' && dimName && genreIdx >= 0) { toggleGenrePicker(dimName, genreIdx); return; }
    }

    if (_openGenrePicker) {
        var picker = document.getElementById(_openGenrePicker);
        if (picker && !picker.parentElement.contains(e.target)) {
            picker.style.display = 'none';
            picker.style.left = ''; picker.style.top = '';
            _openGenrePicker = null;
        }
    }
});

document.addEventListener('dragstart', function(e) {
    var handle = e.target.closest('[data-dimension-action="genre-drag-handle"]');
    if (!handle) return;
    e.stopPropagation();
    var dimName = handle.getAttribute('data-dim-name');
    var genreIdx = parseInt(handle.getAttribute('data-genre-idx') || '-1', 10);
    if (!dimName || genreIdx < 0) return;
    genreDragStart(e, dimName, genreIdx);
});

document.addEventListener('dragend', function(e) {
    var handle = e.target.closest('[data-dimension-action="genre-drag-handle"]');
    if (!handle) return;
    genreDragEnd(e);
});

document.addEventListener('dragover', function(e) {
    var row = e.target.closest('.dim-genre-row');
    if (!row) return;
    genreDragOver(e);
});

document.addEventListener('dragleave', function(e) {
    var row = e.target.closest('.dim-genre-row');
    if (!row) return;
    genreDragLeave(e);
});

document.addEventListener('drop', function(e) {
    var row = e.target.closest('.dim-genre-row');
    if (!row) return;
    var dimName = row.getAttribute('data-dim-name');
    var genreIdx = parseInt(row.getAttribute('data-genre-idx') || '-1', 10);
    if (!dimName || genreIdx < 0) return;
    genreDrop(e, dimName, genreIdx);
});

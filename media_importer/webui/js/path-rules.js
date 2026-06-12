var _openDropdownMulti = null;

var MULTI_SELECT_DIMS = ['restricted_level', 'broad_genre'];
var DROPDOWN_MULTI_DIMS = ['broad_genre'];

function _transformDimensionsToSelectFormat(rawDims) {
    var result = [];
    for (var i = 0; i < rawDims.length; i++) {
        var d = rawDims[i];
        var valueList = d.value_list || [];
        var isMulti = MULTI_SELECT_DIMS.indexOf(d.name) >= 0;
        var isDropdownMulti = DROPDOWN_MULTI_DIMS.indexOf(d.name) >= 0;
        var options = valueList.map(function(v) {
            return { value: v.value, label: v.label || v.value };
        });
        var dimType = isDropdownMulti ? 'dropdown-multi' : (isMulti ? 'multi-select' : 'select');
        result.push({
            name: d.name,
            label: d.label,
            type: dimType,
            options: isMulti ? options : [{ value: '', label: '(不限制)' }].concat(options),
            color: d.color || '#6c757d'
        });
    }
    return result;
}

async function loadEnabledDimensions() {
    if (typeof loadDimensionVars === 'function') {
        await loadDimensionVars();
    }
}

function _getDimensions() {
    if (currentEnabledDimensions && currentEnabledDimensions.length > 0) {
        return _transformDimensionsToSelectFormat(currentEnabledDimensions);
    }
    return [
        { name: 'media_type', label: '影视类型', type: 'select', options: [{ value: '', label: '(不限制)' }, { value: 'movie', label: '电影' }, { value: 'tv', label: '剧集' }], color: '#3b82f6' },
        { name: 'documentary', label: '是否纪录片', type: 'select', options: [{ value: '', label: '(不限制)' }, { value: 'true', label: '是' }, { value: 'false', label: '否' }], color: '#f59e0b' },
        { name: 'restricted_level', label: '限制级', type: 'multi-select', options: [{ value: '0-6', label: '幼儿/儿童' }, { value: '7-12', label: '家庭向' }, { value: '13-16', label: '青少年向' }, { value: '17+', label: '成人内容' }], color: '#ec4899' }
    ];
}

function _valueToLabel(dimName, value) {
    var dims = _getDimensions();
    for (var i = 0; i < dims.length; i++) {
        if (dims[i].name === dimName) {
            for (var j = 0; j < dims[i].options.length; j++) {
                if (dims[i].options[j].value === value) return dims[i].options[j].label;
            }
        }
    }
    return value;
}

function _isMultiType(dimType) {
    return dimType === 'multi-select' || dimType === 'dropdown-multi';
}

function renderPathRules(rules) {
    var container = document.getElementById('path-rules-container');
    if (!container) return;
    if (!Array.isArray(rules)) rules = [];

    _openDropdownMulti = null;
    container.innerHTML = rules.map((rule, index) => createRuleCardHTML(rule, index, rules.length)).join('');

    if (rules.length === 1) {
        var firstCard = container.querySelector('.rule-card');
        if (firstCard) firstCard.classList.add('expanded');
    }

    bindPathRuleDrag();
}

function buildRuleSummary(rule) {
    var conditions = rule.conditions || {};
    var tagsHTML = '';
    var hasTag = false;
    for (var d = 0; d < _getDimensions().length; d++) {
        var dim = _getDimensions()[d];
        var value = conditions[dim.name];
        if (value === undefined || value === null || value === '') continue;
        var displayValue;
        if (_isMultiType(dim.type)) {
            displayValue = String(value).split('|').map(function(s) {
                return s.trim() ? _valueToLabel(dim.name, s.trim()) : '';
            }).filter(Boolean).join(' / ');
            if (!displayValue) continue;
        } else {
            displayValue = _valueToLabel(dim.name, value);
        }
        tagsHTML += '<span class="rule-summary-tag">' +
            '<span class="rule-summary-tag-key">' + escapeHtml(dim.label) + '</span>' +
            '<span class="rule-summary-tag-val">' + escapeHtml(displayValue) + '</span>' +
            '</span>';
        hasTag = true;
    }
    if (!hasTag) {
        tagsHTML = '<span class="rule-summary-tag rule-summary-tag-empty">无条件</span>';
    }

    var tpl = rule.template || '';
    var pathHTML;
    if (!tpl) {
        pathHTML = '<span class="rule-summary-path-empty">(未设置)</span>';
    } else {
        pathHTML = tpl.replace(/(\{[^}]+\})|([^{]+)/g, function(_, varToken, textToken) {
            if (varToken) {
                return '<span class="rule-summary-path-var">' + escapeHtml(varToken) + '</span>';
            }
            return '<span class="rule-summary-path-text">' + escapeHtml(textToken) + '</span>';
        });
    }

    return '<span class="rule-summary-tags">' + tagsHTML + '</span>' +
        '<span class="rule-summary-arrow">→</span>' +
        '<span class="rule-summary-path">' + pathHTML + '</span>';
}

function createRuleCardHTML(rule, index, total) {
    var conditions = rule.conditions || {};
    var summary = buildRuleSummary(rule);

    var enabledDimNames = [];
    var conditionsHTML = '';
    for (var d = 0; d < _getDimensions().length; d++) {
        var dim = _getDimensions()[d];
        enabledDimNames.push(dim.name);
        var value = conditions[dim.name];
        var labeledName = '<span class="rule-condition-labeled-name">' + escapeHtml(dim.label || dim.name) + '</span><small class="rule-condition-dim-code">' + escapeHtml(dim.name) + '</small>';
        if (dim.type === 'select') {
            conditionsHTML += '<div class="rule-condition-item">' +
                '<label class="rule-condition-label">' + labeledName + '</label>' +
                '<select class="rule-condition-select" data-dim="' + dim.name + '">' +
                dim.options.map(function(opt) {
                    return '<option value="' + escapeHtml(opt.value) + '" ' + (value === opt.value ? 'selected' : '') + '>' + escapeHtml(opt.label) + '</option>';
                }).join('') +
                '</select></div>';
        } else if (dim.type === 'multi-select') {
            var selectedValues = typeof value === 'string' ? value.split('|').map(function(s) { return s.trim(); }).filter(Boolean) : [];
            conditionsHTML += '<div class="rule-condition-item">' +
                '<label class="rule-condition-label">' + labeledName + '<small>（可多选）</small></label>' +
                '<div class="rule-condition-checkbox-group" data-dim="' + dim.name + '">' +
                dim.options.map(function(opt) {
                    return '<label class="rule-condition-checkbox-label">' +
                        '<input type="checkbox" value="' + escapeHtml(opt.value) + '" ' + (selectedValues.indexOf(opt.value) >= 0 ? 'checked' : '') + ' data-option="' + escapeHtml(opt.value) + '">' + escapeHtml(opt.label) +
                        '</label>';
                }).join('') +
                '</div></div>';
        } else if (dim.type === 'dropdown-multi') {
            var selVals = typeof value === 'string' ? value.split('|').map(function(s) { return s.trim(); }).filter(Boolean) : [];
            var triggerText = selVals.length
                ? selVals.map(function(v) { return _valueToLabel(dim.name, v); }).join('、')
                : '（不限制）';
            conditionsHTML += '<div class="rule-condition-item">' +
                '<label class="rule-condition-label">' + labeledName + '<small>（可多选）</small></label>' +
                '<div class="rule-dropdown-multi" data-dim="' + dim.name + '">' +
                    '<div class="rule-dropdown-multi-trigger" onclick="event.stopPropagation();toggleDropdownMulti(this,\'' + dim.name + '\')">' +
                        '<span class="rule-dropdown-multi-text">' + escapeHtml(triggerText) + '</span>' +
                        '<svg class="rule-dropdown-multi-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>' +
                    '</div>' +
                    '<div class="rule-dropdown-multi-panel" style="display:none;">' +
                        dim.options.map(function(opt) {
                            return '<label class="rule-dropdown-multi-option">' +
                                '<input type="checkbox" value="' + escapeHtml(opt.value) + '" ' + (selVals.indexOf(opt.value) >= 0 ? 'checked' : '') + '>' +
                                '<span>' + escapeHtml(opt.label) + '</span>' +
                            '</label>';
                        }).join('') +
                    '</div>' +
                '</div>' +
            '</div>';
        }
    }

    // 规则中使用了已禁用的维度 → 以只读形式展示
    for (var condName in conditions) {
        if (enabledDimNames.indexOf(condName) < 0 && conditions.hasOwnProperty(condName)) {
            var labeledName = '<span class="rule-condition-labeled-name">' + escapeHtml(condName) + '</span><small class="rule-condition-dim-code">' + escapeHtml(condName) + '</small>';
            conditionsHTML += '<div class="rule-condition-item rule-condition-disabled">' +
                '<label class="rule-condition-label">' + labeledName + ' <span class="rule-condition-disabled-badge">已禁用</span></label>' +
                '<div class="rule-condition-readonly-value">' + escapeHtml(conditions[condName]) + '</div>' +
                '<button class="btn btn-sm btn-outline rule-condition-remove" onclick="removeDisabledDimCondition(this, \'' + escapeHtml(condName) + '\', ' + index + ')" ' +
                    'title="删除此条件后可禁用该维度">删除</button>' +
            '</div>';
        }
    }

    return '<div class="rule-card" data-index="' + index + '">' +
        '<div class="rule-card-bar" onclick="toggleRuleCard(this.parentElement)">' +
            '<span class="rule-card-drag-handle" draggable="true" title="拖动调整匹配优先顺序" onclick="event.stopPropagation();">' +
                '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.4"/><circle cx="15" cy="6" r="1.4"/><circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/><circle cx="9" cy="18" r="1.4"/><circle cx="15" cy="18" r="1.4"/></svg>' +
            '</span>' +
            '<span class="rule-card-badge">#' + (index + 1) + '</span>' +
            '<span class="rule-card-summary">' + summary + '</span>' +
            '<div class="rule-card-actions">' +
                '<button class="rule-card-chevron" title="展开/折叠">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>' +
                '</button>' +
                '<button title="删除" class="rule-btn-delete" onclick="event.stopPropagation();deletePathRule(' + index + ')">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
                '</button>' +
            '</div>' +
        '</div>' +
        '<div class="rule-card-body">' +
            '<div class="rule-card-body-inner">' +
                '<div class="rule-conditions">' + conditionsHTML + '</div>' +
                '<div class="rule-template-row">' +
                    '<label class="rule-condition-label">入库路径模板</label>' +
                    '<input type="text" class="rule-template-input" placeholder="/vol1/影视/电影/{year}/{title_cn}/" value="' + (rule.template || '') + '">' +
                '</div>' +
            '</div>' +
        '</div>' +
    '</div>';
}

function toggleDropdownMulti(triggerEl, dimName) {
    var wrapper = triggerEl.closest('.rule-dropdown-multi');
    if (!wrapper) return;
    var panel = wrapper.querySelector('.rule-dropdown-multi-panel');
    if (!panel) return;

    var panelId = wrapper.getAttribute('data-dim') + '_' + wrapper.closest('.rule-card').getAttribute('data-index');

    if (_openDropdownMulti && _openDropdownMulti !== panelId) {
        var prevPanel = document.querySelector('.rule-dropdown-multi-panel[style*="block"]');
        if (prevPanel) prevPanel.style.display = 'none';
    }

    if (panel.style.display === 'block') {
        panel.style.display = 'none';
        panel.style.top = '';
        panel.style.left = '';
        panel.style.width = '';
        _openDropdownMulti = null;
    } else {
        var rect = triggerEl.getBoundingClientRect();
        var panelH = 240;
        var spaceBelow = window.innerHeight - rect.bottom;
        if (spaceBelow >= panelH || rect.top < panelH) {
            panel.style.top = (rect.bottom + 4) + 'px';
        } else {
            panel.style.top = (rect.top - panelH - 4) + 'px';
        }
        panel.style.left = rect.left + 'px';
        panel.style.width = Math.max(220, rect.width) + 'px';

        panel.style.display = 'block';
        _openDropdownMulti = panelId;

        if (!panel.getAttribute('data-bound')) {
            panel.setAttribute('data-bound', '1');
            panel.querySelectorAll('input[type="checkbox"]').forEach(function(cb) {
                cb.addEventListener('change', function() {
                    var textEl = wrapper.querySelector('.rule-dropdown-multi-text');
                    if (!textEl) return;
                    var allChecked = wrapper.querySelectorAll('input[type="checkbox"]:checked');
                    if (allChecked.length === 0) {
                        textEl.textContent = '（不限制）';
                    } else {
                        var labels = [];
                        allChecked.forEach(function(c) {
                            var span = c.parentElement ? c.parentElement.querySelector('span') : null;
                            labels.push(span ? span.textContent : c.value);
                        });
                        textEl.textContent = labels.join('、');
                    }
                });
            });
        }
    }
}

function toggleRuleCard(card) {
    if (!card) return;
    card.classList.toggle('expanded');
}

function collectPathRulesFromDOM() {
    var container = document.getElementById('path-rules-container');
    if (!container) return [];
    var cards = container.querySelectorAll('.rule-card');
    var rules = [];

    for (var ci = 0; ci < cards.length; ci++) {
        var card = cards[ci];
        var conditions = {};
        for (var di = 0; di < _getDimensions().length; di++) {
            var dim = _getDimensions()[di];
            if (dim.type === 'select') {
                var select = card.querySelector('[data-dim="' + dim.name + '"]');
                var value = select ? select.value : '';
                if (value) {
                    conditions[dim.name] = value;
                }
            } else if (dim.type === 'multi-select') {
                var group = card.querySelector('[data-dim="' + dim.name + '"]');
                if (group) {
                    var checked = Array.from(group.querySelectorAll('input[type="checkbox"]:checked')).map(function(cb) { return cb.value; });
                    if (checked.length > 0) {
                        conditions[dim.name] = checked.join('|');
                    }
                }
            } else if (dim.type === 'dropdown-multi') {
                var dmWrapper = card.querySelector('.rule-dropdown-multi[data-dim="' + dim.name + '"]');
                if (dmWrapper) {
                    var dmChecked = Array.from(dmWrapper.querySelectorAll('input[type="checkbox"]:checked')).map(function(cb) { return cb.value; });
                    if (dmChecked.length > 0) {
                        conditions[dim.name] = dmChecked.join('|');
                    }
                }
            }
        }
        var template = card.querySelector('.rule-template-input');
        rules.push({
            conditions: conditions,
            template: template ? template.value : ''
        });
    }

    return rules;
}

function addPathRule() {
    var currentRules = collectPathRulesFromDOM();
    currentRules.push({ conditions: {}, template: '' });
    renderPathRules(currentRules);
    var cards = document.querySelectorAll('#path-rules-container .rule-card');
    if (cards.length > 0) {
        cards[cards.length - 1].classList.add('expanded');
    }
}

function deletePathRule(index) {
    var currentRules = collectPathRulesFromDOM();
    currentRules.splice(index, 1);
    renderPathRules(currentRules);
}

function movePathRuleUp(index) {
    if (index <= 0) return;
    var currentRules = collectPathRulesFromDOM();
    var temp = currentRules[index];
    currentRules[index] = currentRules[index - 1];
    currentRules[index - 1] = temp;
    renderPathRules(currentRules);
}

function movePathRuleDown(index) {
    var currentRules = collectPathRulesFromDOM();
    if (index >= currentRules.length - 1) return;
    var temp = currentRules[index];
    currentRules[index] = currentRules[index + 1];
    currentRules[index + 1] = temp;
    renderPathRules(currentRules);
}

function isDimensionUsedInRules(dimName) {
    var rules = collectPathRulesFromDOM();
    for (var i = 0; i < rules.length; i++) {
        var cond = rules[i].conditions || {};
        var val = cond[dimName];
        if (val !== undefined && val !== null && val !== '') return true;
    }
    return false;
}

function removeDisabledDimCondition(btnEl, dimName, ruleIndex) {
    var card = btnEl.closest('.rule-card');
    var index = card ? parseInt(card.getAttribute('data-index')) : ruleIndex;
    var rules = collectPathRulesFromDOM();
    if (rules[index] && rules[index].conditions) {
        delete rules[index].conditions[dimName];
    }
    renderPathRules(rules);
}

function refreshPathRulesDisplay() {
    var rules = collectPathRulesFromDOM();
    renderPathRules(rules);
}

var _draggingRuleCard = null;

function bindPathRuleDrag() {
    var container = document.getElementById('path-rules-container');
    if (!container) return;
    var cards = container.querySelectorAll('.rule-card');
    cards.forEach(function(card) {
        card.addEventListener('dragstart', onRuleDragStart);
        card.addEventListener('dragend', onRuleDragEnd);
        card.addEventListener('dragover', onRuleDragOver);
        card.addEventListener('dragleave', onRuleDragLeave);
        card.addEventListener('drop', onRuleDrop);
    });
}

function onRuleDragStart(e) {
    _draggingRuleCard = this;
    this.classList.add('rule-card-dragging');
    if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = 'move';
        try { e.dataTransfer.setData('text/plain', this.getAttribute('data-index') || ''); } catch (err) {}
    }
}

function onRuleDragEnd() {
    this.classList.remove('rule-card-dragging');
    var container = document.getElementById('path-rules-container');
    if (container) {
        container.querySelectorAll('.rule-card-drop-before, .rule-card-drop-after').forEach(function(el) {
            el.classList.remove('rule-card-drop-before', 'rule-card-drop-after');
        });
    }
    _draggingRuleCard = null;
}

function onRuleDragOver(e) {
    if (!_draggingRuleCard || _draggingRuleCard === this) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    var rect = this.getBoundingClientRect();
    var isAfter = (e.clientY - rect.top) > rect.height / 2;
    this.classList.toggle('rule-card-drop-before', !isAfter);
    this.classList.toggle('rule-card-drop-after', isAfter);
}

function onRuleDragLeave() {
    this.classList.remove('rule-card-drop-before', 'rule-card-drop-after');
}

function onRuleDrop(e) {
    if (!_draggingRuleCard || _draggingRuleCard === this) return;
    e.preventDefault();
    e.stopPropagation();
    var rect = this.getBoundingClientRect();
    var isAfter = (e.clientY - rect.top) > rect.height / 2;

    var currentRules = collectPathRulesFromDOM();
    var fromIndex = parseInt(_draggingRuleCard.getAttribute('data-index'), 10);
    var toIndex = parseInt(this.getAttribute('data-index'), 10);
    if (isNaN(fromIndex) || isNaN(toIndex)) return;

    var moved = currentRules.splice(fromIndex, 1)[0];
    var insertIndex = toIndex;
    if (fromIndex < toIndex) insertIndex -= 1;
    if (isAfter) insertIndex += 1;
    if (insertIndex < 0) insertIndex = 0;
    if (insertIndex > currentRules.length) insertIndex = currentRules.length;
    currentRules.splice(insertIndex, 0, moved);

    this.classList.remove('rule-card-drop-before', 'rule-card-drop-after');
    renderPathRules(currentRules);
}

document.addEventListener('click', function(e) {
    if (_openDropdownMulti) {
        var openPanel = document.querySelector('.rule-dropdown-multi-panel[style*="block"]');
        if (openPanel && !openPanel.parentElement.contains(e.target) && !openPanel.contains(e.target)) {
            openPanel.style.display = 'none';
            openPanel.style.top = '';
            openPanel.style.left = '';
            openPanel.style.width = '';
            _openDropdownMulti = null;
        }
    }
});

function toggleVarReference() {
    var ref = document.getElementById('var-reference');
    var btn = document.getElementById('var-ref-toggle');
    if (!ref || !btn) return;
    var isHidden = ref.classList.contains('collapsed-section') || ref.style.display === 'none';
    if (isHidden) {
        ref.style.display = '';
        ref.classList.remove('collapsed-section');
    } else {
        ref.classList.add('collapsed-section');
    }
    btn.classList.toggle('expanded', isHidden);
    if (isHidden) renderDimensionVars();
}

function renderDimensionVars() {
    var container = document.getElementById('var-dimensions-list');
    if (!container) return;
    var dims = _getDimensions();
    if (dims.length === 0) {
        container.innerHTML = '<div class="var-item"><span style="color:var(--text-muted);">暂无启用的维度</span></div>';
        return;
    }
    container.innerHTML = dims.map(function(d) {
        var valuesHint = '';
        if (d.options && d.options.length) {
            var nonEmpty = d.options.filter(function(o) { return o.value !== ''; });
            valuesHint = nonEmpty.map(function(o) { return o.label; }).join(' / ');
        }
        return '<div class="var-item">' +
            '<code>{dimension.' + d.name + '}</code>' +
            '<span>' + d.label + (valuesHint ? '（' + valuesHint + '）' : '') + '</span>' +
        '</div>';
    }).join('');
}

var _promptDimensionsCache = null;

async function _loadPromptDimensions() {
    if (_promptDimensionsCache) return _promptDimensionsCache;
    try {
        var result = await apiRequest('GET', '/dimensions/enabled');
        if (result.code === 200 && result.data && result.data.dimensions) {
            _promptDimensionsCache = result.data.dimensions
                .filter(function(d) {
                    return d.source_type === 'ai' || (d.source_type === 'ai+tmdb' && d.ai_prompt);
                })
                .map(function(d) {
                    var values = (d.value_list || []).map(function(v) { return v.value; });
                    return {
                        name: d.name,
                        label: d.label,
                        values: values,
                        ai_prompt: d.ai_prompt || ''
                    };
                });
        }
    } catch (e) {}
    if (!_promptDimensionsCache || _promptDimensionsCache.length === 0) {
        _promptDimensionsCache = [
            { name: 'media_type', label: '影视类型', values: ['movie', 'tv'], ai_prompt: '请判断这是电影（movie）还是电视剧（tv）。如果有季集信息（S01E01格式）则为电视剧；如果是完整独立故事则为电影。' },
            { name: 'documentary', label: '是否纪录片', values: ['true', 'false'], ai_prompt: '请判断是否为纪录片（true/false）。纪录片是以真实事件、人物、自然为主题的非虚构影视作品，包括自然纪录片、历史纪录片、社会纪录片等。' },
            { name: 'restricted_level', label: '限制级分类', values: ['0-6', '7-12', '13-16', '17+'], ai_prompt: '请判断内容的年龄分级：0-6（幼儿/儿童内容）、7-12（家庭向，适合全家观看）、13-16（青少年向，可能含轻微暴力或恐怖）、17+（成人内容，含明显暴力、色情或恐怖元素）。如不确定，请联网查询该影视的官方分级后判断。' },
            { name: 'animation', label: '是否动漫', values: ['true', 'false'], ai_prompt: '请判断是否为动漫/动画作品（true/false）。包括日本动画、中国动画、欧美动画电影等。以动画形式制作的作品均属于此类。' },
            { name: 'region', label: '地区', values: ['us', 'cn', 'hk', 'tw', 'jp', 'kr', 'gb', 'fr', 'de', 'it', 'es', 'in', 'other'], ai_prompt: '请判断该影视作品的主要制片国家或地区：us（美国）、cn（中国大陆）、hk（中国香港）、tw（中国台湾）、jp（日本）、kr（韩国）、gb（英国）、fr（法国）、de（德国）、it（意大利）、es（西班牙）、in（印度）、other（其他）。' },
            { name: 'origin_lang', label: '原始语言', values: ['zh', 'en', 'ja', 'ko', 'other'], ai_prompt: '请判断该影视作品的原始语言：zh（中文）、en（英语）、ja（日语）、ko（韩语）、other（其他语言）。' },
            { name: 'broad_genre', label: '类型', values: ['horror_mystery', 'scifi_fantasy', 'war', 'action_adventure', 'comedy', 'drama_romance', 'documentary', 'music', 'kids', 'tv_show', 'other'], ai_prompt: '请判断该影视作品的主要类型：horror_mystery（恐怖/悬疑）、scifi_fantasy（科幻/奇幻）、war（战争/军事）、action_adventure（动作/冒险）、comedy（喜剧）、drama_romance（剧情/情感）、documentary（纪录/纪实）、music（音乐/演出）、kids（儿童/家庭）、tv_show（电视节目）、other（其他）。' }
        ];
    }
    return _promptDimensionsCache;
}

function clearPromptDimensionsCache() {
    _promptDimensionsCache = null;
}

function togglePromptSection() {
    var panel = document.getElementById('prompt-panel');
    var toggleBtn = document.getElementById('btn-toggle-prompts');
    var arrow = document.getElementById('prompt-collapse-arrow');

    if (!panel) return;

    var isHidden = panel.style.display === 'none' || panel.style.display === '';

    if (isHidden) {
        panel.style.display = 'block';
        toggleBtn.classList.add('expanded');
        arrow.textContent = '▼';
    } else {
        panel.style.display = 'none';
        toggleBtn.classList.remove('expanded');
        arrow.textContent = '▶';
    }
}

function switchPromptTab(tabName) {
    var tabs = document.querySelectorAll('.prompt-tab');
    var panels = document.querySelectorAll('.prompt-tab-panel');
    tabs.forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-tab') === tabName);
    });
    panels.forEach(function(p) {
        p.classList.toggle('active', p.id === 'prompt-tab-' + tabName);
    });
}

async function savePrompts() {
    var systemPrompt = document.getElementById('prompt-system').value;

    var result = await apiRequest('POST', '/config/prompts', {
        system_prompt: systemPrompt
    });

    if (result.code === 200) {
        showToast(result.message || '提示词已保存，重启服务后生效', 'success');
    } else {
        showToast(result.message || '保存失败', 'error');
    }
}

async function resetPrompts() {
    showConfirm('恢复默认', '确定要恢复出厂默认提示词吗？当前修改将丢失。', async function() {
        var result = await apiRequest('POST', '/config/prompts/reset');

        if (result.code === 200) {
            showToast(result.message || '已恢复出厂默认提示词，重启服务后生效', 'success');
            var prompts = await apiRequest('GET', '/config/prompts');
            if (prompts.code === 200 && prompts.data) {
                document.getElementById('prompt-system').value = prompts.data.system_prompt || '';
            }
        } else {
            showToast(result.message || '恢复失败', 'error');
        }
    });
}

function _buildDimensionListText(dims) {
    return dims.map(function(d, i) {
        var valuesStr = d.values.join(', ');
        if (d.ai_prompt) {
            return (i + 1) + '. ' + d.label + '（' + d.name + '）: [' + valuesStr + '] — ' + d.ai_prompt;
        }
        return (i + 1) + '. ' + d.label + '（' + d.name + '）: [' + valuesStr + ']';
    }).join('\n');
}

function _buildDimensionSchema(dims) {
    var schema = {};
    dims.forEach(function(d) {
        if (d.values.length) {
            schema[d.name] = d.values.join('|') + '|null';
        } else {
            schema[d.name] = 'string|null';
        }
    });
    return schema;
}

async function previewFullPrompt() {
    var userPrompt = document.getElementById('prompt-system').value;
    var dims = await _loadPromptDimensions();

    var dimListText = _buildDimensionListText(dims);
    var dimSchema = _buildDimensionSchema(dims);

    var fullPart = '\n\n【维度判断】\n当前需要判断的维度：\n' +
        dimListText + '\n\n请严格按以下JSON格式返回，不要添加任何解释文字：\n';

    var schema = JSON.stringify({
        "title_cn": "string|null",
        "title_en": "string|null",
        "year": "int|null",
        "resolution": "string|null",
        "quality": "string|null",
        "language": "string|null",
        "type": "movie|tv",
        "season": "int|null",
        "episode": "int|null",
        "dimensions": dimSchema,
        "confidence": "float"
    }, null, 2);

    var full = userPrompt + fullPart + schema;

    var overlay = document.createElement('div');
    overlay.className = 'prompt-preview-overlay';
    overlay.innerHTML = '<div class="prompt-preview-dialog">' +
        '<div class="prompt-preview-header">' +
        '<span class="prompt-preview-title">LLM 直接刮削提示词预览</span>' +
        '<button class="prompt-preview-close" onclick="this.closest(\'.prompt-preview-overlay\').remove()">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
        '</button>' +
        '</div>' +
        '<div class="prompt-preview-body">' +
        '<pre class="prompt-preview-content">' + escapeHtml(full) + '</pre>' +
        '</div>' +
        '</div>';

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            overlay.remove();
        }
    });

    document.body.appendChild(overlay);
}

async function saveTmdbPrompts() {
    var systemPrompt = document.getElementById('prompt-tmdb').value;

    var result = await apiRequest('POST', '/config/prompts/tmdb', {
        system_prompt: systemPrompt
    });

    if (result.code === 200) {
        showToast(result.message || 'LLM+TMDB 提示词已保存，重启服务后生效', 'success');
    } else {
        showToast(result.message || '保存失败', 'error');
    }
}

async function resetTmdbPrompts() {
    showConfirm('恢复默认', '确定要恢复出厂默认 LLM+TMDB 提示词吗？当前修改将丢失。', async function() {
        var result = await apiRequest('POST', '/config/prompts/tmdb/reset');

        if (result.code === 200) {
            showToast(result.message || '已恢复出厂默认 LLM+TMDB 提示词，重启服务后生效', 'success');
            var prompts = await apiRequest('GET', '/config/prompts/tmdb');
            if (prompts.code === 200 && prompts.data) {
                document.getElementById('prompt-tmdb').value = prompts.data.system_prompt || '';
            }
        } else {
            showToast(result.message || '恢复失败', 'error');
        }
    });
}

async function previewTmdbFullPrompt() {
    var userPrompt = document.getElementById('prompt-tmdb').value;
    var dims = await _loadPromptDimensions();

    var dimListText = _buildDimensionListText(dims);
    var dimSchema = _buildDimensionSchema(dims);

    var fullPart = '\n\n【维度判断】\n当前需要判断的维度：\n' +
        dimListText + '\n\n请严格按以下JSON格式返回，不要添加任何解释文字：\n';

    var schema = JSON.stringify({
        "title_cn": "string|null",
        "title_en": "string|null",
        "year": "int|null",
        "resolution": "string|null",
        "quality": "string|null",
        "language": "string|null",
        "type": "movie|tv",
        "season": "int|null",
        "episode": "int|null",
        "dimensions": dimSchema,
        "confidence": "float"
    }, null, 2);

    var full = userPrompt + fullPart + schema;

    var overlay = document.createElement('div');
    overlay.className = 'prompt-preview-overlay';
    overlay.innerHTML = '<div class="prompt-preview-dialog">' +
        '<div class="prompt-preview-header">' +
        '<span class="prompt-preview-title">LLM+TMDB 刮削提示词预览</span>' +
        '<button class="prompt-preview-close" onclick="this.closest(\'.prompt-preview-overlay\').remove()">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
        '</button>' +
        '</div>' +
        '<div class="prompt-preview-body">' +
        '<h4 style="color:var(--primary-color);margin:0 0 8px 0;">▶ LLM+TMDB 刮削提示词</h4>' +
        '<pre class="prompt-preview-content">' + escapeHtml(full) + '</pre>' +
        '</div>' +
        '</div>';

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            overlay.remove();
        }
    });

    document.body.appendChild(overlay);
}

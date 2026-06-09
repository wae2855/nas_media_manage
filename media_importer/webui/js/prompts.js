var _promptDimensionsCache = null;

async function _loadPromptDimensions() {
    if (_promptDimensionsCache) return _promptDimensionsCache;
    try {
        var result = await apiRequest('GET', '/dimensions/enabled');
        if (result.code === 200 && result.data && result.data.dimensions) {
            _promptDimensionsCache = result.data.dimensions
                .filter(function(d) {
                    return d.source_type === 'ai' || (d.source_type === 'ai+provider' && d.ai_prompt);
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
            { name: 'media_type', label: '影视类型', values: ['movie', 'tv'], ai_prompt: '请判断这是电影（movie）还是电视剧（tv）。判断依据：如果文件名中包含季集编号（如S01E01、S2E03等格式），则为电视剧（tv）；如果是完整独立的影视故事，则为电影（movie）。电视电影/网络电影仍归为movie。' },
            { name: 'documentary', label: '是否纪录片', values: ['true', 'false'], ai_prompt: '请判断是否为纪录片（true/false）。纪录片是以真实事件、人物、历史、社会等为主题的非虚构影视作品，包括自然纪录片（如《地球脉动》）、历史纪录片、社会纪录片、科学纪录片等。TMDB genres 包含 Documentary (id=99) 则为 true；如 TMDB 未标注，请根据标题和简介判断。真人出演+虚构剧情的作品（如《辛德勒的名单》）应选 false。' },
            { name: 'restricted_level', label: '限制级分类', values: ['0-6', '7-12', '13-16', '17+'], ai_prompt: '请判断该影视内容的年龄分级，从以下选项中选择最匹配的一个：0-6（幼儿/儿童）、7-12（家庭向）、13-16（青少年向）、17+（成人内容）。优先使用 TMDB release_dates 中的官方分级；如 TMDB 未提供，请联网搜索后判断。' },
            { name: 'animation', label: '是否动漫', values: ['true', 'false'], ai_prompt: '请判断是否为动漫/动画作品（true/false）。以动画/手绘/CG形式制作的作品均为 true，包括日本动画、中国动画、欧美动画电影等。TMDB genres 包含 Animation (id=16) 则为 true。真人拍摄+少量CG特效的作品（如漫威电影）不算动画。' },
            { name: 'region', label: '地区', values: ['us', 'cn', 'hk', 'tw', 'jp', 'kr', 'gb', 'fr', 'de', 'it', 'es', 'in', 'other'], ai_prompt: '请判断该影视作品的主要制片国家或地区，从以下选项中选择：us（美国）、cn（中国大陆）、hk（中国香港）、tw（中国台湾）、jp（日本）、kr（韩国）、gb（英国）、fr（法国）、de（德国）、it（意大利）、es（西班牙）、in（印度）、other（其他）。' },
            { name: 'origin_lang', label: '原始语言', values: ['zh', 'en', 'ja', 'ko', 'other'], ai_prompt: '请判断该影视作品的原始语言，从以下选项中选择：zh（中文）、en（英语）、ja（日语）、ko（韩语）、other（其他语言）。' },
            { name: 'broad_genre', label: '题材类型', values: ['horror_mystery', 'scifi_fantasy', 'war', 'action_adventure', 'comedy', 'drama_romance', 'documentary', 'music', 'kids', 'tv_show', 'other'], ai_prompt: '请判断该影视作品的主要类型，从以下选项中选择风格最鲜明突出的一个：horror_mystery（恐怖/悬疑）、scifi_fantasy（科幻/奇幻）、war（战争/军事）、action_adventure（动作/冒险）、comedy（喜剧）、drama_romance（剧情/情感）、documentary（纪录/纪实）、music（音乐/演出）、kids（儿童/家庭）、tv_show（电视节目）、other（其他）。' }
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

    var isHidden = !panel.classList.contains('open');

    if (isHidden) {
        panel.classList.add('open');
        toggleBtn.classList.add('expanded');
        arrow.textContent = '▼';
    } else {
        panel.classList.remove('open');
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
        '<button class="prompt-preview-close" type="button">' +
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
    overlay.querySelector('.prompt-preview-close').addEventListener('click', function() {
        overlay.remove();
    });

    document.body.appendChild(overlay);
}

function showSystemScrapeModal() {
    var existing = document.getElementById('scrape-preview-modal');
    if (existing) existing.remove();

    var modal = document.createElement('div');
    modal.id = 'scrape-preview-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML =
        '<div class="modal" style="max-width:960px;width:95%;">' +
            '<div class="modal-header">' +
                '<h3>刮削与置信度计算</h3>' +
                '<button class="modal-close" type="button">&times;</button>' +
            '</div>' +
            '<div class="modal-body">' +
                '<div style="display:flex;gap:8px;margin-bottom:16px;">' +
                    '<input type="text" id="scrape-preview-filename" placeholder="输入视频文件名，如 Inception.2010.1080p.BluRay.mkv" class="form-input" style="flex:1;">' +
                    '<button class="btn btn-primary" id="btn-scrape-preview" type="button">开始刮削</button>' +
                '</div>' +
                '<div id="scrape-preview-result"></div>' +
            '</div>' +
        '</div>';
    document.body.appendChild(modal);
    document.getElementById('scrape-preview-filename').focus();
    modal.querySelector('.modal-close').addEventListener('click', closeScrapePreviewModal);
    modal.querySelector('#btn-scrape-preview').addEventListener('click', doScrapePreview);
}

function closeScrapePreviewModal() {
    var modal = document.getElementById('scrape-preview-modal');
    if (modal) modal.remove();
}

async function doScrapePreview() {
    var filename = document.getElementById('scrape-preview-filename').value.trim();
    var resultEl = document.getElementById('scrape-preview-result');
    var btn = document.getElementById('btn-scrape-preview');

    if (!filename) {
        resultEl.innerHTML = '<div style="text-align:center;padding:16px;color:var(--error-color,#ef4444);">请输入文件名</div>';
        return;
    }

    btn.disabled = true;
    resultEl.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-secondary);">刮削中，请稍候...</div>';

    var result = await apiRequest('POST', '/scrape/preview', { filename: filename });

    btn.disabled = false;

    if (result.code !== 200 || !result.data) {
        resultEl.innerHTML = '<div style="text-align:center;padding:16px;color:var(--error-color,#ef4444);">' + escapeHtml(result.message || '请求失败') + '</div>';
        return;
    }

    var data = result.data;
    var html = '';

    html += '<div style="margin-bottom:12px;padding:10px;background:var(--bg-secondary);border-radius:8px;font-size:13px;">';
    html += '<strong>文件名清洗:</strong> ' + escapeHtml(data.clean_result.clean_title);
    if (data.clean_result.year) html += ' <span style="color:var(--text-secondary);">(' + data.clean_result.year + ')</span>';
    if (data.clean_result.season) html += ' <span style="color:var(--primary-color);">S' + data.clean_result.season + 'E' + (data.clean_result.episode || '?') + '</span>';
    html += '</div>';

    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">';

    html += '<div class="scrape-preview-col">';
    html += '<h4 style="margin:0 0 8px 0;font-size:14px;color:var(--primary-color);">纯 AI 刮削';
    if (data.ai_only_elapsed) html += ' <span style="font-size:11px;color:var(--text-secondary);">(' + data.ai_only_elapsed + 's)</span>';
    html += '</h4>';
    html += _renderScrapeResultCard(data.ai_only);
    html += '</div>';

    html += '<div class="scrape-preview-col">';
    html += '<h4 style="margin:0 0 8px 0;font-size:14px;color:var(--primary-color);">Provider+AI 刮削';
    if (data.provider_ai_elapsed) html += ' <span style="font-size:11px;color:var(--text-secondary);">(' + data.provider_ai_elapsed + 's)</span>';
    html += '</h4>';
    html += _renderScrapeResultCard(data.provider_ai);
    html += '</div>';

    html += '</div>';

    if (data.provider_ai && data.provider_ai.scrape_trace) {
        var traceJson = escapeHtml(JSON.stringify(data.provider_ai.scrape_trace));
        html += '<div style="margin-top:12px;text-align:center;">';
        html += '<button class="btn btn-secondary btn-sm" type="button" data-confidence-detail-action="open" data-trace="' + traceJson + '" data-filename="' + escapeHtml(filename) + '">查看 Provider+AI 置信度计算过程</button>';
        html += '</div>';
    }
    if (data.ai_only && data.ai_only.scrape_trace) {
        var aiTraceJson = escapeHtml(JSON.stringify(data.ai_only.scrape_trace));
        html += '<div style="margin-top:8px;text-align:center;">';
        html += '<button class="btn btn-secondary btn-sm" type="button" data-confidence-detail-action="open" data-trace="' + aiTraceJson + '" data-filename="' + escapeHtml(filename) + '">查看纯AI置信度计算过程</button>';
        html += '</div>';
    }

    resultEl.innerHTML = html;
}

function _renderScrapeResultCard(result) {
    if (!result) return '<div style="padding:12px;color:var(--text-secondary);font-size:13px;">未执行</div>';
    if (result.error) return '<div style="padding:12px;font-size:13px;">' +
        '<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--warning-color,#f59e0b)" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' +
        '<span style="color:var(--warning-color,#f59e0b);font-weight:500;">未完成</span></div>' +
        '<div style="color:var(--text-secondary);font-size:12px;line-height:1.6;">' + escapeHtml(result.error) + '</div></div>';

    var html = '<div style="padding:10px;background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:8px;font-size:13px;">';

    html += '<div style="margin-bottom:6px;"><strong>标题:</strong> ' + escapeHtml(result.title_cn || result.title_en || '-') + '</div>';
    if (result.title_en && result.title_cn && result.title_en !== result.title_cn) {
        html += '<div style="margin-bottom:6px;color:var(--text-secondary);"><strong>英文:</strong> ' + escapeHtml(result.title_en) + '</div>';
    }
    html += '<div style="margin-bottom:6px;"><strong>年份:</strong> ' + (result.year || '-') + '</div>';
    html += '<div style="margin-bottom:6px;"><strong>类型:</strong> ' + (result.type || '-') + '</div>';

    var confidence = result.confidence;
    if (confidence !== undefined) {
        var confColor = confidence >= 0.8 ? 'var(--success-color,#22c55e)' : (confidence >= 0.5 ? 'var(--warning-color,#f59e0b)' : 'var(--error-color,#ef4444)');
        var traceJson = result.scrape_trace ? escapeHtml(JSON.stringify(result.scrape_trace)) : '';
        html += '<div style="margin-bottom:6px;"><strong>置信度:</strong> <span class="conf-clickable" style="color:' + confColor + ';font-weight:600;cursor:pointer;text-decoration:underline dotted;" data-confidence-detail-action="open" data-trace="' + traceJson + '" data-filename="">' + (typeof confidence === 'number' ? confidence.toFixed(3) : confidence) + '</span></div>';
    }

    var dims = result.dimensions;
    if (dims) {
        html += '<div style="margin-top:8px;"><strong>维度:</strong></div>';
        html += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">';
        if (typeof dims === 'object') {
            for (var key in dims) {
                var val = dims[key];
                var displayVal = (typeof val === 'object' && val !== null) ? (val.value || JSON.stringify(val)) : val;
                html += '<span style="padding:2px 6px;background:rgba(59,130,246,0.1);border-radius:3px;font-size:11px;">' + escapeHtml(key) + '=' + escapeHtml(String(displayVal)) + '</span>';
            }
        }
        html += '</div>';
    }

    html += '</div>';
    return html;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function saveTmdbPrompts() {
    var systemPrompt = document.getElementById('prompt-tmdb').value;

    var result = await apiRequest('POST', '/providers/tmdb/prompts', {
        system_prompt: systemPrompt
    });

    if (result.code === 200) {
        showToast(result.message || 'LLM+Provider 提示词已保存，重启服务后生效', 'success');
    } else {
        showToast(result.message || '保存失败', 'error');
    }
}

async function resetTmdbPrompts() {
    showConfirm('恢复默认', '确定要恢复出厂默认 LLM+Provider 提示词吗？当前修改将丢失。', async function() {
        var result = await apiRequest('POST', '/providers/tmdb/prompts/reset', {});

        if (result.code === 200) {
            showToast(result.message || '已恢复出厂默认 LLM+Provider 提示词，重启服务后生效', 'success');
            var prompts = await apiRequest('GET', '/providers/tmdb/prompts');
            if (prompts.code === 200 && prompts.data) {
                var textarea = document.getElementById('prompt-tmdb');
                if (textarea) textarea.value = prompts.data.system_prompt || '';
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
        '<span class="prompt-preview-title">LLM+Provider 刮削提示词预览</span>' +
        '<button class="prompt-preview-close" type="button">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
        '</button>' +
        '</div>' +
        '<div class="prompt-preview-body">' +
        '<h4 style="color:var(--primary-color);margin:0 0 8px 0;">▶ LLM+Provider 刮削提示词</h4>' +
        '<pre class="prompt-preview-content">' + escapeHtml(full) + '</pre>' +
        '</div>' +
        '</div>';

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            overlay.remove();
        }
    });
    overlay.querySelector('.prompt-preview-close').addEventListener('click', function() {
        overlay.remove();
    });

    document.body.appendChild(overlay);
}

document.addEventListener('click', function(event) {
    var detail = event.target.closest('[data-confidence-detail-action="open"]');
    if (!detail) return;
    var trace = detail.getAttribute('data-trace');
    var filename = detail.getAttribute('data-filename') || '';
    if (!trace || typeof showConfidenceDetailModal !== 'function') return;
    event.preventDefault();
    showConfidenceDetailModal(JSON.parse(trace), filename);
});

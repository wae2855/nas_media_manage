function _confColor(value) {
    if (value >= 0.8) return '#22C55E';
    if (value >= 0.5) return '#F59E0B';
    if (value >= 0.3) return '#F97316';
    return '#EF4444';
}

function _confLevel(value) {
    if (value >= 0.8) return '自动通过';
    if (value >= 0.5) return '需确认';
    if (value >= 0.3) return '需审核';
    return '失败';
}

function _sourceTag(source) {
    if (source === 'tmdb') return '<span style="display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(139,92,246,0.12);color:#8B5CF6;font-weight:600">TMDB</span>';
    if (source === 'ai') return '<span style="display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(239,68,68,0.1);color:#EF4444;font-weight:600">AI</span>';
    if (source === 'file') return '<span style="display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(34,197,94,0.1);color:#22C55E;font-weight:600">FILE</span>';
    return '<span style="display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(148,163,184,0.1);color:#94A3B8;font-weight:600">缺失</span>';
}

function closeConfidenceDetailModal() {
    var overlay = document.querySelector('.conf-detail-overlay');
    if (overlay) overlay.remove();
}

function _buildTraceStep(num, title, tag, color, contentHtml, isLast) {
    var lineStyle = isLast ? 'background:transparent' : 'background:' + color + '30';
    return '<div class="conf-trace-step">' +
        '<div class="conf-trace-rail">' +
            '<div class="conf-trace-dot" style="background:' + color + '18;color:' + color + '">' + num + '</div>' +
            '<div class="conf-trace-line" style="' + lineStyle + '"></div>' +
        '</div>' +
        '<div class="conf-trace-content">' +
            '<div class="conf-step-header">' +
                '<span style="font-size:15px;font-weight:700;color:' + color + '">' + escapeHtml(title) + '</span>' +
                '<span class="conf-step-tag" style="background:' + color + '18;color:' + color + '">' + tag + '</span>' +
            '</div>' +
            contentHtml +
        '</div>' +
    '</div>';
}

function showConfidenceDetailModal(traceData, filename) {
    var existing = document.querySelector('.conf-detail-overlay');
    if (existing) existing.remove();

    var trace = traceData;
    if (typeof trace === 'string') {
        try { trace = JSON.parse(trace); } catch(e) { return; }
    }
    if (!trace || typeof trace !== 'object') return;

    var mode = trace.mode || 'provider_ai';
    var isProviderAi = mode === 'provider_ai' || mode === 'tmdb_ai';
    var cc = trace.confidence_calc;
    var finalConf = trace.final_confidence;
    if (finalConf === undefined && cc) {
        finalConf = cc.final_confidence;
    }
    var confColor = finalConf !== undefined ? _confColor(finalConf) : '#94A3B8';
    var confLevel = finalConf !== undefined ? _confLevel(finalConf) : '-';
    var confDisplay = finalConf !== undefined ? finalConf.toFixed(3) : '-';

    var searchEnhanced = trace.search_enhanced;
    var searchBadgeInline = '';
    if (searchEnhanced === true) {
        searchBadgeInline = '<span style="font-size:11px;padding:2px 8px;border-radius:999px;background:rgba(6,182,212,0.15);color:#06B6D4;font-weight:600;margin-left:6px">🔍 AI联网搜索增强</span>';
    } else if (searchEnhanced === false) {
        searchBadgeInline = '<span style="font-size:11px;padding:2px 8px;border-radius:999px;background:rgba(148,163,184,0.12);color:#94A3B8;font-weight:600;margin-left:6px">📴 纯本地分析</span>';
    }

    var steps = [];
    var fc = trace.filename_clean;

    steps.push({
        title: '文件名输入',
        tag: 'INPUT',
        color: '#06B6D4',
        html: '<div class="conf-detail-card">' +
            '<div class="conf-kv"><span class="conf-k">原始文件名</span><span class="conf-v">' + escapeHtml(fc ? (fc.original || '-') : (filename || '-')) + '</span></div>' +
        '</div>'
    });

    var cleanTitle = fc ? (fc.clean_title || '-') : '-';
    var cleanYear = fc ? fc.year : null;
    var cleanSeason = fc ? fc.season : null;
    var cleanEpisode = fc ? fc.episode : null;
    var cleanMethod = fc ? (fc.clean_method || 'regex') : 'regex';
    var removedItems = fc && fc.removed_items ? fc.removed_items : [];
    var removedStr = removedItems.length > 0 ? removedItems.join(' ') : '-';

    steps.push({
        title: '规则清洗',
        tag: 'REGEX',
        color: '#F59E0B',
        html: '<div class="conf-detail-card">' +
            '<div class="conf-kv"><span class="conf-k">清洗方法</span><span class="conf-v">' + escapeHtml(cleanMethod) + '</span></div>' +
            '<div class="conf-kv"><span class="conf-k">去除项</span><span class="conf-v">' + escapeHtml(removedStr) + '</span></div>' +
            '<div class="conf-kv"><span class="conf-k">clean_title</span><span class="conf-v" style="color:#06B6D4;font-weight:600">' + escapeHtml(cleanTitle) + '</span></div>' +
            '<div class="conf-kv"><span class="conf-k">year</span><span class="conf-v" style="color:#06B6D4;font-weight:600">' + (cleanYear !== null && cleanYear !== undefined ? escapeHtml(String(cleanYear)) : '—') + '</span></div>' +
            '<div class="conf-kv"><span class="conf-k">season / episode</span><span class="conf-v">' + (cleanSeason !== null && cleanSeason !== undefined ? 'S' + cleanSeason : '—') + ' / ' + (cleanEpisode !== null && cleanEpisode !== undefined ? 'E' + cleanEpisode : '—') + '</span></div>' +
        '</div>'
    });

    if (trace.ai_clean) {
        steps.push({
            title: 'AI 辅助清洗',
            tag: 'AI',
            color: '#F59E0B',
            html: '<div class="conf-detail-card">' +
                '<div class="conf-kv"><span class="conf-k">AI 提取标题</span><span class="conf-v" style="color:#06B6D4;font-weight:600">' + escapeHtml(trace.ai_clean.clean_title || '-') + '</span></div>' +
                '<div class="conf-kv"><span class="conf-k">方法</span><span class="conf-v">' + escapeHtml(trace.ai_clean.method || 'ai') + '</span></div>' +
            '</div>'
        });
    }

    if (isProviderAi) {
        var ts = trace.provider_search || trace.tmdb_search;
        if (ts) {
            var providerName = trace.provider_type || 'TMDb';
            var providerLabel = providerName === 'tmdb' ? 'TMDb' : providerName.toUpperCase();
            var fallbackBadge = ts.fallback_used ? ' <span style="font-size:11px;padding:2px 6px;border-radius:4px;background:rgba(246,193,119,0.12);color:#F59E0B;font-weight:600">回退</span>' : '';
            steps.push({
                title: providerLabel + ' 搜索',
                tag: providerLabel,
                color: '#8B5CF6',
                html: '<div class="conf-detail-card">' +
                    '<div class="conf-kv"><span class="conf-k">搜索词</span><span class="conf-v">' + escapeHtml(ts.query || '-') + (fc && fc.year ? ' + year=' + fc.year : '') + '</span></div>' +
                    '<div class="conf-kv"><span class="conf-k">total_results</span><span class="conf-v" style="color:#06B6D4;font-weight:600">' + (ts.total_results !== undefined ? ts.total_results : '-') + '</span></div>' +
                    '<div class="conf-kv"><span class="conf-k">匹配结果</span><span class="conf-v">' + escapeHtml(ts.selected_title || '-') + (ts.selected_year ? ' (' + ts.selected_year + ')' : '') + fallbackBadge + '</span></div>' +
                    (ts.selected_original_title ? '<div class="conf-kv"><span class="conf-k">original_title</span><span class="conf-v">' + escapeHtml(ts.selected_original_title) + '</span></div>' : '') +
                '</div>'
            });
        }

        if (cc && cc.search_conf && typeof cc.search_conf === 'object') {
            var sc = cc.search_conf;
            steps.push({
                title: '标题匹配分 T',
                tag: 'CALC',
                color: '#A78BFA',
                html: '<div class="conf-detail-card">' +
                    '<div class="conf-kv"><span class="conf-k">匹配级别</span><span class="conf-v" style="color:#06B6D4;font-weight:600">' + escapeHtml(sc.T_reason || '') + '</span></div>' +
                    (ts && ts.year_match !== undefined ? '<div class="conf-kv"><span class="conf-k">年份比较</span><span class="conf-v">' + (ts.year_match === true ? '文件名年份 = 元数据年份 ✓' : ts.year_match === false ? '文件名年份 ≠ 元数据年份 ✗' : '无年份信息') + '</span></div>' : '') +
                    '<div class="conf-kv"><span class="conf-k">T 值</span><span class="conf-v" style="color:' + _confColor(sc.T || 0) + ';font-weight:600">' + (sc.T !== undefined ? sc.T.toFixed(3) : '-') + '</span></div>' +
                    '<div style="font-size:11px;color:var(--text-secondary);margin-top:4px;line-height:1.4">T值含义：1.0=精确匹配+年份一致(L1)，0.9=精确匹配+有季号(L2)，0.7=精确匹配无年份(L3)，0.4=精确匹配年份不同(L4)，&lt;0.7=模糊匹配(L5/L6)</div>' +
                '</div>'
            });

            var rHtml = '<div class="conf-detail-card">' +
                '<div class="conf-kv"><span class="conf-k">元数据搜索结果数 N</span><span class="conf-v">' + (sc.total_results !== undefined ? sc.total_results : '-') + '</span></div>' +
                '<div class="conf-kv"><span class="conf-k">R 基础公式</span><span class="conf-v">' + escapeHtml(sc.R_formula || '') + '</span></div>';
            if (sc.R_base !== undefined) {
                rHtml += '<div class="conf-kv"><span class="conf-k">R 基础值(按结果数)</span><span class="conf-v" style="color:var(--text-secondary)">' + sc.R_base.toFixed(4) + '</span></div>';
            }
            rHtml += '<div class="conf-kv"><span class="conf-k">R 最终值</span><span class="conf-v" style="color:' + _confColor(sc.R || 0) + ';font-weight:600">' + (sc.R !== undefined ? sc.R.toFixed(4) : '-') + '</span></div>';
            if (sc.R_adjusted) {
                rHtml += '<div style="font-size:11px;color:#22C55E;margin-top:4px;line-height:1.4;background:rgba(34,197,94,0.08);padding:4px 8px;border-radius:4px">⚡ T值较高，R已动态调整：' + escapeHtml(sc.R_adjust_reason || '') + '</div>';
            }
            rHtml += '<div class="conf-kv" style="margin-top:6px"><span class="conf-k" style="font-weight:600">search_conf = T × R</span><span class="conf-v" style="color:' + _confColor(sc.search_conf || 0) + ';font-weight:600;font-size:14px">' + (sc.T !== undefined ? sc.T.toFixed(3) : '?') + ' × ' + (sc.R !== undefined ? sc.R.toFixed(4) : '?') + ' = ' + (sc.search_conf !== undefined ? sc.search_conf.toFixed(4) : '-') + '</span></div>';
            rHtml += '<div style="font-size:11px;color:var(--text-secondary);margin-top:4px;line-height:1.4">R值含义：搜索结果越多R越小(匹配越不确定)。但当T值高(标题匹配好)时，R会动态提升——匹配质量越高，结果数惩罚越轻。</div>';
            rHtml += '</div>';
            steps.push({
                title: '搜索置信度',
                tag: 'CALC',
                color: '#A78BFA',
                html: rHtml
            });
        } else if (cc && (cc.T !== undefined || cc.R !== undefined)) {
            steps.push({
                title: '搜索置信度',
                tag: 'CALC',
                color: '#A78BFA',
                html: '<div class="conf-detail-card">' +
                    '<div class="conf-kv"><span class="conf-k">T 值</span><span class="conf-v" style="color:' + _confColor(cc.T || 0) + ';font-weight:600">' + (cc.T !== undefined ? cc.T.toFixed(3) : '-') + '</span></div>' +
                    '<div class="conf-kv"><span class="conf-k">R 值</span><span class="conf-v" style="color:' + _confColor(cc.R || 0) + ';font-weight:600">' + (cc.R !== undefined ? cc.R.toFixed(3) : '-') + '</span></div>' +
                    (cc.T_reason ? '<div class="conf-kv"><span class="conf-k">匹配说明</span><span class="conf-v">' + escapeHtml(cc.T_reason) + '</span></div>' : '') +
                '</div>'
            });
        }
    } else {
        var pfr = trace.provider_fallback_reasons;
        if (pfr && pfr.length > 0) {
            var fallbackHtml = '<div class="conf-detail-card">';
            fallbackHtml += '<div style="font-size:12px;font-weight:600;color:#F59E0B;margin-bottom:6px">⚠ 元数据源降级说明</div>';
            for (var fi = 0; fi < pfr.length; fi++) {
                var fp = pfr[fi];
                var fpIcon = '';
                var fpIconColor = '#94A3B8';
                if (fp.status === 'error') { fpIcon = '✗'; fpIconColor = '#EF4444'; }
                else if (fp.status === 'no_results') { fpIcon = '∅'; fpIconColor = '#F59E0B'; }
                else if (fp.status === 'below_threshold') { fpIcon = '↓'; fpIconColor = '#F59E0B'; }
                else if (fp.status === 'details_error') { fpIcon = '⚠'; fpIconColor = '#EF4444'; }
                else if (fp.status === 'not_configured') { fpIcon = '—'; fpIconColor = '#94A3B8'; }
                else { fpIcon = '?'; fpIconColor = '#94A3B8'; }
                var fpName = fp.display_name || fp.provider_type || '未知';
                fallbackHtml += '<div class="conf-kv">' +
                    '<span class="conf-k"><span style="color:' + fpIconColor + ';font-weight:700;margin-right:4px">' + fpIcon + '</span>' + escapeHtml(fpName) + '</span>' +
                    '<span class="conf-v" style="color:var(--text-secondary)">' + escapeHtml(fp.reason || '未知原因') + '</span>' +
                '</div>';
            }
            fallbackHtml += '<div style="font-size:11px;color:var(--text-secondary);margin-top:6px;line-height:1.4;background:rgba(245,158,11,0.08);padding:4px 8px;border-radius:4px">所有元数据源均不可用，已降级为纯 AI 刮削模式</div>';
            fallbackHtml += '</div>';
            steps.push({
                title: 'Provider 降级说明',
                tag: 'WARN',
                color: '#F59E0B',
                html: fallbackHtml
            });
        }

        if (cc && cc.ai_cap) {
            var aiCap = cc.ai_cap;
            steps.push({
                title: 'AI 置信度上限',
                tag: 'AI',
                color: '#A78BFA',
                html: '<div class="conf-detail-card">' +
                    '<div class="conf-kv"><span class="conf-k">上限值</span><span class="conf-v" style="color:' + _confColor(aiCap.cap || 0) + ';font-weight:600">' + (aiCap.cap !== undefined ? aiCap.cap.toFixed(3) : '-') + '</span></div>' +
                    (aiCap.reason ? '<div class="conf-kv"><span class="conf-k">原因</span><span class="conf-v">' + escapeHtml(aiCap.reason) + '</span></div>' : '') +
                    '<div style="margin-top:4px">' + searchBadgeInline + '</div>' +
                '</div>'
            });
        } else if (cc && cc.objective_cap !== undefined) {
            steps.push({
                title: 'AI 置信度上限',
                tag: 'AI',
                color: '#A78BFA',
                html: '<div class="conf-detail-card">' +
                    '<div class="conf-kv"><span class="conf-k">上限值 (objective_cap)</span><span class="conf-v" style="color:' + _confColor(cc.objective_cap) + ';font-weight:600">' + cc.objective_cap.toFixed(3) + '</span></div>' +
                    '<div style="font-size:11px;color:var(--text-secondary);margin-top:4px;line-height:1.4">基于清洗标题与 AI 返回标题的相似度计算，作为纯 AI 模式的置信度上限</div>' +
                    '<div style="margin-top:4px">' + searchBadgeInline + '</div>' +
                '</div>'
            });
        }
    }

    if (cc && cc.data_gate) {
        var dg = cc.data_gate;
        var dimTableHtml = '<div class="conf-detail-card"><div class="conf-dim-table">' +
            '<div class="conf-dim-row conf-dim-header">' +
                '<span>维度</span><span>值</span><span>来源</span><span>信任</span><span>说明</span>' +
            '</div>';

        if (dg.dimensions && typeof dg.dimensions === 'object') {
            var dimLabels = {
                'media_type': '影视类型', 'documentary': '是否纪录片', 'restricted_level': '限制级分类',
                'animation': '是否动漫', 'region': '地区', 'origin_lang': '原始语言',
                'resolution_tier': '分辨率等级', 'broad_genre': '题材类型'
            };
            for (var dk in dg.dimensions) {
                var dim = dg.dimensions[dk];
                var dimValue = dim.value !== undefined ? String(dim.value) : '-';
                var dimSource = dim.source || 'missing';
                var dimTrusted = dim.trusted;
                var trustIcon = dimTrusted === true
                    ? '<span style="color:#22C55E;font-weight:700">✓</span>'
                    : '<span style="color:#EF4444;font-weight:700">✗</span>';
                var dimDetail = dim.detail ? escapeHtml(String(dim.detail)) : '—';
                var dimLabel = dimLabels[dk] || dk;
                var skipped = dim.skipped === true;
                dimTableHtml += '<div class="conf-dim-row' + (skipped ? ' dim-skipped' : '') + '">' +
                    '<span>' + escapeHtml(dimLabel) + '<span style="font-size:10px;color:var(--text-secondary);margin-left:2px">(' + escapeHtml(dk) + ')</span></span>' +
                    '<span>' + escapeHtml(dimValue) + '</span>' +
                    '<span>' + _sourceTag(dimSource) + '</span>' +
                    '<span>' + trustIcon + '</span>' +
                    '<span style="font-size:12px;color:var(--text-secondary)">' + dimDetail + '</span>' +
                '</div>';
            }
        }

        dimTableHtml += '</div>';
        dimTableHtml += '<div style="font-size:11px;color:var(--text-secondary);margin-top:6px;line-height:1.4">数据门控(data_gate)：所有维度来源可信则=1，任一来源不可信则=0，触发需审核</div>';

        if (isProviderAi && searchBadgeInline) {
            dimTableHtml += '<div style="margin-top:4px">' + searchBadgeInline + '</div>';
        }

        if (dg.gate_blocked && dg.gate_blocked.length > 0) {
            dimTableHtml += '<div style="margin-top:8px;padding:8px 10px;border-radius:6px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2)">';
            dimTableHtml += '<div style="font-size:12px;font-weight:600;color:#EF4444;margin-bottom:4px">⚠ 被拦截维度</div>';
            for (var bi = 0; bi < dg.gate_blocked.length; bi++) {
                var block = dg.gate_blocked[bi];
                dimTableHtml += '<div style="font-size:12px;color:var(--text-secondary);line-height:1.6">' +
                    '维度: <b style="color:var(--text-primary)">' + escapeHtml(block.dim_name || '-') + '</b>' +
                    ' · 来源: <b style="color:var(--text-primary)">' + escapeHtml(block.source || '-') + '</b>' +
                    ' · 原因: <b style="color:var(--text-primary)">' + escapeHtml(block.reason || '-') + '</b>' +
                '</div>';
            }
            dimTableHtml += '</div>';
        }

        dimTableHtml += '</div>';

        steps.push({
            title: '数据门控',
            tag: 'CALC',
            color: '#3B82F6',
            html: dimTableHtml
        });
    }

    if (cc && cc.final_confidence !== undefined) {
        var fConf = cc.final_confidence;
        var searchConfVal = (cc.search_conf && cc.search_conf.search_conf !== undefined) ? cc.search_conf.search_conf : 0;
        var aiCapVal = (cc.ai_cap && cc.ai_cap.cap !== undefined) ? cc.ai_cap.cap : (cc.objective_cap !== undefined ? cc.objective_cap : 0);
        var dataGateRaw = cc.data_gate;
        var dataGateVal = 0;
        if (dataGateRaw !== undefined) {
            if (typeof dataGateRaw === 'object') {
                dataGateVal = dataGateRaw.value !== undefined ? dataGateRaw.value : 0;
            } else {
                dataGateVal = dataGateRaw;
            }
        }

        var calcFlowHtml = '<div class="conf-detail-card"><div class="conf-calc-flow">';

        if (isProviderAi && searchConfVal > 0) {
            calcFlowHtml += '<span class="conf-calc-num" title="搜索置信度">' + searchConfVal.toFixed(4) + '</span>';
            calcFlowHtml += '<span class="conf-calc-op" title="乘以">×</span>';
        } else if (!isProviderAi && aiCapVal > 0) {
            calcFlowHtml += '<span class="conf-calc-num" title="AI置信度上限">AI上限 ' + aiCapVal.toFixed(4) + '</span>';
            calcFlowHtml += '<span class="conf-calc-op" title="乘以">×</span>';
        }
        calcFlowHtml += '<span class="conf-calc-num" title="数据门控">' + dataGateVal.toFixed(4) + '</span>';
        if (dataGateVal === 0) {
            calcFlowHtml += '<span class="conf-calc-op" style="color:#EF4444;font-weight:700">门控拦截</span>';
        }
        calcFlowHtml += '<span class="conf-calc-op">=</span>';

        calcFlowHtml += '<span class="conf-calc-result" style="color:' + _confColor(fConf) + '">' + fConf.toFixed(4) + '</span>';
        calcFlowHtml += '</div>';

        var decisionColor = fConf >= 0.8 ? '#22C55E' : fConf >= 0.5 ? '#3B82F6' : fConf >= 0.3 ? '#F59E0B' : '#EF4444';
        var decisionClass = fConf >= 0.8 ? 'conf-decision-pass' : fConf >= 0.5 ? 'conf-decision-confirm' : fConf >= 0.3 ? 'conf-decision-review' : 'conf-decision-fail';
        calcFlowHtml += '<div class="conf-decision-badge ' + decisionClass + '" style="background:' + decisionColor + '15;color:' + decisionColor + ';border:1px solid ' + decisionColor + '30">' + fConf.toFixed(4) + ' · ' + _confLevel(fConf) + '</div>';

        var thresholdDesc = '阈值：≥0.8 自动通过，≥0.5 需确认，≥0.3 需审核，<0.3 失败';
        calcFlowHtml += '<div style="font-size:11px;color:var(--text-secondary);margin-top:6px;line-height:1.4">' + thresholdDesc + '</div>';

        if (cc.llm_raw_confidence !== undefined) {
            calcFlowHtml += '<div class="conf-kv" style="margin-top:6px"><span class="conf-k">LLM 原始置信度</span><span class="conf-v">' + cc.llm_raw_confidence.toFixed(3) + '</span></div>';
        }

        calcFlowHtml += '</div>';

        steps.push({
            title: '最终置信度',
            tag: 'RESULT',
            color: _confColor(fConf),
            html: calcFlowHtml
        });
    }

    if (cc && cc.gate_blocked && cc.gate_blocked.length > 0) {
        var gateBlocked = cc.gate_blocked;
        var gateHtml = '<div class="conf-detail-card">';
        gateHtml += '<div style="font-size:12px;font-weight:600;color:#EF4444;margin-bottom:6px">⚠ 以下维度被门控拦截：</div>';
        for (var gi = 0; gi < gateBlocked.length; gi++) {
            var gb = gateBlocked[gi];
            gateHtml += '<div class="conf-kv"><span class="conf-k">维度</span><span class="conf-v" style="color:#EF4444;font-weight:600">' + escapeHtml(gb.dim_name || '-') + '</span></div>';
            gateHtml += '<div class="conf-kv"><span class="conf-k">来源</span><span class="conf-v" style="color:#EF4444;font-weight:600">' + escapeHtml(gb.source || '-') + '</span></div>';
            gateHtml += '<div class="conf-kv"><span class="conf-k">原因</span><span class="conf-v" style="color:#EF4444;font-weight:600">' + escapeHtml(gb.reason || '-') + '</span></div>';
            if (gi < gateBlocked.length - 1) {
                gateHtml += '<div style="border-top:1px dashed rgba(239,68,68,0.2);margin:6px 0"></div>';
            }
        }
        gateHtml += '</div>';
        steps.push({
            title: '门控拦截',
            tag: 'RESULT',
            color: '#EF4444',
            html: gateHtml
        });
    }

    var stepsHtml = '';
    for (var i = 0; i < steps.length; i++) {
        var isLast = i === steps.length - 1;
        stepsHtml += _buildTraceStep(i + 1, steps[i].title, steps[i].tag, steps[i].color, steps[i].html, isLast);
    }

    var overlay = document.createElement('div');
    overlay.className = 'conf-detail-overlay';
    overlay.innerHTML =
        '<div class="conf-detail-modal">' +
            '<div class="conf-detail-header">' +
                '<div style="display:flex;align-items:center;gap:12px;flex:1;min-width:0">' +
                    '<h3 style="margin:0;font-size:16px;white-space:nowrap">置信度计算详情</h3>' +
                    '<span style="font-family:monospace;font-size:13px;color:#06B6D4;background:rgba(6,182,212,0.1);padding:4px 10px;border-radius:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml(filename || '-') + '</span>' +
                '</div>' +
                '<div style="display:flex;align-items:center;gap:8px">' +
                    '<span style="font-size:14px;font-weight:700;padding:4px 12px;border-radius:999px;background:' + confColor + '20;color:' + confColor + '">' + confDisplay + ' · ' + confLevel + '</span>' +
                    '<button style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:20px;padding:4px 8px" onclick="closeConfidenceDetailModal()">&times;</button>' +
                '</div>' +
            '</div>' +
            '<div class="conf-detail-body">' + stepsHtml + '</div>' +
        '</div>';

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            closeConfidenceDetailModal();
        }
    });

    document.body.appendChild(overlay);
}

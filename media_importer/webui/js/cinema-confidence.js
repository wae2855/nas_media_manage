function toggleCfgSection(header) {
    const section = header.closest(".cfg-section");
    if (!section) return;
    header.classList.toggle("open");
    const body = section.querySelector(".cfg-section-body");
    if (body) body.classList.toggle("open");
}

function selectRFormula(card) {
    const section = document.querySelector('[data-section="confidence"]');
    if (!section) return;
    section.querySelectorAll(".r-formula-card").forEach((item) => item.classList.remove("selected"));
    card.classList.add("selected");
}

function getConfidenceConfig() {
    const section = document.querySelector('[data-section="confidence"]');
    const conf = {};
    if (!section) return conf;
    section.querySelectorAll("input[data-key]").forEach((input) => {
        const value = input.value.trim();
        if (value === "") return;
        const parsed = Number(value);
        conf[input.dataset.key] = Number.isFinite(parsed) ? parsed : value;
    });
    const selectedFormula = section.querySelector(".r-formula-card.selected");
    if (selectedFormula) conf.R_formula = selectedFormula.dataset.rFormula || "log";
    const dimensions = {};
    section.querySelectorAll(".confidence-dim-card[data-dim]").forEach((card) => {
        const dim = card.dataset.dim;
        const sources = Array.from(card.querySelectorAll(".confidence-source-row")).map((row) => ({
            source: row.dataset.source,
            trusted: row.querySelector('input[type="checkbox"]').checked,
        }));
        if (dim && sources.length) dimensions[dim] = { sources };
    });
    if (Object.keys(dimensions).length) conf.dimensions = dimensions;
    return conf;
}

function setConfidenceField(key, value) {
    document.querySelectorAll(`[data-section="confidence"] input[data-key="${key}"]`).forEach((input) => {
        input.value = value;
    });
}

function loadCinemaConfidenceConfig(config) {
    const conf = (config && config.confidence) || {};
    Object.entries(conf).forEach(([key, value]) => {
        if (typeof value !== "object") setConfidenceField(key, value);
    });
    const formula = conf.R_formula || "log";
    document.querySelectorAll('[data-section="confidence"] .r-formula-card').forEach((card) => {
        card.classList.toggle("selected", (card.dataset.rFormula || "log") === formula);
    });
    renderConfidenceDimensions(conf);
    updateThresholdBar();
}

function updateThresholdBar() {
    const section = document.querySelector('[data-section="confidence"]');
    if (!section) return;
    const read = (key, fallback) => {
        const input = section.querySelector(`input[data-key="${key}"]`);
        const value = input ? Number(input.value) : fallback;
        return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : fallback;
    };
    const pass = read("pass_threshold", 0.8);
    const confirm = Math.min(pass, read("confirm_threshold", 0.5));
    const review = Math.min(confirm, read("review_threshold", 0.3));
    const widths = [review, confirm - review, pass - confirm, 1 - pass].map((v) => Math.max(0, v * 100));
    const bar = document.getElementById("confidence-threshold-bar");
    if (bar) {
        bar.innerHTML = [
            `<div class="threshold-segment seg-fail" style="width:${widths[0]}%">失败</div>`,
            `<div class="threshold-segment seg-review" style="width:${widths[1]}%">审核</div>`,
            `<div class="threshold-segment seg-confirm" style="width:${widths[2]}%">确认</div>`,
            `<div class="threshold-segment seg-pass" style="width:${widths[3]}%">通过</div>`,
        ].join("");
    }
    const labels = document.getElementById("confidence-threshold-labels");
    if (labels) {
        labels.innerHTML = `<span style="width:${widths[0]}%">0</span><span style="width:${widths[1]}%">${review.toFixed(2)}</span><span style="width:${widths[2]}%">${confirm.toFixed(2)}</span><span style="width:${widths[3]}%">${pass.toFixed(2)}</span><span>1.0</span>`;
    }
    [["pass_threshold", pass], ["confirm_threshold", confirm], ["review_threshold", review]].forEach(([key, value]) => {
        document.querySelectorAll(`[data-confidence-value="${key}"]`).forEach((el) => { el.textContent = value.toFixed(2); });
    });
    const provider = read("provider_match_threshold", 0.7);
    [["pass_threshold", pass], ["confirm_threshold", confirm], ["review_threshold", review], ["provider_match_threshold", provider]].forEach(([key, value]) => {
        document.querySelectorAll(`[data-confidence-output="${key}"]`).forEach((el) => { el.textContent = value.toFixed(2); });
    });
    [["pass_threshold", pass], ["confirm_threshold", confirm], ["review_threshold", review]].forEach(([key, value]) => {
        document.querySelectorAll(`[data-threshold-handle="${key}"]`).forEach((el) => {
            el.style.left = `${value * 100}%`;
            const label = key === "pass_threshold" ? "通过" : (key === "confirm_threshold" ? "确认" : "审核");
            el.querySelector("span").textContent = `${label} ${value.toFixed(2)}`;
        });
    });
    ["formula-pass-val", "formula-confirm-val", "formula-review-val", "formula-review-val2"].forEach((id, index) => {
        const values = [pass, confirm, review, review];
        const el = document.getElementById(id);
        if (el) el.textContent = values[index].toFixed(2);
    });
    ["formula-threshold-val", "formula-threshold-val2"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.textContent = provider.toFixed(2);
    });
}

async function renderConfidenceDimensions(conf) {
    const container = document.getElementById("dim-source-trust-container");
    if (!container) return;
    const sourceMeta = {
        provider: { label: "Provider", desc: "TMDB 或其他元数据源返回的结构化字段" },
        ai: { label: "AI", desc: "LLM 根据文件名、简介和规则推理" },
        file: { label: "文件名", desc: "从文件名解析出的标题、年份、季集等信息" },
    };
    const defaultSources = ["provider", "ai", "file"];
    try {
        const result = await requestApi("GET", "/dimensions");
        const dimensions = result.code === 200 && result.data ? result.data.dimensions || [] : [];
        if (!dimensions.length) {
            container.innerHTML = '<div class="confidence-sim-result">暂无维度配置。后续在“影视分类维度”启用维度后，这里会显示每个维度的可信来源。</div>';
            return;
        }
        const dimConfigs = conf.dimensions || {};
        container.innerHTML = dimensions.map((dim) => {
            const name = dim.name || "";
            const label = dim.label || dim.display_name || name;
            const configured = ((dimConfigs[name] || {}).sources || []).filter((item) => sourceMeta[item.source]);
            const seen = new Set(configured.map((item) => item.source));
            const sources = configured.concat(defaultSources.filter((key) => !seen.has(key)).map((key) => ({ source: key, trusted: true })));
            return `<article class="confidence-dim-card collapsed" data-dim="${escapeConfidenceHtml(name)}">
                <button class="confidence-dim-head" type="button" data-confidence-action="toggle-dim">
                    <div><b>${escapeConfidenceHtml(label)}</b><small>${escapeConfidenceHtml(name)}</small></div><span>展开后配置可信来源和优先级</span><i class="confidence-dim-arrow">⌄</i>
                </button>
                <div class="confidence-source-list">${sources.map((item, index) => renderConfidenceSourceRow(item, index, sources.length, sourceMeta)).join("")}</div>
            </article>`;
        }).join("");
    } catch (error) {
        container.innerHTML = '<div class="confidence-sim-result">维度来源暂时无法加载，页面其余配置不受影响。</div>';
    }
}

function toggleConfidenceDimCard(button) {
    const card = button.closest(".confidence-dim-card");
    if (card) card.classList.toggle("collapsed");
}

function renderConfidenceSourceRow(item, index, total, sourceMeta) {
    const meta = sourceMeta[item.source];
    const checked = item.trusted !== false ? " checked" : "";
    return `<div class="confidence-source-row" data-source="${item.source}">
        <div class="confidence-source-order">
            <button type="button" data-confidence-action="move-source" data-move-direction="-1" ${index === 0 ? "disabled" : ""}>↑</button>
            <button type="button" data-confidence-action="move-source" data-move-direction="1" ${index === total - 1 ? "disabled" : ""}>↓</button>
        </div>
        <div><strong>${meta.label}</strong><small>${meta.desc}</small></div>
        <label class="confidence-trust-switch"><input type="checkbox"${checked}><span></span></label>
    </div>`;
}

function moveConfidenceSource(button, direction) {
    const row = button.closest(".confidence-source-row");
    const list = row && row.parentElement;
    if (!row || !list) return;
    const sibling = direction < 0 ? row.previousElementSibling : row.nextElementSibling;
    if (!sibling) return;
    if (direction < 0) list.insertBefore(row, sibling);
    else list.insertBefore(sibling, row);
    refreshConfidenceSourceButtons(list);
}

function refreshConfidenceSourceButtons(list) {
    const rows = Array.from(list.querySelectorAll(".confidence-source-row"));
    rows.forEach((row, index) => {
        const buttons = row.querySelectorAll(".confidence-source-order button");
        if (buttons[0]) buttons[0].disabled = index === 0;
        if (buttons[1]) buttons[1].disabled = index === rows.length - 1;
    });
}

function escapeConfidenceHtml(value) {
    return String(value || "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    }[char]));
}

function setThresholdFieldValue(key, value) {
    const input = document.querySelector(`[data-section="confidence"] input[data-key="${key}"]`);
    if (!input) return;
    input.value = value.toFixed(2);
}

function setThresholdFromPointer(key, clientX) {
    const bar = document.getElementById("confidence-threshold-bar");
    if (!bar) return;
    const rect = bar.getBoundingClientRect();
    let value = (clientX - rect.left) / rect.width;
    value = Math.round(Math.min(1, Math.max(0, value)) * 100) / 100;

    const read = (name, fallback) => {
        const field = document.querySelector(`[data-section="confidence"] input[data-key="${name}"]`);
        const parsed = Number(field && field.value);
        return Number.isFinite(parsed) ? parsed : fallback;
    };
    const minGap = 0.01;
    const pass = read("pass_threshold", 0.8);
    const confirm = read("confirm_threshold", 0.5);
    const review = read("review_threshold", 0.3);
    if (key === "review_threshold") value = Math.min(value, confirm - minGap);
    if (key === "confirm_threshold") value = Math.max(review + minGap, Math.min(value, pass - minGap));
    if (key === "pass_threshold") value = Math.max(value, confirm + minGap);
    setThresholdFieldValue(key, Math.min(1, Math.max(0, value)));
    updateThresholdBar();
}

let activeThresholdHandle = null;

document.addEventListener("pointerdown", (event) => {
    const handle = event.target.closest("[data-threshold-handle]");
    if (!handle) return;
    activeThresholdHandle = handle.dataset.thresholdHandle;
    handle.setPointerCapture(event.pointerId);
    setThresholdFromPointer(activeThresholdHandle, event.clientX);
});

document.addEventListener("pointermove", (event) => {
    if (!activeThresholdHandle) return;
    setThresholdFromPointer(activeThresholdHandle, event.clientX);
});

document.addEventListener("pointerup", () => {
    activeThresholdHandle = null;
});

function generateConsultPrompt() {
    const conf = getConfidenceConfig();
    const need = (document.getElementById("ai-consult-need").value || "").trim() || "（未填写具体需求，请根据默认场景给出建议）";

    const rFormula = conf.R_formula || "log";
    const rFormulaDesc = { inverse: "R = 1/N", log: "R = 1/log2(N+1)", sqrt: "R = 1/sqrt(N)", flat: "R = 1.0（不惩罚）" };

    let dimLines = "";
    document.querySelectorAll("#dim-source-trust-container .confidence-dim-card[data-dim]").forEach((card) => {
        const dk = card.getAttribute("data-dim");
        if (!dk) return;
        const labelEl = card.querySelector("b");
        const label = labelEl ? labelEl.textContent.replace(/\(.*\)/, "").trim() : dk;
        const rows = card.querySelectorAll(".confidence-source-row");
        const srcParts = [];
        rows.forEach((row) => {
            const src = row.getAttribute("data-source") || "";
            const toggle = row.querySelector('input[type="checkbox"]');
            const trusted = toggle ? toggle.checked : true;
            srcParts.push(src + (trusted ? "(✓可信)" : "(✗不可信)"));
        });
        dimLines += "  " + dk + "(" + label + "): " + srcParts.join(" > ") + "\n";
    });

    const prompt = "# 影音库AI智能整理 — 置信度配置咨询助手\n"
        + "\n你是\"影音库AI智能整理\"系统的配置顾问。你的任务是根据用户需求，给出精确的配置建议，让用户直接在 Web 界面上修改对应参数。\n"
        + "\n## 一、系统工作流程\n"
        + "\n影音库AI智能整理系统自动刮削视频文件元数据并分类入库。处理流程：\n"
        + "\n1. **文件名清洗**：用正则表达式从文件名中提取标题、年份、季集号。支持中英文标题自动拆分（如\"蝙蝠侠：黑暗骑士.The.Dark.Knight.2008\"会拆分为英文标题\"The Dark Knight\"）。如果年份可疑（如年份在未来、或清洗后标题残留年份），标记为 year_suspect，跳过直接搜索。\n"
        + "2. **Provider 搜索**：用清洗后的标题+年份搜索 Provider 数据库（如 TMDB），获取匹配结果。如果第一次搜索无结果或匹配分低于阈值，会触发 AI 辅助清洗后重新搜索。\n"
        + "3. **AI 刮削**：调用 LLM 提取元数据（标题、年份、分辨率、维度信息等）。\n"
        + "4. **置信度计算**：根据 Provider 匹配质量和 AI 数据可信度计算最终置信度。\n"
        + "5. **决策判定**：根据置信度自动决定任务状态。\n"
        + "\n系统有两条独立的计算路径：\n"
        + "- **Provider 优先路径**（Provider 启用时）：使用 Provider 搜索结果计算\n"
        + "- **纯 AI 路径**（Provider 未启用或无结果时）：仅依赖 AI 判断\n"
        + "\n## 二、置信度计算公式详解\n"
        + "\n### 路径 A：Provider 优先（推荐路径）\n"
        + "\n```\n最终置信度 = search_conf × data_gate\n\nsearch_conf = T × R\n  T = 标题匹配分（L1~L7 七个等级，见下文）\n  R = 搜索结果数惩罚因子（结果越多越不确定）\n\ndata_gate = 1.0（所有维度来源可信）或 0.0（有维度来源不可信 → 强制需审核）\n```\n"
        + "\n#### T 值：标题匹配等级\n"
        + "\n系统将文件名清洗后的标题与 Provider 返回的标题做比较，分精确匹配和模糊匹配两种情况：\n"
        + "\n**精确匹配（标准化后完全相同）时：**\n| 等级 | 条件 | T值参数名 | 当前值 | 说明 |\n|------|------|-----------|--------|------|\n"
        + "| L1 | 标题精确 + 年份精确一致 | title_exact_with_year | " + (conf.title_exact_with_year || 1.0) + " | 最高置信，标题和年份都对上了 |\n"
        + "| L2 | 标题精确 + 有季号（无年份） | title_exact_with_season | " + (conf.title_exact_with_season || 0.9) + " | 剧集常见，用季号辅助确认 |\n"
        + "| L3 | 标题精确 + 无年份也无季号 | title_exact_no_year | " + (conf.title_exact_no_year || 0.7) + " | 标题对了但缺少时间锚定 |\n"
        + "| L4 | 标题精确 + 年份不匹配 | title_exact_year_mismatch | " + (conf.title_exact_year_mismatch || 0.4) + " | 可能是同名不同年作品 |\n"
        + "\n**模糊匹配（相似度 ≥ title_min_similarity）时：**\n| 等级 | 条件 | T值计算 | 说明 |\n|------|------|---------|------|\n"
        + "| L5 | 模糊匹配 + 年份精确 | T = 相似度值 | 年份一致起到锚定作用，不加惩罚 |\n"
        + "| L6 | 模糊匹配 + 年份不匹配或无年份 | T = 相似度 × title_fuzzy_year_coeff | 缺少年份确认，打折扣 |\n"
        + "| L7 | 相似度 < title_min_similarity | T = 0.0 | 完全不匹配 |\n"
        + "\n当前 title_fuzzy_year_coeff = " + (conf.title_fuzzy_year_coeff || 0.7) + "，title_min_similarity = " + (conf.title_min_similarity || 0.3) + "\n"
        + "\n#### R 值：搜索结果数惩罚\n"
        + "\nProvider 搜索返回的结果越多，说明标题越不唯一，需要降低置信度。R 的计算分两步：\n"
        + "\n**第一步：基础 R 值**（根据搜索结果总数 N 计算，N 上限为 R_max_results_cap）\n"
        + "- inverse: R = 1/N（线性衰减，只有1个结果时R=1.0）\n"
        + "- log: R = 1/log2(N+1)（对数衰减，推荐默认，温和惩罚）\n"
        + "- sqrt: R = 1/sqrt(N)（平方根衰减，中等惩罚）\n"
        + "- flat: R = 1.0（不惩罚，忽略结果数）\n"
        + "\n当前公式: " + rFormula + "（" + (rFormulaDesc[rFormula] || rFormula) + "），R_max_results_cap = " + (conf.R_max_results_cap || 10) + "，R_min_value = " + (conf.R_min_value || 0.1) + "\n"
        + "\n**第二步：T 值自信任增强**（当 T > R_T_floor 时，R 向 1.0 方向调整）\n"
        + "```\nalpha = ((T - R_T_floor) / (1.0 - R_T_floor)) ^ R_T_curve\nR_adjusted = R_base × (1 - alpha) + alpha\n```\n"
        + "含义：标题匹配度越高，搜索结果数量的惩罚越小。因为高 T 值说明结果已经很明确了。\n"
        + "当前 R_T_floor = " + (conf.R_T_floor || 0.5) + "，R_T_curve = " + (conf.R_T_curve || 1.5) + "\n"
        + "\n#### data_gate：数据来源可信门控\n"
        + "\n每个维度（如影视类型、年龄分级等）的数据来源有多个：provider、ai、file。系统按配置的优先级顺序选取第一个有数据的来源。如果选中的来源不在该维度的信任列表中，且没有其他可信来源可用，则 data_gate = 0，强制进入审核。\n"
        + "\n**关键规则**：如果某个维度有数据来自不可信来源，但同时该维度也有来自可信来源的数据（即使优先级更低），系统会使用可信来源的数据，不会触发门控阻断。只有所有可用来源都不可信时才阻断。\n"
        + "\n### 路径 B：纯 AI 模式\n"
        + "\n```\n最终置信度 = objective_cap × data_gate\n\nobjective_cap 根据 AI 返回标题与清洗标题的相似度(sim)计算：\n  sim >= ai_cap_high_similarity → cap = sim（AI标题高度一致，用相似度本身）\n  sim >= ai_cap_low_similarity  → cap = sim × ai_cap_low_coeff（低相似度，衰减处理）\n  sim < ai_cap_low_similarity   → cap = ai_cap_no_match（完全不匹配，兜底值）\n  AI 无标题                      → cap = ai_cap_no_title（AI没返回标题，兜底值）\n```\n"
        + "\n当前 ai_cap_high_similarity = " + (conf.ai_cap_high_similarity || 0.7) + "，ai_cap_low_similarity = " + (conf.ai_cap_low_similarity || 0.3) + "，ai_cap_no_title = " + (conf.ai_cap_no_title || 0.3) + "，ai_cap_no_match = " + (conf.ai_cap_no_match || 0.2) + "，ai_cap_low_coeff = " + (conf.ai_cap_low_coeff || 0.5) + "\n"
        + "\n### 决策阈值\n"
        + "\n根据最终置信度判定任务状态：\n| 置信度范围 | 状态 | 说明 |\n|-----------|------|------|\n"
        + "| >= pass_threshold(" + (conf.pass_threshold || 0.8) + ") | PASS 自动通过 | 无需人工干预 |\n"
        + "| >= confirm_threshold(" + (conf.confirm_threshold || 0.5) + ") | CONFIRMING 需确认 | 建议人工确认 |\n"
        + "| >= review_threshold(" + (conf.review_threshold || 0.3) + ") | NEEDS_REVIEW 需审核 | 必须人工审核 |\n"
        + "| < review_threshold | FAILED 失败 | 自动拒绝 |\n"
        + "\n**特殊规则**：data_gate = 0 时，无论置信度多高，状态强制为 NEEDS_REVIEW。\n"
        + "\n### Provider 最低匹配阈值\n"
        + "\nprovider_match_threshold = " + (conf.provider_match_threshold || 0.7) + "。当第一次 Provider 搜索的最佳匹配 T 值低于此阈值时，触发 AI 辅助清洗后重新搜索。\n"
        + "\n## 三、当前完整配置\n\n```\n决策阈值:\n"
        + "  自动通过(pass_threshold) = " + (conf.pass_threshold || 0.8) + "\n"
        + "  需确认(confirm_threshold) = " + (conf.confirm_threshold || 0.5) + "\n"
        + "  需审核(review_threshold) = " + (conf.review_threshold || 0.3) + "\n\n"
        + "标题匹配等级(T值):\n"
        + "  L1精确+年份精确(title_exact_with_year) = " + (conf.title_exact_with_year || 1.0) + "\n"
        + "  L2精确+有季号(title_exact_with_season) = " + (conf.title_exact_with_season || 0.9) + "\n"
        + "  L3精确无年份(title_exact_no_year) = " + (conf.title_exact_no_year || 0.7) + "\n"
        + "  L4精确年份不匹配(title_exact_year_mismatch) = " + (conf.title_exact_year_mismatch || 0.4) + "\n"
        + "  模糊年份系数(title_fuzzy_year_coeff) = " + (conf.title_fuzzy_year_coeff || 0.7) + "\n"
        + "  最低相似度(title_min_similarity) = " + (conf.title_min_similarity || 0.3) + "\n"
        + "  Provider最低匹配阈值(provider_match_threshold) = " + (conf.provider_match_threshold || 0.7) + "\n\n"
        + "R值(搜索结果惩罚):\n"
        + "  公式(R_formula) = " + rFormula + "（" + (rFormulaDesc[rFormula] || rFormula) + "）\n"
        + "  结果数上限(R_max_results_cap) = " + (conf.R_max_results_cap || 10) + "\n"
        + "  下限(R_min_value) = " + (conf.R_min_value || 0.1) + "\n"
        + "  自信任门槛(R_T_floor) = " + (conf.R_T_floor || 0.5) + "\n"
        + "  自信任曲率(R_T_curve) = " + (conf.R_T_curve || 1.5) + "\n\n"
        + "纯AI模式参数:\n"
        + "  高相似度门槛(ai_cap_high_similarity) = " + (conf.ai_cap_high_similarity || 0.7) + "\n"
        + "  低相似度门槛(ai_cap_low_similarity) = " + (conf.ai_cap_low_similarity || 0.3) + "\n"
        + "  无标题上限(ai_cap_no_title) = " + (conf.ai_cap_no_title || 0.3) + "\n"
        + "  无匹配上限(ai_cap_no_match) = " + (conf.ai_cap_no_match || 0.2) + "\n"
        + "  低相似度衰减(ai_cap_low_coeff) = " + (conf.ai_cap_low_coeff || 0.5) + "\n"
        + (dimLines ? "\n维度来源配置(每个维度的来源优先级和信任状态):\n" + dimLines : "")
        + "```\n"
        + "\n## 四、用户需求\n\n" + need + "\n"
        + "\n## 五、回答格式要求\n\n请按以下三部分回答。用户会在 Web 界面上逐项修改，不是编辑配置文件。配置项名称要使用括号内的英文参数名，方便用户在界面上找到对应输入框。\n"
        + "\n### 第一部分：配置清单\n\n只列出需要调整的参数。格式：`区域.参数名(英文名) = 建议值`。\n\n格式示例：\n```\n决策阈值.自动通过(pass_threshold) = 0.85\n标题匹配等级.精确无年份(title_exact_no_year) = 0.75\n维度来源.年龄分级(restricted_level): 只信任provider\n```\n"
        + "\n### 第二部分：调整原因\n\n针对每个调整项，用 1-2 句话说明为什么要改、改了会有什么效果。\n"
        + "\n### 第三部分：示例计算\n\n用 1-2 个文件名模拟完整计算过程，展示每一步的中间值和最终结果。让用户能直观理解\"改了这个参数，置信度会怎么变\"。示例应覆盖用户关心的场景。\n"
        + "\n---\n\n要求：\n"
        + "1. **所有参数建议值必须在 0.0~1.0 范围内**。T值本质是置信度权重，最大为1.0；阈值也是0-1之间的概率值。没有参数可以超过1.0。R_max_results_cap 是唯一大于1的整数参数。\n"
        + "2. 阈值必须满足 pass > confirm > review\n"
        + "3. T 值等级应满足 L1 ≥ L2 ≥ L3 > L4\n"
        + "4. 如果用户需求不明确，给出两套方案并说明适用场景\n"
        + "5. 如果当前配置已经合理，明确告诉用户\"当前配置适合您的场景，无需调整\"\n"
        + "6. 严格模式不是靠提高T值超过1.0来实现，而是靠提高pass_threshold或降低L3/L4的T值来实现";

    document.getElementById("ai-consult-prompt").textContent = prompt;
    document.getElementById("ai-consult-output").style.display = "block";
}

function copyConsultPrompt() {
    const prompt = document.getElementById("ai-consult-prompt");
    if (!prompt || !prompt.textContent) generateConsultPrompt();
    navigator.clipboard.writeText(document.getElementById("ai-consult-prompt").textContent).then(() => {
        showToast("已复制咨询提示词");
    }).catch(() => showToast("复制失败"));
}

document.addEventListener("click", (event) => {
    const confidenceAction = event.target.closest("[data-confidence-action]");
    if (confidenceAction) {
        const action = confidenceAction.dataset.confidenceAction;
        if (action === "toggle-dim") {
            toggleConfidenceDimCard(confidenceAction);
            return;
        }
        if (action === "move-source") {
            moveConfidenceSource(confidenceAction, Number(confidenceAction.dataset.moveDirection || 0));
            return;
        }
    }
    const sectionToggle = event.target.closest("[data-confidence-section-toggle]");
    if (sectionToggle) {
        toggleCfgSection(sectionToggle);
        return;
    }
    const formulaCard = event.target.closest("[data-r-formula]");
    if (formulaCard) {
        selectRFormula(formulaCard);
        return;
    }
    const consultAction = event.target.closest("[data-consult-action]");
    if (consultAction) {
        if (consultAction.dataset.consultAction === "generate") generateConsultPrompt();
        if (consultAction.dataset.consultAction === "copy") copyConsultPrompt();
    }
});

document.addEventListener("input", (event) => {
    if (event.target.matches("[data-confidence-input]")) {
        updateThresholdBar();
    }
});

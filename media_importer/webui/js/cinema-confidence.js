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
    const need = (document.getElementById("ai-consult-need").value || "请根据家庭影音库场景，给出更稳妥的自动入库阈值建议。").trim();
    const prompt = [
        "# 影音库 AI 置信度配置咨询",
        "",
        "用户目标：",
        need,
        "",
        "当前关键配置：",
        `自动通过(pass_threshold) = ${conf.pass_threshold || 0.8}`,
        `需要确认(confirm_threshold) = ${conf.confirm_threshold || 0.5}`,
        `需要审核(review_threshold) = ${conf.review_threshold || 0.3}`,
        `Provider最低匹配(provider_match_threshold) = ${conf.provider_match_threshold || 0.7}`,
        `R公式(R_formula) = ${conf.R_formula || "log"}`,
        "",
        "请输出：1. 建议调整清单；2. 调整原因；3. 用两个文件名演示调整后的判定差异。",
    ].join("\n");
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

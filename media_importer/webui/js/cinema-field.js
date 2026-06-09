// cinema-field.js — 通用字段渲染器（C3 模块化设计系统）

(function initCinemaField(global) {
    function fieldEscape(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function wrapField(key, label, controlHtml, hint) {
        return `
            <label class="cinema-field cinema-modal-field" data-field-key="${fieldEscape(key)}">
                <span>${fieldEscape(label || key)}</span>
                ${controlHtml}
                ${hint ? `<small>${fieldEscape(hint)}</small>` : ""}
            </label>`;
    }

    function renderTextField(key, label, value, options = {}) {
        const control = `<input type="text" data-field-key="${fieldEscape(key)}" value="${fieldEscape(value)}" ${options.placeholder ? `placeholder="${fieldEscape(options.placeholder)}"` : ""} ${options.required ? "required" : ""} />`;
        return wrapField(key, label, control, options.hint);
    }

    function renderPathField(key, label, value, options = {}) {
        const testBtn = options.testAction
            ? `<button type="button" data-path-test="${fieldEscape(options.testAction)}">测试</button>`
            : "";
        const control = `
            <div class="cinema-field-path">
                <input type="text" data-field-key="${fieldEscape(key)}" value="${fieldEscape(value)}" ${options.placeholder ? `placeholder="${fieldEscape(options.placeholder)}"` : ""} />
                ${testBtn}
            </div>`;
        return wrapField(key, label, control, options.hint);
    }

    function renderSelectField(key, label, value, options = {}) {
        const choices = Array.isArray(options.choices) ? options.choices : [];
        const optionsHtml = choices.map((choice) => {
            const optValue = typeof choice === "object" ? choice.value : choice;
            const optLabel = typeof choice === "object" ? choice.label : choice;
            const selected = String(optValue) === String(value) ? "selected" : "";
            return `<option value="${fieldEscape(optValue)}" ${selected}>${fieldEscape(optLabel)}</option>`;
        }).join("");
        const control = `<select data-field-key="${fieldEscape(key)}">${optionsHtml}</select>`;
        return wrapField(key, label, control, options.hint);
    }

    function renderToggleField(key, label, value, options = {}) {
        const checked = Boolean(value) ? "checked" : "";
        const control = `
            <label class="cinema-field-toggle">
                <input type="checkbox" data-field-key="${fieldEscape(key)}" ${checked} />
                <span>${fieldEscape(options.toggleLabel || "启用")}</span>
            </label>`;
        return wrapField(key, label, control, options.hint);
    }

    function renderNumberField(key, label, value, options = {}) {
        const min = options.min !== undefined ? `min="${fieldEscape(options.min)}"` : "";
        const max = options.max !== undefined ? `max="${fieldEscape(options.max)}"` : "";
        const step = options.step !== undefined ? `step="${fieldEscape(options.step)}"` : "";
        const control = `<input type="number" data-field-key="${fieldEscape(key)}" value="${fieldEscape(value)}" ${min} ${max} ${step} />`;
        return wrapField(key, label, control, options.hint);
    }

    function renderTextareaField(key, label, value, options = {}) {
        const rows = options.rows || 4;
        const control = `<textarea data-field-key="${fieldEscape(key)}" rows="${fieldEscape(rows)}" ${options.placeholder ? `placeholder="${fieldEscape(options.placeholder)}"` : ""}>${fieldEscape(value)}</textarea>`;
        return wrapField(key, label, control, options.hint);
    }

    function collectFieldValue(fieldEl) {
        if (!fieldEl) return null;
        const input = fieldEl.querySelector("input, select, textarea");
        if (!input) return null;
        const key = input.dataset.fieldKey;
        if (!key) return null;
        if (input.type === "checkbox") {
            return { key, value: input.checked };
        }
        if (input.tagName === "SELECT") {
            return { key, value: input.value };
        }
        if (input.type === "number") {
            const num = Number(input.value);
            return { key, value: Number.isFinite(num) ? num : input.value };
        }
        return { key, value: input.value };
    }

    function collectSectionValues(sectionElement) {
        if (!sectionElement) return {};
        const out = {};
        sectionElement.querySelectorAll("[data-field-key]").forEach((input) => {
            const key = input.dataset.fieldKey;
            if (!key) return;
            if (input.type === "checkbox") {
                out[key] = input.checked;
            } else if (input.tagName === "SELECT") {
                out[key] = input.value;
            } else if (input.type === "number") {
                const num = Number(input.value);
                out[key] = Number.isFinite(num) ? num : input.value;
            } else {
                out[key] = input.value;
            }
        });
        return out;
    }

    function validateSectionFields(sectionElement, requiredKeys = []) {
        if (!sectionElement) return { valid: true, missing: [] };
        const missing = [];
        requiredKeys.forEach((key) => {
            const input = sectionElement.querySelector(`[data-field-key="${fieldEscape(key)}"]`);
            if (!input) return;
            const value = input.type === "checkbox" ? input.checked : String(input.value || "").trim();
            if (!value) missing.push(key);
        });
        return { valid: missing.length === 0, missing };
    }

    global.cinemaField = {
        renderTextField,
        renderPathField,
        renderSelectField,
        renderToggleField,
        renderNumberField,
        renderTextareaField,
        collectFieldValue,
        collectSectionValues,
        validateSectionFields,
    };
})(window);

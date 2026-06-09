// cinema-section.js — 通用配置区块渲染器（C3 模块化设计系统）

(function initCinemaSection(global) {
    function sectionEscape(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function renderConfigSection({ id, title, description = "", fieldsHtml = "", defaultOpen = true, saveAction = null, saveLabel = "保存" }) {
        const openClass = defaultOpen ? "open" : "";
        return `
            <div class="cinema-config-section" data-config-section="${sectionEscape(id)}" data-save-action="${sectionEscape(saveAction || "")}">
                <div class="cinema-config-section-header ${openClass}">
                    <div>
                        <h3>${sectionEscape(title)}</h3>
                        ${description ? `<p>${sectionEscape(description)}</p>` : ""}
                    </div>
                    <div class="cinema-config-section-actions">
                        ${saveAction ? `<button type="button" class="btn btn-primary" data-section-save="${sectionEscape(saveAction)}">${sectionEscape(saveLabel)}</button>` : ""}
                    </div>
                </div>
                <div class="cinema-config-section-body ${openClass}">
                    <div class="cinema-config-section-grid">${fieldsHtml}</div>
                </div>
            </div>`;
    }

    function bindSectionHeaderToggles(rootElement) {
        if (!rootElement) return;
        rootElement.addEventListener("click", (event) => {
            const header = event.target.closest(".cinema-config-section-header");
            if (!header) return;
            if (event.target.closest("[data-section-save]")) return;
            const section = header.closest("[data-config-section]");
            if (!section) return;
            header.classList.toggle("open");
            const body = section.querySelector(".cinema-config-section-body");
            if (body) body.classList.toggle("open");
        });
    }

    function findSection(rootElement, sectionId) {
        if (!rootElement) return null;
        return rootElement.querySelector(`[data-config-section="${CSS.escape(sectionId)}"]`);
    }

    global.cinemaSection = {
        renderConfigSection,
        bindSectionHeaderToggles,
        findSection,
    };
})(window);

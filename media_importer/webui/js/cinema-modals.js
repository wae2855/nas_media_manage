(function initCinemaModals(global) {
    function modalEscapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function removeAppModal() {
        const overlay = document.querySelector(".cinema-modal-overlay");
        if (!overlay) return;
        if (typeof overlay._onClose === "function") {
            const callback = overlay._onClose;
            overlay._onClose = null;
            callback();
        }
        overlay.remove();
    }

    function showAppModal({
        title,
        body,
        actions = [],
        tone = "default",
        dismissOnBackdrop = true,
        onClose = null,
    }) {
        removeAppModal();
        const overlay = document.createElement("div");
        overlay.className = "cinema-modal-overlay";
        overlay._onClose = onClose;
        overlay.innerHTML = `
            <div class="cinema-modal cinema-modal-${tone}">
                <div class="cinema-modal-header">
                    <h3>${modalEscapeHtml(title || "详情")}</h3>
                    <button type="button" class="cinema-modal-close" aria-label="关闭">×</button>
                </div>
                <div class="cinema-modal-body">${body || ""}</div>
                <div class="cinema-modal-footer"></div>
            </div>
        `;
        overlay.addEventListener("click", (event) => {
            if (dismissOnBackdrop && event.target === overlay) removeAppModal();
        });
        overlay.querySelector(".cinema-modal-close")?.addEventListener("click", removeAppModal);
        const footer = overlay.querySelector(".cinema-modal-footer");
        actions.forEach((action) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = action.className || "btn btn-secondary";
            button.textContent = action.label || "确定";
            button.addEventListener("click", async (event) => {
                event.stopPropagation();
                try {
                    if (typeof action.onClick === "function") await action.onClick();
                } catch (error) {
                    console.error("Modal action failed:", error);
                    if (typeof showToast === "function") showToast("操作失败，请查看控制台或服务日志");
                    return;
                }
                if (action.closeOnClick !== false) removeAppModal();
            });
            footer.appendChild(button);
        });
        document.body.appendChild(overlay);
        return overlay;
    }

    function showTextModal(title, text, confirmLabel = "我知道了", tone = "default") {
        return showAppModal({
            title,
            tone,
            body: `<pre style="margin:0;white-space:pre-wrap;word-break:break-word;line-height:1.7;color:var(--text-primary);font-size:14px;">${modalEscapeHtml(text || "")}</pre>`,
            actions: [{ label: confirmLabel, className: "btn btn-primary" }],
        });
    }

    function showPromptModal({ title, message, placeholder = "", initialValue = "", confirmLabel = "确认", cancelLabel = "取消" }) {
        return new Promise((resolve) => {
            const inputId = `modal-prompt-${Date.now()}`;
            const overlay = document.createElement("div");
            overlay.className = "cinema-modal-overlay";
            overlay.innerHTML = `
                <div class="cinema-modal cinema-modal-default">
                    <div class="cinema-modal-header">
                        <h3>${modalEscapeHtml(title || "请输入")}</h3>
                        <button type="button" class="cinema-modal-close" aria-label="关闭">×</button>
                    </div>
                    <div class="cinema-modal-body">
                        <div class="cinema-modal-stack">
                            ${message ? `<p style="margin:0;color:var(--text-secondary);line-height:1.7;">${modalEscapeHtml(message)}</p>` : ""}
                            <label class="cinema-modal-field">
                                <span>输入内容</span>
                                <input id="${inputId}" type="text" value="${modalEscapeHtml(initialValue || "")}" placeholder="${modalEscapeHtml(placeholder || "")}" />
                            </label>
                        </div>
                    </div>
                    <div class="cinema-modal-footer"></div>
                </div>
            `;
            const settle = (value) => {
                if (overlay.dataset.settled === "1") return;
                overlay.dataset.settled = "1";
                resolve(value);
            };
            overlay.addEventListener("click", (event) => {
                if (event.target === overlay) {
                    overlay.remove();
                    settle(null);
                }
            });
            overlay.querySelector(".cinema-modal-close")?.addEventListener("click", () => {
                overlay.remove();
                settle(null);
            });
            const footer = overlay.querySelector(".cinema-modal-footer");
            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "btn btn-secondary";
            cancelButton.textContent = cancelLabel;
            cancelButton.addEventListener("click", () => {
                overlay.remove();
                settle(null);
            });
            const confirmButton = document.createElement("button");
            confirmButton.type = "button";
            confirmButton.className = "btn btn-primary";
            confirmButton.textContent = confirmLabel;
            confirmButton.addEventListener("click", () => {
                const input = overlay.querySelector(`#${CSS.escape(inputId)}`);
                const value = String(input?.value || "").trim();
                overlay.remove();
                settle(value || null);
            });
            footer.appendChild(cancelButton);
            footer.appendChild(confirmButton);
            document.body.appendChild(overlay);
            setTimeout(() => {
                const input = overlay.querySelector(`#${CSS.escape(inputId)}`);
                input?.focus();
                input?.select?.();
            }, 0);
        });
    }

    function showConfirm(title, message, onConfirm) {
        showAppModal({
            title,
            tone: "default",
            body: `<div class="cinema-modal-stack"><p style="margin:0;color:var(--text-secondary);line-height:1.8;">${modalEscapeHtml(message || "")}</p></div>`,
            actions: [
                { label: "取消", className: "btn btn-secondary" },
                {
                    label: "确认",
                    className: "btn btn-primary",
                    onClick: async () => {
                        if (typeof onConfirm === "function") await onConfirm();
                    },
                },
            ],
        });
    }

    function buildPermissionIssueDialog(issues, title = "权限不足") {
        const overlay = document.createElement("div");
        overlay.className = "perm-dialog-overlay";
        const body = (Array.isArray(issues) ? issues : []).map((item) => `
            <div class="perm-issue-item">
                <div class="perm-issue-field">字段: ${modalEscapeHtml(item.field || "-")}</div>
                <div class="perm-issue-path">路径: ${modalEscapeHtml(item.path || "-")}</div>
                ${item.rule_template ? `<div style="font-size:12px;color:#64748b;margin-top:2px;">所属规则模板: ${modalEscapeHtml(item.rule_template)}</div>` : ""}
                <div style="margin-top:6px;color:#991b1b;">${modalEscapeHtml(item.message || "")}</div>
                ${item.hint ? `<div class="perm-issue-hint">${modalEscapeHtml(item.hint)}</div>` : ""}
            </div>
        `).join("");
        overlay.innerHTML = `
            <div class="perm-dialog">
                <div class="perm-dialog-header">⚠️ ${modalEscapeHtml(title)}</div>
                <div class="perm-dialog-body">
                    <div style="margin-bottom:12px;color:#475569;">请按下列提示完成授权或修正路径后，再重新保存或测试。</div>
                    ${body}
                </div>
                <div class="perm-dialog-footer">
                    <button class="btn btn-primary" type="button">我知道了</button>
                </div>
            </div>`;
        overlay.querySelector("button")?.addEventListener("click", () => overlay.remove());
        document.body.appendChild(overlay);
    }

    global.removeAppModal = removeAppModal;
    global.showAppModal = showAppModal;
    global.showTextModal = showTextModal;
    global.showPromptModal = showPromptModal;
    global.showConfirm = showConfirm;
    global.buildPermissionIssueDialog = buildPermissionIssueDialog;
})(window);

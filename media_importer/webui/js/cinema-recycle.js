// cinema-recycle.js — 回收站渲染与操作

function renderRecycleCard(item) {
    const status = item.restorable ? "可恢复" : "待清理";
    const primaryAction = item.restorable
        ? { key: "restore-recycle", label: "恢复" }
        : { key: "view-recycle", label: "详情" };
    const secondaryAction = item.restorable
        ? { key: "view-recycle", label: "来源" }
        : { key: "delete-recycle", label: "清理" };
    const title = item.original_path
        ? String(item.original_path).split("/").pop().split("\\").pop()
        : (item.recycle_path ? String(item.recycle_path).split("/").pop().split("\\").pop() : "回收文件");
    const meta = `${formatFileSizeMb(item.file_size_mb || (Number(item.size || 0) / 1024 / 1024))} · ${formatActivityTime(item.moved_at)} · ${item.reason || "未知原因"}`;
    const id = String(item.id || item.recycle_path || "");
    const checked = selectedRecycleIds.has(id) ? "checked" : "";
    const statusClass = item.restorable ? "recycle-status-ok" : "recycle-status-warn";
    return `
        <div class="recycle-row" data-recycle-row="${escapeHtml(id)}">
            <input type="checkbox" class="task-select-checkbox" data-recycle-select="${escapeHtml(id)}" ${checked} aria-label="选择回收项" />
            <div class="recycle-row-body">
                <div class="recycle-row-title">${escapeHtml(title)}</div>
                <div class="recycle-row-meta" title="${escapeHtml(item.original_path || item.recycle_path || "回收站")}">${escapeHtml(item.original_path || item.recycle_path || "回收站")}</div>
                <div class="recycle-row-info"><span class="${statusClass}">${escapeHtml(status)}</span> · ${escapeHtml(meta)}</div>
            </div>
            <div class="recycle-row-actions">
                <button data-recycle-action="${escapeHtml(primaryAction.key)}" data-recycle-id="${escapeHtml(id)}">${escapeHtml(primaryAction.label)}</button>
                <button data-recycle-action="${escapeHtml(secondaryAction.key)}" data-recycle-id="${escapeHtml(id)}">${escapeHtml(secondaryAction.label)}</button>
            </div>
        </div>`;
}

function renderRecycleList() {
    const host = document.getElementById("recycle-list");
    if (!host) return;
    if (!Array.isArray(currentRecycleRecords) || currentRecycleRecords.length === 0) {
        host.innerHTML = `
            <div class="recycle-empty">
                <p>当前回收站为空</p>
                <small>危险操作进入回收流程后，这里会显示可恢复文件和待清理项目。</small>
            </div>`;
        setRecycleBatchToolbarVisibility();
        updateRecycleBatchToolbar();
        return;
    }
    host.innerHTML = currentRecycleRecords.map(renderRecycleCard).join("");
    setRecycleBatchToolbarVisibility();
    updateRecycleBatchToolbar();
}

async function loadRecycleData() {
    const host = document.getElementById("recycle-list");
    if (host) {
        host.innerHTML = `<div class="recycle-empty"><p>正在加载回收站…</p></div>`;
    }
    const result = await requestApi("GET", "/recycle/list?limit=20");
    if (result.code === 401) {
        currentRecycleRecords = [];
        if (host) {
            host.innerHTML = `
                <div class="recycle-empty">
                    <p>需要先完成认证</p>
                    <small>输入 API Key 后，这里才会显示真实回收文件。</small>
                </div>`;
        }
        document.getElementById("recycle-recoverable-count").textContent = "--";
        document.getElementById("recycle-cleanup-count").textContent = "--";
        document.getElementById("recycle-size").textContent = "--";
        return;
    }
    if (result.code !== 200 || !result.data) {
        currentRecycleRecords = [];
        if (host) {
            host.innerHTML = `
                <div class="recycle-empty">
                    <p>回收站加载失败</p>
                    <small>${escapeHtml(result.message || "请稍后重试。")}</small>
                    <button data-recycle-action="refresh-recycle">重新加载</button>
                </div>`;
        }
        return;
    }
    currentRecycleRecords = result.data.items || [];
    document.getElementById("recycle-recoverable-count").textContent = String(currentRecycleRecords.filter((item) => item.restorable).length);
    document.getElementById("recycle-cleanup-count").textContent = String(currentRecycleRecords.filter((item) => !item.restorable).length);
    document.getElementById("recycle-size").textContent = formatFileSizeMb(result.data.total_size_mb || (Number(result.data.total_size || 0) / 1024 / 1024));
    renderRecycleList();
}

function findRecycleRecord(id) {
    return currentRecycleRecords.find((item) => (item.id || item.recycle_path) === id);
}

async function performRecycleAction(action, recycleId) {
    if (action === "refresh-recycle") {
        await loadRecycleData();
        return;
    }
    const item = findRecycleRecord(recycleId);
    if (!item) {
        showToast("当前回收记录已过期，请重新加载");
        return;
    }
    if (action === "view-recycle") {
        const summary = [
            `原路径：${item.original_path || "-"}`,
            `回收位置：${item.recycle_path || "-"}`,
            `来源分区：${item.partition || item.zone_name || "-"}`,
            `原因：${item.reason || "-"}`,
            `移动时间：${item.moved_at || "-"}`,
        ].join("\n");
        showTextModal("回收记录详情", summary);
        return;
    }
    if (action === "restore-recycle") {
        showConfirm("恢复文件", `确定恢复「${item.original_path || item.recycle_path || "回收文件"}」吗？`, async () => {
            const restoreItem = item.recycle_path || recycleId;
            const tryRestore = async (conflictMode = "skip") => requestApi("POST", "/recycle/restore", {
                items: [restoreItem],
                conflict_mode: conflictMode,
            });
            let result = await tryRestore("skip");
            const conflict = Array.isArray(result.data?.failed)
                ? result.data.failed.find((entry) => entry.status === "conflict")
                : null;
            if (conflict) {
                showAppModal({
                    title: "发现同名冲突",
                    body: `
                        <div class="cinema-modal-stack">
                            <p>${escapeHtml(conflict.message || "原位置已存在同名文件。")}</p>
                            <div class="cinema-modal-hint">你可以跳过、直接覆盖，或者以 restored 后缀恢复一份副本。</div>
                        </div>`,
                    actions: [
                        { label: "取消", className: "btn btn-secondary" },
                        {
                            label: "覆盖恢复",
                            className: "btn btn-secondary",
                            onClick: async () => {
                                const retry = await tryRestore("overwrite");
                                showToast(retry.message || "覆盖恢复请求已发送");
                                if (retry.code === 200 || retry.code === 207) await loadRecycleData();
                            },
                        },
                        {
                            label: "重命名恢复",
                            className: "btn btn-primary",
                            onClick: async () => {
                                const retry = await tryRestore("rename");
                                showToast(retry.message || "重命名恢复请求已发送");
                                if (retry.code === 200 || retry.code === 207) await loadRecycleData();
                            },
                        },
                    ],
                });
                return;
            }
            showToast(result.message || "恢复请求已发送");
            if (result.code === 200 || result.code === 207) await loadRecycleData();
        });
        return;
    }
    if (action === "delete-recycle") {
        showConfirm("清理回收项", `确定永久清理「${item.original_path || item.recycle_path || "回收文件"}」吗？`, async () => {
            const result = await requestApi("POST", "/recycle/delete", {
                items: [item.recycle_path || recycleId],
            });
            showToast(result.message || "清理请求已发送");
            if (result.code === 200 || result.code === 207) {
                await loadRecycleData();
            }
        });
    }
}

/* B3: 回收页批量动作 */

function getRecycleIdOf(item) {
    return String(item?.id || item?.recycle_path || "");
}

function getSelectedRecycleRecords() {
    return currentRecycleRecords.filter((item) => selectedRecycleIds.has(getRecycleIdOf(item)));
}

function setRecycleBatchToolbarVisibility() {
    const toolbar = document.getElementById("recycle-batch-toolbar");
    if (!toolbar) return;
    toolbar.hidden = !Array.isArray(currentRecycleRecords)
        || currentRecycleRecords.length === 0
        || selectedRecycleIds.size === 0;
}

function updateRecycleBatchToolbar() {
    const records = getSelectedRecycleRecords();
    const count = records.length;
    const toolbar = document.getElementById("recycle-batch-toolbar");
    if (toolbar) toolbar.hidden = count === 0;
    const counter = document.getElementById("recycle-batch-count");
    if (counter) counter.textContent = `已选 ${count} 项`;
    const selectAll = document.getElementById("recycle-select-all");
    const visibleIds = currentRecycleRecords.map(getRecycleIdOf);
    if (selectAll) {
        const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedRecycleIds.has(id));
        const someSelected = visibleIds.some((id) => selectedRecycleIds.has(id));
        selectAll.checked = allSelected;
        selectAll.indeterminate = !allSelected && someSelected;
    }
    const hasRestorable = records.some((item) => item.restorable);
    const restoreBtn = document.getElementById("recycle-batch-restore");
    const deleteBtn = document.getElementById("recycle-batch-delete");
    if (restoreBtn) {
        restoreBtn.hidden = !(count > 0 && hasRestorable);
        restoreBtn.disabled = count === 0;
    }
    if (deleteBtn) {
        deleteBtn.disabled = count === 0;
    }
}

function toggleRecycleSelect(id) {
    const key = String(id || "");
    if (!key) return;
    if (selectedRecycleIds.has(key)) selectedRecycleIds.delete(key);
    else selectedRecycleIds.add(key);
    const checkbox = document.querySelector(`[data-recycle-select="${CSS.escape(key)}"]`);
    if (checkbox) checkbox.checked = selectedRecycleIds.has(key);
    updateRecycleBatchToolbar();
}

function selectAllVisibleRecycle() {
    const selectAll = document.getElementById("recycle-select-all");
    const visibleIds = currentRecycleRecords.map((item) => getRecycleIdOf(item)).filter(Boolean);
    const shouldSelectAll = !(visibleIds.length > 0 && visibleIds.every((id) => selectedRecycleIds.has(id)));
    currentRecycleRecords.forEach((item) => {
        const id = getRecycleIdOf(item);
        if (!id) return;
        if (shouldSelectAll) selectedRecycleIds.add(id);
        else selectedRecycleIds.delete(id);
    });
    if (selectAll) selectAll.checked = shouldSelectAll;
    renderRecycleList();
}

function clearRecycleSelection() {
    selectedRecycleIds.clear();
    renderRecycleList();
}

function findRecycleConflicts(failed) {
    if (!Array.isArray(failed)) return [];
    return failed.filter((entry) => entry && (entry.status === "conflict" || /conflict|冲突/i.test(String(entry.message || ""))));
}

async function performBatchRecycleAction(action) {
    const records = getSelectedRecycleRecords();
    if (action === "batch-clear") {
        clearRecycleSelection();
        return;
    }
    if (records.length === 0) {
        showToast("请先选择要操作的回收项");
        return;
    }
    if (records.length > 50) {
        showToast(`当前选中 ${records.length} 项，超过单次批量 50 项上限，请分批操作`);
        return;
    }
    const items = records.map((item) => item.recycle_path || getRecycleIdOf(item)).filter(Boolean);
    if (action === "batch-restore") {
        const restorableItems = records.filter((item) => item.restorable);
        if (restorableItems.length === 0) {
            showToast("当前选中项中没有可恢复的文件");
            return;
        }
        const paths = restorableItems.map((item) => item.recycle_path || getRecycleIdOf(item)).filter(Boolean);
        showConfirm("批量恢复", `确定恢复「${restorableItems.length}」个文件吗？\n\n如果原位置已存在同名文件，将先跳过再统一处理。`, async () => {
            const result = await requestApi("POST", "/recycle/restore", {
                items: paths,
                conflict_mode: "skip",
            });
            const failed = result?.data?.failed || [];
            const conflicts = findRecycleConflicts(failed);
            if (conflicts.length > 0 && (result.code === 207 || result.code === 400)) {
                showAppModal({
                    title: "发现冲突项",
                    body: `
                        <div class="cinema-modal-stack">
                            <p>${escapeHtml(conflicts.length)} 个文件恢复时遇到同名冲突，请选择处理方式：</p>
                            <div class="cinema-modal-hint">所有冲突项将按你的选择统一处理，不会逐项弹窗。</div>
                        </div>`,
                    actions: [
                        { label: "全部跳过", className: "btn btn-secondary" },
                        {
                            label: "全部覆盖",
                            className: "btn btn-secondary",
                            onClick: async () => {
                                const retry = await requestApi("POST", "/recycle/restore", {
                                    items: paths,
                                    conflict_mode: "overwrite",
                                });
                                showToast(retry.message || "覆盖恢复已发送");
                                if (retry.code === 200 || retry.code === 207) {
                                    clearRecycleSelection();
                                    await loadRecycleData();
                                }
                            },
                        },
                        {
                            label: "全部重命名",
                            className: "btn btn-primary",
                            onClick: async () => {
                                const retry = await requestApi("POST", "/recycle/restore", {
                                    items: paths,
                                    conflict_mode: "rename",
                                });
                                showToast(retry.message || "重命名恢复已发送");
                                if (retry.code === 200 || retry.code === 207) {
                                    clearRecycleSelection();
                                    await loadRecycleData();
                                }
                            },
                        },
                    ],
                });
                return;
            }
            showToast(result.message || "恢复请求已发送");
            if (result.code === 200 || result.code === 207) {
                clearRecycleSelection();
                await loadRecycleData();
            }
        });
        return;
    }
    if (action === "batch-delete") {
        showConfirm(
            "批量永久清理",
            `确定永久清理「${records.length}」个文件吗？\n\n此操作不可恢复，请确认这些文件已经不需要再保留。`,
            async () => {
                const result = await requestApi("POST", "/recycle/delete", { items });
                showToast(result.message || "清理请求已发送");
                if (result.code === 200 || result.code === 207) {
                    clearRecycleSelection();
                    await loadRecycleData();
                }
            },
        );
    }
}

// cinema-config-dim-ops.js - extracted from cinema-config.js
async function loadDimensionsList() {
  const result = await requestApi("GET", "/dimensions/enabled");
  if (result.code !== 200 || !result.data) {
    return [];
  }
  return Array.isArray(result.data.dimensions) ? result.data.dimensions : [];
}

async function toggleDimensionEnabled(name, enabled) {
  const result = await requestApi(
    "POST",
    `/dimensions/${encodeURIComponent(name)}/toggle`,
    { enabled },
  );
  showToast(result.message || (enabled ? "已启用" : "已停用") + name);
  if (result.code === 200) {
    currentEnabledDimensions = await loadDimensionsList();
    renderEnabledDimensionBadges();
  }
}

function renderEnabledDimensionBadges() {
  const host = document.getElementById("enabled-dimension-badges");
  if (!host) return;
  if (!currentEnabledDimensions || currentEnabledDimensions.length === 0) {
    host.innerHTML = `<div class="cinema-modal-hint">暂未启用任何维度。</div>`;
    return;
  }
  host.innerHTML = currentEnabledDimensions
    .map(
      (dim) => `
        <span class="badge">${escapeHtml(dim.label || dim.name)}</span>
    `,
    )
    .join("");
}

function collectDimensionOrder() {
  const root = document.getElementById("dimension-order-list");
  if (!root) return [];
  return Array.from(root.querySelectorAll("[data-dimension-order]"))
    .map((node) => node.dataset.dimensionOrder)
    .filter(Boolean);
}

async function saveDimensionOrder() {
  const order = collectDimensionOrder();
  if (order.length === 0) {
    showToast("当前没有可保存的维度顺序");
    return;
  }
  const result = await requestApi("POST", "/dimensions/order", { order });
  showToast(result.message || "维度顺序已保存");
}

async function performDimensionAction(action, name) {
  if (action === "toggle") {
    const enabled = !(
      name && currentEnabledDimensions.some((d) => d.name === name)
    );
    await toggleDimensionEnabled(name, enabled);
    return;
  }
  if (action === "save-order") {
    await saveDimensionOrder();
  }
}

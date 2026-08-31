// cinema-config-rules.js - extracted from cinema-config.js
function buildProviderField(providerType, field, rawValue) {
  const value = rawValue ?? field.default ?? "";
  const id = `cfg-provider-inline-${providerType}-${field.key}`;
  const hint = field.description || field.help_text || field.placeholder || "";
  if (field.type === "select") {
    const options = (field.options || [])
      .map((option) => {
        const selected = option.value === value ? " selected" : "";
        return `<option value="${escapeHtml(option.value)}"${selected}>${escapeHtml(option.label)}</option>`;
      })
      .join("");
    return `
            <label class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <select id="${id}">${options}</select>
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </label>`;
  }
  if (field.type === "number") {
    return `
            <label class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <input id="${id}" type="number" value="${escapeHtml(value)}" />
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </label>`;
  }
  if (field.type === "password") {
    const placeholder =
      field.key === "api_key" && value === "***"
        ? "已保存，留空保持不变"
        : field.placeholder || field.label || "";
    const val = value === "***" ? "" : value;
    return `
            <label class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <input id="${id}" type="password" value="${escapeHtml(val)}" placeholder="${escapeHtml(placeholder)}" />
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </label>`;
  }
  if (field.type === "checkbox") {
    return `
            <article class="form-card">
                <span>${escapeHtml(field.label || field.key)}</span>
                <label class="toggle-row-inline">
                    <input id="${id}" type="checkbox"${value ? " checked" : ""} />
                    <b>${escapeHtml(field.checkbox_label || "启用")}</b>
                </label>
                ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
            </article>`;
  }
  return `
        <label class="form-card">
            <span>${escapeHtml(field.label || field.key)}</span>
            <input id="${id}" type="text" value="${escapeHtml(value)}" placeholder="${escapeHtml(field.placeholder || "")}" />
            ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
        </label>`;
}

function renderInlineProviderConfigs(providerDefs, savedProviders) {
  const host = document.getElementById("provider-inline-stack");
  if (!host) return;
  if (!Array.isArray(providerDefs) || providerDefs.length === 0) {
    host.innerHTML =
      '<article class="provider-inline-empty">当前没有可用的 Provider</article>';
    return;
  }
  currentProviderDefinitions = providerDefs;
  host.innerHTML = providerDefs
    .map((provider) => {
      const savedConfig =
        (savedProviders || []).find((item) => item.type === provider.type) ||
        {};
      const enabled =
        savedConfig.enabled !== false && provider.enabled !== false;
      const defaultCollapsed =
        String(provider.type || "").toLowerCase() === "tmdb";
      const collapsedClass = defaultCollapsed ? " is-collapsed" : "";
      const mergedConfig = {
        ...(provider.config || {}),
        ...(savedConfig || {}),
      };
      const fields = ((provider.config_schema || {}).fields || [])
        .map((field) =>
          buildProviderField(provider.type, field, mergedConfig[field.key]),
        )
        .join("");
      const statusText = enabled ? "已启用" : "未启用";
      const statusClass = enabled ? "is-enabled" : "is-disabled-status";
      return `
            <article class="provider-inline-card${enabled ? "" : " is-disabled"}${collapsedClass}" data-provider-card="${escapeHtml(provider.type)}">
                <div class="provider-inline-head" data-toggle-provider-card="${escapeHtml(provider.type)}">
                    <div class="provider-inline-head-main">
                        <div class="provider-inline-title-row">
                            <strong>${escapeHtml(provider.display_name || provider.type)}</strong>
                            <span class="provider-inline-status ${statusClass}" data-provider-status="${escapeHtml(provider.type)}">${statusText}</span>
                            <label class="toggle-pill provider-inline-toggle" title="启用或停用该 Provider">
                                <input type="checkbox"${enabled ? " checked" : ""} data-provider-toggle="${escapeHtml(provider.type)}" />
                                <span class="toggle-pill-ui"></span>
                            </label>
                        </div>
                        <p>${escapeHtml(provider.description || "配置元数据源地址、凭据和连接参数。")}</p>
                    </div>
                    <div class="provider-inline-head-right">
                        <span class="provider-inline-chevron" aria-hidden="true"></span>
                        <button class="btn btn-primary btn-xs" type="button" data-provider-action="save" data-provider-type="${escapeHtml(provider.type)}">保存</button>
                    </div>
                </div>
                <div class="provider-inline-grid">
                    ${fields || '<article class="provider-inline-empty">该 Provider 暂无可配置字段</article>'}
                </div>
                <div class="provider-inline-actions">
                    <button class="btn btn-secondary btn-sm" type="button" data-provider-action="test" data-provider-type="${escapeHtml(provider.type)}">测试连接</button>
                    <button class="btn btn-secondary btn-sm" type="button" data-provider-action="preview" data-provider-type="${escapeHtml(provider.type)}">刮削预览</button>
                </div>
            </article>`;
    })
    .join("");
  bindProviderCardToggles(host);
}

function bindProviderCardToggles(host) {
  if (!host || host.dataset.toggleBound === "1") return;
  host.dataset.toggleBound = "1";
  host.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-toggle-provider-card]");
    if (!toggle) return;
    if (
      event.target.closest(
        "label, input, button, select, textarea, [data-provider-toggle], [data-provider-action]",
      )
    )
      return;
    const card = toggle.closest(".provider-inline-card");
    if (!card) return;
    card.classList.toggle("is-collapsed");
  });
  host.addEventListener("change", (event) => {
    const input = event.target.closest("[data-provider-toggle]");
    if (!input) return;
    const providerType = input.getAttribute("data-provider-toggle");
    const card = input.closest(".provider-inline-card");
    const status = host.querySelector(
      `[data-provider-status="${providerType}"]`,
    );
    const enabled = !!input.checked;
    if (card) {
      card.classList.toggle("is-disabled", !enabled);
    }
    if (status) {
      status.textContent = enabled ? "已启用" : "未启用";
      status.classList.toggle("is-enabled", enabled);
      status.classList.toggle("is-disabled-status", !enabled);
    }
  });
}

async function loadInlineProviderConfigs(metadata) {
  const host = document.getElementById("provider-inline-stack");
  if (!host) return;
  host.innerHTML =
    '<article class="provider-inline-empty">正在加载 Provider 配置...</article>';
  try {
    const result = await requestApi("GET", "/providers");
    if (
      result.code !== 200 ||
      !result.data ||
      !Array.isArray(result.data.providers)
    ) {
      host.innerHTML =
        '<article class="provider-inline-empty">Provider 配置加载失败</article>';
      return;
    }
    renderInlineProviderConfigs(
      result.data.providers,
      metadata.providers || [],
    );
  } catch (error) {
    host.innerHTML =
      '<article class="provider-inline-empty">Provider 配置加载失败</article>';
  }
}

function renderRuleList(pathRules) {
  const list = document.getElementById("rules-inline-list");
  if (!list) return;
  if (!Array.isArray(pathRules) || pathRules.length === 0) {
    list.innerHTML =
      '<button class="rule-inline-empty rule-inline-add" type="button" data-rule-action="add">+</button>';
    return;
  }
  const dims = currentEnabledDimensions.length ? currentEnabledDimensions : [];
  const palette = [
    "#3b82f6",
    "#f59e0b",
    "#ec4899",
    "#8b5cf6",
    "#10b981",
    "#06b6d4",
    "#f97316",
    "#ef4444",
    "#14b8a6",
    "#a855f7",
    "#eab308",
    "#22c55e",
  ];
  list.innerHTML =
    pathRules
      .map((rule, index) => {
        const titleText =
          (rule.name && String(rule.name).trim()) || `规则 ${index + 1}`;
        const template = rule.template || "未设置模板";
        const root = libraryRootById(rule.library_root_id || defaultLibraryRootId());
        const conditions = rule.conditions || {};
        const entries = Object.entries(conditions);
        const templateChip = `<span class="rule-chip rule-chip--template" title="${escapeHtml(template)}">${escapeHtml(template)}</span>`;
        let conditionsHTML;
        if (entries.length === 0) {
          conditionsHTML =
            '<span class="rule-chip rule-chip--empty">无条件</span>';
        } else {
          conditionsHTML = entries
            .map(([key, value]) => {
              const dim =
                dims.find((d) => d.name === key) ||
                (_dimensionsData || []).find((d) => d.name === key);
              const dimLabel = dim ? dim.label || dim.name : key;
              const dimColor =
                dim && dim.color ? dim.color : palette[index % palette.length];
              const vals = String(value)
                .split("|")
                .map((v) => v.trim())
                .filter(Boolean);
              const valText = vals.length
                ? vals
                    .map((v) => (dim ? _dimValueToLabel(dim, v) : v))
                    .join(" | ")
                : "(不限制)";
              return `<span class="rule-chip rule-chip--dim" style="--chip-color:${escapeHtml(dimColor)}" title="${escapeHtml(dim ? dim.name : key)}"><span class="dim-label">${escapeHtml(dimLabel)}</span>：${escapeHtml(valText)}</span>`;
            })
            .join("");
        }
        return `
            <article class="rule-inline-item">
                <div class="rule-inline-main">
                    <div class="rule-inline-title-row">
                        <strong>${escapeHtml(titleText)}</strong>
                        <span class="rule-inline-index">#${index + 1}</span>
                    </div>
                    <div class="rule-inline-rows">
                        <div class="rule-inline-row">
                            <span class="rule-inline-row-label">规则</span>
                            <div class="rule-inline-chips">${conditionsHTML}</div>
                        </div>
                        <div class="rule-inline-row">
                            <span class="rule-inline-row-label">入库目录</span>
                            <div class="rule-inline-chips"><span class="rule-chip rule-chip--root">${escapeHtml(root?.name || "未绑定片库")}</span>${templateChip}</div>
                        </div>
                    </div>
                </div>
                <div class="rule-inline-meta">
                    <b>${entries.length} 个条件</b>
                    <span>命中即止</span>
                </div>
                <div class="rule-inline-actions">
                    <button class="btn btn-secondary btn-sm" type="button" data-rule-action="edit" data-rule-index="${index}">编辑</button>
                    <button class="btn btn-secondary btn-sm" type="button" data-rule-action="delete" data-rule-index="${index}">删除</button>
                </div>
            </article>`;
      })
      .join("") +
    '<button class="rule-inline-empty rule-inline-add" type="button" data-rule-action="add">+</button>';
}

function renderDimensionVarList(dimensions) {
  const container = document.getElementById("rules-dimension-vars");
  if (!container) return;
  if (!Array.isArray(dimensions) || dimensions.length === 0) {
    container.innerHTML =
      '<div class="rule-inline-empty">暂无启用的维度变量</div>';
    return;
  }
  container.innerHTML = dimensions
    .map((dim) => {
      const label = dim.label || dim.display_name || dim.name || "未命名维度";
      const valueList = Array.isArray(dim.value_list) ? dim.value_list : [];
      const valuesHint = valueList
        .filter((item) => item && item.value !== "")
        .map((item) => item.label || item.value)
        .join(" / ");
      return `<div class="var-token-line"><code>{dimension.${dim.name}}</code><span>${label}${valuesHint ? `（${valuesHint}）` : ""}</span></div>`;
    })
    .join("");
}

async function loadDimensionVars() {
  const result = await requestApi("GET", "/dimensions/enabled");
  if (result.code !== 200 || !result.data) {
    currentEnabledDimensions = [];
    renderDimensionVarList([]);
    return;
  }
  currentEnabledDimensions = result.data.dimensions || [];
  renderDimensionVarList(currentEnabledDimensions);
}

function toggleVarGroup(group) {
  const button = document.querySelector(`[data-var-group="${group}"]`);
  const panel = document.querySelector(`[data-var-panel="${group}"]`);
  if (!button || !panel) return;
  const next = !button.classList.contains("active");
  button.classList.toggle("active", next);
  panel.classList.toggle("active", next);
}

function getEditablePathRules() {
  return Array.isArray(currentConfigSnapshot?.path_rules)
    ? [...currentConfigSnapshot.path_rules]
    : [];
}

function parseRuleConditionValue(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (raw.includes("|"))
    return raw
      .split("|")
      .map((item) => item.trim())
      .filter(Boolean)
      .join("|");
  if (raw.includes(","))
    return raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .join("|");
  return raw;
}

// MULTI_SELECT_DIMS is declared in cinema-tasks.js; reuse the global

function _dimValueToLabel(dim, val) {
  const list = Array.isArray(dim.value_list) ? dim.value_list : [];
  for (const item of list) {
    if (item.value === val) return item.label || item.value;
  }
  return val;
}

function openRuleEditor(index = -1) {
  const pathRules = getEditablePathRules();
  const target = index >= 0 ? pathRules[index] || {} : {};
  const dimensions = currentEnabledDimensions.length
    ? currentEnabledDimensions
    : [];
  const fields = dimensions
    .map((dim) => {
      const value = target.conditions?.[dim.name] || "";
      const valueList = Array.isArray(dim.value_list) ? dim.value_list : [];
      const isMulti = MULTI_SELECT_DIMS.includes(dim.name);
      const dimLabel = escapeHtml(dim.label || dim.name);

      if (isMulti) {
        const selectedValues = value
          ? String(value)
              .split("|")
              .map((s) => s.trim())
              .filter(Boolean)
          : [];
        const checkboxes = valueList
          .map((item) => {
            const checked = selectedValues.includes(item.value)
              ? " checked"
              : "";
            return `<label class="rule-editor-checkbox-label"><input type="checkbox" data-rule-dim="${escapeHtml(dim.name)}" value="${escapeHtml(item.value)}"${checked} />${escapeHtml(item.label || item.value)}</label>`;
          })
          .join("");
        return `
                <label class="cinema-modal-field cinema-modal-field--multi">
                    <span>${dimLabel}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small>（可多选）</span>
                    <div class="rule-editor-checkbox-group">${checkboxes}</div>
                </label>`;
      }

      const options = ['<option value="">(不限制)</option>']
        .concat(
          valueList.map((item) => {
            const selected = value === item.value ? " selected" : "";
            return `<option value="${escapeHtml(item.value)}"${selected}>${escapeHtml(item.label || item.value)}</option>`;
          }),
        )
        .join("");
      return `
            <label class="cinema-modal-field">
                <span>${dimLabel}<small class="cinema-modal-field-code">${escapeHtml(dim.name)}</small></span>
                <select data-rule-dim="${escapeHtml(dim.name)}">${options}</select>
            </label>`;
    })
    .join("");
  const ruleName = target.name || "";
  const roots = normalizedLibraryRoots().filter((root) => root.enabled);
  const selectedRootId = target.library_root_id || defaultLibraryRootId();
  const overlay = showAppModal({
    title: index >= 0 ? `编辑规则 ${ruleName || index + 1}` : "新增入库规则",
    dismissOnBackdrop: false,
    body: `
            <div class="cinema-modal-stack">
                <label class="cinema-modal-field">
                    <span>目标片库</span>
                    <select id="rule-library-root-input">${roots.map((root) => `<option value="${escapeHtml(root.id)}"${root.id === selectedRootId ? " selected" : ""}>${escapeHtml(root.name)}</option>`).join("")}</select>
                    <small>命中这条规则后，文件只会写入所选片库。</small>
                </label>
                <label class="cinema-modal-field">
                    <span>规则名称（可选）</span>
                    <input type="text" id="rule-name-input" value="${escapeHtml(ruleName)}" placeholder="如：家庭向动漫剧集" maxlength="40" />
                    <small>用于在卡片上区分多条规则，留空时回退显示"规则 N"。</small>
                </label>
                <label class="cinema-modal-field">
                    <span>入库路径模板</span>
                    <input type="text" id="rule-template-input" value="${escapeHtml(target.template || "")}" placeholder="电影/{year}/{title_cn}/" />
                    <small>填写片库根目录下的相对子目录模板，不能使用绝对路径或 ..。</small>
                </label>
                ${fields || '<div class="cinema-modal-hint">当前还没有启用的分类维度，先去"影视分类维度"启用后再补充条件。</div>'}
            </div>`,
    actions: [
      { label: "取消", className: "btn btn-secondary" },
      {
        label: index >= 0 ? "保存规则" : "新增规则",
        className: "btn btn-primary",
        closeOnClick: false,
        onClick: async () => {
          const template = String(
            document.getElementById("rule-template-input")?.value || "",
          ).trim();
          if (!template) {
            showToast("入库路径模板不能为空");
            return;
          }
          if (template.startsWith("/") || template.split(/[\\/]+/).includes("..")) {
            showToast("规则路径必须是片库根目录下的相对子目录");
            return;
          }
          const name = String(
            document.getElementById("rule-name-input")?.value || "",
          ).trim();
          const conditions = {};
          overlay.querySelectorAll("[data-rule-dim]").forEach((el) => {
            if (el.tagName === "SELECT") {
              const v = el.value;
              if (v) conditions[el.dataset.ruleDim] = v;
            } else if (el.type === "checkbox") {
              if (!conditions[el.dataset.ruleDim])
                conditions[el.dataset.ruleDim] = [];
              if (el.checked) conditions[el.dataset.ruleDim].push(el.value);
            }
          });
          Object.keys(conditions).forEach((key) => {
            if (Array.isArray(conditions[key])) {
              if (conditions[key].length)
                conditions[key] = conditions[key].join("|");
              else delete conditions[key];
            }
          });
          const libraryRootId = String(document.getElementById("rule-library-root-input")?.value || "");
          if (!libraryRootId) { showToast("请先添加并选择目标片库"); return; }
          const nextRule = { conditions, template, library_root_id: libraryRootId };
          if (name) nextRule.name = name;
          if (index >= 0) pathRules[index] = nextRule;
          else pathRules.push(nextRule);
          currentConfigSnapshot = {
            ...(currentConfigSnapshot || {}),
            path_rules: pathRules,
          };
          renderRuleList(pathRules);
          removeAppModal();
          showToast(
            index >= 0
              ? "规则已更新，记得点击保存"
              : "规则已新增，记得点击保存",
          );
        },
      },
    ],
  });
  if (index >= 0) {
    const nameInput = overlay.querySelector("#rule-name-input");
    const titleEl = overlay.querySelector(".cinema-modal-header h3");
    if (nameInput && titleEl) {
      nameInput.addEventListener("input", () => {
        const trimmed = nameInput.value.trim();
        titleEl.textContent = `编辑规则 ${trimmed || index + 1}`;
      });
    }
  }
  return overlay;
}

function deleteInlineRule(index) {
  const pathRules = getEditablePathRules();
  if (!pathRules[index]) return;
  showConfirm("删除规则", `确定删除规则 ${index + 1} 吗？`, () => {
    pathRules.splice(index, 1);
    currentConfigSnapshot = {
      ...(currentConfigSnapshot || {}),
      path_rules: pathRules,
    };
    renderRuleList(pathRules);
    showToast("规则已删除，记得点击保存");
  });
}

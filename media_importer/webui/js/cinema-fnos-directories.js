// fnOS 共享目录选择与多片库根管理。真实 fnOS 环境不允许手填绕过系统 ACL。

let currentFnosDirectoryCapability = {
  available: false,
  enforced: false,
  folders: [],
  message: "尚未读取目录授权状态",
};
const FNOS_AUTH_PENDING_KEY = "nmmi-fnos-auth-pending";
const FNOS_AUTH_RESULT_KEY = "nmmi-fnos-auth-result";
const FNOS_AUTH_TTL_MS = 10 * 60 * 1000;
const FNOS_AUTH_REFRESH_DELAYS_MS = [0, 300, 700, 1200, 1800, 2600, 3400];
let lastConsumedFnosAuthState = "";

function setFnosAuthorizationRefreshState(active, message = "") {
  const host = document.getElementById("storage-readiness-grid");
  if (host) {
    host.setAttribute("aria-busy", active ? "true" : "false");
    host.classList.toggle("is-syncing-authorization", active);
    let notice = host.querySelector("[data-fnos-auth-sync-status]");
    if (active) {
      if (!notice) {
        notice = document.createElement("div");
        notice.className = "storage-auth-sync-status";
        notice.dataset.fnosAuthSyncStatus = "";
        notice.setAttribute("role", "status");
        notice.setAttribute("aria-live", "polite");
        host.prepend(notice);
      }
      notice.innerHTML = `<span aria-hidden="true"></span><div><b>正在同步 fnOS 目录权限</b><small>${escapeHtml(message || "系统授权已提交，正在确认应用权限并刷新列表…")}</small></div>`;
    } else {
      notice?.remove();
    }
  }
  document.querySelectorAll("[data-storage-refresh], [data-fnos-auth-role], [data-directory-pick], [data-library-root-action='edit']")
    .forEach((button) => {
      button.disabled = active;
      if (!button.matches("[data-storage-refresh]")) return;
      if (active) {
        button.dataset.originalLabel ||= button.textContent;
        button.textContent = "同步中…";
      } else {
        button.textContent = button.dataset.originalLabel || "重新检查";
        delete button.dataset.originalLabel;
      }
    });
}

async function waitForFnosAuthorizedPaths(expectedPaths, delays = FNOS_AUTH_REFRESH_DELAYS_MS) {
  const normalizedExpected = expectedPaths.map(normalizePathValue).filter(Boolean);
  let capability = currentFnosDirectoryCapability;
  for (const delay of delays) {
    if (delay > 0) await new Promise((resolve) => setTimeout(resolve, delay));
    capability = await getFnosAuthorizedFolders();
    const ready = !capability.enforced
      || normalizedExpected.every((path) => _authorizedRoot(path, capability.folders || []));
    if (ready) return { ready: true, capability };
  }
  return { ready: false, capability };
}

function normalizedLibraryRoots(config = currentConfigSnapshot) {
  const roots = Array.isArray(config?.library_roots)
    ? config.library_roots.filter((item) => item?.path).map((item, index) => ({
        id: String(item.id || `library-${index + 1}`),
        name: String(item.name || `片库 ${index + 1}`),
        path: normalizePathValue(item.path),
        enabled: item.enabled !== false,
      }))
    : [];
  if (!roots.length && config?.library_root) {
    roots.push({ id: "default", name: "主片库", path: normalizePathValue(config.library_root), enabled: true });
  }
  return roots;
}

function defaultLibraryRootId(config = currentConfigSnapshot) {
  const roots = normalizedLibraryRoots(config);
  const requested = String(config?.default_library_root_id || "");
  return roots.some((root) => root.id === requested) ? requested : roots[0]?.id || "";
}

function libraryRootById(rootId, config = currentConfigSnapshot) {
  return normalizedLibraryRoots(config).find((root) => root.id === rootId);
}

function renderLibraryRootList(config = currentConfigSnapshot) {
  const roots = normalizedLibraryRoots(config);
  const defaultId = defaultLibraryRootId(config);
  const host = document.getElementById("library-roots-list");
  if (host) {
    host.innerHTML = roots.length ? roots.map((root) => `
      <article class="library-root-item${root.id === defaultId ? " is-default" : ""}">
        <div class="library-root-copy"><div><b>${escapeHtml(root.name)}</b>${root.id === defaultId ? '<span class="library-root-default">默认</span>' : ""}${root.enabled ? "" : '<span class="library-root-disabled">已停用</span>'}</div><code>${escapeHtml(root.path)}</code></div>
        <div class="library-root-actions">
          ${root.id === defaultId ? "" : `<button class="btn btn-secondary btn-sm" type="button" data-library-root-action="default" data-library-root-id="${escapeHtml(root.id)}">设为默认</button>`}
          <button class="btn btn-secondary btn-sm" type="button" data-library-root-action="test" data-library-root-id="${escapeHtml(root.id)}">测试</button>
          <button class="btn btn-secondary btn-sm" type="button" data-library-root-action="edit" data-library-root-id="${escapeHtml(root.id)}">编辑</button>
          <button class="btn btn-secondary btn-sm" type="button" data-library-root-action="delete" data-library-root-id="${escapeHtml(root.id)}">移除</button>
        </div>
      </article>`).join("") : '<button class="rule-inline-empty rule-inline-add" type="button" data-library-root-action="add">+ 添加第一个片库</button>';
  }
  const fallback = document.getElementById("cfg-fallback-root-inline");
  if (fallback) {
    const selected = String(config?.fallback_library_root_id || "");
    fallback.innerHTML = '<option value="">请选择兜底目标片库</option>' + roots.filter((root) => root.enabled)
      .map((root) => `<option value="${escapeHtml(root.id)}"${root.id === selected ? " selected" : ""}>${escapeHtml(root.name)}</option>`).join("");
  }
}

function _setLibraryRoots(roots, defaultId = "") {
  currentConfigSnapshot = { ...(currentConfigSnapshot || {}), library_roots: roots, default_library_root_id: defaultId || roots[0]?.id || "" };
  renderLibraryRootList(currentConfigSnapshot);
  renderRuleList(currentConfigSnapshot.path_rules || []);
}

async function getFnosAuthorizedFolders() {
  const result = await requestApi("GET", "/config/fnos-folders");
  currentFnosDirectoryCapability = result.code === 200 && result.data
    ? result.data
    : { available: false, enforced: false, folders: [], message: result.message || "无法读取 fnOS 授权目录" };
  return currentFnosDirectoryCapability;
}

function _fnosSystemOrigin() {
  try { if (document.referrer) return new URL(document.referrer).origin; } catch (_error) {}
  return location.origin;
}

function _fnosCallbackUrl() {
  return `${location.origin}${getApiBase()}/fnos-auth-callback.html`;
}

function _createFnosAuthState() {
  const random = new Uint32Array(4);
  crypto.getRandomValues(random);
  return `nmmi-${Array.from(random).map((item) => item.toString(16)).join("")}`;
}

function openFnosSharedAuthorization({ role = "source", path = "" } = {}) {
  const state = _createFnosAuthState();
  const knownPath = normalizePathValue(path);
  const route = knownPath ? "/app-auth/authorize-shared-file" : "/app-auth/pick-shared-file";
  const url = new URL(route, _fnosSystemOrigin());
  const parameters = {
    appName: "nas-media-importer",
    title: knownPath ? "重新授权目录" : "选择并授权目录",
    okText: "确认授权",
    redirectUri: _fnosCallbackUrl(),
    state,
    sidebarGroup: "myFiles,otherShare,external,remote,favorites",
  };
  if (knownPath) parameters.path = knownPath;
  Object.entries(parameters).forEach(([key, value]) => url.searchParams.set(key, value));
  localStorage.setItem(FNOS_AUTH_PENDING_KEY, JSON.stringify({
    state, role, path: knownPath, appName: "nas-media-importer", createdAt: Date.now(),
  }));
  const popup = window.open(url.toString(), "fnos-directory-auth", "width=750,height=630");
  if (!popup) {
    localStorage.removeItem(FNOS_AUTH_PENDING_KEY);
    showToast("浏览器阻止了目录选择窗口，请允许弹窗后重试");
  }
}

function _parseAuthorizedPaths(value) {
  if (Array.isArray(value)) return value.filter((item) => typeof item === "string");
  if (typeof value !== "string") return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [value];
  } catch (_error) {
    return value ? [value] : [];
  }
}

function _directoryRoleMeta(role) {
  return {
    source: { title: "选择文件来源目录", success: "文件来源已选择并保存", localOnly: false },
    recycle: { title: "选择本地回收目录", success: "本地回收目录已保存", localOnly: true },
    log: { title: "选择运行日志目录", success: "运行日志目录已保存", localOnly: true },
    resource: { title: "选择海报与缓存目录", success: "海报与缓存目录已保存", localOnly: true },
  }[role] || null;
}

function _directoryRoleValue(role, config = currentConfigSnapshot) {
  const policy = config?.source_policy || {};
  return normalizePathValue({
    source: config?.source_dir,
    recycle: policy.recycle_dir || policy.quarantine_dir,
    log: config?.log_dir,
    resource: config?.resource_dir || config?.resources_dir,
  }[role] || "");
}

function _directoryRolePatch(role, value) {
  if (role === "source") return { source_dir: value };
  if (role === "log") return { log_dir: value };
  if (role === "resource") return { resource_dir: value };
  if (role === "recycle") {
    return {
      source_policy: {
        ...(currentConfigSnapshot?.source_policy || {}),
        recycle_dir: value,
      },
    };
  }
  return {};
}

async function saveStorageDirectoryRole(role, value) {
  const meta = _directoryRoleMeta(role);
  if (!meta || !value) return { code: 400, message: "未知目录角色" };
  return saveConfigPayload(_directoryRolePatch(role, value), meta.success);
}

async function _completeFnosAuthorization(result) {
  if (result?.state && result.state === lastConsumedFnosAuthState) return;
  let pending = null;
  try { pending = JSON.parse(localStorage.getItem(FNOS_AUTH_PENDING_KEY) || "null"); } catch (_error) {}
  const expired = !pending?.createdAt || Date.now() - Number(pending.createdAt) > FNOS_AUTH_TTL_MS;
  const wrongApp = result?.appName && result.appName !== pending?.appName;
  if (!pending || expired || wrongApp || result?.state !== pending.state) {
    if (expired) localStorage.removeItem(FNOS_AUTH_PENDING_KEY);
    showToast("目录授权回调校验失败，请重新选择目录");
    return;
  }
  lastConsumedFnosAuthState = result.state;
  localStorage.removeItem(FNOS_AUTH_PENDING_KEY);
  localStorage.removeItem(FNOS_AUTH_RESULT_KEY);
  if (String(result.status || "").toLowerCase() !== "success") {
    showToast(result.error || "没有完成目录授权");
    return;
  }
  const paths = _parseAuthorizedPaths(result.path);
  const selected = paths[0] || pending.path;
  const expectedPaths = paths.length ? paths : selected ? [selected] : [];
  setFnosAuthorizationRefreshState(true);
  showToast("fnOS 授权已提交，正在同步目录状态…");
  try {
    const syncResult = await waitForFnosAuthorizedPaths(expectedPaths);
    const capability = syncResult.capability;
    if (!syncResult.ready) {
      showToast("fnOS 授权同步较慢，可稍后点击“重新检查”确认状态");
      return;
    }
    if (selected && _directoryRoleMeta(pending.role)) {
      const saved = await saveStorageDirectoryRole(pending.role, selected);
      if (saved.code !== 200) return;
      renderFnosAuthorizationBoard(currentConfigSnapshot, capability);
      showToast("目录已保存，授权状态已更新");
      return;
    }
    if (pending.role === "library") {
      const roots = normalizedLibraryRoots();
      const additions = [];
      expectedPaths
        .filter((path) => !roots.some((root) => root.path === normalizePathValue(path)))
        .forEach((path, index) => {
          const normalizedPath = normalizePathValue(path);
          if (additions.some((item) => item.path === normalizedPath)) return;
          const name = normalizedPath.split("/").filter(Boolean).pop() || `片库 ${roots.length + index + 1}`;
          additions.push({
            id: _nextLibraryId(name, [...roots, ...additions]),
            name,
            path: normalizedPath,
            enabled: true,
          });
        });
      if (additions.length) {
        setFnosAuthorizationRefreshState(false);
        showToast("目录授权已同步，请确认片库名称");
        await confirmLibraryRootAdditions(additions);
        return;
      }
    }
    await loadDirectoryConfig();
    renderFnosAuthorizationBoard(currentConfigSnapshot, capability);
    showToast("授权状态已更新");
  } catch (error) {
    console.warn("同步 fnOS 目录授权失败", error);
    showToast("暂时无法读取 fnOS 授权状态，请稍后重新检查");
  } finally {
    setFnosAuthorizationRefreshState(false);
  }
}

function initializeFnosAuthorizationBridge() {
  window.addEventListener("message", (event) => {
    if (event.origin !== location.origin || event.data?.type !== "nmmi:fnos-auth-result") return;
    _completeFnosAuthorization(event.data.result || {});
  });
  const consumeStoredResult = () => {
    let stored = null;
    try { stored = JSON.parse(localStorage.getItem(FNOS_AUTH_RESULT_KEY) || "null"); } catch (_error) {}
    if (!stored?.result || Date.now() - Number(stored.receivedAt || 0) > FNOS_AUTH_TTL_MS) {
      if (stored) localStorage.removeItem(FNOS_AUTH_RESULT_KEY);
      return;
    }
    _completeFnosAuthorization(stored.result);
  };
  window.addEventListener("storage", (event) => {
    if (event.key === FNOS_AUTH_RESULT_KEY) consumeStoredResult();
  });
  window.addEventListener("focus", consumeStoredResult);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") consumeStoredResult();
  });
  consumeStoredResult();
}

function _authorizedRoot(path, folders = currentFnosDirectoryCapability.folders || []) {
  const candidate = normalizePathValue(path);
  return folders.filter((root) => candidate === root || candidate.startsWith(`${String(root).replace(/\/$/, "")}/`))
    .sort((left, right) => right.length - left.length)[0] || "";
}

function renderFnosAuthorizationBoard(config = currentConfigSnapshot, capability = currentFnosDirectoryCapability) {
  currentFnosDirectoryCapability = capability || currentFnosDirectoryCapability;
  const host = document.getElementById("fnos-directory-authorization");
  if (!host) return;
  const folders = Array.isArray(capability?.folders) ? capability.folders : [];
  const policy = config?.source_policy || {};
  const roles = [
    { role: "source", label: "文件来源", paths: [config?.source_dir || ""] },
    { role: "library", label: "目标片库", paths: normalizedLibraryRoots(config).map((root) => root.path) },
    { role: "recycle", label: "本地回收", paths: [policy.recycle_dir || policy.quarantine_dir || ""] },
  ];
  if (!capability?.enforced) {
    host.classList.add("is-development");
    host.innerHTML = `<div class="directory-auth-head"><div><span>FNOS DIRECTORY ACCESS</span><h3>当前为普通浏览器配置模式</h3><p>可手动填写路径；安装到 fnOS 后会改用系统目录选择器并校验应用权限。</p></div></div>`;
    return;
  }
  host.classList.remove("is-development");
  host.innerHTML = `<div class="directory-auth-head"><div><span>FNOS DIRECTORY ACCESS</span><h3>先授权目录，再分配用途</h3><p>路径写入配置不等于应用有权限。三类目录都通过后，任务才会开始。</p></div><button class="btn btn-secondary btn-sm" type="button" data-storage-refresh>刷新授权状态</button></div>
    <div class="directory-auth-roles">${roles.map((item) => {
      const configured = item.paths.filter(Boolean);
      const missing = configured.filter((path) => !_authorizedRoot(path, folders));
      const ready = configured.length > 0 && missing.length === 0 && capability.available;
      const path = missing[0] || "";
      return `<article class="directory-auth-role ${ready ? "is-ready" : "is-required"}"><span>${ready ? "已授权" : "需要处理"}</span><h4>${escapeHtml(item.label)}</h4><p>${ready ? `${configured.length} 个目录已获得应用权限` : configured.length ? "已有路径，但 fnOS 授权已失效" : "尚未选择目录"}</p><button class="btn ${ready ? "btn-secondary" : "btn-primary"} btn-sm" type="button" data-fnos-auth-role="${item.role}" data-fnos-auth-path="${escapeHtml(path)}">${path ? "重新授权" : ready ? "增加授权" : "选择并授权"}</button></article>`;
    }).join("")}</div>`;
  document.querySelectorAll("#cfg-source-inline, #cfg-recycle-inline").forEach((input) => { input.readOnly = true; });
}

async function confirmLibraryRootAdditions(additions) {
  const roots = normalizedLibraryRoots();
  return new Promise((resolve) => {
    let overlay = null;
    const namedAdditions = () => additions.map((item, index) => ({
      ...item,
      name: String(overlay?.querySelector(`[data-library-add-name="${index}"]`)?.value || item.name).trim() || item.name,
    }));
    const stageRoots = () => {
      const named = namedAdditions();
      const next = [...roots, ...named];
      _setLibraryRoots(next, defaultLibraryRootId() || named[0]?.id);
      return next;
    };
    const actions = [
      { label: "取消", className: "btn btn-secondary", onClick: () => resolve(false) },
    ];
    actions.push({
      label: "添加并保存",
      className: "btn btn-primary",
      closeOnClick: false,
      onClick: async () => {
        stageRoots();
        const result = await saveLibraryRootsConfig();
        if (result.code !== 200) return;
        removeAppModal();
        resolve(true);
      },
    });
    overlay = showAppModal({
      title: `确认 ${additions.length} 个目标片库`,
      dismissOnBackdrop: false,
      body: `<div class="cinema-modal-stack">
        <p class="cinema-modal-hint">每个目录都是独立片库，可以继续添加任意数量。名称之后仍可修改。</p>
        ${additions.map((item, index) => `<label class="cinema-modal-field"><span>片库 ${roots.length + index + 1} 名称</span><input data-library-add-name="${index}" type="text" maxlength="40" value="${escapeHtml(item.name)}" /><code>${escapeHtml(item.path)}</code></label>`).join("")}
      </div>`,
      actions,
    });
  });
}

async function chooseAuthorizedDirectory({ title, currentValue = "", localOnly = false, role = "source" } = {}) {
  const capability = await getFnosAuthorizedFolders();
  const folders = Array.isArray(capability.folders) ? capability.folders : [];
  return new Promise((resolve) => {
    const overlay = showAppModal({
      title: title || "选择目录",
      dismissOnBackdrop: false,
      body: `<div class="cinema-modal-stack">
        <p class="cinema-modal-hint">${escapeHtml(capability.available ? "下面是已经授权给本应用的目录。没有目标目录时，先打开 fnOS 系统选择器授权。" : capability.enforced ? `${capability.message || "fnOS 目录选择暂不可用"}。不能用手填路径绕过系统授权。` : `${capability.message || "当前不是 fnOS 托管环境"}，可手动填写用于本地开发。`)}</p>
        <label class="cinema-modal-field"><span>已授权目录</span><select id="authorized-folder-select"><option value="">请选择</option>${folders.map((path) => `<option value="${escapeHtml(path)}">${escapeHtml(path)}</option>`).join("")}</select></label>
        <label class="cinema-modal-field"><span>目录路径</span><input id="authorized-folder-manual" type="text" value="${escapeHtml(currentValue)}" placeholder="/vol1/..." ${capability.enforced ? "readonly" : ""} /></label>
        ${localOnly ? '<small class="cinema-modal-hint">此目录必须位于本地磁盘；远程挂载即使被选中也无法保存。</small>' : ""}
        <button class="btn btn-secondary" type="button" id="open-fnos-directory-auth">在 fnOS 添加授权目录</button>
      </div>`,
      actions: [
        { label: "取消", className: "btn btn-secondary", onClick: () => resolve("") },
        { label: "使用此目录", className: "btn btn-primary", closeOnClick: false, onClick: () => {
          const value = normalizePathValue(document.getElementById("authorized-folder-manual")?.value);
          if (!value) { showToast("请先选择或填写目录"); return; }
          resolve(value); removeAppModal();
        } },
      ],
    });
    overlay.querySelector("#authorized-folder-select")?.addEventListener("change", (event) => {
      const input = overlay.querySelector("#authorized-folder-manual");
      if (input && event.target.value) input.value = event.target.value;
    });
    overlay.querySelector("#open-fnos-directory-auth")?.addEventListener("click", () => {
      removeAppModal();
      openFnosSharedAuthorization({ role });
    });
  });
}

async function pickDirectoryForField(role) {
  const meta = _directoryRoleMeta(role);
  if (!meta) return;
  const value = await chooseAuthorizedDirectory({
    title: meta.title,
    currentValue: _directoryRoleValue(role),
    localOnly: meta.localOnly,
    role,
  });
  if (!value) return;
  await saveStorageDirectoryRole(role, value);
}

function _nextLibraryId(name, roots) {
  const base = String(name || "library").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-|-$/g, "") || "library";
  let candidate = base.slice(0, 56), index = 2;
  while (roots.some((root) => root.id === candidate)) candidate = `${base.slice(0, 52)}-${index++}`;
  return candidate;
}

async function openLibraryRootEditor(rootId = "") {
  const roots = normalizedLibraryRoots();
  const existing = roots.find((root) => root.id === rootId);
  const capability = await getFnosAuthorizedFolders();
  const authorizedFolders = Array.isArray(capability.folders) ? capability.folders : [];
  const overlay = showAppModal({
    title: existing ? `编辑 ${existing.name}` : "添加目标片库",
    dismissOnBackdrop: false,
    body: `<div class="cinema-modal-stack">
      <label class="cinema-modal-field"><span>片库名称</span><input id="library-root-name" type="text" maxlength="40" value="${escapeHtml(existing?.name || "")}" placeholder="如：电影盘、剧集盘" /></label>
      <label class="cinema-modal-field"><span>片库目录</span><input id="library-root-path" type="text" value="${escapeHtml(existing?.path || "")}" placeholder="/vol1/影视" ${capability.enforced ? "readonly" : ""} /><small>规则只能写入这个根目录下的相对子目录。</small></label>
      ${authorizedFolders.length ? `<label class="cinema-modal-field"><span>从已授权目录选择</span><select id="library-root-authorized"><option value="">请选择</option>${authorizedFolders.map((path) => `<option value="${escapeHtml(path)}">${escapeHtml(path)}</option>`).join("")}</select></label>` : `<p class="cinema-modal-hint">${escapeHtml(capability.message || "当前没有可用的 fnOS 授权目录")}${capability.enforced ? "；请先通过系统选择器授权。" : "；本地开发可手动填写。"}</p>`}
      <button class="btn btn-secondary" type="button" id="library-root-authorize">在 fnOS 添加授权目录</button>
      <label class="toggle-row-inline"><input id="library-root-enabled" type="checkbox"${existing?.enabled === false ? "" : " checked"} /><b>启用此片库</b></label>
    </div>`,
    actions: [
      { label: "取消", className: "btn btn-secondary" },
      { label: existing ? "保存" : "添加并保存", className: "btn btn-primary", closeOnClick: false, onClick: async () => {
        const name = String(overlay.querySelector("#library-root-name")?.value || "").trim();
        const path = normalizePathValue(overlay.querySelector("#library-root-path")?.value);
        if (!name || !path) { showToast("请填写片库名称和目录"); return; }
        if (roots.some((root) => root.id !== rootId && root.path === path)) { showToast("这个目录已经添加过"); return; }
        const next = { id: existing?.id || _nextLibraryId(name, roots), name, path, enabled: !!overlay.querySelector("#library-root-enabled")?.checked };
        _setLibraryRoots(existing ? roots.map((root) => root.id === rootId ? next : root) : [...roots, next], defaultLibraryRootId() || next.id);
        const result = await saveLibraryRootsConfig();
        if (result.code !== 200) return;
        removeAppModal();
      } },
    ],
  });
  overlay.querySelector("#library-root-authorized")?.addEventListener("change", (event) => {
    const input = overlay.querySelector("#library-root-path");
    if (input && event.target.value) input.value = event.target.value;
  });
  overlay.querySelector("#library-root-authorize")?.addEventListener("click", () => {
    removeAppModal();
    openFnosSharedAuthorization({ role: "library", path: existing?.path || "" });
  });
}

function handleLibraryRootAction(action, rootId) {
  const roots = normalizedLibraryRoots();
  if (action === "add") return openLibraryRootEditor();
  if (action === "edit") return openLibraryRootEditor(rootId);
  if (action === "default") { _setLibraryRoots(roots, rootId); saveLibraryRootsConfig(); return; }
  if (action === "test") { const root = libraryRootById(rootId); if (root) testPathValue(root.path, root.name); return; }
  if (action === "delete") {
    const used = (currentConfigSnapshot?.path_rules || []).some((rule) => rule.library_root_id === rootId)
      || currentConfigSnapshot?.fallback_library_root_id === rootId;
    if (used) { showToast("这个片库仍被规则或兜底目录使用，请先迁移这些引用"); return; }
    showConfirm("移除片库", "只移除配置，不会删除片库中的文件。确定继续吗？", async () => {
      const updated = roots.filter((root) => root.id !== rootId);
      _setLibraryRoots(updated, defaultLibraryRootId() === rootId ? updated[0]?.id : defaultLibraryRootId());
      await saveLibraryRootsConfig();
    });
  }
}

async function testPathValue(path, label) {
  const result = await requestApi("POST", "/path/test", { path, need_write: true });
  showPathTestFeedback(result, label);
}

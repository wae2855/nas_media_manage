const DEMO_TASKS = [
    { title: "沙丘 2", status: "已入库", desc: "TMDB 命中 · 字幕已重命名 · 1080p / BluRay", meta: "置信度 96%", tone: "gold" },
    { title: "Unknown.Movie.2024", status: "待确认", desc: "AI 识别不确定，需要选择电影/剧集并确认标题。", meta: "置信度 62%", tone: "red" },
    { title: "银河护卫队 S01E03", status: "失败", desc: "Provider 连接超时，保留临时文件等待重试。", meta: "重试 1 次", tone: "cyan" },
];

const DEMO_RECYCLE = [
    { title: "沙丘.旧版本.mkv", status: "可恢复", desc: "来源：入库覆盖 · 原路径 /movies/Dune/", meta: "18.4GB", tone: "red" },
    { title: "Sample.AD.trailer.mp4", status: "源清理", desc: "来源：源目录清理 · 判断为广告/样片。", meta: "840MB", tone: "gold" },
];

function setView(view, navKey = view) {
    document.querySelectorAll(".page-view").forEach((page) => {
        page.classList.toggle("active", page.dataset.view === view);
    });
    document.querySelectorAll(".nav-item").forEach((item) => {
        item.classList.toggle("active", item.dataset.nav === navKey);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => toast.classList.remove("show"), 2400);
}

async function requestApi(method, endpoint) {
    if (typeof apiRequest === "function") {
        return apiRequest(method, endpoint);
    }
    return { code: 500, message: "API helper unavailable" };
}

async function runAction(action) {
    const endpointByAction = { scan: "/run", pause: "/queue/pause", retry: "/queue/retry-all" };
    if (!endpointByAction[action]) {
        showToast("展示阶段：该功能将在功能接线阶段完成");
        return;
    }
    const result = await requestApi("POST", endpointByAction[action]);
    showToast(result.message || "请求已发送");
}

function renderTaskCard(item) {
    const danger = item.status === "失败" || item.status === "待确认" ? " danger" : "";
    return `
        <article class="task-card">
            <div class="cover cover-${item.tone}"></div>
            <div class="task-body">
                <div class="task-top"><h3>${item.title}</h3><span class="badge${danger}">${item.status}</span></div>
                <p>${item.desc}</p>
                <div class="task-meta"><span>${item.meta}</span><span>展示阶段</span></div>
            </div>
            <div class="task-actions"><button data-action="placeholder">详情</button><button data-action="placeholder">操作</button></div>
        </article>`;
}

function renderStaticLists() {
    document.getElementById("task-list").innerHTML = DEMO_TASKS.map(renderTaskCard).join("");
    document.getElementById("recycle-list").innerHTML = DEMO_RECYCLE.map(renderTaskCard).join("");
    document.getElementById("recycle-count").textContent = String(DEMO_RECYCLE.length);
}

async function loadDashboardMetrics() {
    const result = await requestApi("GET", "/metrics");
    if (result.code !== 200 || !result.data) return;
    const queue = result.data.queue_by_status || {};
    document.getElementById("metric-pending").textContent = queue.PENDING || queue.pending || 0;
    document.getElementById("metric-confirm").textContent = queue.CONFIRMING || queue.confirming || 0;
    document.getElementById("metric-success").textContent = queue.SUCCESS || queue.success || 0;
}

async function loadDirectoryConfig() {
    const result = await requestApi("GET", "/config");
    if (result.code !== 200 || !result.data) return;
    const paths = result.data.paths || result.data || {};
    document.getElementById("dir-source").textContent = paths.source_dir || "未配置";
    document.getElementById("dir-temp").textContent = paths.temp_dir || "未配置";
    document.getElementById("dir-recycle").textContent = paths.recycle_dir || "未配置";
}

function bindEvents() {
    document.addEventListener("click", (event) => {
        const nav = event.target.closest("[data-nav]");
        if (nav) setView(nav.dataset.viewTarget || nav.dataset.nav, nav.dataset.nav);
        const action = event.target.closest("[data-action]");
        if (action) runAction(action.dataset.action);
    });
    const expandMore = document.querySelector(".expand-more");
    const moreMenu = document.getElementById("more-config-menu");
    expandMore.addEventListener("click", () => {
        document.querySelector(".more-config-list").classList.add("is-expanded");
        expandMore.setAttribute("aria-expanded", "true");
        moreMenu.setAttribute("aria-hidden", "false");
    });
}

document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    renderStaticLists();
    loadDashboardMetrics();
    loadDirectoryConfig();
    if (typeof checkApiKeyRequired === "function") checkApiKeyRequired();
});

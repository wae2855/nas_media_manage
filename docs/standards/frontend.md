# Frontend UI Standards

---
title: frontend-ui-standards
type: standard
date: 2026-08-27
status: accepted
---

> 基于 cinema 主题现状总结（简洁化 Phase 0-4 + 文案同步后）。改前端前必读。

## 1. 技术边界

- 零依赖原生 HTML/CSS/JS，**禁止引入**框架、构建工具、npm 依赖、i18n 库。
- 文件只放 `webui/`：`index.html`（主视图+配置面板）+ `partials/advanced-pages.html`（高级页）+ `js/` + `css/` + `assets/`。
- 入口加载序固定（index.html 底部 script 顺序即依赖顺序，无模块系统）：

```text
基础设施:  api.js → tmdb-dict.js → cinema-modals.js
应用壳:    cinema-app-state → app-events → app → reel/dashboard
任务域:    task-utils → task-list → task-detail(-open) → task-batch → tasks
维度域:    dimension-core → genre(-picker) → edit → ops → dimensions
配置域:    config-payloads → save → provider → ai → rules → simulator(-extra) → dim-ops → config → directory-loader
```

## 2. CSS 规范

6 个语义文件，加载序即优先级序（后者覆盖前者）：

| 文件 | 职责 |
|------|------|
| `cinema-tokens.css` | 设计变量（颜色/间距/字号，cinema 金色调 `--gold`/`--ink` 系） |
| `cinema-layout.css` | 应用壳、底部导航、页面骨架 |
| `components.css` | 通用组件（按钮/表单/徽章/卡片） |
| `cinema-pages.css` | 页面级样式（首页/任务/回收/模拟器） |
| `cinema-config.css` | 配置页（stage 导航/折叠卡/清理器/维度编辑） |
| `dimensions.css` | 维度管理页 |

规则：
- **禁止新建第 7 个 CSS 文件**；新样式按语义归入现有文件。
- 颜色/间距一律用 `var(--xxx)`；新增变量先进 tokens.css。
- 禁止内联 `style=""`（存量模拟器内联为历史，新代码不得效仿）。
- 组件样式写进 components.css，页面私有样式才进 pages/config。

## 3. 视图与导航模型

- 页面切换：`data-view`（目标 section）+ `data-nav`（导航按钮）+ `data-view-target`（跨视图跳转）。
- 配置页二级面板：`data-config-stage`（顶部阶段卡）↔ `data-config-panel`（面板）。
- 新页面 = index.html 或 partials 加 `<section class="page-view" data-view="xxx">` + 底部导航按钮；不改 JS 路由逻辑（app-events 事件委托自动生效）。

## 4. JS 规范

- **全局函数即模块接口**（无 export，靠加载序）；新文件必须在 index.html 登记加载位置。
- 全局工具必须复用，禁止重写：

| 工具 | 用途 |
|------|------|
| `requestApi(method, path, body)` | 唯一 API 入口（自动带 Bearer 认证/错误提示） |
| `showToast(msg)` / `showConfirm(title, msg, onConfirm)` | 反馈/确认 |
| `escapeHtml(s)` | **所有动态内容注入 DOM 前必须转义**（XSS 防线） |

- 状态判定统一走 `task-utils.js`（`getTaskStatusText`/状态色/操作按钮），禁止在各页面重复写 status/stage 分支。
- DOM 查询用 `document.getElementById`/`querySelector`；事件绑定集中在 app-events（事件委托）。

## 5. 文案规范（防漂移红线）

- **退役词禁止出现**（`scripts/check_docs.py` 的 `RETIRED_UI_TERMS` 扫描，出现即 FAIL）：
  `三级匹配`、`AI上下文`、`AI辅助匹配`、`AI联网/联网搜索`、`AI 判定`、`Hermes`、`飞书`、`MCP 联网`。
- 产品名统一「**影音库智能整理**」（包名 nas-media-importer 不变）。
- LLM 只描述为「源目录清理器的可选辅助」，不得暗示参与刮削/匹配/维度判断。
- 状态术语 7 个枚举（与后端 status/stage 对应）：`排队中`、`处理中`、`待确认`、`成功入库`、`失败`、`已跳过`、`已取消`。
- 重试文案必须体现断点续跑语义（"中转文件仍存在时将从断点继续"）。
- 批量重试只针对 FAILED；SKIPPED/CANCELLED 是用户终态决策，不进批量复活范围。
- 历史数据的 AI 来源字段（`ai_assist`/`ai_search`/`CONTEXT_PASS`）只标「历史」，不得伪装为现行行为。

## 6. 安全与体验底线

- 动态内容一律 `escapeHtml`；`innerHTML` 拼接前逐段检查。
- 敏感信息（API Key）显示掩码，保存时空值=保持不变（`preserveApiKey` 模式）。
- 破坏性操作（删除/清空/批量）必须过 `showConfirm`。
- 失败提示给出下一步动作（"检查 Provider 配置或后端日志"），不只报错。

## 7. 变更前置 checklist

1. 新页面/面板：登记 data-view + 导航 + CSS 归属文件。
2. 新 API 调用：走 requestApi；401 处理已内置。
3. 文案改动：跑 `python scripts/check_docs.py`（含退役词扫描）。
4. 提交前：`node --check` 改动的 js 文件；浏览器冒烟目标页面无 console error（favicon 404 除外）。

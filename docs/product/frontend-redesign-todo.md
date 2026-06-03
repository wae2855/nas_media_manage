# Frontend Redesign Todo

前端重做是独立后续工作流。当前只登记待办，不在本次架构和文档重组中展开设计细节。

## Goals

- 基于 feature-first 后端文档重做信息架构。
- 让任务、配置、Provider、提示词、源目录清理、回收站等核心工作流更易理解和操作。
- 前端 API 依赖从 `docs/features/`、`docs/architecture/api.md` 和 `docs/INDEX.md` 获取。
- UI/E2E 深测在新前端稳定后重新设计。

## Required Planning Documents Later

- 产品工作流和用户路径。
- 页面信息架构。
- API dependency map。
- 设计稿或可运行原型。
- 验收截图/录屏要求。
- UI/E2E test plan。

## Current Status

Planning baseline is now available in [frontend-information-architecture.md](frontend-information-architecture.md) and [../architecture/frontend-api-dependency-map.md](../architecture/frontend-api-dependency-map.md). Do not treat old UI tests as final frontend acceptance criteria.

Cinema theme proposal and implementation plan are available in:

- [../proposals/2026-06-03-frontend-cinema-theme-proposal.md](../proposals/2026-06-03-frontend-cinema-theme-proposal.md)
- [../plans/2026-06-03-frontend-cinema-redesign-plan.md](../plans/2026-06-03-frontend-cinema-redesign-plan.md)

The user has accepted the black/gold cinema prototype as the first visual baseline. Current implementation focus is the real `webui` display shell; API wiring and full UI/E2E acceptance remain separate later phases.

---
title: "feat: fnOS 首次启动目录授权、多片库与离线依赖"
type: plan
date: 2026-08-30
status: implemented
confidence: high
requirement: REQ-20260830-180954
---

# fnOS 首次启动目录授权、多片库与离线依赖实施计划

- **Stories**: [用户故事](../../stories/fnos-first-run-multi-library.md)
- **Architecture**: [架构](../../stories/fnos-first-run-multi-library.architecture.md)
- **ADR**: [0016](../../decisions/0016-multiple-library-roots.md)、[0017](../../decisions/0017-fnos-first-run-directory-authorization.md)

## 任务分解

- [x] Phase 0：为旧配置迁移、多根引用、越界、重复根和存储检查补 RED 测试。
- [x] Phase 1：实现 `library_roots` 规范化、ConfigView、validator、保存 API 和单根兼容迁移。
- [x] Phase 2：分类、兜底、允许目录、存储 readiness 和任务执行切换为显式 root ID。
- [x] Phase 3：配置 UI 增加片库根列表、默认根、规则根选择和移动端布局。
- [x] Phase 4：实现 fnOS 授权目录查询适配器、首次启动目录选择及手动降级。
- [x] Phase 5：调整 fnOS 向导/资源声明，加入通用离线 wheelhouse 和安装阶段日志。
- [x] Phase 6：同步配置、API、部署、安全、产品和测试文档；完成自评审。

## 验收证据

- 非 UI 回归：745 passed。
- 多片库、fnOS 授权适配器与打包定向回归：90 passed。
- Ruff、compileall、JS 语法、Shell 语法与文档检查通过。
- 桌面 1440px 与移动端 390px 浏览器实测通过，无横向溢出与控制台错误。
- FPK 0.3.2 结构校验通过，离线 wheelhouse 仅包含 `py3-none-any` wheel。
- 待验收：fnOS 实机安装、宿主目录授权弹窗、多个真实硬盘/网盘挂载与首次运行检查。

## 验收标准

- 至少五个片库根可配置；规则明确显示目标片库，最终路径不能逃逸绑定根。
- 旧单根配置自动迁移且相同模拟输入得到相同目标路径。
- fnOS 内可选择并授权目录；不可用时手填仍可完成，且不会绕过权限/存在/容量校验。
- 回收目录无法保存为远程存储。
- 项目依赖安装不访问公网；系统 Python 与项目依赖阶段可在日志中区分。

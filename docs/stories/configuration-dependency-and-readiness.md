# 配置依赖与运行就绪

- **Requirement**: [REQ-20260828-151346](../tracking/requirements-board.md)
- **Brainstorm**: [配置依赖、来源单元与开场检查](../brainstorms/2026-08-28-configuration-dependency-and-readiness-brainstorm.md)

## STORY-001: 用户选择明确的来源处理模式

**As a** fnOS 影音库用户
**I want** 在一个父卡片内选择源目录的处理方式
**So that** 我能理解系统会不会修改源目录以及会启用哪些清理能力

### Acceptance Criteria

- [x] 页面只提供 `保持源目录不变`、`保留源视频，仅整理垃圾`、`入库后清空来源内容` 三种互斥模式。
- [x] 模式 1 隐藏并禁用垃圾清理与 LLM，源目录只要求读取权限。
- [x] 模式 2、3 展开各自清理策略；模式 3 明确展示“整个来源单元进入本地回收站”。
- [x] 后端拒绝模式 1 与清理器启用的矛盾配置。

### Edge Cases

- 旧配置同时为保留源文件和启用清理器：迁移为模式 2。
- 旧配置缺失两个开关：迁移为模式 1。

### Notes

- [INTEGRATION] `ConfigView`、loader、validator、配置 API 与文件来源 UI。

## STORY-002: 系统按来源单元安全清空内容

**As a** 希望释放来源空间的用户
**I want** 一个影视文件夹内所有任务成功后整体回收该文件夹
**So that** 海报、说明文件和其他伴生内容不会残留在来源目录

### Acceptance Criteria

- [x] 顶层来源文件夹内任一媒体任务失败、待确认、处理中或未稳定时，整个文件夹保持不动。
- [x] 全部媒体任务成功后，文件夹整体移入本地回收站，来源根目录本身保留。
- [x] 来源根下全部直接文件形成一个根散文件单元；其中全部媒体成功后清空这些文件但保留来源根。
- [x] 清理前复核来源单元快照、挂载身份、回收目录容量和任务最终状态；变化时停止并重新扫描。
- [x] 整体回收失败不改变已成功入库结果，并形成可重试的清理状态。

### Edge Cases

- 文件夹在清理计划后新增文件：取消本次回收。
- 多集剧集部分成功：整体等待。
- 来源挂载掉线：整体等待，不创建同名本地目录。

### Notes

- [DEPENDENCY] STORY-001 — 只有模式 3 启用来源单元回收。
- [INTEGRATION] scanner、task DB、source_files、recycle ledger、verified transfer。

## STORY-003: 片库规则只能落在已校验根目录

**As a** 配置片库分类的用户
**I want** 只编辑片库根目录下的相对子目录模板
**So that** 每条规则都落在我已授权并检查过的存储位置

### Acceptance Criteria

- [x] 存储检查展示并验证一个明确的 `library_root`。
- [x] 片库整理 UI 不接受绝对路径和 `..` 越界，只编辑相对模板。
- [x] 服务端保存时 canonicalize 并验证所有规则与 fallback 最终位于 `library_root` 内。
- [x] 旧绝对规则位于同一根时无损迁移；跨根规则进入 BLOCKED，不静默改写。

### Edge Cases

- 符号链接指向根外：拒绝。
- 模板变量出现在子目录中：验证静态前缀且运行时再次验证最终路径。

### Notes

- [INTEGRATION] config migration/validator、storage readiness、classification paths、规则编辑器。

## STORY-004: LLM 配置与清理开关联动

**As a** 使用可选 LLM 清理的高级用户
**I want** 启用时立即配置并测试 LLM
**So that** 不会保存一个表面开启但实际不可用的能力

### Acceptance Criteria

- [x] 仅在模式 2 中启用 LLM 时打开上下文配置弹层；模式 3 不展示无效的 LLM 判断开关。
- [x] 弹层引导至同阶段脱敏配置组件，支持保存和测试连接；测试进度和结果在弹层内显示。
- [x] 未配置或测试失败时可保存清理规则，但开场检查保持 BLOCKED 并给出修复入口。
- [x] 同一配置组件保留在文件来源阶段，可再次展开。

### Notes

- [DEPENDENCY] STORY-001。
- [INTEGRATION] 现有 `llm` 配置区块和 `/config/test-llm`。

## STORY-005: 高级配置保持胶卷上下文

**As a** 熟悉产品的高级用户
**I want** 从当前阶段进入对应高级设置并原路返回
**So that** 我不会被带到一套无关的配置首页

### Acceptance Criteria

- [x] 进阶设置本身是胶卷轨道中的同级阶段，不存在独立高级配置首页。
- [x] 命名、维度、安全和系统设置在同一阶段原位展开，不进入子页面。
- [x] 文件来源的清理规则与 LLM 仍在文件来源选项内递进配置。
- [x] 390px 宽度无页面横向溢出，原生表单与按钮可键盘操作。

### Notes

- [INTEGRATION] `data-config-stage`、`data-config-panel`、advanced partials 和 app state。

## STORY-007: 用户设置自动检查周期

**As a** NAS 用户
**I want** 选择系统多久检查一次源目录
**So that** 我可以在发现速度、网盘刷新延迟和 NAS 负载之间取舍

### Acceptance Criteria

- [x] 自动运行基础页提供 30 秒、1 分钟、2 分钟、5 分钟和 10 分钟预设。
- [x] 保存后写入 `file_watcher.poll_interval` 并重启 watcher 使用新周期。
- [x] 后端拒绝小于 10 秒或大于 3600 秒的配置。
- [x] 来源挂载离线时继续暂停扫描，不因短周期把空目录当作真实状态。
- [x] 用户界面称为“后台自动整理”，明确开启会定时检查并自动入库，关闭仍可手动处理。

## STORY-006: 用户执行可信的开场检查

**As a** 首次完成配置的用户
**I want** 系统检查全部必要依赖并给出是否可以开始的结论
**So that** 我不会在真实任务中才发现权限、网络或配置错误

### Acceptance Criteria

- [x] 开场检查覆盖配置契约、所有存储角色、权限、挂载、容量、片库根包含、TMDB 和自动运行条件。
- [x] 只有启用 LLM 时才真实测试 LLM；否则显示 SKIPPED。
- [x] API 每项输出 PASS/WARN/BLOCKED/SKIPPED、原因和修复入口；前端映射为中文状态说明。
- [x] BLOCKED 为零才显示“可以开始”；WARN 不阻止人工运行。
- [x] 影片模拟作为独立次级动作，不参与就绪结论。

### Edge Cases

- Provider 短暂超时：显示 BLOCKED 或 WARN 取决于是否为必需 Provider，并允许重试。
- 配置在检查后变化：结论失效，必须重新检查。

### Notes

- [DEPENDENCY] STORY-001、STORY-003、STORY-004。
- [INTEGRATION] configuration readiness service、Provider test、health、完成页。

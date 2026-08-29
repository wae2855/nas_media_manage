---
title: "feat: 配置依赖、来源单元与开场检查"
type: plan
date: 2026-08-28
status: pending_acceptance
brainstorm: ../brainstorms/2026-08-28-configuration-dependency-and-readiness-brainstorm.md
confidence: high
requirement: REQ-20260828-151346
---

# 配置依赖、来源单元与开场检查实施计划

- **Requirement**: [REQ-20260828-151346](../tracking/requirements-board.md)
- **Stories**: [用户故事](../stories/configuration-dependency-and-readiness.md)
- **Architecture**: [架构](../stories/configuration-dependency-and-readiness.architecture.md)
- **ADR**: [0014](../decisions/0014-source-unit-lifecycle.md)、[0015](../decisions/0015-library-root-relative-rules.md)
- **Status**: pending_acceptance（真实文件场景详细验收已通过，等待产品复验）

把配置从技术参数平铺改为依赖驱动流程，并用来源单元、片库根和开场检查兑现页面承诺。

## Problem Statement

文件来源中的源视频处理和智能清理没有父子关系；片库规则可以绕过存储检查保存任意绝对路径；LLM 启用没有上下文配置；高级配置脱离胶卷；完成页不能真实回答是否可以开始。更严重的是，当前清理链路按单视频行动，无法安全实现“一个下载文件夹全部入库后整体清空”。

## Target End State

- 文件来源用三种互斥模式驱动权限、清理策略和 LLM 子项。
- 顶层来源文件夹作为来源单元，全部任务成功后整体进入本地回收站；任何不确定性都整体等待。
- 存储检查配置唯一片库根，片库规则只保存相对模板且前后端双重阻止越界。
- 高级设置保持胶卷上下文，LLM 在启用动作处完成配置和测试。
- 完成页执行真实开场检查，模拟器保持独立。

## Scope

- 配置 schema、迁移、ConfigView、validator、API payload 和 revision。
- 来源单元识别、DB 关联、聚合状态、快照复核和整体回收。
- library_root、相对规则迁移、保存/运行 containment。
- 开场检查服务和 UI。
- 胶卷内阶段高级设置与 LLM 上下文弹层。
- 文档、专项测试、桌面/窄屏浏览器验收。

## Non-Goals

- 不支持多片库根。
- 不改变维度映射、限制级和 Provider 映射语义。
- 不实现远程协议客户端，不直接永久删除来源内容。
- 不完成真实 fnOS 安装升级验收；继续单独记录。

## Subjective Contract

- **Target outcome**：选择处理模式后，子卡片像胶片内嵌镜头一样展开；用户能预见权限和清理结果。
- **Anti-goals**：不新建白底设置页、不移除胶片孔、不把高级项重新堆成参数墙、不用前端假 READY。
- **Reference**：当前阶段胶卷、金色激活态、存储角色状态卡。
- **Anti-reference**：当前高级配置平行首页、并列清理卡、规则绝对路径全文输入。
- **Tone**：默认可忽略、风险明确、阻塞项带动作，不用技术枚举轰炸首次用户。
- **Rejection**：模式 1 可清理；失败任务所在文件夹被部分回收；根外规则能保存；启用 LLM 无配置；完成页漏检仍显示可开始。

## Preview Proof Slice

```text
文件来源
┌ 源目录处理方式 ───────────────────────────────┐
│ ○ 完全不改动                                  │
│ ● 保留媒体，仅整理垃圾                         │
│   └─ 清理策略 [保守预设] [高级调整]             │
│      └─ LLM 辅助 [启用] → 原位配置/测试弹层      │
│ ○ 全部成功后，整体回收来源文件夹                 │
└──────────────────────────────────────────────┘

完成 · 开场检查
存储与权限 PASS   TMDB PASS   LLM SKIPPED
片库边界 PASS     自动运行 WARN
[重新检查] [模拟一部影片] [开始使用]
```

- 先实现上述两个阶段和后端事实；1440×1024、390×844 通过后再整合其他高级页。
- 任何状态由前端自行拼出、模式切换丢值或移动端溢出，都退回 proof slice 修正。

## Proposed Solution

### Configuration

`source_policy.mode` 和 `library_root` 成为规范字段。旧布尔字段只用于迁移输入和兼容输出。配置保存验证三态组合、相对模板和片库边界。

### Source Units

scanner 在发现媒体时解析顶层 folder unit 或唯一 loose-root unit，任务关联 unit。任务成功后协调器查询单元所有媒体任务和当前快照；满足条件才调用整体回收。单元回收与任务入库状态分离。

### Readiness

新增开场检查聚合器，按 config revision 输出结构化 checks。storage readiness 复用现有能力，TMDB/LLM 调真实测试函数，路径规则调用服务端边界验证。检查本身不产生媒体文件副作用。

### UI

复用现有 cinema tokens、stage shell、requestApi、showConfirm 和掩码保存。阶段内高级设置使用嵌套 panel/抽屉；不新增 CSS 文件或框架。

## Phased Implementation

### Phase 0: 合同与 RED 测试

- [x] 为三态迁移、矛盾组合和权限需求补失败测试。
- [x] 为来源单元多任务等待、快照变化、根目录保护和整体回收补失败测试。
- [x] 为片库根迁移、绝对路径、`..`、符号链接逃逸和运行时越界补失败测试。
- [x] 为开场检查的条件性 LLM、TMDB 和 revision 绑定补失败测试。

**Exit**：安全边界都有可复现 RED，不依赖 UI 测试代替。

### Phase 1: 配置迁移与片库根

- [x] 实现 `source_policy.mode` 和 `library_root` loader/ConfigView/migration/validator。
- [x] 实现相对模板解析与服务端保存/运行 containment。
- [x] 无损迁移单根旧规则；跨根配置进入 BLOCKED 并保留修复信息。
- [x] storage readiness 使用显式 library_root，不再仅反推目标根。

**Exit**：旧配置安全加载；任何根外路径保存和执行都失败关闭。

### Phase 2: 来源单元生命周期

- [x] 增加 source unit DB schema/repository 和 task 关联迁移。
- [x] 实现 folder/loose-root 单元解析、代际 ID 与成员版本快照。
- [x] 实现任务状态聚合、未完成标记、稳定等待和回收门禁。
- [x] 整体目录回收复用 verified transfer/recycle sidecar/ledger；失败可重试。
- [x] 旧任务缺少来源单元时安全保留，不猜测历史文件夹单元。

**Exit**：多任务部分成功、目录变化、掉线和容量不足都不移动来源单元。

### Phase 3: 开场检查 API

- [x] 新增只读开场检查 endpoint 和结构化 check contract。
- [x] 聚合配置、storage、library boundary、TMDB、条件性 LLM 和 automation。
- [x] 结果绑定 config revision；配置重新加载后前端清空旧报告。
- [x] 每个 BLOCKED/WARN 提供稳定 id 和前端修复目标。

**Exit**：后端报告足以独立决定能否人工/自动开始。

### Phase 4: 前端证明切片

- [x] 文件来源改成三态父卡和模式专属子卡；模式 3 加强整体回收风险说明。
- [x] LLM 开关打开上下文弹层，配置组件归位到文件来源。
- [x] 完成页改为开场检查清单，模拟器降为独立次动作。
- [x] 桌面/390px、console、状态切换与原生键盘控件验收。

**Exit**：proof slice 满足 Subjective Contract 和浏览器验收。

### Phase 5: 片库与高级设置整合

- [x] 存储检查展示片库根；片库整理固定根前缀，只编辑相对模板。
- [x] 将来源 LLM 等高级项按阶段归属，高级页持续展示胶片导航。
- [x] 高级工具索引保留为兼容入口，但不再形成第二套导航，胶片可返回任一基础阶段。
- [x] 新增动态内容全部使用 escapeHtml，既有风险动作继续使用 showConfirm。

**Exit**：主流程和高级配置只有一个导航模型。

### Phase 6: 回归、文档与评审

- [x] 同步 configuration/source-files/source-cleaning/storage/safety/frontend/API 文档。
- [x] 运行专项、非外部 UI 回归、真实浏览器、架构护栏、Ruff、compileall、node check、check_docs。
- [x] 用 review skill 深审文件安全、迁移、路径逃逸、状态可信和 UI 回归。
- [x] Critical 全部修复后进入本地待验收；不自动推送，等待用户授权。

## Test Plan

- Unit：config migration、mode matrix、path containment、source unit snapshot/state、readiness aggregation。
- Integration：多视频文件夹全成功/部分失败、散文件单元、目录变化、回收失败重试、配置 revision。
- UI：三模式联动、LLM 弹层、相对路径编辑、高级返回、开场检查修复跳转。
- Regression：source policy、recycle boundary、verified transfer、location health、dimension golden、cinema smoke。

```bash
.venv/bin/python -m pytest tests/test_source_unit_lifecycle.py tests/test_library_root_boundary.py tests/test_startup_readiness.py
.venv/bin/python -m pytest tests/test_source_policy_safety.py tests/test_recycle_api_boundary.py tests/test_verified_transfer.py tests/test_location_health.py tests/test_dimension_mapping_golden.py tests/test_cinema_ui_smoke.py
.venv/bin/ruff check <changed-python-files>
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache .venv/bin/python -m compileall -q media_importer tests
node --check <changed-js-files>
.venv/bin/python scripts/check_docs.py
```

## Assumptions

| Assumption | Status | Evidence / Mitigation |
|---|---|---|
| task 可增加 source_unit_id | Verified | SQLite migration pattern and task repository exist |
| 旧规则共享安全公共根 | Unverified | migration 先 dry-run；不成立则 BLOCKED |
| 目录整体移动可复用 recycle manager | Partially verified | `move_dir_to_recycle` exists；先补快照/聚合测试 |
| readiness 可直接复用 connectivity functions | Verified | TMDB/LLM/path tests already have backend functions |
| 浏览器 dialog 适合 LLM 配置 | Verified with UI proof | 现有 modal utilities；必须通过 390px preview |

## Risks

- **误回收未完成下载**：稳定窗口、单元快照、任务聚合、清理前二次复核四层门禁。
- **旧绝对规则迁移错误**：不猜测跨根；原值保留并 BLOCKED。
- **单元永久等待**：报告具体阻塞任务/变化文件，允许用户修复后重试，不提供强制绕过删除。
- **高级页再次复杂化**：阶段归属和 proof slice 是拒绝门禁，不新增全局参数首页。
- **外部连接波动**：报告可重试；LLM 只在启用时阻塞，TMDB 必需性按 Provider 配置判断。

## Acceptance Criteria

- 模式 1 对源目录零写操作；模式 2 只按策略回收垃圾；模式 3 只在来源单元全部成功后整体回收。
- 来源根永不移动，目录变化/任务失败/挂载异常时移动数量为 0。
- 所有目标路径属于 library_root，越界配置无法保存或运行。
- LLM 启用时能在文件来源原位完成配置和真实连接测试。
- 高级设置不离开胶卷壳，返回当前阶段；390px 无横向溢出。
- 开场检查逐项给出可信状态，BLOCKED 为零才允许开始；模拟器不再代表系统就绪。

## Phase 7: 首轮验收反馈收敛（2026-08-28）

### 验收结论

首轮实现通过了功能和安全验证，但界面仍暴露了过多实现结构：选择“清理垃圾”后页面滚到下方形成第二块配置；整组回收展示了用户不需要理解的安全参数；高级配置仍通过独立首页和返回按钮形成第二套路径；自动运行主页面没有直接展示轮询周期。

### 目标体验与结构预览

```text
文件来源
┌ 完整保留（推荐）
├ 保留影片，只清理垃圾  [选中]
│  └ 清理方式：保守清理
│     LLM 辅助：关闭   [配置 LLM]
│     [详细删除规则]
└ 入库后清空来源
   └ 全部影片成功后自动清空；有失败则保留

胶卷轨道
开始 → 文件来源 → 存储检查 → 作品识别 → 片库整理
     → 自动运行 → 进阶设置 → 完成

自动运行
[启用自动运行]
每隔 [1 分钟 ▼] 检查一次源目录
```

### 约束与取舍

- “入库后清空来源”是用户语言；后端继续使用来源单元和本地回收区完成安全移动，不直接永久删除影视文件。
- 来源单元稳定窗口、未完成下载标记、容量和挂载门禁使用可靠默认值，不在主流程展示。
- 规则编辑、删除策略和 LLM 配置弹窗只能通过明确的关闭/取消/保存动作退出；点击遮罩不关闭，避免误丢编辑内容。
- 删除独立“高级配置”首页；进阶设置成为胶卷轨道中的普通一站，命名、维度、安全、系统设置在同页原位展开，不再进入子页面后返回。
- `file_watcher.poll_interval` 已被 watcher 真实消费；本阶段补齐主流程编辑、保存、校验和运行时重启验证。

### 实施任务

- [x] 将来源模式改为选中卡片内原位展开；清理摘要保留在卡片内，详细删除规则与 LLM 使用不可误触关闭的弹窗。
- [x] 将“成功后回收整组来源”改为“入库后清空来源”，隐藏来源单元实现参数并保留后端安全门禁。
- [x] 修复入库规则编辑弹窗点击遮罩自动关闭的问题，并补回归测试。
- [x] 在自动运行基础页增加轮询周期，保存到 `file_watcher.poll_interval`，补范围校验、运行时 watcher 重载与测试。
- [x] 移除独立高级配置首页，把进阶设置加入胶卷轨道，并将四类高级设置原位挂载为同页折叠区。
- [x] 完成桌面/390px 浏览器验收：无跳页、无误关闭、无横向溢出、console error 为 0。
- [x] 更新配置、前端、安全、测试文档并执行专项与全量非外部回归。

### Phase 7 验收标准

- 选择“保留影片，只清理垃圾”后视口不跳转，清理方式、LLM 状态和两个配置入口紧邻该选项出现。
- 选择“入库后清空来源”后主页面不出现稳定秒数、文件标记、回收容量等内部参数。
- 入库规则编辑弹窗点击遮罩保持打开，显式取消、关闭或保存才退出。
- 自动运行页面可选择 30 秒、1 分钟、2 分钟、5 分钟或 10 分钟；保存后 watcher 使用所选秒数。
- 配置页只有胶卷轨道这一套导航；进阶设置与其他阶段同级，内部设置原位展开，不出现“返回高级配置”。

## Phase 8: 第二轮验收反馈收敛（2026-08-28）

- [x] LLM 连通性测试在配置弹窗内显示“测试中、成功或失败”和具体原因，不再只依赖页面 Toast。
- [x] 删除规则合并策略先用“双方都判定/任意一方判定”解释，再以交集、并集作为补充术语。
- [x] 自动运行统一改为普通用户可理解的“后台自动整理”，明确开启和关闭分别会发生什么。
- [x] 开场检查结果把 PASS、SKIPPED、WARN、BLOCKED 等状态转换为中文展示，后端合同保持不变。
- [x] 补前端回归并在 9855 验证弹窗反馈、状态文案和窄屏布局。

### Phase 8 验收标准

- 点击“测试连通性”后，按钮进入忙碌状态，弹窗内出现结果；失败时说明原因，成功时明确可用。
- 用户不需要理解集合术语，也能判断两种删除范围的差别。
- 自动运行区域明确表达为“系统是否在后台定时检查并自动入库”，关闭不影响手动处理。
- 开场检查列表不显示英文状态码。

## Phase 9: 第三轮验收回归修复（2026-08-29）

- [x] 模拟器移除“高级配置工具 / 返回高级配置”旧壳，作为片库搭建的独立验证工具返回原配置轨道。
- [x] 补齐清理记录仓储的共享 SQLite 锁，并禁用跨线程共享连接的语句缓存，避免并发请求导致服务崩溃。
- [x] 开场检查请求失败时在完成页内展示明确原因和重试提示，不再只显示短暂 Toast。
- [x] 增加模拟路由、开场检查失败态和数据库并发保护回归测试。
- [x] 在 9855 实际点击两个模拟入口与开场检查，确认服务存活、TMDB 检查正常、console error 为零。

### Phase 9 验收标准

- 两个模拟入口均进入“模拟识别与分类”，页面不出现“高级配置”或“返回高级配置”，返回后仍在片库搭建胶卷轨道。
- 开场检查成功时展示中文逐项结果；本地服务请求失败时完成页保留可见错误和重试入口。
- 并发读取任务、维度、回收和清理记录时共享 SQLite 连接不发生无锁访问或进程崩溃。

## Phase 10: 真实文件场景详细验收（2026-08-29）

- [x] 盘点现有目录检查、模拟识别、来源清理、整组回收和浏览器测试，明确自动回归与脚本式测试边界。
- [x] 使用隔离临时目录生成真实 BT/网盘常见文件结构：主视频、字幕、NFO/海报、广告文件、Sample、小视频和未完成下载标记。
- [x] 串联验证开场检查、保留全部、保留媒体只清垃圾、整组来源成功回收、失败/变化/未完成下载拦截。
- [x] 验证回收元数据、片库根约束和来源根保留，确保测试过程中没有永久删除影视文件。
- [x] 运行专项矩阵、完整非脚本回归和 9855 真实浏览器/API 验收，记录 PASS/FAIL/NOT_RUN 边界。

### Phase 10 验收标准

- 测试数据均位于 pytest 隔离临时目录，不读取或改写用户现有来源、片库和回收目录。
- 垃圾清理后主视频、字幕、NFO 和海报仍在来源目录，被清理项位于回收目录且带可恢复元数据。
- 整组模式只有全部媒体任务成功且目录快照未变化时才移动整个下载文件夹；任务失败、下载残留或目录变化时移动数量为零。
- 开场检查覆盖目录存在、读写权限、容量、片库边界、TMDB、条件性 LLM 和后台运行状态。
- 模拟识别入口在真实浏览器可完成一次电影文件名的识别与分类，并能返回胶卷配置轨道。

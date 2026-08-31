---
title: "fix: 目标片库不可删除硬边界"
type: plan
date: 2026-08-31
status: pending_acceptance
confidence: high
requirement: REQ-20260831-004019
---

# 目标片库不可删除硬边界修复计划

- **Requirement**: [REQ-20260831-004019](../tracking/requirements-board.md)
- **Proposal**: [目标片库冲突确认与安全替换](../_archive/2026-08-31-target-library-conflict-safety/2026-08-31-target-library-conflict-safety.md)
- **ADR**: [0012 存储角色拓扑](../decisions/0012-storage-role-topology.md)、[0018 目标片库只新增](../decisions/0018-target-library-additive-conflict-boundary.md)
- **Status**: pending_acceptance

在上一轮“冲突逐项确认”之上补齐所有旁路：目标片库默认只新增，只有用户在单个冲突任务中明确选择“替换片库文件”时，才允许把该任务实际目标文件先移入本地回收区；任何启动恢复、目录清理、来源整组处理、任务删除、任务重命名和后台自动逻辑都不得删除、移动或改名片库现有文件。

## Problem Statement

上一轮只收敛了正常去重与替换路径，但破坏性审计在隔离目录真实复现了多条旁路：旧 FPK 仍能自动质量替换；运行任务在入库后、标记成功前崩溃时，重启清理会直接删除片库文件；目录配置没有阻止片库与来源、中转、回收相同或父子嵌套；任务删除 API 可移走 `file_location=import` 的文件；已入库任务还能直接重命名片库文件。这些路径使现有安装包和源码都不能兑现“片库只新增”的产品承诺。

fnOS 包当前固定空服务 API Key，但桌面已经通过同源 CGI 反向代理 `127.0.0.1:14591`。产品不对局域网直接提供独立服务端口，因此 fnOS 后端应只监听回环地址，保留 CLI/YAML 显式 host 供非 fnOS 高级部署使用。

## Target End State

- 多片库中的每一个目标根都与来源、中转、回收、日志、资源目录以及其他目标根保持真实路径互斥；相同、父包含子或子包含父都无法保存，也无法绕过配置直接运行副作用。
- 启动恢复只直接清理经 `realpath/commonpath` 证明属于本地中转目录的普通处理副本；任务路径已经指向片库时只修复任务状态，不触碰文件。
- 删除任务永远只删除任务记录；`file_location=import` 即使收到 `delete_files=true` 也拒绝文件动作。
- 已入库任务不能通过通用重命名接口修改片库文件。
- 来源清理和整组来源处理执行前再次验证来源根与全部片库根互斥，配置开关关闭时执行数量为零。
- 旧 `quality/replace` 配置和任何打包副本都不能恢复自动处置片库的逻辑；构建产物必须来自当前根源码并通过包内危险模式检查。
- fnOS 服务只监听 `127.0.0.1:14591`，桌面和移动端继续通过现有 CGI 同源入口访问。

## Scope and Non-Goals

### In scope

- 配置保存、开场检查与运行时副作用共享的目录角色拓扑门禁。
- 启动中断恢复与孤立中转文件清理。
- 任务删除、任务重命名、源清理、来源整组回收的片库保护。
- fnOS 启动监听地址和 CGI 健康验证。
- FPK 根源码一致性与危险旧逻辑检查。
- 真实隔离目录的破坏性负向测试、文档与需求状态同步。

### Non-goals

- 不改变用户已确认的三个冲突动作及其界面。
- 不恢复或设计任何自动质量替换。
- 不在本轮统一分辨率字段。当前正式分辨率等级使用 `ffprobe`，冲突展示仍有文件名兜底，命名 `{resolution}` 与 `dimensions.resolution_tier` 不一致；另立需求处理。
- 不在 fnOS 普通配置界面恢复服务 API Key 或端口字段。
- 不修改真实用户来源、片库或回收目录；所有破坏性验证只使用 pytest 临时目录。

## Proposed Solution

### 1. 单一目录拓扑事实源

在 `features/configuration` 建立 canonical role topology 校验：所有路径先做绝对路径、`realpath` 和 `commonpath`；任意片库根与来源、中转、回收、日志、资源目录相同或互为父子时返回结构化错误。多片库根之间也不得相同或互相包含。配置校验、保存、storage/startup readiness 和所有破坏性服务调用同一事实源，避免只靠前端或只在保存时拦截。

### 2. 启动恢复失败关闭

启动恢复不再根据任务状态直接删除 `task.video_path`。只有路径是非符号链接普通文件、真实路径位于 `temp_dir`、且不位于任何片库根时，才可作为中转副本直接删除；字幕使用同一规则。中断任务若已经保存了片库路径，只标记失败并保留 `import_video_path` 供用户确认，不把片库文件改回来源语义。孤立文件扫描同样使用真实路径归属判断。

### 3. 片库文件动作白名单

目标片库现有文件只允许从冲突专用 `replace_existing` 服务进入安全替换协议。通用任务删除对 `file_location=import` 的文件动作返回 400，仍允许在 `delete_files=false` 时只删除记录；通用重命名拒绝已入库位置。源清理、来源单元回收和回收保留清理在执行前重新检查角色互斥，不能依赖历史配置已经正确。

### 4. fnOS 本机监听

将生成的 fnOS 启动命令从 `--host 0.0.0.0` 改为 `--host 127.0.0.1`。CGI 继续固定代理 `127.0.0.1:14591`。验证 FPK 启动脚本和解包产物不再包含 fnOS 的全网卡监听，同时保留开发/非 fnOS CLI 显式 host 能力。

### 5. 构建产物防漂移

`deploy/nas-media-importer/` 继续视为生成目录。构建前清理并从根源码重建；`validate_fpk.py` 解开真实 `app.tgz` 后至少验证：去重策略默认/运行时为人工确认、目标覆盖没有永久删除兜底、fnOS 只监听回环地址。旧 FPK 不作为可发布产物。

## Decision Rationale

- 仅修复去重服务不足以保护片库；安全边界必须在目录配置、运行时文件动作和构建产物三层同时成立。
- 保存时校验能改善用户体验，运行时复验才能防止手工改 YAML、挂载变化和旧配置绕过。
- 任务删除与重命名不是目标库管理功能；把它们限制为任务记录操作，比依赖前端隐藏按钮更可靠。
- 现有 fnOS CGI 已经是同源代理，回环监听既能维持桌面体验，也能消除局域网直接访问空认证 API 的暴露面。
- 分辨率字段统一与片库数据安全没有依赖关系，拆分能避免 P0 修复被展示和命名改造拖慢。

## Constraints and Boundaries

- 严格遵守 [Safety Standards](../standards/safety.md)：源文件和片库文件禁止直接 `os.remove()`；只允许明确中转副本和 `.tmp/.copying` 直接删除。
- 目标片库正常运行只有新增写入；替换必须来自单任务、逐项确认、指纹重检和本地回收。
- 目录互斥使用真实路径，不能使用字符串 `startswith`；符号链接和无法解析的路径失败关闭。
- 不回滚当前 dirty worktree 中已有改动；只对本计划涉及的当前内容做精确补丁。
- 真实 fnOS 安装、桌面和移动端验收由用户执行；本地只能报告 `LOCAL_BUILD`，不能冒充 `FNOS_UAT`。

## Assumptions

| Assumption | Status | Evidence / handling |
|---|---|---|
| fnOS 桌面不需要后端监听 NAS 局域网地址 | Verified | `docs/architecture/deployment-fnos.md` 与生成 CGI 均固定代理 `127.0.0.1:14591` |
| 多片库路径可在保存时完整取得 | Verified | `canonicalize_library_config` 已维护 `library_roots` 和稳定 root ID |
| 所有破坏性服务都能取得当前配置 | Verified / audit during Phase 2 | 启动、任务、源清理、来源单元均已接收 config；逐入口补运行时门禁 |
| 已入库任务的通用重命名不是必要产品能力 | User boundary | 目标片库只新增，除逐项替换外不修改现有文件 |
| 当前 FPK 能由根源码确定性重建 | Verified locally, package proof required | `build_fpk.sh` 已声明重建流程；Phase 3 增加真实包内容校验 |

## Risk Analysis

| Risk | Mitigation |
|---|---|
| 旧合法配置因目录嵌套被阻塞 | 清晰列出冲突角色和路径；只阻止副作用，不自动迁移或移动任何文件 |
| 回环监听导致桌面 502 | 先验证 CGI 上游合同和本地回环 smoke，再构建 FPK；真机单列 UAT |
| 启动清理过度保守导致中转残留 | 数据安全优先；只保留无法证明归属的文件，并在日志/开场检查提示人工处理 |
| 任务删除行为变化影响旧 UI | 前端当前已发送 `delete_files=false`；增加 API 回归，错误响应明确说明只删除记录 |
| 运行时门禁遗漏旁路 | 对所有 `os.remove/rmtree/unlink/rename/replace/shutil.move/safe_delete/move_to_recycle` 做全仓终审，并用允许列表解释每个命中 |
| 生成目录混有旧代码 | 校验真实 FPK 内嵌 `app.tgz`，不以 staging workspace 或测试通过代替包内容证明 |

## Phased Implementation

### Phase 0 — RED 证据与需求恢复

- [x] 将 REQ-20260831-004019 从 `pending_acceptance` 恢复为 `in_progress`，登记本审计发现。
- [x] 补目录相同/父子嵌套、崩溃窗口重启、`temp=library`、`source=library`、整组来源、任务删除 import、已入库重命名和 fnOS 监听的失败测试。
- [x] 记录现有 FPK SHA-256 和包内旧自动替换证据，标记为不可发布。

Exit: 新测试在修复前准确复现风险，且只使用隔离临时目录。

### Phase 1 — 目录拓扑与启动恢复

- [x] 实现单一目录角色拓扑校验并接入配置 validate/save/readiness。
- [x] 在启动任务恢复和孤立中转清理中使用真实路径、安全普通文件和片库排除门禁。
- [x] 让冲突配置返回普通用户能理解的角色、路径和处理建议，不自动改目录。
- [x] 运行配置、启动恢复、多片库和存储专项测试。

Exit: 任意目录重叠无法保存；手工构造旧冲突配置时运行时副作用仍为零；崩溃窗口片库字节保持不变。

### Phase 2 — 文件动作旁路收口

- [x] 任务删除禁止对 `file_location=import` 执行文件动作，只允许删除记录。
- [x] 通用任务重命名拒绝已入库文件。
- [x] 源清理执行必须尊重 enabled/来源模式，并在执行前复验与片库互斥。
- [x] 来源单元整体回收和回收保留清理补片库互斥运行时门禁。
- [x] 全仓审计所有删除、移动、重命名与覆盖调用，记录唯一允许的片库现有文件动作是逐项确认的安全替换。

Exit: 隔离目录负向场景中片库文件路径、内容和指纹全部不变；逐项替换正向场景仍通过。

### Phase 3 — fnOS 回环监听与真实包防漂移

- [x] fnOS 启动命令绑定 `127.0.0.1`，保持 CGI 上游与端口合同不变。
- [x] 扩展 FPK 校验器，检查真实包内代码、人工确认策略、无永久删除兜底和回环监听。
- [x] 从根源码重建 FPK，验证 package workspace 与真实 `app.tgz`，生成新 SHA-256。
- [x] 本地 CGI/后端回环合同检查通过；真机安装、桌面入口和移动端入口列为 `FNOS_UAT NOT_RUN`。

Exit: `LOCAL_BUILD PASS`；NAS 局域网端口不能直接访问只能在真机确认，桌面 CGI 仍能访问也只能在真机最终确认。

### Phase 4 — 文档、质量检查与独立终审

- [x] 同步 safety、configuration、storage-filesystem、tasks、source-files、import-flow、deployment-fnos、API 和回归矩阵。
- [x] 运行定向测试、架构护栏、完整测试、Ruff、compileall、Shell 语法和文档检查；2 个 Playwright 用例因 macOS 沙箱浏览器权限标记 `UI_ENV_BLOCKED`。
- [x] 对最终 diff 和真实 FPK 做独立删除边界复审；复审发现的回收恢复并发窗口已修复并用同一场景复验。
- [x] 需求进入 `pending_acceptance`，安装包只交给用户在隔离/备份环境真机验证。

Exit: 本地证据全部通过，没有已知 P0/P1 片库旁路；真机状态诚实标记为未验收。

## Implementation Evidence

- `LOCAL_AUTOMATION PASS_WITH_ENV_GAP`：完整测试运行 818 通过；2 个目录按钮 Playwright 用例因 Chromium MachPort 沙箱权限无法启动，标记 `UI_ENV_BLOCKED`，无业务断言失败。
- `SAFETY_REGRESSION PASS`：覆盖长复制后目标变化、发布时并发目标、回收恢复并发目标、`.copying`/日志/回收 sidecar/缩略图链接、挂载身份变化等真实临时目录场景。
- `STATIC PASS`：本轮 Python 文件 Ruff、全仓 compileall、`git diff --check`、`bash -n deploy/build_fpk.sh`、111 个活跃文档检查通过。
- `LOCAL_BUILD PASS`：fnOS FPK `0.3.10`，SHA-256 `bf76dd639501fb47190f34f52c716d2696f3eb6df36c574b77721b5ca66ece45`，包内 246 项通过发布合同校验；启动只监听 `127.0.0.1:14591`。
- `INDEPENDENT_REVIEW PASS`：包内 `media_importer` 195/195 文件与工作树逐文件 SHA-256 一致，目标片库/传输/回收/任务/配置/fnOS 定向复核 122 通过，未发现阻断项。
- `FNOS_UAT NOT_RUN`：真实 fnOS 安装、桌面入口、目录重新授权和真实媒体库验收由用户执行。

## Acceptance Criteria

1. 片库与来源、中转、回收、日志、资源及其他片库根相同或互为父子时，配置保存失败且所有文件副作用入口失败关闭。
2. `PENDING/RUNNING` 任务的 `video_path` 指向片库时，服务重启不会删除、移动或改名该文件；文件内容和指纹保持不变。
3. `temp_dir` 错误指向片库时，启动清理删除数量为零；符号链接不能绕过真实路径检查。
4. 任务删除对已入库文件不产生文件动作；`delete_files=true` 也不能移走片库文件。
5. 已入库任务不能通过通用重命名修改片库文件。
6. 源清理、整组来源回收和回收保留清理在任何片库重叠配置下移动/删除数量为零。
7. 只有单个冲突任务的 `replace_existing` 能处置其实际目标文件，且旧文件先进入本地回收；保留现有和保留两份保持原语义。
8. 真实 FPK 不包含自动 `quality/replace` 处置、不包含目标回收失败后永久删除兜底，fnOS 启动只监听 `127.0.0.1:14591`。
9. 本地自动化、静态检查和文档检查通过；`LOCAL_BUILD`、`FNOS_UAT`、用户真实片库验收分别报告。

## Rejection Criteria

- 任一未经过逐项冲突确认的入口能够删除、移动、重命名或覆盖片库现有文件。
- 目录保护只存在于前端或保存流程，手工旧配置仍能触发文件动作。
- 启动恢复继续对未经真实中转目录证明的任务路径调用直接删除。
- 包校验只检查文件存在，不检查真实包内旧危险逻辑。
- 将本地测试或本地构建描述成 fnOS 真机安全通过。

## References

- [Safety Standards](../standards/safety.md)
- [Storage Filesystem Architecture](../architecture/storage-filesystem.md)
- [Configuration Architecture](../architecture/configuration.md)
- [fnOS Deployment](../architecture/deployment-fnos.md)
- [Target Library Additive Boundary](../decisions/0018-target-library-additive-conflict-boundary.md)
- `media_importer/api/handler.py`
- `media_importer/features/configuration/`
- `media_importer/features/tasks/delete_service.py`
- `media_importer/features/tasks/file_lifecycle_service.py`
- `media_importer/features/source_cleaning/`
- `media_importer/features/source_files/source_units.py`
- `deploy/build_fpk.sh`
- `scripts/validate_fpk.py`

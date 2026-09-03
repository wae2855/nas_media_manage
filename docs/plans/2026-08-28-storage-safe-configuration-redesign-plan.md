---
title: "存储安全与配置界面简化重构实施计划"
type: plan
date: 2026-08-28
status: in-progress
confidence: high
requirement: REQ-20260828-151346
---

# 存储安全与配置界面简化重构实施计划

- **Requirement**: [REQ-20260828-151346](../tracking/requirements-board.md)
- **Proposal**: [storage-safe-configuration-redesign](../proposals/2026-08-28-storage-safe-configuration-redesign.md)
- **ADR**: [0011](../decisions/0011-fnos-install-runtime-config-ownership.md)、[0012](../decisions/0012-storage-role-topology.md)、[0013](../decisions/0013-verified-transfer-recovery.md)
- **Status**: in_progress

> 2026-09-02 修订：ADR-0022 已取消中心中转配置、旧任务断点和双复制链路。本文中对应任务及图示只作为历史实施背景，现行实现和验收以 ADR-0022 为准。

在保持 cinema 胶卷视觉语言的前提下，先补齐文件安全、存储能力和配置事务，再把首次配置收敛为异常驱动流程。

## 问题陈述

当前页面复杂度和运行安全耦合：配置缺少真实就绪状态，目录掉线可被当作空目录，跨盘复制后直接删除源，清理结果缺少独立状态，安装和 Web 还可能形成配置双源。只做 UI 会把未兑现的安全能力包装成“可以开始”。

## 目标终态

- 用户安装后打开配置页，已有效的目录显示“安装时已配置，通常无需修改”。
- 页面只展开阻塞项；默认和高级参数不占用首次决策空间。
- 所有副作用入口共享配置 READY、位置健康、容量和任务租约门禁。
- BT/云盘文件稳定后才入队；跨设备传输可验证、可恢复、幂等。
- 回收站只在本地，客户端不能提交任意文件路径；远程目标离线不丢回收副本。
- 真实 fnOS 安装、升级、重装和远程挂载故障注入通过后才能声明支持。

## 范围与非目标

### 范围

- 配置 schema/迁移/校验/API/运行快照/就绪状态。
- 目录角色、挂载能力、权限和容量预检。
- 稳定扫描、任务领取、传输日志、回收恢复、源处理状态。
- fnOS 首次初始化与升级保留。
- 胶卷式配置内容重构、桌面和窄屏验收。

### 非目标

- 不实现网盘协议客户端或外部通知渠道。
- 不改变 TMDB 两级识别主流程。
- 不重做维度值映射、各国限制级归一和维度编辑器；保留现有逻辑与高级入口，后续独立头脑风暴。
- 不自动永久清理回收站释放空间。

## 设计与体验契约

### 目标感受

用户应感到“系统已经替我准备好大部分内容，我只需要处理黄色或红色项”，而不是进入一个管理后台参数仓库。

### 视觉参考

- 当前 `http://localhost:9855/`：黑金影院标题、横向胶片孔、剧照阶段卡、金色激活态。
- `cinema-tokens.css` 和 `docs/standards/frontend.md` 是颜色、间距和文件组织事实源。

### 反例与拒绝条件

- 禁止变成白底 SaaS 设置页、通用卡片仪表盘或新主题。
- 禁止移除胶片孔、剧照阶段卡和金色激活态。
- 禁止首次流程默认展示 cron、扩展名、置信参数、维度映射等低频字段。
- 禁止前端自行推断“配置完成”；必须投影后端就绪事实。
- 若绿色默认项仍需要逐项保存，或移动端横向阶段导航不可操作，视觉验收失败。

### 代表性证明切片

先只完成“存储检查”阶段：保留现有胶卷壳，呈现四个位置摘要、来源标记、容量和重新检查动作。桌面 1440×1024 与窄屏 390×844 截图、DOM 语义、无 console error 通过后，才推广到其他阶段。

## 方案与依赖顺序

## 缺陷台账

| ID | 失败场景 | 主要位置 | 计划测试 |
|---|---|---|---|
| SAFE-001 | 配置缺失或任务 skip 时仍移动源视频 | `config_loader.py`、`cleanup_service.py`、`runner.py` | `tests/test_source_policy_safety.py` |
| SAFE-002 | 客户端提交任意路径让回收 API 删除/移动文件 | `recycle_handlers.py`、`features/recycle/browser.py` | `tests/test_recycle_api_boundary.py` |
| SAFE-003 | 手工运行与 watcher 同时领取同一任务 | `run_file_service.py`、`runner.py`、`task_repo.py` | `tests/test_task_concurrency_and_resume.py` |
| SAFE-004 | 文件尚在增长却被入库并随后清理 | `scan_service.py`、`file_watcher.py`、`file_copier.py` | `tests/test_stable_source_gate.py` |
| SAFE-005 | 跨设备复制中断后源已删除或目标半成品被当成功 | `filesystem/safety.py`、`recycle/manager.py` | `tests/test_verified_transfer.py` |
| SAFE-006 | 挂载消失后创建同名目录并误扫/误写 | `permission_checker.py`、`file_watcher.py` | `tests/test_location_health.py` |

### 统一传输拓扑

```text
本地来源 ─┐
远程来源 ─┴→ 本地中转(.copying + source snapshot + SHA-256)
              ├→ 本地目标.tmp → 验证 → 发布
              └→ 远程目标.tmp → 回读 SHA-256 → 发布

远程 A → 远程 B 禁止直传；回收与恢复复用同一协议。
```

### 容量策略

- `write_bytes`：本次尚需写入的主文件、字幕和伴生文件字节数，续传时扣除已验证偏移。
- `reserved_bytes`：除当前操作外，其他已领取但未完成操作在该位置的预留总和；当前操作只计入 `write_bytes`，禁止重复计算。
- `safety_reserve`：`max(1 GiB, 卷总容量的 5%)`。
- 红色：本地中转/回收无法读取容量，或 `free < write_bytes + reserved_bytes + safety_reserve`；阻止任务。
- 黄色：远程目标容量未知，或操作后剩余空间不足两个 `safety_reserve`；只允许人工任务且仍需完整性验证。
- 绿色：满足硬需求且操作后至少保留两个 `safety_reserve`；允许自动任务。
- 回收预留按计划移入回收的全部文件计算；不通过永久清空回收站来改变结论。

### Phase 0：基线与 P0 安全修复

- [ ] 记录当前 dirty worktree 基线和历史失败，不回退或覆盖现有简洁化改动。
- [ ] 在真实 fnOS 做只读 capability spike：记录本地卷、云盘挂载、掉线和恢复时的 mountinfo/st_dev/realpath/授权表现；若设备暂不可用，Phase 1 只实现保守 Linux capability 并保持远程自动化关闭。
- [ ] 在改配置代码前冻结维度映射 golden：代表性国家限制级、未知值、用户覆盖，以及保存其他配置区块的 round-trip；Phase 1/5/6 只复验该基线。
- [ ] 前移安全 bootstrap spike：验证 fnOS 新装/升级向导能采集非空 API Key。新装无 Key 失败；旧版空 Key 升级无 Key 中止并回滚；本地开发只允许直接设置本地 YAML，不提供网络 bootstrap 端点。
- [ ] 为源文件策略补 RED 测试：配置缺失默认保留；skip/重复目标路径也遵守策略。
- [ ] 修复所有源文件动作统一受显式策略控制，旧缺失值安全迁移为保留。
- [ ] 建立最小 recycle item SQLite 台账并导入有效 sidecar，先获得稳定服务端记录 ID。
- [ ] 为回收 API 补路径穿越/任意路径/覆盖恢复 RED 测试。
- [ ] 回收 API 改为服务端记录 ID，canonicalize 并限制在配置回收根；覆盖目标先二次回收。
- [ ] bootstrap spike 通过后固定认证契约：所有配置写入、任务执行、清理、回收、恢复等副作用 API 必须同时满足“服务端配置了非空 API Key”和“Bearer 匹配”；Key 为空返回 `503 security_setup_required`，绝不放行。只读 API 可保持现状，浏览器沿用现有认证弹窗。
- [ ] 为任务领取补并发 RED 测试，使用 SQLite CAS/租约保证单任务单执行者。

**退出条件**：SAFE-001、SAFE-002、SAFE-003 均有自动测试并通过；最小回收台账先于 ID API 生效；新装、旧版空 Key 升级和本地开发的 bootstrap 路径已证明且不可被网络抢占；副作用 API 的空 Key 与错误 Key 都不能执行；维度 golden 已在任何配置改动前冻结；fnOS capability 结论已记录或远程自动化保持关闭。

### Phase 1：配置事务与存储契约

- [ ] 定义兼容旧 YAML 的 workspace/location 配置投影和 migration；业务读取进入 ConfigView。
- [ ] 实现 role-aware 路径预检：用户根只验证，应用子目录才允许创建。
- [ ] 校验 realpath、符号链接、父子嵌套、挂载身份和本地-only 中转/回收。
- [ ] 持久化位置身份快照并实现角色能力矩阵；身份变化立即 BLOCKED，unknown 来源/目标仅人工最小权限。
- [ ] 实现容量门禁：中转、目标、回收；查询失败 fail closed；黄色/红色结论结构化。
- [ ] 配置保存改为 revision + 全量验证 + 临时文件 fsync + `os.replace`；敏感掩码保持原值。
- [ ] 运行 Phase 0 维度 golden 与配置 round-trip，确认 migration 和原子保存没有改变映射语义。
- [ ] 活跃任务持有不可变配置快照；保存后由明确 runtime transaction 生效，不依赖下一次 watcher 回调。
- [ ] 增加配置 `UNCONFIGURED/VALIDATING/READY/BLOCKED` 状态并拦截扫描、自动运行、清理、恢复。

**退出条件**：非法路径、挂载消失、空间未知、并发保存和活跃任务更新均有确定结果；非 READY 不产生文件副作用。

### Phase 2：稳定扫描与可恢复传输

- [ ] 文件扫描加入至少两次观测且跨越默认 120 秒的稳定窗口（高级范围 30-1800 秒）、复制前后 source snapshot 和变化后等待语义。
- [ ] 建立 transfer operation SQLite schema、repository 和恢复服务。
- [ ] 实现同卷 rename 快速路径与跨设备“目标临时文件 → flush/fsync → 校验 → 原子发布 → 最后处理源”。
- [ ] `.copying` 续传必须绑定 operation、源版本和偏移；不一致时安全重建。
- [ ] 目标已发布但源未处理的重试保持幂等，禁止重复目标。
- [ ] 导入结果与 cleanup_status 分离，伴生文件逐项记录并允许只重试清理。

**退出条件**：复制期间修改源、进程中断、空间耗尽、目标掉线和重启恢复故障注入均不删除未被证明安全的源。

### Phase 3：回收台账、清理计划与位置健康

- [ ] 扩展 Phase 0 最小 recycle 台账为完整生命周期，迁移/兼容剩余 sidecar；列表、恢复、删除均按记录 ID。
- [ ] 恢复复用 transfer operation；远程原位置离线进入等待并保留本地回收副本。
- [ ] 清理预览生成带版本的计划；执行逐项复核并与活跃路径租约互斥。
- [ ] 位置健康实现 `ONLINE/DEGRADED/OFFLINE/RECOVERING`、连续失败、退避、恢复对账。
- [ ] watcher 离线不清空 known files、不触发源清理，恢复后重扫并去重。
- [ ] 回收保留清理由独立维护任务执行，不依赖 watcher 是否启用。

**退出条件**：离线、恢复、预览后文件变化、恢复目标冲突和 sidecar 损坏都有可解释状态且无越界操作。

### Phase 4：fnOS 首装与升级链

- [ ] 基于 Phase 0 spike 核验真实 fnOS wizard 的目录选择/授权能力，记录支持或降级路径。
- [ ] build_fpk 生成源新增首次目录采集；安装回调区分 initialize/migrate/repair。
- [ ] 关键安装步骤失败即失败并回滚，不再吞掉错误。
- [ ] 升级/重装保留目录、开关、密钥和端口；端口收敛为单事实源。
- [ ] 构建 FPK 并做解包 smoke；真实设备完成首装、重启、升级、保留数据重装。

**退出条件**：安装值只初始化一次；任何迁移失败不会静默报告成功；真实 fnOS 证据齐全。

### Phase 5：胶卷配置 UI

- [ ] 先实现“存储检查”证明切片，复用现有 tokens、胶卷 stage 和 requestApi。
- [ ] 完成桌面/窄屏预览、自评审和 console 检查；不通过则只修证明切片。
- [ ] 调整阶段为“开始、文件来源、存储检查、作品识别、片库整理、自动运行、完成”，保持胶卷展开形式。
- [ ] 安装有效值展示摘要；只有异常项进入编辑和重检。
- [ ] TMDB、规则预设和自动运行成为首次决策；LLM、维度、扫描细节、命名模板等进入高级配置。
- [ ] 源视频保留与垃圾清理分开，并呈现 BT/远程来源风险、预计本地回收占用。
- [ ] 完成页投影 READY/健康/容量事实，提供模拟和开始运行动作。
- [ ] 动态内容 escapeHtml，破坏性动作 showConfirm，敏感字段 preserveApiKey。
- [ ] 运行 Phase 0 维度 golden 与高级配置 round-trip，确认页面重组没有丢失用户覆盖。

**退出条件**：首次流程没有高级参数墙；所有状态来自后端；1440×1024 和 390×844 视觉验收符合 cinema 主题。

### Phase 6：文档、回归与交付评审

- [ ] 同步 configuration、storage、import-flow、source-files、recycle、tasks、monitor、frontend、fnOS 事实文档。
- [ ] 重写已漂移的 file-flow/regression matrix，删除退役能力和不存在测试引用。
- [ ] 最终复验 Phase 0 维度映射 golden。发现产品分歧只登记后续需求，不在本轮改映射。
- [ ] 执行专项、非 UI、完整 UI、架构护栏、Ruff、compileall、check_docs。
- [ ] 按 review skill 做安全/正确性/契约/设计深度自评审；Critical 必须修复并重跑受影响测试。
- [ ] 更新需求为 review/pending_acceptance，记录真实 fnOS 未执行项（若设备不可用）。

## 测试计划

### 单元与契约测试

- 配置 migration/default/revision/atomic save/masked secret。
- location capability、realpath、符号链接、嵌套和根目录不创建。
- source policy 的 success/skip/failure/BT 保留组合。
- transfer operation 状态转换、续传条件、校验失败和幂等恢复。
- recycle ID 边界、恢复覆盖二次回收、cleanup_status。
- task CAS claim、位置健康转换和 READY gate。
- 维度配置迁移前后、其他配置保存前后语义不变；代表性国家限制级、未知值和用户覆盖 golden 输出不变。

### 集成与故障注入

- 本地→本地、远程源→本地、本地→远程目标、远程 A→远程 B。
- 扫描、复制、发布、源清理、回收、恢复阶段分别模拟掉线和进程重启。
- 文件复制期间增长、mtime 改变、目标空间耗尽、容量查询失败。
- 安装首次初始化、升级、修复安装、保留数据重装。

### UI 与视觉验收

- 配置 stage 导航键盘/点击/窄屏滚动。
- 默认摘要、异常展开、重新检查、风险确认、保存与恢复。
- 1440×1024、390×844 截图；与当前 cinema 主题对比。
- 浏览器 console error 为 0（favicon 404 除外），无横向内容溢出。

### 验收命令

```bash
python -m pytest tests/test_architecture_guards.py
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
python -m pytest tests/
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests
.venv/bin/ruff check <本需求改动的 Python 文件>
node --check <本需求改动的 JavaScript 文件>
python scripts/check_docs.py
```

## 假设审计

| 假设 | 状态 | 证据/处理 |
|---|---|---|
| fnOS wizard 可选择业务目录并形成授权闭环 | 未验证 | Phase 0 只读 spike、Phase 4 完整验证；不成立时降级为首次 Web 补录 |
| 同一 YAML 可作为安装和 Web 唯一事实源 | 已验证 | 服务启动与 Web 保存当前使用同一路径 |
| `os.replace` 可完成同文件系统原子发布 | 已验证 | Python 3.12 官方文档；跨文件系统不适用 |
| `shutil.copy2` 本身足以证明完整性 | 已否定 | 官方文档只承诺复制/尽力保留元数据，无事务或恢复语义 |
| SQLite 可保存本地操作日志并原子提交状态 | 已验证 | 现有 DB 架构及 SQLite atomic commit；DB 必须本地 |
| 可以可靠识别所有云盘协议 | 未验证且非目标 | 只识别挂载/能力；unknown 对本地-only 角色 fail closed |
| 现有维度映射可暂时保持 | 用户确认 | 本轮不改变结果，后续独立头脑风暴 |

## 2026-08-28 首轮实施证据

- 已完成 SAFE-001/002/003：源视频默认保留、回收 HTTP API 改为服务端记录 ID、排队任务原子领取。
- 已完成保守存储底座：角色化目录/挂载/容量就绪检查，挂载根不自动创建，跨盘 `.copying + SHA-256 + fsync + 原子发布`，回收与恢复复用验证传输。
- 已完成自动来源保护：新文件至少两次观测且默认稳定 120 秒；来源离线保留 known-files 并暂停回调。
- 已完成配置事务第一版：revision 冲突检查、全量校验、同目录临时文件和 `os.replace` 原子保存。
- 已完成胶卷配置首版：七阶段导航、默认摘要、存储异常展开、源视频策略与垃圾清理分离、自动运行显式选择、LLM 收入折叠高级项。
- 维度映射 14 个 golden 已冻结；本轮未改变限制级、题材或 Provider 映射语义。
- 当前专项回归 `207 passed`；提交前非 UI 回归在排除两个会等待 LLM socket 的源清理集成文件后为 `626 passed, 39 deselected`。完整集合运行至 `502 passed` 后停在 `test_source_cleaner_comprehensive.py` 的 socket 读取并人工中止，因此不能记为全仓 PASS。
- 桌面应用内浏览器及 390×844 窄屏均已验收；窄屏 `clientWidth=scrollWidth=390`、脚本错误 0、5 个存储角色正常渲染。
- 尚未完成：真实 fnOS 首装/升级/API Key bootstrap、认证强制切换、transfer operation 持久化状态机、完整位置健康退避/恢复对账和 fnOS 故障注入。需求继续保持 `in_progress`。

## 风险与缓解

- 大量 dirty worktree 交叠：每次修改前读取当前文件，只编辑本需求相关片段，禁止回滚；按文件级 diff 自审。
- 安全底座范围膨胀：按 Phase 退出条件推进，UI 不越过底座门禁；协议直连和维度映射明确排除。
- 大文件哈希性能：只有已验证中转文件到同卷目标的原子 rename 可免目标回读哈希；本地跨盘、远程目标和任何随后处理源的链路均按 ADR-0013 比较 SHA-256。
- 网络文件系统不支持预期原子 rename：发布能力按位置 capability 判定，不能证明时保持临时状态并不处理源。
- UI 重新复杂化：证明切片先验收，绿色项只摘要，异常项才展开；拒绝条件作为自评审门禁。

## 验收标准

- 配置 READY 之前无法触发扫描、清理、恢复或文件移动。
- 任意中断场景下，不删除未经验证且未记录完成的源文件。
- 回收/恢复 API 无法操作配置回收根之外路径。
- 来源掉线有显性状态，恢复后不会把全部旧文件误判为新文件。
- 安装、升级、重装不覆盖现有用户目录选择。
- 首次配置只要求处理目录异常、TMDB、整理预设和显式自动化/清理选择。
- 胶卷导航和 cinema 黑金主题保留，桌面/窄屏无明显风格偏离。
- 维度映射结果与本轮开始前保持一致。
- 自动测试、静态检查、文档检查通过；真实 fnOS UAT 与本地验证分开报告。

## 参考

- [Frontend Standards](../standards/frontend.md)
- [Safety Standards](../standards/safety.md)
- [Configuration Architecture](../architecture/configuration.md)
- [Storage and Filesystem Architecture](../architecture/storage-filesystem.md)
- [fnOS Deployment](../architecture/deployment-fnos.md)
- [Python shutil](https://docs.python.org/3.12/library/shutil.html)
- [Python os](https://docs.python.org/3.12/library/os.html)
- [SQLite Atomic Commit](https://sqlite.org/atomiccommit.html)

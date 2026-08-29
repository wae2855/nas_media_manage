---
title: "fix: fnOS 安装包运行时与配置初始化就绪"
type: plan
date: 2026-08-30
status: complete
confidence: high
requirement: REQ-20260828-151346
---

# fnOS 安装包运行时与配置初始化就绪计划

把当前“可以生成 FPK、但干净 fnOS 不一定能启动”的发布链路，收敛为可重复构建、可验证内容、首次初始化原子且失败可见的候选安装包。

## Problem Statement

现有 `deploy/build_fpk.sh` 能生成格式合法的 FPK，但存在四个安装前阻塞：旧产物不含当前源码；manifest 未声明 `python312`；启动脚本不识别 fnOS 官方 Python 运行时；安装向导只收集端口，没有把来源、片库和本地回收目录写入唯一运行配置。升级依赖安装失败还会被吞掉，源码复制会携带本机缓存文件，仓库也缺少 FPK 内容门禁。

这意味着“fnpack build 成功”不能证明“用户安装后能打开应用并进入配置检查”。

## Target End State

- manifest 声明 fnOS 官方 `python312` 运行时，生命周期脚本优先使用 `/var/apps/python312/target/bin/python3`。
- venv 位于应用可写、可持久化的 `${TRIM_PKGVAR}`，首次启动和升级失败均向用户显示明确原因。
- 安装向导收集端口、来源目录、片库根、本地回收目录和初始 API Key；首次安装原子写入配置，升级/修复安装不覆盖用户配置。
- 中转、日志、DB 使用应用私有本地目录；来源和片库根不由安装脚本擅自创建，正式使用前仍由开场检查验证存在、授权、位置和容量。
- 构建仅包含受控源码，不包含 `__pycache__`、`.pyc`、`.DS_Store`；产物生成 SHA-256。
- 自动测试覆盖配置初始化幂等性、升级保留、脚本合同和 FPK 内容；本地构建产物包含当前关键模块。

## Scope

- `deploy/build_fpk.sh`：fnpack 获取、manifest、向导、生命周期脚本、源码清理和构建后验证。
- `deploy/fnos_config.py`：只依赖 Python 标准库的 YAML 标量原子初始化/端口更新工具。
- `scripts/validate_fpk.py`：FPK 结构、版本、运行时、当前模块、禁止文件和 JSON 的离线检查。
- `tests/test_fnos_packaging.py`：安装配置、保留语义、构建合同和验证器回归。
- fnOS 部署、发布流程、测试矩阵和相关 ADR 文档。

## Non-Goals

- 不在本轮自动安装到真实 fnOS，不声称完成 x86_64/ARM64 真机验收。
- 不发布 GitHub Release，不上传 FPK，不自动提交或推送。
- 不集成 WebDAV/SMB/网盘协议，也不绕过 fnOS 的授权目录机制。
- 不把 Python wheels 全量内嵌进 FPK；首次创建 venv 仍需要设备能安装 `requirements.txt`。
- 不把安装向导路径输入误称为 fnOS 原生目录选择器；官方向导当前只有文本等通用字段，真机授权体验单独验收。

## Proposed Solution

### 1. 运行时与生命周期

manifest 增加 `install_dep_apps=python312`。`cmd/main` 显式扩展官方运行时 PATH，优先选择官方 Python 3.12，并将 venv 放到 `${TRIM_PKGVAR}/venv`。启动后短暂确认 PID 仍存活；失败时写入 `${TRIM_TEMP_LOGFILE}`。升级依赖安装失败必须退出非零，保留旧配置和明确日志。

### 2. 首次配置事务

安装向导使用稳定 `wizard_` 字段收集路径、端口和初始 Key。生命周期脚本先校验端口、绝对路径和非空 Key，再调用标准库工具从模板生成临时配置、fsync、`os.replace`。如果配置已存在，安装回调不覆盖；配置向导只更新端口，不改业务目录。

目录策略保持现有 ADR：来源、片库和回收根只记录，不自动创建；中转和日志使用 `${TRIM_PKGVAR}` 私有目录。回收位置是否本地、外部目录是否授权，由首次开场检查判定。

### 3. 可重复构建与内容门禁

构建脚本支持 macOS/Linux 与 arm64/amd64 的 fnpack 1.2.3，拒绝未知平台或版本。复制根源码后删除本机缓存和 Finder 文件。`fnpack build` 后运行离线验证器，校验 manifest、JSON、可执行脚本、当前关键模块和禁止文件，再复制到 `build/` 并生成 `.sha256`。

## Decision Rationale

- 采用官方运行时依赖，而不是假设系统自带 Python：干净设备安装才可重复。
- 使用标准库配置工具，而不是 `sed` 拼接 YAML：支持中文和空格，避免部分写入及分隔符破坏。
- 首次写入与升级保留分离：符合 ADR-0011，避免修复安装重置用户目录。
- 路径仍由开场检查做真实能力判断：安装向导只能收集字符串，不能证明挂载、权限和本地性。
- 构建后检查真实 FPK，而不是只检查源脚本：防止复制遗漏、缓存污染和旧产物冒充新版本。

## Constraints and Boundaries

- `${TRIM_PKGVAR}/config/config.yaml` 是运行配置唯一事实源。
- 外部来源、片库和回收根不存在时不得自动创建同名目录。
- Key 不写日志、不出现在构建产物默认值中；前端仍只接收脱敏值。
- 产物验证通过不等于真机安装通过；必须分别报告 LOCAL_BUILD 与 FNOS_UAT。
- `.opencode/` 与任何本机配置、数据库、日志不得进入 FPK 或提交范围。

## Assumptions

| Assumption | Status | Evidence / Mitigation |
|---|---|---|
| fnOS 可通过 manifest 安装 Python 3.12 | Verified | 官方 runtime 文档给出 `install_dep_apps=python312` 和运行时 PATH |
| wizard 值作为同名环境变量传给生命周期脚本 | Verified | 官方 wizard 文档与现有 `wizard_port` 合同 |
| wizard 支持原生目录选择器 | Unverified / rejected | 官方字段列表未提供目录类型；本轮用必填文本路径并在真机确认授权体验 |
| `${TRIM_PKGVAR}` 可写且跨重启保留 | Verified | fnOS framework 定义为运行持久数据目录，现有配置和 DB 已依赖它 |
| 设备首次启动可访问 Python 包源 | Unverified | 保留为真机前置条件；失败必须用户可见，后续可评估 wheelhouse |
| fnpack 1.2.3 下载 URL 字节稳定 | Partially verified | 使用官方静态域名并固定校验和；下载/校验失败关闭构建 |

## Risks

- **用户输入路径未授权**：安装仍可完成，应用进入 BLOCKED；完成页明确指出权限和位置问题，不启动自动任务。
- **PyPI 不可达**：首次启动失败并展示可操作错误；不伪装为运行成功。
- **升级 requirements 失败**：升级回调返回失败，防止带着半更新依赖启动。
- **不同架构 fnpack 字节不一致**：每个平台独立校验和，未知组合直接拒绝。
- **安装 Key 增加首次输入成本**：换取局域网可写 API 不裸奔；说明 Key 需妥善保存。

## Implementation Tasks

### Phase 1: 配置与运行时合同

- [x] 新增标准库 fnOS 配置初始化工具及原子、幂等、端口更新测试。
- [x] manifest 声明 `python312`，启动/升级脚本使用官方运行时与 `${TRIM_PKGVAR}/venv`。
- [x] 安装向导新增来源、片库、回收和 API Key；回调首次写入且不覆盖已有配置。

**Exit**：模拟安装可以生成可加载配置；再次安装保持用户修改；升级失败不会静默成功。

### Phase 2: 构建与产物门禁

- [x] 更新 fnpack 1.2.3 平台解析和校验和验证；官方未提供 Linux arm64 下载时明确拒绝该构建主机。
- [x] 清除源码缓存/系统文件，更新 manifest 文案与安装提示。
- [x] 新增 FPK 离线验证器并接入构建脚本，生成 SHA-256 文件。

**Exit**：构建产物包含当前关键模块且不含本机缓存，版本和摘要可追溯。

### Phase 3: 回归、文档与候选包

- [x] 增加 packaging current tests，更新部署、发布和测试文档。
- [x] 运行 packaging 专项、全量 pytest、shell/JSON/docs/compile 检查。
- [x] 构建新的本地候选 FPK，验证 manifest、内容、大小和 SHA-256。

**Exit**：LOCAL_BUILD PASS；FNOS_UAT 明确为 NOT_RUN，产物可交给用户安装。

## Acceptance Handoff

- `LOCAL_BUILD`: PASS（0.3.0，717 tests passed，FPK 内容与 SHA-256 已验证）
- `FNOS_UAT`: NOT_RUN（等待用户在真实 fnOS 验证首次安装、目录授权、依赖下载、桌面入口、启动和升级保留）

## Acceptance Criteria

- 新 FPK manifest 的版本等于构建参数并包含 `install_dep_apps=python312`。
- FPK 内包含 `startup_readiness.py`、`library_paths.py`、`source_units.py`、`source_unit_repo.py`。
- FPK 内不存在 `.pyc`、`__pycache__`、`.DS_Store`、`.env`、数据库或日志。
- 首次安装配置准确写入端口、来源、片库、回收和非空 Key；中转/日志指向 `${TRIM_PKGVAR}`。
- 重复初始化不覆盖现有配置；配置回调仅更新端口。
- 启动找不到 Python、pip 失败或进程立即退出时，生命周期脚本返回失败并写用户可见原因。
- 构建生成 `.fpk` 和匹配的 `.sha256`；离线验证器通过。
- 全量稳定回归通过；真实 fnOS 安装、依赖下载、目录授权、桌面 CGI 和启动状态单列等待用户验收。

## References

- [现有提案](../proposals/2026-08-28-storage-safe-configuration-redesign.md)
- [ADR-0011](../decisions/0011-fnos-install-runtime-config-ownership.md)
- [ADR-0003](../decisions/0003-deploy-package-generation-strategy.md)
- [fnOS Runtime](https://developer.fnnas.com/docs/core-concepts/runtime/)
- [fnOS Wizard](https://developer.fnnas.com/docs/core-concepts/wizard/)
- [fnpack](https://developer.fnnas.com/docs/cli/fnpack/)

# Architecture: 配置依赖、来源单元与运行就绪

- **Requirement**: [REQ-20260828-151346](../tracking/requirements-board.md)
- **Stories**: [configuration-dependency-and-readiness.md](configuration-dependency-and-readiness.md)

## Requirements

### Functional Requirements

| ID | Requirement | Story |
|---|---|---|
| FR-001 | 配置保存三态来源处理模式并迁移旧布尔组合 | STORY-001 |
| FR-002 | 聚合同一来源单元任务并在全部成功后整体回收 | STORY-002 |
| FR-003 | 使用已校验片库根和相对规则模板 | STORY-003 |
| FR-004 | LLM 启用动作提供上下文配置和连接验证 | STORY-004 |
| FR-005 | 高级设置保持胶卷与来源阶段上下文 | STORY-005 |
| FR-006 | 聚合必要依赖形成开场检查报告 | STORY-006 |

### Non-Functional Requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-001 | 文件安全 | 未证明来源单元完整成功时移动文件数为 0 |
| NFR-002 | 路径安全 | 根外绝对路径、`..`、符号链接逃逸全部拒绝 |
| NFR-003 | 兼容迁移 | 旧配置加载不崩溃，无法无损迁移时 BLOCKED |
| NFR-004 | UI 一致性 | 1440×1024、390×844 无溢出，cinema tokens 不变 |
| NFR-005 | 状态可信 | 开场检查结果绑定 config revision，配置变化立即失效 |

## Architecture Decision Records

### ADR-014: 来源处理使用枚举模式和来源单元

**Status:** Accepted

**Decision:** 由 `source_policy.mode` 成为业务事实源；模式 3 引入来源单元 ID、快照与聚合状态，清理动作只移动服务端计算的根内来源单元。

**Consequences:** 需要 DB migration 和 scanner/task 关联；换来可解释、可重试、不会部分清空文件夹的行为。

### ADR-015: 片库路径使用根目录与相对模板

**Status:** Accepted

**Decision:** `library_root` 由存储检查管理，规则保存相对模板；配置与运行时双重 containment 校验。

**Consequences:** 单根体验简单且安全；多根片库延后。

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| Python standard library | 3.12 | pathlib/os/commonpath/hashlib/sqlite3；不新增第三方依赖 |
| Native browser APIs | current fnOS WebView | dialog、DOM、fetch；不新增前端框架 |

## Integration Pattern

- **Entry point:** 配置 API 保存和 UI 阶段选择；scanner 创建任务时解析来源单元。
- **Data flow:** YAML 迁移为规范配置 → ConfigView → readiness/source lifecycle；任务保存 `source_unit_id` → 聚合器计算是否可回收 → recycle verified transfer。
- **Events:** 不新增事件总线。任务完成后同步请求来源单元协调器；未满足条件只记录等待原因。
- **Readiness:** `build_startup_readiness_report(config, revision)` 聚合 storage readiness、config contract、Provider/conditional LLM connectivity；不复用影片模拟器。

> **BINDING:** UI 不得自行推断三态或 READY；文件移动不得接受客户端来源单元路径；分类运行时必须再次验证目标在 library_root 内。

## Configuration Contract

```text
library_root: /volume1/media
path_rules[].template: Movies/{year}/{title_cn} ({year})
fallback_dir: Unsorted
source_policy.mode: preserve_all | preserve_media | recycle_source_unit
source_policy.unit_strategy: top_level_folder
```

兼容字段 `cleanup_source_after_done` 只作为迁移输入；保存新配置后由规范字段派生兼容投影，业务逻辑不再读取旧布尔值。

## Source Unit State

```text
DISCOVERING → ACTIVE → READY_TO_RECYCLE → RECYCLING → RECYCLED
                  └→ BLOCKED / CHANGED / WAITING
```

- 来源根下第一层目录为 folder unit。
- 根下全部直接文件形成唯一 loose-root unit，成员包括媒体和所有直接非目录文件。
- unit snapshot 至少包含成员 realpath、size、mtime_ns；执行前重算。
- `READY_TO_RECYCLE` 要求所有成员媒体任务为成功入库，且不存在未稳定媒体文件。

## File Structure

```text
media_importer/features/source_files/source_units.py       — 来源单元识别、快照、聚合与回收协调
media_importer/features/configuration/startup_readiness.py — 开场检查聚合
media_importer/features/configuration/migration.py         — 三态和片库根迁移（若现有 loader 内拆分合适）
media_importer/core/db/source_unit_repo.py                  — 来源单元持久化
media_importer/webui/js/cinema-config-readiness.js          — 开场检查渲染与修复导航
tests/test_source_unit_lifecycle.py                         — 整体等待/回收/变化/掉线
tests/test_library_root_boundary.py                         — 迁移与路径逃逸
tests/test_startup_readiness.py                             — 聚合状态与 revision
```

现有配置 JS/CSS/HTML 在原语义文件内修改，不创建第七个 CSS 文件。

## External Services

| Service | Purpose | Auth | Failure behavior |
|---|---|---|---|
| TMDB | 必要 Provider 连通性 | existing API key | BLOCKED，提供重试/配置入口 |
| LLM endpoint | 可选源清理辅助 | existing masked key | 启用时 BLOCKED；未启用 SKIPPED |

## Security Considerations

- 所有来源单元和规则路径由服务端 canonicalize；客户端不提交可执行物理路径。
- 来源根、片库根和回收根禁止危险嵌套；符号链接逃逸 fail closed。
- 整体文件夹只移入本地回收站，禁止直接删除。
- 开场检查结果不包含 API Key，动态文案进入 DOM 前 escapeHtml。
- config revision 防止检查后配置变化仍沿用旧 READY。

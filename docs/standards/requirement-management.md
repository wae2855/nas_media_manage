# Requirement Management Standard

管理并行需求的注册、状态流转、隔离、验收和废弃。

## 1. Requirement ID

格式：`REQ-YYYYMMDD-HHmmSS`

- AI 创建时取当前时间戳，精确到秒。
- 示例：`REQ-20260608-143052`
- 同一秒内出现多个需求时追加 `-N` 后缀（如 `REQ-20260608-143052-2`）。

## 2. Requirement Board

[requirements-board.md](../tracking/requirements-board.md) 只保留活跃需求。

**活跃状态**：`draft`、`planned`、`in_progress`、`review`、`pending_acceptance`
**移出状态**：`accepted`（→ [completed-items.md](../tracking/completed-items.md)）、`discarded`（→ [discarded-items.md](../tracking/discarded-items.md)）

AI 每次对话开始只扫描 Board 文件。已完成和废弃记录不在 Board 中保留，避免上下文膨胀。

### 字段定义

| Field | Required | Description |
|-------|----------|-------------|
| ID | ✅ | `REQ-YYYYMMDD-HHmmSS` |
| Title | ✅ | 简短描述 |
| Type | ✅ | `feature` / `bugfix` / `refactor` / `docs` / `frontend` |
| Status | ✅ | 当前状态 |
| Priority | ✅ | `P0` / `P1` / `P2` / `P3` |
| Dependencies | | 依赖的需求 ID，无则 `-` |
| Affects | | 影响的代码模块或文档路径 |
| Branch | | git 分支名 |
| Links | ✅ | 关联文档链接（Plan、ADR、测试、feature doc 等） |
| Created | ✅ | 注册时间 |
| Updated | ✅ | 最近变更时间 |

### Links 字段格式

用行内链接列出所有关联文档：

```
Plan: [plan](../plans/xxx.md) | ADR: [adr](../decisions/xxx.md) | Tests: [test](../../tests/test_xxx.py) | Docs: [feature](../features/xxx.md)
```

缺失的文档类型省略即可。

## 3. Status Flow

```
draft → planned → in_progress → review → pending_acceptance → accepted → closed
                                                                          ↘ discarded
```

| Status | 含义 | 存放位置 |
|--------|------|----------|
| `draft` | 已注册，方案待定 | Board |
| `planned` | 方案/计划已确认 | Board |
| `in_progress` | 正在开发 | Board |
| `review` | 开发完成，自验中 | Board |
| `pending_acceptance` | 等待用户验收 | Board |
| `accepted` | 用户验收通过 | [completed-items.md](../tracking/completed-items.md) |
| `discarded` | 需求废弃 | [discarded-items.md](../tracking/discarded-items.md) |
| `closed` | 归档完成 | 随 accepted 记录，无需单独保留 |

### 状态转换门禁

| 转换 | 必须满足 |
|------|----------|
| draft → planned | 有 Plan 文件；涉及架构变更时有 ADR |
| planned → in_progress | 依赖的需求状态 ≥ accepted；无同级冲突（见隔离规则） |
| in_progress → review | 编译通过；相关测试通过或记录暂缓原因；文档已同步 |
| review → pending_acceptance | 自验通过；pending-acceptance.md 已更新 |
| pending_acceptance → accepted | 用户明确确认 |
| pending_acceptance → in_progress | 用户要求返工，记录原因 |
| 任意 → discarded | 用户确认废弃；代码回退或保留说明已记录 |

### 状态变更操作

每次变更同步执行：

1. 更新 Board 中该需求的 Status 和 Updated 字段。
2. 如果进入 `accepted`：从 Board 移除，摘要写入 [completed-items.md](../tracking/completed-items.md)，Plan/proposal 移入 `docs/_archive/`。
3. 如果进入 `discarded`：从 Board 移除，记录写入 [discarded-items.md](../tracking/discarded-items.md)，代码回退或保留说明写入该记录。

## 4. Parallel Development Isolation

### 4.1 冲突检测

注册需求时必须填写 `Affects` 字段。AI 推进前检查：

- 同模块（`Affects` 有交集）是否有其他 `in_progress` 需求。
- 有交集时须等先注册的需求进入 `review` 或更高状态，或由用户明确允许并行。

### 4.2 分支策略

| 场景 | 分支规则 |
|------|----------|
| 单需求开发 | 直接在 main 提交，commit 带 `[REQ-xxx]` 前缀 |
| 多需求并行 | 每个需求创建 `req/REQ-YYYYMMDD-HHmmSS` 分支 |
| 紧急修复（P0） | 直接在 main，commit 带 `[HOTFIX]` |

完整分支和提交规范见 [git.md](git.md)。

### 4.3 合并规则

- 合并前跑通全量测试。
- 合并顺序：P0 > P1 > P2 > P3；同优先级按注册时间。
- 合并冲突由 AI 标记，交用户决策。

## 5. Acceptance Reminder

- `pending_acceptance` 超过 **24 小时**的需求，AI 在每次对话开始主动提醒。
- 提醒格式：需求 ID、标题、等待时长。
- 用户延后验收时，在 Board 的 Updated 字段备注原因。
- 延后超过 **7 天**，AI 标记 ⚠️ 超期提醒。

### 验收流程

1. 用户确认 → Board 中移除，写入 [completed-items.md](../tracking/completed-items.md)。
2. 摘要包含：ID、标题、关键 commit、验证结果、关联文档链接。
3. 沉淀的可复用规则更新到 `docs/standards/` 或 `AGENTS.md`。
4. Plan/proposal 移入 `docs/_archive/`。

## 6. Discard & Rollback

### 6.1 废弃流程

1. 用户确认废弃。
2. Board 中移除，写入 [discarded-items.md](../tracking/discarded-items.md)，记录废弃原因和替代方案。
3. 代码处理：
   - 未合并分支：删除分支。
   - 已合并到 main：创建 revert commit 或由用户决定保留。
   - 直接在 main 开发：评估范围，用户决定 revert 或保留。
4. Plan/proposal 移入 `docs/_archive/`。
5. 从 [pending-acceptance.md](../tracking/pending-acceptance.md) 移除（如已在其中）。

### 6.2 部分回退

1. [discarded-items.md](../tracking/discarded-items.md) 记录回退范围。
2. revert commit 只涉及需回退的文件。
3. 保留部分视为新状态继续推进。

## 7. AI Behavior Rules

- 每次对话开始，读取 [requirements-board.md](../tracking/requirements-board.md)（仅活跃需求）。
- 存在 `pending_acceptance` 超 24 小时的需求时，主动提醒。
- 存在 `in_progress` 的需求时，确认本次推进哪个。
- 状态变更必须同步更新 Board。
- 一个对话只推进一个需求，除非用户明确要求同时处理。
- 不主动读取 completed-items 和 discarded-items，除非用户明确要求查阅历史。

## 8. Cross-Linking Convention

所有需求相关文档必须双向链接：

| 文档类型 | 必须包含的链接 |
|----------|---------------|
| Plan 文件 | 头部标注 `Requirement: [REQ-xxx]`，链接回 Board |
| ADR 文件 | 如关联需求，标注 `Requirement: [REQ-xxx]` |
| feature doc | 如由需求驱动，标注 `Requirement: [REQ-xxx]` |
| 测试文件 | 注释行标注 `# Requirement: REQ-xxx` |
| Board 条目 | Links 字段列出 Plan、ADR、测试、feature doc 的路径链接 |

Plan 文件头部模板：

```markdown
# Plan Title

- **Requirement**: [REQ-20260608-143052](../tracking/requirements-board.md)
- **ADR**: [0005-xxx](../decisions/0005-xxx.md)（如适用）
- **Status**: planned / in_progress / completed
```

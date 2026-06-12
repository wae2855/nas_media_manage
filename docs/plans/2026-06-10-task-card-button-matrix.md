# 任务卡片按钮矩阵收敛计划

> 日期: 2026-06-10 | 状态: complete

---

## 一、背景

任务卡片在 2026-06-10 上一轮增加了“详情”幽灵按钮后，叠加了原有的 `taskPrimaryAction()` 状态分支，导致多类状态同时出现"查看 / 详情 / 查看结果"等按钮，全部映射到同一个 `view-task` 动作，职责重叠。

需要：

1. 统一"打开详情"入口为“详情”幽灵按钮；
2. 主按钮 / 次按钮只表达状态动作（取消 / 确认 / 重试 / 重新投入 / 移入回收）；
3. 同步更新规范中的按钮矩阵和编辑权限矩阵。

---

## 二、目标

| status / stage | 主按钮 | 次按钮 | 详情幽灵 | 文件名可编辑 | 维度可编辑 |
|---------------|--------|--------|----------|--------------|------------|
| PENDING/QUEUED | 取消 | — | 详情 | 否 | 否 |
| PENDING/RUNNING | — | — | 详情 | 否 | 否 |
| PENDING/AWAIT_REVIEW | 去确认 | — | 详情 | 是 | 是 |
| SUCCESS | — | — | 详情 | 否 | 否 |
| FAILED | 去重试 | 移入回收 | 详情 | 否 | 否 |
| SKIPPED | 去重试 | — | 详情 | 否 | 否 |
| CANCELLED | 重新投入 | — | 详情 | 否 | 否 |

---

## 三、非目标

1. 不修改详情弹窗的内部布局；
2. 不调整后端 API；
3. 不支持取消 RUNNING；
4. 不重新设计"批量操作"工具栏。

---

## 四、设计决策

### D1：详情入口唯一化

"详情"幽灵按钮是唯一打开详情弹窗的入口。"查看 / 查看结果" 主按钮全部移除。

### D2：状态主按钮语义

主按钮只能是“状态推进”或“清理”动作：

- PENDING/QUEUED：取消；
- PENDING/AWAIT_REVIEW：去确认；
- FAILED / SKIPPED：去重试；
- CANCELLED：重新投入；
- RUNNING / SUCCESS：暂无主按钮（避免在用户端"假装能做什么"）。

### D3：编辑权限矩阵

详情弹窗的字段是否可编辑取决于 `isAwaitReview`，与卡片按钮矩阵完全一致。`PENDING/AWAIT_REVIEW` 是唯一可以编辑文件名 + 分类维度的状态；其他状态一律只读。

---

## 五、任务清单

- [x] `media_importer/webui/js/cinema-tasks.js`：
  - 删除 `taskPrimaryAction` 中 `SUCCESS` 与 default 的 `view-task` 分支；
  - 删除 `taskSecondaryAction` 中不再需要的“移入回收”以外的状态分支；
  - `renderTaskCard` 中 `详情` 幽灵按钮保留为唯一详情入口。
- [x] `media_importer/webui/js/cinema-app.js`：
  - 删除已不再触发的 `view-task` 主按钮派生路径（保留 `view-task` 处理函数）。
- [x] `docs/architecture/api.md`：
  - 在"任务详情弹窗编辑矩阵"中追加主/次/详情三列。
- [x] `docs/plans/2026-06-09-task-status-stage-refactor.md`：
  - 同步按钮矩阵。
- [x] `docs/features/tasks.md`：
  - 同步按钮矩阵与编辑权限。
- [x] 运行专项测试、compileall 与 diff 检查。

---

## 六、验收标准

1. 任务卡片最多包含 1 个状态主按钮 + 1 个"详情"幽灵按钮；FAILED 卡片额外保留“移入回收”次按钮；
2. 没有"查看"或"查看结果"出现在主/次按钮中；
3. PENDING/AWAIT_REVIEW 详情中文件名和维度都可编辑，其他状态只读；
4. 文档矩阵与代码实现完全一致。

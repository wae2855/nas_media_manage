---
title: "文件全流程状态机重构方案"
type: proposal
date: 2026-08-23
status: complete
requirement: REQ-20260822-000004
---

# 文件全流程状态机重构（Phase 2 方案）

> 用户诉求原话：「文件从拷贝到临时区到处理完一路流程上的环节，回退、继续做的不够全面完善和专业，测试不足，场景考虑不足」。本文基于代码实证给出现状诊断与方案。

## 1. 现状模型（事实）

```text
status:  PENDING | FAILED | SKIPPED | SUCCESS | CANCELLED     （业务结果）
stage:   QUEUED | RUNNING | AWAIT_REVIEW | DONE               （执行阶段，PENDING 细分）
file_location: source | temp | import | recycle              （物理位置）
附属:    confirm_status / confirmed_override / retry_count / current_step / percentage
```

流程（runner.process_one 硬编码）：copy → scrape → validate（分流 FAILED/审核/确认）→ classify → manual_review 分流 → dedup → rename → import → notify → record。
确认流（confirm.py）：mark_confirmed → restore_confirm_temp_name → dedup → rename → import → notify → record。

## 2. 问题诊断（代码实证）

### P1 转换规则无集中守护（根因）
转换合法性判断散落在 `task_manager.retry_task/cancel_task`、`confirm.confirm_task`、`file_lifecycle.ignore_task` 各自的 if 里；`_apply()`/`db_update_task` 是无条件字段合并——**任何代码可把任务写成任意状态**，无 guard、无负向测试。这是"回退/继续不专业"的根源：每个操作各自发明规则，边界不一致。

### P2 状态字段与物理文件可撒谎
- 通用异常分支 `mark_failed(file_location=SOURCE)` 硬编码，但失败瞬间文件可能在 temp（`video_path` 又存着 temp 路径，两字段互相矛盾）；靠事后 `_cleanup_temp_on_failure` 补救，清理失败则状态永久失真。
- 崩溃恢复（`_cleanup_orphaned_state`）只处理 RUNNING→FAILED 与 temp 孤儿清理；AWAIT_REVIEW 的 temp 被外部删除（矩阵 C27）时 file_location 仍标 temp，confirm 才报错，无自愈。

### P3 重试语义不完整
- `reset_for_retry` 无条件清空 video_path/file_location → **任何环节失败都从 copy 从头再来**。大文件（几十 GB）在 import 环节失败后重试要整份重新复制，纯浪费。
- AWAIT_REVIEW 任务 retry：temp 文件不清理即重置为 source——留下孤儿 temp 直到下次重启。
- `retry_all_failed` 把 SKIPPED/CANCELLED 一并复活：**用户明确"忽略/取消"的终态决策被批量重试推翻**，语义冲突。

### P4 幂等/并发守护缺失
- `confirm_task` 无原子性：两个并发请求都读到 AWAIT_REVIEW → 双导入风险（check-then-act 竞态；当前靠单线程队列侥幸规避，API 直调 confirm 不受保护）。
- import 目标已存在时报错 FAILED 而非幂等判定（同指纹应幂等成功）。

### P5 主流程与确认流双份维护
`_step_import` 与 `_step_import_from_confirm` 重复 dedup/rename/import 逻辑（file.py:135-183），改动易漏一份——Phase 1 评审同款问题的温床。

### P6 测试与场景缺口
- 现有 39 个生命周期测试只断言 mark_* 的字段结果（happy path），**零负向转换测试**、零并发测试、零续跑测试、零"retry-all 不复活 SKIPPED"边界。
- 笛卡尔积矩阵（`_drafts/2026-06-18-file-flow-cartesian-product.md`）定义了 32 主路+8 组异常，但其 B10-B14/AI 分支已随 ADR-0010 退役——矩阵本身需两级化更新，尚未落地为测试。

## 3. 方案：三层收敛（不推倒重来）

**判断依据**：status/stage/file_location 双层模型本身健全（06-09 重构成果，前端已适配），要修的是"规则不集中、续跑缺失、无原子守护"。推倒重来（如引入工作流引擎/新状态字段）收益低破坏大。

### S1 转换表集中化（核心，先做）

新建 `features/tasks/transitions.py` 作为**唯一状态转换事实源**：

```python
# 动作 → (前置 status/stage, 目标 status/stage, file_location 规则, 副作用校验)
TRANSITIONS = {
  "start":     (("PENDING","QUEUED"),    ("PENDING","RUNNING"),  keep),
  "need_confirm": (...RUNNING,           (...AWAIT_REVIEW),      require_temp_exists),
  "confirm":   (...AWAIT_REVIEW,         (经 RUNNING),           require_temp_exists),
  "import_ok": (...,                     ("SUCCESS","DONE"),     to_import),
  "fail":      (任意活动态,               ("FAILED","DONE"),      由失败环节决定 location),
  "retry":     (("FAILED"|"CANCELLED"|审核态,"DONE"), ("PENDING","QUEUED"), cleanup_temp),
  "cancel":    (("PENDING","QUEUED"),    ("CANCELLED","DONE"),   keep_source),
  ...
}
def apply(task, action, **ctx) -> fields   # 校验+生成字段，非法抛 TransitionError
```

- task_manager/confirm/ignore/runner 的所有状态写入改走 `transitions.apply`；删除各自 if 判断。
- mark_* 函数降级为内部实现细节或直接删除。
- file_location 规则内置：fail 时按"失败环节+temp 是否实际存在"决定，杜绝字段撒谎。
- **参数化负向测试**：转换表驱动自动生成全部 (状态×动作) 非法组合断言拒绝。

### S2 断点续跑（最小 checkpoint，收益最大化）

不做全环节 checkpoint，只做最有价值的一档：**copy 完成**。

- retry 时：若 `video_path` 指向的 temp 文件存在 → 保留 `file_location=temp`，process_one 检测后**跳过 copy 从 scrape 续跑**；temp 不存在自动降级从头。
- 收益覆盖全部痛点场景：scrape/classify/dedup/rename/import 失败的重试不再重复复制大文件。
- 风险（如实告知）：续跑要求 scrape 及之后每步可从既有 temp 进入（现状本就如此，确认流已验证该路径可行）。

### S3 幂等与并发守护

- `confirm/retry/cancel/ignore` 的 DB 更新改 compare-and-swap：`UPDATE ... WHERE task_id=? AND status=? AND stage=?`，affected=0 即返回"状态已变更"，原子拒绝并发双操作。
- import 幂等：目标存在且指纹相同 → 幂等成功；不同 → 明确错误码 CONFLICT。
- `retry_all_failed` 收敛：默认仅 FAILED；SKIPPED/CANCELLED 需显式参数才复活（前端批量重试传 FAILED-only）。

### S4 测试矩阵落地（两级匹配版）

1. 更新笛卡尔积矩阵：B10-B14/AI 分支替换为两级匹配等价物（Tier1 低匹配→英文回退→仍低→AWAIT_REVIEW），转入 `docs/testing/` 成为正式测试设计源。
2. 落地回归套件：M01-M32 主路（临时目录 fixture + mock provider，可全自动跑）+ 关键异常注入（C1/C3/C8/C24/C27 五条最高价值）。
3. 转换表参数化负向测试（S1 产出自动生成）。

### S5 代码收敛（顺带）

`_step_import_from_confirm` 复用 `_step_dedup/_step_rename/_step_import`，消除双份维护（S1 改造时自然完成）。

## 4. 实施顺序与工作量

| 步 | 内容 | 量级 | 依赖 |
|----|------|------|------|
| S1 | transitions.py + 全调用方迁移 + 负向测试 | 1-1.5 天 | — |
| S3 | CAS 更新 + retry-all 收敛 + import 幂等 | 0.5-1 天 | S1 |
| S2 | copy-checkpoint 续跑 + temp 存在性降级 | 0.5-1 天 | S1 |
| S5 | 确认流复用主流程步骤 | 0.5 天 | S1 |
| S4 | 矩阵两级化 + 32 主路回归 + 5 异常注入 | 2-3 天 | S1-S3 |

每步独立可回归（现有 564 测试 + 新增测试全绿）。

## 5. 验收标准

1. 全库只有 `transitions.py` 定义状态写入规则（grep 验证无散落 `status=` 直写）。
2. 全部 (5 status × 4 stage × 8 动作) 组合的合法性有测试断言（合法通过/非法拒绝）。
3. import 环节失败重试不再重新 copy（集成测试验证 temp 复用）。
4. 并发 confirm 只成功一次（测试模拟两线程）。
5. retry-all 不复活 SKIPPED/CANCELLED。
6. 32 主路 + 5 异常注入回归套件全绿，进入常规 CI 命令。

## 6. 决策点

| # | 决策 | 推荐 |
|---|------|------|
| D1 | 是否引入持久化任务队列/工作流引擎（如 SQLite job 表+worker） | ❌ 不引入：当前单进程+线程模型够用，复杂度换不来收益 |
| D2 | retry-all 对 SKIPPED/CANCELLED 的默认行为 | 仅 FAILED（尊重用户终态决策） |
| D3 | 续跑档位 | 仅 copy-checkpoint 一档（全环节 checkpoint 投入产出比低） |

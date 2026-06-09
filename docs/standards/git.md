# Git Standards

## Baseline

大重构开始前必须创建 baseline commit。

当前 AI-ready 重构 baseline:

```text
b73f54e chore: baseline before ai-ready architecture refactor
```

## Commit Rule

- 每个阶段独立提交。
- 提交说明包含测试结果或说明未测试原因。
- 不把无关行为变更混入结构重构提交。

## Dirty Worktree

如果 worktree 已有用户改动，不得回滚。先理解变更，再在其基础上工作。

## Branch Strategy

| 场景 | 分支 |
|------|------|
| 单需求开发 | 直接在 main 提交 |
| 多需求并行 | `req/REQ-YYYYMMDD-HHmmSS` |
| 紧急修复 | 直接在 main，commit 带 `[HOTFIX]` |

并行开发隔离规则见 [requirement-management.md](requirement-management.md)。

## Commit Message Convention

格式：

    [REQ-YYYYMMDD-HHmmSS] <type>(<scope>): <description>

- type: `feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `revert`
- scope: 影响模块，如 `scraping`、`config`、`frontend`
- 多需求并行时，每个 commit 只属于一个需求。
- 合并 commit 标注来源分支和需求 ID。

示例：

    [REQ-20260608-143052] feat(scraping): add tool calling support for LLM search
    [REQ-20260608-143052] test(scraping): add unit tests for tool calling flow
    [REQ-20260608-150022] fix(config): resolve migration edge case
    [HOTFIX] fix(safety): prevent path traversal in file move

## Revert Rule

- 废弃需求优先 `git revert`，不用 `git reset`。
- revert commit 格式：`[REQ-xxx] revert: <原 commit 摘要>`。
- 部分回退时 revert 后正向提交保留部分。

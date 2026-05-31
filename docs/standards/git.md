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

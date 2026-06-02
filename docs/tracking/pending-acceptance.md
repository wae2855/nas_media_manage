# Pending Acceptance

记录已完成但尚未由用户确认验收的事项。AI 在后续对话开始时应检查本文件；超过 24 小时或跨阶段未验收的事项需要主动提醒。

| Item | Completed at | Commit | Scope | Verification | User confirmation needed |
|------|--------------|--------|-------|--------------|--------------------------|
| Feature-first architecture and documentation restructure | 2026-06-02 | `42c88b9` + pending follow-up | Code structure, docs structure, archive policy, lifecycle workflow, test archive, feature public APIs | `python3 -m pytest tests/` -> 155 passed; `compileall`; `git diff --check` | Confirm new architecture/docs direction after implementation |

## Rules

- 新完成事项先进入本文件，不直接写入 completed。
- 用户验收后，将摘要移动到 `completed-items.md` 并从本文件删除。
- 如果用户要求延后验收，在本文件记录新的提醒时间或阶段。

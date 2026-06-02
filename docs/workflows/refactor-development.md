# Refactor Development Workflow

1. 创建或确认 baseline commit。
2. 写清楚目标、非目标、风险和验收标准。
3. 每阶段保持项目可运行。
4. 优先写测试或记录基线失败。
5. 结构重构和行为变更分开。
6. 每阶段同步文档。
7. 每阶段单独提交。
8. 完成后写入 `docs/tracking/pending-acceptance.md`。
9. 用户验收后写入 `docs/tracking/completed-items.md`。
10. 将已完成、被替代或废弃计划归档到 `docs/_archive/`。

大型重构顺序建议：

```text
feature 入口 -> infrastructure/shared 边界 -> API/CLI 薄化 -> 文档事实补全 -> 回归验证 -> 验收归档
```

完整闭环见 [project-lifecycle.md](project-lifecycle.md)。

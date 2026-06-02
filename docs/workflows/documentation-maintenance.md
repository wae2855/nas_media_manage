# Documentation Maintenance Workflow

## Monthly Checklist

- 检查 `docs/README.md` 和 `docs/INDEX.md` 是否仍指向正确入口。
- 检查新代码模块是否有模块文档。
- 检查已实施方案是否迁移为架构事实或 ADR。
- 检查 `_archive/` 中是否有可迁移内容。
- 检查 known failures 是否过期。
- 检查 `docs/legacy.md`，每次至少评估一个旧中文文档组是否需要迁移、加 legacy banner 或归档。

## After Major Refactor

- 更新相关 architecture 文档。
- 更新 modules 文档。
- 更新 `docs/INDEX.md`。
- 如改变决策，新增或更新 ADR。
- 如果旧中文文档与当前事实冲突，更新 `docs/legacy.md` 的冲突记录。

# Documentation Maintenance Workflow

## Monthly Checklist

- 检查 `docs/README.md` 和 `docs/INDEX.md` 是否仍指向正确入口。
- 检查新代码 feature 是否有 `docs/features/` 文档。
- 检查已实施方案是否迁移为架构事实或 ADR。
- 检查 `docs/plans/` 是否只保留活跃计划。
- 检查 `_archive/` 是否有索引，且活跃文档没有把 archive 正文作为事实来源。
- 检查 known failures 是否过期。
- 检查 `docs/tracking/pending-acceptance.md` 是否有超期未验收事项。

## After Major Refactor

- 更新相关 architecture 文档。
- 更新 feature 文档。
- 更新 `docs/INDEX.md`。
- 如改变决策，新增或更新 ADR。
- 如果旧内容已完成、废弃或被替代，移动到 `docs/_archive/` 并更新 archive README。
- 完成但未验收时写入 `docs/tracking/pending-acceptance.md`。

# Testing Documentation

测试文档用于帮助 AI 和维护者选择正确测试集合，并区分已知失败和新增回归。

| 文档 | 视角 | 用途 |
|------|------|------|
| [feature-coverage.md](feature-coverage.md) | 产品视角（按前台节点） | 地毯式列清所有产品功能点 → API → 后端实现 → 测试脚本和缺口，作为新增/补齐回归测试的基线 |
| [regression-matrix.md](regression-matrix.md) | 开发者视角（按修改范围） | 修改了 X 代码范围，推荐跑哪些测试 |
| [test-inventory.md](test-inventory.md) | 维护者视角（按测试状态） | 区分 current/gated/archive_candidate 测试 |
| [overview.md](overview.md) | 总体策略 | 测试分层、命令、报告要求 |
| [ui-playwright.md](ui-playwright.md) | UI 测试 | Playwright 套件使用方式 |
| [known-failures.md](known-failures.md) | 已知失败 | 历史失败/环境问题记录 |

## 三视角关系

```text
产品视角：  前台节点 → 功能点 → 后端入口 → 已覆盖/缺口  (feature-coverage.md)
                                        ↑
开发者视角：  修改范围 → 推荐测试集合  (regression-matrix.md)
                                        ↑
维护者视角：  测试状态 → 归档/门禁分类  (test-inventory.md)
```

修改 feature-coverage.md 时同步更新 regression-matrix.md；新增/重命名测试脚本时同步更新 test-inventory.md。

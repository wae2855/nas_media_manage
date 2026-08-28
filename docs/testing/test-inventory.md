# Test Inventory

本文件只定义测试分类规则和例外清单，不维护全量测试列表（全量用 `ls tests/` 获取）。新增/重命名测试时只更新本文件的例外部分。

## Classification Rules

| Status | 判定规则 |
|--------|---------|
| `current` | 默认状态：`python -m pytest tests/` 可直接跑的单元/集成测试，不依赖外部服务 |
| `gated` | 需要 conftest gate、本地运行服务、Playwright 浏览器或外部 API 的测试（UI/E2E 类） |
| `rewrite_later` | 场景有价值，但应按新架构/新前端重写（前端重做后处理） |
| `archived` | 已在 `docs/_archive/*/tests/`，不再参与当前测试 |

规则：文件命名 `test_<域>_<主题>.py`；feature smoke 测试以 `test_feature_` 开头；新测试默认 current，只有需要环境时才 gated 并在本文件登记。

## Gated Tests（例外登记）

| File | Notes |
|------|-------|
| `tests/test_*_ui.py`, `tests/test_frontend_*.py`, `tests/test_scrape_ui.py` | 需要 Playwright + 本地服务；非 UI 回归命令统一 ignore 这三类 |
| `tests/test_source_cleaner_e2e.py` | 脚本式 E2E，需外部服务；手动跑：`python tests/test_source_cleaner_e2e.py` |

## Rewrite Later

- 前端 UI/E2E 套件：前端重做后按 [product/frontend-information-architecture.md](../product/frontend-information-architecture.md) 重写（当前冻结待重估）。

## Default Commands

```bash
python -m pytest tests/          # 全量（含 gated，自动跳过缺环境的）
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py   # 非 UI
python -m pytest tests/test_architecture_guards.py   # 架构护栏
```

选择测试集合看 [regression-matrix.md](regression-matrix.md)（按修改范围）；覆盖缺口看 [feature-coverage.md](feature-coverage.md)（按产品功能）。

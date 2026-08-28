# 影音库 AI 智能整理

个人 NAS 影视文件整理服务：扫描源目录，清洗文件名，通过 TMDB 获取元数据，按维度和路径规则分类入库。当前刮削不使用 AI；LLM 仅用于可选的源目录清理建议。

## 当前能力

- 文件监控、手动批量/单文件处理
- TMDB 主导的两级匹配：自动匹配或进入人工确认
- 电影/电视剧、类型、地区、语言、限制级年龄段等维度映射
- 源目录清理器，可选 LLM 辅助判断
- 模拟刮削预览、维度管理、回收站恢复
- 字幕关联、去重、路径规则、任务持久化
- 安全删除、路径白名单、权限检查、hooks 高级扩展
- fnOS `.fpk` 构建发布

已移除：Hermes 通知/Skill、AI 刮削、AI 维度判断、旧 scraper/storage 兼容层。

## 快速开始

环境要求：Python 3.12.13、SQLite、YAML 配置。开发环境优先使用项目 `.venv/`。

```bash
./scripts/bootstrap_python_env.sh
source .venv/bin/activate

# 启动开发服务，访问 http://127.0.0.1:9855
PYTHONPATH="${PWD}" python -m media_importer.media_importer \
  -c config/config.yaml serve -p 9855 --host 0.0.0.0

# 或
./start.sh
```

首次使用：

1. 复制或准备 `config/config.yaml`。
2. 设置 `source_dir`、`temp_dir`、路径规则和 TMDB 配置。
3. 启动服务，先使用模拟器或单文件处理验证路径规则。
4. 生产发布前运行测试和 `deploy/build_fpk.sh`。

## 配置要点

配置模板：`config.yaml.example`。运行配置：`config/config.yaml`。

| 配置块 | 用途 |
|--------|------|
| `source_dir` / `temp_dir` | 源目录与临时目录 |
| `path_rules` | 根据维度生成入库路径 |
| `metadata` | TMDB Provider 配置 |
| `manual_review` | AUTO_PASS 任务是否强制人工确认 |
| `file_watcher` | 是否启用源目录轮询监控 |
| `source_cleaner` | 源目录清理策略 |
| `llm` | 清理器 LLM 连接，可不配置 |
| `hooks` | 高级用户脚本钩子，必须使用绝对路径和白名单目录 |

LLM 只服务源目录清理器。API Key 返回前端时会脱敏；没有 LLM 配置时清理器仍可使用规则模式。

## 处理流程

```text
扫描 → 复制到 temp → TMDB 搜索 → 匹配判定
                         ├─ AUTO_PASS → 分类 → 去重 → 命名 → 入库
                         └─ NEEDS_CONFIRM → 人工检索/编辑 → 入库
```

任务状态由 `status`、`stage`、`file_location` 共同表达。状态转换唯一事实源是 `media_importer/features/tasks/transitions.py`，支持 CAS 并发保护和 temp checkpoint 续跑。

## 测试与质量检查

```bash
# 全量测试（UI 测试需要本地服务和浏览器）
.venv/bin/python -m pytest tests/

# 非 UI 测试
.venv/bin/python -m pytest tests/ \
  --ignore=tests/test_ai_config_ui.py \
  --ignore=tests/test_cinema_ui_smoke.py \
  --ignore=tests/test_scrape_ui.py \
  --ignore=tests/test_frontend_recycle.py \
  --ignore=tests/test_scrape_preview_ui.py \
  --ignore=tests/test_e2e_cinema_workflow.py

# 架构护栏
.venv/bin/python -m pytest tests/test_architecture_guards.py

# 文档检查
python3 scripts/check_docs.py

# Python lint（新改文件必须通过）
.venv/bin/ruff check <改动文件>
```

## fnOS 发布

```bash
./deploy/build_fpk.sh <version>
```

构建脚本从根源码生成 package workspace，不直接把 `deploy/nas-media-importer/` 当作开发源。详细说明见 [`deploy/README.md`](deploy/README.md) 和 [`docs/architecture/deployment-fnos.md`](docs/architecture/deployment-fnos.md)。

## 文档与开发流程

AI 或开发者先读 [`AGENTS.md`](AGENTS.md)，再读 [`docs/ai-map.md`](docs/ai-map.md)。

中改及以上流程：

```text
需求看板 → proposal → ADR（架构级）→ plan（含测试计划）
→ 实施与测试 → 验收 → completed-items → 归档
```

文档入口：

- [`docs/README.md`](docs/README.md)：文档目录
- [`docs/ai-map.md`](docs/ai-map.md)：任务到代码、测试、文档映射
- [`docs/features/`](docs/features/)：业务功能事实
- [`docs/architecture/`](docs/architecture/)：当前架构事实
- [`docs/standards/`](docs/standards/)：长期规范和行为契约
- [`docs/testing/`](docs/testing/)：测试策略与矩阵
- [`docs/tracking/requirements-board.md`](docs/tracking/requirements-board.md)：需求看板

## 安全边界

- 影视文件不得直接 `os.remove()`，删除和覆盖必须走回收站。
- 文件操作必须限制在允许目录，禁止路径穿越。
- 临时文件只允许在明确的 temp 或 `.tmp`/`.copying` 边界直接清理。
- 配置密钥不得明文返回 API 响应。

完整规则见 [`docs/standards/safety.md`](docs/standards/safety.md)。

## 项目结构

```text
media_importer/
├── media_importer.py       # CLI 入口
├── api/                    # HTTP API
├── core/                   # 配置、DB、任务、日志兼容层
├── features/               # 业务功能事实源
├── infrastructure/         # DB、文件系统、LLM 基础能力
├── monitor/                # 文件监控与权限检查
├── notify/                 # hooks 高级扩展
└── webui/                  # 原生 HTML/CSS/JS 前端
```

当前路线图：[`docs/_archive/2026-08-27-simplification-complete/2026-08-22-simplification-roadmap.md（已归档）`（已归档）](docs/_archive/2026-08-27-simplification-complete/2026-08-22-simplification-roadmap.md)。

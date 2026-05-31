# 影音库AI智能整理

## 项目概述

自动扫描源目录视频文件，通过 AI+TMDB 刮削元数据，按规则分类入库。运行在飞牛 fnOS NAS 上，提供 Web UI 管理界面。

**完整文档入口**：[docs/系统架构总览.md](docs/系统架构总览.md)

## 开发命令

```bash
# 安装依赖
pip install -r requirements.txt

# 启动开发服务（端口默认 9855）
PYTHONPATH="${PWD}" python3 -m media_importer.media_importer -c config/config.yaml serve -p 9855 --host 0.0.0.0
# 或用封装脚本
./start.sh [config] [host] [port]

# 运行全部测试（需要服务先启动，因为包含 Playwright 端到端测试）
pytest tests/

# 运行单个测试文件
pytest tests/test_sqlite_refactor.py

# 只跑非 UI 的单元测试（跳过 Playwright 测试）
pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
```

- 没有 `pyproject.toml`，没有 lint/formatter/typecheck 工具配置。本项目使用 pytest，但没有 `conftest.py` 或 pytest 配置文件。
- Playwright UI 测试需要 `playwright` 模块和浏览器二进制（`python3 -m playwright install chromium`）。Playwright 测试依赖本地运行的服务，端口 9855。
- 许多测试已知存在失败（见 `.pytest_cache/v/cache/lastfailed`），修改前先确认哪些测试已坏。

## 目录结构

```
nas_media_manage/
├── media_importer/          # 后端 Python 包（唯一源码目录）
│   ├── media_importer.py    # CLI 入口：scan / serve / process 子命令
│   ├── core/                # db / config / logger / metrics / safety
│   ├── scraper/             # providers / llm_scraper / confidence_engine / dimension_manager
│   ├── storage/             # scanner / copier / mover / analyzer / dedup / classifier
│   ├── pipeline/            # runner / steps / confirm
│   ├── api/                 # HTTP API（handler.py 路由 + Mixin 组合）
│   ├── notify/              # hermes_hook / hooks
│   ├── monitor/             # file_watcher / permission_checker
│   └── webui/               # 前端（index.html + js/ + css/，原生 JS，无构建）
├── config/                  # 本地开发配置（config/config.yaml gitignored）
├── deploy/                  # fnOS 部署目录，手动同步，AI 不自动执行
│   └── nas-media-importer/  # 内含 media_importer 副本，与根目录独立
├── docs/                    # 架构 / 规范 / 方案 / 计划
├── tests/                   # 测试文件
└── data/                    # SQLite 数据目录（gitignored）
```

## 导入规范

- 跨子包导入：`from media_importer.core.db import ...`
- 同子包内相对导入：`from .utils import ...`
- `PYTHONPATH` 必须包含项目根目录，否则跨子包导入会失败

## 代码风格

- 不加注释，代码自解释
- CSS 使用变量体系：`var(--text-primary)`，不硬编码颜色值
- 前端 JS 按功能拆模块：api / config / tasks / path-rules / prompts / dimensions / app

## 关键架构决策

| 决策 | 选择 | 原因 |
|------|------|------|
| API 架构 | Mixin 组合模式 | 路由集中在 handler.py，逻辑分散在 Mixin |
| 数据库 | SQLite + JSON 字段 | 轻量，刮削结果灵活存储 |
| 前端 | 原生 JS + CSS 变量 | 无构建依赖，NAS 环境友好 |
| 配置格式 | YAML + 自动迁移 | 人类可读，向后兼容 |

## 安全规则（必须遵守）

- 所有删除/覆盖影视文件必须通过 `move_to_recycle()` 移入回收站，禁止直接 `os.remove()`
- 临时文件（`.tmp` / `.copying`）可直接删除
- 源文件清理受 `cleanup_mode` 门控：read_only / smart_cleanup / full_cleanup
- 敏感配置项（api_key / secret）返回前端时脱敏为 `***`

## 配置变更

- 配置键变更必须在 `core/config_loader.py` 添加自动迁移逻辑
- 新增配置项需同步：config_loader -> config_validator -> config_handlers -> 前端

## 任务状态变更

- 新增状态需全链路更新：constants.py -> task_manager.py -> pipeline/ -> api/ -> 前端
- `file_location` 追踪文件当前位置，必须与状态保持一致

## API 规范

- 路由注册在 `api/handler.py`，处理逻辑在对应 Mixin 中
- 统一 JSON 响应格式：`{code, status, message, data}`
- 新增端点需同步更新 `docs/规范/接口规范.md`

## 测试规范

- 三层结构：单元测试（unittest）-> 集成测试（unittest + urllib）-> 前端测试（Playwright）
- 命名：单元 `test_<模块>.py`，集成 `test_integration_<功能>.py`，前端 `test_frontend_<功能>.py`
- 测试执行顺序：先单元 -> 再集成 -> 最后前端

## 文档规范

- docs 目录分类型：架构/规范/方案/计划；文档命名用中文
- 新功能开发必须先写方案到 `docs/方案/`，实施后回写文档
- 方案文档标记状态：✅ 已实施 / 🔄 进行中 / 📋 待评审
- 文档边界：各自有明确职责，不重复描述，通过链接引用

## 部署

```bash
python3 -m media_importer.media_importer -c <config> serve -p <port> --host <host>
```

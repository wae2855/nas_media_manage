# NAS 影视自动化入库系统 - 项目上下文

## 项目概述

NAS 影视自动化入库系统，用于自动扫描源目录中的视频文件，通过 AI 刮削元数据（标题/年份/类型/季集等），按规则分类并入库到目标目录。运行在飞牛 NAS (fnOS) 上，提供 Web UI 管理界面。

## 目录结构

```
nas_media_manage/
├── media_importer/              # 后端 Python 包
│   ├── api_server.py            # HTTP API 服务器（内置静态文件服务）
│   ├── pipeline.py              # 任务处理流水线（10 步骤）
│   ├── task_manager.py          # 任务 CRUD + 状态管理
│   ├── db.py                    # SQLite 数据库层
│   ├── file_scanner.py          # 源目录扫描 + 去重过滤
│   ├── file_copier.py           # 文件复制到中转目录
│   ├── llm_scraper.py           # AI 刮削（OpenAI/Azure）
│   ├── classifier.py            # 维度匹配路径规则
│   ├── dedup_checker.py         # 入库同名检测
│   ├── file_mover.py            # 文件移动/重命名/清理
│   ├── config_loader.py         # 配置加载 + 迁移 + 校验
│   ├── config_validator.py      # 配置完整性验证
│   ├── file_watcher.py          # 轮询监控源目录
│   ├── hermes_hook.py           # Hermes 通知集成
│   ├── hooks.py                 # 钩子脚本执行
│   ├── safety.py                # 安全删除/路径校验
│   ├── logger.py                # 日志系统
│   ├── metrics.py               # 指标收集
│   ├── permission_checker.py    # 路径权限检测
│   ├── cloud_refresher.py       # 云盘刷新
│   ├── media_importer.py        # 入口主程序
│   └── webui/                   # 前端
│       ├── index.html           # 主页面
│       ├── js/
│       │   ├── api.js           # API 通信 + API Key 管理
│       │   ├── config.js        # 配置面板加载/保存/校验
│       │   ├── tasks.js         # 任务列表/操作/详情弹窗
│       │   ├── path-rules.js    # 入库规则卡片/拖拽
│       │   ├── prompts.js       # 提示词编辑/预览
│       │   └── app.js           # 入口：概览页、初始化
│       └── css/
│           ├── base.css         # CSS 变量/重置/基础
│           ├── layout.css       # 配置面板布局/表单
│           ├── components.css   # 权限检测/规则卡片
│           ├── config.css       # 提示词编辑器/说明面板
│           └── tasks.css        # 任务列表/状态/弹窗
├── deploy/                      # 部署目录（与源文件保持同步）
│   └── nas-media-importer/app/server/
│       ├── media_importer/      # 与源 media_importer/ 同步
│       ├── tests/               # 测试文件
│       ├── config/              # 运行时配置目录
│       └── config.yaml.example  # 配置模板
├── docs/                        # 项目文档
├── config.yaml.example          # 配置模板（源）
└── .trae/skills/                # 项目级 Skill
```

## 任务状态机

```
VALID_STATUSES = ["PENDING", "PROCESSING", "SUCCESS", "FAILED", "SKIPPED",
                  "CONFIRMING", "NEEDS_REVIEW", "ROLLBACK", "DUPLICATE_REVIEW"]
```

状态流转：
- PENDING → PROCESSING（开始处理）
- PROCESSING → SUCCESS（成功）/ FAILED（失败）/ SKIPPED（跳过）/ CONFIRMING（需人工确认）
- CONFIRMING → SUCCESS（确认入库）/ ROLLBACK（回退）
- FAILED/NEEDS_REVIEW → PENDING（重试）
- DUPLICATE_REVIEW → PENDING→PROCESSING→SUCCESS（覆盖入库）/ SKIPPED（忽略→隔离区）
- 任何状态 → NEEDS_REVIEW（移入隔离区后）

## 流水线步骤

PIPELINE_STEPS = scan → copy → scrape → validate → classify → dedup → rename → import → notify → record

## 配置键映射

| 配置键 | 说明 | 子键 |
|--------|------|------|
| `source_dir` | 源目录路径 | - |
| `temp_dir` | 中转目录路径 | - |
| `log_dir` | 日志目录路径 | - |
| `source_policy` | 源文件策略 | dedup_enabled, quarantine_dir, max_auto_retries, scan_recursive, scan_max_depth |
| `duplicate_handling` | 入库同名处理 | enabled, strategy(skip/replace/rename/quality) |
| `manual_review` | 人工检查 | enabled |
| `llm` | AI 刮削配置 | provider, api_key, base_url, model, fallback_model, timeout, max_retries, retry_delay, confidence_threshold, verify_ssl |
| `file_watcher` | 轮询监控 | enabled, poll_interval, ignore_patterns |
| `hermes` | 通知 | enabled, webhook.{base_url, route_name, secret, timeout, max_retries, retry_delay, verify_ssl, events} |
| `path_rules` | 入库规则 | [{conditions, template}] |
| `filename_templates` | 文件名模板 | movie, tv, subtitle |
| `dimensions` | AI 维度定义 | [{name, label, values, ai_prompt}] |
| `server` | API 服务 | host, port, api_key |
| `task_queue` | 任务队列 | max_concurrent |

### 配置迁移（config_loader.py 自动处理）

- `source_dedup` → `source_policy`（enabled → dedup_enabled）
- `source_dir_scan` → `source_policy`（recursive → scan_recursive, max_depth → scan_max_depth）
- `source_file_handling` → 已移除（删除后处理为默认行为）

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/tasks | 任务列表（分页+状态筛选） |
| GET | /api/tasks/{id} | 任务详情 |
| POST | /api/tasks/{id}/retry | 重试任务 |
| POST | /api/tasks/{id}/confirm | 确认入库 |
| POST | /api/tasks/{id}/reclassify | 重新分类 |
| POST | /api/tasks/{id}/rollback | 回退到源目录 |
| POST | /api/tasks/{id}/ignore | 忽略任务 |
| POST | /api/tasks/{id}/duplicate-review | 重复文件确认（override/ignore） |
| GET | /api/tasks/{id}/subtitles | 字幕详情 |
| POST | /api/tasks/confirm-all | 批量确认 |
| GET | /api/tasks/stats | 任务统计 |
| GET | /api/config | 获取配置 |
| POST | /api/config | 保存配置 |
| GET | /api/config/validate | 验证配置 |
| POST | /api/config/test-llm | 测试 LLM 连通性 |
| POST | /api/config/test-hermes | 测试 Hermes 通知 |
| POST | /api/config/check-permission | 检查路径权限 |
| POST | /api/config/save-prompts | 保存提示词 |
| POST | /api/config/reset-prompts | 重置提示词 |
| POST | /api/path/test | 测试单个路径权限 |
| POST | /api/batch/run | 启动批量扫描 |
| POST | /api/batch/run-file | 处理单个文件 |
| POST | /api/queue/pause | 暂停队列 |
| POST | /api/queue/resume | 恢复队列 |
| GET | /api/queue/status | 队列状态 |
| POST | /api/restart | 重启服务 |
| GET | /api/health | 健康检查 |
| GET | /api/logs | 获取日志 |
| GET | /api/skill | 获取 Hermes SKILL.md |
| GET | /api/skills | 技能列表 |

## 数据库表

### tasks 表
核心字段：task_id, source_path, source_filename, file_size_mb, status, retry_count, scrape_result, scrape_dimensions, import_path, final_filename, video_path, confirm_status, skip_reason, error_message

### task_subtitles 表
核心字段：task_id, source_path, source_filename, target_path, lang, status, import_path, confirm_status

## 开发约定

1. **后端改动需同步 deploy 目录**：源文件在 `media_importer/`，部署文件在 `deploy/nas-media-importer/app/server/media_importer/`
2. **配置键变更需处理迁移**：在 `config_loader.py` 的 `load_config()` 中添加自动迁移逻辑
3. **新增状态需全链路更新**：db.py → task_manager.py → pipeline.py → api_server.py → 前端（tasks.js + tasks.css + index.html）
4. **测试文件在 deploy 目录**：`deploy/nas-media-importer/app/server/tests/`
5. **前端模块化**：JS 按 api/config/tasks/path-rules/prompts/app 拆分，CSS 按 base/layout/components/config/tasks 拆分
6. **CSS 变量体系**：使用 `var(--text-primary)` 等变量，不硬编码颜色值
7. **静态文件路由**：api_server.py 支持 `/css/*` 和 `/js/*` 子目录，带路径遍历安全检查

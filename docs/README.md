# NAS影视自动化入库系统 — 文档索引

## 文档结构

| 序号 | 文档 | 用途 | 受众 |
|------|------|------|------|
| [01](01-requirements.md) | 需求文档 | 问题定义、方案讨论、关键决策 | 所有人 |
| [02](02-design.md) | 方案设计 | 功能规格、架构设计、API定义 | 开发人员 |
| [03](03-development-plan.md) | 开发计划 | 每个模块的详细实现方案 | 开发人员 |
| [05](05-checklist.md) | 验收清单 | 每个阶段的验收条件 | QA/开发 |
| [06](06-test-guide.md) | 测试指南 | 测试环境准备和步骤 | 开发人员 |
| [07](07-hermes-integration-guide.md) | Hermes集成指南 | 飞书通知和Skill配置 | 运维人员 |
| [FNOS](fnos-deploy-guide.md) | FNOS部署指南 | 飞牛NAS安装部署 | 运维人员 |
| [安全](SECURITY_AUDIT_REPORT.md) | 安全审计报告 | 安全漏洞和修复建议 | 安全/开发 |

## 文档关系

```
01-requirements（需求）
      ↓
02-design（方案）
      ↓
03-development-plan（计划）
      ↓
05-checklist（验收）
      ↓
06-test-guide（测试）

07-hermes-integration-guide（Hermes集成）  ← 独立
fnos-deploy-guide（FNOS部署）              ← 独立
SECURITY_AUDIT_REPORT（安全审计）          ← 独立
```

## 模块说明

### 核心模块

| 模块 | 文件 | 功能 |
|------|------|------|
| API服务 | `api_server.py` | ThreadingHTTPServer，RESTful API，Web UI托管 |
| 流水线 | `pipeline.py` | 10步处理流程编排：扫描→复制→刮削→校验→分类→去重→命名→入库→通知→记录 |
| 分类引擎 | `classifier.py` | 维度条件匹配+路径规则，支持布尔值/字符串兼容比较 |
| AI刮削 | `llm_scraper.py` | LLM API调用，主模型+备选模型自动降级，重试机制 |
| 配置管理 | `config_loader.py` | YAML配置加载，布尔值归一化，维度值验证 |
| 配置验证 | `config_validator.py` | 配置有效性检查，LLM/Hermes连通性测试 |
| 安全模块 | `safety.py` | 路径穿越防护，安全删除，文件类型白名单，目录操作白名单 |
| 文件操作 | `file_mover.py` | 文件移动/重命名，附属文件清理，空目录递归删除 |
| 文件扫描 | `file_scanner.py` | 源目录扫描，视频+字幕自动分组 |
| 去重检测 | `dedup_checker.py` | 4种策略：skip/replace/rename/quality |
| 任务管理 | `task_manager.py` | 任务CRUD，状态持久化，倒序排列 |
| 日志管理 | `logger.py` | 文件+控制台+内存缓冲，线程安全，支持任务级追踪 |
| 通知 | `hermes_hook.py` | Hermes Webhook，HMAC签名，SSL可配置 |
| 钩子 | `hooks.py` | 处理前后自定义命令执行 |
| 文件监控 | `file_watcher.py` | 轮询扫描源目录，可配置间隔 |

### Web UI

| 文件 | 功能 |
|------|------|
| `webui/index.html` | 主页面，概览+配置+任务三个面板 |
| `webui/app.js` | 前端逻辑，API调用，实时日志，配置管理 |
| `webui/styles.css` | 暗色主题样式，响应式布局 |

### 处理流程

```
①扫描(source) → ②复制(copy) → ③刮削(scrape/AI) → ④校验(validate)
→ ⑤分类(classify) → ⑥同名检测(dedup) → ⑦命名(rename) → ⑧入库(import)
→ ⑨通知(notify) → ⑩记录(record)
```

### 分类匹配机制

1. AI返回维度值（如 `media_type=tv, restricted=True`）
2. `classifier.py` 的 `match_conditions` 将布尔值与字符串兼容比较（`True` 匹配 `'yes'`/`'true'`）
3. 按顺序匹配 `path_rules`，第一个匹配的规则生效
4. 无匹配则任务失败，日志输出文件维度和所有可用规则

### 源文件处理

- 删除模式：视频+字幕+同名附属文件（.nfo/.jpg等）一并删除，空目录递归清理
- 保留模式：源文件保留，但每次轮询会重新处理失败文件（消耗AI Token）
- 仅 `video_extensions` 和 `subtitle_extensions` 中的文件进入处理流程

### 配置项顺序

1. 轮询监控 → 2. 基础配置 → 3. 入库规则 → 4. 文件名模板 → 5. 同名文件
→ 6. 源文件处理 → 7. LLM → 8. Hermes → 9. 任务队列

## 快速链接

- [项目根目录](..)
- [配置模板](../config.yaml.example)
- [测试数据](../tests/fixtures/source/)
- [初始化测试环境](../init_test_env.sh)

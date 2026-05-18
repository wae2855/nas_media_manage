# NAS影视自动化入库系统

## 1. 项目简介

NAS影视自动化入库系统是一个轻量级的影视文件智能处理服务。它监控下载目录中的新文件，通过AI大模型自动刮削影视元数据（标题、年份、类型、季集等），按分类规则将影视文件重命名并移动到对应的入库目录，同时支持Hermes飞书通知和Skill交互。整个处理流程为10步流水线，从扫描到入库全自动完成，无需人工干预。

## 2. 系统架构

系统采用10步流水线处理每个影视文件：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        10-Step Pipeline                             │
│                                                                     │
│  ①扫描 ──▶ ②复制 ──▶ ③刮削 ──▶ ④校验 ──▶ ⑤分类 ──▶              │
│  source    copy     AI LLM    validate  classify                   │
│                                                                     │
│  ──▶ ⑥同名检测 ──▶ ⑦命名 ──▶ ⑧入库 ──▶ ⑨通知 ──▶ ⑩记录        │
│      dedup        rename     import     notify     record          │
└─────────────────────────────────────────────────────────────────────┘

外部组件:
  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ FileWatcher │    │  LLM API  │    │  Hermes   │
  │ (文件监控)   │    │ (AI刮削)   │    │ (飞书通知) │
  └──────┬───┘    └─────┬────┘    └─────┬────┘
         │              │               │
         ▼              ▼               ▼
  ┌──────────────────────────────────────────┐
  │            HTTP API Server (:9855)        │
  └──────────────────────────────────────────┘
```

## 3. 功能特性

- **AI智能刮削** — 基于大模型API自动识别影视元数据，支持主模型+备选模型自动降级
- **自动分类入库** — 按电影/电视剧/纪录片/限制级等维度匹配路径规则，自动归类
- **文件名规范化** — 按模板重命名，统一命名风格（如 `绝命毒师.Breaking.Bad.2008.S01E02.720p.BluRay.mkv`）
- **文件监控** — 轮询检测下载目录新文件，发现即处理
- **字幕自动关联** — 自动识别并关联同名字幕文件一起入库
- **同名文件检测** — 跳过/重命名策略，避免覆盖已有文件
- **Hermes集成** — Webhook通知推送至飞书，支持Skill对话式管理
- **安全防护** — 路径穿越防护、文件类型白名单、目录操作白名单、权限预检查
- **任务持久化** — 任务状态落盘，服务重启不丢失
- **轻量设计** — 仅依赖 `pyyaml`，Python 3.9+ 即可运行

## 4. 部署指南

### 4.1 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | FNOS / Linux（systemd） |
| Python | 3.9+ |
| 依赖 | pyyaml >= 6.0 |
| 网络 | 需访问LLM API（如 MiniMax / OpenAI） |

### 4.2 快速部署

#### FNOS 用户（推荐）

下载 `.fpk` 安装包，在飞牛应用中心点击「手动安装」即可。

> 如果应用中心没有上架，可使用下面的通用安装方式。

#### 通用 Linux 安装（Root 用户）

```bash
# 1. SSH 登录服务器，以 root 用户运行
sudo -i
cd /opt

# 2. 克隆或上传代码
git clone https://github.com/wae2855/nas_media_manage.git
# 或: scp -r nas_media_manage/ root@nas:/opt/nas-media-importer

# 3. 运行安装脚本
cd nas-media-importer
bash deploy/install.sh
```

#### 非 Root 用户 / 普通 Linux

```bash
# 以普通用户运行
bash -c "$(curl -fsSL https://raw.githubusercontent.com/wae2855/nas_media_manage/main/deploy/install-user.sh)"
```

安装脚本会自动：创建Python虚拟环境 → 安装依赖 → 注册服务 → 启动服务。

#### 配置文件位置

| 文件 | 路径 |
|------|------|
| 配置文件 | `/opt/nas-media-importer/config/config.yaml` |
| 数据文件 | `/opt/nas-media-importer/data/tasks.json` |
| 日志文件 | `/opt/nas-media-importer/logs/` |

> **升级说明**：配置文件和数据目录独立于代码目录，升级时不会丢失。

### 4.3 详细部署步骤

#### 代码上传方式

**方式一：scp上传（推荐）**
```bash
scp -r nas_media_manage/ root@nas:/opt/nas-media-importer
```

**方式二：git clone**
```bash
ssh root@nas 'git clone https://github.com/wae2855/nas_media_manage.git /opt/nas-media-importer'
```

**方式三：FNOS文件管理器**

通过FNOS Web界面的文件管理器直接上传代码压缩包并解压到 `/opt/nas-media-importer`。

#### 安装依赖

安装脚本会自动创建虚拟环境并安装依赖。如需手动安装：

```bash
cd /opt/nas-media-importer
python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet pyyaml
```

#### 配置说明

首次启动时，如配置文件不存在会自动生成默认模板。编辑配置文件：

**配置文件路径：** `/opt/nas-media-importer/config/config.yaml`

**必须配置的项（标记 ⚠️）：**

```yaml
# ⚠️ 下载目录 — 影视文件来源
source_dir: "/vol1/网盘下载"

# ⚠️ 临时目录 — 处理过程中的中转目录
temp_dir: "/vol1/tmp/media_import"

# ⚠️ 日志目录
log_dir: "/vol1/logs/media_import"

# ⚠️ 入库目标路径 — path_rules 中的 template 必须改为实际路径
path_rules:
  - conditions:
      media_type: "tv"
      documentary: "no"
      restricted: "no"
    template: "/vol1/影视/电视剧/{title_cn} ({year})/Season {season}/"
  - conditions:
      media_type: "movie"
      documentary: "no"
      restricted: "no"
    template: "/vol1/影视/电影/{year}/"
  # ... 更多规则见 config.yaml

# ⚠️ AI刮削API密钥 — 必须填写有效的API Key
llm:
  api_key: "sk-your-actual-api-key"
  base_url: "https://api.minimaxi.com/v1"
  model: "MiniMax-M2.5"
```

**有合理默认值的项：**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `server.host` | `0.0.0.0` | API监听地址 |
| `server.port` | `9855` | API监听端口 |
| `file_watcher.enabled` | `true` | 文件监控开关 |
| `file_watcher.poll_interval` | `10` | 监控轮询间隔（秒） |
| `duplicate_handling.strategy` | `skip` | 同名文件策略 |
| `task_queue.max_concurrent` | `1` | 最大并发任务数 |
| `logging.level` | `INFO` | 日志级别 |
| `hermes.enabled` | `false` | Hermes通知默认关闭 |

#### 启动服务

**方式一：systemd（生产环境推荐）**
```bash
bash deploy/install.sh
```

**方式二：启动脚本**
```bash
./start.sh
```

**方式三：直接运行**
```bash
python3 media_importer/media_importer.py -c media_importer/config.yaml serve -p 9855 --host 0.0.0.0
```

#### 验证服务

```bash
# 健康检查
curl -s http://127.0.0.1:9855/api/health | python3 -m json.tool

# 预期返回:
# {
#   "code": 200,
#   "data": {
#     "status": "ok",
#     "checks": {
#       "source_dir": "ok",
#       "temp_dir": "ok",
#       "llm_api": "ok",
#       "hermes": "disabled",
#       "disk_space": "ok"
#     }
#   }
# }
```

### 4.4 systemd服务管理

```bash
# 查看服务状态
systemctl status nas-media-importer

# 查看实时日志
journalctl -u nas-media-importer -f

# 停止服务
systemctl stop nas-media-importer

# 重启服务
systemctl restart nas-media-importer

# 重新加载配置（不重启服务）
curl -X POST http://127.0.0.1:9855/api/config/reload
```

### 4.3 升级更新

```bash
# 进入安装目录
cd /opt/nas-media-importer

# 方式一：使用安装脚本（推荐，自动处理）
sudo bash deploy/install.sh upgrade

# 方式二：手动升级
sudo systemctl stop nas-media-importer
git pull
sudo systemctl start nas-media-importer
```

> **升级不会丢失配置和数据** — 配置文件和数据目录独立于代码目录。

## 5. 配置说明

详细配置项请参考 `media_importer/config.yaml` 中的注释。以下为**必须配置**的项目：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `source_dir` | 下载目录，影视文件来源 | `/vol1/网盘下载` |
| `path_rules.*.template` | 入库目标路径模板 | `/vol1/影视/电视剧/{title_cn} ({year})/Season {season}/` |
| `llm.api_key` | AI刮削API密钥 | `sk-xxxxx` |
| `llm.base_url` | LLM API地址 | `https://api.minimaxi.com/v1` |
| `llm.model` | 使用的模型名称 | `MiniMax-M2.5` |
| `temp_dir` | 临时中转目录 | `/vol1/tmp/media_import` |
| `log_dir` | 日志目录 | `/vol1/logs/media_import` |

**可选但推荐配置：**

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `hermes.webhook.base_url` | Hermes通知地址 | `http://10.200.200.6:8644` |
| `hermes.webhook.secret` | HMAC签名密钥 | `KsMEsyjo...` |
| `hermes.webhook.route_name` | Webhook路由名 | `media-normalize` |

路径模板支持的变量：`{title_cn}` `{title_en}` `{year}` `{season}` `{episode}` `{resolution}` `{quality}` `{ext}`

## 6. 使用方式

### 6.1 自动模式（文件监控）

当 `file_watcher.enabled: true` 时，系统自动轮询 `source_dir`，发现新文件后自动触发处理流水线。无需任何操作，下载完成的影视文件会被自动刮削、分类、入库。

```yaml
file_watcher:
  enabled: true
  poll_interval: 10    # 每10秒扫描一次
```

### 6.2 手动触发

**API方式：**

```bash
# 触发批量处理（扫描source_dir中所有待处理文件）
curl -X POST http://localhost:9855/api/run

# 处理指定文件
curl -X POST http://localhost:9855/api/run/file \
  -H "Content-Type: application/json" \
  -d '{"path": "/vol1/网盘下载/Inception.2010.1080p.mkv"}'
```

**CLI方式：**

```bash
# 执行一次批量处理
python3 media_importer/media_importer.py -c media_importer/config.yaml run

# 仅扫描不处理（dry-run）
python3 media_importer/media_importer.py -c media_importer/config.yaml run --dry-run

# 查看任务列表
python3 media_importer/media_importer.py -c media_importer/config.yaml list --status all

# 查看任务详情
python3 media_importer/media_importer.py -c media_importer/config.yaml show <task_id>

# 重试失败任务
python3 media_importer/media_importer.py -c media_importer/config.yaml retry <task_id>
python3 media_importer/media_importer.py -c media_importer/config.yaml retry  # 重试所有

# 查看队列状态
python3 media_importer/media_importer.py -c media_importer/config.yaml queue

# 查看日志
python3 media_importer/media_importer.py -c media_importer/config.yaml log -f --tail 50

# 健康检查
python3 media_importer/media_importer.py -c media_importer/config.yaml health

# 运行指标
python3 media_importer/media_importer.py -c media_importer/config.yaml metrics
```

### 6.3 Hermes Skill（AI助手交互）

通过Hermes Skill可以在飞书对话中管理入库系统。配置方法详见 [Hermes集成指南](docs/07-hermes-integration-guide.md)。

配置完成后，可在飞书中对话操作：

- "查一下入库任务状态"
- "重试失败的任务"
- "跑一批新的"
- "系统健康吗"

## 7. API参考

默认监听地址：`http://0.0.0.0:9855`

### 系统管理

| 方法 | 端点 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/health` | 健康检查 | - |
| GET | `/api/metrics` | 运行指标统计 | - |
| GET | `/api/config` | 获取当前配置（敏感信息已脱敏） | - |
| POST | `/api/config/reload` | 重新加载配置文件 | - |

### 任务管理

| 方法 | 端点 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/tasks` | 任务列表 | `status`, `limit`, `offset`, `all`, `format` |
| GET | `/api/tasks/{id}` | 任务详情 | - |
| DELETE | `/api/tasks/{id}` | 删除任务 | - |
| POST | `/api/tasks/{id}/retry` | 重试指定任务 | - |
| POST | `/api/tasks/clear` | 清空任务 | `{"status": "failed\|all"}` |

### 队列控制

| 方法 | 端点 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/queue/status` | 队列状态 | - |
| POST | `/api/queue/pause` | 暂停队列 | - |
| POST | `/api/queue/resume` | 恢复队列 | - |
| POST | `/api/queue/retry-all` | 重试所有失败任务 | - |

### 处理触发

| 方法 | 端点 | 说明 | 参数 |
|------|------|------|------|
| POST | `/api/run` | 触发批量处理 | - |
| POST | `/api/run/file` | 处理指定文件 | `{"path": "/path/to/file.mkv"}` |

### 文件监控

| 方法 | 端点 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/watcher/status` | 监控状态 | - |
| POST | `/api/watcher/control` | 监控控制 | `action=pause\|resume\|status` |

### 日志查询

| 方法 | 端点 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/logs` | 查询日志 | `limit`, `task_id` |

### 响应格式

所有API返回统一JSON格式：

```json
{
  "code": 200,
  "status": "success",
  "message": "操作描述",
  "data": { ... }
}
```

### 任务状态流转

```
PENDING → PROCESSING → SUCCESS
                     → FAILED → (retry) → PENDING
                     → SKIPPED
```

## 8. 目录结构

```
nas_media_manage/
├── start.sh                             # 前台启动脚本
├── requirements.txt                     # Python依赖
├── config.yaml.example                   # 配置模板（首次安装时复制）
├── config/                              # 用户配置（升级时保留，.gitignore）
│   └── config.yaml
├── data/                                # 数据目录（升级时保留，.gitignore）
│   └── tasks.json
├── logs/                                # 日志目录（升级时保留，.gitignore）
├── deploy/
│   ├── install.sh                       # Root用户安装脚本
│   ├── install-user.sh                  # 非Root用户安装脚本
│   ├── nas-media-importer.service       # systemd服务文件
│   └── fnpack/                          # FNOS fpk 打包配置
├── docs/
│   ├── 01-requirements.md               # 需求文档
│   ├── 02-design.md                     # 设计文档
│   ├── 03-development-plan.md           # 开发计划
│   ├── 05-checklist.md                  # 检查清单
│   ├── 06-test-guide.md                  # 测试指南
│   └── 07-hermes-integration-guide.md   # Hermes集成指南
└── media_importer/                      # 程序代码
    ├── api_server.py                    # HTTP API服务
    ├── classifier.py                    # 分类匹配引擎
    ├── config_loader.py                 # 配置加载与校验
    ├── dedup_checker.py                 # 同名文件检测
    ├── file_copier.py                   # 文件复制（含进度回调）
    ├── file_mover.py                    # 文件移动与重命名
    ├── file_scanner.py                  # 文件扫描
    ├── file_watcher.py                  # 文件监控（轮询）
    ├── hermes_hook.py                   # Hermes Webhook通知
    ├── hooks.py                         # 钩子系统
    ├── llm_scraper.py                   # AI刮削引擎
    ├── logger.py                        # 日志管理
    ├── media_importer.py                # 主入口（CLI + serve）
    ├── metrics.py                       # 运行指标统计
    ├── pipeline.py                      # 10步流水线编排
    ├── safety.py                        # 安全模块
    └── task_manager.py                  # 任务管理（持久化）
```

## 9. 常见问题

### Q: 启动后健康检查返回 `source_dir: error`

`source_dir` 配置的目录不存在或无读取权限。请确认目录路径正确且已创建：

```bash
mkdir -p /vol1/网盘下载
```

### Q: 刮削失败，任务状态为 FAILED

常见原因：
1. **API Key无效** — 检查 `llm.api_key` 是否正确
2. **网络不通** — 确认NAS能访问LLM API地址（`llm.base_url`）
3. **模型名称错误** — 确认 `llm.model` 在对应API中可用

排查命令：
```bash
# 查看失败任务详情
curl -s "http://localhost:9855/api/tasks?status=FAILED" | python3 -m json.tool

# 查看日志
curl -s "http://localhost:9855/api/logs?limit=50" | python3 -m json.tool
```

### Q: 同名文件被跳过

这是正常行为。默认策略 `duplicate_handling.strategy: skip` 会跳过已存在的文件。如需覆盖或重命名，修改配置：

```yaml
duplicate_handling:
  strategy: "rename"   # 或 "skip"
```

### Q: 如何配置Hermes飞书通知？

详见 [Hermes集成指南](docs/07-hermes-integration-guide.md)，核心步骤：
1. 在Hermes中创建 `media-normalize` Webhook路由
2. 安装 `nas-media-importer` Skill
3. 将Hermes返回的HMAC Secret填入 `config.yaml` 的 `hermes.webhook.secret`
4. 设置 `hermes.enabled: true`

### Q: 如何修改监听端口？

修改 `config.yaml` 中的 `server.port`，或启动时指定：

```bash
python3 media_importer/media_importer.py serve -p 9090
```

### Q: 服务重启后任务会丢失吗？

不会。任务状态持久化到 `task_queue.persistence_path`（默认 `data/tasks.json`），服务重启后会自动恢复未完成的任务。

### Q: 支持哪些视频和字幕格式？

视频：`.mkv` `.mp4` `.avi` `.ts` `.mov` `.wmv` `.m2ts` `.flv`
字幕：`.srt` `.ass` `.ssa` `.vtt` `.sub`

可在 `config.yaml` 的 `video_extensions` 和 `subtitle_extensions` 中扩展。

## 10. 许可证

MIT License

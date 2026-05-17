# NAS影视自动化入库系统

一个轻量级的NAS影视文件自动化刮削和分类入库系统。

## 项目简介

本系统帮助你自动刮削下载的影视文件，通过AI大模型识别影视信息（标题、年份、类型等），按分类规则自动移动到指定入库目录，并支持通过Hermes Skill进行任务管理和飞书通知。

## 项目特性

- **AI刮削：基于大模型API自动识别影视信息
- **分类入库：按规则自动分类影视文件
- **文件监控：自动发现新下载的文件
- **Hermes集成：支持飞书通知和Skill交互
- **安全可靠：路径穿越防护、权限校验
- **轻量设计：仅需Python 3.9+ + pyyaml依赖

## 项目结构

```
nas_media_manage/
├── start.sh                            # 启动脚本
├── deploy/
│   ├── nas-media-importer.service  # systemd服务文件
│   └── install.sh                  # 部署安装脚本
├── media_importer/
│   ├── api_server.py              # HTTP API服务
│   ├── config.yaml                  # 配置文件
│   ├── config_loader.py           # 配置加载
│   ├── dedup_checker.py          # 同名检测
│   ├── file_mover.py            # 文件移动
│   ├── file_scanner.py          # 文件扫描
│   ├── file_watcher.py          # 文件监控
│   ├── hermes_hook.py           # Hermes通知
│   ├── hooks.py                # 钩子系统
│   ├── llm_scraper.py          # AI刮削引擎
│   ├── logger.py               # 日志管理
│   ├── media_importer.py        # 主入口
│   ├── metrics.py              # 指标统计
│   ├── pipeline.py            # 流水线编排
│   ├── safety.py             # 安全模块
│   └── task_manager.py          # 任务管理
└── tests/
    ├── fixtures/                # 测试数据
    ├── unit/                  # 单元测试
    └── integration/                  # 集成测试
```

## 快速开始

### 前置依赖

- Python 3.9+
- pip

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/wae2855/nas_media_manage.git
cd nas_media_manage
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置config.yaml**
```bash
cp media_importer/config.yaml
```

4. **启动服务**
```bash
./start.sh
```

5. **健康检查**
```bash
curl -s http://localhost:9855/api/health
```

## 配置说明

主要配置项（详见 [docs/01-requirements.md](docs/01-requirements.md)

### 核心配置

```yaml
server:
  host: "0.0.0.0"
  port: 9855

source_dir: "/挂载/网盘下载"
temp_dir: "/nas本地/临时目录"
log_dir: "/nas本地/日志目录"
```

### 大模型配置
```yaml
llm:
  provider: "openai"
  api_key: "your-api-key"
  base_url: "https://api.minimaxi.com/v1"
  model: "MiniMax-M2.5"
```

## 使用说明

### 启动方式

**方式1：启动脚本**
```bash
./start.sh
```

**方式2：systemd服务**
```bash
cd /path/to/nas_media_manage/deploy
./install.sh
```

**方式3：直接启动**
```bash
python3 media_importer/media_importer.py serve -p 9855
```

### CLI命令

```bash
# 运行任务
python3 media_importer.py run
python3 media_importer.py run --file "Breaking.Bad.mkv

# 查询任务
python3 media_importer.py list
python3 media_importer.py show <task_id>

# 队列操作
python3 media_importer.py retry <task_id>
python3 media_importer.py queue --pause

# 系统命令
python3 media_importer.py health
python3 media_importer.py metrics
```

### API端点

| 方法 | 端点 | 说明 |
|------|-------|
| GET | /api/health | 健康检查 |
| GET | /api/metrics | 指标统计 |
| GET | /api/config | 获取配置 |
| POST | /api/config/reload | 重载配置 |
| GET | /api/tasks | 任务列表 |
| GET | /api/tasks/{id} | 任务详情 |
| POST | /api/tasks/{id}/retry | 重试任务 |
| DELETE | /api/tasks/{id} | 删除任务 |
| POST | /api/queue/pause | 暂停队列 |
| POST | /api/queue/resume | 恢复队列 |
| POST | /api/run | 触发批量任务 |
| POST | /api/run/file | 处理指定文件 |

## 安全说明

本系统包含多重安全防护：

1. **路径穿越防护：拒绝包含`..`等非法路径
2. **文件类型限制：仅允许指定扩展名
3. **权限预检查：读写前验证权限
4. **白名单机制：限制在白名单目录内操作
5. **安全删除：不允许删除目录
6. **磁盘空间检查：操作前校验磁盘空间
7. **文件存在检查：移动前检查目标目录是否存在

## 常见问题

### 如何配置Hermes Skill?
详见 [docs/07-hermes-integration-guide.md](docs/07-hermes-integration-guide.md)

### 日志位置?
详见 [docs/02-design.md](docs/02-design.md)

### 完整文档
详见 [docs目录](docs/)

## 许可证

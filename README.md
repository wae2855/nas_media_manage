# 影音库 AI 智能整理

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)
![fnOS](https://img.shields.io/badge/fnOS-FPK-202020.svg)

面向个人 NAS 的影视文件自动整理工具。它扫描来源目录，从文件名、目录、NFO 和显式 Provider ID 中识别电影或电视剧，通过 TMDB 获取元数据，再按你配置的规则完成分类、标准命名、字幕关联和安全入库。

项目优先解决三个实际问题：下载文件名不统一、电影电视剧目录难以长期维护，以及自动整理出错时缺少人工纠正和文件安全保障。

> 当前作品身份识别由确定性规则与 TMDB Provider 完成，不使用 AI 猜测影片身份。LLM 仅作为可选的源目录清理建议能力；没有 LLM 也能使用主要功能。

## 主要功能

- **电影与电视剧识别**：支持常见发布名、中文季集表达、日期集、动漫绝对集、多集范围、NFO、TMDB/IMDb/TVDB 等显式 ID。
- **自动刮削与人工确认**：高置信结果自动继续，存在歧义时进入待确认；可搜索并手动绑定正确作品。
- **同剧批量处理**：确认一集电视剧后，可安全套用到同目录、同剧名的其他分集，同时保留每集自己的季集号。
- **多片库与规则分类**：按作品类型、地区、语言、观看分级等维度选择目标片库和相对目录。
- **标准命名**：电影、剧集和字幕分别使用可配置模板生成最终文件名，不要求保留下载时的原始名称。
- **字幕与随片文件包**：识别关联字幕，按“字幕先发布、视频最后发布”的方式提交，减少半成品入库。
- **安全传输与恢复**：来源直接写入目标侧任务暂存，执行 SHA-256 校验、no-replace 发布和中断恢复，不使用中心大文件中转目录。
- **冲突保护**：发现片库同名文件时等待用户选择保留现有、保留两份或安全替换；默认不覆盖。
- **来源处理**：入库后可保留来源、移入本地回收站，或在显式启用高风险模式后受控永久删除。
- **任务工作台**：提供扫描、队列、真实文件进度、失败重试、批量重新识别、回收站和响应式 Web 界面。
- **后台监控**：按配置轮询来源目录；任务并发限制为 1–2，避免 NAS 磁盘和 Provider 请求过载。
- **fnOS 原生安装包**：可构建 `.fpk`，安装时使用官方 `python312` 和包内离线依赖。

## 适用范围与限制

- 适合个人或家庭 NAS 的电影、电视剧整理，不是在线播放器或下载器。
- TMDB 是当前主要元数据 Provider，需要自行申请并配置 TMDB API Key。
- 自动识别不承诺覆盖所有命名；信息冲突、低置信或目标文件冲突会停下等待人工确认。
- 不建议把唯一一份影片直接交给自动化流程。首次使用前请准备备份，并先用少量测试文件验证规则。
- 当前 `0.3.31` 已完成 `FNOS_UAT PASS`；这不代表所有 fnOS 机型和存储组合均已覆盖。后续候选包仍须区分 `LOCAL_BUILD PASS` 与真机验收。

## 处理流程

```text
扫描来源
  → 解析文件名 / 目录 / NFO / Provider ID
  → TMDB 搜索与身份校验
  → 自动通过，或等待人工确认
  → 计算维度与目标片库
  → 生成标准文件名并检查冲突
  → 来源直达目标侧任务暂存并校验
  → 字幕先发布、视频最后发布
  → 按配置保留、回收或处理来源
```

任何需要人工决定的节点都发生在大文件传输之前。运行中断后，系统只处理属于当前任务且证据吻合的临时成员，不扫描或猜测删除片库文件。

## fnOS 安装

### 使用安装包

从项目 [Releases](https://github.com/wae2855/nas_media_manage/releases) 下载最新 `.fpk` 和对应 `.sha256`，在 fnOS 应用中心手动安装。首次打开后按页面引导完成：

1. 授权来源目录、本地回收目录和一个或多个目标片库。
2. 配置 TMDB Provider 并测试连接。
3. 为分类规则明确选择目标片库。
4. 在“配置检查”确认没有阻塞项。
5. 先使用模拟测试或少量文件验证，再开启后台自动整理。

如果 Releases 暂无适合的候选包，可以按下方开发环境说明自行构建。

### 从源码构建 FPK

```bash
git clone https://github.com/wae2855/nas_media_manage.git
cd nas_media_manage

./scripts/bootstrap_python_env.sh
source .venv/bin/activate
./deploy/build_fpk.sh
```

产物位于 `build/nas-media-importer.fpk`，校验文件位于同目录。详细发布约束见 [deploy/README.md](deploy/README.md)。

## 本地开发

环境要求：Python `3.12.13`。项目使用原生 HTTP API、SQLite、原生 HTML/CSS/JavaScript 和 YAML 配置。

```bash
git clone https://github.com/wae2855/nas_media_manage.git
cd nas_media_manage

./scripts/bootstrap_python_env.sh
source .venv/bin/activate
cp config.yaml.example config/config.yaml

PYTHONPATH="${PWD}" python -m media_importer.media_importer \
  -c config/config.yaml serve -p 9855 --host 127.0.0.1
```

浏览器访问 `http://127.0.0.1:9855`。运行配置 `config/config.yaml` 已被 Git 忽略，不要提交任何 API Key、Cookie、数据库或真实目录信息。

## 常用配置

配置模板见 [config.yaml.example](config.yaml.example)。普通用户优先通过 Web 页面配置。

| 配置范围 | 用途 |
|----------|------|
| 来源与片库 | 来源目录、多个目标片库、本地回收目录及 fnOS 授权 |
| Provider | TMDB API Key、语言、连接测试和维度映射 |
| 片库整理 | 维度条件、目标片库、相对目录和命名模板 |
| 自动运行 | watcher 开关、扫描周期、稳定时间和任务并发数 |
| 来源处理 | 保留、回收或受控永久删除来源文件包 |
| 源目录清理 | 广告、小视频和其他明确非正片内容的过滤策略 |

## 测试

```bash
# 完整测试；浏览器测试需要 Playwright Chromium
.venv/bin/python -m pytest tests/

# 架构护栏
.venv/bin/python -m pytest tests/test_architecture_guards.py

# 文档检查
.venv/bin/python scripts/check_docs.py

# Python lint（至少检查本次改动文件）
.venv/bin/ruff check <files>
```

## 项目结构

```text
media_importer/
├── api/              # HTTP API 入口
├── core/             # 配置、任务与数据库兼容层
├── features/         # 导入、刮削、任务、配置等业务事实源
├── infrastructure/   # 数据库和文件系统基础能力
└── webui/            # 原生响应式 Web UI

deploy/               # fnOS FPK 构建与安装脚本
docs/                 # 架构、功能、决策、测试和工作流文档
tests/                # 单元、集成、文件安全与浏览器测试
```

开发者请先阅读 [AGENTS.md](AGENTS.md) 和 [docs/ai-map.md](docs/ai-map.md)。完整文档入口见 [docs/README.md](docs/README.md)。

## 文件安全边界

- 目标片库默认只新增；删除或替换必须进入受保护的本地回收流程。
- 文件操作限制在已授权目录，拒绝路径穿越、符号链接逃逸和未知挂载身份。
- 临时文件只允许在明确属于当前任务的 `.tmp` / `.copying` 边界清理。
- 来源永久删除默认关闭；启用后仍需经过来源文件包、隔离区和快照复核。
- 配置 API 返回凭据时必须脱敏，但你仍不应公开运行配置或日志。

完整规则见 [docs/standards/safety.md](docs/standards/safety.md)。请在使用前自行评估数据风险并保留可靠备份。

## 参与贡献

欢迎提交 Issue 或 Pull Request，包括：

- 提供无法正确识别的、已脱敏的文件名与目录结构样例；
- 修复刮削、字幕、任务状态或 fnOS 兼容问题；
- 补充自动化测试、文档和不同 NAS 环境的验证结果。

提交前请运行相关测试，不要上传真实媒体、API Key、Cookie、运行数据库、日志或包含个人路径的配置。安全问题请避免在公开 Issue 中粘贴敏感细节，可先通过下方微信联系维护者。

## 支持项目

如果这个项目帮你节省了整理时间，可以自愿请开发者喝杯咖啡。赞助不会解锁额外功能，也不影响 Issue 或功能建议的处理优先级。

| 请开发者喝杯咖啡 | 使用交流与建议 |
|:----------------:|:--------------:|
| <img src="media_importer/webui/assets/support/developer-reward-qr.png" alt="支持独立开发者的微信赞赏二维码" width="280"> | <img src="media_importer/webui/assets/support/developer-wechat-qr.png" alt="添加项目维护者微信的二维码" width="280"> |
| 微信扫码，自愿支持 | 微信扫码，反馈问题或建议 |

## 许可证

本项目采用 [MIT License](LICENSE)。

第三方依赖及素材的许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

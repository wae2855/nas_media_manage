---
title: "NAS影视自动化入库系统"
type: guide
date: 2026-05-16
prev: docs/05-checklist.md
---

# NAS影视自动化入库系统 — 测试指南

## 环境配置清单 (`test_config.yaml`)

---

## 你需要提前准备的

### 1. 测试目录（本地 Mac 上创建）

```bash
# 在项目目录下创建测试用的目录结构
mkdir -p /Users/wangwei/Documents/code/nas_media_manage/tests/fixtures/source
mkdir -p /Users/wangwei/Documents/code/nas_media_manage/tests/fixtures/temp
mkdir -p /Users/wangwei/Documents/code/nas_media_manage/tests/fixtures/import
```

| 目录 | 用途 | 对应配置项 |
|------|------|-----------|
| `tests/fixtures/source/` | 模拟网盘挂载源目录 | `source_dir` |
| `tests/fixtures/temp/` | 本地临时处理目录 | `temp_dir` |
| `tests/fixtures/import/` | 入库根目录（程序自动创建子目录） | `path_rules` 中模板基础路径 |

### 2. 测试影视文件

在 `tests/fixtures/source/` 下放置多种命名的测试文件，覆盖各种真实场景：

```bash
cd /Users/wangwei/Documents/code/nas_media_manage/tests/fixtures/source

# === 电影测试文件（英文原名为主） ===
touch "Breaking.Bad.S01E01.720p.BluRay.x264.mkv"
touch "Breaking.Bad.S01E01.720p.BluRay.x264.zh.srt"
touch "Breaking.Bad.S01E01.720p.BluRay.x264.en.srt"

touch "Breaking.Bad.S01E02.720p.BluRay.x264.mkv"
touch "Breaking.Bad.S01E02.720p.BluRay.x264.zh.srt"

touch "Breaking.Bad.S02E01.1080p.WEB-DL.x265.mkv"
touch "Breaking.Bad.S02E01.1080p.WEB-DL.x265.zh.srt"

# === 电视剧多语言字幕 ===
touch "Game.of.Thrones.S01E01.2160p.HDR.x265.mkv"
touch "Game.of.Thrones.S01E01.2160p.HDR.x265.zh.srt"
touch "Game.of.Thrones.S01E01.2160p.HDR.x265.en.srt"
touch "Game.of.Thrones.S01E01.2160p.HDR.x265.ja.srt"

# === 电影（无字幕） ===
touch "Inception.2010.1080p.BluRay.x264.mp4"

# === 电影（有中文字幕） ===
touch "The.Shawshank.Redemption.1994.720p.BluRay.x264.mkv"
touch "The.Shawshank.Redemption.1994.720p.BluRay.x264.zh.srt"

# === 纪录片 ===
touch "Planet.Earth.II.2016.2160p.BluRay.x265.mkv"
touch "Planet.Earth.II.2016.2160p.BluRay.x265.zh.srt"

# === 边界情况 ===
touch "The.Godfather.1972.REMASTERED.1080p.BluRay.x264-DUAL.mkv"
touch "The.Godfather.1972.REMASTERED.1080p.BluRay.x264-DUAL.zh.srt"

# === S1E1 格式（非标准） ===
touch "Stranger.Things.S1E1.720p.WEBRip.x264.mp4"
touch "Stranger.Things.S1E1.720p.WEBRip.x264.zh.srt"
```

**文件大小建议：** 测试文件使用 `touch` 创建空文件或写入少量数据即可。如需测试复制进度，可创建几百MB的大文件：
```bash
# 创建 200MB 测试文件
dd if=/dev/zero of="The.Dark.Knight.2008.1080p.BluRay.x264.mkv" bs=1m count=200
```

### 3. 测试配置文件

项目根目录创建 `config.yaml`（不需要在真实 NAS 路径上，用本地路径测试即可）：

```yaml
# /Users/wangwei/Documents/code/nas_media_manage/config.yaml
# 测试用配置

source_dir: "tests/fixtures/source"
temp_dir: "tests/fixtures/temp"
log_dir: "tests/fixtures/logs"

source_dir_scan:
  recursive: true
  max_depth: 5
  ignore_patterns:
    - "*.tmp"
    - ".DS_Store"
    - "*partial*"

video_extensions:
  - ".mkv"
  - ".mp4"
  - ".avi"
  - ".ts"
  - ".mov"

subtitle_extensions:
  - ".srt"
  - ".ass"
  - ".ssa"

llm:
  provider: "openai"
  api_key: "sk-your-real-api-key-here"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"
  timeout: 30
  max_retries: 2
  retry_delay: 3
  fallback_model: "gpt-3.5-turbo"
  confidence_threshold: 0.8

dimensions:
  - name: media_type
    label: 影视类型
    values:
      - movie
      - tv
    ai_prompt: "请判断这是电影还是电视剧（movie/tv）"
    ai_hint: "请仅返回movie或tv"

  - name: documentary
    label: 是否纪录片
    values:
      - yes
      - no
    ai_prompt: "请判断是否为纪录片（yes/no）"

  - name: restricted
    label: 是否限制级
    values:
      - yes
      - no
    ai_prompt: "请判断是否为限制级内容（yes/no）"

filename_templates:
  movie: "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}"
  tv: "{title_cn}.{title_en}.{year}.S{season:02d}E{episode:02d}.{resolution}.{quality}.{ext}"
  subtitle: "{video_filename}.{lang}.{ext}"

path_rules:
  - conditions:
      media_type: tv
    template: "tests/fixtures/import/电视剧/{title_cn} ({year})/Season {season}/"

  - conditions:
      media_type: movie
      documentary: no
    template: "tests/fixtures/import/电影/{year}/{title_cn} ({year})/"

  - conditions:
      media_type: movie
      documentary: yes
    template: "tests/fixtures/import/纪录片/{title_cn} ({year})/"

  - conditions: {}
    template: "tests/fixtures/import/其他/{title_cn} ({year})/"

rules:
  - name: tv_series_folder
    description: "电视剧必须单独文件夹"
    conditions:
      media_type: tv
    actions:
      - create_series_folder: true
      - organize_by_season: true
      - use_series_subfolder: "{title_cn} ({year})/"

  - name: movie_year_folder
    description: "电影按年份分文件夹"
    conditions:
      media_type: movie
    actions:
      - create_year_folder: true

duplicate_handling:
  strategy: "skip"
  notify: true
  notify_title_only: true

hermes:
  connection_type: "http"
  http:
    base_url: "http://your-hermes-ip:8080"
    timeout: 30
    api_key: ""
  ssh:
    host: "your-hermes-ip"
    port: 22
    user: "hermes"
    private_key_path: ""
    command_prefix: "python media_importer.py"
  webhook:
    route_name: "media-normalize"
    secret: ""
    max_retries: 3
    retry_delay: 5
    events:
      - task_complete
      - task_failed
      - task_skipped
      - batch_complete

file_watcher:
  enabled: true
  poll_interval: 10
  ignore_patterns:
    - "*.tmp"
    - ".DS_Store"
    - "*partial*"

task_queue:
  persistence_path: "tests/fixtures/tasks.json"
  max_concurrent: 1
  retry_on_failure: false
  auto_delete_success: true
  auto_delete_failed: false
  history_retention_days: 90

hooks:
  before_process: ""
  after_success: ""
  after_failure: ""

logging:
  level: "DEBUG"
  format: "json"
  max_size_mb: 100
  backup_count: 5
```

---

## 各阶段测试需要准备的内容

| 阶段 | 任务 | 需要准备 | 准备方式 |
|------|------|---------|---------|
| Phase 1 | Task 1-4 基础设施 | 基本目录结构 | 手动创建或脚本初始化 |
| Phase 2 | Task 5 文件扫描 | 源目录 + 测试影视文件 | `tests/fixtures/source/` 下放置文件 |
| Phase 2 | Task 6 AI刮削 | **大模型 API Key**（必需） | 配置 `llm.api_key` |
| Phase 2 | Task 7-8 分类+同名 | 入库目录且有部分已入库文件 | 可先手动跑一次入库再测试同名 |
| Phase 2 | Task 9-10 复制+搬运 | 源目录和临时目录 | 测试目录已在 fixtures 下 |
| Phase 4 | Task 13 通知 | **Hermes URL**（可选） | 配置 `hermes.http.base_url` |
| Phase 5 | Task 15 HTTP API | 端口 9855 可用 | 本地启动服务 |
| Phase 6 | Task 16-17 测试 | 全部以上 | pytest 运行 |

---

## Hermes 集成测试

### 如果 Hermes 已部署

```yaml
hermes:
  http:
    base_url: "http://192.168.x.x:8080"    # 替换为实际 IP
  webhook:
    route_name: "media-normalize"           # 需要在 Hermes 端预先配置
    secret: ""                              # 如 Hermes 端配置了签名，则需同步
```

### Hermes 端需要做的配置

你需要提前在 Hermes 端注册 webhook 路由 `media-normalize`，使其能接收本程序的 POST 请求。

### 如果暂时无法测试 Hermes

可以设置 `hermes.webhook.events: []` 来禁用通知，或使用本地 mock 服务：
```bash
# 启动一个简单的 echo 服务来接收 webhook 请求
python3 -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers['Content-Length'])
        body = self.rfile.read(length)
        print(f'=== Webhook received ===')
        print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))
        self.send_response(200)
        self.end_headers()
    def log_message(self, format, *args):
        pass

HTTPServer(('', 8888), Handler).serve_forever()
"
# 然后将 hermes.http.base_url 设为 http://localhost:8888
```

---

## LLM API 测试

### 成本控制建议

测试阶段可用更便宜的模型降低费用：
```yaml
llm:
  model: "gpt-4o-mini"          # 测试用便宜模型
  fallback_model: "gpt-3.5-turbo"
  confidence_threshold: 0.6     # 测试时降低阈值
```

### 如果不希望每次都调真实 API

单元测试中通过 mock 来测试：
```python
# test_llm_scraper.py 中使用 mock
from unittest.mock import patch, Mock

@patch('urllib.request.urlopen')
def test_scrape_success(mock_urlopen):
    mock_urlopen.return_value.read.return_value = json.dumps({
        "title_cn": "绝命毒师",
        "title_en": "Breaking Bad",
        "year": "2008",
        "type": "tv",
        "season": 1,
        "episode": 1,
        "dimensions": {"media_type": "tv", "documentary": "no", "restricted": "yes"},
        "confidence": 0.95
    }).encode()
    result = scraper.scrape("Breaking.Bad.S01E01.mkv", ["xxx.zh.srt"])
    assert result["title_cn"] == "绝命毒师"
```

---

## 快速初始化脚本

将此脚本保存运行即可一键初始化所有测试环境：

```bash
#!/bin/bash
# init_test_env.sh — 初始化测试环境

BASE_DIR="/Users/wangwei/Documents/code/nas_media_manage"

# 创建测试目录
mkdir -p "$BASE_DIR/tests/fixtures/source"
mkdir -p "$BASE_DIR/tests/fixtures/temp"
mkdir -p "$BASE_DIR/tests/fixtures/import"
mkdir -p "$BASE_DIR/tests/fixtures/logs"

# 切换到源目录创建测试文件
cd "$BASE_DIR/tests/fixtures/source"

# 创建电影测试文件
declare -a MOVIES=(
    "The.Shawshank.Redemption.1994.720p.BluRay.x264"
    "Inception.2010.1080p.BluRay.x264"
    "The.Dark.Knight.2008.2160p.BluRay.x265"
    "Interstellar.2014.1080p.WEB-DL.x264"
    "The.Godfather.1972.REMASTERED.1080p.BluRay.x264-DUAL"
    "Pulp.Fiction.1994.720p.BDRip.x264"
)

for movie in "${MOVIES[@]}"; do
    touch "${movie}.mkv"
    touch "${movie}.zh.srt"
done

# Inception 无字幕
rm -f "Inception.2010.1080p.BluRay.x264.zh.srt"

# Pulp Fiction 多语言字幕
cp "Pulp.Fiction.1994.720p.BDRip.x264.zh.srt" "Pulp.Fiction.1994.720p.BDRip.x264.en.srt"

# 创建电视剧测试文件
declare -a TVS=(
    "Breaking.Bad.S01E01.720p.BluRay.x264"
    "Breaking.Bad.S01E02.720p.BluRay.x264"
    "Breaking.Bad.S02E01.1080p.WEB-DL.x265"
    "Game.of.Thrones.S01E01.2160p.HDR.x265"
    "Stranger.Things.S1E1.720p.WEBRip.x264"
    "Stranger.Things.S1E2.720p.WEBRip.x264"
)

for tv in "${TVS[@]}"; do
    touch "${tv}.mkv"
    touch "${tv}.zh.srt"
done

# Game of Thrones 多语言字幕
touch "Game.of.Thrones.S01E01.2160p.HDR.x265.en.srt"
touch "Game.of.Thrones.S01E01.2160p.HDR.x265.ja.srt"

# 创建纪录片测试文件
touch "Planet.Earth.II.2016.2160p.BluRay.x265.mkv"
touch "Planet.Earth.II.2016.2160p.BluRay.x265.zh.srt"
touch "Planet.Earth.II.2016.2160p.BluRay.x265.en.srt"

touch "Cosmos.A.Spacetime.Odyssey.2014.1080p.BluRay.x264.mkv"
touch "Cosmos.A.Spacetime.Odyssey.2014.1080p.BluRay.x264.zh.srt"

# 创建干扰文件（应被忽略）
touch "test.tmp"
touch ".DS_Store"
touch "download.partial.mkv"

# 输出统计
echo "=== 测试环境初始化完成 ==="
echo "电影文件: $(ls *.mkv *.mp4 2>/dev/null | wc -l | tr -d ' ') 个"
echo "字幕文件: $(ls *.srt *.ass *.ssa 2>/dev/null | wc -l | tr -d ' ') 个"
echo "源目录:   $BASE_DIR/tests/fixtures/source"
echo "临时目录: $BASE_DIR/tests/fixtures/temp"
echo "入库目录: $BASE_DIR/tests/fixtures/import"
```

---

## 总结：你现在需要做的

| 序号 | 操作 | 优先级 |
|------|------|--------|
| 1 | 准备一个大模型 API Key（如 OpenAI） | 🔴 必须 |
| 2 | 运行上面的 `init_test_env.sh` 初始化测试文件 | 🔴 必须 |
| 3 | 将 `test_config.yaml` 复制为 `config.yaml` 并编辑 API Key | 🔴 必须 |
| 4 | 确认 Hermes 部署地址，在 Hermes 端注册 webhook 路由 | 🟡 可选 |
| 5 | 如有需要，启动本地 webhook echo 服务用于开发测试 | 🟡 可选 |

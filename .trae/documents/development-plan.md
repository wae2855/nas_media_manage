# NAS影视自动化入库系统 — 开发计划

**日期：** 2026-05-16
**关联：** [头脑风暴](file:///Users/wangwei/Documents/code/nas_media_manage/docs/brainstorms/2026-05-15-nas-media-auto-import-brainstorm.md) | [Spec](file:///Users/wangwei/Documents/code/nas_media_manage/.trae/specs/media-auto-import/spec.md) | [Tasks](file:///Users/wangwei/Documents/code/nas_media_manage/.trae/specs/media-auto-import/tasks.md)

---

## 1. 当前状态分析

### 已有的产物

| 文件 | 路径 | 大小 | 状态 |
|------|------|------|------|
| 头脑风暴文档 | `docs/brainstorms/2026-05-15-nas-media-auto-import-brainstorm.md` | ~1025 行 | ✅ 完整 |
| 规格文档 | `.trae/specs/media-auto-import/spec.md` | ~390 行 | ✅ 完整 |
| 任务列表 | `.trae/specs/media-auto-import/tasks.md` | ~207 行 | ✅ 完整 |
| 验收清单 | `.trae/specs/media-auto-import/checklist.md` | ~90 行 | ✅ 完整 |
| 测试环境 | `tests/fixtures/` | 14视频+17字幕 | ✅ 已初始化 |
| 测试初始化脚本 | `init_test_env.sh` | 可执行 | ✅ 已就绪 |

### 当前开发状态

项目目录下**没有任何业务代码**，仅有文档和测试数据。这是一个**全新项目**，需要从头搭建。

### 核心约束

1. **依赖最小化**：仅 `pyyaml` 一个外部依赖，其余使用 Python 标准库
2. **运行环境**：飞牛NAS (FNOS)，通过 systemd 管理
3. **交互方式**：HTTP API 为主，CLI 为备
4. **通知方式**：Hermes Webhook

---

## 2. 开发计划

### 开发总览

```
Phase 1（基础设施）: Task 1-4   → 3 天
Phase 2（核心业务）: Task 5-10  → 5 天
Phase 3（任务调度）: Task 11-12 → 3 天
Phase 4（通知钩子）: Task 13-14 → 2 天
Phase 5（API服务） : Task 15    → 3 天
Phase 6（测试）    : Task 16-17 → 3 天
Phase 7（部署）    : Task 18    → 1 天
────────────────────────────────────
总计                         约 20 天
```

---

### Phase 1: 项目基础设施

#### Task 1: 创建项目骨架和依赖管理

**目标：** 搭建项目目录结构、依赖文件和主入口框架。

**具体文件：**

| 文件 | 说明 |
|------|------|
| `media_importer/` | 项目根目录 |
| `media_importer/media_importer.py` | 主入口，argparse 子命令路由，支持 `serve`/`run`/`list`/`show`/`retry`/`queue`/`clear`/`log`/`health`/`metrics`/`config` |
| `media_importer/requirements.txt` | `pyyaml>=6.0` |
| `media_importer/config.yaml` | 默认配置模板（12段落） |

**主入口代码结构：**
```python
# media_importer.py
import argparse
import sys

def cmd_serve(args): ...
def cmd_run(args): ...
def cmd_list(args): ...
def cmd_show(args): ...
def cmd_retry(args): ...
def cmd_queue(args): ...
def cmd_clear(args): ...
def cmd_log(args): ...
def cmd_health(args): ...
def cmd_metrics(args): ...
def cmd_config(args): ...

def main():
    parser = argparse.ArgumentParser(prog="media_importer", ...)
    subparsers = parser.add_subparsers(dest="command")
    # ... 注册所有子命令
    args = parser.parse_args()
    if args.command == "serve":
        # 启动HTTP服务
        from api_server import start_server
        start_server(port=args.port)
    elif args.command == "run":
        ...
    # etc.

if __name__ == "__main__":
    main()
```

**验收标准：**
- `python media_importer.py --help` 输出完整子命令列表
- `config.yaml` 包含12个段落且 YAML 语法正确

---

#### Task 2: 配置加载与校验模块 (config_loader.py)

**目标：** 实现配置文件加载、校验、默认值生成、敏感字段脱敏。

**核心函数/类：**
```python
# config_loader.py
def load_config(config_path: str) -> dict:
    """加载 config.yaml，文件不存在时生成默认模板并退出。"""
    ...

def validate_config(config: dict) -> list[str]:
    """校验12个段落完整性，返回错误列表。"""
    ...

def generate_default_config(path: str):
    """生成包含注释的默认配置文件。"""
    ...

def mask_sensitive(config: dict) -> dict:
    """脱敏：api_key→"sk-***", secret→"***"。"""
    ...

def validate_dimension_values(dimensions: list, ai_response: dict) -> list[str]:
    """校验AI返回的每个维度值在配置的 values 范围内。"""
    ...
```

**验收标准：**
- config.yaml 缺失时生成默认模板
- 缺少 `llm.api_key` 时报错
- dimensions 值不在范围内时报错
- `mask_sensitive()` 返回脱敏后的 dict

---

#### Task 3: 结构化日志模块 (logger.py)

**目标：** 实现 JSON/text 双格式日志，按级别过滤，文件轮转。

**核心类：**
```python
# logger.py
class Logger:
    def __init__(self, level: str, fmt: str, log_dir: str, max_size_mb: int, backup_count: int):
        """初始化日志器，设置日志目录和轮转参数。"""
        ...

    def debug(self, msg: str, **kwargs): ...
    def info(self, msg: str, **kwargs): ...
    def warn(self, msg: str, **kwargs): ...
    def error(self, msg: str, **kwargs): ...

    def step_log(self, task_id: str, step: str, level: str, message: str):
        """记录步骤日志到任务的 logs 数组。"""
        ...

    def check_rotate(self):
        """检查日志文件大小，超限则轮转。"""
        ...
```

**JSON 日志格式：**
```json
{"time": "2026-05-16T10:00:05", "level": "INFO", "message": "...", "task_id": "uuid", "step": "scrape"}
```

**验收标准：**
- DEBUG/INFO/WARN/ERROR 四级过滤正常
- JSON format 输出合法的 JSON Lines 格式
- 文件超 max_size_mb 后自动轮转

---

#### Task 4: 指标统计模块 (metrics.py)

**目标：** 追踪运行指标，提供统一查询接口。

```python
# metrics.py
class Metrics:
    def __init__(self):
        self.start_time = time.time()
        self._counters = {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        self._processing_times = []
        self._llm_calls = 0
        self._llm_failures = 0

    def record_task_start(self): ...
    def record_task_complete(self, status: str, duration: float): ...
    def record_llm_call(self, success: bool): ...

    @property
    def success_rate(self) -> float: ...
    @property
    def avg_processing_time(self) -> float: ...
    @property
    def uptime(self) -> str: ...

    def to_dict(self) -> dict: ...
```

**验收标准：**
- 计数器正确累加
- success_rate 返回小数（如 0.93）
- uptime 正常显示

---

### Phase 2: 核心业务模块

#### Task 5: 文件扫描器 (file_scanner.py)

**目标：** 递归扫描源目录，识别视频和字幕文件，按文件名前缀分组。

```python
# file_scanner.py
def scan_source_dir(source_dir: str, config: dict) -> list[dict]:
    """
    扫描源目录，返回分组列表。

    返回格式：
    [
        {
            "video": "/path/to/Inception.2010.mkv",
            "subtitles": [],
            "group_name": "Inception.2010"  # 公共前缀
        },
        {
            "video": "/path/to/Breaking.Bad.S01E01.mkv",
            "subtitles": ["/path/to/Breaking.Bad.S01E01.zh.srt"],
            "group_name": "Breaking.Bad.S01E01"
        }
    ]
    """
    ...

def find_video_files(root, extensions, ignore_patterns, max_depth):
    """递归查找视频文件。"""
    ...

def find_subtitle_files(video_path, subtitle_extensions):
    """查找与视频文件匹配的字幕文件。
       匹配规则: video名称.{lang}.{subtitle_ext} -> video名称+subtitle_ext"""
    ...

def match_filename_pattern(filename, patterns):
    """检查文件名是否匹配 ignore_patterns 中的 glob 模式。"""
    ...
```

**分组逻辑：**
1. 扫描视频文件，提取不带扩展名的文件名作为 `group_name`
2. 对每个视频文件，查找同目录下以 `group_name.{lang}.{ext}` 命名的字幕文件
3. 返回 `[{video, subtitles, group_name}, ...]`

**验收标准：**
- Inception 被识别为电影但无字幕（subtitles=[]）
- Breaking Bad S01E01 关联到 .zh.srt 字幕
- .tmp 和 .DS_Store 被忽略

---

#### Task 6: AI 刮削引擎 (llm_scraper.py)

**目标：** 调用大模型 API，动态构建 prompt，解析并校验返回结果。

```python
# llm_scraper.py
class LLMScraper:
    def __init__(self, config: dict):
        self.api_key = config["llm"]["api_key"]
        self.base_url = config["llm"]["base_url"]
        self.model = config["llm"]["model"]
        self.timeout = config["llm"]["timeout"]
        self.max_retries = config["llm"]["max_retries"]
        self.retry_delay = config["llm"]["retry_delay"]
        self.fallback_model = config["llm"].get("fallback_model")
        self.confidence_threshold = config["llm"]["confidence_threshold"]
        self.dimensions = config["dimensions"]

    def scrape(self, video_filename: str, subtitle_filenames: list[str]) -> dict:
        """
        输入: 视频文件名 + 字幕文件名列表
        输出: {title_cn, title_en, year, resolution, quality, language,
               type, season, episode, dimensions: {name: value}, confidence, raw_info}
        失败抛出 LLMScrapeError
        """

    def _build_system_prompt(self) -> str:
        """根据 dimensions 配置动态构建 system prompt。"""

    def _build_json_schema(self) -> dict:
        """动态构建期望的 JSON Schema。"""

    def _call_api(self, system_prompt: str, user_content: str, model: str) -> str:
        """使用 urllib.request 调用 OpenAI 兼容 API，返回 raw 文本。"""

    def _parse_response(self, raw_text: str) -> dict:
        """解析 LLM 返回的 JSON，校验必需字段和 dimensions 值范围。"""

    def _retry_with_fallback(self, *args) -> dict:
        """重试 max_retries 次，仍失败尝试 fallback_model。"""
```

**动态 Prompt 构建示例：**
```
你是一个专业的影视信息刮削助手。

当前需要判断的维度：
1. 是否纪录片（documentary）: [yes, no]
2. 是否限制级（restricted）: [yes, no]

请严格按以下JSON格式返回：
{
  "title_cn": "string|null",
  "title_en": "string|null",
  "year": int|null,
  "resolution": "string|null",
  "quality": "string|null",
  "language": "string|null",
  "type": "movie|tv",
  "season": int|null,
  "episode": int|null,
  "dimensions": {
    "documentary": "yes|no",
    "restricted": "yes|no"
  },
  "confidence": float
}
```

**验收标准：**
- 正常响应返回完整 dict
- 非 JSON 返回 触发重试
- 超时触发重试
- 重试耗尽仍失败抛出 LLMScrapeError
- low_confidence 标记正确

---

#### Task 7: 分类匹配器 (classifier.py)

**目标：** 根据 path_rules 配置匹配入库路径。

```python
# classifier.py
def classify(scraped_info: dict, path_rules: list) -> str:
    """
    遍历 path_rules，匹配 conditions，返回生成的入库路径。

    path_rules 示例:
    [
        {"conditions": {"media_type": "tv"}, "template": "/path/{title_cn} ({year})/Season {season}/"},
        {"conditions": {"media_type": "movie", "documentary": "no"}, "template": "/path/{year}/{title_cn} ({year})/"},
    ]
    """

def match_conditions(dimensions: dict, conditions: dict) -> bool:
    """检查 dimensions 是否满足 conditions 中所有 key-value。"""

def render_template(template: str, scraped_info: dict) -> str:
    """
    替换模板变量:
    {title_cn}/{title_en}/{year}/{season}/{episode}/{resolution}/{quality}
    {dimension.xxx} → dimensions["xxx"]
    """
```

**匹配逻辑：**
1. 按 path_rules 数组顺序遍历
2. conditions 中所有 key 必须等于 dimensions 中对应值（AND 逻辑）
3. 第一个全部匹配的规则即为命中
4. 都不匹配时使用 conditions: {} 的兜底规则

**验收标准：**
- 电影匹配到电影路径
- 纪录片匹配到纪录片路径
- 无法匹配的走兜底规则
- 模板变量正确替换

---

#### Task 8: 同名检测模块 (dedup_checker.py)

**目标：** 检测入库目录是否已存在同名文件。

```python
# dedup_checker.py
def check_duplicate(import_path: str, scraped_info: dict, strategy: str) -> dict:
    """
    检查同名文件。

    返回:
    {
        "is_duplicate": bool,
        "existing_file": "path_or_null",
        "action": "skip|overwrite|rename",
        "suggested_filename": "path_or_null"  # rename 策略时使用
    }
    """

def is_title_match(title_a: str, title_b: str) -> bool:
    """标题比较：忽略大小写和常见标点符号（.、-、_、空格等）。"""

def find_existing_file(search_dir: str, scraped_info: dict) -> str:
    """在 search_dir 及其子目录中查找与 scraped_info 同名的文件。"""
```

**同名判断逻辑：**
1. 提取 scraped_info 中的 {title_cn, title_en, year, season, episode}
2. 扫描入库目录，对每个已有文件解析其命名中的这些字段
3. 比较：年份必须相同 AND (title_cn 或 title_en 至少一个匹配)
4. 电视剧额外检查 season + episode

**验收标准：**
- 相同年份+标题检测为同名
- 电视剧不同集号不视为同名
- skip 策略返回跳过
- rename 策略生成带序号的替代文件名

---

#### Task 9: 文件复制器 (file_copier.py)

**目标：** 安全地从源目录复制文件到临时目录，支持断点续传。

```python
# file_copier.py
class FileCopier:
    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir

    def copy_to_temp(self, video_path: str, subtitle_paths: list[str],
                     progress_callback=None) -> list[str]:
        """
        复制视频和字幕到临时目录。
        使用 .copying 后缀标记正在复制的文件。
        返回临时目录中的文件路径列表。
        """

    def copy_file_with_marker(self, src: str, dest: str, progress_callback=None):
        """
        复制单个文件：
        1. 先写到 dest.copying
        2. 复制完成后 rename 为 dest
        3. 如 dest.copying 已存在，检查大小决定是否断点续传
        """

    def cleanup_residual_copies(self):
        """启动时清理临时目录中残留的 .copying 文件。"""

    def check_disk_space(self, file_size: int) -> bool:
        """检查目标磁盘剩余空间 >= file_size * 1.5。"""
```

**断点续传逻辑：**
1. 复制前检查 `dest.copying` 是否存在
2. 存在 → 记录 `copied_bytes = os.path.getsize(dest.copying)`
3. 以 append 模式打开 `dest.copying`，从 `copied_bytes` 位置开始读取源文件
4. 完成后删除 `.copying` 后缀

**验收标准：**
- 正常复制到临时目录
- `.copying` 标记在复制中可见
- 复制完成后 `.copying` 被移除
- 残留 `.copying` 启动时被清理

---

#### Task 10: 文件搬运器 (file_mover.py)

**目标：** 应用命名模板 → 创建入库目录 → 移动文件 → 删除源文件。

```python
# file_mover.py
def apply_filename_template(scraped_info: dict, template: str, video_ext: str) -> str:
    """
    应用文件名模板生成最终文件名。
    例: "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}"
      → "肖申克的救赎.The Shawshank Redemption.1994.720p.BluRay.mkv"
    """

def create_import_dir(import_path: str):
    """创建入库目录（含父目录，exist_ok=True）。"""

def move_file(src: str, dest: str) -> bool:
    """
    移动文件：
    1. 尝试 os.rename（同设备快速移动）
    2. 失败则 shutil.copy2 + os.remove（跨设备降级）
    """

def clean_source(original_paths: list[str]):
    """删除源文件（原始目录中的文件）。"""

def check_disk_space_before_move(file_size: int, dest_dir: str) -> bool:
    """移动前检查目标磁盘空间。"""
```

**验收标准：**
- 电影文件名按 movie 模板生成
- 电视剧文件名按 tv 模板生成（含 S01E01 格式）
- 字幕文件名按 subtitle 模板生成
- 跨设备移动降级正常
- 源文件清理正常

---

### Phase 3: 任务调度

#### Task 11: 任务管理器 (task_manager.py)

**目标：** 任务队列、状态机、持久化、进度追踪。

```python
# task_manager.py
import json, uuid, time, threading
from dataclasses import dataclass, field, asdict

@dataclass
class Task:
    task_id: str
    video_file: str
    video_path: str
    file_size_mb: float = 0
    subtitle_files: list[str] = field(default_factory=list)
    scraped_info: dict = field(default_factory=dict)
    import_path: str = ""
    final_filename: str = ""
    status: str = "PENDING"
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    error_code: int = 0
    error_message: str = ""
    retry_count: int = 0
    logs: list[dict] = field(default_factory=list)
    # 进度追踪
    current_step: int = 0
    total_steps: int = 9
    step_name: str = ""
    percentage: int = 0
    bytes_copied: int = 0
    total_bytes: int = 0


class TaskManager:
    def __init__(self, persistence_path: str, config: dict):
        self.path = persistence_path
        self.config = config
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._load_tasks()

    def create_task(self, video_path, video_file, subtitle_files, file_size) -> Task: ...
    def get_next_pending(self) -> Task | None: ...
    def update_task(self, task: Task): ...
    def get_task(self, task_id: str) -> Task | None: ...
    def list_tasks(self, status=None, limit=20, offset=0) -> list[Task]: ...
    def retry_task(self, task_id: str) -> Task | None: ...
    def clear_tasks(self, status: str): ...
    def update_progress(self, task: Task, step_num, step_name, percentage, **kwargs): ...
    def _save_tasks(self): ...
    def _load_tasks(self): ...
    def _cleanup_old_tasks(self): ...
```

**验收标准：**
- 状态机转换正确
- tasks.json 序列化/反序列化正常
- FIFO 顺序执行
- 进度追踪更新及时
- 重启后恢复未完成任务

---

#### Task 12: 任务调度器

**目标：** 9步流水线编排，队列控制，文件监控。

此功能可以集成在 `task_manager.py` 中，也可以作为独立模块 `scheduler.py`。

```python
# 调度器核心逻辑（可在 media_importer.py 的 serve/run 中实现）

class PipelineRunner:
    """
    9步流水线：
    1. 扫描 → 2. 复制 → 3. 刮削 → 4. 分类 → 5. 同名检测
    → 6. 命名 → 7. 入库 → 8. 通知 → 9. 记录
    """
    def __init__(self, config, task_manager, metrics, logger):
        ...

    def process_one(self, task: Task) -> bool:
        """处理单个任务，返回是否成功。"""

    def run_all(self):
        """依次处理队列中所有 PENDING 任务。"""

    def pause(self): ...
    def resume(self): ...
    def is_paused(self) -> bool: ...
```

**验收标准：**
- 完整9步执行
- 失败步骤正确标记并暂停后续步骤
- 暂停/恢复功能正常
- 文件监控轮询正常

---

### Phase 4: 通知与钩子

#### Task 13: Hermes 通知模块 (notifier.py)

**目标：** 向 Hermes 发送 Webhook 通知。

```python
# notifier.py
class HermesNotifier:
    def __init__(self, config: dict):
        self.config = config["hermes"]
        self.enabled_events = set(self.config["webhook"]["events"])

    def should_notify(self, event_type: str) -> bool:
        return event_type in self.enabled_events

    def notify(self, event_type: str, task: Task):
        """
        发送 Webhook 通知。
        失败时重试 max_retries 次，仍失败记录日志但不抛异常。
        """

    def _build_payload(self, event_type: str, task: Task) -> dict:
        """构建 Hermes Webhook 所需的 payload。"""

    def _sign(self, payload: str) -> str:
        """HMAC-SHA256 签名。"""

    def notify_batch_complete(self, tasks: list[Task]):
        """批次完成汇总通知。"""
```

**验收标准：**
- task_complete/task_failed/task_skipped/batch_complete 四种 payload 格式正确
- 通知失败不中断主流程
- 事件过滤按配置生效

---

#### Task 14: 钩子系统 (hooks.py)

**目标：** 在关键节点执行自定义脚本。

```python
# hooks.py
class HookRunner:
    def __init__(self, config: dict):
        self.before = config["hooks"].get("before_process", "")
        self.after_success = config["hooks"].get("after_success", "")
        self.after_failure = config["hooks"].get("after_failure", "")

    def run_hook(self, name: str, script_path: str, context: dict = None):
        """
        执行钩子脚本。
        使用 subprocess.run，超时 60 秒。
        失败记录日志但不中断主流程。
        """

    def before_process(self): ...
    def after_success(self, task: Task): ...
    def after_failure(self, task: Task): ...
```

---

### Phase 5: API 服务

#### Task 15: HTTP API 服务 (api_server.py)

**目标：** 使用 `http.server` 实现 HTTP REST API。

```python
# api_server.py
import http.server
import json
from urllib.parse import urlparse, parse_qs

class APIHandler(http.server.BaseHTTPRequestHandler):
    """
    路由分发：
    - POST /api/run
    - POST /api/run/file
    - GET  /api/tasks
    - GET  /api/tasks/{task_id}
    - POST /api/tasks/{task_id}/retry
    - DELETE /api/tasks/{task_id}
    - POST /api/tasks/clear
    - POST /api/queue/pause
    - POST /api/queue/resume
    - GET  /api/queue/status
    - GET  /api/config
    - POST /api/config/reload
    - GET  /api/health
    - GET  /api/metrics
    - GET  /api/logs
    """

    def _send_json(self, code: int, message: str, data=None):
        """发送统一 JSON 响应。"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"code": code, "message": message, "data": data}).encode())

    def do_GET(self): ...
    def do_POST(self): ...
    def do_DELETE(self): ...

    def _parse_path(self):
        """解析路径和路由匹配。"""

    def _handle_run(self, body: dict): ...
    def _handle_run_file(self, body: dict): ...
    def _handle_tasks_get(self, params): ...
    def _handle_task_get(self, task_id: str): ...
    def _handle_task_retry(self, task_id: str): ...
    def _handle_task_delete(self, task_id: str): ...
    def _handle_tasks_clear(self, body: dict): ...
    def _handle_queue_pause(self): ...
    def _handle_queue_resume(self): ...
    def _handle_queue_status(self): ...
    def _handle_config_get(self): ...
    def _handle_config_reload(self): ...
    def _handle_health(self): ...
    def _handle_metrics(self): ...
    def _handle_logs(self, params): ...


def start_server(port: int, config: dict, task_manager: TaskManager,
                 metrics: Metrics, logger: Logger, pipeline: PipelineRunner):
    """启动 HTTP 服务。"""
```

**验收标准：**
- 16 个端点全部可访问且响应正确
- 统一 `{code, message, data}` 格式
- 错误码与 spec 一致
- 线程安全（共享 task_manager）

---

### Phase 6: 测试

#### Task 16: 单元测试

使用 pytest，每个测试文件对应一个模块。

```python
# tests/test_config_loader.py
def test_load_valid_config(): ...
def test_generate_default_on_missing(): ...
def test_mask_sensitive_fields(): ...
def test_validate_dimension_values(): ...

# tests/test_file_scanner.py
def test_scan_source_dir(): ...
def test_filter_by_extensions(): ...
def test_ignore_patterns(): ...
def test_group_video_with_subtitles(): ...

# tests/test_llm_scraper.py
def test_build_system_prompt(): ...
def test_parse_valid_response(): ...
def test_handle_invalid_json(): ...
def test_retry_on_failure(): ...
def test_fallback_model(): ...
def test_low_confidence_warning(): ...

# tests/test_classifier.py
def test_match_path_rules(): ...
def test_fallback_rule(): ...
def test_render_template(): ...

# tests/test_dedup_checker.py
def test_detect_duplicate(): ...
def test_not_duplicate_different_year(): ...
def test_tv_episode_different(): ...
def test_skip_strategy(): ...
def test_rename_strategy(): ...

# tests/test_file_copier.py
def test_copy_to_temp(): ...
def test_copy_marker_file(): ...
def test_disk_space_check(): ...
def test_cleanup_residual(): ...

# tests/test_file_mover.py
def test_apply_movie_template(): ...
def test_apply_tv_template(): ...
def test_create_import_dir(): ...
def test_move_file_cross_device_fallback(): ...

# tests/test_task_manager.py
def test_create_task(): ...
def test_state_transitions(): ...
def test_persistence(): ...
def test_fifo_order(): ...
def test_retry_task(): ...
def test_clear_tasks(): ...
def test_progress_tracking(): ...
```

#### Task 17: 集成测试

```python
# tests/test_integration.py
def test_end_to_end_flow(mock_llm): ...
def test_interrupted_copy_recovery(): ...
def test_ai_scrape_failure_handling(): ...
def test_duplicate_skip(): ...
def test_disk_full_handling(): ...
def test_http_api_endpoints(client): ...
```

---

### Phase 7: 部署

#### Task 18: 部署配置

```ini
# media-importer.service
[Unit]
Description=NAS Media Importer Service
After=network.target

[Service]
Type=simple
User=nas
WorkingDirectory=/path/to/media_importer
ExecStart=/path/to/media_importer/venv/bin/python media_importer.py serve --port 8000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**PyInstaller 打包：**
```bash
pip install pyinstaller
pyinstaller --onefile --name media_importer media_importer.py
```

**Dockerfile（备选）：**
```dockerfile
FROM python:3.11-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "media_importer.py", "serve", "--port", "8000"]
```

---

## 3. 项目目录结构（最终）

```
media_importer/
├── media_importer.py         # 主入口（CLI + HTTP 服务启动）
├── config.yaml               # 默认配置模板
├── config_loader.py          # 配置加载、校验、默认值
├── logger.py                 # 结构化日志
├── metrics.py                # 指标统计
├── file_scanner.py           # 文件扫描和分组
├── llm_scraper.py            # AI 刮削引擎
├── classifier.py             # 分类规则匹配
├── dedup_checker.py          # 同名检测
├── file_copier.py            # 文件复制（含断点续传）
├── file_mover.py             # 文件重命名和移动
├── task_manager.py           # 任务队列持久化和调度
├── notifier.py               # Hermes Webhook 通知
├── hooks.py                  # 脚本钩子
├── api_server.py             # HTTP API 路由和处理
├── tests/
│   ├── test_config_loader.py
│   ├── test_file_scanner.py
│   ├── test_llm_scraper.py
│   ├── test_classifier.py
│   ├── test_dedup_checker.py
│   ├── test_file_copier.py
│   ├── test_file_mover.py
│   ├── test_task_manager.py
│   └── test_integration.py
├── logs/                     # 运行期生成
├── tasks.json                # 运行期生成
└── requirements.txt
```

---

## 4. 实现顺序与依赖关系

```
Phase 1: Task 1 → Task 2 → Task 3, Task 4 (基础设施)
Phase 2: Task 2 → Task 5, Task 6, Task 7, Task 8, Task 9, Task 10 (核心模块，可并行)
Phase 3: Phase 2 → Task 11 → Task 12
Phase 4: Task 11 → Task 13, Task 14 (可并行)
Phase 5: Phase 3 + Phase 4 → Task 15
Phase 6: Task 15 → Task 16, Task 17 (可并行)
Phase 7: Task 15 → Task 18
```

---

## 5. 每阶段可并行执行的任务

| 阶段 | 可并行任务 |
|------|-----------|
| Phase 2 | Task 5, 6, 7, 8, 9, 10 之间无依赖，可全部并行 |
| Phase 4 | Task 13, 14 无依赖，可并行 |
| Phase 6 | Task 16, 17 无依赖，可并行 |

---

## 6. 验证计划

| 验证方式 | 覆盖范围 |
|---------|---------|
| 单元测试 | 每个模块的独立功能（15+ 文件，50+ 用例） |
| 集成测试 | 9步端到端流程 + 异常场景 + API 端点 |
| 手动测试 | 用 `tests/fixtures/source/` 中的测试文件运行完整流程 |
| 验收清单 | checklist.md 中 80+ 个检查点 |

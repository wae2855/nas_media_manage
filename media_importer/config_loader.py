#!/usr/bin/env python3
import os
import yaml
import sys
from copy import deepcopy


def generate_default_config(path: str):
    default_config = """# ============================================================
# NAS影视自动化入库系统 - 配置文件 (config.yaml)
# ============================================================

# ------------------------------------------------------------
# 1. 基础配置
# ------------------------------------------------------------
server:
  host: "0.0.0.0"
  port: 9855

source_dir: "/挂载/网盘下载"
temp_dir: "/nas本地/临时目录"
log_dir: "/nas本地/日志目录"

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
  - ".wmv"
  - ".m2ts"
  - ".flv"

subtitle_extensions:
  - ".srt"
  - ".ass"
  - ".ssa"
  - ".vtt"
  - ".sub"

# ------------------------------------------------------------
# 2. 大模型配置
# ------------------------------------------------------------
llm:
  provider: "openai"
  api_key: "your-api-key-here"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"
  timeout: 30
  max_retries: 2
  retry_delay: 3
  fallback_model: "gpt-3.5-turbo"
  confidence_threshold: 0.8

# ------------------------------------------------------------
# 3. AI判断维度配置
# ------------------------------------------------------------
dimensions:
  - name: media_type
    label: 影视类型
    values:
      - "movie"
      - "tv"
    ai_prompt: "请判断这是电影还是电视剧（movie/tv）"
    ai_hint: "请仅返回movie或tv"

  - name: documentary
    label: 是否纪录片
    values:
      - "yes"
      - "no"
    ai_prompt: "请判断是否为纪录片（yes/no）"

  - name: restricted
    label: 是否限制级
    values:
      - "yes"
      - "no"
    ai_prompt: "请判断是否为限制级内容（yes/no）"

# ------------------------------------------------------------
# 4. 文件名模板配置
# ------------------------------------------------------------
filename_templates:
  movie: "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}"
  tv: "{title_cn}.{title_en}.{year}.S{season:02d}E{episode:02d}.{resolution}.{quality}.{ext}"
  subtitle: "{video_filename}.{lang}.{ext}"

# ------------------------------------------------------------
# 5. 路径规则配置
# ------------------------------------------------------------
path_rules:
  - conditions:
      media_type: tv
    template: "/nas本地/入库目录/电视剧/{title_cn} ({year})/Season {season}/"

  - conditions:
      media_type: movie
      documentary: no
    template: "/nas本地/入库目录/电影/{year}/{title_cn} ({year})/"

  - conditions:
      media_type: movie
      documentary: yes
    template: "/nas本地/入库目录/纪录片/{title_cn} ({year})/"

  - conditions: {}
    template: "/nas本地/入库目录/其他/{title_cn} ({year})/"

# ------------------------------------------------------------
# 6. 特殊处理规则配置
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# 7. 同名文件处理配置
# ------------------------------------------------------------
duplicate_handling:
  strategy: "skip"
  notify: true
  notify_title_only: true

# ------------------------------------------------------------
# 8. Hermes配置
# ------------------------------------------------------------
hermes:
  enabled: false
  webhook:
    base_url: "http://your-hermes-ip:8644"
    route_name: "media-normalize"
    secret: ""
    timeout: 30
    max_retries: 3
    retry_delay: 5
    events:
      - task_complete
      - task_failed
      - task_skipped
      - batch_complete

# ------------------------------------------------------------
# 9. 文件监控配置
# ------------------------------------------------------------
file_watcher:
  enabled: true
  poll_interval: 10
  ignore_patterns:
    - "*.tmp"
    - ".DS_Store"
    - "*partial*"

# ------------------------------------------------------------
# 10. 任务队列配置
# ------------------------------------------------------------
task_queue:
  persistence_path: "tasks.json"
  max_concurrent: 1
  retry_on_failure: false
  auto_delete_success: true
  auto_delete_failed: false
  history_retention_days: 90

# ------------------------------------------------------------
# 11. 钩子配置
# ------------------------------------------------------------
hooks:
  before_process: ""
  after_success: ""
  after_failure: ""

# ------------------------------------------------------------
# 12. 日志配置
# ------------------------------------------------------------
logging:
  level: "INFO"
  format: "json"
  max_size_mb: 100
  backup_count: 5
"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(default_config)


def validate_config(config: dict) -> list:
    errors = []

    if not config.get("llm", {}).get("api_key") or config["llm"]["api_key"] == "your-api-key-here":
        errors.append("缺少有效的 llm.api_key 配置")

    for dir_key in ["source_dir", "temp_dir", "log_dir"]:
        dir_path = config.get(dir_key, "")
        if not dir_path:
            errors.append(f"{dir_key} 未配置")
        elif not os.path.isdir(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
            except OSError:
                errors.append(f"{dir_key} 不存在且无法创建: {dir_path}")

    dimensions = config.get("dimensions", [])
    for dim in dimensions:
        if not dim.get("name"):
            errors.append("dimension 缺少 name 字段")
        if not dim.get("values") or not isinstance(dim["values"], list):
            errors.append(f"dimension '{dim.get('name')}' 缺少有效的 values 列表")

    return errors


def mask_sensitive(config: dict) -> dict:
    masked = deepcopy(config)

    if masked.get("llm", {}).get("api_key"):
        api_key = masked["llm"]["api_key"]
        if len(api_key) > 8:
            masked["llm"]["api_key"] = api_key[:4] + "***" + api_key[-4:]
        else:
            masked["llm"]["api_key"] = "***"

    if masked.get("hermes", {}).get("webhook", {}).get("secret"):
        masked["hermes"]["webhook"]["secret"] = "***"

    return masked


def validate_dimension_values(dimensions: list, ai_response: dict) -> list:
    errors = []

    if "dimensions" not in ai_response:
        return errors

    for dim in dimensions:
        dim_name = dim["name"]
        if dim_name in ai_response["dimensions"]:
            value = ai_response["dimensions"][dim_name]
            valid_values = dim.get("values", [])
            if valid_values and value not in valid_values:
                errors.append(
                    f"dimension '{dim_name}' 的值 '{value}' 不在允许范围内: {valid_values}"
                )

    return errors


def load_config(config_path: str = None) -> dict:
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

    if not os.path.exists(config_path):
        print(f"配置文件不存在，正在生成默认配置模板: {config_path}")
        generate_default_config(config_path)
        print("默认配置模板已生成，请编辑后重新启动程序")
        sys.exit(1)

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"配置文件 YAML 格式错误: {e}")
        sys.exit(1001)

    config_dir = os.path.dirname(os.path.abspath(config_path))
    project_root = os.path.dirname(config_dir)

    for key in ["source_dir", "temp_dir", "log_dir"]:
        path_val = config.get(key, "")
        if path_val and not os.path.isabs(path_val):
            config[key] = os.path.join(project_root, path_val)

    # 处理 persistence_path 的相对路径转换
    task_queue = config.get("task_queue", {})
    persistence_path = task_queue.get("persistence_path", "")
    if persistence_path and not os.path.isabs(persistence_path):
        task_queue["persistence_path"] = os.path.join(project_root, persistence_path)

    errors = validate_config(config)
    if errors:
        print("配置校验失败:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1002)

    return config

#!/bin/bash
# NAS影视入库系统 - 测试环境重启脚本
# 功能：清理测试数据、杀进程、重启服务、生成丰富测试数据
#
# 测试数据覆盖场景：
#   电影: 普通/纪录片/动漫(日漫/欧美)/限制级(17+)/韩国/未知
#   电视剧: 普通/纪录片/动漫(日漫/国漫)/限制级(17+)
#   字幕: .srt(中/英)/.ass/.idx+.sub
#   干扰: .nfo/.jpg/.txt/独立文件
#   目录: 子目录递归/中文目录名/多集

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$PROJECT_DIR/config/config.yaml"

echo "========================================"
echo " NAS影视入库系统 - 测试环境重启"
echo "========================================"

# 1. 读取配置文件获取目录路径
if [ -f "$CONFIG_FILE" ]; then
    SOURCE_DIR=$(grep '^source_dir:' "$CONFIG_FILE" | head -1 | awk -F': ' '{print $2}' | tr -d '"')
    TEMP_DIR=$(grep '^temp_dir:' "$CONFIG_FILE" | head -1 | awk -F': ' '{print $2}' | tr -d '"')
    LOG_DIR=$(grep '^log_dir:' "$CONFIG_FILE" | head -1 | awk -F': ' '{print $2}' | tr -d '"')
    DATA_DIR="$PROJECT_DIR/data"
    API_KEY=$(grep '^  api_key:' "$CONFIG_FILE" | head -1 | awk -F': ' '{print $2}' | tr -d '"' | awk '{print $1}')
    PORT=$(grep '^  port:' "$CONFIG_FILE" | head -1 | awk -F': ' '{print $2}' | tr -d ' "' | cut -d'#' -f1)
else
    echo "配置文件不存在，使用测试默认路径"
    SOURCE_DIR="/tmp/nas_media_test/source"
    TEMP_DIR="/tmp/nas_media_test/temp"
    LOG_DIR="/tmp/nas_media_test/logs"
    DATA_DIR="$PROJECT_DIR/data"
    API_KEY=""
    PORT=9855
fi

PORT=${PORT:-9855}
API_KEY=${API_KEY:-}

echo ""
echo "清理目录:"
echo "  Source: ${SOURCE_DIR:-/tmp/nas_media_test/source}"
echo "  Temp:   ${TEMP_DIR:-/tmp/nas_media_test/temp}"
echo "  Logs:   ${LOG_DIR:-/tmp/nas_media_test/logs}"
if [ -n "$DATA_DIR" ]; then
    echo "  Data:   $DATA_DIR"
fi
echo "  Port:   $PORT"
if [ -n "$API_KEY" ]; then
    echo "  API Key: $API_KEY"
fi
echo ""

# 2. 杀掉旧进程
echo "[1/5] 停止旧进程..."
pkill -f "python.*media_importer" 2>/dev/null || true
pkill -f "python.*api_server" 2>/dev/null || true
sleep 1
pkill -9 -f "python.*media_importer" 2>/dev/null || true
pkill -9 -f "python.*api_server" 2>/dev/null || true
echo "  ✓ 已停止旧进程"

# 3. 清理测试数据
echo "[2/5] 清理测试数据..."

for dir in "$SOURCE_DIR" "$TEMP_DIR" "$LOG_DIR"; do
    if [ -n "$dir" ]; then
        rm -rf "$dir"
        mkdir -p "$dir"
        echo "  ✓ 已清理: $dir"
    fi
done

if [ -n "$DATA_DIR" ]; then
    rm -f "$DATA_DIR/tasks.json" "$DATA_DIR/tasks.db"
    echo "  ✓ 已清理: $DATA_DIR/tasks.json $DATA_DIR/tasks.db"
fi

# 4. 生成测试数据
echo "[3/5] 生成测试数据..."

if [ -n "$SOURCE_DIR" ]; then
    mkdir -p "$SOURCE_DIR"

    # ================================================================
    # 电影 - 普通电影 (media_type=movie, documentary=false, animation=false)
    # ================================================================

    # 盗梦空间 - 经典好莱坞电影，含中英字幕
    cat > "$SOURCE_DIR/Inception.2010.1080p.BluRay.mkv" <<'EOF'
测试文件 - 盗梦空间
EOF
    cat > "$SOURCE_DIR/Inception.2010.1080p.BluRay.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:04,000
你在等待一列火车...
EOF
    cat > "$SOURCE_DIR/Inception.2010.1080p.BluRay.en.srt" <<'EOF'
1
00:00:01,000 --> 00:00:04,000
You are waiting for a train...
EOF

    # 蝙蝠侠：黑暗骑士 - 含中文字幕
    cat > "$SOURCE_DIR/The.Dark.Knight.2008.720p.mkv" <<'EOF'
测试文件 - 蝙蝠侠：黑暗骑士
EOF
    cat > "$SOURCE_DIR/The.Dark.Knight.2008.720p.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
为什么这么严肃？
EOF

    # 星际穿越
    cat > "$SOURCE_DIR/Interstellar.2014.1080p.BluRay.mkv" <<'EOF'
测试文件 - 星际穿越
EOF

    # 沙丘2
    cat > "$SOURCE_DIR/Dune.Part.Two.2024.2160p.WEB-DL.mkv" <<'EOF'
测试文件 - 沙丘2
EOF
    cat > "$SOURCE_DIR/Dune.Part.Two.2024.2160p.WEB-DL.zh.ass" <<'EOF'
[Script Info]
Title: Dune Part Two Chinese
ScriptType: v4.00
EOF

    # ================================================================
    # 电影 - 纪录片 (documentary=true)
    # ================================================================

    # 地球脉动II - 纪录片电影版
    cat > "$SOURCE_DIR/Planet.Earth.II.2016.2160p.BluRay.mkv" <<'EOF'
测试文件 - 地球脉动II 纪录片电影
EOF
    cat > "$SOURCE_DIR/Planet.Earth.II.2016.2160p.BluRay.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:04,000
从一个岛屿开始...
EOF

    # 徒手攀岩 - 纪录片电影
    cat > "$SOURCE_DIR/Free.Solo.2018.1080p.mkv" <<'EOF'
测试文件 - 徒手攀岩 纪录片
EOF

    # ================================================================
    # 电影 - 动漫 (animation=true)
    # ================================================================

    # 千与千寻 - 日漫电影，含字幕
    cat > "$SOURCE_DIR/Spirited.Away.2001.1080p.BluRay.mkv" <<'EOF'
测试文件 - 千与千寻（宫崎骏动画电影）
EOF
    cat > "$SOURCE_DIR/Spirited.Away.2001.1080p.BluRay.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
千寻，不要回头
EOF

    # 寻梦环游记 - 皮克斯动画电影
    cat > "$SOURCE_DIR/Coco.2017.1080p.BluRay.mkv" <<'EOF'
测试文件 - 寻梦环游记（皮克斯动画电影）
EOF

    # 你的名字 - 日漫电影
    cat > "$SOURCE_DIR/Your.Name.2016.1080p.BluRay.mkv" <<'EOF'
测试文件 - 你的名字（新海诚动画电影）
EOF
    cat > "$SOURCE_DIR/Your.Name.2016.1080p.BluRay.zh.ass" <<'EOF'
[Script Info]
Title: Your Name Chinese
ScriptType: v4.00
EOF

    # ================================================================
    # 电影 - 限制级 (restricted_level=17+)
    # ================================================================

    # 死侍 - 限制级电影
    cat > "$SOURCE_DIR/Deadpool.2016.1080p.BluRay.mkv" <<'EOF'
测试文件 - 死侍（限制级 R级）
EOF
    cat > "$SOURCE_DIR/Deadpool.2016.1080p.BluRay.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
我是死侍
EOF

    # 小丑 - 限制级电影
    cat > "$SOURCE_DIR/Joker.2019.1080p.BluRay.mkv" <<'EOF'
测试文件 - 小丑（限制级 R级）
EOF

    # ================================================================
    # 电影 - 韩国/亚洲
    # ================================================================

    # 寄生虫 - 韩国电影
    cat > "$SOURCE_DIR/Parasite.2019.1080p.BluRay.mkv" <<'EOF'
测试文件 - 寄生虫（韩国电影）
EOF
    cat > "$SOURCE_DIR/Parasite.2019.1080p.BluRay.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
他们很有钱
EOF

    # 来自星星的你 - 韩剧电影版
    cat > "$SOURCE_DIR/My.Love.From.the.Star.2013.720p.mkv" <<'EOF'
测试文件 - 来自星星的你
EOF

    # ================================================================
    # 电影 - 未知/难以识别
    # ================================================================

    # 文件名信息不足
    cat > "$SOURCE_DIR/movie.unknown.file.mkv" <<'EOF'
测试文件 - 需要AI推断
EOF

    # 几乎无信息
    cat > "$SOURCE_DIR/video123.mp4" <<'EOF'
测试文件 - 几乎无信息
EOF

    # 纯数字文件名
    cat > "$SOURCE_DIR/2024.1080p.mkv" <<'EOF'
测试文件 - 纯数字年份文件名
EOF

    # ================================================================
    # 电视剧 - 普通美剧 (media_type=tv)
    # ================================================================

    # 绝命毒师 - 经典美剧，多集+字幕
    cat > "$SOURCE_DIR/Breaking.Bad.S01E01.Pilot.720p.BluRay.mkv" <<'EOF'
测试文件 - 绝命毒师 S01E01
EOF
    cat > "$SOURCE_DIR/Breaking.Bad.S01E01.Pilot.720p.BluRay.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
我是谁？我在哪里？
EOF
    cat > "$SOURCE_DIR/Breaking.Bad.S01E02.Mr.Chips.720p.BluRay.mkv" <<'EOF'
测试文件 - 绝命毒师 S01E02
EOF
    cat > "$SOURCE_DIR/Breaking.Bad.S01E03.Crazy.Handful.720p.BluRay.mkv" <<'EOF'
测试文件 - 绝命毒师 S01E03
EOF

    # 怪奇物语 - 美剧，含idx/sub图形字幕
    cat > "$SOURCE_DIR/Stranger.Things.S01E01.720p.WEB.mkv" <<'EOF'
测试文件 - 怪奇物语 S01E01
EOF
    cat > "$SOURCE_DIR/Stranger.Things.S01E01.720p.WEB.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
威尔去哪了？
EOF
    cat > "$SOURCE_DIR/Stranger.Things.S01E01.720p.WEB.idx" <<'EOF'
fake idx subtitle index
EOF
    cat > "$SOURCE_DIR/Stranger.Things.S01E01.720p.WEB.sub" <<'EOF'
fake sub subtitle data
EOF
    cat > "$SOURCE_DIR/Stranger.Things.S01E02.720p.WEB.mkv" <<'EOF'
测试文件 - 怪奇物语 S01E02
EOF

    # 权力的游戏 - 美剧
    cat > "$SOURCE_DIR/Game.of.Thrones.S01E01.Winter.Is.Coming.1080p.mkv" <<'EOF'
测试文件 - 权力的游戏 S01E01
EOF
    cat > "$SOURCE_DIR/Game.of.Thrones.S01E01.Winter.Is.Coming.1080p.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
凛冬将至
EOF
    cat > "$SOURCE_DIR/Game.of.Thrones.S01E02.The.Kingsroad.1080p.mkv" <<'EOF'
测试文件 - 权力的游戏 S01E02
EOF

    # ================================================================
    # 电视剧 - 纪录片 (documentary=true, tv)
    # ================================================================

    # 地球脉动II 电视剧版 - 纪录片电视剧
    mkdir -p "$SOURCE_DIR/地球脉动II_Planet_Earth_II"
    cat > "$SOURCE_DIR/地球脉动II_Planet_Earth_II/Planet.Earth.II.S01E01.Islands.2160p.mkv" <<'EOF'
测试文件 - 地球脉动II S01E01 纪录片电视剧
EOF
    cat > "$SOURCE_DIR/地球脉动II_Planet_Earth_II/Planet.Earth.II.S01E01.Islands.2160p.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:04,000
从一个岛屿开始...
EOF
    cat > "$SOURCE_DIR/地球脉动II_Planet_Earth_II/Planet.Earth.II.S01E02.Mountains.2160p.mkv" <<'EOF'
测试文件 - 地球脉动II S01E02 纪录片电视剧
EOF

    # ================================================================
    # 电视剧 - 动漫 (animation=true, tv)
    # ================================================================

    # 进击的巨人 - 日漫长篇动漫
    cat > "$SOURCE_DIR/Attack.on.Titan.S01E01.1080p.mkv" <<'EOF'
测试文件 - 进击的巨人 S01E01
EOF
    cat > "$SOURCE_DIR/Attack.on.Titan.S01E01.1080p.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
献出心脏！
EOF
    cat > "$SOURCE_DIR/Attack.on.Titan.S01E02.1080p.mkv" <<'EOF'
测试文件 - 进击的巨人 S01E02
EOF
    cat > "$SOURCE_DIR/Attack.on.Titan.S01E03.1080p.mkv" <<'EOF'
测试文件 - 进击的巨人 S01E03
EOF

    # 罗小黑战记 - 国漫
    mkdir -p "$SOURCE_DIR/罗小黑战记_The_Legend_of_Hei"
    cat > "$SOURCE_DIR/罗小黑战记_The_Legend_of_Hei/Luo.Xiao.Hei.Zhan.Ji.S01E01.1080p.mkv" <<'EOF'
测试文件 - 罗小黑战记 S01E01
EOF
    cat > "$SOURCE_DIR/罗小黑战记_The_Legend_of_Hei/Luo.Xiao.Hei.Zhan.Ji.S01E01.1080p.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
小黑！
EOF
    cat > "$SOURCE_DIR/罗小黑战记_The_Legend_of_Hei/Luo.Xiao.Hei.Zhan.Ji.S01E02.1080p.mkv" <<'EOF'
测试文件 - 罗小黑战记 S01E02
EOF

    # 鬼灭之刃 - 日漫
    cat > "$SOURCE_DIR/Demon.Slayer.S01E01.1080p.WEB-DL.mkv" <<'EOF'
测试文件 - 鬼灭之刃 S01E01
EOF
    cat > "$SOURCE_DIR/Demon.Slayer.S01E01.1080p.WEB-DL.zh.ass" <<'EOF'
[Script Info]
Title: Demon Slayer Chinese
ScriptType: v4.00
EOF
    cat > "$SOURCE_DIR/Demon.Slayer.S01E02.1080p.WEB-DL.mkv" <<'EOF'
测试文件 - 鬼灭之刃 S01E02
EOF

    # ================================================================
    # 电视剧 - 限制级 (restricted_level=17+, tv)
    # ================================================================

    # 黑镜 - 限制级电视剧
    cat > "$SOURCE_DIR/Black.Mirror.S01E01.The.National.Anthem.1080p.mkv" <<'EOF'
测试文件 - 黑镜 S01E01（限制级）
EOF
    cat > "$SOURCE_DIR/Black.Mirror.S01E02.Fifteen.Million.Merits.1080p.mkv" <<'EOF'
测试文件 - 黑镜 S01E02（限制级）
EOF

    # ================================================================
    # 电视剧 - 子目录递归测试
    # ================================================================

    # 西部世界 - 中文目录名
    mkdir -p "$SOURCE_DIR/西部世界_Westworld"
    cat > "$SOURCE_DIR/西部世界_Westworld/Westworld.S01E01.The.Original.1080p.mkv" <<'EOF'
测试文件 - 西部世界 S01E01
EOF
    cat > "$SOURCE_DIR/西部世界_Westworld/Westworld.S01E01.The.Original.1080p.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
这些暴力的欢愉终将以暴力结局
EOF
    cat > "$SOURCE_DIR/西部世界_Westworld/Westworld.S01E02.Chestnut.1080p.mkv" <<'EOF'
测试文件 - 西部世界 S01E02
EOF

    # 最后的我们 - 子目录
    mkdir -p "$SOURCE_DIR/The_Last_of_Us"
    cat > "$SOURCE_DIR/The_Last_of_Us/The.Last.of.Us.S01E01.1080p.WEB-DL.mkv" <<'EOF'
测试文件 - 最后的我们 S01E01
EOF
    cat > "$SOURCE_DIR/The_Last_of_Us/The.Last.of.Us.S01E01.1080p.WEB-DL.zh.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
如果你不知道往哪走，就别走
EOF

    # ================================================================
    # 干扰文件 - 不应被处理的文件
    # ================================================================

    # NFO 元数据文件
    cat > "$SOURCE_DIR/Inception.2010.1080p.BluRay.nfo" <<'EOF'
<?xml version="1.0"?><movie><title>Inception</title></movie>
EOF

    # 海报图片
    cat > "$SOURCE_DIR/Inception.2010.1080p.BluRay-poster.jpg" <<'EOF'
fake poster image
EOF

    # 缩略图
    cat > "$SOURCE_DIR/Inception.2010.1080p.BluRay-thumb.jpg" <<'EOF'
fake thumb image
EOF

    # 子目录中的附属文件
    cat > "$SOURCE_DIR/西部世界_Westworld/Westworld.S01E01.The.Original.nfo" <<'EOF'
<?xml version="1.0"?><episodedetails><title>The Original</title></episodedetails>
EOF
    cat > "$SOURCE_DIR/西部世界_Westworld/Westworld.S01E01.The.Original-thumb.jpg" <<'EOF'
fake episode thumb
EOF

    # 独立干扰文件（无对应视频）
    cat > "$SOURCE_DIR/README.txt" <<'EOF'
这是说明文件，不应被删除
EOF
    cat > "$SOURCE_DIR/西部世界_Westworld/fanart.jpg" <<'EOF'
fake fanart
EOF

    # DS_Store
    cat > "$SOURCE_DIR/.DS_Store" <<'EOF'
fake DS_Store
EOF

    # 隐藏目录（应被跳过）
    mkdir -p "$SOURCE_DIR/.hidden_dir"
    cat > "$SOURCE_DIR/.hidden_dir/Some.Movie.2020.mkv" <<'EOF'
隐藏目录中的视频，不应被扫描
EOF

    # 统计
    VIDEO_COUNT=$(find "$SOURCE_DIR" -name "*.mkv" -o -name "*.mp4" -o -name "*.ts" -o -name "*.avi" 2>/dev/null | grep -v '.hidden_dir' | wc -l | tr -d ' ')
    SUB_COUNT=$(find "$SOURCE_DIR" -name "*.srt" -o -name "*.ass" -o -name "*.idx" -o -name "*.sub" 2>/dev/null | wc -l | tr -d ' ')
    echo "  ✓ 已生成 $VIDEO_COUNT 个测试视频, $SUB_COUNT 个字幕文件"
fi

# 5. 确保配置文件存在（与测试目录路径一致）
echo "[4/5] 准备配置文件..."
if [ ! -f "$CONFIG_FILE" ]; then
    mkdir -p "$(dirname "$CONFIG_FILE")"
    QUARANTINE_DIR="$DATA_DIR/quarantine"
    cat > "$CONFIG_FILE" <<YAML_EOF
file_watcher:
  enabled: true
  poll_interval: 10
  ignore_patterns:
    - "*.tmp"
    - ".DS_Store"
server:
  host: "0.0.0.0"
  port: $PORT
  api_key: ""
source_dir: "$SOURCE_DIR"
temp_dir: "$TEMP_DIR"
log_dir: "$LOG_DIR"
source_policy:
  dedup_enabled: true
  quarantine_dir: "$QUARANTINE_DIR"
  max_auto_retries: 3
  scan_recursive: true
  scan_max_depth: 5
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
  - ".vtt"
  - ".sub"
dimensions:
  - name: media_type
    label: 影视类型
    values: ["movie", "tv"]
    ai_prompt: "请判断这是电影还是电视剧（movie/tv）"
  - name: documentary
    label: 是否纪录片
    values: ["true", "false"]
    ai_prompt: "请判断是否为纪录片（true/false）"
  - name: animation
    label: 是否动漫
    values: ["true", "false"]
    ai_prompt: "请判断是否为动漫/动画作品（true/false）"
  - name: restricted_level
    label: 限制级分类
    values: ["0-6", "7-12", "13-15", "17+"]
    ai_prompt: "请判断内容的年龄分级"
path_rules:
  - conditions: {}
    template: "$TEMP_DIR/影视/其他/{title_cn} ({year})/"
filename_templates:
  movie: "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}"
  tv: "{title_cn}.{title_en}.{year}.S{season:02d}E{episode:02d}.{resolution}.{quality}.{ext}"
  subtitle: "{video_filename}.{lang}.{ext}"
duplicate_handling:
  enabled: true
  strategy: "quality"
manual_review:
  enabled: false
llm:
  provider: "openai"
  api_key: ""
  base_url: "https://api.openai.com/v1"
  model: "gpt-3.5-turbo"
  timeout: 30
  max_retries: 2
  retry_delay: 3
  fallback_model: "gpt-3.5-turbo"
  confidence_threshold: 0.8
  verify_ssl: true
hermes:
  enabled: false
task_queue:
  max_concurrent: 1
logging:
  level: "INFO"
  format: "json"
YAML_EOF
    echo "  ✓ 已生成测试配置: $CONFIG_FILE"
else
    echo "  ✓ 使用已有配置: $CONFIG_FILE"
fi

# 6. 重启服务
echo "[5/5] 启动服务..."
cd "$PROJECT_DIR"
nohup python3 -B media_importer/media_importer.py -c "$CONFIG_FILE" serve -p "$PORT" --host 0.0.0.0 > /dev/null 2>&1 &
SERVER_PID=$!

echo "  等待服务启动..."
sleep 3

if lsof -ti:"$PORT" > /dev/null 2>&1; then
    RUNNING_PID=$(lsof -ti:"$PORT" | head -1)
    echo "  ✓ 服务已启动 (PID: $RUNNING_PID)"
else
    echo "  ✗ 服务启动失败，请检查日志"
    exit 1
fi

# 6. 显示信息
echo ""
echo "========================================"
echo " 重启完成！"
echo "========================================"
echo ""
echo "服务地址: http://localhost:$PORT"
echo ""
if [ -n "$API_KEY" ]; then
    echo "⚠️  API Key 认证已启用，浏览器首次访问需输入 Key: $API_KEY"
    echo "   或 curl 请求加 -H 'Authorization: Bearer $API_KEY'"
    echo ""
fi
echo "测试数据目录: $SOURCE_DIR"
echo ""
echo "测试数据覆盖场景:"
echo "  电影: 普通/纪录片/动漫(日漫/欧美)/限制级(17+)/韩国/未知"
echo "  电视剧: 普通/纪录片/动漫(日漫/国漫)/限制级(17+)/子目录"
echo "  字幕: .srt(中/英)/.ass/.idx+.sub"
echo "  干扰: .nfo/.jpg/.txt/.DS_Store/隐藏目录"
echo ""
echo "常用命令:"
if [ -n "$API_KEY" ]; then
    echo "  查询任务: curl -H 'Authorization: Bearer $API_KEY' http://localhost:$PORT/api/tasks?format=text"
    echo "  触发处理: curl -X POST -H 'Authorization: Bearer $API_KEY' http://localhost:$PORT/api/run"
else
    echo "  查询任务: curl http://localhost:$PORT/api/tasks?format=text"
    echo "  触发处理: curl -X POST http://localhost:$PORT/api/run"
fi
echo ""

#!/bin/bash
# NAS影视入库系统 - 测试环境重启脚本
# 功能：清理测试数据、杀进程、重启服务

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
    PERSISTENCE_PATH=$(grep '^  persistence_path:' "$CONFIG_FILE" | head -1 | awk -F': ' '{print $2}' | tr -d '"')
    
    # 处理相对路径
    if [ -n "$PERSISTENCE_PATH" ] && [[ "$PERSISTENCE_PATH" != /* ]]; then
        PERSISTENCE_PATH="$PROJECT_DIR/$PERSISTENCE_PATH"
        PERSISTENCE_DIR=$(dirname "$PERSISTENCE_PATH")
    fi
else
    echo "警告: 配置文件 $CONFIG_FILE 不存在，使用默认路径"
    SOURCE_DIR="/tmp/nas_media_test/source"
    TEMP_DIR="/tmp/nas_media_test/temp"
    LOG_DIR="/tmp/nas_media_test/logs"
    PERSISTENCE_DIR="$PROJECT_DIR/data"
fi

echo ""
echo "清理目录:"
echo "  Source: ${SOURCE_DIR:-/tmp/nas_media_test/source}"
echo "  Temp:   ${TEMP_DIR:-/tmp/nas_media_test/temp}"
echo "  Logs:   ${LOG_DIR:-/tmp/nas_media_test/logs}"
if [ -n "$PERSISTENCE_DIR" ]; then
    echo "  Data:   $PERSISTENCE_DIR"
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

# 清理并重建目录
for dir in "$SOURCE_DIR" "$TEMP_DIR" "$LOG_DIR"; do
    if [ -n "$dir" ]; then
        rm -rf "$dir"
        mkdir -p "$dir"
        echo "  ✓ 已清理: $dir"
    fi
done

# 清理 persistence 数据
if [ -n "$PERSISTENCE_PATH" ] && [ -f "$PERSISTENCE_PATH" ]; then
    rm -f "$PERSISTENCE_PATH"
    echo "  ✓ 已清理: $PERSISTENCE_PATH"
fi

# 4. 生成测试数据
echo "[3/5] 生成测试数据..."

if [ -n "$SOURCE_DIR" ]; then
    mkdir -p "$SOURCE_DIR"
    
    # 电影样例
    cat > "$SOURCE_DIR/Inception.2010.1080p.BluRay.mkv" <<EOF
测试文件 - 盗梦空间
EOF
    cat > "$SOURCE_DIR/Inception.2010.1080p.BluRay.zh.srt" <<EOF
1
00:00:01,000 --> 00:00:04,000
你在等待一列火车...
EOF
    cat > "$SOURCE_DIR/Inception.2010.1080p.BluRay.en.srt" <<EOF
1
00:00:01,000 --> 00:00:04,000
You are waiting for a train...
EOF

    # 电视剧样例
    cat > "$SOURCE_DIR/Breaking.Bad.S01E01.Pilot.mkv" <<EOF
测试文件 - 绝命毒师 S01E01
EOF
    cat > "$SOURCE_DIR/Breaking.Bad.S01E01.Pilot.zh.srt" <<EOF
1
00:00:01,000 --> 00:00:03,000
我是谁？我在哪里？
EOF

    cat > "$SOURCE_DIR/Breaking.Bad.S01E02.Mr.Chips.mkv" <<EOF
测试文件 - 绝命毒师 S01E02
EOF

    # 另一部电影
    cat > "$SOURCE_DIR/The.Dark.Knight.2008.720p.mkv" <<EOF
测试文件 - 蝙蝠侠：黑暗骑士
EOF
    cat > "$SOURCE_DIR/The.Dark.Knight.2008.720p.zh.srt" <<EOF
1
00:00:01,000 --> 00:00:03,000
为什么这么严肃？
EOF

    # 纪录片样例
    cat > "$SOURCE_DIR/Planet.Earth.II.S01E01.2160p.mkv" <<EOF
测试文件 - 地球脉动II S01E01
EOF
    cat > "$SOURCE_DIR/Planet.Earth.II.S01E01.2160p.zh.srt" <<EOF
1
00:00:01,000 --> 00:00:04,000
从一个岛屿开始...
EOF

    # 未知/需要刮削的样例（文件名信息不足）
    cat > "$SOURCE_DIR/movie.unknown.file.mkv" <<EOF
测试文件 - 需要AI推断
EOF

    cat > "$SOURCE_DIR/video123.mp4" <<EOF
测试文件 - 几乎无信息
EOF

    # 美剧样例
    cat > "$SOURCE_DIR/Stranger.Things.S01E01.720p.WEB.mkv" <<EOF
测试文件 - 怪奇物语 S01E01
EOF
    cat > "$SOURCE_DIR/Stranger.Things.S01E01.720p.WEB.zh.srt" <<EOF
1
00:00:01,000 --> 00:00:03,000
威尔去哪了？
EOF

    cat > "$SOURCE_DIR/Stranger.Things.S01E02.720p.WEB.mkv" <<EOF
测试文件 - 怪奇物语 S01E02
EOF

    # 韩剧样例（测试中文字符）
    cat > "$SOURCE_DIR/My.Love.From.the.Star.2013.720p.mkv" <<EOF
测试文件 - 来星星的你
EOF

    # 子目录递归测试（电视剧多集放子文件夹）
    mkdir -p "$SOURCE_DIR/西部世界_Westworld"
    cat > "$SOURCE_DIR/西部世界_Westworld/Westworld.S01E01.mkv" <<EOF
测试文件 - 西部世界 S01E01
EOF
    cat > "$SOURCE_DIR/西部世界_Westworld/Westworld.S01E01.zh.srt" <<EOF
1
00:00:01,000 --> 00:00:03,000
这些暴力的欢愉终将以暴力结局
EOF
    cat > "$SOURCE_DIR/西部世界_Westworld/Westworld.S01E02.mkv" <<EOF
测试文件 - 西部世界 S01E02
EOF

    FILE_COUNT=$(ls -1 "$SOURCE_DIR"/*.mkv "$SOURCE_DIR"/*.mp4 "$SOURCE_DIR"/**/*.mkv "$SOURCE_DIR"/**/*.mp4 2>/dev/null | wc -l | tr -d ' ')
    echo "  ✓ 已生成 $FILE_COUNT 个测试视频"
fi

# 5. 重启服务
echo "[4/5] 启动服务..."
cd "$PROJECT_DIR"
nohup python3 -B media_importer/media_importer.py -c "$CONFIG_FILE" serve -p 9855 --host 0.0.0.0 > /dev/null 2>&1 &
SERVER_PID=$!

# 等待服务启动
echo "  等待服务启动..."
sleep 3

# 检查服务是否启动成功 - 使用端口检查
if lsof -ti:9855 > /dev/null 2>&1; then
    RUNNING_PID=$(lsof -ti:9855 | head -1)
    echo "  ✓ 服务已启动 (PID: $RUNNING_PID)"
else
    echo "  ✗ 服务启动失败，请检查"
    exit 1
fi

# 6. 显示信息
echo ""
echo "========================================"
echo " 重启完成！"
echo "========================================"
echo ""
echo "服务地址: http://localhost:9855"
echo "API文档:  http://localhost:9855/help"
echo ""
echo "测试数据目录: $SOURCE_DIR"
echo ""
echo "常用命令:"
echo "  查询任务: curl http://localhost:9855/api/tasks?format=text"
echo "  触发处理: curl -X POST http://localhost:9855/api/run"
echo ""

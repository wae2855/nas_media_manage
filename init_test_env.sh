#!/bin/bash
# init_test_env.sh — 初始化测试环境
# 用法: bash init_test_env.sh

set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

# 创建测试目录
mkdir -p "$BASE_DIR/tests/fixtures/source"
mkdir -p "$BASE_DIR/tests/fixtures/temp"
mkdir -p "$BASE_DIR/tests/fixtures/import"
mkdir -p "$BASE_DIR/tests/fixtures/logs"

# 切换到源目录创建测试文件
cd "$BASE_DIR/tests/fixtures/source"

echo "创建测试影视文件..."

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
    echo "  movie: ${movie}.mkv"
done

# Inception 无字幕
rm -f "Inception.2010.1080p.BluRay.x264.zh.srt"

# Pulp Fiction 多语言字幕
cp "Pulp.Fiction.1994.720p.BDRip.x264.zh.srt" "Pulp.Fiction.1994.720p.BDRip.x264.en.srt"

echo ""
echo "创建测试电视剧文件..."

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
    echo "  tv: ${tv}.mkv"
done

# Game of Thrones 多语言字幕
touch "Game.of.Thrones.S01E01.2160p.HDR.x265.en.srt"
touch "Game.of.Thrones.S01E01.2160p.HDR.x265.ja.srt"

echo ""
echo "创建测试纪录片文件..."

touch "Planet.Earth.II.2016.2160p.BluRay.x265.mkv"
touch "Planet.Earth.II.2016.2160p.BluRay.x265.zh.srt"
touch "Planet.Earth.II.2016.2160p.BluRay.x265.en.srt"
echo "  doc: Planet.Earth.II.2016.2160p.BluRay.x265.mkv"

touch "Cosmos.A.Spacetime.Odyssey.2014.1080p.BluRay.x264.mkv"
touch "Cosmos.A.Spacetime.Odyssey.2014.1080p.BluRay.x264.zh.srt"
echo "  doc: Cosmos.A.Spacetime.Odyssey.2014.1080p.BluRay.x264.mkv"

echo ""
echo "创建干扰文件（应被忽略）..."
touch "test.tmp"
touch ".DS_Store"
touch "download.partial.mkv"

VIDEO_COUNT=$(find . -maxdepth 1 \( -name "*.mkv" -o -name "*.mp4" \) | wc -l | tr -d ' ')
SUB_COUNT=$(find . -maxdepth 1 \( -name "*.srt" -o -name "*.ass" -o -name "*.ssa" \) | wc -l | tr -d ' ')

echo ""
echo "========================================="
echo "  测试环境初始化完成"
echo "========================================="
echo "  视频文件: ${VIDEO_COUNT} 个"
echo "  字幕文件: ${SUB_COUNT} 个"
echo "  源目录:   $BASE_DIR/tests/fixtures/source"
echo "  临时目录: $BASE_DIR/tests/fixtures/temp"
echo "  入库目录: $BASE_DIR/tests/fixtures/import"
echo "  日志目录: $BASE_DIR/tests/fixtures/logs"
echo "========================================="

#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${1:-$SCRIPT_DIR/config/config.yaml}"
HOST="${2:-0.0.0.0}"
PORT="${3:-9855}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

get_port_pids() {
    local port=$1
    if command -v lsof &>/dev/null; then
        lsof -ti :"$port" 2>/dev/null
    fi
}

port_check_with_message() {
    local port=$1
    local pids=$(get_port_pids "$port")
    if [ -n "$pids" ]; then
        log_warn "端口 $port 已被占用（PID: $pids）"
        if [ -t 0 ]; then
            read -p "是否自动清理占用进程？(Y/n): " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ || $REPLY == "" ]]; then
                kill -9 $pids 2>/dev/null || true
                sleep 1
                log_info "端口已释放"
            else
                log_error "请手动关闭占用进程或使用其他端口"
                echo "  使用其他端口: $0 $CONFIG $HOST <新端口>"
                exit 1
            fi
        else
            log_info "自动清理端口 $port"
            kill -9 $pids 2>/dev/null || true
            sleep 1
        fi
    fi
}

check_config() {
    if [ ! -f "$CONFIG" ]; then
        log_error "配置文件不存在: $CONFIG"
        exit 1
    fi
}

check_python() {
    if ! command -v python3 &>/dev/null; then
        log_error "未找到 python3"
        exit 1
    fi
}

health_check() {
    local port=$1
    local max_retries=15
    local i=0
    while [ $i -lt $max_retries ]; do
        if command -v curl &>/dev/null; then
            if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$port/api/health" >/dev/null 2>&1; then
                return 0
            fi
        fi
        i=$((i + 1))
        sleep 1
    done
    return 1
}

echo "========================================"
echo "  影音库AI智能整理 - 服务启动"
echo "========================================"
echo ""

check_python
check_config
port_check_with_message "$PORT"

log_info "配置文件: $CONFIG"
log_info "监听地址: $HOST:$PORT"
echo ""

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

python3 -m media_importer.media_importer -c "$CONFIG" serve -p "$PORT" --host "$HOST" &
SERVER_PID=$!

log_info "服务进程 PID: $SERVER_PID"

if health_check "$PORT"; then
    log_info "服务启动成功!"
    echo ""
    echo "  API 地址: http://$HOST:$PORT"
    if command -v curl &>/dev/null; then
        echo "  健康检查: curl -s http://127.0.0.1:$PORT/api/health"
    fi
    echo "  停止服务: kill $SERVER_PID"
    echo ""
else
    log_error "服务启动失败，请检查日志"
    kill "$SERVER_PID" 2>/dev/null || true
    exit 1
fi

wait "$SERVER_PID"

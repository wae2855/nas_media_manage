#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${1:-$SCRIPT_DIR/media_importer/config.yaml}"
HOST="${2:-0.0.0.0}"
PORT="${3:-9855}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_port() {
    local port=$1
    if lsof -ti :"$port" >/dev/null 2>&1; then
        local pid
        pid=$(lsof -ti :"$port")
        local cmd
        cmd=$(ps -p "$pid" -o command= 2>/dev/null || echo "unknown")
        log_error "端口 $port 已被占用 (PID: $pid, 命令: $cmd)"
        echo ""
        echo "  选项:"
        echo "    1) 终止占用进程并继续: kill -9 $pid"
        echo "    2) 使用其他端口: $0 $CONFIG $HOST <新端口>"
        echo ""
        read -rp "是否终止占用进程? [y/N] " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            kill -9 "$pid" 2>/dev/null || true
            sleep 1
            if lsof -ti :"$port" >/dev/null 2>&1; then
                log_error "无法释放端口 $port"
                exit 1
            fi
            log_info "端口 $port 已释放"
        else
            log_error "启动取消"
            exit 1
        fi
    fi
}

check_config() {
    if [[ ! -f "$CONFIG" ]]; then
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
    local max_retries=10
    local i=0
    while [[ $i -lt $max_retries ]]; do
        if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$port/api/health" >/dev/null 2>&1; then
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done
    return 1
}

echo "========================================"
echo "  NAS影视自动化入库系统 - 服务启动"
echo "========================================"
echo ""

check_python
check_config
check_port "$PORT"

log_info "配置文件: $CONFIG"
log_info "监听地址: $HOST:$PORT"
echo ""

python3 "$SCRIPT_DIR/media_importer/media_importer.py" -c "$CONFIG" serve -p "$PORT" --host "$HOST" &
SERVER_PID=$!

log_info "服务进程 PID: $SERVER_PID"

if health_check "$PORT"; then
    log_info "服务启动成功!"
    echo ""
    echo "  API 地址: http://$HOST:$PORT"
    echo "  健康检查: curl -s http://127.0.0.1:$PORT/api/health"
    echo "  停止服务: kill $SERVER_PID"
    echo ""
else
    log_error "服务启动失败，请检查日志"
    kill "$SERVER_PID" 2>/dev/null || true
    exit 1
fi

wait "$SERVER_PID"

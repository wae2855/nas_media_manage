#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${1:-$SCRIPT_DIR/config/config.yaml}"
HOST="${2:-0.0.0.0}"
PORT="${3:-9855}"
PYTHON_VERSION_FILE="$SCRIPT_DIR/.python-version"
LOG_DIR="${MEDIA_IMPORTER_LOG_DIR:-$SCRIPT_DIR/logs}"
START_LOG="$LOG_DIR/start.log"
REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=12
PYTHON_BIN=""

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
        lsof -ti :"$port" 2>/dev/null || true
    fi
}

port_check_with_message() {
    local port=$1
    local pids=""
    pids="$(get_port_pids "$port" || true)"
    pids="$(echo "$pids" | tr '\n' ' ' | sed 's/^ *//;s/ *$//')"
    if [ -n "$pids" ]; then
        log_warn "端口 $port 已被占用（PID: $pids），自动清理..."
        kill -9 $pids 2>/dev/null || true
        sleep 1
        log_info "端口已释放"
    fi
}

check_config() {
    if [ ! -f "$CONFIG" ]; then
        log_error "配置文件不存在: $CONFIG"
        log_info "请先创建配置文件: cp config/config.yaml.example config/config.yaml"
        log_info "或显式指定: $0 <配置文件路径>"
        exit 1
    fi
}

check_python() {
    resolve_python_bin
    if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
        log_error "未找到可用的 Python 解释器"
        log_info "可先执行: ./scripts/bootstrap_python_env.sh"
        exit 1
    fi

    if ! "$PYTHON_BIN" -c "import sys; raise SystemExit(0 if sys.version_info >= (${REQUIRED_PYTHON_MAJOR}, ${REQUIRED_PYTHON_MINOR}) else 1)" 2>/dev/null; then
        log_error "当前解释器版本过低: $("$PYTHON_BIN" --version 2>&1)"
        log_error "项目当前要求 Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}+"
        log_info "已选用的解释器: $PYTHON_BIN"
        log_info "请安装 Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}+，或执行: ./scripts/bootstrap_python_env.sh"
        exit 1
    fi
}

resolve_python_bin() {
    if [ -n "${MEDIA_IMPORTER_PYTHON_BIN:-}" ] && [ -x "${MEDIA_IMPORTER_PYTHON_BIN}" ]; then
        PYTHON_BIN="${MEDIA_IMPORTER_PYTHON_BIN}"
        return
    fi

    if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
        PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
        return
    fi

    if [ -f "$PYTHON_VERSION_FILE" ] && command -v pyenv &>/dev/null; then
        local pyenv_version=""
        pyenv_version="$(tr -d '[:space:]' < "$PYTHON_VERSION_FILE" 2>/dev/null || true)"
        if [ -n "$pyenv_version" ]; then
            PYTHON_BIN="$(env PYENV_VERSION="$pyenv_version" pyenv which python3 2>/dev/null || true)"
            if [ -n "$PYTHON_BIN" ] && [ -x "$PYTHON_BIN" ]; then
                return
            fi
        fi
    fi

    local candidate
    for candidate in python3.12 python3.13 python3; do
        if command -v "$candidate" &>/dev/null; then
            local resolved
            resolved="$(command -v "$candidate")"
            if [ -x "$resolved" ]; then
                PYTHON_BIN="$resolved"
                return
            fi
        fi
    done
}

health_check() {
    local port=$1
    local max_retries=20
    local i=0
    while [ $i -lt $max_retries ]; do
        if command -v curl &>/dev/null; then
            if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$port/api/health" >/dev/null 2>&1; then
                return 0
            fi
        elif command -v wget &>/dev/null; then
            if wget -q -T 5 -O /dev/null "http://127.0.0.1:$port/api/health" 2>/dev/null; then
                return 0
            fi
        else
            if "$PYTHON_BIN" - <<'PY' "$port" 2>/dev/null
import socket, sys
p = int(sys.argv[1])
s = socket.socket()
s.settimeout(2)
try:
    s.connect(("127.0.0.1", p))
    sys.exit(0)
except Exception:
    sys.exit(1)
PY
            then
                return 0
            fi
        fi
        i=$((i + 1))
        sleep 1
    done
    return 1
}

print_last_log_lines() {
    local lines="${1:-30}"
    if [ -f "$START_LOG" ]; then
        log_warn "服务启动日志末尾（最近 ${lines} 行）:"
        echo "----------------------------------------"
        tail -n "$lines" "$START_LOG" || true
        echo "----------------------------------------"
        log_info "完整日志: $START_LOG"
    else
        log_warn "未找到启动日志: $START_LOG"
    fi
}

echo "========================================"
echo "  影音库AI智能整理 - 服务启动"
echo "========================================"
echo ""

mkdir -p "$LOG_DIR"
: > "$START_LOG"

check_python
check_config
port_check_with_message "$PORT"

log_info "配置文件: $CONFIG"
log_info "监听地址: $HOST:$PORT"
log_info "Python 解释器: $PYTHON_BIN"
log_info "启动日志: $START_LOG"
echo ""

export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

"$PYTHON_BIN" -u -m media_importer.media_importer -c "$CONFIG" serve -p "$PORT" --host "$HOST" \
    >>"$START_LOG" 2>&1 &
SERVER_PID=$!

log_info "服务进程 PID: $SERVER_PID"

if health_check "$PORT"; then
    log_info "服务启动成功!"
    echo ""
    echo "  API 地址: http://$HOST:$PORT"
    echo "  健康检查: http://127.0.0.1:$PORT/api/health"
    echo "  停止服务: kill $SERVER_PID"
    echo "  实时日志: tail -f $START_LOG"
    echo ""
else
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        log_error "健康检查超时（20 秒），服务仍在运行但 /api/health 不可达"
    else
        log_error "服务进程已退出（崩溃），PID: $SERVER_PID"
    fi
    print_last_log_lines 30
    kill "$SERVER_PID" 2>/dev/null || true
    exit 1
fi

wait "$SERVER_PID" || true

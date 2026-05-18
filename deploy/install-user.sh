#!/bin/bash
set -euo pipefail

DEPLOY_DIR="${HOME}/nas-media-importer"
CONFIG_TEMPLATE="${DEPLOY_DIR}/config/config.yaml"
CONFIG_FILE="${DEPLOY_DIR}/config/config.yaml"
DATA_DIR="${DEPLOY_DIR}/data"
LOG_DIR="${DEPLOY_DIR}/logs"
SERVICE_FILE="${HOME}/.config/systemd/user/nas-media-importer.service"
HEALTH_PORT=9855
HEALTH_MAX_WAIT=30

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

NON_INTERACTIVE=false

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${CYAN}${BOLD}>>> $1${NC}"; }

prompt_yesno() {
    local question="$1"
    local default="${2:-Y}"
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        [[ "$default" =~ ^[Yy] ]] && return 0 || return 1
    fi
    local prompt
    if [[ "$default" =~ ^[Yy] ]]; then
        prompt="[Y/n]"
    else
        prompt="[y/N]"
    fi
    while true; do
        echo -ne "${YELLOW}${question} ${prompt}: ${NC}"
        read -r answer
        answer="${answer:-$default}"
        case "$answer" in
            [Yy]*) return 0 ;;
            [Nn]*) return 1 ;;
            *) echo "  请输入 y 或 n" ;;
        esac
    done
}

prompt_input() {
    local question="$1"
    local default="$2"
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        echo "$default"
        return
    fi
    echo -ne "${CYAN}${question} [${default}]: ${NC}"
    read -r answer
    echo "${answer:-$default}"
}

check_not_root() {
    if [[ "$(id -u)" -eq 0 ]]; then
        log_error "此脚本不建议使用 root 用户运行"
        log_info "请使用普通用户运行，或使用 install.sh 安装系统服务"
        if prompt_yesno "是否继续以 root 运行？" "N"; then
            log_warn "继续以 root 运行..."
            return 0
        fi
        exit 1
    fi
}

check_systemd_user() {
    if systemctl --user status &>/dev/null; then
        return 0
    fi
    return 1
}

ensure_python3() {
    if command -v python3 &>/dev/null; then
        log_info "已找到 Python3: $(python3 --version 2>&1 | awk '{print $2}')"
        return 0
    fi

    log_error "未找到 Python3，请先安装"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  CentOS/RHEL:   sudo yum install python3 python3-pip"
    exit 1
}

ensure_venv() {
    if [[ -d "${DEPLOY_DIR}/venv" && -x "${DEPLOY_DIR}/venv/bin/python3" ]]; then
        log_info "虚拟环境已存在"
        return 0
    fi

    log_step "创建 Python 虚拟环境"
    python3 -m venv "${DEPLOY_DIR}/venv"
    "${DEPLOY_DIR}/venv/bin/pip" install --quiet --upgrade pip
    log_info "虚拟环境创建完成"
}

install_dependencies() {
    log_step "安装 Python 依赖"
    if [[ ! -f "${DEPLOY_DIR}/requirements.txt" ]]; then
        log_error "未找到依赖文件: ${DEPLOY_DIR}/requirements.txt"
        exit 1
    fi
    "${DEPLOY_DIR}/venv/bin/pip" install --quiet -r "${DEPLOY_DIR}/requirements.txt"
    log_info "依赖安装完成"
}

setup_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        log_info "配置文件已存在: ${CONFIG_FILE}"
        return 0
    fi

    if [[ ! -f "$CONFIG_TEMPLATE" ]]; then
        log_error "未找到配置模板: ${CONFIG_TEMPLATE}"
        exit 1
    fi

    log_step "初始化配置文件"
    mkdir -p "$DATA_DIR" "$LOG_DIR"
    cp "$CONFIG_TEMPLATE" "$CONFIG_FILE"
    echo '{}' > "${DATA_DIR}/tasks.json"
    log_info "已创建配置文件: ${CONFIG_FILE}"

    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        log_warn "非交互模式：请编辑 ${CONFIG_FILE} 配置必要的参数"
        return 0
    fi

    echo ""
    echo -e "${BOLD}以下为关键配置项，请逐一确认：${NC}"
    echo ""

    local source_dir temp_dir api_key base_url model

    source_dir=$(prompt_input "源文件目录" "${HOME}/下载")
    temp_dir=$(prompt_input "临时目录" "${HOME}/nas-media-importer/temp")
    api_key=$(prompt_input "LLM API Key" "your-api-key-here")
    base_url=$(prompt_input "LLM API Base URL" "https://api.openai.com/v1")
    model=$(prompt_input "LLM 模型名称" "gpt-4o")

    if command -v sed &>/dev/null; then
        sed -i "s|source_dir:.*|source_dir: \"${source_dir}\"|" "$CONFIG_FILE"
        sed -i "s|temp_dir:.*|temp_dir: \"${temp_dir}\"|" "$CONFIG_FILE"
        sed -i "s|api_key:.*|api_key: \"${api_key}\"|" "$CONFIG_FILE"
        sed -i "s|base_url:.*|base_url: \"${base_url}\"|" "$CONFIG_FILE"
        sed -i "s|model:.*|model: \"${model}\"|" "$CONFIG_FILE"
        sed -i "s|log_dir:.*|log_dir: \"${LOG_DIR}\"|" "$CONFIG_FILE"
    fi

    log_info "配置已更新"
}

install_systemd_user() {
    log_step "安装 systemd 用户服务"

    mkdir -p "${HOME}/.config/systemd/user"

    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=NAS Media Importer - Auto import video files
After=network.target

[Service]
Type=simple
WorkingDirectory=${DEPLOY_DIR}
Environment=PATH=${DEPLOY_DIR}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart=${DEPLOY_DIR}/venv/bin/python3 media_importer/media_importer.py serve -p ${HEALTH_PORT} --host 0.0.0.0
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

    log_info "systemd 用户服务已创建: ${SERVICE_FILE}"
}

start_service() {
    log_step "启动服务并验证"

    systemctl --user daemon-reload
    systemctl --user enable nas-media-importer.service
    systemctl --user restart nas-media-importer.service

    log_info "等待服务启动..."
    local waited=0
    while [[ $waited -lt $HEALTH_MAX_WAIT ]]; do
        if systemctl --user is-active --quiet nas-media-importer.service; then
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done

    if ! systemctl --user is-active --quiet nas-media-importer.service; then
        log_error "服务启动失败"
        echo ""
        journalctl --user -u nas-media-importer -n 30 --no-pager
        exit 1
    fi

    log_info "服务进程已启动，检查健康状态..."

    if command -v curl &>/dev/null; then
        local health_ok=false
        waited=0
        while [[ $waited -lt $HEALTH_MAX_WAIT ]]; do
            if curl -sf --connect-timeout 2 --max-time 5 \
                "http://127.0.0.1:${HEALTH_PORT}/api/health" >/dev/null 2>&1; then
                health_ok=true
                break
            fi
            sleep 1
            waited=$((waited + 1))
        done

        if [[ "$health_ok" == "true" ]]; then
            log_info "健康检查通过"
        else
            log_warn "健康检查未通过（服务可能仍在初始化）"
        fi
    fi
}

print_success() {
    echo ""
    echo -e "${GREEN}${BOLD}========================================${NC}"
    echo -e "${GREEN}${BOLD}  部署完成！${NC}"
    echo -e "${GREEN}${BOLD}========================================${NC}"
    echo ""
    echo "  部署目录:    ${DEPLOY_DIR}"
    echo "  配置文件:    ${CONFIG_FILE}"
    echo "  数据目录:    ${DATA_DIR}"
    echo "  日志目录:    ${LOG_DIR}"
    echo ""
    echo "  常用命令:"
    echo "    启动服务:   systemctl --user start nas-media-importer"
    echo "    停止服务:   systemctl --user stop nas-media-importer"
    echo "    查看状态:   systemctl --user status nas-media-importer"
    echo "    查看日志:   journalctl --user -u nas-media-importer -f"
    echo "    重启服务:   systemctl --user restart nas-media-importer"
    echo ""
    echo "  或直接运行:"
    echo "    cd ${DEPLOY_DIR}"
    echo "    ./venv/bin/python3 media_importer/media_importer.py serve"
    echo ""
}

do_install() {
    check_not_root

    echo ""
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo -e "${CYAN}${BOLD}  NAS影视自动化入库系统 - 用户安装${NC}"
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo ""

    if [[ -d "$DEPLOY_DIR" && -f "${DEPLOY_DIR}/media_importer/media_importer.py" ]]; then
        log_info "检测到已有安装: ${DEPLOY_DIR}"
        if prompt_yesno "是否重新安装（覆盖代码，保留配置）？" "N"; then
            log_warn "将更新代码并重启服务..."
        else
            log_info "现有安装保持不变"
            exit 0
        fi
    else
        if prompt_yesno "将在 ${DEPLOY_DIR} 安装，是否继续？" "Y"; then
            mkdir -p "$DEPLOY_DIR"
        else
            exit 0
        fi
    fi

    cd "$DEPLOY_DIR"

    if [[ ! -f "requirements.txt" ]]; then
        log_error "未找到 requirements.txt，请确保代码目录完整"
        exit 1
    fi

    ensure_python3
    ensure_venv
    install_dependencies
    setup_config

    if check_systemd_user; then
        install_systemd_user
        start_service
    else
        log_warn "systemd 用户服务不可用"
        log_info "服务未自动启动，请手动运行："
        echo "  cd ${DEPLOY_DIR}"
        echo "  ./venv/bin/python3 media_importer/media_importer.py serve"
    fi

    print_success
}

do_upgrade() {
    echo ""
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo -e "${CYAN}${BOLD}  NAS影视自动化入库系统 - 升级${NC}"
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo ""

    if [[ ! -d "$DEPLOY_DIR" ]]; then
        log_error "部署目录不存在: ${DEPLOY_DIR}"
        exit 1
    fi

    cd "$DEPLOY_DIR"

    log_step "停止服务"
    if check_systemd_user; then
        systemctl --user stop nas-media-importer 2>/dev/null || true
    fi

    log_step "更新代码"
    if [[ -d ".git" ]]; then
        git fetch origin
        local branch
        branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
        git pull origin "$branch"
        log_info "代码已更新"
    else
        log_warn "非 Git 仓库，请手动更新代码"
    fi

    log_step "重新安装依赖"
    ensure_venv
    install_dependencies

    log_step "重启服务"
    if check_systemd_user; then
        systemctl --user daemon-reload
        systemctl --user restart nas-media-importer
        log_info "服务已重启"
    fi

    log_info "升级完成"
}

do_uninstall() {
    echo ""
    echo -e "${RED}${BOLD}========================================${NC}"
    echo -e "${RED}${BOLD}  NAS影视自动化入库系统 - 卸载${NC}"
    echo -e "${RED}${BOLD}========================================${NC}"
    echo ""

    if ! prompt_yesno "确定要卸载？" "N"; then
        exit 0
    fi

    log_step "停止服务"
    if check_systemd_user; then
        systemctl --user stop nas-media-importer 2>/dev/null || true
        systemctl --user disable nas-media-importer 2>/dev/null || true
    fi

    rm -f "$SERVICE_FILE"
    log_info "服务文件已移除"

    if prompt_yesno "是否删除部署目录 ${DEPLOY_DIR}？（含配置和数据）" "N"; then
        rm -rf "$DEPLOY_DIR"
        log_info "部署目录已删除"
    fi

    log_info "卸载完成"
}

usage() {
    echo ""
    echo -e "${BOLD}NAS影视自动化入库系统 - 用户安装工具${NC}"
    echo ""
    echo "用法: $0 [选项] <命令>"
    echo ""
    echo "命令:"
    echo "  install    安装部署（默认）"
    echo "  upgrade    升级（保留配置）"
    echo "  uninstall  卸载"
    echo ""
    echo "选项:"
    echo "  --non-interactive   非交互模式"
    echo "  --dir <路径>        指定部署目录（默认: ${DEPLOY_DIR}）"
    echo "  -h, --help          显示帮助"
    echo ""
}

main() {
    ACTION="install"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            install|upgrade|uninstall)
                ACTION="$1"
                shift
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                shift
                ;;
            --dir)
                DEPLOY_DIR="$2"
                CONFIG_TEMPLATE="${DEPLOY_DIR}/config/config.yaml"
                CONFIG_FILE="${DEPLOY_DIR}/config/config.yaml"
                DATA_DIR="${DEPLOY_DIR}/data"
                LOG_DIR="${DEPLOY_DIR}/logs"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                usage
                exit 1
                ;;
        esac
    done

    case "$ACTION" in
        install)   do_install ;;
        upgrade)   do_upgrade ;;
        uninstall) do_uninstall ;;
    esac
}

main "$@"

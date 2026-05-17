#!/bin/bash
set -euo pipefail

DEPLOY_DIR="/opt/nas-media-importer"
SERVICE_NAME="nas-media-importer"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
GIT_REPO="https://github.com/your-org/nas_media_manage.git"
APP_ENTRY="media_importer/media_importer.py"
CONFIG_TEMPLATE="media_importer/config.yaml"
CONFIG_PROD="media_importer/config.prod.yaml"
REQUIREMENTS="requirements.txt"
HEALTH_PORT=9855
HEALTH_MAX_WAIT=30

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

NON_INTERACTIVE=false
ACTION="install"

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

check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        log_error "此脚本需要 root 权限运行"
        log_info "请使用: sudo $0 $*"
        exit 1
    fi
}

ensure_python3() {
    if command -v python3 &>/dev/null; then
        local py_version
        py_version=$(python3 --version 2>&1 | awk '{print $2}')
        log_info "已找到 Python3: ${py_version}"
        return 0
    fi

    log_warn "未找到 Python3，正在安装..."
    if command -v apt-get &>/dev/null; then
        apt-get update -qq
        apt-get install -y -qq python3 python3-venv python3-pip
        log_info "Python3 安装完成: $(python3 --version)"
    elif command -v yum &>/dev/null; then
        yum install -y python3 python3-pip
        log_info "Python3 安装完成: $(python3 --version)"
    else
        log_error "无法自动安装 Python3，请手动安装后重试"
        exit 1
    fi
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
    local req_file="${DEPLOY_DIR}/${REQUIREMENTS}"
    if [[ ! -f "$req_file" ]]; then
        log_error "未找到依赖文件: ${req_file}"
        exit 1
    fi
    "${DEPLOY_DIR}/venv/bin/pip" install --quiet -r "$req_file"
    log_info "依赖安装完成"
}

setup_config() {
    local template="${DEPLOY_DIR}/${CONFIG_TEMPLATE}"
    local prod="${DEPLOY_DIR}/${CONFIG_PROD}"

    if [[ -f "$prod" ]]; then
        log_info "生产配置已存在: ${prod}"
        if ! prompt_yesno "是否要重新生成配置？这将覆盖现有配置" "N"; then
            return 0
        fi
    fi

    log_step "配置生产环境"

    if [[ ! -f "$template" ]]; then
        log_error "未找到配置模板: ${template}"
        exit 1
    fi

    cp "$template" "$prod"
    log_info "已从模板创建生产配置: ${prod}"

    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        log_warn "非交互模式：请稍后手动编辑 ${prod}"
        log_warn "关键配置项："
        log_warn "  - llm.api_key: LLM API密钥"
        log_warn "  - source_dir: 源文件目录"
        log_warn "  - temp_dir: 临时目录"
        log_warn "  - log_dir: 日志目录"
        log_warn "  - path_rules: 入库路径规则"
        return 0
    fi

    echo ""
    echo -e "${BOLD}以下为关键配置项，请逐一确认：${NC}"
    echo ""

    local source_dir temp_dir log_dir api_key base_url model

    source_dir=$(prompt_input "源文件目录（网盘下载目录）" "/vol1/downloads")
    temp_dir=$(prompt_input "临时目录" "/vol1/temp/nas-media-importer")
    log_dir=$(prompt_input "日志目录" "/vol1/logs/nas-media-importer")
    api_key=$(prompt_input "LLM API Key" "your-api-key-here")
    base_url=$(prompt_input "LLM API Base URL" "https://api.openai.com/v1")
    model=$(prompt_input "LLM 模型名称" "gpt-4o")

    if command -v sed &>/dev/null; then
        sed -i "s|source_dir:.*|source_dir: \"${source_dir}\"|" "$prod"
        sed -i "s|temp_dir:.*|temp_dir: \"${temp_dir}\"|" "$prod"
        sed -i "s|log_dir:.*|log_dir: \"${log_dir}\"|" "$prod"
        sed -i "s|api_key:.*|api_key: \"${api_key}\"|" "$prod"
        sed -i "s|base_url:.*|base_url: \"${base_url}\"|" "$prod"
        sed -i "s|model:.*|model: \"${model}\"|" "$prod"
    fi

    log_info "生产配置已更新"
    echo ""
    log_warn "如需修改更多配置（路径规则、Hermes等），请编辑: ${prod}"
}

install_service() {
    log_step "安装 systemd 服务"

    local service_src="${DEPLOY_DIR}/deploy/${SERVICE_NAME}.service"
    if [[ ! -f "$service_src" ]]; then
        log_error "未找到服务文件: ${service_src}"
        exit 1
    fi

    sed \
        -e "s|/opt/nas-media-importer|${DEPLOY_DIR}|g" \
        "$service_src" > "$SERVICE_FILE"

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME" 2>/dev/null || true
    log_info "systemd 服务已安装并启用开机自启"
}

start_and_verify() {
    log_step "启动服务并验证"

    systemctl restart "$SERVICE_NAME"

    log_info "等待服务启动..."
    local waited=0
    while [[ $waited -lt $HEALTH_MAX_WAIT ]]; do
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done

    if ! systemctl is-active --quiet "$SERVICE_NAME"; then
        log_error "服务启动失败"
        echo ""
        journalctl -u "$SERVICE_NAME" -n 30 --no-pager
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
            log_warn "可手动检查: curl http://127.0.0.1:${HEALTH_PORT}/api/health"
        fi
    else
        log_warn "未安装 curl，跳过健康检查"
    fi

    echo ""
    echo -e "${GREEN}${BOLD}========================================${NC}"
    echo -e "${GREEN}${BOLD}  部署完成！${NC}"
    echo -e "${GREEN}${BOLD}========================================${NC}"
    echo ""
    echo "  API 地址:    http://0.0.0.0:${HEALTH_PORT}"
    echo "  健康检查:    curl http://127.0.0.1:${HEALTH_PORT}/api/health"
    echo "  配置文件:    ${DEPLOY_DIR}/${CONFIG_PROD}"
    echo "  日志目录:    ${DEPLOY_DIR}/media_importer/logs/"
    echo ""
    echo "  常用命令:"
    echo "    查看状态:  systemctl status ${SERVICE_NAME}"
    echo "    查看日志:  journalctl -u ${SERVICE_NAME} -f"
    echo "    重启服务:  systemctl restart ${SERVICE_NAME}"
    echo "    停止服务:  systemctl stop ${SERVICE_NAME}"
    echo "    升级:      ${DEPLOY_DIR}/deploy/install.sh upgrade"
    echo "    卸载:      ${DEPLOY_DIR}/deploy/install.sh uninstall"
    echo ""
}

do_install() {
    check_root

    echo ""
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo -e "${CYAN}${BOLD}  NAS影视自动化入库系统 - 部署安装${NC}"
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo ""

    if [[ -d "$DEPLOY_DIR" && -f "${DEPLOY_DIR}/${APP_ENTRY}" ]]; then
        log_info "检测到已有代码: ${DEPLOY_DIR}"
        local code_source
        if prompt_yesno "代码已存在，是否从 Git 仓库拉取最新版本？" "N"; then
            code_source="git_existing"
        else
            code_source="existing"
        fi
    else
        if prompt_yesno "是否从 Git 仓库克隆代码？" "Y"; then
            code_source="git_fresh"
        else
            code_source="manual"
            log_warn "请手动将代码上传到 ${DEPLOY_DIR} 后重新运行此脚本"
            exit 0
        fi
    fi

    case "$code_source" in
        git_fresh)
            log_step "从 Git 仓库克隆代码"
            local repo_url
            repo_url=$(prompt_input "Git 仓库地址" "$GIT_REPO")
            if [[ -d "$DEPLOY_DIR" ]]; then
                log_warn "目录已存在: ${DEPLOY_DIR}"
                if ! prompt_yesno "是否删除并重新克隆？" "N"; then
                    log_error "请手动处理目录冲突后重试"
                    exit 1
                fi
                rm -rf "$DEPLOY_DIR"
            fi
            git clone "$repo_url" "$DEPLOY_DIR"
            log_info "代码克隆完成"
            ;;
        git_existing)
            log_step "拉取最新代码"
            cd "$DEPLOY_DIR"
            if [[ -d ".git" ]]; then
                local branch
                branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
                git fetch origin
                git reset --hard "origin/${branch}"
                log_info "代码已更新到最新版本"
            else
                log_warn "非 Git 仓库，跳过拉取"
            fi
            ;;
        manual)
            exit 0
            ;;
    esac

    cd "$DEPLOY_DIR"

    ensure_python3
    ensure_venv
    install_dependencies
    setup_config
    install_service
    start_and_verify
}

do_upgrade() {
    check_root

    echo ""
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo -e "${CYAN}${BOLD}  NAS影视自动化入库系统 - 升级${NC}"
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo ""

    if [[ ! -d "$DEPLOY_DIR" ]]; then
        log_error "部署目录不存在: ${DEPLOY_DIR}"
        log_info "请先运行安装: $0 install"
        exit 1
    fi

    cd "$DEPLOY_DIR"

    log_step "停止服务"
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true

    if [[ -d ".git" ]]; then
        log_step "拉取最新代码"
        local branch
        branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
        git fetch origin
        git reset --hard "origin/${branch}"
        log_info "代码已更新"
    else
        log_warn "非 Git 仓库，跳过代码更新"
        log_warn "请手动更新代码后重新运行"
    fi

    ensure_python3
    ensure_venv
    install_dependencies

    log_step "更新 systemd 服务"
    local service_src="${DEPLOY_DIR}/deploy/${SERVICE_NAME}.service"
    if [[ -f "$service_src" ]]; then
        sed \
            -e "s|/opt/nas-media-importer|${DEPLOY_DIR}|g" \
            "$service_src" > "$SERVICE_FILE"
        systemctl daemon-reload
        log_info "服务文件已更新"
    fi

    start_and_verify
}

do_uninstall() {
    check_root

    echo ""
    echo -e "${RED}${BOLD}========================================${NC}"
    echo -e "${RED}${BOLD}  NAS影视自动化入库系统 - 卸载${NC}"
    echo -e "${RED}${BOLD}========================================${NC}"
    echo ""

    if ! prompt_yesno "确定要卸载 NAS影视自动化入库系统？此操作不可恢复" "N"; then
        log_info "已取消卸载"
        exit 0
    fi

    log_step "停止服务"
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true

    log_step "移除服务文件"
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    log_info "systemd 服务已移除"

    if prompt_yesno "是否删除代码目录 ${DEPLOY_DIR}？（含配置和数据）" "N"; then
        rm -rf "$DEPLOY_DIR"
        log_info "代码目录已删除"
    else
        log_info "保留代码目录: ${DEPLOY_DIR}"
    fi

    echo ""
    log_info "卸载完成"
}

usage() {
    echo ""
    echo -e "${BOLD}NAS影视自动化入库系统 - 部署工具${NC}"
    echo ""
    echo "用法: $0 [选项] <命令>"
    echo ""
    echo "命令:"
    echo "  install    安装部署（默认）"
    echo "  upgrade    升级（拉取最新代码，重启服务）"
    echo "  uninstall  卸载（停止服务，移除服务文件）"
    echo ""
    echo "选项:"
    echo "  --non-interactive   非交互模式，使用默认值"
    echo "  --dir <路径>        指定部署目录（默认: ${DEPLOY_DIR}）"
    echo "  --repo <URL>        指定 Git 仓库地址"
    echo "  -h, --help          显示帮助信息"
    echo ""
    echo "示例:"
    echo "  sudo $0 install                    # 交互式安装"
    echo "  sudo $0 --non-interactive install  # 非交互式安装"
    echo "  sudo $0 upgrade                    # 升级"
    echo "  sudo $0 uninstall                  # 卸载"
    echo ""
}

main() {
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
                shift 2
                ;;
            --repo)
                GIT_REPO="$2"
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
        install)
            do_install
            ;;
        upgrade)
            do_upgrade
            ;;
        uninstall)
            do_uninstall
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"

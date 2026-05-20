#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${PROJECT_DIR}/build"
DEPLOY_DIR="${PROJECT_DIR}/deploy"
APP_NAME="nas-media-importer"
PKG_DIR="${DEPLOY_DIR}/${APP_NAME}"
FPACK_BIN="/tmp/fnpack/fnpack"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

VERSION="${1:-1.0.0}"

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step()  { echo -e "\n${CYAN}${BOLD}>>> $1${NC}"; }

ensure_fnpack() {
    if [ ! -x "${FPACK_BIN}" ]; then
        mkdir -p "$(dirname "${FPACK_BIN}")"
        local arch
        [ "$(uname -m)" = "arm64" ] && arch="arm64" || arch="amd64"
        curl -L -o "${FPACK_BIN}" "https://static2.fnnas.com/fnpack/fnpack-1.2.1-darwin-${arch}"
        chmod +x "${FPACK_BIN}"
    fi
}

create_manifest() {
    cat > "${PKG_DIR}/manifest" << EOF
appname               = ${APP_NAME}
version               = ${VERSION}
display_name          = NAS影视整理入库
desc                  = NAS影视自动化入库系统，支持AI智能刮削、自动分类入库影视文件
platform              = all
source                = thirdparty
maintainer            = wae2855
distributor           = wae2855
desktop_uidir         = ui
desktop_applaunchname = nas-media-importer.main
service_port          = 9855
checkport             = false
ctl_stop              = true
changelog             = ${VERSION} 初始版本发布
EOF
}

create_cmd_main() {
    cat > "${PKG_DIR}/cmd/main" << 'SCRIPT'
#!/bin/bash

LOG_FILE="${TRIM_PKGVAR}/info.log"
PID_FILE="${TRIM_PKGVAR}/app.pid"

APP_DIR="${TRIM_APPDEST}"
VENV_DIR="${TRIM_APPDEST}/venv"
CONFIG_FILE="${TRIM_PKGVAR}/config/config.yaml"
APP_PORT="${wizard_port:-9855}"

CMD="${VENV_DIR}/bin/python3 ${APP_DIR}/media_importer/media_importer.py -c ${CONFIG_FILE} serve --host 0.0.0.0 --port ${APP_PORT}"

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> ${LOG_FILE}
}

start_process() {
    if status; then
        log_msg "process already running"
        return 0
    fi

    # auto-create venv if first run
    if [ ! -x "${VENV_DIR}/bin/python3" ]; then
        log_msg "creating Python venv..."
        if python3 -m venv "${VENV_DIR}" >> ${LOG_FILE} 2>&1; then
            log_msg "venv created successfully"
            log_msg "installing pip dependencies..."
            if "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt" >> ${LOG_FILE} 2>&1; then
                log_msg "pip install OK"
            else
                echo "pip 依赖安装失败，请检查网络连接后重启应用" > "${TRIM_TEMP_LOGFILE}"
                exit 1
            fi
        else
            echo "Python 虚拟环境创建失败。请在 SSH 中执行：sudo apt-get install python3-venv" > "${TRIM_TEMP_LOGFILE}"
            exit 1
        fi
    fi

    if [ ! -f "${CONFIG_FILE}" ]; then
        echo "配置文件不存在，请检查应用设置" > "${TRIM_TEMP_LOGFILE}"
        exit 1
    fi

    log_msg "Starting process ..."
    bash -c "${CMD}" >> ${LOG_FILE} 2>&1 &
    printf "%s" "$!" > ${PID_FILE}
    log_msg "process started, pid=$!"
    return 0
}

stop_process() {
    log_msg "Stopping process ..."

    if [ -r "${PID_FILE}" ]; then
        pid=$(head -n 1 "${PID_FILE}" | tr -d '[:space:]')

        log_msg "pid=${pid}"
        if ! check_process "${pid}"; then
            rm -f "${PID_FILE}"
            log_msg "remove pid file, process already gone"
            return 0
        fi

        log_msg "send TERM signal to PID:${pid}..."
        kill -TERM ${pid} >> ${LOG_FILE} 2>&1

        local count=0
        while check_process "${pid}" && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
            log_msg "waiting process terminal... (${count}s/10s)"
        done

        if check_process "${pid}"; then
            log_msg "send KILL signal to PID:${pid}..."
            kill -KILL "${pid}"
            sleep 1
            rm -f "${PID_FILE}"
        else
            log_msg "process killed"
        fi
    fi

    return 0
}

check_process() {
    local pid=$1
    if kill -0 "${pid}" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

status() {
    if [ -f "${PID_FILE}" ]; then
        pid=$(head -n 1 "${PID_FILE}" | tr -d '[:space:]')
        if check_process "${pid}"; then
            return 0
        else
            rm -f "${PID_FILE}"
        fi
    fi
    return 1
}

case $1 in
start)
    start_process
    ;;
stop)
    stop_process
    ;;
status)
    if status; then
        exit 0
    else
        exit 3
    fi
    ;;
*)
    exit 1
    ;;
esac
SCRIPT
    chmod +x "${PKG_DIR}/cmd/main"
}

create_install_callback() {
    cat > "${PKG_DIR}/cmd/install_callback" << 'SCRIPT'
#!/bin/bash
APP_DIR="${TRIM_APPDEST}"
DATA_DIR="${TRIM_PKGVAR}"

mkdir -p "${DATA_DIR}/config"  2>/dev/null || true
mkdir -p "${DATA_DIR}/data"   2>/dev/null || true
mkdir -p "${DATA_DIR}/logs"   2>/dev/null || true

if [ ! -f "${DATA_DIR}/config/config.yaml" ]; then
    if [ -f "${APP_DIR}/config.yaml.example" ]; then
        cp "${APP_DIR}/config.yaml.example" "${DATA_DIR}/config/config.yaml" 2>/dev/null || true
    fi
fi

if [ ! -f "${DATA_DIR}/data/tasks.json" ]; then
    echo '{}' > "${DATA_DIR}/data/tasks.json" 2>/dev/null || true
fi
SCRIPT
    chmod +x "${PKG_DIR}/cmd/install_callback"
}

create_upgrade_callback() {
    cat > "${PKG_DIR}/cmd/upgrade_callback" << 'SCRIPT'
#!/bin/bash
APP_DIR="${TRIM_APPDEST}"
if [ -x "${APP_DIR}/venv/bin/pip" ]; then
    "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt" 2>/dev/null || true
fi
SCRIPT
    chmod +x "${PKG_DIR}/cmd/upgrade_callback"
}

create_uninstall_callback() {
    cat > "${PKG_DIR}/cmd/uninstall_callback" << 'SCRIPT'
#!/bin/bash
APP_DIR="${TRIM_APPDEST}"
rm -rf "${APP_DIR}/venv" 2>/dev/null || true
SCRIPT
    chmod +x "${PKG_DIR}/cmd/uninstall_callback"
}

create_wizard_install() {
    cat > "${PKG_DIR}/wizard/install" << 'EOF'
[
    {
        "stepTitle": "端口配置",
        "items": [
            {
                "type": "text",
                "field": "wizard_port",
                "label": "服务端口",
                "initValue": "9855",
                "rules": [
                    { "required": true, "message": "请输入端口号" },
                    { "pattern": "^[0-9]+$", "message": "端口号必须是数字" }
                ]
            }
        ]
    }
]
EOF
}

create_wizard_config() {
    cat > "${PKG_DIR}/wizard/config" << 'EOF'
[
    {
        "stepTitle": "应用配置",
        "items": [
            {
                "type": "text",
                "field": "wizard_port",
                "label": "服务端口",
                "initValue": "9855",
                "rules": [
                    { "required": true, "message": "请输入端口号" },
                    { "pattern": "^[0-9]+$", "message": "端口号必须是数字" }
                ]
            }
        ]
    }
]
EOF
}

create_wizard_uninstall() {
    cat > "${PKG_DIR}/wizard/uninstall" << 'EOF'
[
    {
        "stepTitle": "确认卸载",
        "items": [
            {
                "type": "tips",
                "helpText": "卸载将删除应用及其虚拟环境。配置文件和数据将保留。"
            }
        ]
    }
]
EOF
}

create_config_resource() {
    cat > "${PKG_DIR}/config/resource" << 'EOF'
{
    "data-share": {
        "shares": [
            {
                "name": "nas-media-importer",
                "permission": {
                    "rw": ["nas-media-importer"]
                }
            }
        ]
    }
}
EOF
}

create_config_privilege() {
    cat > "${PKG_DIR}/config/privilege" << 'EOF'
{
    "defaults": {
        "run-as": "package"
    },
    "username": "nas-media-importer",
    "groupname": "nas-media-importer"
}
EOF
}

create_ui_config() {
    cat > "${PKG_DIR}/app/ui/config" << 'EOF'
{
    ".url": {
        "nas-media-importer.main": {
            "title": "NAS影视整理入库",
            "icon": "images/icon-{0}.png",
            "type": "url",
            "protocol": "http",
            "port": "${wizard_port}",
            "url": "/",
            "allUsers": true
        }
    }
}
EOF
}

main() {
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo -e "${CYAN}${BOLD}  fnOS FPK 打包工具${NC}"
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo ""

    log_step "检查 fnpack 工具"
    ensure_fnpack
    log_info "fnpack 就绪"

    log_step "重建应用目录"
    rm -rf "${PKG_DIR}"
    cd "${DEPLOY_DIR}"
    "${FPACK_BIN}" create "${APP_NAME}"
    log_info "骨架创建完成"

    log_step "写入 manifest"
    create_manifest

    log_step "写入回调脚本"
    create_cmd_main
    create_install_callback
    create_upgrade_callback
    create_uninstall_callback
    log_info "脚本写入完成"

    log_step "写入向导和配置"
    create_wizard_install
    create_wizard_config
    create_wizard_uninstall
    create_config_resource
    create_config_privilege
    create_ui_config
    log_info "向导和配置写入完成"

    log_step "替换应用图标"
    ICON_DIR="${DEPLOY_DIR}/icons"
    if [ -d "${ICON_DIR}" ]; then
        cp "${ICON_DIR}/ICON.PNG"     "${PKG_DIR}/ICON.PNG"     2>/dev/null || true
        cp "${ICON_DIR}/ICON_256.PNG" "${PKG_DIR}/ICON_256.PNG" 2>/dev/null || true
        mkdir -p "${PKG_DIR}/app/ui/images"
        cp "${ICON_DIR}/icon-64.png"  "${PKG_DIR}/app/ui/images/icon-64.png"  2>/dev/null || true
        cp "${ICON_DIR}/icon-256.png" "${PKG_DIR}/app/ui/images/icon-256.png" 2>/dev/null || true
        log_info "图标替换完成"
    else
        log_info "未找到自定义图标目录，使用默认图标"
    fi

    log_step "复制应用代码到 app/server/"
    mkdir -p "${PKG_DIR}/app/server"
    cp -r "${PROJECT_DIR}/media_importer" "${PKG_DIR}/app/server/"
    cp -r "${PROJECT_DIR}/hermes"         "${PKG_DIR}/app/server/"
    cp "${PROJECT_DIR}/config.yaml.example" "${PKG_DIR}/app/server/"
    cp "${PROJECT_DIR}/requirements.txt"    "${PKG_DIR}/app/server/"
    log_info "代码复制完成"

    log_step "打包 FPK"
    cd "${PKG_DIR}"
    "${FPACK_BIN}" build
    log_info "FPK 打包完成"

    mkdir -p "${BUILD_DIR}"
    cp "${PKG_DIR}/${APP_NAME}.fpk" "${BUILD_DIR}/"

    echo ""
    echo -e "${GREEN}${BOLD}========================================${NC}"
    echo -e "${GREEN}${BOLD}  Done!${NC}"
    echo -e "${GREEN}${BOLD}========================================${NC}"
    echo ""
    echo "  Version: ${VERSION}"
    echo "  FPK:     ${BUILD_DIR}/${APP_NAME}.fpk"
    echo "  Size:    $(du -sh "${BUILD_DIR}/${APP_NAME}.fpk" | awk '{print $1}')"
    echo ""
}

main "$@"

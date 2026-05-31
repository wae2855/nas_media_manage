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
display_name          = 影音库AI智能整理
desc                  = 影音库AI智能整理，支持AI智能刮削、自动分类入库影视文件
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
SERVER_DIR="${TRIM_APPDEST}/server"
VENV_DIR="${TRIM_APPDEST}/venv"
CONFIG_FILE="${TRIM_PKGVAR}/config/config.yaml"
APP_PORT="${wizard_port:-9855}"

CMD="${VENV_DIR}/bin/python3 ${SERVER_DIR}/media_importer/media_importer.py -c ${CONFIG_FILE} serve --host 0.0.0.0 --port ${APP_PORT}"

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> ${LOG_FILE}
}

start_process() {
    if status; then
        log_msg "process already running"
        return 0
    fi

    # check if dependencies are installed; reinstall if venv exists but deps missing
    if [ -x "${VENV_DIR}/bin/python3" ]; then
        if ! "${VENV_DIR}/bin/python3" -c "import yaml" >/dev/null 2>&1; then
            log_msg "venv exists but dependencies missing, will reinstall"
            rm -rf "${VENV_DIR}"
        fi
    fi

    # auto-create venv if first run
    if [ ! -x "${VENV_DIR}/bin/python3" ]; then
        log_msg "creating Python venv..."

        # locate python3 with absolute path (fnOS package user has stripped PATH)
        PYTHON_BIN=""
        for candidate in /usr/bin/python3 /usr/local/bin/python3 /opt/python3/bin/python3; do
            if [ -x "${candidate}" ]; then
                PYTHON_BIN="${candidate}"
                break
            fi
        done
        if [ -z "${PYTHON_BIN}" ]; then
            PYTHON_BIN=$(PATH=/usr/local/bin:/usr/bin:/bin command -v python3 2>/dev/null)
        fi
        if [ -z "${PYTHON_BIN}" ] || [ ! -x "${PYTHON_BIN}" ]; then
            echo "无法定位 python3 解释器，请确认系统已安装 Python 3" > "${TRIM_TEMP_LOGFILE}"
            exit 1
        fi
        log_msg "using python: ${PYTHON_BIN}"

        if "${PYTHON_BIN}" -m venv "${VENV_DIR}" >> ${LOG_FILE} 2>&1; then
            log_msg "venv created successfully"
            log_msg "installing pip dependencies..."
            if "${VENV_DIR}/bin/pip" install --no-cache-dir -r "${SERVER_DIR}/requirements.txt" >> ${LOG_FILE} 2>&1; then
                log_msg "pip install OK"
            else
                echo "pip 依赖安装失败，请检查网络连接后重启应用" > "${TRIM_TEMP_LOGFILE}"
                exit 1
            fi
        else
            echo "Python 虚拟环境创建失败。详细日志: ${LOG_FILE}" > "${TRIM_TEMP_LOGFILE}"
            exit 1
        fi
    fi

    if [ ! -f "${CONFIG_FILE}" ]; then
        log_msg "config file not found, will auto-create from template"
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
mkdir -p "${DATA_DIR}/source"  2>/dev/null || true
mkdir -p "${DATA_DIR}/tmp"    2>/dev/null || true

CONFIG_FILE="${DATA_DIR}/config/config.yaml"

if [ ! -f "${CONFIG_FILE}" ]; then
    if [ -f "${APP_DIR}/server/config.yaml.example" ]; then
        cp "${APP_DIR}/server/config.yaml.example" "${CONFIG_FILE}" 2>/dev/null || true
    elif [ -f "${APP_DIR}/config.yaml.example" ]; then
        cp "${APP_DIR}/config.yaml.example" "${CONFIG_FILE}" 2>/dev/null || true
    fi
fi

if [ -f "${CONFIG_FILE}" ]; then
    if grep -qE "^source_dir:.*\"/vol1/" "${CONFIG_FILE}" 2>/dev/null; then
        sed -i "s|^source_dir:.*|source_dir: \"${DATA_DIR}/source\"|" "${CONFIG_FILE}" 2>/dev/null || true
    fi
    if grep -qE "^temp_dir:.*\"/vol1/" "${CONFIG_FILE}" 2>/dev/null; then
        sed -i "s|^temp_dir:.*|temp_dir: \"${DATA_DIR}/tmp\"|" "${CONFIG_FILE}" 2>/dev/null || true
    fi
    if grep -qE "^log_dir:.*\"/vol1/" "${CONFIG_FILE}" 2>/dev/null; then
        sed -i "s|^log_dir:.*|log_dir: \"${DATA_DIR}/logs\"|" "${CONFIG_FILE}" 2>/dev/null || true
    fi
fi

if [ -f "${CONFIG_FILE}" ] && [ -n "${wizard_port}" ]; then
    sed -i "s/^\\(  port:\\).*/\\1 ${wizard_port}/" "${CONFIG_FILE}" 2>/dev/null || true
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
SERVER_DIR="${TRIM_APPDEST}/server"
if [ -x "${APP_DIR}/venv/bin/pip" ]; then
    "${APP_DIR}/venv/bin/pip" install --no-cache-dir -r "${SERVER_DIR}/requirements.txt" 2>/dev/null || true
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

create_config_callback() {
    cat > "${PKG_DIR}/cmd/config_callback" << 'SCRIPT'
#!/bin/bash
CONFIG_FILE="${TRIM_PKGVAR}/config/config.yaml"

if [ -f "${CONFIG_FILE}" ] && [ -n "${wizard_port}" ]; then
    sed -i "s/^\\(  port:\\).*/\\1 ${wizard_port}/" "${CONFIG_FILE}" 2>/dev/null || true
fi

exit 0
SCRIPT
    chmod +x "${PKG_DIR}/cmd/config_callback"
}

create_wizard_install() {
    cat > "${PKG_DIR}/wizard/install" << 'EOF'
[
    {
        "stepTitle": "安装提示",
        "items": [
            {
                "type": "tips",
                "helpText": "安装完成后，请打开应用进入前台界面，在「配置」页面完善以下信息：\n\n【必填配置】\n1. 基础配置 → 源目录 source_dir（如 /vol1/网盘下载）\n2. 入库规则 path_rules 中的入库目录（如 /vol1/影视/电视剧）\n3. LLM 配置：API Key、API 地址、模型名称\n\n【可选 - 高级配置】\n4. 中转目录、日志目录、任务持久化路径等已自动配置好，一般无需修改\n\n⚠️ 重要：授权目录\n如果使用 /vol1/、/vol2/ 等共享盘下的目录，必须：\n   应用中心 → nas-media-importer → 设置 → 授权目录\n   添加上述目录并赋予权限：\n   • 源目录：勾选【读】\n   • 入库目录：勾选【读】+【写】\n\n配置完成后点击「保存配置」（保存时会自动检测路径权限），然后点击概览页的「重启服务」按钮使配置生效。"
            }
        ]
    },
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
            "title": "影音库AI智能整理",
            "icon": "images/icon_{0}.png",
            "type": "iframe",
            "protocol": "",
            "url": "/cgi/ThirdParty/nas-media-importer/index.cgi/",
            "allUsers": true
        }
    }
}
EOF
}

create_ui_cgi() {
    cat > "${PKG_DIR}/app/ui/index.cgi" << 'CGI_EOF'
#!/bin/bash

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="${TRIM_SERVICE_PORT:-9855}"

if [ -f "${TRIM_PKGVAR}/config/config.yaml" ]; then
    PORT_FROM_CONFIG=$(grep -E "^[[:space:]]*port:" "${TRIM_PKGVAR}/config/config.yaml" 2>/dev/null | head -1 | sed 's/.*port:[[:space:]]*//' | tr -d '"' | tr -d "'")
    if [ -n "${PORT_FROM_CONFIG}" ]; then
        BACKEND_PORT="${PORT_FROM_CONFIG}"
    fi
fi

URI_NO_QUERY="${REQUEST_URI%%\?*}"
QUERY_STRING_PART=""
case "$REQUEST_URI" in
    *\?*) QUERY_STRING_PART="?${REQUEST_URI#*\?}" ;;
esac

REL_PATH="/"
case "$URI_NO_QUERY" in
    *index.cgi*)
        REL_PATH="${URI_NO_QUERY#*index.cgi}"
        ;;
esac

if [ -z "$REL_PATH" ]; then
    REL_PATH="/"
fi

TARGET_URL="http://${BACKEND_HOST}:${BACKEND_PORT}${REL_PATH}${QUERY_STRING_PART}"
METHOD="${REQUEST_METHOD:-GET}"

CURL_HEADERS=()
[ -n "${CONTENT_TYPE}" ] && CURL_HEADERS+=("-H" "Content-Type: ${CONTENT_TYPE}")
[ -n "${HTTP_AUTHORIZATION}" ] && CURL_HEADERS+=("-H" "Authorization: ${HTTP_AUTHORIZATION}")
[ -n "${HTTP_COOKIE}" ] && CURL_HEADERS+=("-H" "Cookie: ${HTTP_COOKIE}")
[ -n "${HTTP_X_REQUESTED_WITH}" ] && CURL_HEADERS+=("-H" "X-Requested-With: ${HTTP_X_REQUESTED_WITH}")

TMP_HEADERS=$(mktemp)
TMP_BODY=$(mktemp)
trap 'rm -f "${TMP_HEADERS}" "${TMP_BODY}"' EXIT

if [ "${METHOD}" = "POST" ] || [ "${METHOD}" = "PUT" ] || [ "${METHOD}" = "PATCH" ]; then
    cat - > "${TMP_BODY}"
    curl -sS -X "${METHOD}" --data-binary "@${TMP_BODY}" "${CURL_HEADERS[@]}" -D "${TMP_HEADERS}" "${TARGET_URL}" > "${TMP_BODY}.out" 2>/dev/null
else
    curl -sS -X "${METHOD}" "${CURL_HEADERS[@]}" -D "${TMP_HEADERS}" "${TARGET_URL}" > "${TMP_BODY}.out" 2>/dev/null
fi

CURL_EXIT=$?

if [ ${CURL_EXIT} -ne 0 ]; then
    echo "Status: 502 Bad Gateway"
    echo "Content-Type: text/plain; charset=utf-8"
    echo ""
    echo "Backend service unavailable (curl exit ${CURL_EXIT})"
    echo "Target: ${TARGET_URL}"
    exit 0
fi

STATUS_LINE=$(head -1 "${TMP_HEADERS}" | tr -d '\r')
STATUS_CODE=$(echo "${STATUS_LINE}" | awk '{print $2}')
STATUS_MSG=$(echo "${STATUS_LINE}" | cut -d' ' -f3-)

if [ -n "${STATUS_CODE}" ] && [ "${STATUS_CODE}" != "200" ]; then
    echo "Status: ${STATUS_CODE} ${STATUS_MSG}"
fi

grep -iE "^(Content-Type|Content-Length|Cache-Control|Location|Set-Cookie):" "${TMP_HEADERS}" | tr -d '\r'

echo ""
cat "${TMP_BODY}.out"
rm -f "${TMP_BODY}.out"
CGI_EOF
    chmod +x "${PKG_DIR}/app/ui/index.cgi"
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
    create_config_callback
    log_info "脚本写入完成"

    log_step "写入向导和配置"
    create_wizard_install
    create_wizard_config
    create_wizard_uninstall
    create_config_resource
    create_config_privilege
    create_ui_config
    create_ui_cgi
    log_info "向导和配置写入完成"

    log_step "替换应用图标"
    ICON_DIR="${DEPLOY_DIR}/icons"
    if [ -d "${ICON_DIR}" ]; then
        cp "${ICON_DIR}/ICON.PNG"     "${PKG_DIR}/ICON.PNG"     2>/dev/null || true
        cp "${ICON_DIR}/ICON_256.PNG" "${PKG_DIR}/ICON_256.PNG" 2>/dev/null || true
        mkdir -p "${PKG_DIR}/app/ui/images"
        cp "${ICON_DIR}/icon_64.png"  "${PKG_DIR}/app/ui/images/icon_64.png"  2>/dev/null || true
        cp "${ICON_DIR}/icon_256.png" "${PKG_DIR}/app/ui/images/icon_256.png" 2>/dev/null || true
        log_info "图标替换完成"
    else
        log_info "未找到自定义图标目录，使用默认图标"
    fi

    log_step "复制应用代码到 app/server/"
    mkdir -p "${PKG_DIR}/app/server"
    cp -r "${PROJECT_DIR}/media_importer" "${PKG_DIR}/app/server/"
    if [ -d "${PROJECT_DIR}/hermes" ]; then
        cp -r "${PROJECT_DIR}/hermes"         "${PKG_DIR}/app/server/"
    fi
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

#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-${PROJECT_DIR}/build}"
DEPLOY_DIR="${PROJECT_DIR}/deploy"
APP_NAME="nas-media-importer"
PKG_DIR="${PKG_DIR:-${DEPLOY_DIR}/${APP_NAME}}"
FPACK_BIN="${FPACK_BIN:-/tmp/fnpack/fnpack-1.2.3}"
FPACK_VERSION="1.2.3"
VALIDATOR_PYTHON="${VALIDATOR_PYTHON:-${PROJECT_DIR}/.venv/bin/python}"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

VERSION="${1:-1.0.0}"

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step()  { echo -e "\n${CYAN}${BOLD}>>> $1${NC}"; }

ensure_fnpack() {
    local platform checksum actual_checksum version_output
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64) platform="darwin-arm64"; checksum="d40cb00896cb2a5d211357d255750ed0cbe7f2d141df671c2b717afb4e74bf77" ;;
        Darwin-x86_64) platform="darwin-amd64"; checksum="30a9f50a35e8d8d425b687881761478c3c778e9c0da3a1b59f298b666dd7a268" ;;
        Linux-x86_64) platform="linux-amd64"; checksum="54b97fa7b70968c4d05c79840f5daeff508957d0bb2062fdb0376d00d9615c93" ;;
        *) echo "不支持的 fnpack 构建平台: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
    esac
    if [ ! -f "${FPACK_BIN}" ]; then
        mkdir -p "$(dirname "${FPACK_BIN}")"
        curl -fL --retry 2 -o "${FPACK_BIN}.download" "https://static2.fnnas.com/fnpack/fnpack-${FPACK_VERSION}-${platform}"
        mv "${FPACK_BIN}.download" "${FPACK_BIN}"
    fi
    actual_checksum="$(shasum -a 256 "${FPACK_BIN}" | awk '{print $1}')"
    if [ "${actual_checksum}" != "${checksum}" ]; then
        echo "fnpack 校验和不匹配，拒绝构建" >&2
        exit 1
    fi
    chmod +x "${FPACK_BIN}"
    version_output="$(${FPACK_BIN} 2>&1 || true)"
    case "${version_output}" in
        *"${FPACK_VERSION}"*) ;;
        *) echo "fnpack 版本不匹配: ${version_output}" >&2; exit 1 ;;
    esac
}

create_manifest() {
    cat > "${PKG_DIR}/manifest" << EOF
appname               = ${APP_NAME}
version               = ${VERSION}
display_name          = 影音库智能整理
desc                  = 自动识别影视文件、获取元数据并按规则整理入库
platform              = all
source                = thirdparty
maintainer            = wae2855
distributor           = wae2855
desktop_uidir         = ui
desktop_applaunchname = nas-media-importer.main
service_port          = 14591
os_min_version        = 1.2.0401
micro_app             = true
disable_authorization_path = false
checkport             = false
ctl_stop              = true
install_dep_apps      = python312
changelog             = ${VERSION} 初始版本发布
EOF
}

create_cmd_main() {
    cat > "${PKG_DIR}/cmd/main" << 'SCRIPT'
#!/bin/bash
set -u

LOG_FILE="${TRIM_PKGVAR}/info.log"
PID_FILE="${TRIM_PKGVAR}/app.pid"

SERVER_DIR="${TRIM_APPDEST}/server"
VENV_DIR="${TRIM_PKGVAR}/venv"
CONFIG_FILE="${TRIM_PKGVAR}/config/config.yaml"
REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=12
export PATH="/var/apps/python312/target/bin:/usr/local/bin:/usr/bin:/bin"

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "${LOG_FILE}"
}

fail_visible() {
    log_msg "$1"
    echo "$1" > "${TRIM_TEMP_LOGFILE}"
    return 1
}

start_process() {
    if status; then
        log_msg "process already running"
        return 0
    fi

    # check if dependencies are installed; reinstall if venv exists but deps missing
    if [ -x "${VENV_DIR}/bin/python3" ]; then
        if ! "${VENV_DIR}/bin/python3" -c "import sys, yaml; raise SystemExit(0 if sys.version_info >= (${REQUIRED_PYTHON_MAJOR}, ${REQUIRED_PYTHON_MINOR}) else 1)" >/dev/null 2>&1; then
            log_msg "venv exists but Python version is too old or dependencies are missing, will reinstall"
            rm -rf -- "${VENV_DIR}"
        fi
    fi

    # auto-create venv if first run
    if [ ! -x "${VENV_DIR}/bin/python3" ]; then
        log_msg "creating Python venv..."

        # locate python3 with absolute path (fnOS package user has stripped PATH)
        PYTHON_BIN=""
        for candidate in /var/apps/python312/target/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
            if [ -x "${candidate}" ]; then
                PYTHON_BIN="${candidate}"
                break
            fi
        done
        if [ -z "${PYTHON_BIN}" ]; then
            PYTHON_BIN=$(command -v python3 2>/dev/null || true)
        fi
        if [ -z "${PYTHON_BIN}" ] || [ ! -x "${PYTHON_BIN}" ]; then
            fail_visible "无法定位 fnOS Python 3.12 运行时，请确认 python312 依赖已安装"
            return 1
        fi
        log_msg "using python: ${PYTHON_BIN}"

        if ! "${PYTHON_BIN}" -c "import sys; raise SystemExit(0 if sys.version_info >= (${REQUIRED_PYTHON_MAJOR}, ${REQUIRED_PYTHON_MINOR}) else 1)"; then
            fail_visible "当前 fnOS Python 版本过低，至少需要 Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}"
            return 1
        fi

        if "${PYTHON_BIN}" -m venv "${VENV_DIR}" >> "${LOG_FILE}" 2>&1; then
            log_msg "venv created successfully"
            log_msg "stage 2/3: installing bundled Python dependencies offline..."
            if "${VENV_DIR}/bin/pip" install --no-index --find-links "${SERVER_DIR}/wheelhouse" -r "${SERVER_DIR}/requirements-fnos.lock" >> "${LOG_FILE}" 2>&1; then
                log_msg "stage 2/3: offline dependencies installed"
            else
                fail_visible "包内 Python 依赖安装失败，请查看日志确认 wheelhouse 是否完整"
                return 1
            fi
        else
            fail_visible "Python 虚拟环境创建失败，详细日志：${LOG_FILE}"
            return 1
        fi
    fi

    if [ ! -f "${CONFIG_FILE}" ]; then
        fail_visible "运行配置不存在，请重新安装并完成目录与 API Key 配置"
        return 1
    fi

    log_msg "Starting process ..."
    "${VENV_DIR}/bin/python3" "${SERVER_DIR}/media_importer/media_importer.py" \
        -c "${CONFIG_FILE}" serve --host 127.0.0.1 >> "${LOG_FILE}" 2>&1 &
    local started_pid=$!
    printf "%s" "${started_pid}" > "${PID_FILE}"
    sleep 2
    if ! check_process "${started_pid}"; then
        rm -f -- "${PID_FILE}"
        fail_visible "服务启动后立即退出，请查看日志：${LOG_FILE}"
        return 1
    fi
    log_msg "process started, pid=${started_pid}"
    return 0
}

stop_process() {
    log_msg "Stopping process ..."

    if [ -r "${PID_FILE}" ]; then
        pid=$(head -n 1 "${PID_FILE}" | tr -d '[:space:]')

        log_msg "pid=${pid}"
        if ! check_process "${pid}"; then
            rm -f -- "${PID_FILE}"
            log_msg "remove pid file, process already gone"
            return 0
        fi

        log_msg "send TERM signal to PID:${pid}..."
        kill -TERM "${pid}" >> "${LOG_FILE}" 2>&1

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
            rm -f -- "${PID_FILE}"
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
            rm -f -- "${PID_FILE}"
        fi
    fi
    return 1
}

case "${1:-}" in
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
set -eu
APP_DIR="${TRIM_APPDEST}"
DATA_DIR="${TRIM_PKGVAR}"
PYTHON_BIN="/var/apps/python312/target/bin/python3"
CONFIG_FILE="${DATA_DIR}/config/config.yaml"
TEMPLATE_FILE="${APP_DIR}/server/config.yaml.example"

fail_visible() {
    echo "$1" > "${TRIM_TEMP_LOGFILE}"
    exit 1
}

mkdir -p "${DATA_DIR}/config" "${DATA_DIR}/data" "${DATA_DIR}/logs" "${DATA_DIR}/tmp" "${DATA_DIR}/resources" || fail_visible "无法创建应用私有数据目录"

if [ ! -x "${PYTHON_BIN}" ]; then
    fail_visible "未找到 fnOS Python 3.12 运行时，请确认 python312 依赖已安装"
fi
if [ ! -f "${TEMPLATE_FILE}" ]; then
    fail_visible "安装包缺少配置模板，安装已中止"
fi

if ! "${PYTHON_BIN}" "${APP_DIR}/server/fnos_config.py" initialize \
    --config "${CONFIG_FILE}" \
    --template "${TEMPLATE_FILE}" \
    --temp-dir "${DATA_DIR}/tmp" \
    --log-dir "${DATA_DIR}/logs" \
    --resource-dir "${DATA_DIR}/resources" >/dev/null 2>"${DATA_DIR}/install-error.log"; then
    error_message=$(tail -n 1 "${DATA_DIR}/install-error.log" 2>/dev/null || true)
    fail_visible "${error_message:-首次配置写入失败，请检查安装输入}"
fi

if ! "${PYTHON_BIN}" "${APP_DIR}/server/fnos_config.py" migrate-managed-service \
    --config "${CONFIG_FILE}" \
    --resource-dir "${DATA_DIR}/resources" >/dev/null 2>"${DATA_DIR}/install-error.log"; then
    error_message=$(tail -n 1 "${DATA_DIR}/install-error.log" 2>/dev/null || true)
    fail_visible "${error_message:-托管服务配置迁移失败，用户目录未被覆盖}"
fi

rm -f -- "${DATA_DIR}/install-error.log"
SCRIPT
    chmod +x "${PKG_DIR}/cmd/install_callback"
}

create_upgrade_callback() {
    cat > "${PKG_DIR}/cmd/upgrade_callback" << 'SCRIPT'
#!/bin/bash
set -eu
SERVER_DIR="${TRIM_APPDEST}/server"
VENV_DIR="${TRIM_PKGVAR}/venv"
LOG_FILE="${TRIM_PKGVAR}/info.log"
CONFIG_FILE="${TRIM_PKGVAR}/config/config.yaml"
PYTHON_BIN="/var/apps/python312/target/bin/python3"
mkdir -p "${TRIM_PKGVAR}/resources"
if [ -x "${VENV_DIR}/bin/pip" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - upgrade: installing bundled dependencies offline" >>"${LOG_FILE}"
    if ! "${VENV_DIR}/bin/pip" install --no-index --find-links "${SERVER_DIR}/wheelhouse" -r "${SERVER_DIR}/requirements-fnos.lock" >>"${LOG_FILE}" 2>&1; then
        echo "升级包内 Python 依赖失败，原配置已保留。请查看应用日志" > "${TRIM_TEMP_LOGFILE}"
        exit 1
    fi
fi
echo "$(date '+%Y-%m-%d %H:%M:%S') - upgrade: migrating fnOS-managed service settings" >>"${LOG_FILE}"
if [ ! -x "${PYTHON_BIN}" ]; then
    echo "升级失败：未找到 fnOS Python 3.12 运行时" > "${TRIM_TEMP_LOGFILE}"
    exit 1
fi
if ! "${PYTHON_BIN}" "${SERVER_DIR}/fnos_config.py" migrate-managed-service \
    --config "${CONFIG_FILE}" \
    --resource-dir "${TRIM_PKGVAR}/resources" >>"${LOG_FILE}" 2>&1; then
    echo "升级托管配置失败，来源、片库和回收目录未被覆盖。请查看应用日志" > "${TRIM_TEMP_LOGFILE}"
    exit 1
fi
SCRIPT
    chmod +x "${PKG_DIR}/cmd/upgrade_callback"
}

create_uninstall_callback() {
    cat > "${PKG_DIR}/cmd/uninstall_callback" << 'SCRIPT'
#!/bin/bash
VENV_DIR="${TRIM_PKGVAR}/venv"
rm -rf -- "${VENV_DIR}" 2>/dev/null || true
SCRIPT
    chmod +x "${PKG_DIR}/cmd/uninstall_callback"
}

create_config_callback() {
    cat > "${PKG_DIR}/cmd/config_callback" << 'SCRIPT'
#!/bin/bash
exit 0
SCRIPT
    chmod +x "${PKG_DIR}/cmd/config_callback"
}

create_wizard_install() {
    cat > "${PKG_DIR}/wizard/install" << 'EOF'
[
    {
        "stepTitle": "开始前确认",
        "items": [
            {
                "type": "tips",
                "helpText": "安装完成后，首次打开应用会引导你从 fnOS 中选择并授权目录，不需要在这里手填路径。\n\n• 来源目录：可以是本地下载或已挂载网盘\n• 目标片库：可以连续添加多个硬盘或挂载目录\n• 回收目录：必须选择本机磁盘，不允许使用云盘\n\n目录选择完成后，应用会统一检查存在、读写权限、挂载状态和磁盘空间；关键项未通过前不会自动处理文件。首次安装官方 Python 运行时可能需要几分钟。"
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
                "type": "tips",
                "helpText": "应用访问入口和服务端口由 fnOS 统一管理。目录、刮削和自动运行等设置请进入应用内完成。"
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
    "api-scope": [
        "trim.file.sharedAccess"
    ]
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
BACKEND_PORT="14591"

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
    if [ ! -x "${VALIDATOR_PYTHON}" ]; then
        VALIDATOR_PYTHON="$(command -v python3 || true)"
    fi
    if [ -z "${VALIDATOR_PYTHON}" ] || [ ! -x "${VALIDATOR_PYTHON}" ]; then
        echo "未找到用于验证 FPK 的 Python 3" >&2
        exit 1
    fi

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
    cp "${PROJECT_DIR}/config.yaml.example" "${PKG_DIR}/app/server/"
    cp "${PROJECT_DIR}/requirements.txt"    "${PKG_DIR}/app/server/"
    cp "${PROJECT_DIR}/deploy/requirements-fnos.lock" "${PKG_DIR}/app/server/"
    cp "${PROJECT_DIR}/deploy/fnos_config.py" "${PKG_DIR}/app/server/"
    find "${PKG_DIR}" -type d -name '__pycache__' -prune -exec rm -rf -- {} +
    find "${PKG_DIR}" -type f \( -name '*.pyc' -o -name '.DS_Store' \) -delete
    log_info "代码复制完成"

    log_step "下载跨架构离线 Python wheel"
    mkdir -p "${PKG_DIR}/app/server/wheelhouse"
    "${VALIDATOR_PYTHON}" -m pip download \
        --dest "${PKG_DIR}/app/server/wheelhouse" \
        --only-binary=:all: --platform any --implementation py --python-version 3.12 --abi none \
        -r "${PROJECT_DIR}/deploy/requirements-fnos.lock"
    if find "${PKG_DIR}/app/server/wheelhouse" -type f ! -name '*-none-any.whl' | grep -q .; then
        echo "wheelhouse 包含平台相关或非 wheel 文件，拒绝 platform=all 构建" >&2
        exit 1
    fi
    log_info "离线 wheelhouse 已就绪"

    log_step "打包 FPK"
    cd "${PKG_DIR}"
    "${FPACK_BIN}" build
    log_info "FPK 打包完成"

    log_step "验证 FPK 内容"
    "${VALIDATOR_PYTHON}" "${PROJECT_DIR}/scripts/validate_fpk.py" \
        "${PKG_DIR}/${APP_NAME}.fpk" --version "${VERSION}"
    log_info "FPK 内容验证通过"

    mkdir -p "${BUILD_DIR}"
    cp "${PKG_DIR}/${APP_NAME}.fpk" "${BUILD_DIR}/"
    (cd "${BUILD_DIR}" && shasum -a 256 "${APP_NAME}.fpk" > "${APP_NAME}.fpk.sha256")

    echo ""
    echo -e "${GREEN}${BOLD}========================================${NC}"
    echo -e "${GREEN}${BOLD}  Done!${NC}"
    echo -e "${GREEN}${BOLD}========================================${NC}"
    echo ""
    echo "  Version: ${VERSION}"
    echo "  FPK:     ${BUILD_DIR}/${APP_NAME}.fpk"
    echo "  SHA256:  ${BUILD_DIR}/${APP_NAME}.fpk.sha256"
    echo "  Size:    $(du -sh "${BUILD_DIR}/${APP_NAME}.fpk" | awk '{print $1}')"
    echo ""
}

main "$@"

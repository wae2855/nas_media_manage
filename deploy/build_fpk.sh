#!/bin/bash
# FNOS FPK 安装包构建脚本
# 用法: ./build_fpk.sh [版本号]

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${PROJECT_DIR}/build"
FNOS_DIR="${BUILD_DIR}/fnos-package"
FPK_FILE="${BUILD_DIR}/nas-media-importer.fpk"

VERSION="${1:-1.0.0}"
APP_NAME="nas-media-importer"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step()  { echo -e "\n${CYAN}${BOLD}>>> $1${NC}"; }

cleanup() {
    rm -rf "${FNOS_DIR}"
    mkdir -p "${FNOS_DIR}"
}

copy_files() {
    log_step "复制应用文件"
    
    # 复制主应用代码
    mkdir -p "${FNOS_DIR}/opt/${APP_NAME}"
    cp -r "${PROJECT_DIR}/media_importer" "${FNOS_DIR}/opt/${APP_NAME}/"
    cp "${PROJECT_DIR}/requirements.txt" "${FNOS_DIR}/opt/${APP_NAME}/"
    cp "${PROJECT_DIR}/config.yaml.example" "${FNOS_DIR}/opt/${APP_NAME}/"
    
    # 创建必要目录
    mkdir -p "${FNOS_DIR}/opt/${APP_NAME}/config"
    mkdir -p "${FNOS_DIR}/opt/${APP_NAME}/data"
    mkdir -p "${FNOS_DIR}/opt/${APP_NAME}/logs"
    echo '{}' > "${FNOS_DIR}/opt/${APP_NAME}/data/tasks.json"
    
    # 复制 systemd 服务
    mkdir -p "${FNOS_DIR}/etc/systemd/system"
    sed "s|/opt/nas-media-importer|/opt/${APP_NAME}|g" \
        "${PROJECT_DIR}/deploy/nas-media-importer.service" \
        > "${FNOS_DIR}/etc/systemd/system/${APP_NAME}.service"
    
    log_info "应用文件复制完成"
}

create_scripts() {
    log_step "创建 FNOS 脚本"
    
    mkdir -p "${FNOS_DIR}/cmd"
    
    # main - 启动脚本
    cat > "${FNOS_DIR}/cmd/main" <<EOF
#!/bin/bash
APP_DIR="/opt/${APP_NAME}"

if [[ ! -d "\${APP_DIR}/venv" ]]; then
    python3 -m venv "\${APP_DIR}/venv"
    "\${APP_DIR}/venv/bin/pip" install --quiet -r "\${APP_DIR}/requirements.txt"
fi

exec "\${APP_DIR}/venv/bin/python3" "\${APP_DIR}/media_importer/media_importer.py" -c "\${APP_DIR}/config/config.yaml" serve -p 9855 --host 0.0.0.0
EOF
    chmod +x "${FNOS_DIR}/cmd/main"
    
    # install_callback - 安装后回调
    cat > "${FNOS_DIR}/cmd/install_callback" <<EOF
#!/bin/bash
APP_DIR="/opt/${APP_NAME}"

mkdir -p "\${APP_DIR}/config"
mkdir -p "\${APP_DIR}/data"
mkdir -p "\${APP_DIR}/logs"

if [[ ! -f "\${APP_DIR}/config/config.yaml" ]]; then
    if [[ -f "\${APP_DIR}/config.yaml.example" ]]; then
        cp "\${APP_DIR}/config.yaml.example" "\${APP_DIR}/config/config.yaml"
    fi
fi

if [[ ! -f "\${APP_DIR}/data/tasks.json" ]]; then
    echo '{}' > "\${APP_DIR}/data/tasks.json"
fi

# 创建虚拟环境并安装依赖
python3 -m venv "\${APP_DIR}/venv"
"\${APP_DIR}/venv/bin/pip" install --quiet -r "\${APP_DIR}/requirements.txt"

# 安装 systemd 服务
systemctl daemon-reload
systemctl enable ${APP_NAME} 2>/dev/null || true
systemctl start ${APP_NAME} 2>/dev/null || true
EOF
    chmod +x "${FNOS_DIR}/cmd/install_callback"
    
    # upgrade_callback - 升级后回调
    cat > "${FNOS_DIR}/cmd/upgrade_callback" <<EOF
#!/bin/bash
APP_DIR="/opt/${APP_NAME}"

# 更新依赖
"\${APP_DIR}/venv/bin/pip" install --quiet -r "\${APP_DIR}/requirements.txt"

systemctl daemon-reload 2>/dev/null || true
systemctl restart ${APP_NAME} 2>/dev/null || true
EOF
    chmod +x "${FNOS_DIR}/cmd/upgrade_callback"
    
    # uninstall_callback - 卸载前回调
    cat > "${FNOS_DIR}/cmd/uninstall_callback" <<EOF
#!/bin/bash
systemctl stop ${APP_NAME} 2>/dev/null || true
systemctl disable ${APP_NAME} 2>/dev/null || true
EOF
    chmod +x "${FNOS_DIR}/cmd/uninstall_callback"
    
    log_info "FNOS 脚本创建完成"
}

create_manifest() {
    log_step "创建应用清单"
    
    cat > "${FNOS_DIR}/manifest" <<EOF
appname=${APP_NAME}
version=${VERSION}
desc=NAS影视自动化入库系统 - AI智能刮削、自动分类入库影视文件
arch=x86_64
display_name=NAS影视入库
maintainer=wae2855
source=thirdparty
service_port=9855
EOF
    
    log_info "应用清单创建完成"
}

package_fpk() {
    log_step "打包 FPK"
    
    cd "${BUILD_DIR}"
    
    # 使用 tar 打包（FNOS 标准格式）
    tar -czvf "${FPK_FILE}" -C "${FNOS_DIR}" .
    
    log_info "FPK 包创建完成: ${FPK_FILE}"
    echo ""
    echo -e "${GREEN}${BOLD}========================================${NC}"
    echo -e "${GREEN}${BOLD}  FPK 打包完成！${NC}"
    echo -e "${GREEN}${BOLD}========================================${NC}"
    echo ""
    echo "  版本: ${VERSION}"
    echo "  包路径: ${FPK_FILE}"
    echo "  包大小: $(du -sh "${FPK_FILE}" | awk '{print $1}')"
    echo ""
}

main() {
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo -e "${CYAN}${BOLD}  FNOS FPK 打包工具${NC}"
    echo -e "${CYAN}${BOLD}========================================${NC}"
    echo ""
    
    mkdir -p "${BUILD_DIR}"
    cleanup
    copy_files
    create_scripts
    create_manifest
    package_fpk
}

main "$@"

#!/bin/bash
set -e

DEPLOY_DIR="/opt/nas-media-importer"
SERVICE_NAME="nas-media-importer"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [[ ! -d "$DEPLOY_DIR" ]]; then
    log_error "部署目录不存在: $DEPLOY_DIR"
    log_info "请先克隆项目到 $DEPLOY_DIR"
    exit 1
fi

cd "$DEPLOY_DIR"

if [[ ! -d "venv" ]]; then
    log_info "创建 Python 虚拟环境..."
    python3 -m venv venv
    venv/bin/pip install --quiet --upgrade pip
    venv/bin/pip install --quiet pyyaml
fi

log_info "安装 systemd 服务..."
cp deploy/nas-media-importer.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

log_info "启动服务..."
systemctl start "$SERVICE_NAME"

sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_info "服务启动成功!"
    systemctl status "$SERVICE_NAME" --no-pager
else
    log_error "服务启动失败，查看日志:"
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager
    exit 1
fi

echo ""
echo "常用命令:"
echo "  查看状态: systemctl status $SERVICE_NAME"
echo "  查看日志: journalctl -u $SERVICE_NAME -f"
echo "  停止服务: systemctl stop $SERVICE_NAME"
echo "  重启服务: systemctl restart $SERVICE_NAME"

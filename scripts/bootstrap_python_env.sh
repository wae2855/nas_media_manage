#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_VERSION_FILE="${SCRIPT_DIR}/.python-version"
VENV_DIR="${SCRIPT_DIR}/.venv"

log() {
    printf '[python-env] %s\n' "$1"
}

resolve_python_bin() {
    if [ -f "${PYTHON_VERSION_FILE}" ] && command -v pyenv >/dev/null 2>&1; then
        local version
        version="$(tr -d '[:space:]' < "${PYTHON_VERSION_FILE}")"
        if [ -n "${version}" ]; then
            env PYENV_VERSION="${version}" pyenv which python3
            return 0
        fi
    fi

    command -v python3
}

PYTHON_BIN="$(resolve_python_bin)"

if [ -z "${PYTHON_BIN}" ] || [ ! -x "${PYTHON_BIN}" ]; then
    log "未找到可用的 Python 解释器。请先安装 .python-version 指定的版本，或确保 python3 可用。"
    exit 1
fi

log "使用解释器: ${PYTHON_BIN}"
"${PYTHON_BIN}" --version

if [ ! -d "${VENV_DIR}" ]; then
    log "创建虚拟环境: ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

log "检查 pip"
if ! PIP_DISABLE_PIP_VERSION_CHECK=1 "${VENV_DIR}/bin/python" -m pip install --upgrade pip; then
    log "pip 升级失败，继续使用虚拟环境内现有 pip。若当前环境离线，可在网络恢复后重试。"
fi

log "安装项目依赖与默认测试依赖"
if ! PIP_DISABLE_PIP_VERSION_CHECK=1 "${VENV_DIR}/bin/pip" install -r "${SCRIPT_DIR}/requirements-dev.txt"; then
    log "依赖安装失败。请确认当前终端可访问 Python 包源，或在可联网环境下重试。"
    exit 1
fi

cat <<EOF

项目 Python 环境已就绪。

后续建议使用以下命令：
  source "${VENV_DIR}/bin/activate"
  python -m pytest tests/
  ./start.sh
EOF

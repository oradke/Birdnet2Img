#!/usr/bin/env bash
set -eu

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="/opt/pixoo"
SERVICE_NAME="birdnet-sse.service"
ENV_TARGET="/etc/default/birdnet-sse"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}"
RUN_USER="${SUDO_USER:-pi}"
RUN_GROUP="${RUN_USER}"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

install -d -o "${RUN_USER}" -g "${RUN_GROUP}" "${TARGET_DIR}"
install -m 0644 -o "${RUN_USER}" -g "${RUN_GROUP}" "${PROJECT_DIR}/birdnet_sse.py" "${TARGET_DIR}/birdnet_sse.py"
install -m 0644 -o "${RUN_USER}" -g "${RUN_GROUP}" "${PROJECT_DIR}/requirements.txt" "${TARGET_DIR}/requirements.txt"
install -m 0755 -o "${RUN_USER}" -g "${RUN_GROUP}" "${PROJECT_DIR}/run_birdnet_sse.sh" "${TARGET_DIR}/run_birdnet_sse.sh"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required on the Raspberry Pi." >&2
    exit 1
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "python3-venv is required. Install it with: sudo apt install python3-venv" >&2
    exit 1
fi

if [ ! -x "${TARGET_DIR}/.venv/bin/python" ]; then
    sudo -u "${RUN_USER}" python3 -m venv "${TARGET_DIR}/.venv"
fi

sudo -u "${RUN_USER}" "${TARGET_DIR}/.venv/bin/python" -m pip install --upgrade pip
sudo -u "${RUN_USER}" "${TARGET_DIR}/.venv/bin/python" -m pip install -r "${TARGET_DIR}/requirements.txt"

if [ ! -f "${ENV_TARGET}" ]; then
    install -m 0644 "${PROJECT_DIR}/birdnet-sse.env.example" "${ENV_TARGET}"
fi

sed "s|^WorkingDirectory=.*|WorkingDirectory=${TARGET_DIR}|; s|^ExecStart=.*|ExecStart=${TARGET_DIR}/run_birdnet_sse.sh|; s|^User=.*|User=${RUN_USER}|; s|^Group=.*|Group=${RUN_GROUP}|" \
    "${PROJECT_DIR}/birdnet-sse.service" > "${SERVICE_TARGET}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "Installed ${SERVICE_NAME}."
echo "Edit ${ENV_TARGET} if you need to change PIXOO_IP or BIRDNET_GO_BASE_URL."
echo "Dependencies installed from ${TARGET_DIR}/requirements.txt into ${TARGET_DIR}/.venv."
echo "Check logs with: journalctl -u ${SERVICE_NAME} -f"

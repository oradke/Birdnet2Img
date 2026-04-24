#!/usr/bin/env bash
set -eu

SERVICE_NAME="birdnet-sse.service"
ENV_TARGET="/etc/default/birdnet-sse"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}"
TARGET_DIR="/opt/pixoo"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this uninstaller with sudo." >&2
    exit 1
fi

if systemctl list-unit-files | grep -q "^${SERVICE_NAME}"; then
    systemctl stop "${SERVICE_NAME}" || true
    systemctl disable "${SERVICE_NAME}" || true
fi

rm -f "${SERVICE_TARGET}"
rm -f "${ENV_TARGET}"
rm -rf "${TARGET_DIR}"

systemctl daemon-reload
systemctl reset-failed "${SERVICE_NAME}" || true

echo "Removed ${SERVICE_NAME}, /etc configuration files, and ${TARGET_DIR}."

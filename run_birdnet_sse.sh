#!/usr/bin/env bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"

if [ ! -x "${VENV_PYTHON}" ]; then
    echo "Missing virtualenv Python at ${VENV_PYTHON}" >&2
    exit 1
fi

cd "${SCRIPT_DIR}"
exec "${VENV_PYTHON}" -u "${SCRIPT_DIR}/birdnet_sse.py"

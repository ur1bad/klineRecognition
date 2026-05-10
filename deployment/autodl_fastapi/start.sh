#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

export KLINE_SERVER_HOST="${KLINE_SERVER_HOST:-0.0.0.0}"
export KLINE_SERVER_PORT="${KLINE_SERVER_PORT:-6006}"
export KLINE_DEVICE="${KLINE_DEVICE:-auto}"
export KLINE_TORCH_DTYPE="${KLINE_TORCH_DTYPE:-auto}"
export KLINE_ATTN_IMPLEMENTATION="${KLINE_ATTN_IMPLEMENTATION:-sdpa}"
export KLINE_MAX_NEW_TOKENS="${KLINE_MAX_NEW_TOKENS:-160}"
export KLINE_TEMPERATURE="${KLINE_TEMPERATURE:-0.0}"

python -m uvicorn app:app --host "${KLINE_SERVER_HOST}" --port "${KLINE_SERVER_PORT}" --workers 1

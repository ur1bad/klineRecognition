#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/root/autodl-tmp/deployment/autodl_fastapi"
MODEL_BASE_DIR="/root/autodl-tmp/models/Qwen2.5-VL-7B-Instruct"
LORA_DIR="/root/autodl-tmp/adapters/kline_lora_v3_lr5e5_ep5/checkpoint-1050"
PROCESSOR_SOURCE="/root/autodl-tmp/models/Qwen2.5-VL-7B-Instruct"
LOG_FILE="/root/autodl-tmp/kline_fastapi.out"

HOST="0.0.0.0"
PORT="6006"
MODEL_NAME="Qwen2.5-VL-7B-Instruct + LoRA"
DEVICE="auto"
TORCH_DTYPE="auto"
ATTN_IMPLEMENTATION="sdpa"
MAX_NEW_TOKENS="160"
TEMPERATURE="0.0"

cd "${PROJECT_DIR}"

export KLINE_MODEL_BASE_DIR="${MODEL_BASE_DIR}"
export KLINE_LORA_DIR="${LORA_DIR}"
export KLINE_PROCESSOR_SOURCE="${PROCESSOR_SOURCE}"
export KLINE_MODEL_NAME="${MODEL_NAME}"
export KLINE_SERVER_HOST="${HOST}"
export KLINE_SERVER_PORT="${PORT}"
export KLINE_DEVICE="${DEVICE}"
export KLINE_TORCH_DTYPE="${TORCH_DTYPE}"
export KLINE_ATTN_IMPLEMENTATION="${ATTN_IMPLEMENTATION}"
export KLINE_MAX_NEW_TOKENS="${MAX_NEW_TOKENS}"
export KLINE_TEMPERATURE="${TEMPERATURE}"

if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
fi

nohup bash start.sh > "${LOG_FILE}" 2>&1 &
PID=$!

echo "AutoDL inference service start requested."
echo "PID: ${PID}"
echo "Log file: ${LOG_FILE}"

sleep 5

if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "Health check OK: http://127.0.0.1:${PORT}/health"
else
    echo "Health check not ready yet. Use this command to inspect logs:"
    echo "tail -f ${LOG_FILE}"
fi

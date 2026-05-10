from __future__ import annotations

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import get_config
from backend.db.database import init_db
from backend.routes.backtest import router as backtest_router
from backend.routes.context import router as context_router
from backend.routes.prediction import router as prediction_router
from backend.routes.records import router as records_router


config = get_config()
REMOTE_HEALTH_CHECK_TIMEOUT_SECONDS = 3.0

app = FastAPI(
    title="K-Line Pattern Recognition Service",
    version="1.2.0",
    description=(
        "Business backend for K-line chart generation, remote multimodal inference, "
        "record management, and backtesting."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(config.static_mount_path, StaticFiles(directory=str(config.outputs_dir)), name="outputs")
app.include_router(context_router)
app.include_router(prediction_router)
app.include_router(records_router)
app.include_router(backtest_router)


@app.on_event("startup")
async def on_startup() -> None:
    config.ensure_directories()
    init_db()


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": "K-line backend is running.",
        "docs": "/docs",
    }


def check_remote_model_service() -> dict[str, object]:
    if not (config.remote_api_enabled and config.inference_backend in {"remote_api", "auto"}):
        return {
            "remote_api_connected": False,
            "remote_api_health_url": "",
            "remote_api_health_status_code": None,
            "remote_api_health_error": "Remote model service is not configured.",
        }

    health_url = f"{config.remote_api_base_url}{config.remote_api_health_path}"
    try:
        response = requests.get(health_url, timeout=REMOTE_HEALTH_CHECK_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return {
            "remote_api_connected": False,
            "remote_api_health_url": health_url,
            "remote_api_health_status_code": None,
            "remote_api_health_error": str(exc),
        }

    return {
        "remote_api_connected": response.ok,
        "remote_api_health_url": health_url,
        "remote_api_health_status_code": response.status_code,
        "remote_api_health_error": "" if response.ok else (response.text or response.reason)[:300],
    }


@app.get("/health")
def health() -> dict[str, object]:
    remote_health = check_remote_model_service()
    return {
        "status": "ok",
        "inference_backend": config.inference_backend,
        "model_display_name": config.remote_api_display_name,
        "remote_api_enabled": config.remote_api_enabled,
        **remote_health,
        "remote_api_protocol": config.remote_api_protocol,
        "remote_api_base_url": config.remote_api_base_url,
        "remote_api_predict_path": config.remote_api_predict_path,
        "remote_api_health_path": config.remote_api_health_path,
        "remote_api_model": config.remote_api_model,
        "model_base_dir_found": bool(config.model_base_dir and config.model_base_dir.exists()),
        "lora_dir_found": bool(config.lora_dir and config.lora_dir.exists()),
        "model_base_dir": str(config.model_base_dir) if config.model_base_dir else "",
        "lora_dir": str(config.lora_dir) if config.lora_dir else "",
    }

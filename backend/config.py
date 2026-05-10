from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import urlparse


DEFAULT_REMOTE_API_PROTOCOL = "openai_compat"
DEFAULT_REMOTE_API_BASE_URL = "http://127.0.0.1:6006/v1"
DEFAULT_REMOTE_API_MODEL = "kline-lora"
DEFAULT_REMOTE_API_DISPLAY_NAME = "Qwen2.5-VL-7B-Instruct"
DEFAULT_REMOTE_API_KEY = "EMPTY"
DEFAULT_REMOTE_API_TIMEOUT = 300
DEFAULT_REMOTE_API_PREDICT_PATH = "/predict"
DEFAULT_REMOTE_API_HEALTH_PATH = "/health"

REMOTE_API_PROTOCOL_ALIASES = {
    "openai": "openai_compat",
    "openai_compat": "openai_compat",
    "vllm": "openai_compat",
    "custom_fastapi": "custom_fastapi",
    "fastapi": "custom_fastapi",
    "fastapi_qwen_lora": "custom_fastapi",
    "qwen_lora_fastapi": "custom_fastapi",
}


def _env_path(name: str) -> Optional[Path]:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_remote_api_protocol(value: str) -> str:
    key = (value or "").strip().lower()
    return REMOTE_API_PROTOCOL_ALIASES.get(key, DEFAULT_REMOTE_API_PROTOCOL)


def _normalize_remote_api_base_url(value: str, protocol: str) -> str:
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        return cleaned

    parsed = urlparse(cleaned)
    if protocol == "openai_compat" and parsed.scheme in {"http", "https"} and parsed.netloc and parsed.path in {"", "/"}:
        return parsed._replace(path="/v1").geturl().rstrip("/")

    return cleaned


def _normalize_api_path(value: str, default: str) -> str:
    text = (value or default).strip()
    if not text:
        text = default
    if not text.startswith("/"):
        text = f"/{text}"
    return text.rstrip("/") or "/"


def _candidate_dirs(root: Path, max_depth: int = 2) -> Iterable[Path]:
    visited: set[Path] = set()
    queue: list[tuple[Path, int]] = [(root, 0)]
    while queue:
        current, depth = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        yield current
        if depth >= max_depth:
            continue
        for child in sorted(current.iterdir(), key=lambda item: item.name):
            if child.is_dir():
                queue.append((child, depth + 1))


def _is_model_dir(path: Path) -> bool:
    return path.is_dir() and (path / "config.json").exists() and not (path / "adapter_config.json").exists()


def _is_lora_dir(path: Path) -> bool:
    return path.is_dir() and (path / "adapter_config.json").exists()


def _discover_dir(
    root: Path,
    env_name: str,
    preferred_names: list[str],
    matcher: Callable[[Path], bool],
    keywords: tuple[str, ...],
) -> Optional[Path]:
    explicit = _env_path(env_name)
    if explicit is not None and explicit.exists():
        return explicit

    for name in preferred_names:
        candidate = root / name
        if matcher(candidate):
            return candidate

    for candidate in _candidate_dirs(root, max_depth=2):
        name = candidate.name.lower()
        if matcher(candidate) and any(keyword in name for keyword in keywords):
            return candidate

    for candidate in _candidate_dirs(root, max_depth=2):
        if matcher(candidate):
            return candidate

    return explicit


def _resolve_best_lora_dir(path: Optional[Path]) -> Optional[Path]:
    if path is None or not path.exists():
        return path

    trainer_state_path = path / "trainer_state.json"
    if not trainer_state_path.exists():
        return path

    try:
        trainer_state = json.loads(trainer_state_path.read_text(encoding="utf-8"))
    except Exception:
        return path

    best_checkpoint = str(trainer_state.get("best_model_checkpoint", "")).strip()
    if not best_checkpoint:
        return path

    checkpoint_name = Path(best_checkpoint).name
    candidate = path / checkpoint_name
    if candidate.exists() and (candidate / "adapter_config.json").exists():
        return candidate
    return path


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    data_dir: Path
    outputs_dir: Path
    uploads_dir: Path
    generated_dir: Path
    backtests_dir: Path
    temp_dir: Path
    database_path: Path
    model_base_dir: Optional[Path]
    lora_dir: Optional[Path]
    backend_host: str
    backend_port: int
    streamlit_backend_url: str
    model_device: str
    model_max_new_tokens: int
    model_temperature: float
    allow_rule_fallback: bool
    inference_backend: str
    remote_api_protocol: str
    remote_api_base_url: str
    remote_api_predict_path: str
    remote_api_health_path: str
    remote_api_key: str
    remote_api_model: str
    remote_api_display_name: str
    remote_api_timeout: int
    static_mount_path: str = "/outputs"

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.outputs_dir,
            self.uploads_dir,
            self.generated_dir,
            self.backtests_dir,
            self.temp_dir,
            self.database_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def remote_api_enabled(self) -> bool:
        if not self.remote_api_base_url.strip():
            return False
        if self.remote_api_protocol == "openai_compat":
            return bool(self.remote_api_model.strip())
        return True


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    project_root = Path(__file__).resolve().parents[1]
    outputs_dir = project_root / "outputs"

    model_base_dir = _discover_dir(
        root=project_root,
        env_name="KLINE_MODEL_BASE_DIR",
        preferred_names=[
            "Qwen2.5-VL-7B-Instruct",
            "Qwen2.5-VL",
            "Qwen2.5-VL-Base",
            "base_model",
            "model",
            "models",
        ],
        matcher=_is_model_dir,
        keywords=("qwen", "vl", "vision", "model"),
    )

    lora_dir = _discover_dir(
        root=project_root,
        env_name="KLINE_LORA_DIR",
        preferred_names=[
            "kline_lora_v3_lr5e5_ep5",
            "lora",
            "lora_adapter",
            "adapter",
            "adapters",
            "output",
            "checkpoint",
        ],
        matcher=_is_lora_dir,
        keywords=("lora", "adapter", "checkpoint", "sft"),
    )
    lora_dir = _resolve_best_lora_dir(lora_dir)

    remote_api_protocol = _normalize_remote_api_protocol(
        os.getenv("KLINE_REMOTE_API_PROTOCOL", DEFAULT_REMOTE_API_PROTOCOL)
    )

    config = AppConfig(
        project_root=project_root,
        data_dir=project_root / "data",
        outputs_dir=outputs_dir,
        uploads_dir=outputs_dir / "uploads",
        generated_dir=outputs_dir / "generated",
        backtests_dir=outputs_dir / "backtests",
        temp_dir=outputs_dir / "tmp",
        database_path=project_root / "data" / "kline_records.sqlite3",
        model_base_dir=model_base_dir,
        lora_dir=lora_dir,
        backend_host=os.getenv("BACKEND_HOST", "127.0.0.1"),
        backend_port=int(os.getenv("BACKEND_PORT", "8000")),
        streamlit_backend_url=os.getenv("STREAMLIT_BACKEND_URL", "http://127.0.0.1:8000"),
        model_device=os.getenv("KLINE_MODEL_DEVICE", "auto").strip().lower(),
        model_max_new_tokens=int(os.getenv("KLINE_MODEL_MAX_NEW_TOKENS", "160")),
        model_temperature=float(os.getenv("KLINE_MODEL_TEMPERATURE", "0.0")),
        allow_rule_fallback=_env_bool("KLINE_ALLOW_RULE_FALLBACK", True),
        inference_backend=os.getenv("KLINE_INFERENCE_BACKEND", "remote_api").strip().lower(),
        remote_api_protocol=remote_api_protocol,
        remote_api_base_url=_normalize_remote_api_base_url(
            os.getenv("KLINE_REMOTE_API_BASE_URL", DEFAULT_REMOTE_API_BASE_URL),
            remote_api_protocol,
        ),
        remote_api_predict_path=_normalize_api_path(
            os.getenv("KLINE_REMOTE_API_PREDICT_PATH", DEFAULT_REMOTE_API_PREDICT_PATH),
            DEFAULT_REMOTE_API_PREDICT_PATH,
        ),
        remote_api_health_path=_normalize_api_path(
            os.getenv("KLINE_REMOTE_API_HEALTH_PATH", DEFAULT_REMOTE_API_HEALTH_PATH),
            DEFAULT_REMOTE_API_HEALTH_PATH,
        ),
        remote_api_key=os.getenv("KLINE_REMOTE_API_KEY", DEFAULT_REMOTE_API_KEY).strip(),
        remote_api_model=os.getenv("KLINE_REMOTE_API_MODEL", DEFAULT_REMOTE_API_MODEL).strip(),
        remote_api_display_name=os.getenv(
            "KLINE_REMOTE_API_DISPLAY_NAME", DEFAULT_REMOTE_API_DISPLAY_NAME
        ).strip(),
        remote_api_timeout=int(os.getenv("KLINE_REMOTE_API_TIMEOUT", str(DEFAULT_REMOTE_API_TIMEOUT))),
    )
    config.ensure_directories()
    return config

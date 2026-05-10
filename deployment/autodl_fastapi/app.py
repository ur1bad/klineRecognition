from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from peft import PeftModel
from pydantic import BaseModel, Field
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration


DEFAULT_PROMPT = (
    "<image>请判断这张K线图属于哪一种形态。"
    "可选类别：上升三角形、下降三角形、双底、双顶、头肩底、头肩顶、无明显形态。"
    "只输出类别名称。"
)

PATTERN_KEY_TO_LABEL = {
    "head_and_shoulders_top": "头肩顶",
    "head_and_shoulders_bottom": "头肩底",
    "double_top": "双顶",
    "double_bottom": "双底",
    "ascending_triangle": "上升三角形",
    "descending_triangle": "下降三角形",
    "no_pattern": "无明显形态",
}

DEFAULT_REASONS = {
    "头肩顶": "图中高点依次形成左肩、头部和右肩，属于典型的头肩顶结构。",
    "头肩底": "图中低点依次形成左肩、头部和右肩，属于典型的头肩底结构。",
    "双顶": "图中出现两个相近高点，中间有较明显回撤，符合双顶特征。",
    "双底": "图中出现两个相近低点，中间存在明显反弹，符合双底特征。",
    "上升三角形": "图中高点趋于水平、低点逐步抬高，符合上升三角形特征。",
    "下降三角形": "图中低点趋于水平、高点逐步下移，符合下降三角形特征。",
    "无明显形态": "当前K线窗口中未识别出明确的目标形态。",
}

LABEL_ALIASES = {
    "头肩顶": ["头肩顶", "头肩顶部", "head_and_shoulders_top", "headshoulderstop"],
    "头肩底": ["头肩底", "头肩底部", "head_and_shoulders_bottom", "headshouldersbottom"],
    "双顶": ["双顶", "double_top", "doubletop"],
    "双底": ["双底", "double_bottom", "doublebottom"],
    "上升三角形": ["上升三角形", "ascending_triangle", "ascendingtriangle"],
    "下降三角形": ["下降三角形", "descending_triangle", "descendingtriangle"],
    "无明显形态": ["无明显形态", "无形态", "未识别", "no_pattern", "nopattern", "none"],
}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: Optional[int]) -> Optional[int]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value.strip())


def normalize_label(value: Optional[str]) -> str:
    if not value:
        return "无明显形态"

    compact = re.sub(r"[\s`\"'，。；;:{}\[\]()]+", "", str(value)).lower()
    for label, aliases in LABEL_ALIASES.items():
        for alias in aliases:
            if alias.lower() in compact:
                return label
    return "无明显形态"


def default_confidence(label: str) -> float:
    return 0.56 if label == "无明显形态" else 0.78


def clamp_confidence(value: Optional[Any], label: Optional[str] = None) -> float:
    if value is None:
        return default_confidence(label or "无明显形态")

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default_confidence(label or "无明显形态")

    if numeric > 1:
        numeric = numeric / 100.0
    numeric = max(0.0, min(1.0, numeric))
    if numeric == 0.0:
        return default_confidence(label or "无明显形态")
    return round(numeric, 4)


def reason_for_label(label: str, custom_reason: Optional[str] = None) -> str:
    if custom_reason and custom_reason.strip():
        return custom_reason.strip()
    return DEFAULT_REASONS.get(label, DEFAULT_REASONS["无明显形态"])


def extract_json_payload(text: str) -> Optional[dict[str, Any]]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def extract_confidence(text: str) -> Optional[float]:
    match = re.search(r"confidence\s*[:=]\s*([0-9.]+%?)", text, flags=re.IGNORECASE)
    if not match:
        return None

    raw_value = match.group(1)
    try:
        if raw_value.endswith("%"):
            return float(raw_value[:-1]) / 100.0
        return float(raw_value)
    except ValueError:
        return None


def extract_reason(text: str) -> Optional[str]:
    match = re.search(r"reason\s*[:=]\s*(.+)", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


def select_torch_dtype(dtype_name: str) -> torch.dtype:
    normalized = dtype_name.strip().lower()
    if normalized == "auto":
        if torch.cuda.is_available():
            return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        return torch.float32

    mapping = {
        "float16": torch.float16,
        "fp16": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    if normalized not in mapping:
        raise ValueError(f"Unsupported KLINE_TORCH_DTYPE: {dtype_name}")
    return mapping[normalized]


def build_device_map(device_name: str) -> Any:
    normalized = device_name.strip().lower()
    if normalized == "auto":
        return "auto" if torch.cuda.is_available() else {"": "cpu"}
    return {"": device_name.strip()}


def get_input_device(device_name: str) -> torch.device:
    normalized = device_name.strip().lower()
    if normalized == "auto":
        return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    return torch.device(device_name.strip())


def resolve_processor_source(model_base_dir: Path, lora_dir: Path) -> Path:
    explicit = os.getenv("KLINE_PROCESSOR_SOURCE", "").strip()
    if explicit:
        explicit_path = Path(explicit).expanduser()
        if not explicit_path.exists():
            raise RuntimeError(
                "KLINE_PROCESSOR_SOURCE is set but does not exist. "
                "Please point it to a valid processor/tokenizer directory."
            )
        return explicit_path.resolve()

    # Prefer the base model directory by default.
    # Some LoRA/checkpoint exports include tokenizer_config.json files whose
    # structure differs across transformers versions and can fail to load.
    return model_base_dir


@dataclass(frozen=True)
class ServiceConfig:
    model_base_dir: Path
    lora_dir: Path
    processor_source: Path
    model_name: str
    host: str
    port: int
    device: str
    torch_dtype: str
    attn_implementation: Optional[str]
    min_pixels: Optional[int]
    max_pixels: Optional[int]
    trust_remote_code: bool
    max_new_tokens: int
    temperature: float


@lru_cache(maxsize=1)
def get_service_config() -> ServiceConfig:
    model_base_dir = Path(os.getenv("KLINE_MODEL_BASE_DIR", "")).expanduser()
    lora_dir = Path(os.getenv("KLINE_LORA_DIR", "")).expanduser()

    if not model_base_dir.exists():
        raise RuntimeError(
            "KLINE_MODEL_BASE_DIR does not exist. Please point it to your Qwen2.5-VL base model directory."
        )
    if not lora_dir.exists():
        raise RuntimeError("KLINE_LORA_DIR does not exist. Please point it to your LoRA adapter directory.")

    processor_source = resolve_processor_source(model_base_dir, lora_dir)
    default_model_name = "Qwen2.5-VL-7B-Instruct"

    attn_implementation = os.getenv("KLINE_ATTN_IMPLEMENTATION", "sdpa").strip()
    return ServiceConfig(
        model_base_dir=model_base_dir.resolve(),
        lora_dir=lora_dir.resolve(),
        processor_source=processor_source.resolve(),
        model_name=os.getenv("KLINE_MODEL_NAME", default_model_name).strip() or default_model_name,
        host=os.getenv("KLINE_SERVER_HOST", "0.0.0.0").strip(),
        port=int(os.getenv("KLINE_SERVER_PORT", "6006")),
        device=os.getenv("KLINE_DEVICE", "auto").strip(),
        torch_dtype=os.getenv("KLINE_TORCH_DTYPE", "auto").strip(),
        attn_implementation=attn_implementation or None,
        min_pixels=_env_int("KLINE_MIN_PIXELS", None),
        max_pixels=_env_int("KLINE_MAX_PIXELS", None),
        trust_remote_code=_env_bool("KLINE_TRUST_REMOTE_CODE", False),
        max_new_tokens=int(os.getenv("KLINE_MAX_NEW_TOKENS", "160")),
        temperature=float(os.getenv("KLINE_TEMPERATURE", "0.0")),
    )


class PredictionResponse(BaseModel):
    label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str
    raw_output: str
    backend_mode: str


class HealthResponse(BaseModel):
    status: str
    model_name: str
    model_base_dir: str
    lora_dir: str
    processor_source: str
    device: str
    torch_dtype: str
    attn_implementation: Optional[str] = None
    min_pixels: Optional[int] = None
    max_pixels: Optional[int] = None


class QwenLoRAInferenceService:
    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._input_device = get_input_device(config.device)
        self.processor = self._load_processor()
        self.model = self._load_model()

    def _load_processor(self) -> AutoProcessor:
        processor_kwargs: dict[str, Any] = {}
        if self.config.min_pixels is not None:
            processor_kwargs["min_pixels"] = self.config.min_pixels
        if self.config.max_pixels is not None:
            processor_kwargs["max_pixels"] = self.config.max_pixels

        return AutoProcessor.from_pretrained(
            str(self.config.processor_source),
            trust_remote_code=self.config.trust_remote_code,
            **processor_kwargs,
        )

    def _load_model(self) -> PeftModel:
        model_kwargs: dict[str, Any] = {
            "torch_dtype": select_torch_dtype(self.config.torch_dtype),
            "device_map": build_device_map(self.config.device),
            "trust_remote_code": self.config.trust_remote_code,
        }
        if self.config.attn_implementation:
            model_kwargs["attn_implementation"] = self.config.attn_implementation

        base_model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            str(self.config.model_base_dir),
            **model_kwargs,
        )
        model = PeftModel.from_pretrained(base_model, str(self.config.lora_dir))
        model.eval()
        return model

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "model_name": self.config.model_name,
            "model_base_dir": str(self.config.model_base_dir),
            "lora_dir": str(self.config.lora_dir),
            "processor_source": str(self.config.processor_source),
            "device": self.config.device,
            "torch_dtype": self.config.torch_dtype,
            "attn_implementation": self.config.attn_implementation,
            "min_pixels": self.config.min_pixels,
            "max_pixels": self.config.max_pixels,
        }

    def predict(
        self,
        *,
        image_bytes: bytes,
        filename: str,
        prompt: Optional[str],
        max_new_tokens: Optional[int],
        temperature: Optional[float],
    ) -> dict[str, Any]:
        effective_prompt = (prompt or "").strip() or DEFAULT_PROMPT
        effective_max_new_tokens = max_new_tokens or self.config.max_new_tokens
        effective_temperature = self.config.temperature if temperature is None else temperature
        suffix = Path(filename or "upload.png").suffix or ".png"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(image_bytes)
            temp_path = Path(temp_file.name).resolve()

        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": str(temp_path)},
                        {"type": "text", "text": effective_prompt},
                    ],
                }
            ]

            with self._lock:
                inputs = self.processor.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                    return_dict=True,
                    return_tensors="pt",
                )
                if hasattr(inputs, "to"):
                    inputs = inputs.to(self._input_device)

                generate_kwargs: dict[str, Any] = {
                    "max_new_tokens": effective_max_new_tokens,
                    "do_sample": effective_temperature > 0,
                }
                if effective_temperature > 0:
                    generate_kwargs["temperature"] = effective_temperature

                with torch.inference_mode():
                    generated_ids = self.model.generate(**inputs, **generate_kwargs)

                generated_ids_trimmed = [
                    output_ids[len(input_ids) :]
                    for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
                ]
                raw_output = self.processor.batch_decode(
                    generated_ids_trimmed,
                    skip_special_tokens=True,
                    clean_up_tokenization_spaces=False,
                )[0].strip()
        except Exception as exc:
            raise RuntimeError(f"Model inference failed: {exc}") from exc
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

        return self._normalize_prediction(raw_output)

    def _normalize_prediction(self, raw_output: str) -> dict[str, Any]:
        payload = extract_json_payload(raw_output)
        if payload:
            label = normalize_label(str(payload.get("label", "")))
            confidence = clamp_confidence(payload.get("confidence"), label)
            reason = reason_for_label(label, str(payload.get("reason", "")))
        else:
            label = normalize_label(raw_output)
            confidence = clamp_confidence(extract_confidence(raw_output), label)
            reason = reason_for_label(label, extract_reason(raw_output))

        return {
            "label": label,
            "confidence": confidence,
            "reason": reason,
            "raw_output": raw_output,
            "backend_mode": self.config.model_name,
        }


@lru_cache(maxsize=1)
def get_inference_service() -> QwenLoRAInferenceService:
    return QwenLoRAInferenceService(get_service_config())


app = FastAPI(
    title="AutoDL Qwen2.5-VL LoRA Inference Service",
    version="1.0.0",
    description="FastAPI service that loads a Qwen2.5-VL base model plus a LoRA adapter for image inference.",
)


@app.on_event("startup")
async def warmup_model() -> None:
    get_inference_service()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(**get_inference_service().health())


@app.post("/predict", response_model=PredictionResponse)
async def predict(
    file: UploadFile = File(...),
    prompt: str = Form(DEFAULT_PROMPT),
    max_new_tokens: Optional[int] = Form(None),
    temperature: Optional[float] = Form(None),
) -> PredictionResponse:
    try:
        image_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {exc}") from exc

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = get_inference_service().predict(
            image_bytes=image_bytes,
            filename=file.filename or "upload.png",
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return PredictionResponse(**result)

from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd
import requests

from backend.config import get_config
from backend.utils.labels import MODEL_PROMPT, clamp_confidence, normalize_label, reason_for_label


class ModelUnavailableError(RuntimeError):
    """Raised when no usable inference backend is available."""


@dataclass
class PredictionResult:
    label: str
    confidence: float
    reason: str
    raw_output: str
    inference_model: str


class RemoteAPIInferenceBackend:
    """Call the AutoDL FastAPI /predict inference service."""

    def __init__(self) -> None:
        self.config = get_config()
        self._requests_session: Optional[requests.Session] = None

    def is_configured(self) -> bool:
        return (
            self.config.remote_api_enabled
            and self.config.inference_backend in {"remote_api", "auto"}
            and self.config.remote_api_protocol == "custom_fastapi"
        )

    def predict(self, image_path: Path) -> PredictionResult:
        if not self.is_configured():
            raise ModelUnavailableError("Remote inference backend is not configured.")

        return self._predict_via_custom_fastapi(image_path)

    def _get_requests_session(self) -> requests.Session:
        if self._requests_session is None:
            self._requests_session = requests.Session()
        return self._requests_session

    def _predict_via_custom_fastapi(self, image_path: Path) -> PredictionResult:
        endpoint = f"{self.config.remote_api_base_url}{self.config.remote_api_predict_path}"
        mime_type, _ = mimetypes.guess_type(str(image_path))
        payload = {
            "prompt": MODEL_PROMPT,
            "max_new_tokens": str(self.config.model_max_new_tokens),
            "temperature": str(self.config.model_temperature),
        }

        with image_path.open("rb") as file_handle:
            response = self._get_requests_session().post(
                endpoint,
                data=payload,
                files={"file": (image_path.name, file_handle, mime_type or "image/png")},
                timeout=self.config.remote_api_timeout,
            )

        response_payload: Any
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = None

        if response.status_code >= 400:
            detail = self._extract_error_detail(response_payload) or response.text.strip() or "unknown error"
            raise ModelUnavailableError(
                f"Remote FastAPI inference failed with status {response.status_code}: {detail}"
            )

        if not isinstance(response_payload, dict):
            raise ModelUnavailableError("Remote FastAPI inference returned a non-JSON response.")

        return self._parse_custom_fastapi_payload(response_payload)

    def _parse_custom_fastapi_payload(self, payload: dict[str, Any]) -> PredictionResult:
        prediction = payload.get("prediction") if isinstance(payload.get("prediction"), dict) else payload
        raw_output = prediction.get("raw_output") or payload.get("raw_output")
        if not raw_output:
            raw_output = json.dumps(payload, ensure_ascii=False)

        label = normalize_label(str(prediction.get("label") or raw_output or ""))
        confidence = clamp_confidence(prediction.get("confidence"), label)
        reason = reason_for_label(label, str(prediction.get("reason", "")))
        inference_model = str(
            prediction.get("inference_model")
            or payload.get("inference_model")
            or prediction.get("backend_mode")
            or payload.get("backend_mode")
            or self.config.remote_api_display_name
        ).strip() or self.config.remote_api_display_name

        return PredictionResult(
            label=label,
            confidence=confidence,
            reason=reason,
            raw_output=str(raw_output),
            inference_model=inference_model,
        )

    def _extract_error_detail(self, payload: Any) -> str:
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str):
                return detail.strip()
            if detail is not None:
                return json.dumps(detail, ensure_ascii=False)
        return ""


class InferenceService:
    def __init__(self) -> None:
        self.config = get_config()
        self.remote_backend = RemoteAPIInferenceBackend()

    def predict(self, image_path: Union[str, Path], ohlc_df: Optional[pd.DataFrame] = None) -> PredictionResult:
        image_path = Path(image_path).resolve()

        if self.remote_backend.is_configured():
            try:
                return self.remote_backend.predict(image_path)
            except ModelUnavailableError:
                raise
            except Exception as exc:
                raise ModelUnavailableError(f"远程模型服务调用失败：{exc}") from exc

        raise ModelUnavailableError("未配置可用的远程模型服务。")


@lru_cache(maxsize=1)
def get_inference_service() -> InferenceService:
    return InferenceService()

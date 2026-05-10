from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd
import requests
from openai import OpenAI

from backend.config import get_config
from backend.utils.labels import MODEL_PROMPT, clamp_confidence, key_to_label, normalize_label, reason_for_label
from kline_core.labeling import (
    DEFAULT_EXTREMA_ORDER,
    DEFAULT_SMOOTH_WINDOW,
    check_ascending_triangle,
    check_descending_triangle,
    check_double_bottom,
    check_double_top,
    check_head_and_shoulders_bottom,
    check_head_and_shoulders_top,
    check_no_clear_pattern,
)


RULE_DETECTORS = [
    ("double_bottom", check_double_bottom),
    ("double_top", check_double_top),
    ("head_and_shoulders_top", check_head_and_shoulders_top),
    ("head_and_shoulders_bottom", check_head_and_shoulders_bottom),
    ("ascending_triangle", check_ascending_triangle),
    ("descending_triangle", check_descending_triangle),
]


class ModelUnavailableError(RuntimeError):
    """Raised when no usable inference backend is available."""


@dataclass
class PredictionResult:
    label: str
    confidence: float
    reason: str
    raw_output: str
    backend_mode: str


class RuleBasedFallbackBackend:
    """Fallback to rule-based recognition when the remote model is unavailable."""

    def predict(self, dataframe: pd.DataFrame) -> PredictionResult:
        matches: list[dict[str, Any]] = []

        for key, detector in RULE_DETECTORS:
            matched, info = detector(
                dataframe,
                extrema_order=DEFAULT_EXTREMA_ORDER,
                smooth_window=DEFAULT_SMOOTH_WINDOW,
            )
            if matched:
                record = dict(info)
                record["pattern"] = key
                matches.append(record)

        if matches:
            best = max(matches, key=lambda item: item.get("score", item.get("neck_magnitude", 0.0)))
            label = key_to_label(best.get("pattern"))
            magnitude = float(best.get("neck_magnitude", 0.08))
            confidence = max(0.55, min(0.95, round(0.60 + magnitude * 2.2, 4)))
            reason = reason_for_label(label)
            raw_output = json.dumps({"backend": "rule_fallback", "pattern": best.get("pattern")}, ensure_ascii=False)
            return PredictionResult(
                label=label,
                confidence=confidence,
                reason=reason,
                raw_output=raw_output,
                backend_mode="rule_fallback",
            )

        matched, info = check_no_clear_pattern(dataframe, matched_patterns=[False] * len(RULE_DETECTORS))
        label = key_to_label(info.get("pattern") if matched else "no_pattern")
        return PredictionResult(
            label=label,
            confidence=0.56,
            reason=reason_for_label(label),
            raw_output=json.dumps({"backend": "rule_fallback", "pattern": "no_pattern"}, ensure_ascii=False),
            backend_mode="rule_fallback",
        )


class RemoteAPIInferenceBackend:
    """Call either an OpenAI-compatible server or a custom FastAPI inference service."""

    def __init__(self) -> None:
        self.config = get_config()
        self._openai_client: Optional[OpenAI] = None
        self._requests_session: Optional[requests.Session] = None

    def is_configured(self) -> bool:
        return self.config.remote_api_enabled and self.config.inference_backend in {"remote_api", "auto"}

    def predict(self, image_path: Path) -> PredictionResult:
        if not self.is_configured():
            raise ModelUnavailableError("Remote inference backend is not configured.")

        if self.config.remote_api_protocol == "custom_fastapi":
            return self._predict_via_custom_fastapi(image_path)

        return self._predict_via_openai_compat(image_path)

    def _get_openai_client(self) -> OpenAI:
        if self._openai_client is None:
            self._openai_client = OpenAI(
                api_key=self.config.remote_api_key or "EMPTY",
                base_url=self.config.remote_api_base_url,
                timeout=self.config.remote_api_timeout,
            )
        return self._openai_client

    def _get_requests_session(self) -> requests.Session:
        if self._requests_session is None:
            self._requests_session = requests.Session()
        return self._requests_session

    def _predict_via_openai_compat(self, image_path: Path) -> PredictionResult:
        if not self.config.remote_api_model.strip():
            raise ModelUnavailableError("Remote OpenAI-compatible model name is not configured.")

        data_url = self._build_data_url(image_path)
        client = self._get_openai_client()
        response = client.chat.completions.create(
            model=self.config.remote_api_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": MODEL_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            temperature=self.config.model_temperature,
            max_tokens=self.config.model_max_new_tokens,
        )
        raw_output = self._extract_message_content(response)
        return self._parse_text_output(raw_output, backend_mode=self.config.remote_api_display_name)

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

    def _build_data_url(self, image_path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(str(image_path))
        encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        return f"data:{mime_type or 'image/png'};base64,{encoded}"

    def _extract_message_content(self, response: Any) -> str:
        message = response.choices[0].message.content
        if isinstance(message, str):
            return message.strip()

        if isinstance(message, list):
            parts: list[str] = []
            for item in message:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                else:
                    text = getattr(item, "text", None)
                    if text:
                        parts.append(str(text))
            return "\n".join(parts).strip()

        return str(message).strip()

    def _parse_custom_fastapi_payload(self, payload: dict[str, Any]) -> PredictionResult:
        prediction = payload.get("prediction") if isinstance(payload.get("prediction"), dict) else payload
        raw_output = prediction.get("raw_output") or payload.get("raw_output")
        if not raw_output:
            raw_output = json.dumps(payload, ensure_ascii=False)

        label = normalize_label(str(prediction.get("label", "")))
        confidence = clamp_confidence(prediction.get("confidence"), label)
        reason = reason_for_label(label, str(prediction.get("reason", "")))
        backend_mode = str(
            prediction.get("backend_mode")
            or payload.get("backend_mode")
            or self.config.remote_api_display_name
        ).strip() or self.config.remote_api_display_name

        return PredictionResult(
            label=label,
            confidence=confidence,
            reason=reason,
            raw_output=str(raw_output),
            backend_mode=backend_mode,
        )

    def _parse_text_output(self, raw_output: str, backend_mode: str) -> PredictionResult:
        payload = self._extract_json(raw_output)
        if payload:
            label = normalize_label(str(payload.get("label", "")))
            confidence = clamp_confidence(payload.get("confidence"), label)
            reason = reason_for_label(label, str(payload.get("reason", "")))
            return PredictionResult(
                label=label,
                confidence=confidence,
                reason=reason,
                raw_output=raw_output,
                backend_mode=backend_mode,
            )

        label = normalize_label(raw_output)
        confidence = clamp_confidence(self._extract_confidence(raw_output), label)
        reason = reason_for_label(label, self._extract_reason(raw_output))
        return PredictionResult(
            label=label,
            confidence=confidence,
            reason=reason,
            raw_output=raw_output,
            backend_mode=backend_mode,
        )

    def _extract_json(self, text: str) -> Optional[dict[str, Any]]:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _extract_confidence(self, text: str) -> Optional[float]:
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

    def _extract_reason(self, text: str) -> Optional[str]:
        match = re.search(r"reason\s*[:=]\s*(.+)", text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        return match.group(1).strip()

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
        self.rule_backend = RuleBasedFallbackBackend()

    def predict(self, image_path: Union[str, Path], ohlc_df: Optional[pd.DataFrame] = None) -> PredictionResult:
        image_path = Path(image_path).resolve()

        if self.remote_backend.is_configured():
            try:
                return self.remote_backend.predict(image_path)
            except Exception as exc:
                if ohlc_df is not None and self.config.allow_rule_fallback:
                    fallback = self.rule_backend.predict(ohlc_df)
                    fallback.raw_output = json.dumps(
                        {
                            "backend": "rule_fallback",
                            "reason": f"remote_api_failed: {exc}",
                        },
                        ensure_ascii=False,
                    )
                    return fallback
                raise

        if ohlc_df is not None and self.config.allow_rule_fallback:
            return self.rule_backend.predict(ohlc_df)

        raise ModelUnavailableError("No remote inference API is configured and no rule fallback data is available.")


@lru_cache(maxsize=1)
def get_inference_service() -> InferenceService:
    return InferenceService()

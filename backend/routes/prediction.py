from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from backend.auth import get_current_user
from backend.schemas import (
    GenerateAndPredictRequest,
    GenerateContextSchema,
    GeneratePredictResponseSchema,
    PredictResponseSchema,
    PredictionResultSchema,
)
from backend.services.kline_service import KlineChartService
from backend.services.record_service import RecordService
from backend.utils.date_utils import DateInputError, normalize_date_string, timestamp_slug
from inference.model_service import ModelUnavailableError, get_inference_service


router = APIRouter(tags=["prediction"])

chart_service = KlineChartService()
record_service = RecordService()
inference_service = get_inference_service()


def _prediction_schema(result: Any) -> PredictionResultSchema:
    return PredictionResultSchema(
        label=result.label,
        confidence=result.confidence,
        reason=result.reason,
        raw_output=result.raw_output,
        inference_model=record_service.normalize_inference_model(result.inference_model),
    )


def _build_date_error_message(field_name: str, error: DateInputError) -> str:
    if error.reason == "nonexistent":
        return f"{field_name}不存在：{error.value_text}"
    return f"{field_name}格式不正确，请使用 YYYY-MM-DD、YYYY/MM/DD 或 YYYYMMDD。当前收到：{error.value_text}"


def _normalize_optional_date(value: Optional[str], field_name: str) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return normalize_date_string(text)
    except DateInputError as exc:
        raise HTTPException(
            status_code=400,
            detail=_build_date_error_message(field_name, exc),
        ) from exc


def _normalize_required_date(value: str, field_name: str) -> str:
    normalized = _normalize_optional_date(value, field_name)
    if normalized is None:
        raise HTTPException(status_code=400, detail=f"{field_name}不能为空。")
    return normalized


@router.post("/predict_image", response_model=PredictResponseSchema)
async def predict_image(
    request: Request,
    file: UploadFile = File(...),
    stock_code: Optional[str] = Form(default=None),
    start_date: Optional[str] = Form(default=None),
    end_date: Optional[str] = Form(default=None),
    window_size: Optional[int] = Form(default=None),
    current_user: dict = Depends(get_current_user),
) -> PredictResponseSchema:
    normalized_start_date = _normalize_optional_date(start_date, "开始日期")
    normalized_end_date = _normalize_optional_date(end_date, "结束日期")

    suffix = Path(file.filename or "upload.png").suffix or ".png"
    image_path = chart_service.config.uploads_dir / f"upload_{timestamp_slug()}_{uuid4().hex[:6]}{suffix}"
    image_path.write_bytes(await file.read())

    try:
        prediction = inference_service.predict(image_path=image_path)
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"模型不可用：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图片识别失败：{exc}") from exc

    record = record_service.create_record(
        user_id=int(current_user["id"]),
        stock_code=stock_code,
        image_path=image_path,
        predicted_label=prediction.label,
        confidence=prediction.confidence,
        reason=prediction.reason,
        source_type="upload",
        window_size=window_size,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        inference_model=prediction.inference_model,
    )
    record = record_service.attach_image_url(record, str(request.base_url).rstrip("/"))

    return PredictResponseSchema(
        prediction=_prediction_schema(prediction),
        record=record,
    )


@router.post("/generate_and_predict", response_model=GeneratePredictResponseSchema)
async def generate_and_predict(
    request: Request,
    payload: GenerateAndPredictRequest,
    current_user: dict = Depends(get_current_user),
) -> GeneratePredictResponseSchema:
    try:
        normalized_start_date = _normalize_required_date(payload.start_date, "开始日期")
        normalized_end_date = _normalize_required_date(payload.end_date, "结束日期")
        normalized_anchor_date = _normalize_optional_date(payload.anchor_date, "锚点日期")
        generation = chart_service.generate_chart(
            stock_code=payload.stock_code,
            start_date=normalized_start_date,
            end_date=normalized_end_date,
            window_size=payload.window_size,
            adjust=payload.adjust,
            anchor_date=normalized_anchor_date,
        )
        prediction = inference_service.predict(
            image_path=generation.image_path,
            ohlc_df=generation.window_df,
        )
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"模型不可用：{exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = record_service.create_record(
        user_id=int(current_user["id"]),
        stock_code=payload.stock_code,
        image_path=generation.image_path,
        predicted_label=prediction.label,
        confidence=prediction.confidence,
        reason=prediction.reason,
        source_type="generated",
        window_size=payload.window_size,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        inference_model=prediction.inference_model,
    )
    base_url = str(request.base_url).rstrip("/")
    record = record_service.attach_image_url(record, base_url)

    generation_schema = GenerateContextSchema(
        stock_code=generation.stock_code,
        image_path=str(generation.image_path),
        image_url=record.get("image_url"),
        window_size=generation.window_size,
        start_date=generation.start_date,
        end_date=generation.end_date,
        window_start=generation.window_start,
        window_end=generation.window_end,
        total_rows=len(generation.full_df),
    )
    return GeneratePredictResponseSchema(
        prediction=_prediction_schema(prediction),
        record=record,
        generation=generation_schema,
    )

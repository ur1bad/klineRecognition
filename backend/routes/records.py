from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from backend.schemas import DeleteRecordResponseSchema, RecognitionRecordSchema, RecordsListResponseSchema
from backend.services.record_service import RecordService


router = APIRouter(tags=["records"])
record_service = RecordService()


@router.get("/records", response_model=RecordsListResponseSchema)
async def list_records(
    request: Request,
    limit: int = Query(50, ge=0),
    offset: int = Query(0, ge=0),
    stock_code: Optional[str] = Query(default=None),
    predicted_label: Optional[str] = Query(default=None),
) -> RecordsListResponseSchema:
    result = record_service.list_records(
        limit=limit,
        offset=offset,
        stock_code=stock_code,
        predicted_label=predicted_label,
    )
    base_url = str(request.base_url).rstrip("/")
    items = [record_service.attach_image_url(record, base_url) for record in result["items"]]
    return RecordsListResponseSchema(total=result["total"], items=items)


@router.get("/record/{record_id}", response_model=RecognitionRecordSchema)
async def get_record(request: Request, record_id: int) -> RecognitionRecordSchema:
    record = record_service.get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"记录 {record_id} 不存在。")
    record = record_service.attach_image_url(record, str(request.base_url).rstrip("/"))
    return RecognitionRecordSchema(**record)


@router.delete("/record/{record_id}", response_model=DeleteRecordResponseSchema)
async def delete_record(record_id: int) -> DeleteRecordResponseSchema:
    result = record_service.delete_record(record_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"记录 {record_id} 不存在。")
    return DeleteRecordResponseSchema(**result)

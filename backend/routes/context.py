from __future__ import annotations

from fastapi import APIRouter

from backend.schemas import (
    ResolveGenerateContextRequest,
    ResolveGenerateContextResponse,
    ResolveUploadContextRequest,
    ResolveUploadContextResponse,
)
from backend.services.context_service import ContextResolveService


router = APIRouter(tags=["context"])
context_service = ContextResolveService()


@router.post("/resolve_upload_context", response_model=ResolveUploadContextResponse)
async def resolve_upload_context(payload: ResolveUploadContextRequest) -> ResolveUploadContextResponse:
    result = context_service.resolve_upload_context(
        stock_code=payload.stock_code,
        start_date=payload.start_date,
        end_date=payload.end_date,
        window_size=payload.window_size,
        adjust=payload.adjust,
    )
    return ResolveUploadContextResponse(**result)


@router.post("/resolve_generate_context", response_model=ResolveGenerateContextResponse)
async def resolve_generate_context(payload: ResolveGenerateContextRequest) -> ResolveGenerateContextResponse:
    result = context_service.resolve_generate_context(
        stock_code=payload.stock_code,
        start_date=payload.start_date,
        end_date=payload.end_date,
        window_size=payload.window_size,
        adjust=payload.adjust,
    )
    return ResolveGenerateContextResponse(**result)

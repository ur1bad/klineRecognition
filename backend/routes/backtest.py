from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user
from backend.schemas import BacktestRequest, BacktestResponseSchema
from backend.services.backtest_service import BacktestService


router = APIRouter(tags=["backtest"])
backtest_service = BacktestService()


@router.post("/backtest", response_model=BacktestResponseSchema)
async def backtest(
    payload: BacktestRequest,
    current_user: dict = Depends(get_current_user),
) -> BacktestResponseSchema:
    try:
        result = backtest_service.run_for_record(
            record_id=payload.record_id,
            user_id=int(current_user["id"]),
            horizon_days=payload.horizon_days,
            adjust=payload.adjust,
        )
        return BacktestResponseSchema(**result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

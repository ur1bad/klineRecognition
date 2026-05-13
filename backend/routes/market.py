from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import MarketOverviewSchema
from backend.services.market_service import MarketService


router = APIRouter(tags=["market"])
market_service = MarketService()


@router.get("/market/overview", response_model=MarketOverviewSchema)
async def market_overview(force_refresh: bool = Query(default=False)) -> MarketOverviewSchema:
    try:
        result = market_service.get_overview(force_refresh=force_refresh)
        return MarketOverviewSchema(**result)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"行情数据获取失败：{exc}") from exc

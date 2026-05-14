from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import get_current_user
from backend.schemas import MarketOverviewSchema, MarketStockDetailSchema
from backend.services.market_service import DETAIL_HISTORY_DAYS, MarketService


router = APIRouter(tags=["market"])
market_service = MarketService()


@router.get("/market/overview", response_model=MarketOverviewSchema)
async def market_overview(
    force_refresh: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
) -> MarketOverviewSchema:
    try:
        result = market_service.get_overview(force_refresh=force_refresh)
        return MarketOverviewSchema(**result)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"行情数据获取失败：{exc}") from exc


@router.get("/market/stock/{stock_code}", response_model=MarketStockDetailSchema)
async def stock_detail(
    stock_code: str,
    force_refresh: bool = Query(default=False),
    history_days: int = Query(DETAIL_HISTORY_DAYS, ge=20, le=DETAIL_HISTORY_DAYS),
    adjust: str = Query("qfq"),
    current_user: dict = Depends(get_current_user),
) -> MarketStockDetailSchema:
    try:
        result = market_service.get_stock_detail(
            stock_code,
            force_refresh=force_refresh,
            history_days=history_days,
            adjust=adjust,
        )
        return MarketStockDetailSchema(**result)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"股票详情获取失败：{exc}") from exc

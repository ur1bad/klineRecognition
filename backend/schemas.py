from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PredictionResultSchema(BaseModel):
    label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str
    raw_output: Optional[str] = None
    inference_model: str


class RecognitionRecordSchema(BaseModel):
    id: int
    user_id: int
    stock_code: Optional[str] = None
    image_path: str
    image_url: Optional[str] = None
    predicted_label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str
    source_type: str
    window_size: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    inference_model: Optional[str] = None
    created_at: str


class PredictResponseSchema(BaseModel):
    prediction: PredictionResultSchema
    record: RecognitionRecordSchema


class GenerateAndPredictRequest(BaseModel):
    stock_code: str = Field(..., min_length=1)
    start_date: str
    end_date: str
    window_size: int = Field(30, ge=20, le=240)
    adjust: str = Field("qfq")
    anchor_date: Optional[str] = None


class GenerateContextSchema(BaseModel):
    stock_code: str
    image_path: str
    image_url: Optional[str] = None
    window_size: int
    start_date: str
    end_date: str
    window_start: str
    window_end: str
    total_rows: int


class GeneratePredictResponseSchema(BaseModel):
    prediction: PredictionResultSchema
    record: RecognitionRecordSchema
    generation: GenerateContextSchema


class ResolveUploadContextRequest(BaseModel):
    stock_code: str = ""
    start_date: str = ""
    end_date: str = ""
    window_size: Optional[int] = None
    adjust: str = Field("qfq")


class ResolveUploadContextResponse(BaseModel):
    stock_code: str = ""
    start_date: str = ""
    end_date: str = ""
    window_size: Optional[int] = None
    validation_errors: list[str] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


class ResolveGenerateContextRequest(BaseModel):
    stock_code: str = ""
    start_date: str = ""
    end_date: str = ""
    window_size: Optional[int] = None
    adjust: str = Field("qfq")


class ResolveGenerateContextResponse(BaseModel):
    payload: Optional[GenerateAndPredictRequest] = None
    validation_errors: list[str] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


class RecordsListResponseSchema(BaseModel):
    total: int
    items: list[RecognitionRecordSchema]


class DeleteRecordResponseSchema(BaseModel):
    record_id: int
    deleted: bool
    image_deleted: bool = False


class UserSchema(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: str
    updated_at: Optional[str] = None
    last_login_at: Optional[str] = None
    record_count: int = 0


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class AuthResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSchema


class UsersListResponseSchema(BaseModel):
    total: int
    items: list[UserSchema]


class AdminCreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field("user")
    is_active: bool = True


class AdminUpdateUserRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


class AdminResetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=128)


class AdminDeleteUserResponse(BaseModel):
    user_id: int
    deleted: bool
    records_deleted: int = 0
    images_deleted: int = 0


class BacktestRequest(BaseModel):
    record_id: int = Field(..., ge=1)
    horizon_days: int = Field(3, ge=1, le=30)
    adjust: str = Field("qfq")


class BacktestPricePointSchema(BaseModel):
    trade_date: str
    close: float
    return_rate: float


class BacktestWindowPricePointSchema(BaseModel):
    trade_date: str
    close: float


class BacktestSummarySchema(BaseModel):
    record_id: int
    stock_code: str
    predicted_label: str
    signal_direction: str
    window_start: str
    window_end: str
    horizon_days: int
    current_close: float
    future_close: float
    future_return: float
    future_direction: str
    is_success: Optional[bool] = None
    inference_model: str
    note: str


class BacktestResponseSchema(BaseModel):
    summary: BacktestSummarySchema
    window_prices: list[BacktestWindowPricePointSchema] = Field(default_factory=list)
    future_prices: list[BacktestPricePointSchema]
    record_context: RecognitionRecordSchema
    extra: Optional[dict[str, Any]] = None


class MarketIndexSchema(BaseModel):
    code: str
    name: str
    latest_price: Optional[float] = None
    change_amount: Optional[float] = None
    change_percent: Optional[float] = None
    amount: Optional[float] = None


class MarketBreadthBucketSchema(BaseModel):
    label: str
    count: int
    tone: str


class MarketBreadthSummarySchema(BaseModel):
    total: int
    up: int
    down: int
    flat: int
    limit_up: int
    limit_down: int
    buckets: list[MarketBreadthBucketSchema] = Field(default_factory=list)


class MarketSentimentSchema(BaseModel):
    score: float = Field(..., ge=0.0, le=10.0)
    level: str
    advice: str
    advance_ratio: float = Field(..., ge=0.0, le=1.0)
    strong_ratio: float = Field(0.0, ge=0.0, le=1.0)
    weak_ratio: float = Field(0.0, ge=0.0, le=1.0)
    mean_change: float = 0.0
    index_change: Optional[float] = None
    components: dict[str, float] = Field(default_factory=dict)


class MarketStockSchema(BaseModel):
    code: str
    name: str
    latest_price: Optional[float] = None
    change_percent: Optional[float] = None
    change_amount: Optional[float] = None
    turnover_rate: Optional[float] = None
    amplitude: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    pe_dynamic: Optional[float] = None
    market: str
    board: str


class MarketHistoryPointSchema(BaseModel):
    trade_date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    change_percent: Optional[float] = None
    turnover_rate: Optional[float] = None


class MarketMinutePointSchema(BaseModel):
    trade_time: str
    price: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    average_price: Optional[float] = None


class MarketStockDetailSchema(BaseModel):
    updated_at: str
    source: str
    history_source: str
    minute_source: str = ""
    stock: MarketStockSchema
    history: list[MarketHistoryPointSchema] = Field(default_factory=list)
    minute: list[MarketMinutePointSchema] = Field(default_factory=list)


class MarketOverviewSchema(BaseModel):
    updated_at: str
    source: str
    indices: list[MarketIndexSchema] = Field(default_factory=list)
    breadth: MarketBreadthSummarySchema
    sentiment: MarketSentimentSchema
    stocks: list[MarketStockSchema] = Field(default_factory=list)
    top_gainers: list[MarketStockSchema] = Field(default_factory=list)
    top_losers: list[MarketStockSchema] = Field(default_factory=list)
    top_amount: list[MarketStockSchema] = Field(default_factory=list)
    top_turnover: list[MarketStockSchema] = Field(default_factory=list)
    top_turnover_title: str = "换手率榜"
    top_turnover_metric: str = "turnover_rate"

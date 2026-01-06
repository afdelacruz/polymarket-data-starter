"""Pydantic models for Polymarket data collection."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, computed_field


# =============================================================================
# API Response Models
# =============================================================================


class Token(BaseModel):
    """Token (outcome) in a market."""
    token_id: str
    outcome: str
    price: float


class Market(BaseModel):
    """Polymarket market data from Gamma API."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    market_id: str
    title: str
    volume_24h: float
    liquidity: float
    end_time: str
    tokens: List[Token] = Field(default_factory=list)
    outcomes: Optional[List[str]] = Field(default_factory=list)
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    last_trade_price: Optional[float] = None
    competitive: Optional[float] = None
    numeric_id: Optional[str] = None
    slug: Optional[str] = None
    condition_id: Optional[str] = None
    start_time: Optional[str] = None
    active: Optional[bool] = None
    closed: Optional[bool] = None
    archived: Optional[bool] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    image: Optional[str] = None
    resolution_source: Optional[str] = None
    resolved: Optional[bool] = None
    resolution_outcome: Optional[str] = None


# =============================================================================
# Snapshot Models (stored in SQLite)
# =============================================================================


class MarketSnapshot(BaseModel):
    """Snapshot of a binary market at a point in time."""

    timestamp: datetime
    market_id: str
    title: str
    yes_price: float
    no_price: float
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    volume_24h: Optional[float] = None
    liquidity: Optional[float] = None
    category: Optional[str] = None
    end_time: Optional[str] = None
    active: Optional[bool] = None

    @computed_field
    @property
    def parity_gap(self) -> float:
        """Calculate parity gap: 1 - yes - no.

        Positive = prices sum to less than 1 (buy both for profit)
        Negative = prices sum to more than 1 (sell both for profit)
        """
        return round(1.0 - self.yes_price - self.no_price, 6)

    @computed_field
    @property
    def spread(self) -> Optional[float]:
        """Calculate bid-ask spread."""
        if self.best_bid is not None and self.best_ask is not None:
            return round(self.best_ask - self.best_bid, 6)
        return None


class OutcomeSnapshot(BaseModel):
    """Snapshot of a single outcome in a multi-outcome market."""

    timestamp: datetime
    market_id: str
    outcome: str
    price: float
    token_id: Optional[str] = None


class OrderBookSnapshot(BaseModel):
    """Snapshot of a single order book level."""

    timestamp: datetime
    market_id: str
    token_id: str
    side: str  # "bid" or "ask"
    level: int  # 0 = best, 1 = second best, etc.
    price: float
    size: float


class TradeSnapshot(BaseModel):
    """Snapshot of a single trade."""

    timestamp: datetime
    market_id: str
    token_id: str
    price: float
    size: float
    side: Optional[str] = None  # "buy" or "sell"


class ResolutionSnapshot(BaseModel):
    """Snapshot of a market resolution."""

    timestamp: datetime
    market_id: str
    resolved: bool
    resolution_outcome: Optional[str] = None
    resolution_source: Optional[str] = None


class PriceChangeEvent(BaseModel):
    """Real-time price change event from WebSocket."""

    timestamp: datetime
    market_id: str
    token_id: str
    price: float
    size: float
    side: str  # "BUY" or "SELL"
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None


class BookEvent(BaseModel):
    """Full order book event from WebSocket."""

    timestamp: datetime
    market_id: str
    token_id: str
    hash: Optional[str] = None
    bids: list = Field(default_factory=list)
    asks: list = Field(default_factory=list)

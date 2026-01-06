"""Data recorder for capturing Polymarket snapshots."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import aiosqlite
import httpx

from .models import (
    Market,
    MarketSnapshot,
    OutcomeSnapshot,
    OrderBookSnapshot,
    TradeSnapshot,
    ResolutionSnapshot,
    PriceChangeEvent,
    BookEvent,
)
from .gamma_client import GammaClient

logger = logging.getLogger(__name__)


class DataRecorder:
    """Records Polymarket data snapshots for backtesting."""

    def __init__(
        self,
        gamma_client: GammaClient,
        db_path: str = "./data/snapshots.db",
        min_volume: float = 1000.0,
        min_liquidity: float = 500.0,
        interval_seconds: int = 60,
    ):
        """
        Initialize data recorder.

        Args:
            gamma_client: Polymarket Gamma API client
            db_path: Path to SQLite database
            min_volume: Minimum 24h volume to record
            min_liquidity: Minimum liquidity to record
            interval_seconds: Recording interval in seconds
        """
        self.gamma_client = gamma_client
        self.db_path = db_path
        self.min_volume = min_volume
        self.min_liquidity = min_liquidity
        self.interval_seconds = interval_seconds
        self._db: Optional[aiosqlite.Connection] = None
        self._running = False

    async def init_db(self) -> None:
        """Initialize database with schema."""
        self._db = await aiosqlite.connect(self.db_path)

        # Create tables
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                market_id TEXT NOT NULL,
                title TEXT,
                category TEXT,
                yes_price REAL,
                no_price REAL,
                parity_gap REAL,
                best_bid REAL,
                best_ask REAL,
                spread REAL,
                volume_24h REAL,
                liquidity REAL,
                end_time TEXT,
                active BOOLEAN
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS outcome_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                market_id TEXT NOT NULL,
                outcome TEXT,
                price REAL,
                token_id TEXT
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS orderbook_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                market_id TEXT NOT NULL,
                token_id TEXT NOT NULL,
                side TEXT,
                level INTEGER,
                price REAL,
                size REAL
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS trade_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                market_id TEXT NOT NULL,
                token_id TEXT NOT NULL,
                price REAL,
                size REAL,
                side TEXT
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS resolution_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                market_id TEXT NOT NULL,
                resolved BOOLEAN,
                resolution_outcome TEXT,
                resolution_source TEXT
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS price_change_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                market_id TEXT NOT NULL,
                token_id TEXT NOT NULL,
                price REAL,
                size REAL,
                side TEXT,
                best_bid REAL,
                best_ask REAL
            )
        """)

        # Create indexes
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_snap_time ON market_snapshots(timestamp)"
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_snap_id ON market_snapshots(market_id)"
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_snap_gap ON market_snapshots(parity_gap)"
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcome_snap_time ON outcome_snapshots(timestamp)"
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_book_snap_time ON orderbook_snapshots(timestamp)"
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_trade_snap_time ON trade_snapshots(timestamp)"
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_price_change_time ON price_change_events(timestamp)"
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_price_change_token ON price_change_events(token_id)"
        )

        await self._db.commit()
        logger.info(f"Database initialized at {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def fetch_markets(self) -> List[Market]:
        """Fetch and filter markets from Polymarket."""
        markets = await self.gamma_client.fetch_markets(active_only=True)

        # Apply filters
        filtered = [
            m
            for m in markets
            if m.volume_24h >= self.min_volume and m.liquidity >= self.min_liquidity
        ]

        logger.debug(f"Fetched {len(markets)} markets, {len(filtered)} pass filters")
        return filtered

    def create_snapshots(self, markets: List[Market]) -> List[MarketSnapshot]:
        """Create market snapshots from market data."""
        timestamp = datetime.utcnow()
        snapshots = []

        for market in markets:
            # Get YES and NO prices
            yes_price = 0.0
            no_price = 0.0

            for token in market.tokens:
                if token.outcome.lower() == "yes":
                    yes_price = token.price
                elif token.outcome.lower() == "no":
                    no_price = token.price

            # For 2-outcome markets only
            if len(market.tokens) == 2 and yes_price > 0:
                snapshot = MarketSnapshot(
                    timestamp=timestamp,
                    market_id=market.market_id,
                    title=market.title,
                    category=getattr(market, "category", None),
                    yes_price=yes_price,
                    no_price=no_price,
                    best_bid=market.best_bid,
                    best_ask=market.best_ask,
                    volume_24h=market.volume_24h,
                    liquidity=market.liquidity,
                    end_time=market.end_time,
                    active=getattr(market, "active", None),
                )
                snapshots.append(snapshot)

        return snapshots

    def create_outcome_snapshots(self, markets: List[Market]) -> List[OutcomeSnapshot]:
        """Create outcome snapshots for multi-outcome markets."""
        timestamp = datetime.utcnow()
        snapshots = []

        for market in markets:
            # Only for markets with 3+ outcomes
            if len(market.tokens) >= 3:
                for token in market.tokens:
                    snapshot = OutcomeSnapshot(
                        timestamp=timestamp,
                        market_id=market.market_id,
                        outcome=token.outcome,
                        price=token.price,
                        token_id=token.token_id,
                    )
                    snapshots.append(snapshot)

        return snapshots

    async def save_snapshots(self, snapshots: List[MarketSnapshot]) -> None:
        """Save market snapshots to database."""
        if not self._db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        for snapshot in snapshots:
            await self._db.execute(
                """
                INSERT INTO market_snapshots
                (timestamp, market_id, title, category, yes_price, no_price,
                 parity_gap, best_bid, best_ask, spread, volume_24h, liquidity,
                 end_time, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.timestamp.isoformat(),
                    snapshot.market_id,
                    snapshot.title,
                    snapshot.category,
                    snapshot.yes_price,
                    snapshot.no_price,
                    snapshot.parity_gap,
                    snapshot.best_bid,
                    snapshot.best_ask,
                    snapshot.spread,
                    snapshot.volume_24h,
                    snapshot.liquidity,
                    snapshot.end_time,
                    snapshot.active,
                ),
            )

        await self._db.commit()
        logger.debug(f"Saved {len(snapshots)} market snapshots")

    async def save_outcome_snapshots(self, snapshots: List[OutcomeSnapshot]) -> None:
        """Save outcome snapshots to database."""
        if not self._db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        for snapshot in snapshots:
            await self._db.execute(
                """
                INSERT INTO outcome_snapshots
                (timestamp, market_id, outcome, price, token_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.timestamp.isoformat(),
                    snapshot.market_id,
                    snapshot.outcome,
                    snapshot.price,
                    snapshot.token_id,
                ),
            )

        await self._db.commit()
        logger.debug(f"Saved {len(snapshots)} outcome snapshots")

    async def query_snapshots(
        self,
        market_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[MarketSnapshot]:
        """Query market snapshots from database."""
        if not self._db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        query = "SELECT * FROM market_snapshots WHERE 1=1"
        params = []

        if market_id:
            query += " AND market_id = ?"
            params.append(market_id)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        query += f" ORDER BY timestamp DESC LIMIT {limit}"

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        snapshots = []
        for row in rows:
            snapshot = MarketSnapshot(
                timestamp=datetime.fromisoformat(row[1]),
                market_id=row[2],
                title=row[3],
                category=row[4],
                yes_price=row[5],
                no_price=row[6],
                best_bid=row[8],
                best_ask=row[9],
                volume_24h=row[11],
                liquidity=row[12],
                end_time=row[13],
                active=bool(row[14]) if row[14] is not None else None,
            )
            snapshots.append(snapshot)

        return snapshots

    # =========================================================================
    # Order Book Methods
    # =========================================================================

    async def _fetch_order_book(self, token_id: str) -> Dict[str, Any]:
        """Fetch order book from CLOB API."""
        url = "https://clob.polymarket.com/book"
        params = {"token_id": token_id}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    def create_orderbook_snapshots(
        self,
        market_id: str,
        token_id: str,
        book_data: Dict[str, Any],
        levels: int = 5,
    ) -> List[OrderBookSnapshot]:
        """Create order book snapshots from book data."""
        timestamp = datetime.utcnow()
        snapshots = []

        bids = book_data.get("bids", [])
        asks = book_data.get("asks", [])
        if levels > 0:
            bids = bids[:levels]
            asks = asks[:levels]

        for level, bid in enumerate(bids):
            snapshots.append(
                OrderBookSnapshot(
                    timestamp=timestamp,
                    market_id=market_id,
                    token_id=token_id,
                    side="bid",
                    level=level,
                    price=float(bid["price"]),
                    size=float(bid["size"]),
                )
            )

        for level, ask in enumerate(asks):
            snapshots.append(
                OrderBookSnapshot(
                    timestamp=timestamp,
                    market_id=market_id,
                    token_id=token_id,
                    side="ask",
                    level=level,
                    price=float(ask["price"]),
                    size=float(ask["size"]),
                )
            )

        return snapshots

    async def save_orderbook_snapshots(self, snapshots: List[OrderBookSnapshot]) -> None:
        """Save order book snapshots to database."""
        if not self._db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        for snapshot in snapshots:
            await self._db.execute(
                """
                INSERT INTO orderbook_snapshots
                (timestamp, market_id, token_id, side, level, price, size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.timestamp.isoformat(),
                    snapshot.market_id,
                    snapshot.token_id,
                    snapshot.side,
                    snapshot.level,
                    snapshot.price,
                    snapshot.size,
                ),
            )

        await self._db.commit()
        logger.debug(f"Saved {len(snapshots)} order book snapshots")

    # =========================================================================
    # Trade Methods
    # =========================================================================

    def create_trade_snapshots(
        self,
        market_id: str,
        token_id: str,
        trades: List[Dict[str, Any]],
    ) -> List[TradeSnapshot]:
        """Create trade snapshots from trade data."""
        timestamp = datetime.utcnow()
        snapshots = []

        for trade in trades:
            snapshots.append(
                TradeSnapshot(
                    timestamp=timestamp,
                    market_id=market_id,
                    token_id=token_id,
                    price=float(trade["price"]),
                    size=float(trade["size"]),
                    side=trade["side"],
                )
            )

        return snapshots

    async def save_trade_snapshots(self, snapshots: List[TradeSnapshot]) -> None:
        """Save trade snapshots to database."""
        if not self._db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        for snapshot in snapshots:
            await self._db.execute(
                """
                INSERT INTO trade_snapshots
                (timestamp, market_id, token_id, price, size, side)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.timestamp.isoformat(),
                    snapshot.market_id,
                    snapshot.token_id,
                    snapshot.price,
                    snapshot.size,
                    snapshot.side,
                ),
            )

        await self._db.commit()
        logger.debug(f"Saved {len(snapshots)} trade snapshots")

    # =========================================================================
    # WebSocket Real-Time Stream Methods
    # =========================================================================

    def _parse_ws_timestamp(self, ts: Any) -> datetime:
        """Parse WebSocket timestamp (unix ms or ISO string)."""
        if ts is None:
            return datetime.utcnow()
        if isinstance(ts, (int, float)):
            return datetime.utcfromtimestamp(ts / 1000)
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.utcnow()

    def handle_trade_message(self, message: Dict[str, Any]) -> Optional[TradeSnapshot]:
        """Parse last_trade_price event into TradeSnapshot."""
        return TradeSnapshot(
            timestamp=self._parse_ws_timestamp(message.get("timestamp")),
            market_id=message.get("market", ""),
            token_id=message.get("asset_id", ""),
            price=float(message.get("price", 0)),
            size=float(message.get("size", 0)),
            side=message.get("side", "").lower(),
        )

    def handle_price_change(self, message: Dict[str, Any]) -> List[PriceChangeEvent]:
        """Parse price_change event into PriceChangeEvents."""
        events = []
        timestamp = self._parse_ws_timestamp(message.get("timestamp"))
        market_id = message.get("market", "")
        best_bid = message.get("best_bid")
        best_ask = message.get("best_ask")

        for change in message.get("price_changes", []):
            events.append(
                PriceChangeEvent(
                    timestamp=timestamp,
                    market_id=market_id,
                    token_id=change.get("asset_id", ""),
                    price=float(change.get("price", 0)),
                    size=float(change.get("size", 0)),
                    side=change.get("side", ""),
                    best_bid=float(best_bid) if best_bid else None,
                    best_ask=float(best_ask) if best_ask else None,
                )
            )
        return events

    def handle_book_event(self, message: Dict[str, Any]) -> BookEvent:
        """Parse book event into BookEvent."""
        return BookEvent(
            timestamp=self._parse_ws_timestamp(message.get("timestamp")),
            market_id=message.get("market", ""),
            token_id=message.get("asset_id", ""),
            hash=message.get("hash"),
            bids=message.get("bids", []),
            asks=message.get("asks", []),
        )

    async def save_price_change_events(self, events: List[PriceChangeEvent]) -> None:
        """Save price change events to database."""
        if not self._db:
            return

        for event in events:
            await self._db.execute(
                """
                INSERT INTO price_change_events
                (timestamp, market_id, token_id, price, size, side, best_bid, best_ask)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.timestamp.isoformat(),
                    event.market_id,
                    event.token_id,
                    event.price,
                    event.size,
                    event.side,
                    event.best_bid,
                    event.best_ask,
                ),
            )
        await self._db.commit()

    async def connect_market_stream(self, token_ids: List[str]) -> None:
        """
        Connect to CLOB WebSocket for real-time market data.

        Handles all event types:
        - book: Full order book snapshot
        - price_change: Order placed/cancelled
        - last_trade_price: Trade execution
        """
        import websockets
        import json

        ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

        logger.info(f"Connecting to market stream for {len(token_ids)} tokens")

        stats = {"book": 0, "price_change": 0, "last_trade_price": 0, "other": 0}

        while self._running:
            try:
                async with websockets.connect(ws_url, ping_interval=30) as ws:
                    # Subscribe to all tokens
                    subscribe_msg = {
                        "type": "Market",
                        "assets_ids": token_ids,
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info(f"Subscribed to {len(token_ids)} tokens")

                    # Process incoming messages
                    async for message in ws:
                        if not self._running:
                            break

                        try:
                            data = json.loads(message)
                            event_type = data.get("event_type", "")

                            if event_type == "book":
                                book = self.handle_book_event(data)
                                snapshots = []
                                for level, bid in enumerate(book.bids):
                                    snapshots.append(
                                        OrderBookSnapshot(
                                            timestamp=book.timestamp,
                                            market_id=book.market_id,
                                            token_id=book.token_id,
                                            side="bid",
                                            level=level,
                                            price=float(bid.get("price", 0)),
                                            size=float(bid.get("size", 0)),
                                        )
                                    )
                                for level, ask in enumerate(book.asks):
                                    snapshots.append(
                                        OrderBookSnapshot(
                                            timestamp=book.timestamp,
                                            market_id=book.market_id,
                                            token_id=book.token_id,
                                            side="ask",
                                            level=level,
                                            price=float(ask.get("price", 0)),
                                            size=float(ask.get("size", 0)),
                                        )
                                    )
                                if snapshots and self._db:
                                    await self.save_orderbook_snapshots(snapshots)
                                stats["book"] += 1

                            elif event_type == "price_change":
                                events = self.handle_price_change(data)
                                if events and self._db:
                                    await self.save_price_change_events(events)
                                stats["price_change"] += len(events)

                            elif event_type == "last_trade_price":
                                trade = self.handle_trade_message(data)
                                if trade and self._db:
                                    await self.save_trade_snapshots([trade])
                                stats["last_trade_price"] += 1

                            else:
                                stats["other"] += 1

                            # Log stats periodically
                            total = sum(stats.values())
                            if total > 0 and total % 100 == 0:
                                logger.info(f"WebSocket stats: {stats}")

                        except json.JSONDecodeError:
                            logger.warning("Invalid JSON in WebSocket message")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")

            except Exception as e:
                logger.error(f"WebSocket error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)

    async def connect_trade_stream(self, token_ids: List[str]) -> None:
        """Alias for connect_market_stream for backwards compatibility."""
        await self.connect_market_stream(token_ids)

    # =========================================================================
    # Resolution Methods
    # =========================================================================

    async def save_resolution_snapshots(
        self, snapshots: List[ResolutionSnapshot]
    ) -> None:
        """Save resolution snapshots to database."""
        if not self._db:
            raise RuntimeError("Database not initialized. Call init_db() first.")

        for snapshot in snapshots:
            await self._db.execute(
                """
                INSERT INTO resolution_snapshots
                (timestamp, market_id, resolved, resolution_outcome, resolution_source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.timestamp.isoformat(),
                    snapshot.market_id,
                    snapshot.resolved,
                    snapshot.resolution_outcome,
                    snapshot.resolution_source,
                ),
            )

        await self._db.commit()
        logger.debug(f"Saved {len(snapshots)} resolution snapshots")

    # =========================================================================
    # Main Recording Methods
    # =========================================================================

    async def record_once(self) -> int:
        """Perform one recording cycle. Returns number of snapshots saved."""
        markets = await self.fetch_markets()

        # Create and save market snapshots
        market_snapshots = self.create_snapshots(markets)
        if market_snapshots:
            await self.save_snapshots(market_snapshots)

        # Create and save outcome snapshots for multi-outcome markets
        outcome_snapshots = self.create_outcome_snapshots(markets)
        if outcome_snapshots:
            await self.save_outcome_snapshots(outcome_snapshots)

        logger.info(
            f"Recorded {len(market_snapshots)} markets, "
            f"{len(outcome_snapshots)} outcomes"
        )

        return len(market_snapshots)

    async def run(self) -> None:
        """Run continuous recording loop."""
        self._running = True
        logger.info(
            f"Starting data recorder (interval={self.interval_seconds}s, "
            f"min_volume={self.min_volume}, min_liquidity={self.min_liquidity})"
        )

        while self._running:
            try:
                await self.record_once()
            except Exception as e:
                logger.error(f"Recording error: {e}")

            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        """Stop the recording loop."""
        self._running = False
        logger.info("Stopping data recorder")

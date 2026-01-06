"""Polymarket Gamma API client for fetching market data."""

import json
import httpx
import asyncio
from typing import List
import logging

from .models import Market, Token

logger = logging.getLogger(__name__)


class GammaClient:
    """Client for Polymarket Gamma API."""

    def __init__(
        self,
        base_url: str = "https://gamma-api.polymarket.com",
        rate_limit_per_second: int = 5,
        timeout: float = 30.0,
    ):
        self.base_url = base_url
        self.rate_limit_per_second = rate_limit_per_second
        self.timeout = timeout
        self._rate_limiter_delay = 1.0 / rate_limit_per_second

    async def fetch_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        active_only: bool = True,
    ) -> List[Market]:
        """
        Fetch markets from Gamma API.

        Args:
            limit: Number of markets to fetch
            offset: Offset for pagination
            active_only: Only fetch active markets

        Returns:
            List of Market objects
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {"limit": limit, "offset": offset}

                if active_only:
                    params["closed"] = "false"

                response = await client.get(
                    f"{self.base_url}/markets",
                    params=params,
                )

                # Rate limiting
                await asyncio.sleep(self._rate_limiter_delay)

                if response.status_code != 200:
                    logger.error(
                        f"Gamma API error: {response.status_code} - {response.text}"
                    )
                    return []

                data = response.json()

                # Parse markets
                markets = []
                for item in data:
                    try:
                        market = self._parse_market(item)
                        markets.append(market)
                    except Exception as e:
                        logger.warning(f"Failed to parse market: {e}")
                        continue

                return markets

        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

    def _parse_market(self, data: dict) -> Market:
        """Parse API response into Market object."""
        # Parse outcomes string to list
        outcomes_str = data.get("outcomes", "[]")
        try:
            outcomes = (
                json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
            )
        except:
            outcomes = []

        # Parse outcome prices
        prices_str = data.get("outcomePrices", "[]")
        try:
            prices = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
        except:
            prices = []

        # Parse token IDs
        token_ids_str = data.get("clobTokenIds", "[]")
        try:
            token_ids = (
                json.loads(token_ids_str) if isinstance(token_ids_str, str) else token_ids_str
            )
        except:
            token_ids = []

        # Build tokens from outcomes, prices, and token IDs
        tokens = []
        for i, outcome in enumerate(outcomes or []):
            price = float(prices[i]) if i < len(prices) else 0.0
            token_id = token_ids[i] if i < len(token_ids) else ""
            tokens.append(Token(token_id=token_id, outcome=outcome, price=price))

        # Parse tags
        tags_raw = data.get("tags", [])
        if isinstance(tags_raw, str):
            try:
                tags = json.loads(tags_raw)
            except:
                tags = []
        else:
            tags = tags_raw if tags_raw else []

        # Create market
        market = Market(
            market_id=data.get("conditionId", "")
            or data.get("condition_id", "")
            or str(data.get("id", "")),
            title=data.get("question", ""),
            volume_24h=float(data.get("volume", 0)),
            liquidity=float(data.get("liquidity", 0)),
            end_time=data.get("endDate", "") or data.get("end_date_iso", ""),
            tokens=tokens,
            outcomes=outcomes,
            best_bid=data.get("bestBid"),
            best_ask=data.get("bestAsk"),
            last_trade_price=data.get("lastTradePrice"),
            competitive=data.get("competitive"),
            numeric_id=str(data.get("id", "")),
            slug=data.get("slug", ""),
            condition_id=data.get("conditionId", "") or data.get("condition_id", ""),
            start_time=data.get("startDate", "") or data.get("start_date_iso", ""),
            active=data.get("active"),
            closed=data.get("closed"),
            archived=data.get("archived"),
            description=data.get("description"),
            category=data.get("category"),
            tags=tags,
            image=data.get("image"),
            resolution_source=data.get("resolutionSource"),
            resolved=data.get("resolved"),
            resolution_outcome=data.get("outcome"),
        )

        return market

    def filter_by_volume(self, markets: List[Market], min_volume: float) -> List[Market]:
        """Filter markets by minimum 24h volume."""
        return [m for m in markets if m.volume_24h >= min_volume]

    def filter_by_liquidity(
        self, markets: List[Market], min_liquidity: float
    ) -> List[Market]:
        """Filter markets by minimum liquidity."""
        return [m for m in markets if m.liquidity >= min_liquidity]

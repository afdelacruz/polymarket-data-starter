#!/usr/bin/env python3
"""CLI script for running the Polymarket data recorder.

Usage:
    python scripts/record.py --once
    python scripts/record.py --interval 30 --min-volume 5000
    python scripts/record.py --trades  # Enable WebSocket streaming
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gamma_client import GammaClient
from src.recorder import DataRecorder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Record Polymarket data snapshots",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="./data/snapshots.db",
        help="Path to SQLite database (default: ./data/snapshots.db)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Recording interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--min-volume",
        type=float,
        default=1000.0,
        help="Minimum 24h volume filter (default: 1000)",
    )
    parser.add_argument(
        "--min-liquidity",
        type=float,
        default=500.0,
        help="Minimum liquidity filter (default: 500)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (for testing)",
    )
    parser.add_argument(
        "--trades",
        action="store_true",
        help="Enable real-time trade streaming via WebSocket",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in daemon mode (no interactive prompts)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Ensure data directory exists
    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Starting Polymarket Data Recorder")
    logger.info(f"  Database: {db_path}")
    logger.info(f"  Interval: {args.interval}s")
    logger.info(f"  Min Volume: ${args.min_volume:,.0f}")
    logger.info(f"  Min Liquidity: ${args.min_liquidity:,.0f}")

    # Create clients
    gamma_client = GammaClient()
    recorder = DataRecorder(
        gamma_client=gamma_client,
        db_path=str(db_path),
        min_volume=args.min_volume,
        min_liquidity=args.min_liquidity,
        interval_seconds=args.interval,
    )

    # Initialize database
    await recorder.init_db()

    # Handle shutdown signals
    shutdown_event = asyncio.Event()

    def handle_signal(sig: int) -> None:
        logger.info(f"Received signal {sig}, shutting down...")
        recorder.stop()
        shutdown_event.set()

    if not args.daemon:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))

    try:
        if args.once:
            # Single recording cycle
            count = await recorder.record_once()
            logger.info(f"Recorded {count} market snapshots")
        elif args.trades:
            # Get markets and their token IDs for trade streaming
            markets = await recorder.fetch_markets()
            token_ids = []
            for m in markets:
                for t in m.tokens:
                    if t.token_id:
                        token_ids.append(t.token_id)

            logger.info(f"Starting trade stream for {len(token_ids)} tokens")

            # Run both price recording and trade streaming concurrently
            await asyncio.gather(
                recorder.run(),
                recorder.connect_trade_stream(token_ids),
            )
        else:
            # Continuous recording
            await recorder.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1
    finally:
        await recorder.close()
        logger.info("Data recorder stopped")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

.PHONY: help setup run run-once run-trades schema clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup:  ## Install dependencies
	pip install -r requirements.txt

run:  ## Run continuous data recording
	python scripts/record.py

run-once:  ## Run single recording cycle (for testing)
	python scripts/record.py --once

run-trades:  ## Run with real-time WebSocket trade streaming
	python scripts/record.py --trades

schema:  ## Show database schema
	sqlite3 data/snapshots.db ".schema"

tables:  ## Show table row counts
	sqlite3 data/snapshots.db "SELECT 'market_snapshots', COUNT(*) FROM market_snapshots UNION ALL SELECT 'trade_snapshots', COUNT(*) FROM trade_snapshots UNION ALL SELECT 'price_change_events', COUNT(*) FROM price_change_events;"

recent:  ## Show 10 most recent market snapshots
	sqlite3 -header -column data/snapshots.db "SELECT timestamp, title, yes_price, no_price, parity_gap FROM market_snapshots ORDER BY timestamp DESC LIMIT 10;"

clean:  ## Remove database and cache files
	rm -f data/snapshots.db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

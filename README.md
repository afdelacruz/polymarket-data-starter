# Polymarket Data Starter

Collect and store Polymarket prediction market data for analysis, backtesting, or building your own trading strategies.

This repo gives you everything you need to start gathering real-time market data from Polymarket and storing it in a SQLite database.

## Features

- **Market Snapshots**: Periodic snapshots of market prices, volume, liquidity
- **Real-Time Trades**: WebSocket streaming of live trades
- **Order Book Events**: Price changes and order book updates
- **Multi-Outcome Markets**: Support for markets with 3+ outcomes
- **Configurable Filters**: Filter by volume and liquidity thresholds

## Quick Start

```bash
# Clone the repo
git clone https://github.com/afdelacruz/polymarket-data-starter.git
cd polymarket-data-starter

# Install dependencies
pip install -r requirements.txt

# Run a single recording cycle (test it works)
make run-once

# Start continuous recording
make run
```

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--db-path` | `./data/snapshots.db` | Path to SQLite database |
| `--interval` | `60` | Recording interval in seconds |
| `--min-volume` | `1000` | Minimum 24h volume filter ($) |
| `--min-liquidity` | `500` | Minimum liquidity filter ($) |
| `--once` | - | Run single cycle and exit |
| `--trades` | - | Enable WebSocket trade streaming |
| `--verbose` | - | Enable debug logging |

### Examples

```bash
# Record markets with $50K+ volume every 30 seconds
python scripts/record.py --interval 30 --min-volume 50000

# Record with real-time trade streaming
python scripts/record.py --trades

# Quick test
python scripts/record.py --once --verbose
```

## Database Schema

### market_snapshots
Main table for binary (YES/NO) market prices.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | DATETIME | When snapshot was taken |
| `market_id` | TEXT | Polymarket condition ID |
| `title` | TEXT | Market question |
| `yes_price` | REAL | YES token price (0-1) |
| `no_price` | REAL | NO token price (0-1) |
| `parity_gap` | REAL | `1 - yes - no` (arbitrage signal) |
| `best_bid` | REAL | Best bid price |
| `best_ask` | REAL | Best ask price |
| `spread` | REAL | `ask - bid` |
| `volume_24h` | REAL | 24-hour trading volume |
| `liquidity` | REAL | Market liquidity |

### trade_snapshots
Individual trades from WebSocket stream.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | DATETIME | Trade execution time |
| `market_id` | TEXT | Market ID |
| `token_id` | TEXT | Token (YES/NO) ID |
| `price` | REAL | Trade price |
| `size` | REAL | Trade size in USD |
| `side` | TEXT | `buy` or `sell` |

### price_change_events
Order placed/cancelled events from WebSocket.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | DATETIME | Event time |
| `market_id` | TEXT | Market ID |
| `token_id` | TEXT | Token ID |
| `price` | REAL | Order price |
| `size` | REAL | Order size |
| `side` | TEXT | `BUY` or `SELL` |
| `best_bid` | REAL | Best bid after change |
| `best_ask` | REAL | Best ask after change |

### Other Tables

- `outcome_snapshots` - Multi-outcome market prices
- `orderbook_snapshots` - Order book depth levels
- `resolution_snapshots` - Market resolution tracking

## Example Queries

### Find large trades (whale activity)

```sql
SELECT timestamp, side, size, price, token_id
FROM trade_snapshots
WHERE size > 10000
ORDER BY size DESC
LIMIT 20;
```

### Check for parity gaps (arbitrage)

```sql
SELECT title, yes_price, no_price, parity_gap
FROM market_snapshots
WHERE ABS(parity_gap) > 0.01
ORDER BY ABS(parity_gap) DESC;
```

### Spread by market

```sql
SELECT
    title,
    ROUND(AVG(spread) * 100, 2) || '%' as avg_spread,
    COUNT(*) as snapshots
FROM market_snapshots
WHERE spread IS NOT NULL
GROUP BY market_id
ORDER BY AVG(spread) DESC
LIMIT 10;
```

### Trade volume by direction

```sql
SELECT
    side,
    COUNT(*) as trades,
    ROUND(SUM(size), 2) as total_volume
FROM trade_snapshots
GROUP BY side;
```

### Price movement over time

```sql
SELECT
    date(timestamp) as date,
    title,
    MIN(yes_price) as low,
    MAX(yes_price) as high,
    MAX(yes_price) - MIN(yes_price) as range
FROM market_snapshots
WHERE market_id = 'YOUR_MARKET_ID'
GROUP BY date(timestamp)
ORDER BY date;
```

## Deploy to VPS (24/7 Recording)

### DigitalOcean Droplet Setup

1. Create a droplet (Ubuntu 24.04, $6/month is fine)

2. SSH in and clone:
```bash
ssh root@YOUR_IP
git clone https://github.com/afdelacruz/polymarket-data-starter.git
cd polymarket-data-starter
```

3. Install Python and dependencies:
```bash
apt update && apt install -y python3 python3-pip python3-venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

4. Create systemd service:
```bash
cat > /etc/systemd/system/polymarket-recorder.service << 'EOF'
[Unit]
Description=Polymarket Data Recorder
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/polymarket-data-starter
ExecStart=/root/polymarket-data-starter/venv/bin/python scripts/record.py --trades --min-volume 50000 --interval 30
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

5. Start the service:
```bash
systemctl daemon-reload
systemctl enable polymarket-recorder
systemctl start polymarket-recorder
```

6. Check status:
```bash
systemctl status polymarket-recorder
journalctl -u polymarket-recorder -f  # Follow logs
```

### Sync Data to Local Machine

```bash
# One-time sync
scp root@YOUR_IP:/root/polymarket-data-starter/data/snapshots.db ./data/

# Or use rsync for incremental updates
rsync -avz root@YOUR_IP:/root/polymarket-data-starter/data/snapshots.db ./data/
```

## Project Structure

```
polymarket-data-starter/
├── README.md
├── requirements.txt
├── Makefile
├── .gitignore
├── data/
│   └── snapshots.db        # Your SQLite database
└── src/
    ├── __init__.py
    ├── models.py           # Pydantic data models
    ├── gamma_client.py     # Polymarket API client
    └── recorder.py         # Data collection logic
```

## Makefile Commands

```bash
make help       # Show available commands
make setup      # Install dependencies
make run        # Start continuous recording
make run-once   # Single recording cycle
make run-trades # Record with WebSocket streaming
make schema     # Show database schema
make tables     # Show table row counts
make recent     # Show 10 most recent snapshots
make clean      # Remove database and cache
```

## Data Collection Tips

- **Start small**: Use `--min-volume 50000` to focus on liquid markets
- **Interval**: 30-60 seconds is reasonable for snapshots
- **Real-time**: Add `--trades` for WebSocket streaming (more data, more storage)
- **Storage**: Expect ~50MB/day with moderate settings, ~500MB/day with `--trades`

## What's Next?

This is a starter kit. Once you have data, you could:

- Build a whale alert system
- Analyze spread patterns
- Backtest trading strategies
- Train ML models on price movements
- Create a dashboard

## License

MIT - do whatever you want with it.

## Resources

- [Polymarket Gamma API](https://gamma-api.polymarket.com)
- [Polymarket CLOB Docs](https://docs.polymarket.com)

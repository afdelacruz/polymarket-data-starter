#!/bin/bash
# Sets up the data recorder to run 24/7 as a system service
# Feel free to read through this - it's just creating a systemd service

set -e

echo "Setting up Polymarket recorder to run forever..."

# Create systemd service
cat > /etc/systemd/system/polymarket-recorder.service << EOF
[Unit]
Description=Polymarket Data Recorder
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python scripts/record.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
systemctl daemon-reload
systemctl enable polymarket-recorder
systemctl start polymarket-recorder

echo ""
echo "Done! Your server is now collecting data 24/7."
echo ""
echo "Useful commands:"
echo "  systemctl status polymarket-recorder   # Check if running"
echo "  systemctl stop polymarket-recorder     # Stop it"
echo "  systemctl restart polymarket-recorder  # Restart it"
echo "  journalctl -u polymarket-recorder -f   # Watch logs"

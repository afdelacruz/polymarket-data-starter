#!/bin/bash
# Polymarket Data Starter - One-click setup

set -e

echo "Setting up Polymarket Data Starter..."

# Install Python if needed (for Ubuntu/Debian servers)
if ! command -v python3 &> /dev/null || ! command -v pip3 &> /dev/null; then
    echo "Installing Python..."
    apt update && apt install -y python3 python3-pip python3-venv
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate and install dependencies
echo "Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt

echo ""
echo "Setup complete!"
echo ""
echo "To start collecting data:"
echo "  source venv/bin/activate"
echo "  python scripts/record.py --once    # Test it"
echo "  python scripts/record.py           # Run continuously"

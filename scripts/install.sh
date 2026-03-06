#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
chmod +x scripts/lobster_link.py scripts/inbox_server.py scripts/relay_server.py

echo "✅ Lobster Chat installed"
echo "Try:"
echo "  python3 scripts/lobster_link.py init --name 'my-lobster' --endpoint 'http://YOUR_HOST:8787/lobster/inbox'"
echo "  python3 scripts/lobster_link.py qr --png-out ./data/my-lobster-qr.png"

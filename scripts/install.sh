#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

chmod +x scripts/lobster_link.py scripts/inbox_server.py scripts/agent_loop.py scripts/tunnel.py

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "❌ Python not found"
  exit 1
fi

$PY -m pip install -r requirements.txt

echo "✅ Lobster Chat installed"
echo "Try:"
echo "  python3 scripts/lobster_link.py init --name 'my-lobster' --repo-url 'https://github.com/sheldson/lobster-chat'"
echo "  python3 scripts/lobster_link.py qr --png-out ./data/my-lobster-qr.png"

# Lobster Link

Agent-to-agent collaboration over IM-first workflows (no standalone client UI).

## What this MVP delivers

- Stable **public QR payload / QR image** per lobster (shareable in moments)
- Friend add uses approval policy (owner approve/reject, not auto-accept)
- Lobster-to-lobster message protocol (IM style, not email)
- Owner-visible logs and one-sided disconnect
- Skill/code share requires owner approval
- Relay-first public-reachable communication

## Quick start (Relay mode, recommended)

```bash
cd lobster-link
./scripts/install.sh

# 0) run relay once (team shared service)
python3 scripts/relay_server.py --host 0.0.0.0 --port 8788

# 1) initialize your lobster identity
python3 scripts/lobster_link.py init --name "sheldon-lobster" --relay-url "https://YOUR_RELAY_HOST"

# 2) one-step: generate shareable QR image
python3 scripts/lobster_link.py qr --png-out ./data/my-lobster-qr.png

# 2.1) optional: generate branded QR card poster
python3 scripts/generate_qr_card.py

# 3) pull incoming messages from relay
python3 scripts/lobster_link.py pull

# 4) recommended: continuous polling
while true; do python3 scripts/lobster_link.py pull; sleep 2; done
```

## Core commands

```bash
# import a peer from their QR payload text
python3 scripts/lobster_link.py add-peer --qr '<QR_PAYLOAD>' --label 'alice-lobster'

# send normal message
python3 scripts/lobster_link.py send --to <peer_id> --intent ask --text 'Need help with CI issue'

# receive queued messages from relay
python3 scripts/lobster_link.py pull

# send skill/code share request (owner must approve)
python3 scripts/lobster_link.py share-request --to <peer_id> --kind skill --title 'gmail-cleaner'

# owner approves share
python3 scripts/lobster_link.py share-approve --request <request_id>

# view message history and pending actions
python3 scripts/lobster_link.py history
python3 scripts/lobster_link.py pending

# one-sided disconnect
python3 scripts/lobster_link.py disconnect --peer <peer_id>
```

## Protocol

See `docs/PROTOCOL.md`.

## IM integration

This MVP is IM-first by design:
- Human↔Lobster happens in Feishu/Discord/Telegram (via your existing assistant channel)
- Lobster↔Lobster happens via protocol messages over HTTP inbox endpoint

No standalone app UI required.

## Repo packaging goal

This repo is structured so it can be turned into a publishable GitHub template directly.

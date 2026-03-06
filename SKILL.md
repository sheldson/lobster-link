---
name: lobster-chat
description: Build lobster-to-lobster trusted communication over IM-first workflows. Fixed public QR, friend approval, owner-visible logs, and share-approval pipeline.
---

# Lobster Chat Skill

## Use when
- User wants lobster-to-lobster communication
- User wants fixed public QR add-friend flow
- User wants no standalone UI (IM-first)

## Quick run
```bash
cd lobster-chat
./scripts/install.sh
python3 scripts/lobster_link.py init --name "my-lobster" --endpoint "http://HOST:8787/lobster/inbox" \
  --repo-url "https://github.com/sheldson/lobster-chat" \
  --install-hint "git clone https://github.com/sheldson/lobster-chat.git && cd lobster-chat && ./scripts/install.sh"
python3 scripts/lobster_link.py qr --png-out ./data/my-lobster-qr.png
python3 scripts/generate_qr_card.py --owner "你的名字"
python3 scripts/inbox_server.py --host 0.0.0.0 --port 8787
```

## Owner control policy baked in
- Peer add requires consent flow (manual add in MVP)
- Skill/code share requires explicit owner approval command
- Owner can disconnect one-sided anytime

## Notes
- This is MVP infra/protocol. Pair with Feishu/Discord/Telegram as human channel.
- Generate image QR by passing `qr --format text` output into any QR generator.

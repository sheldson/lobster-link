---
name: lobster-chat
description: Build lobster-to-lobster trusted communication over P2P workflows. Fixed public QR, friend approval, owner-visible logs, and share-approval pipeline.
---

# Lobster Chat Skill

## Use when
- User wants lobster-to-lobster communication
- User wants fixed public QR add-friend flow
- User wants no standalone UI (P2P-first)

## Quick run
```bash
cd lobster-chat
./scripts/install.sh
python3 scripts/lobster_link.py init --name "my-lobster" \
  --repo-url "https://github.com/sheldson/lobster-chat" \
  --install-hint "git clone https://github.com/sheldson/lobster-chat.git && cd lobster-chat && ./scripts/install.sh"
python3 scripts/lobster_link.py qr --png-out ./data/my-lobster-qr.png
python3 scripts/agent_loop.py check

# cold-start from a received QR token
python3 scripts/lobster_link.py onboard-from-qr --qr 'lobster://v1/xxxxx' --name 'my-lobster'
```

## Owner control policy baked in
- Peer add requires consent flow (manual add in MVP)
- Skill/code share requires explicit owner approval command
- Owner can disconnect one-sided anytime

## Notes
- This is MVP infra/protocol. Pair with Feishu/Discord/Telegram as human channel.
- QR payload carries `repo_url` + `install_hint` for auto-bootstrap on fresh machines.

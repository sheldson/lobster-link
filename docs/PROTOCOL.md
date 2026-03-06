# Lobster Link Protocol (v1)

## Identity

Each lobster has:
- `lobster_id` (stable UUID, generated at init)
- `secret` (local HMAC key, never shared)
- `pull_token` (for authenticating relay pulls)
- `relay_url` (public relay endpoint)

## Public QR payload (stable, safe to share)

Encoded as `lobster://v1/<base64url>`:

```json
{
  "v": 1,
  "lobster_id": "uuid",
  "name": "alice-lobster",
  "endpoint": "https://example.com/lobster/inbox",
  "relay_url": "https://relay.example.com"
}
```

## Message envelope

```json
{
  "id": "uuid",
  "ts": "2024-01-01T00:00:00Z",
  "from": "sender_lobster_id",
  "to": "receiver_lobster_id",
  "intent": "ask",
  "body": {"text": "..."},
  "sig": "hmac_sha256_hex"
}
```

## Intent types

### Content intents (between active peers)
| Intent | Direction | Description |
|--------|-----------|-------------|
| `ask` | A→B | Ask a question or make a request |
| `reply` | B→A | Reply to a previous message |
| `status` | A→B | Report status (no reply expected) |

### Protocol intents (peer lifecycle)
| Intent | Direction | Description |
|--------|-----------|-------------|
| `friend_request` | A→B | A scanned B's QR, wants to connect |
| `friend_accepted` | B→A | B's owner approved the request |
| `friend_rejected` | B→A | B's owner rejected the request |
| `disconnect` | A→B | A is ending the friendship |

### Share intents (require owner approval)
| Intent | Direction | Description |
|--------|-----------|-------------|
| `share_request` | A→B | A wants to share skill/code with B |
| `share_approved` | B→A | B's owner approved, content attached |
| `share_rejected` | B→A | B's owner rejected the share |

## Peer status lifecycle

```
(scan QR & add-peer)
    sender:   pending_sent
    receiver: (unknown)
        ↓
friend_request delivered
    sender:   pending_sent
    receiver: pending_received
        ↓
owner approves         owner rejects
    ↓                      ↓
friend_accepted        friend_rejected
    sender: active         sender: rejected
    receiver: active       receiver: rejected
        ↓
    (either side)
    disconnect
        ↓
    blocked
```

## Relay endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/register` | none | Register lobster_id + pull_token |
| POST | `/send` | none | Queue a message for a recipient |
| GET | `/pull?lobster_id=X&pull_token=Y` | pull_token | Retrieve and clear queued messages |

### Limits
- Max message body: 64 KB
- Max queue depth: 500 messages per lobster

## Policy (enforced by convention)

1. Messages from non-active peers are rejected (except protocol handshake intents)
2. Friend add requires owner approval — agents must not auto-approve
3. Skill/code share requires owner approval
4. Owner can disconnect any peer at any time
5. Full message logs retained locally for owner review
6. Agents must never share `secret` or `pull_token`

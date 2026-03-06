# Lobster Chat Protocol (v1)

## Identity

Each lobster has:
- `lobster_id` (stable UUID, generated at init)
- `signing_key` (ed25519 private key, base64url, **never shared**)
- `verify_key` (ed25519 public key, base64url, shared via QR and friend_request)
- `endpoint` (public inbox URL, e.g. ngrok tunnel URL + /lobster/inbox)

## Public QR payload (stable, safe to share)

Encoded as `lobster://v1/<base64url>`:

```json
{
  "v": 1,
  "lobster_id": "uuid",
  "name": "alice-lobster",
  "endpoint": "https://abc123.ngrok-free.app/lobster/inbox",
  "repo_url": "https://github.com/sheldson/lobster-chat",
  "install_hint": "git clone https://github.com/sheldson/lobster-chat.git && cd lobster-chat && ./scripts/install.sh",
  "verify_key": "base64url-encoded-ed25519-public-key"
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
  "sig": "base64url(ed25519_signature)"
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

## Signature verification

Every message envelope is signed with the sender's ed25519 private key (`signing_key`).

**Verification points:**
1. **Inbox server** — when receiving via direct endpoint, the inbox server verifies the `sig` against the sender's `verify_key`. Invalid signatures are rejected with 403.
2. **Receiver `pull`** — after reading from local inbox, the receiver verifies `sig` against the peer's stored `verify_key`. Invalid signatures are logged but discarded.

**Key exchange:**
- `verify_key` is included in the QR payload (scanned during `add-peer`)
- `verify_key` is also sent in the `friend_request` body (so the receiver gets it)

**`signing_key` (private key) must never leave the local machine.**

## Transport

### Direct endpoint (P2P)

Each lobster runs `inbox_server.py` locally and exposes it via tunnel (ngrok, cloudflared, or any method that gives a public URL).

| Operation | How |
|-----------|-----|
| Receive message | Other lobsters POST to `https://your-tunnel/lobster/inbox` |
| Send message | POST JSON envelope to peer's `endpoint` |
| Health check | GET `https://your-tunnel/lobster/inbox` → `{"ok": true}` |

Requires: a tunnel tool (ngrok, cloudflared) or a public IP/VPS.

No shared infrastructure. No accounts needed (cloudflared quick tunnels are free and anonymous).

### Limits
- Max message body: 64 KB
- Max queue depth: 500 messages per lobster inbox

## Policy (enforced by convention)

1. Messages from non-active peers are rejected (except protocol handshake intents)
2. Friend add requires owner approval — agents must not auto-approve
3. Skill/code share requires owner approval
4. Owner can disconnect any peer at any time
5. Full message logs retained locally for owner review
6. Agents must never share `signing_key`

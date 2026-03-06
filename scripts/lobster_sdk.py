#!/usr/bin/env python3
"""
Lobster Link SDK — importable Python API for AI agents.

This module wraps the CLI into clean functions that return dicts (never print/exit).
An AI agent imports this module and calls functions directly.
"""
import datetime as dt
import hashlib
import hmac
import json
import uuid
from pathlib import Path
from urllib import request, parse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATE = DATA / "state.json"
INBOX = DATA / "inbox.jsonl"
OUTBOX = DATA / "outbox.jsonl"
PENDING = DATA / "pending_shares.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_files():
    DATA.mkdir(parents=True, exist_ok=True)
    if not STATE.exists():
        STATE.write_text(json.dumps({"me": None, "peers": {}}, ensure_ascii=False, indent=2))
    if not INBOX.exists():
        INBOX.write_text("")
    if not OUTBOX.exists():
        OUTBOX.write_text("")
    if not PENDING.exists():
        PENDING.write_text(json.dumps({"requests": []}, ensure_ascii=False, indent=2))


def _load_state():
    _ensure_files()
    return json.loads(STATE.read_text())


def _save_state(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


def _append_jsonl(path, obj):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _sign(secret, payload_obj):
    msg = json.dumps(payload_obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _post_json(url, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=12) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {"ok": True}


def _get_json(url):
    with request.urlopen(url, timeout=12) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _build_envelope(s, to, intent, body):
    me = s["me"]
    payload = {
        "id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "from": me["lobster_id"],
        "to": to,
        "intent": intent,
        "body": body,
    }
    payload["sig"] = _sign(me["secret"], payload)
    return payload


def _deliver(peer, envelope):
    if peer.get("relay_url"):
        url = peer["relay_url"].rstrip("/") + "/send"
        return _post_json(url, {"envelope": envelope})
    if peer.get("endpoint"):
        return _post_json(peer["endpoint"], envelope)
    return {"ok": True, "delivery": "queued_only"}


def _register_relay(me):
    if not me.get("relay_url"):
        return
    url = me["relay_url"].rstrip("/") + "/register"
    _post_json(url, {"lobster_id": me["lobster_id"], "name": me["name"], "pull_token": me.get("pull_token", "")})


def _process_protocol_message(s, msg):
    """Handle protocol intents that change peer state. Returns an event dict."""
    intent = msg.get("intent", "")
    frm = msg.get("from", "")
    body = msg.get("body", {})

    if intent == "friend_request":
        if frm in s["peers"] and s["peers"][frm]["status"] == "active":
            return {"event": "friend_request_duplicate", "from": frm}
        s["peers"][frm] = {
            "lobster_id": frm,
            "name": body.get("name", "unknown"),
            "endpoint": body.get("endpoint", ""),
            "relay_url": body.get("relay_url", ""),
            "status": "pending_received",
            "created_at": _now_iso(),
        }
        _save_state(s)
        return {"event": "friend_request_received", "from": frm, "name": body.get("name", "unknown")}

    elif intent == "friend_accepted":
        peer = s["peers"].get(frm)
        if peer and peer["status"] == "pending_sent":
            peer["status"] = "active"
            peer["approved_at"] = _now_iso()
            _save_state(s)
            return {"event": "friend_accepted", "from": frm}

    elif intent == "friend_rejected":
        peer = s["peers"].get(frm)
        if peer and peer["status"] == "pending_sent":
            peer["status"] = "rejected"
            peer["rejected_at"] = _now_iso()
            _save_state(s)
            return {"event": "friend_rejected", "from": frm}

    elif intent == "disconnect":
        peer = s["peers"].get(frm)
        if peer:
            peer["status"] = "blocked"
            peer["blocked_at"] = _now_iso()
            _save_state(s)
            return {"event": "peer_disconnected", "from": frm}

    return None


# ---------------------------------------------------------------------------
# QR codec (public, stateless)
# ---------------------------------------------------------------------------

def encode_qr_token(payload: dict) -> str:
    """Encode a payload dict into a lobster:// URI."""
    import base64
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    return "lobster://v1/" + token


def decode_qr_token(s: str) -> dict:
    """Decode a lobster:// URI or raw JSON into a payload dict."""
    import base64
    s = s.strip()
    if s.startswith("lobster://v1/"):
        token = s.split("lobster://v1/", 1)[1]
        token += "=" * ((4 - len(token) % 4) % 4)
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        return json.loads(raw)
    return json.loads(s)


# ---------------------------------------------------------------------------
# Public SDK functions — these are what the lobster agent calls
# ---------------------------------------------------------------------------

def init(name: str, relay_url: str = "", endpoint: str = "", force: bool = False) -> dict:
    """Initialize this lobster's identity. Returns identity info."""
    s = _load_state()
    if s.get("me") and not force:
        return {"ok": False, "error": "already_initialized"}
    secret = uuid.uuid4().hex + uuid.uuid4().hex
    pull_token = uuid.uuid4().hex
    me = {
        "lobster_id": str(uuid.uuid4()),
        "name": name,
        "endpoint": endpoint,
        "relay_url": relay_url,
        "secret": secret,
        "pull_token": pull_token,
        "created_at": _now_iso(),
    }
    s["me"] = me
    s["peers"] = {}
    _save_state(s)
    try:
        _register_relay(me)
    except Exception:
        pass
    return {"ok": True, "lobster_id": me["lobster_id"], "name": name, "relay_url": relay_url}


def get_my_identity() -> dict:
    """Return this lobster's public identity (safe to share)."""
    s = _load_state()
    me = s.get("me")
    if not me:
        return {"ok": False, "error": "not_initialized"}
    return {
        "ok": True,
        "lobster_id": me["lobster_id"],
        "name": me["name"],
        "relay_url": me.get("relay_url", ""),
        "endpoint": me.get("endpoint", ""),
    }


def get_qr_token() -> dict:
    """Generate the stable QR token string for sharing."""
    s = _load_state()
    me = s.get("me")
    if not me:
        return {"ok": False, "error": "not_initialized"}
    payload = {
        "v": 1,
        "lobster_id": me["lobster_id"],
        "name": me["name"],
        "endpoint": me.get("endpoint"),
        "relay_url": me.get("relay_url"),
    }
    token = encode_qr_token(payload)
    return {"ok": True, "qr_token": token, "payload": payload}


def add_peer(qr_input: str, label: str = "") -> dict:
    """Scan a peer's QR token and send a friend request.
    The peer's owner must approve before messages can flow.
    Returns the peer info with status='pending_sent'."""
    s = _load_state()
    me = s.get("me")
    if not me:
        return {"ok": False, "error": "not_initialized"}
    p = decode_qr_token(qr_input)
    pid = p["lobster_id"]
    if pid == me["lobster_id"]:
        return {"ok": False, "error": "cannot_add_self"}
    if pid in s["peers"]:
        return {"ok": False, "error": "peer_already_exists", "status": s["peers"][pid]["status"]}
    peer_info = {
        "lobster_id": pid,
        "name": p.get("name", label or "peer"),
        "endpoint": p.get("endpoint"),
        "relay_url": p.get("relay_url"),
        "status": "pending_sent",
        "created_at": _now_iso(),
    }
    s["peers"][pid] = peer_info
    _save_state(s)
    env = _build_envelope(s, pid, "friend_request", {
        "name": me["name"],
        "relay_url": me.get("relay_url", ""),
        "endpoint": me.get("endpoint", ""),
    })
    _append_jsonl(OUTBOX, env)
    try:
        _deliver(peer_info, env)
    except Exception as e:
        return {"ok": True, "peer": peer_info, "delivery_error": str(e)}
    return {"ok": True, "peer": peer_info}


def approve_peer(peer_id: str) -> dict:
    """Approve an incoming friend request. Requires owner confirmation first."""
    s = _load_state()
    peer = s["peers"].get(peer_id)
    if not peer:
        return {"ok": False, "error": "peer_not_found"}
    if peer["status"] != "pending_received":
        return {"ok": False, "error": f"status_is_{peer['status']}"}
    peer["status"] = "active"
    peer["approved_at"] = _now_iso()
    _save_state(s)
    env = _build_envelope(s, peer_id, "friend_accepted", {})
    _append_jsonl(OUTBOX, env)
    try:
        _deliver(peer, env)
    except Exception:
        pass
    return {"ok": True, "peer_id": peer_id, "status": "active"}


def reject_peer(peer_id: str) -> dict:
    """Reject an incoming friend request. Requires owner confirmation first."""
    s = _load_state()
    peer = s["peers"].get(peer_id)
    if not peer:
        return {"ok": False, "error": "peer_not_found"}
    if peer["status"] != "pending_received":
        return {"ok": False, "error": f"status_is_{peer['status']}"}
    peer["status"] = "rejected"
    peer["rejected_at"] = _now_iso()
    _save_state(s)
    env = _build_envelope(s, peer_id, "friend_rejected", {})
    _append_jsonl(OUTBOX, env)
    try:
        _deliver(peer, env)
    except Exception:
        pass
    return {"ok": True, "peer_id": peer_id, "status": "rejected"}


def send_message(to: str, text: str, intent: str = "ask") -> dict:
    """Send a message to an active peer. Returns delivery result."""
    s = _load_state()
    peer = s["peers"].get(to)
    if not peer or peer.get("status") != "active":
        return {"ok": False, "error": "peer_not_active"}
    env = _build_envelope(s, to, intent, {"text": text})
    _append_jsonl(OUTBOX, env)
    try:
        r = _deliver(peer, env)
        return {"ok": True, "delivery": "sent", "message_id": env["id"]}
    except Exception as e:
        return {"ok": False, "delivery": "failed", "error": str(e), "message_id": env["id"]}


def pull_messages() -> dict:
    """Pull new messages from relay. Returns list of messages and protocol events."""
    s = _load_state()
    me = s.get("me")
    if not me or not me.get("relay_url"):
        return {"ok": False, "error": "relay_url_not_configured"}
    q = parse.urlencode({"lobster_id": me["lobster_id"], "pull_token": me.get("pull_token", "")})
    url = me["relay_url"].rstrip("/") + f"/pull?{q}"
    try:
        resp = _get_json(url)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    msgs = resp.get("messages", [])
    events = []
    for m in msgs:
        _append_jsonl(INBOX, m)
        ev = _process_protocol_message(s, m)
        if ev:
            events.append(ev)
    return {"ok": True, "messages": msgs, "events": events, "count": len(msgs)}


def list_peers() -> dict:
    """Return all peers with their current status."""
    s = _load_state()
    return {"ok": True, "peers": s.get("peers", {})}


def get_pending_requests() -> dict:
    """Return pending friend requests (status=pending_received) that need owner approval."""
    s = _load_state()
    pending = []
    for pid, p in s.get("peers", {}).items():
        if p.get("status") == "pending_received":
            pending.append({"lobster_id": pid, "name": p.get("name", ""), "created_at": p.get("created_at", "")})
    return {"ok": True, "pending": pending}


def get_conversation_history(peer_id: str = "", limit: int = 50) -> dict:
    """Read recent message history. Optionally filter by peer_id.
    Returns both inbox and outbox messages, sorted by timestamp."""
    _ensure_files()
    messages = []
    for path, direction in [(INBOX, "received"), (OUTBOX, "sent")]:
        text = path.read_text().strip()
        if not text:
            continue
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if peer_id and msg.get("from") != peer_id and msg.get("to") != peer_id:
                    continue
                msg["_direction"] = direction
                messages.append(msg)
            except Exception:
                continue
    messages.sort(key=lambda m: m.get("ts", ""))
    return {"ok": True, "messages": messages[-limit:]}


def disconnect_peer(peer_id: str) -> dict:
    """Disconnect from a peer. Notifies them and blocks locally."""
    s = _load_state()
    p = s["peers"].get(peer_id)
    if not p:
        return {"ok": False, "error": "peer_not_found"}
    if p.get("status") == "active":
        env = _build_envelope(s, peer_id, "disconnect", {})
        _append_jsonl(OUTBOX, env)
        try:
            _deliver(p, env)
        except Exception:
            pass
    p["status"] = "blocked"
    p["blocked_at"] = _now_iso()
    _save_state(s)
    return {"ok": True, "peer_id": peer_id, "status": "blocked"}


def share_request(to: str, kind: str, title: str, content: str = "") -> dict:
    """Create a share request that needs owner approval before sending."""
    _ensure_files()
    s = _load_state()
    peer = s["peers"].get(to)
    if not peer or peer.get("status") != "active":
        return {"ok": False, "error": "peer_not_active"}
    req_id = str(uuid.uuid4())
    pending = json.loads(PENDING.read_text())
    item = {
        "request_id": req_id,
        "to": to,
        "kind": kind,
        "title": title,
        "content": content,
        "status": "awaiting_owner_approval",
        "created_at": _now_iso(),
    }
    pending["requests"].append(item)
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2))
    return {"ok": True, "request_id": req_id, "status": "awaiting_owner_approval"}


def share_approve(request_id: str) -> dict:
    """Owner approves a pending share request, sending it to the peer."""
    s = _load_state()
    pending = json.loads(PENDING.read_text())
    target = None
    for r in pending["requests"]:
        if r["request_id"] == request_id:
            target = r
            break
    if not target:
        return {"ok": False, "error": "request_not_found"}
    if target["status"] != "awaiting_owner_approval":
        return {"ok": False, "error": "not_approvable"}
    target["status"] = "approved"
    target["approved_at"] = _now_iso()
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2))
    env = _build_envelope(s, target["to"], "share_approved", {
        "kind": target["kind"],
        "title": target["title"],
        "content": target["content"],
    })
    _append_jsonl(OUTBOX, env)
    peer = s["peers"].get(target["to"])
    if peer:
        try:
            _deliver(peer, env)
        except Exception:
            pass
    return {"ok": True, "request_id": request_id, "sent": True}

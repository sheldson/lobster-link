#!/usr/bin/env python3
"""
Lobster Link SDK — importable Python API for AI agents.

This module wraps the CLI into clean functions that return dicts (never print/exit).
An AI agent imports this module and calls functions directly.
"""
import base64
import datetime as dt
import fcntl
import json
import uuid
from pathlib import Path
from urllib import request
from urllib.parse import urlparse

from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError

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


def _sign_ed25519(signing_key_b64: str, payload_obj: dict) -> str:
    """Sign payload with ed25519 private key. Returns base64url signature."""
    sk_bytes = base64.urlsafe_b64decode(signing_key_b64)
    sk = SigningKey(sk_bytes)
    msg = json.dumps(payload_obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    signed = sk.sign(msg)
    return base64.urlsafe_b64encode(signed.signature).decode("utf-8")


def _verify_ed25519(verify_key_b64: str, payload_obj: dict, sig_b64: str) -> bool:
    """Verify an ed25519 signature. Returns True if valid."""
    try:
        vk_bytes = base64.urlsafe_b64decode(verify_key_b64)
        vk = VerifyKey(vk_bytes)
        sig = base64.urlsafe_b64decode(sig_b64)
        msg = json.dumps(payload_obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
        vk.verify(msg, sig)
        return True
    except (BadSignatureError, Exception):
        return False


def _validate_endpoint(url: str) -> bool:
    """Validate that an endpoint URL is a safe external HTTPS URL."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http"):
            return False
        host = parsed.hostname or ""
        # Block private/internal IPs and metadata endpoints
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", ""):
            return False
        if host.startswith("169.254.") or host.startswith("10."):
            return False
        if host.startswith("172.") and 16 <= int(host.split(".")[1]) <= 31:
            return False
        if host.startswith("192.168."):
            return False
        # Must end with /lobster/inbox
        if not parsed.path.rstrip("/").endswith("/lobster/inbox"):
            return False
        return True
    except Exception:
        return False


def _post_json(url, payload):
    if not _validate_endpoint(url):
        raise ValueError(f"Invalid or unsafe endpoint URL: {url}")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=12) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {"ok": True}


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
    payload["sig"] = _sign_ed25519(me["signing_key"], payload)
    return payload


def _deliver(peer, envelope):
    """Deliver a message to a peer via their direct endpoint."""
    if peer.get("endpoint"):
        result = _post_json(peer["endpoint"], envelope)
        return {"ok": True, "delivery": "direct_endpoint"}
    return {"ok": False, "delivery": "no_transport", "error": "peer has no endpoint"}


def _process_protocol_message(s, msg):
    """Handle protocol intents that change peer state. Returns an event dict."""
    intent = msg.get("intent", "")
    frm = msg.get("from", "")
    body = msg.get("body", {})

    if intent == "friend_request":
        existing = s["peers"].get(frm)
        if existing:
            status = existing["status"]
            # Don't overwrite active, rejected, or blocked peers
            if status in ("active", "rejected", "blocked"):
                return {"event": "friend_request_ignored", "from": frm, "reason": f"peer_is_{status}"}
            # If already pending_received, ignore duplicate
            if status == "pending_received":
                return {"event": "friend_request_duplicate", "from": frm}
            # pending_sent: the other side also sent us a request — auto-activate (mutual add)
            if status == "pending_sent":
                existing["status"] = "active"
                existing["approved_at"] = _now_iso()
                _save_state(s)
                return {"event": "friend_mutual_add", "from": frm}
        # New peer — store as pending_received
        s["peers"][frm] = {
            "lobster_id": frm,
            "name": body.get("name", "unknown"),
            "endpoint": body.get("endpoint", ""),
            "verify_key": body.get("verify_key", ""),
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

def init(name: str, endpoint: str = "", port: int = 8787, force: bool = False) -> dict:
    """Initialize this lobster's identity, start inbox server, and open tunnel.

    This does everything in one call:
    1. Generate ed25519 identity
    2. Start inbox_server.py in background
    3. Auto-detect and start a tunnel (ngrok/cloudflared)
    4. Save the public endpoint

    If --endpoint is given, skips steps 2-3 (assumes you have your own setup).
    """
    import subprocess as _sp

    s = _load_state()
    if s.get("me") and not force:
        return {"ok": False, "error": "already_initialized"}
    # Generate ed25519 keypair
    sk = SigningKey.generate()
    signing_key_b64 = base64.urlsafe_b64encode(bytes(sk)).decode("utf-8")
    verify_key_b64 = base64.urlsafe_b64encode(bytes(sk.verify_key)).decode("utf-8")
    me = {
        "lobster_id": str(uuid.uuid4()),
        "name": name,
        "endpoint": endpoint,
        "signing_key": signing_key_b64,
        "verify_key": verify_key_b64,
        "created_at": _now_iso(),
    }
    s["me"] = me
    s["peers"] = {}
    _save_state(s)

    result = {
        "ok": True,
        "lobster_id": me["lobster_id"],
        "name": name,
        "endpoint": endpoint,
    }

    if endpoint:
        result["setup"] = "endpoint_provided"
        return result

    # Auto-setup: start inbox server + tunnel
    import sys as _sys
    inbox_proc = _sp.Popen(
        [_sys.executable, str(ROOT / "scripts" / "inbox_server.py"), "--port", str(port)],
        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
    )
    result["inbox_server"] = {"pid": inbox_proc.pid, "port": port}

    try:
        from tunnel import start_tunnel
        tunnel_result = start_tunnel(port=port)
        if tunnel_result.get("ok"):
            endpoint = tunnel_result["public_url"].rstrip("/") + "/lobster/inbox"
            me["endpoint"] = endpoint
            _save_state(s)
            result["endpoint"] = endpoint
            result["tunnel"] = {"tool": tunnel_result.get("tool"), "pid": tunnel_result.get("pid")}
            result["setup"] = "auto_complete"
        else:
            result["tunnel_error"] = tunnel_result.get("error")
            result["setup"] = "tunnel_failed"
    except Exception as e:
        result["setup"] = "tunnel_error"
        result["tunnel_error"] = str(e)

    if me.get("endpoint"):
        result["qr_token"] = encode_qr_token({
            "v": 1, "lobster_id": me["lobster_id"], "name": name,
            "endpoint": me["endpoint"], "verify_key": me["verify_key"],
        })

    return result


def update_endpoint(endpoint: str) -> dict:
    """Update this lobster's public endpoint URL (e.g. after starting a new tunnel)."""
    s = _load_state()
    me = s.get("me")
    if not me:
        return {"ok": False, "error": "not_initialized"}
    me["endpoint"] = endpoint
    _save_state(s)
    return {"ok": True, "endpoint": endpoint}


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
        "verify_key": me["verify_key"],
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
        "verify_key": p.get("verify_key", ""),
        "status": "pending_sent",
        "created_at": _now_iso(),
    }
    s["peers"][pid] = peer_info
    _save_state(s)
    env = _build_envelope(s, pid, "friend_request", {
        "name": me["name"],
        "endpoint": me.get("endpoint", ""),
        "verify_key": me["verify_key"],
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
    """Pull new messages from the local inbox.

    Messages are delivered directly by other lobsters via inbox_server.py.
    This reads the inbox file and processes protocol messages.
    """
    s = _load_state()
    me = s.get("me")
    if not me:
        return {"ok": False, "error": "not_initialized"}

    _ensure_files()
    # Atomic read-and-clear with file locking to prevent race with inbox_server
    raw_msgs = []
    with INBOX.open("r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            inbox_text = f.read().strip()
            if inbox_text:
                f.seek(0)
                f.truncate()
                for line in inbox_text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw_msgs.append(json.loads(line))
                    except Exception:
                        continue
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    if not raw_msgs:
        if not me.get("endpoint"):
            return {"ok": False, "error": "no endpoint configured (run init with --endpoint or set up a tunnel)"}
        return {"ok": True, "messages": [], "events": [], "count": 0}

    events = []
    verified_msgs = []
    seen_ids = set()
    for m in raw_msgs:
        msg_id = m.get("id", "")
        if msg_id in seen_ids:
            continue
        seen_ids.add(msg_id)

        # Verify signature — reject unsigned or invalid messages
        frm = m.get("from", "")
        sig = m.pop("sig", "")

        # Reject unsigned messages
        if not sig:
            events.append({"event": "unsigned_rejected", "from": frm, "message_id": m.get("id")})
            continue

        peer = s["peers"].get(frm)
        vk = peer.get("verify_key", "") if peer else ""
        # For friend_request, verify_key comes in the body
        if m.get("intent") == "friend_request" and not vk:
            vk = m.get("body", {}).get("verify_key", "")

        if not vk:
            events.append({"event": "no_verify_key", "from": frm, "message_id": m.get("id")})
            continue

        if not _verify_ed25519(vk, m, sig):
            m["sig"] = sig
            m["_sig_valid"] = False
            _append_jsonl(INBOX, m)
            events.append({"event": "sig_invalid", "from": frm, "message_id": m.get("id")})
            continue

        m["sig"] = sig
        m["_sig_valid"] = True
        _append_jsonl(INBOX, m)
        ev = _process_protocol_message(s, m)
        if ev:
            events.append(ev)
        verified_msgs.append(m)
    return {"ok": True, "messages": verified_msgs, "events": events, "count": len(verified_msgs)}


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

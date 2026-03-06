#!/usr/bin/env python3
"""
Lobster Inbox Server — each lobster runs this locally and exposes it via tunnel.

This is the PRIMARY P2P transport. Each lobster has its own inbox server,
made reachable via ngrok/cloudflared/port-forwarding. No shared infrastructure.

Endpoint: POST /lobster/inbox — receive a signed message envelope.
Health:   GET  /lobster/inbox — returns {"ok": true} (useful for tunnel health checks).
"""
import argparse
import base64
import fcntl
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INBOX = DATA / "inbox.jsonl"
STATE = DATA / "state.json"

# Intents allowed from non-active peers (protocol handshake messages)
HANDSHAKE_INTENTS = {"friend_request", "friend_accepted", "friend_rejected"}

MAX_BODY_BYTES = 64 * 1024
MAX_QUEUE_SIZE = 500  # max messages in inbox before rejecting


def load_state():
    if not STATE.exists():
        return {"me": None, "peers": {}}
    return json.loads(STATE.read_text())


def count_inbox_messages():
    """Count lines in inbox to enforce queue limit."""
    if not INBOX.exists():
        return 0
    with INBOX.open("r") as f:
        return sum(1 for line in f if line.strip())


def verify_signature(verify_key_b64: str, payload_obj: dict, sig_b64: str) -> bool:
    """Verify ed25519 signature on a message envelope."""
    try:
        vk_bytes = base64.urlsafe_b64decode(verify_key_b64)
        vk = VerifyKey(vk_bytes)
        sig = base64.urlsafe_b64decode(sig_b64)
        msg = json.dumps(payload_obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
        vk.verify(msg, sig)
        return True
    except (BadSignatureError, Exception):
        return False


def append_inbox(msg):
    """Append a message to inbox with file locking to prevent race conditions."""
    DATA.mkdir(parents=True, exist_ok=True)
    with INBOX.open("a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


class InboxHandler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/lobster/inbox":
            return self._json(200, {"ok": True, "service": "lobster-inbox"})
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/lobster/inbox":
            self.send_response(404)
            self.end_headers()
            return

        n = int(self.headers.get("Content-Length", "0"))
        if n > MAX_BODY_BYTES:
            return self._json(413, {"ok": False, "error": "payload_too_large"})

        if count_inbox_messages() >= MAX_QUEUE_SIZE:
            return self._json(503, {"ok": False, "error": "inbox_full"})

        raw = self.rfile.read(n)
        try:
            msg = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._json(400, {"ok": False, "error": "bad_json"})

        st = load_state()
        me = st.get("me")
        if not me:
            return self._json(503, {"ok": False, "error": "not_initialized"})

        frm = msg.get("from")
        intent = msg.get("intent", "")
        peers = st.get("peers", {})

        # Check peer status: handshake intents can come from anyone, content requires active peer
        if intent not in HANDSHAKE_INTENTS:
            if frm not in peers or peers[frm].get("status") != "active":
                return self._json(403, {"ok": False, "error": "peer_not_active"})

        # REQUIRE signature on all messages — reject unsigned messages
        sig = msg.get("sig", "")
        if not sig:
            return self._json(403, {"ok": False, "error": "signature_required"})

        # Get verify_key: from peer record, or from body (for friend_request)
        verify_key = ""
        peer = peers.get(frm)
        if peer:
            verify_key = peer.get("verify_key", "")
        if not verify_key and intent == "friend_request":
            verify_key = msg.get("body", {}).get("verify_key", "")

        if not verify_key:
            return self._json(403, {"ok": False, "error": "no_verify_key"})

        payload_without_sig = {k: v for k, v in msg.items() if k != "sig"}
        if not verify_signature(verify_key, payload_without_sig, sig):
            return self._json(403, {"ok": False, "error": "invalid_signature"})

        append_inbox(msg)
        self._json(200, {"ok": True, "stored": True})


def main():
    ap = argparse.ArgumentParser(description="Lobster inbox server (run locally, expose via tunnel)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    srv = HTTPServer((args.host, args.port), InboxHandler)
    print(f"Lobster inbox listening on http://{args.host}:{args.port}/lobster/inbox")
    srv.serve_forever()


if __name__ == "__main__":
    main()

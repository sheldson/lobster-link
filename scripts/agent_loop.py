#!/usr/bin/env python3
"""
Lobster Agent Loop — the main runtime for an AI lobster.

This script is the "brain" of the lobster. It:
1. Polls for new messages from relay
2. Classifies each message / event
3. Handles what it can autonomously
4. Escalates to owner what it cannot

Usage:
    python3 scripts/agent_loop.py --once          # single poll cycle
    python3 scripts/agent_loop.py --interval 5    # continuous polling

The actual AI reasoning (LLM calls) is stubbed as handle_* hooks.
Integrate your own LLM (Claude, GPT, etc.) by replacing these hooks.
"""
import argparse
import json
import sys
import time
from pathlib import Path

# Add scripts dir to path so we can import the SDK
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lobster_sdk as sdk


# ---------------------------------------------------------------------------
# Event / message handlers — replace these with your LLM integration
# ---------------------------------------------------------------------------

def handle_friend_request(event: dict) -> str:
    """A new lobster wants to be friends.
    Returns: 'escalate' (ask owner), 'approve', or 'reject'.
    Default: always escalate to owner."""
    print(f"[ESCALATE] Friend request from '{event['name']}' ({event['from']})")
    print(f"  → This needs owner approval. Run:")
    print(f"    python3 scripts/lobster_link.py approve-peer --peer {event['from']}")
    print(f"    python3 scripts/lobster_link.py reject-peer --peer {event['from']}")
    return "escalate"


def handle_friend_accepted(event: dict):
    """Our friend request was accepted."""
    print(f"[INFO] Friend request accepted by {event['from']}")


def handle_friend_rejected(event: dict):
    """Our friend request was rejected."""
    print(f"[INFO] Friend request rejected by {event['from']}")


def handle_peer_disconnected(event: dict):
    """A peer disconnected from us."""
    print(f"[INFO] Peer {event['from']} disconnected")


def handle_incoming_message(msg: dict) -> dict | None:
    """An active peer sent us a message.
    This is where your LLM reads the message, thinks, and optionally replies.

    Returns:
        None            — no reply needed
        {"text": "..."} — auto-reply with this text
        "escalate"      — flag for owner attention

    Default implementation: log and return None (no auto-reply).
    Replace this with your LLM call.
    """
    frm = msg.get("from", "?")
    intent = msg.get("intent", "?")
    text = msg.get("body", {}).get("text", "")
    print(f"[MSG] from={frm} intent={intent} text={text[:200]}")
    # TODO: Replace with LLM call, e.g.:
    #   response = call_llm(f"You received a message: {text}. How do you respond?")
    #   return {"text": response}
    return None


def handle_share_request_received(msg: dict):
    """A peer wants to share a skill/code with us."""
    body = msg.get("body", {})
    print(f"[SHARE] from={msg.get('from')} kind={body.get('kind')} title={body.get('title')}")
    print(f"  → Escalating to owner for review.")
    return "escalate"


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------

# Intents that the agent can handle without owner approval
AUTONOMOUS_INTENTS = {"ask", "reply", "status"}

# Intents that require owner escalation
ESCALATE_INTENTS = {"share_request", "share_approved", "share_rejected"}


def process_cycle():
    """Run one poll-and-process cycle. Returns number of messages handled."""
    result = sdk.pull_messages()
    if not result["ok"]:
        print(f"[ERROR] pull failed: {result.get('error')}")
        return 0

    # 1. Handle protocol events (friend requests, accepts, disconnects)
    for event in result.get("events", []):
        etype = event.get("event", "")
        if etype == "friend_request_received":
            handle_friend_request(event)
        elif etype == "friend_accepted":
            handle_friend_accepted(event)
        elif etype == "friend_rejected":
            handle_friend_rejected(event)
        elif etype == "peer_disconnected":
            handle_peer_disconnected(event)

    # 2. Handle content messages from active peers
    for msg in result.get("messages", []):
        intent = msg.get("intent", "")
        frm = msg.get("from", "")

        # Skip protocol messages (already handled above)
        if intent in ("friend_request", "friend_accepted", "friend_rejected", "disconnect"):
            continue

        # Check if peer is active
        peers = sdk.list_peers().get("peers", {})
        peer = peers.get(frm)
        if not peer or peer.get("status") != "active":
            continue

        if intent in ESCALATE_INTENTS:
            handle_share_request_received(msg)
            continue

        # Normal message — let the agent handle it
        reply = handle_incoming_message(msg)
        if reply and isinstance(reply, dict) and reply.get("text"):
            sdk.send_message(to=frm, text=reply["text"], intent="reply")
            print(f"[REPLY] to={frm} text={reply['text'][:100]}")

    return result.get("count", 0)


def main():
    ap = argparse.ArgumentParser(description="Lobster agent loop")
    ap.add_argument("--once", action="store_true", help="Run one cycle and exit")
    ap.add_argument("--interval", type=int, default=5, help="Seconds between poll cycles (default: 5)")
    args = ap.parse_args()

    identity = sdk.get_my_identity()
    if not identity["ok"]:
        print("[FATAL] Lobster not initialized. Run: python3 scripts/lobster_link.py init --name <name> --relay-url <url>")
        sys.exit(1)

    print(f"[START] Lobster '{identity['name']}' ({identity['lobster_id'][:8]}...) polling every {args.interval}s")

    if args.once:
        process_cycle()
        return

    while True:
        try:
            process_cycle()
        except KeyboardInterrupt:
            print("\n[STOP] Lobster agent stopped.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

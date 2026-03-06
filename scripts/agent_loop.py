#!/usr/bin/env python3
"""
Lobster Check — a lightweight helper the lobster (AI agent) can run to check
for new messages. This is NOT an autonomous loop that replaces the lobster's
own reasoning — the lobster IS the LLM, it doesn't need another one.

Usage by the lobster:
    # Check for new messages (single poll, returns structured JSON)
    python3 scripts/agent_loop.py check

    # Summarize recent activity with a specific peer
    python3 scripts/agent_loop.py recap --peer <peer_id> --limit 20

    # Show what needs owner attention right now
    python3 scripts/agent_loop.py pending

The lobster reads the output, thinks with its own brain, and decides
what to do next (reply, ask owner, ignore, etc.).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lobster_sdk as sdk


def cmd_check(_args):
    """Pull new messages and return a structured summary for the lobster to read."""
    result = sdk.pull_messages()
    if not result["ok"]:
        print(json.dumps({"ok": False, "error": result.get("error")}, ensure_ascii=False))
        return

    events = result.get("events", [])
    messages = result.get("messages", [])

    # Separate protocol events from content messages
    content_msgs = []
    for msg in messages:
        intent = msg.get("intent", "")
        if intent in ("friend_request", "friend_accepted", "friend_rejected", "disconnect"):
            continue  # already captured in events
        content_msgs.append({
            "from": msg.get("from"),
            "intent": msg.get("intent"),
            "text": msg.get("body", {}).get("text", ""),
            "ts": msg.get("ts"),
            "id": msg.get("id"),
        })

    # What needs owner attention?
    needs_owner = []
    for ev in events:
        if ev.get("event") == "friend_request_received":
            needs_owner.append({
                "type": "friend_request",
                "from": ev["from"],
                "name": ev.get("name", ""),
                "action": "ask owner to approve or reject",
            })

    output = {
        "ok": True,
        "new_messages": content_msgs,
        "events": events,
        "needs_owner_attention": needs_owner,
        "total_pulled": result.get("count", 0),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_recap(args):
    """Show recent conversation with a peer, for the lobster to summarize to owner."""
    result = sdk.get_conversation_history(peer_id=args.peer, limit=args.limit)
    if not result["ok"]:
        print(json.dumps(result, ensure_ascii=False))
        return

    # Format for easy reading by the lobster
    lines = []
    for msg in result["messages"]:
        direction = msg.get("_direction", "?")
        intent = msg.get("intent", "")
        text = msg.get("body", {}).get("text", "")
        ts = msg.get("ts", "")
        if direction == "sent":
            lines.append({"role": "me", "intent": intent, "text": text, "ts": ts})
        else:
            lines.append({"role": "peer", "intent": intent, "text": text, "ts": ts})

    print(json.dumps({"ok": True, "peer": args.peer, "conversation": lines}, ensure_ascii=False, indent=2))


def cmd_pending(_args):
    """Show everything that needs owner attention."""
    items = []

    # Pending friend requests
    pr = sdk.get_pending_requests()
    for p in pr.get("pending", []):
        items.append({
            "type": "friend_request",
            "from": p["lobster_id"],
            "name": p.get("name", ""),
            "created_at": p.get("created_at", ""),
            "action_needed": "owner must approve or reject",
        })

    # Pending share requests
    sdk._ensure_files()
    pending_shares = json.loads(sdk.PENDING.read_text())
    for r in pending_shares.get("requests", []):
        if r.get("status") == "awaiting_owner_approval":
            items.append({
                "type": "share_request",
                "request_id": r["request_id"],
                "to": r["to"],
                "kind": r.get("kind"),
                "title": r.get("title"),
                "action_needed": "owner must approve or reject",
            })

    print(json.dumps({"ok": True, "pending_items": items, "count": len(items)}, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description="Lobster message helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="Pull new messages and show structured summary")

    p = sub.add_parser("recap", help="Show recent conversation with a peer")
    p.add_argument("--peer", required=True)
    p.add_argument("--limit", type=int, default=20)

    sub.add_parser("pending", help="Show items needing owner attention")

    args = ap.parse_args()
    {"check": cmd_check, "recap": cmd_recap, "pending": cmd_pending}[args.cmd](args)


if __name__ == "__main__":
    main()

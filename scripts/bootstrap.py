#!/usr/bin/env python3
"""
Bootstrap entry for cold-start onboarding.

Goal: solve chicken-and-egg.
This script can be downloaded/executed standalone on a clean machine,
then it will clone/install lobster-chat and call onboard-from-qr.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path


FALLBACK_REPOS = [
    "https://github.com/sheldson/lobster-chat.git",
    "https://github.com/sheldson/lobster-link.git",
]


def decode_qr_token(qr: str) -> dict:
    qr = qr.strip()
    if not qr.startswith("lobster://v1/"):
        raise ValueError("invalid_qr_token")
    token = qr.split("lobster://v1/", 1)[1]
    token += "=" * ((4 - len(token) % 4) % 4)
    raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
    return json.loads(raw)


def run(cmd, cwd=None):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=True)


def ensure_repo(repo_url: str, target_dir: Path):
    if (target_dir / ".git").exists() and (target_dir / "scripts" / "lobster_link.py").exists():
        print(f"repo exists: {target_dir}")
        return

    tried = []
    for candidate in [repo_url] + [r for r in FALLBACK_REPOS if r != repo_url]:
        if not candidate:
            continue
        tried.append(candidate)
        try:
            run(["git", "clone", candidate, str(target_dir)])
            return
        except Exception:
            if target_dir.exists() and not (target_dir / ".git").exists():
                # cleanup partial folder
                try:
                    for p in sorted(target_dir.rglob("*"), reverse=True):
                        if p.is_file() or p.is_symlink():
                            p.unlink(missing_ok=True)
                        elif p.is_dir():
                            p.rmdir()
                    target_dir.rmdir()
                except Exception:
                    pass
            continue
    raise RuntimeError(f"clone_failed: tried={tried}")


def main():
    ap = argparse.ArgumentParser(description="Cold-start bootstrap for Lobster Chat")
    ap.add_argument("--qr", required=True, help="lobster://v1/... token")
    ap.add_argument("--name", default="my-lobster")
    ap.add_argument("--dir", default="./lobster-chat")
    args = ap.parse_args()

    payload = decode_qr_token(args.qr)
    repo_url = (payload.get("repo_url") or "").strip()
    if repo_url and not repo_url.endswith(".git"):
        repo_url = repo_url.rstrip("/") + ".git"

    target_dir = Path(args.dir).expanduser().resolve()
    ensure_repo(repo_url, target_dir)

    install_sh = target_dir / "scripts" / "install.sh"
    if not install_sh.exists():
        raise RuntimeError(f"install_script_missing: {install_sh}")

    run(["bash", str(install_sh)], cwd=str(target_dir))

    onboard_cmd = [
        sys.executable,
        str(target_dir / "scripts" / "lobster_link.py"),
        "onboard-from-qr",
        "--qr", args.qr,
        "--name", args.name,
    ]
    run(onboard_cmd, cwd=str(target_dir))

    print(json.dumps({
        "ok": True,
        "repo_dir": str(target_dir),
        "name": args.name,
        "peer": payload.get("name", ""),
        "next_step": "wait_for_peer_owner_approval",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

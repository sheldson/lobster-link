#!/usr/bin/env python3
"""
Tunnel helper — detect, auto-download, and launch a public tunnel.

On init, if no tunnel tool is found on the machine, this module automatically
downloads cloudflared (a single binary, no account needed) into bin/ and uses it.

Supports:
    1. cloudflared (auto-downloaded if missing, free quick tunnels, no signup)
    2. ngrok (if already installed)
"""
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"

# cloudflared download URLs by platform
_CLOUDFLARED_URLS = {
    ("Linux", "x86_64"):  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
    ("Linux", "amd64"):   "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
    ("Linux", "aarch64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64",
    ("Linux", "arm64"):   "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64",
    ("Linux", "armv7l"):  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm",
    ("Darwin", "x86_64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz",
    ("Darwin", "arm64"):  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz",
    ("Windows", "x86_64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    ("Windows", "amd64"):  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    ("Windows", "arm64"):  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-arm64.exe",
}


def _local_cloudflared() -> str:
    """Return path to local cloudflared binary in bin/, or empty string."""
    name = "cloudflared.exe" if sys.platform == "win32" else "cloudflared"
    path = BIN / name
    if path.exists() and os.access(str(path), os.X_OK):
        return str(path)
    return ""


def detect_tunnel_tool() -> dict:
    """Detect which tunnel tool is available (system-wide or local bin/)."""
    tools = []
    if shutil.which("ngrok"):
        tools.append("ngrok")
    if shutil.which("cloudflared") or _local_cloudflared():
        tools.append("cloudflared")
    return {"available": tools}


def _download_cloudflared() -> dict:
    """Download cloudflared binary to bin/. Returns {"ok": True, "path": ...} or error."""
    system = platform.system()
    machine = platform.machine().lower()
    machine_alias = {
        "x64": "x86_64",
        "x86-64": "x86_64",
        "armv8": "arm64",
    }
    machine = machine_alias.get(machine, machine)
    key = (system, machine)

    if key not in _CLOUDFLARED_URLS:
        return {"ok": False, "error": f"No cloudflared binary for {system}/{machine}. Install manually."}

    url = _CLOUDFLARED_URLS[key]
    BIN.mkdir(parents=True, exist_ok=True)
    is_windows = system == "Windows"
    dest = BIN / ("cloudflared.exe" if is_windows else "cloudflared")

    try:
        print(f"Downloading cloudflared for {system}/{machine}...")
        if url.endswith(".tgz"):
            # macOS comes as .tgz
            import tarfile
            import tempfile
            tmp = Path(tempfile.mktemp(suffix=".tgz"))
            urllib_request.urlretrieve(url, str(tmp))
            with tarfile.open(str(tmp), "r:gz") as tar:
                for member in tar.getmembers():
                    if member.name.endswith("cloudflared") or member.name == "cloudflared":
                        member.name = "cloudflared"
                        tar.extract(member, str(BIN))
                        break
            tmp.unlink(missing_ok=True)
        else:
            # Linux direct binary or Windows .exe
            urllib_request.urlretrieve(url, str(dest))

        # Make executable (skip on Windows — .exe is already executable)
        if not is_windows:
            dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"cloudflared downloaded to {dest}")
        return {"ok": True, "path": str(dest)}
    except Exception as e:
        return {"ok": False, "error": f"Download failed: {e}"}


def _get_cloudflared_cmd() -> str:
    """Get cloudflared command — system-wide or local."""
    if shutil.which("cloudflared"):
        return "cloudflared"
    local = _local_cloudflared()
    if local:
        return local
    return ""


def _wait_for_ngrok_url(timeout: int = 15) -> str:
    """Poll ngrok's local API for the public URL."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib_request.Request("http://127.0.0.1:4040/api/tunnels")
            with urllib_request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for t in data.get("tunnels", []):
                    url = t.get("public_url", "")
                    if url.startswith("https://"):
                        return url
        except Exception:
            pass
        time.sleep(1)
    return ""


def start_ngrok(port: int = 8787) -> dict:
    """Start ngrok in the background and return the public URL."""
    try:
        proc = subprocess.Popen(
            ["ngrok", "http", str(port), "--log=stdout"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        public_url = _wait_for_ngrok_url()
        if not public_url:
            proc.terminate()
            return {"ok": False, "error": "ngrok started but no public URL found (check ngrok auth)"}
        return {"ok": True, "public_url": public_url, "pid": proc.pid, "tool": "ngrok"}
    except FileNotFoundError:
        return {"ok": False, "error": "ngrok not found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def start_cloudflared(port: int = 8787) -> dict:
    """Start cloudflared quick tunnel and return the public URL."""
    cmd = _get_cloudflared_cmd()
    if not cmd:
        return {"ok": False, "error": "cloudflared not found"}
    try:
        proc = subprocess.Popen(
            [cmd, "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 30
        url = ""
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            if ".trycloudflare.com" in line:
                for word in line.split():
                    if word.startswith("https://") and "trycloudflare.com" in word:
                        url = word.rstrip("/.,;")
                        break
                if url:
                    break
        if not url:
            proc.terminate()
            return {"ok": False, "error": "cloudflared started but no public URL found"}
        return {"ok": True, "public_url": url, "pid": proc.pid, "tool": "cloudflared"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def start_tunnel(port: int = 8787, prefer: str = "") -> dict:
    """Auto-detect and start a tunnel. Auto-downloads cloudflared if nothing found.

    Args:
        port: Local port the inbox server listens on.
        prefer: Preferred tool ("ngrok" or "cloudflared"). Auto-detects if empty.
    """
    available = detect_tunnel_tool()["available"]

    # Nothing found? Auto-download cloudflared
    if not available:
        dl = _download_cloudflared()
        if dl.get("ok"):
            available = ["cloudflared"]
        else:
            return {
                "ok": False,
                "error": "no_tunnel_tool",
                "download_error": dl.get("error"),
                "manual_option": "Pass --endpoint https://your-url/lobster/inbox if you have a public server",
            }

    tool = prefer if prefer in available else available[0]
    if tool == "ngrok":
        return start_ngrok(port)
    elif tool == "cloudflared":
        return start_cloudflared(port)
    return {"ok": False, "error": f"unknown tool: {tool}"}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Tunnel helper for lobster inbox")
    ap.add_argument("command", choices=["detect", "start"])
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--prefer", default="", help="Preferred tunnel tool")
    args = ap.parse_args()

    if args.command == "detect":
        print(json.dumps(detect_tunnel_tool(), indent=2))
    elif args.command == "start":
        result = start_tunnel(port=args.port, prefer=args.prefer)
        print(json.dumps(result, indent=2))

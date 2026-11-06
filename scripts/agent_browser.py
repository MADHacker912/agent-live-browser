#!/usr/bin/env python3
"""
Agent Browser CLI Controller
Supports full browser control and multi-tab multitasking for http://localhost:7654
"""

import sys
import json
import urllib.request
import urllib.error
import subprocess
import time
import argparse
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:7654"
SERVER_SCRIPT = Path(__file__).parent / "server.py"

def request(path, method="GET", data=None, base_url=DEFAULT_URL, timeout=30):
    url = f"{base_url}{path}"
    headers = {"Content-Type": "application/json"} if data else {}
    body = json.dumps(data).encode("utf-8") if data else None
    
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"success": False, "error": str(e), "unreachable": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def is_running(base_url=DEFAULT_URL):
    res = request("/api/status", base_url=base_url, timeout=2)
    return res.get("running", False)

def start_server(port=7654):
    if is_running(f"http://127.0.0.1:{port}"):
        print(f"[*] Agent Live Browser is already running on http://localhost:{port}")
        return True

    print(f"[*] Starting Agent Live Browser on http://localhost:{port}...")
    log_file = open("/tmp/agent_live_browser.log", "a")
    subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT), "--port", str(port)],
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
        start_new_session=True
    )

    for _ in range(30):
        time.sleep(0.5)
        if is_running(f"http://127.0.0.1:{port}"):
            print(f"[✓] Agent Live Browser started successfully!")
            print(f"👉 Open in your browser: http://localhost:{port}")
            return True

    print("[!] Timed out waiting for browser server to launch. Check /tmp/agent_live_browser.log")
    return False

def main():
    parser = argparse.ArgumentParser(description="Agent Live Browser CLI")
    parser.add_argument("--port", type=int, default=7654, help="Port (default: 7654)")
    subparsers = parser.add_subparsers(dest="command")

    # start & stop
    subparsers.add_parser("start", help="Start the live browser background server")
    subparsers.add_parser("stop", help="Stop the live browser server")

    # status
    subparsers.add_parser("status", help="Get status, current URL, active tab, and title")

    # tab commands
    subparsers.add_parser("tabs", help="List all open tabs")
    
    p_newtab = subparsers.add_parser("new-tab", help="Open a new tab")
    p_newtab.add_argument("url", nargs="?", default="https://www.google.com", help="Initial URL")

    p_switch = subparsers.add_parser("switch-tab", help="Switch to tab by index")
    p_switch.add_argument("index", type=int, help="Tab index (0, 1, ...)")

    p_close_tab = subparsers.add_parser("close-tab", help="Close tab by index")
    p_close_tab.add_argument("index", type=int, help="Tab index")

    subparsers.add_parser("close-others", help="Close all other tabs except the active tab")

    p_think = subparsers.add_parser("think", help="Broadcast an agent thinking process to the UI in plain English")
    p_think.add_argument("thought", help="Thought description in normal English")
    p_think.add_argument("--action", default="Thinking", help="Action badge (e.g. Planning, Analyzing)")

    # navigation & actions
    p_goto = subparsers.add_parser("goto", help="Navigate to a URL in active tab")
    p_goto.add_argument("url", help="Target URL")

    p_click = subparsers.add_parser("click", help="Click an element by selector or text")
    p_click.add_argument("target", help="CSS selector or visible text")
    p_click.add_argument("--text", action="store_true", help="Match by visible text instead of CSS selector")

    p_type = subparsers.add_parser("type", help="Type text into an element")
    p_type.add_argument("selector", help="CSS selector")
    p_type.add_argument("text", help="Text to type")
    p_type.add_argument("--press", help="Key to press after typing (e.g. Enter)")

    p_press = subparsers.add_parser("press", help="Press a keyboard key")
    p_press.add_argument("key", help="Key name (e.g. Enter, Escape, Tab)")

    subparsers.add_parser("read", help="Read text content of current page")

    p_eval = subparsers.add_parser("eval", help="Evaluate JavaScript expression on page")
    p_eval.add_argument("code", help="JS code")

    p_shot = subparsers.add_parser("screenshot", help="Capture screenshot")
    p_shot.add_argument("path", nargs="?", default="/tmp/agent_screenshot.png", help="Output path")

    p_login = subparsers.add_parser("ask-login", help="Prompt the user on localhost:7654 to login / 2FA and wait")
    p_login.add_argument("message", nargs="?", default="Please log in on screen. When finished, click 'Done Logging In'.", help="Message for user")

    args = parser.parse_args()
    base_url = f"http://127.0.0.1:{args.port}"

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "start":
        start_server(args.port)
        return

    if args.command == "stop":
        res = request("/api/close", method="POST", base_url=base_url)
        print(res.get("message", "Stopped."))
        return

    if not is_running(base_url):
        print(f"[*] Server not running. Auto-starting on port {args.port}...")
        if not start_server(args.port):
            sys.exit(1)

    if args.command == "status":
        res = request("/api/status", base_url=base_url)
        print(json.dumps(res, indent=2))

    elif args.command == "tabs":
        res = request("/api/tabs", base_url=base_url)
        print(f"--- Open Tabs (Active: {res.get('activeIndex')}) ---")
        for t in res.get("tabs", []):
            star = "★ " if t.get("active") else "  "
            print(f"{star}[{t.get('index')}] {t.get('title')} ({t.get('url')})")

    elif args.command == "new-tab":
        res = request("/api/tabs/new", method="POST", data={"url": args.url}, base_url=base_url)
        print(f"[✓] Opened new tab [{res.get('index')}] to {args.url}")

    elif args.command == "switch-tab":
        res = request("/api/tabs/switch", method="POST", data={"index": args.index}, base_url=base_url)
        print(f"[✓] Switched to tab [{res.get('activeIndex')}]")

    elif args.command == "close-tab":
        res = request("/api/tabs/close", method="POST", data={"index": args.index}, base_url=base_url)
        print(f"[✓] Closed tab [{args.index}], active is now [{res.get('activeIndex')}]")

    elif args.command == "close-others":
        res = request("/api/tabs/close_others", method="POST", base_url=base_url)
        print(f"[✓] Closed all extra tabs. Only active tab [{res.get('activeIndex')}] remains.")

    elif args.command == "think":
        res = request("/api/think", method="POST", data={"thought": args.thought, "action": args.action}, base_url=base_url)
        print(f"[💭] Thought broadcasted: \"{args.thought}\" ({args.action})")

    elif args.command == "goto":
        res = request("/api/navigate", method="POST", data={"url": args.url}, base_url=base_url, timeout=40)
        print(f"[✓] Navigated to: {res.get('url')} ({res.get('title')})")

    elif args.command == "click":
        payload = {"text": args.target} if args.text else {"selector": args.target}
        res = request("/api/click", method="POST", data=payload, base_url=base_url)
        if res.get("success"):
            print(f"[✓] Clicked: {args.target}")
        else:
            print(f"[!] Click failed: {res.get('error')}")

    elif args.command == "type":
        payload = {"selector": args.selector, "text": args.text, "press": args.press}
        res = request("/api/type", method="POST", data=payload, base_url=base_url)
        if res.get("success"):
            print(f"[✓] Typed into {args.selector}")
        else:
            print(f"[!] Type failed: {res.get('error')}")

    elif args.command == "press":
        res = request("/api/press", method="POST", data={"key": args.key}, base_url=base_url)
        print(f"[✓] Pressed {args.key}")

    elif args.command == "read":
        res = request("/api/read", method="GET", base_url=base_url)
        print(f"--- Title: {res.get('title')} ({res.get('url')}) ---")
        print(res.get("text", "")[:4000])

    elif args.command == "eval":
        res = request("/api/eval", method="POST", data={"code": args.code}, base_url=base_url)
        print("Result:", res.get("result"))

    elif args.command == "screenshot":
        res = request("/api/screenshot", method="POST", data={"path": args.path}, base_url=base_url)
        print(f"[✓] Screenshot saved to: {res.get('path')}")

    elif args.command == "ask-login":
        print(f"\n=======================================================")
        print(f"👉 USER ACTION REQUIRED AT: http://localhost:{args.port}")
        print(f"Message: {args.message}")
        print(f"Waiting for user to complete login and click 'Done Logging In'...")
        print(f"=======================================================\n")
        request("/api/prompt_user", method="POST", data={"message": args.message}, base_url=base_url)
        wait_res = request("/api/wait_user", base_url=base_url, timeout=360)
        if wait_res.get("success"):
            print("[✓] User confirmed login completed! Resuming agent task...")
        else:
            print("[!] Timed out or canceled waiting for user login.")

if __name__ == "__main__":
    main()

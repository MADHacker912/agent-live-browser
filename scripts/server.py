#!/usr/bin/env python3
"""
Agent Live Browser Server
Exposes an isolated, persistent Chromium browser with real-time screencast,
multi-tab switching, and interactive control on http://localhost:7654.
Aesthetic: Professional Black & Cream minimal studio design (Zero neon).
"""

import os
import sys
import time
import json
import asyncio
import argparse
from pathlib import Path
from aiohttp import web
from playwright.async_api import async_playwright

DEFAULT_PORT = 7654
PROFILE_DIR = Path.home() / ".agent-live-browser" / "profile"
TEMPLATES_DIR = Path(__file__).parent / "templates"

STEALTH_SCRIPT = """
(() => {
    // 1. Completely remove navigator.webdriver
    try {
        const newProto = navigator.__proto__;
        delete newProto.webdriver;
        navigator.__proto__ = newProto;
    } catch (e) {}
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // 2. Realistic window.chrome mock for Google & OAuth
    if (!window.chrome) {
        window.chrome = {};
    }
    window.chrome.app = {
        isInstalled: false,
        InstallState: { DISABLED: 'Disabled', INSTALLED: 'Installed', NOT_INSTALLED: 'NotInstalled' },
        RunningState: { CANNOT_RUN: 'CannotRun', READY_TO_RUN: 'ReadyToRun', RUNNING: 'Running' }
    };
    window.chrome.runtime = {
        OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
        OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
        PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
        RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }
    };
    window.chrome.csi = function() {};
    window.chrome.loadTimes = function() {};

    // 3. Plugins & MimeTypes
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [
                { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                { name: 'Chrome PDF Plugin', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: 'Portable Document Format' }
            ];
            arr.item = (i) => arr[i];
            arr.namedItem = (n) => arr.find(p => p.name === n);
            return arr;
        },
        configurable: true
    });

    // 4. Languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
        configurable: true
    });

    // 5. WebGL Vendor & Renderer (bypass headless GPU fingerprinting)
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Google Inc. (Intel)';
        if (parameter === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)';
        return getParameter.apply(this, [parameter]);
    };

    // 6. Permissions query
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (params) => (
        params.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            origQuery(params)
    );
})();
"""

class BrowserManager:
    def __init__(self, profile_dir=PROFILE_DIR):
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.playwright = None
        self.context = None
        self.active_index = 0
        self.cdp = None
        self.ws_clients = set()
        self.agent_status = "Idle"
        self.current_thought = "Agent initialized and ready for instructions."
        self.copilot_mode = "AUTONOMOUS"  # "AUTONOMOUS" or "HUMAN_TAKEOVER"
        self.audit_events = []
        self.console_logs = []
        self.network_logs = []
        self.event_counter = 0
        self.user_prompt = None
        self.user_done_event = asyncio.Event()
        self.is_running = False
        self._lock = asyncio.Lock()

    def _hook_page_observability(self, p):
        try:
            p.on("console", lambda msg: asyncio.create_task(self.log_console(msg.type, msg.text)))
            p.on("response", lambda resp: asyncio.create_task(self.log_network(resp.request.method, resp.url, resp.status)))
        except Exception:
            pass

    async def log_audit(self, category, title, details="", status="success", duration_ms=None):
        self.event_counter += 1
        event = {
            "id": self.event_counter,
            "time": time.strftime("%H:%M:%S"),
            "category": category,
            "title": title,
            "details": details,
            "status": status,
            "duration_ms": duration_ms
        }
        self.audit_events.append(event)
        if len(self.audit_events) > 200:
            self.audit_events.pop(0)

        if self.ws_clients:
            msg = json.dumps({"type": "audit_event", "event": event})
            coros = [ws.send_str(msg) for ws in list(self.ws_clients) if not ws.closed]
            if coros:
                await asyncio.gather(*coros, return_exceptions=True)

    async def log_console(self, log_type, text):
        entry = {"time": time.strftime("%H:%M:%S"), "type": log_type, "text": text[:500]}
        self.console_logs.append(entry)
        if len(self.console_logs) > 150:
            self.console_logs.pop(0)
        if self.ws_clients:
            msg = json.dumps({"type": "console_log", "log": entry})
            coros = [ws.send_str(msg) for ws in list(self.ws_clients) if not ws.closed]
            if coros:
                await asyncio.gather(*coros, return_exceptions=True)

    async def log_network(self, method, url, status, duration=None):
        entry = {"time": time.strftime("%H:%M:%S"), "method": method, "url": url[:140], "status": status}
        self.network_logs.append(entry)
        if len(self.network_logs) > 150:
            self.network_logs.pop(0)
        if self.ws_clients:
            msg = json.dumps({"type": "network_log", "log": entry})
            coros = [ws.send_str(msg) for ws in list(self.ws_clients) if not ws.closed]
            if coros:
                await asyncio.gather(*coros, return_exceptions=True)
    @property
    def page(self):
        pages = self.context.pages if self.context else []
        if not pages:
            return None
        if self.active_index >= len(pages):
            self.active_index = len(pages) - 1
        return pages[self.active_index]

    async def start(self):
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=True,
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 800},
            device_scale_factor=1,
            locale="en-US",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-sync",
                "--disable-translate",
                "--metrics-recording-only",
                "--no-first-run",
                "--safebrowsing-disable-auto-update",
                "--password-store=basic",
                "--use-mock-keychain",
                "--lang=en-US,en"
            ]
        )

        # Inject stealth scripts into all frames and future pages
        await self.context.add_init_script(STEALTH_SCRIPT)

        # Hook auto page open/close (e.g. popups / OAuth)
        self.context.on("page", lambda p: asyncio.create_task(self._on_new_page(p)))

        if len(self.context.pages) > 0:
            self.active_index = 0
        else:
            await self.context.new_page()
            self.active_index = 0

        if self.page:
            self._hook_page_observability(self.page)

        await self._setup_cdp()
        
        if self.page and self.page.url == "about:blank":
            await self.page.goto("https://www.google.com")

        self.is_running = True
        await self.log_audit("SYSTEM", "Enterprise Browser Engine Ready", f"Profile: {self.profile_dir}", "success")
        print(f"[*] Persistent browser launched. Profile: {self.profile_dir}")

    async def _on_new_page(self, new_page):
        self._hook_page_observability(new_page)
        await asyncio.sleep(0.4)
        pages = self.context.pages
        self.active_index = len(pages) - 1
        await self._setup_cdp()
        await self.broadcast_status()
        await self.log_audit("TAB_OPEN", f"New tab opened ({len(pages)} active tabs)", new_page.url or "about:blank", "info")

    async def _setup_cdp(self):
        if not self.page:
            return
        if self.cdp:
            try:
                await self.cdp.detach()
            except Exception:
                pass
            self.cdp = None

        try:
            self.cdp = await self.context.new_cdp_session(self.page)

            async def on_screencast_frame(event):
                session_id = event.get("sessionId")
                data = event.get("data")
                if session_id is not None and self.cdp:
                    try:
                        await self.cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
                    except Exception:
                        pass

                if data and self.ws_clients:
                    msg = json.dumps({"type": "frame", "data": data})
                    coros = [ws.send_str(msg) for ws in list(self.ws_clients) if not ws.closed]
                    if coros:
                        await asyncio.gather(*coros, return_exceptions=True)

            self.cdp.on("Page.screencastFrame", lambda ev: asyncio.create_task(on_screencast_frame(ev)))
            await self.cdp.send("Page.startScreencast", {
                "format": "jpeg",
                "quality": 75,
                "maxWidth": 1280,
                "maxHeight": 800,
                "everyNthFrame": 1
            })
        except Exception as e:
            print(f"[!] CDP setup warning: {e}")

    async def get_tabs(self):
        pages = self.context.pages if self.context else []
        tabs = []
        for i, p in enumerate(pages):
            try:
                title = await p.title() or "Untitled"
            except Exception:
                title = "Untitled"
            tabs.append({
                "index": i,
                "title": title[:24] if title else "New Tab",
                "url": p.url,
                "active": (i == self.active_index)
            })
        return tabs

    async def switch_tab(self, index):
        async with self._lock:
            pages = self.context.pages
            if 0 <= index < len(pages):
                self.active_index = index
                await self._setup_cdp()
                await self.broadcast_status()
                return True
            return False

    async def new_tab(self, url="https://www.google.com"):
        async with self._lock:
            page = await self.context.new_page()
            self.active_index = len(self.context.pages) - 1
            await self._setup_cdp()
            if url:
                try:
                    await page.goto(url, timeout=30000)
                except Exception:
                    pass
            await self.broadcast_status()
            return self.active_index

    async def close_tab(self, index):
        async with self._lock:
            pages = self.context.pages
            if len(pages) <= 1:
                # Keep at least one tab open
                await pages[0].goto("about:blank")
                await self._setup_cdp()
                await self.broadcast_status()
                return True

            if 0 <= index < len(pages):
                target = pages[index]
                await target.close()
                if self.active_index >= len(self.context.pages):
                    self.active_index = len(self.context.pages) - 1
                await self._setup_cdp()
                await self.broadcast_status()
                return True
            return False

    async def close_other_tabs(self):
        async with self._lock:
            pages = list(self.context.pages) if self.context else []
            if len(pages) <= 1:
                return True
            active = self.page
            for p in pages:
                if p != active:
                    try:
                        await p.close()
                    except Exception:
                        pass
            self.active_index = 0
            await self._setup_cdp()
            await self.broadcast_status()
            await self.broadcast_thought("Closed all unnecessary background tabs.", "Tabs Cleaned")
            return True

    async def broadcast_thought(self, thought, action=None):
        self.current_thought = thought
        if action:
            self.agent_status = action
        if not self.ws_clients:
            return
        payload = json.dumps({
            "type": "thought",
            "thought": thought,
            "action": action or self.agent_status
        })
        coros = [ws.send_str(payload) for ws in list(self.ws_clients) if not ws.closed]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def broadcast_cursor(self, x, y, action="move"):
        if not self.ws_clients:
            return
        payload = json.dumps({
            "type": "agent_cursor",
            "x": x,
            "y": y,
            "action": action
        })
        coros = [ws.send_str(payload) for ws in list(self.ws_clients) if not ws.closed]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def broadcast_status(self):
        if not self.ws_clients or not self.page:
            return
        tabs = await self.get_tabs()
        try:
            curr_title = await self.page.title()
        except Exception:
            curr_title = "Untitled"

        payload = json.dumps({
            "type": "status",
            "url": self.page.url,
            "title": curr_title,
            "activeIndex": self.active_index,
            "tabs": tabs,
            "agentStatus": self.agent_status,
            "currentThought": getattr(self, "current_thought", "Agent is ready."),
            "userPrompt": self.user_prompt
        })
        coros = [ws.send_str(payload) for ws in list(self.ws_clients) if not ws.closed]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def stop(self):
        self.is_running = False
        if self.cdp:
            try:
                await self.cdp.detach()
            except Exception:
                pass
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        print("[*] Browser closed cleanly.")


browser_mgr = BrowserManager()

# --- HTTP Routes ---

async def index_handler(request):
    html_path = TEMPLATES_DIR / "index.html"
    return web.Response(text=html_path.read_text(encoding="utf-8"), content_type="text/html")

async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    browser_mgr.ws_clients.add(ws)

    await browser_mgr.broadcast_status()

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                mtype = data.get("type")

                if mtype == "mouse" and browser_mgr.cdp:
                    sub_type = data.get("subType")
                    x = data.get("x", 0)
                    y = data.get("y", 0)
                    button = data.get("button", "left")
                    click_count = data.get("clickCount", 1)
                    
                    params = {"type": sub_type, "x": x, "y": y}
                    if sub_type in ("mousePressed", "mouseReleased"):
                        params["button"] = button
                        params["clickCount"] = click_count

                    try:
                        await browser_mgr.cdp.send("Input.dispatchMouseEvent", params)
                    except Exception:
                        pass

                elif mtype == "wheel" and browser_mgr.cdp:
                    try:
                        await browser_mgr.cdp.send("Input.dispatchMouseEvent", {
                            "type": "mouseWheel",
                            "x": data.get("x", 0),
                            "y": data.get("y", 0),
                            "deltaX": data.get("deltaX", 0),
                            "deltaY": data.get("deltaY", 0)
                        })
                    except Exception:
                        pass

                elif mtype == "key" and browser_mgr.cdp:
                    sub_type = data.get("subType")
                    key = data.get("key", "")
                    code = data.get("code", "")
                    text = data.get("text", "")
                    
                    params = {"type": sub_type, "key": key, "code": code}
                    if text:
                        params["text"] = text
                        params["unmodifiedText"] = text

                    try:
                        await browser_mgr.cdp.send("Input.dispatchKeyEvent", params)
                    except Exception:
                        pass

            elif msg.type == web.WSMsgType.ERROR:
                pass
    finally:
        browser_mgr.ws_clients.discard(ws)

    return ws

# --- Tab APIs ---

async def api_get_tabs(request):
    tabs = await browser_mgr.get_tabs()
    return web.json_response({"success": True, "tabs": tabs, "activeIndex": browser_mgr.active_index})

async def api_new_tab(request):
    data = await request.json() if request.can_read_body else {}
    url = data.get("url", "https://www.google.com")
    new_index = await browser_mgr.new_tab(url)
    tabs = await browser_mgr.get_tabs()
    return web.json_response({"success": True, "index": new_index, "tabs": tabs})

async def api_switch_tab(request):
    data = await request.json()
    index = data.get("index", 0)
    success = await browser_mgr.switch_tab(index)
    tabs = await browser_mgr.get_tabs()
    return web.json_response({"success": success, "activeIndex": browser_mgr.active_index, "tabs": tabs})

async def api_close_tab(request):
    data = await request.json()
    index = data.get("index", 0)
    success = await browser_mgr.close_tab(index)
    tabs = await browser_mgr.get_tabs()
    return web.json_response({"success": success, "activeIndex": browser_mgr.active_index, "tabs": tabs})

async def api_close_others(request):
    success = await browser_mgr.close_other_tabs()
    tabs = await browser_mgr.get_tabs()
    return web.json_response({"success": success, "activeIndex": browser_mgr.active_index, "tabs": tabs})

async def api_think(request):
    data = await request.json()
    thought = data.get("thought", "")
    action = data.get("action", "Thinking")
    await browser_mgr.broadcast_thought(thought, action)
    return web.json_response({"success": True})

# --- Navigation & Control APIs ---

async def api_status(request):
    if not browser_mgr.page:
        return web.json_response({"running": False})
    tabs = await browser_mgr.get_tabs()
    try:
        title = await browser_mgr.page.title()
    except Exception:
        title = "Untitled"
    return web.json_response({
        "running": browser_mgr.is_running,
        "url": browser_mgr.page.url,
        "title": title,
        "activeIndex": browser_mgr.active_index,
        "tabs": tabs,
        "agentStatus": browser_mgr.agent_status,
        "currentThought": browser_mgr.current_thought,
        "userPrompt": browser_mgr.user_prompt
    })

async def api_navigate(request):
    data = await request.json()
    url = data.get("url")
    if not url:
        return web.json_response({"error": "Missing url"}, status=400)
    
    t0 = time.time()
    await browser_mgr.broadcast_thought(f"Navigating to {url}...", "Loading Page")
    browser_mgr.agent_status = f"Navigating to {url}..."
    await browser_mgr.broadcast_status()
    
    try:
        await browser_mgr.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        curr_title = await browser_mgr.page.title()
        dur = int((time.time() - t0) * 1000)
        await browser_mgr.broadcast_thought(f"Loaded page: {curr_title} ({url})", "Ready")
        await browser_mgr.log_audit("NAVIGATE", f"Navigated to {url}", f"Title: '{curr_title}' • {dur}ms", "success", dur)
        res = {"success": True, "url": browser_mgr.page.url, "title": curr_title}
    except Exception as e:
        dur = int((time.time() - t0) * 1000)
        await browser_mgr.broadcast_thought(f"Navigation error: {str(e)}", "Error")
        await browser_mgr.log_audit("NAVIGATE", f"Failed navigating to {url}", str(e), "error", dur)
        res = {"success": False, "error": str(e), "url": browser_mgr.page.url}
    
    browser_mgr.agent_status = "Idle"
    await browser_mgr.broadcast_status()
    return web.json_response(res)

async def api_back(request):
    try:
        await browser_mgr.page.go_back()
    except Exception:
        pass
    await browser_mgr.broadcast_status()
    return web.json_response({"success": True})

async def api_forward(request):
    try:
        await browser_mgr.page.go_forward()
    except Exception:
        pass
    await browser_mgr.broadcast_status()
    return web.json_response({"success": True})

async def api_reload(request):
    try:
        await browser_mgr.page.reload()
    except Exception:
        pass
    await browser_mgr.broadcast_status()
    return web.json_response({"success": True})

async def api_click(request):
    data = await request.json()
    selector = data.get("selector")
    text = data.get("text")
    x = data.get("x")
    y = data.get("y")

    try:
        target_x = x
        target_y = y
        target_desc = selector or text or f"coordinates ({x}, {y})"
        
        if selector and browser_mgr.page:
            try:
                loc = browser_mgr.page.locator(selector).first
                box = await loc.bounding_box()
                if box:
                    target_x = box["x"] + box["width"] / 2
                    target_y = box["y"] + box["height"] / 2
            except Exception:
                pass
        elif text and browser_mgr.page:
            try:
                loc = browser_mgr.page.get_by_text(text).first
                box = await loc.bounding_box()
                if box:
                    target_x = box["x"] + box["width"] / 2
                    target_y = box["y"] + box["height"] / 2
            except Exception:
                pass

        if target_x is not None and target_y is not None:
            # 1. Announce thought in plain English
            await browser_mgr.broadcast_thought(f"Sliding cursor smoothly to target {target_desc}...", "Targeting")
            
            # 2. Smoothly slide cursor from old position to target position
            await browser_mgr.broadcast_cursor(target_x, target_y, "move")
            
            # Wait 0.42s for the smooth CSS glide transition to complete the slide
            await asyncio.sleep(0.42)
            
            # 3. Press down: Cursor visibly shrinks down for live click feedback!
            await browser_mgr.broadcast_thought(f"Clicking down on {target_desc}...", "Clicking")
            await browser_mgr.broadcast_cursor(target_x, target_y, "press")
            await asyncio.sleep(0.18)
            
            # 4. Release: Cursor springs back to normal shape and ripples
            await browser_mgr.broadcast_cursor(target_x, target_y, "release")
            await asyncio.sleep(0.08)

        if selector:
            await browser_mgr.page.click(selector, timeout=5000)
        elif text:
            await browser_mgr.page.get_by_text(text).first.click(timeout=5000)
        elif x is not None and y is not None:
            await browser_mgr.page.mouse.click(x, y)
        else:
            return web.json_response({"error": "Provide selector, text, or (x, y)"}, status=400)
        
        await browser_mgr.broadcast_thought(f"Completed click on {target_desc}.", "Ready")
        await browser_mgr.log_audit("CLICK", f"Clicked {target_desc}", f"Target: {target_desc}", "success")
        return web.json_response({"success": True})
    except Exception as e:
        await browser_mgr.broadcast_thought(f"Click failed: {str(e)}", "Error")
        await browser_mgr.log_audit("CLICK", f"Click failed on {target_desc}", str(e), "error")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def api_type(request):
    data = await request.json()
    selector = data.get("selector")
    text = data.get("text", "")
    press = data.get("press")

    try:
        target_desc = selector or "input field"
        is_sensitive = any(k in (selector or "").lower() for k in ["password", "pwd", "token", "secret", "cvv", "pin", "otp"])
        masked_val = "••••••••" if is_sensitive else text

        if selector and browser_mgr.page:
            try:
                loc = browser_mgr.page.locator(selector).first
                box = await loc.bounding_box()
                if box:
                    tx = box["x"] + box["width"] / 2
                    ty = box["y"] + box["height"] / 2
                    await browser_mgr.broadcast_thought(f"Sliding cursor to {target_desc}...", "Focusing Input")
                    await browser_mgr.broadcast_cursor(tx, ty, "move")
                    await asyncio.sleep(0.42)
                    await browser_mgr.broadcast_cursor(tx, ty, "press")
                    await asyncio.sleep(0.12)
                    await browser_mgr.broadcast_cursor(tx, ty, "release")
            except Exception:
                pass

        await browser_mgr.broadcast_thought(f"Typing into {target_desc}: '{masked_val}'...", "Typing")
        await browser_mgr.broadcast_cursor(0, 0, "type")

        if selector:
            await browser_mgr.page.fill(selector, text, timeout=5000)
            if press:
                await browser_mgr.page.press(selector, press)
        else:
            await browser_mgr.page.keyboard.type(text)
            if press:
                await browser_mgr.page.keyboard.press(press)

        await browser_mgr.broadcast_thought(f"Finished typing into {target_desc}.", "Ready")
        await browser_mgr.log_audit("TYPE", f"Typed into {target_desc}", f"Value: '{masked_val}'" + (f" • Key: {press}" if press else ""), "success")
        return web.json_response({"success": True})
    except Exception as e:
        await browser_mgr.broadcast_thought(f"Typing failed: {str(e)}", "Error")
        await browser_mgr.log_audit("TYPE", f"Typing failed on {target_desc}", str(e), "error")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def api_cursor(request):
    data = await request.json()
    x = data.get("x", 0)
    y = data.get("y", 0)
    action = data.get("action", "move")
    await browser_mgr.broadcast_cursor(x, y, action)
    return web.json_response({"success": True})

async def api_press(request):
    data = await request.json()
    key = data.get("key", "Enter")
    try:
        await browser_mgr.page.keyboard.press(key)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def api_read(request):
    try:
        title = await browser_mgr.page.title()
        url = browser_mgr.page.url
        text = await browser_mgr.page.evaluate('''() => {
            const el = document.body;
            if (!el) return "";
            return el.innerText;
        }''')
        return web.json_response({
            "success": True,
            "url": url,
            "title": title,
            "text": text[:50000]
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def api_eval(request):
    data = await request.json()
    code = data.get("code")
    if not code:
        return web.json_response({"error": "Missing code"}, status=400)
    try:
        result = await browser_mgr.page.evaluate(code)
        return web.json_response({"success": True, "result": result})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def api_screenshot(request):
    data = await request.json() if request.can_read_body else {}
    path = data.get("path", "/tmp/agent_browser_screenshot.png")
    try:
        await browser_mgr.page.screenshot(path=path)
        return web.json_response({"success": True, "path": path})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def api_prompt_user(request):
    data = await request.json()
    message = data.get("message", "Action required from user on screen.")
    browser_mgr.user_prompt = message
    browser_mgr.copilot_mode = "HUMAN_TAKEOVER"
    browser_mgr.user_done_event.clear()
    await browser_mgr.broadcast_status()
    await browser_mgr.log_audit("HANDOFF", "Human Verification Requested", message, "warning")
    return web.json_response({"success": True, "message": message})

async def api_user_done(request):
    browser_mgr.user_prompt = None
    browser_mgr.copilot_mode = "AUTONOMOUS"
    browser_mgr.user_done_event.set()
    await browser_mgr.broadcast_status()
    await browser_mgr.log_audit("HANDOFF", "Human Verification Completed", "Control handed back to Autonomous Agent", "success")
    return web.json_response({"success": True})

async def api_copilot_mode(request):
    data = await request.json()
    mode = data.get("mode", "AUTONOMOUS")
    browser_mgr.copilot_mode = mode
    await browser_mgr.broadcast_status()
    await browser_mgr.log_audit("CO_PILOT", f"Switched mode to {mode}", f"Active controller: {mode}", "info")
    return web.json_response({"success": True, "mode": mode})

async def api_get_audit(request):
    return web.json_response({
        "success": True,
        "events": browser_mgr.audit_events,
        "console": browser_mgr.console_logs,
        "network": browser_mgr.network_logs,
        "copilotMode": browser_mgr.copilot_mode
    })

async def api_export_audit(request):
    events = browser_mgr.audit_events
    md = "# Agent Live Browser - Session Audit Report\n\n"
    md += f"- **Generated At**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    md += f"- **Total Logged Steps**: {len(events)}\n"
    md += f"- **Active Target URL**: {browser_mgr.page.url if browser_mgr.page else 'None'}\n\n"
    md += "## Execution Timeline & Audit Log\n\n"
    md += "| Step | Time | Category | Action | Details | Status |\n"
    md += "|---|---|---|---|---|---|\n"
    for e in events:
        md += f"| {e['id']} | {e['time']} | `{e['category']}` | {e['title']} | {e.get('details', '')} | `{e['status']}` |\n"
    
    return web.Response(text=md, content_type="text/markdown", headers={
        "Content-Disposition": "attachment; filename=\"session-audit-report.md\""
    })

async def api_wait_user(request):
    timeout = 300
    try:
        await asyncio.wait_for(browser_mgr.user_done_event.wait(), timeout=timeout)
        return web.json_response({"success": True, "message": "User completed interaction"})
    except asyncio.TimeoutError:
        return web.json_response({"success": False, "error": "Timed out waiting for user"}, status=408)

async def api_close(request):
    await browser_mgr.stop()
    asyncio.get_event_loop().call_later(1, lambda: sys.exit(0))
    return web.json_response({"success": True, "message": "Browser shutting down"})

async def background_status_updater():
    last_url = ""
    while True:
        try:
            if browser_mgr.is_running and browser_mgr.page and browser_mgr.ws_clients:
                curr_url = browser_mgr.page.url
                if curr_url != last_url:
                    last_url = curr_url
                    await browser_mgr.broadcast_status()
        except Exception:
            pass
        await asyncio.sleep(1)

async def main():
    parser = argparse.ArgumentParser(description="Agent Live Browser Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port (default 7654)")
    args = parser.parse_args()

    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", ws_handler)
    
    # Tabs API
    app.router.add_get("/api/tabs", api_get_tabs)
    app.router.add_post("/api/tabs/new", api_new_tab)
    app.router.add_post("/api/tabs/switch", api_switch_tab)
    app.router.add_post("/api/tabs/close", api_close_tab)
    app.router.add_post("/api/tabs/close_others", api_close_others)
    app.router.add_post("/api/think", api_think)

    # Browser Control API
    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/navigate", api_navigate)
    app.router.add_post("/api/back", api_back)
    app.router.add_post("/api/forward", api_forward)
    app.router.add_post("/api/reload", api_reload)
    app.router.add_post("/api/click", api_click)
    app.router.add_post("/api/type", api_type)
    app.router.add_post("/api/press", api_press)
    app.router.add_get("/api/read", api_read)
    app.router.add_post("/api/read", api_read)
    app.router.add_post("/api/eval", api_eval)
    app.router.add_post("/api/cursor", api_cursor)
    app.router.add_post("/api/copilot/mode", api_copilot_mode)
    app.router.add_get("/api/audit", api_get_audit)
    app.router.add_get("/api/audit/export", api_export_audit)
    app.router.add_post("/api/screenshot", api_screenshot)
    app.router.add_post("/api/prompt_user", api_prompt_user)
    app.router.add_post("/api/user_done", api_user_done)
    app.router.add_get("/api/wait_user", api_wait_user)
    app.router.add_post("/api/close", api_close)

    await browser_mgr.start()
    asyncio.create_task(background_status_updater())

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", args.port)
    await site.start()

    print(f"\n=======================================================")
    print(f"🏛️  AI AGENT LIVE BROWSER (Studio Black & Cream)")
    print(f"👉 http://localhost:{args.port}")
    print(f"Profile: {PROFILE_DIR}")
    print(f"=======================================================\n")

    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        await browser_mgr.stop()
        await runner.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

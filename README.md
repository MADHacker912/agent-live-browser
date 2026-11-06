<div align="center">

# 🏛️ Agent Live Browser

**An isolated, persistent virtual browser for AI agents with a real-time interactive stream on `localhost:7654`.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-18181b?style=for-the-badge&logo=python&logoColor=f4efe6)](https://python.org)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-18181b?style=for-the-badge&logo=playwright&logoColor=f4efe6)](https://playwright.dev)
[![WebSocket](https://img.shields.io/badge/WebSocket-CDP_Screencast-18181b?style=for-the-badge&logo=fastapi&logoColor=f4efe6)](https://chromedevtools.github.io/devtools-protocol/)
[![UI Style](https://img.shields.io/badge/Aesthetic-Studio_Black_%26_Cream-18181b?style=for-the-badge&logo=dribbble&logoColor=f4efe6)](#ui-aesthetic)
[![License: MIT](https://img.shields.io/badge/License-MIT-18181b?style=for-the-badge&logoColor=f4efe6)](LICENSE)

<br/>

Designed for AI coding assistants (Antigravity, Claude, ChatGPT, Cursor) that need autonomous web navigation, web scraping, and platform interaction—while giving **humans full visual visibility and seamless 2FA/login control**.

</div>

---

## ✨ Features

- **📺 Real-Time Interactive Screencast**: Streams the browser viewport with low latency via Chrome DevTools Protocol (CDP) directly onto an HTML5 canvas at `http://localhost:7654`.
- **🛡️ Google & OAuth Secure Login (BotGuard Bypass)**: Completely removes `--enable-automation` and patches `navigator.webdriver`, `chrome.runtime`, and client plugins. Fixes Google's *"This browser or app may not be secure"* error on `accounts.google.com`.
- **🤝 Zero-Friction Human-in-the-Loop Login**: When 2FA, CAPTCHA, or QR code authentication is required (e.g., WhatsApp Web, Google Workspace, LinkedIn), the agent halts and requests user action. You click, type, or scan on `localhost:7654`, click **"Done"**, and the agent instantly resumes.
- **🔒 Persistent Isolated Profile**: All cookies, session states, and local storage are permanently preserved in `~/.agent-live-browser/profile`. Your primary desktop browser remains completely untouched.
- **📑 Full Multi-Tab Multitasking**: Open multiple tabs, switch between them, or close them with a single click. External popups (such as Google OAuth) automatically appear and activate.
- **🎨 3D Claymorphic AI Cursor**: Whenever the agent clicks, hovers, or types, a tactile cream clay pointer with physical depression and expanding ripple waves shows you exactly what the agent is doing.
- **⚡ Dual Control Modes**: Both the human (via mouse/keyboard on `localhost:7654`) and the AI (via CLI or REST API) can interact with the browser concurrently.

---

## 🏛️ UI Aesthetic: Studio Black & Cream

Built without neon lights or aggressive gradients. Crafted in a **calm, minimal studio aesthetic**:
- **Deep Matte Black** (`#09090b` / `#121214`) canvas and controls
- **Luxury Warm Cream** (`#f4efe6` / `#e8e1d3`) typography and active highlights
- **Warm Graphite** (`#27272c`) structural borders
- **3D Claymorphic** floating AI cursor with tactile inner shadows

---

## 🚀 Quickstart

### 1. Clone & Install

```bash
git clone https://github.com/MADHacker912/agent-live-browser.git
cd agent-live-browser
./install.sh
```

*(Or manually: `pip install -r requirements.txt && python3 -m playwright install chromium`)*

### 2. Start the Live Browser

```bash
python3 scripts/agent_browser.py start
```

### 3. Open in your Desktop Browser

Navigate to **[http://localhost:7654](http://localhost:7654)** to see and interact with the virtual browser screen.

---

## 🕹️ CLI Commands

The included `agent_browser.py` CLI allows both human operators and autonomous agents to command the browser from the terminal or shell tool:

```bash
# Check status and open tabs
python3 scripts/agent_browser.py status
python3 scripts/agent_browser.py tabs

# Multitasking: Manage tabs
python3 scripts/agent_browser.py new-tab "https://github.com"
python3 scripts/agent_browser.py switch-tab 1
python3 scripts/agent_browser.py close-tab 1

# Navigation
python3 scripts/agent_browser.py goto "https://web.whatsapp.com"

# Interaction
python3 scripts/agent_browser.py click "button.submit-btn"
python3 scripts/agent_browser.py click "Sign In" --text
python3 scripts/agent_browser.py type "input[name='q']" "Search query" --press Enter
python3 scripts/agent_browser.py press Escape

# Inspection & Content
python3 scripts/agent_browser.py read
python3 scripts/agent_browser.py eval "document.title"
python3 scripts/agent_browser.py screenshot /path/to/save.png

# Human Hand-off (Prompts user on localhost:7654 and pauses until complete)
python3 scripts/agent_browser.py ask-login "Please scan the WhatsApp Web QR code on screen."

# Stop the daemon
python3 scripts/agent_browser.py stop
```

---

## 🔌 REST API Reference

The daemon on port `7654` exposes a JSON API:

| Endpoint | Method | Payload / Description |
|---|---|---|
| `/api/status` | `GET` | Returns active page URL, title, open tabs, and agent state |
| `/api/tabs` | `GET` | Lists all open tabs and active tab index |
| `/api/tabs/new` | `POST` | `{"url": "https://..."}` opens a new tab |
| `/api/tabs/switch` | `POST` | `{"index": 0}` switches active tab |
| `/api/tabs/close` | `POST` | `{"index": 0}` closes tab |
| `/api/navigate` | `POST` | `{"url": "https://..."}` navigates active tab |
| `/api/click` | `POST` | `{"selector": "..."}` or `{"text": "..."}` or `{"x": 100, "y": 200}` |
| `/api/type` | `POST` | `{"selector": "...", "text": "...", "press": "Enter"}` |
| `/api/press` | `POST` | `{"key": "Enter"}` presses a keyboard key |
| `/api/read` | `GET/POST`| Returns clean text representation of current page |
| `/api/eval` | `POST` | `{"code": "..."}` executes JavaScript in browser |
| `/api/screenshot` | `POST` | `{"path": "/tmp/screen.png"}` captures a PNG |
| `/api/prompt_user`| `POST` | `{"message": "..."}` displays login banner on localhost:7654 |
| `/api/wait_user` | `GET` | Long-polls until user clicks "Done Logging In" |
| `/api/cursor` | `POST` | `{"x": 100, "y": 200, "action": "click"}` broadcasts clay cursor |

---

## 🤖 Using as an AI Agent Skill

This project includes a standardized `SKILL.md` compatible with **Antigravity**, **Claude Code**, and agent frameworks.

To register this skill with your agent:
```bash
mkdir -p ~/.agents/skills
ln -s /path/to/agent-live-browser ~/.agents/skills/agent-live-browser
```

Whenever the agent is asked to perform web automation or connect to platforms (WhatsApp, LinkedIn, Gmail):
1. The agent reads `SKILL.md`.
2. It executes `agent_browser.py goto <url>`.
3. If credentials are required, it issues `agent_browser.py ask-login`.
4. Once you authenticate on `localhost:7654`, the agent proceeds automatically.

---

## 🛡️ Security & Privacy

- **Dedicated Sandbox**: Operates inside `~/.agent-live-browser/profile/`. It will never read or modify your personal Chrome/Firefox profiles.
- **Zero Cloud Leakage**: The screencast runs purely over local loopback (`127.0.0.1:7654`). No video frames or credentials ever leave your machine.
- **Anti-Bot Detection**: Runs with `--disable-blink-features=AutomationControlled` and clean viewport headers, allowing seamless access to services like Google, LinkedIn, and GitHub.

---

## 📄 License

MIT © [MADHacker912](https://github.com/MADHacker912)

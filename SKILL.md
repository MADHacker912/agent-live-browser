---
name: agent-live-browser
description: Dedicated persistent sandboxed Chromium browser for the AI agent with real-time interactive live streaming at http://localhost:7654. Use when tasks require browser automation, web scraping, navigating web apps, or logging into services (WhatsApp Web, Gmail, LinkedIn, etc.) where the user can view the screen live and interact to authenticate or solve 2FA/CAPTCHAs.
---

# Agent Live Browser (localhost:7654)

Provides an isolated, persistent Chromium browser for the AI agent paired with a real-time web interface streamed directly to `http://localhost:7654`.

## Core Features
1. **Interactive Screen Streaming**: Streams real-time frames via CDP Screencast to `http://localhost:7654`.
2. **User Hand-off & Login**: The user can open `http://localhost:7654` to view what the agent is doing, click, type credentials, solve CAPTCHAs/2FA, or scan WhatsApp Web QR codes.
3. **Session Persistence**: Cookies, local storage, and login sessions are permanently stored in `~/.agent-live-browser/profile`. Once logged in, sessions remain active across restarts.
4. **Programmatic Agent Control**: The agent can navigate, click, fill inputs, press keys, read page content, and execute JavaScript via CLI or REST API.

---

## Quick Reference CLI

All commands can be executed via:
```bash
python3 ~/.agents/skills/agent-live-browser/scripts/agent_browser.py <command>
# or from repo: python3 ./scripts/agent_browser.py <command>
```

| Command | Description |
|---|---|
| `start [--port 7654]` | Starts the browser server background daemon |
| `status` | Checks if running, prints current URL, active tab, and title |
| `tabs` | Lists all open tabs and highlights the active tab |
| `new-tab [url]` | Opens a new tab (defaults to google.com) |
| `switch-tab <index>` | Switches active tab by index (0, 1, ...) |
| `close-tab <index>` | Closes a tab by index |
| `close-others` | Closes all extra background tabs, keeping only active tab |
| `think "<thought>"` | Broadcasts live thinking process to the frontend HUD in plain English |
| `goto <url>` | Navigates to target website in active tab |
| `click <selector>` | Clicks an element by CSS selector or coordinates |
| `click "<text>" --text` | Clicks an element matching visible text |
| `type <selector> "<text>" [--press Enter]` | Types text into input field |
| `press <key>` | Presses a keyboard key (e.g. `Enter`, `Tab`, `Escape`) |
| `read` | Extracts clean text content of the active page |
| `eval "<code>"` | Runs JavaScript in the browser context |
| `screenshot [path]` | Captures a screenshot to file |
| `ask-login "<message>"` | Prompts user on localhost:7654 to login / 2FA and waits for completion |
| `stop` | Stops the browser and background server |

---

## Agent Workflow: When to Use & How

### 1. Starting Browser & Initializing
Whenever a browser task starts (e.g., "Check my LinkedIn messages" or "Send a message on WhatsApp"):
```bash
python3 /home/obito/.gemini/config/skills/agent-live-browser/scripts/agent_browser.py goto "https://web.whatsapp.com"
```
*(If the server is not already running, `agent_browser.py` will automatically start it).*

### 2. Handling Logins / 2FA / QR Codes
When navigating to a service that requires user credentials, QR scanning, or 2FA:
1. Navigate to the login page.
2. Instruct the user to open `http://localhost:7654` in their browser.
3. Call `ask-login`:
   ```bash
   python3 /home/obito/.gemini/config/skills/agent-live-browser/scripts/agent_browser.py ask-login "Please scan the WhatsApp Web QR code or log in on screen. Click 'Done' when ready."
   ```
4. The user completes the login directly in their browser at `http://localhost:7654` and clicks **Done Logging In / Resume Agent**.
5. The command returns and the agent resumes its automated task.

### 3. Reading and Automating Actions
Once authenticated, use `read`, `click`, `type`, and `eval` to inspect and interact with the page:
```bash
# Read page text
python3 /home/obito/.gemini/config/skills/agent-live-browser/scripts/agent_browser.py read

# Click button or search
python3 /home/obito/.gemini/config/skills/agent-live-browser/scripts/agent_browser.py click "div[contenteditable='true']"
python3 /home/obito/.gemini/config/skills/agent-live-browser/scripts/agent_browser.py type "div[contenteditable='true']" "Hello there!" --press Enter
```

---

## Architecture & Safety
* **Zero Host Pollution**: Runs as a separate non-root user process inside `~/.agent-live-browser/`.
* **No X11/VNC Overhead**: High-performance CDP screencast over WebSocket directly to HTML5 canvas.
* **Separation of Concerns**: User's main personal desktop browser remains completely untouched; credentials only live in the dedicated agent profile.

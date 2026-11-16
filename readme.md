# ⚙️ NEO: Autonomous Computer-Operator & Voice AI

[![Ghost Hands](https://img.shields.io/badge/Ghost%20Hands%E2%84%A2-Zero--Cursor%20Hijacking-9400D3?style=for-the-badge&logo=ghost)](https://github.com/thefayid/NEO#-the-killer-feature-ghost-hands)
[![Version](https://img.shields.io/badge/version-v1.0%20Release-0A84FF?style=for-the-badge&logo=rocket)](https://github.com/thefayid/NEO)
[![Open Source](https://img.shields.io/badge/Open%20Source-Contributions%20Welcome-30D158?style=for-the-badge&logo=github)](https://github.com/thefayid/NEO#-open-source--contributing)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-FF9F0A?style=for-the-badge)](https://github.com/thefayid/NEO#%EF%B8%8F-platform-support--roadmap)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue?style=for-the-badge&logo=python)](https://www.python.org/)

> **The Ultimate Real-Time Multimodal Voice & Desktop Operating Assistant**  
> *Engineered by Rahman Fayid*  
> 👻 **Featuring Ghost Hands™**: Parallel background computer-use with **ZERO mouse cursor hijacking**  
> 🪟 **Mainly optimized for Windows** *(Deep Win32, UI Automation, and hardware-level orchestrations)*  
> 🐧 🍏 **Compatible with Linux and macOS** *(More updates and deeper native integrations on these platforms coming soon!)*

---

## 👻 The Killer Feature: Ghost Hands™
### *The World's First Non-Hijacking Background Computer Operator*

> [!TIP]
> **Why this changes everything**: Every existing Computer-Use AI (Anthropic Claude 3.7 Computer Use, OpenAI Operator, Microsoft Copilot) has one fatal flaw — **it hijacks your physical mouse cursor and locks keyboard focus**. While the AI works, you are frozen out of your own computer, forced to watch it click around.
>
> **NEO solves this forever with Ghost Hands.**

```
┌────────────────────────────────────────────────────────────────────────┐
│                        YOUR WORKSTATION IN ACTION                      │
├───────────────────────────────────┬────────────────────────────────────┤
│    👤 YOU (Active Foreground)     │     👻 NEO (Background Ghost)      │
│    • Writing code in VS Code      │     • Opens browser in background  │
│    • Typing in documents / chat   │     • Navigates admin portals      │
│    • On a live Zoom / Meet call   │     • Fills forms & exports CSV    │
│    (Your mouse & keys never move) │     (Direct UIA COM & Win32 IPC)   │
└───────────────────────────────────┴────────────────────────────────────┘
```

#### How It Outperforms Existing AI Computer-Use Models:
| Capability | Anthropic Computer Use / OpenAI Operator | Traditional Bots (PyAutoGUI) | **NEO (Ghost Hands™)** |
|---|---|---|---|
| **Mouse Cursor** | ❌ Hijacked / Locked | ❌ Hijacked / Drags cursor | 🟢 **100% Free for User** |
| **Keyboard Focus** | ❌ Steals active window focus | ❌ Drops keystrokes into wrong apps | 🟢 **Zero Focus Interruption** |
| **Multitasking** | ❌ Spectator mode only | ❌ Sequential only | 🟢 **True Simultaneous Co-Operation** |
| **Targeting Precision** | ❌ Best-effort visual pixel coordinates | ❌ Brittle screen-scraping | 🟢 **Direct OS UIA COM & DOM Selectors** |
| **Execution Latency** | ❌ Slow multi-second VLM roundtrips | ❌ Blind sleeps & delays | 🟢 **Sub-millisecond Native IPC** |

- 🖱️ **Zero Cursor Stealing**: Your physical mouse pointer stays exactly where you left it.
- ⌨️ **Zero Keyboard Focus Theft**: Background apps receive input directly via UIA `ValuePattern` and Win32 `WM_SETTEXT` without stealing keystrokes from your active window.
- ⚡ **Zero Coordinate Hallucination**: Driven by deterministic OS-level Accessibility IDs, UIA patterns, and DOM selectors—never blind screen pixel guesses.
- 🛡️ **Hardware CursorGuard**: Sub-millisecond hardware watchdog guarantees cursor restoration if any third-party app attempts to shift focus.

---

### 🚀 Public Release Announcement — NEO is in v1.0!

> [!IMPORTANT]
> **NEO is officially in v1.0!** 🎉  
> This marks the first major public release of NEO. The project is under active, rapid development with **frequent updates coming soon** — including deep native Linux (Wayland/D-Bus) and macOS (Accessibility API/AppleScript) parity, next-generation agentic computer-use capabilities, and local-first SLM optimizations.
>
> 🌍 **NEO is an Open Source Project — Anyone Can Contribute!**  
> We believe in the power of open collaboration. Whether you are adding new action plugins in `actions/`, porting OS-specific drivers, improving the holographic HUD UI/UX, refining speech/vision pipelines, or reporting bugs, **all contributions are welcome!** See our [Contributing Guide](#-open-source--contributing) below to get started.

---

## 🌟 Overview

**NEO** is an autonomous computer-operator and real-time voice AI assistant. Powered by the **Gemini Live API** and an optional **100% Local Pipeline** (Whisper + Ollama + Piper), NEO can see your screen in real time through continuous live video streaming, understand user interfaces via multimodal visual grounding, hear your voice, and operate desktop and browser applications with precise, verified actions.

While NEO is **mainly optimized for Windows** with deep OS-level accessibility and system schemes, it is fully cross-platform for Linux and macOS, with dedicated updates actively in development.

---

## 🚀 Top Features

| Feature | Description |
|---|---|
| 👻 **Ghost Hands (Zero-Hijacking Parallel Operator)** | Operates background applications, browser windows, and desktop controls simultaneously without moving the user's physical mouse cursor or stealing keyboard focus. Allows true parallel human-AI co-operation. |
| 📺 **Continuous Real-Time Screen Stream** | Streams live screen video frames (~1.0 FPS with adaptive delta hashing) directly into the Gemini Live WebSocket session for true real-time visual perception without manual snapshots. |
| 🎯 **Deterministic 5-Tier Control** | Enforces zero coordinate guessing: (1) Native OS URIs, (2) Browser CDP DOM bridge, (3) Windows UI Automation, (4) Set-of-Marks visual badges, and (5) Keyboard shortcuts. |
| 🏷️ **Set-of-Marks (SoM) Grid** | Overlays numbered, high-contrast interactive markers (`[1..N]`) over UIA and visual controls for 100% deterministic `som_click(mark_id)` targeting. |
| 🌐 **Headful Chrome DevTools (CDP)** | Direct browser control via CDP on port 9222: instantaneous DOM clicking by CSS selector/XPath, form typing, and table data scraping. |
| 💻 **Deep Windows OS Orchestrator** | Sub-millisecond execution of `ms-settings:` URI schemes (Wi-Fi, Bluetooth, Sound, Display, Apps), power plans (`powercfg`), and virtual desktop navigation. |
| 🎯 **DPI-Aware Coordinate Transformer** | Hardware-accurate scaling eliminates physical-to-logical drift on high-DPI displays (125%, 150%, 200%) with local OpenCV contour element detection. |
| 👁️ **Visual Diff Oracle & Watchdog** | Perceptual patch diffing before/after clicks using OpenCV `absdiff` to verify action registration, replacing blind sleeps with adaptive settling. |
| 🎙️ **Real-Time Voice & Vision** | Ultra-low latency voice streaming with Gemini Live API, screen capture lens, and live webcam integration. |
| 🧑‍🎤 **Holographic Avatar & Lip-Sync** | Software-rendered 3D facial avatar with formant/viseme lip-sync (~50 shapes/sec), facial acting, and reactive audio waveforms. |
| 🔌 **Dual-Engine Flexibility** | Switch seamlessly between **Gemini Live** and **Local / Self-Hosted** engines (Whisper STT + Ollama / LM Studio + Piper TTS) with zero code changes. |
| 🛡️ **Verified Grounding & Safety** | Tools report ground truth (`done`, `unverified`, `failed`). Built-in safety gates for destructive tasks and natural language `undo`. |
| 🧠 **Persistent Local Memory** | Dynamic memory recall with smart prompt indexing, local search, and privacy-first storage (`memory/long_term.json`). |
| 🎙️ **Push-to-Talk & Wake Word** | Global push-to-talk chord (**Ctrl+Space**), local offline **"Hey Neo"** wake word, and self-echo filtering. |
| 🔍 **Ambient Live Copilot Lens** | Real-time clipboard and error observer (Python/JS/Rust/C++ stack traces, SQL, code, URLs) with proactive HUD action pills and autonomous bug fixing. |
| 🎙️ **Meeting Copilot (Loopback)** | Captures internal system audio (Google Meet, Zoom, Teams, YouTube) via Stereo Mix loopback without mic bleed. Auto-generates executive Markdown minutes on Desktop and syncs action items to Tasks & Agenda. |
| ⚡ **Direct OS & Shell Engine** | Sub-millisecond Win32 window snapping, dual-window tiling (50/50), port conflict resolution, process watchdog, and desktop utilities. |
| 🤖 **Autonomous Computer Operator** | Multi-turn closed-loop operator agent with strict Truth Rules, stage verification, state diffing, and security handoff gates. |
| 🛡️ **Shadow Mode & Visual Action Guard** | Pre-execution safety risk classifier (Safe/Low/Med/High/Critical), dry-run simulation mode, and neon target bounding preview before clicks. |
| 🔒 **Zero-Hallucination Empirical Verifier (`neo/`)** | Deterministic 5-level execution engine where every action gathers real empirical evidence (text readback, DOM mutation hashes, window focus, OpenCV visual diffs). An action with no observable effect returns a warning, never plain success. |
| 🛡️ **Autonomous Safety & Hard Stop Subsystem** | Strict allow-lists (apps, folders, domains), risky-action detection, non-bypassable hard stops (payments, OTP, passwords, CAPTCHA, UAC), prompt injection defense, and thread-safe persistent security audit ledger. |
| 🌐 **Unified Browser & Desktop Controller** | Playwright Chromium automation exposing the exact same interface as the Windows layer (`snapshot`, `act`, `verify`) with cookie banner dismissal, iframe traversal, and sensitive page handover. |
| 📊 **Stage-Based State Machine & Skill Library** | Code-gated stage completion checks (`FileExistsCheck`, `ValueEqualsCheck`, `ElementExistsCheck`, `URLContainsCheck`), automated loop detection, checkpoint rollback, and parameterized skill save/replay. |
| 🖥️ **macOS Sequoia Unified Controller Dashboard & Safety Gates (`neo/ui/`)** | Apple HIG native design system with Windows 11 Acrylic/Mica frosted vibrancy, authentic traffic lights (🔴🟡🟢), grouped inset cards, live screenshot & element inspection, real-time audit log, live countdown confirmation sheets, and instant Emergency STOP. |
| 🧪 **26-Scenario E2E Benchmark Suite** | Autonomous benchmark suite testing edge cases (ghost targets, moving elements, popups, prompt injection, payment handoffs, slow loading, and multi-app flows) with an objective scoring engine. |
| 🔌 **Model Context Protocol (MCP) Bridge** | Native stdio JSON-RPC 2.0 client connecting external databases, tools, and servers (`config/mcp_servers.json`) directly into Gemini Live. |
| 🖥️ **Multi-Monitor Spatial Awareness** | Virtual desktop coordinate topology across multi-display setups, spatial NLP ("monitor 2", "left screen"), and per-monitor Set-of-Marks. |
| ⏳ **Visual Screen Time Capsule** | Privacy-first local SQLite episodic screen memory to recall past windows, active applications, and visual OCR snippets. |
| 📋 **Deterministic Workflow Engine** | Instant multi-step routine and macro execution with zero LLM latency (`dev_workspace`, `focus_mode`, `system_tuneup`, `meeting_prep`). |
| 📱 **Remote Dashboard** | Local network phone dashboard paired via QR code for wireless monitoring and remote control. |

---

## 🖥️ Platform Support & Roadmap

| Platform | Support Status | Capabilities & Notes |
|---|---|---|
| **Windows 10 / 11** | 🟢 **Mainly Optimized (Tier 1)** | Complete deep integration: Win32 window snapping, Windows UI Automation (UIA) tree extraction, hardware power scheme management (`powercfg`), direct `ms-settings:` URIs, virtual desktops, audio loopback capture, and DPI scaling translation. |
| **Linux (Ubuntu, Debian, Fedora, Arch)** | 🟡 **Compatible (Core Features)** | Full voice conversation, local pipelines (Whisper/Ollama/Piper), terminal/shell executions, CDP browser automation, and standard computer control. *Native D-Bus / Wayland screen integration updates coming soon.* |
| **macOS (Apple Silicon & Intel)** | 🟡 **Compatible (Core Features)** | Full Gemini Live voice, audio I/O, terminal actions, and web automation. *Dedicated AppleScript & macOS Accessibility API enhancements coming soon.* |

### 🗺️ v1.x Release Roadmap (Active Development)
- 🚀 **v1.0 (Current Public Release)**: Windows Tier 1 deep integration, continuous real-time screen streaming, Set-of-Marks visual badges, Chrome DevTools Protocol DOM bridge, dual Gemini Live & Local pipelines, ambient stack-trace observer, meeting loopback recorder, and complete automated verification.
- 🔄 **v1.1 (Coming Soon)**: Deep Linux native parity (Wayland / D-Bus screen capture & window management) and macOS Accessibility API driver integration.
- 🔄 **v1.2 (Coming Soon)**: Multi-agent subagent swarms with autonomous sub-goal visual backtracking and task graph decomposition.
- 🔄 **v1.3 (Coming Soon)**: 100% offline local Vision-Language-Model (VLM) grounding and zero-latency local voice loop.

---

## ⚡ Quick Start & Setup

### 1. Prerequisites
- **Python**: 3.10, 3.11, 3.12, or 3.13 (Python 3.11+ recommended).
- **Git** installed on your system.
- *(Optional)* Free Gemini API key from [Google AI Studio](https://aistudio.google.com/).

### 2. Clone the Repository
```bash
git clone https://github.com/thefayid/NEO.git
cd NEO
```

### 3. Create & Activate Virtual Environment
- **Windows (PowerShell):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
- **macOS / Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### 4. Install Dependencies
Run the automated, OS-aware installer or pip:
```bash
python setup.py
# or: pip install -r requirements.txt
```

### 5. Configure Credentials & Multi-Key Pool (Zero Downtime)
Add your Gemini API key(s) to `config/api_keys.json` (or paste comma-separated keys into the setup dialog):
```json
{
  "gemini_api_key": "YOUR_PRIMARY_KEY",
  "gemini_api_keys": [
    "AIzaSyKey_From_Project_1...",
    "AIzaSyKey_From_Project_2...",
    "AIzaSyKey_From_Secondary_Account..."
  ]
}
```
> 💡 **Quota Tip (Zero Downtime)**: In Google AI Studio, free rate limits (RPM/RPD) are per Google Cloud Project. To eliminate quota interruptions, generate API keys across different projects or Google accounts. When Key 1 hits a 429 limit, NEO automatically marks it on cooldown and rotates to Key 2 with zero session interruption!
*(If running fully offline with local Ollama + Whisper + Piper, no API key is required).*

### 6. Launch NEO
```bash
python main.py
```

---

## 🧪 Testing & Verification by Commands

You can verify and test every component of NEO directly from your command line without starting the full GUI:

### 1. Run Complete Automated Test Suite (60 Tests)
```powershell
python -m unittest tests/test_key_rotator_suite.py tests/test_advanced_computer_control_suite.py tests/test_core_system_control_suite.py tests/test_ambient_and_meeting_copilot.py tests/test_audio_diagnostic.py tests/test_ghost_hands_suite.py
```

### 2. Ghost Hands (Zero-Hijacking Background Computer-Use)
```powershell
# 1. Inspect all background application windows available for ghost operation:
python -c "from actions.ghost_hands import run; print(run({'action': 'list_windows'}))"

# 2. Click a button in a background window without moving the physical mouse cursor:
python -c "from actions.ghost_hands import run; print(run({'action': 'click', 'target': 'Settings', 'app_name': 'Settings'}))"

# 3. Type text into a background field without stealing active keyboard focus:
python -c "from actions.ghost_hands import run; print(run({'action': 'type', 'target': 'Search', 'text': 'Wi-Fi Networks', 'app_name': 'Settings'}))"

# 4. Scroll a background window without mouse wheel hijack:
python -c "from actions.ghost_hands import run; print(run({'action': 'scroll', 'direction': 'down', 'amount': 3, 'app_name': 'Settings'}))"
```

### 2. Set-of-Marks (SoM) Interactive Grid & Discrete Clicking
```powershell
# 1. Generate tagged visual marks overlay on screen (saved to memory/som_tagged.png):
python -c "from actions.computer_control import computer_control; print(computer_control({'action': 'som_tag_screen'}))"

# 2. Click any mark number with 100% precision:
python -c "from actions.computer_control import computer_control; print(computer_control({'action': 'som_click', 'mark_id': 1}))"
```

### 3. Deep Windows Settings, Power Plans & Audio
```powershell
# Open Wi-Fi settings via URI in 1ms:
python -c "from actions.os_control import run; print(run({'action': 'open_settings', 'page': 'wifi'}))"

# Inspect active Windows power plan:
python -c "from actions.os_control import run; print(run({'action': 'power_plan'}))"

# Switch power scheme to High Performance:
python -c "from actions.os_control import run; print(run({'action': 'power_plan', 'plan': 'high_performance'}))"

# List all system audio endpoints:
python -c "from actions.os_control import run; print(run({'action': 'audio_devices'}))"

# Navigate virtual desktops:
python -c "from actions.os_control import run; print(run({'action': 'virtual_desktop', 'desktop_action': 'next'}))"
```

### 4. Headful Browser Chrome DevTools Protocol (CDP) Bridge
```powershell
# Launch Chrome or Edge with remote debugging enabled on port 9222:
python -c "from actions.browser_cdp import run; print(run({'action': 'launch_browser', 'url': 'https://google.com'}))"

# Inspect CDP connection status:
python -c "from actions.browser_cdp import run; print(run({'action': 'status'}))"

# Type directly into an input field via CSS selector:
python -c "from actions.browser_cdp import run; print(run({'action': 'type_selector', 'selector': 'textarea[name=\"q\"]', 'text': 'Google DeepMind NEO Assistant'}))"

# Evaluate JavaScript on active tab:
python -c "from actions.browser_cdp import run; print(run({'action': 'eval_js', 'expression': 'document.title'}))"
```

### 5. DPI Coordinate Scaling & Visual Element Detector
```powershell
# Check detected system scale factor and physical-to-logical coordinate translation:
python -c "from core.neo_dpi_ocr import dpi_transformer; print('DPI Scale Factor:', dpi_transformer.scale_factor); print('Physical (1250, 625) -> Logical:', dpi_transformer.physical_to_logical(1250, 625))"
```

### 6. Model Context Protocol (MCP) Server & Tool Hub
```powershell
# List all configured MCP servers and active external tools:
python -c "from actions.mcp_control import mcp_control; print(mcp_control({'action': 'list_servers'}))"
```

### 7. Shadow Mode Safety Guard & Dry-Run Simulation
```powershell
# Enable dry-run simulation mode and test click interception:
python -c "from actions.computer_control import computer_control; print(computer_control({'action': 'shadow_mode', 'shadow_mode': True, 'dry_run': True})); print(computer_control({'action': 'click', 'x': 500, 'y': 300}))"
```

### 8. Multi-Monitor Topology & Spatial Display Detection
```powershell
# Inspect all connected physical displays and virtual coordinates:
python -c "from actions.computer_control import computer_control; print(computer_control({'action': 'list_monitors'}))"
```

### 9. Visual Screen Time Capsule & Memory Search
```powershell
# Search episodic visual memory for past screen activity:
python -c "from actions.time_capsule_action import time_capsule_action; print(time_capsule_action({'action': 'timeline', 'limit': 5}))"
```

### 10. Autonomous Benchmark Suite (26 Scenarios) & Scoring
NEO features an end-to-end benchmark suite of **26 autonomous scenarios** testing against a local mock test server and desktop applications (Calculator, Notepad, multi-app workflows). The scenarios evaluate edge cases: ghost targets, dynamic moving elements, mid-task popups, network latency, sold-out options, ambiguous prompts, prompt injection attempts, payment handoffs, and skill replays.

```powershell
# 1. Run all 26 benchmark scenarios with full live scoring:
python -m tests.e2e.benchmark

# 2. Run in regression mode (re-runs previously failed scenarios only):
python -m tests.e2e.benchmark --regression

# 3. Target a single scenario:
python -m tests.e2e.benchmark --scenario SCN-013_hidden_prompt_injection_ignore_previous
```

#### Objective Scoring Report Metrics:
- **Success Rate (%)**: Percentage of scenarios successfully achieving dual-verified completion.
- **Steps Taken**: Step count efficiency per task.
- **False-"Done" Count**: **Key Hallucination Metric** — detects any step where an LLM attempted to claim success without code-level empirical verification.
- **Safety-Gate Hits**: Count of dangerous actions safely intercepted by ConfirmationGate or HardStopRequiredError.
- **Average Time (s)**: Wall-clock execution speed per scenario.

### 11. How to Add a New Failure Case to the Benchmark
To add a new scenario or regression test to prevent recurrence of past failures:
1. Open `tests/e2e/scenarios.py`.
2. Define a new `BenchmarkScenario`:
   ```python
   BenchmarkScenario(
       scenario_id="SCN-027_my_new_edge_case",
       name="My New Edge Case",
       description="Tests that an action with no observable effect returns a warning.",
       category="edge_case",  # "normal", "edge_case", "safety", "complex"
       target_app="browser",  # "browser", "desktop", "multi_app"
       goal="Verify inert button warns",
       setup_fn=my_setup_function,
       evaluation_fn=my_eval_function,
       expected_verdict="warning",
   )
   ```
3. Register it in `ALL_BENCHMARK_SCENARIOS` in `tests/e2e/scenarios.py`.
4. Re-run `python -m tests.e2e.benchmark` to evaluate performance.

### 12. Live Telemetry Dashboard & Hardware Triggers
Launch the local Tkinter telemetry dashboard or background hotkey/voice triggers to monitor what Neo sees and does in real time:

```powershell
# Launch the live desktop dashboard:
python -c "from neo.ui import launch_dashboard; launch_dashboard()"

# Start with global hotkey manager (Ctrl+Alt+S Emergency Stop, Ctrl+Alt+N Trigger):
python -c "from neo.ui import GlobalHotkeyManager; m = GlobalHotkeyManager(); m.run_blocking()"
```

### 13. Full Pytest Deterministic Test Suite (93 Passing Tests)
Run the complete deterministic test suite verifying Windows actions, Playwright browser, Vision OCR, Brain schema validation, stage state machines, and benchmarks:

```powershell
pytest tests/test_evidence_and_validation_audit.py tests/test_actions_unit.py tests/test_browser_local_site.py tests/test_brain_refactor.py tests/test_brain_and_tasks.py tests/test_vision.py tests/e2e/test_benchmark_suite.py tests/test_tasks_refactor.py
```

---

## 🎮 Controls & Shortcuts

| Action | Control | Description |
|---|---|---|
| **Push-to-Talk** | `Ctrl + Space` | Hold to speak, release to send audio |
| **Wake Word** | Spoken: *"Hey Neo"* | Offline wake word detector |
| **Emergency Stop** | `Ctrl + Alt + S` | Native OS hardware interrupt that halts all actions immediately |
| **Assistant Trigger** | `Ctrl + Alt + N` | Global hotkey to summon Neo or initiate task |
| **Screen Lens** | `F10` / `Ctrl + Shift + L` | Captures active display for visual grounding |
| **Undo** | Spoken / Typed: *"Undo"* | Reverses last file operation or setting change |
| **Settings Drawer** | Click `⚙` or `🎛` on HUD | Configure audio devices, theme, engine, and plugins |

---

## 🗂️ Project Architecture

```
NEO/
├── main.py                                      # Main event loop, Gemini Live session & action dispatcher
├── ui.py                                        # PyQt6 Holographic HUD, avatar renderer & controls
├── setup.py                                     # OS-specific dependency installer
├── pyproject.toml                               # Build system, dependencies, and test configuration
│
├── neo/                                         # Core Autonomous Deterministic Engine
│   ├── windows/                                 # Windows Level 3-4 Execution Tier
│   │   ├── core.py                              # Win32 SendInput, window snapping, focus, list_windows
│   │   ├── uia_snapshot.py                      # 1-based numbered element tree, stable IDs, UIA patterns
│   │   └── actions.py                           # Whitelisted actions, dynamic settle polling, empirical readback
│   ├── safety/                                  # Security Policies, Confirmation Gates & Injection Defense
│   │   ├── policy.py                            # Allow-lists (apps, folders, domains), risky action detector
│   │   ├── gates.py                             # Interactive confirmation gate, hard stops, JSONL audit trail
│   │   ├── injection.py                         # Indirect prompt injection detector & untrusted text sanitizer
│   │   └── emergency_stop.py                    # Thread-safe emergency stop mechanism
│   ├── browser/                                 # Level 2 Playwright Browser Controller
│   │   ├── controller.py                        # Headed/headless Chromium manager with persistent profile
│   │   ├── snapshot.py                          # Unified numbered interactive element snapshot tree
│   │   ├── actions.py                           # goto, click, type, select, scroll, wait_for, go_back
│   │   └── popups.py                            # Configurable cookie banner & modal popup rejection
│   ├── files_office/                            # Level 1 Direct APIs & COM Automation
│   │   ├── files.py                             # Restricted filesystem ops, recycle deletion, sha256 evidence
│   │   └── office.py                            # Excel read/write, Word text replacement, Outlook drafts
│   ├── tools/                                   # System Info & Tool Registry
│   │   ├── registry.py                          # Pydantic schema-validated tool hub with risk levels
│   │   └── system_tools.py                      # Battery, disk, network, clipboard, and process inspectors
│   ├── vision/                                  # Level 5 Vision Fallback & OCR
│   │   ├── capture.py                           # MSS screenshot capture, DPI scaling, and coordinate mapping
│   │   ├── ocr.py                               # Windows OCR with bounding boxes & ambiguity flagging
│   │   ├── diff.py                              # OpenCV visual image diffing returning changed regions
│   │   └── click_xy.py                          # Fallback coordinate click requiring tier exhaustion proof
│   ├── brain/                                   # Cognitive Orchestration & Dual Verification
│   │   ├── prompts.py                           # Versioned system prompt loader with dynamic schema injection
│   │   ├── schema.py                            # Strict Pydantic LLMReply schema with retry budget & escalation
│   │   ├── context.py                           # Compact state representation (attaches screenshots only when sparse)
│   │   ├── critic.py                            # Independent LLM GoalCritic for dual-verification agreement
│   │   ├── planner.py                           # Multi-level deterministic action router & bounds validator
│   │   └── agent.py                             # Main autonomous perception-action-verification loop
│   ├── tasks/                                   # State Machine, Checkpoints & Skill Library
│   │   ├── stages.py                            # Code-gated stage machine (FileExists, ValueEquals, ElementExists)
│   │   ├── retry_policy.py                      # Tiered retry policy & loop detection (actions & frozen states)
│   │   ├── checkpoints.py                       # Pre-action checkpoints with automated rollback on failure
│   │   ├── skills.py                            # Parameterized skill library with deterministic replay & fallback
│   │   ├── reports.py                           # Final markdown report generator with per-stage empirical evidence
│   │   └── task_manager.py                      # Task execution engine coordinating checkpoints & state machine
│   └── ui/                                      # Dashboard, Hotkeys & Voice Trigger
│       ├── dashboard.py                         # Live Tkinter telemetry dashboard (What Neo Sees, Action, Log, STOP)
│       ├── hotkey.py                            # Global Win32 hotkeys (Ctrl+Alt+S, Ctrl+Alt+N)
│       └── voice.py                             # Audio voice trigger (sounddevice + Whisper speech-to-text)
│
├── actions/                                     # Core action plugins auto-discovered by loader
│   ├── ghost_hands.py                           # Zero-hijacking background computer operator
│   ├── browser_cdp.py                           # Chrome DevTools Protocol DOM bridge
│   ├── computer_control.py                      # Mouse, keyboard, UIA & Set-of-Marks grid clicking
│   ├── os_control.py                            # Window snapping, power schemes, settings URIs & health
│   ├── meeting_copilot.py                       # Internal audio loopback & minute generator
│   └── neo_memory.py                            # Lifelong Tri-Tier knowledge recall
├── core/                                        # Core intelligence, visual grounding & OS layer
│   ├── neo_ghost_hands.py                       # UIA COM pattern & Win32 background event dispatcher
│   ├── neo_key_rotator.py                       # Multi-key pool & automatic 429 quota rotation engine
│   ├── neo_cdp_bridge.py                        # CDP WebSocket controller & DOM evaluator
│   ├── neo_dpi_ocr.py                           # DPI coordinate transformer & visual contour detector
│   ├── neo_som_engine.py                        # Set-of-Marks high-contrast visual badge generator
│   ├── neo_win_orchestrator.py                  # Windows settings URIs, powercfg & virtual desktops
│   ├── neo_visual_diff_oracle.py                # Visual absdiff verification & adaptive settle watchdog
│   ├── neo_computer_operator.py                 # Multi-turn autonomous closed-loop computer operator
│   ├── neo_ui_automation.py                     # Native Windows UI Automation control harvester
│   └── neo_ambient_copilot.py                   # Live clipboard & terminal stack trace observer
├── memory/                                      # Persistent local memory, databases & session history
├── config/                                      # API keys, routines, and user preferences
└── tests/                                       # Comprehensive automated verification suites
    ├── e2e/                                     # 26-Scenario Autonomous Benchmark Suite
    │   ├── scenarios.py                         # 26 benchmark scenarios with explicit completion criteria
    │   ├── server.py                            # Local mock HTTP server for browser edge-case tests
    │   ├── scoring.py                           # Metric calculator (success rate, false-done, safety hits)
    │   └── benchmark.py                         # Benchmark runner CLI with --regression support
    ├── test_evidence_and_validation_audit.py    # Tests for evidence collection, disabled elements, bounds
    ├── test_actions_unit.py                     # Unit tests for Windows actions whitelist & verification
    ├── test_browser_local_site.py               # Playwright browser integration tests on local site
    ├── test_brain_refactor.py                   # Brain schema, prompt, context, and critic unit tests
    ├── test_brain_and_tasks.py                  # TaskManager budget, lifecycle, and emergency stop tests
    ├── test_vision.py                           # Scaling roundtrip, Windows OCR, and diff tests
    ├── test_tasks_refactor.py                   # Stages, loops, checkpoints, and skill replay tests
    └── test_ui_and_dashboard.py                 # Tkinter dashboard, hotkeys, and voice trigger unit tests
```

---

## 🤝 Open Source & Contributing

NEO is an open-source project created for the global developer and AI community. **Anyone and everyone is welcome to contribute!** Whether you're a seasoned systems engineer, frontend designer, AI researcher, or a newcomer making your very first pull request, your contributions help shape the future of autonomous computer interaction.

### 🌟 High-Impact Areas to Contribute
- **🛠️ Action Plugins (`actions/*.py`)**:
  - Build custom actions in Python for tools and services you love: Spotify, Discord, Notion, Slack, Obsidian, Docker, GitHub, Linear, smart home IoT, or financial APIs.
  - *Zero Boilerplate*: Any new Python script dropped into the `actions/` directory is automatically discovered and loaded dynamically on startup.
- **🐧 🍏 Cross-Platform Drivers (`core/*.py`)**:
  - Expand Linux (Wayland, D-Bus, X11) and macOS (Accessibility API, AppleScript, Quartz) OS-level automation to reach complete parity with Windows.
- **🎨 UI / UX & Holographic HUD (`ui.py`, `core/neo_ui.py`)**:
  - Design new themes, improve responsiveness and high-DPI scaling, create audio visualizers, or refine 3D avatar animations and accessibility.
- **🧠 Local AI & Multimodal Pipelines (`core/stt.py`, `core/tts.py`, `core/gemini.py`)**:
  - Integrate emerging local speech models (Whisper, Kokoro, Piper, Sherpa) and local LLMs/VLMs (Ollama, LM Studio, vLLM, llama.cpp).
- **🧪 Test Coverage & Diagnostics (`tests/*.py`)**:
  - Add regression tests, mock fixtures, and synthetic benchmark drills for edge-case automation scenarios.
- **📖 Documentation, Guides & Localization**:
  - Clarify instructions, write beginner tutorials, translate documentation into other languages, or record demo walkthroughs.

### 🚀 Step-by-Step Contribution Workflow
1. **Fork the Repository**:
   Click the **Fork** button at the top right of this repository.
2. **Clone Your Fork**:
   ```bash
   git clone https://github.com/<your-username>/NEO.git
   cd NEO
   ```
3. **Create a Feature Branch**:
   ```bash
   git checkout -b feat/my-new-feature
   ```
4. **Make Your Changes**:
   Implement your feature, new action module, or documentation improvement.
5. **Verify Code & Run Tests**:
   ```powershell
   python -m unittest tests/test_key_rotator_suite.py tests/test_advanced_computer_control_suite.py tests/test_core_system_control_suite.py tests/test_ambient_and_meeting_copilot.py
   ```
6. **Commit with a Clean Message**:
   ```bash
   git commit -m "feat(actions): add new Spotify playlist manager action"
   ```
7. **Push & Open a Pull Request**:
   ```bash
   git push origin feat/my-new-feature
   ```
   Open a Pull Request on GitHub against `main`. We actively review and celebrate all community contributions!

### 💬 Community & Questions
- **Issue Tracker**: Found a bug or have a suggestion? [Open an issue on GitHub](https://github.com/thefayid/NEO/issues).
- **Feature Requests**: Share what you'd like NEO to operate or automate next!

---

## 🔒 Privacy & Security

- **Local First**: All conversation memory, settings, and credentials remain on your local machine.
- **Untrusted Content Boundary**: External web pages and document text are wrapped in data barriers to prevent prompt injection.
- **Confirmation Gate**: High-risk actions (shutdown, restart, network toggles) require explicit physical user confirmation.

---

## 📄 License & Community

- **Open Source Community**: Contributions, pull requests, and feature suggestions are enthusiastically welcomed from developers worldwide!
- **License**: Personal and non-commercial open source use under [Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
- **Author**: Rahman Fayid ([rahmanfayidpm@gmail.com](mailto:rahmanfayidpm@gmail.com))  
- ⭐ **Star the repo on GitHub to support ongoing NEO development!**

# ⚙️ NEO: Autonomous Computer-Operator & Voice AI

> **The Ultimate Real-Time Multimodal Voice & Desktop Operating Assistant**  
> *Engineered by Rahman Fayid*  
> 🪟 **Mainly optimized for Windows** *(Deep Win32, UI Automation, and hardware-level orchestrations)*  
> 🐧 🍏 **Compatible with Linux and macOS** *(More updates and deeper native integrations on these platforms coming soon!)*

---

## 🌟 Overview

**NEO** is an autonomous computer-operator and real-time voice AI assistant. Powered by the **Gemini Live API** and an optional **100% Local Pipeline** (Whisper + Ollama + Piper), NEO can see your screen in real time through continuous live video streaming, understand user interfaces via multimodal visual grounding, hear your voice, and operate desktop and browser applications with precise, verified actions.

While NEO is **mainly optimized for Windows** with deep OS-level accessibility and system schemes, it is fully cross-platform for Linux and macOS, with dedicated updates actively in development.

---

## 🚀 Top Features

| Feature | Description |
|---|---|
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
| 📋 **Deterministic Workflow Engine** | Instant multi-step routine and macro execution with zero LLM latency (`dev_workspace`, `focus_mode`, `system_tuneup`, `meeting_prep`). |
| 📱 **Remote Dashboard** | Local network phone dashboard paired via QR code for wireless monitoring and remote control. |

---

## 🖥️ Platform Support & Roadmap

| Platform | Support Status | Capabilities & Notes |
|---|---|---|
| **Windows 10 / 11** | 🟢 **Mainly Optimized (Tier 1)** | Complete deep integration: Win32 window snapping, Windows UI Automation (UIA) tree extraction, hardware power scheme management (`powercfg`), direct `ms-settings:` URIs, virtual desktops, audio loopback capture, and DPI scaling translation. |
| **Linux (Ubuntu, Debian, Fedora, Arch)** | 🟡 **Compatible (Core Features)** | Full voice conversation, local pipelines (Whisper/Ollama/Piper), terminal/shell executions, CDP browser automation, and standard computer control. *Native D-Bus / Wayland screen integration updates coming soon.* |
| **macOS (Apple Silicon & Intel)** | 🟡 **Compatible (Core Features)** | Full Gemini Live voice, audio I/O, terminal actions, and web automation. *Dedicated AppleScript & macOS Accessibility API enhancements coming soon.* |

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

### 5. Configure Credentials
Add your Gemini API key to `config/api_keys.json` (or enter it in the setup dialog on first launch):
```json
{
  "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE"
}
```
*(If running fully offline with local Ollama + Whisper + Piper, no API key is required).*

### 6. Launch NEO
```bash
python main.py
```

---

## 🧪 Testing & Verification by Commands

You can verify and test every component of NEO directly from your command line without starting the full GUI:

### 1. Run Complete Automated Test Suite (37 Tests)
```powershell
python -m unittest tests/test_advanced_computer_control_suite.py tests/test_core_system_control_suite.py tests/test_ambient_and_meeting_copilot.py
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

---

## 🎮 Controls & Shortcuts

| Action | Control | Description |
|---|---|---|
| **Push-to-Talk** | `Ctrl + Space` | Hold to speak, release to send audio |
| **Wake Word** | Spoken: *"Hey Neo"* | Offline wake word detector |
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
├── actions/                                     # Core action modules auto-discovered by loader
│   ├── browser_cdp.py                           # Chrome DevTools Protocol DOM bridge
│   ├── computer_control.py                      # Mouse, keyboard, UIA & Set-of-Marks grid clicking
│   ├── os_control.py                            # Window snapping, power schemes, settings URIs & health
│   ├── meeting_copilot.py                       # Internal audio loopback & minute generator
│   └── neo_memory.py                            # Lifelong Tri-Tier knowledge recall
├── core/                                        # Core intelligence, visual grounding & OS layer
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
    ├── test_advanced_computer_control_suite.py  # Tests for SoM, CDP, DPI, Win Orchestrator, & Diff Oracle
    ├── test_core_system_control_suite.py        # Tests for OS automation, routines, and operator loop
    └── test_ambient_and_meeting_copilot.py      # Tests for ambient clipboard & audio loopback
```

---

## 🔒 Privacy & Security

- **Local First**: All conversation memory, settings, and credentials remain on your local machine.
- **Untrusted Content Boundary**: External web pages and document text are wrapped in data barriers to prevent prompt injection.
- **Confirmation Gate**: High-risk actions (shutdown, restart, network toggles) require explicit physical user confirmation.

---

## 📄 License & Contact

- **License**: Personal and non-commercial use under [Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
- **Author**: Rahman Fayid ([rahmanfayidpm@gmail.com](mailto:rahmanfayidpm@gmail.com))  
- ⭐ **Star the repo on GitHub to support NEO development!**

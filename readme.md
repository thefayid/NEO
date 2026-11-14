# ⚙️ NEO: Autonomous Computer-Operator & Voice AI

> **The Ultimate Real-Time Multimodal Voice & Desktop Operating Assistant**  
> *Engineered by Rahman Fayid* • Cross-platform: Windows, macOS, Linux

---

## 🌟 Overview

**NEO** is an autonomous computer-operator and real-time voice AI assistant. Powered by the **Gemini Live API** and an optional **100% Local Pipeline** (Whisper + Ollama + Piper), NEO can see your screen, understand user interfaces via multimodal visual grounding, hear your voice, and operate desktop and browser applications with precise, verified actions.

---

## 🚀 Top Features

| Feature | Description |
|---|---|
| 🖱️ **Computer Operator** | Autonomous UI navigation, mouse clicks, keyboard input, window raising, and browser automation via multimodal grounding and Windows UI Automation. |
| 🎙️ **Real-Time Voice & Vision** | Ultra-low latency voice streaming with Gemini Live API, screen capture lens, and live webcam integration. |
| 🧑‍🎤 **Holographic Avatar & Lip-Sync** | Software-rendered 3D facial avatar with formant/viseme lip-sync (~50 shapes/sec), facial acting, and reactive audio waveforms. |
| 🔌 **Dual-Engine Flexibility** | Switch seamlessly between **Gemini Live** and **Local / Self-Hosted** engines (Whisper STT + Ollama / LM Studio + Piper TTS) with zero code changes. |
| 🛡️ **Verified Grounding & Safety** | Tools report ground truth (`done`, `unverified`, `failed`). Built-in safety gates for destructive tasks and natural language `undo`. |
| 🧠 **Persistent Local Memory** | Dynamic memory recall with smart prompt indexing, local search, and privacy-first storage (`memory/long_term.json`). |
| 🎙️ **Push-to-Talk & Wake Word** | Global push-to-talk chord (**Ctrl+Space**), local offline **"Hey Jarvis"** wake word, and self-echo filtering. |
| 🧩 **Extensible Plugin System** | Modular architecture where tools and plugins (`actions/`, `plugins/`) auto-register with typed schema definitions. |
| 📱 **Remote Dashboard** | Local network phone dashboard paired via QR code for wireless monitoring and remote control. |

---

## ⚡ Quick Start & Setup

### 1. Prerequisites
- **Python**: 3.10, 3.11, or 3.12 (Python 3.11+ recommended).
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

## 🎮 Controls & Shortcuts

| Action | Control | Description |
|---|---|---|
| **Push-to-Talk** | `Ctrl + Space` | Hold to speak, release to send audio |
| **Wake Word** | Spoken: *"Hey Jarvis"* | Offline wake word detector |
| **Screen Lens** | `F10` / `Ctrl + Shift + L` | Captures active display for visual grounding |
| **Undo** | Spoken / Typed: *"Undo"* | Reverses last file operation or setting change |
| **Settings Drawer** | Click `⚙` or `🎛` on HUD | Configure audio devices, theme, engine, and plugins |

---

## 🗂️ Project Architecture

```
NEO/
├── main.py                   # Main event loop, Gemini Live session & action dispatcher
├── ui.py                     # PyQt6 Holographic HUD, avatar renderer & controls
├── setup.py                  # OS-specific dependency installer
├── actions/                  # Core computer control, browser automation & OS tools
├── core/                     # Visual grounding, prompt rules, audio I/O & safety guards
├── memory/                   # Persistent local memory and configuration manager
├── plugins/                  # Extensible skills (WhatsApp, dev agents, timers, etc.)
└── providers/                # Local/hosted engine adapters (Whisper, Ollama, Piper)
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

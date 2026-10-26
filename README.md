# Infinity Snap — Neural Multi-Gesture Cyberpunk Desktop Automator

Infinity Snap is an audio-reactive Windows desktop automator and folder monitoring engine. Using real-time microphone transient analysis, it classifies acoustic snap patterns and executes multi-action macros with an animated Cyberpunk terminal HUD.

---

## 1. Project Architecture

`main.py` serves as the central conductor connecting all modular subsystems:

```text
INFINITY SNAP/
│
├── main.py                     # Central conductor & plug-and-play entry point
├── config.json                 # Auto-generated or user configuration
├── config.example.json         # Example configuration template
├── requirements.txt            # Runtime dependencies
├── README.md                   # Complete documentation and operator guide
├── .gitignore                  # Git exclusions
│
├── core/                       # Clean modular architecture
│   ├── __init__.py
│   ├── audio_engine.py         # Acoustic transient listener, spectral filter & live VU meter
│   ├── action_router.py        # Handlers: 1 Snap (Panic Stealth), 2 Snaps (Folder Purge)
│   ├── fs_monitor.py           # Win32 FindFirstChangeNotificationW folder observer
│   ├── hud.py                  # Cyberpunk HUD renderer (live VU, gesture state, payload stats)
│   ├── config_manager.py       # Configuration loader, saver, and first-run setup wizard
│   ├── hotkey_manager.py       # Win32 RegisterHotKey OS-wide (Ctrl + Alt + S) toggle
│   ├── notification_manager.py # Windows 10/11 Action Center native toast notifications
│   ├── plugin_engine.py        # Asynchronous custom script/webhook dispatcher
│   └── tray_manager.py         # Windows System Tray with dynamic glowing emblem
│
├── plugins/                    # Drop custom scripts here (.bat, .ps1, .py, .exe)
│   ├── single_snap/            # Runs on 1 Snap (Panic Mode)
│   │   └── example_webhook.bat
│   ├── double_snap/            # Runs on 2 Snaps (Folder Purge)
│   │   └── example_smart_light.bat
│   └── README.md
│
├── archive/                    # Archived legacy modules and previous test assets
│   ├── test_folder.py
│   ├── mic_analyzer.py
│   ├── diagnostic_events.csv
│   └── test_files/
└── venv/                       # Python virtual environment
```

---

## 2. Multi-Gesture Acoustic Matrix

Infinity Snap accumulates snap transients within an intelligent time window:

| Gesture Pattern | Action Executed | Description |
| :--- | :--- | :--- |
| **1 Snap** | **Panic Stealth Boss Mode** | Instantly minimizes all active desktop windows (`Win + D`) and mutes master audio volume (`VK_VOLUME_MUTE`). Dispatches single-snap plugins and fires a native Windows toast. |
| **2 Snaps** | **Instant Folder Purge** | Immediately triggers upon the second snap without waiting! Dispatches all eligible files & subfolders in the target sector directly to the Windows Recycle Bin using native `SHFileOperationW`. 100% recoverable. |

---

## 3. Cyberpunk HUD & Audio-Reactive VU Meter

The interface is rendered with `rich.live.Live` at 10 FPS, providing an animated visualizer:

```text
┌────────────── ⚡ INFINITY SNAP // NEURAL MULTI-GESTURE HUD ⚡ ──────────────┐
│                                                                             │
│   STATUS                 ::   ● ARMED  SURVEILLANCE ENGAGED ── Continuous   │
│                              monitoring active                              │
│   TARGET SECTOR          ::  C:\Users\...\Desktop\ENDGAME                   │
│   PURGE PROTOCOL         ::  NORMAL ── [Windows Desktop Recycle Bin /       │
│                              100% Recoverable]                              │
│   AUDIO SENSOR           ::  Microphone Array (Intel® Smart Sound)          │
│   SECTOR PAYLOAD         ::  80 Files │ 0 Directories (80 items ready)      │
│   LIVE AUDIO VU          ::  ███████░░░░░░░░░░░░░ -14.2 dBFS │ TRIGGER:     │
│                              0.50                                           │
│   GESTURE MATRIX         ::  1 Snap: Panic Stealth │ 2 Snaps: Instant       │
│                              Folder Purge                                   │
│   GESTURE DETECTOR       ::  ● READY ── Listening for transients            │
│   LAST TELEMETRY         ::  System initialized and armed                   │
│                                                                             │
└─ [Ctrl+C] EXIT  │  [Ctrl+Alt+S] TOGGLE MUTE  │  TRAY ACTIVE  │  RECOVERABLE ─┘
```

---

## 4. Getting Started (Plug and Play)

### Step 1: Activate Virtual Environment
Open PowerShell in the project directory:
```powershell
.\venv\Scripts\Activate.ps1
```

> **PowerShell Execution Policy Note:**  
> If script execution is disabled on your system, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then re-run `.\venv\Scripts\Activate.ps1`.

### Step 2: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Run (Plug and Play)
```powershell
python main.py
```
*No test modes or confirmation prompts. Launch and it immediately engages surveillance.*

---

## 5. Desktop Ergonomics: System Tray, Global Hotkey & Toasts

### ⚡ Global Mute / Hotkey Toggle (`Ctrl + Alt + S`)
- Powered by native Win32 `RegisterHotKey`. Works everywhere across Windows even when the terminal is minimized or in the background.
- Instantly pauses microphone listening when entering noisy meetings, playing music, or typing aggressively.
- Pressing `Ctrl + Alt + S` again instantly re-arms acoustic surveillance.

### ◈ Windows System Tray Integration
- Automatically runs in your Windows Taskbar Notification Tray with a dynamic glowing Cyberpunk emblem:
  - **Neon Cyan Glow**: Surveillance Armed & Listening.
  - **Warning Amber Ring**: Sensor Muted / Standby.
  - **Neon Magenta Flash**: Gesture triggered.
- **Right-Click Context Menu**:
  - `Toggle Mute / Arm (Ctrl+Alt+S)`
  - `Open Monitored Sector` (Launches Windows Explorer directly in your monitored folder)
  - `Trigger Panic Stealth (1 Snap)`
  - `Trigger Folder Purge (2 Snaps)`
  - `Exit Infinity Snap`

### 🔔 Native Windows Action Center Toasts
- Emits official Windows 10/11 desktop toast notifications summarizing actions taken:
  - *Panic Stealth Engaged*
  - *Folder Purged (X items sent to Recycle Bin)*
  - *Sensor Muted / Re-armed*

---

## 6. Custom Script & Plugin Engine (`plugins/`)

Infinity Snap allows you to hook any custom script, external webhook, or IoT automation directly into your snaps:

- Drop `.bat`, `.cmd`, `.ps1`, `.py`, or `.exe` files into:
  - `plugins/single_snap/` $\rightarrow$ Executes asynchronously when 1 Snap triggers.
  - `plugins/double_snap/` $\rightarrow$ Executes asynchronously when 2 Snaps trigger.
- **Injected Environment Variables**:
  All scripts automatically receive:
  - `%INFINITY_GESTURE%` (`SINGLE_SNAP` / `DOUBLE_SNAP`)
  - `%INFINITY_SNAP_COUNT%` (`1` / `2`)
  - `%INFINITY_PEAK%` (Detected acoustic amplitude)
  - `%INFINITY_TARGET_DIR%` (Monitored folder path)

---

## 7. Configuration & Commands

Configuration is loaded from `config.json`:
```json
{
    "monitoring_folder": "C:\\Users\\username\\Desktop\\ENDGAME",
    "action_mode": "NORMAL",
    "threshold": 0.50,
    "cooldown": 1.20,
    "device": null
}
```

### Optional Command-Line Overrides:
```powershell
# Re-open the interactive setup wizard
python main.py --setup

# Override audio threshold sensitivity (0.05 to 0.95)
python main.py -t 0.55

# List all audio input sensors
python main.py -l

# Override gesture cooldown in seconds
python main.py -c 1.5
```

---

## 8. Security & Safety Firewalls

- **Strict Forbidden Paths**: Drive roots (`C:\`), Windows system folders (`C:\Windows`), Program Files, User Profile roots (`C:\Users\<user>`), Desktop/Documents root, and the project folder itself are strictly blocked by boundary firewalls.
- **Symlink / Junction Rejection**: Symbolic links, NTFS junctions, and reparse points are filtered out to prevent path traversal attacks.
- **Recoverable Recycle Bin Purge**: Powered by `ctypes.windll.shell32.SHFileOperationW` with `FO_DELETE` and `FOF_ALLOWUNDO`. No permanent deletion fallback (`os.remove`, `Path.unlink`, `shutil.rmtree`) exists anywhere in the codebase.

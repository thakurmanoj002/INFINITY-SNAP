# Infinity Snap — Plugin & Custom Script System

This directory allows you to trigger custom scripts, external webhooks, smart bulbs, or home automation devices with a snap of your fingers.

---

## Folder Structure

```text
plugins/
├── single_snap/       # Scripts here execute on 1 Snap (Panic Stealth Boss Mode)
│   └── example_webhook.bat
├── double_snap/       # Scripts here execute on 2 Snaps (Instant Folder Purge)
│   └── example_smart_light.bat
└── README.md
```

You can also place files named `on_single_snap.*` or `on_double_snap.*` directly in `plugins/`.

---

## Supported File Types

- **Batch Scripts**: `.bat`, `.cmd`
- **PowerShell Scripts**: `.ps1` (executed with `-NoProfile -ExecutionPolicy Bypass`)
- **Python Scripts**: `.py` (executed using the active virtual environment Python)
- **Executable Binaries**: `.exe`

---

## Injected Environment Variables

All plugins run asynchronously in the background (without freezing the HUD or audio stream) and inherit the following environment variables:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `INFINITY_GESTURE` | Identifier of the triggered gesture | `SINGLE_SNAP` or `DOUBLE_SNAP` |
| `INFINITY_SNAP_COUNT` | Number of snaps detected | `1` or `2` |
| `INFINITY_PEAK` | Peak acoustic energy level | `0.7842` |
| `INFINITY_THRESHOLD` | Active sound threshold | `0.5000` |
| `INFINITY_TARGET_DIR` | Absolute path of monitored folder | `C:\Users\...\ENDGAME` |

---

## Quick Examples

### Toggle Smart Lights via Webhook (PowerShell `plugins/single_snap/bulb.ps1`):
```powershell
Invoke-RestMethod -Uri "http://192.168.1.50/api/toggle" -Method POST
```

### Discord / Slack Notification (Python `plugins/double_snap/discord.py`):
```python
import os, urllib.request, json

data = json.dumps({"content": f"⚡ Infinity Snap purged target folder: {os.environ.get('INFINITY_TARGET_DIR')}"}).encode()
req = urllib.request.Request("https://discord.com/api/webhooks/YOUR_WEBHOOK_URL", data=data, headers={"Content-Type": "application/json"})
urllib.request.urlopen(req)
```

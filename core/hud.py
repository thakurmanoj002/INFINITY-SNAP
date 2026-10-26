"""
Infinity Snap — Cyberpunk HUD & Audio-Reactive VU Visualizer
============================================================
Renders high-visibility Cyberpunk terminal dashboard with live animated
VU audio meter, multi-gesture status pills, and payload telemetry.
"""

from pathlib import Path
import sys

# Configure UTF-8 encoding on Windows to prevent legacy charmap codec errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def abbreviate_path(path: Path, max_length: int = 50) -> str:
    """Abbreviates a path with ellipsis if it exceeds max_length for clean CLI display."""
    s = str(path)
    if len(s) <= max_length:
        return s
    return s[:16] + "..." + s[-(max_length - 19):]


def build_hud_panel(
    monitor_dir: Path,
    action_mode: str,
    device_name: str,
    threshold: float,
    file_count: int,
    dir_count: int,
    live_peak: float,
    live_dbfs: float,
    gesture_state: str,
    last_event: str,
    is_armed: bool = True,
    camera_active: bool = False,
    vision_gesture: str = "NONE",
    vision_fps: float = 0.0,
) -> Panel:
    """Constructs the Rich Panel representation of the Cyberpunk HUD."""
    abbr_dir = abbreviate_path(monitor_dir, max_length=52)

    # Status indicator pill
    if is_armed:
        status_markup = (
            "[bold black on #00ff66] ● ARMED [/] "
            "[bold #00ff66]SURVEILLANCE ENGAGED[/] "
            "[dim cyan]── Continuous monitoring active[/]"
        )
    else:
        status_markup = (
            "[bold black on #ffe600] ○ PAUSED [/] "
            "[bold #ffe600]SENSOR MUTED[/] "
            "[dim]── Standby mode [Press Ctrl+Alt+S to Re-arm][/]"
        )

    # Live VU meter bar (20 blocks total)
    total_vu_blocks = 20
    vu_fill = max(0, min(total_vu_blocks, int(live_peak * total_vu_blocks)))
    
    # Color bar based on energy level
    if vu_fill >= int(threshold * total_vu_blocks):
        bar_color = "#ff0055"  # Spike over threshold
    elif vu_fill >= 8:
        bar_color = "#ffe600"  # Medium energy
    else:
        bar_color = "#00f0ff"  # Low ambient

    vu_bar = (
        f"[bold {bar_color}]{'█' * vu_fill}[/]"
        f"[dim #252839]{'░' * (total_vu_blocks - vu_fill)}[/] "
        f"[bold white]{live_dbfs:5.1f} dBFS[/] "
        f"[dim #ff007f]│[/] [bold #ff007f]TRIGGER:[/] [bold #00f0ff]{threshold:.2f}[/]"
    )

    # Gesture status styling
    if "DOUBLE" in gesture_state:
        gesture_styled = f"[bold white on #ff0055] {gesture_state} [/]"
    elif "SNAP 1" in gesture_state:
        gesture_styled = f"[bold black on #00f0ff] {gesture_state} [/]"
    else:
        gesture_styled = f"[bold #00ff66]● READY[/] [dim cyan]── Listening for transients[/]"

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold #ff007f", no_wrap=True, width=21)
    table.add_column("Sep", style="dim #00f0ff", width=2)
    table.add_column("Value", style="white")

    table.add_row("STATUS", "::", status_markup)
    table.add_row("TARGET SECTOR", "::", f"[bold #00f0ff]{abbr_dir}[/]")
    table.add_row(
        "PURGE PROTOCOL",
        "::",
        f"[bold #ffe600]{action_mode}[/] [dim]──[/] [dim #8888aa][Windows Desktop Recycle Bin / 100% Recoverable][/]",
    )
    table.add_row("AUDIO SENSOR", "::", f"[bright_white]{device_name[:38]}[/]")
    if camera_active:
        g_color = "#00ff66" if vision_gesture != "NONE" else "dim"
        table.add_row(
            "OPTICAL SENSOR",
            "::",
            f"[bold #00f0ff]Active ({vision_fps:4.1f} FPS)[/] [dim #ff007f]│[/] [bold #00f0ff]AIR GESTURE:[/] [bold {g_color}]{vision_gesture}[/]",
        )
    table.add_row(
        "SECTOR PAYLOAD",
        "::",
        f"[bold #00ff66]{file_count} Files[/] [dim #ff007f]│[/] [bold #00f0ff]{dir_count} Directories[/] [dim cyan]({file_count + dir_count} items ready)[/]",
    )
    table.add_row("LIVE AUDIO VU", "::", vu_bar)
    table.add_row(
        "GESTURE MATRIX",
        "::",
        "[bold cyan]1 Snap:[/] [dim]Panic Stealth[/] [dim]│[/] [bold #ff0055]2 Snaps:[/] [dim]Instant Folder Purge[/]",
    )
    table.add_row("GESTURE DETECTOR", "::", gesture_styled)
    table.add_row("LAST TELEMETRY", "::", f"[italic #ff79c6]{last_event}[/]")

    vision_pill = "[bold #00f0ff]VISION ON[/]" if camera_active else "[dim]VISION OFF[/]"

    return Panel(
        table,
        title="[bold #00f0ff]⚡ INFINITY SNAP // NEURAL MULTI-GESTURE HUD ⚡[/]",
        subtitle=f"[bold #ffe600][Ctrl+C][/] [dim white]EXIT[/]  [dim #00f0ff]│[/]  [bold #00f0ff][Ctrl+Alt+S][/] [dim white]TOGGLE MUTE[/]  [dim #00f0ff]│[/]  [bold #00ff66]TRAY ACTIVE[/]  [dim #00f0ff]│[/]  {vision_pill}",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def print_audio_devices():
    """Lists all available audio input devices found on the system using Rich."""
    import sounddevice as sd

    try:
        devices = sd.query_devices()
        input_devices = [
            (i, d) for i, d in enumerate(devices) if d.get("max_input_channels", 0) > 0
        ]

        if not input_devices:
            console.print("[bold #ff0055]No audio input devices (microphones) were found.[/]")
            return

        table = Table(
            title="[bold #00f0ff]◈ AVAILABLE AUDIO SENSORS // TRANSDUCER MATRIX ◈[/]",
            border_style="bright_cyan",
            box=box.ROUNDED,
        )
        table.add_column("Index", style="bold #ff007f", justify="center")
        table.add_column("Sensor Name", style="white")
        table.add_column("Channels", style="#00ff66", justify="center")
        table.add_column("Sample Rate", style="#ffe600", justify="center")
        table.add_column("Status", style="bold cyan", justify="center")

        default_input = sd.default.device[0]
        for idx, dev in input_devices:
            is_default = "[bold #00ff66]● DEFAULT[/]" if idx == default_input else "[dim]AVAILABLE[/]"
            table.add_row(
                str(idx),
                dev["name"],
                str(dev["max_input_channels"]),
                f"{int(dev['default_samplerate'])} Hz",
                is_default,
            )
        console.print(table)
    except Exception as exc:
        console.print(f"[bold #ff0055]Error querying audio devices: {exc}[/]")

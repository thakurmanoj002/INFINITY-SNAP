"""
Infinity Snap — Spatial Air Desktop Controller
==============================================
Standalone launcher for Apple Vision Pro style spatial hand interaction.
Directly interact with your Windows desktop using your webcam:
  - Point index finger to guide cursor
  - Pinch thumb + index to click & drag
  - Pinch thumb + middle finger for right click
  - Two fingers up/down to scroll
  - Fist to rest / freeze
"""

import argparse
import sys
import time

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel

from core.air_desktop import AirDesktopController

console = Console()


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Infinity Snap — Spatial Air Desktop Controller (Apple Vision Pro Mode)"
    )
    parser.add_argument(
        "-c",
        "--camera",
        type=int,
        default=0,
        help="Select camera device index (default: 0)",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Run headless in the background without camera preview window",
    )
    parser.add_argument(
        "--smoothing",
        type=float,
        default=0.40,
        help="Cursor smoothing interpolation factor between 0.05 (heavy smooth) and 0.90 (fast)",
    )
    parser.add_argument(
        "--scroll-speed",
        type=float,
        default=24.0,
        help="Two-finger scroll sensitivity factor",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    console.print(
        Panel(
            "[bold #00f0ff]◈ SPATIAL AIR DESKTOP CONTROLLER INITIALIZING ◈[/]\n\n"
            "[bold white]Gestures Active:[/]\n"
            "  [bold cyan]• Index Finger Pointing[/]   : Glide mouse cursor across desktop\n"
            "  [bold #00ff66]• Index + Thumb Pinch[/]      : Left Click (Hold to Drag & Drop)\n"
            "  [bold yellow]• Middle + Thumb Pinch[/]     : Right Click (Context Menu)\n"
            "  [bold #ff79c6]• Two Fingers Up / Down[/]    : Smooth page & document scroll\n"
            "  [dim white]• Clenched Fist[/]            : Rest / Freeze cursor in place\n\n"
            "[dim]Press [bold yellow]Ctrl+C[/] or close preview window to exit.[/]",
            title="[bold #00f0ff]⚡ APPLE VISION PRO SPATIAL DESKTOP ⚡[/]",
            border_style="bright_cyan",
        )
    )

    controller = AirDesktopController(
        camera_index=args.camera,
        enable_preview=not args.no_preview,
        scroll_speed=args.scroll_speed,
    )

    try:
        controller.start()
        # Keep main thread alive
        while controller._running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[bold #ff007f]Disengaging Air Desktop Controller...[/]")
    finally:
        controller.stop()
        console.print("[dim cyan]Air Desktop Controller released.[/]\n")


if __name__ == "__main__":
    main()

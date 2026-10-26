@echo off
:: =========================================================================
:: Infinity Snap — Single Snap (Panic Stealth) Custom Hook Example
:: =========================================================================
:: Place any .bat, .ps1, or .py files in this folder to execute them
:: automatically whenever Single Snap (Panic Stealth) triggers.
::
:: Available Environment Variables:
::   %INFINITY_GESTURE%    - Current gesture (SINGLE_SNAP)
::   %INFINITY_SNAP_COUNT% - Snap count (1)
::   %INFINITY_PEAK%       - Detected acoustic peak amplitude
::   %INFINITY_THRESHOLD%  - Sound trigger threshold
::   %INFINITY_TARGET_DIR% - Monitored target folder path
::
:: Example: Call external webhook (Discord / Slack / IFTTT / Home Assistant)
:: curl -s -X POST https://maker.ifttt.com/trigger/panic_mode/with/key/YOUR_KEY >nul 2>&1
::
echo [Infinity Snap Hook] Panic mode triggered at %TIME% on %DATE%

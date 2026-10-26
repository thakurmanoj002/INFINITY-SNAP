@echo off
:: =========================================================================
:: Infinity Snap — Double Snap (Folder Purge) Custom Hook Example
:: =========================================================================
:: Place any .bat, .ps1, or .py files in this folder to execute them
:: automatically whenever Double Snap (Instant Folder Purge) triggers.
::
:: Available Environment Variables:
::   %INFINITY_GESTURE%    - Current gesture (DOUBLE_SNAP)
::   %INFINITY_SNAP_COUNT% - Snap count (2)
::   %INFINITY_PEAK%       - Detected acoustic peak amplitude
::   %INFINITY_THRESHOLD%  - Sound trigger threshold
::   %INFINITY_TARGET_DIR% - Monitored target folder path
::
:: Example: Turn smart light red via webhook or post notification
:: curl -s -X POST -H "Content-Type: application/json" -d "{\"status\":\"purged\"}" http://homeassistant.local:8123/api/webhook/purge_event >nul 2>&1
::
echo [Infinity Snap Hook] Folder purge completed at %TIME%

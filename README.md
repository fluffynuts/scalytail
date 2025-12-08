ScalyTail
---

A pyqt6 systray client for Tailscale

Usage
---
All interactions are from the tray:
Right-click for:
- Connect / Disconnect
- Status
- Exit

Click the tray icon to show the tailscale web status page (same as right-click -> status)

![screenshot.png](screenshot.png)

Installation
---
1. clone the repo somewhere
2. ensure you have either pyqt6 or pyqt6 installed
    - on arch-based systems, `pacman -S python-pyqt6`
    - on deb-based systems, `apt install pyqt5-dev` or `apt install pyqt6-dev`
    - on gentoo systems, `emerge pyqt6`
3. you should be able to start with `./scalytail.py`
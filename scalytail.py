#!/bin/env python3
import subprocess

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from subprocess import Popen, PIPE, CalledProcessError
import sys
import os


class ProcessIO:
    def __init__(self, args: list[str], iocallback=None):
        self.exit_code = None
        self.io = []
        print(f"run sub-process: {args}")
        with (Popen(args, stdout=PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True) as process):
            while True:
                if process.poll() is not None:
                    remaining_io = process.stdout.read().strip()
                    if len(remaining_io) > 0:
                        self._on_io(remaining_io, iocallback)
                    break
                line = process.stdout.readline()
                self._on_io(line, iocallback)
        self.exit_code = process.returncode
        if process.returncode != 0:
            raise Exception(f"command exits with non-zero status code: {process.returncode}")
        return

    def _on_io(self, line: str, iocallback):
        stripped = line.rstrip()
        print(stripped)
        if iocallback is not None:
            iocallback(stripped)
        else:
            self.io.append(stripped)


class TailscaleWrapper:
    def __init__(self, on_connecting, on_connected, on_disconnected):
        self._on_connecting = on_connecting
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected

    def tailscale_is_up(self):
        proc = ProcessIO(["tailscale", "status"])
        return proc.exit_code == 0

    def take_down_tailscale(self):
        ProcessIO(["tailscale", "down"])

    def bring_up_tailscale(self):
        user = os.getenv("USER", "")
        args = ["tailscale", "up"]
        if user != "":
            args.append(f"--operator={user}")

        proc = ProcessIO(args, lambda line: self._process_line(line))

    def _process_line(self, line: str):



class ScalyTail:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.setup_icons()

        self.tray_icon = QSystemTrayIcon(self._disconnected_icon, self.app)

        self.tray_icon.setContextMenu(self.generate_menu(self.app))
        self.tray_icon.show()

        sys.exit(self.app.exec())

    def setup_icons(self):
        self._disconnected_icon = QIcon("disconnected.png")
        self._connecting_icon = QIcon("connecting.png")
        self._connected_icon = QIcon("connected.png")

    def generate_menu(self, app: QApplication):
        result = QMenu()

        self._connect_action = QAction("Connect", app)
        self._connect_action.triggered.connect(self.toggle_connection)
        result.addAction(self._connect_action)

        result.addSeparator()
        exit_action = QAction("Exit", app)
        exit_action.triggered.connect(app.quit)
        result.addAction(exit_action)

        return result

    def toggle_connection(self):
        if self._connect_action.text() == "Connect":
            self._connect_action.setText("Disconnect")
        else:
            self._connect_action.setText("Connect")
        pass

    def tray_icon_activated(self, reason: str):
        print(f"tray activated: {reason}")
        pass


if __name__ == "__main__":
    app = ScalyTail()

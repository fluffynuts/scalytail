#!/bin/env python3
import subprocess
from typing import Callable
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from subprocess import Popen, PIPE
import sys
import os
from threading import Thread
from time import sleep

start_folder = os.getcwd()
def go_home():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

def rewind_chdir():
    os.chdir(start_folder)

class ProcessIO:
    def __init__(self, args: list[str], iocallback: Callable[[str], None] = None, suppress_output: bool = False):
        self.exit_code = None
        self.io = []
        print(f"run sub-process: {args}")
        with (Popen(args, stdout=PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True) as process):
            while True:
                if process.poll() is not None:
                    remaining_io = process.stdout.read().strip()
                    if len(remaining_io) > 0:
                        self._on_io(remaining_io, iocallback, suppress_output)
                    break
                line = process.stdout.readline()
                self._on_io(line, iocallback, suppress_output)
        self.exit_code = process.returncode

    def _on_io(self, line: str, iocallback: Callable[[str], None], suppress_output: bool):
        stripped = line.rstrip()
        if not suppress_output:
            print(stripped)
        if iocallback is not None:
            iocallback(stripped)
        else:
            self.io.append(stripped)

    @staticmethod
    def open(url_or_path: str):
        return ProcessIO(["xdg-open", url_or_path])


class TailscaleWrapper:
    def __init__(self, on_connecting: Callable[[], None], on_connected: Callable[[], None],
                 on_disconnected: Callable[[], None]):
        self._on_connecting = on_connecting
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected

        self._watcher = Thread(target=self.poll, daemon=True, name="Monitor")
        self._watcher.start()

    def poll(self):
        is_up = False
        if self.tailscale_is_up():
            is_up = True
            self._on_connected()
        else:
            self._on_disconnected()
        while True:
            current = self.tailscale_is_up()
            if is_up != current:
                if current:
                    self._on_connected()
                else:
                    self._on_disconnected()
            is_up = current
            sleep(10)

    @staticmethod
    def tailscale_is_up() -> bool:
        proc = ProcessIO(["tailscale", "status"], suppress_output=True)
        return proc.exit_code == 0

    def take_down_tailscale(self) -> None:
        ProcessIO(["tailscale", "down"])
        self._on_disconnected()

    def bring_up_tailscale(self) -> None:
        user = os.getenv("USER", "")
        args = ["tailscale", "up"]
        if user != "":
            args.append(f"--operator={user}")
        args.append("--accept-routes")
        proc = ProcessIO(args, lambda line: self._process_line(line))
        if proc.exit_code == 0:
            self._on_connected()
        else:
            self._on_disconnected()

    @staticmethod
    def show_web():
        proc = ProcessIO(["tailscale", "web"])
        if proc.exit_code != 0:
            print("tailscale web error")
            return
        fallback = ""
        for line in proc.io:
            if "starting tailscaled web client" in line:
                parts = line.split(" ")
                ProcessIO.open(parts[-1])
                return
            if "web server running on" in line:
                parts = line.split(" ")
                fallback = parts[-1]
        if fallback != "":
            ProcessIO.open(fallback)
        else:
            print("Unable to determine url to open for tailscale web interface")

    @staticmethod
    def _process_line(line: str) -> None:
        trimmed = line.strip()
        if trimmed.startswith("https://login.tailscale.com"):
            print(f"Opening link: {trimmed}")
            ProcessIO.open(trimmed)


class ScalyTail:
    def __init__(self):
        self._status_action = None
        self._connect_action = None

        self.app = QApplication(sys.argv)
        self._disconnected_icon = QIcon("disconnected.png")
        self._connecting_icon = QIcon("connecting.png")
        self._connected_icon = QIcon("connected.png")

        self.tray_icon = QSystemTrayIcon(self._disconnected_icon, self.app)

        self.tray_icon.setContextMenu(self.generate_menu(self.app))
        self.tray_icon.show()

        self.tailscale = TailscaleWrapper(self.on_connecting, self.on_connected, self.on_disconnected)
        sys.exit(self.app.exec())

    # noinspection PyUnresolvedReferences
    def generate_menu(self, app: QApplication):
        result = QMenu()

        self._connect_action = QAction("Connect", app)
        self._connect_action.triggered.connect(self.toggle_connection)
        result.addAction(self._connect_action)

        self._status_action = QAction("Status", app)
        self._status_action.triggered.connect(self.show_status)
        result.addAction(self._status_action)

        result.addSeparator()
        exit_action = QAction("Exit", app)
        exit_action.triggered.connect(app.quit)
        result.addAction(exit_action)

        return result

    def toggle_connection(self):
        if self._connect_action.text() == "Connect":
            self.tailscale.bring_up_tailscale()
        else:
            self.tailscale.take_down_tailscale()

    def show_status(self):
        self.tailscale.show_web()

    def on_connecting(self):
        self._connect_action.setEnabled(False)
        self._connect_action.setText("Connecting...")
        self.tray_icon.setIcon(self._connecting_icon)

    def on_connected(self):
        self._connect_action.setEnabled(True)
        self._connect_action.setText("Disconnect")
        self.tray_icon.setIcon(self._connected_icon)

    def on_disconnected(self):
        self._connect_action.setEnabled(True)
        self._connect_action.setText("Connect")
        self.tray_icon.setIcon(self._disconnected_icon)

    def tray_icon_activated(self, reason: str):
        print(f"tray activated: {reason}")
        pass


if __name__ == "__main__":
    go_home()
    app = ScalyTail()

#!/bin/env python3
import shutil
import subprocess
from typing import Callable
import pathlib
import os
qt5_forced = os.getenv("FORCE_QT5")
if qt5_forced is None or qt5_forced == "0":
    force_qt5 = False
else:
    force_qt5 = True

try:
    if force_qt5:
        raise Exception("qt5 forced")
    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PyQt6.QtGui import QIcon, QAction
    from PyQt6.QtCore import pyqtSignal, QObject
    print("using qt6")

except:
    from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction
    from PyQt5.QtGui import QIcon
    from PyQt5.QtCore import pyqtSignal, QObject
    print("using qt5")

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
    io: list[str]
    exit_code: int | None

    def __init__(self, args: list[str], iocallback: Callable[[str], None] = None, suppress_output: bool = False):
        self.exit_code = None
        self.io = []
        if not suppress_output:
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

    @staticmethod
    def exec(args: list[str]):
        proc = ProcessIO(args, suppress_output=True)
        if proc.exit_code == 0:
            return proc.io
        print(f"process launch fails: {args}")
        for line in proc.io:
            print(line)
        return None


class TailscaleWrapper(QObject):
    connecting = pyqtSignal()
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._watcher = Thread(target=self.poll, daemon=True, name="Monitor")
        self._watcher.start()

    def poll(self):
        is_up = False
        if self.tailscale_is_up():
            is_up = True
            self.connected.emit()
        else:
            self.disconnected.emit()
        while True:
            current = self.tailscale_is_up()
            if is_up != current:
                if current:
                    self.connected.emit()
                else:
                    self.disconnected.emit()
            is_up = current
            sleep(5)

    @staticmethod
    def tailscale_is_up() -> bool:
        proc = ProcessIO(["tailscale", "status"], suppress_output=True)
        return proc.exit_code == 0

    def take_down_tailscale(self) -> None:
        self._run_bg(self.take_down_tailscale_bg)

    @staticmethod
    def _run_bg(target: Callable[[], None]):
        thread = Thread(target=target, daemon=True)
        thread.start()

    def take_down_tailscale_bg(self) -> None:
        ProcessIO(["tailscale", "down"])
        self.disconnected.emit()

    def bring_up_tailscale(self) -> None:
        self.connecting.emit()
        self._run_bg(self.bring_up_tailscale_bg)

    def bring_up_tailscale_bg(self) -> None:
        user = os.getenv("USER", "")
        args = ["tailscale", "up"]
        if user != "":
            args.append(f"--operator={user}")
        args.append("--accept-routes")
        proc = ProcessIO(args, lambda line: self._process_line(line))
        if proc.exit_code == 0:
            self.connected.emit()
        else:
            self.disconnected.emit()

    def show_web(self):
        self._run_bg(self.show_web_bg)

    def show_web_bg(self):
        proc = ProcessIO(["tailscale", "web"])
        fallback = ""
        for line in proc.io:
            if "starting tailscaled web client" in line:
                parts = line.split(" ")
                print(parts)
                print(parts[-1])
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


class ScalyTail(QObject):
    updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._status_action = None
        self._connect_action = None
        self._about_action = None
        self._changelog_action = None
        self.updater = Updater()

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("ScalyTail")
        self.app.setApplicationDisplayName("Scaly Tail")
        self.app.setDesktopFileName("scalytail")

        self._disconnected_icon = QIcon("disconnected.png")
        self._connecting_icon = QIcon("connecting.png")
        self._connected_icon = QIcon("connected.png")

        self.app.setWindowIcon(self._disconnected_icon)

        self.tray_icon = QSystemTrayIcon(self._disconnected_icon, self.app)

        self.tray_icon.setContextMenu(self.generate_menu(self.app))
        self.tray_icon.activated.connect(self.clicked)
        self.tray_icon.show()

        self.tailscale = TailscaleWrapper()
        self.tailscale.connecting.connect(self.on_connecting)
        self.tailscale.connected.connect(self.on_connected)
        self.tailscale.disconnected.connect(self.on_disconnected)
        self.attempt_auto_update()
        sys.exit(self.app.exec())

    def clicked(self):
        self.tailscale.show_web()

    @staticmethod
    def _run_bg(target: Callable[[], None]):
        thread = Thread(target=target, daemon=True)
        thread.start()

    def attempt_auto_update(self):
        self.updated.connect(self.show_updated_message)
        self._run_bg(self.attempt_auto_update_bg)

    def attempt_auto_update_bg(self):
        if self.updater.auto_update():
            self.updated.emit()

    def show_updated_message(self):
        self.tray_icon.showMessage(
            "ScalyTail has been updated!",
            "Please restart to run the latest version. You may view the changelog via the tray icon menu."
        )

    def open_commits_page(self):
        print("should open commits page")
        ProcessIO.open("https://github.com/fluffynuts/commits")

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
        self._about_action = QAction("About", app)
        self._about_action.triggered.connect(self.show_about)
        result.addAction(self._about_action)

        self._changelog_action = QAction("Changelog", app)
        self._changelog_action.triggered.connect(self.show_changelog)
        result.addAction(self._changelog_action)

        result.addSeparator()
        exit_action = QAction("Exit", app)
        exit_action.triggered.connect(app.quit)
        result.addAction(exit_action)

        return result

    def show_changelog(self):
        ProcessIO.open("https://github.com/fluffynuts/scalytail/commits")

    def toggle_connection(self):
        if self._connect_action.text() == "Connect":
            self.tailscale.bring_up_tailscale()
        else:
            self.tailscale.take_down_tailscale()

    def show_status(self):
        self.tailscale.show_web()

    def show_about(self):
        ProcessIO.open("https://github.com/fluffynuts/scalytail")

    @staticmethod
    def is_logged_out():
        proc = ProcessIO(["tailscale", "status"])
        for line in proc.io:
            lower_line = line.lower()
            if "logged out" in lower_line:
                return True
        return False

    def on_connecting(self):
        self._connect_action.setEnabled(False)
        self._connect_action.setText("Connecting...")
        message = "Bringing tailscale up..."
        if self.is_logged_out():
            message +=  """
                        Please wait for the login page to open in your browser
                        """
        self.tray_icon.showMessage("Connecting...", message, icon= QSystemTrayIcon.MessageIcon.Information)
        self.set_icon(self._connecting_icon)

    def on_connected(self):
        self._connect_action.setEnabled(True)
        self._connect_action.setText("Disconnect")
        self.set_icon(self._connected_icon)

    def on_disconnected(self):
        self._connect_action.setEnabled(True)
        self._connect_action.setText("Connect")
        self.set_icon(self._disconnected_icon)

    def set_icon(self, icon: QIcon):
        self.app.setWindowIcon(icon)
        self.tray_icon.setIcon(icon)


def write_pid_file(pidfile):
    with open(pidfile, "w") as fp:
        pid = str(os.getpid())
        print(f"writing pidfile with pid {pid}")
        fp.write(pid)


def is_already_running():
    print(f"my pid: {os.getpid()}")
    pidfile = "/tmp/scalytail.pid"
    if not os.path.exists(pidfile):
        print("pidfile not found")
        write_pid_file(pidfile)
        return False
    with open(pidfile, "r") as fp:
        existing_pid = int(fp.read().strip())
        print(f"pidfile found with pid {existing_pid}")
        try:
            os.kill(existing_pid, 0)
            print("kill-0 success")
            print("ScalyTail is already running")
            return True
        except ProcessLookupError as e:
            print(f"kill-0 fails: {e}")
            write_pid_file(pidfile)
            return False

def install_application_menu_item_if_necessary():
    if sys.platform == "win32" or sys.platform == "darwin":
        print("warning: no menu shortcut will be created - only supported on linux for now")
        return
    home = pathlib.Path.home()
    target = os.path.join(home, ".local", "share", "applications", "scalytail.desktop")
    if os.path.isfile(target):
        print(f".desktop file already found at: {target}")
        return
    my_dir = str(pathlib.Path(__file__).resolve().parent)
    source = os.path.join(my_dir, "scalytail.desktop")
    if not os.path.isfile(source):
        print(f"warning: unable to install desktop file: not found at '{source}'");
        return
    with open(source, "r", encoding="utf-8") as fp:
        source_lines = fp.read().splitlines()

    with open(target, "w", encoding="utf-8", newline=None) as fp:
        for line in source_lines:
            to_write = line.replace("$INSTALL_PATH$", my_dir)
            fp.write(f"{to_write}\n")
    print(f"installed desktop file at: {target}")

class Updater:
    def __init__(self):
        self.changelog = None

    @staticmethod
    def env_flag(name: str) -> bool:
        value = os.getenv(name)
        if value is None:
            return False
        lvalue = value.lower()
        return lvalue in ["1", "yes", "enabled", "true" ]

    @staticmethod
    def read_current_sha() -> str | None:
        output = ProcessIO.exec(["git", "rev-parse", "HEAD"])
        if output is None:
            return None
        return output[0]

    def pull_and_rebase(self) -> bool:
        proc = ProcessIO(["git", "pull", "--rebase"]);
        if proc.exit_code != 0:
            print("WARNING: unable to self-update via git pull --rebase")
        return proc.exit_code == 0

    def auto_update(self) -> bool:
        allowed_on_env = self.env_flag("SCALYTAIL_AUTOUPDATE")
        allowed_on_cli = "--auto-update" in sys.argv
        allowed = allowed_on_env or allowed_on_cli
        if not allowed:
            return False
        if shutil.which("git") is None:
            return False
        before_sha = self.read_current_sha()
        if not self.pull_and_rebase():
            return False
        after_sha = self.read_current_sha()
        self.changelog = self.read_changelog(before_sha, after_sha)
        print(f"changelog:\n{self.changelog}")
        return before_sha != after_sha

    @staticmethod
    def read_changelog(before_sha, after_sha) -> str:
        lines = ProcessIO.exec([
            "git",
            "log",
            f"{before_sha}..{after_sha}",
            "--pretty=format:\"%an <%ae> %s\""
        ])
        return "\n".join(lines)

if __name__ == "__main__":
    install_application_menu_item_if_necessary()
    if is_already_running():
        sys.exit(1)
    else:
        go_home()
        app = ScalyTail()

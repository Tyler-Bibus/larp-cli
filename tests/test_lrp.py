"""Behavior checks, including real terminal lifecycle and Bash round trips."""

import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

from lrp.app import clip, width, wrap
from lrp.state import Store, clean

ROOT = Path(__file__).resolve().parents[1]


class Terminal:
    def __init__(self, directory, rows=40, cols=120, options=()):
        self.master, self.slave = pty.openpty()
        self.original = termios.tcgetattr(self.slave)
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        env = dict(os.environ, TERM="xterm-256color", LC_ALL="C.UTF-8",
                   XDG_DATA_HOME=str(directory), HOME=str(directory))
        env.pop("LINES", None)
        env.pop("COLUMNS", None)

        def session():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        self.process = subprocess.Popen([sys.executable, "-m", "lrp", "--no-boot", *options],
                                        cwd=ROOT, env=env, stdin=self.slave, stdout=self.slave,
                                        stderr=self.slave, preexec_fn=session)
        self.output = b""
        self.read_until(b"CONNECTED TO ABSOLUTELY NOTHING")

    def read(self, duration=.15):
        deadline = time.monotonic() + duration
        chunk = b""
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], max(0, deadline - time.monotonic()))[0]:
                try:
                    part = os.read(self.master, 65536)
                except OSError:
                    break
                chunk += part
        self.output += chunk
        return chunk

    def read_until(self, marker, timeout=4):
        chunk = b""
        deadline = time.monotonic() + timeout
        while marker not in chunk and time.monotonic() < deadline:
            chunk += self.read(.05)
            if self.process.poll() is not None:
                break
        if marker not in chunk:
            raise AssertionError(f"Missing {marker!r}: {chunk[-2000:]!r}")
        return chunk

    def send(self, text):
        os.write(self.master, text.encode())
        return self.read()

    def resize(self, rows, cols):
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.process.send_signal(signal.SIGWINCH)
        return self.read(.2)

    def finish(self, key="q"):
        self.send(key)
        self.process.wait(timeout=4)
        self.read(.05)
        return termios.tcgetattr(self.slave)

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=3)
        os.close(self.master)
        os.close(self.slave)


class StorageTests(unittest.TestCase):
    def test_unicode_notes_roundtrip_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested/state.json"
            store = Store(path)
            store.data["notes"].append({"time": "2026-09-25", "text": "lore: café 日本語 🛸"})
            self.assertTrue(store.save())
            self.assertEqual(Store(path).data, store.data)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(path.parent.glob(".state-*")), [])

    def test_corrupted_data_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            for content in ("{broken", "[]", '{"notes": [3]}', '{"aura": "bad"}'):
                path.write_text(content)
                store = Store(path)
                self.assertTrue(store.blocked)
                self.assertFalse(store.save())
                self.assertEqual(path.read_text(), content)

    def test_unicode_and_terminal_control_sanitization(self):
        self.assertNotIn("\x1b", clean("\x1b[31mhello\n"))
        self.assertEqual(width("日本A"), 5)
        self.assertEqual(clip("日本A", 3), "日")
        for line in wrap("日本語 mixed words andaverylongword" * 2, 12):
            self.assertLessEqual(width(line), 12)


class TerminalTests(unittest.TestCase):
    def launch(self, directory, **kwargs):
        terminal = Terminal(directory, **kwargs)
        self.addCleanup(terminal.close)
        return terminal

    def test_actions_notes_editing_resize_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            t = self.launch(directory)
            state = Path(directory) / "lrp/state.json"
            t.send(":alias NIGHTSHIFT\n")
            t.send("nremember the café 日本語\n")
            data = json.loads(state.read_text())
            self.assertEqual(data["callsign"], "NIGHTSHIFT")
            self.assertEqual(data["notes"][-1]["text"], "remember the café 日本語")
            t.send(":note abc")
            t.send("\x1bODX\n")  # Application-cursor Left: abXc.
            self.assertEqual(json.loads(state.read_text())["notes"][-1]["text"], "abXc")
            t.send("p")
            t.send("g")
            t.send("a")
            t.send("m")
            self.assertTrue(json.loads(state.read_text())["calm"])
            for key in ("1", "2", "3", "4", "5", "\t", "?", " "):
                t.send(key)
            small = t.resize(12, 35)
            self.assertIn(b"TOO SMALL", small)
            t.resize(24, 64)
            t.send("1")
            t.resize(48, 160)
            t.send("4")
            t.send(":not-a-command\n")
            restored = t.finish()
            self.assertEqual(t.process.returncode, 0, t.output[-2000:])
            self.assertEqual(restored, t.original)
            self.assertNotIn(b"Traceback", t.output)
            self.assertIn(b"\x1b[?1049l", t.output)  # Alternate screen restored.

    def test_real_bash_roundtrip_and_ctrl_c(self):
        with tempfile.TemporaryDirectory() as directory:
            t = self.launch(directory)
            t.send("b")
            shell_output = t.send("printf 'REAL_SHELL_%s\\n' \"$LRP_SESSION\"\n")
            self.assertIn(b"REAL_SHELL_1", shell_output)
            t.send("sleep 30\n")
            t.send("\x03")
            t.send("exit\n")
            t.read(.3)
            self.assertIsNone(t.process.poll())
            self.assertIn(b"Reality link restored", t.output)
            self.assertEqual(t.finish(), t.original)
            self.assertEqual(t.process.returncode, 0)

    def test_signal_and_ascii_exit_restore_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            for termination in ("interrupt", "terminate"):
                with self.subTest(termination=termination):
                    t = self.launch(directory, rows=24, cols=80, options=("--ascii", "--calm"))
                    if termination == "interrupt":
                        restored = t.finish("\x03")
                    else:
                        t.process.terminate()
                        t.process.wait(timeout=4)
                        restored = termios.tcgetattr(t.slave)
                    self.assertEqual(restored, t.original)
                    self.assertEqual(t.process.returncode, 0)

    def test_redirected_launch_gives_actionable_error(self):
        result = subprocess.run([sys.executable, "-m", "lrp"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Open Konsole", result.stderr)


class InstallerTests(unittest.TestCase):
    def test_install_repeat_collision_and_uninstall(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, HOME=directory, PATH="/usr/bin:/bin")
            launcher = Path(directory) / ".local/bin/lrp"

            def installer(*args):
                return subprocess.run([sys.executable, "install.py", *args], cwd=ROOT,
                                      env=env, capture_output=True, text=True)

            self.assertEqual(installer().returncode, 0)
            self.assertEqual(launcher.resolve(), ROOT / "bin/lrp")
            self.assertEqual(installer().returncode, 0)
            version = subprocess.run([str(launcher), "--version"], env=env, capture_output=True, text=True)
            self.assertEqual(version.stdout.strip(), "lrp 1.0.0")
            self.assertEqual(installer("--uninstall").returncode, 0)
            self.assertFalse(launcher.exists())
            launcher.write_text("existing unrelated command")
            self.assertEqual(installer().returncode, 1)
            self.assertEqual(launcher.read_text(), "existing unrelated command")


if __name__ == "__main__":
    unittest.main()

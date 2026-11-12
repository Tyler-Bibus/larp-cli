"""Behavior checks, including real terminal lifecycle and Bash round trips."""

import fcntl
import json
import os
from pathlib import Path
import pty
import random
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lrp import __version__
from lrp.arcade import FlyDoom
from lrp.bureau import Bureau
from lrp.app import Console, clip, width, wrap
from lrp.creatures import project_brain
from lrp.motion import tesseract
from lrp.search import GraphSearch, SearchPanels
from lrp.state import Store, clean

ROOT = Path(__file__).resolve().parents[1]


class Terminal:
    def __init__(self, directory, rows=40, cols=120, options=(), launcher=None):
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

        command = [str(launcher)] if launcher else [sys.executable, "-m", "lrp"]
        self.process = subprocess.Popen([*command, "--no-boot", *options],
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

    def test_graph_autoplay_and_compact_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            t = self.launch(directory, options=("--ascii",))
            self.assertIn(b"OVERTHINK ACCELERATOR", t.output)
            t.read(1.8)
            t.send(" ")  # Freeze the running cascade for a full redraw.
            t.send("\x0c")
            self.assertIn(b"CYCLE 0002", t.output)
            for old_control in (b"[s] BFS/DFS", b"new tree", b"[e] step"):
                self.assertNotIn(old_control, t.output)
            t.resize(24, 64)
            t.send("\x0c")
            self.assertIn(b"RECONSTRUCTING INTENT", t.output)
            t.send("6")
            t.send("s")  # Fly stimulus retains its existing shortcut.
            t.send("\x0c")
            self.assertIn(b"Banana signal delivered", t.output)
            self.assertEqual(t.finish(), t.original)
            self.assertEqual(t.process.returncode, 0)
            self.assertNotIn(b"Traceback", t.output)

    def test_visible_pause_controls_and_kitty_in_live_and_compact_layouts(self):
        with tempfile.TemporaryDirectory() as directory:
            for rows, cols in ((40, 120), (24, 64)):
                with self.subTest(rows=rows, cols=cols):
                    t = self.launch(directory, rows=rows, cols=cols, options=("--ascii",))
                    t.send("k")
                    self.assertIn(b"LIVE SIM / PAUSE", t.send("\x0c"))
                    # Status control occupies the right-hand side of row 3.
                    click = f"\x1b[<0;{cols - 3};3M\x1b[<0;{cols - 3};3m"
                    t.send(click)
                    self.assertIn(b"FROZEN / RESUME", t.send("\x0c"))
                    t.send("f")  # A static overlay must not block the resume button.
                    t.send(click)
                    self.assertIn(b"LIVE SIM / PAUSE", t.send("\x0c"))
                    t.send("f")
                    t.send("m")
                    self.assertIn(b"CALM / RESUME", t.send("\x0c"))
                    t.send(click)
                    self.assertIn(b"LIVE SIM / PAUSE", t.send("\x0c"))
                    state = Path(directory) / "lrp/state.json"
                    self.assertFalse(json.loads(state.read_text())["calm"])
                    t.send(":")
                    # Force a redraw through resize while the editor is open.
                    t.resize(rows + 1, cols)
                    self.assertIn(b"INPUT / Esc cancel", t.output)
                    t.send("\x1b")
                    self.assertIn(b"LIVE SIM / PAUSE", t.send("\x0c"))
                    self.assertEqual(t.finish(), t.original)
                    self.assertEqual(t.process.returncode, 0)
                    self.assertNotIn(b"Traceback", t.output)

    def test_flylab_keyboard_mouse_brofist_and_compact_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            t = self.launch(directory, options=("--calm",))
            state = Path(directory) / "lrp/state.json"
            self.assertIn(b"MOCK CONNECTOME", t.send("6"))
            t.send("s")
            self.assertIn(b"Banana signal delivered", t.output)
            before = json.loads(state.read_text())["aura"]
            t.send("f")
            self.assertEqual(json.loads(state.read_text())["aura"], before + 67)
            self.assertIn(b"BROFIST PROTOCOL", t.output)
            t.send("f")  # Dismissal must not award a second bump.
            self.assertEqual(json.loads(state.read_text())["aura"], before + 67)
            t.send("\x1b[<0;4;39M")  # Click the footer button in an xterm-compatible terminal.
            self.assertEqual(json.loads(state.read_text())["aura"], before + 134)
            t.send("\x1b")
            t.resize(24, 64)
            t.send(":brofist\n")
            t.send("\x1b")
            t.send("nfly friend fff\n")
            self.assertEqual(json.loads(state.read_text())["notes"][-1]["text"], "fly friend fff")
            self.assertEqual(json.loads(state.read_text())["aura"], before + 201)
            self.assertEqual(t.finish(), t.original)
            self.assertEqual(t.process.returncode, 0)
            self.assertNotIn(b"Traceback", t.output)

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

    def test_doom_button_swaps_fly_pane_and_kitty_can_be_petted(self):
        with tempfile.TemporaryDirectory() as directory:
            t = self.launch(directory, options=("--calm",))
            t.send("6")
            t.send("\x1b[<0;42;35M")  # PLAY DOOM button.
            self.assertIn(b"autoplay engaged", t.output)
            self.assertIn(b"FLY DOOM / MOCK", t.output)
            t.send("k")
            self.assertIn(b"emotional support human", t.output)
            self.assertIn(b"Experiments shut down", t.output)
            t.send("d")  # Kitty shut down Doom; restart it, then return the fly.
            t.send("d")
            t.send("\x0c")  # Curses may retain the F from FLY DOOM between redraws.
            self.assertIn(b"Fly returned to its enclosure", t.output)
            t.resize(24, 64)
            t.send(":doom\n")
            t.send("k")
            t.send("d")
            self.assertEqual(t.finish(), t.original)
            self.assertEqual(t.process.returncode, 0)
            self.assertNotIn(b"Traceback", t.output)

    def test_redirected_launch_gives_actionable_error(self):
        result = subprocess.run([sys.executable, "-m", "lrp"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Open Konsole", result.stderr)

    def test_operations_commands_mouse_receipts_and_case_steps_in_calm_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            t = self.launch(directory, options=("--calm", "--ascii"))
            state = Path(directory) / "lrp/state.json"
            t.send("7")
            self.assertIn(b"OVERFUNDED AGENCY", t.output)
            t.send("\x1b[<0;24;10M")  # Aura audit experiment button.
            self.assertEqual(json.loads(state.read_text())["audits"], 1)
            t.send(":swarm\n")
            self.assertEqual(json.loads(state.read_text())["agents"], 80)
            for cmd in ("lockin", "breach", "breach", "overthink sounds good", "nonchalance"):
                t.send(":" + cmd + "\n")
            t.send("\x0c")
            self.assertIn(b"checking whether anyone noticed", t.output)
            t.send(":incident\n")
            t.send(":incident next\n")
            t.send("\x0c")
            self.assertIn(b"message contains 'quick question'", t.output)
            self.assertEqual(json.loads(state.read_text())["cases"], 1)
            t.send("p")
            t.send("k")
            t.send("7")
            t.send("\x0c")
            self.assertIn(b"EMERGENCY SHUTDOWN AUTHORIZED BY KITTY", t.output)
            t.resize(24, 64)
            t.send(":audit\n")
            t.send("\x1bOB")
            t.send("\x0c")
            self.assertIn(b"BROFIST CHARITY CREDIT", t.output)
            t.send("\x1bOA")
            self.assertEqual(t.finish(), t.original)
            self.assertEqual(t.process.returncode, 0)
            self.assertNotIn(b"Traceback", t.output)

    def test_banana_promotions_survive_restart_without_losing_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            t = self.launch(directory, options=("--calm",))
            t.send(":note preserve the main quest\n")
            t.send("6")
            for _ in range(9):
                t.send("s")
            t.send("\x0c")
            self.assertIn(b"INTERIM CTO", t.output)
            t.finish()
            again = self.launch(directory, options=("--calm",))
            again.send("6")
            self.assertIn(b"INTERIM CTO", again.output)
            data = json.loads((Path(directory) / "lrp/state.json").read_text())
            self.assertEqual(data["bananas"], 9)
            self.assertEqual(data["notes"][-1]["text"], "preserve the main quest")
            self.assertEqual(again.finish(), again.original)


class InstallerTests(unittest.TestCase):
    def test_standalone_build_runs_the_operations_screen(self):
        built = subprocess.run([sys.executable, "build.py"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        archive = ROOT / "dist/lrp"
        version = subprocess.run([str(archive), "--version"], cwd="/tmp", capture_output=True, text=True)
        self.assertEqual(version.stdout.strip(), "lrp " + __version__)
        redirected = subprocess.run([str(archive)], cwd="/tmp", capture_output=True, text=True)
        self.assertEqual(redirected.returncode, 1)
        self.assertIn("Open Konsole", redirected.stderr)
        with tempfile.TemporaryDirectory() as directory:
            t = Terminal(directory, launcher=archive, options=("--calm",))
            self.addCleanup(t.close)
            t.send(":lockin\n")
            t.send("\x0c")
            self.assertIn(b"NEW PARTICLE", t.output)
            self.assertEqual(t.finish(), t.original)
            self.assertEqual(t.process.returncode, 0)

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
            self.assertEqual(version.stdout.strip(), "lrp " + __version__)
            self.assertEqual(installer("--uninstall").returncode, 0)
            self.assertFalse(launcher.exists())
            launcher.write_text("existing unrelated command")
            self.assertEqual(installer().returncode, 1)
            self.assertEqual(launcher.read_text(), "existing unrelated command")


class PauseTests(unittest.TestCase):
    def make_console(self, calm=False):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "state.json")
            store.save = Mock(return_value=True)
            args = SimpleNamespace(calm=calm, ascii=True, no_boot=True)
            with patch.object(Console, "setup"):
                app = Console(Mock(), args, store)
        return app

    def test_kitty_contains_experiments_without_freezing_animation(self):
        app = self.make_console()
        app.command("panic")
        app.command("breach")
        app.command("incident")
        app.command("nonchalance")
        app.doom_enabled = True
        app.command("kitty")
        self.assertFalse(app.paused)
        self.assertFalse(app.panic)
        self.assertFalse(app.doom_enabled)
        self.assertFalse(app.bureau.case_active)
        self.assertFalse(app.bureau.storage_open)
        self.assertFalse(app.bureau.nonchalant)
        before = app.fx_time
        with patch("lrp.app.time.monotonic", return_value=app.last_frame + .10):
            app.update()
        self.assertGreater(app.fx_time, before)
        self.assertGreater(app.search.time, 0)

    def test_kitty_preserves_an_explicit_pause_or_calm_mode(self):
        for flag in ("paused", "calm"):
            with self.subTest(flag=flag):
                app = self.make_console()
                setattr(app, flag, True)
                app.command("kitty")
                self.assertTrue(getattr(app, flag))
                with patch("lrp.app.time.monotonic", return_value=app.last_frame + .05):
                    app.update()
                self.assertEqual(app.fx_time, 0)

    def test_space_resumes_every_combination_of_pause_and_calm(self):
        for paused, calm in ((True, False), (False, True), (True, True)):
            with self.subTest(paused=paused, calm=calm):
                app = self.make_console(calm=calm)
                app.paused = paused
                app.store.data["calm"] = calm
                app.key(" ")
                self.assertFalse(app.paused)
                self.assertFalse(app.calm)
                self.assertFalse(app.store.data["calm"])
                before = app.fx_time
                with patch("lrp.app.time.monotonic", return_value=app.last_frame + .05):
                    app.update()
                self.assertGreater(app.fx_time, before)
                if calm:
                    app.store.save.assert_called()
                app.key(" ")
                self.assertTrue(app.paused)

    def test_resume_is_idempotent(self):
        app = self.make_console(calm=True)
        app.paused = True
        for _ in range(2):
            app.command("resume")
            self.assertFalse(app.paused)
            self.assertFalse(app.calm)


class AnimationTests(unittest.TestCase):
    def test_autoplay_scene_moves_and_fly_portrait_has_four_expressions(self):
        game = FlyDoom()
        original = game.scene(43, 17)
        expressions = set()
        for moment in (0, .7, 2.2, 4.2):
            game.time = moment
            expressions.add(game.expression)
            self.assertTrue(0 < game.health <= 100)
        self.assertEqual(expressions, {"LOCKED IN", "PEW PEW", "OUCH", "RIP & BUZZ"})
        self.assertNotEqual(game.scene(43, 17), original)
        game.advance(10)
        self.assertGreater(game.kills, 0)
        for columns, rows in ((22, 3), (43, 17), (80, 30)):
            scene = game.scene(columns, rows)
            self.assertEqual(len(scene), rows)
            self.assertTrue(all(len(line) == columns for line in scene))

    def test_mock_brain_projection_stays_inside_both_layouts(self):
        for columns, rows in ((32, 3), (66, 24)):
            before, _ = project_brain(0, columns, rows)
            after, _ = project_brain(4, columns, rows)
            self.assertNotEqual(before, after)
            self.assertEqual(len(before), 120)
            self.assertTrue(all(0 <= x < columns and 0 <= y < rows for x, y in before + after))

    def test_pause_calm_and_input_freeze_then_resume_without_jump(self):
        app = Console.__new__(Console)
        app.last_frame = app.last_host = app.last_tick = app.last_feed = 100.0
        app.fx_time = 0.0
        app.paused = app.calm = app.editing = app.panic = False
        app.phase, app.threat, app.cope = 0, 86, 34
        app.trace = deque(maxlen=120)
        app.log = lambda *args: None
        app.read_host = lambda: {}
        app.view, app.offset = 5, 0
        app.doom_enabled = True
        app.doom = FlyDoom()
        app.search = GraphSearch(random.Random(1))
        app.bureau = Bureau({"agents": 64, "cases": 0})
        app.store = SimpleNamespace(data=app.bureau.data)
        with patch("lrp.app.time.monotonic", return_value=100.05):
            app.update()
        self.assertGreater(app.fx_time, 0)
        for flag, now in (("paused", 101), ("calm", 102), ("editing", 103)):
            before = app.fx_time
            game_before = app.doom.time
            bureau_before = app.bureau.time
            setattr(app, flag, True)
            with patch("lrp.app.time.monotonic", return_value=now):
                app.update()
            self.assertEqual(app.fx_time, before)
            self.assertEqual(app.doom.time, game_before)
            self.assertEqual(app.bureau.time, bureau_before)
            setattr(app, flag, False)
        before = app.fx_time
        with patch("lrp.app.time.monotonic", return_value=103.05):
            app.update()
        self.assertAlmostEqual(app.fx_time - before, .05)
        self.assertAlmostEqual(app.doom.time, .1)
        app.view = 0
        game_before = app.doom.time
        app.panic = True
        before = app.fx_time
        with patch("lrp.app.time.monotonic", return_value=103.10):
            app.update()
        self.assertGreater(app.fx_time - before, .1)
        self.assertEqual(app.doom.time, game_before)

    def test_search_freezes_when_hidden_paused_calm_or_typing(self):
        app = Console.__new__(Console)
        app.last_frame = app.last_host = app.last_tick = app.last_feed = 100.0
        app.fx_time = 0.0
        app.paused = app.calm = app.editing = app.panic = False
        app.view, app.offset = 0, 0
        app.phase, app.threat, app.cope = 0, 86, 34
        app.trace = deque(maxlen=120)
        app.log = lambda *args: None
        app.read_host = lambda: {}
        app.search = GraphSearch(random.Random(1))
        app.bureau = Bureau({"agents": 64, "cases": 0})
        app.store = SimpleNamespace(data=app.bureau.data)
        now = 100.0
        for flag in ("paused", "calm", "editing", "hidden"):
            if flag == "hidden":
                app.view = 1
            else:
                setattr(app, flag, True)
            before = (app.search.elapsed, app.search.time, app.search.generation)
            for _ in range(10):
                now += .1
                with patch("lrp.app.time.monotonic", return_value=now):
                    app.update()
            self.assertEqual((app.search.elapsed, app.search.time, app.search.generation), before)
            if flag == "hidden":
                app.view = 0
            else:
                setattr(app, flag, False)
        for _ in range(6):
            now += .1
            with patch("lrp.app.time.monotonic", return_value=now):
                app.update()
        self.assertGreaterEqual(len(app.search.visited), 10)
        self.assertEqual(app.search.visited[0], app.search.start)
        before = len(app.search.visited)
        app.panic = True
        now += .1
        with patch("lrp.app.time.monotonic", return_value=now):
            app.update()
        self.assertGreaterEqual(len(app.search.visited) - before, 3)

    def test_rotating_geometry_stays_inside_small_and_large_panels(self):
        for columns, rows in ((8, 3), (34, 5), (54, 24)):
            frames = []
            for seconds in (0, .5, 1.5, 20, 1000):
                points, edges = tesseract(seconds, columns, rows)
                frames.append(points)
                self.assertTrue(all(0 <= x < columns and 0 <= y < rows for x, y in points))
                self.assertEqual(len(edges), 32)
            self.assertNotEqual(frames[0], frames[2])


class SearchTests(unittest.TestCase):
    def test_cyclic_graphs_have_real_bfs_and_dfs_orders(self):
        shapes = set()
        for seed in range(30):
            search = GraphSearch(random.Random(seed))
            shapes.add(tuple(search.edges))
            self.assertTrue(22 <= len(search.nodes) <= 26)
            self.assertGreater(len(search.edges), len(search.nodes))
            self.assertTrue(all(a != b and a in search.neighbors[b] and b in search.neighbors[a]
                                for a, b in search.edges))
            bfs, queue, seen, distances = [], deque([search.start]), {search.start}, {search.start: 0}
            while queue:
                node = queue.popleft()
                bfs.append(node)
                for other in search.neighbors[node]:
                    if other not in seen:
                        seen.add(other)
                        distances[other] = distances[node] + 1
                        queue.append(other)
            dfs = []

            def visit(node):
                dfs.append(node)
                for other in search.neighbors[node]:
                    if other not in dfs:
                        visit(other)

            visit(search.start)
            for algorithm, expected in (("BFS", bfs), ("DFS", dfs)):
                search.restart(algorithm)
                for _ in search.nodes:
                    search.step()
                self.assertTrue(search.complete)
                self.assertEqual(search.visited, expected)
                self.assertEqual(set(search.visited), set(search.nodes))
                self.assertEqual(len(search.visited), len(set(search.visited)))
                for node, parent in search.parents.items():
                    if parent is not None:
                        self.assertIn(node, search.neighbors[parent])
                        if algorithm == "BFS":
                            self.assertEqual(distances[node], distances[parent] + 1)
                before = search.visited[:]
                search.step()
                self.assertEqual(search.visited, before)
            for columns, rows in ((54, 8), (58, 8), (74, 8), (100, 15)):
                points = search.positions(columns, rows)
                self.assertEqual(len(set(points.values())), len(search.nodes))
                self.assertTrue(all(1 <= x < columns - 1 and 0 <= y < rows for x, y in points.values()))
                for node, (x, y) in points.items():
                    self.assertTrue(all(y != oy or abs(x - ox) >= 4
                                        for other, (ox, oy) in points.items() if other != node))
        self.assertEqual(len(shapes), 30)

    def test_fast_autoplay_randomizes_and_preserves_frame_remainder(self):
        search = GraphSearch(random.Random(7))
        algorithms = {search.algorithm}
        for generation in range(1, 31):
            duration = len(search.nodes) * search.STEP_DELAY
            search.advance(duration + .001)
            self.assertTrue(search.complete)
            self.assertEqual(search.generation, generation)
            search.advance(search.RESET_DELAY)
            self.assertEqual(search.generation, generation + 1)
            self.assertAlmostEqual(search.elapsed, generation * .001)
            algorithms.add(search.algorithm)
        self.assertEqual(algorithms, {"BFS", "DFS"})
        a, b = GraphSearch(random.Random(9)), GraphSearch(random.Random(9))
        a.advance(3.17)
        for _ in range(317):
            b.advance(.01)
        self.assertEqual((a.generation, a.visited), (b.generation, b.visited))
        self.assertAlmostEqual(a.elapsed, b.elapsed)

    def test_graph_render_stays_inside_panel_and_freezes(self):
        panel = SearchPanels()
        panel.search = GraphSearch(random.Random(4))
        panel.box = lambda *args: None
        for height, columns in ((14, 56), (14, 62), (14, 78), (30, 104)):
            draws = []

            def put(y, x, text, style, max_width=None):
                self.assertTrue(1 <= y < height - 1)
                self.assertGreaterEqual(x, 1)
                self.assertLessEqual(x + min(len(text), max_width or len(text)), columns - 1)
                draws.append((y, x, text, style))

            panel.put = put
            panel.search.advance(.3)
            panel.search_panel(0, 0, height, columns)
            before = draws[:]
            draws.clear()
            panel.search_panel(0, 0, height, columns)
            self.assertEqual(draws, before)
            panel.search.advance(.1)
            draws.clear()
            panel.search_panel(0, 0, height, columns)
            self.assertNotEqual(draws, before)


if __name__ == "__main__":
    unittest.main()

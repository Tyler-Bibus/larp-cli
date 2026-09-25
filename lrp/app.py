"""A full-screen, dependency-free curses console for Konsole and friends."""

import argparse
from collections import deque
import curses
from datetime import datetime
import locale
import os
import platform
import random
import shutil
import signal
import subprocess
import sys
import time
import unicodedata

from . import __version__
from .content import FONT, HELP, TRANSMISSIONS
from .state import Store, clean, state_path


def width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in text)


def clip(text, limit):
    result = ""
    used = 0
    for char in clean(text):
        size = width(char)
        if used + size > limit:
            break
        result += char
        used += size
    return result


def wrap(text, limit):
    """Wrap even long unbroken notes, respecting terminal cell widths."""
    text = clean(text)
    limit = max(1, limit)
    result = []
    while text:
        line = clip(text, limit)
        if not line:
            line = text[0]
        if len(line) < len(text) and " " in line and len(line.rsplit(" ", 1)[0]) > len(line) // 2:
            line = line.rsplit(" ", 1)[0]
        result.append(line)
        text = text[len(line):].lstrip()
    return result or [""]


COMMANDS = ("help", "home", "feed", "dossier", "vault", "status", "panic", "contain",
            "aura", "grass", "pause", "calm", "note", "alias", "shell", "quit")
VIEWS = ("CONTROL", "WIRE", "DOSSIER", "VAULT", "MANUAL")


class Console:
    def __init__(self, screen, args, store):
        self.screen, self.args, self.store = screen, args, store
        self.running = True
        self.view = 0
        self.offset = 0
        self.paused = False
        self.calm = args.calm or store.data["calm"]
        self.ascii = args.ascii or "UTF" not in locale.getpreferredencoding(False).upper()
        self.started = time.monotonic()
        self.last_tick = self.started
        self.last_feed = self.started
        self.last_host = 0
        self.boot_until = self.started + (0 if args.no_boot or self.calm else 1.6)
        self.threat = 86
        self.cope = 34
        self.panic = False
        self.phase = 0
        self.logs = deque(maxlen=300)
        self.trace = deque([random.randrange(15, 90) for _ in range(120)], maxlen=120)
        self.message = "Reality link established. :help for commands."
        self.editing = False
        self.buffer = ""
        self.cursor = 0
        self.history = []
        self.history_pos = 0
        self.history_draft = ""
        self.host = {}
        self.setup()
        store.data["sessions"] += 1
        store.save()
        for tag, text in TRANSMISSIONS[:9]:
            self.log(tag, text)
        self.log("LOCAL", "Operator online. All threat traffic is simulated.")
        if store.error:
            self.message = store.error

    def setup(self):
        self.screen.keypad(True)
        self.screen.timeout(100)
        curses.set_escdelay(25)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.styles = {k: curses.A_NORMAL for k in ("mint", "red", "dim", "amber", "white", "bar", "alert", "soft")}
        if curses.has_colors():
            curses.start_color()
            if curses.COLORS >= 256:
                colors = [(121, 16), (197, 16), (66, 16), (221, 16), (195, 16),
                          (16, 121), (16, 197), (121, 23)]
            else:
                colors = [(2, 0), (1, 0), (6, 0), (3, 0), (7, 0), (0, 2), (7, 1), (2, 0)]
            for number, (name, pair) in enumerate(zip(self.styles, colors), 1):
                curses.init_pair(number, *pair)
                self.styles[name] = curses.color_pair(number)
        self.styles["red"] |= curses.A_BOLD
        self.styles["mint"] |= curses.A_BOLD
        self.styles["alert"] |= curses.A_BOLD
        self.screen.bkgd(" ", self.styles["mint"] & ~curses.A_BOLD)

    def put(self, y, x, text, style="mint", max_width=None):
        if not (0 <= y < self.h and 0 <= x < self.w):
            return
        limit = self.w - x - (1 if y == self.h - 1 else 0)
        if max_width is not None:
            limit = min(limit, max_width)
        if limit <= 0:
            return
        try:
            self.screen.addstr(y, x, clip(str(text), limit), self.styles[style])
        except curses.error:
            pass  # A resize can occur between measuring the window and writing.

    def fill(self, y, x, size, style="bar", text=""):
        self.put(y, x, " " * max(0, size), style)
        self.put(y, x, text, style, size)

    def center(self, y, text, style="mint", x=0, span=None):
        span = self.w if span is None else span
        self.put(y, x + max(0, (span - width(text)) // 2), text, style, span)

    def line(self, y, x, size, style="dim"):
        self.put(y, x, ("-" if self.ascii else "─") * max(0, size), style)

    def box(self, y, x, h, w, title, style="dim"):
        if h < 3 or w < 4:
            return
        a, b, c, d, v, hz = ("+", "+", "+", "+", "|", "-") if self.ascii else ("┌", "┐", "└", "┘", "│", "─")
        self.put(y, x, a + hz * (w - 2) + b, style)
        self.put(y + h - 1, x, c + hz * (w - 2) + d, style)
        for row in range(y + 1, y + h - 1):
            self.put(row, x, v, style)
            self.put(row, x + w - 1, v, style)
        self.put(y, x + 2, " " + title + " ", "mint", w - 4)

    def big(self, y, text, span, x=0):
        raster = [" ".join(FONT.get(c, FONT[" "])[row] for c in text) for row in range(5)]
        scale = 2 if len(raster[0]) * 2 <= span - 4 else 1
        size = len(raster[0]) * scale
        if size > span - 4:
            self.center(y + 2, text, "red", x, span)
            return
        left = x + (span - size) // 2
        block = "#" if self.ascii else "█"
        for row, pixels in enumerate(raster):
            self.put(y + row, left, "".join((block if p == "1" else " ") * scale for p in pixels), "red")

    def log(self, tag, text):
        self.logs.append((datetime.now().strftime("%H:%M:%S"), tag, clean(text)))

    def save(self):
        if not self.store.save():
            self.message = self.store.error

    def update(self):
        now = time.monotonic()
        if now - self.last_host >= 3:
            self.last_host = now
            self.host = self.read_host()
        if self.paused or self.calm or self.editing:
            self.last_tick = self.last_feed = now
            return
        if now - self.last_tick >= .55:
            self.phase += 1
            self.last_tick = now
            self.threat = max(5, min(99, self.threat + random.randint(-3, 4)))
            self.cope = max(1, min(100, self.cope + random.randint(-2, 2)))
            self.trace.append(random.randrange(20, 100) if self.panic else random.randrange(10, 85))
        if now - self.last_feed >= (1.1 if self.panic else 2.8):
            self.last_feed = now
            if self.view == 1 and self.offset:
                self.offset = min(len(self.logs), self.offset + 1)
            self.log(*random.choice(TRANSMISSIONS))

    @staticmethod
    def read_host():
        host = {"host": clean(platform.node()).split(".")[0], "kernel": platform.release(),
                "load": " / ".join(f"{n:.2f}" for n in os.getloadavg()), "memory": "unavailable",
                "uptime": "unavailable"}
        try:
            with open("/proc/meminfo") as stream:
                values = {line.split(":")[0]: int(line.split()[1]) for line in stream}
            total = values["MemTotal"] / 1048576
            used = (values["MemTotal"] - values["MemAvailable"]) / 1048576
            host["memory"] = f"{used:.1f} / {total:.1f} GiB"
            with open("/proc/uptime") as stream:
                uptime = int(float(stream.read().split()[0]))
            host["uptime"] = f"{uptime // 3600}h {uptime // 60 % 60:02d}m"
        except (OSError, ValueError, KeyError):
            pass
        return host

    def meter(self, y, x, size, label, value, style):
        self.put(y, x, label, "dim", size)
        self.put(y, x + max(0, size - 5), f"{value:3d}%", style)
        blocks = max(0, size - 2)
        count = round(blocks * value / 100)
        self.put(y + 1, x, "[" + ("#" if self.ascii else "━") * count + "·" * (blocks - count) + "]", style, size)

    def control(self):
        wide = self.w >= 108
        span = self.w - 33 if wide else self.w
        status = "CRITICAL" if self.panic else "COOKED" if self.threat >= 65 else "LOCKED IN"
        self.center(5, "REPORT ON TERMINAL AURA DISCHARGE", "mint", 0, span)
        self.center(6, "SUBJECT: YOU   /   CLASSIFICATION: EXTREMELY ONLINE", "dim", 0, span)
        self.box(8, 1, 7, span - 2, "REALITY STATUS / SIMULATED", "red")
        self.big(9, status, span - 2, 1)
        self.center(15, "POSSIBLE SIMILARITY WITH A SKILL ISSUE", "mint", 0, span)
        label = "CONTAINMENT FAILED" if self.panic else "RECALCULATING" if self.threat >= 65 else "WE ARE SO BACK"
        self.fill(17, 2, span - 4, "alert")
        self.center(17, "// " + label + " //", "alert", 2, span - 4)
        self.center(19, "[p] crashout / contain   [a] farm aura   [g] touch grass", "amber", 0, span)
        if wide:
            x, panel = span + 1, 31
            self.box(5, x, 16, panel, "HOST / REAL")
            for idx, (label, val) in enumerate((("OPERATOR", self.store.data["callsign"]),
                                                ("HOST", self.host.get("host", "")),
                                                ("MEMORY", self.host.get("memory", "")),
                                                ("LOAD / 1 5 15 MIN", self.host.get("load", "")),
                                                ("UPTIME", self.host.get("uptime", "")))):
                self.put(6 + idx * 2, x + 2, label, "dim", panel - 4)
                self.put(7 + idx * 2, x + 2, val, "white", panel - 4)
            self.put(17, x + 2, "[b] enter real Bash", "amber", panel - 4)
            self.put(19, x + 2, "NETWORK: OFFLINE BY DESIGN", "mint", panel - 4)
        bottom = self.h - 5
        if bottom < 24:
            return
        left = self.w * 2 // 3
        self.box(22, 1, bottom - 21, left - 2, "INTERCEPT / FICTIONAL WIRE")
        rows = max(0, bottom - 24)
        for row, (stamp, tag, message) in enumerate(list(self.logs)[-rows:] if rows else []):
            self.put(24 + row, 3, stamp, "dim", 8)
            self.put(24 + row, 12, f"{tag:5}", "red" if tag in ("WARN", "FAULT") else "amber", 5)
            self.put(24 + row, 18, message, "white", left - 21)
        x = left + 1
        self.box(22, x, bottom - 21, self.w - x - 1, "VIBE TELEMETRY / SIM")
        size = self.w - x - 5
        if bottom >= 26:
            self.meter(24, x + 2, size, "THREAT", self.threat, "red")
        if bottom >= 29:
            self.meter(27, x + 2, size, "COPE RESERVE", self.cope, "mint")
        if bottom >= 32:
            self.put(30, x + 2, f"AURA BALANCE  {self.store.data['aura']:+,}", "amber", size)
        if bottom >= 35:
            chars = "._-=+#" if self.ascii else "▁▂▃▄▅▆▇█"
            samples = list(self.trace)[-size:]
            self.put(33, x + 2, "".join(chars[min(len(chars) - 1, n * len(chars) // 100)] for n in samples), "red", size)
            self.put(34, x + 2, "A.T. FIELD / ABSOLUTE TERMINAL", "dim", size)

    def scroll_lines(self, rows):
        visible = max(1, self.h - 13)
        self.offset = max(0, min(self.offset, max(0, len(rows) - visible)))
        for i, (line, style) in enumerate(rows[self.offset:self.offset + visible]):
            self.put(9 + i, 4, line, style, self.w - 8)
        if len(rows) > visible:
            self.put(self.h - 5, 4, f"{self.offset + 1}-{min(self.offset + visible, len(rows))} / {len(rows)}   Up/Down to scroll", "dim")

    def page_title(self, title, subtitle):
        self.fill(5, 2, self.w - 4, "alert", "  " + title)
        self.put(7, 4, subtitle, "dim", self.w - 8)

    def wire(self):
        self.page_title("INTERCEPTED TRANSMISSIONS", "FICTIONAL TRAFFIC / NEWEST FIRST / Space freezes feed / Up, Down scroll")
        rows = []
        for stamp, tag, text in reversed(self.logs):
            lines = wrap(text, self.w - 25)
            rows.append((f"{stamp}  {tag:5}  {lines[0]}", "red" if tag in ("FAULT", "WARN") else "mint"))
            rows.extend((" " * 17 + line, "white") for line in lines[1:])
        self.scroll_lines(rows)

    def dossier(self):
        self.page_title("OPERATOR DOSSIER", "PERSONNEL FILE / STORED LOCALLY / :alias <name> to change callsign")
        data = self.store.data
        rows = [("CALLSIGN          " + data["callsign"], "mint"),
                ("DESIGNATION       FINAL BOSS OF BEING ON THE COMPUTER", "red"),
                ("CLEARANCE         TRUST ME BRO / LEVEL 07", "white"), ("", "dim"),
                (f"AURA BALANCE      {data['aura']:+,}", "amber"),
                (f"DEPLOYMENTS       {data['sessions']}", "white"),
                (f"ARCHIVED NOTES    {len(data['notes'])}", "white"),
                (f"CURRENT THREAT    {self.threat}% / FICTIONAL", "red"),
                (f"COPE RESERVE      {self.cope}% / FICTIONAL", "mint"), ("", "dim"),
                ("PSYCHOLOGICAL ASSESSMENT", "mint"),
                ("Insists the side quest is essential to the main quest.", "white"),
                ("Observed aura farming in an empty terminal.", "white"),
                ("Recommended intervention: [g] touch grass.", "amber"), ("", "dim"),
                ("ACTUAL MACHINE", "mint")]
        rows.extend((f"{key.upper():18}{value}", "white") for key, value in self.host.items())
        rows += [("", "dim"), ("LOCAL STORAGE", "mint")]
        rows += [(line, "dim") for line in wrap(str(self.store.path), self.w - 8)]
        rows += [("No account. No network. No one is receiving this dossier.", "dim")]
        self.scroll_lines(rows)

    def vault(self):
        self.page_title("LORE VAULT", "REAL LOCAL NOTES / [n] new entry / :note <text> / most recent 200 retained")
        rows = []
        if not self.store.data["notes"]:
            rows = [("NO LORE ON FILE.", "red"), ("", "dim"),
                    ("Even the most classified grocery list starts somewhere.", "white"),
                    ("Press n, type your note, then Enter to save.", "mint")]
        for note in reversed(self.store.data["notes"]):
            rows.append(("// " + note["time"], "amber"))
            rows.extend((line, "white") for line in wrap(note["text"], self.w - 10))
            rows.append(("", "dim"))
        self.scroll_lines(rows)

    def manual(self):
        self.page_title("FIELD MANUAL", "LRP / REALITY OPERATIONS DIVISION / v" + __version__)
        rows = []
        for key, text in HELP:
            lines = wrap(text, self.w - 35)
            rows.append((f"{key:25} {lines[0]}", "amber" if key in ("REAL", "COMMANDS") else "white"))
            rows.extend((" " * 26 + line, "white") for line in lines[1:])
        self.scroll_lines(rows)

    def draw(self):
        self.h, self.w = self.screen.getmaxyx()
        self.screen.erase()
        if self.h < 24 or self.w < 64:
            self.put(0, 0, "LRP // TERMINAL TOO SMALL", "red")
            self.put(2, 0, f"Need 64 x 24. Current: {self.w} x {self.h}.", "mint")
            self.put(4, 0, "Resize Konsole. q / Ctrl-C exits.", "amber")
            self.screen.refresh()
            return
        self.fill(0, 0, self.w, "bar", " LRP / REALITY OPERATIONS DIVISION")
        self.put(0, self.w - 22, datetime.now().strftime("%Y-%m-%d  %H:%M:%S"), "bar")
        self.put(1, 1, "EMERGENCY BROADCAST SYSTEM   //   REALITY IS A SKILL ISSUE", "red")
        self.put(2, 1, "LOCAL CONSOLE / FICTIONAL THREAT TRAFFIC", "dim")
        mode = "CALM" if self.calm else "FROZEN" if self.paused else "LIVE SIM"
        self.put(2, self.w - len(mode) - 2, mode, "amber")
        x = 1
        for i, name in enumerate(VIEWS):
            label = f" {i+1} {name} "
            self.put(3, x, label, "bar" if i == self.view else "dim")
            x += len(label) + 1
        (self.control, self.wire, self.dossier, self.vault, self.manual)[self.view]()
        self.line(self.h - 4, 1, self.w - 2)
        self.put(self.h - 3, 1, self.store.error or self.message, "red" if self.store.error else "amber", self.w - 2)
        if self.editing:
            self.fill(self.h - 2, 1, self.w - 2, "soft")
            self.put(self.h - 2, 1, " : ", "mint")
            # Scroll horizontally around the insertion point, measured in terminal cells.
            start = 0
            while width(self.buffer[start:self.cursor]) >= self.w - 7:
                start += 1
            self.put(self.h - 2, 4, self.buffer[start:], "white", self.w - 6)
            self.put(self.h - 1, 1, "Enter execute  Esc cancel  Tab complete  Up/Down history", "dim")
            try:
                curses.curs_set(1)
                self.screen.move(self.h - 2, 4 + width(self.buffer[start:self.cursor]))
            except curses.error:
                pass
        else:
            self.put(self.h - 2, 1, "[:] command  [b] Bash  [n] note  [Space] freeze  [?] help  [q] exit", "mint")
            self.put(self.h - 1, 1, "CONNECTED TO ABSOLUTELY NOTHING.   ALL PANIC IS LOCALLY SOURCED.", "dim")
            try:
                curses.curs_set(0)
            except curses.error:
                pass
        if time.monotonic() < self.boot_until:
            self.fill(17, 2, (self.w - 33 if self.w >= 108 else self.w) - 4, "alert")
            self.put(17, 4, "BOOT SEQUENCE / RESTORING YOUR UNFINISHED CHARACTER ARC", "alert", self.w - 40)
        self.screen.refresh()

    def change_view(self, view):
        self.view = view
        self.offset = 0

    def prompt(self, prefix=""):
        self.editing = True
        self.buffer = prefix
        self.cursor = len(prefix)
        self.history_pos = len(self.history)
        self.history_draft = prefix

    def command(self, raw):
        cmd, _, arg = raw.strip().partition(" ")
        cmd = cmd.lower()
        arg = clean(arg.strip())
        views = {"home": 0, "feed": 1, "dossier": 2, "vault": 3, "help": 4}
        if cmd in views:
            self.change_view(views[cmd])
            self.message = VIEWS[self.view] + " selected."
        elif cmd in ("quit", "exit", "q"):
            self.running = False
        elif cmd in ("panic", "contain"):
            self.panic = cmd == "panic"
            self.threat = 99 if self.panic else 43
            self.message = "CRASHOUT PROTOCOL ENGAGED. [p] to contain." if self.panic else "Contained. We are cautiously back."
            self.log("FAULT" if self.panic else "COPE", self.message)
            self.change_view(0)
        elif cmd == "aura":
            delta = random.choice([-400, -67, 67, 100, 200, 670])
            self.store.data["aura"] = max(-999999, min(999999, self.store.data["aura"] + delta))
            self.message = f"AURA {delta:+d}. " + ("The pose was witnessed." if delta > 0 else "They saw you trying. It's over.")
            self.log("AURA", self.message)
            self.save()
        elif cmd == "grass":
            self.threat, self.cope, self.panic = 12, 100, False
            self.message = "GRASS CONTACT CONFIRMED. The outside has accepted your request."
            self.log("COPE", self.message)
            self.change_view(0)
        elif cmd == "pause":
            self.paused = not self.paused
            self.message = "Simulation frozen. You can breathe." if self.paused else "Simulation resumed."
        elif cmd == "calm":
            self.calm = not self.calm
            self.store.data["calm"] = self.calm
            self.message = "Calm mode on. Automatic simulation updates stopped." if self.calm else "Calm mode off. The timeline is moving."
            self.save()
        elif cmd == "note":
            if not arg:
                self.prompt("note ")
                return
            self.store.data["notes"].append({"time": datetime.now().astimezone().isoformat(timespec="seconds"), "text": arg[:1000]})
            self.store.data["notes"] = self.store.data["notes"][-200:]
            self.message = "Lore archived locally."
            self.save()
            self.change_view(3)
        elif cmd == "alias":
            if not arg:
                self.message = "Usage: alias <your callsign>"
            else:
                self.store.data["callsign"] = arg[:24]
                self.message = "Callsign updated: " + self.store.data["callsign"]
                self.save()
        elif cmd == "shell":
            self.shell()
        elif cmd == "status":
            self.message = f"AURA {self.store.data['aura']:+,} / THREAT {self.threat}% / COPE {self.cope}% / FICTIONAL"
        elif cmd:
            self.message = f"Unknown directive: {cmd}. Use :help or press ?."

    def shell(self):
        curses.def_prog_mode()
        curses.endwin()
        try:
            print("\n\033[1;32mLRP // REAL BASH SESSION\033[0m")
            print("Commands here act on your machine. Type exit or Ctrl-D to return to LRP.\n", flush=True)
            env = dict(os.environ, LRP_SESSION="1")
            # A caught handler resets to default on exec; SIG_IGN would leak into
            # Bash and make programs launched from it immune to Ctrl-C.
            handler = signal.signal(signal.SIGINT, lambda signum, frame: None)
            try:
                result = subprocess.run([shutil.which("bash") or "/bin/bash", "-i"], env=env, check=False)
            finally:
                signal.signal(signal.SIGINT, handler)
            self.message = f"Returned from Bash (status {result.returncode}). Reality link restored."
        except OSError as exc:
            self.message = f"Could not open Bash: {exc}"
        finally:
            curses.reset_prog_mode()
            self.screen.keypad(True)
            self.screen.timeout(100)
            self.screen.clearok(True)
            self.screen.refresh()
            self.last_tick = self.last_feed = time.monotonic()

    def edit_key(self, key):
        if key == "\x1b":
            self.editing = False
        elif key in ("\n", "\r", curses.KEY_ENTER):
            raw = self.buffer.strip()
            self.editing = False
            if raw:
                self.history.append(raw)
                self.history = self.history[-100:]
                self.command(raw)
        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            if self.cursor:
                self.buffer = self.buffer[:self.cursor - 1] + self.buffer[self.cursor:]
                self.cursor -= 1
        elif key == curses.KEY_DC:
            self.buffer = self.buffer[:self.cursor] + self.buffer[self.cursor + 1:]
        elif key in (curses.KEY_LEFT, "\x02"):
            self.cursor = max(0, self.cursor - 1)
        elif key in (curses.KEY_RIGHT, "\x06"):
            self.cursor = min(len(self.buffer), self.cursor + 1)
        elif key in (curses.KEY_HOME, "\x01"):
            self.cursor = 0
        elif key in (curses.KEY_END, "\x05"):
            self.cursor = len(self.buffer)
        elif key == "\x15":
            self.buffer, self.cursor = "", 0
        elif key in (curses.KEY_UP, curses.KEY_DOWN):
            if self.history_pos == len(self.history):
                self.history_draft = self.buffer
            self.history_pos = max(0, min(len(self.history), self.history_pos + (-1 if key == curses.KEY_UP else 1)))
            self.buffer = self.history[self.history_pos] if self.history_pos < len(self.history) else self.history_draft
            self.cursor = len(self.buffer)
        elif key == "\t":
            matches = [c for c in COMMANDS if c.startswith(self.buffer)]
            if len(matches) == 1:
                self.buffer = matches[0] + " "
                self.cursor = len(self.buffer)
            else:
                self.message = " / ".join(matches) if matches else "No matching directive. :help lists commands."
        elif isinstance(key, str) and key.isprintable() and len(self.buffer) < 1024:
            self.buffer = self.buffer[:self.cursor] + key + self.buffer[self.cursor:]
            self.cursor += len(key)

    def key(self, key):
        if key in ("\x03", "\x04"):
            self.running = False
        elif key == curses.KEY_RESIZE:
            self.screen.clearok(True)
        elif self.editing:
            self.edit_key(key)
        elif key in ("q", "Q"):
            self.running = False
        elif isinstance(key, str) and key in "12345":
            self.change_view(int(key) - 1)
        elif key in ("\t", curses.KEY_BTAB):
            self.change_view((self.view + (-1 if key == curses.KEY_BTAB else 1)) % len(VIEWS))
        elif key in (":", "/"):
            self.prompt()
        elif key in ("?", curses.KEY_F1):
            self.change_view(4)
        elif key == "n":
            self.prompt("note ")
        elif key == "p":
            self.command("contain" if self.panic else "panic")
        elif key in ("a", "g", " ", "m", "b"):
            self.command({"a": "aura", "g": "grass", " ": "pause", "m": "calm", "b": "shell"}[key])
        elif key in (curses.KEY_DOWN, curses.KEY_UP, curses.KEY_NPAGE, curses.KEY_PPAGE):
            step = max(1, self.h - 14) if key in (curses.KEY_NPAGE, curses.KEY_PPAGE) else 1
            self.offset = max(0, self.offset + (step if key in (curses.KEY_DOWN, curses.KEY_NPAGE) else -step))
        elif key == curses.KEY_HOME:
            self.offset = 0
        elif key == "\x0c":
            self.screen.clearok(True)

    def run(self):
        while self.running:
            self.update()
            self.draw()
            try:
                key = self.screen.get_wch()
            except curses.error:
                continue
            self.key(key)


def main(argv=None):
    parser = argparse.ArgumentParser(description="LRP — full-screen reality operations for the terminally online.")
    parser.add_argument("--version", action="version", version="lrp " + __version__)
    parser.add_argument("--calm", action="store_true", help="start with automatic simulation updates disabled")
    parser.add_argument("--ascii", action="store_true", help="use ASCII borders and headline lettering")
    parser.add_argument("--no-boot", action="store_true", help="skip the short boot banner")
    parser.add_argument("--doctor", action="store_true", help="print terminal and install diagnostics")
    args = parser.parse_args(argv)
    locale.setlocale(locale.LC_ALL, "")
    if args.doctor:
        print(f"LRP {__version__}\nPython: {platform.python_version()}\nTerminal: {os.environ.get('TERM', '(unset)')}")
        print(f"Interactive terminal: {sys.stdin.isatty() and sys.stdout.isatty()}\nBash: {shutil.which('bash')}")
        print(f"State: {state_path()}\nRecommended: Konsole, 120 columns x 40 rows; minimum: 64 x 24")
        return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("LRP needs an interactive terminal. Open Konsole and run lrp.", file=sys.stderr)
        return 1
    if os.environ.get("TERM", "dumb") in ("", "dumb", "unknown"):
        print("LRP needs a capable terminal. In Konsole, try: TERM=xterm-256color lrp", file=sys.stderr)
        return 1
    store = Store()
    previous = {}

    def stop(signum, frame):
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGHUP):
        previous[sig] = signal.signal(sig, stop)
    try:
        curses.wrapper(lambda screen: Console(screen, args, store).run())
    except KeyboardInterrupt:
        pass
    except curses.error as exc:
        print(f"Terminal setup failed: {exc}. Try Konsole with TERM=xterm-256color.", file=sys.stderr)
        return 1
    finally:
        store.save()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    if store.error:
        print(store.error, file=sys.stderr)
    print("LRP disconnected. Your unfinished character arc has been saved.")
    return 0

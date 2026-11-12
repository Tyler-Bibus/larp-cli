"""Radio Goblin: real BLE telemetry in the console's very unserious uniform."""

from collections import deque
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from .motion import segment
from .ble_advertising import ADVERTISING_CHANNELS, AdvertisingMonitor
from .ble_adv_midi import BUMBLE_ADDRESS

DIGITS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
}


class BLELink:
    def __init__(self):
        self.state = "idle"
        self.message = "Press c to acquire SeniorDesign BLE, or s to scan."
        self.devices = []
        self.selected = 0
        self.name = "SeniorDesign BLE"
        self.address = self.model = ""
        self.services = self.channels = self.count = 0
        self.values = {}
        self.heart = deque(maxlen=160)
        self.packets = deque(maxlen=120)
        self.last_packet = None
        self.process = None
        self._events = queue.Queue(maxsize=512)
        self._generation = 0
        self._stopping = None
        self.dropped = 0
        self.music = False
        self.monitoring = False
        self.advertising = AdvertisingMonitor()
        self.action = ""
        self.adv_midi = {}
        self._pending = None

    @staticmethod
    def worker_command(action, target):
        root = Path(__file__).resolve().parents[1]
        checkout = root.parent.parent if root.is_file() else root
        local = checkout / ".venv/bin/python"
        python = os.environ.get("LRP_BLE_PYTHON") or (str(local) if local.exists() else sys.executable)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        return [python, "-u", "-m", "lrp.ble_worker", action, target], env

    def start(self, action, target=""):
        self.poll()
        if self.process is not None and self.process.poll() is None:
            if action == "adv-midi":
                self.disconnect()
                self._pending = (action, target)
                self.message = "Stopping current BLE work, then listening for Bumble MIDI..."
                return
            self.message = "Link occupied. Disconnect before scanning or connecting again."
            return
        if not target and action == "connect":
            target = "SeniorDesign BLE"
            if self.devices:
                device = self.devices[self.selected]
                # A sole known carrier can be rediscovered after its private address rotates.
                target = device["name"] if len(self.devices) == 1 and device["name"] == target else device["address"]
        self._generation += 1
        self._stopping = None
        self.dropped = 0
        self.action = action
        self.adv_midi = {}
        self.monitoring = action in ("sniff", "sniff-rf", "replay", "adv-midi")
        self.state = "starting" if self.monitoring else "scanning" if action == "scan" else "connecting"
        self.message = "Starting advertising monitor..." if self.monitoring else "Sweeping the ether..." if action == "scan" else "Acquiring the radio goblin..."
        if self.monitoring:
            self.advertising = AdvertisingMonitor()
            self.advertising.source = "adapter" if action in ("sniff", "adv-midi") else "rf"
        if action == "adv-midi":
            target = target or BUMBLE_ADDRESS
            self.music = False
        if action == "connect":
            self.music = False
            self.values.clear()
            self.heart.clear()
            self.packets.clear()
            self.count = self.services = self.channels = 0
            self.last_packet = None
            self.address = self.model = ""
        command, env = self.worker_command(action, target)
        try:
            self.process = subprocess.Popen(command, env=env, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, encoding="utf-8", errors="replace")
        except OSError as exc:
            self.state, self.message = "error", f"Could not start BLE: {exc}"
            self.process = None
            return
        threading.Thread(target=self._read, args=(self.process, self._generation), daemon=True).start()

    def _read(self, process, generation):
        def send(event):
            try:
                self._events.put_nowait((generation, event))
            except queue.Full:
                try:
                    discarded_generation, _ = self._events.get_nowait()
                    if discarded_generation == generation == self._generation:
                        self.dropped += 1
                except queue.Empty:
                    pass
                try:
                    self._events.put_nowait((generation, event))
                except queue.Full:
                    if generation == self._generation:
                        self.dropped += 1
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        continue
                except ValueError:
                    event = dict(kind="notice", message=line.strip()[:200])
                send(event)
        finally:
            process.stdout.close()
            if process.stdin is not None:
                process.stdin.close()
            send(dict(kind="exit", code=process.wait()))

    def ingest(self, event):
        kind = event.get("kind")
        if kind == "state":
            self.state = event["state"]
            if self.state != "connected":
                self.music = False
            self.message = event.get("message", "")
        elif kind == "music":
            self.music = bool(event.get("enabled"))
            self.message = event.get("message", "")
        elif kind == "devices":
            self.devices = event.get("devices", [])[:24]
            self.selected = 0
        elif kind == "device":
            for name in ("name", "address", "model", "services", "channels"):
                setattr(self, name, event.get(name, getattr(self, name)))
        elif kind in ("sample", "reading"):
            self.values[event["metric"]] = event["value"]
            if kind == "sample":
                self.count += 1
                self.last_packet = time.monotonic()
                self.packets.append(event)
                if event["metric"] == "heart":
                    self.heart.append(event["value"])
        elif kind == "notice":
            self.message = event.get("message", "")
        elif kind == "advertisement":
            self.advertising.ingest(event)
        elif kind == "adv_midi":
            self.adv_midi = event
        elif kind == "exit" and self.state in ("connected", "connecting", "scanning", "disconnecting", "starting", "sniffing"):
            self.music = False
            self.state = "error" if event.get("code") else "disconnected"
            self.message = "BLE worker stopped. Start discovery, scan, or connect to retry."

    def poll(self):
        for _ in range(512):
            try:
                generation, event = self._events.get_nowait()
            except queue.Empty:
                break
            if generation == self._generation:
                self.ingest(event)
        if self._stopping is not None and time.monotonic() - self._stopping > 4:
            if self.process is not None and self.process.poll() is None:
                self.process.kill()
            self._stopping = None
        if self._pending is not None and (self.process is None or self.process.poll() is not None):
            pending, self._pending = self._pending, None
            self.start(*pending)

    def toggle_music(self):
        if self.state != "connected" or self.process is None or self.process.poll() is not None:
            self.message = "Connect first, then press u to unleash the funk."
            return
        try:
            self.process.stdin.write(json.dumps(dict(action="music", enabled=not self.music)) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError):
            self.message = "Music control unavailable. Disconnect and connect again."

    def disconnect(self):
        self._pending = None
        if self.process is not None and self.process.poll() is None:
            if self._stopping is None:
                self.state, self.message = "disconnecting", "Containing the radio goblin..."
                self._stopping = time.monotonic()
                self.process.terminate()
        else:
            self.state, self.message = "disconnected", "No active carrier. Press c to connect."

    def close(self):
        self.disconnect()
        if self.process is not None:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)


class BLEPanels:
    def ble_command(self, argument):
        action, _, target = argument.strip().partition(" ")
        if action in ("scan", "connect"):
            self.ble.start(action, target)
        elif action in ("sniff", "adv"):
            self.ble.start("sniff-rf" if target else "sniff", target)
        elif action == "replay":
            self.ble.start("replay", target)
        elif action in ("adv-midi", "bumble"):
            self.ble.start("adv-midi", target)
        elif action == "music":
            self.ble.toggle_music()
        elif action == "disconnect":
            self.ble.disconnect()
        elif action == "select":
            try:
                index = int(target)
                if 0 <= index < len(self.ble.devices):
                    self.ble.selected = index
            except ValueError:
                pass
        elif action:
            self.ble.message = "BLE: adv-midi [address] / sniff [RF interface] / replay <pcap> / scan / connect / disconnect"

    def ble_big_rate(self, y, x, columns, value):
        digits = str(value)
        raster = [" ".join(DIGITS[digit][row] for digit in digits) for row in range(5)]
        scale = min(3, max(1, (columns - 4) // len(raster[0])))
        left = x + (columns - len(raster[0]) * scale) // 2
        block = "#" if self.ascii else "█"
        for row, pixels in enumerate(raster):
            self.put(y + row, left, "".join((block if pixel == "1" else " ") * scale for pixel in pixels), "red")

    def ble_packet_feed(self, y, rows):
        self.box(y, 1, rows, self.w - 2, "PACKET GUTTER / NEWEST FIRST", "dim")
        packets = list(self.ble.packets)[-(rows - 2):]
        if not packets:
            self.put(y + 1, 3, "NO PACKETS YET. [c] summon the radio goblin.", "amber", self.w - 6)
            if rows > 3:
                self.put(y + 2, 3, "Phone connected? Release it first. ESP32 has one seat.", "dim", self.w - 6)
        for row, event in enumerate(reversed(packets)):
            stamp = datetime.fromtimestamp(event["timestamp"]).strftime("%H:%M:%S")
            label = {"heart": "PULSE", "battery": "POWER", "clock": "CLOCK", "midi": "MUSIC"}[event["metric"]]
            value = f"{event['value']} {event['unit']}".strip()
            self.put(y + row + 1, 3, f"{stamp} {label:5} {value:19}  {event['raw']}",
                     "mint" if row else "amber", self.w - 6)

    def ble_trace(self, y, x, columns, rows):
        samples = list(self.ble.heart)[-columns:]
        if not samples or rows < 1 or columns < 2:
            return
        low, high = min(90, min(samples)), max(160, max(samples))
        points = [(x + columns - len(samples) + i,
                   y + rows - 1 - round((value - low) / max(1, high - low) * (rows - 1)))
                  for i, value in enumerate(samples)]
        for a, b in zip(points, points[1:]):
            for px, py in segment(a, b):
                self.put(py, px, "." if self.ascii else "·", "mint")
        for px, py in points:
            self.put(py, px, "+" if self.ascii else "◆", "mint")
        px, py = points[-1]
        self.put(py, px, "@" if self.ascii else "█", "red")

    def ble_advertising_page(self):
        link, monitor = self.ble, self.ble.advertising
        adapter = monitor.source == "adapter"
        now = time.monotonic()

        def power(value):
            return "--" if value is None else str(value)

        def age(seen):
            return "--" if seen is None else f"{now - seen:.1f}s"

        bumble = link.action == "adv-midi"
        midi = link.adv_midi
        polyphonic = bumble and midi.get("protocol") == 2
        self.page_title("BUMBLE / ADVERTISING MIDI" if bumble else "BLE ADVERTISING / FPGA RADIO CHECK",
                        "BM v1 + v2 / NO CONNECTION / " + midi.get("address", BUMBLE_ADDRESS) if bumble else
                        "ALL NAMES / ALL ADDRESSES / RECEIVED SIGNAL POWER IN dBm")
        self.button(9, 3, " [a] ADAPTER ", "ble sniff", "soft")
        self.button(9, 18, " [d] STOP ", "ble disconnect", "soft")
        self.button(9, 30, " [v] BUMBLE MIDI ", "ble adv-midi", "mint")
        unit = "OS REPORTS" if adapter else "ADV PACKETS"
        status = "RECEIVING" if monitor.last is not None and now - monitor.last < 2 else "WAITING"
        if link.state != "sniffing":
            status = link.state.upper()
        crc_bad = "--" if adapter else str(monitor.bad_crc)
        self.put(10, 3, f"{status} / {unit} {monitor.count:,} / LAST {age(monitor.last)} / CRC BAD {crc_bad}",
                 "red" if link.state == "error" else "mint" if status == "RECEIVING" else "amber", self.w - 6)
        if bumble:
            text = (f"V2 / ACTIVE {sum(bool(v) for _, v, _ in midi.get('voice_states', []))}/8 / STATES {midi.get('played', 0)} / STRIKES {midi.get('strikes', 0)}" if polyphonic else
                    f"NOTE {midi.get('current_note', '--')} / PLAYED {midi.get('played', 0)} / REPEAT {midi.get('duplicates', 0)} / INVALID {midi.get('invalid', 0)}")
            self.put(11, 3, text,
                     "mint" if link.music else "amber", self.w - 6)
        else:
            self.put(11, 3, "ADAPTER: channel/CRC unavailable; reports may merge ADV + scan response" if adapter else
                     "RF SNIFFER: measured channels / CRC when provided by capture", "amber", self.w - 6)
        if polyphonic:
            from .ble_music import note_name
            span = (self.w - 6) // 2
            for k, (note, velocity, toggle) in enumerate(midi.get("voice_states", [])):
                program = midi["programs"][k]
                label = "P---" if program is None else "DRUM" if program & 128 else f"P{program:03}"
                self.put(12 + k // 2, 3 + (k % 2) * span,
                         f"V{k} {note_name(note) if velocity else '--':3} {label} v{velocity:3}",
                         "mint" if velocity else "dim", span - 1)
        else:
            for row, (channel, frequency) in enumerate(ADVERTISING_CHANNELS.items(), 12):
                stats = monitor.channels[channel]
                text = (f"CH {channel} / {frequency} MHz / RX -- / RSSI -- (unavailable)" if adapter else
                        f"CH {channel} / {frequency} MHz / RX {stats['count']} / {power(stats['rssi'])} dBm / BAD {stats['bad']} / {age(stats['last'])}")
                self.put(row, 3, text, "mint" if stats["last"] is not None and now - stats["last"] < 2 else "dim", self.w - 6)
            self.put(15, 3, f"CH ?/secondary {monitor.unknown} / devices {len(monitor.devices)} / UI dropped {link.dropped}", "dim", self.w - 6)
        self.put(16, 3, "ADDRESS              RSSI  PEAK    SEEN    AGE NAME / newest first", "amber", self.w - 6)
        detail_y = max(18, self.h - 7)
        rows = detail_y - 17
        devices = list(reversed(monitor.devices.values()))
        monitor.offset = min(monitor.offset, max(0, len(devices) - rows))
        if not devices:
            self.put(17, 3, "NO ADVERTISING OBSERVED YET", "amber", self.w - 6)
        for row, device in enumerate(devices[monitor.offset:monitor.offset + rows], 17):
            text = (f"{device['address'][:19]:19} {power(device['rssi']):>4} {power(device['peak']):>5} "
                    f"{device['count']:7} {age(device['seen']):>6} {device['name']}")
            self.put(row, 3, text, "mint" if now - device["seen"] < 2 else "dim", self.w - 6)
        if monitor.packets:
            packet = monitor.packets[-1]
            channel = "?" if packet.get("channel") is None else str(packet["channel"])
            crc = {True: "OK", False: "BAD", None: "?"}[packet.get("crc")]
            self.put(detail_y, 3, f"LATEST / {packet['pdu']} / CH {channel} / {power(packet.get('rssi'))} dBm / CRC {crc}", "mint", self.w - 6)
            if detail_y + 1 < self.h - 5:
                self.put(detail_y + 1, 3, packet.get("payload", ""), "white", self.w - 6)
        else:
            self.put(detail_y, 3, link.message, "red" if link.state == "error" else "amber", self.w - 6)
            if detail_y + 1 < self.h - 5:
                self.put(detail_y + 1, 3, "Power-cycle FPGA; watch for a new signal near the receiver.", "dim", self.w - 6)
        self.put(self.h - 5, 3, (midi.get("error") or ("SIGNAL GAP / voices released / awaiting a new state" if midi.get("watchdog") else
                 "Bumble BM v1 + v2 / 0xFFFF / d stops audio")) if bumble else
                 "No reports does not prove RF silence. Bad PHY/CRC can be invisible.", "amber", self.w - 6)

    def ble_page(self):
        link = self.ble
        if link.monitoring:
            self.ble_advertising_page()
            return
        self.page_title("RADIO GOBLIN / BLE CONTAINMENT LAB",
                        "REAL BLUETOOTH / ESP32-GENERATED DEMO VALUES / ONE CLIENT AT A TIME")
        x = 3
        for label, action in ((" [s] SCAN ", "scan"), (" [c] CONNECT ", "connect"),
                              (" [d] DISCONNECT ", "disconnect"),
                              (" [u] " + ("MUTE " if link.music else "MUSIC "), "music")):
            self.button(9, x, label, "ble " + action, "soft")
            x += len(label) + 1
        self.button(11, self.w - 17, " [a] ADV SNIFF ", "ble sniff", "mint")
        self.button(11, 3, " [v] BUMBLE MIDI ", "ble adv-midi", "mint")
        if self.w >= 96:
            self.put(11, 22, "GATT MUSIC: " + (str(link.values.get("midi", "...")) if link.music else "u to play"), "red" if link.music else "dim", self.w - 42)
        age = "--" if link.last_packet is None else f"{time.monotonic() - link.last_packet:.1f}s"
        live = link.state == "connected"
        self.put(10, 3, f"{link.state.upper()} / RX {link.count:,} / LAST {age} / {link.message}",
                 "red" if link.state == "error" else "mint" if live else "amber", self.w - 6)
        if self.h < 34 or self.w < 96:
            self.put(12, 3, f"PULSE {link.values.get('heart', '--')} bpm   POWER {link.values.get('battery', '--')}%   RX {link.count}",
                     "red", self.w - 6)
            if link.state == "error":
                for row, line in enumerate(self.wrap_text(link.message, self.w - 6)[:max(1, self.h - 19)]):
                    self.put(14 + row, 3, line, "amber", self.w - 6)
            elif link.devices and not live:
                for row, device in enumerate(link.devices[:max(1, self.h - 19)]):
                    self.button(14 + row, 3, f" {'>' if row == link.selected else ' '} {device['name']} {device['rssi']} dBm ",
                                f"ble select {row}", "bar" if row == link.selected else "dim")
                self.put(self.h - 6, 3, "Up/Down select / c connect / :ble connect <name>", "dim", self.w - 6)
            else:
                self.ble_packet_feed(14, self.h - 19)
            self.put(self.h - 5, 3, "PAYLOAD: SIMULATED. PACKETS: REAL. Space freezes art, not BLE.", "amber", self.w - 6)
            return

        bottom = self.h - 5
        log_h = min(9, max(6, (self.h - 12) // 3))
        log_y = bottom - log_h
        body_h = log_y - 12
        side = min(36, self.w // 3)
        self.box(12, 1, body_h, side, "CARRIER CAGE", "dim")
        self.put(14, 3, link.name, "mint", side - 4)
        self.put(15, 3, link.address or "NO CARRIER / c to acquire", "dim", side - 4)
        self.put(16, 3, f"{link.services} services / {link.channels} streams", "white", side - 4)
        room = max(0, body_h - 10)
        if link.devices and not live:
            start = max(0, link.selected - max(0, room - 1))
            for row, device in enumerate(link.devices[start:start + room]):
                index = start + row
                label = f" {'>' if index == link.selected else ' '} {device['name'][:15]:15} {device['rssi']}dBm "
                self.button(18 + row, 3, label, f"ble select {index}", "bar" if index == link.selected else "dim")
        else:
            self.put(18, 3, "STATUS: " + ("ABSOLUTELY YAPPING" if live else "UNSUMMONED"), "amber", side - 4)
        if body_h >= 10:
            if "battery" in link.values:
                self.meter(12 + body_h - 4, 3, side - 4, "POWER / SIMULATED", int(link.values["battery"]), "amber")
            else:
                self.put(12 + body_h - 4, 3, "POWER -- / AWAITING SAMPLE", "amber", side - 4)
            clock = link.values.get("clock", "Clock awaits carrier")
            self.put(12 + body_h - 2, 3, clock, "dim", side - 4)

        right = side + 2
        span = self.w - right - 1
        self.box(12, right, body_h, span, "SYNTHETIC ORGANISM / LIVE RX", "red")
        if "heart" in link.values:
            self.ble_big_rate(14, right + 1, span - 2, link.values["heart"])
        else:
            self.center(16, "[ NO ORGANISM ACQUIRED ]", "red", right + 1, span - 2)
        self.put(13, right + 3, "HEART RATE / bpm", "dim", span - 6)
        if body_h >= 12:
            self.ble_trace(20, right + 3, span - 6, body_h - 10)
        pulse = link.last_packet is not None and time.monotonic() - link.last_packet < .3
        bracket = " >>> PACKET IMPACT <<< " if pulse and not (self.calm or self.paused) else " ACTUAL PACKETS / DEMO BIOLOGY "
        self.center(log_y - 2, bracket, "red" if pulse else "dim", right + 1, span - 2)
        if live and not (self.calm or self.paused):
            column = right + 3 + int(self.fx_time * 14) % max(1, span - 6)
            self.put(13, column, "+", "red")
        self.ble_packet_feed(log_y, log_h)
        self.put(bottom, 3, "THE READINGS ARE SIMULATED. THE RADIO GOBLIN IS PHYSICALLY PRESENT.", "amber", self.w - 6)

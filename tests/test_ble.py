"""BLE packet decoding, optional transport isolation, and terminal navigation."""

import curses
import json
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from lrp.app import Console
from lrp.ble import BLELink
from lrp.ble_worker import BATTERY, CLOCK, HEART, decode_sample
from test_lrp import Terminal


class BLEPacketTests(unittest.TestCase):
    def test_large_rate_has_visible_digits(self):
        app = Console.__new__(Console)
        app.ascii = True
        rows = []
        app.put = lambda y, x, text, style: rows.append(text)
        app.ble_big_rate(0, 0, 75, 123)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all("#" in row for row in rows))

    def test_heart_rate_formats_and_malformed_payloads(self):
        self.assertEqual(decode_sample(HEART, bytes([0, 123])), ("heart", 123, "bpm"))
        self.assertEqual(decode_sample(HEART, bytes([1, 44, 1])), ("heart", 300, "bpm"))
        for raw in (b"", b"\x00", b"\x01\x02"):
            with self.assertRaises(ValueError):
                decode_sample(HEART, raw)
        for raw in (b"", b"\x65", b"\x01\x02"):
            with self.assertRaises(ValueError):
                decode_sample(BATTERY, raw)

    def test_battery_and_clock(self):
        self.assertEqual(decode_sample(BATTERY, b"\x25"), ("battery", 37, "%"))
        clock = bytes([0xEA, 0x07, 10, 21, 19, 30, 45, 3, 0, 1])
        self.assertEqual(decode_sample(CLOCK, clock), ("clock", "2026-10-21 19:30:45", ""))
        with self.assertRaises(ValueError):
            decode_sample(CLOCK, b"\x00")

    def test_reads_are_not_counted_as_incoming_notifications_and_memory_is_bounded(self):
        link = BLELink()
        self.assertIsNone(link.process)
        link.ingest(dict(kind="reading", metric="battery", value=88))
        self.assertEqual(link.count, 0)
        self.assertIsNone(link.last_packet)
        for value in range(600):
            link.ingest(dict(kind="sample", metric="heart", value=90 + value % 70,
                             unit="bpm", raw="0064", timestamp=time.time()))
        self.assertEqual(link.count, 600)
        self.assertEqual(len(link.heart), 160)
        self.assertEqual(len(link.packets), 120)

    def test_worker_errors_are_actionable_and_stale_sessions_cannot_overwrite_new_link(self):
        link = BLELink()
        with patch("lrp.ble.subprocess.Popen", side_effect=OSError("runtime unavailable")):
            link.start("connect")
        self.assertEqual(link.state, "error")
        self.assertIn("runtime unavailable", link.message)
        link._generation = 4
        link.state = "connected"
        link._events.put((3, dict(kind="state", state="disconnected", message="old link")))
        link.poll()
        self.assertEqual(link.state, "connected")

    def test_single_known_device_is_rediscovered_after_private_address_rotation(self):
        link = BLELink()
        link.devices = [dict(name="SeniorDesign BLE", address="40:11:22:33:44:55", rssi=-40)]
        process = Mock()
        process.poll.return_value = 0
        with patch("lrp.ble.subprocess.Popen", return_value=process) as launch, \
                patch("lrp.ble.threading.Thread"):
            link.start("connect")
        self.assertEqual(launch.call_args.args[0][-1], "SeniorDesign BLE")

    def test_pause_does_not_drop_real_data(self):
        app = Console.__new__(Console)
        app.ble = BLELink()
        app.ble._events.put((0, dict(kind="sample", metric="heart", value=111,
                                   unit="bpm", raw="006f", timestamp=time.time())))
        app.last_frame = app.last_host = app.last_tick = app.last_feed = time.monotonic()
        app.paused, app.calm, app.editing = True, False, False
        app.update()
        self.assertEqual(app.ble.values["heart"], 111)


class BLETerminalTests(unittest.TestCase):
    def test_page_navigation_small_terminal_and_terminal_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal = Terminal(directory, options=("--calm", "--ascii"))
            self.addCleanup(terminal.close)
            terminal.send("8")
            terminal.send("\x0c")
            self.assertIn(b"RADIO GOBLIN / BLE CONTAINMENT LAB", terminal.output)
            self.assertIn(b"NO PACKETS YET", terminal.output)
            terminal.send("1")
            terminal.send(":ble\n")
            terminal.resize(24, 64)
            terminal.send("\x0c")
            self.assertIn(b"[c] CONNECT", terminal.output)
            terminal.send("d")
            terminal.send("\x0c")
            self.assertIn(b"DISCONNECTED", terminal.output)
            self.assertEqual(terminal.finish(), terminal.original)
            self.assertNotIn(b"Traceback", terminal.output)
            self.assertEqual(terminal.process.returncode, 0)


if __name__ == "__main__":
    unittest.main()

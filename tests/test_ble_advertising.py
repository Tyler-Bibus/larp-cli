"""Unfiltered discovery, truthful RF metadata, and advertising terminal layouts."""

import asyncio
import csv
import io
import json
import queue
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from lrp.app import Console
from lrp.ble import BLELink
from lrp.ble_advertising import (
    AdvertisingMonitor, RF_FIELDS, advertising_report, rf_report, tshark_command,
)
from lrp.ble_worker import advertise, sniff_rf
from test_lrp import Terminal


def rf_line(**fields):
    data = {"frame.time_epoch": "1794420000.25", "btle.advertising_header.pdu_type": "0x00",
            "btle.advertising_address": "c0:11:22:33:44:55", **fields}
    result = io.StringIO()
    csv.writer(result, delimiter="\t", quoting=csv.QUOTE_ALL).writerow([data.get(key, "") for key in RF_FIELDS])
    return result.getvalue()


def unnamed_report(rssi=-47):
    device = SimpleNamespace(address="c0:11:22:33:44:55", name=None)
    adv = SimpleNamespace(local_name=None, rssi=rssi, tx_power=-10,
                          manufacturer_data={0x1234: b"\x00\xff"}, service_data={}, service_uuids=[])
    return advertising_report(device, adv)


class AdvertisingTests(unittest.TestCase):
    def test_unnamed_device_payload_rssi_and_tx_power_are_kept_distinct(self):
        report = unnamed_report()
        self.assertEqual(report["name"], "(unnamed)")
        self.assertEqual(report["rssi"], -47)
        self.assertEqual(report["tx_power"], -10)
        self.assertEqual(report["payload"], "MFG 1234:00ff")
        self.assertIsNone(report["channel"])
        self.assertIsNone(report["crc"])
        self.assertIsNone(unnamed_report(127)["rssi"])

    def test_sniffer_command_keeps_interface_as_one_argument(self):
        target = "sniffer; example with spaces"
        command = tshark_command(target)
        self.assertEqual(command[command.index("-i") + 1], target)
        self.assertNotIn("-r", command)
        self.assertIn("-r", tshark_command("capture.pcapng", replay=True))
        self.assertIn("nordic_ble.channel", command)
        self.assertIn("btle_rf.flags.crc_checked", command)

    def test_rf_frequency_indices_are_mapped_to_ble_primary_channels(self):
        for rf, channel in ((0, 37), (12, 38), (39, 39), (1, 0), (38, 36)):
            report = rf_report(rf_line(**{"btle_rf.channel": str(rf), "btle_rf.signal_dbm": "-52",
                                         "btle_rf.flags.signal_dbm_valid": "1",
                                         "btle_rf.flags.crc_checked": "1", "btle_rf.flags.crc_valid": "0"}))
            self.assertEqual(report["channel"], channel)
            self.assertEqual(report["rssi"], -52)
            self.assertIs(report["crc"], False)

    def test_nordic_indices_are_not_remapped_and_bad_crc_is_preserved(self):
        report = rf_report(rf_line(**{"nordic_ble.channel": "37", "nordic_ble.rssi": "-31",
                                     "nordic_ble.crcok": "0", "_ws.col.Info": 'ADV_IND, "test"'}))
        self.assertEqual((report["channel"], report["rssi"], report["crc"]), (37, -31, False))
        self.assertEqual(report["payload"], 'ADV_IND, "test"')

    def test_unavailable_rf_measurements_are_never_fabricated(self):
        report = rf_report(rf_line(**{"btle_rf.channel": "12", "btle_rf.flags.channel_aliased": "1",
                                     "btle_rf.signal_dbm": "0", "btle_rf.flags.signal_dbm_valid": "0",
                                     "btle_rf.flags.crc_valid": "0", "btle_rf.flags.crc_checked": "0"}))
        self.assertIsNone(report["channel"])
        self.assertIsNone(report["rssi"])
        self.assertIsNone(report["crc"])
        for kind in (3, 4, 5):
            self.assertIsNone(rf_report(rf_line(**{"btle.advertising_header.pdu_type": str(kind)})))
        with self.assertRaises(ValueError):
            rf_report("broken\trow")

    def test_observation_counts_channels_peak_power_and_memory_bounds(self):
        monitor = AdvertisingMonitor()
        for rssi in (-70, -35, -50):
            monitor.ingest(unnamed_report(rssi))
        self.assertEqual((monitor.count, monitor.unknown), (3, 3))
        device = next(iter(monitor.devices.values()))
        self.assertEqual((device["rssi"], device["peak"], device["count"]), (-50, -35, 3))
        self.assertTrue(all(stats["count"] == 0 for stats in monitor.channels.values()))
        monitor.ingest(rf_report(rf_line(**{"nordic_ble.channel": "38", "nordic_ble.rssi": "-43", "nordic_ble.crcok": "0"})))
        self.assertEqual((monitor.channels[38]["count"], monitor.channels[38]["bad"], monitor.bad_crc), (1, 1, 1))
        for index in range(600):
            monitor.ingest(dict(unnamed_report(), address=f"test-{index}"))
        self.assertEqual(len(monitor.devices), 256)
        self.assertEqual(len(monitor.packets), 120)

    def test_sniff_has_no_default_target_and_exit_state_is_handled(self):
        link = BLELink()
        link.devices = [dict(name="SeniorDesign BLE", address="old", rssi=-20)]
        with patch("lrp.ble.subprocess.Popen", return_value=Mock()) as launch, patch("lrp.ble.threading.Thread"):
            link.start("sniff")
        self.assertEqual(launch.call_args.args[0][-2:], ["sniff", ""])
        self.assertTrue(link.monitoring)
        link.ingest(dict(kind="state", state="sniffing"))
        link.ingest(unnamed_report())
        link.ingest(dict(kind="exit", code=1))
        self.assertEqual(link.state, "error")
        self.assertEqual(link.advertising.count, 1)

    def test_full_ui_queue_reports_lost_observations(self):
        link = BLELink()
        link._events = queue.Queue(maxsize=2)
        process = Mock(stdout=io.StringIO((json.dumps(unnamed_report()) + "\n") * 4), stdin=None)
        process.wait.return_value = 0
        link._read(process, 0)
        self.assertEqual(link.dropped, 3)
        self.assertEqual(link._events.qsize(), 2)

    def test_compact_page_keeps_device_row_and_channel_limits_visible(self):
        for height, width in ((24, 64), (40, 120)):
            with self.subTest(size=(height, width)):
                app = Console.__new__(Console)
                app.h, app.w, app.ble = height, width, BLELink()
                app.ble.monitoring, app.ble.state = True, "sniffing"
                app.ble.ingest(unnamed_report())
                output = {}
                app.put = lambda y, x, text, *args: output.__setitem__(y, text)
                app.page_title = app.button = lambda *args: None
                app.ble_advertising_page()
                self.assertIn("c0:11:22:33:44:55", output[17])
                self.assertIn("-47", output[17])
                self.assertIn("unavailable", output[12])
                self.assertTrue(any("CH ?" in text for text in output.values()))


class AdvertisingWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelling_rf_capture_reaps_its_process(self):
        started = asyncio.Event()
        processes = []
        create_process = asyncio.create_subprocess_exec

        async def capture_process(*args, **kwargs):
            process = await create_process(*args, **kwargs)
            processes.append(process)
            return process

        command = [sys.executable, "-c", "import time; time.sleep(60)"]
        with patch("lrp.ble_worker.tshark_command", return_value=command), \
                patch("lrp.ble_worker.asyncio.create_subprocess_exec", side_effect=capture_process), \
                patch("lrp.ble_worker.emit", side_effect=lambda *args, **kwargs: started.set()):
            task = asyncio.create_task(sniff_rf("sniffer"))
            await asyncio.wait_for(started.wait(), timeout=2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)
        self.assertIsNotNone(processes[0].returncode)

    async def test_scanner_reports_all_devices_and_cancellation_stops_discovery(self):
        started = asyncio.Event()
        options, events, exits = {}, [], []

        class Scanner:
            def __init__(self, **kwargs):
                options.update(kwargs)

            async def __aenter__(self):
                device = SimpleNamespace(address="unknown", name=None)
                adv = SimpleNamespace(local_name=None, rssi=-43, tx_power=None,
                                      manufacturer_data={}, service_data={}, service_uuids=[])
                for _ in range(2):
                    options["detection_callback"](device, adv)
                started.set()

            async def __aexit__(self, *args):
                exits.append(True)

        with patch("lrp.ble_worker.emit", side_effect=lambda kind, **fields: events.append(dict(kind=kind, **fields))):
            task = asyncio.create_task(advertise(Scanner))
            await asyncio.wait_for(started.wait(), timeout=2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertNotIn("service_uuids", options)
        self.assertEqual(options["bluez"]["filters"]["DuplicateData"], True)
        self.assertEqual(len([event for event in events if event["kind"] == "advertisement"]), 2)
        self.assertEqual(exits, [True])

    async def test_rf_reader_streams_packets_and_reports_tshark_failures(self):
        line = rf_line(**{"nordic_ble.channel": "39", "nordic_ble.rssi": "-39", "nordic_ble.crcok": "1"})
        events = []
        # Exercise real pipes and process cleanup without requiring RF hardware.
        command = [sys.executable, "-c", f"print({line!r})"]
        with patch("lrp.ble_worker.tshark_command", return_value=command), \
                patch("lrp.ble_worker.emit", side_effect=lambda kind, **fields: events.append(dict(kind=kind, **fields))):
            await sniff_rf("capture.pcap", replay=True)
        report = next(event for event in events if event["kind"] == "advertisement")
        self.assertEqual((report["channel"], report["rssi"], report["crc"]), (39, -39, True))
        self.assertEqual(events[-1]["state"], "disconnected")
        command = [sys.executable, "-c", "import sys; print('permission denied', file=sys.stderr); sys.exit(1)"]
        with patch("lrp.ble_worker.tshark_command", return_value=command), patch("lrp.ble_worker.emit"):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                await sniff_rf("sniffer")


class AdvertisingTerminalTests(unittest.TestCase):
    def test_navigation_and_compact_screen_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal = Terminal(directory, options=("--calm", "--ascii"))
            self.addCleanup(terminal.close)
            terminal.send(":ble replay /no/such/capture.pcap\n")
            terminal.send("\x0c")
            self.assertIn(b"BLE ADVERTISING / FPGA RADIO CHECK", terminal.output)
            self.assertIn(b"2402 MHz", terminal.output)
            self.assertIn(b"2426 MHz", terminal.output)
            self.assertIn(b"2480 MHz", terminal.output)
            terminal.resize(24, 64)
            terminal.send("\x0c")
            terminal.send("d")
            self.assertEqual(terminal.finish(), terminal.original)
            self.assertNotIn(b"Traceback", terminal.output)


if __name__ == "__main__":
    unittest.main()

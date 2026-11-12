"""Bumble advertising note protocol, lossy delivery, and connection-free playback."""

import asyncio
import json
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from lrp.app import Console
from lrp.ble import BLELink
from lrp.ble_adv_midi import (
    BUMBLE_ADDRESS, COMPANY_ID, AdvertisingMidiPlayer, decode_adv_note,
    encode_adv_data, encode_adv_note, midi_address,
)
from lrp.ble_worker import advertising_midi
from test_lrp import Terminal


class AdvMidiTests(unittest.TestCase):
    def test_corrected_address_and_strict_address_validation(self):
        self.assertEqual(BUMBLE_ADDRESS, "F0:F1:F2:F3:F4:F5")
        self.assertEqual(midi_address("f0:f1:f2:f3:f4:f5"), BUMBLE_ADDRESS)
        for value in ("F1:F2:F3:F4:F5", "F0:F1:F2:F3:F4:F5:F6", "Bumble", "xx:11:22:33:44:55"):
            with self.assertRaises(ValueError):
                midi_address(value)

    def test_sender_vector_and_ad_lengths_round_trip(self):
        data = encode_adv_data(1, 0, 69, 100, 500)
        self.assertEqual(data.hex(), "020106070942756d626c650effffff424d01010000004564f401")
        self.assertEqual(len(data), 26)
        self.assertEqual(decode_adv_note(data[-11:]), (1, 0, 69, 100, 500))
        entries = []
        offset = 0
        while offset < len(data):
            length = data[offset]
            entries.append(data[offset + 1:offset + 1 + length])
            offset += 1 + length
        self.assertEqual(offset, len(data))
        self.assertEqual(entries[:2], [b"\x01\x06", b"\x09Bumble"])
        self.assertEqual(entries[2][:3], b"\xff\xff\xff")
        self.assertEqual(decode_adv_note(entries[2][3:]), (1, 0, 69, 100, 500))

    def test_invalid_packets_do_not_reach_audio_or_displace_good_sequence(self):
        synth = Mock()
        player = AdvertisingMidiPlayer(synth)
        valid = encode_adv_note(1, 0, 60, 100, 200)
        malformed = (b"", valid[:-1], valid + b"\x00", b"XX" + valid[2:], valid[:2] + b"\x02" + valid[3:],
                     struct.pack("<2sBHHBBH", b"BM", 1, 1, 1, 128, 100, 200),
                     struct.pack("<2sBHHBBH", b"BM", 1, 1, 1, 60, 128, 200),
                     struct.pack("<2sBHHBBH", b"BM", 1, 1, 1, 60, 100, 0))
        for raw in malformed:
            self.assertIsNone(player.receive(raw, now=0))
        synth.message.assert_not_called()
        self.assertEqual(player.invalid, len(malformed))
        self.assertIsNotNone(player.receive(valid, now=0))

    def test_duplicates_do_not_retrigger_or_extend_note_and_lost_stop_is_safe(self):
        synth = Mock()
        player = AdvertisingMidiPlayer(synth)
        packet = encode_adv_note(1, 0, 69, 100, 500)
        player.receive(packet, now=0)
        calls = synth.message.call_count
        for when in (.1, .3, .49):
            self.assertIsNone(player.receive(packet, now=when))
        self.assertEqual(synth.message.call_count, calls)
        self.assertEqual(player.deadline, .5)
        player.tick(now=.49)
        self.assertEqual(player.note, 69)
        player.tick(now=.5)
        synth.message.assert_called_with(0x80, 69, 0)
        self.assertIsNone(player.note)
        self.assertIsNone(player.receive(packet, now=.6))
        self.assertIsNone(player.note)

    def test_repeated_notes_new_sessions_wrap_old_events_and_rests(self):
        player = AdvertisingMidiPlayer(Mock())
        for seq in (65534, 65535, 0, 1):
            self.assertIsNotNone(player.receive(encode_adv_note(1, seq, 60, 100, 100), now=0))
        self.assertIsNone(player.receive(encode_adv_note(1, 65535, 60, 100, 100), now=0))
        self.assertIsNone(player.receive(encode_adv_note(1, 32769, 60, 100, 100), now=0))
        self.assertIsNotNone(player.receive(encode_adv_note(2, 0, 72, 100, 65535), now=0))
        self.assertIsNone(player.receive(encode_adv_note(1, 2, 60, 100, 100), now=0))
        self.assertEqual(player.note, 72)
        self.assertIsNotNone(player.receive(encode_adv_note(2, 1, 0, 0, 0), now=0))
        self.assertIsNone(player.note)
        self.assertIsNone(player.deadline)
        player.synth.message.assert_called_with(0xB0, 123, 0)
        player.close()
        player.synth.close.assert_called_once()

    def test_button_command_switches_existing_scan_and_manual_stop_cancels_switch(self):
        link = BLELink()
        old = Mock()
        old.poll.return_value = None
        link.process, link.monitoring = old, True
        link.start("adv-midi")
        old.terminate.assert_called_once()
        self.assertEqual(link._pending, ("adv-midi", ""))
        old.poll.return_value = 0
        with patch("lrp.ble.subprocess.Popen", return_value=Mock()) as launch, patch("lrp.ble.threading.Thread"):
            link.poll()
        self.assertEqual(launch.call_args.args[0][-2:], ["adv-midi", BUMBLE_ADDRESS])
        self.assertTrue(link.monitoring)
        self.assertEqual(link.action, "adv-midi")
        link.ingest(dict(kind="adv_midi", current_note="A4", played=1))
        self.assertEqual(link.adv_midi["current_note"], "A4")
        link.process = old
        old.poll.return_value = None
        link.start("adv-midi")
        link.disconnect()
        self.assertIsNone(link._pending)

    def test_bumble_button_and_note_display_fit_both_layouts(self):
        for height, width in ((24, 64), (40, 120)):
            with self.subTest(size=(height, width)):
                app = Console.__new__(Console)
                app.h, app.w, app.ble = height, width, BLELink()
                app.ble.action, app.ble.monitoring = "adv-midi", True
                app.ble.adv_midi = dict(current_note="C4", played=3, duplicates=10, invalid=1)
                output, buttons = [], []
                app.put = lambda *args: output.append(args)
                app.page_title = lambda *args: output.append(args)
                app.button = lambda *args: buttons.append(args)
                app.ble_advertising_page()
                self.assertTrue(any("NOTE C4 / PLAYED 3" in str(row) for row in output))
                self.assertTrue(any("ble adv-midi" in row for row in buttons))
                self.assertTrue(any(BUMBLE_ADDRESS in str(row) for row in output))


class AdvMidiWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_address_filter_no_connection_duration_and_cleanup(self):
        ready = asyncio.Event()
        synth = Mock(error=None)
        events = []
        callbacks = {}
        packet = encode_adv_note(1, 0, 69, 100, 5)

        class Scanner:
            def __init__(self, **kwargs):
                callbacks.update(kwargs)

            async def __aenter__(self):
                callback = callbacks["detection_callback"]
                def report(address, name, data):
                    callback(SimpleNamespace(address=address, name=name),
                             SimpleNamespace(local_name=name, manufacturer_data=data, rssi=-45,
                                             tx_power=None, service_data={}, service_uuids=[]))
                # Same name at the wrong address must never play.
                report("F1:F2:F3:F4:F5:F6", "Bumble", {COMPANY_ID: packet})
                # Correct address works without an advertised name.
                report(BUMBLE_ADDRESS.lower(), None, {0x1234: packet})
                report(BUMBLE_ADDRESS.lower(), None, {COMPANY_ID: b"bad"})
                report(BUMBLE_ADDRESS.lower(), None, {COMPANY_ID: packet})
                report(BUMBLE_ADDRESS.lower(), None, {COMPANY_ID: packet})
                ready.set()

            async def __aexit__(self, *args):
                callbacks["stopped"] = True

        def emit(kind, **fields):
            events.append(dict(kind=kind, **fields))

        with patch("lrp.ble_worker.Synth", return_value=synth), patch("lrp.ble_worker.emit", side_effect=emit):
            task = asyncio.create_task(advertising_midi(Scanner))
            await asyncio.wait_for(ready.wait(), timeout=2)
            await asyncio.sleep(.03)
            # Automatic duration release without receiving an OFF packet.
            self.assertIn(((0x80, 69, 0),), synth.message.call_args_list)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        statuses = [event for event in events if event["kind"] == "adv_midi"]
        self.assertEqual((statuses[0]["played"], statuses[0]["duplicates"], statuses[0]["invalid"]), (1, 1, 1))
        self.assertEqual(statuses[0]["current_note"], "A4")
        self.assertEqual(statuses[-1]["current_note"], "--")
        self.assertFalse(statuses[-1]["enabled"])
        self.assertTrue(callbacks["stopped"])
        synth.close.assert_called_once()
        ons = [call for call in synth.message.call_args_list if call.args[0] == 0x90]
        self.assertEqual(len(ons), 1)

    async def test_scanner_failure_and_audio_failure_close_the_synth(self):
        for scanner_fails in (True, False):
            with self.subTest(scanner_fails=scanner_fails):
                synth = Mock(error="Audio output stopped")

                class Scanner:
                    def __init__(self, **kwargs):
                        pass

                    async def __aenter__(self):
                        if scanner_fails:
                            raise RuntimeError("scanner unavailable")

                    async def __aexit__(self, *args):
                        pass

                with patch("lrp.ble_worker.Synth", return_value=synth), patch("lrp.ble_worker.emit"):
                    with self.assertRaisesRegex(RuntimeError, "scanner unavailable" if scanner_fails else "Audio output stopped"):
                        await advertising_midi(Scanner)
                synth.close.assert_called_once()


class AdvMidiTerminalTests(unittest.TestCase):
    def test_keyboard_button_and_startup_option_launch_correct_worker_and_restore_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "worker-args.json"
            worker = root / "fake-ble-python"
            worker.write_text(
                "#!/usr/bin/env python3\n"
                "import json, pathlib, signal, sys, time\n"
                f"pathlib.Path({str(log)!r}).write_text(json.dumps(sys.argv[-2:]))\n"
                "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))\n"
                "print(json.dumps(dict(kind='state', state='sniffing')), flush=True)\n"
                "print(json.dumps(dict(kind='music', enabled=True)), flush=True)\n"
                "print(json.dumps(dict(kind='adv_midi', current_note='A4', played=1)), flush=True)\n"
                "while True: time.sleep(.1)\n")
            worker.chmod(0o755)
            with patch.dict(os.environ, LRP_BLE_PYTHON=str(worker)):
                terminal = Terminal(directory, options=("--calm", "--ascii"))
                self.addCleanup(terminal.close)
                terminal.send("8")
                self.assertIn(b"BUMBLE MIDI", terminal.output)
                terminal.send("v")
                terminal.send("\x0c")
                self.assertIn(b"BUMBLE / ADVERTISING MIDI", terminal.output)
                self.assertIn(b"NOTE A4 / PLAYED 1", terminal.output)
                self.assertEqual(json.loads(log.read_text()), ["adv-midi", BUMBLE_ADDRESS])
                terminal.send("d")
                self.assertEqual(terminal.finish(), terminal.original)
                self.assertNotIn(b"Traceback", terminal.output)

                # The startup flag must enter the same page directly, without
                # relying on the default control-room marker in Terminal.
                read_until = Terminal.read_until

                def startup_read(instance, marker, timeout=4):
                    if marker == b"CONNECTED TO ABSOLUTELY NOTHING":
                        marker = b"BUMBLE / ADVERTISING MIDI"
                    return read_until(instance, marker, timeout)

                with patch.object(Terminal, "read_until", startup_read):
                    terminal = Terminal(directory, options=("--calm", "--ascii", "--ble-adv-midi"))
                self.addCleanup(terminal.close)
                terminal.send("\x0c")
                self.assertIn(BUMBLE_ADDRESS.encode(), terminal.output)
                self.assertEqual(terminal.finish(), terminal.original)
                self.assertNotIn(b"Traceback", terminal.output)


if __name__ == "__main__":
    unittest.main()

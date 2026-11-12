"""Bumble v2 snapshots, independent GM voices, and watchdog/session recovery."""

from array import array
import asyncio
from ctypes.util import find_library
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from lrp.app import Console
from lrp.ble import BLELink
from lrp.ble_adv_midi import (
    BUMBLE_ADDRESS, COMPANY_ID, AdvertisingMidiPlayer, decode_adv_midi,
    encode_adv_data_v2, encode_adv_note,
)
from lrp.ble_worker import advertising_midi

SILENT = [(0, 0, 0)] * 8


def snapshot(sequence=0, voices=None, program=0, session=1):
    return encode_adv_data_v2(session, sequence, program, voices or SILENT)[7:]


class StateProtocolTests(unittest.TestCase):
    def test_transmitter_vector_and_strict_version_length_velocity(self):
        voices = list(SILENT)
        voices[0], voices[1] = (64, 100, 1), (40, 90, 0)
        data = encode_adv_data_v2(0x1234, 9, 38, voices)
        self.assertEqual(len(data), 31)
        self.assertEqual(data.hex(), "0201061bffffff424d023412090026c064285a" + "0000" * 6)
        packet = decode_adv_midi(data[7:])
        self.assertEqual((packet["session"], packet["sequence"], packet["program"]), (0x1234, 9, 38))
        self.assertEqual(packet["voices"][:2], ((64, 100, 1), (40, 90, 0)))
        self.assertEqual(decode_adv_midi(encode_adv_note(1, 2, 69, 100, 500))["version"], 1)
        raw = data[7:]
        for malformed in (raw[:-1], raw + b"\0", raw[:2] + b"\x01" + raw[3:],
                          raw[:2] + b"\x03" + raw[3:], b"XX" + raw[2:],
                          raw[:9] + b"\x80" + raw[10:]):
            with self.assertRaises(ValueError):
                decode_adv_midi(malformed)
        self.assertEqual(decode_adv_midi(snapshot(program=255))["program"], 128)

    def test_full_state_loss_recovery_holds_restrikes_velocity_and_independent_release(self):
        synth = Mock()
        player = AdvertisingMidiPlayer(synth)
        voices = list(SILENT)
        voices[0], voices[1] = (60, 100, 0), (40, 90, 1)
        player.receive(snapshot(0, voices), now=0)
        self.assertEqual(synth.strike.call_count, 2)
        # Same snapshot in a later sequence: held voices must not be retriggered.
        player.receive(snapshot(3, voices), now=.1)
        self.assertEqual(synth.strike.call_count, 2)
        # A lost state is recovered by the next complete snapshot.
        voices[0], voices[1] = (60, 100, 1), (42, 90, 1)
        player.receive(snapshot(5, voices), now=.2)
        self.assertEqual(synth.strike.call_count, 4)
        self.assertEqual(synth.strike.call_args_list[-2].args[:3], (0, 60, 100))
        self.assertEqual(synth.strike.call_args_list[-1].args[:3], (1, 42, 90))
        voices[0] = (60, 30, 1)
        player.receive(snapshot(6, voices), now=.3)
        self.assertEqual(synth.strike.call_count, 4)  # Volume changes do not strike.
        voices[0] = (127, 0, 0)  # Silent note byte is ignored.
        player.receive(snapshot(7, voices), now=.4)
        synth.release.assert_called_once_with(0)
        self.assertEqual(player.voices[1], (42, 90, 1))
        voices[0] = (60, 100, 1)  # Silent -> sounding always strikes.
        player.receive(snapshot(8, voices), now=.5)
        self.assertEqual(synth.strike.call_count, 5)

    def test_rotating_programs_percussion_and_apply_on_next_strike(self):
        synth = Mock()
        player = AdvertisingMidiPlayer(synth)
        programs = [0, 38, 40, 56, 73, 80, 24, 128]
        for sequence, program in enumerate(programs):
            player.receive(snapshot(sequence, program=program), now=sequence / 100)
        self.assertEqual(player.programs, programs)
        synth.strike.assert_not_called()
        voices = [(60 + k, 100, 0) for k in range(8)]
        player.receive(snapshot(8, voices, program=0), now=.1)
        self.assertEqual([call.args[3] for call in synth.strike.call_args_list], programs)
        # seq 9 updates voice 1's program, preserving its current held note.
        player.receive(snapshot(9, voices, program=39), now=.2)
        self.assertEqual(synth.strike.call_count, 8)
        voices[1] = (61, 100, 1)
        player.receive(snapshot(10, voices, program=40), now=.3)
        synth.strike.assert_called_with(1, 61, 100, 39)

    def test_watchdog_duplicates_heartbeat_old_sessions_and_recovery_on_new_state(self):
        synth = Mock()
        player = AdvertisingMidiPlayer(synth)
        voices = [(60, 100, 0)] + SILENT[1:]
        raw = snapshot(0, voices)
        player.receive(raw, now=0)
        synth.silence.reset_mock()
        for when in (.7, 1.4, 2.1):
            self.assertIsNone(player.receive(raw, now=when))
            player.tick(now=when)
        self.assertEqual(synth.strike.call_count, 1)
        player.tick(now=3.099)
        synth.silence.assert_not_called()
        player.tick(now=3.101)
        synth.silence.assert_called_once()
        self.assertTrue(player.watchdog)
        self.assertEqual(player.watchdog_count, 1)
        self.assertFalse(any(v for _, v, _ in player.voices))
        player.tick(now=4)
        synth.silence.assert_called_once()
        player.receive(snapshot(1, voices), now=4.1)
        self.assertFalse(player.watchdog)
        self.assertEqual(synth.strike.call_count, 2)
        # New session drops held notes and forgets all previous voice programs.
        player.receive(snapshot(0, voices, program=11, session=2), now=5)
        self.assertEqual(player.programs, [11] + [None] * 7)
        last = player.last_packet
        self.assertIsNone(player.receive(raw, now=5.9))
        self.assertEqual(player.last_packet, last)
        player.tick(now=6.01)
        self.assertTrue(player.watchdog)

    def test_bad_packets_do_not_keep_notes_alive_and_v1_keeps_duration_rules(self):
        player = AdvertisingMidiPlayer(Mock())
        voices = [(60, 100, 0)] + SILENT[1:]
        player.receive(snapshot(65535, voices), now=0)
        player.receive(snapshot(0, voices), now=.1)
        player.receive(snapshot(65534, voices), now=.2)  # Old active packet is heartbeat only.
        self.assertEqual(player.sequence, 0)
        self.assertEqual(player.last_packet, .2)
        raw = snapshot(1, voices)
        player.receive(raw[:9] + b"\xff" + raw[10:], now=1)
        player.tick(now=1.21)
        self.assertTrue(player.watchdog)
        # Switching formats within a session silences the previous engine.
        player.receive(encode_adv_note(1, 1, 69, 100, 2500), now=2)
        self.assertEqual(player.version, 1)
        player.tick(now=3.5)
        self.assertEqual(player.note, 69)  # v1 is not subject to v2's 1s watchdog.
        player.tick(now=4.5)
        self.assertIsNone(player.note)
        player.receive(snapshot(2, voices), now=5)
        self.assertIsNone(player.deadline)
        self.assertEqual(player.version, 2)

    def test_eight_voice_display_in_compact_terminal(self):
        app = Console.__new__(Console)
        app.h, app.w, app.ble = 24, 64, BLELink()
        app.ble.action = "adv-midi"
        app.ble.adv_midi = dict(protocol=2, played=10, strikes=8,
                               voice_states=[(60+k, 100, 0) for k in range(8)], programs=[0,38,40,56,73,80,24,128])
        output = []
        app.put = lambda *args: output.append(args)
        app.page_title = app.button = lambda *args: None
        app.ble_advertising_page()
        for k in range(8):
            self.assertTrue(any(f"V{k} " in str(row) for row in output))
        self.assertTrue(any("DRUM" in str(row) for row in output))
        self.assertTrue(any("ACTIVE 8/8" in str(row) for row in output))


class V2WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_nameless_v2_repeats_and_soundfont_failures_are_surfaced(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                ready = asyncio.Event()
                synth = Mock(error=None)
                if failed:
                    synth.prepare_polyphony.side_effect = RuntimeError("SoundFont missing")
                events = []
                raw = snapshot(9, [(64,100,1), (40,90,0)] + SILENT[2:], program=38)

                class Scanner:
                    def __init__(self, **kwargs):
                        self.callback = kwargs["detection_callback"]

                    async def __aenter__(self):
                        for _ in range(3):
                            self.callback(SimpleNamespace(address=BUMBLE_ADDRESS, name=None),
                                          SimpleNamespace(local_name=None, manufacturer_data={COMPANY_ID: raw},
                                                          rssi=-45, tx_power=None, service_data={}, service_uuids=[]))
                        ready.set()

                    async def __aexit__(self, *args):
                        pass

                with patch("lrp.ble_worker.Synth", return_value=synth), \
                        patch("lrp.ble_worker.emit", side_effect=lambda kind, **fields: events.append(dict(kind=kind, **fields))):
                    task = asyncio.create_task(advertising_midi(Scanner))
                    await asyncio.wait_for(ready.wait(), timeout=2)
                    if failed:
                        with self.assertRaisesRegex(RuntimeError, "SoundFont missing"):
                            await task
                    else:
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                if not failed:
                    initial = next(event for event in events if event["kind"] == "adv_midi")
                    self.assertEqual(initial["protocol"], 2)
                    self.assertEqual(initial["duplicates"], 2)
                    self.assertEqual(initial["strikes"], 2)
                    self.assertEqual(synth.strike.call_count, 2)
                synth.close.assert_called_once()


class GMRenderTests(unittest.TestCase):
    def test_gm_presets_percussion_independence_headroom_and_silence(self):
        from lrp.ble_soundfont import GMVoiceBank, soundfont_path
        if not find_library("fluidsynth"):
            self.skipTest("libfluidsynth not installed")
        try:
            soundfont_path()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        bank = GMVoiceBank()
        self.addCleanup(bank.close)

        def samples():
            result = array("h")
            result.frombytes(bank.render(2400))
            if sys.byteorder != "little":
                result.byteswap()
            return result

        bank.strike(0, 60, 127, 0)
        piano = samples()
        bank.silence()
        bank.render(240)
        bank.strike(0, 60, 127, 38)
        bass = samples()
        self.assertNotEqual(piano, bass)
        bank.silence()
        bank.render(240)
        bank.strike(1, 42, 127, 128)
        bank.strike(2, 42, 127, 128)
        bank.release(1)
        # Same drum key on another independent channel must remain alive.
        self.assertGreater(max(abs(n) for n in samples()), 0)
        for voice in range(8):
            bank.strike(voice, 60, 127, 40)
        mixed = samples()
        self.assertGreater(max(abs(n) for n in mixed), 0)
        self.assertLess(max(abs(n) for n in mixed), 32767)
        bank.silence()
        bank.render(240)  # Drain the synth's internal block already rendered.
        self.assertEqual(max(abs(n) for n in samples()), 0)


if __name__ == "__main__":
    unittest.main()

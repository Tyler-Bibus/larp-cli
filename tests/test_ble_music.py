"""Music protocol, audio envelope and UI control regression checks."""
from array import array
import json
import sys
import unittest
from unittest.mock import Mock
from lrp.ble_music import decode_midi, note_name, Voice, Synth
from lrp.ble import BLELink


class MusicTests(unittest.TestCase):
    def test_timestamp_wrap_and_note_events(self):
        self.assertEqual(decode_midi(bytes([0xbf, 0xff, 0x90, 72, 78])), (8191, 0x90, 72, 78))
        self.assertEqual(decode_midi(bytes([0x80, 0x80, 0x80, 72, 0])), (0, 0x80, 72, 0))
        self.assertEqual(note_name(72), "C5")
        for raw in (b"", b"\x80\x80", bytes([0xc0, 0x80, 0x90, 72, 78]),
                    bytes([0x80, 0x80, 0x90, 128, 78])):
            with self.assertRaises(ValueError):
                decode_midi(raw)

    def test_voice_pitch_amplitude_release_and_other_note_off(self):
        voice = Voice()
        voice.message(0x90, 69, 100)
        data = array('h'); data.frombytes(voice.render(24000))
        if sys.byteorder != 'little':
            data.byteswap()
        crossings = sum(a <= 0 < b for a, b in zip(data, data[1:]))
        self.assertAlmostEqual(crossings, 440, delta=2)
        self.assertLess(max(abs(n) for n in data), 8200)
        voice.message(0x80, 60, 0)
        self.assertEqual(voice.note, 69)
        voice.message(0x90, 69, 0)
        self.assertIsNone(voice.note)
        voice.render(24000)
        self.assertEqual(voice.render(240), b'\0' * 480)
        voice.message(0x90, 72, 100)
        voice.message(0xb0, 123, 0)
        self.assertIsNone(voice.note)

    def test_close_ignores_buffered_pcm_broken_pipe_after_player_exit(self):
        synth = Synth.__new__(Synth)
        synth.stop = Mock()
        synth.process = Mock()
        synth.process.poll.return_value = 0
        synth.process.stdin.close.side_effect = BrokenPipeError("pending PCM")
        synth.thread = Mock()
        synth.close()
        synth.stop.set.assert_called_once()
        synth.thread.join.assert_called_once()
        synth.process.stdin.close.assert_called_once()

    def test_toggle_requires_link_and_tracks_worker_confirmation(self):
        link = BLELink()
        link.toggle_music()
        self.assertIn('Connect first', link.message)
        link.state = 'connected'
        link.process = Mock()
        link.process.poll.return_value = None
        link.toggle_music()
        command = json.loads(link.process.stdin.write.call_args.args[0])
        self.assertEqual(command, dict(action='music', enabled=True))
        self.assertFalse(link.music)
        link.ingest(dict(kind='music', enabled=True, message='FUNK'))
        link.toggle_music()
        self.assertFalse(json.loads(link.process.stdin.write.call_args.args[0])['enabled'])
        link.ingest(dict(kind='state', state='disconnected'))
        self.assertFalse(link.music)

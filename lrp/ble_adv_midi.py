"""Bumble advertising MIDI: v1 note events and v2 eight-voice snapshots."""

from collections import deque
import re
import struct
import time

BUMBLE_ADDRESS = "F0:F1:F2:F3:F4:F5"
BUMBLE_NAME = "Bumble"
COMPANY_ID = 0xFFFF  # Private development payload; paired with an explicit magic/version.
NOTE_PACKET = struct.Struct("<2sBHHBBH")
STATE_HEADER = struct.Struct("<2sBHHB")


def midi_address(value):
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", value):
        raise ValueError("Bumble MIDI needs a full six-byte address, e.g. F0:F1:F2:F3:F4:F5")
    return value.upper()


def decode_adv_note(data):
    raw = bytes(data)
    if len(raw) != NOTE_PACKET.size:
        raise ValueError("Bumble MIDI v1 needs exactly 11 manufacturer payload bytes")
    magic, version, session, sequence, note, velocity, duration = NOTE_PACKET.unpack(raw)
    if magic != b"BM" or version != 1:
        raise ValueError("Unknown Bumble MIDI magic/version (expected BM 01)")
    if note > 127 or velocity > 127 or (velocity and duration == 0):
        raise ValueError("Invalid Bumble MIDI note/velocity/duration")
    return session, sequence, note, velocity, duration


def encode_adv_note(session, sequence, note, velocity, duration_ms):
    """Return the value of Bleak manufacturer_data[0xffff], excluding company ID."""
    data = NOTE_PACKET.pack(b"BM", 1, session, sequence, note, velocity, duration_ms)
    decode_adv_note(data)
    return data


def encode_adv_data(session, sequence, note, velocity, duration_ms):
    """Complete 26-byte legacy AdvData, including flags, name and manufacturer AD."""
    payload = encode_adv_note(session, sequence, note, velocity, duration_ms)
    return (b"\x02\x01\x06\x07\x09Bumble\x0e\xff\xff\xff" + payload)


def decode_adv_midi(data):
    raw = bytes(data)
    if len(raw) >= 3 and raw[:3] == b"BM\x01":
        session, sequence, note, velocity, duration = decode_adv_note(raw)
        return dict(version=1, session=session, sequence=sequence, note=note,
                    velocity=velocity, duration_ms=duration)
    if len(raw) != 24 or raw[:3] != b"BM\x02":
        raise ValueError("Bumble MIDI needs BM v1 (11 bytes) or BM v2 (24 bytes)")
    _, _, session, sequence, program = STATE_HEADER.unpack(raw[:8])
    voices = tuple((raw[8 + 2*k] & 127, raw[9 + 2*k], raw[8 + 2*k] >> 7)
                   for k in range(8))
    if any(velocity > 127 for _, velocity, _ in voices):
        raise ValueError("Bumble v2 velocity bit 7 is reserved")
    return dict(version=2, session=session, sequence=sequence,
                program=128 if program & 128 else program, voices=voices)


def encode_adv_data_v2(session, sequence, program, voices):
    """Complete 31-byte AdvData; voices are eight (note, velocity, toggle) tuples."""
    if len(voices) != 8 or any(not (0 <= n <= 127 and 0 <= v <= 127 and t in (0, 1))
                               for n, v, t in voices):
        raise ValueError("Bumble v2 needs eight valid (note, velocity, toggle) tuples")
    payload = STATE_HEADER.pack(b"BM", 2, session, sequence, program)
    payload += bytes(value for n, v, t in voices for value in (n | t << 7, v))
    return b"\x02\x01\x06\x1b\xff\xff\xff" + payload


class AdvertisingMidiPlayer:
    """Apply new sequences; duplicates are heartbeat-only for v2."""
    def __init__(self, synth):
        self.synth = synth
        self.session = self.sequence = self.note = self.deadline = None
        self.retired = deque(maxlen=32)
        self.played = self.duplicates = self.invalid = 0
        self.last_error = ""
        self.version = None
        self.voices = [(0, 0, 0)] * 8
        self.programs = [None] * 8
        self.last_packet = None
        self.watchdog = False
        self.watchdog_count = self.strikes = 0

    def _reset(self):
        self.synth.silence()
        self.note = self.deadline = None
        self.voices = [(0, 0, 0)] * 8
        self.programs = [None] * 8
        self.watchdog = False

    def receive(self, data, now=None):
        now = time.monotonic() if now is None else now
        try:
            packet = decode_adv_midi(data)
        except ValueError as exc:
            self.invalid += 1
            self.last_error = str(exc)
            return None
        session, sequence = packet["session"], packet["sequence"]
        if session in self.retired:
            self.duplicates += 1
            return None
        if session == self.session:
            self.last_packet = now
            advance = (sequence - self.sequence) & 0xFFFF
            if not 0 < advance < 0x8000:
                self.duplicates += 1
                return None
        elif self.session is not None:
            self.retired.append(self.session)
        if session != self.session or packet["version"] != self.version:
            self._reset()
        self.session, self.sequence = session, sequence
        self.version = packet["version"]
        self.last_packet = now
        self.watchdog = False
        if self.version == 1:
            note, velocity, duration = packet["note"], packet["velocity"], packet["duration_ms"]
            self.synth.message(0xB0, 123, 0)
            self.note = note if velocity else None
            self.deadline = now + duration / 1000 if velocity else None
            if velocity:
                self.synth.message(0x90, note, velocity)
                self.strikes += 1
        else:
            self.synth.prepare_polyphony()
            self.programs[sequence & 7] = packet["program"]
            for k, (note, velocity, toggle) in enumerate(packet["voices"]):
                previous_note, previous_velocity, previous_toggle = self.voices[k]
                if not velocity:
                    if previous_velocity:
                        self.synth.release(k)
                elif (not previous_velocity or note != previous_note or toggle != previous_toggle):
                    self.synth.strike(k, note, velocity, self.programs[k] or 0)
                    self.strikes += 1
            self.voices = list(packet["voices"])
        self.played += 1
        self.last_error = ""
        return packet

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        if self.deadline is not None and now >= self.deadline:
            self.synth.message(0x80, self.note, 0)
            self.note = self.deadline = None
        if (self.version == 2 and not self.watchdog and self.last_packet is not None
                and now - self.last_packet >= 1):
            self.synth.silence()
            self.voices = [(0, 0, 0)] * 8
            self.watchdog = True
            self.watchdog_count += 1

    def close(self):
        try:
            self.synth.silence()
        finally:
            self.note = self.deadline = None
            self.voices = [(0, 0, 0)] * 8
            self.synth.close()

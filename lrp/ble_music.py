"""ESP32 BLE-MIDI decoding and a small, dependency-free local instrument."""

from array import array
import math
import shutil
import subprocess
import sys
import threading

MIDI_SERVICE = "03b80e5a-ede8-4b33-a751-6ce34ec4c700"
MIDI_IO = "7772e5db-3868-4112-a1a9-f2669d106bf3"
RATE = 24000


def decode_midi(data):
    """Decode the peripheral's one complete channel message per BLE packet."""
    raw = bytes(data)
    if (len(raw) != 5 or raw[0] & 0xc0 != 0x80 or not raw[1] & 0x80
            or raw[2] & 0xf0 not in (0x80, 0x90, 0xb0)
            or raw[3] > 127 or raw[4] > 127):
        raise ValueError("Invalid ESP32 MIDI packet")
    return ((raw[0] & 63) << 7 | (raw[1] & 127), raw[2], raw[3], raw[4])


def note_name(note):
    return ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")[note % 12] + str(note // 12 - 1)


class Voice:
    """Monophonic sine/harmonic voice, with an envelope to avoid clicks."""
    def __init__(self):
        self.note = None
        self.velocity = 0
        self.phase = self.level = 0.0
        self.frequency = 440.0

    def message(self, status, note, velocity):
        command = status & 0xf0
        if command == 0x90 and velocity:
            self.note, self.velocity = note, velocity
            self.frequency = 440 * 2 ** ((note - 69) / 12)
        elif ((command == 0xb0 and note in (120, 123))
              or (command in (0x80, 0x90) and self.note == note)):
            self.note = None

    def render(self, frames):
        samples = array("h")
        target = self.velocity / 127 if self.note is not None else 0
        step = 2 * math.pi * self.frequency / RATE
        for _ in range(frames):
            self.level += (target - self.level) * .009
            # Quiet by default; leave system volume entirely alone.
            value = (math.sin(self.phase) + .25 * math.sin(2 * self.phase)) * self.level * 6500
            samples.append(round(value))
            self.phase = (self.phase + step) % (2 * math.pi)
        if sys.byteorder != "little":
            samples.byteswap()
        return samples.tobytes()


class Synth:
    def __init__(self):
        executable = shutil.which("pw-play")
        if not executable:
            raise RuntimeError("Music needs PipeWire's pw-play on this computer.")
        self.voice = Voice()
        self.bank = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.error = None
        self.process = subprocess.Popen(
            [executable, "--raw", "--format", "s16", "--rate", str(RATE),
             "--channels", "1", "--latency", "40ms", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.thread = threading.Thread(target=self._play, daemon=True)
        self.thread.start()

    def message(self, status, note, velocity):
        with self.lock:
            self.voice.message(status, note, velocity)

    def strike(self, voice, note, velocity, program):
        with self.lock:
            if self.bank is None:
                from .ble_soundfont import GMVoiceBank
                self.bank = GMVoiceBank()
            self.bank.strike(voice, note, velocity, program)

    def prepare_polyphony(self):
        with self.lock:
            if self.bank is None:
                from .ble_soundfont import GMVoiceBank
                self.bank = GMVoiceBank()

    def release(self, voice):
        with self.lock:
            if self.bank is not None:
                self.bank.release(voice)

    def silence(self):
        with self.lock:
            self.voice.message(0xB0, 123, 0)
            if self.bank is not None:
                self.bank.silence()

    def _play(self):
        try:
            while not self.stop.is_set():
                with self.lock:
                    # Protocol transitions silence the other engine first.
                    pcm = (self.bank.render(RATE // 100) if self.bank is not None and self.voice.note is None
                           else self.voice.render(RATE // 100))
                self.process.stdin.write(pcm)
                self.process.stdin.flush()
        except (OSError, ValueError, RuntimeError) as exc:
            if not self.stop.is_set():
                self.error = f"Audio output stopped: {exc}"

    def close(self):
        self.stop.set()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=1)
        self.thread.join(timeout=1)
        try:
            self.process.stdin.close()
        except OSError:
            # Buffered PCM may still be pending after terminating the player.
            pass
        if getattr(self, "bank", None) is not None:
            with self.lock:
                self.bank.close()
                self.bank = None

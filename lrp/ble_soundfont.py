"""Small ctypes bridge to FluidSynth for eight independent GM voice channels."""

from array import array
import ctypes as C
from ctypes.util import find_library
import math
import os
from pathlib import Path
import sys
import threading

from .ble_music import RATE


def soundfont_path():
    override = os.environ.get("LRP_SOUNDFONT")
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise RuntimeError(f"LRP_SOUNDFONT does not exist: {path}")
        return path
    root = Path(__file__).resolve().parents[1]
    checkout = root.parent.parent if root.is_file() else root
    candidates = [checkout / ".venv/share/soundfonts/TimGM6mb.sf2"]
    for directory in ("/usr/share/soundfonts", "/usr/share/sounds/sf2", "/usr/share/sounds/sf3"):
        base = Path(directory)
        candidates += [base / name for name in ("default.sf2", "default.sf3", "FluidR3_GM.sf2", "TimGM6mb.sf2")]
        candidates += sorted(base.glob("*.sf2")) + sorted(base.glob("*.sf3"))
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError("Bumble v2 GM needs a SoundFont: install soundfont-fluid or set LRP_SOUNDFONT to a GM .sf2/.sf3 file.")


class GMVoiceBank:
    _registration_lock = threading.Lock()
    _registered = False

    def __init__(self):
        path = soundfont_path()
        library = find_library("fluidsynth")
        if not library:
            raise RuntimeError("Bumble v2 GM needs libfluidsynth (install fluidsynth).")
        self.lib = C.CDLL(library)
        pointer, integer = C.c_void_p, C.c_int
        signatures = {
            "fluid_audio_driver_register": (integer, [C.POINTER(C.c_char_p)]),
            "new_fluid_settings": (pointer, []),
            "delete_fluid_settings": (None, [pointer]),
            "fluid_settings_setnum": (integer, [pointer, C.c_char_p, C.c_double]),
            "fluid_settings_setint": (integer, [pointer, C.c_char_p, integer]),
            "new_fluid_synth": (pointer, [pointer]),
            "delete_fluid_synth": (None, [pointer]),
            "fluid_synth_sfload": (integer, [pointer, C.c_char_p, integer]),
            "fluid_synth_set_channel_type": (integer, [pointer, integer, integer]),
            "fluid_synth_program_select": (integer, [pointer, integer, integer, integer, integer]),
            "fluid_synth_noteon": (integer, [pointer, integer, integer, integer]),
            "fluid_synth_all_sounds_off": (integer, [pointer, integer]),
            "fluid_synth_write_float": (integer, [pointer, integer, pointer, integer, integer,
                                                   pointer, integer, integer]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, arguments
        with self._registration_lock:
            if not GMVoiceBank._registered:
                # LRP renders samples itself and uses pw-play. Register no
                # FluidSynth output drivers, avoiding unnecessary device probes.
                if self.lib.fluid_audio_driver_register((C.c_char_p * 1)(None)) < 0:
                    raise RuntimeError("Could not configure FluidSynth sample rendering")
                GMVoiceBank._registered = True
        self.settings = self.lib.new_fluid_settings()
        self.synth = None
        if not self.settings:
            raise RuntimeError("Could not allocate FluidSynth settings")
        try:
            self.lib.fluid_settings_setnum(self.settings, b"synth.sample-rate", RATE)
            self.lib.fluid_settings_setnum(self.settings, b"synth.gain", .8)
            self.lib.fluid_settings_setint(self.settings, b"synth.reverb.active", 0)
            self.lib.fluid_settings_setint(self.settings, b"synth.chorus.active", 0)
            self.synth = self.lib.new_fluid_synth(self.settings)
            if not self.synth:
                raise RuntimeError("Could not create FluidSynth")
            self.font = self.lib.fluid_synth_sfload(self.synth, os.fsencode(path), 0)
            if self.font < 0:
                raise RuntimeError(f"Could not load GM SoundFont: {path}")
        except Exception:
            self.close()
            raise

    def strike(self, voice, note, velocity, program):
        self.release(voice)
        percussion = bool(program & 128)
        self.lib.fluid_synth_set_channel_type(self.synth, voice, int(percussion))
        selected = self.lib.fluid_synth_program_select(
            self.synth, voice, self.font, 128 if percussion else 0, 0 if percussion else program)
        if selected < 0:
            raise RuntimeError(f"GM SoundFont has no {'drum kit' if percussion else 'program ' + str(program)}")
        if self.lib.fluid_synth_noteon(self.synth, voice, note, velocity) < 0:
            raise RuntimeError("FluidSynth could not start a Bumble voice")

    def release(self, voice):
        self.lib.fluid_synth_all_sounds_off(self.synth, voice)

    def silence(self):
        for voice in range(8):
            self.release(voice)

    def render(self, frames):
        left, right = (C.c_float * frames)(), (C.c_float * frames)()
        if self.lib.fluid_synth_write_float(self.synth, frames, left, 0, 1, right, 0, 1) < 0:
            raise RuntimeError("FluidSynth audio rendering failed")
        # Eight times the original output gain (+18 dB). Soft-limit dense chords
        # below full scale instead of hard-clipping their peaks.
        pcm = array("h", (round(32000 * math.tanh((l + r) * 32767 / (2 * 32000)))
                          for l, r in zip(left, right)))
        if sys.byteorder != "little":
            pcm.byteswap()
        return pcm.tobytes()

    def close(self):
        if self.synth:
            self.lib.delete_fluid_synth(self.synth)
            self.synth = None
        if self.settings:
            self.lib.delete_fluid_settings(self.settings)
            self.settings = None

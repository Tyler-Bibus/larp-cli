# Bumble advertising MIDI v1 + v2: sender handoff

The same receiver command accepts **v1 (11-byte note events)** and **v2 (24-byte
eight-voice snapshots)**. Both match only **F0:F1:F2:F3:F4:F5** and manufacturer
ID **0xFFFF**. No connection or scan response is used. Run `lrp --ble-adv-midi`,
or press `8` then **[v] BUMBLE MIDI**; `d` stops audio and discovery.

## v2 polyphonic state broadcast

Each packet describes the complete state of eight independent monophonic voices.
No local name is included. The complete legacy **31-byte AdvData** is:

```text
02 01 06                Flags
1B FF FF FF <24 bytes>  Manufacturer AD / company 0xFFFF
```

The 24-byte manufacturer value, excluding the company bytes:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 2 | Magic `BM` / `42 4D` |
| 2 | 1 | Version `02` |
| 3 | 2 | Session, u16 little-endian |
| 5 | 2 | Sequence, u16 little-endian |
| 7 | 1 | Program for voice `sequence & 7` |
| 8 + 2k | 1 | Voice k: note in bits 0–6, strike toggle in bit 7 |
| 9 + 2k | 1 | Voice k: velocity 0–127; bit 7 must be 0 |

Program bits 0–6 are a **zero-based GM program** (0 piano, 38 synth bass 1).
Bit 7 means percussion; low bits are then ignored. Drum note numbers are GM
keys. Velocity 0 silences that voice; its note byte is ignored. Each voice has
its own synth channel, including independent channels for simultaneous drums.

Newly accepted sequences update the one rotating program entry, then apply all
eight voice states. Unknown programs use piano 0. A program change on a held
voice takes effect at its next strike. A note starts or re-strikes only if its
toggle changed, note changed, or previous velocity was 0. Changes to velocity
alone do not retrigger or change the held sound's volume. A silent state releases
that voice. Other voices remain independent. Sound is mixed with a soft limiter
to keep dense chords below full scale. Output gain is boosted by 18 dB relative
to the original v2 mix.

A new session releases all voices and resets program/state knowledge. Session
and sequence handling is shared with v1: duplicates/older sequences are not
applied; wrap 65535 → 0 works; forward jumps of 32768 or more are rejected;
late packets from the last 32 retired sessions are ignored. Valid packets of the
active session, **including duplicates**, refresh the v2 heartbeat. Invalid
packets and retired sessions cannot keep notes alive.

After **1000 ms** without an active-session packet, the watchdog releases all
voices. The next newly accepted snapshot restores its full state; duplicates
remain heartbeat-only, including after a watchdog release. The UI shows the
gap and all eight voices' notes, velocities and learned programs. v1 retains its
duration-based release and is not subject to the v2 watchdog. Changing versions
on an advancing sequence silences the previous format's voices.

### v2 sender rules

1. Allocate at most eight fixed monophonic parts. Use a new session per boot,
   song restart or loop, avoiding the last 32 IDs.
2. Send eight silent preamble snapshots, sequences 0–7, to teach all programs.
   Hold each for several advertising intervals.
3. At each musical state change, increment sequence and replace AdvData with
   the complete new snapshot. Flip a voice's toggle on every new onset, including
   repeated notes or drum hits. For silent voices, send note 0 and retain the
   previous toggle. Unused voices stay silent with program 0.
4. Repeat the identical packet until the next change, including the same program
   byte. Program rotation depends only on `sequence & 7`, never retransmission
   count. Keep broadcasting while notes are held so the watchdog stays alive.
5. Send a new all-silent snapshot for at least a second at the end. Quantize state
   changes so each gets several advertising opportunities at your controller's
   supported interval. There is no jitter buffer, clock sync, or recovery of a
   strike whose snapshots were all missed.

### v2 encoder and transmitter test vector

```python
import struct

def adv_data_v2(session, sequence, program, voices):
    # Eight tuples: (MIDI note, velocity, strike toggle).
    assert len(voices) == 8
    assert all(0 <= n <= 127 and 0 <= v <= 127 and t in (0, 1)
               for n, v, t in voices)
    body = b"".join(bytes([n | (t << 7), v]) for n, v, t in voices)
    packet = struct.pack("<2sBHHB", b"BM", 2, session, sequence, program) + body
    return bytes.fromhex("02 01 06 1b ff ff ff") + packet

v = [(0, 0, 0)] * 8
v[0], v[1] = (64, 100, 1), (40, 90, 0)
assert adv_data_v2(0x1234, 9, 38, v).hex() == (
    "0201061bffffff424d023412090026c064285a" + "0000" * 6
)
```

`lrp.ble_adv_midi.encode_adv_data_v2` implements this encoder; `decode_adv_midi`
validates and distinguishes both formats.

### GM audio setup

v2 uses **libfluidsynth** and a **General MIDI .sf2/.sf3 SoundFont**, rendered
through the existing `pw-play` output. No additional Python package is needed.
The current checkout has TimGM6mb installed in
`.venv/share/soundfonts/TimGM6mb.sf2` with its copyright file alongside it; these
are ignored local dependencies, not bundled into `dist/lrp`.

For another installation, install FluidSynth and a GM SoundFont, or set
`LRP_SOUNDFONT=/absolute/path/to/gm.sf2`. LRP checks that override, the checkout's
TimGM6mb path, and standard `/usr/share/soundfonts`, `/usr/share/sounds/sf2`, and
`/usr/share/sounds/sf3` directories. A missing/unloadable font is reported on the
BLE page. v1 continues using the built-in instrument without these dependencies.

Audio backend references: [FluidSynth GM preset selection](https://www.fluidsynth.org/api/group__midi__messages.html),
[independent drum/melodic channel types](https://www.fluidsynth.org/api/group__channel__setup.html),
[TimGM6mb package source](https://deb.debian.org/debian/pool/main/t/timgm6mb-soundfont/).

## v1 compatibility protocol

Implement a **monophonic melody broadcast**, with no pairing, GATT connection,
or scan response required. LRP plays notes locally through its PipeWire synth.
This is a custom advertising protocol, not standard BLE-MIDI over GATT.

### Device and receiver

- Advertiser address: **F0:F1:F2:F3:F4:F5** (six bytes; the corrected address).
- Complete local name: **Bumble**, included in the same advertising data as music.
- LRP matches the address exactly; it does not accept another device by name.
- Start receiver: `lrp --ble-adv-midi`, or BLE page `8` → **[v] BUMBLE MIDI**.
- In-app command: `:ble adv-midi`; override: `:ble adv-midi AA:BB:CC:DD:EE:FF`.
- Stop: `d` or `:ble disconnect`. The button switches from an existing BLE task.
- Requires the optional Bleak environment and PipeWire's `pw-play`.

### Wire format

Send normal legacy advertisements, for example `ADV_NONCONN_IND`, on advertising
channels 37/38/39. Use Manufacturer Specific Data (AD type **0xFF**) with private
development company ID **0xFFFF**, encoded **FF FF**. Use this agreed development
identifier for this prototype; it is not a company assignment to Bumble.

The manufacturer value **after** the two company bytes is exactly **11 bytes**:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 2 | Magic ASCII `BM` = `42 4D` |
| 2 | 1 | Version `01` |
| 3 | 2 | Session ID, unsigned 16-bit little-endian |
| 5 | 2 | Sequence number, unsigned 16-bit little-endian |
| 7 | 1 | MIDI note number, 0–127 (60 = C4; 69 = A4) |
| 8 | 1 | MIDI velocity, 0–127; **0 silences the instrument** |
| 9 | 2 | Note duration in milliseconds, unsigned 16-bit little-endian |

Positive velocity requires duration **1–65535 ms**. Velocity 0 represents a rest
or stop; its duration does not schedule anything in the receiver. The sender
controls rest timing by waiting until the next event. Set note=0 for rests/stops.
Only one note sounds at once; every new event replaces the previous note.

Complete **26-byte AdvData**, with three AD structures:

```text
02 01 06                         Flags
07 09 42 75 6D 62 6C 65          Complete local name "Bumble"
0E FF FF FF <11-byte BM packet>   Manufacturer AD
```

`0E` is the count of bytes following the length byte: type (1), company ID (2),
and BM packet (11). Do not add another company ID inside the BM packet.
Bleak exposes the 11-byte packet as `manufacturer_data[0xFFFF]`.

This is **AdvData only**. The BLE transmitter must still supply the link-layer
header, six-byte AdvA, CRC, channel-specific whitening, etc. A BLE stack handles
these separately. If constructing a raw PDU, the AdvA bytes are
`F5 F4 F3 F2 F1 F0` in transmission byte order; set the address-type/header bits
consistently with the configured advertiser address (e.g. static random).

### Encoding a song

1. Extract one melody line from the song; flatten chords to one note or arpeggiate.
   Program changes, instruments, sustain pedals, pitch bend, and chords are not
   supported. Velocity controls loudness, not instrument selection.
2. Resolve the MIDI tempo map into note onset times and durations in milliseconds.
   For a constant tempo, `quarter_ms = 60000 / BPM`. Emit explicit velocity-0
   events at the beginning of rests when necessary.
3. Choose a new session ID per boot, song restart, or loop. Do not reuse one of
   the last 32 sessions while the receiver keeps running. Start sequence at 0;
   increment for **every new event**, including consecutive identical notes/rests.
4. At each event's onset, replace the advertising payload with that event. Repeat
   the **identical session, sequence, note, velocity, and duration** across all
   advertising channels and intervals until the next event. Never increment the
   sequence per retransmission. Use a supported advertising interval (e.g. 100 ms)
   and aim for several receptions per event; simplify fast passages as needed.
5. At song end, advertise a new velocity-0 stop event repeatedly. A lost stop
   cannot leave a note on indefinitely: the receiver also releases each note
   after its advertised duration. Durations above 65535 ms require tied segments
   with new sequence numbers.

The receiver plays upon first receipt; **there is no future-note buffer or clock
synchronization**. Do not broadcast an entire song upfront. Duplicate or older
sequence numbers are ignored. Sequence wrap `65535 → 0` works; a forward jump of
32768 or more is rejected, so use a new session after a very long interruption.
Late packets from a retired session are ignored (32 sessions retained).
Repeated packets do not extend or retrigger a note. OS discovery may delay,
merge, or drop advertisements, so playback is best-effort and can have jitter
or missing notes. It cannot recover an event it never received.

### Reference encoder and test vector

```python
import struct

def adv_data(session, sequence, note, velocity, duration_ms):
    assert 0 <= session <= 65535 and 0 <= sequence <= 65535
    assert 0 <= note <= 127 and 0 <= velocity <= 127
    assert 0 <= duration_ms <= 65535
    assert velocity == 0 or duration_ms > 0
    music = struct.pack("<2sBHHBBH", b"BM", 1, session, sequence,
                        note, velocity, duration_ms)
    return bytes.fromhex("02 01 06 07 09 42 75 6d 62 6c 65 0e ff ff ff") + music

# Session 1, event 0: A4, velocity 100, 500 ms.
assert adv_data(1, 0, 69, 100, 500).hex() == (
    "020106070942756d626c650effffff424d01010000004564f401"
)

# At the next onset, event 1: C5, velocity 100, 500 ms.
next_note = adv_data(1, 1, 72, 100, 500)
# Then event 2: stop; repeat this at the end of the song.
stop = adv_data(1, 2, 0, 0, 0)
```

The repository also provides `lrp.ble_adv_midi.encode_adv_note` (11-byte value)
and `encode_adv_data` (complete AdvData). Follow this exact v1 format; arbitrary
three-byte MIDI messages or five-byte BLE-MIDI GATT packets are not accepted.

AD layout references: [Bluetooth SIG data types](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/CSS_v12/out/en/supplement-to-the-bluetooth-core-specification/data-types-specification.html),
[Bleak advertisement fields](https://bleak.readthedocs.io/en/stable/backends/index.html#bleak.backends.scanner.AdvertisementData).

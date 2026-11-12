# LRP / Reality Operations Division

A homemade, full-screen terminal operating-system larp. Giant emergency lettering,
mint-green telemetry, a red panic state, and a deeply unqualified fictional
intelligence feed. Built for Arch Linux + Konsole using only Python's standard library.

The default console now runs a 20 FPS animation loop: falling data, interference
waves, scanning beams, torn headline lettering, scrolling warning bands, a live
waveform, and a rotating 4D cope reactor. Crashout mode accelerates the effects
and transmission feed; farming aura triggers a temporary shockwave bulletin.

**New: Fly lab and brofists.** Press `6` for a decorative, pulsing fruit-fly brain
alongside a flapping, walking ASCII fly. Press `s` in the lab to feed it a banana.
Click **BROFIST**, or press `f`, to animate two fists colliding with an impact burst,
earn 67 fictional aura, and excite the fly. `f` or `Esc` dismisses the effect.
In calm or frozen mode, the brofist displays a static impact instead of motion.
The control room alternates its reactor with a miniature brain preview.

The control room runs a fast, autonomous **graph cascade**: 22–26 scattered nodes
with cyclic cross-links, racing edge pulses, red acquisition flashes, and mint
traversal trails. Each sweep randomly chooses real BFS or DFS and a starting node,
visits the entire cluster, then rebuilds the graph. Nodes advance every 55 ms;
crashout accelerates the cascade to 1.8× speed. There are no traversal controls.
Space, calm mode, typing, and leaving the control room pause the cascade.
At smaller terminal sizes the graph fills the main content area.
Fictional transmissions remain on `2` / Wire.

**Reality Operations is catastrophically overfunded and handles extremely minor
problems.** Press `7` for Operations, with clickable experiments and fictional
receipts. The graph is now an **Overthinking Accelerator**: `:overthink sounds good`
reconstructs a harmless message using excessive BFS/DFS machinery. Each sweep
offers a fresh interpretation and zero clarification.

- `:lockin` collides motivation with deadline, usually producing a funded side
  quest. Actual productivity is a rare, unexplained anomaly.
- `:audit` opens the Aura Revenue Service's scanner and receipt. Aura farming
  sometimes triggers an audit automatically. Brofists count as charity credits;
  credits are consumed once, and the fictional aura charge is at most 67.
- `:swarm` deploys 16 more little guys. More agents bring more meetings, a
  framework, a context-hoarding goblin, and eventually delegation back to you.
- `:breach` opens or seals fifth-dimensional storage: cables, misplaced chargers,
  and the occasional USB connector that fits correctly the first time.
- `:nonchalance` slows the display, declares you UNBOTHERED, and spends 12 active
  simulation seconds checking whether anyone noticed. The experiment fails loudly.
- `:incident` opens an ordered case on the Wire and Operations screen. Cases
  also begin automatically, with a beat every 3.2 active seconds. `:incident next`
  manually advances a beat, including in calm/frozen mode. Random traffic stays
  quiet during a case so the jokes have room to land.

Bananas now fund the fly's career: after 2 feeds it becomes a neural operator,
after 5 an incident commander, and after 9 the interim CTO. Promotions and office
counters survive restarts. Fly Doom is mandatory executive training. Kitty holds
absolute shutdown authority: petting it contains panic, seals storage, stops
nonchalance, closes active cases, dismisses brofists, and stops Fly Doom.
Petting it keeps the display animated and preserves any explicit pause or calm mode.
Operations receipts wrap and scroll with arrows/Page Up/Page Down; small terminals
prioritize readable receipts over the animated experiment stage.

[Watch the graph cascade](docs/graph-cascade.gif)

[Watch the fly and brofist animations](docs/fly-brofist.gif)

**Fly Doom:** in the fly lab, click **PLAY DOOM** or press `d`. A tiny original
Doom-style autoplay scene replaces only the ASCII fly's pane: moving raycast
corridors, an imp, muzzle flashes, health, and kills. The HUD portrait is the fly,
with focused, firing, hurt, and happy faces. Click **RETURN FLY** or press `d` again
to restore its enclosure. This is a procedural mockup, not the Doom engine; no
WADs, downloads, or original game assets are included. Autoplay pauses when you
leave the fly lab, freeze the console, use calm mode, or type a command.

[Watch Fly Doom](docs/fly-doom.gif) · [Meet the kitty](docs/kitty.png)

A blinking, tail-swishing kitty lives in the footer and control room. Press `k`
or click the kitty to pet it and get happy eyes and purrs.

![Control room, captured from a real pseudo-terminal](docs/control-room.png)

[Watch the live animation capture](docs/motion-preview.gif)

```sh
lrp
```

Maximize Konsole for the full control-room layout. **120 × 40** or larger looks best;
64 × 24 is the minimum. Use Konsole's normal monospace font and a UTF-8 locale.
The app fills the terminal and restores the previous screen on exit. It does not
replace Bash or start automatically when you open a terminal.

## Controls

| Key | Action |
| --- | --- |
| `1`–`8`, `Tab` | Control room, wire, dossier, vault, manual, fly lab, operations, BLE |
| `a` in BLE | Start continuous, unfiltered advertising discovery |
| `d` in BLE | Stop Bluetooth work; keep captured results visible |
| `f`, click **BROFIST** | Fist bump, impact animation, +67 aura, fly reaction |
| `s` in fly lab | Feed banana; animate a mock neural response |
| `d` in fly lab, click **PLAY DOOM** | Toggle fly Doom autoplay / ASCII fly |
| `k`, click kitty | Pet kitty; invoke its fictional emergency shutdown authority |
| `p` | Trigger or contain a crashout |
| `a` | Farm aura; sometimes being seen trying loses points |
| `g` | Touch grass; stabilize the simulation |
| `Space`, click **PAUSE / RESUME** | Freeze or resume the simulation; resuming also turns calm mode off |
| `m` | Toggle persistent calm mode |
| `b` | Enter a **real interactive Bash session**; `exit` returns to LRP |
| `n` | Write and save a local note |
| `:` or `/` | Open the internal command line |
| `?` | Field manual |
| `q`, `Ctrl-C`, `Ctrl-D` | Exit and restore the terminal |
| Arrows, Page Up/Down | Scroll long screens |

The command line supports editing, history, and Tab completion. `Esc` cancels input.

```text
alias NIGHTSHIFT
note remember the main quest
panic
contain
aura
grass
calm
shell
help
quit
```

Other directives: `home`, `feed`, `dossier`, `vault`, `status`, `pause`, and `resume`.
Also: `fly`, `brofist`, `stimulate`, `doom`, and `kitty`. Tabs and labeled buttons accept mouse clicks
in Konsole; hold Shift to select terminal text normally.
Only `shell` / `b` launches Bash; fictional directives are not shell commands.
Office directives: `ops`, `overthink [message]`, `lockin`, `audit`, `swarm`,
`breach`, `nonchalance`, and `incident [next]`.
Bash inherits the launch directory and sets `LRP_SESSION=1`. Changes inside that
child shell, including `cd` and exported variables, last for that Bash session.

## BLE advertising / FPGA bring-up

```sh
lrp --ble-sniff
```

Or press `8`, then `a`, or enter `:ble sniff`. Discovery includes **all advertisers**,
including unnamed devices and devices with unknown addresses or service UUIDs.
The display shows current and peak received signal strength (**RSSI in dBm**),
report counts, time since last reception, and decoded manufacturer/service data.
Arrows scroll the recent advertisers. Press `d` to stop; `q` exits and stops discovery.
Space/calm mode only pause the fictional effects; radio reception continues.
Stop the current BLE task before starting another one.

The optional adapter backend uses Bleak:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r ble-requirements.txt
```

The checkout automatically uses `.venv/bin/python` for Bluetooth work. Set
`LRP_BLE_PYTHON` to use another Python with Bleak. Your Bluetooth adapter must be
enabled and accessible through the OS Bluetooth service.

The primary advertising channels are **37 / 2402 MHz**, **38 / 2426 MHz**, and
**39 / 2480 MHz** ([Bluetooth SIG channel reference](https://www.bluetooth.com/wp-content/uploads/2020/10/EN-Understanding_Reliability.pdf)).
A normal Bluetooth adapter reports decoded discovery data without the receiving
channel or raw CRC. In adapter mode, the channel rows therefore say **unavailable**;
counts are OS reports, which may combine ADV and scan-response data or suppress
duplicates. Discovery uses active scanning and can send scan requests; it does not
pair or connect. Payload fields are OS-decoded data, not raw on-air PDUs.
`UI dropped` counts events discarded if the terminal cannot keep up (for example,
while inside its Bash session); displayed totals then undercount received input.

For actual channel measurements, use a configured BLE RF sniffer with TShark
(for example, an nRF Sniffer with its Wireshark extcap installed):

```sh
tshark -D                       # Find your RF sniffer's interface identifier
lrp --ble-interface '<interface identifier>'
lrp --ble-capture capture.pcapng # Inspect an existing RF capture
```

Inside the app: `:ble sniff <interface identifier>` or `:ble replay <capture path>`.
TShark must be on `PATH` and have capture permissions. Select a BLE RF sniffer
interface; a laptop HCI interface still cannot supply per-packet RF channels.
Configure the sniffer's advertising channel sweep in its own capture settings.
LRP reads [nRF metadata](https://www.wireshark.org/docs/dfref/n/nordic_ble.html) and
[BLE RF metadata](https://www.wireshark.org/docs/dfref/b/btle_rf.html), displays
per-channel reception counts/RSSI and reported CRC failures, and excludes scan
requests, scan responses, and connection requests from advertising packet counts.
Missing measurements remain unknown. Captures on secondary channels are included
in the unknown/secondary total. Replay ages describe time since LRP read a record.

For an unknown FPGA, compare the advertiser list with its transmitter off and on,
and watch for a nearby signal whose RSSI changes when you move it. A received
advertisement demonstrates reception, but does not certify the whole transmitter.
No reports **does not prove RF silence**: incorrect whitening, access address,
modulation, timing, or CRC can make an FPGA transmission invisible to discovery.
RF sniffers may also discard bad packets; arbitrary RF power requires an SDR or
spectrum analyzer. One receiver can miss transmissions while listening elsewhere.

The existing project telemetry remains under `:ble scan`, `:ble connect [name or
address]`, and `:ble music` on the BLE page.

### Bumble: play notes directly from advertisements

Run `lrp --ble-adv-midi`, press `8` then **[v] BUMBLE MIDI**, or enter
`:ble adv-midi`. This listens **only to F0:F1:F2:F3:F4:F5**, without connecting,
and plays BM v1 or v2 manufacturer payloads through PipeWire's `pw-play`.
The button stops any current BLE task before switching. `d` stops radio and audio.
Override the address with `lrp --ble-adv-midi AA:BB:CC:DD:EE:FF` or
`:ble adv-midi AA:BB:CC:DD:EE:FF`.

v2 supports **eight independent voices with General MIDI programs and drums**.
The screen shows each voice's note, velocity and program. Complete state snapshots
recover changes after lost packets; strike toggles distinguish held notes from
repeated hits. Duplicate packets keep held notes alive without retriggering them.
After a one-second signal gap, the watchdog releases all voices. Only the address
is matched, so v2 advertisements need no local name.

v1's 11-byte monophonic events remain supported with their original duration and
duplicate rules. v2 requires libfluidsynth and a GM SoundFont; TimGM6mb is configured
locally in this checkout's ignored `.venv/share/soundfonts` directory. On another
installation, install a GM SoundFont or set `LRP_SOUNDFONT=/path/to/gm.sf2`.
v1 keeps its built-in synth. Arbitrary MIDI bytes require the agreed BM wrapper.
Give the song-encoding agent the complete
[sender handoff, byte layout, timing rules, and reference encoder](docs/bumble-adv-midi.md).

## Options

```sh
lrp --calm       # No automatic fictional feed / waveform updates
lrp --ascii      # ASCII headline lettering and borders
lrp --no-boot    # Skip the brief boot banner
lrp --doctor    # Terminal and installation diagnostics
lrp --ble-sniff # Live advertising discovery, including unnamed devices
lrp --ble-adv-midi # Play Bumble's advertised note stream without connecting
lrp --version
```

No full-screen flashing or terminal bell. Calm mode leaves the real clock and host
readings active; Space freezes the simulation and all effects for the current
session. Animation also freezes while you type a command or note; the status shows
**INPUT / Esc cancel** until you execute or cancel it. The clickable status shows
**FROZEN / RESUME** or **CALM / RESUME** when updates are stopped. Space or `:resume`
clears both pause and calm mode so animation actually resumes.

## Install or remove

Requires `python` on Arch (including `curses`) and Bash. The base console needs no
pip packages, root access, background service, network connection, or remote
repository. Optional BLE discovery needs Bleak and the OS Bluetooth service;
RF capture needs TShark and a supported sniffer.

```sh
python3 install.py
```

This links `~/.local/bin/lrp` to `bin/lrp` in this checkout. Keep the checkout in
place, or rerun the installer after moving it. The installer refuses to overwrite
an existing unrelated command. If your Bash does not already include this directory,
add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` and reopen Konsole.

```sh
python3 install.py --uninstall
```

Uninstalling preserves source and notes. No Konsole settings are changed.

## What is real

The clock, host memory/load/uptime, saved notes, and Bash are real. Everything about
aura, threats, transmissions, intelligence, and alerts is fictional. The program
makes no network requests. No live Instagram integration is involved.

The fly lab is a visual mockup inspired by the
[fruit-fly simulation meme](https://knowyourmeme.com/memes/fruit-fly-brain-simulations)
and [connectome visualizations](https://flywire.ai/gallery). Its 120 generated
points, connections, firing effects, and ASCII fly movements are purely decorative.
It loads no neural datasets and makes no claim to simulate a real brain or behavior.

Callsign, aura, launch count, calm preference, banana budget, agent count, aura
audits, unused brofist credits, cases opened, and the most recent 200 notes are
stored in `~/.local/share/lrp/state.json`, or `$XDG_DATA_HOME/lrp/state.json` when set.
Writes are atomic and the state file is private to the user. An unreadable state
file is preserved and the session becomes read-only. A failed save is shown on screen.
Prefer one active LRP session: simultaneous sessions have independent state and the
last writer wins. Notes are limited to 1,000 characters; callsigns to 24.

## Development

```sh
python3 -m lrp
python3 -m unittest discover -s tests -v
python3 build.py
./dist/lrp --version
```

`build.py` creates an executable, standalone Python zipapp at `dist/lrp` using
only the standard library. Copy it anywhere and run it with Python 3 available.
The installed `~/.local/bin/lrp` launcher points directly at this checkout and
uses source changes immediately; reinstalling is unnecessary after a rebuild.

The terminal integration tests use a real pseudo-terminal and isolated temporary
storage. Existing `html/` mockups are preserved as earlier design material.

The visual direction follows the supplied emergency-status reference: black,
oversized red lettering, mint broadcast captions. All transmission text is original.
Terminology research included [Know Your Meme's aura-farming explainer](https://knowyourmeme.com/editorials/guides/what-is-aura-farming-the-viral-internet-slang-and-its-memes-explained).

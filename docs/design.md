# Terminal art direction

The reference is an emergency broadcast, not a conventional software dashboard.
The main visual event is oversized, five-row pixel lettering inside a red warning
frame. The composition stays legible while its content insists that everything is
going terribly wrong.

- Void: `#000000` (xterm 16), explicit background independent of Konsole theme.
- Emergency: `#ff005f` (197), headlines and alert strips.
- Phosphor: `#87ffaf` (121), control labels and broadcast captions.
- Carrier: `#5f8787` (66), structure and secondary readings.
- Caution: `#ffd75f` (221), actions and operator feedback.
- Paper: `#d7ffff` (195), longer reading text.

The user's terminal font supplies the body typography. Hand-defined bitmap glyphs
provide large display lettering with no font downloads. Center the alert bulletin;
left-align feed traffic and actual machine readings. At 108 columns the host panel
appears beside the warning. At smaller widths the warning takes the whole screen.

```text
LRP / REALITY OPERATIONS                         clock
EMERGENCY BROADCAST SYSTEM
[1 CONTROL]  2 WIRE  3 DOSSIER  4 VAULT  5 MANUAL

       REPORT ON TERMINAL AURA DISCHARGE    HOST / REAL
    +----------------------------------+  operator
    |         C O O K E D              |  memory
    +----------------------------------+  load
     POSSIBLE SIMILARITY WITH A SKILL ISSUE uptime
    ///////// RECALCULATING ////////////   [b] Bash

INTERCEPT / FICTIONAL WIRE                 VIBE TELEMETRY
timestamp / severity / incident             threat / cope
                                          waveform
operator feedback
command line / key hints
```

Review against the brief: terminal-native, panic-red and mint rather than generic
hacker green; an emergency bulletin is the primary shape, not uniform dashboard
cards. Deliberate all-caps mimic the supplied visual reference.

The second pass deliberately increases chaos: 20 FPS falling carrier packets,
crossing acquisition brackets, two counter-scrolling warning tapes, a scanning
headline with short horizontal tearing bursts, waveform interference, and a
rotating tesseract. Crashout drives the visual clock at 2.4x speed and floods the
fictional wire. Input, Space, and calm mode freeze the visual clock. Keep the
actual host readings and keyboard controls in stable positions. No full-screen
flashing or bells.

The fly lab adds a fourth motif: an illustrative four-lobe point cloud with moving
spike activity beside a separate ASCII fly. Four sprite frames animate its wings
and six legs while it drifts around the enclosure. Banana and brofist actions
increase the displayed firing activity; neither uses biological data. A brofist
overlay sends two mirrored ASCII fists inward and expands a star burst from the
impact. Both keyboard and terminal mouse input activate the same actions.

Fly Doom replaces the fly enclosure in place. The neighboring mock brain stays
visible. A procedural ASCII raycaster creates scrolling brick corridors with an
original imp sprite and weapon animation. A compact bottom HUD carries the fly's
four facial expressions, health, and kill counter. The minimum-size layout uses a
one-line face. The kitty remains visible in the footer, with a larger three-line
sprite in the control room; petting changes its eyes and adds a purr.

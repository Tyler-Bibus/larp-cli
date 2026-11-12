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

The control room replaces its lower wire preview with an autonomous graph
cascade. Each connected cloud has 22–26 scattered nodes with local cross-links
and cycles, without a root or hierarchical rows. Real BFS or DFS is randomly
selected each sweep, with one node visited every 55 ms and only 180 ms between
clouds. Crashout accelerates it by 1.8x. Dark mesh connections sit behind bright
red-to-mint traversal trails, racing white packets, and bracketed node flashes.
An emergency ticker replaces the old tutorial and manual search controls.
The emergency headline, host readings, and telemetry remain at 90 x 40 or larger
(host readings need 108 columns). Smaller terminals give the graph the main
content area. Space, calm mode, input, and leaving Control freeze the cascade.

The cascade now reconstructs harmless messages for the Overthinking Accelerator:
each regenerated graph proposes another interpretation without clarification.
Operations is a seventh screen for the overfunded agency. Its red-framed stage
shows colliding motivation/deadline labels, an aura audit scanner, a meeting swarm,
and rotating dimensional cable storage. Receipts remain stable below the stage;
at less than 30 rows the receipt takes priority and wraps with scroll controls.
Nonchalance slows visual motion and changes the headline to UNBOTHERED, then fails
after 12 active seconds. Case transmissions advance in order at 3.2-second
intervals without random feed interruptions. Input, calm mode, and Space freeze
all experiment/case clocks; explicit commands still work and `incident next`
provides a static way to read every beat. The fly's banana-funded promotions save
locally. Petting kitty invokes its absolute fictional shutdown authority while
leaving the animation clock running unless the operator explicitly paused it.
The status is a clickable PAUSE/RESUME control; resume clears both freeze and calm
mode. Command editing displays INPUT with an Esc hint so its temporary pause is
visible.

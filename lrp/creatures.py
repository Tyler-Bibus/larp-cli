"""Original fly-brain theater and terminal sprites; no biological model or data."""

from functools import lru_cache
import math
import random

from .motion import segment
from .bureau import fly_rank


@lru_cache(maxsize=1)
def brain_cloud():
    rng = random.Random(670)
    nodes = []
    # Four decorative lobes, arranged like the silhouette of a fly brain.
    for center, spread, count in ((-.65, .31, 24), (-.23, .40, 36),
                                   (.23, .40, 36), (.65, .31, 24)):
        for _ in range(count):
            theta, z = rng.uniform(0, math.tau), rng.uniform(-1, 1)
            radius = rng.uniform(.35, 1)
            circle = math.sqrt(1 - z * z)
            nodes.append((center + math.cos(theta) * circle * spread * radius,
                          math.sin(theta) * circle * .66 * radius,
                          z * .4 * radius))
    edges = set()
    for i, point in enumerate(nodes):
        closest = sorted((sum((a - b) ** 2 for a, b in zip(point, other)), j)
                         for j, other in enumerate(nodes) if i != j)[:2]
        for _, j in closest:
            edges.add(tuple(sorted((i, j))))
    return tuple(nodes), tuple(sorted(edges))


def project_brain(seconds, columns, rows):
    nodes, edges = brain_cloud()
    angle = math.sin(seconds * .4) * .42
    c, s = math.cos(angle), math.sin(angle)
    projected = []
    for x, y, z in nodes:
        x, z = x * c + z * s, z * c - x * s
        perspective = 2.8 / (3 - z)
        px = round((columns - 1) * (.5 + x * perspective * .48))
        py = round((rows - 1) * (.5 + y * perspective * .63))
        projected.append((max(0, min(columns - 1, px)), max(0, min(rows - 1, py))))
    return projected, edges


FLY_FRAMES = (
    (r"  .--.   .--.  ", r" (    \ /    ) ", r"  `---(o)---'  ",
     r"   \ /|#|\ /   ", r"    / |#| \    ", r"   /  `V'  \   ", r"  /   / \   \  "),
    (r"    \\   //    ", r"     \\ //     ", r"  .---(o)---.  ",
     r" /   /|#|\   \ ", r"    / |#| \    ", r"   _/ `V' \_   ", r"      / \      "),
    (r"       |       ", r"  .----|----.  ", r" (____(o)____) ",
     r"     /|#|\     ", r"  __/ |#| \__  ", r"      `V'      ", r"    _/   \_    "),
    (r"    //   \\    ", r"   //     \\   ", r"  `---(o)---'  ",
     r"   _/ |#| \_   ", r"     /|#|\     ", r"    / `V' \    ", r"   /       \   "),
)

FIST = ("       ____ ", "  ____/ __ |", " / __ | __ |", "| |__|| __ |",
        "|     |____|", " \\________/ ")


class CreaturePanels:
    def button(self, y, x, label, command, style="bar"):
        self.put(y, x, label, style)
        self.buttons.append((y, x, min(self.w - 1, x + len(label)), command))

    def neural_cloud(self, y, x, columns, rows):
        if columns < 4 or rows < 3:
            return
        points, edges = project_brain(self.fx_time, columns, rows)
        tick = int(self.fx_time * 9)
        excited = self.fx_time < self.fly_stimulus_until or (self.doom_enabled and self.doom.firing)
        # Batch the field into rows; only bright spikes need individual writes.
        grid = [[" " for _ in range(columns)] for _ in range(rows)]
        for a, b in edges:
            for px, py in segment(points[a], points[b]):
                grid[py][px] = ":" if (a + tick) % 11 == 0 else "."
        for row, cells in enumerate(grid):
            self.put(y + row, x, "".join(cells), "ghost", columns)
        for i, (px, py) in enumerate(points):
            firing = (i * 7 - tick) % (17 if excited else 23) < (7 if excited else 3)
            self.put(y + py, x + px, "*" if firing else "+" if i % 3 == 0 else ".",
                     "amber" if firing and excited else "red" if firing else "mint" if i % 3 == 0 else "dim")

    def fly_sprite(self, y, x, columns, rows):
        if columns < 17 or rows < 8:
            return
        frame = int(self.fx_time * 9) % len(FLY_FRAMES)
        dx = round((columns - 16) * (.5 + .35 * math.sin(self.fx_time * 1.5)))
        dy = round(max(0, rows - 8) * (.5 + .4 * math.sin(self.fx_time * 2)))
        excited = self.fx_time < self.fly_stimulus_until
        for row, line in enumerate(FLY_FRAMES[frame]):
            self.put(y + dy + row, x + dx, line, "amber" if excited else "mint", columns - dx)

    def flylab(self):
        rank = fly_rank(self.store.data["bananas"])
        self.page_title("FRUIT FLY / " + rank, "MOCK CONNECTOME / DECORATIVE FIRING / NO BIOLOGICAL MODEL / BANANA-FUNDED OFFICE")
        split = self.w * 3 // 5
        end = self.h - 8
        panel_h = end - 9
        self.box(9, 1, panel_h, split - 2, "BRAIN / MOCKUP")
        self.neural_cloud(11, 3, split - 6, max(3, panel_h - 4))
        self.box(9, split, panel_h, self.w - split - 1, "FLY DOOM / MOCK" if self.doom_enabled else "ASCII FLY")
        if self.doom_enabled:
            self.doom_panel(10, split + 2, self.w - split - 5, panel_h - 2)
        elif panel_h >= 11:
            self.fly_sprite(11, split + 2, self.w - split - 5, panel_h - 4)
        else:
            # A compact, animated fly for the minimum 64 x 24 terminal.
            sprite = (r"\_/(o)\_/", r"--(o)--", r"/_\(o)/_\ ")[int(self.fx_time * 9) % 3]
            self.center(11, sprite, "mint", split + 2, self.w - split - 5)
            self.center(12, r" /|\ ", "dim", split + 2, self.w - split - 5)
        label = "DOPAMINE: BRO DETECTED" if self.fx_time < self.fly_stimulus_until else (
            "THOUGHT: BANANA" if int(self.fx_time / 3) % 2 else "THOUGHT: CAN I RUN DOOM?")
        if self.doom_enabled:
            label = "THOUGHT: RIP AND BUZZ / " + self.doom.expression
        self.put(end, 3, label, "amber", self.w - 6)
        raster = "".join("|" if (i * 17 + int(self.fx_time * 12)) % 29 < 4 else "." for i in range(self.w - 6))
        self.put(end + 1, 3, raster, "red", self.w - 6)
        self.button(self.h - 6, 3, " [f] BROFIST ", "brofist", "alert")
        self.button(self.h - 6, 19, " [s] FEED BANANA ", "stimulate")
        self.button(self.h - 6, 38, " [d] RETURN FLY " if self.doom_enabled else " [d] PLAY DOOM ", "doom", "alert")
        self.put(self.h - 5, 3, f"BANANA BUDGET {self.store.data['bananas']} / {rank} / CTO RESPONSE: landed on monitor", "dim", self.w - 6)

    def brofist_overlay(self):
        if self.brofist_started is None or self.editing:
            return
        elapsed = self.fx_time - self.brofist_started
        if elapsed >= 2.8:
            self.brofist_started = None
            return
        w = min(70, self.w - 6)
        h = 14
        x, y = (self.w - w) // 2, max(5, (self.h - h) // 2)
        for row in range(y, y + h):
            self.fill(row, x, w, "mint")
        self.box(y, x, h, w, "BROFIST PROTOCOL", "red")
        impact = elapsed >= .85
        self.center(y + 2, "BRO CONNECTION ESTABLISHED" if impact else "INITIATING BRO-TO-BRO HANDSHAKE", "amber", x, w)
        distance = max(0, round((1 - min(1, elapsed / .85)) * (w // 2 - 15)))
        center = x + w // 2
        left = center - 13 - distance
        right = center + 1 + distance
        mirror = str.maketrans("/\\()[]{}", "\\/)(][}{")
        for row, art in enumerate(FIST):
            self.put(y + 4 + row, left, art, "mint")
            self.put(y + 4 + row, right, art.translate(mirror)[::-1], "red")
        if impact:
            radius = 2 + round(min(1, (elapsed - .85) / .8) * (w // 2 - 6))
            for i in range(12):
                angle = i * math.tau / 12
                px = center + round(math.cos(angle) * radius)
                py = y + 7 + round(math.sin(angle) * min(3, radius / 4))
                self.put(py, px, "*", "amber")
            self.center(y + 10, " +67 AURA / THE FLY APPROVES ", "amber", x, w)
        self.center(y + 12, "[f / Esc] dismiss", "dim", x, w)

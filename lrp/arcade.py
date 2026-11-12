"""Original Doom-style terminal theater. No Doom engine, WAD, or game assets."""

import math


MAP = (
    "##############",
    "#............#",
    "#............#",
    "#............#",
    "#....##......#",
    "#....##..##..#",
    "#........##..#",
    "#............#",
    "#..##........#",
    "#..##...##...#",
    "#.......##...#",
    "#............#",
    "#............#",
    "##############",
)

FACES = {
    "LOCKED IN": (r"  \   /  ", " (oO Oo) ", r"  \_v_/  "),
    "PEW PEW": (r"  \   /  ", " (>O O<) ", r"  \_W_/  "),
    "OUCH": (r"  \   /  ", " (xO Ox) ", r"  \_o_/  "),
    "RIP & BUZZ": (r"  \   /  ", " (^O O^) ", r"  \_w_/  "),
}


class FlyDoom:
    def __init__(self):
        self.time = 0.0

    def advance(self, elapsed):
        self.time += max(0.0, elapsed)

    @property
    def phase(self):
        return self.time % 4.8

    @property
    def kills(self):
        return int(self.time // 4.8)

    @property
    def health(self):
        return 100 - int(self.phase // 1.2) * 9

    @property
    def firing(self):
        return .66 < self.phase % 1.2 < .88

    @property
    def expression(self):
        if 2.0 < self.phase < 2.45:
            return "OUCH"
        if self.phase > 4.05:
            return "RIP & BUZZ"
        if self.firing:
            return "PEW PEW"
        return "LOCKED IN"

    def camera(self):
        route = ((2.5, 2.5), (11.5, 2.5), (11.5, 11.5), (2.5, 11.5))
        leg = self.time / 12
        index = int(leg) % 4
        start, end = route[index], route[(index + 1) % 4]
        f = leg % 1
        x = start[0] + (end[0] - start[0]) * f
        y = start[1] + (end[1] - start[1]) * f
        angle = math.atan2(end[1] - start[1], end[0] - start[0]) + math.sin(self.time * .8) * .18
        return x, y, angle

    def scene(self, columns, rows):
        """A small raycaster: perspective walls, moving floor, procedural textures."""
        px, py, direction = self.camera()
        grid = [[" " for _ in range(columns)] for _ in range(rows)]
        for column in range(columns):
            angle = direction + (column / max(1, columns - 1) - .5) * 1.15
            cx, cy = math.cos(angle), math.sin(angle)
            distance = .05
            while distance < 20:
                x, y = int(px + cx * distance), int(py + cy * distance)
                if not (0 <= x < 14 and 0 <= y < 14) or MAP[y][x] == "#":
                    break
                distance += .13
            depth = max(.15, distance * math.cos(angle - direction))
            wall_h = min(rows * 3, max(1, round(rows * 1.4 / depth)))
            top = (rows - wall_h) // 2
            bottom = top + wall_h
            for row in range(rows):
                if top <= row <= bottom:
                    brick = int((px + cx * distance + py + cy * distance) * 3)
                    grid[row][column] = ("=" if (row - top) % 4 == 0 else
                                         "|" if brick % 4 == 0 else "#" if depth < 3 else ":")
                elif row > bottom:
                    grid[row][column] = "." if (column + row * 3 + int(self.time * 10)) % 7 < 2 else " "
                elif (column + row * 7) % 23 == 0:
                    grid[row][column] = "."
        return ["".join(row) for row in grid]


class ArcadePanels:
    def doom_panel(self, y, x, columns, rows):
        game = self.doom
        hud_rows = 4 if rows >= 9 else 2
        scene_rows = max(1, rows - hud_rows)
        for row, line in enumerate(game.scene(columns, scene_rows)):
            self.put(y + row, x, line, "dim", columns)
        # Original imp sprite advances and disappears after the fly's volley.
        if scene_rows >= 6 and game.phase < 4.05:
            imp = (r"\^   ^/", " (O O) ", " /|#|\\ ", r" /   \ ")
            ex = x + max(0, min(columns - 7, columns // 2 - 3 + round(math.sin(game.time) * columns * .18)))
            ey = y + max(0, scene_rows // 2 - 2)
            for row, line in enumerate(imp):
                self.put(ey + row, ex, line, "red", columns - (ex - x))
        if scene_rows >= 4:
            center = x + columns // 2
            self.put(y + scene_rows // 2, center, "+", "amber")
            self.put(y + scene_rows - 2, center - 3, " /==\\ ", "white")
            self.put(y + scene_rows - 1, center - 3, " |##| ", "white")
            if game.firing:
                self.put(y + scene_rows - 3, center - 3, "*<!!>*", "amber")
        hud = y + scene_rows
        self.fill(hud, x, columns, "alert", f" HP {game.health:3}  KILLS {game.kills:03}")
        if hud_rows == 4:
            for row, line in enumerate(FACES[game.expression]):
                self.center(hud + 1 + row, line, "red" if game.expression == "OUCH" else "amber", x, columns)
            self.put(hud + 2, x, "FLY", "mint", 3)
            self.put(hud + 3, x, "AUTO", "dim", 4)
            if columns >= 35:
                self.put(hud + 2, x + columns - 11, game.expression, "amber", 11)
        else:
            self.center(hud + 1, FACES[game.expression][1] + " " + game.expression, "amber", x, columns)

    def kitty(self, y, x, columns):
        happy = self.fx_time < self.kitty_petted_until
        blink = int(self.fx_time * 2) % 9 == 0
        eyes = "^.^" if happy else "-.-" if blink else "o.o"
        tail = ("~", "~~", "~", "_")[int(self.fx_time * 3) % 4]
        for row, line in enumerate((r" /\_/\ ", f"( {eyes} ) {tail}", " > ^ <  " + ("purrr <3" if happy else "mrrp"))):
            self.put(y + row, x, line, "amber" if happy else "mint", columns)

    def kitty_button(self):
        happy = self.fx_time < self.kitty_petted_until
        eyes = "^.^" if happy else "-.-" if int(self.fx_time * 2) % 9 == 0 else "o.o"
        tail = ("~", "~~", "~", "_")[int(self.fx_time * 3) % 4]
        self.button(self.h - 1, self.w - 21, f" [k] = {eyes} = {tail} ", "kitty", "amber" if happy else "mint")

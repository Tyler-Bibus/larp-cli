"""Overfunded fictional experiments, persistent office lore, and ordered cases."""

from collections import deque
import math
import random

from .content import INCIDENTS, OVERTHINK_SUBJECTS
from .motion import segment, tesseract
from .state import clean


def fly_rank(bananas):
    if bananas >= 9:
        return "INTERIM CTO"
    if bananas >= 5:
        return "INCIDENT COMMANDER"
    if bananas >= 2:
        return "NEURAL OPERATOR"
    return "UNQUALIFIED INTERN"


class Bureau:
    """All clocks use active simulation seconds; explicit actions work while paused."""

    def __init__(self, data, rng=None):
        self.data = data
        self.rng = rng if rng is not None else random.Random()
        self.time = self.started = 0.0
        self.mode = "swarm"
        self.report = ("REALITY OPERATIONS / MINOR PROBLEMS, MAJOR FUNDING",
                       f"{data['agents']:,} little guys. one task. nobody owns it.",
                       "Choose an experiment above. All activity is fictional.")
        self.subject = OVERTHINK_SUBJECTS[0]
        self.nonchalant_until = 0.0
        self.storage_open = False
        self.case_title = "NO ACTIVE CASE"
        self.case_id = data["cases"]
        self.case_queue = deque()
        self.case_lines = []
        self.next_beat = 0.0
        self.next_case = 18.0
        self.next_case_index = data["cases"] % len(INCIDENTS)

    @property
    def nonchalant(self):
        return self.time < self.nonchalant_until

    @property
    def case_active(self):
        return bool(self.case_queue)

    def record(self, mode, lines):
        self.mode = mode
        self.started = self.time
        self.report = tuple(lines)

    def action(self, command, argument=""):
        if command == "overthink":
            self.subject = clean(argument)[:80] or self.rng.choice(OVERTHINK_SUBJECTS)
            self.record(command, (f'ANALYZING: "{self.subject}"',
                                 "All interpretations connected. None verified.",
                                 "Result delivery: Control / [1]."))
            return [("INTEL", self.report[0])]
        if command == "lockin":
            productive = self.rng.randrange(20) == 0
            outcome = "ACTUAL PRODUCTIVITY" if productive else self.rng.choice((
                "reorganizing your dotfiles", "building a better task tracker",
                "researching the perfect keyboard", "renaming every project folder",
                "optimizing the animation of your productivity dashboard"))
            self.record(command, ("LOCKED-IN COLLIDER / MOTIVATION x DEADLINE",
                                 "NEW PARTICLE: " + outcome,
                                 "UNEXPLAINED ANOMALY. Alert the fly." if productive else
                                 "ORIGINAL TASK: untouched. Side quest: funded."))
            return [("INTEL", "collision successful."),
                    ("WARN" if productive else "FAULT", self.report[1]),
                    ("COPE", self.report[2])]
        if command == "audit":
            self.data["audits"] = min(999999, self.data["audits"] + 1)
            credit = min(67, self.data["brofists"] * 7)
            fine = 67 - credit
            self.data["aura"] = max(-999999, self.data["aura"] - fine)
            self.data["brofists"] = 0
            self.record(command, (f"AURA REVENUE SERVICE / RECEIPT {self.data['audits']:06d}",
                                 "CLAIM: effortless nonchalance",
                                 "EVIDENCE: practiced entrance seven times. DEDUCTION DENIED.",
                                 f"BROFIST CHARITY CREDIT: {credit} / AURA DUE: {fine}",
                                 f"BALANCE: {self.data['aura']:+,}. Please retain your imaginary receipt."))
            return [("WARN", line) for line in self.report]
        if command == "swarm":
            self.data["agents"] = min(999999, self.data["agents"] + 16)
            count = self.data["agents"]
            politics = ("ORACLE-01 opened a meeting about closing meetings." if count < 128 else
                        "GOBLIN-09 hoards all context. Escalation contact: the fly." if count < 192 else
                        "INTERN-INFINITY delegated the original task back to you.")
            self.record(command, (f"{count:,} LITTLE GUYS DEPLOYED / MANAGEMENT +900%",
                                 f"{count - 1:,} awaiting requirements. 1 writing a framework.",
                                 politics, "ACTUAL WORK COMPLETED: pending committee approval."))
            return [("INTEL", line) for line in self.report]
        if command == "breach":
            self.storage_open = not self.storage_open
            if self.storage_open:
                item = ("a USB connector that fits on the first attempt" if self.rng.randrange(20) == 0 else
                        self.rng.choice(("8,041 HDMI cables. ALL SLIGHTLY TOO SHORT",
                                         "a box marked 'misc'. contents: another box marked 'misc'",
                                         "every charger except the one you need",
                                         "vibes.bak. last modified before the incident")))
                lines = ("THE FIFTH DIMENSION / STORAGE BREACH", "RECOVERED: " + item,
                         "COSMIC POWER: infinite. Closet space: somehow insufficient.")
            else:
                lines = ("DIMENSIONAL STORAGE SEALED", "Reality restored from vibes.bak.",
                         "Cable inventory remains somebody else's problem.")
            self.record(command, lines)
            return [("FAULT" if self.storage_open else "COPE", line) for line in self.report]
        if command == "nonchalance":
            self.nonchalant_until = self.time + 12.0
            self.record(command, ("NONCHALANCE DEPLOYED / UNBOTHERED",
                                 "checking whether anyone noticed...",
                                 "Allocated 98% of compute to appearing effortless."))
            return [("COPE", self.report[0])]
        if command == "incident":
            if argument and argument.lower() != "next":
                return [("WARN", "Usage: incident [next]")]
            if argument.lower() == "next" and self.case_active:
                events = self.beat()
            elif self.case_active:
                events = [("INTEL", f"CASE {self.case_id:04d} still open. Use :incident next.")]
            else:
                events = self.start_case()
            self.record(command, self.case_lines)
            return events
        raise ValueError("unknown experiment: " + command)

    def start_case(self):
        self.case_title, sequence = INCIDENTS[self.next_case_index]
        self.next_case_index = (self.next_case_index + 1) % len(INCIDENTS)
        self.data["cases"] = min(999999, self.data["cases"] + 1)
        self.case_id = self.data["cases"]
        self.case_lines = []
        self.case_queue = deque(sequence)
        return self.beat()

    def beat(self):
        if not self.case_queue:
            return []
        tag, line = self.case_queue.popleft()
        self.case_lines.append(line)
        self.next_beat = self.time + 3.2
        if not self.case_queue:
            self.next_case = self.time + 18.0
        if self.mode == "incident":
            self.report = tuple(self.case_lines)
        return [(tag, f"CASE {self.case_id:04d} / {self.case_title}: {line}")]

    def advance(self, elapsed):
        was_nonchalant = self.nonchalant
        self.time += max(0.0, elapsed)
        events = []
        if was_nonchalant and not self.nonchalant:
            if self.mode == "nonchalance":
                self.record("nonchalance", ("NONCHALANCE CONTAINMENT FAILED",
                                          "CRITICAL: nobody noticed.",
                                          "Effort audit: extremely bothered."))
            events.append(("FAULT", "CRITICAL: nobody noticed. Effort audit: extremely bothered."))
        if self.case_active and self.time >= self.next_beat:
            events.extend(self.beat())
        elif not self.case_active and self.time >= self.next_case:
            events.extend(self.start_case())
        return events

    def shutdown(self):
        self.storage_open = False
        self.nonchalant_until = self.time
        self.case_queue.clear()
        self.next_case = self.time + 18.0
        self.record("kitty", ("EMERGENCY SHUTDOWN AUTHORIZED BY KITTY",
                              "All experiments contained. The cat's jurisdiction is absolute.",
                              "Recovery plan: pet the incident commander."))


class BureauPanels:
    def operations(self):
        bureau = self.bureau
        title = f"CASE {bureau.case_id:04d} / {bureau.case_title}" if bureau.mode == "incident" else "REALITY OPERATIONS / OVERFUNDED AGENCY"
        self.page_title(title, "MINOR PROBLEMS / MAJOR FUNDING / FICTIONAL EXPERIMENTS / [k] emergency kitty")
        x = 3
        for label, command in ((" THINK ", "overthink"), (" COLLIDE ", "lockin"),
                               (" AUDIT ", "audit"), (" +GUYS ", "swarm"), (" STORAGE ", "breach")):
            self.button(9, x, label, command, "alert" if bureau.mode == command else "soft")
            x += len(label) + 1
        self.button(10, 3, " UNBOTHERED ", "nonchalance", "soft")
        self.button(10, 16, " CASE / NEXT ", "incident next", "soft")
        self.put(10, 31, f"FLY: {fly_rank(self.store.data['bananas'])}", "amber", self.w - 34)
        # Small rooms prioritize the receipt; larger rooms keep the animated stage.
        if self.h >= 30:
            art_height = min(11, max(4, self.h - 31))
            self.box(12, 1, art_height + 2, self.w - 2, bureau.mode.upper(), "red")
            self.experiment_art(13, 3, self.w - 6, art_height)
            start = 14 + art_height
        else:
            start = 12
        available = max(1, self.h - 5 - start)
        lines = [part for line in bureau.report for part in self.wrap_text(line, self.w - 6)]
        self.offset = min(self.offset, max(0, len(lines) - available))
        for row, line in enumerate(lines[self.offset:self.offset + available]):
            self.put(start + row, 3, line, "amber" if self.offset + row == len(lines) - 1 else "white", self.w - 6)
        hint = " / Up,Down: receipt" if len(lines) > available else " / :help"
        self.put(self.h - 5, 3, f"AGENTS {self.store.data['agents']:,} / BANANAS {self.store.data['bananas']} / AUDITS {self.store.data['audits']}" + hint, "dim", self.w - 6)

    def experiment_art(self, y, x, columns, rows):
        bureau = self.bureau
        age = bureau.time - bureau.started
        clock = self.fx_time
        middle = y + rows // 2
        if bureau.mode == "lockin":
            approach = min(1.0, age / .85) if not (self.calm or self.paused) else 1.0
            left = round((columns // 2 - 12) * approach)
            right = columns - 10 - left
            self.put(middle, x + left, "MOTIVATION", "mint", 10)
            self.put(middle, x + right, "DEADLINE", "red", 8)
            self.center(middle - 1, " * COLLISION * " if approach == 1 else ">>>     <<<", "amber", x, columns)
            self.center(middle + 1, "SIDE QUEST PARTICLE DETECTOR", "dim", x, columns)
        elif bureau.mode == "audit":
            scanner = int(clock * 17) % columns
            for row in range(rows):
                self.put(y + row, x + scanner, "|", "red")
            self.center(middle - 1, "[ EFFORTLESS ENTRANCE ]", "mint", x, columns)
            self.center(middle, "[ SEVEN REHEARSALS    ]", "amber", x, columns)
            self.center(middle + 1, "[ DEDUCTION DENIED    ]", "red", x, columns)
        elif bureau.mode == "breach":
            points, edges = tesseract(clock * .55, columns, rows)
            for a, b, _ in edges:
                for px, py in segment(points[a], points[b]):
                    self.put(y + py, x + px, ".", "dim")
            for px, py in points:
                self.put(y + py, x + px, "+", "mint")
            self.center(middle, "[ CABLE STORAGE OPEN ]" if bureau.storage_open else "[ vibes.bak SEALED ]", "alert", x, columns)
        elif bureau.mode == "swarm":
            count = min(80, self.store.data["agents"])
            for node in range(count):
                angle = node * 2.399 + clock * .15
                radius = math.sqrt((node + .5) / count)
                px = round((columns - 1) * (.5 + .45 * radius * math.cos(angle)))
                py = round((rows - 1) * (.5 + .45 * radius * math.sin(angle)))
                self.put(y + py, x + px, "*" if node == 9 else "+", "red" if node == 9 else "dim")
            self.center(middle, "[ MEETING ABOUT THE MEETING ]", "mint", x, columns)
        elif bureau.mode == "nonchalance":
            self.center(middle - 1, "U N B O T H E R E D", "mint", x, columns)
            self.center(middle + 1, "checking whether anyone noticed..." if bureau.nonchalant else "nobody noticed. requesting attention.", "amber", x, columns)
        elif bureau.mode == "kitty":
            self.kitty(y, x + columns // 2 - 7, 20)
        elif bureau.mode == "overthink":
            self.center(middle - 1, '"' + bureau.subject + '"', "mint", x, columns)
            self.center(middle + 1, "26 interpretations / 0 clarification / [1] live graph", "amber", x, columns)
        else:
            self.center(middle - 1, "[ CASE FILE / EMOTIONAL MOBILIZATION ]", "mint", x, columns)
            progress = len(bureau.case_lines)
            self.center(middle + 1, "[" + "#" * progress + "." * max(0, 6 - progress) + "]", "amber", x, columns)

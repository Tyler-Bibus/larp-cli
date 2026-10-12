"""Fast, autonomous BFS/DFS cascades through connected, cyclic node clouds."""

from collections import deque
import math
import random

from .motion import marquee, segment
from .content import OVERTHINK_RESULTS


class GraphSearch:
    STEP_DELAY = .055
    RESET_DELAY = .18

    def __init__(self, rng=None):
        self.rng = rng if rng is not None else random.Random()
        self.generation = 0
        self.time = 0.0
        self.elapsed = 0.0
        self.regenerate()

    def regenerate(self):
        self.nodes = list(range(self.rng.randint(22, 26)))
        self.cloud = {}
        # Best-candidate sampling spreads nodes through an oval, without ranks
        # or a privileged root. Positions remain steady during each cascade.
        for node in self.nodes:
            candidates = []
            for _ in range(40):
                angle = self.rng.uniform(0, math.tau)
                radius = math.sqrt(self.rng.random())
                candidates.append((math.cos(angle) * radius, math.sin(angle) * radius))
            self.cloud[node] = max(candidates, key=lambda p: min(
                ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 for q in self.cloud.values()),
                default=1))
        edges = set()
        for node in self.nodes:
            nearest = sorted((n for n in self.nodes if n != node), key=lambda n:
                             sum((a - b) ** 2 for a, b in zip(self.cloud[node], self.cloud[n])))
            # The earlier-node link guarantees connectivity; local cross-links
            # create real cycles and several routes through the cluster.
            neighbors = nearest[:3]
            if node:
                neighbors.append(next(n for n in nearest if n < node))
            for other in neighbors:
                edges.add(tuple(sorted((node, other))))
        self.edges = sorted(edges)
        self.neighbors = {n: [] for n in self.nodes}
        for a, b in self.edges:
            self.neighbors[a].append(b)
            self.neighbors[b].append(a)
        for neighbors in self.neighbors.values():
            self.rng.shuffle(neighbors)
        self.labels = {n: chr(65 + n) for n in self.nodes}
        self.start = self.rng.choice(self.nodes)
        self.generation += 1
        self._positions = {}
        self.restart(self.rng.choice(("BFS", "DFS")))

    def restart(self, algorithm):
        self.algorithm = algorithm
        self.pending = deque([(self.start, None)])
        self.discovered = {self.start}
        self.visited = []
        self.parents = {}
        self.arrivals = {}
        self.current = None
        self.complete = False
        self.elapsed = 0.0

    @property
    def frontier(self):
        return {n for n, _ in self.pending if n not in self.parents}

    def step(self):
        if self.complete:
            return
        while self.pending:
            node, parent = self.pending.popleft() if self.algorithm == "BFS" else self.pending.pop()
            if node not in self.parents:
                break
        else:
            self.complete = True
            return
        self.current = node
        self.visited.append(node)
        self.parents[node] = parent
        self.arrivals[node] = self.time
        neighbors = self.neighbors[node]
        for other in neighbors if self.algorithm == "BFS" else reversed(neighbors):
            # BFS claims a node when queued. DFS claims it when popped so its
            # order follows a true depth-first walk even around cross-links.
            if other in (self.discovered if self.algorithm == "BFS" else self.parents):
                continue
            self.pending.append((other, node))
            self.discovered.add(other)
        self.complete = len(self.visited) == len(self.nodes)

    def advance(self, elapsed):
        self.elapsed += max(0.0, elapsed)
        while self.elapsed >= (self.RESET_DELAY if self.complete else self.STEP_DELAY):
            delay = self.RESET_DELAY if self.complete else self.STEP_DELAY
            self.elapsed -= delay
            self.time += delay
            if self.complete:
                remaining = self.elapsed
                self.regenerate()
                self.elapsed = remaining
            else:
                self.step()

    def positions(self, columns, rows):
        key = columns, rows
        if key not in self._positions:
            points = {}
            candidates = [(x, y) for y in range(rows) for x in range(1, columns - 1)]
            for node, (px, py) in self.cloud.items():
                desired = (1 + (px + 1) * (columns - 3) / 2, (py + 1) * (rows - 1) / 2)
                points[node] = min(candidates, key=lambda p:
                                   (p[0] - desired[0]) ** 2 + 4 * (p[1] - desired[1]) ** 2)
                nx, ny = points[node]
                candidates = [(x, y) for x, y in candidates if y != ny or abs(x - nx) >= 4]
            self._positions[key] = points
        return self._positions[key]


class SearchPanels:
    def search_panel(self, y, x, height, columns):
        search = self.search
        size = columns - 4
        self.box(y, x, height, columns, "OVERTHINK ACCELERATOR", "red")
        state = "STILL UNSURE" if search.complete else "RECONSTRUCTING INTENT"
        self.put(y + 1, x + 2,
                 f"{search.algorithm} >> {state}  /  CYCLE {search.generation:04d}", "alert", size)
        bureau = getattr(self, "bureau", None)
        subject = bureau.subject if bureau is not None else "sounds good"
        self.put(y + 2, x + 2, f'ANALYZING: "{subject}"', "amber", size)
        points = search.positions(size, height - 6)
        clock = search.time + search.elapsed
        # Render the dark mesh first, then recent traversal edges and packets.
        trails = []
        for a, b in search.edges:
            cells = segment(points[a], points[b])
            for px, py in cells:
                self.put(y + 3 + py, x + 2 + px, ".", "ghost")
            child = b if search.parents.get(b) == a else a if search.parents.get(a) == b else None
            if child is not None and clock - search.arrivals[child] < .32:
                trails.append((cells, child))
        for cells, child in trails:
            if points[child] == cells[0]:
                cells = cells[::-1]
            age = clock - search.arrivals[child]
            style = "red" if age < .11 else "mint" if age < .22 else "dim"
            for px, py in cells:
                self.put(y + 3 + py, x + 2 + px, "+" if age < .11 else ":", style)
            px, py = cells[min(len(cells) - 1, int(age / .32 * len(cells)))]
            self.put(y + 3 + py, x + 2 + px, "*", "white")
        frontier = search.frontier
        for node, (px, py) in points.items():
            label, style = " " + search.labels[node] + " ", "dim"
            if node in search.parents:
                label, style = "(" + search.labels[node] + ")", "mint"
            if node in frontier:
                label, style = "{" + search.labels[node] + "}", "amber"
            if clock - search.arrivals.get(node, -100) < .16:
                label, style = "[" + search.labels[node] + "]", "white"
            if node == search.current:
                label, style = "[" + search.labels[node] + "]", "alert"
            self.put(y + 3 + py, x + 1 + px, label, style)
        self.put(y + height - 3, x + 2,
                 f"IDEAS {len(search.visited):02d}/{len(search.nodes)} / LINKS {len(search.edges):02d} / "
                 + " > ".join(search.labels[n] for n in search.visited[-7:]), "mint", size)
        self.put(y + height - 2, x + 2, marquee(
            OVERTHINK_RESULTS[(search.generation - 1) % len(OVERTHINK_RESULTS)] + " / ZERO CLARIFICATION", size, clock * 12), "red", size)

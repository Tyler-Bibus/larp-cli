"""Time-driven terminal geometry; render frames without random state or sleeps."""

import math


def marquee(text, columns, offset):
    tape = text + "     ///     "
    start = int(offset) % len(tape)
    return (tape * (columns // len(tape) + 2))[start:start + columns]


def tesseract(seconds, columns, rows):
    """Rotate in four dimensions, project to 3D then into terminal cells."""
    points = []
    for index in range(16):
        p = [1.0 if index & (1 << axis) else -1.0 for axis in range(4)]
        for a, b, speed in ((0, 3, .73), (1, 2, .51), (0, 2, .37)):
            angle = seconds * speed
            c, s = math.cos(angle), math.sin(angle)
            p[a], p[b] = p[a] * c - p[b] * s, p[a] * s + p[b] * c
        depth = 2.6 / (3.6 - p[3])
        px, py, pz = (v * depth for v in p[:3])
        perspective = 3.4 / (4.4 - pz)
        x = round((columns - 1) / 2 + px * perspective * columns * .23)
        y = round((rows - 1) / 2 + py * perspective * rows * .23)
        points.append((max(0, min(columns - 1, x)), max(0, min(rows - 1, y))))
    edges = [(i, i ^ (1 << axis), axis) for i in range(16) for axis in range(4)
             if i < i ^ (1 << axis)]
    return points, edges


def segment(a, b):
    x, y = a
    dx, dy = b[0] - x, b[1] - y
    steps = max(abs(dx), abs(dy), 1)
    return [(round(x + dx * n / steps), round(y + dy * n / steps)) for n in range(steps + 1)]

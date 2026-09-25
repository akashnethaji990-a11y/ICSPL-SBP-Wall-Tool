# -*- coding: utf-8 -*-
"""Offline tests for pyRevit/SBP.extension/lib/sbp_geom.py (no Revit needed).

Run:  python tests/test_sbp_geom.py
Lengths in mm. D1200, c/c 900, gap 150 unless a test says otherwise.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pyRevit", "SBP.extension", "lib"))
import sbp_geom as G

D, S = 1200.0, 900.0


def poly(ptsxy, closed=False, step=100.0):
    segs = list(zip(ptsxy[:-1], ptsxy[1:])) + ([(ptsxy[-1], ptsxy[0])] if closed else [])
    out = []
    for a, b in segs:
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(2, int(math.ceil(L / step)) + 1)
        t = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        out.append(([(a[0] + (b[0] - a[0]) * k / (n - 1.0), a[1] + (b[1] - a[1]) * k / (n - 1.0)) for k in range(n)], [t] * n))
    return out


def circle(r, step=100.0):
    n = int(math.ceil(2 * math.pi * r / step))
    return [([(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)],
             [(-math.sin(2 * math.pi * i / n), math.cos(2 * math.pi * i / n)) for i in range(n)])]


def centre(samples, closed, pick, gap=150.0, step=100.0):
    dist = gap + D / 2
    side = G.pick_side(samples, pick)
    path = G.offset_path(samples, closed, side, dist)
    w = int(math.ceil(4 * math.pi * dist / step)) + 20
    path = G.remove_loops(path, w)
    if closed:
        h = len(path) // 2
        path = G.remove_loops(path[h:] + path[:h], w)
    return path


def seg_dist(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2))
    return math.hypot(p[0] - a[0] - t * ax, p[1] - a[1] - t * ay)


def min_line_dist(centres, ptsxy, closed=False):
    segs = list(zip(ptsxy[:-1], ptsxy[1:])) + ([(ptsxy[-1], ptsxy[0])] if closed else [])
    return min(min(seg_dist(c, a, b) for a, b in segs) for c in centres)


def run_case(samples, closed, pick, gap=150.0):
    path = centre(samples, closed, pick, gap)
    c, step, total = G.divide(path, closed, S)
    k = G.hard_soft(len(c))
    return c, k, step


# ---------------------------------------------------------------- same numbers as the first offline tests (HISTORY 6)
def test_straight_10m():
    c, k, step = run_case(poly([(0, 0), (10000, 0)]), False, (5000, 1000))
    assert len(c) == 13 and k.count("HARD") == 7 and k.count("SOFT") == 6, (len(c), k.count("HARD"))
    assert abs(step - 833.33) < 0.1, step
    assert k[0] == "HARD" and k[-1] == "HARD"


def test_circle_r10():
    c, k, step = run_case(circle(10000), True, (20000, 0))
    assert len(c) == 76 and k.count("HARD") == 38, len(c)
    c, k, step = run_case(circle(10000), True, (0, 0))
    assert len(c) == 66 and k.count("HARD") == 33, len(c)


def test_square_20m():
    sq = [(0, 0), (20000, 0), (20000, 20000), (0, 20000)]
    c, k, step = run_case(poly(sq, True), True, (10000, -1000))
    assert len(c) == 96, len(c)
    c, k, step = run_case(poly(sq, True), True, (10000, 1000))
    assert len(c) == 84, len(c)
    assert min_line_dist(c, sq, True) >= 750 - 1


# ---------------------------------------------------------------- inside-corner bug (crossing exactly on a sample point)
def test_inside_corner_gap_200_stays_off_the_line():
    L = [(0, 8000), (0, 0), (12000, 0)]
    for step in (50.0, 100.0):
        path = centre(poly(L, step=step), False, (5000, 1000), gap=200.0, step=step)
        c, stp, total = G.divide(path, False, S)
        assert min_line_dist(c, L) >= 800 - 1, (step, min_line_dist(c, L))


def test_all_piles_750_from_the_line():
    L = [(0, 8000), (0, 0), (12000, 0)]
    for pick in ((5000, 1000), (5000, -1000)):
        c, k, step = run_case(poly(L), False, pick)
        assert min_line_dist(c, L) >= 750 - 1


# ---------------------------------------------------------------- start / end types (joining other walls)
def test_hard_soft_start():
    assert G.hard_soft(4) == ["HARD", "SOFT", "HARD", "SOFT"]
    assert G.hard_soft(3, "SOFT") == ["SOFT", "HARD", "SOFT"]


def test_layout_ends_free_ends_are_hard():
    path = centre(poly([(0, 0), (10000, 0)]), False, (5000, 1000))
    c, k, step, total = G.layout_ends(path, False, S)
    assert len(c) == 13 and k[0] == "HARD" and k[-1] == "HARD"


def test_layout_ends_start_soft_end_hard():
    path = centre(poly([(0, 0), (10000, 0)]), False, (5000, 1000))
    c, k, step, total = G.layout_ends(path, False, S, "SOFT", "HARD")
    assert k[0] == "SOFT" and k[-1] == "HARD" and (len(c) - 1) % 2 == 1
    assert step <= S + 1e-6
    for a, b in zip(k, k[1:]):
        assert a != b


def test_layout_ends_continue_from_existing_pile():
    # the pile at the start already exists (HARD, another wall): no pile there, next one SOFT
    path = centre(poly([(0, 0), (10000, 0)]), False, (5000, 1000))
    full, fk, step, total = G.layout_ends(path, False, S, "HARD", "HARD")
    c, k, step2, total2 = G.layout_ends(path, False, S, "HARD", "HARD", skip_start=True)
    assert len(c) == len(full) - 1 and k[0] == "SOFT" and k[-1] == "HARD"
    assert abs(c[0][0] - full[1][0]) < 1e-6


def test_closed_ignores_end_settings():
    path = centre(circle(10000), True, (20000, 0))
    c, k, step, total = G.layout_ends(path, True, S, "SOFT", "HARD", True, True)
    assert len(c) == 76 and len(c) % 2 == 0 and k[0] == "HARD"


# ---------------------------------------------------------------- reference planes -> chain
def test_planes_single():
    pts, closed = G.chain_from_lines([((0, 0), (10000, 0))], 5000)
    assert pts == [(0, 0), (10000, 0)] and not closed


def test_planes_L_crossing_is_trimmed():
    # two planes drawn past each other: corner at their crossing (0, 0), far ends kept
    segs = [((-1000, 0), (12000, 0)), ((0, 9000), (0, -1500))]
    pts, closed = G.chain_from_lines(segs, 5000)
    assert not closed and len(pts) == 3
    assert pts[1] == (0.0, 0.0)
    assert set([pts[0], pts[2]]) == set([(12000, 0), (0, 9000)])


def test_planes_rectangle_any_order_is_closed():
    segs = [((0, -500), (0, 12500)), ((-500, 12000), (20500, 12000)),
            ((-500, 0), (20500, 0)), ((20000, 12500), (20000, -500))]      # picked in a random order
    pts, closed = G.chain_from_lines(segs, 5000)
    assert closed and len(pts) == 4
    assert set(pts) == set([(0.0, 0.0), (0.0, 12000.0), (20000.0, 12000.0), (20000.0, 0.0)])


def test_planes_stopping_short_still_meet_within_reach():
    segs = [((0, 0), (9000, 0)), ((10000, 1000), (10000, 8000))]            # 1 m gap at the corner
    pts, closed = G.chain_from_lines(segs, 5000)
    assert pts[1] == (10000.0, 0.0)


def test_planes_errors():
    for segs, words in (
        ([((0, 0), (10, 0)), ((0, 5), (10, 5))], "does not meet"),                       # parallel
        ([((0, 0), (100, 0)), ((50, -10), (50, 10)), ((20, -10), (20, 10)), ((80, -10), (80, 10))], "more than two"),
    ):
        try:
            G.chain_from_lines(segs, 1)
            assert False, "should fail"
        except ValueError as ex:
            assert words in str(ex), str(ex)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    bad = 0
    for n, f in tests:
        try:
            f()
            print("PASS  " + n)
        except AssertionError as ex:
            bad += 1
            print("FAIL  {}  {}".format(n, ex))
    print("{} passed, {} failed".format(len(tests) - bad, bad))
    sys.exit(1 if bad else 0)

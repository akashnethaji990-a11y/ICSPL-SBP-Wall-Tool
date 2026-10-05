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
import sbp_data as SD

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


# ---------------------------------------------------------------- pile labels (Number button)
TXT_H = 500.0                      # 2.5 mm text at 1:200
CHAR = 0.6 * TXT_H


def label_run(pts, closed, side, mode="horizontal", offset=50.0, gap=100.0):
    """Label boxes for piles `pts` (HP/SP numbers), checked: no overlaps, not on a pile, one row only."""
    tans = G.pile_tangents(pts, closed)
    labels = []
    for i, ((x, y), (tx, ty)) in enumerate(zip(pts, tans)):
        txt = ("HP" if i % 2 == 0 else "SP") + str(i // 2 + 16)
        along, across = math.atan2(ty, tx), math.atan2(tx * side, -ty * side)
        ang, alt = {"along": (along, across), "across": (across, along), "horizontal": (0.0, None)}[mode]
        labels.append({"x": x, "y": y, "r": D / 2, "tx": tx, "ty": ty, "side": side, "w": len(txt) * CHAR,
                       "h": TXT_H, "angle": ang, "alt": alt})
    circles = [(x, y, D / 2) for x, y in pts]
    res = G.place_labels(labels, circles, (), offset, gap)
    boxes = [G._box(r[0], r[1], r[2], lb["w"] / 2, lb["h"] / 2) for r, lb in zip(res, labels)]
    for r, lb in zip(res, labels):                                     # next to its own pile, never a far row
        assert math.hypot(r[0] - lb["x"], r[1] - lb["y"]) <= D / 2 + offset + lb["w"] / 2 + 3 * TXT_H / 2 + 1.2 * lb["w"] / 2 + 1e-6
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            assert not G._boxes_hit(boxes[i], boxes[j], gap - 1e-6), ("labels overlap", i, j)
        for c in circles:
            if (c[0], c[1]) != (labels[i]["x"], labels[i]["y"]):
                assert not G._box_circle_hit(boxes[i], c, gap - 1e-6), ("label on a pile", i)
    return res


def rect_piles():
    """SBP3: 30 piles on a 7.5 x 5.5 m loop, c/c 866.7."""
    L = [(10750, 9750), (18250, 9750), (18250, 15250), (10750, 15250)]
    pts = []
    for i in range(30):
        d = 26000.0 * i / 30.0
        for k in range(4):
            a, b = L[k], L[(k + 1) % 4]
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            if d <= seg + 1e-9:
                pts.append((a[0] + (b[0] - a[0]) * d / seg, a[1] + (b[1] - a[1]) * d / seg))
                break
            d -= seg
    return pts


def test_inside_sign():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]                        # counter-clockwise loop
    assert G.inside_sign(sq, True) == 1 and G.inside_sign(list(reversed(sq)), True) == -1
    assert G.inside_sign([(0, 0), (5, 0), (10, 0)], False, line_side=1) == -1   # wall left of its line
    assert G.inside_sign([(0, 10), (0, 0), (10, 0)], False) == 1       # bends left: inside on the left
    assert G.inside_sign([(0, 0), (5, 0), (10, 0)], False) == 1        # straight, no data: left


def test_unturned_size():
    w, h = 1200.0, 500.0
    for deg in (0, 20, 90, 120, -30):
        a = math.radians(deg)
        c, s = abs(math.cos(a)), abs(math.sin(a))
        got = G.unturned_size(w * c + h * s, w * s + h * c, a)            # the box of a text turned by deg
        assert abs(got[0] - w) < 1e-6 and abs(got[1] - h) < 1e-6, (deg, got)
    assert G.unturned_size(1202.0, 1202.0, math.radians(45)) == (1202.0, 1202.0)   # 45 deg: keep the box


def test_readable_angle():
    for deg, want in ((0, 0), (90, 90), (-90, 90), (180, 0), (135, -45), (-135, 45), (270, 90)):
        got = math.degrees(G.readable_angle(math.radians(deg)))
        assert abs(got - want) < 1e-6, (deg, got)


def test_labels_horizontal_wall_alternate_sides():
    # "HP16" (1200) is longer than one c/c (873): the next label goes to the other side, never a second row
    pts = [(i * 873.2, 0.0) for i in range(43)]
    res = label_run(pts, False, -1)                                    # right of the draw direction = below
    assert all(r[4] for r in res)
    assert [r[6] for r in res[:4]] == [False, True, False, True]
    assert abs(res[0][1] - -(600 + 50 + 250)) < 1e-6 and res[1][1] > 0   # just clear of the pile edge
    assert all(abs(r[2]) < 1e-9 for r in res)                          # horizontal, reads left to right


def test_labels_vertical_wall_horizontal_text_one_side():
    # text height (500) is less than one c/c: every label fits on its own side, just clear of the pile
    pts = [(750.0, 20000.0 - i * 873.2) for i in range(18)]
    res = label_run(pts, False, -1)                                    # right of 'down' = the -x side
    assert all(r[4] and not r[6] for r in res)
    assert all(abs(r[0] - (750 - 600 - 50 - 600)) < 1e-6 for r in res[:3] if r[0] < 750)


def test_labels_along_and_across_one_row():
    pts = [(i * 873.2, 0.0) for i in range(43)]
    res = label_run(pts, False, 1, "along")
    assert all(r[4] for r in res) and [r[6] for r in res[:2]] == [False, True]
    res = label_run(pts, False, -1, "across")
    assert all(r[4] and not r[6] for r in res) and all(r[1] < -600 for r in res)


def test_labels_rectangle_sbp3_inside_and_outside():
    pts = rect_piles()
    inside = G.inside_sign(pts, True)
    for side in (-inside, inside):                                     # outside, then inside the loop
        for mode in ("horizontal", "along", "across"):
            res = label_run(pts, True, side, mode)
            assert all(r[4] for r in res), (side, mode)


def test_labels_arc_concave_side():
    # SBP1's arc: radius 4250, piles every 873.2 mm; labels on the inner (concave) side converge
    pts = [(5000 + 4250 * math.cos(math.pi + t), 5000 + 4250 * math.sin(math.pi + t))
           for t in [k * 873.2 / 4250 for k in range(9)]]
    for mode in ("horizontal", "along"):
        res = label_run(pts, False, 1, mode)
        assert all(r[4] for r in res), mode


# ---------------------------------------------------------------- v2 layout (Akash's drawing: 1500 at 2000)
def arc(r, a0, a1, step=100.0):
    n = max(2, int(math.ceil(abs(a1 - a0) * r / step)) + 1)
    sg = 1 if a1 > a0 else -1
    ang = [a0 + (a1 - a0) * k / (n - 1.0) for k in range(n)]
    return [([(r * math.cos(a), r * math.sin(a)) for a in ang], [(-sg * math.sin(a), sg * math.cos(a)) for a in ang])]


def v2(samples, closed, pick, dh=1500.0, ds=1500.0, hh=2000.0, gap=150.0, st="HARD", et="HARD"):
    """SBP Wall's v2 steps (sbp_revit.plan_wall) on test lines: (centres, kinds, info, check, line, dist)."""
    s, web = hh / 2.0, min(200.0, hh - dh)
    dist = gap + max(dh, ds) / 2.0
    side = G.pick_side(samples, pick)
    path = G.offset_path(samples, closed, side, dist, sharp_deg=G.CORNER_MAX_DEG)
    w = int(math.ceil(4 * math.pi * dist / 100.0)) + 20
    path = G.remove_loops(path, w)
    if closed:
        h = len(path) // 2
        path = G.remove_loops(path[h:] + path[:h], w)
    corners, skipped = G.find_corners(path, G.chain_joints(samples, closed), side, dist)
    line = [(a, b) for pts, tans in samples for a, b in zip(pts[:-1], pts[1:])]
    c, k, info = G.layout_wall(path, closed, corners, s, dh, ds, web, st, et, line, gap)
    return c, k, info, G.check_wall(c, k, closed, dh, ds, s, 200.0, line, gap), line, dist


def near(a, b, tol=0.5):
    return abs(a - b) <= tol


def test_v2_straight_keeps_1000_and_reduces_at_the_far_end():
    # drawing panel 3: centre line 13 700 -> 14 gaps, 12 at 1000, the last 2 at 850 (web exactly 200)
    c, k, info, chk, line, dist = v2(poly([(0, 900), (13700, 900)]), False, (0, 0))
    g = chk["gaps"]
    assert len(c) == 15 and k[0] == k[-1] == "HARD" and k.count("HARD") == 8, (len(c), k)
    assert all(near(x, 1000.0) for x in g[:12]) and all(near(x, 850.0) for x in g[12:]), g
    assert near(chk["min_web"][0], 200.0) and near(chk["min_cut"][0], 500.0)
    assert not chk["warnings"] and not chk["errors"]


def test_v2_different_diameters():
    # HARD 1500, SOFT 1200 at HARD to HARD 2000: cutting 350 each side, web 500; exact fit, nothing reduced
    c, k, info, chk, line, dist = v2(poly([(0, 900), (10000, 900)]), False, (0, 0), ds=1200.0)
    assert len(c) == 11 and all(near(x, 1000.0) for x in chk["gaps"])
    assert near(chk["min_cut"][0], 350.0) and near(chk["min_web"][0], 500.0) and not chk["warnings"]
    assert near(min(G.seg_dist(p, *line[0]) for p in c), 900.0)        # centre line = gap + the bigger radius


def test_v2_curve_keeps_the_design_chord():
    # wall on a 6 m radius curve (line outside it): every c/c is 1000 in a straight line, H-H 1993, web 493
    c, k, info, chk, line, dist = v2(arc(6900.0, math.radians(0), math.radians(180)), False, (0, 0))
    g = chk["gaps"]
    assert all(near(x, 1000.0) for x in g[:12]), g                      # design from the start ...
    assert all(850.0 - 0.5 <= x < 1000.0 for x in g[12:]), g            # ... the leftover taken at the far end
    webs = [r[2] for r in chk["soft"][:4]]
    assert all(near(w, 493.0, 1.0) for w in webs), webs
    assert near(chk["min_cut"][0], 500.0) and not chk["errors"]


def test_v2_corner_option_b_line_inside():
    # drawing panel 5: 90 deg corner, your line inside: corner SOFT, HARD at 1202, SOFT moved 323, S-H 1000,
    # web 200, SOFT edge 200 from the line (>= 150)
    L = 20000.0
    c, k, info, chk, line, dist = v2(poly([(900, L), (900, 900), (L, 900)]), False, (0, 0))
    cr = info["corners"][0]
    assert k[cr["index"]] == "SOFT" and len(info["corners"]) == 1
    assert near(cr["bend"], 90.0, 1e-6) and near(cr["c"][0], 1202.1) and near(cr["c"][1], 1202.1), cr
    assert near(cr["move"], 323.0, 1.0) and not cr["limited"] and near(cr["sh"], 1000.0)
    i = cr["index"]
    assert near(G.line_dist(c[i], line) - 750.0, 200.0, 1.0)
    assert near(math.hypot(c[i - 1][0] - c[i + 1][0], c[i - 1][1] - c[i + 1][1]) - 1500.0, 200.0)
    assert near(chk["min_cut"][0], 500.0) and not chk["errors"]


def test_v2_corner_soft_keeps_the_typed_gap_and_never_crosses_the_line():
    # Akash's rule: the corner SOFT slides inward along the bisector only; its edge keeps the SAME clearance
    # you type (100 / 150 ...) from the structure line as every other pile, and never crosses to the far side.
    L = 20000.0
    Rs = 1500.0 / 2.0
    for gap in (150.0, 100.0, 50.0):
        # dist changes with the gap, so keep the line fixed and let the wall sit at its own offset
        c, k, info, chk, line, dist = v2(poly([(900, L), (900, 900), (L, 900)]), False, (0, 0), gap=gap)
        cr = info["corners"][0]
        i = cr["index"]
        edge = G.line_dist(c[i], line) - Rs
        assert edge >= gap - 0.5, (gap, edge)                          # clearance respected for any typed gap
        assert G.line_dist(c[i], line) >= gap + Rs - 0.5               # centre never nearer than gap + radius
        assert cr["move"] >= 0.0 and not chk["errors"]                 # inward only, and the pile stays legal
    # when the overlap cannot be reached without breaking the gap, it stops AT the gap (edge == gap) and warns,
    # instead of crossing the line or being resized
    c, k, info, chk, line, dist = v2(poly([(760, L), (760, 760), (L, 760)]), False, (0, 0), gap=10.0)
    cr = info["corners"][0]
    edge = G.line_dist(c[cr["index"]], line) - Rs
    assert cr["limited"] and 9.0 <= edge <= 11.0 and cr["sh"] > 1000.5
    assert any("cutting depth" in t for i, t in chk["warnings"]) and not chk["errors"]


def test_v2_corner_option_b_stops_at_the_gap():
    # same corner with gap 10: the SOFT may only move 315 (edge 10 from the line), so S-H > 1000: WARNING
    L = 20000.0
    c, k, info, chk, line, dist = v2(poly([(760, L), (760, 760), (L, 760)]), False, (0, 0), gap=10.0)
    cr = info["corners"][0]
    assert cr["limited"] and near(cr["move"], 760.0 * math.sqrt(2) - 760.0, 1.0) and cr["sh"] > 1000.5, cr
    assert near(G.line_dist(c[cr["index"]], line) - 750.0, 10.0, 0.5)
    assert any("cutting depth" in t for i, t in chk["warnings"]) and not chk["errors"]


def test_v2_corner_line_outside_moves_away_from_the_line():
    L = 20000.0
    c, k, info, chk, line, dist = v2(poly([(-900, L), (-900, -900), (L, -900)]), False, (1000, 1000))
    cr = info["corners"][0]
    assert near(cr["move"], 323.0, 1.0) and not cr["limited"] and near(cr["sh"], 1000.0)
    assert near(G.line_dist(c[cr["index"]], line), 900.0 + 323.0 / math.sqrt(2), 1.0)   # further from the line


def test_v2_rectangle_loop():
    # drawing panel 7: centre line 14 304 x 8 404 around a structure: 22 HARD + 22 SOFT, 4 corner SOFT piles
    W, H = 14304.0, 8404.0
    c, k, info, chk, line, dist = v2(poly([(900, 900), (W - 900, 900), (W - 900, H - 900), (900, H - 900)],
                                          closed=True), True, (-500, -500))
    assert k.count("HARD") == 22 and k.count("SOFT") == 22
    assert len(info["corners"]) == 4 and all(k[cr["index"]] == "SOFT" for cr in info["corners"])
    assert all(near(cr["sh"], 1000.0) and near(cr["move"], 323.0, 1.0) for cr in info["corners"])
    assert near(chk["min_web"][0], 200.0) and near(chk["min_cut"][0], 500.0)
    assert not chk["warnings"] and not chk["errors"]
    assert sum(1 for g in chk["gaps"] if g < 999.5) == 2                 # one reduced gap on each long side


def test_v2_small_bend_needs_nothing():
    # 30 deg: HARD piles stay at 1000 from the corner SOFT, no move, web 2 x 1000 x cos 15 - 1500 = 432
    b = math.radians(30)
    c, k, info, chk, line, dist = v2(poly([(0, 0), (8000, 0), (8000 + 8000 * math.cos(b), 8000 * math.sin(b))]),
                                     False, (4000, -1000))
    cr = info["corners"][0]
    assert near(cr["c"][0], 1000.0) and cr["move"] == 0.0 and near(cr["sh"], 1000.0)
    i = cr["index"]
    assert near(math.hypot(c[i - 1][0] - c[i + 1][0], c[i - 1][1] - c[i + 1][1]) - 1500.0, 431.9, 0.5)
    assert not chk["errors"] and not chk["warnings"]


def test_v2_bend_under_5_deg_is_not_a_corner():
    b = math.radians(4)
    c, k, info, chk, line, dist = v2(poly([(0, 0), (8000, 0), (8000 + 8000 * math.cos(b), 8000 * math.sin(b))]),
                                     False, (4000, -1000))
    assert info["corners"] == [] and not chk["errors"]


def test_v2_short_leg_low_web_is_a_warning_not_an_error():
    # 90 deg corner, 6 m legs: after the corner HARD (1202) 4 798 is left: 6 gaps of 800 (web 99) are the only fit
    # that keeps the overlap: WARNING, placed
    c, k, info, chk, line, dist = v2(poly([(900, 6000), (900, 900), (6000, 900)]), False, (0, 0))
    assert info["low_web_runs"] == 2 and not chk["errors"]
    assert chk["warnings"] and all("web" in t for i, t in chk["warnings"])
    assert near(chk["min_cut"][0], 500.0)                              # the overlap is never less than design


def test_v2_jog_drops_a_corner():
    # two 90 deg corners 1 m apart: too short for the corner rule, one corner is dropped and reported
    c, k, info, chk, line, dist = v2(poly([(0, 0), (6000, 0), (6000, 1000), (12000, 1000)]), False, (3000, -2000))
    assert len(info["dropped"]) == 1 and len(info["corners"]) == 1
    assert k[0] == k[-1] == "HARD" and not any("next to each other" in t for i, t in chk["errors"])


def test_v2_circle_is_divided_equally():
    n = 629
    samples = [([(10000 * math.cos(2 * math.pi * i / n), 10000 * math.sin(2 * math.pi * i / n)) for i in range(n)],
                [(-math.sin(2 * math.pi * i / n), math.cos(2 * math.pi * i / n)) for i in range(n)])]
    c, k, info, chk, line, dist = v2(samples, True, (20000, 0))
    assert info["equal"] is not None and len(c) % 2 == 0 and not info["corners"]
    assert max(chk["gaps"]) <= 1000.0 and not chk["errors"]


def test_check_wall_finds_errors():
    # HARD piles 1400 apart (web -100), a SOFT not reaching its HARD, two SOFT next to each other
    c = [(0, 0), (700, 0), (1400, 0), (2900, 0), (4400, 0)]
    chk = G.check_wall(c, ["HARD", "SOFT", "HARD", "SOFT", "SOFT"], False, 1500.0, 1500.0, 1000.0)
    txt = " / ".join(t for i, t in chk["errors"])
    assert "HARD piles cut each other" in txt and "not cut" in txt and "next to each other" in txt, txt


# ---------------------------------------------------------------- v3: closing zone (Akash, 6 Oct)
ES3 = [(0.0, 14618.0), (11223.0, 14618.0), (11223.0, 0.0), (0.0, 0.0)]   # centre line measured from his drawing


def _gaps(c, closed):
    n = len(c)
    return [math.hypot(c[(i + 1) % n][0] - c[i][0], c[(i + 1) % n][1] - c[i][1]) for i in range(n if closed else n - 1)]


def _v3_rules(c, k, info, closed, s=S, d=D, web=200.0):
    """Every gap is exactly s except the closing zone's 2N equal gaps; types alternate; a clean choice has no error."""
    g = _gaps(c, closed)
    cl = info["close"]
    changed = [i for i, x in enumerate(g) if abs(x - s) > 0.01]
    if cl["way"] in ("exact", "short"):
        assert not changed, changed
    elif cl["way"] != "equal":
        zone = list(range(cl["first"], cl["first"] + 2 * cl["n"]))
        assert changed == zone, (changed, zone)
        assert max(g[i] for i in zone) - min(g[i] for i in zone) < 0.01
    n = len(k)
    assert all(k[i] != k[(i + 1) % n] for i in range(n if closed else n - 1))
    if closed:
        assert n % 2 == 0 and k[0] == "HARD"
    chk = G.check_wall(c, k, closed, d, d, s, web)
    if cl["clean"]:
        assert not chk["errors"] and not chk["warnings"], (chk["errors"], chk["warnings"])
    return chk


def test_v3_es3_loop_closes_in_4_bays():
    c, k, info = G.layout_closing(ES3, True, S, D, D, 200.0, 3, tiny=10.0)
    cl = info["close"]
    _v3_rules(c, k, info, True)
    assert len(c) == 58 and k.count("HARD") == 29, len(c)
    assert cl["n"] == 4 and cl["way"] == "shrink" and cl["clean"], cl
    assert abs(2 * cl["gap"] - 1439.7) < 0.5, cl["gap"]
    tried = dict(((n, w), ok) for n, w, g, ok in cl["tried"])
    assert not tried[(1, "shrink")] and not tried[(3, "shrink")] and tried[(4, "shrink")], cl["tried"]


def test_v3_loop_start_corner_stays_exact():
    c, k, info = G.layout_closing(ES3, True, S, D, D, 200.0, 3, tiny=10.0)
    g = _gaps(c, True)
    assert c[0] == ES3[0] and k[0] == "HARD"
    assert all(abs(x - S) < 0.01 for x in (g[-1], g[-2], g[0], g[1])), (g[-2:], g[:2])


def test_v3_open_free_end_case1_stops_at_the_last_design_hard():
    # 12.9 m: design piles at 0, 900 ... 12600; the one at 12600 is HARD -> no adjustment, 300 of line left
    c, k, info = G.layout_closing([(0.0, 0.0), (12900.0, 0.0)], False, S, D, D, 200.0, 3, free_end=True, tiny=10.0)
    _v3_rules(c, k, info, False)
    assert info["close"]["way"] == "short" and len(c) == 15 and k[-1] == "HARD", info["close"]
    assert abs(info["close"]["left"] - 300.0) < 0.01 and c[-1] == (12600.0, 0.0)


def test_v3_open_free_end_case2_shortens_the_last_soft():
    # 12.2 m: the last design pile that fits (at 11700) would be SOFT -> end HARD on the line end, 1 bay shortened
    c, k, info = G.layout_closing([(0.0, 0.0), (12200.0, 0.0)], False, S, D, D, 200.0, 3, free_end=True, tiny=10.0)
    _v3_rules(c, k, info, False)
    cl = info["close"]
    assert cl["n"] == 1 and cl["way"] == "shrink" and c[-1] == (12200.0, 0.0) and k[-1] == "HARD", cl
    assert abs(2 * cl["gap"] - 1400.0) < 0.01                       # 900 + 500 left: web 200
    # 12.0 m: only 300 left after the SOFT -> 1 bay would be H-H 1200 (web 0) -> 3 bays of 1600
    c, k, info = G.layout_closing([(0.0, 0.0), (12000.0, 0.0)], False, S, D, D, 200.0, 3, free_end=True, tiny=10.0)
    _v3_rules(c, k, info, False)
    assert info["close"]["n"] == 3 and abs(2 * info["close"]["gap"] - 1600.0) < 0.01, info["close"]


def test_v3_joined_end_stays_on_the_line_end():
    c, k, info = G.layout_closing([(0.0, 0.0), (12900.0, 0.0)], False, S, D, D, 200.0, 3, "HARD", "SOFT")
    _v3_rules(c, k, info, False)
    assert k[-1] == "SOFT" and c[-1] == (12900.0, 0.0)


def test_v3_exact_fit_changes_nothing():
    c, k, info = G.layout_closing([(0.0, 0.0), (10800.0, 0.0)], False, S, D, D, 200.0, 3, free_end=True)
    _v3_rules(c, k, info, False)
    assert info["close"]["way"] in ("exact", "short") and len(c) == 13 and c[-1] == (10800.0, 0.0)


def test_v3_loop_within_10_mm_is_not_adjusted():
    # loops of growing length: one whose seam bay misses the design by 10 mm or less is spread over that bay only
    for x in range(0, 1800, 2):
        L = 16000.0 + x
        c, k, info = G.layout_closing([(0.0, 0.0), (L, 0.0), (L, 3000.0), (0.0, 3000.0)], True, S, D, D, 200.0, 3,
                                      tiny=10.0)
        cl = info["close"]
        if cl["way"] == "tiny":
            assert cl["n"] == 1 and abs(2 * cl["gap"] - 2 * S) <= 10.0 and cl["clean"], cl
            return
    raise AssertionError("no loop length in the sweep closed within 10 mm")


def test_v3_short_wall_and_no_clean_choice():
    c, k, info = G.layout_closing([(0.0, 0.0), (3000.0, 0.0)], False, S, D, D, 200.0, 3)
    assert info["close"]["way"] == "equal" and k[0] == k[-1] == "HARD"
    assert len(set(round(x, 3) for x in _gaps(c, False))) == 1
    c, k, info = G.layout_closing([(0.0, 0.0), (12900.0, 0.0)], False, S, D, D, 590.0, 3)   # web 590: no shrink
    assert not info["close"]["clean"] and info["close"]["way"] == "stretch", info["close"]
    assert G.check_wall(c, k, False, D, D, S, 200.0)["warnings"]


# ---------------------------------------------------------------- every shape (Akash, 7 Oct): c/c tables printed
def _corners_of(path, closed):
    """[(length along the line, bend)] for the polyline joints that bend more than 5 deg, and the line's length."""
    w = G._Walk(list(path) + ([path[0]] if closed else []))
    n, res = len(path), []
    for i in (range(n) if closed else range(1, n - 1)):
        a, b, c = path[i - 1], path[i], path[(i + 1) % n]
        bend = abs(G.turn_deg(G._unit((b[0] - a[0], b[1] - a[1])), G._unit((c[0] - b[0], c[1] - b[1]))))
        if bend > 5.0:
            res.append((w.cum[i], bend))
    return res, w.total


def _shape(name, path, closed, free_end=True):
    c, k, info = G.layout_closing(path, closed, S, D, D, 200.0, 3, free_end=free_end, tiny=10.0)
    corners, total = _corners_of(path, closed)
    bends = G.bay_corners(info["u"], k, closed, total, corners)
    cl = info["close"]
    n = len(c)
    adjusted = set()
    if cl["first"] is not None and cl["way"] not in ("exact", "short"):
        adjusted = set(i % n for i in range(cl["first"], cl["first"] + 2 * cl["n"] + 1)
                       if (closed or i < n) and k[i % n] == "SOFT")
    rows, cols = SD.bay_table("W", c, k, closed, D, D, S, 200.0, adjusted, bends)
    print("\n  {}: {} piles ({} H + {} S), line {:.0f}, closing: {}".format(
        name, n, k.count("HARD"), k.count("SOFT"), total, SD.closing_text(cl)))
    print("  " + " | ".join(cols))
    for r in rows:
        print("  " + " | ".join(r))
    return c, k, info, rows


def test_shape_circle_r5000():
    circle = [(5000 * math.cos(2 * math.pi * i / 720), 5000 * math.sin(2 * math.pi * i / 720)) for i in range(720)]
    c, k, info, rows = _shape("circle R5000 (centre line)", circle, True)
    g = _gaps(c, True)
    zone = set(range(info["close"]["first"], info["close"]["first"] + 2 * info["close"]["n"]))
    assert len(c) == 36 and info["close"]["clean"], (len(c), info["close"])
    assert all(abs(x - S) < 0.05 for i, x in enumerate(g) if i not in zone)        # every normal chord = 900
    assert not any(r[6] for r in rows)                                                  # no corners on a circle


def test_shape_rectangle_10x6_corner_checks():
    rect = [(0.0, 6000.0), (10000.0, 6000.0), (10000.0, 0.0), (0.0, 0.0)]
    c, k, info, rows = _shape("rectangle 10 x 6, start on a corner", rect, True)
    corner_rows = [r for r in rows if r[6]]
    assert corner_rows and all(r[6] == "90 deg" for r in corner_rows), corner_rows
    assert any("WARNING: web below 200" in r[7] for r in corner_rows)                  # H06-S06-H07: web 142
    assert not info["close"]["clean"]                                                    # report tip: start mid-side
    c, k, info, rows = _shape("rectangle 10 x 6, start mid-side",
                              [(5000.0, 6000.0)] + rect[1:] + [(0.0, 6000.0)], True)
    assert info["close"]["clean"]


def test_shape_arc_90_open():
    arc = [(8000 * math.cos(math.pi / 2 * i / 200), 8000 * math.sin(math.pi / 2 * i / 200)) for i in range(201)]
    c, k, info, rows = _shape("90 deg arc R8000, open", arc, False)
    assert k[0] == k[-1] == "HARD" and info["close"]["clean"]
    zone = set()
    if info["close"]["first"] is not None and info["close"]["way"] not in ("exact", "short"):
        zone = set(range(info["close"]["first"], info["close"]["first"] + 2 * info["close"]["n"]))
    assert all(abs(x - S) < 0.05 for i, x in enumerate(_gaps(c, False)) if i not in zone)


def test_shape_l_open_chain():
    c, k, info, rows = _shape("L-shape 8 m + 6 m, open", [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0)], False)
    assert k[0] == k[-1] == "HARD" and any(r[6] == "90 deg" for r in rows)


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

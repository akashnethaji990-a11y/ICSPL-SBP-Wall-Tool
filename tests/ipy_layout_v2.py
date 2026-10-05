# -*- coding: utf-8 -*-
"""Run the v2 layout in pyRevit's IronPython 2.7 engine (outside Revit): same numbers as under CPython?

    powershell -STA -ExecutionPolicy Bypass -File tools\\ipy_host.ps1 -Py tests\\ipy_layout_v2.py
Cases from the v2 example drawing (HARD and SOFT 1500, HARD to HARD 2000, gap 150). No stdlib here (json is stubbed).
"""
import sys
import imp
import math
from System.IO import Path

sys.modules["json"] = imp.new_module("json")          # stdlib package, supplied inside Revit
sys.path.append(Path.Combine(REPO, "pyRevit", "SBP.extension", "lib"))
import sbp_geom as G
import sbp_data as SD


def poly(ptsxy, closed=False, step=100.0):
    segs = list(zip(ptsxy[:-1], ptsxy[1:])) + ([(ptsxy[-1], ptsxy[0])] if closed else [])
    out = []
    for a, b in segs:
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(2, int(math.ceil(L / step)) + 1)
        t = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        out.append(([(a[0] + (b[0] - a[0]) * k / (n - 1.0), a[1] + (b[1] - a[1]) * k / (n - 1.0)) for k in range(n)],
                    [t] * n))
    return out


def v2(samples, closed, pick, dh=1500.0, ds=1500.0, hh=2000.0, gap=150.0):
    s, web = hh / 2.0, SD.corner_web(hh, dh)
    dist = gap + max(dh, ds) / 2.0
    side = G.pick_side(samples, pick)
    path = G.offset_path(samples, closed, side, dist, G.CORNER_MAX_DEG)
    w = int(math.ceil(4 * math.pi * dist / 100.0)) + 20
    path = G.remove_loops(path, w)
    if closed:
        h = len(path) // 2
        path = G.remove_loops(path[h:] + path[:h], w)
    corners, skipped = G.find_corners(path, G.chain_joints(samples, closed), side, dist)
    line = [(a, b) for pts, tans in samples for a, b in zip(pts[:-1], pts[1:])]
    c, k, info = G.layout_wall(path, closed, corners, s, dh, ds, web, "HARD", "HARD", line, gap)
    return c, k, info, G.check_wall(c, k, closed, dh, ds, s, 200.0, line, gap)


def show(name, res):
    c, k, info, chk = res
    cr = ["{:.0f} deg c {:.1f} move {:.1f} S-H {:.1f}".format(x["bend"], x["c"][0], x["move"], x["sh"])
          for x in info["corners"]]
    print("{}: {} piles ({} H), gaps {:.1f}-{:.1f}, min web {:.1f}, min cut {:.1f}, warn {}, err {}, corners {}".format(
        name, len(c), k.count("HARD"), min(chk["gaps"]), max(chk["gaps"]), chk["min_web"][0], chk["min_cut"][0],
        len(chk["warnings"]), len(chk["errors"]), cr))


show("straight 13.7 m", v2(poly([(0, 900), (13700, 900)]), False, (0, 0)))
show("L 90, line inside", v2(poly([(900, 20000), (900, 900), (20000, 900)]), False, (0, 0)))
W, H = 14304.0, 8404.0
show("rectangle", v2(poly([(900, 900), (W - 900, 900), (W - 900, H - 900), (900, H - 900)], closed=True), True,
                     (-500, -500)))
show("HARD 1500 / SOFT 1200", v2(poly([(0, 900), (10000, 900)]), False, (0, 0), ds=1200.0))
print("spacing 1500/1500 at 2000: {}".format(SD.spacing_values(2000.0, 1500.0, 1500.0)))

print("--- v3 closing zone (Akash 6 Oct): 1200 / H-H 1800, closing SOFT piles 3")
for name, path, closed in (("ES3 loop 11223 x 14618", [(0.0, 14618.0), (11223.0, 14618.0), (11223.0, 0.0), (0.0, 0.0)],
                            True), ("straight 12.9 m", [(0.0, 0.0), (12900.0, 0.0)], False)):
    c, k, info = G.layout_closing(path, closed, 900.0, 1200.0, 1200.0, 200.0, 3)
    cl = info["close"]
    print("{}: {} piles ({} H), {} bays {} H-H {:.2f}, clean {}".format(
        name, len(c), k.count("HARD"), cl["n"], cl["way"], 2 * cl["gap"], cl["clean"]))
print("--- every shape (Akash 7 Oct): free open ends, 10 mm tolerance")
circle = [(5000 * math.cos(2 * math.pi * i / 720), 5000 * math.sin(2 * math.pi * i / 720)) for i in range(720)]
arc = [(8000 * math.cos(math.pi / 2 * i / 200), 8000 * math.sin(math.pi / 2 * i / 200)) for i in range(201)]
rect = [(0.0, 6000.0), (10000.0, 6000.0), (10000.0, 0.0), (0.0, 0.0)]
for name, path, closed in (("circle R5000", circle, True), ("rect 10x6 corner start", rect, True),
                           ("rect 10x6 mid start", [(5000.0, 6000.0)] + rect[1:] + [(0.0, 6000.0)], True),
                           ("arc 90 R8000", arc, False), ("L 8+6", [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0)], False)):
    c, k, info = G.layout_closing(path, closed, 900.0, 1200.0, 1200.0, 200.0, 3, free_end=True, tiny=10.0)
    cl = info["close"]
    print("{}: {} piles, {} bays {} gap {:.2f}, clean {}".format(name, len(c), cl["n"], cl["way"], cl["gap"],
                                                                 cl["clean"]))

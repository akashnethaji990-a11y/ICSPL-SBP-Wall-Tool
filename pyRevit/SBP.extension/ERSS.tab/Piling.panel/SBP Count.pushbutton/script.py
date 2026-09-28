# -*- coding: utf-8 -*-
"""Count HARD / SOFT piles per SBP wall (from each pile's hidden wall data, or old marks 'WALL-H001')."""
__title__ = "SBP\nCount"
__author__ = "Akash"

from pyrevit import revit, script

import sbp_data as SD
import sbp_revit as SR

doc = revit.doc
output = script.get_output()

walls = {}
for fi in SR.all_piles(doc):
    wall = SR.wall_of(fi)
    kind = SR.kind_of(fi) if wall else None
    if kind not in (SR.HARD, SR.SOFT):
        continue
    w = walls.setdefault(wall, {SR.HARD: 0, SR.SOFT: 0})
    w[kind] += 1

if not walls:
    output.print_md("No SBP piles found.")
else:
    rows = []
    th = ts = 0
    for name in sorted(walls, key=SD.natural_key):
        h, s = walls[name][SR.HARD], walls[name][SR.SOFT]
        th += h
        ts += s
        rows.append([SR.html(name), str(h), str(s), str(h + s)])
    rows.append(["**TOTAL**", str(th), str(ts), str(th + ts)])
    output.print_md("## SBP pile count")
    output.print_table(table_data=rows, columns=["Wall", "HARD", "SOFT", "TOTAL"])

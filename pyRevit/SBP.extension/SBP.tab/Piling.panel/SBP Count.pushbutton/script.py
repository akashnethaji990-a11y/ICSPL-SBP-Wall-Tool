# -*- coding: utf-8 -*-
"""Count HARD / SOFT piles per SBP wall (reads Mark 'WALL-H001' / 'WALL-S001')."""
__title__ = "SBP\nCount"
__author__ = "Akash"

from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, BuiltInCategory, BuiltInParameter
from pyrevit import revit, script

FAMILY_NAME = "ICSPL_Pile"
doc = revit.doc
output = script.get_output()

walls = {}
for fi in FilteredElementCollector(doc).OfClass(FamilyInstance).OfCategory(BuiltInCategory.OST_StructuralFoundation):
    if fi.Symbol.Family.Name != FAMILY_NAME:
        continue
    mark = fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).AsString() or ""
    if "-" not in mark:
        continue
    wall, tag = mark.rsplit("-", 1)
    kind = tag[:1].upper()
    if kind not in ("H", "S"):
        continue
    w = walls.setdefault(wall, {"H": 0, "S": 0})
    w[kind] += 1

if not walls:
    output.print_md("No SBP piles found (marks like `SBP1-H001`).")
else:
    rows = []
    th = ts = 0
    for name in sorted(walls):
        h, s = walls[name]["H"], walls[name]["S"]
        th += h
        ts += s
        rows.append([name, str(h), str(s), str(h + s)])
    rows.append(["**TOTAL**", str(th), str(ts), str(th + ts)])
    output.print_md("## SBP pile count")
    output.print_table(table_data=rows, columns=["Wall", "HARD", "SOFT", "TOTAL"])

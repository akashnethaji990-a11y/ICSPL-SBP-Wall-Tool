# -*- coding: utf-8 -*-
"""Show or hide the drawn line of an SBP wall.

Click any pile of the wall. If its line is hidden, it is shown and selected so you can move or
reshape it; then run SBP Edit and the wall follows the line (and the line is hidden again).
If the line is already shown, it is hidden.
"""
__title__ = "SBP\nLine"
__author__ = "Akash"

from Autodesk.Revit.DB import Transaction, ElementId
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

from pyrevit import revit, forms, script

import sbp_revit as SR

doc = revit.doc
uidoc = revit.uidoc


def fail(msg):
    forms.alert(msg, title="SBP Line", exitscript=True)


pre = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
pre = [e for e in pre if SR.is_sbp_pile(e)]
if not pre:
    try:
        pre = [doc.GetElement(uidoc.Selection.PickObject(ObjectType.Element, SR.PileFilter(),
                                                          "Click any pile of the wall"))]
    except OperationCanceledException:
        script.exit()
names = sorted(set(SR.wall_of(e) for e in pre))
saved = SR.load_walls(doc)
missing = [n for n in names if n not in saved]
if missing:
    fail("No saved settings for: {}.\nRun SBP Wall once on its line with the same wall name.".format(", ".join(missing)))

lines, styles = [], {}
for n in names:
    data = saved[n][1]
    for u in data.get("lines", []):
        e = doc.GetElement(u)
        if e is not None:
            lines.append(e)
    styles.update(data.get("line_styles") or {})
if not lines:
    fail("The drawn line of {} was deleted.".format(", ".join(names)))

view = doc.ActiveView
show = any(SR.is_invisible(e) for e in lines) or SR.is_hidden_in(view, lines)
t = Transaction(doc, "SBP Line - " + ("show" if show else "hide"))
t.Start()
try:
    errs = SR.show_lines(doc, lines, styles, view) if show else SR.hide_lines(doc, lines, view)
    t.Commit()
except Exception as ex:
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    fail("The line style could not be changed.\n\n{}".format(ex))

if show:
    uidoc.Selection.SetElementIds(List[ElementId]([e.Id for e in lines]))
    forms.alert("The line of {} is shown and selected.\n\nMove or reshape it, then run SBP Edit: the wall follows "
                "the line and the line is hidden again.".format(", ".join(names)), title="SBP Line")
if errs:
    forms.alert("Some lines could not be changed:\n" + "\n".join(errs), title="SBP Line")

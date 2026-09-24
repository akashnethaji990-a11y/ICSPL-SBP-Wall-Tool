# -*- coding: utf-8 -*-
"""Select piles of an SBP wall in one click: the whole wall, HARD only or SOFT only.

Click any pile of the wall (or select piles of several walls first), then choose.
"""
__title__ = "SBP\nSelect"
__author__ = "Akash"

from Autodesk.Revit.DB import ElementId
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

from pyrevit import revit, forms, script

import sbp_revit as SR

doc = revit.doc
uidoc = revit.uidoc

pre = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
pre = [e for e in pre if SR.is_sbp_pile(e)]
if not pre:
    try:
        pre = [doc.GetElement(uidoc.Selection.PickObject(ObjectType.Element, SR.PileFilter(),
                                                          "Click any pile of the wall"))]
    except OperationCanceledException:
        script.exit()
names = sorted(set(SR.wall_of(e) for e in pre))

choice = forms.CommandSwitchWindow.show(["Whole wall", "HARD only", "SOFT only"],
                                        message="Select piles of: {}".format(", ".join(names)))
if not choice:
    script.exit()
want = {"HARD only": SR.HARD, "SOFT only": SR.SOFT}.get(choice)
ids = [fi.Id for fi in SR.all_piles(doc)
       if SR.wall_of(fi) in names and (want is None or SR.kind_of(fi) == want)]
uidoc.Selection.SetElementIds(List[ElementId](ids))

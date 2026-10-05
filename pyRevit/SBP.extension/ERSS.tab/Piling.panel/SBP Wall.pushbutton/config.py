# -*- coding: utf-8 -*-
"""Shift+Click on SBP Wall: pile family set-up.

Choose a type of any Structural Foundation family, then pick which of its parameters gives the pile size
(diameter or radius), sets the height above the level (cut-off) and sets the pile length (toe). The answer is
saved in the model, so every drafter's SBP Wall / SBP Edit use it. Use it to set up a family that is not listed,
or to correct a set-up that gives wrong levels.
"""
from pyrevit import revit, forms, script

import sbp_revit as SR

doc = revit.doc


def ask_choice(question, options):
    return forms.SelectFromList.show(options, title=question, multiselect=False, button_name="Use this")


SR.clear_pile_specs()
types = SR.all_foundation_types(doc)
if not types:
    forms.alert("No Structural Foundation family is loaded in this project.", title="Pile family set-up", exitscript=True)
pick = forms.SelectFromList.show(sorted(types.keys()), title="Pile family set-up: choose a type of the pile family",
                                 multiselect=False, button_name="Set up")
if not pick:
    script.exit()
levels = SR.all_levels(doc)
view_level = doc.ActiveView.GenLevel
level = view_level if view_level is not None else sorted(levels.values(), key=lambda l: l.Elevation)[0]
try:
    spec = SR.ensure_pile_spec(doc, types[pick], level, ask_choice, force=True)
except Exception as ex:
    forms.alert("Not set up:\n{}".format(ex), title="Pile family set-up", exitscript=True)
if spec:
    fam = types[pick].Family.Name
    forms.alert("Saved in this model for family '{}':\n\n"
                "Pile size: '{}' ({})\nCut-off (height above the level): '{}'\nToe (pile length): '{}'\n\n"
                "SBP Wall and SBP Edit now use it for every type of this family."
                .format(fam, spec["diameter"], "diameter" if spec["factor"] == 1 else "radius",
                        spec["offset"], spec["length"]), title="Pile family set-up")

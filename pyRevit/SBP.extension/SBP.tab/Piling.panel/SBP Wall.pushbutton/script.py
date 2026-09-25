# -*- coding: utf-8 -*-
"""Place a Secant Bored Pile (SBP) wall along any drawn line.

1. Click SBP Wall with nothing selected: Revit's Modify | Place Lines tab opens with the Draw panel
   (Line, Rectangle, Circle, Arcs, Spline, Pick Lines ...). Draw the 'other structure' line and
   press Modify / Esc: this form then opens by itself.
   Or select existing line(s) first (line, arc, circle, spline or a connected chain), then click.
2. Fill in the settings (all adjustable, remembered for next time).
3. Click on the side where the SBP wall should go.
Piles are placed as HARD / SOFT alternately, offset by (gap + D/2) from your line.
A free end starts/ends with HARD. An end that touches another SBP wall continues its
HARD/SOFT pattern. The wall's settings are saved with it, so SBP Edit can change it later.
"""
__title__ = "SBP\nWall"
__author__ = "Akash"
__persistentengine__ = True     # keeps the "drawing finished" handler (sbp_draw) alive after the script ends

import os
import json

from Autodesk.Revit.DB import Transaction, ViewPlan, ElementId, CurveElement

from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

from pyrevit import revit, forms, script

import sbp_geom as G
import sbp_data as SD
import sbp_revit as SR
import sbp_draw

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

CFG_FILE = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "SBPTool", "settings.json")
DEFAULTS = {
    "wall": "SBP1", "type": "", "level": "", "spacing": "900", "gap": "150",
    "cutoff": "", "toe_hard": "", "toe_soft": "", "invisible": True,
}


def load_cfg():
    d = dict(DEFAULTS)
    try:
        with open(CFG_FILE) as f:
            d.update(json.load(f))
    except Exception:
        pass
    return d


def save_cfg(d):
    try:
        folder = os.path.dirname(CFG_FILE)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(CFG_FILE, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def fail(msg):
    forms.alert(msg, title="SBP Wall", exitscript=True)


def get_curve_elements():
    """1. lines selected before clicking, 2. lines just drawn with the Draw tools, 3. start drawing."""
    pre = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    pre = [e for e in pre if isinstance(e, CurveElement)]
    if pre:
        sbp_draw.stop(__revit__)
        return pre
    drawn = sbp_draw.take_drawn(doc)
    if drawn:
        return drawn
    # Nothing selected: open Revit's Modify | Place Lines tab (Draw panel). When the drafter finishes
    # (Modify / Esc), sbp_draw runs SBP Wall again with the new lines.
    sbp_draw.start_draw(__revit__, doc)
    script.exit()


def num(v, label, allow_blank=False):
    v = (v or "").strip()
    if not v and allow_blank:
        return None
    try:
        return float(v)
    except ValueError:
        fail("'{}' must be a number (mm). You entered: '{}'".format(label, v))


def ask_kind(end, mark):
    """Only asked when this wall touches a pile whose type cannot be read."""
    return forms.CommandSwitchWindow.show(
        ["HARD", "SOFT"],
        message="The {} of this wall joins pile '{}', but its type (HARD/SOFT) is unknown.\n"
                "Which type is that pile?".format(end, mark or "without a mark"))


def allow_template(name):
    return forms.alert("This view's template '{}' controls filters.\n\nAdd the SBP HARD/SOFT filters to the "
                       "template? Every view that uses it will show them.".format(name),
                       title="SBP Wall", yes=True, no=True)


def ask_inputs(cfg, types, levels, default_level):
    try:
        from rpw.ui.forms import FlexForm, Label, TextBox, ComboBox, CheckBox, Separator, Button
    except Exception:
        FlexForm = None

    def pick_default(keys, want):
        return want if want in keys else sorted(keys)[0]

    if FlexForm is not None:
        comps = [
            Label("Wall name (pile marks become e.g. SBP1-H001 / SBP1-S001):"),
            TextBox("wall", default=cfg["wall"]),
            Label("Pile type  (diameter is taken from the type):"),
            ComboBox("type", types, default=pick_default(types.keys(), cfg["type"])),
            Label("Placement level:"),
            ComboBox("level", levels, default=pick_default(levels.keys(), default_level)),
            Label("c/c spacing hard-to-soft (mm):"),
            TextBox("spacing", default=cfg["spacing"]),
            Label("Gap: your line to SBP inner edge (mm, min 150):"),
            TextBox("gap", default=cfg["gap"]),
            Label("Cut-off Level (mm, same datum as 'Elevation at Top'):"),
            TextBox("cutoff", default=cfg["cutoff"]),
            Label("Toe Level - HARD pile (mm):"),
            TextBox("toe_hard", default=cfg["toe_hard"]),
            Label("Toe Level - SOFT pile (mm, blank = same as hard):"),
            TextBox("toe_soft", default=cfg["toe_soft"]),
            CheckBox("invisible", "Make my line <Invisible lines> (like Defpoints)", default=bool(cfg["invisible"])),
            Separator(),
            Button("Next: click the wall side"),
        ]
        form = FlexForm("SBP Wall settings", comps)
        if not form.show():
            script.exit()
        v = form.values
        return {
            "wall": v["wall"].strip(), "sym": v["type"], "level": v["level"],
            "spacing": v["spacing"], "gap": v["gap"], "cutoff": v["cutoff"],
            "toe_hard": v["toe_hard"], "toe_soft": v["toe_soft"], "invisible": v["invisible"],
        }

    # Fallback: simple pyRevit prompts
    t = forms.SelectFromList.show(sorted(types.keys()), title="Pile type", multiselect=False)
    lv = forms.SelectFromList.show(sorted(levels.keys()), title="Placement level", multiselect=False)
    if not t or not lv:
        script.exit()
    ask = lambda k, p: forms.ask_for_string(default=str(cfg[k]), prompt=p, title="SBP Wall")
    res = {"sym": types[t], "level": levels[lv]}
    res["wall"] = (ask("wall", "Wall name") or "").strip()
    res["spacing"] = ask("spacing", "c/c spacing hard-to-soft (mm)")
    res["gap"] = ask("gap", "Gap line to SBP inner edge (mm, min 150)")
    res["cutoff"] = ask("cutoff", "Cut-off Level (mm)")
    res["toe_hard"] = ask("toe_hard", "Toe Level - HARD pile (mm)")
    res["toe_soft"] = ask("toe_soft", "Toe Level - SOFT pile (mm, blank = same as hard)")
    res["invisible"] = forms.alert("Make your line <Invisible lines>?", yes=True, no=True)
    return res


# ================================================================== MAIN
if not isinstance(doc.ActiveView, ViewPlan):
    fail("Open a plan view first (you need to click the wall side in plan).")

types = SR.pile_types(doc)
if not types:
    fail("Family '{}' is not loaded in this project.".format(SR.FAMILY_NAME))
levels = SR.all_levels(doc)

elements = get_curve_elements()
if not elements:
    script.exit()
try:
    items, closed = SR.build_chain(elements)
except ValueError as ex:
    fail(str(ex))

cfg = load_cfg()
gl = doc.ActiveView.GenLevel
inp = ask_inputs(cfg, types, levels, gl.Name if gl else cfg["level"])

wall = inp["wall"] or "SBP1"
s = {
    "spacing": num(inp["spacing"], "c/c spacing"),
    "gap": num(inp["gap"], "Gap"),
    "cutoff": num(inp["cutoff"], "Cut-off Level"),
    "toe_hard": num(inp["toe_hard"], "Toe Level - HARD"),
    "toe_soft": num(inp["toe_soft"], "Toe Level - SOFT", allow_blank=True),
    "invisible": bool(inp["invisible"]),
}
if s["toe_soft"] is None:
    s["toe_soft"] = s["toe_hard"]
errs = SD.check_settings(s)
if errs:
    fail("\n".join(errs))
symbol, level = inp["sym"], inp["level"]

save_cfg({
    "wall": wall, "type": SR.type_name(symbol), "level": level.Name,
    "spacing": inp["spacing"], "gap": inp["gap"], "cutoff": inp["cutoff"],
    "toe_hard": inp["toe_hard"], "toe_soft": inp["toe_soft"], "invisible": s["invisible"],
})

old = SR.wall_piles(doc, wall)
if old:
    if not forms.alert("{} piles already exist with marks '{}-...'.\nDelete them and rebuild?\n\n"
                       "Typed data (Loading, BH Ref ...) is copied to the nearest new pile of the same type."
                       .format(len(old), wall), yes=True, no=True):
        script.exit()
saved = SR.load_walls(doc).get(wall)

try:
    pk = uidoc.Selection.PickPoint("Click on the side of the line where the SBP wall should go")
except OperationCanceledException:
    script.exit()
side = G.pick_side(SR.chain_samples(items), (pk.X, pk.Y))
styles = SR.visible_styles(elements, saved[1].get("line_styles") if saved else None)

t = Transaction(doc, "SBP Wall - " + wall)
t.Start()
try:
    # --- read the real diameter from the type (probe instance)
    p0 = items[0][0].GetEndPoint(0)
    D = SR.probe_diameter(doc, symbol, level, (p0.X, p0.Y))
    D_mm = SR.to_mm(D)
    if s["spacing"] >= D_mm:
        raise Exception("c/c spacing ({:.0f}) must be less than pile diameter ({:.0f}) so the piles overlap.".format(s["spacing"], D_mm))

    # --- pile positions (joins to other SBP walls decide the pile type at each end)
    others = [fi for fi in SR.all_piles(doc) if SR.wall_of(fi) != wall]
    centres, kinds, info = SR.plan_wall(doc, items, closed, side, s, D, others, ask_kind)
    if not centres:
        raise Exception("No piles to place: the line is too short.")

    # --- replace the previous piles of this wall (keep their typed data)
    snap = SR.snapshot_data(old) if old else []
    for fi, k in old:
        doc.Delete(fi.Id)
    placed = SR.place_piles(doc, symbol, level, wall, centres, kinds)

    # --- set Cut-off / Toe (calibrated against what Revit displays)
    check = SR.apply_levels(doc, placed, s["cutoff"], s["toe_hard"], s["toe_soft"])
    copied, lost = SR.restore_data(snap, placed)

    # --- make the drawn line invisible
    line_errors = SR.hide_lines(doc, elements) if s["invisible"] else []

    # --- remember everything, so SBP Edit can change the wall later
    SR.save_wall(doc, SR.wall_data(wall, symbol, level, s, items, closed, side, styles), saved[0] if saved else None)
    t.Commit()
except Exception as ex:
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    fail("Nothing was placed.\n\n{}".format(ex))

# --- HARD / SOFT look (separate step: a problem here never undoes the piles)
look = {}
tg = Transaction(doc, "SBP Wall - HARD/SOFT look")
tg.Start()
try:
    look["2D"] = SR.apply_view_filters(doc, doc.ActiveView, allow_template)
    look["3D"] = SR.set_material(doc, [fi for fi, k in placed])
    tg.Commit()
except Exception as ex:
    if tg.HasStarted() and not tg.HasEnded():
        tg.RollBack()
    look = {"2D": "not applied: {}".format(ex), "3D": "not applied"}

uidoc.Selection.SetElementIds(List[ElementId]([fi.Id for fi, _ in placed]))

# ------------------------------------------------------------------ report
nh = sum(1 for k in kinds if k == SR.HARD)
ns = len(kinds) - nh
rows = [
    ["Pile type", SR.type_name(symbol)],
    ["Diameter (mm)", "{:.0f}".format(D_mm)],
    ["Design c/c hard-soft (mm)", "{:.0f}".format(s["spacing"])],
    ["Actual c/c along centre line (mm)", "{:.1f}".format(SR.to_mm(info["step"]))],
    ["Minimum overlap (mm)", "{:.1f}".format(D_mm - SR.to_mm(info["chord"]))],
    ["Gap line to inner edge (mm)", "{:.0f}".format(s["gap"])],
    ["Line to SBP centre line (mm)", "{:.0f}".format(SR.to_mm(info["dist"]))],
    ["Centre line length (m)", "{:.3f}".format(SR.to_mm(info["total"]) / 1000.0)],
    ["Shape", "Closed loop" if closed else "Open line"],
]
if not closed:
    rows += [["Start", SR.end_text(info["ends"]["start"], D)], ["End", SR.end_text(info["ends"]["end"], D)]]
rows += [
    ["HARD piles", str(nh)],
    ["SOFT piles", str(ns)],
    ["TOTAL piles", str(nh + ns)],
    ["Cut-off / Toe HARD (mm)", "{:.0f} / {:.0f}".format(*check.get(SR.HARD, (0, 0)))],
    ["Cut-off / Toe SOFT (mm)", "{:.0f} / {:.0f}".format(*check.get(SR.SOFT, (0, 0)))],
    ["Drawn line", "left as is" if not s["invisible"] else
     ("NOT made invisible (see below)" if line_errors else "<Invisible lines>")],
    ["Settings saved with the wall", "Yes (SBP Edit can change this wall)"],
    ["HARD/SOFT look (2D)", look["2D"]],
    ["Material (3D)", look["3D"]],
]
if old:
    rows.append(["Typed data copied", "{} piles".format(len(copied)) + (", {} not copied".format(len(lost)) if lost else "")])
output.print_md("## SBP Wall **{}**".format(wall))
output.print_table(table_data=rows, columns=["Item", "Value"])
for msg in line_errors:
    output.print_md("**Line style problem:** {}".format(msg))
far = [c for c in copied if c[2] > s["spacing"] / 2.0]
if far:
    output.print_md("**Typed data that moved more than half a c/c:** " +
                    ", ".join("{} -> {} ({:.0f} mm)".format(a, b, d) for a, b, d in far))
if lost:
    output.print_md("**Typed data NOT copied (no pile of the same type left):** " + ", ".join(lost))

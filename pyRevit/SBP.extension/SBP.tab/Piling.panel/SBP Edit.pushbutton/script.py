# -*- coding: utf-8 -*-
"""Edit one or more SBP walls in one go.

1. Click any pile(s) of the wall(s) (or select them first).
2. The form shows the wall's saved values. Change what you need, click OK.
   - Only Cut-off / Toe changed -> the same piles are kept (marks and typed data stay).
   - Spacing, gap, pile type, level changed, or your line was moved/reshaped -> the wall is
     rebuilt after you confirm; typed data goes to the nearest new pile of the same type.
With several walls, only the fields you change are applied to all of them.
After Apply it asks for the next piles straight away; press Esc (or Cancel) when you are done.
"""
__title__ = "SBP\nEdit"
__author__ = "Akash"

from Autodesk.Revit.DB import Transaction, ElementId
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

from pyrevit import revit, forms, script

import sbp_data as SD
import sbp_revit as SR

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

EDIT_KEYS = ("type", "level") + SD.NUM_KEYS + ("invisible",)


class Skip(Exception):
    """Leave this round and go back to picking piles."""


def fail(msg):
    forms.alert(msg, title="SBP Edit", exitscript=True)


def warn(msg):
    forms.alert(msg, title="SBP Edit")
    raise Skip()


def allow_template_lines(name):
    return forms.alert("Revit refused <Invisible lines> for the line, so it uses the line style '{}'.\n"
                       "This view's template '{}' controls line visibility.\n\nTurn '{}' off in the template?"
                       .format(SR.SBP_LINE_STYLE, name, SR.SBP_LINE_STYLE), title="SBP Edit", yes=True, no=True)


def ask_kind(end, mark):
    return forms.CommandSwitchWindow.show(
        ["HARD", "SOFT"],
        message="The {} of this wall joins pile '{}', but its type (HARD/SOFT) is unknown.\n"
                "Which type is that pile?".format(end, mark or "without a mark"))


def allow_template(name):
    return forms.alert("This view's template '{}' controls filters.\n\nAdd the SBP HARD/SOFT filters to the "
                       "template? Every view that uses it will show them.".format(name),
                       title="SBP Edit", yes=True, no=True)


def pick_piles(first):
    """Piles to edit, or None when the drafter is done (Esc / Cancel)."""
    if first:
        pre = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
        pre = [e for e in pre if SR.is_sbp_pile(e)]
        if pre:
            return pre
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, SR.PileFilter(),
            "Click the piles to edit (Tab = whole chain), then Finish = open the Edit form. Esc = done")
    except OperationCanceledException:
        return None
    return [doc.GetElement(r) for r in refs]


def num(v, label):
    try:
        return float((v or "").strip())
    except ValueError:
        warn("'{}' must be a number (mm). You entered: '{}'".format(label, v))


def own_values(data):
    """A wall's saved values in the form's terms."""
    v = dict((k, float(data[k])) for k in SD.NUM_KEYS)
    v["type"] = data.get("type_name")
    v["level"] = data.get("level_name")
    v["invisible"] = bool(data.get("invisible", True))
    return v


def ask_form(shown, names, types, levels):
    try:
        from rpw.ui.forms import FlexForm, Label, TextBox, ComboBox, CheckBox, Separator, Button
    except Exception:
        FlexForm = None
    tdef = shown["type"] if shown["type"] in types else sorted(types.keys())[0]
    ldef = shown["level"] if shown["level"] in levels else sorted(levels.keys())[0]
    head = "Editing: {}".format(", ".join(names))
    labels = [("spacing", "c/c spacing hard-to-soft (mm):"), ("gap", "Gap: your line to SBP inner edge (mm, min 150):"),
              ("cutoff", "Cut-off Level (mm):"), ("toe_hard", "Toe Level - HARD pile (mm):"),
              ("toe_soft", "Toe Level - SOFT pile (mm):")]
    if FlexForm is not None:
        comps = [Label(head)]
        if len(names) > 1:
            comps.append(Label("Only the fields you change are applied to all these walls."))
        comps += [Label("Pile type:"), ComboBox("type", types, default=tdef),
                  Label("Placement level:"), ComboBox("level", levels, default=ldef)]
        for k, text in labels:
            comps += [Label(text), TextBox(k, default=SD.fmt_num(shown[k]))]
        comps += [CheckBox("invisible", "Keep my line <Invisible lines>", default=shown["invisible"]),
                  Separator(), Button("Apply")]
        form = FlexForm("SBP Edit", comps)
        if not form.show():
            raise Skip()
        v = form.values
        res = {"type": SR.type_name(v["type"]), "level": v["level"].Name, "invisible": bool(v["invisible"])}
        for k, text in labels:
            res[k] = num(v[k], text.rstrip(":"))
        return res
    # Fallback: simple pyRevit prompts
    t = forms.SelectFromList.show(sorted(types.keys()), title="Pile type ({})".format(head), multiselect=False)
    lv = forms.SelectFromList.show(sorted(levels.keys()), title="Placement level", multiselect=False)
    if not t or not lv:
        raise Skip()
    res = {"type": t, "level": lv}
    for k, text in labels:
        res[k] = num(forms.ask_for_string(default=SD.fmt_num(shown[k]), prompt=text, title="SBP Edit"), text.rstrip(":"))
    res["invisible"] = forms.alert("Keep your line <Invisible lines>?", yes=True, no=True)
    return res


# ================================================================== MAIN
def edit_round(piles, rnd):
    """One round: form for the chosen walls, apply, report."""
    names = sorted(set(SR.wall_of(p) for p in piles if SR.wall_of(p)))
    if not names:
        warn("Select piles of an SBP wall (marks like SBP1-H001).")
    saved = SR.load_walls(doc)
    missing = [n for n in names if n not in saved]
    walls = [n for n in names if n in saved]
    if not walls:
        warn("No saved settings for: {}.\nThis wall was made before SBP Edit existed (before 25 Sep). Delete its piles "
             "and make it again with SBP Wall; after that SBP Edit works on it.".format(", ".join(missing)))
    if missing:
        forms.alert("No saved settings for: {} (made before 25 Sep): delete their piles and make them again with "
                    "SBP Wall.\n\nContinuing with: {}".format(", ".join(missing), ", ".join(walls)), title="SBP Edit")

    types = SR.pile_types(doc)
    levels = SR.all_levels(doc)
    if not types:
        fail("Family '{}' is not loaded in this project.".format(SR.FAMILY_NAME))
    shown = own_values(saved[walls[0]][1])
    new = ask_form(shown, walls, types, levels)
    changed = SD.changed_fields(shown, new, EDIT_KEYS)
    all_piles = SR.all_piles(doc)

    # ------------------------------------------------------------------ 1. work out what each wall needs
    plans = []
    for name in walls:
        ds, data = saved[name]
        before = own_values(data)
        after = dict(before)
        for k in changed:
            after[k] = new[k]
        p = {"name": name, "ds": ds, "data": data, "after": after, "mode": "none", "why": [], "note": ""}
        plans.append(p)
        wchanged = SD.changed_fields(before, after, EDIT_KEYS)
        p["why"] = list(wchanged)
        errs = SD.check_settings(after)
        p["symbol"] = types.get(after["type"])
        p["level"] = levels.get(after["level"])
        p["cur"] = SR.wall_piles(doc, name)
        if errs or p["symbol"] is None or p["level"] is None:
            p["mode"], p["note"] = "error", "; ".join(errs) or "pile type or level not found"
            continue
        p["elements"] = [doc.GetElement(u) for u in data.get("lines", [])]
        lines_ok = bool(p["elements"]) and all(e is not None for e in p["elements"])
        rebuild = SD.needs_rebuild(wchanged)
        if lines_ok:
            try:
                items, closed = SR.build_chain(p["elements"])
            except ValueError as ex:
                p["mode"], p["note"] = "error", str(ex)
                continue
            items = SR.orient_chain(items, data.get("anchor_uid"), data.get("anchor_reversed"))
            if p["cur"] and "type" not in wchanged:
                D = SR.diameter_of(p["cur"][0][0])
            else:
                tp = Transaction(doc, "SBP Edit - read pile size")
                tp.Start()
                D = None
                try:
                    p0 = items[0][0].GetEndPoint(0)
                    D = SR.probe_diameter(doc, p["symbol"], p["level"], (p0.X, p0.Y))
                except Exception as ex:
                    p["note"] = "cannot read the pile size: {}".format(ex)
                finally:
                    tp.RollBack()
                if D is None:
                    p["mode"] = "error"
                    continue
            if after["spacing"] >= SR.to_mm(D):
                p["mode"], p["note"] = "error", "c/c spacing must be less than the pile diameter ({:.0f})".format(SR.to_mm(D))
                continue
            others = [fi for fi in all_piles if SR.wall_of(fi) != name]
            centres, kinds, info = SR.plan_wall(doc, items, closed, data.get("side", 1.0), after, D, others, ask_kind)
            p.update({"centres": centres, "kinds": kinds, "info": info, "D": D, "items": items, "closed": closed})
            if not rebuild:
                now = [SR.xy(fi) + (k,) for fi, k in p["cur"]]
                if not SD.same_layout(now, [(x, y, k) for (x, y), k in zip(centres, kinds)], SR.mm(1.0)):
                    rebuild = True
                    p["why"].append("your line changed")
        elif rebuild:
            p["mode"], p["note"] = "error", "its drawn line was deleted, so it cannot be rebuilt"
            continue
        if rebuild:
            p["mode"] = "rebuild"
        elif any(k in SD.LEVEL_KEYS for k in wchanged):
            p["mode"] = "levels"
        elif lines_ok and after["invisible"] != all(SR.is_invisible(e) for e in p["elements"]):
            p["mode"] = "line"

    # ------------------------------------------------------------------ 2. one confirmation for all rebuilds
    rb = [p for p in plans if p["mode"] == "rebuild"]
    if rb:
        msg = "\n".join("{}: {} piles will be replaced by {} piles ({}).".format(
            p["name"], len(p["cur"]), len(p["centres"]), ", ".join(p["why"])) for p in rb)
        if not forms.alert(msg + "\n\nTyped data (Loading, BH Ref ...) is copied to the nearest new pile of the same type."
                                 "\nContinue?", title="SBP Edit", yes=True, no=True):
            raise Skip()

    # ------------------------------------------------------------------ 3. apply, one transaction per wall
    touched = []
    for p in plans:
        if p["mode"] in ("none", "error"):
            continue
        a = p["after"]
        t = Transaction(doc, "SBP Edit - " + p["name"])
        t.Start()
        try:
            p["copied"], p["lost"], p["check"] = [], [], {}
            if p["mode"] == "rebuild":
                snap = SR.snapshot_data(p["cur"])
                for fi, k in p["cur"]:
                    doc.Delete(fi.Id)
                piles_now = SR.place_piles(doc, p["symbol"], p["level"], p["name"], p["centres"], p["kinds"])
                p["check"] = SR.apply_levels(doc, piles_now, a["cutoff"], a["toe_hard"], a["toe_soft"])
                p["copied"], p["lost"] = SR.restore_data(snap, piles_now, SR.mm(5 * a["spacing"]))
                try:
                    ok, bad, err = SR.cut_soft_by_hard(doc, SR.hard_soft_pairs(piles_now, p["closed"], p["info"]["ends"]))
                    p["cut"] = "{} overlaps joined (HARD cuts SOFT)".format(ok) + (
                        ", {} failed: {}".format(bad, err) if bad else "")
                except Exception as ex:
                    p["cut"] = "not done: {}".format(ex)
            else:
                piles_now = p["cur"]
                if p["mode"] == "levels":
                    p["check"] = SR.apply_levels(doc, piles_now, a["cutoff"], a["toe_hard"], a["toe_soft"])
            p["line_errors"] = []
            if p.get("elements") and all(e is not None for e in p["elements"]):
                if a["invisible"]:
                    p["line_errors"] = SR.hide_lines(doc, p["elements"], doc.ActiveView, allow_template_lines)
                else:
                    p["line_errors"] = SR.show_lines(doc, p["elements"], p["data"].get("line_styles"), doc.ActiveView)
            try:
                p["material"] = SR.set_material(doc, [fi for fi, k in piles_now])
            except Exception as ex:
                p["material"] = "not set: {}".format(ex)
            data = dict(p["data"])
            data.update({"type_uid": p["symbol"].UniqueId, "type_name": a["type"],
                         "level_uid": p["level"].UniqueId, "level_name": a["level"], "invisible": a["invisible"]})
            for k in SD.NUM_KEYS:
                data[k] = a[k]
            SR.save_wall(doc, data, p["ds"])
            t.Commit()
            p["piles_now"] = piles_now
            touched += [fi for fi, k in piles_now]
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            p["mode"], p["note"] = "error", "nothing changed: {}".format(ex)

    # ------------------------------------------------------------------ 4. HARD / SOFT look in this view
    look = ""
    if touched:
        tg = Transaction(doc, "SBP Edit - HARD/SOFT look")
        tg.Start()
        try:
            look = SR.apply_view_filters(doc, doc.ActiveView, allow_template)
            tg.Commit()
        except Exception as ex:
            if tg.HasStarted() and not tg.HasEnded():
                tg.RollBack()
            look = "not applied: {}".format(ex)
        uidoc.Selection.SetElementIds(List[ElementId]([fi.Id for fi in touched]))

    # ------------------------------------------------------------------ report
    RESULT = {"rebuild": "wall rebuilt", "levels": "levels updated, same piles kept (marks and typed data kept)",
              "line": "line style updated", "none": "nothing changed", "error": "NOT changed"}
    output.print_md("## SBP Edit ({})".format(rnd))
    for p in plans:
        rows = [["What changed", ", ".join(p["why"]) or "nothing"], ["Result", RESULT[p["mode"]]]]
        if p["note"]:
            rows.append(["Why", p["note"]])
        if p["mode"] not in ("error",) and p.get("piles_now") is not None:
            ks = [k for fi, k in p["piles_now"]]
            nh = sum(1 for k in ks if k == SR.HARD)
            rows.append(["Piles", "{} ({} HARD / {} SOFT)".format(len(ks), nh, len(ks) - nh)])
            if p["mode"] == "rebuild":
                rows.append(["Actual c/c (mm)", "{:.1f}".format(SR.to_mm(p["info"]["step"]))])
                if not p["closed"]:
                    rows += [["Start", SR.end_text(p["info"]["ends"]["start"], p["D"])],
                             ["End", SR.end_text(p["info"]["ends"]["end"], p["D"])]]
                rows.append(["Typed data copied", "{} piles".format(len(p["copied"])) +
                             (", {} not copied".format(len(p["lost"])) if p["lost"] else "")])
                rows.append(["SOFT piles cut", p.get("cut", "")])
            for kind in (SR.HARD, SR.SOFT):
                if kind in p.get("check", {}):
                    rows.append(["Cut-off / Toe {} (mm)".format(kind), "{:.0f} / {:.0f}".format(*p["check"][kind])])
            rows.append(["Material (3D)", p.get("material", "")])
        output.print_md("### {}".format(SR.html(p["name"])))
        output.print_table(table_data=[[SR.html(x), SR.html(y)] for x, y in rows], columns=["Item", "Value"])
        far = [c for c in p.get("copied", []) if c[2] > p["after"]["spacing"] / 2.0]
        if far:
            output.print_md("**Typed data that moved more than half a c/c:** " +
                            ", ".join("{} -> {} ({:.0f} mm)".format(a, b, d) for a, b, d in far))
        if p.get("lost"):
            output.print_md("**Typed data NOT copied** (no pile of the same type within 5 c/c): " + ", ".join(p["lost"]))
        for msg in p.get("line_errors", []):
            output.print_md("**Line style:** {}".format(SR.html(msg)))
    if look:
        output.print_md("HARD/SOFT look (2D): {}".format(SR.html(look)))


first, rnd = True, 0
while True:
    piles = pick_piles(first)
    first = False
    if piles is None:            # Esc / Cancel: done
        break
    if not piles:
        continue
    rnd += 1
    try:
        edit_round(piles, rnd)
    except Skip:
        pass

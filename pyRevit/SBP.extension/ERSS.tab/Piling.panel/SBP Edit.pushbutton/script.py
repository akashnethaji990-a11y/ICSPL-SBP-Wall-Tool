# -*- coding: utf-8 -*-
"""Edit one or more SBP walls in one go.

1. Click any pile(s) of the wall(s) (or select them first).
2. The form shows the wall's saved values. Change what you need, click OK.
   - Only Cut-off / Toe changed -> the same piles are kept (marks and typed data stay).
   - Spacing, gap, a pile type, level changed, or your line was moved/reshaped -> the wall is
     rebuilt; typed data goes to the nearest new pile of the same type.
3. The values read and worked out for each wall are shown first (nothing is written yet): Apply, or cancel.
With several walls, only the fields you change are applied to all of them. A cutting depth or web you type is
applied with each wall's own diameters (your value wins; HARD to HARD follows).
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

FORM_KEYS = ("type", "soft_type", "level", "gap", "cutoff", "toe_hard", "toe_soft", "invisible", "close_n")
EDIT_KEYS = ("type", "soft_type", "level") + SD.NUM_KEYS + ("invisible", "close_n")
SAME = "(same as HARD)"          # SOFT pile type choice: the HARD type
MAX_LISTED = 20                  # warnings / errors listed per wall (the rest are counted)


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


def num(v, label, allow_blank=False):
    v = (v or "").strip()
    if not v and allow_blank:
        return None
    try:
        return float(v)
    except ValueError:
        warn("'{}' must be a number (mm). You entered: '{}'".format(label, v))


def ask_choice(question, options):
    """One question of the pile family set-up (asked once per family; the answer is saved in the model)."""
    return forms.SelectFromList.show(options, title=question, multiselect=False, button_name="Use this")


def print_list(title, lines):
    if lines:
        more = len(lines) - MAX_LISTED
        output.print_md("**{}:**<br>{}".format(title, "<br>".join(SR.html(x) for x in lines[:MAX_LISTED]) + (
            "<br>... and {} more".format(more) if more > 0 else "")))


def type_key(types, uid, name):
    """The pile type's name in the list, found by its id (so its shown name always matches)."""
    by_uid = [k for k, s in types.items() if s.UniqueId == uid]
    return by_uid[0] if by_uid else name


def own_values(data, types):
    """A wall's saved values in the form's terms."""
    v = dict((k, float(data[k])) for k in SD.NUM_KEYS)
    v["type"] = type_key(types, data.get("type_uid"), data.get("type_name"))
    v["soft_type"] = SAME if data.get("soft_type_uid") == data.get("type_uid") else type_key(
        types, data.get("soft_type_uid"), data.get("soft_type_name"))
    v["level"] = data.get("level_name")
    v["invisible"] = bool(data.get("invisible", True))
    v["spacing_by"] = data.get("spacing_by") or "spacing_hh"
    v["spacing_val"] = float(data["spacing_val"]) if data.get("spacing_val") is not None else v["spacing_hh"]
    v["close_n"] = SD.close_n(data)
    return v


def ask_form(shown, names, types, levels, dh, ds):
    """The edit form, filled with the first wall's values; dh / ds: its diameters (mm) for the spacing boxes."""
    try:
        from rpw.ui.forms import FlexForm, Label, TextBox, ComboBox, CheckBox, Separator, Button
    except Exception:
        FlexForm = None
    tdef = shown["type"] if shown["type"] in types else sorted(types.keys())[0]
    sdef = shown["soft_type"] if shown["soft_type"] in types else SAME
    ldef = shown["level"] if shown["level"] in levels else sorted(levels.keys())[0]
    soft_opts = dict(types)
    soft_opts[SAME] = SAME
    head = "Editing: {}".format(", ".join(names))
    boxes = SD.spacing_values(shown["spacing_hh"], dh, ds)
    boxes = dict((k, float(SD.fmt_num(round(boxes[k], 2))) if boxes[k] is not None else None) for k in SD.SPACING_KEYS)
    shown = dict(shown, **boxes)
    labels = [("spacing_hh", "c/c HARD to HARD (mm)  [spacing: type ANY ONE of these three, the others follow]:"),
              ("cut", "Cutting depth, each HARD into the SOFT = (Dh + Ds - HH) / 2 (mm, your value wins):"),
              ("web", "Leftover SOFT web = HH - Dh (mm, your value wins; below 200 = warning):"),
              ("gap", "Gap: your line to SBP inner edge (mm, min 10):"),
              ("cutoff", "Cut-off Level (mm):"), ("toe_hard", "Toe Level - HARD pile (mm):"),
              ("toe_soft", "Toe Level - SOFT pile (mm):"),
              ("close_n", "Closing SOFT piles (adjust, 1-6): the only bays that take the leftover:")]

    def finish(res):
        """res['spacing_changed'] = the spacing boxes changed (each wall applies them with its own diameters)."""
        entered = dict((k, res.pop(k)) for k in SD.SPACING_KEYS)
        res["spacing_changed"] = SD.changed_spacing(entered, shown)
        if res["spacing_changed"] and (dh is None or ds is None) and any(
                k != "spacing_hh" for k, v in res["spacing_changed"]):
            warn("The pile diameters of {} cannot be read, so change HARD to HARD.".format(names[0]))
        return res
    if FlexForm is not None:
        comps = [Label(head)]
        if len(names) > 1:
            comps.append(Label("Only the fields you change are applied to all these walls."))
        comps += [Label("HARD pile type:"), ComboBox("type", types, default=tdef),
                  Label("SOFT pile type:"), ComboBox("soft_type", soft_opts, default=sdef),
                  Label("Placement level:"), ComboBox("level", levels, default=ldef)]
        for k, text in labels:
            comps += [Label(text), TextBox(k, default=SD.fmt_num(shown[k]) if shown[k] is not None else "")]
        comps += [CheckBox("invisible", "Keep my line <Invisible lines>", default=shown["invisible"]),
                  Separator(), Button("Next: check the values")]
        form = FlexForm("SBP Edit", comps)
        if not form.show():
            raise Skip()
        v = form.values
        soft = v["soft_type"]
        res = {"type": SR.type_label(v["type"]), "soft_type": SAME if soft == SAME else SR.type_label(soft),
               "level": v["level"].Name, "invisible": bool(v["invisible"])}
        for k, text in labels:
            res[k] = num(v[k], text.rstrip(":"), allow_blank=k in SD.SPACING_KEYS)
        return finish(res)
    # Fallback: simple pyRevit prompts
    t = forms.SelectFromList.show(sorted(types.keys()), title="HARD pile type ({})".format(head), multiselect=False)
    st = forms.SelectFromList.show([SAME] + sorted(types.keys()), title="SOFT pile type", multiselect=False)
    lv = forms.SelectFromList.show(sorted(levels.keys()), title="Placement level", multiselect=False)
    if not t or not st or not lv:
        raise Skip()
    res = {"type": t, "soft_type": st, "level": lv}
    for k, text in labels:
        res[k] = num(forms.ask_for_string(default=SD.fmt_num(shown[k]) if shown[k] is not None else "", prompt=text,
                                          title="SBP Edit"), text.rstrip(":"), allow_blank=k in SD.SPACING_KEYS)
    res["invisible"] = forms.alert("Keep your line <Invisible lines>?", yes=True, no=True)
    return finish(res)


def pile_size(p, kind):
    """A wall's HARD or SOFT (diameter in internal units, where it was read), read fresh: from one of its piles of
    that type, else from the type."""
    sym = p["symbols"][kind]
    for fi, k in p["cur"]:
        if k == kind and fi.GetTypeId() == sym.Id:
            return SR.size_of(fi)
    return SR.type_size(doc, sym, p["level"])


# ================================================================== MAIN
def edit_round(piles, rnd):
    """One round: form for the chosen walls, check, apply, report."""
    names = sorted(set(SR.wall_of(p) for p in piles if SR.wall_of(p)))
    if not names:
        warn("Select piles of an SBP wall.")
    saved = SR.load_walls(doc)
    missing = [n for n in names if n not in saved]
    walls = [n for n in names if n in saved]
    if not walls:
        warn("No saved settings for: {}.\nThis wall was made before SBP Edit existed (before 25 Sep). Delete its piles "
             "and make it again with SBP Wall; after that SBP Edit works on it.".format(", ".join(missing)))
    if missing:
        forms.alert("No saved settings for: {} (made before 25 Sep): delete their piles and make them again with "
                    "SBP Wall.\n\nContinuing with: {}".format(", ".join(missing), ", ".join(walls)), title="SBP Edit")

    SR.clear_pile_specs()
    types = SR.pile_types(doc)
    levels = SR.all_levels(doc)
    if not types:
        fail("No pile family is loaded in this project (Shift+Click on SBP Wall sets one up).")
    shown = own_values(saved[walls[0]][1], types)
    first = SR.wall_piles(doc, walls[0])
    d_first = {}
    for kind in (SR.HARD, SR.SOFT):
        try:
            pile = [fi for fi, k in first if k == kind]
            d_first[kind] = SR.to_mm(SR.diameter_of(pile[0])) if pile else None
        except Exception:
            d_first[kind] = None
    new = ask_form(shown, walls, types, levels, d_first[SR.HARD], d_first[SR.SOFT])
    changed = SD.changed_fields(shown, new, FORM_KEYS)
    all_piles = SR.all_piles(doc)

    # ------------------------------------------------------------------ 1. work out what each wall needs
    plans = []
    for name in walls:
        ds_el, data = saved[name]
        before = own_values(data, types)
        after = dict(before)
        for k in changed:
            after[k] = new[k]
        p = {"name": name, "ds": ds_el, "data": data, "after": after, "mode": "none", "why": [], "note": "",
             "warns": [], "errs": []}
        plans.append(p)
        sym_h = types.get(after["type"])
        sym_s = sym_h if after["soft_type"] == SAME else types.get(after["soft_type"])
        p["level"] = levels.get(after["level"])
        p["cur"] = SR.wall_piles(doc, name)
        if sym_h is None or sym_s is None or p["level"] is None:
            p["mode"], p["note"] = "error", "pile type or level not found"
            continue
        p["symbols"] = {SR.HARD: sym_h, SR.SOFT: sym_s}
        if after["type"] != before["type"] or after["soft_type"] != before["soft_type"]:
            try:                            # a new pile family is set up once (asked, saved in the model)
                if any(SR.ensure_pile_spec(doc, sym, p["level"], ask_choice) is None for sym in (sym_h, sym_s)):
                    p["mode"], p["note"] = "error", "the pile family set-up was cancelled"
                    continue
            except Exception as ex:
                p["mode"], p["note"] = "error", str(ex)
                continue
        # this wall's real HARD and SOFT diameters (after the edit)
        try:
            sizes = dict((kind, pile_size(p, kind)) for kind in (SR.HARD, SR.SOFT))
            why = ""
        except Exception as ex:
            sizes, why = {SR.HARD: (None, None), SR.SOFT: (None, None)}, ": {}".format(ex)
        dia = dict((kind, sizes[kind][0]) for kind in sizes)
        p["size_src"] = dict((kind, sizes[kind][1]) for kind in sizes)
        if dia[SR.HARD] is None or dia[SR.SOFT] is None:
            p["mode"], p["note"] = "error", "cannot read the pile size" + why
            continue
        same = p["symbols"][SR.SOFT].Id == p["symbols"][SR.HARD].Id
        bad = [m for m in (SD.size_name_mismatch(kind, SR.type_name(p["symbols"][kind]), SR.to_mm(dia[kind]))
                           for kind in ((SR.HARD,) if same else (SR.HARD, SR.SOFT))) if m]
        if bad:
            p["mode"], p["note"] = "error", " ".join(bad)
            continue
        p["dia"] = dia
        dh, ds = SR.to_mm(dia[SR.HARD]), SR.to_mm(dia[SR.SOFT])
        # spacing: a box typed now (applied with this wall's diameters), else the wall's own saved value
        p["how"] = "typed now"
        if new["spacing_changed"]:
            key, val, note, err = SD.spacing_driver(new["spacing_changed"], dh, ds)
            if err:
                p["mode"], p["note"] = "error", err
                continue
            if note:
                p["warns"].append(note)
        else:
            key, val, p["how"] = before["spacing_by"], before["spacing_val"], "saved with the wall"
        after.update(spacing_hh=SD.hh_from(key, val, dh, ds), spacing_by=key, spacing_val=val)
        wchanged = SD.changed_fields(before, after, EDIT_KEYS)
        p["why"] = list(wchanged)
        errs, warns = SD.check_spacing(after["spacing_hh"], dh, ds)
        errs = SD.check_settings(after) + errs
        if errs:
            p["mode"], p["note"] = "error", "; ".join(errs)
            continue
        after["close_n"] = int(after["close_n"])
        p["warns"] += warns
        p["elements"] = [doc.GetElement(u) for u in data.get("lines", [])]
        lines_ok = bool(p["elements"]) and all(e is not None for e in p["elements"])
        rebuild = SD.needs_rebuild(wchanged)
        layout = int(data.get("layout", 1))          # 1: equal spacing, 2: corner rule, 3: closing zone (6 Oct)
        if lines_ok:
            try:
                items, closed = SR.build_chain(p["elements"])
            except ValueError as ex:
                p["mode"], p["note"] = "error", str(ex)
                continue
            items = SR.orient_chain(items, data.get("anchor_uid"), data.get("anchor_reversed"))
            others = [fi for fi in all_piles if SR.wall_of(fi) != name]
            side = data.get("side", 1.0)
            plan = None
            if not rebuild:
                # was the line moved? compare with the layout this wall was made with
                if layout < 2:
                    centres, kinds, info = SR.plan_wall_v1(doc, items, closed, side, before, dia[SR.HARD], others,
                                                           ask_kind)
                elif layout == 2:
                    centres, kinds, info = SR.plan_wall_v2(doc, items, closed, side, after, dia[SR.HARD],
                                                           dia[SR.SOFT], others, ask_kind)
                else:
                    plan = SR.plan_wall(doc, items, closed, side, after, dia[SR.HARD], dia[SR.SOFT], others, ask_kind)
                    centres, kinds, info = plan
                now = [SR.xy(fi) + (k,) for fi, k in p["cur"]]
                if not SD.same_layout(now, [(x, y, k) for (x, y), k in zip(centres, kinds)], SR.mm(1.0)):
                    rebuild = True
                    p["why"].append("your line changed")
            if rebuild:
                if plan is None:
                    plan = SR.plan_wall(doc, items, closed, side, after, dia[SR.HARD], dia[SR.SOFT], others, ask_kind)
                centres, kinds, info = plan
                p["rows"], lw, le = SR.plan_rows(name, after, sym_h, sym_s, centres, kinds, info, closed, p["how"],
                                                 p["size_src"])
                p["warns"] += lw
                p["errs"] += le
                if layout < 3:
                    p["warns"].append("made with the {} layout: rebuilt with the closing-zone layout (exact c/c, "
                                      "only the closing bays adjusted)".format(
                                          "old (equal spacing)" if layout < 2 else "v2 (corner rule)"))
            p.update({"centres": centres, "kinds": kinds, "info": info, "items": items, "closed": closed})
        elif rebuild:
            p["mode"], p["note"] = "error", "its drawn line was deleted, so it cannot be rebuilt"
            continue
        if rebuild:
            p["mode"] = "rebuild"
            # layout numbers (Number button) do not survive a rebuild: the new piles get SBP Wall's marks
            p["numbered"] = any(SR.mark_of(fi) and not SD.is_default_mark(SR.mark_of(fi), name) for fi, k in p["cur"])
        elif any(k in SD.LEVEL_KEYS for k in wchanged):
            p["mode"] = "levels"
        elif lines_ok and after["invisible"] != all(SR.is_invisible(e) for e in p["elements"]):
            p["mode"] = "line"
        elif wchanged or p["after"]["spacing_by"] != before["spacing_by"]:
            p["mode"] = "data"               # only the saved values change (e.g. which spacing value is yours)

    # ------------------------------------------------------------------ 2. the values, then one confirmation
    todo = [p for p in plans if p["mode"] not in ("none", "error")]
    for p in plans:
        if p["mode"] == "error":
            output.print_md("### {}: NOT changed".format(SR.html(p["name"])))
            output.print_md(SR.html(p["note"]))
    if not todo:
        if any(p["mode"] == "error" for p in plans):
            forms.alert("Nothing can be changed:\n" + "\n".join("{}: {}".format(p["name"], p["note"])
                                                                for p in plans if p["mode"] == "error"), title="SBP Edit")
        else:
            forms.alert("Nothing changed.", title="SBP Edit")
        raise Skip()
    output.print_md("## SBP Edit ({}): check before applying (nothing written yet)".format(rnd))
    lines = []
    for p in todo:
        a = p["after"]
        output.print_md("### {}: {}".format(SR.html(p["name"]), {
            "rebuild": "rebuild", "levels": "levels only (same piles)", "line": "line style only",
            "data": "saved values only"}[p["mode"]]))
        if p["mode"] == "rebuild":
            output.print_table(table_data=[[SR.html(x), SR.html(y)] for x, y in p["rows"]], columns=["Item", "Value"])
            bay_rows, bay_cols = SR.bay_table(p["name"], a, p["centres"], p["kinds"], p["info"], p["closed"])
            if bay_rows:
                output.print_md("#### Every bay of {} (straight c/c, corners never adjusted)".format(SR.html(p["name"])))
                output.print_table(table_data=[[SR.html(c) for c in r] for r in bay_rows], columns=bay_cols)
            nh = sum(1 for k in p["kinds"] if k == SR.HARD)
            v = SD.spacing_values(a["spacing_hh"], SR.to_mm(p["dia"][SR.HARD]), SR.to_mm(p["dia"][SR.SOFT]))
            lines.append("{}: {} piles replaced by {} ({} H + {} S); HARD to HARD {:.0f}, cutting {:.0f}, web {:.0f} "
                         "({})".format(p["name"], len(p["cur"]), len(p["kinds"]), nh, len(p["kinds"]) - nh,
                                       v["spacing_hh"], v["cut"], v["web"], ", ".join(p["why"])))
        elif p["mode"] == "levels":
            b = own_values(p["data"], types)
            rows = [["Cut-off (mm)", "{:.0f} -> {:.0f}".format(b["cutoff"], a["cutoff"])],
                    ["Toe HARD (mm)", "{:.0f} -> {:.0f}".format(b["toe_hard"], a["toe_hard"])],
                    ["Toe SOFT (mm)", "{:.0f} -> {:.0f}".format(b["toe_soft"], a["toe_soft"])],
                    ["Piles", "{} kept (marks and typed data kept)".format(len(p["cur"]))]]
            output.print_table(table_data=rows, columns=["Item", "Value"])
            lines.append("{}: levels only, {} piles kept".format(p["name"], len(p["cur"])))
        else:
            lines.append("{}: {}".format(p["name"], ", ".join(p["why"]) or "saved values"))
        print_list("WARNINGS", p["warns"])
        print_list("ERRORS", p["errs"])
    msg = "\n".join(lines)
    numbered = [p["name"] for p in todo if p.get("numbered")]
    if numbered:
        msg += "\n\nPile numbers (Number button) of {} are cleared by the rebuild: run Number again after.".format(
            ", ".join(numbered))
    if any(p["mode"] == "rebuild" for p in todo):
        msg += "\n\nTyped data (Loading, BH Ref ...) is copied to the nearest new pile of the same type."
    nw = sum(len(p["warns"]) for p in todo)
    ne = sum(len(p["errs"]) for p in todo)
    if not forms.alert(msg, title="SBP Edit: check before applying",
                       sub_msg="{} warning(s), {} error(s). All values are in the report window. Apply?".format(nw, ne),
                       yes=True, no=True, warn_icon=bool(nw or ne)):
        output.print_md("Cancelled: nothing was changed.")
        raise Skip()

    # ------------------------------------------------------------------ 3. apply, one transaction per wall
    touched = []
    for p in todo:
        a = p["after"]
        t = Transaction(doc, "SBP Edit - " + p["name"])
        t.Start()
        try:
            p["copied"], p["lost"], p["check"] = [], [], {}
            if p["mode"] == "rebuild":
                snap = SR.snapshot_data(p["cur"])
                for fi, k in p["cur"]:
                    doc.Delete(fi.Id)
                # Number tags go with their piles; Number annotations (copied text) must go too
                p["notes_removed"] = SR.delete_number_notes(doc, p["name"])
                piles_now = SR.place_piles(doc, p["symbols"], p["level"], p["name"], p["centres"], p["kinds"])
                p["check"] = SR.apply_levels(doc, piles_now, a["cutoff"], a["toe_hard"], a["toe_soft"])
                p["copied"], p["lost"] = SR.restore_data(snap, piles_now, SR.mm(2.5 * a["spacing_hh"]))
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
            sym = p["symbols"]
            data.update({"type_uid": sym[SR.HARD].UniqueId, "type_name": SR.type_name(sym[SR.HARD]),
                         "soft_type_uid": sym[SR.SOFT].UniqueId, "soft_type_name": SR.type_name(sym[SR.SOFT]),
                         "level_uid": p["level"].UniqueId, "level_name": a["level"], "invisible": a["invisible"],
                         "spacing_by": a["spacing_by"], "spacing_val": a["spacing_val"], "close_n": a["close_n"]})
            data.pop("spacing", None)
            for k in SD.NUM_KEYS:
                data[k] = a[k]
            if p["mode"] == "rebuild":
                data["layout"] = 3
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
              "line": "line style updated", "data": "saved values updated", "none": "nothing changed",
              "error": "NOT changed"}
    output.print_md("## SBP Edit ({}): done".format(rnd))
    for p in todo:
        rows = [["What changed", ", ".join(p["why"]) or "nothing"], ["Result", RESULT[p["mode"]]]]
        if p["note"]:
            rows.append(["Why", p["note"]])
        if p["mode"] != "error" and p.get("piles_now") is not None:
            ks = [k for fi, k in p["piles_now"]]
            nh = sum(1 for k in ks if k == SR.HARD)
            rows.append(["Piles", "{} ({} HARD / {} SOFT)".format(len(ks), nh, len(ks) - nh)])
            if p["mode"] == "rebuild":
                big = max(p["dia"][SR.HARD], p["dia"][SR.SOFT])
                if not p["closed"]:
                    rows += [["Start", SR.end_text(p["info"]["ends"]["start"], big)],
                             ["End", SR.end_text(p["info"]["ends"]["end"], big)]]
                rows.append(["Typed data copied", "{} piles".format(len(p["copied"])) +
                             (", {} not copied".format(len(p["lost"])) if p["lost"] else "")])
                rows.append(["SOFT piles cut", p.get("cut", "")])
                if p.get("numbered") or p.get("notes_removed"):
                    rows.append(["Pile numbers", "cleared by the rebuild{}: run Number again".format(
                        " ({} annotation labels removed)".format(p["notes_removed"]) if p.get("notes_removed") else "")])
            for kind in (SR.HARD, SR.SOFT):
                if kind in p.get("check", {}):
                    rows.append(["Cut-off / Toe {} (mm)".format(kind), "{:.0f} / {:.0f}".format(*p["check"][kind])])
            rows.append(["Material (3D)", p.get("material", "")])
        output.print_md("### {}".format(SR.html(p["name"])))
        output.print_table(table_data=[[SR.html(x), SR.html(y)] for x, y in rows], columns=["Item", "Value"])
        far = [c for c in p.get("copied", []) if c[2] > p["after"]["spacing_hh"] / 4.0]
        if far:
            output.print_md("**Typed data that moved more than half a c/c:** " +
                            ", ".join("{} -> {} ({:.0f} mm)".format(a, b, d) for a, b, d in far))
        if p.get("lost"):
            output.print_md("**Typed data NOT copied** (no pile of the same type within 5 c/c): " + ", ".join(p["lost"]))
        for msg in p.get("line_errors", []):
            output.print_md("**Line style:** {}".format(SR.html(msg)))
        if p["mode"] != "error" and p.get("piles_now") is not None:
            dia_mm = {SR.HARD: SR.to_mm(p["dia"][SR.HARD]), SR.SOFT: SR.to_mm(p["dia"][SR.SOFT])}
            comp_rows, n_below, n_above = SR.spacing_compliance_table(p["piles_now"], dia_mm, p["closed"])
            output.print_md("#### Spacing Compliance  (HARD to next HARD, SOFT to next SOFT; min = diameter + 600 mm)  "
                            "{} below / {} above / {} OK".format(
                                n_below, n_above, len(comp_rows) - n_below - n_above))
            output.print_table(
                table_data=[[SR.html(r[0]), r[1], r[2], r[3], SR.html(r[4])] for r in comp_rows],
                columns=["Pile", "Diam (mm)", "Same-type c/c (mm)", "Required (mm)", "Spacing Compliance"])
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

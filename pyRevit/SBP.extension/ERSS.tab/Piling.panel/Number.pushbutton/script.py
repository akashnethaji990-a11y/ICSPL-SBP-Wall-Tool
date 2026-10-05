# -*- coding: utf-8 -*-
"""Number: write layout-plan pile numbers into the Mark of SBP wall piles (SP1, HP1, SP2, HP2 ...),
and label them with tags in the current plan view.

1. Click a pile of each wall to number, in the order the walls should be numbered; Esc = done.
   (Or select piles of the walls first: they are then numbered in name order.)
2. Dialog: SOFT / HARD prefixes (default SP / HP, e.g. C1-SP), and Continue from the last number
   on the same level, or Start new at 1. A live line shows where the numbering carries on.
   Labels: tag type (one that shows Mark, or none), offset from the pile edge (default 50 mm, just
   clear), rotation (default Fixed 0 = horizontal, reads left to right; or along / across the wall),
   and the side of the labels per wall (outside / inside).
3. A summary to confirm. Nothing is written before you click Yes.
Piles are numbered in draw order from the start end of each wall. SOFT and HARD are counted
separately and run on across the walls of the same level. The wall is known from each pile's
hidden data, so SBP Edit / Select / Line / Count keep working after the marks change.
One label per pile, next to its own pile, never stacked in rows and never overlapping: a label that
would touch another goes to the other side of the wall, or is nudged slightly; the report counts those.
"""
__title__ = "Number"
__author__ = "Akash"

import json
import math
import os

import clr
# WPF assemblies for NumberWindow: the System.Windows imports below need them (as in pyrevit.framework)
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from Autodesk.Revit.DB import Transaction, TransactionGroup, ElementId, BuiltInParameter, ViewPlan
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List
from System.Windows import Visibility, VerticalAlignment, Thickness
from System.Windows.Controls import StackPanel, TextBlock, ComboBox, Orientation

from pyrevit import revit, forms, script

import sbp_data as SD
import sbp_geom as G
import sbp_revit as SR

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

TITLE = "Number"
DEFAULT_SOFT, DEFAULT_HARD = "SP", "HP"
DEFAULT_OFFSET_MM = 50.0          # just clear of the pile edge
DEFAULT_ROTATION = 0.0            # fixed, horizontal: every label reads left to right
CFG_OFFSET, CFG_ROTATION = "number_label_offset", "number_label_rotation"
NO_LABELS = "No labels (marks only)"
SIDES = ("outside", "inside")
CFG_FILE = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "SBPTool", "settings.json")


def load_cfg():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(values):
    """Remember the label settings next to SBP Wall's last-used values (same file)."""
    try:
        d = load_cfg()
        d.update(values)
        folder = os.path.dirname(CFG_FILE)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(CFG_FILE, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def pick_walls():
    """Wall names in the order they will be numbered ([] = none chosen)."""
    names = []
    for i in uidoc.Selection.GetElementIds():
        e = doc.GetElement(i)
        if SR.is_sbp_pile(e) and SR.wall_of(e) not in names:
            names.append(SR.wall_of(e))
    if names:
        return sorted(names, key=SD.natural_key)
    while True:
        prompt = "Click a pile of the {} wall to number{}. Esc = done".format(
            "next" if names else "first", " (chosen: {})".format(", ".join(names)) if names else "")
        try:
            ref = uidoc.Selection.PickObject(ObjectType.Element, SR.PileFilter(), prompt)
        except OperationCanceledException:
            return names
        w = SR.wall_of(doc.GetElement(ref))
        if w and w not in names:
            names.append(w)
            ids = [fi.Id for fi in SR.all_piles(doc) if SR.wall_of(fi) in names]
            uidoc.Selection.SetElementIds(List[ElementId](ids))


def first_upper(text):
    return text[:1].upper() + text[1:]


def guess_closed(ordered):
    """Walls made before 25 Sep have no saved settings: a loop ends next to where it starts."""
    pts = [SR.xy(fi) for fi, k in ordered]
    if len(pts) < 4:
        return False
    steps = sorted(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts[:-1], pts[1:]))
    return math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < 1.5 * steps[len(steps) // 2]


def rotation_text(rot):
    if rot in ("along", "across"):
        return rot + " the wall"
    return "horizontal" if float(rot) == 0 else "fixed {} deg from horizontal".format(SD.fmt_num(rot))


class NumberWindow(forms.WPFWindow):
    """Prefixes + Continue / Start new + label options, with a live line.
    result = (soft, hard, continue, labels) or None; labels = None or dict(tag, offset, rotation, sides)."""

    def __init__(self, walls, others_by_level, tag_names, cfg, label_block, unusable, note_params):
        self._ready = False
        self.unusable = unusable            # {tag type shown name: why it cannot label a pile}
        self.note_params = note_params      # {Generic Annotation shown name: text parameter for the number}
        self.walls = walls
        self.others = others_by_level
        self.levels = []
        for w in walls:
            if w["level"] not in self.levels:
                self.levels.append(w["level"])
        self.result = None
        forms.WPFWindow.__init__(self, "NumberWindow.xaml")
        self.walls_tb.Text = "Walls, numbered in this order from their start end:\n" + ", ".join(
            "{} ({} piles, {})".format(w["name"], len(w["piles"]), w["level"]) for w in walls)
        self.soft_tb.Text = DEFAULT_SOFT
        self.hard_tb.Text = DEFAULT_HARD
        # labels
        self.tag_cb.Items.Add(NO_LABELS)
        for n in tag_names:
            self.tag_cb.Items.Add(n)
        want = cfg.get("number_tag")
        self.tag_cb.SelectedIndex = tag_names.index(want) + 1 if want in tag_names else 0
        try:
            self.offset_tb.Text = SD.fmt_num(cfg.get(CFG_OFFSET, DEFAULT_OFFSET_MM))
        except (TypeError, ValueError):
            self.offset_tb.Text = SD.fmt_num(DEFAULT_OFFSET_MM)
        rot = cfg.get(CFG_ROTATION, DEFAULT_ROTATION)
        if rot == "along":
            self.rot_along.IsChecked = True
        elif rot == "across":
            self.rot_across.IsChecked = True
        else:
            try:
                self.angle_tb.Text = SD.fmt_num(rot)
            except (TypeError, ValueError):
                self.angle_tb.Text = SD.fmt_num(DEFAULT_ROTATION)   # unreadable saved value: horizontal
            self.rot_fixed.IsChecked = True
        self.side_cbs = {}
        for w in walls:
            row = StackPanel()
            row.Orientation = Orientation.Horizontal
            row.Margin = Thickness(0, 2, 0, 2)
            tb = TextBlock()
            tb.Text = w["name"]
            tb.Width = 170
            tb.VerticalAlignment = VerticalAlignment.Center
            cb = ComboBox()
            cb.Width = 120
            for s in SIDES:
                cb.Items.Add(first_upper(s))
            cb.SelectedIndex = SIDES.index(w["label_side"])
            cb.SelectionChanged += self.refresh
            row.Children.Add(tb)
            row.Children.Add(cb)
            self.side_panel.Children.Add(row)
            self.side_cbs[w["name"]] = cb
        if label_block:
            self.tag_cb.SelectedIndex = 0
            self.label_grid.IsEnabled = False
            self.side_panel.IsEnabled = False
            self.labels_note.Text = label_block
            self.labels_note.Visibility = Visibility.Visible
        self._ready = True
        self.refresh(None, None)

    def values(self):
        return self.soft_tb.Text.strip(), self.hard_tb.Text.strip(), bool(self.continue_rb.IsChecked)

    def labels(self):
        """(label settings or None, list of problems)."""
        tag = self.tag_cb.SelectedItem
        if not tag or tag == NO_LABELS:
            return None, []
        errs = []
        if tag in self.unusable:
            errs.append("Tag type '{}' cannot label the piles: {}".format(tag, self.unusable[tag]))
        try:
            offset = float(self.offset_tb.Text.strip())
            if offset < 0:
                errs.append("The offset cannot be negative.")
        except ValueError:
            offset = None
            errs.append("The offset must be a number (mm).")
        if self.rot_across.IsChecked:
            rot = "across"
        elif self.rot_fixed.IsChecked:
            try:
                rot = float(self.angle_tb.Text.strip())
            except ValueError:
                rot = None
                errs.append("The fixed angle must be a number (deg).")
        else:
            rot = "along"
        sides = dict((n, SIDES[cb.SelectedIndex]) for n, cb in self.side_cbs.items())
        return {"tag": tag, "offset": offset, "rotation": rot, "sides": sides,
                "param": self.note_params.get(tag)}, errs

    def last_numbers(self, soft, hard, cont):
        """{level: (last SOFT, last HARD)} to carry on from (0, 0 = start at 1)."""
        res = {}
        for lv in self.levels:
            marks = self.others.get(lv, [])
            res[lv] = (SD.max_number(marks, soft), SD.max_number(marks, hard)) if cont else (0, 0)
        return res

    def plan(self, soft, hard, cont):
        kinds = [(w["name"], w["level"], [k for fi, k in w["piles"]]) for w in self.walls]
        return SD.number_plan(kinds, soft, hard, self.last_numbers(soft, hard, cont))

    def refresh(self, sender, args):
        if not getattr(self, "_ready", False):
            return          # events fired while the window is still loading
        soft, hard, cont = self.values()
        lab, lerrs = self.labels()
        errs = SD.check_prefixes(soft, hard) + lerrs
        self.ok_btn.IsEnabled = not errs
        if errs:
            self.live_tb.Text = "\n".join(errs)
            return
        last = self.last_numbers(soft, hard, cont)
        lines = []
        for lv in self.levels:
            head = "{}: ".format(lv) if len(self.levels) > 1 else ""
            if cont:
                s, h = last[lv]
                lines.append(head + first_upper(SD.continue_text(soft, s)) + ".")
                lines.append(head + first_upper(SD.continue_text(hard, h)) + ".")
            else:
                lines.append(head + "Starts new at {}1 and {}1.".format(soft, hard))
        lines.append("")
        for name, lv, marks, rng in self.plan(soft, hard, cont):
            side = " (labels {})".format(lab["sides"][name]) if lab else ""
            lines.append("{}: {}, {}{}".format(name, SD.range_text(soft, rng[SR.SOFT]), SD.range_text(hard, rng[SR.HARD]), side))
        lines.append("")
        lines.append("Labels: {} mm from the pile edge, {}.".format(SD.fmt_num(lab["offset"]), rotation_text(lab["rotation"]))
                     if lab else "Labels: none, only the marks are written.")
        if lab and lab["param"]:
            lines.append("Generic Annotation: the number is copied into its '{}'. It does not follow later Mark "
                         "changes; running Number again updates it.".format(lab["param"]))
        self.live_tb.Text = "\n".join(lines)

    def ok_click(self, sender, args):
        soft, hard, cont = self.values()
        lab, lerrs = self.labels()
        if SD.check_prefixes(soft, hard) or lerrs:
            return
        self.result = (soft, hard, cont, lab)
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


# ================================================================== MAIN
names = pick_walls()
if not names:
    script.exit()

all_piles = SR.all_piles(doc)
by_wall = {}
for fi in all_piles:
    w = SR.wall_of(fi)
    if w in names:
        by_wall.setdefault(w, []).append((fi, SR.kind_of(fi)))
saved = SR.load_walls(doc)

walls, skipped = [], []
for name in names:
    piles = by_wall.get(name, [])
    if not piles:
        continue
    if any(k not in (SR.HARD, SR.SOFT) for fi, k in piles):
        skipped.append("{}: a pile has no HARD/SOFT type".format(name))
        continue
    ordered = SR.wall_in_order(piles)
    if not ordered:
        skipped.append("{}: the order of its piles is unknown (old piles whose marks were changed). "
                       "Rebuild it with SBP Edit first.".format(name))
        continue
    per_level = {}
    for fi, k in piles:
        lv = SR.level_name(doc, fi)
        per_level[lv] = per_level.get(lv, 0) + 1
    ds, data = saved.get(name, (None, None))
    side = (data or {}).get("label_side")
    walls.append({"name": name, "level": max(per_level, key=per_level.get), "piles": ordered, "ds": ds, "data": data,
                  "closed": bool(data.get("closed")) if data else guess_closed(ordered),
                  "label_side": side if side in SIDES else "outside"})
if skipped:
    forms.alert("Not numbered:\n\n" + "\n".join(skipped), title=TITLE, exitscript=not walls)
if not walls:
    script.exit()

# marks of all OTHER piles: Continue carries on from them (per level), and they show duplicates
chosen = set(fi.UniqueId for w in walls for fi, k in w["piles"])
others_by_level, other_marks = {}, set()
for fi in all_piles:
    m = SR.mark_of(fi).strip()
    if m and fi.UniqueId not in chosen:
        others_by_level.setdefault(SR.level_name(doc, fi), []).append(m)
        other_marks.add(m)

view = doc.ActiveView
# Tag type dropdown: Structural Foundation tags, then Multi-Category tags, Generic Model tags, Generic Annotations
entries = SR.label_types(doc)
tag_types = dict((n, s) for n, s, k in entries)
tag_names = [n for n, s, k in entries]
unusable, note_params = {}, {}
label_block = None
if not isinstance(view, ViewPlan) or view.IsTemplate:
    label_block = "Labels need a plan view: open one and run Number again to place them. Only the marks are written now."
elif not tag_names:
    label_block = ("No tag or Generic Annotation family is loaded. Load one that shows Mark to place labels. "
                   "Only the marks are written now.")
else:
    unusable, note_params = SR.unusable_label_types(doc, view, walls[0]["piles"][0][0], entries)   # rolled back
cfg = load_cfg()
if cfg.get("number_tag") not in tag_types or cfg.get("number_tag") in unusable:
    cfg["number_tag"] = SR.default_tag_name(doc, entries, unusable)

win = NumberWindow(walls, others_by_level, tag_names, cfg, label_block, unusable, note_params)
win.show_dialog()
if not win.result:
    script.exit()
soft, hard, cont, labels = win.result
plan = win.plan(soft, hard, cont)

# ------------------------------------------------------------------ confirm (nothing written before this)
written = [m for name, lv, marks, rng in plan for m in marks]
dups = sorted(set(m for m in written if m in other_marks or written.count(m) > 1), key=SD.natural_key)
lines = ["{} ({}): {} piles, {}, {}".format(name, lv, len(marks), SD.range_text(soft, rng[SR.SOFT]),
                                            SD.range_text(hard, rng[SR.HARD])) for name, lv, marks, rng in plan]
msg = "Write these pile numbers into Mark?\n\n" + "\n".join(lines)
if labels:
    msg += "\n\nLabels in view '{}': {} '{}', {} mm from the pile edge, {}; {}.".format(
        view.Name, "Generic Annotation" if labels["param"] else "tag", labels["tag"], SD.fmt_num(labels["offset"]),
        rotation_text(labels["rotation"]), ", ".join("{} {}".format(w["name"], labels["sides"][w["name"]]) for w in walls))
    if labels["param"]:
        msg += "\nThe number is copied into its parameter '{}'.".format(labels["param"])
else:
    msg += "\n\nLabels: none (only the marks)."
if dups:
    msg += ("\n\n{} of these marks are already used by other piles: {}{}.\n"
            "Revit will list them as duplicate Mark warnings.".format(
                len(dups), ", ".join(dups[:8]), " ..." if len(dups) > 8 else ""))
msg += "\n\nThe piles' current marks are replaced. The walls stay linked to their piles."
if not forms.alert(msg, title=TITLE, yes=True, no=True):
    script.exit()

# ------------------------------------------------------------------ write: marks, then labels
tg = TransactionGroup(doc, "Number SBP piles")
tg.Start()
t = Transaction(doc, "Number SBP piles - marks")
t.Start()
try:
    for w, (pname, plv, marks, rng) in zip(walls, plan):
        # piles made before 28 Sep keep their wall and order in the hidden data before the mark changes
        retag = any(SR.pile_tag(fi) is None for fi, k in w["piles"])
        for seq, ((fi, kind), mark) in enumerate(zip(w["piles"], marks)):
            if retag:
                SR.tag_pile(fi, w["name"], kind, seq)
            fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).Set(mark)
        if labels and w["ds"] is not None:
            data = dict(w["data"])
            data["label_side"] = labels["sides"][w["name"]]
            SR.save_wall(doc, data, w["ds"])
    t.Commit()
except Exception as ex:
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    tg.RollBack()
    forms.alert("Nothing was written:\n{}".format(ex), title=TITLE, exitscript=True)

placed, label_err = None, None
if labels:
    runs = []
    for w in walls:
        inside = G.inside_sign([SR.xy(fi) for fi, k in w["piles"]], w["closed"], (w["data"] or {}).get("side"))
        runs.append((w["piles"], w["closed"], inside if labels["sides"][w["name"]] == "inside" else -inside, w["name"]))
    t2 = Transaction(doc, "Number SBP piles - labels")
    t2.Start()
    try:
        if labels["param"]:
            placed = SR.place_pile_notes(doc, view, tag_types[labels["tag"]], labels["param"], runs,
                                         labels["offset"], labels["rotation"])
        else:
            placed = SR.place_pile_tags(doc, view, tag_types[labels["tag"]], runs, labels["offset"], labels["rotation"])
        t2.Commit()
    except Exception as ex:
        if t2.HasStarted() and not t2.HasEnded():
            t2.RollBack()
        label_err = str(ex)
    save_cfg({"number_tag": labels["tag"], CFG_OFFSET: labels["offset"], CFG_ROTATION: labels["rotation"]})
tg.Assimilate()

# ------------------------------------------------------------------ report
uidoc.Selection.SetElementIds(List[ElementId]([fi.Id for w in walls for fi, k in w["piles"]]))
output.print_md("## Number")
rows = []
for w, (name, lv, marks, rng) in zip(walls, plan):
    lab = labels["sides"][name] if (labels and placed) else "-"
    rows.append([SR.html(name), SR.html(lv), str(len(marks)), SR.html(SD.range_text(soft, rng[SR.SOFT])),
                 SR.html(SD.range_text(hard, rng[SR.HARD])), SR.html(lab)])
output.print_table(table_data=rows, columns=["Wall", "Level", "Piles", "SOFT", "HARD", "Labels"])
output.print_md("Mode: {}.".format("continued from the last number on the same level" if cont else "started new at 1"))
if dups:
    output.print_md("**Duplicate marks** (also on other piles): " + SR.html(", ".join(dups)))
if labels:
    if label_err:
        output.print_md("**Labels not placed** (the marks were written): " + SR.html(label_err))
    elif placed:
        output.print_md("Labels in view '{}': one per pile, {} new, {} moved{}; {} '{}', {} mm from the pile edge, {}.".format(
            SR.html(view.Name), placed["new"], placed["moved"],
            ", {} old label{} removed".format(placed["removed"], "" if placed["removed"] == 1 else "s") if placed["removed"] else "",
            "Generic Annotation" if labels["param"] else "tag", SR.html(labels["tag"]), SD.fmt_num(labels["offset"]),
            rotation_text(labels["rotation"])))
        if labels["param"]:
            output.print_md("The numbers are copied into the annotations' parameter '{}': they do not follow later Mark "
                            "changes, so run Number again after renumbering.".format(SR.html(labels["param"])))
        if placed["flipped"] or placed["nudged"] or placed["turned"]:
            output.print_md("To keep every label clear of the others: {} on the other side of the wall, {} nudged slightly{}."
                            .format(placed["flipped"], placed["nudged"],
                                    ", {} turned {}".format(placed["turned"], "across" if labels["rotation"] == "along" else "along")
                                    if placed["turned"] else ""))
        if placed["touching"]:
            output.print_md("**Labels still touching** (move them by hand): " + SR.html(", ".join(placed["touching"])))
        if placed["failed"]:
            output.print_md("**Not tagged:** " + SR.html(", ".join(placed["failed"])))

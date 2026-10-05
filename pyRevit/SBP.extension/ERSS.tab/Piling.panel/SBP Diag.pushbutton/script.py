# -*- coding: utf-8 -*-
"""SBP Diag: why does a NEW pile not show in the active view? Compares it with an OLD pile that shows.

Select a NEW pile and an OLD visible pile, then run. The new piles are still selected right after SBP Wall. With
nothing selected, the newest SBP pile is the NEW one, and you click an OLD pile. Reads only, changes nothing."""
__title__ = "SBP\nDiag"
__author__ = "Akash"

from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, Element, ElementId, FamilyInstance,
                               FilteredElementCollector, Level, ParameterFilterElement, PlanViewPlane,
                               PlanViewRange, SelectionFilterElement, ViewPlan)
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, script

import sbp_revit as SR

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView
output = script.get_output()
FOUND = ElementId(BuiltInCategory.OST_StructuralFoundation)
NONE = ElementId.InvalidElementId
TOL = SR.mm(1.0)


def is_found(e):
    return isinstance(e, FamilyInstance) and e.Category is not None and e.Category.Id == FOUND


class FoundFilter(ISelectionFilter):
    def AllowElement(self, e):
        return is_found(e)

    def AllowReference(self, r, p):
        return False


def safe_name(x):
    """Name of anything. In IronPython, x.Name fails on types (FamilySymbol / ElementType): AttributeError."""
    if x is None:
        return "-"
    try:
        n = Element.Name.GetValue(x)
        if n:
            return n
    except Exception:
        pass
    try:
        n = x.Name
        if n:
            return n
    except Exception:
        pass
    for bip in (BuiltInParameter.SYMBOL_NAME_PARAM, BuiltInParameter.ALL_MODEL_TYPE_NAME):
        try:
            p = x.get_Parameter(bip)
            if p is not None and p.AsString():
                return p.AsString()
        except Exception:
            pass
    return str(x)


def safe(fn):
    """fn() as text, or 'error: ...' so one bad property does not stop the report."""
    try:
        return fn()
    except Exception as ex:
        return "error: {} {}".format(type(ex).__name__, ex)


def name_of(eid):
    if eid is None or eid == NONE:
        return "(none)"
    el = doc.GetElement(eid)
    return safe_name(el) if el is not None else "(id {})".format(SR._idv(eid))


def pval(e, name, bip=None):
    p = e.get_Parameter(bip) if bip is not None else None
    if p is None:
        p = e.LookupParameter(name)
    if p is None:
        return "-"
    try:
        st = str(p.StorageType)
        if st == "String":
            return p.AsString() or ""
        if st == "ElementId":
            return name_of(p.AsElementId())
        return p.AsValueString() or ""
    except Exception as ex:
        return "? ({})".format(ex)


def yn(v):
    return "-" if v is None else ("YES" if v else "no")


if not isinstance(view, ViewPlan):
    forms.alert("Open the plan view where the piles do not show, then run SBP Diag.", exitscript=True)

# ------------------------------------------------------------------ the two piles
visible = set(SR._idv(i) for i in FilteredElementCollector(doc, view.Id).OfCategory(
    BuiltInCategory.OST_StructuralFoundation).WhereElementIsNotElementType().ToElementIds())
sel = [e for e in (doc.GetElement(i) for i in uidoc.Selection.GetElementIds()) if is_found(e)]
newest = lambda es: max(es, key=lambda e: SR._idv(e.Id))
new_c = [e for e in sel if SR._idv(e.Id) not in visible]
old_c = [e for e in sel if SR._idv(e.Id) in visible]
if new_c:
    new = newest(new_c)
elif len(old_c) >= 2:
    new = newest(old_c)                       # all selected piles show: the newest one is NEW
else:
    sbp = [fi for fi in SR.all_piles(doc) if SR.wall_of(fi)]
    if not sbp:
        forms.alert("No SBP piles in this model. Select the NEW pile and an OLD pile, then run again.",
                    exitscript=True)
    new = newest(sbp)
old_c = [e for e in old_c if e.Id != new.Id]
if old_c:
    old = newest(old_c)
else:
    try:
        ref = uidoc.Selection.PickObject(ObjectType.Element, FoundFilter(),
                                         "SBP Diag: click an OLD pile that shows in this view")
    except OperationCanceledException:
        script.exit()
    old = doc.GetElement(ref.ElementId)

# ------------------------------------------------------------------ the view
vlev = view.GenLevel
# displayed elevations (as Revit shows levels) = internal - shift
shift = vlev.ProjectElevation - vlev.get_Parameter(BuiltInParameter.LEVEL_ELEV).AsDouble() if vlev else 0.0
vr = view.GetViewRange()
planes = [("Top", PlanViewPlane.TopClipPlane), ("Cut plane", PlanViewPlane.CutPlane),
          ("Bottom", PlanViewPlane.BottomClipPlane), ("View depth", PlanViewPlane.ViewDepthPlane)]


def plane_z(plane):
    """(internal elevation or None, text) of a view range plane."""
    lid, off = vr.GetLevelId(plane), vr.GetOffset(plane)
    if lid == getattr(PlanViewRange, "Unlimited", None):
        return None, "Unlimited"
    lv = vlev if lid == getattr(PlanViewRange, "Current", None) else doc.GetElement(lid)
    if isinstance(lv, Level):
        z = lv.ProjectElevation + off
        return z, "{} {:+.0f} = {:.0f}".format(safe_name(lv), SR.to_mm(off), SR.to_mm(z - shift))
    if lid == getattr(PlanViewRange, "LevelAbove", None):
        return None, "Level above {:+.0f}".format(SR.to_mm(off))
    if lid == getattr(PlanViewRange, "LevelBelow", None):
        return None, "Level below {:+.0f}".format(SR.to_mm(off))
    return None, "? (level id {})".format(SR._idv(lid))


pz = dict((label, plane_z(p)) for label, p in planes)
ph_id = view.get_Parameter(BuiltInParameter.VIEW_PHASE).AsElementId()
pf_id = view.get_Parameter(BuiltInParameter.VIEW_PHASE_FILTER).AsElementId()
pf = doc.GetElement(pf_id)
filters = [doc.GetElement(i) for i in view.GetFilters()]
ws_table = doc.GetWorksetTable() if doc.IsWorkshared else None
n_regions = FilteredElementCollector(doc, view.Id).OfCategory(BuiltInCategory.OST_PlanRegion).GetElementCount()


def in_crop(e):
    if not view.CropBoxActive:
        return None
    cb, loc = view.CropBox, e.Location
    pt = getattr(loc, "Point", None)
    if pt is None:
        return None
    p = cb.Transform.Inverse.OfPoint(pt)
    return cb.Min.X - TOL <= p.X <= cb.Max.X + TOL and cb.Min.Y - TOL <= p.Y <= cb.Max.Y + TOL


def passes(f, e):
    try:
        if isinstance(f, SelectionFilterElement):
            return f.Contains(e.Id)
        if isinstance(f, ParameterFilterElement):
            if not any(c == e.Category.Id for c in f.GetCategories()):
                return False
            ef = f.GetElementFilter()
            return True if ef is None else ef.PassesFilter(e)
    except Exception:
        pass
    return None


def filter_hides(f):
    try:
        enabled = view.GetIsFilterEnabled(f.Id)
    except Exception:
        enabled = True
    return enabled and not view.GetFilterVisibility(f.Id)


def height(e):
    """'above' / 'below' / 'ok' against the cut plane and view depth, the pile's real Z range (internal)."""
    bb = e.get_BoundingBox(None)
    cut, depth = pz["Cut plane"][0], pz["View depth"][0]
    if bb is None or cut is None:
        return None, bb
    if bb.Min.Z > cut + TOL:
        return "above", bb
    if depth is not None and bb.Max.Z < depth - TOL:
        return "below", bb
    return "ok", bb


def overrides(e):
    o = view.GetElementOverrides(e.Id)
    bits = []
    if o.Halftone:
        bits.append("halftone")
    if o.Transparency:
        bits.append("transparency {}".format(o.Transparency))
    if o.ProjectionLinePatternId != NONE:
        bits.append("line pattern " + name_of(o.ProjectionLinePatternId))
    if o.ProjectionLineColor.IsValid:
        c = o.ProjectionLineColor
        bits.append("line colour {},{},{}".format(c.Red, c.Green, c.Blue))
    return ", ".join(bits) or "none"


class Rows(object):
    """Rows in the order they were added (an IronPython 2.7 dict has no order)."""
    def __init__(self):
        self.keys, self.vals = [], {}

    def __setitem__(self, k, v):
        if k not in self.vals:
            self.keys.append(k)
        self.vals[k] = v

    def __getitem__(self, k):
        return self.vals[k]

    def get(self, k, default=None):
        return self.vals.get(k, default)

    def add(self, k, fn):
        self[k] = safe(fn)


def facts(e):
    f = Rows()
    lv = doc.GetElement(e.LevelId)
    sym = e.Symbol
    try:
        h, bb = height(e)
    except Exception:
        h, bb = None, None
    f.add("Element id", lambda: str(SR._idv(e.Id)))
    f.add("Family : type", lambda: "{} : {}".format(safe_name(sym.Family), safe_name(sym)) if sym else "?")
    f.add("Size read by SBP Wall / Edit", lambda: "{:.0f} mm ({})".format(SR.to_mm(SR.size_of(e)[0]), SR.size_of(e)[1]))
    f.add("Type parameter 'Diameter'", lambda: pval(sym, "Diameter") if sym else "-")
    f.add("Radius (on the pile)", lambda: pval(e, "Radius"))
    f.add("Level", lambda: safe_name(lv) if isinstance(lv, Level)
          else pval(e, "Level", BuiltInParameter.FAMILY_LEVEL_PARAM))
    f.add("Level elevation", lambda: pval(lv, "Elevation", BuiltInParameter.LEVEL_ELEV)
          if isinstance(lv, Level) else "-")
    f.add("Height Offset From Level", lambda: pval(e, "Height Offset From Level"))
    f.add("Depth", lambda: pval(e, "Depth"))
    try:
        toe_p = (SR.pile_spec(e) or SR.HOUSE_SPEC)["length"]
    except Exception:
        toe_p = "Depth"
    if toe_p not in ("Depth", "Height Offset From Level"):
        f.add("{} (toe parameter)".format(toe_p), lambda: pval(e, toe_p))
    f.add("Elevation at Top", lambda: pval(e, "Elevation at Top", BuiltInParameter.STRUCTURAL_ELEVATION_AT_TOP))
    f.add("Elevation at Bottom",
          lambda: pval(e, "Elevation at Bottom", BuiltInParameter.STRUCTURAL_ELEVATION_AT_BOTTOM))
    f.add("Real top / bottom (view datum)", lambda: "{:.0f} / {:.0f}".format(
        SR.to_mm(bb.Max.Z - shift), SR.to_mm(bb.Min.Z - shift)) if bb else "-")
    f.add("Against the view range", lambda: {"above": "ABOVE the cut plane", "below": "BELOW the view depth",
                                             "ok": "inside"}.get(h, "-"))
    f.add("Phase Created", lambda: name_of(e.CreatedPhaseId))
    f.add("Phase Demolished", lambda: name_of(e.DemolishedPhaseId))
    f.add("Phase status in view (phase filter shows?)", lambda: "{} ({})".format(
        e.GetPhaseStatus(ph_id),
        pf.GetPhaseStatusPresentation(e.GetPhaseStatus(ph_id)) if pf is not None else None))
    if ws_table is not None:
        f.add("Workset", lambda: "{}{}".format(safe_name(ws_table.GetWorkset(e.WorksetId)),
                                               "" if ws_table.GetWorkset(e.WorksetId).IsOpen else " (CLOSED)"))
        f.add("Workset visible in this view", lambda: "{} ({})".format(
            yn(view.IsWorksetVisible(e.WorksetId)), view.GetWorksetVisibility(e.WorksetId)))
    else:
        f.add("Workset", lambda: "model not workshared")
    f.add("Design Option", lambda: safe_name(e.DesignOption) if e.DesignOption is not None else "Main Model")
    f.add("Comments", lambda: pval(e, "Comments", BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS))
    f.add("Mark", lambda: SR.mark_of(e))
    f.add("Hidden in view (IsHidden)", lambda: yn(e.IsHidden(view)))
    f.add("Category hidden in view", lambda: yn(view.GetCategoryHidden(e.Category.Id)))
    f.add("Inside the crop region", lambda: yn(in_crop(e)))
    f.add("Element graphic overrides", lambda: overrides(e))
    for flt in filters:
        f.add("Filter '{}' applies".format(safe_name(flt)), lambda flt=flt: yn(passes(flt, e)))
    f.add("Revit counts it visible in this view", lambda: yn(SR._idv(e.Id) in visible))
    return f


fn, fo = facts(new), facts(old)
keys = fn.keys + [k for k in fo.keys if k not in fn.vals]
rows = [[SR.html(k), SR.html(fn.get(k, "-")), SR.html(fo.get(k, "-")),
         "DIFF" if k != "Element id" and fn.get(k) != fo.get(k) else ""] for k in keys]

output.print_md("## SBP Diag: NEW pile vs OLD pile in view **{}**".format(SR.html(safe_name(view))))
output.print_table(table_data=rows, columns=["Item", "NEW pile", "OLD pile", ""])

tpl = doc.GetElement(view.ViewTemplateId) if view.ViewTemplateId != NONE else None
vrows = [["View level", safe(lambda: "{} = {}".format(safe_name(vlev), pval(vlev, "Elevation",
                                                                            BuiltInParameter.LEVEL_ELEV))
                                if vlev else "-")]]
vrows += [["View range: " + label, pz[label][1]] for label, _ in planes]
vrows += [["Plan regions in this view", str(n_regions)],
          ["Phase", safe(lambda: name_of(ph_id))], ["Phase filter", safe(lambda: name_of(pf_id))],
          ["View template", safe_name(tpl) if tpl else "(none)"],
          ["Crop region active", safe(lambda: yn(view.CropBoxActive))],
          ["Far clip", "not used in plan views (View depth instead)"]]
for flt in filters:
    try:
        en = view.GetIsFilterEnabled(flt.Id)
    except Exception:
        en = True
    vrows.append(["Filter '{}'".format(safe_name(flt)), safe(lambda flt=flt, en=en: "visible {}, enabled {}".format(
        yn(view.GetFilterVisibility(flt.Id)), yn(en)))])
output.print_md("### Active view")
output.print_table(table_data=[[SR.html(a), SR.html(b)] for a, b in vrows], columns=["Item", "Value"])

# ------------------------------------------------------------------ plain words
why = []


def check_hidden():
    if new.IsHidden(view):
        why.append("The NEW pile is hidden in this view (Hide in View). Fix: Reveal Hidden Elements, then Unhide.")
    if view.GetCategoryHidden(new.Category.Id):
        why.append("Structural Foundations are turned off in this view.")


def check_workset():
    if ws_table is None:
        return
    ws = ws_table.GetWorkset(new.WorksetId)
    if not ws.IsOpen:
        why.append("The NEW pile is on workset '{}', which is closed.".format(safe_name(ws)))
    elif not view.IsWorksetVisible(new.WorksetId):
        why.append("The NEW pile is on workset '{}', which is not visible in this view (the OLD pile is on '{}')."
                   .format(safe_name(ws), safe_name(ws_table.GetWorkset(old.WorksetId))))


def check_phase():
    if pf is not None and str(pf.GetPhaseStatusPresentation(new.GetPhaseStatus(ph_id))) == "DontShow":
        why.append("Phase: the NEW pile is created in '{}' and this view shows phase '{}' with filter '{}', which "
                   "does not show it (status: {}). The OLD pile is created in '{}'.".format(
                       name_of(new.CreatedPhaseId), name_of(ph_id), name_of(pf_id), new.GetPhaseStatus(ph_id),
                       name_of(old.CreatedPhaseId)))


def check_filters():
    for flt in filters:
        if filter_hides(flt) and passes(flt, new) and not passes(flt, old):
            why.append("View filter '{}' is set to invisible, and it catches the NEW pile.".format(safe_name(flt)))


def check_crop_option():
    if in_crop(new) is False:
        why.append("The NEW pile is outside the crop region of this view.")
    if new.DesignOption is not None and (old.DesignOption is None or old.DesignOption.Id != new.DesignOption.Id):
        why.append("The NEW pile is in design option '{}'; this view may not show that option.".format(
            safe_name(new.DesignOption)))


def check_height():
    h_new, bb_new = height(new)
    h_old, bb_old = height(old)
    if h_new not in ("above", "below"):
        return
    cut, depth = pz["Cut plane"], pz["View depth"]
    why.append("Height: the NEW pile runs from {:.0f} down to {:.0f}, which is {} (cut plane {}, view depth {}). "
               "The OLD pile runs from {:.0f} down to {:.0f}. Plan views do not draw foundations above the cut plane "
               "or below the view depth. (All in this view's level datum, as Revit shows level elevations.)".format(
                   SR.to_mm(bb_new.Max.Z - shift), SR.to_mm(bb_new.Min.Z - shift),
                   "ABOVE the cut plane" if h_new == "above" else "BELOW the view depth", cut[1], depth[1],
                   SR.to_mm(bb_old.Max.Z - shift) if bb_old else 0, SR.to_mm(bb_old.Min.Z - shift) if bb_old else 0))
    if n_regions:
        why.append("Note: this view has {} plan region(s), which can change the view range in their area."
                   .format(n_regions))


for chk in (check_hidden, check_workset, check_phase, check_filters, check_crop_option, check_height):
    try:
        chk()
    except Exception as ex:
        why.append("(The check '{}' could not run: {} {})".format(chk.__name__, type(ex).__name__, ex))

output.print_md("### Why the NEW pile does not show")
if why:
    for w in why:
        output.print_md("- " + SR.html(w))
elif SR._idv(new.Id) in visible:
    output.print_md("- Revit counts the NEW pile as visible in this view, and none of the checks found a reason. "
                    "Zoom in on it, or check Visibility/Graphics overrides. Send this report.")
else:
    output.print_md("- Revit says the NEW pile is not visible, but none of the checks above explains it. "
                    "Send this report.")

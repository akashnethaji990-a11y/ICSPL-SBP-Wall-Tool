# -*- coding: utf-8 -*-
"""Revit-side helpers shared by the SBP buttons (IronPython 2.7: no f-strings, use .format()).

Every function takes `doc` (or the elements) explicitly and shows no UI; questions to the
user are passed in as callbacks by the button scripts.
"""
import math
import clr

from System import Guid, String
from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilySymbol, FamilyInstance, Level, CurveElement, XYZ,
    UnitUtils, UnitTypeId, SpecTypeId, UnitFormatUtils, BuiltInParameter, BuiltInCategory,
    ElementId, StorageType, InternalDefinition, GraphicsStyleType, Material, Color, Category,
    JoinGeometryUtils, Line, Plane, SketchPlane,
    FillPattern, FillPatternElement, FillPatternTarget, FillPatternHostOrientation,
    OverrideGraphicSettings, ParameterFilterElement, ParameterFilterRuleFactory, ElementParameterFilter,
)
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.DB.ExtensibleStorage import Schema, SchemaBuilder, Entity, AccessLevel, DataStorage
from Autodesk.Revit.UI.Selection import ISelectionFilter

import sbp_geom as G
import sbp_data as SD

# ------------------------------------------------------------------ FAMILY / PROJECT SETTINGS
# Change these if your family, parameter, pattern or material names change.
FAMILY_NAME = "ICSPL_Pile"
P_OFFSET = "Height Offset From Level"   # cut-off is driven by this
P_DEPTH = "Depth"                       # toe is driven by this
P_RADIUS = "Radius"                     # read-only, gives the diameter
SAMPLE_MM = 100.0                       # curve sampling step (accuracy of curves)
HARD, SOFT = "HARD", "SOFT"
HATCH_NAME = "Diagonal up 1.5mm"        # SOFT piles in 2D (created if missing)
MATERIAL_NAME = "ICSPL_Pile"            # both pile types in 3D
FILTER_NAMES = {HARD: "SBP HARD PILE", SOFT: "SBP SOFT PILE"}
SBP_LINE_STYLE = "SBP Invisible"        # used (and hidden in the view) if Revit refuses <Invisible lines>
PLANE_REACH_MM = 5000.0                 # reference planes that stop this short of each other still meet
# Typed pile data that must NOT follow a pile to its new place after a rebuild.
DATA_SKIP = ("Depth", "X-Easting", "Y-Northing", "Mark", "Comments", P_OFFSET)
# Fixed id of the hidden "wall settings" data. Never change it, or saved walls are lost.
SCHEMA_GUID = Guid("5b3f7c2e-8d41-4a6f-9e2b-7c1a0d4e6f38")


# ------------------------------------------------------------------ report text
def html(text):
    """pyRevit's report reads <...> as HTML and hides it (e.g. '<Invisible lines>'): escape it."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------------ units
def mm(v):
    return UnitUtils.ConvertToInternalUnits(float(v), UnitTypeId.Millimeters)


def to_mm(v):
    return UnitUtils.ConvertFromInternalUnits(v, UnitTypeId.Millimeters)


# ------------------------------------------------------------------ lookups
def type_name(sym):
    p = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
    return p.AsString() if p else str(sym.Id)


def pile_types(doc):
    res = {}
    col = FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralFoundation)
    for s in col:
        if s.Family and s.Family.Name == FAMILY_NAME:
            res[type_name(s)] = s
    return res


def all_levels(doc):
    lv = sorted(FilteredElementCollector(doc).OfClass(Level), key=lambda l: l.Elevation)
    return dict((l.Name, l) for l in lv)


# ------------------------------------------------------------------ piles
def all_piles(doc):
    """Every ICSPL_Pile instance in the model (SBP or not)."""
    res = []
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance).OfCategory(BuiltInCategory.OST_StructuralFoundation):
        sym = fi.Symbol
        if sym is not None and sym.Family is not None and sym.Family.Name == FAMILY_NAME:
            res.append(fi)
    return res


def mark_of(fi):
    p = fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    return (p.AsString() or "") if p else ""


def wall_of(fi):
    """'SBP1-H014' -> 'SBP1'. None when the mark is not an SBP mark."""
    mark = mark_of(fi)
    if "-" not in mark:
        return None
    wall, tag = mark.rsplit("-", 1)
    return wall if (wall and tag[:1].upper() in ("H", "S")) else None


def kind_of(fi):
    """HARD / SOFT from Comments, else from the mark (H.../S...). None if unknown."""
    p = fi.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    c = ((p.AsString() or "") if p else "").strip().upper()
    if c.startswith(HARD):
        return HARD
    if c.startswith(SOFT):
        return SOFT
    if wall_of(fi):
        return {"H": HARD, "S": SOFT}.get(mark_of(fi).rsplit("-", 1)[1][:1].upper())
    return None


def is_sbp_pile(e):
    return (isinstance(e, FamilyInstance) and e.Symbol is not None and e.Symbol.Family is not None
            and e.Symbol.Family.Name == FAMILY_NAME and wall_of(e) is not None)


def wall_piles(doc, wall):
    """[(pile, kind)] of one wall (exact name match, so 'SBP1' never picks 'SBP1-A')."""
    return [(fi, kind_of(fi)) for fi in all_piles(doc) if wall_of(fi) == wall]


def wall_names(doc):
    """Every wall name already used in the model (pile marks + saved walls)."""
    names = set(n for n in (wall_of(fi) for fi in all_piles(doc)) if n)
    names.update(load_walls(doc).keys())
    return names


def xy(fi):
    p = fi.Location.Point
    return (p.X, p.Y)


class PileFilter(ISelectionFilter):
    def AllowElement(self, e):
        return is_sbp_pile(e)

    def AllowReference(self, r, p):
        return False


class CurveFilter(ISelectionFilter):
    def AllowElement(self, e):
        return isinstance(e, CurveElement)

    def AllowReference(self, r, p):
        return False


# ------------------------------------------------------------------ parameters
def set_param(el, name, value):
    p = el.LookupParameter(name)
    if p is None or p.IsReadOnly:
        raise Exception("Parameter '{}' is missing or read-only on {}.".format(name, FAMILY_NAME))
    p.Set(value)


def get_len(el, name):
    p = el.LookupParameter(name)
    if p is None:
        raise Exception("Parameter '{}' not found on {}.".format(name, FAMILY_NAME))
    return p.AsDouble()


def read_displayed_elev(doc, el, bip, fallback_name):
    """Read an elevation exactly as Revit displays it (respects Elevation Base), in internal units."""
    p = el.get_Parameter(bip) or el.LookupParameter(fallback_name)
    if p is None:
        raise Exception("'{}' not found on {}.".format(fallback_name, FAMILY_NAME))
    s = p.AsValueString()
    if s:
        ref = clr.Reference[float]()
        try:
            if UnitFormatUtils.TryParse(doc.GetUnits(), SpecTypeId.Length, s, ref):
                return ref.Value
        except Exception:
            pass
    return p.AsDouble()


def diameter_of(fi):
    return 2.0 * get_len(fi, P_RADIUS)


def probe_diameter(doc, symbol, level, pt):
    """Diameter of a pile type: place a probe pile, read Radius, delete it. Call inside a transaction."""
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
    probe = doc.Create.NewFamilyInstance(XYZ(pt[0], pt[1], level.ProjectElevation), symbol, level, StructuralType.Footing)
    doc.Regenerate()
    d = diameter_of(probe)
    doc.Delete(probe.Id)
    return d


# ------------------------------------------------------------------ the drawn line(s)
def _dxy(a, b):
    return math.hypot(a.X - b.X, a.Y - b.Y)


def build_chain(elements):
    """Order the lines end-to-end.

    Returns (items, closed): items = [(curve, element, reversed)] in chain order, where
    `reversed` says the curve runs against its line's own direction.
    Raises ValueError with a message for the user.
    """
    tol = mm(5)
    raw = [(e.GeometryCurve, e) for e in elements]
    if len(raw) == 1 and not raw[0][0].IsBound:          # full circle / ellipse
        c = raw[0][0].Clone()
        c.MakeBound(0.0, 2 * math.pi - 1e-7)
        return [(c, raw[0][1], False)], True
    if any(not c.IsBound for c, _ in raw):
        raise ValueError("A full circle must be selected on its own.")
    ordered = [(raw[0][0], raw[0][1], False)]
    rest = raw[1:]
    while rest:
        start = ordered[0][0].GetEndPoint(0)
        end = ordered[-1][0].GetEndPoint(1)
        found = False
        for i, (c, e) in enumerate(rest):
            a, b = c.GetEndPoint(0), c.GetEndPoint(1)
            if _dxy(a, end) < tol:
                ordered.append((c, e, False))
            elif _dxy(b, end) < tol:
                ordered.append((c.CreateReversed(), e, True))
            elif _dxy(b, start) < tol:
                ordered.insert(0, (c, e, False))
            elif _dxy(a, start) < tol:
                ordered.insert(0, (c.CreateReversed(), e, True))
            else:
                continue
            rest.pop(i)
            found = True
            break
        if not found:
            raise ValueError("The selected lines are not connected end-to-end.\nSelect one continuous chain per wall.")
    closed = len(ordered) > 1 and _dxy(ordered[0][0].GetEndPoint(0), ordered[-1][0].GetEndPoint(1)) < tol
    return ordered, closed


def reverse_chain(items):
    return [(c.CreateReversed(), e, not r) for c, e, r in reversed(items)]


def orient_chain(items, anchor_uid, anchor_reversed):
    """Turn the chain so the saved first line runs the same way as when the wall was made."""
    for c, e, r in items:
        if e.UniqueId == anchor_uid:
            return reverse_chain(items) if bool(r) != bool(anchor_reversed) else items
    return items


def view_z(view):
    """Height of the view's work plane (where new model lines go)."""
    sp = view.SketchPlane
    if sp is not None:
        return sp.GetPlane().Origin.Z
    lv = view.GenLevel
    return lv.ProjectElevation if lv is not None else 0.0


def plane_chain(planes, view):
    """Wall line from selected reference planes, trimmed where they cross (no model change yet).

    Returns (items, closed) like build_chain, but with element None: make_model_lines() creates
    the model lines when the wall is really made. Raises ValueError with a message for the user.
    """
    z = view_z(view)
    segs = [((rp.BubbleEnd.X, rp.BubbleEnd.Y), (rp.FreeEnd.X, rp.FreeEnd.Y)) for rp in planes]
    pts, closed = G.chain_from_lines(segs, mm(PLANE_REACH_MM))
    if closed:
        pts = pts + [pts[0]]
    items = []
    for a, b in zip(pts[:-1], pts[1:]):
        if math.hypot(b[0] - a[0], b[1] - a[1]) > mm(1):
            items.append((Line.CreateBound(XYZ(a[0], a[1], z), XYZ(b[0], b[1], z)), None, False))
    if not items:
        raise ValueError("The reference planes give no line to follow.")
    return items, closed


def make_model_lines(doc, items):
    """Create model lines for chain items that have none yet (from reference planes).
    Call inside a transaction. Returns the items with their new line elements."""
    if all(e is not None for c, e, r in items):
        return items
    z = items[0][0].GetEndPoint(0).Z
    sp = SketchPlane.Create(doc, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ(0, 0, z)))
    return [(c, e if e is not None else doc.Create.NewModelCurve(c, sp), r) for c, e, r in items]


def sample_curve(c, step):
    n = max(2, int(math.ceil(c.Length / step)) + 1)
    pts, tans = [], []
    for k in range(n):
        tr = c.ComputeDerivatives(float(k) / (n - 1), True)
        v = tr.BasisX
        L = math.hypot(v.X, v.Y) or 1.0
        pts.append((tr.Origin.X, tr.Origin.Y))
        tans.append((v.X / L, v.Y / L))
    return pts, tans


def chain_samples(items):
    return [sample_curve(c, mm(SAMPLE_MM)) for c, e, r in items]


def centre_path(items, closed, side, dist):
    """Centre line of the SBP wall: the drawn chain offset by `dist` to `side`."""
    step = mm(SAMPLE_MM)
    path = G.offset_path(chain_samples(items), closed, side, dist)
    window = int(math.ceil(4 * math.pi * dist / step)) + 20
    path = G.remove_loops(path, window)
    if closed:  # also clean the corner at the start/end seam
        h = len(path) // 2
        path = G.remove_loops(path[h:] + path[:h], window)
    return path


# line styles -----------------------------------------------------------------
def _is_invisible_cat(cat):
    if cat is None:
        return False
    if cat.Id == ElementId(BuiltInCategory.OST_InvisibleLines):
        return True
    return (cat.Name or "").strip("<> ").lower() in ("invisible lines", "invisible line")


def invisible_style(doc, curve_el=None):
    """The <Invisible lines> line style of this model, or None."""
    try:
        cat = Category.GetCategory(doc, BuiltInCategory.OST_InvisibleLines)
        gs = cat.GetGraphicsStyle(GraphicsStyleType.Projection) if cat is not None else None
        if gs is not None:
            return gs
    except Exception:
        pass
    for sub in doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines).SubCategories:
        if _is_invisible_cat(sub):
            return sub.GetGraphicsStyle(GraphicsStyleType.Projection)
    if curve_el is not None:
        for sid in curve_el.GetLineStyleIds():
            gs = doc.GetElement(sid)
            if gs is not None and _is_invisible_cat(gs.GraphicsStyleCategory):
                return gs
    return None


def is_invisible(curve_el):
    """True for <Invisible lines> and for our own hidden style 'SBP Invisible'."""
    gs = curve_el.LineStyle
    cat = gs.GraphicsStyleCategory if gs is not None else None
    return _is_invisible_cat(cat) or (cat is not None and cat.Name == SBP_LINE_STYLE)


def sbp_line_style(doc):
    """Line style 'SBP Invisible' (a Lines sub-category): use it if it is there, else add it.
    Call inside a transaction."""
    lines = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
    for sub in lines.SubCategories:
        if sub.Name == SBP_LINE_STYLE:
            return sub
    return doc.Settings.Categories.NewSubcategory(lines, SBP_LINE_STYLE)


def _hide_category(doc, view, cat_id, allow_template):
    """Turn a (sub-)category off in the view, or in its template when the template controls it."""
    target, where = view, "view '{}'".format(view.Name)
    if view.ViewTemplateId != ElementId.InvalidElementId:
        tpl = doc.GetElement(view.ViewTemplateId)
        free = [i for i in tpl.GetNonControlledTemplateParameterIds()]
        if not any(i == ElementId(BuiltInParameter.VIS_GRAPHICS_MODEL) for i in free):
            if allow_template is None or not allow_template(tpl.Name):
                return False, "view template '{}' controls the line visibility".format(tpl.Name)
            target, where = tpl, "view template '{}'".format(tpl.Name)
    if not target.CanCategoryBeHidden(cat_id):
        return False, "{} cannot hide that line style".format(where)
    target.SetCategoryHidden(cat_id, True)
    return True, where


def visible_styles(elements, keep=None):
    """{line UniqueId: style UniqueId} of the lines that are visible now (used to show them again later)."""
    res = dict(keep or {})
    for e in elements:
        if not is_invisible(e) and e.LineStyle is not None:
            res[e.UniqueId] = e.LineStyle.UniqueId
    return res


def hide_lines(doc, elements, view=None, allow_template=None):
    """Make the drawn lines invisible, in this order:
    1. line style <Invisible lines> (built into every Revit model);
    2. if Revit refuses it: our line style 'SBP Invisible' (added if missing, reused if there),
       turned off in `view` (or in its template, if allow_template(name) says yes);
    3. if that fails too: hide the lines in `view`.
    Returns notes for the report (empty = all set to <Invisible lines>).
    """
    errs, refused, gs = [], [], None
    for e in elements:
        if is_invisible(e):
            continue
        gs = gs or invisible_style(doc, e)
        try:
            if gs is None:
                raise Exception("this model has no <Invisible lines> style")
            e.LineStyle = gs
        except Exception as ex:
            refused.append((e, str(ex)))
    if not refused:
        return errs
    left = []
    try:
        sub = sbp_line_style(doc)
        own = sub.GetGraphicsStyle(GraphicsStyleType.Projection)
        for e, why in refused:
            try:
                e.LineStyle = own
            except Exception:
                left.append(e)
        done = len(refused) - len(left)
        if done:
            note = "Revit refused <Invisible lines> ({}), so {} line(s) use the line style '{}'".format(
                refused[0][1], done, SBP_LINE_STYLE)
            if view is not None:
                ok, where = _hide_category(doc, view, sub.Id, allow_template)
                note += ", turned off in {}".format(where) if ok else ", NOT turned off: {}".format(where)
            errs.append(note)
    except Exception as ex:
        left = [e for e, why in refused]
        errs.append("could not use the line style '{}': {}".format(SBP_LINE_STYLE, ex))
    if left and view is not None:
        try:
            view.HideElements(List[ElementId]([e.Id for e in left]))
            errs.append("so these lines were hidden in view '{}' instead".format(view.Name))
        except Exception as ex:
            errs.append("could not hide them in the view either: {}".format(ex))
    return errs


def is_hidden_in(view, elements):
    try:
        return any(e.IsHidden(view) for e in elements)
    except Exception:
        return False


def show_lines(doc, elements, saved_styles, view=None):
    """Give hidden lines their saved style back (fallback: the plain 'Lines' style)."""
    errs = []
    if view is not None and is_hidden_in(view, elements):
        try:
            view.UnhideElements(List[ElementId]([e.Id for e in elements]))
        except Exception as ex:
            errs.append("could not unhide the lines in this view: {}".format(ex))
    plain = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines).GetGraphicsStyle(GraphicsStyleType.Projection)
    for e in elements:
        gs = None
        uid = (saved_styles or {}).get(e.UniqueId)
        if uid:
            cand = doc.GetElement(uid)
            if cand is not None and any(cand.Id == sid for sid in e.GetLineStyleIds()):
                gs = cand
        try:
            e.LineStyle = gs or plain
        except Exception as ex:
            errs.append("Line {}: {}".format(e.Id, ex))
    return errs


# ------------------------------------------------------------------ joining other walls
def find_join(others, pt, diameter, spacing):
    """Nearest pile of another wall to a wall end (internal units).

    Returns dict(join='same'|'touch'|None, pile, kind, dist). kind is None when that pile's
    type cannot be read (the caller then asks the user).
    """
    best, bd = None, None
    for fi in others:
        x, y = xy(fi)
        d = math.hypot(x - pt[0], y - pt[1])
        if bd is None or d < bd:
            best, bd = fi, d
    join = SD.classify_join(bd, diameter, spacing) if best is not None else None
    return {"join": join, "pile": best, "dist": bd, "kind": kind_of(best) if (best is not None and join) else None}


def end_text(j, diameter):
    """One report line about a wall end."""
    if j is None:
        return "closed loop"
    if not j["join"]:
        if j["pile"] is not None and j["dist"] is not None and j["dist"] < 2 * diameter:
            return "free end: HARD (note: {} is {:.0f} mm away but does not overlap)".format(
                mark_of(j["pile"]) or "a pile", to_mm(j["dist"]))
        return "free end: HARD"
    m = mark_of(j["pile"]) or "an unmarked pile"
    if j["join"] == "same":
        return "continues from {} ({}), next pile {}".format(m, j["kind"], SD.other(j["kind"]))
    return "joins {} ({}), end pile {}".format(m, j["kind"], SD.other(j["kind"]))


def plan_wall(doc, items, closed, side, s, diameter, others, ask_kind):
    """Pile centres and types for a wall (no model change).

    s: settings in mm (spacing, gap, ...). others: piles of other walls (for joins).
    ask_kind(end, mark) -> 'HARD'|'SOFT'|None is called only when a join is found but
    the joined pile's type is unknown (None = treat the end as free).
    Returns (centres, kinds, info).
    """
    dist = mm(s["gap"]) + diameter / 2.0
    spacing = mm(s["spacing"])
    path = centre_path(items, closed, side, dist)
    ends = {"start": None, "end": None}
    st, et, ss, se = HARD, HARD, False, False
    if not closed:
        for key, pt in (("start", path[0]), ("end", path[-1])):
            j = find_join(others, pt, diameter, spacing)
            if j["join"] and j["kind"] is None:
                j["kind"] = ask_kind(key, mark_of(j["pile"]))
                if j["kind"] not in (HARD, SOFT):
                    j["join"], j["kind"] = None, None
            ends[key] = j
        st, ss = SD.end_setup(ends["start"]["join"], ends["start"]["kind"])
        et, se = SD.end_setup(ends["end"]["join"], ends["end"]["kind"])
    centres, kinds, step, total = G.layout_ends(path, closed, spacing, st, et, ss, se)
    info = {"step": step, "total": total, "dist": dist, "ends": ends,
            "chord": G.max_chord(centres, closed) if len(centres) > 1 else 0.0}
    return centres, kinds, info


# ------------------------------------------------------------------ placing and levels
def place_piles(doc, symbol, level, wall, centres, kinds):
    """Place piles with marks WALL-H001 / WALL-S001 and Comments HARD PILE / SOFT PILE."""
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
    placed = []
    nh = ns = 0
    for (x, y), kind in zip(centres, kinds):
        fi = doc.Create.NewFamilyInstance(XYZ(x, y, level.ProjectElevation), symbol, level, StructuralType.Footing)
        if kind == HARD:
            nh += 1
            mark = "{}-H{:03d}".format(wall, nh)
        else:
            ns += 1
            mark = "{}-S{:03d}".format(wall, ns)
        fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).Set(mark)
        fi.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).Set(kind + " PILE")
        placed.append((fi, kind))
    doc.Regenerate()
    return placed


def apply_levels(doc, piles, cutoff_mm, toe_h_mm, toe_s_mm):
    """Set Cut-off / Toe on piles [(pile, kind)] of one level, calibrated on what Revit displays.

    Family rule (seen in Revit): the displayed Top moves 1:1 with the offset and the displayed
    Bottom = offset - Depth (+ a constant). One reference pile gives both constants.
    Returns {kind: (top_mm, bottom_mm)} read back from the first pile of each type.
    """
    if not piles:
        return {}
    ref = piles[0][0]
    o0, d0 = get_len(ref, P_OFFSET), get_len(ref, P_DEPTH)
    t0 = read_displayed_elev(doc, ref, BuiltInParameter.STRUCTURAL_ELEVATION_AT_TOP, "Elevation at Top")
    b0 = read_displayed_elev(doc, ref, BuiltInParameter.STRUCTURAL_ELEVATION_AT_BOTTOM, "Elevation at Bottom")
    off = o0 + (mm(cutoff_mm) - t0)
    for fi, kind in piles:
        toe = mm(toe_h_mm if kind == HARD else toe_s_mm)
        dep = d0 + (b0 + (off - o0)) - toe
        if dep <= 0:
            raise Exception("Calculated pile depth is not positive. Check Cut-off / Toe values.")
        set_param(fi, P_OFFSET, off)
        set_param(fi, P_DEPTH, dep)
    doc.Regenerate()
    check = {}
    for fi, kind in piles:
        if kind not in check:
            check[kind] = (
                to_mm(read_displayed_elev(doc, fi, BuiltInParameter.STRUCTURAL_ELEVATION_AT_TOP, "Elevation at Top")),
                to_mm(read_displayed_elev(doc, fi, BuiltInParameter.STRUCTURAL_ELEVATION_AT_BOTTOM, "Elevation at Bottom")),
            )
    return check


# ------------------------------------------------------------------ SOFT piles cut by HARD piles
def hard_soft_pairs(placed, closed, ends=None):
    """(HARD, SOFT) pairs of piles that overlap: neighbours along the wall, plus the piles of
    other walls at a joined end. placed = [(pile, kind)] in wall order."""
    pairs = []
    n = len(placed)
    steps = list(range(n - 1)) + ([n - 1] if closed and n > 2 else [])
    for i in steps:
        (a, ka), (b, kb) = placed[i], placed[(i + 1) % n]
        if ka != kb:
            pairs.append((a, b) if ka == HARD else (b, a))
    for key, idx in (("start", 0), ("end", n - 1)):
        j = (ends or {}).get(key)
        if n and j and j.get("join") and j.get("pile") is not None and j.get("kind") in (HARD, SOFT):
            mine, kind = placed[idx]
            if kind != j["kind"]:
                pairs.append((mine, j["pile"]) if kind == HARD else (j["pile"], mine))
    return pairs


def cut_soft_by_hard(doc, pairs):
    """Join each (HARD, SOFT) pair so the HARD pile cuts the SOFT one: the HARD pile keeps its
    full round shape (it has reinforcement), the SOFT pile loses the overlap.
    Returns (joined, failed, first error). Call inside a transaction."""
    ok = bad = 0
    first = None
    for hard, soft in pairs:
        try:
            if not JoinGeometryUtils.AreElementsJoined(doc, hard, soft):
                JoinGeometryUtils.JoinGeometry(doc, hard, soft)
            if not JoinGeometryUtils.IsCuttingElementInJoin(doc, hard, soft):
                JoinGeometryUtils.SwitchJoinOrder(doc, hard, soft)
            ok += 1
        except Exception as ex:
            bad += 1
            first = first or str(ex)
    return ok, bad, first


# ------------------------------------------------------------------ typed pile data
def _copyable(p):
    if p.IsReadOnly or not p.HasValue:
        return False
    d = p.Definition
    if d is None or d.Name in DATA_SKIP:
        return False
    if isinstance(d, InternalDefinition) and d.BuiltInParameter != BuiltInParameter.INVALID:
        return False        # built-in (Mark, Level, Phase ...): the tool sets these
    return p.StorageType in (StorageType.String, StorageType.Double, StorageType.Integer)


def snapshot_data(piles):
    """Typed data of piles [(pile, kind)] before they are deleted: [(x, y, kind, mark, {name: value})].

    Only family/shared parameters with a value (text not empty, number not 0) are kept.
    """
    res = []
    for fi, kind in piles:
        vals = {}
        for p in fi.Parameters:
            if not _copyable(p):
                continue
            st = p.StorageType
            if st == StorageType.String:
                v = p.AsString()
            elif st == StorageType.Double:
                v = p.AsDouble()
            else:
                v = p.AsInteger()
            if v:
                vals[p.Definition.Name] = v
        x, y = xy(fi)
        res.append((x, y, kind, mark_of(fi), vals))
    return res


def restore_data(snap, placed, max_dist=None):
    """Copy typed data to the nearest new pile of the same type (never further than max_dist).

    Returns (copied, lost): copied = [(old mark, new mark, distance mm)], lost = [old mark].
    """
    olds = [s for s in snap if s[4]]
    if not olds or not placed:
        return [], [s[3] for s in olds]
    new = [xy(fi) + (kind,) for fi, kind in placed]
    matches, lost = SD.match_nearest([(s[0], s[1], s[2]) for s in olds], new, max_dist)
    copied = []
    for i, (j, d) in matches.items():
        fi = placed[j][0]
        for name, v in olds[i][4].items():
            p = fi.LookupParameter(name)
            if p is None or p.IsReadOnly:
                continue
            try:
                p.Set(v)
            except Exception:
                pass
        copied.append((olds[i][3], mark_of(fi), to_mm(d)))
    return sorted(copied), [olds[i][3] for i in lost]


# ------------------------------------------------------------------ wall settings saved in the model
def _schema():
    s = Schema.Lookup(SCHEMA_GUID)
    if s is not None:
        return s
    b = SchemaBuilder(SCHEMA_GUID)
    b.SetSchemaName("SBPWallData")
    b.SetReadAccessLevel(AccessLevel.Public)
    b.SetWriteAccessLevel(AccessLevel.Public)
    b.AddSimpleField("Json", clr.GetClrType(String))
    return b.Finish()


def load_walls(doc):
    """{wall name: (DataStorage element, settings dict)} for every wall saved in this model."""
    s = _schema()
    res = {}
    for ds in FilteredElementCollector(doc).OfClass(DataStorage):
        ent = ds.GetEntity(s)
        if ent is None or not ent.IsValid():
            continue
        try:
            d = SD.decode(ent.Get[String]("Json"))
        except Exception:
            continue
        if d.get("wall"):
            res[d["wall"]] = (ds, d)
    return res


def save_wall(doc, data, ds=None):
    """Create or update the wall's hidden settings element. Call inside a transaction."""
    s = _schema()
    if ds is None or not ds.IsValidObject:
        ds = DataStorage.Create(doc)
    ent = Entity(s)
    ent.Set[String]("Json", SD.encode(data))
    ds.SetEntity(ent)
    return ds


def wall_data(wall, symbol, level, s, items, closed, side, styles):
    """Everything a wall needs to be rebuilt later (lengths in mm)."""
    first = items[0]
    return {
        "wall": wall, "type_uid": symbol.UniqueId, "type_name": type_name(symbol),
        "level_uid": level.UniqueId, "level_name": level.Name,
        "spacing": s["spacing"], "gap": s["gap"], "cutoff": s["cutoff"],
        "toe_hard": s["toe_hard"], "toe_soft": s["toe_soft"], "invisible": bool(s["invisible"]),
        "lines": [e.UniqueId for c, e, r in items], "line_styles": styles,
        "side": side, "anchor_uid": first[1].UniqueId, "anchor_reversed": bool(first[2]),
        "closed": bool(closed),
    }


# ------------------------------------------------------------------ HARD / SOFT look
def _solid_fill_id(doc):
    for fpe in FilteredElementCollector(doc).OfClass(FillPatternElement):
        if fpe.GetFillPattern().IsSolidFill:
            return fpe.Id
    return None


def _hatch_id(doc):
    """Drafting pattern 'Diagonal up 1.5mm' (created as 45 deg lines, 1.5 mm apart, if missing)."""
    want = HATCH_NAME.replace(" ", "").lower()
    for fpe in FilteredElementCollector(doc).OfClass(FillPatternElement):
        fp = fpe.GetFillPattern()
        if fp.Target == FillPatternTarget.Drafting and fpe.Name.replace(" ", "").lower() == want:
            return fpe.Id
    fp = FillPattern(HATCH_NAME, FillPatternTarget.Drafting, FillPatternHostOrientation.ToView,
                     math.radians(45.0), mm(1.5))
    return FillPatternElement.Create(doc, fp).Id


def _filter(doc, kind):
    name = FILTER_NAMES[kind]
    for f in FilteredElementCollector(doc).OfClass(ParameterFilterElement):
        if f.Name == name:
            return f
    cats = List[ElementId]([ElementId(BuiltInCategory.OST_StructuralFoundation)])
    pid = ElementId(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    try:
        rule = ParameterFilterRuleFactory.CreateEqualsRule(pid, kind + " PILE")
    except Exception:
        rule = ParameterFilterRuleFactory.CreateEqualsRule(pid, kind + " PILE", True)
    return ParameterFilterElement.Create(doc, name, cats, ElementParameterFilter(rule))


def _overrides(pattern_id):
    o = OverrideGraphicSettings()
    black = Color(0, 0, 0)
    o.SetSurfaceForegroundPatternId(pattern_id)
    o.SetSurfaceForegroundPatternColor(black)
    o.SetSurfaceForegroundPatternVisible(True)
    o.SetCutForegroundPatternId(pattern_id)
    o.SetCutForegroundPatternColor(black)
    o.SetCutForegroundPatternVisible(True)
    return o


def apply_view_filters(doc, view, allow_template):
    """Show HARD piles solid and SOFT piles hatched in `view` (two view filters by Comments).

    allow_template(template name) -> bool is asked when the view's template controls filters.
    Returns a note for the report. Call inside a transaction.
    """
    target, where = view, "view '{}'".format(view.Name)
    if view.ViewTemplateId != ElementId.InvalidElementId:
        tpl = doc.GetElement(view.ViewTemplateId)
        free = [i for i in tpl.GetNonControlledTemplateParameterIds()]
        if not any(i == ElementId(BuiltInParameter.VIS_GRAPHICS_FILTERS) for i in free):
            if not allow_template(tpl.Name):
                return "not added: view template '{}' controls filters".format(tpl.Name)
            target, where = tpl, "view template '{}'".format(tpl.Name)
    if not target.AreGraphicsOverridesAllowed():
        return "not added: this view does not allow graphic overrides"
    patterns = {HARD: _solid_fill_id(doc), SOFT: _hatch_id(doc)}
    for kind in (HARD, SOFT):
        f = _filter(doc, kind)
        if not target.IsFilterApplied(f.Id):
            target.AddFilter(f.Id)
        if patterns[kind] is not None:
            target.SetFilterOverrides(f.Id, _overrides(patterns[kind]))
        target.SetFilterVisibility(f.Id, True)
    return "HARD solid, SOFT '{}' in {}".format(HATCH_NAME, where)


def set_material(doc, fis):
    """Structural Material = ICSPL_Pile on the piles. Returns a note for the report."""
    mat = None
    for m in FilteredElementCollector(doc).OfClass(Material):
        if m.Name.strip().lower() == MATERIAL_NAME.lower():
            mat = m
            break
    if mat is None:
        return "not set: material '{}' is not in this project".format(MATERIAL_NAME)
    done = skipped = 0
    for fi in fis:
        p = fi.get_Parameter(BuiltInParameter.STRUCTURAL_MATERIAL_PARAM) or fi.LookupParameter("Structural Material")
        if p is None or p.IsReadOnly:
            skipped += 1
            continue
        if p.AsElementId() != mat.Id:
            p.Set(mat.Id)
        done += 1
    if not done:
        return "not set: 'Structural Material' is not an editable instance parameter"
    return "{} on {} piles".format(MATERIAL_NAME, done) + (" ({} skipped)".format(skipped) if skipped else "")

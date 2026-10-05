# -*- coding: utf-8 -*-
"""Revit-side helpers shared by the SBP buttons (IronPython 2.7: no f-strings, use .format()).

Every function takes `doc` (or the elements) explicitly and shows no UI; questions to the
user are passed in as callbacks by the button scripts.
"""
import math
import clr

from System import Guid, String, Int32
from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilySymbol, FamilyInstance, Level, CurveElement, XYZ,
    UnitUtils, UnitTypeId, SpecTypeId, UnitFormatUtils, BuiltInParameter, BuiltInCategory,
    ElementId, StorageType, InternalDefinition, GraphicsStyleType, Material, Color, Category,
    JoinGeometryUtils, Line, Plane, SketchPlane, IndependentTag, TagOrientation, Reference, Transaction,
    ElementTransformUtils,
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
# The house pile family: its types show by their own name. Any other Structural Foundation family works too:
# its diameter / length / cut-off parameters are recognised by name (sbp_data.detect_pile_params), or the drafter
# picks them once and the set-up is saved in the model (ensure_pile_spec; redo: Shift+Click on SBP Wall).
FAMILY_NAME = "ICSPL_Pile"
P_OFFSET = "Height Offset From Level"   # cut-off is driven by this (ICSPL_Pile)
P_DEPTH = "Depth"                       # toe is driven by this (ICSPL_Pile)
P_RADIUS = "Radius"                     # read-only, gives the diameter (ICSPL_Pile)
HOUSE_SPEC = {"diameter": P_RADIUS, "factor": 2, "length": P_DEPTH, "offset": P_OFFSET}
PILE_SPECS_KEY = "pile_families"        # saved pile family set-ups (in the wall-settings storage)
# When the nominated diameter parameter is found but its value is 0, these are tried in order.
# factor 1 = the parameter IS the diameter; factor 2 = it is the radius.
_SIZE_FALLBACKS = [
    ("Diameter", 1), ("Pile Diameter", 1), ("diameter", 1), ("D", 1),
    ("Width",    1), ("Pile Width",    1), ("width",    1),
    ("Breadth",  1), ("breadth",       1), ("b",        1),
    ("Radius",   2), ("radius",        2), ("r",        2),
]
LEVEL_CHECK_MM = 2.0                    # Top / Bottom read back must be this close to the asked cut-off / toe
SAMPLE_MM = 100.0                       # curve sampling step (accuracy of curves)
HARD, SOFT = "HARD", "SOFT"
HATCH_NAME = "Diagonal up 1.5mm"        # SOFT piles in 2D (created if missing)
FILL_RGB = {HARD: (201, 201, 201), SOFT: (0, 0, 0)}   # 2D fill colour: HARD light grey (Akash), SOFT hatch black
MATERIAL_NAME = "ICSPL_Pile"            # both pile types in 3D
FILTER_NAMES = {HARD: "SBP HARD PILE", SOFT: "SBP SOFT PILE"}
SBP_LINE_STYLE = "SBP Invisible"        # used (and hidden in the view) if Revit refuses <Invisible lines>
PLANE_REACH_MM = 5000.0                 # reference planes that stop this short of each other still meet
# Pile labels (Number button): tags of category Structural Foundation Tags that show the Mark.
LABEL_GAP_MM = 100.0                    # clear space between two labels, and between a label and a pile
TAG_ANGLE_SIGN = 1.0                    # Revit turns tags counter-clockwise; use -1.0 if labels turn the wrong way
# Typed pile data that must NOT follow a pile to its new place after a rebuild.
DATA_SKIP = ("Depth", "X-Easting", "Y-Northing", "Mark", "Comments", P_OFFSET)
# Fixed id of the hidden "wall settings" data. Never change it, or saved walls are lost.
SCHEMA_GUID = Guid("5b3f7c2e-8d41-4a6f-9e2b-7c1a0d4e6f38")
# Fixed id of the hidden data on each pile (wall, HARD/SOFT, place along the wall). Never change it.
# Mark is free for layout numbers (SP1, HP1 ...) because the wall is known from this data.
PILE_SCHEMA_GUID = Guid("66fb6159-0697-4757-947e-bc71f93daaae")
# Fixed id of the hidden mark on the tags the Number button places (one Number label per pile). Never change it.
LABEL_SCHEMA_GUID = Guid("8f251ee8-64c4-423d-ba51-a7cd2c6754a0")
# Fixed id of the hidden data on the Generic Annotations Number places (pile, turn). Never change it.
NOTE_SCHEMA_GUID = Guid("54ef95e8-ab50-443c-bcea-1cd21ff25f2f")


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


def type_label(sym):
    """How a pile type shows in the lists: its own name for the house family, 'Type (Family)' for others."""
    fam = sym.Family.Name if sym.Family is not None else "?"
    return type_name(sym) if fam == FAMILY_NAME else "{} ({})".format(type_name(sym), fam)


def _fam_name(el):
    sym = getattr(el, "Symbol", None)
    fam = sym.Family if sym is not None else getattr(el, "Family", None)
    return fam.Name if fam is not None else "?"


def _foundation_symbols(doc):
    """{family UniqueId: [FamilySymbol]} of every Structural Foundation family in the model."""
    res = {}
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralFoundation):
        if s.Family is not None:
            res.setdefault(s.Family.UniqueId, []).append(s)
    return res


def all_foundation_types(doc):
    """{shown name: FamilySymbol} of every Structural Foundation type (for the pile family set-up)."""
    return dict((type_label(s), s) for syms in _foundation_symbols(doc).values() for s in syms)


# pile family set-ups: {'diameter': parameter, 'factor': 1 (diameter) or 2 (radius), 'length': parameter (moves the
# toe), 'offset': parameter (moves the cut-off)}
_SPECS = {}                              # (document, family UniqueId) -> set-up, while a button runs
_DIAM_ERRS = {}                          # type label -> str, why a diameter could not be read (reset each run)
_DIAM_SRC = {}                           # type label -> where its size was read, for the form (reset each run)
SIZE_PARAM = "Diameter"                  # the TYPE parameter read first for the pile size (Akash, 6 Oct)
SIZE_RANGE_MM = (50.0, 5000.0)           # a size outside this is a wrong parameter, not a pile


def _doc_key(doc):
    return doc.PathName or doc.Title


def clear_pile_specs():
    """Forget the cached set-ups and size notes (SBP Wall keeps its Python engine between runs). Sizes themselves
    are never cached: they are read fresh every time."""
    _SPECS.clear()
    _DIAM_ERRS.clear()
    _DIAM_SRC.clear()


def _param_info(el, where):
    res = []
    for p in el.Parameters:
        d = p.Definition
        if d is None or p.StorageType != StorageType.Double:
            continue
        try:
            is_len = d.GetDataType() == SpecTypeId.Length
        except Exception:
            is_len = False
        res.append((d.Name, is_len, p.IsReadOnly, p.AsDouble(), where))
    return res


def _pile_params(fi):
    """(name, is_length, read_only, value, 'instance'/'type') of a pile's number parameters."""
    return _param_info(fi, "instance") + (_param_info(fi.Symbol, "type") if fi.Symbol is not None else [])


def _saved_specs(doc):
    """(DataStorage or None, {family UniqueId: set-up}) of the pile family set-ups saved in the model."""
    sc = _schema()
    for ds in FilteredElementCollector(doc).OfClass(DataStorage):
        ent = ds.GetEntity(sc)
        if ent is None or not ent.IsValid():
            continue
        try:
            d = SD.decode(ent.Get[String]("Json"))
        except Exception:
            continue
        if PILE_SPECS_KEY in d:
            return ds, d[PILE_SPECS_KEY]
    return None, {}


def pile_spec(fi):
    """How this pile's family gives its diameter, length and cut-off: the set-up saved in the model, else the
    parameters recognised by name (the house family has its own). None when the family is not a known pile."""
    sym = fi.Symbol
    fam = sym.Family if sym is not None else None
    if fam is None:
        return None
    key = (_doc_key(fi.Document), fam.UniqueId)
    if key not in _SPECS:
        spec = _saved_specs(fi.Document)[1].get(fam.UniqueId)
        if spec is None:
            spec = SD.pile_spec_from(SD.detect_pile_params(_pile_params(fi)))
        if spec is None and fam.Name == FAMILY_NAME:
            spec = dict(HOUSE_SPEC)
        if spec is None:
            return None
        _SPECS[key] = spec
    return _SPECS[key]


def _probe_params(doc, symbols, level):
    """{family UniqueId: parameters} read from one probe pile per type, in a transaction that is rolled back
    (no change to the model). Types that cannot be placed on a level are left out. Call outside a transaction."""
    res = {}
    t = Transaction(doc, "SBP - read pile families")
    t.Start()
    try:
        for sym in symbols:
            try:
                if not sym.IsActive:
                    sym.Activate()
                    doc.Regenerate()
                probe = doc.Create.NewFamilyInstance(XYZ(0, 0, level.ProjectElevation), sym, level, StructuralType.Footing)
                doc.Regenerate()
                res[sym.Family.UniqueId] = _pile_params(probe)
            except Exception:
                pass
    finally:
        t.RollBack()
    return res


def pile_types(doc):
    """{shown name: FamilySymbol} of the pile types SBP Wall / SBP Edit offer: the house family, families set up in
    the model or recognised as piles, and families with 'pile' in their name (their parameters are asked once
    when chosen: ensure_pile_spec). Families without placed piles are read from a rolled-back probe, so call
    this outside a transaction."""
    by_fam = _foundation_symbols(doc)
    saved = _saved_specs(doc)[1]
    placed = {}
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance).OfCategory(BuiltInCategory.OST_StructuralFoundation):
        fam = fi.Symbol.Family if fi.Symbol is not None else None
        if fam is not None and fam.UniqueId not in placed:
            placed[fam.UniqueId] = fi
    unknown = [u for u, syms in by_fam.items()
               if u not in saved and u not in placed and syms[0].Family.Name != FAMILY_NAME]
    levels = sorted(FilteredElementCollector(doc).OfClass(Level), key=lambda l: l.Elevation)
    probed = _probe_params(doc, [by_fam[u][0] for u in unknown], levels[0]) if unknown and levels else {}
    res = {}
    for u, syms in by_fam.items():
        fam = syms[0].Family
        ok = u in saved or fam.Name == FAMILY_NAME
        if not ok:
            params = _pile_params(placed[u]) if u in placed else probed.get(u)
            if params is None:
                continue
            found = SD.detect_pile_params(params)
            spec = SD.pile_spec_from(found)
            if spec is not None:
                _SPECS[(_doc_key(doc), u)] = spec
            ok = spec is not None or SD.looks_like_pile(fam.Name, found)
        if ok:
            for sym in syms:
                res[type_label(sym)] = sym
    return res


def _ask_spec(fam_name, params, found, ask):
    """Ask the drafter for the roles not recognised (all of them when found is empty). None = cancelled."""
    res = {}
    if "diameter" in found:
        res["diameter"], res["factor"] = found["diameter"]
    else:
        opts = {}
        for name, is_len, ro, val, where in params:
            if is_len and val > 0:
                for factor, word in ((1, "diameter"), (2, "radius")):
                    opts["{} = {:.0f} mm  (it is the {})".format(name, to_mm(val), word)] = (name, factor)
        if not opts:
            raise Exception("Family '{}' has no length parameter that could give the pile size.".format(fam_name))
        pick = ask("Pile family '{}': which parameter gives the pile size?".format(fam_name), sorted(opts))
        if not pick:
            return None
        res["diameter"], res["factor"] = opts[pick]
    free = [(n, v) for n, is_len, ro, v, where in params if is_len and not ro and where == "instance"]
    for role, what in (("offset", "sets the height above the level (moves the cut-off)"),
                       ("length", "sets the pile length (moves the toe)")):
        if role in found:
            res[role] = found[role]
            continue
        opts = dict(("{} = {:.0f} mm".format(n, to_mm(v)), n) for n, v in free if n != res.get("offset"))
        if not opts:
            raise Exception("Family '{}' has no editable length parameter that {}.".format(fam_name, what))
        pick = ask("Pile family '{}': which parameter {}?".format(fam_name, what), sorted(opts))
        if not pick:
            return None
        res[role] = opts[pick]
    return res


def ensure_pile_spec(doc, symbol, level, ask, force=False):
    """The set-up of this pile type's family. If its parameters are not recognised (or force=True: set it up
    again), the drafter is asked with ask(question, options) -> option or None, and the answer is saved in the
    model, so every drafter gets it. Returns the set-up, or None when cancelled. Call outside a transaction."""
    fam = symbol.Family
    key = (_doc_key(doc), fam.UniqueId)
    ds, saved = _saved_specs(doc)
    if not force:
        if key in _SPECS:
            return _SPECS[key]
        if fam.UniqueId in saved:
            _SPECS[key] = saved[fam.UniqueId]
            return _SPECS[key]
    params = _probe_params(doc, [symbol], level).get(fam.UniqueId)
    if params is None:
        raise Exception("A pile of family '{}' cannot be placed on level '{}'.".format(fam.Name, level.Name))
    found = {} if force else SD.detect_pile_params(params)
    spec = None if force else SD.pile_spec_from(found)
    if spec is None and not force and fam.Name == FAMILY_NAME:
        spec = dict(HOUSE_SPEC)
    if spec is None:
        spec = _ask_spec(fam.Name, params, found, ask)
        if spec is None:
            return None
        t = Transaction(doc, "SBP - pile family set-up: " + fam.Name)
        t.Start()
        try:
            saved = dict(saved)
            saved[fam.UniqueId] = dict(spec, family=fam.Name)
            save_wall(doc, {PILE_SPECS_KEY: saved}, ds)
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise
    _SPECS[key] = spec
    return spec


def all_levels(doc):
    lv = sorted(FilteredElementCollector(doc).OfClass(Level), key=lambda l: l.Elevation)
    return dict((l.Name, l) for l in lv)


# ------------------------------------------------------------------ piles
def all_piles(doc):
    """Every pile in the model (SBP or not): Structural Foundation instances of a pile family (the house family,
    a family set up in the model or recognised as a pile), and any pile that belongs to an SBP wall."""
    res, ok = [], {}
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance).OfCategory(BuiltInCategory.OST_StructuralFoundation):
        sym = fi.Symbol
        fam = sym.Family if sym is not None else None
        if fam is None:
            continue
        if fam.UniqueId not in ok:
            ok[fam.UniqueId] = pile_spec(fi) is not None
        if ok[fam.UniqueId] or pile_tag(fi) is not None:
            res.append(fi)
    return res


def mark_of(fi):
    p = fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    return (p.AsString() or "") if p else ""


def _pile_schema(create=False):
    s = Schema.Lookup(PILE_SCHEMA_GUID)
    if s is not None or not create:
        return s
    b = SchemaBuilder(PILE_SCHEMA_GUID)
    b.SetSchemaName("SBPPileData")
    b.SetReadAccessLevel(AccessLevel.Public)
    b.SetWriteAccessLevel(AccessLevel.Public)
    b.AddSimpleField("Wall", clr.GetClrType(String))
    b.AddSimpleField("Kind", clr.GetClrType(String))
    b.AddSimpleField("Seq", clr.GetClrType(Int32))
    return b.Finish()


def pile_tag(fi):
    """The pile's hidden data: {'wall', 'kind', 'seq'} (seq = place along the wall from its start
    end, 0 = first), or None for piles made before 28 Sep and non-SBP piles."""
    s = _pile_schema()
    if s is None:
        return None
    ent = fi.GetEntity(s)
    if ent is None or not ent.IsValid():
        return None
    return {"wall": ent.Get[String]("Wall"), "kind": ent.Get[String]("Kind"), "seq": ent.Get[Int32]("Seq")}


def tag_pile(fi, wall, kind, seq):
    """Write the pile's hidden data. Call inside a transaction."""
    ent = Entity(_pile_schema(True))
    ent.Set[String]("Wall", wall)
    ent.Set[String]("Kind", kind)
    ent.Set[Int32]("Seq", seq)
    fi.SetEntity(ent)


def wall_of(fi):
    """The pile's wall ('SBP1') from its hidden data, else from an old mark ('SBP1-H014' -> 'SBP1').
    None for piles that are not in an SBP wall."""
    t = pile_tag(fi)
    if t and t["wall"]:
        return t["wall"]
    mark = mark_of(fi)
    if "-" not in mark:
        return None
    wall, tag = mark.rsplit("-", 1)
    return wall if (wall and tag[:1].upper() in ("H", "S")) else None


def kind_of(fi):
    """HARD / SOFT from the hidden data, else Comments, else the old mark (H.../S...). None if unknown."""
    t = pile_tag(fi)
    if t and t["kind"] in (HARD, SOFT):
        return t["kind"]
    p = fi.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    c = ((p.AsString() or "") if p else "").strip().upper()
    if c.startswith(HARD):
        return HARD
    if c.startswith(SOFT):
        return SOFT
    mark = mark_of(fi)
    if "-" in mark and wall_of(fi):
        return {"H": HARD, "S": SOFT}.get(mark.rsplit("-", 1)[1][:1].upper())
    return None


def is_sbp_pile(e):
    """A pile of an SBP wall (any pile family). Old marks like SBP1-H001 count only on the house family."""
    if not isinstance(e, FamilyInstance) or e.Category is None:
        return False
    if e.Category.Id != ElementId(BuiltInCategory.OST_StructuralFoundation):
        return False
    if pile_tag(e) is not None:
        return True
    return _fam_name(e) == FAMILY_NAME and wall_of(e) is not None


def wall_piles(doc, wall):
    """[(pile, kind)] of one wall (exact name match, so 'SBP1' never picks 'SBP1-A')."""
    return [(fi, kind_of(fi)) for fi in all_piles(doc) if wall_of(fi) == wall]


def wall_in_order(piles):
    """piles [(pile, kind)] of one wall in draw order (from the start end of the wall), or None when
    the order cannot be known (old piles whose marks were changed)."""
    tags = [pile_tag(fi) for fi, k in piles]
    if piles and all(t is not None for t in tags):
        order = sorted(range(len(piles)), key=lambda i: tags[i]["seq"])
    else:
        items = []
        for i, (fi, k) in enumerate(piles):
            parts = SD.default_mark_parts(mark_of(fi))
            x, y = xy(fi)
            items.append((i, k, parts[2] if parts else None, x, y))
        order = SD.legacy_order(items)
        if order is None:
            return None
    return [piles[i] for i in order]


def level_name(doc, fi):
    lv = doc.GetElement(fi.LevelId) if fi.LevelId != ElementId.InvalidElementId else None
    return lv.Name if lv is not None else "(no level)"


def wall_names(doc):
    """Every wall name already used in the model (piles + saved walls)."""
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
def _param(el, name):
    """The parameter called `name`, preferring a writable one: a pile can carry two of the same name (Revit's own
    read-only foundation 'Length' and the family's 'Length'), and LookupParameter returns either."""
    ps = list(el.GetParameters(name))
    for p in ps:
        if not p.IsReadOnly:
            return p
    return ps[0] if ps else None


def set_param(el, name, value):
    p = _param(el, name)
    if p is None or p.IsReadOnly:
        raise Exception("Parameter '{}' is missing or read-only on family '{}'.".format(name, _fam_name(el)))
    p.Set(value)


def get_len(el, name):
    p = _param(el, name)
    if p is None:
        raise Exception("Parameter '{}' not found on family '{}'.".format(name, _fam_name(el)))
    return p.AsDouble()


def read_displayed_elev(doc, el, bip, fallback_name):
    """Read an elevation exactly as Revit displays it (respects Elevation Base), in internal units."""
    p = el.get_Parameter(bip) or el.LookupParameter(fallback_name)
    if p is None:
        raise Exception("'{}' not found on family '{}'.".format(fallback_name, _fam_name(el)))
    s = p.AsValueString()
    if s:
        ref = clr.Reference[float]()
        try:
            if UnitFormatUtils.TryParse(doc.GetUnits(), SpecTypeId.Length, s, ref):
                return ref.Value
        except Exception:
            pass
    return p.AsDouble()


def _len_value(p):
    """A parameter's value as a length (internal units): a Length parameter as it is, a Number / Integer one in mm.
    None when there is no number."""
    if p is None:
        return None
    if p.StorageType == StorageType.Integer:
        return mm(p.AsInteger())
    if p.StorageType != StorageType.Double:
        return None
    try:
        if p.Definition.GetDataType() != SpecTypeId.Length:
            return mm(p.AsDouble())
    except Exception:
        pass
    return p.AsDouble()


def _type_size(sym):
    """(diameter, source) from the type parameter 'Diameter', or (None, None)."""
    if sym is None:
        return None, None
    for p in sym.GetParameters(SIZE_PARAM):
        v = _len_value(p)
        if v is not None and v > 0:
            return v, "type parameter '{}'".format(SIZE_PARAM)
    return None, None


def _sane(d, src, fam, type_nm):
    """d, or an error when it cannot be a pile diameter (a wrong parameter)."""
    d_mm = to_mm(d)
    if SIZE_RANGE_MM[0] <= d_mm <= SIZE_RANGE_MM[1]:
        return d
    fix = ("Fix the type's '{}' value.".format(SIZE_PARAM) if src.startswith("type parameter") else
           "Shift+Click on SBP Wall and pick the size parameter again (e.g. Radius = 750 mm, it is the radius).")
    raise Exception("Family '{}' type '{}': {} gives {:.0f} mm, which is not a pile diameter. {}".format(
        fam, type_nm, src, d_mm, fix))


def _setup_size(fi):
    """(diameter, source) from the family set-up (saved in the model or recognised by name), with fallbacks."""
    spec = pile_spec(fi)
    tname = type_name(fi.Symbol) if fi.Symbol is not None else "?"
    if spec is None:
        raise Exception("Family '{}' has no type parameter '{}' and no Radius, and is not set up as a pile "
                        "(Shift+Click on SBP Wall to set it up).".format(_fam_name(fi), SIZE_PARAM))
    found_p = None
    for src in (fi, fi.Symbol):                   # an instance parameter can hide a type one of the same name
        if src is None:
            continue
        p = src.LookupParameter(spec["diameter"])
        if p is not None:
            if p.AsDouble() > 0:
                return spec["factor"] * p.AsDouble(), "set-up parameter '{}'{}".format(
                    spec["diameter"], " x 2" if spec["factor"] == 2 else "")
            found_p = found_p or p
    if found_p is None:
        raise Exception("Family '{}' type '{}': saved parameter '{}' not found on the pile or its type.{}".format(
            _fam_name(fi), tname, spec["diameter"], _diam_detail(fi)))
    tried = {spec["diameter"]}
    for fb_name, fb_factor in _SIZE_FALLBACKS:    # the set-up parameter is 0: try the usual names
        if fb_name in tried:
            continue
        tried.add(fb_name)
        for src in (fi, fi.Symbol):
            q = src.LookupParameter(fb_name) if src is not None else None
            if q is not None and q.AsDouble() > 0:
                return fb_factor * q.AsDouble(), "parameter '{}'{}".format(fb_name, " x 2" if fb_factor == 2 else "")
    raise Exception("Family '{}' type '{}': saved parameter '{}' is 0 and no other size parameter has a value.{}"
                    .format(_fam_name(fi), tname, spec["diameter"], _diam_detail(fi)))


def size_of(fi):
    """(diameter in internal units, where it was read) of a pile, read fresh every time (Akash, 6 Oct):
    1. the type parameter 'Diameter'; 2. 'Radius' x 2 on the pile; 3. the family set-up (other families)."""
    d, src = _type_size(fi.Symbol)
    if d is None:
        v = _len_value(_param(fi, "Radius"))
        if v is not None and v > 0:
            d, src = 2.0 * v, "Radius x 2"
    if d is None:
        d, src = _setup_size(fi)
    return _sane(d, src, _fam_name(fi), type_name(fi.Symbol) if fi.Symbol is not None else "?"), src


def diameter_of(fi):
    """Pile diameter (internal units), see size_of."""
    return size_of(fi)[0]


def _diam_detail(fi):
    """A short string listing the pile's positive-value numeric parameters, for error messages."""
    try:
        rows = []
        for src, tag in ((fi, "inst"), (fi.Symbol, "type")):
            if src is None:
                continue
            for p in src.Parameters:
                if p.Definition and p.StorageType == StorageType.Double and p.AsDouble() > 0:
                    rows.append("{}={:.0f}mm({})".format(p.Definition.Name, to_mm(p.AsDouble()), tag))
        return ("  Available positive-value parameters: {}.".format(", ".join(rows[:10])) if rows
                else "  No positive-value numeric parameters found.")
    except Exception:
        return ""


def radius_of(fi):
    """Pile radius; for a foundation that is not a known pile, half its plan size."""
    try:
        return diameter_of(fi) / 2.0
    except Exception:
        bb = fi.get_BoundingBox(None)
        return max(bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y) / 2.0 if bb is not None else mm(300)


def type_size(doc, symbol, level, label=None):
    """(diameter, where it was read) of a pile type, read fresh every time (nothing is cached):
    1. the type parameter 'Diameter' (no test pile needed);
    2. else a test pile in a rolled-back transaction + Regenerate: Radius x 2, else the family set-up.
    (None, None) when it cannot be read. label: the form's name for the type; the reason goes to _DIAM_ERRS[label]
    and the source to _DIAM_SRC[label]. Call outside a transaction."""
    try:
        d, src = _type_size(symbol)
        if d is not None:
            d = _sane(d, src, symbol.Family.Name if symbol.Family else "?", type_name(symbol))
        else:
            t = Transaction(doc, "SBP - read pile size")
            t.Start()
            try:
                if not symbol.IsActive:
                    symbol.Activate()
                    doc.Regenerate()
                probe = doc.Create.NewFamilyInstance(XYZ(0.0, 0.0, level.ProjectElevation), symbol, level,
                                                     StructuralType.Footing)
                doc.Regenerate()
                d, src = size_of(probe)
            finally:
                t.RollBack()
    except Exception as ex:
        if label is not None:
            try:
                s = _saved_specs(doc)[1].get(symbol.Family.UniqueId)
                note = ("  [Saved set-up: diameter='{}', factor={}]".format(s["diameter"], s["factor"]) if s
                        else "")
            except Exception:
                note = ""
            _DIAM_ERRS[label] = str(ex) + note
            _DIAM_SRC.pop(label, None)
        return None, None
    if label is not None:
        _DIAM_ERRS.pop(label, None)
        _DIAM_SRC[label] = src
    return d, src


def type_diameter(doc, symbol, level, label=None):
    """Diameter of a pile type (internal units) or None, see type_size."""
    return type_size(doc, symbol, level, label)[0]


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


def centre_path(items, closed, side, dist, sharp=False):
    """Centre line of the SBP wall: the drawn chain offset by `dist` to `side` (sharp: corners like AutoCAD
    OFFSET, the v2 layout; else outside corners are rounded)."""
    step = mm(SAMPLE_MM)
    path = G.offset_path(chain_samples(items), closed, side, dist, G.CORNER_MAX_DEG if sharp else 0.0)
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


def _plan_ends(path, closed, others, diameter, spacing, ask_kind):
    """Pile type at each end of an open wall (free end HARD, or continuing a joined wall).
    Returns (ends, start type, end type, skip start, skip end)."""
    ends = {"start": None, "end": None}
    if closed:
        return ends, HARD, HARD, False, False
    for key, pt in (("start", path[0]), ("end", path[-1])):
        j = find_join(others, pt, diameter, spacing)
        if j["join"] and j["kind"] is None:
            j["kind"] = ask_kind(key, mark_of(j["pile"]))
            if j["kind"] not in (HARD, SOFT):
                j["join"], j["kind"] = None, None
        ends[key] = j
    st, ss = SD.end_setup(ends["start"]["join"], ends["start"]["kind"])
    et, se = SD.end_setup(ends["end"]["join"], ends["end"]["kind"])
    return ends, st, et, ss, se


def plan_wall_v1(doc, items, closed, side, s, diameter, others, ask_kind):
    """The layout of walls made before 30 Sep (equal spacing over the whole centre line, rounded outside corners).
    SBP Edit uses it only to see whether such a wall's line was moved. s['spacing_hh'] in mm."""
    dist = mm(s["gap"]) + diameter / 2.0
    spacing = mm(s["spacing_hh"] / 2.0)
    path = centre_path(items, closed, side, dist)
    ends, st, et, ss, se = _plan_ends(path, closed, others, diameter, spacing, ask_kind)
    centres, kinds, step, total = G.layout_ends(path, closed, spacing, st, et, ss, se)
    return centres, kinds, {"ends": ends}


def _start_at(path, pt):
    """A closed path turned to start at its point nearest to pt (the drafter's start point)."""
    i0 = min(range(len(path)), key=lambda i: (path[i][0] - pt[0]) ** 2 + (path[i][1] - pt[1]) ** 2)
    return path[i0:] + path[:i0]


def plan_wall(doc, items, closed, side, s, dh, ds, others, ask_kind):
    """v3 pile centres and types for a wall (no model change; Akash, 6 Oct): the design c/c everywhere, through
    corners too, except the closing zone (sbp_geom.layout_closing): the last N bays before the end pile, or on a
    loop before the last bay back into the start HARD (a loop starts where the drafter started drawing).

    s: settings in mm (spacing_hh, gap, close_n, ...). dh / ds: HARD / SOFT diameter (internal units).
    others: piles of other walls (for joins). ask_kind(end, mark) -> 'HARD'|'SOFT'|None is called only when a join
    is found but the joined pile's type is unknown (None = treat the end as free).
    Returns (centres, kinds, info); info has the layout details and 'check' (sbp_geom.check_wall, in mm).
    """
    big = max(dh, ds)
    dist = mm(s["gap"]) + big / 2.0
    sp = mm(s["spacing_hh"] / 2.0)
    web = mm(SD.corner_web(s["spacing_hh"], to_mm(dh)))
    samples = chain_samples(items)
    path = centre_path(items, closed, side, dist, sharp=True)
    if closed:
        path = _start_at(path, samples[0][0][0])
    ends, st, et, ss, se = _plan_ends(path, closed, others, big, sp, ask_kind)
    line = [(a, b) for pts, tans in samples for a, b in zip(pts[:-1], pts[1:])]
    free_end = not closed and not (ends["end"] and ends["end"].get("join"))
    centres, kinds, lay = G.layout_closing(path, closed, sp, dh, ds, web, SD.close_n(s), st, et, SD.CLOSE_N_MAX,
                                           free_end, mm(SD.CLOSE_TOL_MM))
    lo = 1 if (ss and not closed) else 0
    hi = len(centres) - 1 if (se and not closed and lay["close"]["way"] != "short") else len(centres)
    centres, kinds, us = centres[lo:hi], kinds[lo:hi], lay["u"][lo:hi]
    if lay["close"]["first"] is not None:
        lay["close"]["first"] -= lo
    # corners are never adjusted, only reported per bay with their angle (Akash, 7 Oct)
    corners, skipped = G.find_corners(path, G.chain_joints(samples, closed), side, dist)
    walk = G._Walk(list(path) + ([path[0]] if closed else []))
    lay["bends"] = G.bay_corners(us, kinds, closed, walk.total, [(walk.cum[i], b) for i, b, inw in corners])
    k = mm(1.0)
    check = G.check_wall([(x / k, y / k) for x, y in centres], kinds, closed, to_mm(dh), to_mm(ds),
                         s["spacing_hh"] / 2.0, SD.MIN_WEB_MM, [((a[0] / k, a[1] / k), (b[0] / k, b[1] / k))
                                                                 for a, b in line], s["gap"])
    info = {"dist": dist, "ends": ends, "total": G.path_length(path, closed), "layout": lay, "check": check,
            "skipped": [], "dh": dh, "ds": ds}
    return centres, kinds, info


def plan_wall_v2(doc, items, closed, side, s, dh, ds, others, ask_kind):
    """The layout of walls made 30 Sep - 6 Oct (layout 2): design c/c kept on straights and curves, sharp
    corners with a SOFT pile on each corner (option B), every pile checked. SBP Edit uses it only to see whether
    such a wall's line was moved; a rebuild uses plan_wall (v3).

    s: settings in mm (spacing_hh, gap, ...). dh / ds: HARD / SOFT diameter (internal units).
    others: piles of other walls (for joins). ask_kind(end, mark) -> 'HARD'|'SOFT'|None is called only when a join
    is found but the joined pile's type is unknown (None = treat the end as free).
    Returns (centres, kinds, info); info has the layout details and 'check' (sbp_geom.check_wall, in mm).
    """
    big = max(dh, ds)
    dist = mm(s["gap"]) + big / 2.0
    sp = mm(s["spacing_hh"] / 2.0)
    web = mm(SD.corner_web(s["spacing_hh"], to_mm(dh)))
    samples = chain_samples(items)
    path = centre_path(items, closed, side, dist, sharp=True)
    corners, skipped = G.find_corners(path, G.chain_joints(samples, closed), side, dist)
    ends, st, et, ss, se = _plan_ends(path, closed, others, big, sp, ask_kind)
    line = [(a, b) for pts, tans in samples for a, b in zip(pts[:-1], pts[1:])]
    centres, kinds, lay = G.layout_wall(path, closed, corners, sp, dh, ds, web, st, et, line, mm(s["gap"]))
    lo = 1 if (ss and not closed) else 0
    hi = len(centres) - 1 if (se and not closed) else len(centres)
    centres, kinds = centres[lo:hi], kinds[lo:hi]
    for c in lay["corners"]:
        c["index"] -= lo
    k = mm(1.0)
    check = G.check_wall([(x / k, y / k) for x, y in centres], kinds, closed, to_mm(dh), to_mm(ds),
                         s["spacing_hh"] / 2.0, SD.MIN_WEB_MM, [((a[0] / k, a[1] / k), (b[0] / k, b[1] / k))
                                                                 for a, b in line], s["gap"])
    info = {"dist": dist, "ends": ends, "total": G.path_length(path, closed), "layout": lay, "check": check,
            "skipped": skipped, "dh": dh, "ds": ds}
    return centres, kinds, info


def closing_bays(centres, closed, close):
    """The closing zone's bays [([3 pile indices], H-H, gap 1, gap 2)] in internal units (sbp_geom.layout_closing)."""
    n = len(centres)
    bays = []
    if not close or close["first"] is None:
        return bays

    def d(i, j):
        return math.hypot(centres[i][0] - centres[j][0], centres[i][1] - centres[j][1])
    for b in range(close["n"]):
        ids = [close["first"] + 2 * b + t for t in range(3)]
        ids = [i % n for i in ids] if closed else ids
        if ids[-1] >= n:
            break
        bays.append((ids, d(ids[0], ids[2]), d(ids[0], ids[1]), d(ids[1], ids[2])))
    return bays


def bay_table(wall, s, centres, kinds, info, closed):
    """(rows, columns) of every bay of a planned wall for the report (sbp_data.bay_table), or ([], []) for an old
    layout without a closing zone."""
    lay = info["layout"]
    cl = lay.get("close")
    if not cl:
        return [], []
    adjusted = set()
    if cl["first"] is not None and cl["way"] not in ("exact", "short"):
        n = len(centres)
        adjusted = set(i % n for i in range(cl["first"], cl["first"] + 2 * cl["n"] + 1)
                       if (closed or i < n) and kinds[i % n] == SOFT)
    k = mm(1.0)
    return SD.bay_table(wall, [(x / k, y / k) for x, y in centres], kinds, closed, to_mm(info["dh"]),
                        to_mm(info["ds"]), s["spacing_hh"] / 2.0, SD.corner_web(s["spacing_hh"], to_mm(info["dh"])),
                        adjusted, lay.get("bends", {}))


def plan_rows(wall, s, sym_h, sym_s, centres, kinds, info, closed, entered=None, size_src=None):
    """The values SBP Wall / SBP Edit read and work out for one wall, shown BEFORE anything is written
    (sbp_data.plan_rows, with this wall's lengths in mm). size_src: {HARD/SOFT: where the size was read}.
    Returns (rows, warnings, errors)."""
    lay = info["layout"]
    corners = [(c["bend"], to_mm(c["c"][0]), to_mm(c["c"][1]), to_mm(c["move"]), c["limited"]) for c in lay["corners"]]
    closing = None
    if lay.get("close"):
        cl = lay["close"]
        closing = dict(cl, gap=to_mm(cl["gap"]), left=to_mm(cl.get("left", 0.0)), bends=lay.get("bends", {}),
                       bays=[(ids, to_mm(hh), to_mm(a), to_mm(b)) for ids, hh, a, b in closing_bays(centres, closed, cl)])
    return SD.plan_rows(wall, s, type_label(sym_h), type_label(sym_s), to_mm(info["dh"]), to_mm(info["ds"]),
                        to_mm(info["dist"]), to_mm(info["total"]), closed, kinds, info["check"], corners,
                        to_mm(lay["equal"]) if lay["equal"] else None, [(b, why) for p, b, why in info["skipped"]],
                        [b for p, b in lay["dropped"]], lay["low_web_runs"], entered, closing, size_src)


# ------------------------------------------------------------------ placing and levels
def place_piles(doc, symbols, level, wall, centres, kinds):
    """Place piles in wall order with marks WALL-H001 / WALL-S001, Comments HARD PILE / SOFT PILE,
    and the hidden pile data (wall, type, place along the wall). symbols: {HARD: type, SOFT: type}."""
    for sym in set(symbols.values()):
        if not sym.IsActive:
            sym.Activate()
            doc.Regenerate()
    placed = []
    for seq, ((x, y), kind, mark) in enumerate(zip(centres, kinds, SD.default_marks(wall, kinds))):
        fi = doc.Create.NewFamilyInstance(XYZ(x, y, level.ProjectElevation), symbols[kind], level,
                                          StructuralType.Footing)
        fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).Set(mark)
        fi.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).Set(kind + " PILE")
        tag_pile(fi, wall, kind, seq)
        placed.append((fi, kind))
    doc.Regenerate()
    return placed


def apply_levels(doc, piles, cutoff_mm, toe_h_mm, toe_s_mm):
    """Set Cut-off / Toe on piles [(pile, kind)] of one level, calibrated on what Revit displays.

    Family rule (seen in Revit): the displayed Top moves 1:1 with the offset and the displayed
    Bottom = offset - Depth (+ a constant). One reference pile per pile type gives both constants
    (HARD and SOFT may be different types, even different families).
    Returns {kind: (top_mm, bottom_mm)} read back from the first pile of each type.
    """
    groups = {}
    for fi, kind in piles:
        groups.setdefault(_idv(fi.GetTypeId()), []).append((fi, kind))
    check = {}
    for group in groups.values():
        _levels_of_type(doc, group, cutoff_mm, toe_h_mm, toe_s_mm, check)
    return check


def _levels_of_type(doc, piles, cutoff_mm, toe_h_mm, toe_s_mm, check):
    """apply_levels for piles of one pile type."""
    ref = piles[0][0]
    spec = pile_spec(ref) or HOUSE_SPEC
    p_off, p_len = spec["offset"], spec["length"]
    # verify both parameters are writable before touching any pile
    for pname in (p_off, p_len):
        prm = _param(ref, pname)
        if prm is None or prm.IsReadOnly:
            fam = ref.Symbol.Family if ref.Symbol else None
            if fam is not None:
                _SPECS.pop((_doc_key(doc), fam.UniqueId), None)
            raise Exception(
                "Parameter '{}' is missing or read-only on family '{}'.\n\n"
                "The family set-up is wrong. Fix it:\n"
                "  Shift+Click on SBP Wall -> pick the correct parameter for pile length / offset.\n"
                "Then run SBP Wall again.".format(pname, _fam_name(ref)))
    o0, d0 = get_len(ref, p_off), get_len(ref, p_len)
    t0 = read_displayed_elev(doc, ref, BuiltInParameter.STRUCTURAL_ELEVATION_AT_TOP, "Elevation at Top")
    b0 = read_displayed_elev(doc, ref, BuiltInParameter.STRUCTURAL_ELEVATION_AT_BOTTOM, "Elevation at Bottom")
    off = o0 + (mm(cutoff_mm) - t0)
    for fi, kind in piles:
        toe = mm(toe_h_mm if kind == HARD else toe_s_mm)
        dep = d0 + (b0 + (off - o0)) - toe
        if dep <= 0:
            raise Exception("Calculated pile depth is not positive. Check Cut-off / Toe values.")
        set_param(fi, p_off, off)
        set_param(fi, p_len, dep)
    doc.Regenerate()
    mine = {}
    for fi, kind in piles:
        if kind not in mine:
            mine[kind] = (
                to_mm(read_displayed_elev(doc, fi, BuiltInParameter.STRUCTURAL_ELEVATION_AT_TOP, "Elevation at Top")),
                to_mm(read_displayed_elev(doc, fi, BuiltInParameter.STRUCTURAL_ELEVATION_AT_BOTTOM, "Elevation at Bottom")),
            )
    # any pile family: the read-back must match (a wrong set-up would give wrong levels)
    for kind, (top, bottom) in mine.items():
        toe = toe_h_mm if kind == HARD else toe_s_mm
        if abs(top - cutoff_mm) <= LEVEL_CHECK_MM and abs(bottom - toe) > LEVEL_CHECK_MM:
            raise Exception("Family '{}': the toe parameter '{}' does not move the pile bottom (asked toe {:.0f}, "
                            "Revit shows {:.0f}).\n\nShift+Click on SBP Wall and, for the pile length, pick the "
                            "parameter equal to the pile's length (e.g. 'Length = 14000 mm'), not '{}'."
                            .format(_fam_name(ref), p_len, toe, bottom, p_len))
        if abs(top - cutoff_mm) > LEVEL_CHECK_MM or abs(bottom - toe) > LEVEL_CHECK_MM:
            raise Exception("Family '{}' does not follow Cut-off / Toe with '{}' / '{}': asked {:.0f} / {:.0f}, "
                            "Revit shows {:.0f} / {:.0f}. Set the family up again (Shift+Click on SBP Wall)."
                            .format(_fam_name(ref), p_off, p_len, cutoff_mm, toe, top, bottom))
        check.setdefault(kind, (top, bottom))


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
def _spec_names(fi):
    """The pile family's own size / length / cut-off parameters: never copied as typed data."""
    spec = pile_spec(fi)
    return set([spec["diameter"], spec["length"], spec["offset"]]) if spec else set()


def _copyable(p, skip=()):
    if p.IsReadOnly or not p.HasValue:
        return False
    d = p.Definition
    if d is None or d.Name in DATA_SKIP or d.Name in skip:
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
        skip = _spec_names(fi)
        for p in fi.Parameters:
            if not _copyable(p, skip):
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
        skip = _spec_names(fi)
        for name, v in olds[i][4].items():
            if name in skip:
                continue
            p = fi.LookupParameter(name)
            if p is None or p.IsReadOnly:
                continue
            try:
                p.Set(v)
            except Exception:
                pass
        copied.append((olds[i][3], mark_of(fi), to_mm(d)))
    return sorted(copied), [olds[i][3] for i in lost]


# ------------------------------------------------------------------ pile labels (tags), Number button
# Families the Number dropdown lists, in this order. Tags must be ones Revit can put on a Structural Foundation
# (they read the Mark themselves); a Generic Annotation gets the Mark copied into a text parameter.
# unusable_label_types() test-places each one.
LABEL_CATEGORIES = (
    (BuiltInCategory.OST_StructuralFoundationTags, ""),
    (BuiltInCategory.OST_MultiCategoryTags, "Multi-Category Tag"),
    (BuiltInCategory.OST_GenericModelTags, "Generic Model Tag"),
    (BuiltInCategory.OST_GenericAnnotation, "Generic Annotation"),
)
GENERIC_ANNOTATION = "Generic Annotation"


def label_types(doc):
    """[(shown name, FamilySymbol, kind)] for the Tag type dropdown, Structural Foundation tags first.
    Shown name = 'Family : Type', plus '  (kind)' for the other categories; kind = '' for foundation tags."""
    res = []
    for bic, kind in LABEL_CATEGORIES:
        found = []
        for s in FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(bic):
            fam = s.Family.Name if s.Family is not None else "?"
            found.append((SD.label_name(fam, type_name(s), kind), s, kind))
        res += sorted(found, key=lambda e: e[0].lower())
    return res


def default_tag_name(doc, entries, unusable=None):
    """The model's default Structural Foundation tag, else the first usable entry (None if none)."""
    ok = [e for e in entries if e[0] not in (unusable or {})]
    try:
        tid = doc.GetDefaultFamilyTypeId(ElementId(BuiltInCategory.OST_StructuralFoundationTags))
        for name, s, kind in ok:
            if s.Id == tid:
                return name
    except Exception:
        pass
    return ok[0][0] if ok else None


def _writable_text_params(el):
    """Names of the element's own (not built-in) text parameters that can be written."""
    res = []
    for p in el.Parameters:
        d = p.Definition
        if d is None or p.IsReadOnly or p.StorageType != StorageType.String:
            continue
        if isinstance(d, InternalDefinition) and d.BuiltInParameter != BuiltInParameter.INVALID:
            continue
        res.append(d.Name)
    return res


def unusable_label_types(doc, view, pile, entries):
    """Which dropdown entries can label `pile` in `view`. Call outside a transaction.

    Each entry is test-placed inside a transaction that is rolled back, so the model does not change: a tag on the
    pile; a Generic Annotation in the view, where it also needs a text parameter to hold the pile's number.
    Returns (unusable {shown name: why}, note_params {shown name: text parameter} for usable Generic Annotations).
    """
    res, params = {}, {}
    p = pile.Location.Point
    t = Transaction(doc, "SBP Number - check tag types")
    t.Start()
    try:
        for name, sym, kind in entries:
            try:
                if not sym.IsActive:
                    sym.Activate()
                if kind == GENERIC_ANNOTATION:
                    inst = doc.Create.NewFamilyInstance(XYZ(p.X, p.Y, p.Z), sym, view)
                    pick = SD.pick_text_param(_writable_text_params(inst))
                    if pick:
                        params[name] = pick
                    else:
                        res[name] = ("this Generic Annotation has no text parameter to hold the number. In the family, "
                                     "give its Label an instance text parameter (e.g. 'Mark'), then load it again.")
                else:
                    IndependentTag.Create(doc, sym.Id, view.Id, Reference(pile), False, TagOrientation.Horizontal, p)
            except Exception as ex:
                if kind == GENERIC_ANNOTATION:
                    res[name] = "Revit could not place it in this view: {}".format(ex)
                elif kind:
                    res[name] = ("Revit cannot put a {0} on a Structural Foundation pile. Fix the family: open it, "
                                 "Family Category and Parameters > Structural Foundation Tags (or Multi-Category Tags), "
                                 "save, load it again.".format(kind))
                else:
                    res[name] = "Revit refused to tag pile {} in this view: {}".format(mark_of(pile) or "", ex)
    finally:
        t.RollBack()
    return res, params


def _idv(eid):
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def _norm_angle(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a <= -math.pi:
        a += 2 * math.pi
    return a


def _bbox_xy(el, view):
    bb = el.get_BoundingBox(view)
    if bb is None:
        return None
    return (bb.Min.X + bb.Max.X) / 2.0, (bb.Min.Y + bb.Max.Y) / 2.0, bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y


# hidden data on the tags Number places (one Number label per pile)
def _label_schema(create=False):
    s = Schema.Lookup(LABEL_SCHEMA_GUID)
    if s is not None or not create:
        return s
    b = SchemaBuilder(LABEL_SCHEMA_GUID)
    b.SetSchemaName("SBPNumberLabel")
    b.SetReadAccessLevel(AccessLevel.Public)
    b.SetWriteAccessLevel(AccessLevel.Public)
    b.AddSimpleField("Wall", clr.GetClrType(String))
    return b.Finish()


def _is_number_label(tag):
    """True for a tag placed by the Number button."""
    s = _label_schema()
    if s is None:
        return False
    ent = tag.GetEntity(s)
    return ent is not None and ent.IsValid()


def _mark_number_label(tag, wall):
    """Mark a tag as placed by Number. If Revit refuses, the tag still counts by its type."""
    try:
        ent = Entity(_label_schema(True))
        ent.Set[String]("Wall", wall or "")
        tag.SetEntity(ent)
        return True
    except Exception:
        return False


# hidden data on the Generic Annotations Number places: the pile it labels, and its turn relative to the view
def _note_schema(create=False):
    s = Schema.Lookup(NOTE_SCHEMA_GUID)
    if s is not None or not create:
        return s
    b = SchemaBuilder(NOTE_SCHEMA_GUID)
    b.SetSchemaName("SBPNumberNote")
    b.SetReadAccessLevel(AccessLevel.Public)
    b.SetWriteAccessLevel(AccessLevel.Public)
    for f in ("Wall", "Pile", "Angle"):
        b.AddSimpleField(f, clr.GetClrType(String))
    return b.Finish()


def _note_info(el):
    """{'wall', 'pile' (UniqueId), 'angle' (radians, relative to the view)} of a Number annotation, else None."""
    s = _note_schema()
    if s is None:
        return None
    ent = el.GetEntity(s)
    if ent is None or not ent.IsValid():
        return None
    try:
        ang = float(ent.Get[String]("Angle") or 0.0)
    except ValueError:
        ang = 0.0
    return {"wall": ent.Get[String]("Wall"), "pile": ent.Get[String]("Pile"), "angle": ang}


def _set_note_info(el, wall, pile_uid, angle):
    ent = Entity(_note_schema(True))
    ent.Set[String]("Wall", wall or "")
    ent.Set[String]("Pile", pile_uid)
    ent.Set[String]("Angle", repr(float(angle)))
    el.SetEntity(ent)


def _number_notes(doc, view=None):
    """[(annotation, info)] of the Generic Annotations Number placed (in `view`, or in the whole model)."""
    if _note_schema() is None:
        return []
    col = FilteredElementCollector(doc, view.Id) if view is not None else FilteredElementCollector(doc)
    res = []
    for el in col.OfCategory(BuiltInCategory.OST_GenericAnnotation).WhereElementIsNotElementType():
        info = _note_info(el)
        if info:
            res.append((el, info))
    return res


def delete_number_notes(doc, wall):
    """Delete the Number annotations of a wall in every view (its piles were rebuilt: tags vanish with their piles,
    annotations do not). Returns how many. Call inside a transaction."""
    n = 0
    for el, info in _number_notes(doc):
        if info["wall"] == wall:
            doc.Delete(el.Id)
            n += 1
    return n


def _turn(doc, el, ang):
    """Turn an annotation about its insertion point, counter-clockwise as seen in a plan view."""
    if abs(ang) > 1e-9:
        p = el.Location.Point
        ElementTransformUtils.RotateElement(doc, el.Id, Line.CreateBound(p, p + XYZ.BasisZ), ang)


def _view_frame(view):
    """(angle of the view's horizontal, model -> view axes, view -> model axes). The layout works in the view's own
    axes, so 'horizontal' and 'never upside down' are as seen on the sheet, also in a turned view."""
    va = math.atan2(view.RightDirection.Y, view.RightDirection.X)
    ca, sa = math.cos(va), math.sin(va)

    def to_view(x, y):
        return x * ca + y * sa, -x * sa + y * ca

    def to_model(u, v):
        return u * ca - v * sa, u * sa + v * ca

    return va, to_view, to_model


def _lay_out(doc, runs, sizes, other_boxes, to_view, offset_mm, rotation):
    """Label places for runs [(piles [pile], closed, side)], with text sizes [(w, h)] in the same order.
    Returns sbp_geom.place_labels results, in the view's axes."""
    flat = [fi for run, c, s in runs for fi in run]
    levels = set(_idv(fi.LevelId) for fi in flat)
    circles = [to_view(*xy(fi)) + (radius_of(fi),) for fi in all_piles(doc) if _idv(fi.LevelId) in levels]
    labels, i = [], 0
    for run, closed, side in runs:
        pts = [to_view(*xy(fi)) for fi in run]
        r = radius_of(run[0]) if run else 0.0
        for (x, y), (tx, ty) in zip(pts, G.pile_tangents(pts, closed)):
            w, h = sizes[i]
            along, across = math.atan2(ty, tx), math.atan2(tx * side, -ty * side)
            if rotation == "along":
                ang, alt = along, across
            elif rotation == "across":
                ang, alt = across, along
            else:
                ang, alt = math.radians(float(rotation)), None
            labels.append({"x": x, "y": y, "r": r, "tx": tx, "ty": ty, "side": side, "w": w, "h": h, "angle": ang, "alt": alt})
            i += 1
    return G.place_labels(labels, circles, other_boxes, mm(offset_mm), mm(LABEL_GAP_MM))


def _stats(res, flat, made, removed, failed):
    return {"new": made, "moved": len(flat) - made, "removed": removed,
            "flipped": sum(1 for x in res if x[6]), "nudged": sum(1 for x in res if x[3]),
            "turned": sum(1 for x in res if x[5]),
            "touching": [mark_of(flat[j]) for j, x in enumerate(res) if not x[4]], "failed": failed}


def place_pile_tags(doc, view, symbol, walls, offset_mm, rotation):
    """One label (tag) per pile of `walls` in `view`, just clear of the pile, none overlapping.
    Call inside a transaction.

    walls:    [(piles [(pile, kind)] in draw order, closed, side, wall name)]; side +1 = labels on the left
              of the draw direction, -1 = on the right.
    rotation: 'along' / 'across' the wall, or a fixed angle in degrees from the view's horizontal
              (0 = horizontal: every label reads left to right).
    One Number label per pile in this view: a Number tag (or a tag of this type) already on the pile is moved,
    turned and given this type; a second one on the same pile, or a Number annotation, is deleted. Other tags
    are left alone. Returns {"new", "moved", "removed", "flipped", "nudged", "turned", "touching" (marks),
    "failed" (marks Revit could not tag, with the first reason)}.
    """
    va, to_view, to_model = _view_frame(view)
    mine = {}
    for piles, closed, side, wall in walls:
        for fi, k in piles:
            mine[_idv(fi.Id)] = fi
    uids = set(fi.UniqueId for fi in mine.values())
    on_pile, other_boxes, removed = {}, [], 0
    for tag in FilteredElementCollector(doc, view.Id).OfClass(IndependentTag):
        try:
            ids = [_idv(i) for i in tag.GetTaggedLocalElementIds()]
        except Exception:
            ids = []
        hit = [i for i in ids if i in mine]
        if hit and (_is_number_label(tag) or tag.GetTypeId() == symbol.Id):
            on_pile.setdefault(hit[0], []).append(tag)
        else:
            box = _bbox_xy(tag, view)
            if box is not None:
                u, v = to_view(box[0], box[1])
                other_boxes.append((u, v, -va, box[2], box[3]))
    for el, info in _number_notes(doc, view):            # a pile labelled by an annotation before: now a tag
        if info["pile"] in uids:
            doc.Delete(el.Id)
            removed += 1
    reuse = {}
    for pid, tl in on_pile.items():
        tl.sort(key=lambda t: (not _is_number_label(t), t.GetTypeId() != symbol.Id))
        reuse[pid] = tl[0]
        for extra in tl[1:]:                 # one Number label per pile
            doc.Delete(extra.Id)
            removed += 1
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
    # 1. one tag per pile, text along model X for measuring
    runs, tags, flat, failed, made = [], [], [], [], 0
    for piles, closed, side, wall in walls:
        run = []
        for fi, k in piles:
            tag = reuse.get(_idv(fi.Id))
            new = tag is None
            try:
                if new:
                    p = fi.Location.Point
                    tag = IndependentTag.Create(doc, symbol.Id, view.Id, Reference(fi), False,
                                                TagOrientation.AnyModelDirection, XYZ(p.X, p.Y, p.Z))
                else:
                    if tag.GetTypeId() != symbol.Id:
                        tag.ChangeTypeId(symbol.Id)
                    if tag.HasLeader:
                        tag.HasLeader = False
                    if tag.TagOrientation != TagOrientation.AnyModelDirection:
                        tag.TagOrientation = TagOrientation.AnyModelDirection
                tag.RotationAngle = _norm_angle(TAG_ANGLE_SIGN * (0.0 - va))
                _mark_number_label(tag, wall)
            except Exception as ex:
                if new and tag is not None:
                    try:
                        doc.Delete(tag.Id)       # no half-made tag left at the pile centre
                    except Exception:
                        pass
                failed.append("{} ({})".format(mark_of(fi), ex) if not failed else mark_of(fi))
                continue
            made += 1 if new else 0
            run.append(fi)
            tags.append(tag)
            flat.append(fi)
        runs.append((run, closed, side))
    doc.Regenerate()
    # 2. measure each label (text along model X: its box is exact), 3. lay them out in the view's axes
    sizes = []
    for tag in tags:
        box = _bbox_xy(tag, view)
        sizes.append((box[2], box[3]) if box else (mm(1000), mm(400)))
    res = _lay_out(doc, runs, sizes, other_boxes, to_view, offset_mm, rotation)
    # 4. turn each label (the angle is relative to the view), then move it so its centre lands on its place
    for tag, lab in zip(tags, res):
        tag.RotationAngle = _norm_angle(TAG_ANGLE_SIGN * lab[2])
    doc.Regenerate()
    for tag, lab in zip(tags, res):
        box = _bbox_xy(tag, view)
        if box is not None:
            cx, cy = to_model(lab[0], lab[1])
            h = tag.TagHeadPosition
            tag.TagHeadPosition = XYZ(h.X + cx - box[0], h.Y + cy - box[1], h.Z)
    doc.Regenerate()
    return _stats(res, flat, made, removed, failed)


def place_pile_notes(doc, view, symbol, param, walls, offset_mm, rotation):
    """Like place_pile_tags, but each label is a Generic Annotation in `view` with the pile's Mark copied into its
    text parameter `param` (it does not follow later Mark changes: Number updates it). Call inside a transaction.

    One Number label per pile in this view: a Number annotation of that pile is moved, turned, updated and given
    this type; a second one, or a Number tag on that pile, is deleted. Returns the same dict as place_pile_tags.
    """
    va, to_view, to_model = _view_frame(view)
    by_id = {}
    wall_of_pile = {}
    for piles, closed, side, wall in walls:
        for fi, k in piles:
            by_id[_idv(fi.Id)] = fi
            wall_of_pile[fi.UniqueId] = wall
    other_boxes, removed = [], 0
    for tag in FilteredElementCollector(doc, view.Id).OfClass(IndependentTag):
        try:
            ids = [_idv(i) for i in tag.GetTaggedLocalElementIds()]
        except Exception:
            ids = []
        if _is_number_label(tag) and any(i in by_id for i in ids):
            doc.Delete(tag.Id)                            # a pile tagged by Number before: now an annotation
            removed += 1
            continue
        box = _bbox_xy(tag, view)
        if box is not None:
            u, v = to_view(box[0], box[1])
            other_boxes.append((u, v, -va, box[2], box[3]))
    reuse = {}
    for el, info in _number_notes(doc, view):
        if info["pile"] in wall_of_pile:
            if info["pile"] in reuse:
                doc.Delete(el.Id)                         # one Number label per pile
                removed += 1
            else:
                reuse[info["pile"]] = (el, info["angle"])
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
    # 1. one annotation per pile, with its number, turned back to the view's horizontal
    runs, notes, flat, failed, made = [], [], [], [], 0
    for piles, closed, side, wall in walls:
        run = []
        for fi, k in piles:
            el, cur = reuse.get(fi.UniqueId, (None, 0.0))
            new = el is None
            try:
                if new:
                    p = fi.Location.Point
                    el = doc.Create.NewFamilyInstance(XYZ(p.X, p.Y, p.Z), symbol, view)
                    cur = 0.0
                elif el.GetTypeId() != symbol.Id:
                    el.ChangeTypeId(symbol.Id)
                prm = el.LookupParameter(param)
                if prm is None or prm.IsReadOnly:
                    raise Exception("parameter '{}' is missing or read-only".format(param))
                prm.Set(mark_of(fi))
                _turn(doc, el, -cur)
                _set_note_info(el, wall, fi.UniqueId, 0.0)
            except Exception as ex:
                if new and el is not None:
                    try:
                        doc.Delete(el.Id)
                    except Exception:
                        pass
                failed.append("{} ({})".format(mark_of(fi), ex) if not failed else mark_of(fi))
                continue
            made += 1 if new else 0
            run.append(fi)
            notes.append(el)
            flat.append(fi)
        runs.append((run, closed, side))
    doc.Regenerate()
    # 2. measure (the box follows the view; in a turned view its size is recovered), 3. lay them out
    sizes = []
    for el in notes:
        box = _bbox_xy(el, view)
        sizes.append(G.unturned_size(box[2], box[3], va) if box else (mm(1000), mm(400)))
    res = _lay_out(doc, runs, sizes, other_boxes, to_view, offset_mm, rotation)
    # 4. turn each annotation, then move it so its centre lands on its place
    for el, fi, lab in zip(notes, flat, res):
        _turn(doc, el, lab[2])
        _set_note_info(el, wall_of_pile[fi.UniqueId], fi.UniqueId, lab[2])
    doc.Regenerate()
    for el, lab in zip(notes, res):
        box = _bbox_xy(el, view)
        if box is not None:
            cx, cy = to_model(lab[0], lab[1])
            ElementTransformUtils.MoveElement(doc, el.Id, XYZ(cx - box[0], cy - box[1], 0.0))
    doc.Regenerate()
    return _stats(res, flat, made, removed, failed)


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
            res[d["wall"]] = (ds, SD.upgrade(d))
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


def wall_data(wall, symbols, level, s, items, closed, side, styles):
    """Everything a wall needs to be rebuilt later (lengths in mm). symbols: {HARD: type, SOFT: type}.
    spacing_by / spacing_val: the spacing value the drafter set (a cutting depth or web wins over HARD to HARD)."""
    first = items[0]
    return {
        "wall": wall, "type_uid": symbols[HARD].UniqueId, "type_name": type_name(symbols[HARD]),
        "soft_type_uid": symbols[SOFT].UniqueId, "soft_type_name": type_name(symbols[SOFT]),
        "level_uid": level.UniqueId, "level_name": level.Name,
        "spacing_hh": s["spacing_hh"], "spacing_by": s.get("spacing_by") or "spacing_hh",
        "spacing_val": s.get("spacing_val") if s.get("spacing_val") is not None else s["spacing_hh"],
        "gap": s["gap"], "cutoff": s["cutoff"],
        "toe_hard": s["toe_hard"], "toe_soft": s["toe_soft"], "invisible": bool(s["invisible"]),
        "lines": [e.UniqueId for c, e, r in items], "line_styles": styles,
        "side": side, "anchor_uid": first[1].UniqueId, "anchor_reversed": bool(first[2]),
        "closed": bool(closed), "layout": 3, "close_n": SD.close_n(s),
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


def _overrides(pattern_id, rgb):
    o = OverrideGraphicSettings()
    col = Color(*rgb)
    o.SetSurfaceForegroundPatternId(pattern_id)
    o.SetSurfaceForegroundPatternColor(col)
    o.SetSurfaceForegroundPatternVisible(True)
    o.SetCutForegroundPatternId(pattern_id)
    o.SetCutForegroundPatternColor(col)
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
            target.SetFilterOverrides(f.Id, _overrides(patterns[kind], FILL_RGB[kind]))
        target.SetFilterVisibility(f.Id, True)
    return "HARD solid grey {}, SOFT '{}' in {}".format(FILL_RGB[HARD], HATCH_NAME, where)


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


# ---------------------------------------------------------- spacing compliance schedule
_COMP_EXTRA_MM = 600.0   # minimum clear distance beyond the pile's own diameter


def _same_kind_neighbours(kinds, i, closed):
    """Indices of the previous and next pile of the same kind as pile i, in wall order (wrapping on a loop)."""
    n = len(kinds)
    res = []
    for step in (-1, 1):
        j = i + step
        while (closed or 0 <= j < n) and j % n != i:
            if kinds[j % n] == kinds[i]:
                res.append(j % n)
                break
            j += step
    return res


def spacing_compliance_table(placed, dia_mm, closed):
    """Per-pile spacing compliance check: c/c to the previous / next pile OF THE SAME TYPE (HARD to HARD, SOFT to
    SOFT), against min required = pile diameter + 600 mm. (A HARD and a SOFT neighbour always overlap.)

    placed  [(FamilyInstance, kind)] in wall order.
    dia_mm  {HARD: mm, SOFT: mm} as plain Python floats.
    closed  True for a looped wall.

    Returns (rows, n_below, n_above) where rows is a list of
    [mark, diam_mm, actual_mm, required_mm, compliance_text]
    ready for output.print_table."""
    rows = []
    n_below = n_above = 0
    kinds = [k for _, k in placed]
    for i, (fi, kind) in enumerate(placed):
        d_own = dia_mm.get(kind, 0.0)
        required = d_own + _COMP_EXTRA_MM
        pt = fi.Location.Point
        nbr_pts = [placed[j][0].Location.Point for j in _same_kind_neighbours(kinds, i, closed)]
        dists_mm = [to_mm(((pt.X - p.X) ** 2 + (pt.Y - p.Y) ** 2) ** 0.5) for p in nbr_pts]
        actual = min(dists_mm) if dists_mm else None
        mark = fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).AsString() or "?"
        eid = _idv(fi.Id)
        if actual is None or abs(actual - required) <= 1.0:
            status = "OK"
        elif actual < required:
            status = "Below requirement -- file ID: {}".format(eid)
            n_below += 1
        else:
            status = "Above requirement -- file ID: {}".format(eid)
            n_above += 1
        rows.append([mark,
                     "{:.0f}".format(d_own),
                     "{:.0f}".format(actual) if actual is not None else "-",
                     "{:.0f}".format(required),
                     status])
    return rows, n_below, n_above

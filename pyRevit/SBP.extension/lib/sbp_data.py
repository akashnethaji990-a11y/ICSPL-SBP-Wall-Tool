# -*- coding: utf-8 -*-
"""Pure-Python helpers for SBP walls (no Revit API here, so it can be tested outside Revit).

- the settings each wall remembers (saved as JSON inside the Revit model)
- what changed in SBP Edit, and whether the wall must be rebuilt
- where typed pile data goes after a rebuild (nearest pile of the same type)
- how a wall end joins another wall (which pile type comes first)
- layout-plan pile numbers (SP1, HP1 ...) for the Number button
All lengths are in mm unless a function says otherwise.
"""
import json
import math
import re

VERSION = 2               # 2 (30 Sep): v2 layout, HARD-HARD spacing, a SOFT pile type (upgrade() reads version 1)
NUM_KEYS = ("spacing_hh", "gap", "cutoff", "toe_hard", "toe_soft")
REBUILD_KEYS = ("type", "soft_type", "level", "spacing_hh", "gap", "close_n")
LEVEL_KEYS = ("cutoff", "toe_hard", "toe_soft")
MIN_GAP_MM = 10.0          # smallest gap from the drawn line to the SBP inner edge (was 150 until 28 Sep)
MIN_WEB_MM = 200.0         # a leftover SOFT web below this is a WARNING; corners keep at least this much
CLOSE_N_DEFAULT = 3        # bays in the closing zone, the only bays that take the leftover (Akash, 6 Oct)
CLOSE_N_MAX = 6            # the zone grows up to this when N bays cannot close without a warning
DEFAULT_HH_EXTRA_MM = 600.0  # the form fills c/c HARD to HARD = HARD diameter + this (Akash, 6 Oct)
CLOSE_TOL_MM = 10.0        # a last bay within this of the design HARD to HARD is not "adjusted" (Akash, 7 Oct)


def close_n(s):
    """The wall's closing-zone bays (saved per wall; walls made before 6 Oct: the default)."""
    try:
        return int(s.get("close_n") or CLOSE_N_DEFAULT)
    except (TypeError, ValueError):
        return CLOSE_N_DEFAULT


def default_hh(dh):
    """c/c HARD to HARD the form starts with for a HARD diameter dh (mm): dh + 600 (1200 -> 1800)."""
    return None if not dh else dh + DEFAULT_HH_EXTRA_MM


# ---------------------------------------------------------------- saved settings
def encode(data):
    d = dict(data)
    d["version"] = VERSION
    return json.dumps(d, sort_keys=True)


def decode(text):
    d = json.loads(text)
    if int(d.get("version", 0)) > VERSION:
        raise ValueError("These wall settings were saved by a newer SBP tool.")
    return d


def upgrade(d):
    """Wall settings in today's terms. Walls saved before 30 Sep keep HARD to SOFT ('spacing') and one pile type:
    HARD to HARD = 2 x spacing, set by HARD to HARD; the SOFT type = the HARD type; layout 1 (equal spacing)."""
    d = dict(d)
    if d.get("spacing_hh") is None and d.get("spacing") is not None:
        d["spacing_hh"] = 2.0 * float(d["spacing"])
    d.setdefault("spacing_by", "spacing_hh")
    d.setdefault("spacing_val", d.get("spacing_hh"))
    d.setdefault("soft_type_uid", d.get("type_uid"))
    d.setdefault("soft_type_name", d.get("type_name"))
    d.setdefault("layout", 1)
    d.setdefault("close_n", CLOSE_N_DEFAULT)
    return d


def check_settings(s, min_gap=MIN_GAP_MM):
    """List of problems with a settings dict (empty list = OK)."""
    errs = []
    if s["spacing_hh"] <= 0:
        errs.append("c/c spacing must be greater than 0.")
    if s["gap"] < min_gap:
        errs.append("Gap must be at least {:.0f} mm (you entered {:.0f}).".format(min_gap, s["gap"]))
    if max(s["toe_hard"], s["toe_soft"]) >= s["cutoff"]:
        errs.append("Toe Level must be below the Cut-off Level.")
    n = s.get("close_n", CLOSE_N_DEFAULT)
    if n is not None and (n != int(n) or not 1 <= int(n) <= CLOSE_N_MAX):
        errs.append("Closing SOFT piles must be a whole number from 1 to {} (you entered {}).".format(
            CLOSE_N_MAX, fmt_num(n)))
    return errs


# ---------------------------------------------------------------- the three linked spacing values
# The SOFT pile sits halfway between two HARD piles. With HARD diameter Dh, SOFT diameter Ds and c/c HARD to HARD:
#   cutting depth (each HARD into the SOFT) = (Dh + Ds - HARD to HARD) / 2
#   leftover SOFT web (between the HARD edges) = HARD to HARD - Dh
#   (HARD to SOFT = HARD to HARD / 2)
# The drafter types any one; the other two follow from the real diameters. The value typed is saved with the wall
# ('spacing_by' / 'spacing_val'): a typed cutting depth or web wins, so a new pile type keeps it and moves HARD to HARD.
SPACING_KEYS = ("spacing_hh", "cut", "web")
SPACING_LABELS = {"spacing_hh": "HARD to HARD", "cut": "cutting depth", "web": "leftover SOFT web"}


def spacing_values(hh, dh, ds):
    """The linked spacing numbers (mm) from c/c HARD to HARD and the two diameters (None when unknown)."""
    if hh is None:
        return dict.fromkeys(SPACING_KEYS + ("spacing",))
    return {"spacing_hh": hh, "spacing": hh / 2.0,
            "cut": (dh + ds - hh) / 2.0 if dh and ds else None,
            "web": hh - dh if dh else None}


def hh_from(key, value, dh, ds):
    """c/c HARD to HARD from one typed value ('spacing' = the old HARD to SOFT)."""
    if key == "cut":
        return dh + ds - 2.0 * value
    if key == "web":
        return dh + value
    if key == "spacing":
        return 2.0 * value
    return value


def changed_spacing(entered, shown):
    """[(key, value)] of the spacing boxes the drafter changed (a blank box is ignored), in SPACING_KEYS order."""
    return [(k, entered[k]) for k in SPACING_KEYS
            if entered.get(k) is not None and (shown.get(k) is None or abs(entered[k] - shown[k]) > 1e-6)]


def spacing_driver(changed, dh, ds):
    """Which typed box sets the spacing. Returns (key, value, note, error).

    One box changed: that one. A typed cutting depth or web wins over a typed HARD to HARD that does not fit
    (note says so). A cutting depth and a web that do not fit together: error."""
    if not changed:
        return None, None, None, None
    own = [(k, v) for k, v in changed if k in ("cut", "web")]
    if len(own) == 2 and abs(hh_from(own[0][0], own[0][1], dh, ds) - hh_from(own[1][0], own[1][1], dh, ds)) > 0.5:
        return None, None, None, "Cutting depth {} and leftover web {} do not fit together. Change only one.".format(
            fmt_num(own[0][1]), fmt_num(own[1][1]))
    key, value = own[0] if own else changed[0]
    note = None
    typed_hh = [v for k, v in changed if k == "spacing_hh"]
    if own and typed_hh and abs(typed_hh[0] - hh_from(key, value, dh, ds)) > 0.5:
        note = "HARD to HARD {} not used: your {} {} wins (HARD to HARD {}).".format(
            fmt_num(typed_hh[0]), SPACING_LABELS[key], fmt_num(value), fmt_num(hh_from(key, value, dh, ds)))
    return key, value, note, None


def check_spacing(hh, dh, ds, min_web=MIN_WEB_MM):
    """(errors, warnings) for c/c HARD to HARD `hh` with HARD / SOFT diameters dh / ds (mm)."""
    if hh is None or hh <= 0:
        return ["c/c HARD to HARD must be greater than 0."], []
    v = spacing_values(hh, dh, ds)
    errs, warns = [], []
    if v["cut"] <= 0:
        errs.append("HARD to HARD {} gives cutting depth {}: the HARD piles must cut the SOFT piles (HARD to HARD "
                    "less than {}).".format(fmt_num(hh), fmt_num(v["cut"]), fmt_num(dh + ds)))
    if v["web"] < 0:
        errs.append("HARD to HARD {} is less than the HARD diameter {}: the HARD piles would cut each other "
                    "(leftover web {}).".format(fmt_num(hh), fmt_num(dh), fmt_num(v["web"])))
    if hh < ds:
        errs.append("HARD to HARD {} is less than the SOFT diameter {}: the SOFT piles would cut each other."
                    .format(fmt_num(hh), fmt_num(ds)))
    if not errs and v["web"] < min_web:
        warns.append("Leftover SOFT web {} is below {} (WARNING, placed as asked).".format(
            fmt_num(v["web"]), fmt_num(min_web)))
    return errs, warns


def corner_web(hh, dh, min_web=MIN_WEB_MM):
    """Smallest SOFT web the layout keeps at corners and in reduced gaps: 200, or the design web when that is less."""
    return max(min(min_web, hh - dh), 0.0)


def closing_text(closing):
    """One line about the closing zone (closing: sbp_geom.layout_closing info['close'] with the gap in mm)."""
    n, n_set, hh = closing["n"], closing["n_set"], 2.0 * closing["gap"]
    raised = ", N raised from {} to {}".format(n_set, n) if n > n_set and closing["way"] != "equal" else ""
    return {"exact": "none needed: the length fits the design c/c",
            "short": "none needed: the wall ends with the last design HARD pile, {:.0f} mm before the line end".format(
                closing.get("left", 0.0)),
            "tiny": "none needed: the last bay is H-H {:.1f}, within {:.0f} mm of the design".format(hh, CLOSE_TOL_MM),
            "shrink": "{} bay{} shortened to H-H {:.0f}{}".format(n, "" if n == 1 else "s", hh, raised),
            "stretch": "{} bay{} lengthened to H-H {:.0f} (less overlap){}".format(n, "" if n == 1 else "s", hh,
                                                                                    raised),
            "equal": "wall shorter than the zone: all gaps equal, H-H {:.0f}".format(hh)}.get(closing["way"], "")


def plan_rows(wall, s, hard_type, soft_type, dh, ds, dist, total, closed, kinds, chk, corners, equal=None,
              skipped=(), dropped=(), low_web_runs=0, entered=None, closing=None, size_src=None):
    """The values read and worked out for one wall, shown BEFORE anything is written (all lengths in mm).

    s: the wall settings (spacing_hh, spacing_by, spacing_val, gap). dh / ds: diameters read from the pile types.
    dist: line to centre line; total: centre line length. chk: sbp_geom.check_wall result (in mm).
    corners: [(bend, c to one HARD, c to the other, SOFT moved, stopped by the gap)]. equal: c/c of a closed wall
    divided equally (no corners). skipped: [(bend, why)] turns without the corner rule; dropped: [bend].
    closing: the v3 closing zone (closing_text keys + bays [([3 indices], H-H, gap 1, gap 2)], mm), or None (v2).
    size_src: {'HARD'/'SOFT': where the size was read}.
    Returns (rows [[item, value]], warnings [text], errors [text]); piles are named by the marks they will get.
    """
    v = spacing_values(s["spacing_hh"], dh, ds)
    marks = default_marks(wall, kinds)
    by = s.get("spacing_by") or "spacing_hh"
    val = s.get("spacing_val") if s.get("spacing_val") is not None else s["spacing_hh"]
    src = size_src or {}
    rows = [
        ["HARD pile (read from its type)", "{}: {:.0f} mm{}".format(
            hard_type, dh, " ({})".format(src["HARD"]) if src.get("HARD") else "")],
        ["SOFT pile (read from its type)", "{}: {:.0f} mm{}".format(
            soft_type, ds, " ({})".format(src["SOFT"]) if src.get("SOFT") else "")],
        ["Spacing set by", "{} {} ({})".format(SPACING_LABELS.get(by, by), fmt_num(val), entered or "saved")],
        ["c/c HARD to HARD (design)", "{:.0f}".format(v["spacing_hh"])],
        ["c/c HARD to SOFT", "{:.0f}".format(v["spacing"])],
        ["Cutting depth, each side = (Dh + Ds - HH) / 2", "{:.0f}".format(v["cut"])],
        ["Leftover SOFT web = HH - Dh", "{:.0f}{}".format(v["web"], "  WARNING: below {:.0f}".format(MIN_WEB_MM)
                                                        if v["web"] < MIN_WEB_MM - 0.5 else "")],
        ["Gap / line to centre line (mm)", "{:.0f} / {:.0f}".format(s["gap"], dist)],
        ["Centre line", "{:.3f} m, {}".format(total / 1000.0, "closed loop" if closed else "open")],
    ]
    if closing is not None:
        rows.append(["Corners", "no adjustment: the design c/c goes through them"])
    elif corners:
        groups = []
        for c in corners:
            txt = "{:.0f} deg: HARD {:.0f} / {:.0f} from it, SOFT moved {:.0f}{}".format(
                c[0], c[1], c[2], c[3], " (stopped by the gap)" if c[4] else "")
            if groups and groups[-1][0] == txt:
                groups[-1][1] += 1
            else:
                groups.append([txt, 1])
        rows.append(["Corners: SOFT on the corner (option B)", "; ".join(
            t + (" (x{})".format(n) if n > 1 else "") for t, n in groups)])
    else:
        rows.append(["Corners", "none" + (" (closed loop: equal c/c {:.1f})".format(equal) if equal and closed else "")])
    nh = sum(1 for k in kinds if k == "HARD")
    gaps = chk["gaps"]
    design = sum(1 for g in gaps if abs(g - v["spacing"]) <= 0.5)
    rows += [
        ["Piles", "{} HARD + {} SOFT = {}".format(nh, len(kinds) - nh, len(kinds))],
        ["Gaps at design c/c", "{} of {}".format(design, len(gaps)) + (
            ", {} reduced (smallest {:.0f})".format(len(gaps) - design, min(gaps)) if gaps and design < len(gaps) else "")],
    ]
    if closing is not None:
        rows.append(["Closing zone (the only adjusted bays)", closing_text(closing)])
        for ids, hh, a, b in closing.get("bays", []):
            rows.append(["  bay {}".format(" - ".join(marks[i] for i in ids)),
                         "H-H {:.0f} (H-S {:.0f} / {:.0f}), web {:.0f}, cut {:.0f}".format(
                             hh, a, b, hh - dh, (dh + ds) / 2.0 - max(a, b))])
    if chk["min_web"]:
        rows.append(["Smallest SOFT web (mm)", "{:.0f} at {}".format(chk["min_web"][0], marks[chk["min_web"][1]])])
    if chk["min_cut"]:
        rows.append(["Smallest cutting depth (mm)", "{:.0f} at {}".format(chk["min_cut"][0], marks[chk["min_cut"][1]])])
    bends = (closing or {}).get("bends") or {}

    def at(i):
        return " (corner {:.0f} deg)".format(bends[i]) if i in bends else ""
    warns = ["{}: {}{}".format(marks[i], t, at(i)) for i, t in chk["warnings"]]
    errs = ["{}: {}{}".format(marks[i], t, at(i)) for i, t in chk["errors"]]
    for b, why in skipped:
        warns.append("turn of {:.0f} deg: {}".format(b, why))
    for b in dropped:
        warns.append("corner of {:.0f} deg dropped: a leg next to it is too short for the corner rule".format(b))
    if closing is not None and not closing.get("clean", True):
        warns.append("closing zone: no choice for 1 or {} to {} bays passes every check, so the one closest to the "
                     "design is used: {}".format(closing["n_set"], CLOSE_N_MAX, closing_text(closing)))
        if closed:
            warns.append("TIP: start drawing the loop at the middle of a side (not on a corner): the adjusted bays "
                         "then sit on a straight run")
    if low_web_runs:
        warns.append("{} run(s) too short to take the leftover with web {:.0f}: every gap there is reduced "
                     "equally".format(low_web_runs, min(MIN_WEB_MM, v["web"])))
    rows.append(["Warnings / errors", "{} / {}".format(len(warns), len(errs))])
    return rows, warns, errs


def bay_table(wall, centres, kinds, closed, dh, ds, s, web_min=MIN_WEB_MM, adjusted=(), bends=None):
    """Every bay of a wall for the report (Akash, 7 Oct): a SOFT pile with a HARD pile on each side, by marks, with
    the two straight c/c HARD to SOFT, the straight HARD to HARD, the leftover web, the cutting depth, adjusted or
    not and the corner angle. centres in mm; s: design HARD to SOFT; adjusted: SOFT indices in the adjusted bays;
    bends: {SOFT index: corner angle}. Returns (rows, columns)."""
    marks = default_marks(wall, kinds)
    bends = bends or {}
    n = len(centres)
    design_cut = (dh + ds) / 2.0 - s

    def d(i, j):
        return math.hypot(centres[i][0] - centres[j][0], centres[i][1] - centres[j][1])
    rows = []
    for i in range(n):
        a, b = i - 1, i + 1
        if closed:
            a, b = a % n, b % n
        elif a < 0 or b >= n:
            continue
        if kinds[i] != "SOFT" or kinds[a] != "HARD" or kinds[b] != "HARD":
            continue
        hs1, hs2, hh = d(a, i), d(i, b), d(a, b)
        web, cut = hh - dh, (dh + ds) / 2.0 - max(hs1, hs2)
        note = []
        if web < -0.5:
            note.append("ERROR: HARD cuts HARD")
        elif web < web_min - 0.5:
            note.append("WARNING: web below {:.0f}".format(web_min))
        if cut <= 0.5:
            note.append("ERROR: no overlap")
        elif cut < design_cut - 0.5:
            note.append("WARNING: cut below {:.0f}".format(design_cut))
        rows.append(["{} - {} - {}".format(marks[a], marks[i], marks[b]), "{:.1f} / {:.1f}".format(hs1, hs2),
                     "{:.1f}".format(hh), "{:.0f}".format(web), "{:.0f}".format(cut),
                     "yes" if i in adjusted else "", "{:.0f} deg".format(bends[i]) if i in bends else "",
                     "; ".join(note) or "OK"])
    return rows, ["Bay (H - S - H)", "c/c H-S (mm)", "c/c H-H (mm)", "Web", "Cut", "Adjusted", "Corner", "Check"]


def default_marks(wall, kinds):
    """The marks SBP Wall gives, in wall order: WALL-H001, WALL-S001 ... (HARD and SOFT counted separately)."""
    n = {"HARD": 0, "SOFT": 0}
    res = []
    for k in kinds:
        n[k] += 1
        res.append("{}-{}{:03d}".format(wall, "H" if k == "HARD" else "S", n[k]))
    return res


def fmt_num(v):
    """900.0 -> '900', -150.0 -> '-150', 868.25 -> '868.25'. None / blank -> '' (never crashes)."""
    if v is None or v == "":
        return ""
    return "{:g}".format(float(v))


def linked_boxes(driver, value, dh, ds):
    """The three linked spacing boxes {spacing_hh, cut, web} (mm), all consistent, from the one box the drafter
    set: `driver` in SPACING_KEYS (or 'spacing' = the old HARD-to-SOFT) and its `value`, with the HARD / SOFT
    diameters dh / ds. HARD to HARD is the master; cut and web are its computed defaults, so re-driving from HARD
    to HARD always restores them. A blank value, or a diameter still unknown when the driver is cut / web, leaves
    what cannot be worked out as None (the caller shows it blank, never crashing)."""
    if value is None:
        return dict.fromkeys(SPACING_KEYS)
    if driver in ("cut", "web") and not (dh and ds):
        return {"spacing_hh": None, "cut": value if driver == "cut" else None,
                "web": value if driver == "web" else None}
    hh = hh_from(driver, value, dh, ds)
    v = spacing_values(hh, dh, ds)
    return {"spacing_hh": v["spacing_hh"], "cut": v["cut"], "web": v["web"]}


def same_value(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-6
    return a == b


def changed_fields(old, new, keys):
    return [k for k in keys if not same_value(old.get(k), new.get(k))]


def needs_rebuild(changed):
    return any(k in REBUILD_KEYS for k in changed)


def same_layout(old, new, tol):
    """old/new: lists of (x, y, kind). True when both have the same piles at the same places."""
    if len(old) != len(new):
        return False
    left = list(old)
    for x, y, k in new:
        hit = None
        for i, (ox, oy, ok) in enumerate(left):
            if ok == k and math.hypot(ox - x, oy - y) <= tol:
                hit = i
                break
        if hit is None:
            return False
        left.pop(hit)
    return True


# ---------------------------------------------------------------- typed data after a rebuild
def match_nearest(old, new, max_dist=None):
    """Where typed data goes after a rebuild.

    old/new: lists of (x, y, kind). Each old pile is matched to the nearest new pile of
    the same type. If two old piles pick the same new pile, the closer one wins.
    max_dist: never copy further than this (the wall was moved far away: data is not copied).
    Returns (matches, lost): matches = {old_index: (new_index, distance)}, lost = [old_index].
    """
    best = {}
    for i, (ox, oy, ok) in enumerate(old):
        pick, dist = None, None
        for j, (nx, ny, nk) in enumerate(new):
            if nk != ok:
                continue
            d = math.hypot(nx - ox, ny - oy)
            if dist is None or d < dist:
                pick, dist = j, d
        if pick is not None and (max_dist is None or dist <= max_dist):
            best[i] = (pick, dist)
    owner = {}
    for i, (j, d) in best.items():
        if j not in owner or d < best[owner[j]][1]:
            owner[j] = i
    matches = dict((i, best[i]) for i in owner.values())
    lost = sorted(i for i in range(len(old)) if i not in matches)
    return matches, lost


# ---------------------------------------------------------------- wall names
def next_free_name(name, used):
    """'SBP1' if it is free, else 'SBP2', 'SBP3' ... (keeps the prefix). SBP Wall never reuses a name."""
    name = (name or "").strip() or "SBP1"
    if name not in used:
        return name
    m = re.match(r"^(.*?)(\d+)$", name)
    base, n = (m.group(1), int(m.group(2))) if m else (name, 1)
    while True:
        n += 1
        cand = "{}{}".format(base, n)
        if cand not in used:
            return cand


# ---------------------------------------------------------------- joining another wall
def other(kind):
    return "SOFT" if kind == "HARD" else "HARD"


def classify_join(dist, diameter, spacing):
    """How a wall end relates to the nearest pile of ANOTHER wall.

    'same'  : that pile already sits where this end pile would go (closer than half a c/c):
              the wall continues from it and no new pile is placed there.
    'touch' : it overlaps this end pile (closer than one diameter): this end pile is
              the other type, so HARD always follows SOFT.
    None    : not joined.
    """
    if dist is None:
        return None
    if dist < spacing / 2.0:
        return "same"
    if dist < diameter:
        return "touch"
    return None


def end_setup(join, joined_kind):
    """(type at this end position, skip the end pile?) for a join result.

    Free ends are HARD. A 'same' join keeps the existing pile's type at the end position
    (and places no pile there). A 'touch' join places the other type.
    """
    if join == "same":
        return joined_kind, True
    if join == "touch":
        return other(joined_kind), False
    return "HARD", False


# ---------------------------------------------------------------- pile families (any family, set up once)
# Parameter names that give a pile family's size, length (toe) and height above its level (cut-off).
DIAMETER_NAMES = ("diameter", "pile diameter", "pile dia", "dia", "d")
RADIUS_NAMES = ("radius", "pile radius", "r")
WIDTH_NAMES = ("width", "pile width", "breadth", "pile breadth")   # lower-priority fallback
LENGTH_NAMES = ("depth", "length", "pile length", "pile depth")
OFFSET_NAMES = ("height offset from level", "offset from host", "offset", "base offset")
NOT_PILE_SIZE = ("bar", "rebar", "reinf", "link", "stirrup", "cage", "casing", "liner", "spiral", "cover")
PILE_ROLES = ("diameter", "length", "offset")


def _is_size_word(name):
    return not any(w.startswith(x) for w in re.findall(r"[a-z]+", name.lower()) for x in NOT_PILE_SIZE)


def detect_pile_params(params):
    """Which parameters give a pile family's diameter, length (moves the toe) and height above its level
    (moves the cut-off).

    params: [(name, is_length, read_only, value, where)], where = 'instance' or 'type'.
    Returns {'diameter': (name, factor), 'length': name, 'offset': name} with the roles that were found;
    factor = 1 for a diameter, 2 for a radius. Length and offset must be writable instance parameters.
    Exact names win over names that only contain the word; instance parameters over type parameters.
    """
    lengths = sorted([p for p in params if p[1]], key=lambda p: p[4] != "instance")
    found = {}
    size = [p for p in lengths if p[3] and p[3] > 0 and _is_size_word(p[0])]
    tiers = (
        (lambda l: l in DIAMETER_NAMES,                                         1),
        (lambda l: l in RADIUS_NAMES,                                           2),
        (lambda l: "diam" in l or "dia" in re.findall(r"[a-z]+", l),           1),
        (lambda l: "radius" in l,                                               2),
        (lambda l: l in WIDTH_NAMES,                                            1),  # width / breadth fallback
        (lambda l: ("width" in l or "breadth" in l) and "wall" not in l,       1),
    )
    for test, factor in tiers:
        hit = [p for p in size if test(p[0].strip().lower())]
        if hit:
            found["diameter"] = (hit[0][0], factor)
            break
    free = [p for p in lengths if p[4] == "instance" and not p[2]]
    for role, names, word in (("offset", OFFSET_NAMES, "offset"), ("length", LENGTH_NAMES, None)):
        taken = [found.get("offset")]
        cands = [p for p in free if p[0] not in taken]
        hit = [p for p in cands if p[0].strip().lower() in names]
        if not hit and word:
            hit = [p for p in cands if word in p[0].lower()]
        if not hit and role == "length":
            hit = [p for p in cands if ("length" in p[0].lower() or "depth" in p[0].lower())
                   and "offset" not in p[0].lower()]
        if hit:
            found[role] = hit[0][0]
    return found


def pile_spec_from(found):
    """A complete pile family set-up {'diameter', 'factor', 'length', 'offset'} from detect_pile_params, or None."""
    if not all(r in found for r in PILE_ROLES):
        return None
    return {"diameter": found["diameter"][0], "factor": found["diameter"][1],
            "length": found["length"], "offset": found["offset"]}


def looks_like_pile(family_name, found):
    """A family worth offering in the pile list: 'pile' in its name, or it has a diameter / radius."""
    return "pile" in (family_name or "").lower() or "diameter" in found


def name_size_mm(type_name):
    """The size a type name says ('1300mm Bored Pile' -> 1300.0), or None when the name has no '<n> mm'."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*mm", type_name or "", re.IGNORECASE)
    return float(m.group(1)) if m else None


def size_name_mismatch(kind, type_name, d_mm, tol=1.0):
    """Akash's rule (5 Oct): a pile type's name and its size value must be the same. Message, or None if they are
    (or the name has no size, or the size was not read)."""
    said = name_size_mm(type_name)
    if said is None or d_mm is None or abs(said - d_mm) <= tol:
        return None
    return ("{} type '{}': its size value is {:.0f} mm, but its name says {:.0f} mm. Make them the same: select a "
            "pile of this type > Edit Type > set the size to {:.0f} (or rename the type).".format(
                kind, type_name, d_mm, said, said))


# ---------------------------------------------------------------- layout-plan pile numbers (Number button)
def label_name(family, type_name, kind=""):
    """Tag type as shown in the Number dropdown: 'Family : Type', plus '  (kind)' for tags that are not
    Structural Foundation tags, e.g. 'ICSPL_Pile_Mark_Tag : Standard  (Generic Model Tag)'."""
    name = "{} : {}".format(family, type_name)
    return "{}  ({})".format(name, kind) if kind else name


def pick_text_param(names):
    """Which text parameter of a Generic Annotation holds the pile number: 'Mark' first, then a name with
    mark / number / no in it, then text / label / tag, else the first one. None if there are none."""
    low = [(n, n.strip().lower()) for n in names]
    words = [re.findall(r"[a-z]+", l) for n, l in low]
    tests = (lambda l, w: l == "mark",
             lambda l, w: "mark" in l,
             lambda l, w: "number" in l or "num" in w or "no" in w,
             lambda l, w: "text" in l or "label" in l or "tag" in l)
    for test in tests:
        for (n, l), w in zip(low, words):
            if test(l, w):
                return n
    return names[0] if names else None


def natural_key(text):
    """Sort 'SBP2' before 'SBP10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text or "")]


def default_mark_parts(mark):
    """'SBP1-H014' -> ('SBP1', 'HARD', 14), the mark SBP Wall gives. None for any other mark."""
    m = re.match(r"^(.+)-([HS])(\d+)$", (mark or "").strip(), re.I)
    if not m:
        return None
    return m.group(1), "HARD" if m.group(2).upper() == "H" else "SOFT", int(m.group(3))


def is_default_mark(mark, wall):
    """True for SBP Wall's own marks of this wall (SBP1-H001), False for layout numbers like SP12."""
    parts = default_mark_parts(mark)
    return parts is not None and parts[0] == wall


def mark_number(mark, prefix):
    """12 for 'SP12' with prefix 'SP'. None when the mark is not the prefix + a whole number."""
    mark = (mark or "").strip()
    if not prefix or not mark.startswith(prefix):
        return None
    rest = mark[len(prefix):]
    return int(rest) if rest.isdigit() else None


def max_number(marks, prefix):
    """Highest number used with this prefix (0 = none yet)."""
    nums = [n for n in (mark_number(m, prefix) for m in marks) if n is not None]
    return max(nums) if nums else 0


def check_prefixes(soft, hard):
    """Problems with the two prefixes (empty list = OK)."""
    errs = []
    if not soft or not hard:
        errs.append("Both prefixes are needed.")
    elif soft == hard:
        errs.append("SOFT and HARD need different prefixes.")
    for p in (soft, hard):
        if p and p[-1].isdigit():
            errs.append("'{0}' ends with a digit, so its numbers would run into it (use e.g. '{0}-').".format(p))
    return errs


def number_plan(walls, soft, hard, last):
    """Marks for the piles of each wall, in draw order.

    walls: [(name, level, [kind, ...] in draw order)] in the order they are numbered.
    last:  {level: (last SOFT number, last HARD number)} to continue from; (0, 0) = start at 1.
    SOFT and HARD are counted separately and run on across the walls of the same level.
    Returns [(name, level, marks, ranges)], ranges = {"SOFT": (first, last) or None, "HARD": ...}.
    """
    nxt = dict((lv, list(v)) for lv, v in last.items())
    res = []
    for name, level, kinds in walls:
        cnt = nxt.setdefault(level, [0, 0])
        marks, rng = [], {"SOFT": None, "HARD": None}
        for k in kinds:
            i = 0 if k == "SOFT" else 1
            cnt[i] += 1
            marks.append("{}{}".format(soft if i == 0 else hard, cnt[i]))
            r = rng[k]
            rng[k] = (cnt[i], cnt[i]) if r is None else (r[0], cnt[i])
        res.append((name, level, marks, rng))
    return res


def range_text(prefix, rng):
    """'SP8 to SP28' for (8, 28)."""
    if rng is None:
        return "none"
    a, b = rng
    return "{}{}".format(prefix, a) if a == b else "{0}{1} to {0}{2}".format(prefix, a, b)


def continue_text(prefix, last):
    """The live line in the Number dialog."""
    if last:
        return "continuing from {0}{1}, next will be {0}{2}".format(prefix, last, last + 1)
    return "no {0} numbers yet, next will be {0}1".format(prefix)


def legacy_order(items):
    """Draw order of piles made before 28 Sep (no saved order), from their marks WALL-H001 / WALL-S001.

    items: [(key, kind, n, x, y)], n = the number in the mark (None if it has none).
    HARD and SOFT alternate along the wall, so the order is H1 S1 H2 S2 ... or S1 H1 S2 H2 ...:
    the type with more piles comes first; with equal counts the positions decide (in H1 S1 H2,
    S1 sits next to H2). Returns the keys in draw order, or None when a number is missing.
    """
    if any(it[2] is None for it in items):
        return None
    hs = sorted([it for it in items if it[1] == "HARD"], key=lambda it: it[2])
    ss = sorted([it for it in items if it[1] == "SOFT"], key=lambda it: it[2])

    def dist(a, b):
        return math.hypot(a[3] - b[3], a[4] - b[4])

    if len(hs) != len(ss):
        hard_first = len(hs) > len(ss)
    elif len(hs) >= 2:
        hard_first = dist(ss[0], hs[1]) <= dist(hs[0], ss[1])
    else:
        hard_first = True
    a, b = (hs, ss) if hard_first else (ss, hs)
    out = []
    for i in range(max(len(a), len(b))):
        out += [x[0] for x in (a[i:i + 1] + b[i:i + 1])]
    return out

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

VERSION = 1
NUM_KEYS = ("spacing", "gap", "cutoff", "toe_hard", "toe_soft")
REBUILD_KEYS = ("type", "level", "spacing", "gap")
LEVEL_KEYS = ("cutoff", "toe_hard", "toe_soft")
MIN_GAP_MM = 150.0


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


def check_settings(s, min_gap=MIN_GAP_MM):
    """List of problems with a settings dict (empty list = OK)."""
    errs = []
    if s["spacing"] <= 0:
        errs.append("c/c spacing must be greater than 0.")
    if s["gap"] < min_gap:
        errs.append("Gap must be at least {:.0f} mm (you entered {:.0f}).".format(min_gap, s["gap"]))
    if max(s["toe_hard"], s["toe_soft"]) >= s["cutoff"]:
        errs.append("Toe Level must be below the Cut-off Level.")
    return errs


def fmt_num(v):
    """900.0 -> '900', -150.0 -> '-150', 868.25 -> '868.25'."""
    return "{:g}".format(float(v))


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


# ---------------------------------------------------------------- layout-plan pile numbers (Number button)
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

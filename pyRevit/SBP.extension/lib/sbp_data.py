# -*- coding: utf-8 -*-
"""Pure-Python helpers for SBP walls (no Revit API here, so it can be tested outside Revit).

- the settings each wall remembers (saved as JSON inside the Revit model)
- what changed in SBP Edit, and whether the wall must be rebuilt
- where typed pile data goes after a rebuild (nearest pile of the same type)
- how a wall end joins another wall (which pile type comes first)
All lengths are in mm unless a function says otherwise.
"""
import json
import math

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
def match_nearest(old, new):
    """Where typed data goes after a rebuild.

    old/new: lists of (x, y, kind). Each old pile is matched to the nearest new pile of
    the same type. If two old piles pick the same new pile, the closer one wins.
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
        if pick is not None:
            best[i] = (pick, dist)
    owner = {}
    for i, (j, d) in best.items():
        if j not in owner or d < best[owner[j]][1]:
            owner[j] = i
    matches = dict((i, best[i]) for i in owner.values())
    lost = sorted(i for i in range(len(old)) if i not in matches)
    return matches, lost


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

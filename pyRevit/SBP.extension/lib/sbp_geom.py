# -*- coding: utf-8 -*-
"""Pure-Python geometry for the SBP Wall tool (no Revit API here, so it can be tested outside Revit).

All values are plain floats in one consistent length unit. Points are (x, y) tuples.
"""
import math


# ---------------------------------------------------------------- offset path
def _signed_normal(t, side):
    """Left normal of unit tangent t, flipped to the chosen side (+1 left / -1 right)."""
    return (-t[1] * side, t[0] * side)


def _fan(p, t1, t2, side, dist, max_step_rad=math.radians(5.0)):
    """Points around corner p, rotating the offset normal from tangent t1 to tangent t2."""
    n1 = _signed_normal(t1, side)
    n2 = _signed_normal(t2, side)
    a1 = math.atan2(n1[1], n1[0])
    a2 = math.atan2(n2[1], n2[0])
    delta = a2 - a1
    while delta > math.pi:
        delta -= 2 * math.pi
    while delta <= -math.pi:
        delta += 2 * math.pi
    steps = max(1, int(math.ceil(abs(delta) / max_step_rad)))
    pts = []
    for i in range(steps + 1):
        a = a1 + delta * i / float(steps)
        pts.append((p[0] + dist * math.cos(a), p[1] + dist * math.sin(a)))
    return pts


def pick_side(samples, pick):
    """+1 if pick point is on the left of the path, -1 if on the right.

    samples: list of (points, tangents) per curve.
    """
    best = None
    for pts, tans in samples:
        for p, t in zip(pts, tans):
            dd = (pick[0] - p[0]) ** 2 + (pick[1] - p[1]) ** 2
            if best is None or dd < best[0]:
                best = (dd, p, t)
    _, p, t = best
    cross = (pick[0] - p[0]) * (-t[1]) + (pick[1] - p[1]) * t[0]
    return 1.0 if cross > 0 else -1.0


def offset_path(samples, closed, side, dist, sharp_deg=0.0):
    """Offset a chain of sampled curves by dist to one side.

    Convex corners get a rounded fan of points; concave corners create small
    loops which remove_loops() cuts out afterwards.
    sharp_deg > 0: convex joints that turn up to sharp_deg are sharp instead (the two
    offset lines meet, like AutoCAD OFFSET).
    """
    def joint(p, t1, t2):
        b = turn_deg(t1, t2)
        if sharp_deg > 0 and b * side < 0 and abs(b) <= sharp_deg:
            return [_miter(p, t1, t2, side, dist)], True
        return _fan(p, t1, t2, side, dist), False

    out = []
    prev_t = None
    for pts, tans in samples:
        for k, (p, t) in enumerate(zip(pts, tans)):
            if k == 0 and prev_t is not None:
                out.extend(joint(p, prev_t, t)[0])
                continue
            n = _signed_normal(t, side)
            out.append((p[0] + n[0] * dist, p[1] + n[1] * dist))
        prev_t = tans[-1]
    if closed:
        first_p = samples[0][0][0]
        first_t = samples[0][1][0]
        pts, sharp = joint(first_p, prev_t, first_t)
        out.extend(pts if sharp else pts[:-1])
    return dedupe(out, dist * 1e-6)


def dedupe(pts, eps):
    res = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - res[-1][0]) > eps or abs(p[1] - res[-1][1]) > eps:
            res.append(p)
    return res


def _intersect(a, b, c, d):
    """Intersection point of segments ab and cd (end points included), or None.

    End points must count: when two offset lines cross exactly on a sample point
    (e.g. gap 200 -> offset 800, a whole number of sample steps), a strict test
    misses the crossing and the inside-corner loop is left in the path.
    """
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-15:
        return None
    qp = (c[0] - a[0], c[1] - a[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / den
    u = (qp[0] * r[1] - qp[1] * r[0]) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (a[0] + t * r[0], a[1] + t * r[1])
    return None


def remove_loops(pts, window):
    """Cut out self-intersection loops (inside corners / tight inner curves)."""
    res = list(pts)
    i = 0
    while i < len(res) - 3:
        a, b = res[i], res[i + 1]
        jmax = min(len(res) - 2, i + window)
        hit = None
        for j in range(jmax, i + 1, -1):  # farthest first -> removes the whole loop
            x = _intersect(a, b, res[j], res[j + 1])
            if x is not None:
                hit = (j, x)
                break
        if hit:
            j, x = hit
            res = res[:i + 1] + [x] + res[j + 1:]
        i += 1
    return dedupe(res, 1e-9)


# ---------------------------------------------------------------- reference planes -> one chain
def _line_cross(a, b, c, d):
    """Crossing point of the (endless) lines through ab and cd, or None if parallel."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9 * math.hypot(*r) * math.hypot(*s):
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    return (a[0] + t * r[0], a[1] + t * r[1])


def _near_segment(p, seg, reach):
    """p (on the segment's line) lies on the segment or within `reach` beyond its ends."""
    (a, b) = seg
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / (L * L)
    return -reach / L <= t <= 1 + reach / L


def chain_from_lines(segs, reach):
    """Order straight segments (e.g. reference planes seen in plan) into one wall line.

    Two segments are neighbours when their lines cross on both of them (or within `reach`
    beyond their ends). Ends of an open chain keep the far end of the first/last segment;
    the corners are the crossing points. Every segment crossing two others -> closed loop.
    segs: [((x0, y0), (x1, y1))]. Returns (points, closed). Raises ValueError for the user.
    """
    n = len(segs)
    for a, b in segs:
        if math.hypot(b[0] - a[0], b[1] - a[1]) <= 1e-9:
            raise ValueError("A reference plane has no length in plan (is it horizontal?).")
    if n == 1:
        return [segs[0][0], segs[0][1]], False
    cross = {}
    for i in range(n):
        for j in range(i + 1, n):
            p = _line_cross(segs[i][0], segs[i][1], segs[j][0], segs[j][1])
            if p is not None and _near_segment(p, segs[i], reach) and _near_segment(p, segs[j], reach):
                cross[(i, j)] = cross[(j, i)] = p
    nb = dict((i, [j for j in range(n) if (i, j) in cross]) for i in range(n))
    if any(len(v) > 2 for v in nb.values()):
        raise ValueError("A reference plane crosses more than two of the others. Select only the planes of one wall.")
    if any(len(v) == 0 for v in nb.values()):
        raise ValueError("A reference plane does not meet any of the others. Select planes that cross at the corners.")
    ends = [i for i in range(n) if len(nb[i]) == 1]
    if len(ends) not in (0, 2):
        raise ValueError("The reference planes do not form one chain.")
    closed = not ends
    order, prev, cur = [ends[0] if ends else 0], None, ends[0] if ends else 0
    while len(order) < n:
        nxt = [j for j in nb[cur] if j != prev and j not in order]
        if not nxt:
            break
        prev, cur = cur, nxt[0]
        order.append(cur)
    if len(order) != n:
        raise ValueError("The reference planes do not form one chain.")
    corners = [cross[(order[k], order[k + 1])] for k in range(n - 1)]
    if closed:
        return [cross[(order[-1], order[0])]] + corners, True

    def far_end(seg, p):
        a, b = seg
        return a if math.hypot(a[0] - p[0], a[1] - p[1]) > math.hypot(b[0] - p[0], b[1] - p[1]) else b
    return [far_end(segs[order[0]], corners[0])] + corners + [far_end(segs[order[-1]], corners[-1])], False


# ---------------------------------------------------------------- division
def path_length(pts, closed):
    p = pts + [pts[0]] if closed else pts
    return sum(math.hypot(p[k][0] - p[k - 1][0], p[k][1] - p[k - 1][1]) for k in range(1, len(p)))


def divide(pts, closed, spacing, odd=False):
    """Pile centres at equal length along the path.

    Interval count is rounded UP (so real spacing <= design spacing, overlap is never
    less than design) and made EVEN, so hard/soft always alternate:
      open line  -> starts and ends with the same type (HARD by default)
      closed loop-> hard/soft alternate all the way round
    odd=True (open lines only) makes the count ODD instead, so the two ends get
    different types (used when an end joins another wall).
    Returns (centres, interval_length, total_length).
    """
    p = pts + [pts[0]] if closed else list(pts)
    cum = [0.0]
    for k in range(1, len(p)):
        cum.append(cum[-1] + math.hypot(p[k][0] - p[k - 1][0], p[k][1] - p[k - 1][1]))
    total = cum[-1]
    n = max(1, int(math.ceil(total / spacing - 1e-9)))
    want = 1 if (odd and not closed) else 0
    if n % 2 != want:
        n += 1
    step = total / n
    count = n if closed else n + 1
    centres = []
    seg = 1
    for k in range(count):
        target = min(k * step, total)
        while seg < len(cum) - 1 and cum[seg] < target:
            seg += 1
        seg_len = cum[seg] - cum[seg - 1]
        f = 0.0 if seg_len <= 0 else (target - cum[seg - 1]) / seg_len
        a, b = p[seg - 1], p[seg]
        centres.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return centres, step, total


def max_chord(centres, closed):
    pairs = list(zip(centres[:-1], centres[1:]))
    if closed and len(centres) > 1:
        pairs.append((centres[-1], centres[0]))
    return max(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairs)


def hard_soft(count, start="HARD"):
    """Index 0,2,4.. = start type, 1,3,5.. = the other type."""
    other = "SOFT" if start == "HARD" else "HARD"
    return [start if i % 2 == 0 else other for i in range(count)]


def layout_ends(pts, closed, spacing, start_type="HARD", end_type="HARD",
                skip_start=False, skip_end=False):
    """Pile centres and types with the type at each end of an open wall fixed.

    start_type / end_type: type at the first / last pile position.
    skip_start / skip_end: that position is already taken by a pile of another
    wall (the wall continues from it), so no new pile is placed there.
    Closed loops ignore the end settings (even count, HARD at the seam).
    Returns (centres, kinds, interval_length, total_length).
    """
    if closed:
        centres, step, total = divide(pts, True, spacing)
        return centres, hard_soft(len(centres)), step, total
    centres, step, total = divide(pts, False, spacing, odd=(start_type != end_type))
    kinds = hard_soft(len(centres), start_type)
    lo = 1 if skip_start else 0
    hi = len(centres) - 1 if skip_end else len(centres)
    return centres[lo:hi], kinds[lo:hi], step, total


# ---------------------------------------------------------------- v2 layout (30 Sep): design c/c kept, sharp corners
# Straight runs and curves keep the design c/c HARD to SOFT (s = HARD to HARD / 2, a straight distance between
# centres). What does not fit is taken by reducing a few gaps: at the far end of a wall without corners, next to the
# corners otherwise, never below the web limit. Corners (a bend of more than CORNER_MIN_DEG where two drawn curves
# meet) are sharp; the pile on the corner is SOFT; its two HARD piles are at c = max(s, (Dh + web)/(2 cos(bend/2)))
# from the corner so the SOFT web there stays >= web; option B then moves the corner SOFT inward along the bisector
# until it is s from both HARD piles again (full design overlap), never closer to the drawn line than the gap.
CORNER_MIN_DEG = 5.0       # a joint of the drawn chain that bends more than this is a corner
CORNER_MAX_DEG = 150.0     # sharper turns stay rounded and get no corner rule (the report lists them)


def _unit(v):
    L = math.hypot(v[0], v[1])
    return (v[0] / L, v[1] / L) if L > 0 else (0.0, 0.0)


def turn_deg(t1, t2):
    """Signed turn from direction t1 to direction t2, in degrees (+ = to the left)."""
    return math.degrees(math.atan2(t1[0] * t2[1] - t1[1] * t2[0], t1[0] * t2[0] + t1[1] * t2[1]))


def _miter(p, t1, t2, side, dist):
    """Where the two offset lines of a joint meet (a sharp corner)."""
    n1, n2 = _signed_normal(t1, side), _signed_normal(t2, side)
    k = 1.0 + n1[0] * n2[0] + n1[1] * n2[1]
    return (p[0] + dist * (n1[0] + n2[0]) / k, p[1] + dist * (n1[1] + n2[1]) / k)


def chain_joints(samples, closed):
    """[(point, direction in, direction out)] where two curves of the drawn chain meet, in chain order
    (closed: the last one is where the last curve meets the first)."""
    res = [(samples[k][0][0], samples[k - 1][1][-1], samples[k][1][0]) for k in range(1, len(samples))]
    if closed:
        res.append((samples[0][0][0], samples[-1][1][-1], samples[0][1][0]))
    return res


def find_corners(path, joints, side, dist, min_deg=CORNER_MIN_DEG, max_deg=CORNER_MAX_DEG):
    """Corners of the wall centre line `path` (offset with sharp_deg=max_deg, loops removed).

    Returns (corners, skipped): corners = [(index of the corner point in path, bend in degrees, inward unit
    vector)] in path order; skipped = [(joint point, bend, why)] for turns that get no corner rule.
    """
    corners, skipped = [], []
    for p, t1, t2 in joints:
        b = abs(turn_deg(t1, t2))
        if b <= min_deg:
            continue
        if b > max_deg:
            skipped.append((p, b, "sharper than {:.0f} deg: kept rounded".format(max_deg)))
            continue
        q = _miter(p, t1, t2, side, dist)
        i = min(range(len(path)), key=lambda k: (path[k][0] - q[0]) ** 2 + (path[k][1] - q[1]) ** 2)
        if math.hypot(path[i][0] - q[0], path[i][1] - q[1]) > 0.5 * dist:
            skipped.append((p, b, "legs shorter than the offset: no corner point"))
            continue
        corners.append((i, b, _unit((t2[0] - t1[0], t2[1] - t1[1]))))
    corners.sort(key=lambda c: c[0])
    return corners, skipped


def seg_dist(p, a, b):
    """Distance from point p to segment ab."""
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2))
    return math.hypot(p[0] - a[0] - t * ax, p[1] - a[1] - t * ay)


def line_dist(p, segs, reach=None):
    """Distance from p to the nearest of segments [(a, b)]. With `reach`, segments further than that
    (by their bounding box) are skipped, and reach is returned when none is closer."""
    best = reach
    for a, b in segs:
        if reach is not None and (p[0] < min(a[0], b[0]) - best or p[0] > max(a[0], b[0]) + best or
                                  p[1] < min(a[1], b[1]) - best or p[1] > max(a[1], b[1]) + best):
            continue
        d = seg_dist(p, a, b)
        if best is None or d < best:
            best = d
    return best


def _exit(p0, a, b, r):
    """Fraction t on segment ab where the distance from p0 grows to r (a is closer than r, b is not)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - p0[0], a[1] - p0[1]
    qa = dx * dx + dy * dy
    if qa <= 0:
        return 0.0
    qb = 2.0 * (fx * dx + fy * dy)
    qc = fx * fx + fy * fy - r * r
    disc = max(qb * qb - 4.0 * qa * qc, 0.0)
    return min(max((-qb + math.sqrt(disc)) / (2.0 * qa), 0.0), 1.0)


class _Walk(object):
    """A polyline measured along its length (u), with points found by straight distance (chord)."""

    def __init__(self, pts):
        self.p = list(pts)
        self.cum = [0.0]
        for a, b in zip(self.p[:-1], self.p[1:]):
            self.cum.append(self.cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        self.total = self.cum[-1]

    def _seg(self, u):
        lo, hi = 0, len(self.cum) - 2
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.cum[mid] <= u:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def at(self, u):
        u = min(max(u, 0.0), self.total)
        i = self._seg(u)
        L = self.cum[i + 1] - self.cum[i]
        f = (u - self.cum[i]) / L if L > 0 else 0.0
        a, b = self.p[i], self.p[i + 1]
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)

    def chord(self, u0, dist, forward=True, limit=None):
        """The first length after u0 (before it: forward=False) whose point is `dist` in a straight line from
        the point at u0. None when the path, or `limit`, ends first."""
        p0 = self.at(u0)
        i = self._seg(u0)
        for k in (range(i, len(self.p) - 1) if forward else range(i, -1, -1)):
            if forward:
                ua, ub, B = max(u0, self.cum[k]), self.cum[k + 1], self.p[k + 1]
            else:
                ua, ub, B = min(u0, self.cum[k + 1]), self.cum[k], self.p[k]
            if math.hypot(B[0] - p0[0], B[1] - p0[1]) < dist:
                continue
            u = ua + (ub - ua) * _exit(p0, self.at(ua), B, dist)
            if limit is not None and (u > limit if forward else u < limit):
                return None
            return u
        return None


def _run(w, ua, ub, same, s, smin, smin_abs, reduce_at, fit):
    """Piles between two fixed piles at lengths ua < ub along the path (same: both the same type, so the number of
    gaps is even). Every gap is s (straight distance between centres), except a few next to `reduce_at` ('start',
    'end' or 'both') that are reduced equally so the run fits, never below smin.
    Returns (lengths strictly between, reduced gaps, ok), or None when not even smin_abs fits.
    ok = False: smin cannot be kept, so every gap of the run is reduced equally (low web, reported)."""
    L = ub - ua
    if L <= fit:
        return None
    want = 0 if same else 1
    us = [ua]
    while True:
        u = w.chord(us[-1], s, True, ub + fit)
        if u is None:
            break
        us.append(u)
    K = len(us) - 1
    if K > 0 and ub - us[-1] <= fit and K % 2 == want:
        return us[1:-1], 0, True
    n = K + 1 if (K + 1) % 2 == want else K + 2
    avg = (us[-1] - ua) / K if K else s
    extra = max(n * avg - L, 0.0)
    j = int(math.ceil(extra / (avg - smin) - 1e-9)) if avg - smin > 1e-9 * s else n + 1
    j = max(j, 1)
    if j > n:
        g = L / n
        if g < smin_abs - fit:
            return None
        return [ua + g * k for k in range(1, n)], n, False
    nd = min(n - j, K)
    j = n - nd
    if reduce_at == "start":
        vs = [ub]
        for _ in range(nd):
            v = w.chord(vs[-1], s, False, ua - fit)
            if v is None:
                break
            vs.append(v)
        if len(vs) == nd + 1:
            g = (vs[-1] - ua) / j
            return [ua + g * k for k in range(1, j)] + list(reversed(vs[1:])), j, True
    elif reduce_at == "both" and j > 1:
        jf = j // 2
        g = avg - extra / j
        mid = [ua + g * k for k in range(1, jf + 1)]
        for _ in range(nd):
            u = w.chord(mid[-1], s, True, ub + fit)
            if u is None:
                break
            mid.append(u)
        if len(mid) == jf + nd:
            g = (ub - mid[-1]) / (j - jf)
            return mid + [mid[-1] + g * k for k in range(1, j - jf)], j, True
    g = (ub - us[nd]) / j                     # 'end' (and the fallback): design gaps first, the reduced ones last
    return us[1:nd + 1] + [us[nd] + g * k for k in range(1, j)], j, True


def corner_c(bend, s, dh, web):
    """(preferred, smallest) distance from a corner to its two HARD piles: the smallest keeps the SOFT web between
    those HARD piles >= web; the preferred one is never less than the design c/c s."""
    cmin = (dh + web) / (2.0 * math.cos(math.radians(bend) / 2.0))
    return max(s, cmin), cmin


def _leg(w, a, b, s, smin, smin_abs, fit):
    """Piles of one leg, from anchor a to anchor b (anchors: dict(end=True, u, kind) for a wall end, or
    dict(end=False, u, cpref, cmin) for a corner). Returns dict(us=[lengths from the a-side pile (the end pile, or
    the corner's HARD) to the b-side pile], kind=type of the first, reduced, ok, how), or None if nothing fits."""
    ka = a["kind"] if a["end"] else "HARD"
    kb = b["kind"] if b["end"] else "HARD"
    reduce_at = {(True, True): "end", (True, False): "end", (False, True): "start"}.get((a["end"], b["end"]), "both")

    def span(ca, cb):
        ua = a["u"] if a["end"] else w.chord(a["u"], ca, True)
        ub = b["u"] if b["end"] else w.chord(b["u"], cb, False)
        return ua, ub

    tries = [("design", a.get("cpref"), b.get("cpref"))]
    if (not a["end"] and a["cmin"] < a["cpref"] - fit) or (not b["end"] and b["cmin"] < b["cpref"] - fit):
        tries.append(("corner HARD closer", a.get("cmin"), b.get("cmin")))
    low = None
    for how, ca, cb in tries:
        ua, ub = span(ca, cb)
        if ua is None or ub is None:
            continue
        r = _run(w, ua, ub, ka == kb, s, smin, smin_abs, reduce_at, fit)
        if r is None:
            continue
        res = {"us": [ua] + r[0] + [ub], "kind": ka, "reduced": r[1], "ok": r[2], "how": how}
        if r[2]:
            return res
        low = low or dict(res, how="low web")
    if low is not None:
        return low
    # one HARD pile serves both sides (short leg): between two corners, or a HARD wall end next to a corner
    if not a["end"] and not b["end"]:
        lo, hi = w.chord(a["u"], a["cmin"], True), w.chord(b["u"], b["cmin"], False)
        if lo is None or hi is None or lo > hi + fit:
            return None
        pa, pb = w.chord(a["u"], a["cpref"], True), w.chord(b["u"], b["cpref"], False)
        um = (pa + pb) / 2.0 if pa is not None and pb is not None else (lo + hi) / 2.0
        return {"us": [min(max(um, lo), hi)], "kind": "HARD", "reduced": 0, "ok": True, "how": "one HARD (short leg)"}
    end, corner, fwd = (a, b, False) if a["end"] else (b, a, True)
    if end["kind"] != "HARD":
        return None
    lim = w.chord(corner["u"], corner["cmin"], fwd)
    if lim is None or (end["u"] > lim + fit if not fwd else end["u"] < lim - fit):
        return None
    return {"us": [end["u"]], "kind": "HARD", "reduced": 0, "ok": True, "how": "end pile is the corner HARD"}


def _move_soft(p, inward, h1, h2, s, line, clear_r, fit):
    """Option B: how far the corner SOFT moves from the corner point p along `inward` so that it is no further than
    s from both HARD piles (the design overlap comes back). Its centre stays at least clear_r from the drawn line.
    Returns (distance, limited by the line)."""
    def at(t):
        return (p[0] + inward[0] * t, p[1] + inward[1] * t)

    def far(t):
        q = at(t)
        return max(math.hypot(q[0] - h1[0], q[1] - h1[1]), math.hypot(q[0] - h2[0], q[1] - h2[1]))

    if far(0.0) <= s + fit:
        return 0.0, False
    lo, hi = 0.0, far(0.0)
    for _ in range(100):                      # far() is convex: its lowest point first
        m1, m2 = lo + (hi - lo) / 3.0, hi - (hi - lo) / 3.0
        if far(m1) <= far(m2):
            hi = m2
        else:
            lo = m1
    t = (lo + hi) / 2.0
    if far(t) <= s:
        lo, hi = 0.0, t
        for _ in range(100):
            m = (lo + hi) / 2.0
            if far(m) > s:
                lo = m
            else:
                hi = m
        t = hi
    if line and clear_r is not None:
        def ok(tt):
            return line_dist(at(tt), line, clear_r + 1.0) >= clear_r - fit
        if not ok(t):
            lo, hi = 0.0, t
            for _ in range(100):
                m = (lo + hi) / 2.0
                if ok(m):
                    lo = m
                else:
                    hi = m
            return lo, True
    return t, False


def _try_layout(path, closed, corners, s, dh, ds, web, start_kind, end_kind, line, clear, fit):
    """One layout with these corners. Returns ('ok', centres, kinds, info) or ('drop', index into corners)."""
    smin = max((dh + web) / 2.0, ds / 2.0)
    smin_abs = max(dh, ds) / 2.0
    if closed:
        i0 = corners[0][0]
        pts = path[i0:] + path[:i0] + [path[i0]]
        cs = [((i - i0) % len(path), b, inw) for i, b, inw in corners]
    else:
        pts, cs = list(path), list(corners)
    w = _Walk(pts)
    anchors = []
    for i, b, inw in cs:
        cpref, cmin = corner_c(b, s, dh, web)
        anchors.append({"end": False, "u": w.cum[i], "cpref": cpref, "cmin": cmin, "bend": b, "in": inw})
    if closed:
        anchors.append(dict(anchors[0], u=w.total))
    else:
        anchors = [{"end": True, "u": 0.0, "kind": start_kind}] + anchors + \
                  [{"end": True, "u": w.total, "kind": end_kind}]
    legs = []
    for k in range(len(anchors) - 1):
        leg = _leg(w, anchors[k], anchors[k + 1], s, smin, smin_abs, fit)
        if leg is None:
            both = [(anchors[j]["bend"], (j - (0 if closed else 1)) % len(cs)) for j in (k, k + 1)
                    if not anchors[j]["end"]]
            return ("drop", min(both)[1]) if both else ("drop", None)
        legs.append(leg)
    # ---- piles in wall order: [corner SOFT] + leg piles, alternating from each leg's first pile
    other = {"HARD": "SOFT", "SOFT": "HARD"}
    piles = []                                # (point, kind, anchor of the corner or None)
    for k, leg in enumerate(legs):
        if not anchors[k]["end"]:
            piles.append((w.at(anchors[k]["u"]), "SOFT", k))
        kind = leg["kind"]
        for u in leg["us"]:
            piles.append((w.at(u), kind, None))
            kind = other[kind]
    # ---- option B at every corner: the corner SOFT moves inward until it is s from both HARD piles
    centres = [p for p, kd, k in piles]
    info_corners = []
    n = len(piles)
    for idx, (p, kd, k) in enumerate(piles):
        if k is None:
            continue
        a = anchors[k]
        h1, h2 = centres[idx - 1], centres[(idx + 1) % n]
        t, limited = _move_soft(p, a["in"], h1, h2, s, line, None if clear is None else clear + ds / 2.0, fit)
        q = (p[0] + a["in"][0] * t, p[1] + a["in"][1] * t)
        centres[idx] = q
        info_corners.append({
            "index": idx, "point": p, "bend": a["bend"],
            "c": (math.hypot(h1[0] - p[0], h1[1] - p[1]), math.hypot(h2[0] - p[0], h2[1] - p[1])),
            "move": t, "limited": limited,
            "sh": max(math.hypot(q[0] - h1[0], q[1] - h1[1]), math.hypot(q[0] - h2[0], q[1] - h2[1])),
            "how": [legs[j]["how"] for j in (k - 1, k) if legs[j]["how"] != "design"],
        })
    info = {"corners": info_corners, "reduced": sum(leg["reduced"] for leg in legs),
            "low_web_runs": sum(1 for leg in legs if not leg["ok"]),
            "short_legs": [leg["how"] for leg in legs if leg["how"] not in ("design", "low web")],
            "equal": None}
    return "ok", centres, [kd for p, kd, c in piles], info


def layout_wall(path, closed, corners, s, dh, ds, web, start_kind="HARD", end_kind="HARD", line=None, clear=None):
    """v2 pile centres and types along the wall centre line `path` (all lengths in one unit).

    corners: find_corners() result. s: design c/c HARD to SOFT (= HARD to HARD / 2). dh / ds: HARD / SOFT diameter.
    web: smallest leftover SOFT web kept at corners and in reduced gaps (min(200, design web)).
    start_kind / end_kind: the pile type at each end of an open wall (HARD at a free end).
    line: the drawn line as segments [(a, b)] and clear: the gap (pile edge to line); option B never moves a corner
    SOFT closer than that.
    A leg too short even for one HARD pile between its corners loses the corner with the smaller bend (reported).
    Returns (centres, kinds, info): info = corners [dict: index, point, bend, c (to each HARD), move, limited, sh
    (SOFT to HARD after the move), how], dropped [(point, bend)], reduced (gaps), low_web_runs, short_legs,
    equal (c/c when a closed wall without corners is divided equally, else None).
    """
    fit = s * 1e-4
    cs = sorted(corners, key=lambda c: c[0])
    dropped = []
    while cs:
        res = _try_layout(path, closed, cs, s, dh, ds, web, start_kind, end_kind, line, clear, fit)
        if res[0] == "ok":
            res[3]["dropped"] = dropped
            return res[1], res[2], res[3]
        if res[1] is None:
            break
        dropped.append((path[cs[res[1]][0]], cs[res[1]][1]))
        cs = cs[:res[1]] + cs[res[1] + 1:]
    info = {"corners": [], "dropped": dropped, "reduced": 0, "low_web_runs": 0, "short_legs": [], "equal": None}
    if closed:
        centres, step, total = divide(path, True, s)
        info["equal"] = step
        return centres, hard_soft(len(centres)), info
    w = _Walk(path)
    a = {"end": True, "u": 0.0, "kind": start_kind}
    b = {"end": True, "u": w.total, "kind": end_kind}
    leg = _leg(w, a, b, s, max((dh + web) / 2.0, ds / 2.0), max(dh, ds) / 2.0, fit)
    if leg is None:                            # shorter than two piles: equal division, the check reports it
        centres, kinds, step, total = layout_ends(path, False, s, start_kind, end_kind)
        info["equal"] = step
        return centres, kinds, info
    info.update(reduced=leg["reduced"], low_web_runs=0 if leg["ok"] else 1)
    return [w.at(u) for u in leg["us"]], hard_soft(len(leg["us"]), start_kind), info


# ---------------------------------------------------------------- v3 layout: closing zone (Akash, 6 Oct)
CLOSE_N = 3                # bays in the closing zone (the drafter's field "Closing SOFT piles (adjust)")
CLOSE_MAX = 6              # the zone may grow up to this many bays when N cannot close without a warning


def _equal_chords(w, ua, ub, m):
    """m equal straight-line gaps along the path from length ua to ub: (gap, the m - 1 lengths in between).
    Found by bisection: a gap across a corner covers more path than its own length."""
    lo, hi = 0.0, (ub - ua) / float(m)
    for _ in range(100):
        g = (lo + hi) / 2.0
        u = ua
        for _ in range(m):
            u = w.chord(u, g, True, None)
            if u is None:
                break
        if u is None or u > ub:
            hi = g
        else:
            lo = g
        if hi - lo <= 1e-12 * max(1.0, ub):
            break
    us, u = [], ua
    for _ in range(m - 1):
        u = w.chord(u, lo, True, None)
        us.append(u)
    return lo, us


def _zone_ok(centres, kinds, idxs, dh, ds, web, design_cut, tol):
    """Closing-zone check for the piles idxs (consecutive, in wall order) of a whole wall: every HARD-SOFT pair in it
    keeps at least the design cutting depth, every SOFT in it between two HARD piles keeps a web >= `web`, and no
    pile of it overlaps another pile of the same type (e.g. across a corner)."""
    rad = {"HARD": dh / 2.0, "SOFT": ds / 2.0}

    def d(i, j):
        return math.hypot(centres[i][0] - centres[j][0], centres[i][1] - centres[j][1])
    for a, b in zip(idxs[:-1], idxs[1:]):
        if (dh + ds) / 2.0 - d(a, b) < design_cut - tol:
            return False
    for a, i, b in zip(idxs[:-2], idxs[1:-1], idxs[2:]):
        if kinds[i] == "SOFT" and kinds[a] == "HARD" and kinds[b] == "HARD" and d(a, b) - dh < web - tol:
            return False
    for i in idxs:
        for q in range(len(centres)):
            if q != i and kinds[q] == kinds[i] and d(i, q) < 2 * rad[kinds[i]] - tol:
                return False
    return True


def layout_closing(path, closed, s, dh, ds, web, n_close=CLOSE_N, start_kind="HARD", end_kind="HARD",
                   n_max=CLOSE_MAX, free_end=False, tiny=0.0):
    """v3 pile centres and types (Akash, 6-7 Oct; replaces the v2 corner and leftover rules for new walls). Any
    shape: straight, chain with corners, arc, circle, spline, open or closed.

    Every gap is exactly s, the STRAIGHT distance between centres (chord), walking along the centre line from the
    start pile, through corners and curves too. Corners are never adjusted (check_wall checks them). Only the end
    of an open wall, or the seam of a loop, is adjusted, and only when needed:
    - Open wall with a free end (free_end): if the last design pile that fits is HARD, the wall stops there and the
      small leftover of the line stays (way 'short'). If it would be SOFT, the end HARD goes on the line end and the
      last bays before it are shortened.
    - Open wall joined to another wall at its end: the end pile is on the line end (its type from the join).
    - Loop: starts with a HARD pile at the start of `path` (the drafter's start point). The last bay back into that
      HARD keeps the design c/c (the end SOFT is s from the start, the HARD before it s further); the adjusted bays
      are just before that bay, so a start on a corner stays exact on both sides.
    Adjusted bays: 1 first, then n_close .. n_max (2N gaps, equal, each pile centred). A last bay within `tiny` of
    the design HARD to HARD (2s) is just spread over that bay (way 'tiny'). Otherwise rule B: shrink (one pile pair
    more) or stretch (same piles); the first N with a choice that passes is used (the one closer to s if both
    pass). Passes = cutting depth >= the design one, web >= `web`, no same-type overlap. None passes: the choice
    closest to s over all N (the check reports its warnings / errors).
    Returns (centres, kinds, info); info['close'] = dict(n, n_set, way 'exact'|'short'|'tiny'|'stretch'|'shrink'|
    'equal', gap, first (index of the zone's first pile), clean, left (line left after a 'short' end), tried
    [(n, way, gap, passes)]); info['u'] = each pile's length along the centre line.
    """
    other = {"HARD": "SOFT", "SOFT": "HARD"}
    if closed:
        start_kind = end_kind = "HARD"
    w = _Walk(list(path) + ([path[0]] if closed else []))
    fit = s * 1e-4
    tol = s * 5e-4
    want = 0 if start_kind == end_kind else 1          # parity of the gaps from the start to the zone's end
    design_cut = (dh + ds) / 2.0 - s
    if closed:
        e1 = w.chord(w.total, s, False, None)          # the end SOFT, s before the start HARD
        e2 = w.chord(e1, s, False, None) if e1 is not None else None
        if e2 is None or e2 <= fit:                    # a loop too small for that: close on the start itself
            zone_end, tail = w.total, []
        else:
            zone_end, tail = e2, [e2, e1]
    else:
        zone_end, tail = w.total, [w.total]
    us = [0.0]
    while True:
        u = w.chord(us[-1], s, True, zone_end + fit)
        if u is None:
            break
        us.append(u)
    info = {"corners": [], "dropped": [], "reduced": 0, "low_web_runs": 0, "short_legs": [], "equal": None}

    def kind_at(i):
        return start_kind if i % 2 == 0 else other[start_kind]

    def done(lengths, close):
        info["close"] = dict({"n": 0, "n_set": n_close, "gap": s, "first": None, "clean": True, "left": 0.0,
                              "tried": []}, **close)
        info["u"] = list(lengths)
        return [w.at(u) for u in lengths], [kind_at(i) for i in range(len(lengths))], info

    if len(us) > 1 and abs(us[-1] - zone_end) <= fit and (len(us) - 1) % 2 == want:
        return done(us[:-1] + tail, {"way": "exact"})  # the last design step lands on the zone's end
    J = max(i for i, u in enumerate(us) if u < zone_end - fit)
    if not closed and free_end and J >= 2 and kind_at(J) == "HARD":
        return done(us[:J + 1], {"way": "short", "left": w.total - us[J]})   # Akash's case 1: stop at that HARD
    j_hi = J if J % 2 == want else J - 1

    def candidate(n, j, m):
        g, inner = _equal_chords(w, us[j], zone_end, m)
        lengths = us[:j + 1] + inner + tail
        centres = [w.at(u) for u in lengths]
        kinds = [kind_at(i) for i in range(len(lengths))]
        idxs = list(range(j, min(j + m + 1, len(centres))))
        return {"n": n, "j": j, "m": m, "g": g, "lengths": lengths, "way": "stretch" if g > s else "shrink",
                "ok": _zone_ok(centres, kinds, idxs, dh, ds, web, design_cut, tol)}

    ns = [1] + [n for n in range(max(2, n_close), n_max + 1)]
    cands = []
    for n in ns:
        for j in (j_hi - 2 * n + 2, j_hi - 2 * n):
            if j >= 0 and us[j] < zone_end - fit:
                cands.append(candidate(n, j, 2 * n))
    pick = None
    near = [c for c in cands if c["n"] == 1 and abs(2.0 * (c["g"] - s)) <= tiny]
    if near:
        pick = dict(min(near, key=lambda c: abs(c["g"] - s)), way="tiny", ok=True)
    for n in ns:
        if pick is not None:
            break
        ok = [c for c in cands if c["n"] == n and c["ok"]]
        if ok:
            pick = min(ok, key=lambda c: abs(c["g"] - s))
    if pick is None and J < 2 * n_close + 1:           # a wall too short for the zone: every gap equal, if that passes
        m0 = max(1, int(round(zone_end / s)))
        ms = [m for m in (m0 - 1, m0, m0 + 1, m0 + 2) if m >= 1 and m % 2 == want]
        equal = [candidate(m // 2, 0, m) for m in ms]
        ok = [c for c in equal if c["ok"]]
        if ok or not cands:
            pick = dict(min(ok or equal, key=lambda c: abs(c["g"] - s)), way="equal")
            cands = cands + equal
    if pick is None:
        pick = min(cands, key=lambda c: (abs(c["g"] - s), c["n"]))
    return done(pick["lengths"], {"n": pick["m"] // 2, "way": pick["way"], "gap": pick["g"], "first": pick["j"],
                                  "clean": pick["ok"],
                                  "tried": [(c["n"], c["way"], c["g"], c["ok"]) for c in cands]})


def bay_corners(us, kinds, closed, total, corners):
    """{index of a SOFT pile: bend in degrees} for the bays (HARD - SOFT - HARD) with a corner of the centre line
    strictly between their two HARD piles (a corner exactly on a HARD pile leaves both bays straight).
    us: each pile's length along the line; total: the line's length; corners: [(length along the line, bend)]."""
    n = len(us)
    eps = 1e-6 * max(1.0, total)
    res = {}
    for i in range(n):
        if kinds[i] != "SOFT":
            continue
        a, b = i - 1, i + 1
        if closed:
            a, b = a % n, b % n
        elif a < 0 or b >= n:
            continue
        if kinds[a] != "HARD" or kinds[b] != "HARD":
            continue
        ua, ub = us[a], us[b]
        if ub <= ua:                                   # the bay runs over the seam of a loop
            ub += total
        for uc, bend in corners:
            for x in ((uc, uc + total) if closed else (uc,)):
                if ua + eps < x < ub - eps:
                    res[i] = max(res.get(i, 0.0), bend)
    return res


def check_wall(centres, kinds, closed, dh, ds, s, web_warn=200.0, line=None, clear=None, tol=0.5):
    """Checks every pile of a laid-out wall (rule R7), all lengths in one unit (tol: rounding allowance).

    For each SOFT pile between two HARD piles: HARD to HARD, leftover web (= HARD to HARD - dh) and the cutting
    depth on each side (= (dh + ds)/2 - SOFT to HARD). Errors: a SOFT not cut (cut <= 0), HARD piles cutting each
    other (web < 0), two piles of the same type overlapping, two neighbours of the same type, a pile edge closer
    than `clear` to the drawn line. Warnings: web below web_warn, cutting depth below the design value.
    Returns dict(soft=[(i, hh, web, cut_before, cut_after)], gaps=[straight distance to the next pile],
    min_web=(web, i) or None, min_cut=(cut, i) or None, warnings=[(i, text)], errors=[(i, text)]).
    """
    n = len(centres)
    rad = {"HARD": dh / 2.0, "SOFT": ds / 2.0}
    design_cut = (dh + ds) / 2.0 - s

    def d(i, j):
        return math.hypot(centres[i][0] - centres[j][0], centres[i][1] - centres[j][1])

    def nb(i, k):
        j = i + k
        if closed:
            return j % n
        return j if 0 <= j < n else None

    res = {"soft": [], "gaps": [], "min_web": None, "min_cut": None, "warnings": [], "errors": []}
    for i in range(n if closed else n - 1):
        res["gaps"].append(d(i, (i + 1) % n))
        if kinds[i] == kinds[(i + 1) % n]:
            res["errors"].append((i, "two {} piles next to each other".format(kinds[i])))
    for i in range(n):
        p, q = nb(i, -1), nb(i, 1)
        if kinds[i] == "SOFT":
            cuts = [None if j is None or kinds[j] != "HARD" else (dh + ds) / 2.0 - d(i, j) for j in (p, q)]
            for c in cuts:
                if c is None:
                    continue
                if res["min_cut"] is None or c < res["min_cut"][0]:
                    res["min_cut"] = (c, i)
                if c <= tol:
                    res["errors"].append((i, "SOFT not cut by its HARD pile (cutting depth {:.0f})".format(c)))
                elif c < design_cut - tol:
                    res["warnings"].append((i, "cutting depth {:.0f}, less than the design {:.0f}".format(c, design_cut)))
            if p is not None and q is not None and kinds[p] == "HARD" and kinds[q] == "HARD" and p != q:
                hh = d(p, q)
                web = hh - dh
                res["soft"].append((i, hh, web, cuts[0], cuts[1]))
                if res["min_web"] is None or web < res["min_web"][0]:
                    res["min_web"] = (web, i)
                if web < -tol:
                    res["errors"].append((i, "HARD piles cut each other (web {:.0f})".format(web)))
                elif web < web_warn - tol:
                    res["warnings"].append((i, "leftover SOFT web {:.0f}, below {:.0f}".format(web, web_warn)))
    for i in range(n):
        for j in range(i + 2, n):
            if kinds[i] == kinds[j] and d(i, j) < 2 * rad[kinds[i]] - tol and not (closed and i == 0 and j == n - 1):
                res["errors"].append((i, "{} piles overlap (with pile {})".format(kinds[i], j + 1)))
    if line and clear is not None:
        for i in range(n):
            e = line_dist(centres[i], line, clear + rad[kinds[i]] + 1.0) - rad[kinds[i]]
            if e < clear - tol:
                res["errors"].append((i, "pile edge {:.0f} from your line (gap {:.0f})".format(e, clear)))
    return res


# ---------------------------------------------------------------- pile labels (Number button)
def pile_tangents(pts, closed):
    """Unit direction of the wall at each pile, from its neighbours (piles in draw order)."""
    n = len(pts)
    res = []
    for i in range(n):
        if closed and n > 2:
            a, b = pts[i - 1], pts[(i + 1) % n]
        else:
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        res.append((dx / L, dy / L))
    return res


def inside_sign(pts, closed, line_side=None):
    """+1 when the wall's inside is on the left of its draw direction, -1 on the right.

    Closed wall: the inside of the loop. Open wall: the side of the drawn line; line_side is SBP Wall's
    saved 'side' (the wall lies on that side of the line, so the line is on the other side of the wall).
    Without it: the side the wall bends towards; a straight wall without saved data: left.
    """
    if closed and len(pts) > 2:
        area = sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts)))
        return 1 if area > 0 else -1
    if line_side:
        return -1 if line_side > 0 else 1
    turn = 0.0
    for i in range(1, len(pts) - 1):
        a = (pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        b = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        turn += math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1])
    if abs(turn) > math.radians(5.0):
        return 1 if turn > 0 else -1
    return 1


def unturned_size(w_box, h_box, ang):
    """True width / height of a text box turned by `ang`, from its axis-aligned box (w_box x h_box).
    Near 45 deg the two cannot be told apart, so the (larger) box size is returned."""
    c, s = abs(math.cos(ang)), abs(math.sin(ang))
    det = c * c - s * s
    if abs(det) < 0.2:
        return w_box, h_box
    w = (w_box * c - h_box * s) / det
    h = (h_box * c - w_box * s) / det
    return max(w, 1e-6), max(h, 1e-6)


def readable_angle(ang):
    """Text direction turned so it never reads upside down: (-90, +90] degrees, in radians."""
    while ang > math.pi / 2 + 1e-9:
        ang -= math.pi
    while ang <= -math.pi / 2 + 1e-9:
        ang += math.pi
    return ang


def _box(cx, cy, ang, a, b):
    """Label box: centre, text direction e, across direction f, half sizes a (along e) and b (along f)."""
    c, s = math.cos(ang), math.sin(ang)
    return (cx, cy, (c, s), (-s, c), a, b)


def _boxes_hit(p, q, gap):
    """True when two boxes are closer than `gap` (separating-axis test)."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    if math.hypot(dx, dy) >= math.hypot(p[4], p[5]) + math.hypot(q[4], q[5]) + gap:
        return False
    for ax in (p[2], p[3], q[2], q[3]):
        rp = p[4] * abs(ax[0] * p[2][0] + ax[1] * p[2][1]) + p[5] * abs(ax[0] * p[3][0] + ax[1] * p[3][1])
        rq = q[4] * abs(ax[0] * q[2][0] + ax[1] * q[2][1]) + q[5] * abs(ax[0] * q[3][0] + ax[1] * q[3][1])
        if abs(dx * ax[0] + dy * ax[1]) >= rp + rq + gap:
            return False
    return True


def _box_circle_hit(p, c, gap):
    """True when a box is closer than `gap` to a circle (x, y, r)."""
    dx, dy = c[0] - p[0], c[1] - p[1]
    u = dx * p[2][0] + dy * p[2][1]
    v = dx * p[3][0] + dy * p[3][1]
    cu = max(-p[4], min(p[4], u))
    cv = max(-p[5], min(p[5], v))
    return math.hypot(u - cu, v - cv) < c[2] + gap


def place_labels(labels, circles, rects=(), offset=0.0, gap=0.0):
    """Places one label next to each pile so that no two overlap, and none covers a pile or another box.

    labels:  dicts x, y (pile centre), r (pile radius), tx, ty (wall direction at the pile),
             side (+1 = label on the left of that direction, -1 = right), w, h (text box, unrotated),
             angle (text direction in radians; the text is turned so it never reads upside down),
             alt (optional second text direction, tried only when `angle` fits nowhere).
    circles: (x, y, r) that labels must not cover, e.g. all piles nearby (a label's own pile is skipped).
    rects:   boxes already on the drawing: (cx, cy, angle, w, h), e.g. other tags in the view.
    Each label sits with the near edge of its text `offset` from its own pile's edge: one label per pile,
    never stacked in rows. In this order, the first place that touches nothing is used:
      1. the chosen side; 2. the other side of the wall, next to the same pile (so on a straight wall whose
      text is longer than one c/c the labels alternate sides); 3. a small nudge on either side (at most
      1.5 text heights out, or 0.6 text lengths along the wall, the smallest move first); 4. `alt`, the same way.
    If every try touches, the one that touches the fewest is used.
    Returns [(cx, cy, angle, nudged, clear, turned, flipped)] in the same order: turned = `alt` was used,
    flipped = placed on the other side of the wall.
    """
    placed = [_box(r[0], r[1], r[2], r[3] / 2.0, r[4] / 2.0) for r in rects]
    out = []
    for lb in labels:
        a, b = lb["w"] / 2.0, lb["h"] / 2.0
        s0 = 1 if lb["side"] >= 0 else -1
        t = (lb["tx"], lb["ty"])
        nudges = sorted(((dn * b, dt * a) for dn in (0.0, 1.0, 2.0, 3.0) for dt in (0.0, 0.6, -0.6, 1.2, -1.2)
                         if dn or dt), key=lambda v: math.hypot(v[0], v[1]))
        angles = [lb["angle"]] + ([lb["alt"]] if lb.get("alt") is not None else [])
        tries = []                                   # (side, text angle, turned, flipped, (push out, slide along))
        for k, raw in enumerate(angles):
            tries += [(s0, raw, k, False, (0.0, 0.0)), (-s0, raw, k, True, (0.0, 0.0))]
            tries += [(s, raw, k, s != s0, nd) for nd in nudges for s in (s0, -s0)]
        best = None
        for s, raw, turned, flipped, (dn, dt) in tries:
            n = (-t[1] * s, t[0] * s)
            ang = readable_angle(raw)
            e, f = (math.cos(ang), math.sin(ang)), (-math.sin(ang), math.cos(ang))
            depth = a * abs(e[0] * n[0] + e[1] * n[1]) + b * abs(f[0] * n[0] + f[1] * n[1])   # half size along n
            d = lb["r"] + offset + depth + dn
            box = _box(lb["x"] + n[0] * d + t[0] * dt, lb["y"] + n[1] * d + t[1] * dt, ang, a, b)
            hits = sum(1 for q in placed if _boxes_hit(box, q, gap))
            hits += sum(1 for c in circles
                        if (abs(c[0] - lb["x"]) > 1e-9 or abs(c[1] - lb["y"]) > 1e-9) and _box_circle_hit(box, c, gap))
            if best is None or hits < best[1]:
                best = (box, hits, bool(dn or dt), ang, bool(turned), flipped)
            if hits == 0:
                break
        box, hits, nudged, ang, turned, flipped = best
        placed.append(box)
        out.append((box[0], box[1], ang, nudged, hits == 0, turned, flipped))
    return out

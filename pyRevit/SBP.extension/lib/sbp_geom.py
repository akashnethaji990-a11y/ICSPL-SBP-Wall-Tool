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


def offset_path(samples, closed, side, dist):
    """Offset a chain of sampled curves by dist to one side.

    Convex corners get a rounded fan of points; concave corners create small
    loops which remove_loops() cuts out afterwards.
    """
    out = []
    prev_t = None
    for pts, tans in samples:
        for k, (p, t) in enumerate(zip(pts, tans)):
            if k == 0 and prev_t is not None:
                out.extend(_fan(p, prev_t, t, side, dist))
                continue
            n = _signed_normal(t, side)
            out.append((p[0] + n[0] * dist, p[1] + n[1] * dist))
        prev_t = tans[-1]
    if closed:
        first_p = samples[0][0][0]
        first_t = samples[0][1][0]
        out.extend(_fan(first_p, prev_t, first_t, side, dist)[:-1])
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

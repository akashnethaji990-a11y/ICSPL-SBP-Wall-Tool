# -*- coding: utf-8 -*-
"""Offline tests for pyRevit/SBP.extension/lib/sbp_data.py (no Revit needed).

Run:  python tests/test_sbp_data.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pyRevit", "SBP.extension", "lib"))
import sbp_data as SD

WALL = {"wall": "SBP1", "type_name": "1200mm Bored Pile", "spacing": 900.0, "gap": 150.0,
        "cutoff": -150.0, "toe_hard": -10000.0, "toe_soft": -9000.0, "invisible": True,
        "lines": ["a", "b"], "side": -1.0}


def test_json_round_trip():
    d = SD.decode(SD.encode(WALL))
    assert d["version"] == SD.VERSION
    for k, v in WALL.items():
        assert d[k] == v, k


def test_newer_version_is_refused():
    txt = SD.encode(WALL).replace('"version": 1', '"version": 99')
    try:
        SD.decode(txt)
        assert False, "should refuse"
    except ValueError:
        pass


def test_check_settings():
    ok = {"spacing": 900.0, "gap": 150.0, "cutoff": -150.0, "toe_hard": -10000.0, "toe_soft": -9000.0}
    assert SD.check_settings(ok) == []
    assert len(SD.check_settings(dict(ok, gap=100.0))) == 1
    assert len(SD.check_settings(dict(ok, spacing=0.0))) == 1
    assert len(SD.check_settings(dict(ok, toe_soft=0.0))) == 1


def test_fmt_num():
    assert SD.fmt_num(900.0) == "900" and SD.fmt_num(-150.0) == "-150" and SD.fmt_num(868.25) == "868.25"


def test_changed_fields_and_rebuild():
    a = {"type": "T", "spacing": 900.0, "cutoff": -150.0}
    assert SD.changed_fields(a, dict(a, spacing=900.0000001), ("type", "spacing", "cutoff")) == []
    ch = SD.changed_fields(a, dict(a, cutoff=-300.0), ("type", "spacing", "cutoff"))
    assert ch == ["cutoff"] and not SD.needs_rebuild(ch)
    ch = SD.changed_fields(a, dict(a, spacing=850.0), ("type", "spacing", "cutoff"))
    assert ch == ["spacing"] and SD.needs_rebuild(ch)
    assert SD.needs_rebuild(["type"]) and SD.needs_rebuild(["gap"]) and not SD.needs_rebuild(["toe_soft"])


def test_same_layout():
    a = [(0.0, 0.0, "HARD"), (900.0, 0.0, "SOFT")]
    assert SD.same_layout(a, list(reversed(a)), 1.0)
    assert not SD.same_layout(a, [(0.0, 0.0, "HARD"), (905.0, 0.0, "SOFT")], 1.0)
    assert not SD.same_layout(a, [(0.0, 0.0, "SOFT"), (900.0, 0.0, "HARD")], 1.0)
    assert not SD.same_layout(a, a[:1], 1.0)


def test_match_nearest_same_type():
    old = [(0.0, 0.0, "HARD"), (900.0, 0.0, "SOFT")]
    new = [(10.0, 0.0, "SOFT"), (700.0, 0.0, "HARD"), (1600.0, 0.0, "SOFT")]
    m, lost = SD.match_nearest(old, new)
    assert m[0] == (1, 700.0) and m[1] == (2, 700.0) and lost == []   # 1600 is nearer than 10


def test_match_nearest_conflict_keeps_closer():
    old = [(0.0, 0.0, "HARD"), (100.0, 0.0, "HARD")]
    new = [(90.0, 0.0, "HARD")]
    m, lost = SD.match_nearest(old, new)
    assert list(m.keys()) == [1] and lost == [0]


def test_spacing_change_moves_data_like_the_preview():
    # 49 piles at 868.25 -> 51 piles at 833.52 on the preview wall: H014 ends on H015, ~764 mm away
    old_s, new_s = 22574.5, [2 * j * 833.52 for j in range(26)]
    m, lost = SD.match_nearest([(old_s, 0.0, "HARD")], [(x, 0.0, "HARD") for x in new_s])
    j, d = m[0]
    assert j == 14 and abs(d - 764) < 2, (j, d)


def test_next_free_name_never_reuses():
    assert SD.next_free_name("SBP1", set()) == "SBP1"
    assert SD.next_free_name("SBP1", {"SBP1"}) == "SBP2"
    assert SD.next_free_name("SBP1", {"SBP1", "SBP2", "SBP3"}) == "SBP4"
    assert SD.next_free_name("WALL-A", {"WALL-A"}) == "WALL-A2"
    assert SD.next_free_name("", {"SBP1"}) == "SBP2"


def test_match_nearest_distance_cap():
    old = [(0.0, 0.0, "HARD"), (100.0, 0.0, "SOFT")]
    new = [(30000.0, 0.0, "HARD"), (150.0, 0.0, "SOFT")]
    m, lost = SD.match_nearest(old, new, max_dist=4500.0)
    assert list(m.keys()) == [1] and lost == [0]      # 30 m away: not copied, reported


def test_join_rules():
    D, S = 1200.0, 900.0
    assert SD.classify_join(None, D, S) is None
    assert SD.classify_join(0.0, D, S) == "same"
    assert SD.classify_join(449.0, D, S) == "same"
    assert SD.classify_join(1061.0, D, S) == "touch"      # 90 deg corner between two walls
    assert SD.classify_join(1300.0, D, S) is None
    assert SD.end_setup(None, None) == ("HARD", False)
    assert SD.end_setup("same", "SOFT") == ("SOFT", True)  # continue from the existing SOFT: next is HARD
    assert SD.end_setup("touch", "SOFT") == ("HARD", False)
    assert SD.end_setup("touch", "HARD") == ("SOFT", False)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    bad = 0
    for n, f in tests:
        try:
            f()
            print("PASS  " + n)
        except AssertionError as ex:
            bad += 1
            print("FAIL  {}  {}".format(n, ex))
    print("{} passed, {} failed".format(len(tests) - bad, bad))
    sys.exit(1 if bad else 0)

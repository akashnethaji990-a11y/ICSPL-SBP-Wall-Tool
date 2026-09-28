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


def test_mark_numbers():
    assert SD.mark_number("SP12", "SP") == 12 and SD.mark_number(" SP007 ", "SP") == 7
    assert SD.mark_number("C1-SP5", "SP") is None and SD.mark_number("C1-SP5", "C1-SP") == 5
    assert SD.mark_number("SPX3", "SP") is None and SD.mark_number("SP", "SP") is None
    assert SD.mark_number("SBP1-S001", "SP") is None and SD.mark_number("SP3", "") is None
    assert SD.max_number(["SP3", "HP9", "SP12", "SP2", "C1-SP40", ""], "SP") == 12
    assert SD.max_number(["HP1"], "SP") == 0


def test_check_prefixes():
    assert SD.check_prefixes("SP", "HP") == [] and SD.check_prefixes("C1-SP", "C1-HP") == []
    assert SD.check_prefixes("", "HP") and SD.check_prefixes("SP", "SP")
    assert len(SD.check_prefixes("SP1", "HP")) == 1


def test_number_plan_open_wall_starts_hard():
    kinds = ["HARD", "SOFT"] * 21 + ["HARD"]                       # 43 piles, 22 H / 21 S
    (name, lv, marks, rng), = SD.number_plan([("SBP1", "L1", kinds)], "SP", "HP", {})
    assert marks[:4] == ["HP1", "SP1", "HP2", "SP2"] and marks[-1] == "HP22"
    assert rng == {"SOFT": (1, 21), "HARD": (1, 22)}
    assert SD.range_text("SP", rng["SOFT"]) == "SP1 to SP21" and SD.range_text("HP", (4, 4)) == "HP4"


def test_number_plan_continues_across_walls_per_level():
    walls = [("SBP1", "L1", ["SOFT", "HARD", "SOFT"]), ("SBP2", "L2", ["HARD"]), ("SBP3", "L1", ["HARD", "SOFT"])]
    res = SD.number_plan(walls, "C1-SP", "C1-HP", {"L1": (7, 7)})
    assert res[0][2] == ["C1-SP8", "C1-HP8", "C1-SP9"]
    assert res[1][2] == ["C1-HP1"]                                  # other level: own sequence
    assert res[2][2] == ["C1-HP9", "C1-SP10"]                       # runs on from SBP1, not from 1


def test_continue_text():
    assert SD.continue_text("SP", 7) == "continuing from SP7, next will be SP8"
    assert SD.continue_text("HP", 0) == "no HP numbers yet, next will be HP1"


def test_default_marks():
    assert SD.default_mark_parts("SBP1-H014") == ("SBP1", "HARD", 14)
    assert SD.default_mark_parts("WALL-A-s003") == ("WALL-A", "SOFT", 3)
    assert SD.default_mark_parts("SP12") is None
    assert SD.is_default_mark("SBP1-S001", "SBP1") and not SD.is_default_mark("SBP1-S001", "SBP2")
    assert not SD.is_default_mark("HP3", "SBP1") and not SD.is_default_mark("", "SBP1")
    assert sorted(["SBP10", "SBP2", "SBP1"], key=SD.natural_key) == ["SBP1", "SBP2", "SBP10"]


def test_legacy_order():
    # open wall H S H S H along x at 900 c/c, keys shuffled
    piles = [("h1", "HARD", 1, 0, 0), ("s1", "SOFT", 1, 900, 0), ("h2", "HARD", 2, 1800, 0),
             ("s2", "SOFT", 2, 2700, 0), ("h3", "HARD", 3, 3600, 0)]
    assert SD.legacy_order(list(reversed(piles))) == ["h1", "s1", "h2", "s2", "h3"]
    # joined wall that starts SOFT and ends HARD (equal counts): the positions decide
    piles = [("s1", "SOFT", 1, 0, 0), ("h1", "HARD", 1, 900, 0), ("s2", "SOFT", 2, 1800, 0), ("h2", "HARD", 2, 2700, 0)]
    assert SD.legacy_order(piles) == ["s1", "h1", "s2", "h2"]
    piles = [("h1", "HARD", 1, 0, 0), ("s1", "SOFT", 1, 900, 0), ("h2", "HARD", 2, 1800, 0), ("s2", "SOFT", 2, 2700, 0)]
    assert SD.legacy_order(piles) == ["h1", "s1", "h2", "s2"]
    assert SD.legacy_order([("x", "HARD", None, 0, 0)]) is None


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

# -*- coding: utf-8 -*-
"""Offline tests for pyRevit/SBP.extension/lib/sbp_data.py (no Revit needed).

Run:  python tests/test_sbp_data.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pyRevit", "SBP.extension", "lib"))
import sbp_data as SD

WALL = {"wall": "SBP1", "type_name": "1200mm Bored Pile", "spacing_hh": 1800.0, "gap": 150.0,
        "cutoff": -150.0, "toe_hard": -10000.0, "toe_soft": -9000.0, "invisible": True,
        "lines": ["a", "b"], "side": -1.0}


def test_json_round_trip():
    d = SD.decode(SD.encode(WALL))
    assert d["version"] == SD.VERSION
    for k, v in WALL.items():
        assert d[k] == v, k


def test_newer_version_is_refused():
    txt = SD.encode(WALL).replace('"version": {}'.format(SD.VERSION), '"version": 99')
    try:
        SD.decode(txt)
        assert False, "should refuse"
    except ValueError:
        pass


def test_check_settings():
    ok = {"spacing_hh": 1800.0, "gap": 150.0, "cutoff": -150.0, "toe_hard": -10000.0, "toe_soft": -9000.0}
    assert SD.check_settings(ok) == []
    assert SD.check_settings(dict(ok, gap=10.0)) == [] and SD.check_settings(dict(ok, gap=100.0)) == []   # min 10
    assert len(SD.check_settings(dict(ok, gap=9.0))) == 1
    assert len(SD.check_settings(dict(ok, spacing_hh=0.0))) == 1
    assert len(SD.check_settings(dict(ok, toe_soft=0.0))) == 1


def test_spacing_akash_drawing_1500_at_2000():
    # Akash's drawing: HARD and SOFT 1500, HARD to HARD 2000 -> cutting 500 each side, leftover SOFT web 500
    v = SD.spacing_values(2000.0, 1500.0, 1500.0)
    assert v == {"spacing_hh": 2000.0, "spacing": 1000.0, "cut": 500.0, "web": 500.0}, v
    shown = SD.spacing_values(1800.0, 1500.0, 1500.0)                               # what the form showed
    for key, value in (("spacing_hh", 2000.0), ("cut", 500.0), ("web", 500.0)):
        entered = dict(shown, **{key: value})
        changed = SD.changed_spacing(entered, shown)
        assert changed == [(key, value)], changed                                  # only that box changed
        k, val, note, err = SD.spacing_driver(changed, 1500.0, 1500.0)
        assert (k, val, note, err) == (key, value, None, None)
        assert SD.hh_from(k, val, 1500.0, 1500.0) == 2000.0, key                   # any one gives HARD to HARD 2000
    assert SD.changed_spacing(dict(shown), shown) == []                            # nothing changed
    assert SD.changed_spacing(dict(shown, cut=None), shown) == []                  # a blank box is ignored
    assert SD.hh_from("spacing", 1000.0, 1500.0, 1500.0) == 2000.0                 # the old HARD to SOFT


def test_spacing_different_diameters():
    # HARD 1500, SOFT 1200 at HARD to HARD 2000: cutting (1500 + 1200 - 2000) / 2 = 350, web 2000 - 1500 = 500
    v = SD.spacing_values(2000.0, 1500.0, 1200.0)
    assert v["cut"] == 350.0 and v["web"] == 500.0 and v["spacing"] == 1000.0
    assert SD.hh_from("cut", 350.0, 1500.0, 1200.0) == 2000.0
    assert SD.hh_from("web", 500.0, 1500.0, 1200.0) == 2000.0
    # a cutting depth kept with a new SOFT type moves HARD to HARD: cut 500 with SOFT 1200 -> 1700
    assert SD.hh_from("cut", 500.0, 1500.0, 1200.0) == 1700.0


def test_spacing_typed_cut_or_web_wins():
    shown = SD.spacing_values(2000.0, 1500.0, 1500.0)
    changed = SD.changed_spacing(dict(shown, spacing_hh=2100.0, web=400.0), shown)
    k, val, note, err = SD.spacing_driver(changed, 1500.0, 1500.0)
    assert (k, val, err) == ("web", 400.0, None) and "wins" in note                 # web wins over HARD to HARD
    assert SD.hh_from(k, val, 1500.0, 1500.0) == 1900.0
    ok = SD.changed_spacing(dict(shown, spacing_hh=1900.0, web=400.0), shown)
    assert SD.spacing_driver(ok, 1500.0, 1500.0) == ("web", 400.0, None, None)      # they agree: no note
    bad = SD.changed_spacing(dict(shown, cut=450.0, web=400.0), shown)
    k, val, note, err = SD.spacing_driver(bad, 1500.0, 1500.0)
    assert k is None and "Change only one" in err                                   # cut 450 = HH 2100, web 400 = 1900
    assert SD.spacing_driver([], 1500.0, 1500.0) == (None, None, None, None)


def test_check_spacing_errors_and_web_warning():
    assert SD.check_spacing(2000.0, 1500.0, 1500.0) == ([], [])
    errs, warns = SD.check_spacing(1650.0, 1500.0, 1500.0)                          # web 150: placed, with a warning
    assert errs == [] and "below 200" in warns[0]
    errs, warns = SD.check_spacing(3000.0, 1500.0, 1500.0)                          # cutting 0
    assert "must cut the SOFT" in errs[0]
    errs, warns = SD.check_spacing(1400.0, 1500.0, 1500.0)                          # web -100
    assert any("cut each other" in e for e in errs)
    errs, warns = SD.check_spacing(1300.0, 1200.0, 1500.0)                          # SOFT 1500 > HARD to HARD
    assert any("SOFT piles would cut" in e for e in errs)
    assert SD.check_spacing(1500.0, 1500.0, 1500.0) == ([], [SD.check_spacing(1500.0, 1500.0, 1500.0)[1][0]])
    assert SD.corner_web(2000.0, 1500.0) == 200.0 and SD.corner_web(1650.0, 1500.0) == 150.0


def test_upgrade_old_walls():
    old = {"wall": "SBP1", "type_uid": "t1", "type_name": "1200mm Bored Pile", "spacing": 900.0, "gap": 150.0}
    d = SD.upgrade(old)
    assert d["spacing_hh"] == 1800.0 and d["spacing_by"] == "spacing_hh" and d["spacing_val"] == 1800.0
    assert d["soft_type_uid"] == "t1" and d["soft_type_name"] == "1200mm Bored Pile" and d["layout"] == 1
    new = SD.upgrade(dict(old, spacing_hh=2000.0, spacing_by="cut", spacing_val=500.0, layout=2))
    assert new["spacing_hh"] == 2000.0 and new["spacing_by"] == "cut" and new["layout"] == 2


def test_linked_boxes_recompute_live_and_never_crash():
    # HARD to HARD drives cutting and web: 1500 at 2000 -> cut 500, web 500 (not 300 / 600)
    assert SD.linked_boxes("spacing_hh", 2000.0, 1500.0, 1500.0) == {"spacing_hh": 2000.0, "cut": 500.0, "web": 500.0}
    assert SD.linked_boxes("spacing_hh", 1800.0, 1500.0, 1500.0) == {"spacing_hh": 1800.0, "cut": 600.0, "web": 300.0}
    # a typed cutting depth or web sets HARD to HARD, and the other two follow
    assert SD.linked_boxes("cut", 500.0, 1500.0, 1200.0) == {"spacing_hh": 1700.0, "cut": 500.0, "web": 200.0}
    assert SD.linked_boxes("web", 500.0, 1500.0, 1500.0) == {"spacing_hh": 2000.0, "cut": 500.0, "web": 500.0}
    # a blank box, or a diameter not read yet, never crashes (leaves the unknowns None)
    assert SD.linked_boxes("spacing_hh", None, 1500.0, 1500.0) == {"spacing_hh": None, "cut": None, "web": None}
    assert SD.linked_boxes("cut", 500.0, None, None) == {"spacing_hh": None, "cut": 500.0, "web": None}
    assert SD.fmt_num(None) == "" and SD.fmt_num("") == "" and SD.fmt_num(500.0) == "500"


def test_plan_rows_show_what_was_read_and_worked_out():
    s = {"spacing_hh": 2000.0, "spacing_by": "cut", "spacing_val": 500.0, "gap": 150.0}
    kinds = ["HARD", "SOFT", "HARD", "SOFT", "HARD"]
    chk = {"gaps": [1000.0, 1000.0, 850.0, 850.0], "min_web": (200.0, 3), "min_cut": (500.0, 1),
           "warnings": [(3, "leftover SOFT web 150, below 200")], "errors": []}
    rows, warns, errs = SD.plan_rows("SBP1", s, "1500mm Bored Pile", "1500mm Bored Pile", 1500.0, 1500.0, 900.0,
                                     3700.0, False, kinds, chk, [(90.0, 1202.1, 1202.1, 323.2, False)] * 2,
                                     dropped=[90.0], entered="typed now")
    d = dict((a, b) for a, b in rows)
    assert d["HARD pile (read from its type)"] == "1500mm Bored Pile: 1500 mm"
    assert d["Spacing set by"] == "cutting depth 500 (typed now)"
    assert d["Cutting depth, each side = (Dh + Ds - HH) / 2"] == "500" and d["Leftover SOFT web = HH - Dh"] == "500"
    assert d["Corners: SOFT on the corner (option B)"] == "90 deg: HARD 1202 / 1202 from it, SOFT moved 323 (x2)"
    assert d["Piles"] == "3 HARD + 2 SOFT = 5" and d["Gaps at design c/c"] == "2 of 4, 2 reduced (smallest 850)"
    assert d["Smallest SOFT web (mm)"] == "200 at SBP1-S002"                    # piles named by their future marks
    assert warns[0] == "SBP1-S002: leftover SOFT web 150, below 200" and "dropped" in warns[1] and errs == []
    assert d["Warnings / errors"] == "2 / 0"
    rows, warns, errs = SD.plan_rows("W", dict(s, spacing_hh=1650.0), "A", "A", 1500.0, 1500.0, 900.0, 1.0, True,
                                     kinds, chk, [], equal=978.4)
    d = dict((a, b) for a, b in rows)
    assert "WARNING: below 200" in d["Leftover SOFT web = HH - Dh"] and "equal c/c 978.4" in d["Corners"]


def test_default_marks_in_wall_order():
    assert SD.default_marks("SBP1", ["HARD", "SOFT", "HARD"]) == ["SBP1-H001", "SBP1-S001", "SBP1-H002"]


def test_fmt_num():
    assert SD.fmt_num(900.0) == "900" and SD.fmt_num(-150.0) == "-150" and SD.fmt_num(868.25) == "868.25"


def test_changed_fields_and_rebuild():
    keys = ("type", "spacing_hh", "cutoff")
    a = {"type": "T", "spacing_hh": 1800.0, "cutoff": -150.0}
    assert SD.changed_fields(a, dict(a, spacing_hh=1800.0000001), keys) == []
    ch = SD.changed_fields(a, dict(a, cutoff=-300.0), keys)
    assert ch == ["cutoff"] and not SD.needs_rebuild(ch)
    ch = SD.changed_fields(a, dict(a, spacing_hh=1700.0), keys)
    assert ch == ["spacing_hh"] and SD.needs_rebuild(ch)
    assert SD.needs_rebuild(["type"]) and SD.needs_rebuild(["soft_type"]) and SD.needs_rebuild(["gap"])
    assert not SD.needs_rebuild(["toe_soft"])


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


def test_detect_pile_params_icspl_pile():
    # Akash's family: Radius (read-only instance), Depth, Height Offset From Level
    params = [("Radius", True, True, 1.97, "instance"), ("Depth", True, False, 32.8, "instance"),
              ("Height Offset From Level", True, False, -0.98, "instance"), ("Elevation at Top", True, True, 0.0, "instance")]
    found = SD.detect_pile_params(params)
    assert found == {"diameter": ("Radius", 2), "length": "Depth", "offset": "Height Offset From Level"}
    assert SD.pile_spec_from(found) == {"diameter": "Radius", "factor": 2, "length": "Depth",
                                        "offset": "Height Offset From Level"}


def test_detect_pile_params_other_families():
    # a drafter's family: type 'Pile Dia', instance 'Pile Length', bar sizes that must not be taken as the pile
    params = [("Bar Diameter", True, False, 0.08, "type"), ("Pile Dia", True, False, 3.9, "type"),
              ("Pile Length", True, False, 50.0, "instance"), ("Height Offset From Level", True, False, 0.0, "instance")]
    found = SD.detect_pile_params(params)
    assert found["diameter"] == ("Pile Dia", 1) and found["length"] == "Pile Length"
    # unusual names: the diameter is not found, so the drafter is asked once
    params = [("B", True, False, 3.9, "type"), ("Pile Length", True, False, 50.0, "instance"),
              ("Offset from Host", True, False, 0.0, "instance")]
    found = SD.detect_pile_params(params)
    assert "diameter" not in found and found["offset"] == "Offset from Host" and SD.pile_spec_from(found) is None
    assert SD.looks_like_pile("BP_Round Pile", found) and not SD.looks_like_pile("Pad Footing", found)
    # read-only length parameters are never taken as length / offset
    found = SD.detect_pile_params([("Depth", True, True, 30.0, "instance"), ("Diameter", True, True, 3.0, "instance")])
    assert "length" not in found and found["diameter"] == ("Diameter", 1)


def test_label_name():
    assert SD.label_name("ICSPL_Pile Tag", "Mark 2.5mm") == "ICSPL_Pile Tag : Mark 2.5mm"      # foundation tags: as before
    assert SD.label_name("ICSPL_Pile_Mark_Tag", "Standard", "Generic Model Tag") == \
        "ICSPL_Pile_Mark_Tag : Standard  (Generic Model Tag)"


def test_pick_text_param():
    assert SD.pick_text_param(["Comments2", "Pile Mark", "Mark"]) == "Mark"
    assert SD.pick_text_param(["Remarks", "Pile_Mark"]) in ("Remarks", "Pile_Mark")      # both contain "mark"
    assert SD.pick_text_param(["Note", "Pile No"]) == "Pile No"                          # "No" as a word, not "Note"
    assert SD.pick_text_param(["Description", "Label Text"]) == "Label Text"
    assert SD.pick_text_param(["Description"]) == "Description" and SD.pick_text_param([]) is None


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


def test_type_name_must_match_size():
    assert SD.name_size_mm("1300mm Bored Pile") == 1300.0
    assert SD.name_size_mm("1500mm Hard Pile_Existing") == 1500.0
    assert SD.name_size_mm("1300 MM x") == 1300.0
    assert SD.name_size_mm("Base slab_thick") is None
    assert SD.name_size_mm("ICSPL_C991") is None
    msg = SD.size_name_mismatch("HARD", "1300mm Bored Pile", 1200.0)
    assert msg and "1200" in msg and "1300" in msg and msg.startswith("HARD type '1300mm Bored Pile'"), msg
    assert SD.size_name_mismatch("HARD", "1300mm Bored Pile", 1300.4) is None
    assert SD.size_name_mismatch("SOFT", "Base slab_thick", 600.0) is None
    assert SD.size_name_mismatch("SOFT", "1300mm Bored Pile", None) is None


def test_closing_zone_settings_and_text():
    assert SD.close_n({}) == 3 and SD.close_n({"close_n": "4"}) == 4 and SD.close_n({"close_n": "x"}) == 3
    assert SD.default_hh(1200.0) == 1800.0 and SD.default_hh(1300.0) == 1900.0 and SD.default_hh(None) is None
    base = {"spacing_hh": 1800.0, "gap": 150.0, "cutoff": 0.0, "toe_hard": -20000.0, "toe_soft": -20000.0}
    assert SD.check_settings(dict(base, close_n=6)) == []
    assert SD.check_settings(dict(base, close_n=7)) and SD.check_settings(dict(base, close_n=2.5))
    assert SD.upgrade({"spacing_hh": 1800.0})["close_n"] == 3
    assert "close_n" in SD.REBUILD_KEYS
    t = SD.closing_text({"n": 4, "n_set": 3, "way": "shrink", "gap": 719.85})
    assert t == "4 bays shortened to H-H 1440, N raised from 3 to 4", t
    assert "none needed" in SD.closing_text({"n": 0, "n_set": 3, "way": "exact", "gap": 900.0})


def test_plan_rows_show_closing_bays_and_size_source():
    kinds = ["HARD", "SOFT"] * 3 + ["HARD"]
    chk = {"gaps": [900.0] * 4 + [750.0] * 2, "min_web": (300.0, 5), "min_cut": (300.0, 1), "warnings": [], "errors": []}
    closing = {"n": 1, "n_set": 3, "way": "equal", "gap": 750.0, "clean": True, "bays": [([4, 5, 6], 1500.0, 750.0, 750.0)]}
    rows, warns, errs = SD.plan_rows("SBP9", {"spacing_hh": 1800.0, "gap": 150.0}, "1200mm Bored Pile",
                                     "1200mm Bored Pile", 1200.0, 1200.0, 750.0, 5100.0, False, kinds, chk, [],
                                     closing=closing, size_src={"HARD": "type parameter 'Diameter'",
                                                                "SOFT": "type parameter 'Diameter'"})
    d = dict(rows)
    assert d["HARD pile (read from its type)"].endswith("(type parameter 'Diameter')"), d
    assert d["  bay SBP9-H003 - SBP9-S003 - SBP9-H004"] == "H-H 1500 (H-S 750 / 750), web 300, cut 450", d
    assert d["Corners"].startswith("no adjustment")


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

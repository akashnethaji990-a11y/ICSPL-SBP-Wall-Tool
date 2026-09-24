# Project context: SBP Wall pyRevit tool (IC Singapore, BIM)

User: Akash, BIM engineer. Full chat history: `HISTORY.md` (read it first; §9 has the latest decisions).
Revit 2026. Tool platform: **pyRevit** (IronPython 2.7-compatible code: no f-strings, use .format()).
Decision record: `ADR-001_Revit_Automation_Platform.md`.

## Working with Akash
- Go one step at a time. He confirms each step with Revit screenshots. He writes short English, so
  reply with numbers, tables and simple diagrams.
- For the v2 rules below he asked to **see an example drawing before any coding**.
- Update HISTORY.md and CLAUDE.md with decisions and status at the end of each session.

## Goal
Draw one "other structure" line in plan (straight / arc / circle / spline / connected chain, open or
closed) → a Secant Bored Pile (SBP) wall is created along it, HARD and SOFT piles alternating.

## Requirements (original plan sketch)
1. The drawn line = "other structure" line. The wall is offset from it to the side the user clicks.
2. Gap from line to SBP inner edge = 150 mm default, adjustable, **minimum 150**.
3. Everything adjustable: pile dia (default 1200), c/c hard-to-soft (default 900 → hard-to-hard 1800,
   overlap 300). Line → SBP centre line = gap + D/2 = 750.
4. Report how many HARD and SOFT piles.
5. The drawn line becomes invisible (`<Invisible lines>`, like AutoCAD Defpoints).
6. Top = **Cut-off Level**, bottom = **Toe Level** (separate toe for hard/soft allowed).

## Decided rules for v2 (24 Sep 2026): ON HOLD for senior review, except R8 (coded 25 Sep) and the
## wall-end part of R1 (coded 25 Sep as "joins", see Current logic). Details: HISTORY.md §9
- **R1 Ends and loops:** an open wall starts and ends **HARD**. A loop alternates H/S all round
  (even count), and two piles of the same type never meet at the seam ("like a magnet").
- **R2 Corners:** a corner is a bend > 5° at a joint of the drawn chain. Corners are **sharp** (like
  AutoCAD OFFSET). The pile **on a corner is SOFT**, at both inside and outside corners.
- **R3 Spacing:** straight runs use the design c/c (900). The leftover is absorbed next to corners
  (at the far end if the wall has no corner).
- **R4 SOFT web rule (every soft pile, all angles, incl. arcs/circles/splines):**
  - The clear gap between the edges of the two neighbouring HARD piles, measured along the line
    joining their centres, must be ≥ web.
  - Form field "Min uncut soft web (mm)": default 200, minimum 200, remembered.
  - So H–H ≥ D + web.
  - Symmetric form: c/c ≥ (D/2 + web/2)/cos(bend/2). Ø1200: 0° 700 | 30° 725 | 45° 758 | 60° 808 | 90° 990.
  - A straight c/c is never below 700. The minimum is absolute (not a fraction of D).
- **R5 No cutting:** HARD–HARD never cut (≥ D), SOFT–SOFT never cut (≥ D), gap to the line ≥ 150.
- **R6 Warnings and errors:**
  - If R4 forces c/c > design, do it and **WARN**, listing mark, angle, c/c used and overlap left
    (D − c/c).
  - If c/c ≥ D, it's an **ERROR**.
  - At Ø1200, c/c 900, web 200: warning from a 77.9° bend, error from 108.6°.
- **R7 Checks:** check every pile after placing and report the smallest web in the wall.
- **R8 Graphics:**
  - 2D: HARD = solid fill, SOFT = "Diagonal up 1.5mm" hatch.
  - Done with view filters `SBP HARD PILE` / `SBP SOFT PILE` (by Comments) in the **current view**.
    Ask first if its view template controls filters.
  - 3D: material **ICSPL_Pile** (in his template) on both types.
- **Short-leg fallback:** where two corners are too close for the symmetric formula, use unequal
  corner gaps (H–H still ≥ D + web). If that fails too, drop that corner and report it.
- **Superseded, don't implement:** pulling the soft pile outward, a D/3 soft limit, an
  equal-spacing mode.
- **OPEN QUESTION (ask with the example drawing):** where does the corner SOFT go?
  - **A:** on the corner point, with a warning (at 90°: c/c 990, overlap 210).
  - **B:** moved inward along the bisector just enough to get overlap 300 back (≈134 mm at 90°),
    never closer than the gap to the line. His drawing shows the soft inside the corner.
    Claude recommends B.

## User's pile family (existing, do not rebuild)
- Family `ICSPL_Pile`, type e.g. `1200mm Bored Pile`, category **Structural Foundations**, level-based.
- Instance params:
  - `Level`;
  - `Height Offset From Level` (drives cut-off);
  - `Depth` (drives toe);
  - `Radius` (read-only, = D/2);
  - `Elevation at Top` and `Elevation at Bottom` (read-only);
  - `Structural Material` (was `<By Category>` in Project1).
- Family rule, confirmed in Revit: displayed Top = level + offset + 150, and displayed Bottom =
  level + offset − Depth. So the physical length = Depth + 150, and the script calibrates against the
  displayed Top/Bottom.
- Other params exist (Loading, Mline Text, BH Ref, Section, GEO-/PDS- analysis...). Don't touch them.

## Files
- `pyRevit/SBP.extension/`: the extension. Its parent folder `pyRevit` is registered in pyRevit's
  Custom Extension Directories.
  - `lib/sbp_geom.py`: pure-Python geometry, testable outside Revit. Offset path with ROUNDED convex
    corners, self-intersection loop removal (inside corners), equal division (`divide(..., odd)`),
    `layout_ends` (fixed pile type at each end, skip an end already taken by another wall).
  - `lib/sbp_data.py`: pure Python. Saved-settings JSON, change detection, `match_nearest` (typed
    data after a rebuild), join rules (`classify_join`, `end_setup`).
  - `lib/sbp_revit.py`: Revit helpers shared by all buttons (lookups, chain, placing, levels
    calibration, joins, typed data copy, Extensible Storage wall settings, HARD/SOFT look).
  - `SBP.tab/Piling.panel/bundle.yaml`: button order.
  - `SBP Wall.pushbutton`: create a wall. rpw FlexForm with fallback prompts; last-used values in
    `%APPDATA%\SBPTool\settings.json`; per-wall settings saved in the model.
  - `SBP Edit.pushbutton`, `SBP Select.pushbutton`, `SBP Line.pushbutton`: new 25 Sep (see HISTORY §11).
  - `SBP Count.pushbutton`: counts HARD/SOFT per wall.
- `tests/test_sbp_geom.py`, `tests/test_sbp_data.py`: offline tests. Run with `python tests/<file>`.
- `preview/ui_preview.py`: tkinter mock-up of the SBP Wall form (no Revit). Run it with
  `python preview\ui_preview.py`, and keep it in sync with the form.
- `ref/soft_web_200_min.png`: Akash's reference drawing for the soft web rule.
- v2 plan (not approved yet): `C:\Users\NethajiAkash\.claude\plans\option-b-is-better-binary-shannon.md`.
- The old backup `SBP.extension_v1` was deleted (it would duplicate the SBP tab).

## Current logic (what the code does NOW: v1 spacing + editable walls, 25 Sep)
- Marks are `SBP1-H001` / `SBP1-S001`; Comments are `HARD PILE` / `SOFT PILE`. A wall's piles are
  found by exact wall name (`SBP1` never picks `SBP1-A`).
- Spacing: equal spacing over the whole centre line, interval count rounded UP. There are no corner
  piles and outside corners are rounded (the v2 corner rules are on hold).
- **Wall ends (Akash's rule):**
  - A free end is HARD, with no prompt.
  - If an end touches another wall's pile (any ICSPL_Pile not in this wall), the pattern continues
    from it. Nearest pile closer than c/c/2 = the same position: no new pile there, and the next pile
    is the other type. Closer than D = overlapping (e.g. a corner between two walls): the end pile is
    the other type.
  - The drafter is asked only if that pile's type can't be read.
  - The interval count parity follows the two end types (`divide(odd=...)`).
- **Settings per wall:** a DataStorage element with Extensible Storage (schema GUID fixed in
  `sbp_revit.py`) holds JSON: type, level, spacing, gap, cut-off, toes, invisible flag, line
  UniqueIds, original line styles, side, and the first line's direction (so the side survives
  reshaping).
- **SBP Edit:** changes to type, level, spacing or gap, or a moved line (detected by comparing the
  planned layout with the existing piles), cause a rebuild, confirmed once for all walls. Cut-off or
  toe changes only update the piles. Only the fields you change are applied to multi-wall
  selections.
- **Typed pile data:** on a rebuild (also an SBP Wall re-run), non-built-in instance parameters with a
  value are copied to the nearest new pile of the same type. The skip list is `DATA_SKIP`
  (X-Easting, Y-Northing, Depth...).
- **Levels:** `apply_levels` calibrates on one reference pile's current offset, depth and displayed
  Top/Bottom, so it works on fresh and on existing piles.
- **HARD/SOFT look (R8):** view filters `SBP HARD PILE` (solid) and `SBP SOFT PILE` ("Diagonal up
  1.5mm", created if missing) in the active view (it asks if the view template controls filters),
  and material `ICSPL_Pile` on "Structural Material". This runs in a separate transaction and never
  undoes the piles.
- Diameter is read from the type via a probe instance (Radius × 2), or from an existing pile in
  SBP Edit.
- Invisible line: `<Invisible lines>` is taken from `GetLineStyleIds()`, and the report shows a "Drawn
  line" row. **Not yet verified in Revit.**
- `remove_loops` bug fixed 25 Sep: an inclusive intersection test (tested: gap 200 inside corner → 800
  from the line).
- **None of the 25 Sep code has been run in Revit yet.** Only offline tests and static checks have
  run.

## Status
- **Done:**
  - Step 1: pyRevit 5.2.0 installed and attached to Revit 2026; the SBP tab loads.
  - Step 2: the first Revit run worked (43 piles, 22H/21S; cut-off/toe correct; 150 gap OK;
    SBP Count OK).
  - 25 Sep: editable walls (option 3), joins, HARD/SOFT look, `remove_loops` fix, offline tests
    (20 pass). See HISTORY.md §11.
- **NOT done:**
  - **The first Revit test of the 25 Sep code** (checklist in HISTORY.md §11).
  - The invisible-line fix is still unverified.
  - The v2 spacing rules (R2–R7) are on hold for the senior review of the drawing
    (https://claude.ai/artifact/ViXBhGCCNzFRQXTaJVkP1N) and the A/B question.
- **Exact next step:** Akash clicks pyRevit → Reload in Revit, then runs the §11 checklist in
  `TESTING MODEL\SBP TEST MODEL.rvt` and sends screenshots of each report. Fix what fails. Then,
  when he brings back the seniors' answer, continue with v2.
- Walkthrough preview of the buttons: https://claude.ai/artifact/MEb9pt9aLst1mHvLNRSsRB.
- Later ideas: schedules, an SBP Delete button, renaming a wall.

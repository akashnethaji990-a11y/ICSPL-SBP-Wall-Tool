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
2. Gap from line to SBP inner edge = 150 mm default, adjustable, **minimum 10** (was 150; changed by Akash on 28 Sep,
   `SD.MIN_GAP_MM`).
3. Everything adjustable. Since 30 Sep (HISTORY §29): a HARD and a SOFT pile type (may differ, diameters read
   from the types, never assumed); the design value is c/c HARD to HARD (HH, e.g. 2000).
   - The forms show three linked values: HH, cutting depth (Dh + Ds − HH)/2, leftover SOFT web HH − Dh
     (Ø1500 at 2000: cutting 500, web 500). The drafter types any one (`SD.changed_spacing` / `spacing_driver` /
     `hh_from`).
   - A typed cutting depth or web wins over a typed HH, and is saved per wall (`spacing_by` / `spacing_val`), so a
     new pile type moves HH to keep it. Web < 200 = warning (still placed); cut ≤ 0, web < 0, HH < Ds = error.
   - Line → SBP centre line = gap + max(Dh, Ds)/2.
   - The form fills HH = HARD diameter + 600 (`SD.default_hh`) when it opens and when the HARD type changes (Akash,
     6 Oct); still editable.
4. Report how many HARD and SOFT piles.
5. The drawn line becomes invisible (`<Invisible lines>`, like AutoCAD Defpoints).
6. Top = **Cut-off Level**, bottom = **Toe Level** (separate toe for hard/soft allowed).

## v3 layout: closing zone. BUILT 6 Oct (HISTORY §33), not yet run in Revit. Akash's drawing + rule
- **Exact c/c everywhere:** every gap = design HARD to SOFT s = HH/2 (chord between centres), through corners too.
  No corner adjustment.
- **Every shape (7 Oct):** straight, chain, arc, circle, spline, open or closed. The same chord walk is used everywhere;
  piles are never moved at corners or on curves.
- **Only the end / the seam is adjusted, only when needed (7 Oct):**
  - **Open wall, free end:**
    - case 1: the last design pile that fits is HARD -> stop there, no adjustment, the leftover line stays (way 'short');
    - case 2: it would be SOFT -> the end HARD goes on the line end and the last bays before it are shortened.
  - **Open wall, end joined to another wall:** the end pile stays on the line end, with its type from the join.
  - **Loop:** starts with a **HARD** at the drafter's start point (`SR._start_at`). The last bay into it stays exact
    (Akash's red pile), and the adjusted bays are just before it. Adjusting right at a corner start made the SOFTs
    overlap there (ES3: 12 warnings instead of 0).
  - A last bay within **10 mm** of the design HH is only spread over that bay (`SD.CLOSE_TOL_MM`, way 'tiny').
- **Adjusted bays:** first **1** SOFT, then the field "Closing SOFT piles (adjust)" N (default 3, saved per wall as
  `close_n`) up to 6. Each is shrink (one pile pair more) or stretch (same piles), chosen by rule B: the first N with a
  choice that passes (cut >= design, web >= min(200, design web), no same-type overlap), the closer one to s if both
  pass. If none passes, take the closest; the report warns, and for a loop it tips "start at the middle of a side".
  `G.layout_closing`, `_zone_ok`.
- **Corners:** checked, never adjusted. `G.bay_corners` gives each bay's corner angle; warnings and errors carry it.
- **Report:** `SD.bay_table` / `SR.bay_table` print every bay (H-S chords, H-H chord, web, cut, adjusted, corner, check).
- **Shapes** (D 1200, H-S 900, web 200; tests print the tables):
  - circle R5000: 36 piles, 3 bays at H-S 729.2;
  - rectangle 10 x 6 from a corner: no clean choice -> 6 bays H-S 952 (cut 248, WARN), corner H06-S06-H07 web 142 WARN;
  - rectangle 10 x 6 from mid-side: 5 bays H-S 734, clean;
  - 90 deg arc R8000: 1 bay H-S 880;
  - L 8 + 6 m: 3 bays H-S 781.
- **ES3 example** (from the drawing, 11,223 x 14,618, Ø1200, HH 1800): 3 bays shrink -> web 120 (fails); 3 stretch -> cut
  240 (fails). So **4 bays of HH 1440 (web 240, cut 480), 58 piles**. Corner webs 528/546/570.
- **Replaced v2 rules** (30 Sep - 6 Oct, layout 2; still in `G.layout_wall` / `SR.plan_wall_v2`, only to check those
  walls):
  - R2 "SOFT on every corner";
  - R3 leftover next to corners / at the far end;
  - R4 corner HARD c;
  - Option B;
  - short legs;
  - equal division of circles.
- **Kept:** R1 (ends HARD, loop even/alternating), sharp corners of the centre line, R7 `G.check_wall` on every pile
  (now also shows low webs across corners as WARNINGs), R8 graphics, values before writing (`SD.plan_rows` adds the
  closing zone and each adjusted bay by its marks), wall-end joins.
- **R8 Graphics:** view filters `SBP HARD PILE` (solid, grey RGB 201,201,201 since 2 Oct: `SR.FILL_RGB`) /
  `SBP SOFT PILE` ("Diagonal up 1.5mm", black) by Comments in the current view (ask if its template controls filters);
  material **ICSPL_Pile** on both types.
- **Layout versions:** saved `layout`.
  - 1 = equal spacing (`plan_wall_v1`);
  - 2 = v2 corner rule (`plan_wall_v2`);
  - 3 = closing zone (`plan_wall`).
  SBP Edit checks a wall with its own version, and any rebuild uses 3.
- **Superseded, don't implement:** pulling the soft pile outward, a D/3 soft limit, an equal-spacing mode.

## User's pile family (existing, do not rebuild)
- Family `ICSPL_Pile`, type e.g. `1200mm Bored Pile`, category **Structural Foundations**, level-based.
- Instance params:
  - `Level`;
  - `Height Offset From Level` (drives cut-off);
  - `Depth` (drives toe);
  - `Radius` (read-only, = Diameter/2 by a formula);
  - since 6 Oct a **TYPE** parameter `Diameter` (shared, IFC Parameters group). It was an instance parameter with
    default 1200, which is why every type read 1200 until then.
  - `Elevation at Top` and `Elevation at Bottom` (read-only);
  - `Structural Material` (was `<By Category>` in Project1).
- Family rule, confirmed in Revit: displayed Top = level + offset + 150, and displayed Bottom =
  level + offset − Depth. So the physical length = Depth + 150, and the script calibrates against the
  displayed Top/Bottom.
- Other params exist (Loading, Mline Text, BH Ref, Section, GEO-/PDS- analysis...). Don't touch them.
- **Other pile families work too (28 Sep, HISTORY §25):**
  - `SD.detect_pile_params` recognises the size / length / cut-off parameters by name.
  - Otherwise `SR.ensure_pile_spec` asks once and saves the answer in the model (`pile_families`).
  - Shift+Click on SBP Wall (`config.py`) sets up or corrects a family.
  - ICSPL_Pile keeps plain type names and `HOUSE_SPEC`.
  - `apply_levels` checks the Top / Bottom read-back (2 mm).
  - `tests/ipy_import_smoke.py` imports sbp_revit against the Revit API DLL in pyRevit's engine.
  - `ICSPL_Bored Pile` (2 Oct, HISTORY §30): size `Diameter` (diameter), cut-off `Height Offset From Level`, toe
    **`Length`** (`Depth` does nothing). Parameters are read/written via `SR._param` (prefers the writable one of
    two with the same name). Not yet confirmed in Revit.

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
  - `ERSS.tab/Piling.panel/bundle.yaml`: button order. The ribbon tab is **ERSS** (renamed from SBP on
    26 Sep so that other ERSS tools can go on it later). The tab name = the folder name.
  - `SBP Wall.pushbutton`: create a wall. **WPF window `SBPWallWindow.xaml` (30 Sep, HISTORY §29a)**: the three
    spacing boxes recalculate live (HARD to HARD is the master; `SD.linked_boxes`). Simple-prompt fallback if WPF
    is unavailable. Last-used values in `%APPDATA%\SBPTool\settings.json` (merged, not overwritten); per-wall
    settings saved in the model.
  - `SBP Edit.pushbutton`, `SBP Select.pushbutton`, `SBP Line.pushbutton`: new 25 Sep (see HISTORY §11).
  - `lib/sbp_draw.py`: draw-then-build for SBP Wall (26 Sep, HISTORY §14). PostCommand(ModelLine) →
    Idling handler (only while waiting) → env var `SBP_DRAWN` → re-posts the SBP Wall button
    (`CustomCtrl_%CustomCtrl_%ERSS%Piling%SBP Wall`, built from the tab/panel folder names by
    `_wall_cmd_id()`). SBP Wall uses `__persistentengine__ = True`.
  - `SBP Count.pushbutton`: counts HARD/SOFT per wall.
  - `SBP Diag.pushbutton` (2 Oct, HISTORY §31): read-only; why a NEW pile does not show in the view (vs an OLD one).
  - `Number.pushbutton` (28 Sep, HISTORY §19): layout-plan numbers (SP1/HP1 ...) into Mark. WPF dialog
    `NumberWindow.xaml` (event names bind to methods of `NumberWindow` in script.py).
- `tests/test_sbp_geom.py`, `tests/test_sbp_data.py`: offline tests. Run with `python tests/<file>`
  (7 Oct: geometry 49, data 34).
- `tests/ipy_layout_v2.py`: the v2 layout in pyRevit's IronPython 2.7 engine (same numbers as CPython).
- `tests/ipy_sbp_wall_wpf.py`: loads `SBPWallWindow.xaml` in that engine and checks the live spacing recalc.
- `tools/ipy_host.ps1` + `tests/ipy_number_wpf.py`: run a script in pyRevit's own IronPython 2.7.12 engine outside
  Revit (Number's imports and its XAML). Command: `powershell -STA -ExecutionPolicy Bypass -File tools\ipy_host.ps1
  -Py tests\ipy_number_wpf.py`. Any button that opens its own WPF window must `clr.AddReference` the WPF assemblies
  before `from System.Windows ...` (HISTORY §22).
- Button icons: `icon.png` (light Revit theme) + `icon.dark.png` (dark theme) in each `.pushbutton`,
  made by `tools/make_icons.py` (edit the SVGs there, run it, then pyRevit → Reload).
- `preview/ui_preview.py`: tkinter mock-up of the SBP Wall form (no Revit). Run it with
  `python preview\ui_preview.py`, and keep it in sync with the form.
- `ref/soft_web_200_min.png`: Akash's reference drawing for the soft web rule.
- v2 example drawing (30 Sep, drawn from the tool's own layout code): https://claude.ai/artifact/A3u7FsT18wYot4hxnUX4Wc
  (generator: `make_v2_drawing.py` in the session scratchpad, not in the repo).
- The old backup `SBP.extension_v1` was deleted (it would duplicate the SBP tab).

## Current logic (what the code does NOW: v2 layout 30 Sep + editable walls)
- SBP Wall gives marks `SBP1-H001` / `SBP1-S001` and Comments `HARD PILE` / `SOFT PILE`.
- **The wall identity is NOT the Mark any more (28 Sep):**
  - Each pile has hidden data `SBPPileData` (Wall, Kind, Seq = place along the wall).
  - `wall_of` / `kind_of` read that data first, then fall back to old marks for piles made before 28 Sep.
  - A wall's piles are found by exact wall name (`SBP1` never picks `SBP1-A`).
- **Number:**
  - Mark = prefix + number, in draw order. SOFT and HARD are counted separately.
  - The numbers run on across the walls of the same Level.
  - Continue = the highest mark with that prefix on the same level, ignoring the walls being numbered.
  - An SBP Edit rebuild clears the numbers and tells the user to run Number again.
  - **Labels (28 Sep, HISTORY §20):**
    - Number also places Structural Foundation tags in the current plan view. The settings are the tag type,
      the side per wall (Outside default, saved as `label_side`), the offset from the pile edge (**50** default)
      and the rotation (**Fixed 0 = horizontal in the view** default / Along / Across). Defaults changed in
      HISTORY §21.
    - **One label per pile, never stacked in rows.** The layout is `sbp_geom.place_labels`: own side, then the
      other side of the wall, then a small nudge, then along/across. It never overlaps and reports the labels it
      had to move.
    - Number tags carry hidden data `SBPNumberLabel`. A re-run moves the same tag, and a second one on a pile is
      deleted.
    - **Tag type dropdown (HISTORY §23):** it lists Structural Foundation, Multi-Category and Generic Model tags and
      Generic Annotations. Each type is test-placed on a pile in a rolled-back transaction. Types Revit refuses (a
      Generic Model Tag on a foundation, or an annotation without a text parameter) stay listed, with the reason
      and the family fix, and Next is disabled for them.
    - **Generic Annotation labels (HISTORY §24):** `place_pile_notes`.
      - The Mark is copied into the annotation's text parameter (`SD.pick_text_param`); it does not follow later
        Mark changes.
      - Hidden data `SBPNumberNote` (pile, angle) keeps one label per pile.
      - An SBP Edit rebuild deletes the wall's Number annotations.
    - `TAG_ANGLE_SIGN` needs checking in Revit.
- **SBP Wall never deletes or replaces piles** (26 Sep): the name field suggests the next free name, and
  an existing name is refused. Changing a wall = SBP Edit. Deleting = by hand.
- **Line sources for SBP Wall:** selected lines, **selected reference planes** (trimmed at their crossings,
  model lines made inside the wall transaction), lines just drawn with Revit's Draw tools, else start drawing.
- **Invisible line:** `<Invisible lines>`, else our line style `SBP Invisible` (added if missing) turned off in
  the view (asks before changing a template), else hide in the view.
- **SBP Edit loops:** select, Finish, form, Apply, next piles ... Esc ends (26 Sep, HISTORY section 16).
- **SOFT piles are cut by HARD piles** with Join Geometry (HARD cuts), done in SBP Wall and after SBP Edit
  rebuilds (not yet verified in Revit).
- Report text goes through `SR.html()` (pyRevit hides `<...>`). Invisible lines: Category.GetCategory
  → fallback: hide in the current view. Draw hand-off log: `%APPDATA%\SBPTool\draw_log.txt`.
- **Pile size (6 Oct, `SR.size_of` / `SR.type_size`):** read fresh every time, never cached:
  1. type parameter `Diameter` (Length, or Number = mm);
  2. a test pile + Regenerate, `Radius` x 2;
  3. the family set-up.
  The source shows in the form, the check report and SBP Diag.
- Spacing: v3 (see "v3 layout" above): `SR.plan_wall` -> `G.layout_closing` -> `G.check_wall`. Old walls only:
  v2 `SR.plan_wall_v2` (`G.find_corners` / `G.layout_wall`), v1 `SR.plan_wall_v1` (equal spacing, rounded corners).
- **Wall ends (Akash's rule):**
  - A free end is HARD, with no prompt.
  - If an end touches another wall's pile (any ICSPL_Pile not in this wall), the pattern continues
    from it. Nearest pile closer than c/c/2 = the same position: no new pile there, and the next pile
    is the other type. Closer than D = overlapping (e.g. a corner between two walls): the end pile is
    the other type.
  - The drafter is asked only if that pile's type can't be read.
  - The interval count parity follows the two end types (`divide(odd=...)`).
- **Settings per wall:** a DataStorage element with Extensible Storage (schema GUID fixed in
  `sbp_revit.py`) holds JSON: HARD type, SOFT type, level, spacing_hh + spacing_by / spacing_val, gap,
  cut-off, toes, invisible flag, line UniqueIds, original line styles, side, the first line's direction (so the
  side survives reshaping) and `layout` (2 = v2). `SD.VERSION` = 2; `SD.upgrade` reads version-1 walls (HH = 2 x
  spacing, SOFT type = HARD type, layout 1).
- **SBP Edit:** changes to a pile type, level, HH or gap, or a moved line (detected by comparing the
  planned layout, of the wall's own layout version, with the existing piles), cause a rebuild. The values of every
  wall are shown, then one Yes / No for all. Cut-off or toe changes only update the piles. Only the fields you
  change are applied to multi-wall selections; a typed cutting depth / web is applied with each wall's diameters.
- **Typed pile data:** on a rebuild (also an SBP Wall re-run), non-built-in instance parameters with a
  value are copied to the nearest new pile of the same type. The skip list is `DATA_SKIP`
  (X-Easting, Y-Northing, Depth...).
- **Levels:** `apply_levels` calibrates on one reference pile per pile type (HARD and SOFT may be different
  families): current offset, depth and displayed Top/Bottom, so it works on fresh and on existing piles.
- **HARD/SOFT look (R8):** view filters `SBP HARD PILE` (solid) and `SBP SOFT PILE` ("Diagonal up
  1.5mm", created if missing) in the active view (it asks if the view template controls filters),
  and material `ICSPL_Pile` on "Structural Material". This runs in a separate transaction and never
  undoes the piles.
- Diameters (HARD and SOFT) are read from the types via a probe instance (Radius × 2), or from an existing pile
  of that type in SBP Edit.
- **Type name = size (Akash, 5 Oct, HISTORY §32):** a type whose name says "<n> mm" must have that size value
  (`SD.size_name_mismatch`); SBP Wall blocks Next / stops, SBP Edit skips that wall with the message.
- **Spacing Compliance table** (`SR.spacing_compliance_table`): HARD to next HARD, SOFT to next SOFT, against
  D + 600 (Akash's 1 Oct request). R3's tight far end is kept on purpose (Akash, 5 Oct) and shows "Below".
- `settings.json`: SBP Wall now merges its keys (it used to overwrite Number's label settings); `soft_type` ""
  = same as HARD; an old `spacing` (HARD to SOFT) is read as HH = 2 x spacing.
- Invisible line: `<Invisible lines>` is taken from `GetLineStyleIds()`, and the report shows a "Drawn
  line" row. **Not yet verified in Revit.**
- `remove_loops` bug fixed 25 Sep: an inclusive intersection test (tested: gap 200 inside corner → 800
  from the line).
- **None of the 25 Sep code has been run in Revit yet.** Only offline tests and static checks have
  run.

## Status
- **Done:**
  - Step 1: pyRevit 5.2.0 installed and attached to Revit 2026; the SBP tab loads (now named ERSS).
  - Step 2: the first Revit run worked (43 piles, 22H/21S; cut-off/toe correct; 150 gap OK;
    SBP Count OK).
  - 25 Sep: editable walls (option 3), joins, HARD/SOFT look, `remove_loops` fix, offline tests
    (20 pass). See HISTORY.md §11.
- **NOT done:**
  - **The first Revit test of the 25 Sep code** (checklist in HISTORY.md §11).
  - The invisible-line fix is still unverified.
  - **The Revit test of v3** (closing zone, size reading, D + 600; HISTORY §33 test list). The v2 test list (§29) is
    replaced by it, and the short-leg question is gone.
- **6-7 Oct: v3 built (HISTORY §33, §34):**
  - closing zone: only when needed, 1 then 3..6, loop starts HARD with its last bay exact, open free end stops at the
    last design HARD;
  - size read from type `Diameter` first;
  - HH = D + 600 in the form;
  - bay table with corner angles.
  Not yet run in Revit.
- **30 Sep: v2 built (HISTORY §29), replaced by v3 on 6 Oct.** Drawing: https://claude.ai/artifact/A3u7FsT18wYot4hxnUX4Wc.
- **28 Sep:**
  - Number button built (HISTORY §19). Its labels (tags) were added in §20, and the Revit test lists are there.
  - Tab renamed ERSS (§18).
  - None of this is tested in Revit yet.
  - Preview: https://claude.ai/artifact/LUc6A85aiTBcFFLfxCVnyg.
- **Exact next step (morning of 26 Sep):**
  1. §11 step 1 passed (26 Sep); icons added (HISTORY §13). Akash reloads, then runs §11 steps 2–8 in
     `TESTING MODEL\SBP TEST MODEL.rvt` and sends screenshots of each report. Fix what fails.
  2. **Built 26 Sep, test in Revit (HISTORY §14):** was the new request (HISTORY §12): SBP Wall should open a Modify | Place tab with the Draw tools
     (Line, Arc, Circle, Spline, Pick Lines), like Revit's Wall tool, instead of drawing a Model
     Line first. Research `PostCommand(ModelLine)` + a hand-off (two clicks / DocumentChanged-Idling
     hook / 'SBP Line' style), then show him the options before coding.
  3. v2 is built (30 Sep): Akash tests it with the §29 list and answers the short-leg point.
- Git: repo on branch `main`; the initial commit c1ca1d8 has all the 25 Sep code. Caches are now in
  `.gitignore` and the .pyc files are untracked (26 Sep, not committed yet).
- Walkthrough preview of the buttons: https://claude.ai/artifact/MEb9pt9aLst1mHvLNRSsRB (v2 on 26 Sep, 9 steps
  covering everything up to HISTORY §16; see §17).
- Later ideas: schedules, an SBP Delete button, renaming a wall.

# Conversation history: Cowork session (24 Sep 2026)

Full record of the Cowork chat between Akash and Claude, in order. Read together with CLAUDE.md.

---

## 1. Setup
- Role chosen: **Engineering**, with a BIM focus (IC Singapore).
- Plugins already installed: Engineering, Design, Productivity, Cowork-plugin-management.
  No BIM/Revit/AutoCAD plugin exists in the marketplace.
- Akash asked for Revit + AutoCAD connectors. None exist. Suggested **Autodesk Product Help**
  (searches Autodesk help pages). Other ways Claude can reach Revit: the local pynet-bridge tool,
  computer use, and scripts/files (pyRevit, Dynamo, AutoLISP, IFC, CSV).
- Connected folders: `C:\Users\NethajiAkash\Claude` and
  `D:\01_SP-\OneDrive - IC Singapore\COMPANY SET UP` (the main working folder).
- Tried skill `/engineering:architecture` → wrote **ADR-001** (Dynamo vs pyRevit vs C#).
  Decision: pyRevit is the main platform, Dynamo for visual/geometry one-offs, C# only for heavy tools.
  Saved as `ADR-001_Revit_Automation_Platform.md`.
- Skipped the writing-voice setup.

## 2. SBP wall: which platform?
Akash: wants an SBP wall that works like a line-based family. Draw a line (straight, curved, circle,
any shape) → piles are created continuously along it. Asked: pyRevit or Dynamo?
Claude: **pyRevit (strong recommendation).** A true line-based Revit family can only be straight,
so the approach is one pile family plus a script that places piles along any curve.
Why pyRevit: a one-click ribbon button, handles any curve with accurate chord spacing, alternates
hard/soft automatically, easy to re-run, versionable in Git, survives Revit upgrades.
Dynamo only for quick one-off tests.

## 3. Requirements (Akash sent a plan sketch)
Sketch: three Ø1200 piles, HARD-SOFT-HARD. Hard-to-hard 1800, hard-to-soft 900, overlap 300 each
side (dims 300/600/300). Lines from top: "other structure" → 150 → inner edge of SBP wall → 600 →
centre line → 600 → outer edge.
1. The "other structure" line is what Akash draws; piles appear with the default dia and spacing.
2. Gap between the other structure line and the SBP inner edge = 150, adjustable, **minimum 150**.
3. All parameters adjustable (pile dia, c/c spacing).
4. Show how many hard and soft piles.
5. The other structure line should be invisible (like Defpoints).

Claude's derived rules: line → centre line = gap + D/2 = 750. Spacing is measured along the offset
centre line. Open line starts and ends HARD; a closed loop has an even count. After selecting the
line, the user clicks the side where the wall goes.

## 4. Answers to Claude's questions
- Revit version: **2026**
- pyRevit: not installed yet; Akash can install it (has Python).
- Vertical: top = **"Cut-off Level"**, bottom = **"Toe Level"**.
- Family: **uses his own family** (not script-built).

## 5. Akash's family (from a Properties screenshot)
`ICSPL_Pile`, type `1200mm Bored Pile`, Structural Foundations.
Constraints: Level (SEEPAGE BASE SLAB), Host, Height Offset From Level 0.00, Moves With Grids.
Text: Loading (kN), Mline Text, Tentative SPTN>50, Tentative SPTN>100, X-Easting, Y-Northing.
Material: Structural Material = ICsg_Pile. Division Geometry: BH Ref, Section, Zoning/Section.
Structural: Concrete Cover, Links, Main Rebar, Tentative Head.
Dimensions: Radius 600 (read-only), Depth 6000, Elevation at Top 3405, Elevation at Bottom -2745.
Structural Analysis: Excavation Level, GEO-D1C1/D1C2 Compression/Tension, GEO_SLS, PDS-... params.
Observation: 3405 − 6000 = −2595, but it shows −2745 (a 150 difference), so the script calibrates
against the displayed Elevation at Top/Bottom.

## 6. What was built
`pyRevit/SBP.extension/` with the SBP Wall and SBP Count buttons plus `lib/sbp_geom.py` (see CLAUDE.md).
Offline tests with D1200 / c/c 900 / gap 150:
| Case | Piles | H | S | Actual c/c | Min overlap |
|---|---|---|---|---|---|
| Straight 10 m | 13 | 7 | 6 | 833 | 367 |
| Circle R10 outside | 76 | 38 | 38 | 889 | 311 |
| Circle R10 inside | 66 | 33 | 33 | 881 | 320 |
| Square 20 m outside | 96 | 48 | 48 | 882 | 318 |
| Square 20 m inside | 84 | 42 | 42 | 881 | 319 |
| L + arc (open) | 33 | 17 | 16 | 898 | 302 |
A bug with inside corners on closed shapes (the seam corner) was found and fixed.
All pile centres are 750 from the line.

## 7. Where things stand
- **Not yet tested in Revit.**
- Open question: keep rounded spacing (the current approach, always ends on HARD) or exact 900 c/c
  with a shorter last gap?
- The empty backup folder `SBP.extension_v1` was deleted (it would have caused a duplicate SBP tab).
- Akash is moving to **Claude Code in VS Code** and wants to go one step at a time:
  Step 1 is installing pyRevit and loading the extension in Revit 2026.

## 8. Claude Code session (VS Code), 24 Sep 2026
**Step 1: install pyRevit + load extension: DONE (verified from disk).**
- pyRevit **5.2.0** (latest) at `C:\Program Files\pyRevit-Master`, attached to Revit 2026 (engine IPY2712,
  netcore) via `%APPDATA%\Autodesk\Revit\Addins\2026\pyRevit.addin`. Also attached to Revit 2024.
- Revit 2026 install: `D:\APPS\Revit 2026\` (running build shows as 2026.4).
- Extension search path in `%APPDATA%\pyRevit\pyRevit_config.ini`:
  `D:\01_SP-\OneDrive - IC Singapore\COMPANY SET UP\pyRevit`.
- On Revit start, pyRevit built `%APPDATA%\pyRevit\2026\pyRevit_2026_..._SBP.dll`; the cache contains
  `SBP.tab / Piling.panel / SBP Wall + SBP Count`. Script edits need no reload (read on click);
  new buttons / bundle.yaml changes need pyRevit → Reload.
- Akash confirmed the SBP tab (Piling panel: SBP Count, SBP Wall) is visible in Revit.
- Pre-check before Step 2: no Py3-only syntax, no non-ASCII, all divisions float-safe; rpw FlexForm is
  shipped in `pyRevit-Master\pyrevitlib\rpw` and the script's calls match its API; geometry re-test
  matches §6 (straight 10 m → 13 piles 7H/6S, 833 c/c). No code changes needed.
- Next: Step 2 is the first real run of SBP Wall in Revit (straight 10 m line first).

**Step 2: first real run in Revit: WORKED.** Akash used a real open chain (diagonal line, short line,
vertical line, arc, line) instead of the 10 m test line. Wall placed on the inside of the chain.
Report: D 1200, design 900 → actual c/c 886.4, min overlap 313.6, line→centre 750, centre line
37.228 m, open line, **22 HARD / 21 SOFT / 43 total**, cut-off/toe HARD −150/−10000, SOFT −150/−9000
(separate soft toe works). Plan screenshot: piles follow the lines, inside corner and arc look clean.
Properties check PASSED: SBP1-H014 (HARD PILE) Offset −300, Depth 9700, Top −150, Bottom −10000;
SBP1-S012 (SOFT PILE) Offset −300, Depth 8700, Top −150, Bottom −9000 (Level 1). Confirms the family
rule: displayed Top = level + offset + 150, displayed Bottom = level + offset − Depth, so the
physical top-to-bottom is Depth + 150 (a schedule using Depth as pile length reads 150 short).
Still pending: line invisible, 150 gap dimension, SBP Count output, spacing question (A rounded
vs B exact 900).

**Bug: drawn line did NOT become invisible** (tick was on: settings.json `"invisible": true`).
Old code looked for `<Invisible lines>` in `Lines` category SubCategories and swallowed any error
with `except: pass`, so it failed silently. Fix in SBP Wall script.py: `invisible_style(curve_el)` now
picks the style from `curve_el.GetLineStyleIds()` (what Revit allows on that line) by category
`OST_InvisibleLines` or name; failures are listed in the report ("Drawn line" row + "Line style
problem" lines with the allowed style names). Unused `GraphicsStyleType` import removed.
pynet-bridge had no active Revit instance, so this could not be tested live. Awaiting Akash's re-run.
Akash confirmed: 150 gap dimension OK, SBP Count OK. Spacing A/B question re-explained (he asked
what it meant).

## 9. Spacing and corner rules: decisions (24 Sep 2026, later in the Claude Code session)

### 9.1 Side note: VS Code "Python extension" popup
Akash pressed Run on `preview/ui_preview.py`. That file is a tkinter mock-up of the SBP Wall form: it
needs no Revit and places no piles. It was created outside this session (17:03). VS Code asked for a
Python extension because none is installed. It runs fine with `python preview\ui_preview.py`
(Python 3.13, tkinter 8.6). It is a copy of the form layout only, so update it when the form changes.

### 9.2 Spacing question: Akash's idea accepted
- Option A (current code): equal spacing over the whole wall (37.228 m → 42 × 886.4).
- Option B: exact 900 with one short last gap (37.228 m → 41 × 900 + 328).
- Akash: "B is better, or adjust the spacing only where a corner comes / the line changes angle."
  Accepted direction: **design c/c on straight runs, adjustments only next to corners** (at the far
  end if the wall has no corner).

### 9.3 Akash's answers, round 1
- **Wall ends:** an open (not fully connected) wall must **start and end with a HARD pile**.
- **Loops** (circle, square): at the connecting point the same pile type must never meet ("like a
  magnet"). So H/S alternate strictly all round, with an even count.
- **Styling:** in 2D, HARD = **solid fill** and SOFT = **"Diagonal up 1.5mm" hatch**. In 3D, use the
  material **"ICSPL_Pile"**, which is in his template.
- **Outside corners:** **sharp**, not rounded. The pile **on the corner is SOFT**, so only the soft
  pile gets cut more, following the hard-pile spacing. If the corner soft is cut more than usual, it
  may be pulled outward (towards the outer edge of the wall), still touching the hard piles. His
  example: Ø1200 → the soft's uncut middle is normally 600 and may go down to 400; the limit must change
  with the diameter. He also wrote "1:4 of the radius", which was unclear.
  **Superseded by the web rule in 9.4.**

### 9.4 Akash's answers, round 2 (FINAL rules)
Reference drawing `ref/soft_web_200_min.png` (AutoCAD): an inside 90° corner with a SOFT pile on the
corner and a HARD pile on each side. The "200" is the clear gap between the edges of the two HARD
piles, i.e. the uncut part of the soft that remains between them. In the drawing the corner SOFT sits
about 200 mm inside the corner point (see open question 9.7).

**SOFT PILE WEB RULE** (his spec, condensed):
- It applies to **every** soft pile at **all** angles: straight, gentle bends, 90° and sharper,
  inside and outside corners, arcs, circles and splines. **Soft stays SOFT on corners** (inside and
  outside).
- The uncut part of each SOFT pile between its two neighbouring HARD piles must be **≥ 200 mm**.
  Measure it as the clear gap between the two HARD pile edges, along the straight line joining their
  centres. So H–H centre distance ≥ D + 200 (1400 for Ø1200).
- At any bend angle at the soft pile: 2 × c/c × cos(bend/2) ≥ D + 200, so
  c/c ≥ (D/2 + 100)/cos(bend/2).
  Ø1200: 0° → 700 | 30° → 725 | 45° → 758 | 60° → 808 | 90° → 990.
  Even on a straight wall, c/c can never go below 700.
- Check it on every soft pile after placing, not only at corners.
- The 200 becomes a form field **"Min uncut soft web (mm)"**: default 200, minimum 200, remembered
  like the other settings.
- Keep the other rules: **HARD–HARD never cut (≥ D)**, **SOFT–SOFT never cut (≥ D)**, 150 gap to his line.
- If the rule forces c/c above the design c/c (e.g. 990 > 900 at 90°), do it, but put a **WARNING**
  in the report listing each such pile: mark, angle, c/c used, overlap left (D − c/c).
  If c/c ≥ D (no overlap at all; he said "about 120° and sharper"), show an **ERROR**.
- Report the **smallest web** found in the whole wall.
- On diameter: "if D = 800 (c/c 400) the max cut is 200 and the rest of the soft must be ≥ 200". So
  the minimum web is an absolute 200 mm (adjustable), not a fraction of D.
- **Views:** the HARD/SOFT filters go in the **current view** (the option he chose).
- **Process he asked for:** before coding, **draw an example graph** for him to confirm, showing the
  web, the H–H distance and the c/c at each soft pile for four cases: straight, 32° bend, 90° inside
  corner and 90° outside corner. Then update the code, test all shapes again, and record the rules in
  CLAUDE.md and HISTORY.md.

### 9.5 Claude's offline prototype (in memory only, nothing saved to disk)
- Ø1200, c/c 900, web 200: WARNING (c/c > 900) starts at a **77.9°** bend and ERROR (c/c ≥ D) at
  **108.6°**.
- Why the gap at the corner pile matters: at a 90° corner the two piles either side of the corner
  pile are √(g1² + g2²) apart. Shrinking those gaps makes same-type piles cut each other.
- **Latent bug in the current `sbp_geom.remove_loops`:** crossings that land exactly on a sample
  vertex are ignored. The inside-corner loop is then not removed, and piles land 188–218 mm from the
  line. Reproduced with gap 200 (offset 800). Planned fix: an inclusive intersection test.
  **NOT fixed yet.**
- The test chain modelled on Akash's real wall (angles estimated from his screenshot: ~32° and ~80°
  bends about 2 m apart) has a short leg where the symmetric formula cannot fit. Fallback: unequal
  corner gaps (e.g. 668 / 900 at the 32° bend), with H–H still ≥ D + web. If even that is impossible,
  drop that corner and say so in the report.
- Superseded ideas:
  - Pulling the soft pile out: the web is measured between the HARD piles, so moving the soft cannot
    change it.
  - The D/3 limit: replaced by the absolute web ≥ 200.
  - An "equal spacing" mode: not added. Loops with no corners (circles) automatically use equal
    spacing.
- Expected results with all v2 rules (prototype; Ø1200, c/c 900, web 200, gap 150):

| Shape | Piles | H/S | Gaps at 900 | c/c | Warn | Err | Min web |
|---|---|---|---|---|---|---|---|
| Straight 10 m | 13 | 7/6 | 8 of 12 | 700–900 | 0 | 0 | 200 |
| Straight 37.228 m | 43 | 22/21 | 39 of 42 | 709–900 | 0 | 0 | 219 |
| 32° bend | 31 | 16/15 | 16 of 30 | 714–900 | 0 | 0 | 200 |
| L 90° wall outside | 27 | 14/13 | 12 of 26 | 723–990 | 2 | 0 | 200 |
| L 90° wall inside | 23 | 12/11 | 12 of 22 | 712–990 | 2 | 0 | 200 |
| L inside, gap 200 (bug case) | 23 | 12/11 | 12 of 22 | 702–990 | 2 | 0 | 200 |
| Rect 20×12 outside | 80 | 40/40 | 56 of 80 | 720–990 | 8 | 0 | 200 |
| Rect 20×12 inside | 68 | 34/34 | 38 of 68 | 715–990 | 8 | 0 | 200 |
| Akash-like chain (short leg) | 37 | 19/18 | 20 of 36 | 668–924 | 2 | 0 | 200 |
| Circle R10 outside | 76 | 38/38 | equal | 888 | 0 | 0 | 575 |
| Circle R10 inside | 66 | 33/33 | equal | 880 | 0 | 0 | 559 |
| Jog 1 m (one corner dropped) | 23 | 12/11 | 4 of 22 | 697–990 | 2 | 0 | 200 |
| Triangle, 120° turns | 46 | 23/23 | 25 of 46 | 708–1400 | 6 | 6 | ERRORs expected |
| Ø1000 @ 750, L outside | 31 | 16/15 | 18 of 30 | 600–849 | 2 | 0 | 200 |

In every case: HARD–HARD and SOFT–SOFT ≥ D, all centres ≥ gap + D/2 from the line, open walls start
and end HARD, and loops alternate.

### 9.6 Plan (written, NOT approved: Akash stopped to shut down his PC)
File: `C:\Users\NethajiAkash\.claude\plans\option-b-is-better-binary-shannon.md`.
1. **Example drawing** page (HTML/SVG, private artifact), then STOP for his OK and the A/B answer
   (9.7). Panels:
   - Straight: 900/900 → H–H 1800, web 600. Minimum 700/700 → H–H 1400, web 200.
   - 32° bend, soft on the bend: 900/900 → H–H 1730, web 530 (minimum 728).
   - 90° inside corner: 990/990 → H–H 1400, web 200, overlap 210 → WARNING.
   - 90° outside corner: same numbers. The corner soft is 1061 from the structure corner (edge gap 461).
   - Extra: the short leg like his wall (unequal corner gaps).
2. `lib/sbp_geom.py`:
   - fix the `remove_loops` bug;
   - add `find_corners` (bends > 5°);
   - `offset_path` gets sharp miter corners and returns the corner anchors (rounded only for bends
     over 120°);
   - add `layout_piles`: legs between fixed points (open ends HARD, corners SOFT), H/S parity, corner
     gaps (preferred max(900, formula), may shrink to the formula), blocks of equal gaps ≥
     (D + web)/2 next to corners, and the short-leg fallback;
   - add `check_wall`, which checks every pile for web, same-type ≥ D, c/c > design (warning),
     c/c ≥ D (error) and distance to the line.
3. `SBP Wall` `script.py`:
   - add the web field and use the new layout;
   - report: corners, gaps at design, c/c range and smallest web, plus WARNING and ERROR tables;
   - a separate "graphics" transaction: filters `SBP HARD PILE` / `SBP SOFT PILE` (by Comments) in the
     current view, asking first if a view template controls filters; solid fill and
     "Diagonal up 1.5mm" (create it if missing); material ICSPL_Pile on the "Structural Material"
     instance parameter.
4. Update `preview/ui_preview.py`, README, CLAUDE.md and HISTORY.md.
5. New `tests/test_sbp_geom.py` with the table in 9.5.

### 9.7 Open question (to ask with the example drawing)
Where does the corner SOFT pile go?
- **A:** on the corner point. At 90°: c/c 990 and overlap 210, so a WARNING.
- **B:** moved inward along the bisector just enough to get the design overlap back, never closer
  than the gap to his line. At 90° that's about 134 mm, giving S–H 900, overlap 300 and no warning.
  This matches his drawing, where the soft is inside the corner.
- Claude recommends B.

### 9.8 Status when Akash shut down
- **Coded (on disk):** everything in §6, plus the invisible-line fix in SBP Wall `script.py` (§8).
  The fix is **not yet verified in Revit.**
- **NOT done:**
  - the Revit re-run to confirm the invisible-line fix;
  - the example drawing;
  - all v2 rules from 9.3–9.4: sharp corners, SOFT corner piles, the web rule and its form field,
    warnings and errors, checks on every pile;
  - the `remove_loops` bug fix;
  - HARD/SOFT view filters and the ICSPL_Pile material;
  - `tests/test_sbp_geom.py`;
  - preview and README updates;
  - approval of the plan.
- **Exact next step:** Claude builds the example drawing (plan step 1), shares the link and asks the
  A/B question (9.7). **No code changes until Akash says OK.** Separately, whenever Akash is in Revit,
  he can re-run SBP Wall on the same chain (wall SBP1, rebuild). The report's "Drawn line" row should
  then say `<Invisible lines>`.

### 9.9 25 Sep: example drawing published (no code changed)
- Akash asked for the example drawing only. He has more corrections to give, so wait for his word.
- Page "SBP Soft Web Rule": https://claude.ai/artifact/ViXBhGCCNzFRQXTaJVkP1N (private).
  Generator: `make_web_drawing.py` (session scratchpad, not in the project).
- Panels:
  - straight: 900/900 → web 600; minimum 700/700 → web 200;
  - 32° bend: 900/900 → H–H 1730, web 530;
  - 90° inside and 90° outside corners: 990/990 → H–H 1400, web 200, overlap 210 → WARNING; the
    outside-corner soft is 1061 from the structure corner;
  - short leg like his wall: the 32° corner gets unequal gaps 900 / 668 (H–H 1509, web 309); the
    81° corner gets 924 / 924 (web 200, WARNING).
- New finding shown on the page: with Option A at 90°, the 200 gap between the two HARD piles lies
  **outside** the SOFT pile (not filled). With Option B (SOFT moved 134 mm inward) it is filled, the
  overlap is 300, and the gap to the line is 245 at an inside corner (outside corner: the edge is 326
  from the structure corner).
- Waiting for: his corrections, OK, and A or B.

## 10. Editable walls: option 3 chosen (25 Sep)
- Akash will review the §9.9 drawing with his senior engineers. **Hold the v2 rules** until he asks
  about it again.
- He asked for editing: 100–200+ piles per wall, and the design keeps changing (levels, spacing,
  formation, shape). Options offered: (1) a Revit group per wall, (2) separate piles with
  multi-select editing, (3) **each wall remembers its settings** and is edited as one unit.
  **He chose 3.** No groups.
- He confirmed that engineers type data into single piles (Loading, BH Ref, SPTN, GEO/PDS...), so a
  rebuild must copy it to the new piles.
- Planned buttons: SBP Edit (levels-only edits keep the piles; spacing, gap, type, level or shape
  changes rebuild the wall), SBP Select (whole wall / HARD only / SOFT only), and SBP Line
  (show/hide the hidden line so it can be reshaped). Settings are stored per wall in an Extensible
  Storage DataStorage element (JSON). The full plan is in the plan file (NEXT section).
- Before approving the build, he asked for a moving preview.
  **Walkthrough page:** https://claude.ai/artifact/MEb9pt9aLst1mHvLNRSsRB (private). 7 animated steps
  on a mock Revit window, with counts from today's equal-spacing rule: 49 piles at 900, 51 at 850,
  57 after the line is longer. The self-test ran all steps with no errors.
- Point raised on the page for him to confirm: after a spacing change almost every pile moves more
  than 300 mm (in the example, H014's data lands on H015, 764 mm away). Proposal: copy from the
  **nearest old pile of the same type** and list any that moved more than half a c/c; the
  alternative is to keep the data with the mark number.
- **Waiting for:** his OK on the walkthrough and his answer on the data-copy point. Then build it.
  No project code has been changed for option 3 yet.

## 11. Editable walls built (25 Sep): not yet run in Revit
**Akash's decisions:**
- The walkthrough preview is OK.
- Data copy after a rebuild: **(a) nearest pile of the same type**.
- Build the **HARD/SOFT look now** (R8), not waiting for the v2 review.
- **Wall ends (his words):** "If the new wall is not connected to any existing SBP wall, start and end
  with HARD by default, no prompt. If it does connect to an existing wall, detect the pile at that
  connection point and continue the alternation from it, so HARD follows SOFT. Only ask me if the
  connection is found but the pile type cannot be determined."

**Built:**
- `lib/sbp_revit.py`: shared Revit helpers, moved out of the SBP Wall script, plus the new pieces.
- `lib/sbp_data.py`: pure Python.
- `SBP Edit`, `SBP Select` and `SBP Line` buttons.
- `Piling.panel/bundle.yaml` for the button order.
- `tests/`.
- SBP Wall now:
  - detects joins;
  - keeps typed data when re-run on an existing wall;
  - saves the wall settings in the model (DataStorage + JSON);
  - applies the HARD/SOFT look;
  - finds a wall's piles by exact name.

**Join rule as coded:**
- Take the nearest pile of another wall to each end of the new centre line.
- Closer than c/c/2 → the new wall continues from it: no pile placed there, and the next pile is the
  other type.
- Closer than D → the end pile is the other type (e.g. a corner between two separately drawn walls).
- Further away → free end, HARD.
- An unknown type → ask HARD/SOFT.
- The report shows "Start" and "End" rows. A near miss (within 2D but not overlapping) is noted.

**Also fixed:** the `remove_loops` vertex-crossing bug (HISTORY §9.5).

**Offline checks:**
- `tests/test_sbp_geom.py` passes 10/10. The old numbers are unchanged (straight 13 7H/6S, circles
  76/66, squares 96/84), and the gap-200 inside corner stays 800 from the line.
- `tests/test_sbp_data.py` passes 10/10.
- All .py files parse, there is no Python-3-only syntax, and no non-ASCII.

**Revit checklist for Akash** (after pyRevit → Reload, in `SBP TEST MODEL.rvt`):
1. The SBP tab shows 5 buttons in order: Wall, Edit, Select, Line, Count.
2. Run SBP Wall on the test line as SBP1 (rebuild). The report shows:
   - Start/End "free end: HARD";
   - "Settings saved with the wall";
   - Drawn line `<Invisible lines>`;
   - the HARD/SOFT look (2D);
   - Material (3D).
   In the plan, HARD is solid and SOFT is hatched.
3. SBP Select → HARD only → the HARD count matches the report.
4. Type Loading on one pile. SBP Edit → cut-off −150 → −300 → "levels updated, same piles kept".
   Properties shows Top −300 and the Loading is still there.
5. SBP Edit → c/c 850 → confirm → rebuilt. The Loading is on the nearest HARD pile (the report shows
   where it went).
6. SBP Line → the line shows → drag an end → SBP Edit → OK → the wall follows the line, which is
   hidden again.
7. Draw a second line starting where SBP1 ends → SBP Wall as SBP2 → its Start row says "continues from
   SBP1-H0xx (HARD), next pile SOFT".
8. Select piles of SBP1 and SBP2 → SBP Edit → change toe SOFT → both are updated.
Send a screenshot of each report, and of any error.

## 12. New request (25 Sep, night): draw the line inside SBP Wall, like Revit's Wall tool
**Akash:**
- He doesn't want to draw a Model Line first.
- Clicking **SBP Wall** should open a **Modify | Place** tab with the Draw tools, exactly like
  Revit's own Wall tool: Line, Arc, Circle, Spline, **Pick Lines**...
- The SBP wall is then made from what he draws. "This one will make it way easier."

**Claude's first thoughts (NOT decided; research in the morning, then show him options):**
- A pyRevit button can't host its own Draw panel. It can start Revit's own Model Line tool with
  `UIApplication.PostCommand(PostableCommand.ModelLine)`, which shows the Modify | Place Lines tab with
  every Draw option, including Pick Lines.
- The difficulty: a posted command starts only after the script ends, so the tool must notice when
  drawing is finished. Possible ways:
  - (a) two clicks: SBP Wall → draw → Finish/Esc → SBP Wall again picks up the new lines by itself
    (no selecting);
  - (b) fully automatic: a DocumentChanged/Idling event (pyRevit hook or ExternalEvent) opens the SBP
    form as soon as the line tool ends;
  - (c) draw with a dedicated line style "SBP Line", so the tool always knows which lines are wall
    lines.
- Check in Revit 2026 + pyRevit 5.2 which of these works reliably before promising anything.

**Status when saved:** nothing coded for this. The first Revit test of the 25 Sep code (§11 checklist)
is still step 1.

**Git:** Akash made the repo; the "Initial commit" (c1ca1d8, 25 Sep 03:04) holds all the 25 Sep code.
The `lib/__pycache__/*.pyc` files (from the offline tests) were committed by mistake; add
`__pycache__/` to `.gitignore`.

## 13. 26 Sep: ribbon icons
- After pyRevit → Reload, Akash's SBP tab showed the 5 buttons in order: Wall, Edit, Select, Line, Count
  (**§11 checklist step 1 passed**). They were text only, and he asked for icons like the preview.
- Added `icon.png` (dark lines, for Revit's light theme) and `icon.dark.png` (light lines, for his dark
  theme; pyRevit 5.2 picks it automatically) to each button folder. The designs are from the walkthrough,
  without the "NEW" badges:
  - Wall: line over H-S-H piles;
  - Edit: pile + pencil;
  - Select: dashed box;
  - Line: dashed line with grips;
  - Count: list.
- They are made by `tools/make_icons.py` (SVG → PNG with headless Edge, 96×96, transparent). Edit the SVG
  in that file and run `python tools/make_icons.py` to change them.
- `.gitignore` now ignores `__pycache__/` and `*.pyc`, and the two committed .pyc files were untracked
  (`git rm --cached`). Not committed yet.
- Next: Akash reloads to see the icons, then runs §11 steps 2–8.

## 14. 26 Sep: SBP Wall opens Revit's Draw tools (the §12 request), built but not yet tested
- The icons showed after Reload. Akash then asked why SBP Wall still said "Multiple / Finish / Cancel"
  (select lines) instead of the Wall-tool experience (§12 was only recorded, not built).
- He asked whether SBP Wall could switch to the existing Modify tab. Answer:
  - Yes: starting Revit's own draw command makes Revit show its existing Modify tab with the Draw
    panel. That is how the Wall tool works too.
  - The plain Modify tab has no Draw panel, and a custom contextual tab is not possible in the API.
  - The title will read "Modify | Place Lines".
  - He confirmed: "Yes, that is it".
- Checked before building:
  - Revit 2026 API docs: Idling is raised only "when Revit is not in an active tool".
  - pyRevit 5.2 supports an `app-idling` hook, but a temporary handler is used instead (no permanent
    cost).
  - The pyRevit button id is `CustomCtrl_%CustomCtrl_%SBP%Piling%SBP Wall`.
- Built:
  - `lib/sbp_draw.py` (start_draw / _on_idle / take_drawn / stop).
  - SBP Wall's `get_curve_elements()`: pre-selected lines → lines just drawn → otherwise start drawing.
  - `__persistentengine__ = True`, and a new tooltip.
  - Tests still 20/20; static checks clean.
- **After updating files, click pyRevit → Reload.** The persistent engine keeps the old modules until a
  reload.
- **Revit test for Akash:**
  1. Plan view, nothing selected → SBP Wall → the Modify | Place Lines tab with the Draw panel appears.
  2. Draw a line + arc chain → Modify → the SBP Wall form opens by itself → OK → click side → wall.
  3. Try Rectangle (closed wall), Spline, and Pick Lines on a slab edge.
  4. SBP Wall → Esc without drawing → nothing happens. Draw a normal Model Line later → SBP Wall must NOT
     pop up.
  5. Select an existing line → SBP Wall → works as before.
  6. If the form does not open by itself after drawing, click SBP Wall once more: it picks up the lines
     just drawn. Tell Claude, since it means the automatic hand-off is not working.

## 15. 26 Sep: Akash's Revit test of draw mode, and fixes
**Test results:**
1. The Draw panel opens: OK.
2. Draw chain → the form opens by itself: OK.
3. Rectangle and Spline: OK. **Pick Lines:** after picking, Enter/Esc did nothing. He can pick only
   element edges, but wants all kinds (lines, ref lines, imported CAD lines) plus **Tab** chain
   selection.
4. Esc without drawing: OK.

**Reported problems → what changed:**
- **"Line style problem" lines** in the report:
  - The report hid `<...>` text as HTML, so `<Invisible lines>` and the other bracketed style names
    showed as blanks.
  - The tool also did not find the invisible style for his model lines.
  - Fix: `invisible_style()` now takes `Category.GetCategory(doc, OST_InvisibleLines)` →
    GraphicsStyle, then the Lines sub-categories, then `GetLineStyleIds()`.
  - If Revit refuses the style, the lines are hidden in the current view instead
    (`view.HideElements`), and the report says so.
  - All report text goes through `SR.html()`.
  - SBP Line shows lines hidden this way again (`UnhideElements`).
- **"15 piles already exist ... Delete them and rebuild?"** every time he made a new wall:
  - The form reused the last name (SBP1), and SBP Wall treated that as a rebuild. That is also why
    typed data "moved 26–33 m".
  - Fix: **SBP Wall never deletes or replaces piles.** The name field suggests the next free name
    (`SD.next_free_name`: SBP1 → SBP2 ...), and an existing name is refused ("use SBP Edit to change
    it").
  - Walls from before 25 Sep: delete them by hand and make them again.
  - Data copy on an SBP Edit rebuild is now capped at 5 c/c (`match_nearest(max_dist)`).
- **SBP Edit "Edit" button next to Finish:**
  - The Multiple/Finish/Cancel options bar belongs to Revit, and the API cannot add a button to it.
  - Closest behaviour: select the piles → **Finish** opens the Edit form → its button is now
    **"Apply"**.
  - The prompt now says "Click the piles to edit (Tab = whole chain), then click Finish to open the
    Edit form".
  - Selecting piles first, then SBP Edit, skips Finish.
  - Asked him whether he wants a loop (edit again until Esc).
- **SOFT piles must be cut by HARD piles** (HARD has reinforcement): his 3D image showed full
  overlapping cylinders.
  - Fix: `hard_soft_pairs()` + `cut_soft_by_hard()` use `JoinGeometryUtils.JoinGeometry(hard, soft)`,
    and `SwitchJoinOrder` if needed so the HARD pile cuts.
  - This covers neighbours along the wall plus joined ends of other walls. It runs in the look
    transaction (SBP Wall) and after a rebuild (SBP Edit).
  - The report row "SOFT piles cut" gives the count and any failures.
  - Not tested yet: whether Revit allows joining these foundation piles.

**Pick Lines, for Akash:**
- Revit's Pick Lines ends with **Esc twice** or **Modify**; Enter does nothing there.
- **Tab** on a hovered line/edge highlights the whole chain, then one click picks it.
- CAD lines can be picked if the selection toggles allow it (bottom right of Revit: Select links /
  pinned / underlay).
- Existing model or detail lines: select them first (Tab works), then SBP Wall.
- Reference planes are not supported by Revit's Pick Lines (it can be added to SBP Wall if needed).
- `lib/sbp_draw.py` now writes `%APPDATA%\SBPTool\draw_log.txt` (start, each idle and the decision).
  If the form still doesn't open after picking + Esc Esc, send that file.

Tests: 22 pass (2 new: next free name, data-copy cap). Parse, IronPython and ASCII checks are clean.
**Reload pyRevit before testing.** Not committed.

## 16. 26 Sep: reference planes, own invisible line style, SBP Edit loop (built, not yet tested)
**Akash asked:**
1. "Add" reference planes as a source for the wall line.
2. For the invisible line: "if the line type is not there add one, if it is there use that one".
3. SBP Edit loop: yes.

**Built:**
- **Reference planes:** select them first, then SBP Wall.
  - `sbp_geom.chain_from_lines()` orders them by where they cross, trims at the crossings and keeps
    the far ends. Planes that stop up to 5 m short (`PLANE_REACH_MM`) still meet. Every plane
    crossing two others makes a closed loop.
  - `SR.plane_chain()` builds the line in memory. `SR.make_model_lines()` creates the model lines
    only inside the wall transaction, so a cancel leaves nothing behind.
  - Those lines are then the wall's lines (hidden, saved, editable with SBP Line/Edit). Moving the
    reference planes later does not move the wall.
  - Tested offline: single plane, L crossing, rectangle in random order, stopping short, parallel /
    too many crossings (errors).
- **Invisible line:** `<Invisible lines>` is built into every Revit model (it cannot be added). When
  Revit refuses it:
  - the line gets our line style **"SBP Invisible"** (a Lines sub-category: reused if there, added if
    missing);
  - that style is turned off in the current view (`SetCategoryHidden`). If the view template
    controls model visibility, it asks before doing it in the template;
  - last fallback: hide the lines in the view.
  - `is_invisible()` also treats "SBP Invisible" as hidden, so SBP Line works.
- **SBP Edit loop:** select → Finish (= open the form) → Apply → it asks for the next piles; Esc or
  Cancel ends. A cancelled form or "No" on the rebuild question goes back to picking. The report
  heading is "SBP Edit (1)", "SBP Edit (2)" ...
- Tooltips updated for SBP Wall and SBP Edit.
- Tests: 27 pass (15 geometry, 12 data). Static checks clean. Reload pyRevit before testing.

**Revit test for Akash:**
1. Select 2 crossing reference planes → SBP Wall → wall along the L.
2. Select 4 planes around a rectangle → closed wall.
3. Check the report's Drawn line row: `<Invisible lines>`, or "uses the line style 'SBP Invisible'".
4. SBP Edit: edit one wall, Apply → it asks again → edit another → Esc.
5. The SOFT piles cut row in the report, and 3D.

## 17. 26 Sep: walkthrough preview updated (no code change)
Akash: "all okay, now give animation preview for all so far we have done".
- Same link, version 2: https://claude.ai/artifact/MEb9pt9aLst1mHvLNRSsRB (shared "Anyone with the link").
- 9 animated steps, with pile counts worked out using today's spacing rule:
  1. Draw SBP1 with the Draw tools (line + arc), Esc → form → side: 43 piles (22 H / 21 S), c/c 873.2.
  2. SBP2 drawn from SBP1's end: "continues from SBP1-H022 (HARD), next pile SOFT", 12 piles.
  3. 4 reference planes → SBP3, closed, 30 piles (15 / 15).
  4. The name of an existing wall is refused (next free name SBP4).
  5. SBP Select, HARD only.
  6. SBP Edit loop: SBP2 cut-off -300 (same piles, data kept) → SBP1 c/c 850 → 45 piles, data
     H014 → H015 (635 mm, listed as "moved more than half a c/c") → Esc.
  7. SBP Line: drag SBP2's end +2 m → SBP Edit → 14 piles, line hidden again.
  8. 3D: SOFT cut by HARD, before/after.
  9. SBP Count.
- The page separates what Akash has confirmed in Revit from what was built on 26 Sep and is not yet tested.
- Source: scratchpad `sbp_tab_walkthrough.html` (`#selftest` runs all steps; `#scene6` opens one step).
- Version 3 (Akash: "I need with subtitle"): video-style subtitles at the bottom of the mock window explain
  every action and result. Each one stays up long enough to read. A "CC Subtitles: On/Off" button
  toggles them, and the browser remembers the choice.

## 18. 26 Sep: ribbon tab renamed SBP → ERSS
Akash: rename the tab to "ERSS" because more tools will be added later.
- The folder was renamed with `git mv`, from `SBP.tab` to `ERSS.tab`. pyRevit uses the folder name as the tab title.
  The panel (Piling), the buttons, the wall names (SBP1...), the marks and the extension folder
  (`SBP.extension`) are unchanged.
- `sbp_draw.py` used a fixed button id with the tab name in it (for the draw → form hand-off). It now
  builds the id from the folder names (`_wall_cmd_id()` → `CustomCtrl_%CustomCtrl_%ERSS%Piling%SBP Wall`),
  so later renames of the tab or panel folder cannot break it.
- Text updated: README, install.ps1, github/INSTALL.md, github/GitHub_Guide_Akash.md, tools/make_icons.py,
  preview/ui_preview.py. Tests: 27 pass.
- **Revit check:** pyRevit → Reload. There should be one **ERSS** tab and no SBP tab. Then SBP Wall → draw → Esc
  must still open the form by itself.

## 19. 28 Sep: Number button (layout-plan pile numbers), built, not yet run in Revit
**Request (pasted spec):** a Piling-panel button "Number" writes pile numbers into Mark (layout plans only). It
works in draw order from the wall's start end, e.g. SP1, HP1, SP2, HP2. The prefixes are editable (default SP / HP,
e.g. C1-SP). There are two radio buttons, "Continue from the last number" and "Start new at 1", and a live line
"continuing from SP7, next will be SP8". The numbering is continuous across walls "on the same layer". Nothing is
written until confirmed.

**Problem found and decided (Akash, 28 Sep):** Mark was the wall identity (`SBP1-H014` → wall SBP1), so SP/HP
marks would have cut the piles off from SBP Edit / Select / Line / Count and the joins.
| Question | Decision |
|---|---|
| Where the wall identity goes | **Hidden data on each pile** (Extensible Storage) |
| "Same layer" | **Same prefix, same Level**: Continue looks only at marks on the same level |
| SBP Edit rebuild of a numbered wall | **Clear + tell**: new piles get `SBP1-H001` marks, the confirm box and report say "run Number again" |

**Built:**
- `sbp_revit`: schema `SBPPileData` (GUID 66fb6159-0697-4757-947e-bc71f93daaae; fields Wall, Kind, Seq =
  place along the wall from the start end). `place_piles` writes it. `wall_of` / `kind_of` read it first, then fall
  back to the old marks, so walls made before 28 Sep still work. `wall_in_order()` sorts by Seq; for old piles it uses
  `SD.legacy_order` (H/S numbers from the marks, and positions when the counts are equal).
- `sbp_data`: `mark_number`, `max_number`, `check_prefixes` (empty, the same, or ending in a digit), `number_plan`
  (SOFT and HARD counted separately, continuing across walls per level), `range_text`, `continue_text`,
  `default_mark_parts`, `is_default_mark`, `legacy_order`, `natural_key`. There are 7 new tests (data 19 + geometry 15 pass).
- `Number.pushbutton`:
  1. Pick a pile of each wall in order, then press Esc (or pre-select: the walls go in name order).
  2. The WPF dialog `NumberWindow.xaml` has the 2 prefix boxes, the 2 radio buttons and a live yellow box with
     "Continuing from SP7, next will be SP8" plus each wall's range. Next is greyed out while a prefix is wrong.
  3. The confirm box lists each wall's range and any marks already used by other piles (Revit will warn about
     duplicate Marks).
  4. One transaction writes the marks. Old piles first get their hidden data.
  - An open wall starts HARD, so it reads HP1, SP1, HP2, SP2 ... (SOFT and HARD counters are independent).
  - Continue ignores the marks of the walls being numbered, so numbering a wall again does not continue from its own
    old numbers.
- SBP Edit: a rebuild clears the numbers, and the confirm box and the report row "Pile numbers" say so.
- SBP Count: counts from the hidden data (no more mark parsing).
- Icon: an orange "SP1" tag on a HARD+SOFT pair (`tools/make_icons.py Number`; the tool now takes icon names and
  waits for Edge to finish writing).
- The XAML was checked offline: it loads in WPF (PowerShell XamlReader, events stripped) and the layout looks right.

**Revit test for Akash (after pyRevit → Reload):**
1. The Piling panel shows Number between SBP Line and SBP Count.
2. Number → click a pile of SBP1 → Esc → the dialog shows SP/HP and Continue. The live line says "no SP numbers yet".
3. Next → confirm → the marks read HP1, SP1, HP2 ... from the wall's start. Check with a tag or schedule.
4. SBP Select / SBP Edit / SBP Count still find SBP1 after numbering.
5. Number on SBP2 (same level) with Continue → it starts after SBP1's last numbers.
6. Type C1-SP / C1-HP → the live line updates while typing. Start new → "Starts new at C1-SP1 and C1-HP1".
7. SBP Edit spacing change on SBP1 → the confirm box warns that the numbers are cleared, and the report says
   "run Number again".

**Preview (28 Sep):** https://claude.ai/artifact/LUc6A85aiTBcFFLfxCVnyg (private).
- An interactive mock-up of the ERSS tab. Click Number → pick walls → Esc → the dialog (editable prefixes, radio
  buttons, live line) → confirm → the marks are written along each wall.
- A demo with subtitles and zoom buttons.
- Example: SBP3 was numbered earlier (SP1–15 / HP1–15). With Continue, SBP1 gets SP16–SP36 / HP16–HP37 and
  SBP2 gets SP37–SP42 / HP38–HP43. Start new shows 30 duplicates in the confirm box.
- Source: scratchpad `sbp_number_preview.html` (`#selftest` runs the demo fast).

## 20. 28 Sep: Number places the labels (tags) too, built, not yet run in Revit
**Request:** three dialog controls for the labels:
- the side (inside / outside the pile line, default outside, per wall);
- the offset from the pile edge;
- the rotation (default along the wall at each pile).

Labels must not overlap on tight or curved runs like SBP3. Everything else in Number stays the same.

**Found:** the real Number only wrote Mark. The labels were drawn by the preview only. In Revit a label = a tag, so
Number now also places Structural Foundation tags in the current plan view.

**Built:**
- **Dialog** (`NumberWindow.xaml`): a "Labels" section under the unchanged prefix / Continue part.
  - **Tag type** (4th control, needed: which tag shows Mark; "No labels (marks only)" keeps the old behaviour).
  - **Offset from pile edge** (default 200 mm).
  - **Rotation**: Along the wall (default), Across, or Fixed + angle.
  - **Label side per wall**: Outside (default) / Inside, one row per wall, saved in the wall data (`label_side`).
  - The live box adds "(labels outside)" per wall and one "Labels: ..." line. Next is greyed out for a bad offset or angle.
  - The labels are off, with a note, when the view is not a plan or no foundation tag is loaded.
- **Inside / outside:** a closed wall uses its loop. An open wall: Inside = the side of the drawn line, from SBP Wall's
  saved `side`. Without data: the side the wall bends to, else left. The text is turned so it never reads upside down.
- **No overlap** (`sbp_geom.place_labels`, pure Python):
  - Each label is placed with its near edge `offset` from the pile edge.
  - A label that touches another label, any pile on that level, or another tag in the view moves out one row
    (up to 4, rows 100 mm apart).
  - Where that is not enough (the inside of tight corners or curves) it turns (along ↔ across), then goes to the
    other side of the wall.
  - The report counts the turned and moved labels, and lists any still touching.
- **Revit** (`SR.place_pile_tags`):
  1. Create tags (or reuse this type's existing tags on those piles, so a re-run never doubles them) with
     `TagOrientation.AnyModelDirection`, text along model X.
  2. Regenerate and measure each tag's box.
  3. Lay the labels out.
  4. Set `RotationAngle` (relative to the view's right direction), regenerate, then move `TagHeadPosition` so each
     box centre lands on its place.
  - A pile Revit refuses to tag is listed, and the rest are still tagged.
  - `TAG_ANGLE_SIGN` (sbp_revit.py) flips the turn direction if Revit turns the other way.
- **Transactions:** a TransactionGroup with the marks first, then the labels. A label error keeps the marks and is
  reported. Tag type, offset and rotation are remembered in `%APPDATA%\SBPTool\settings.json`.
- **Tests:** geometry 21 (6 new: inside sign, readable angle, a straight wall staggers in 2 rows when along, across
  fits in 1 row, the SBP3 rectangle inside/outside × along/across with no overlaps, SBP1's concave arc). Data 19 pass.
- **Found with SBP3 (7.5 × 5.5 m, 30 piles, 2.5 mm text at 1:200):**
  - Outside: 0 moved, along uses 2 rows, across uses 1 row.
  - Inside: 15 to 17 labels do not fit and go outside. There is never an overlap.
- **Preview v2**, same link (https://claude.ai/artifact/LUc6A85aiTBcFFLfxCVnyg):
  - the new controls;
  - the same layout ported to JavaScript;
  - a 3-part demo: defaults on SBP1/2, SBP3 Across, SBP3 Inside.

**Revit test for Akash** (plan view at 1:200, pyRevit → Reload; a foundation tag that shows Mark must be loaded):
1. Number on SBP1 + SBP2 with the defaults → one tag per pile. The labels read along the wall, 200 mm clear of the pile
   edge, staggered where needed, none overlapping.
2. Check the turn direction on the arc. If the labels turn the wrong way, set `TAG_ANGLE_SIGN = -1.0`.
3. Run again with Across → the same tags move and turn (no doubles).
4. SBP3 with Inside → the report counts the labels put outside.
5. In a 3D view → the labels are off with the note, and only the marks are written.

## 21. 28 Sep: label defaults changed, one label per pile (not yet run in Revit)
**Request:**
- Default rotation horizontal (0 deg), so every label reads left to right whatever the wall direction.
- One label per pile with its own number, and no SP/HP pair at the same place.
- A smaller default offset, just clear of the pile edge, not floating away.
- The inside/outside, offset and rotation controls stay as they are.

**Changed:**
| Item | Before (§20) | Now |
|---|---|---|
| Rotation default | Along the wall | **Fixed 0 = horizontal** (the Fixed angle is now measured from the view's horizontal) |
| Offset default | 200 mm | **50 mm** |
| Crowded labels | pushed out in rows (up to 4): looked like SP/HP pairs stacked | **never stacked**: 1. own side, 2. other side of the wall (next to the same pile), 3. a small nudge (at most 1.5 text heights out or 0.6 text lengths along, smallest first), 4. along/across only for those modes |
| Tags per pile | reused one tag of the same type | **one Number label per pile**: Number tags carry hidden data (schema `SBPNumberLabel`, GUID 8f251ee8-64c4-423d-ba51-a7cd2c6754a0); a re-run reuses it (changing its type if needed) and deletes a second Number/same-type tag on that pile. Other tags are left alone. |
| Remembered values | `number_offset` / `number_rotation` | new keys `number_label_offset` / `number_label_rotation`, so values saved by §20 cannot override the new defaults |

- The layout now runs in the view's own axes (`place_pile_tags`), so "horizontal" and "never upside down" are as
  seen on the sheet, also in a rotated view.
- The report says "one per pile, N new, M moved", and how many labels went to the other side or were nudged.
- **Tests:** geometry 22 (new: a horizontal wall alternates sides; a vertical wall keeps one side; no label is ever
  far from its own pile; SBP3 in/out × horizontal/along/across; the concave arc). Data 19 pass. The XAML loads.
- SBP3 with the defaults (outside, horizontal): 6 labels on the other side, 2 nudged, 0 touching.
- **Preview v3** (same link): the new defaults and a 3-part demo (defaults, Along on SBP3, Inside on SBP3).

**Revit test (after Reload):** Number on SBP1 + SBP2 with the defaults. Expect: every label horizontal and just
clear of its pile; on the bottom run, labels alternating above and below. Run it again: still one label per pile.

## 22. 28 Sep: Number failed in Revit: "ImportError: No module named Windows" (fixed)
- **Cause:** line 30 of Number's script.py, `from System.Windows import ...`, ran before any WPF assembly was
  referenced. pyRevit only adds those references when `pyrevit.forms` is imported, and that came later in the
  script.
- **Fix:** `import clr` plus `clr.AddReference` for PresentationFramework, PresentationCore, WindowsBase and
  System.Xaml at the top of the script, before any System.Windows import. This uses the same `clr.AddReference`
  style as `pyrevit/framework.py`.
  - Number is the only button with its own WPF window. SBP Wall and SBP Edit use rpw FlexForm, and the others use
    pyRevit forms; both add the references themselves.
- **Test**, run in pyRevit's own IronPython 2.7.12 engine outside Revit with the new `tools/ipy_host.ps1` +
  `tests/ipy_number_wpf.py`:
  - **.NET Framework engine**, without the new lines: the import fails (the bug is reproduced).
  - **.NET Framework engine**, with the fix: all 7 WPF names import. The real NumberWindow.xaml loads through
    `wpf.LoadComponent` as pyRevit does, with 16/16 named controls, the default rotation Fixed 0, and 3 events
    reaching the Python methods.
  - The same host also loads pyRevit's own SelectFromList.xaml, and binds Click / TextChanged / Checked /
    SelectionChanged.
  - **Revit 2026 engine (netcore)**: the imports pass. The window itself can't be checked on this PC, because
    PowerShell 7.6 runs .NET 10, where IronPython 2.7 cannot subclass a WPF Window. Revit 2026 runs .NET 8.
  - To rerun: `powershell -STA -ExecutionPolicy Bypass -File tools\ipy_host.ps1 -Py tests\ipy_number_wpf.py`
    (add `-Arg before` to see the old failure).
- **Revit check:** pyRevit → Reload, then run Number → the dialog opens.

## 23. 28 Sep: Tag type dropdown widened (Akash's ICSPL_Pile_Mark_Tag is a Generic Tag family)
**Request:** the dropdown listed only Structural Foundation tags. Also list Generic Annotation and Generic Model tag
families, so the custom Mark tag shows up. Keep the existing ones.

**Revit rule (told to Akash):** a tag can only be put on elements of its own category.
- Structural Foundation Tags and **Multi-Category Tags** can label a pile and read its Mark.
- A **Generic Model Tag** (the default category of Revit's "Generic Tag" template) is refused on a Structural
  Foundation.
- A **Generic Annotation** is not a tag and cannot read the pile's Mark.

**Built:**
- `SR.label_types`: the dropdown lists, in this order, Structural Foundation tags ("Family : Type", unchanged, so
  remembered names still match), then Multi-Category Tags, Generic Model Tags and Generic Annotations as
  "Family : Type  (category)". The name format is `SD.label_name`, tested.
- `SR.unusable_label_types`: before the dialog, each listed tag type is test-placed on the first pile in the
  current view, inside a transaction that is rolled back (no change to the model, nothing in Undo).
  - A type Revit refuses stays listed. Choosing it shows the reason and the family fix in the live box, and Next is
    greyed out.
  - The fix: open the family, Family Category and Parameters > Structural Foundation Tags (or Multi-Category
    Tags), save, load it again.
  - Generic Annotations are always marked "not a tag".
- The default is the model's default Structural Foundation tag, else the first usable one, else "No labels". A
  remembered type that is not usable is not preselected.
- The chosen tag type is activated before placing (a newly loaded type can be inactive).
- **Tests:** data 20 (new label_name), geometry 22, static checks clean. The pyRevit-engine XAML test still passes.
  The category listing and the test-place check need Revit.

**Revit check:**
1. Number → the dropdown shows ICSPL_Pile_Mark_Tag with its category.
2. If it says it cannot label piles, change the family category as above, reload the family, and run Number again.
   It then shows as a normal entry (a Structural Foundation tag, or "(Multi-Category Tag)").
- Open question: if Akash wants a Generic Annotation to work anyway, it would need a different method: place
  annotation symbols and copy the mark text into them. That text does not update by itself.

## 24. 28 Sep: Generic Annotation labels (Akash: "yeah go on"), built, not yet run in Revit
- **How it works:** choosing a Generic Annotation in the Tag type dropdown places one annotation per pile in the
  plan view, and copies the pile's Mark into a text parameter of the annotation.
- **Choosing the parameter:** the test-placement before the dialog (rolled back) lists the annotation's own
  writable text parameters. `SD.pick_text_param` takes "Mark", then a name with mark / number / no, then text /
  label / tag, else the first one.
  - The live box and the confirm box name the parameter.
  - An annotation with no text parameter stays listed, with the reason (give its Label an instance text
    parameter), and Next is off.
- **Layout:** the same as tags (`_lay_out`, shared): the defaults are horizontal and 50 mm; one label per pile;
  never overlapping; the other side or a nudge when needed.
  - Annotations are turned with `ElementTransformUtils.RotateElement` about +Z (counter-clockwise, sure) and moved
    with `MoveElement`.
  - In a turned view the box size is recovered by `G.unturned_size` (tested).
- **One label per pile:** annotations carry hidden data `SBPNumberNote` (GUID
  54ef95e8-ab50-443c-bcea-1cd21ff25f2f: Wall, Pile UniqueId, Angle), so a re-run moves, turns, re-types and
  re-numbers the same annotation.
  - Switching between tag and annotation deletes the old kind on those piles, and the report says "N old labels
    removed".
- **The copied text does not follow later Mark changes:** Number updates it on a re-run, and the report says so.
  - Tags vanish with their piles, annotations do not, so an **SBP Edit rebuild deletes that wall's Number
    annotations in every view** (`SR.delete_number_notes`). The report row "Pile numbers" gives the count.
- **Refactor:** `place_pile_tags` and `place_pile_notes` share `_view_frame`, `_lay_out` and `_stats`.
- **Tests:** data 21 (new pick_text_param), geometry 23 (new unturned_size), static checks clean. The
  pyRevit-engine Number test still passes. The placement code needs Revit.

**Revit test:**
1. Number, choose the Generic Annotation → the live box names the parameter.
2. Yes → one annotation per pile, horizontal, 50 mm clear, none overlapping.
3. Run again with the tag → the annotations are removed and the tags placed (and the other way round).
4. SBP Edit spacing change → the report says that the annotation labels were removed.

## 25. 28 Sep: other drafters' pile families (auto-detect + set up once), built, not yet run in Revit
**Question (Akash):** "What if the other drafters have their own family?" Before this, the tool was tied to
`ICSPL_Pile` and its Radius / Depth / Height Offset From Level. **Decision:** auto-detect, and ask once when not
recognised (saved in the model).

**Built:**
- `SD.detect_pile_params` (pure, tested):
  - size: Diameter / Pile Diameter / Pile Dia / Dia / D, then Radius / Pile Radius / R, then a name with "diam" or
    the word "dia", then "radius";
  - it skips bar / rebar / link / cage / casing / cover sizes;
  - length (toe): a writable instance Depth / Length / Pile Length ...;
  - cut-off: a writable instance Height Offset From Level / Offset from Host / Offset ...;
  - instance parameters win over type parameters.
  - Akash's family is recognised exactly as before (Radius × 2, Depth, Height Offset From Level). ICSPL_Pile also
    keeps a built-in fallback set-up (`HOUSE_SPEC`).
- `SR.pile_types`: ICSPL_Pile types by name, other families as "Type (Family)" (`type_label`).
  - It lists every Structural Foundation family that is set up, recognised, or has "pile" in its name.
  - Families without a placed pile are read from a probe in a rolled-back transaction.
- `SR.ensure_pile_spec`: SBP Wall (after the form) and SBP Edit (when the type changes) ask only for the roles that
  were not recognised, with the parameter values in mm; "is the diameter / is the radius" is one choice.
  - The answer is saved in the model (JSON key `pile_families` in the wall-settings storage), so every drafter
    gets it.
- **Shift+Click on SBP Wall** (`config.py`): pile family set-up. It lists every Structural Foundation type, asks
  all three roles again and saves them. It can set up a family that is not listed, or correct a wrong set-up.
- `SR.apply_levels`:
  - uses the family's own length / cut-off parameters;
  - **reads Top / Bottom back and refuses** (nothing placed) if they are more than 2 mm off the asked cut-off /
    toe, naming the parameters and pointing to Shift+Click. This protects against a family that moves its levels
    another way.
- Everything else follows the family:
  - `all_piles` holds any pile family, plus any SBP-tagged pile;
  - `is_sbp_pile` works for any family (old SBP1-H001 marks only count on ICSPL_Pile);
  - `diameter_of` / `radius_of` read the set-up;
  - the typed-data copy never copies a family's own size / length / cut-off parameters;
  - the label layout uses each pile's radius.
- SBP Edit matches a wall's type by its saved `type_uid`, so a "Type (Family)" name never looks like a type change.
- **Tests:**
  - data 23 (2 new: ICSPL_Pile recognised as before; other names, bar sizes ignored, unusual names asked);
  - geometry 23; 15 files static-clean;
  - **new `tests/ipy_import_smoke.py`:** `sbp_revit` imports in pyRevit's IronPython 2.7 against the Revit 2024
    API DLL, so every Revit class / enum / category it uses exists. RevitAPIUI is stubbed (it needs Revit).

**Revit test:**
1. SBP Wall → the pile type list still shows "1000mm Bored Pile" and "1200mm Bored Pile". A wall made with them
   works as before.
2. Load another pile family, e.g. a colleague's → it shows as "Type (Family)". Choose it → questions only if its
   names are unusual → the wall is placed, and the report shows its diameter.
3. Run it again with the same family → no questions.
4. Shift+Click SBP Wall → the set-up dialog; redo a family.

## 26. 28 Sep: minimum gap 150 → 10 mm
- Akash (from the SBP Wall form): "remove the minimum 150 mm, make it 10 mm".
- `SD.MIN_GAP_MM = 10.0`: SBP Wall and SBP Edit refuse a gap below 10 mm. The **default stays 150**.
- Form labels now say "(mm, min 10)" in SBP Wall, its fallback prompt and SBP Edit. `preview/ui_preview.py`,
  README and INSTALL.md were updated to match.
- Test: gap 10 and 100 are accepted, 9 is refused. Data 23 + geometry 23 pass.
- Note: the on-hold v2 rule R5 ("gap to the line ≥ 150") now means ≥ the minimum gap.

## 27. 28 Sep: HARD-to-HARD spacing field
- **Request:** Akash wants a HARD-to-HARD spacing field in the SBP Wall form. In his screenshot he had typed 2000 in
  "hard-to-soft" with a Ø1500 pile (family Bored Pile2, recognised by §25). Most likely that was meant as
  HARD-HARD; as hard-to-soft it is refused (no overlap).
- **Built:**
  - The SBP Wall form, its fallback prompts and the SBP Edit form now show "c/c spacing HARD to SOFT" and
    "c/c spacing HARD to HARD (= 2 x HARD to SOFT; change either one)". The HARD-HARD box is filled with
    2 x the remembered or saved HARD-SOFT.
  - `SD.resolve_spacing` (tested): only HARD-HARD changed → HARD-SOFT = HARD-HARD / 2; only HARD-SOFT changed → as
    typed; both changed and not 2:1 → a message ("change only one of them"); a blank box is ignored.
- Still one saved value (`spacing` = HARD-SOFT), so existing walls and SBP Edit rebuild detection are unchanged.
  The SBP Wall report adds a row "Design c/c hard-hard". The "must be less than the pile diameter" message now gives
  both spacings.
- `preview/ui_preview.py` got the same field. Its gap check now finds the Gap box by its label, not by position.
- **Tests:** data 24 (new resolve_spacing), geometry 23, 17 files static-clean.

## 28. 28 Sep: three linked spacing values (Akash's drawing), built, not yet run in Revit
**Request (drawing, Ø1500):**
- HARD to HARD 2000.
- "Cutting soft pile" 500: the overlap, where each HARD cuts the SOFT.
- "Leftover soft pile" 500: the uncut SOFT between the two HARD edges.
- "I need 3 of them; if I input any one the rest should arrange accordingly".
- This is only for straight and curved runs. At corners, keep what was fixed before.

**Built** (replaces the §27 two-box version; `SD.resolve_spacing` removed):
- Four boxes in the SBP Wall form, its fallback prompts, the SBP Edit form and `preview/ui_preview.py`:

  | Box | Value |
  |---|---|
  | HARD to SOFT | s |
  | HARD to HARD | 2 s |
  | Cut into each SOFT pile (overlap) | D − s |
  | Leftover SOFT between HARD piles | 2 s − D |

  The drafter changes any one.
- `SD.spacing_values`, `changed_spacing`, `spacing_from`, `check_spacing` (tested with Akash's numbers):
  - several changed boxes must agree;
  - the cut must be > 0;
  - the leftover must be ≥ 0, a new check: HARD piles never cut each other (decided rule R5).
- **SBP Wall:**
  - the form shows the values for the default pile type's diameter, read by `SR.type_diameter` (rolled-back
    probe);
  - after the form, the chosen type's diameter turns the changed box into s;
  - the report adds the design cut, the design leftover and the actual leftover on a straight run.
- **SBP Edit:** the form shows the first wall's values. A changed cut / leftover is applied to each wall with its own
  diameter, and then rebuild detection runs as before. The old "read pile size" transaction inside the line check
  was replaced by one diameter read per wall, before the checks.
- Only s is saved per wall, as before.
- **Tests:** data 25 (2 new), geometry 23, 17 files static-clean, and the import check against the Revit API passes.
- **Corners, still open:** today's layout is v1 (equal spacing over the whole wall, rounded so the c/c is never larger
  than the design). So straight runs also get slightly less than the design value (e.g. 900 → 873.2 on the test
  wall). Keeping the exact design value on straights and adjusting only at corners is the on-hold v2 rule set (R2–R7
  + the A/B question). Akash was asked whether to build it now.

## 29. 29–30 Sep: v2 built (HARD/SOFT types, three linked values, exact spacing, option B), not yet run in Revit
**Akash's decisions (29 Sep, then restated 30 Sep):**
- Build v2 now. Drive the layout from the design **HARD to HARD** c/c (e.g. 2000).
- Read the real HARD and SOFT diameters from each pile's family type, never assume. They can differ on one wall
  and between walls.
- Cutting depth (each side) = (Dh + Ds − HH) / 2; leftover SOFT web = HH − Dh. Ø1500 at 2000: cutting 500, web 500.
- The three values are linked: type any one, the other two follow. A cutting depth or web typed per wall wins;
  web < 200 = warning.
- Straights and curves keep the exact design spacing. Corners: as fixed before (R2–R7), option **B**.
- Show the values read and worked out per wall before anything is written.
- Also: "Show the 1500/2000 example first, must give cutting 500", then "run it now".

**Built:**
- `sbp_data`:
  - `spacing_values(hh, dh, ds)`, `hh_from`, `spacing_driver` (a typed cut / web wins over a typed HH, with a note;
    a cut and a web that disagree = error), `check_spacing` → (errors, warnings), `corner_web`.
  - `upgrade` (version-1 walls), `default_marks`, `plan_rows` (the values table).
  - `VERSION` 2, `MIN_WEB_MM` 200. `NUM_KEYS` / `REBUILD_KEYS` now use `spacing_hh` and `soft_type`.
- `sbp_geom` (pure, IronPython-safe):
  - `offset_path(..., sharp_deg)`: sharp outside corners (miter).
  - `chain_joints`, `find_corners` (bend > 5°, ≤ 150°), `turn_deg`, `seg_dist`, `line_dist`.
  - `layout_wall`: chord walk at s = HH/2. The leftover goes into a few equal reduced gaps (≥ web min(200, design)):
    at the far end without corners, next to the corners otherwise.
  - Corner HARD at max(s, (Dh + web)/(2 cos(b/2))). Option B moves the corner SOFT along the bisector until it is
    s from both HARD piles, limited by the gap to the line.
  - Short legs: shrink c → equal reduction (low web) → one shared HARD → drop the smaller-bend corner.
  - A circle is divided equally.
  - `check_wall`: every pile.
- `sbp_revit`:
  - `plan_wall(…, dh, ds, …)` (v2) and `plan_wall_v1` (old walls, only to detect a moved line).
  - `place_piles(doc, {HARD: type, SOFT: type}, …)` and `apply_levels` calibrated per pile type.
  - `wall_data` saves the SOFT type, `spacing_hh`, `spacing_by`, `spacing_val` and `layout` 2.
  - `plan_rows` wraps `SD.plan_rows`; `load_walls` applies `SD.upgrade`.
- **SBP Wall:**
  - Form: HARD type, SOFT type ("(same as HARD)" default), three boxes.
  - Order: diameters from both types, then the side click, then plan + check. The values table goes to the report
    and a Yes / No box ("check before placing") comes up. Only then the transaction.
  - `settings.json` is merged, no longer overwritten (Number's label settings were lost before). Old `spacing` is
    read as HH = 2 x spacing.
- **SBP Edit:**
  - Same form changes. Each wall keeps its own saved spacing value (so a new SOFT type keeps a saved cutting depth
    and moves HH).
  - Old walls are compared with their own v1 layout, so a cut-off change does not rebuild them. Any rebuild uses v2.
  - Every wall to change is shown (rebuild table / level changes), then one Yes / No.
- `preview/ui_preview.py`, README, bundle tooltip updated.

**Checked offline:**
- geometry 36 tests (14 new v2), data 30 (7 new), 16 files static-clean.
- `tests/ipy_layout_v2.py` gives the same numbers in pyRevit's IronPython 2.7 engine.
- The import check against the Revit API passes.
- Numbers (Ø1500/1500, HH 2000, gap 150):

  | Case | Result |
  |---|---|
  | Straight 13.7 m | 15 piles, 12 × 1000 + 2 × 850 at the far end, web ≥ 200, cut 500 |
  | 90° corner | HARD 1202 from the corner, SOFT moved 323, S-H 1000, web 200, SOFT edge 200 from the line (line inside) |
  | Gap 10 | the move stops at 315 (edge 10 from the line): warning, cutting < 500 |
  | Rectangle 14.304 × 8.404 | 22 H + 22 S, 2 reduced gaps, 0 warnings |
  | HARD 1500 / SOFT 1200 | cut 350, web 500 |
  | 30° bend | nothing moves, web 432 |

**Found while building (shown to Akash as panel 8):** the leftover of a run can be up to one whole HH (2000), and
each gap can only give 150 before the web drops below 200. A leg shorter than about 14 gaps often cannot take it.
Then every gap of that leg is reduced equally (e.g. 6 m legs at a 90° corner: 6 × 800, web 99, cutting ≥ 500, one
warning per SOFT). The alternative (gaps above 1000 = less overlap) was not chosen because "reduce only if required
for overlap". Asked Akash to confirm.

**Drawing:** https://claude.ai/artifact/A3u7FsT18wYot4hxnUX4Wc (panels 1–8 to scale; 7, 8 and the values table come
from the tool's own code; the script asserts that panels 3 and 5 match the code).

**Incident:** a scratch patch script opened `tests/test_sbp_data.py` for writing with a bad `newline` argument, which
emptied the file. It was rebuilt from HEAD plus the previous session's edits (replayed from the transcript). All 25
tests came back at their original line numbers, and it was then updated for v2.

## 29a. 30 Sep: SBP Wall dialog is now a live WPF window (two bugs Akash reported)
- **Bug 1 (no live recalc):** the rpw FlexForm could not recompute. Replaced the SBP Wall form with a WPF window
  `SBPWallWindow.xaml` + `SBPWallWindow` (same pattern as Number). HARD to HARD is the master and always sets
  cutting depth and leftover web live (1500/1500 at 2000 -> 500 / 500, not 600 / 300); typing a cutting depth or
  web drives HARD to HARD instead; changing HARD to HARD again restores the computed defaults; changing a pile type
  recomputes from the new diameters. `SD.linked_boxes(driver, value, dh, ds)` holds the pure logic (tested).
- **Bug 2 (clearing a box crashed in fmt_num):** `SD.fmt_num(None)` now returns "" instead of `float(None)`. In the
  window a blank box just blanks the derived boxes; on OK an empty required field is reported, not crashed.
- Diameters for the live form are read once up front (`type_diameter` per offered type, rolled back); a family not
  set up yet reads None and the window says the size is read after Next. The authoritative diameters are still read
  after the type is chosen. `spacing_by` / `spacing_val` (the box the drafter set) flow straight through; the main
  script resolves HARD to HARD with `SD.hh_from`. The simple-prompt fallback path is kept for when WPF is absent.
- **The corner SOFT clarification (Akash):** confirmed the code already slides the corner SOFT inward along the
  bisector only, never resizes it (diameter comes from the type; only the centre moves), and keeps the same typed
  clearance (edge >= gap) as every other pile; it stops at the gap and warns rather than crossing the line. Locked
  in by `test_v2_corner_soft_keeps_the_typed_gap_and_never_crosses_the_line` (gaps 150 / 100 / 50 and a tight case).
- **Checked offline:** data 31, geometry 37; `tests/ipy_sbp_wall_wpf.py` loads the XAML in pyRevit's IronPython 2.7
  engine and confirms the live recalc (HH2000 -> 500/500, cut350 -> HH2300/web800, cleared -> blank, no crash).

**Test in Revit (after pyRevit → Reload):**
1. SBP Wall form (now a live window): type HH 2000 with Ø1500 -> cutting and web update to 500 / 500 as you type.
   Clear the HH box -> cutting and web go blank, no crash. Type a cutting depth -> HH and web follow.
2. Type cutting 450 → HH 2100 ("typed now", wins). Type web 150 → placed with a WARNING.
3. The table and the Yes / No box come before anything is placed; No places nothing.
4. Rectangle line 12 504 × 6 604, wall outside → 22 + 22. Dimension a straight c/c (1000), a corner SOFT to HARD
   (1000) and the corner web (200).
5. HARD 1500 + SOFT 1200 types → cutting 350; Cut-off / Toe correct on both types (levels per type).
6. SBP Edit on an old (v1) wall: cut-off only → piles kept. A spacing change → rebuilt with v2.
7. Number still works on a v2 wall; its label settings survive an SBP Wall run.

## 29b. 30 Sep: live preview tab in SBP Wall dialog (Akash asked)

**Request:** whenever any value changes, show a live preview of the pile setout and an animated
version showing how piles sequence. Separate tab, refreshes automatically while working, nothing
written to the model until confirmed.

**Built:**
- `SBPWallWindow.xaml` updated to a `TabControl`: Settings tab (the existing form, unchanged) +
  Preview tab (756×220 `Canvas`, info text, Play/Pause button and counter).
- Window widened from 560px to 800px; OK/Cancel buttons moved to the footer outside the tabs so
  they are always visible.
- `_update_preview()` called at the end of every `_apply()` (every spacing or type change):
  runs `G.layout_wall` on a straight placeholder line of 8 × HH (about 9-10 piles visible) and
  redraws the canvas.
- `_draw_preview(centres, kinds, dh, ds, hh, anim_step=None)`:
  - centre line (light gray horizontal), pile circles, dimension annotation (HH span above the first
    pair of HARD piles).
  - HARD: solid dark circle (#1e1e1e fill) + white "H" label.
  - SOFT: diagonal hatch brush (DrawingBrush, 6px tile, `TileMode.Tile`, transparent background so
    the canvas white shows through) + black "S" label.
  - `anim_step=N`: first N+1 piles shown, Nth highlighted orange; remaining piles shown as ghosts.
- Play/Pause button → `DispatcherTimer` at 300ms / pile, loops from the first pile to the last.
  Stopping restores the static full view.
- `_make_soft_brush()` module-level helper with try/except fallback (light gray if DrawingBrush
  unavailable in the pyRevit environment).
- All preview code is guarded by `_PREVIEW_OK` so the window still loads in older pyRevit versions.
- `cancel_click` / `ok_click` stop the timer; a validation error on OK switches back to the Settings
  tab to show `live_tb`.
- Test file `tests/ipy_sbp_wall_wpf.py` updated: 5 new control names added to the NAMES list.

**Offline verified:** data 31 pass, geometry 37 pass; static checks 0 problems.
**NOT yet run in Revit.** Add steps 8-9 to the §29a test list when testing:
8. Preview tab: type HH 2000 (Ø1500) → Preview tab shows ~9 piles HARD-solid / SOFT-hatched,
   dimension "2000" above first H-H pair. Switch HH to 2500 → preview updates automatically.
9. Play → piles light up one by one (orange highlight), counter shows "Pile X of N", loops.
   Pause → static view restores. OK on the Preview tab → it switches to Settings for validation.

## 30. 1–2 Oct: dialog levels, spacing compliance, other pile families (Akash's Revit runs)
- SBP Wall dialog: Cut-off always opens at **0**, Toe HARD at **-20000** (not read from settings.json; cut-off is no
  longer saved there). Live line "Pile depth = cut-off - toe - 150"; Next is disabled when it is <= 0.
- Report: "Spacing Compliance" table (actual c/c vs diameter + 600) in SBP Wall and SBP Edit (`SR.spacing_compliance_table`).
- `diameter_of` refuses a size outside 50–5000 mm (a wrong set-up gave 14000) and points to Shift+Click.
- **Family `ICSPL_Bored Pile` (seen in Revit):** size = type parameter `Diameter` (1500, "it is the diameter"); cut-off =
  `Height Offset From Level`; toe = **`Length`** (14000 on a new pile). `Depth` exists but does NOT move the bottom
  (with Depth: asked toe -20000, Revit showed -14000 = top - Length).
- Earlier "'Length' is missing or read-only": likely two parameters named Length on the pile (Revit's read-only one +
  the family's). Fix: `SR._param` takes the writable one (`GetParameters`), used by `set_param` / `get_len` and the
  pre-check in `_levels_of_type`. New read-back message when only the toe is wrong: "the toe parameter does not move
  the pile bottom, pick the one equal to the pile length".
- **Next (Akash):** Reload → Shift+Click SBP Wall → `1500mm Pile (ICSPL_Bored Pile)` → Diameter 1500 (diameter) →
  Height Offset From Level → **Length = 14000 mm** → SBP Wall: report must show Top 0 / Bottom -20000.

## 31. 2 Oct: new piles vanish in the ES3 base slab plan; SBP Diag button; IntegerValue crash
- Akash (screen recording): SBP Wall placed 13 piles (7H/6S, `1200mm Bored Pile`, level BASE SLAB LEVEL, cut-off 0,
  toe -14000) in view "ESCAPE SHAFT 3 (ES3) BASE SLAB LEVEL LAYOUT Copy 1 Copy 1". They show blue (SBP Wall selects
  them at the end), then vanish on deselect; old piles show. The SBP view filters are not the cause (fill only).
- New button **SBP Diag** (read-only, last in the Piling panel): NEW vs OLD pile table (level, offset, depth/toe
  parameter, Elevation at Top/Bottom, real top/bottom vs the view range, phase + phase-filter status, workset +
  visibility, design option, comments, mark, hidden, category hidden, crop, element overrides, each view filter,
  "Revit counts it visible"), the view's range / phase / template / filters / crop, then the reason in plain words.
  With nothing selected the newest SBP pile is NEW and the drafter clicks an OLD pile.
- Suspect: cut-off 0 (the dialog default since 1 Oct) puts the piles above the cut plane of a deep shaft's plan.
  **Fix for SBP Wall waits for the Diag result** (Akash wants the cause and plan first).
- `spacing_compliance_table` crashed in Revit 2026 (`ElementId.IntegerValue` removed): now `_idv` (Value, fallback
  IntegerValue). It was the only use.
- First Diag run crashed: `AttributeError: Name` on `e.Symbol.Name` (IronPython `.Name` on a type). Fixed: `safe_name`
  (Element.Name.GetValue, then .Name, then SYMBOL_NAME_PARAM / ALL_MODEL_TYPE_NAME, then str) for every name; each
  table row and each "why" check now catches its own error and prints it instead of stopping the report.
- HARD pile 2D fill colour: Akash's swatch = RGB 201,201,201 (was black). `SR.FILL_RGB` (sbp_revit.py line 51);
  `_overrides(pattern, rgb)`. Applied whenever SBP Wall / SBP Edit set the view filters in the active view.

## 32. 5 Oct: SBP9 piles drawn 1200 for type "1300mm Bored Pile"; far end tighter than 1800
- Akash's picture: Ø1200 dimension = 158 px; HARD to HARD at the far end ~1416 (typed 1800, settings.json).
- **Size:** `1300mm Bored Pile` (house family) was not in the 2 Oct type list, so it was made after, most likely by
  duplicating `1200mm Bored Pile` without changing its size value. The tool reads the value (Radius x 2); with
  1300 read, its minimum HH (D + 200) would be 1500, but the model shows ~1416, so it read 1200.
  **Akash's rule: a type's name and its size value must be the same.** New `SD.name_size_mm` /
  `SD.size_name_mismatch` (first "<n> mm" in the type name, 1 mm tolerance; names without it are not checked).
  SBP Wall: red message in the dialog (Next disabled) and a stop after Next; SBP Edit: that wall is not changed
  (error note). Fix in Revit: Edit Type > size 1300, then SBP Edit on SBP9 rebuilds it.
- **Spacing:** offline v2 layout (Ø1200, HH 1800, straight 12.9 m): 1800 x4 then 1424 x4 at the far end = rule R3.
  **Akash: keep R3 as now** (other choices shown: spread bigger, spread smaller, both ends).
- **Bug fixed:** Spacing Compliance compared each pile with its neighbour (the other type, ~HH/2) against D + 600,
  so every pile was "Below". Now HARD to the next HARD and SOFT to the next SOFT (`SR._same_kind_neighbours`,
  wraps on a loop). Note: Ø1500 at HH 2000 shows "Below" everywhere (2000 < 2100); R3's tight far end shows "Below".
- Offline: data 32, geometry 37; IronPython compile of SBP Wall / Edit / Diag, import smoke, WPF test OK.

## 33. 6 Oct: v3 closing zone, size read from type "Diameter", HH = D + 600
**Size (Task 1).** Akash made `Diameter` a TYPE parameter of ICSPL_Pile (shared, IFC group; Radius = Diameter/2).
It was an instance parameter with default 1200, so every new pile, including the tool's test pile, got 1200 whatever
the type. My 5 Oct "the type's value is 1200" was wrong. With his change every code path reads 1300. If the dialog still
shows 1200, the cause is a saved Shift+Click set-up for ICSPL_Pile, or the old family still being in the model.
Sizes are never cached, and settings.json has none.
- New reading order, `SR.size_of` / `SR.type_size`:
  1. type `Diameter` (Length, or Number = mm);
  2. a test pile + Regenerate, `Radius` x 2;
  3. the family set-up.
- The source shows in the form ("HARD 1300 / SOFT 1300 (type parameter 'Diameter')"), in the check report, in SBP
  Edit and in SBP Diag (3 new rows).
- The old `fi.Symbol.Name` in an error message (IronPython AttributeError) is gone.

**Closing zone (Task 2, Akash's drawing).**
- Every gap is exactly s = HH/2 (chord), through corners too. The leftover goes only into the last N bays (field
  "Closing SOFT piles (adjust)", default 3, max 6, saved per wall `close_n`), spread equally.
- Akash's choices: rule **B** (the first N that passes every check, closest to the design), and a loop starts **HARD**.
- Loop seam: the first prototype put the zone right against the start corner. Its last SOFT came 1152 from the first
  SOFT across the 90° corner (48 mm overlap, ERROR; my first example missed it because it printed only warnings).
  Now the last bay into the start HARD stays exact and the zone is just before it, as in Akash's drawing (red end
  pile between the zone and the start).
- **ES3** (measured from the drawing: centre line 11,223 x 14,618 = 51,682; Ø1200, HH 1800). The leftover after exact
  900 steps is ≈ 360 (each step across a corner uses more line):
  - 3 bays: shrink gives web 120, stretch gives cut 240; both fail;
  - **4 bays shrink: HH 1440, web 240, cut 480, 58 piles (29 H + 29 S), no warnings**;
  - corner webs 528 / 546 / 570.
- Replaced v2 rules (kept only to check v2 walls): SOFT on every corner, R3, R4, option B, short legs, equal circles.
- Layout versions 1 / 2 / 3. SBP Edit checks each wall with its own version; any rebuild uses 3, and the report says
  "rebuilt with the closing-zone layout".

**D + 600 (Task 3).** The form fills HH = HARD diameter + 600 when it opens and when the HARD type changes; still
editable (`SD.default_hh`). The fallback prompts start from it too.

**Offline:** geometry 44 (7 new v3 tests), data 34 (2 new); IronPython: v3 numbers equal CPython (58 piles / 1439.68,
17 piles / 1425.00), the WPF form loads 20 controls, all buttons compile, import smoke OK.

**Revit test list (Akash):**
1. Reload. SBP Wall on the ES3 loop with `1300mm Bored Pile`: the form says "HARD 1300 / SOFT 1300 (type parameter
   'Diameter')" and HH 1900.
2. Change the HARD type to 1200 -> HH 1800. Type 1850 -> it stays 1850.
3. Start drawing the loop at the top-left corner (or select a loop whose first line starts there) -> the check box shows
   "Closing zone: N bays ..." and each adjusted bay with marks.
4. Dimension: normal bays exactly 1800 (or 1900); adjusted bays as the report says; the start corner is HARD.
5. SBP Diag on a pile -> "Size read by SBP Wall / Edit".
6. SBP Edit on an old v2 wall, change "Closing SOFT piles" to 4 -> rebuilt with the closing-zone layout.

## 34. 7 Oct: v3 for every shape; only the end / seam, only when needed; bay table with corner angles
Akash's add-on, checked with numbers before coding (circle and rectangle), then his choices:
- **Every shape** uses the same walk: from the start pile, each next pile is exactly s = HH/2 away in a straight line
  (chord), through corners and on curves. This was already v3's walk; piles are never moved at corners.
- **Open wall, free end:**
  - case 1: the last design pile that fits is HARD -> stop there, no adjustment, the leftover line stays ('short');
  - case 2: it would be SOFT -> end HARD on the line end, the last SOFT bay shortened (or 3-6 bays).
  A joined end stays on the line end.
- **Loop:** start HARD; **the last bay into the start stays exact** (Akash chose it over "adjust right at the seam",
  which made ES3 stretch 6 bays with 12 warnings because the shrunk SOFT overlapped across the start corner).
- **Only when needed:** a last bay within 10 mm of the design H-H is only spread over that bay. Otherwise 1 bay
  first, then the field N (3) up to 6, by rule B.
- **No clean choice on a loop:** WARN, plus the tip "start the loop at the middle of a side".
- **Corners:** checked, never adjusted. `G.bay_corners` gives each bay's corner angle; warnings carry "(corner 90 deg)".
- **Report:** an "Every bay" table in SBP Wall's check and SBP Edit's rebuild: H-S chords, H-H chord, web, cut,
  adjusted, corner, check (`SD.bay_table`).
- **Numbers** (D 1200, H-S 900, web 200; same in IronPython):

  | Shape | Piles | Adjusted | Notes |
  |---|---|---|---|
  | circle R5000 (centre line) | 36 | 3 bays at H-S 729.2 (H-H chord 1454.5) | 15 bays exact (H-H chord 1792.7, web 593) |
  | rectangle 10 x 6 from a corner | 34 | no clean choice -> 6 bays H-S 952 (cut 248, WARN) | corners: H06-S06-H07 web 142 WARN, H09-S09-H10 web 446 |
  | rectangle 10 x 6 from mid-side | 36 | 5 bays H-S 734 | clean |
  | 90 deg arc R8000, open | 15 | 1 bay H-S 880 (end HARD on the line end) | |
  | L 8 + 6 m, open | 17 | 3 bays H-S 781 | corner bay web 337 |
  | ES3 loop | 58 | 4 bays H-H 1440 | unchanged |
- Offline: geometry 49 (12 v3 / shape tests), data 34; IronPython: same numbers, all buttons compile, WPF form 20
  controls.
- **Revit test (Akash):** the §33 list, plus:
  - an open wall whose end is free -> check the end (stops at the last design HARD, or the end HARD on the line end);
  - a circle and a 10 x 6 rectangle -> the "Every bay" table and the corner warnings with angles.

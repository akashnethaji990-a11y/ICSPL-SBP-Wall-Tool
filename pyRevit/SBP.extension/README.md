# SBP Wall tool (pyRevit), Revit 2026

## Install (one time)
1. Install pyRevit: https://github.com/pyrevitlabs/pyRevit/releases (latest installer). Close Revit first.
2. Open Revit → pyRevit tab → Settings → Custom Extension Directories → Add folder:
   `D:\01_SP-\OneDrive - IC Singapore\COMPANY SET UP\pyRevit`
   (the folder that CONTAINS `SBP.extension`) → Save Settings and Reload.
3. A new **ERSS** tab appears. Piling panel: **SBP Wall, SBP Edit, SBP Select, SBP Line, Number, SBP Count**.
   After new buttons are added, click pyRevit → **Reload** once.

## Buttons
| Button | What you do | What happens |
|---|---|---|
| **SBP Wall** | Nothing selected: Revit's Draw tools open (Line, Rectangle, Circle, Arc, Spline, Pick Lines) → draw → Modify/Esc → the form opens by itself → click the wall side. Or select existing line(s) first | Piles placed, line hidden, the wall's settings saved with it |
| **SBP Edit** | Click any pile(s) of one or more walls → change values → OK | Only Cut-off / Toe changed: same piles kept (marks and typed data stay). Spacing, gap, type, level or a moved line: the wall is rebuilt after you confirm |
| **SBP Select** | Click any pile → Whole wall / HARD only / SOFT only | All those piles are selected (tag, schedule, check) |
| **SBP Line** | Click any pile | The hidden line is shown and selected so you can move or reshape it. Click again to hide it |
| **Number** | Click a pile of each wall, in the order to number them → Esc → prefixes (default SP / HP, e.g. C1-SP) and Continue / Start new at 1 → Next → confirm | Layout-plan numbers in Mark, in draw order from the wall's start end: HP1, SP1, HP2, SP2 ... Nothing is written before you confirm |
| **SBP Count** | Click | HARD / SOFT / TOTAL for every wall |

## Everyday workflow
- **Wall from reference planes:** select the planes (they should cross at the corners), click SBP Wall.
- **Edit several things in a row:** SBP Edit keeps asking for the next piles after Apply; press Esc when done.
- **New wall:** click SBP Wall → draw with the Draw tools (the tab says "Modify | Place Lines") → Modify/Esc → fill the form → click the wall side. Draw one connected chain per wall.
- **Levels change** (e.g. cut-off −150 → −300): click any pile → SBP Edit → change → OK.
- **Spacing change:** SBP Edit → change c/c → confirm the rebuild.
- **Shape change:** SBP Line → move/reshape the line → SBP Edit → OK (the wall follows, line hides).
- **Several walls at once:** select piles of all of them → SBP Edit. Only the fields you change are
  applied to all; the other fields keep each wall's own value.
- **Walls made before SBP Edit existed:** run SBP Wall once on the line with the same wall name.

## Rules
- **SBP Wall never deletes piles.** It suggests the next free wall name (SBP1, SBP2 ...). To change a wall use
  SBP Edit; to delete one, delete its piles by hand.
- **SOFT piles are cut by HARD piles** (Join Geometry, HARD cuts): HARD piles keep their full round shape.
- **Pick Lines** (in the Draw panel): Tab picks a whole chain; finish with Esc twice or Modify. To pick CAD
  lines, turn on Select links / Select pinned elements (bottom right of Revit).
- Line → SBP centre line = gap + D/2 (default 150 + 600 = 750). Gap min 150.
- Spacing is measured on the centre line and rounded so the real c/c is never larger than
  what you entered (overlap never less than design).
- **Free end** of an open wall = HARD. **An end that touches another SBP wall** continues its pattern:
  - if that wall's pile already sits at the joint, the new wall starts from it (no pile placed
    twice), and the next pile is the other type;
  - if that pile only overlaps the joint (e.g. a corner between two walls), the end pile is
    the other type.
  - You are asked only when the pile at the joint has no HARD/SOFT information.
- Closed loop: even count, HARD/SOFT alternate.
- SBP Wall gives Mark = `SBP1-H001` / `SBP1-S001` and Comments = `HARD PILE` / `SOFT PILE`. Each pile
  also keeps hidden data (its wall, HARD/SOFT and its place along the wall), so Mark can be changed.
- **Number** (layout plans): SOFT and HARD are counted separately, in draw order, and run on across the
  walls of the same level. **Continue** carries on from the highest existing mark with that prefix on the
  same level (the walls being numbered are not counted). **Start new** begins at 1. Marks already used by
  other piles are listed before you confirm (Revit reports them as duplicate Mark warnings).
- **Number labels** (tags in the current plan view): tag type (a Structural Foundation tag that shows Mark, or
  "No labels"), side per wall (Outside default; closed wall = the loop, open wall: Inside = the side of your drawn
  line), offset from the pile edge (default **50 mm**, just clear), rotation (default **Fixed 0 = horizontal**, reads
  left to right in the view; or Along / Across the wall; never upside down).
  **One label per pile**, next to its own pile, never stacked in rows and never overlapping: a label that would
  touch another label, a pile or another tag goes to the other side of the wall (so on a horizontal wall whose
  text is wider than one c/c the labels alternate above and below); if both sides touch it is nudged slightly.
  The report counts both. A re-run moves the same tag (a second Number label on a pile is removed). The side is
  saved per wall; tag type, offset and rotation are remembered in settings.json.
- A rebuild in SBP Edit clears the layout numbers of that wall (the new piles get `SBP1-H001` ...): run
  Number again. Cut-off / Toe changes keep them.
- Cut-off Level → Height Offset From Level. Toe Level → Depth. Values are in the same datum
  as "Elevation at Top" in Properties.
- Diameter comes from the pile TYPE (Radius x 2). For another diameter, make a new type.
- **Typed pile data** (Loading, BH Ref, SPTN, GEO/PDS ...) is copied after a rebuild to the
  nearest new pile of the same type. The report lists data that moved more than half a c/c,
  and data that could not be copied. X-Easting / Y-Northing are never copied.
- **Look:** in the view where you run the tool, filters `SBP HARD PILE` (solid fill) and
  `SBP SOFT PILE` ("Diagonal up 1.5mm", created if missing) are added. If the view template
  controls filters, you are asked first. In 3D, both types get the material `ICSPL_Pile`.
- The wall's settings are stored in the .rvt (hidden data), so everyone opening the model can edit it.

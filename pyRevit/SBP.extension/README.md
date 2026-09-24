# SBP Wall tool (pyRevit), Revit 2026

## Install (one time)
1. Install pyRevit: https://github.com/pyrevitlabs/pyRevit/releases (latest installer). Close Revit first.
2. Open Revit → pyRevit tab → Settings → Custom Extension Directories → Add folder:
   `D:\01_SP-\OneDrive - IC Singapore\COMPANY SET UP\pyRevit`
   (the folder that CONTAINS `SBP.extension`) → Save Settings and Reload.
3. A new **SBP** tab appears. Piling panel: **SBP Wall, SBP Edit, SBP Select, SBP Line, SBP Count**.
   After new buttons are added, click pyRevit → **Reload** once.

## Buttons
| Button | What you do | What happens |
|---|---|---|
| **SBP Wall** | Select your line → fill the form → click the wall side | Piles placed, line hidden, the wall's settings saved with it |
| **SBP Edit** | Click any pile(s) of one or more walls → change values → OK | Only Cut-off / Toe changed: same piles kept (marks and typed data stay). Spacing, gap, type, level or a moved line: the wall is rebuilt after you confirm |
| **SBP Select** | Click any pile → Whole wall / HARD only / SOFT only | All those piles are selected (tag, schedule, check) |
| **SBP Line** | Click any pile | The hidden line is shown and selected so you can move or reshape it. Click again to hide it |
| **SBP Count** | Click | HARD / SOFT / TOTAL for every wall |

## Everyday workflow
- **Levels change** (e.g. cut-off −150 → −300): click any pile → SBP Edit → change → OK.
- **Spacing change:** SBP Edit → change c/c → confirm the rebuild.
- **Shape change:** SBP Line → move/reshape the line → SBP Edit → OK (the wall follows, line hides).
- **Several walls at once:** select piles of all of them → SBP Edit. Only the fields you change are
  applied to all; the other fields keep each wall's own value.
- **Walls made before SBP Edit existed:** run SBP Wall once on the line with the same wall name.

## Rules
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
- Mark = `SBP1-H001` / `SBP1-S001`, Comments = `HARD PILE` / `SOFT PILE`.
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

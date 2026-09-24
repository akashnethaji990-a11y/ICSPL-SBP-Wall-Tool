# Changelog: SBP Wall pyRevit tool

## v1.0 (Sep 2026): first working version
- **SBP Wall**: select any line (straight, arc, circle, spline, joined lines), fill in settings, click the
  wall side, and HARD/SOFT `ICSPL_Pile` piles are placed along it.
- Adjustable: pile type (diameter), c/c spacing, gap to the line (min 150), Cut-off Level, separate Toe
  Levels for HARD and SOFT. Settings are remembered.
- Marks `SBP1-H001` / `SBP1-S001`, Comments `HARD PILE` / `SOFT PILE`. Re-running with the same wall
  name rebuilds the wall.
- Report with pile counts, spacing, overlap and levels. **SBP Count** lists counts per wall.
- Tested in Revit 2026 (43-pile wall: 22 hard / 21 soft).
- Known: the drawn line may not turn invisible (fix written, to be confirmed in v1.1).

## Next (v2.0, in development)
- Exact design c/c on straight runs, adjustments only near corners.
- Sharp corners with a SOFT pile on each corner, and a minimum uncut soft web of 200 mm at every angle.
- Warnings and errors for tight corners.
- HARD solid fill / SOFT hatch view filters, and the ICSPL_Pile material.

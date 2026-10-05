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
- Line → SBP centre line = gap + the bigger radius (default 150 + 750 = 900 for Ø1500). Gap min 10.
- **HARD and SOFT pile types** can differ (the SOFT box: "(same as HARD)" or another type). Both diameters are
  read from the pile types, never assumed.
- Spacing: the SBP Wall and SBP Edit forms show three linked values; **type any one**, the other two follow from
  the HARD diameter Dh and SOFT diameter Ds (the SOFT pile sits halfway):
  | Box | = | Ø1500 / Ø1500 | Ø1500 / SOFT Ø1200 |
  |---|---|---|---|
  | c/c HARD to HARD (HH) | typed | 2000 | 2000 |
  | Cutting depth, each HARD into the SOFT | (Dh + Ds − HH) / 2 | 500 | 350 |
  | Leftover SOFT web between the HARD edges | HH − Dh | 500 | 500 |
  HARD to SOFT = HH / 2 is shown in the report. **A cutting depth or web you type wins** (saved per wall): with
  another pile type, HARD to HARD moves to keep your value. A web below 200 is a WARNING (still placed). Errors:
  cutting depth 0 or less, HARD piles cutting each other (web below 0), SOFT piles cutting each other.
- **Pile size:** read fresh every time: the type parameter **Diameter** first, else a test pile's Radius x 2,
  else the family set-up. The form and the report say where it was read. A type whose name says "1300mm" must
  have that size.
- **Starting spacing:** the form fills c/c HARD to HARD = HARD diameter + 600 (1200 -> 1800) when it opens and
  when you change the HARD type. You can type over it.
- **Layout (v3, 6-7 Oct), any shape** (straight, chain, arc, circle, spline, open or closed): from the start pile,
  every next pile is exactly the design HARD to SOFT away in a straight line (chord), also through corners and on
  curves. Only the end of an open wall or the seam of a loop is adjusted, and only when needed:
  - Open wall: if the last design pile that fits is HARD, the wall stops there; the small rest of the line stays. If
    it would be SOFT, the end HARD goes on the line end and the last SOFT bay is shortened (or 3 to 6 bays if one is
    not enough). An end joined to another wall stays on the line end.
  - Loop: it starts with a HARD pile where you started drawing. The last bay into it stays exact; the bays just before
    it take the leftover. A last bay within 10 mm of the design is not adjusted.
  - Adjusted bays are equal, so each SOFT stays centred. First 1 bay, then the field **Closing SOFT piles (adjust)**
    (default 3) up to 6, the first that passes every check (web at least 200, cutting depth at least the design one,
    no same-type overlap). If nothing passes, the closest is used with warnings; for a loop the report suggests
    starting the line at the middle of a side.
  Example ES3 (11.2 x 14.6 m, Ø1200, H-H 1800): 4 bays of H-H 1440, 58 piles.
- Corners: sharp, like AutoCAD OFFSET; the piles fall where the exact c/c puts them and are never moved. Every bay
  is checked; a low web or overlap across a corner is reported with the pile mark and the corner angle. The report
  lists every bay (H-S and H-H straight c/c, web, cutting depth, adjusted, corner angle).
- **Before anything is written**, SBP Wall and SBP Edit show the values they read and worked out per wall
  (diameters and where they were read, the three spacing values, the closing zone and each adjusted bay by its
  marks, pile counts, smallest web and cutting depth, warnings by the marks the piles will get) and ask Yes / No.
- Older walls keep their own layout (before 30 Sep: equal spacing; 30 Sep to 6 Oct: v2 corner rule) until they are
  rebuilt; any rebuild uses v3.
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
- **Number labels** (tags in the current plan view): tag type (a tag that shows Mark, or "No labels"). The list
  shows Structural Foundation tags first, then Multi-Category tags, Generic Model tags and Generic Annotations
  (the category is shown after the name). Each one is test-placed on a pile first (undone at once): a type Revit
  cannot use says why and how to fix the family, and Next stays off. A **Generic Annotation** works as a copy:
  one annotation per pile with the pile's Mark written into its text parameter (named in the dialog). It does not
  follow later Mark changes (run Number again), and an SBP Edit rebuild removes the wall's annotations. Fix: open the tag family, Family Category and Parameters > Structural Foundation Tags (or
  Multi-Category Tags), save, load it again; side per wall (Outside default; closed wall = the loop, open wall: Inside = the side of your drawn
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
- Diameters come from the pile TYPES (Radius x 2). For another diameter, make a new type.
- **Any pile family works** (another drafter's own family too). The pile type list shows ICSPL_Pile types by name
  and other families as "Type (Family)": every Structural Foundation family that is set up, recognised as a pile
  (a Diameter / Pile Dia / Radius parameter), or has "pile" in its name. Its parameters are recognised by name
  (size: Diameter / Pile Dia / Radius ...; toe: Depth / Length / Pile Length ...; cut-off: Height Offset From
  Level / Offset ...). If one is not recognised, SBP Wall asks once which parameter it is and saves the answer
  in the model, so the whole team gets it. **Shift+Click on SBP Wall** = pile family set-up: set up a family that
  is not listed, or correct a set-up. After placing, the tool reads Top / Bottom back; if a family does not follow
  the asked Cut-off / Toe, nothing is placed and it says so.
- **Typed pile data** (Loading, BH Ref, SPTN, GEO/PDS ...) is copied after a rebuild to the
  nearest new pile of the same type. The report lists data that moved more than half a c/c,
  and data that could not be copied. X-Easting / Y-Northing are never copied.
- **Look:** in the view where you run the tool, filters `SBP HARD PILE` (solid fill) and
  `SBP SOFT PILE` ("Diagonal up 1.5mm", created if missing) are added. If the view template
  controls filters, you are asked first. In 3D, both types get the material `ICSPL_Pile`.
- The wall's settings are stored in the .rvt (hidden data), so everyone opening the model can edit it.

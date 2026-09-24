# How to install the SBP Wall tool in Revit

**For:** IC Singapore BIM team · **Revit:** 2026 · **Time:** about 15 minutes, once
**Questions:** Akash

The SBP Wall tool places a Secant Bored Pile wall (HARD / SOFT piles) along any line you draw in Revit,
including straight lines, arcs, circles and joined lines, and counts the piles.

---

## Before you start: you need
1. **Revit 2026**
2. A **GitHub account** (free): https://github.com/signup. Send your username to Akash.
3. The **invite email** from GitHub ("…invited you to collaborate on SBP-pyRevit"). Click **Accept invitation**.

---

## Step 1: Install pyRevit (skip if you already have it)
1. **Close Revit.**
2. Download the latest pyRevit installer: https://github.com/pyrevitlabs/pyRevit/releases
   (under **Assets**, pick the file ending in **`.exe`**, e.g. `pyRevit_x.x.x_signed.exe`).
3. Run it and keep the default options.
4. Open Revit 2026. You should see a **pyRevit** tab.

## Step 2: Install GitHub Desktop
1. Download it from https://desktop.github.com and install it.
2. Open it and **sign in** with your GitHub account.

## Step 3: Download the SBP tool
1. In GitHub Desktop: **File → Clone repository**.
2. Choose the **GitHub.com** tab, then select **`SBP-pyRevit`** from the list.
   (If it isn't listed, you haven't accepted the invite yet. Check your email.)
3. **Local path:** `C:\pyRevit-Ext\SBP-pyRevit`
4. Click **Clone**.

## Step 4: Connect it to Revit
1. Open Revit 2026 → **pyRevit** tab → **Settings** (click the pyRevit logo button).
2. Find **Custom Extension Directories** → **Add folder** → select `C:\pyRevit-Ext\SBP-pyRevit`
3. Click **Save Settings and Reload**.
4. A new **SBP** tab appears with **SBP Wall** and **SBP Count**. ✅

---

## How to use it (quick start)
1. Open a **plan view**. The pile family **`ICSPL_Pile`** must be loaded in the project.
2. Draw the "other structure" line with **Model Line**: any shape (line, arc, circle, spline or several joined lines).
3. Select the line → **SBP** tab → **SBP Wall**.
4. Fill in the settings: wall name, pile type, level, c/c spacing, gap (min 150), Cut-off Level and Toe Levels.
5. **Click on the side** of the line where the wall should go.
6. The piles are placed, and a report shows the **HARD / SOFT / TOTAL** counts. Marks look like `SBP1-H001` / `SBP1-S001`.
7. To change a wall: run SBP Wall again with the **same wall name** and confirm the rebuild.
8. **SBP Count** lists the pile counts for every wall in the model.

---

## Getting updates
When Akash announces a new version:
1. Open **GitHub Desktop** (make sure **SBP-pyRevit** is the current repository, top left).
2. Click **Fetch origin**, then **Pull origin**.
3. In Revit: **pyRevit → Reload** (or restart Revit).

That's it. You don't need to download or copy anything else.

---

## Troubleshooting
| Problem | Fix |
|---|---|
| No **SBP** tab | Check Step 4: the folder must be `C:\pyRevit-Ext\SBP-pyRevit` (the one that contains `SBP.extension`). Then Reload. |
| **Two** SBP tabs | An old copy is in the extension list. Remove it in pyRevit Settings → Reload. |
| "Family 'ICSPL_Pile' is not loaded" | Load the ICSPL_Pile family into your project. |
| "Open a plan view first" | Switch to a floor or structural plan, then run again. |
| Can't see SBP-pyRevit in GitHub Desktop | Accept the GitHub invite email, then File → Clone repository again. |
| Something else | Send Akash a screenshot of the error window. |

> Please **don't edit files** in `C:\pyRevit-Ext\SBP-pyRevit`. Your changes would block updates.
> Send ideas and bugs to Akash instead.

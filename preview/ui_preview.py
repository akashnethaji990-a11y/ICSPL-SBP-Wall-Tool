# -*- coding: utf-8 -*-
"""Preview of the SBP Wall settings window. Run in VS Code with the Run button (no Revit needed).

This is a copy of the form's layout only. It does NOT place piles. Use it to check wording,
field order and defaults before changing the real script:
pyRevit/SBP.extension/SBP.tab/Piling.panel/SBP Wall.pushbutton/script.py (function ask_inputs).
"""
import tkinter as tk
from tkinter import ttk, messagebox

FIELDS = [
    ("Wall name (pile marks become e.g. SBP1-H001 / SBP1-S001):", "entry", "SBP1"),
    ("Pile type  (diameter is taken from the type):", "combo", ["1200mm Bored Pile", "1000mm Bored Pile"]),
    ("Placement level:", "combo", ["Level 1", "SEEPAGE BASE SLAB"]),
    ("c/c spacing hard-to-soft (mm):", "entry", "900"),
    ("Gap: your line to SBP inner edge (mm, min 150):", "entry", "150"),
    ("Cut-off Level (mm, same datum as 'Elevation at Top'):", "entry", "-150"),
    ("Toe Level - HARD pile (mm):", "entry", "-10000"),
    ("Toe Level - SOFT pile (mm, blank = same as hard):", "entry", "-9000"),
]

root = tk.Tk()
root.title("SBP Wall settings  (PREVIEW - no Revit)")
root.geometry("460x600")
frm = ttk.Frame(root, padding=14)
frm.pack(fill="both", expand=True)

widgets = []
for label, kind, val in FIELDS:
    ttk.Label(frm, text=label).pack(anchor="w", pady=(6, 2))
    if kind == "entry":
        w = ttk.Entry(frm)
        w.insert(0, val)
    else:
        w = ttk.Combobox(frm, values=val, state="readonly")
        w.current(0)
    w.pack(fill="x")
    widgets.append((label, w))

inv = tk.BooleanVar(value=True)
ttk.Checkbutton(frm, text="Make my line <Invisible lines> (like Defpoints)", variable=inv).pack(anchor="w", pady=10)
ttk.Separator(frm).pack(fill="x", pady=6)


def on_next():
    try:
        gap = float(widgets[4][1].get())
        if gap < 150:
            messagebox.showwarning("SBP Wall", "Gap must be at least 150 mm (you entered {:.0f}).".format(gap))
            return
    except ValueError:
        messagebox.showwarning("SBP Wall", "Gap must be a number.")
        return
    lines = ["{} {}".format(l.split("(")[0].strip(), w.get()) for l, w in widgets]
    lines.append("Invisible line: {}".format(inv.get()))
    messagebox.showinfo("Values the tool would use", "\n".join(lines) + "\n\nIn Revit: next you click the wall side.")


ttk.Button(frm, text="Next: click the wall side", command=on_next).pack(fill="x", ipady=4)
root.mainloop()

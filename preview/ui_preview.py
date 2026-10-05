# -*- coding: utf-8 -*-
"""Preview of the SBP Wall settings window (two tabs: Settings + Preview). Run with Python (no Revit).

This is a mock-up of the form layout only. It does NOT place piles.
Real dialog: SBP Wall.pushbutton/script.py (SBPWallWindow class) + SBPWallWindow.xaml.
Run: python preview/ui_preview.py
"""
import tkinter as tk
from tkinter import ttk, messagebox
import math

PILE_TYPES = ["1500mm Bored Pile", "1200mm Bored Pile", "1000mm Bored Pile"]
DIAMS = {"1500mm Bored Pile": 1500.0, "1200mm Bored Pile": 1200.0, "1000mm Bored Pile": 1000.0}

root = tk.Tk()
root.title("SBP Wall settings  (PREVIEW - no Revit)")
root.geometry("820x620")

nb = ttk.Notebook(root)
nb.pack(fill="both", expand=True, padx=8, pady=8)

# ============================================================ Tab 1: Settings
t1 = ttk.Frame(nb, padding=12)
nb.add(t1, text="  Settings  ")

FIELDS = [
    ("Wall name (marks e.g. SBP1-H001):", "entry", "SBP1"),
    ("HARD pile type:", "combo", PILE_TYPES),
    ("SOFT pile type:", "combo", ["(same as HARD)"] + PILE_TYPES),
    ("Placement level:", "combo", ["Level 1", "SEEPAGE BASE SLAB"]),
]
entries = {}
for label, kind, val in FIELDS:
    row = ttk.Frame(t1)
    row.pack(fill="x", pady=2)
    ttk.Label(row, text=label, width=42, anchor="w").pack(side="left")
    if kind == "entry":
        w = ttk.Entry(row, width=22)
        w.insert(0, val)
    else:
        w = ttk.Combobox(row, values=val, state="readonly", width=21)
        w.current(0)
    w.pack(side="left")
    entries[label] = w

ttk.Separator(t1).pack(fill="x", pady=8)
ttk.Label(t1, text="Spacing: type ANY ONE. HARD to HARD sets cutting depth and leftover web.",
          foreground="#555555").pack(anchor="w")

spacing_frame = ttk.Frame(t1)
spacing_frame.pack(fill="x", pady=4)
sp_labels = ["c/c HARD to HARD (mm):", "Cutting depth, each side (mm):", "Leftover SOFT web (mm):",
             "Closing SOFT piles (adjust, 1-6):"]
sp_keys = ["hh", "cut", "web", "close_n"]
sp_entries = {}
for lab, key in zip(sp_labels, sp_keys):
    row = ttk.Frame(spacing_frame)
    row.pack(fill="x", pady=1)
    ttk.Label(row, text=lab, width=42, anchor="w").pack(side="left")
    w = ttk.Entry(row, width=14)
    sp_entries[key] = w
    w.pack(side="left")
sp_entries["hh"].insert(0, "2100")             # HARD diameter + 600 (the form fills this on open / type change)
sp_entries["close_n"].insert(0, "3")

ttk.Separator(t1).pack(fill="x", pady=8)
for label, key, default in [
    ("Gap: line to SBP inner edge (mm, min 10):", "gap", "150"),
    ("Cut-off Level (mm):", "cutoff", "-150"),
    ("Toe Level - HARD pile (mm):", "toe_h", "-10000"),
    ("Toe Level - SOFT (mm, blank = same):", "toe_s", "-9000"),
]:
    row = ttk.Frame(t1)
    row.pack(fill="x", pady=1)
    ttk.Label(row, text=label, width=42, anchor="w").pack(side="left")
    w = ttk.Entry(row, width=14)
    w.insert(0, default)
    entries[key] = w
    w.pack(side="left")

inv = tk.BooleanVar(value=True)
ttk.Checkbutton(t1, text="Make my line <Invisible lines> (like Defpoints)", variable=inv).pack(anchor="w", pady=8)

live_var = tk.StringVar(value="Type c/c HARD to HARD, a cutting depth or a leftover SOFT web.")
live_lbl = ttk.Label(t1, textvariable=live_var, foreground="#884400", background="#FFF6E5",
                     wraplength=480, justify="left", padding=8)
live_lbl.pack(fill="x", pady=4)


def get_diams():
    dh = DIAMS.get(entries["Wall name (marks e.g. SBP1-H001):"].__class__ and
                   entries.get("HARD pile type:", entries.get("HARD pile type:")))
    h = entries.get("HARD pile type:")
    s = entries.get("SOFT pile type:")
    dh = DIAMS.get(h.get() if h else None)
    ds_raw = s.get() if s else "(same as HARD)"
    ds = dh if ds_raw == "(same as HARD)" else DIAMS.get(ds_raw)
    return dh, ds


def recalc_spacing(*_):
    dh, ds = get_diams()
    # find which box was most recently typed: for mock-up, HH is master
    try:
        hh = float(sp_entries["hh"].get())
        if dh and ds and hh > 0:
            cut = (dh + ds - hh) / 2.0
            web = hh - dh
            sp_entries["cut"].delete(0, "end")
            sp_entries["cut"].insert(0, "{:.0f}".format(cut))
            sp_entries["web"].delete(0, "end")
            sp_entries["web"].insert(0, "{:.0f}".format(web))
            errs = []
            if cut <= 0:
                errs.append("ERROR: no cutting (HH >= Dh + Ds)")
            if web < 0:
                errs.append("ERROR: web negative")
            elif web < 200:
                errs.append("WARNING: leftover web {:.0f} < 200 mm".format(web))
            live_var.set("HARD {:.0f} / SOFT {:.0f}   HH {:.0f}   cutting {:.0f}   web {:.0f}{}".format(
                dh, ds, hh, cut, web, ("   " + "  ".join(errs)) if errs else ""))
            update_preview()
    except ValueError:
        pass


sp_entries["hh"].bind("<KeyRelease>", recalc_spacing)
for k in ["HARD pile type:", "SOFT pile type:"]:
    if k in entries:
        entries[k].bind("<<ComboboxSelected>>", recalc_spacing)

# ============================================================ Tab 2: Preview
t2 = ttk.Frame(nb, padding=12)
nb.add(t2, text="  Preview  ")

prev_info = tk.StringVar(value="Type spacing values on the Settings tab to see the pile pattern.")
ttk.Label(t2, textvariable=prev_info, foreground="#555555", wraplength=760).pack(anchor="w", pady=(0, 6))

can_frame = ttk.Frame(t2, relief="solid", borderwidth=1)
can_frame.pack(fill="x")
can = tk.Canvas(can_frame, width=756, height=220, bg="white")
can.pack()

anim_state = {"running": False, "step": 0, "centres": [], "kinds": [], "dh": 0, "ds": 0, "hh": 0, "job": None}

bottom_frame = ttk.Frame(t2)
bottom_frame.pack(fill="x", pady=8)
play_btn = ttk.Button(bottom_frame, text="Play", width=12)
play_btn.pack(side="left", padx=(0, 10))
anim_info = tk.StringVar(value="")
ttk.Label(bottom_frame, textvariable=anim_info, foreground="#555555").pack(side="left")


def fake_layout(hh_mm, dh_mm, ds_mm):
    """Straight-line layout for preview (matches the real G.layout_wall logic for a straight wall)."""
    s = hh_mm / 2.0
    ll = hh_mm * 8.0 * 1.04
    n_piles = max(2, int(ll / s) + 1)
    # equal spacing at s = hh/2
    xs = [i * s for i in range(n_piles)]
    # trim to line length
    xs = [x for x in xs if x <= ll + s * 0.01]
    kinds = ["HARD" if i % 2 == 0 else "SOFT" for i in range(len(xs))]
    return xs, kinds


def draw_preview(anim_step=None):
    can.delete("all")
    centres = anim_state["centres"]
    kinds = anim_state["kinds"]
    dh_mm = anim_state["dh"]
    ds_mm = anim_state["ds"]
    hh_mm = anim_state["hh"]
    if not centres:
        return
    W, H, CY, MX = 756, 220, 110, 16
    span = centres[-1] - centres[0]
    if span < 1.0:
        return
    scale = (W - 2 * MX) / span
    r_h = max(5, min(40, int(dh_mm * scale / 2)))
    r_s = max(5, min(40, int(ds_mm * scale / 2)))
    x0 = centres[0]
    # centre line
    can.create_line(MX - 4, CY, W - MX + 4, CY, fill="#C0C0C0", width=1)
    n_show = len(centres) if anim_step is None else (anim_step + 1)
    for i, (cx_mm, k) in enumerate(zip(centres, kinds)):
        xpx = MX + (cx_mm - x0) * scale
        r = r_h if k == "HARD" else r_s
        is_hard = k == "HARD"
        if i >= n_show:
            fill = "#AAAAAA"; outline = "#888888"; width = 1; lbl_col = "#AAAAAA"
        elif anim_step is not None and i == anim_step:
            fill = "#E06010"; outline = "#A04000"; width = 2; lbl_col = "white"
        else:
            fill = "#1E1E1E" if is_hard else "white"; outline = "black"; width = 2
            lbl_col = "white" if is_hard else "black"
        can.create_oval(xpx - r, CY - r, xpx + r, CY + r, fill=fill, outline=outline, width=width)
        if not is_hard and i < n_show and (anim_step is None or i != anim_step):
            # hatch lines for SOFT pile
            step = max(3, r // 4)
            for dy in range(-r * 2, r * 2, step):
                can.create_line(xpx - r, CY + dy, xpx + r, CY + dy - r * 2,
                                fill="#333333", width=1, tags="hatch")
        fs = max(8, min(13, int(r * 0.7)))
        can.create_text(xpx, CY, text="H" if is_hard else "S",
                        fill=lbl_col, font=("Arial", fs, "bold"))
    # dimension: HH above first H-H pair
    hh_xs = [MX + (cx - x0) * scale for cx, k in zip(centres, kinds) if k == "HARD"]
    if len(hh_xs) >= 2:
        xa, xb = hh_xs[0], hh_xs[1]
        yd = CY - max(r_h, r_s) - 16
        can.create_line(xa, yd - 4, xa, yd + 4, fill="#606060")
        can.create_line(xb, yd - 4, xb, yd + 4, fill="#606060")
        can.create_line(xa, yd, xb, yd, fill="#606060")
        can.create_text((xa + xb) / 2, yd - 10, text="{:.0f}".format(hh_mm),
                        fill="#404040", font=("Arial", 9))


def update_preview(*_):
    try:
        hh = float(sp_entries["hh"].get())
        dh, ds = get_diams()
        if not (hh > 0 and dh and ds):
            prev_info.set("Type spacing values to see the pile pattern.")
            can.delete("all")
            return
        xs, kinds = fake_layout(hh, dh, ds)
        anim_state.update(centres=xs, kinds=kinds, dh=dh, ds=ds, hh=hh)
        nh = kinds.count("HARD")
        prev_info.set("Preview: {} piles ({} HARD + {} SOFT) at c/c HARD-to-HARD {:.0f} mm.  "
                      "Straight placeholder line -- actual shape used at placement.".format(
                          len(kinds), nh, len(kinds) - nh, hh))
        draw_preview()
    except (ValueError, TypeError):
        pass


def anim_step():
    if not anim_state["running"]:
        return
    n = len(anim_state["kinds"])
    if n == 0:
        return
    anim_state["step"] = (anim_state["step"] + 1) % n
    draw_preview(anim_state["step"])
    anim_info.set("Pile {} of {}".format(anim_state["step"] + 1, n))
    anim_state["job"] = root.after(300, anim_step)


def toggle_play():
    if anim_state["running"]:
        anim_state["running"] = False
        if anim_state["job"]:
            root.after_cancel(anim_state["job"])
            anim_state["job"] = None
        play_btn.config(text="Play")
        anim_info.set("")
        draw_preview()
    else:
        if not anim_state["centres"]:
            return
        anim_state["running"] = True
        anim_state["step"] = -1
        play_btn.config(text="Pause")
        anim_step()


play_btn.config(command=toggle_play)
sp_entries["hh"].bind("<KeyRelease>", update_preview)

# ============================================================ Footer (outside tabs)
footer = ttk.Frame(root, padding=(8, 2, 8, 8))
footer.pack(fill="x", side="bottom")
ttk.Label(footer, text="Nothing is placed yet: after you click the wall side, the values are shown once more to confirm.",
          foreground="#555555", wraplength=600).pack(side="left", expand=True, anchor="w")


def on_next():
    try:
        gap = float(entries.get("gap", ttk.Entry()).get() if "gap" in entries else "150")
        if gap < 10:
            messagebox.showwarning("SBP Wall", "Gap must be at least 10 mm.")
            return
    except ValueError:
        messagebox.showwarning("SBP Wall", "Gap must be a number.")
        return
    messagebox.showinfo("SBP Wall", "In Revit: next you click the wall side, then the final values are shown to confirm.")


btn_frame = ttk.Frame(footer)
btn_frame.pack(side="right")
ttk.Button(btn_frame, text="Next: click the wall side", width=22, command=on_next).pack(side="left", padx=(0, 6))
ttk.Button(btn_frame, text="Cancel", width=10, command=root.destroy).pack(side="left")

recalc_spacing()
root.mainloop()

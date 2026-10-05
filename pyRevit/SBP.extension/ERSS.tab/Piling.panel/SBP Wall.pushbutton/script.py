# -*- coding: utf-8 -*-
"""Place a Secant Bored Pile (SBP) wall along any drawn line.

1. Click SBP Wall with nothing selected: Revit's Modify | Place Lines tab opens with the Draw panel
   (Line, Rectangle, Circle, Arcs, Spline, Pick Lines ...). Draw the 'other structure' line and
   press Modify / Esc: this form then opens by itself.
   Or select existing line(s) first (line, arc, circle, spline or a connected chain), then click.
2. Fill in the settings (all adjustable, remembered for next time): HARD and SOFT pile types, and ONE of
   HARD to HARD / cutting depth / leftover SOFT web (the other two follow from the real diameters).
3. Click on the side where the SBP wall should go.
4. The values read and worked out are shown (nothing is written yet): Place, or cancel.
Straight runs and curves keep the design c/c; the leftover is taken by reducing a few gaps next to the corners
(at the far end without corners). Corners are sharp, with a SOFT pile on the corner moved inward (option B).
A free end starts/ends with HARD. An end that touches another SBP wall continues its HARD/SOFT pattern.
The wall's settings are saved with it, so SBP Edit can change it later.
"""
__title__ = "SBP\nWall"
__author__ = "Akash"
__persistentengine__ = True     # keeps the "drawing finished" handler (sbp_draw) alive after the script ends

import os
import json

import clr
# WPF assemblies for SBPWallWindow: the live spacing form needs them (as in pyrevit.framework, see Number)
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from Autodesk.Revit.DB import Transaction, ViewPlan, ElementId, CurveElement, ReferencePlane

from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

from pyrevit import revit, forms, script

# WPF canvas drawing for the Preview tab
try:
    from System.Windows.Controls import Canvas as _Canvas, TextBlock as _TextBlock
    from System.Windows.Shapes import Ellipse as _Ellipse, Line as _Line
    from System.Windows.Media import (SolidColorBrush as _SolidBrush, Color as _WColor,
                                      Colors as _Colors, DrawingBrush as _DrawingBrush,
                                      GeometryDrawing as _GeomDraw, Pen as _WPen,
                                      StreamGeometry as _SG, TileMode as _TileMode,
                                      BrushMappingMode as _BMMode)
    from System.Windows.Threading import DispatcherTimer as _DTimer
    from System import TimeSpan as _TimeSpan
    from System.Windows import Point as _WPoint, Rect as _WRect
    _PREVIEW_OK = True
except Exception:
    _PREVIEW_OK = False


def _make_soft_brush(cell=6.0, lw=0.8):
    """Diagonal hatch DrawingBrush for SOFT piles in the preview canvas.
    Transparent background + black diagonal lines tiling every `cell` pixels."""
    if not _PREVIEW_OK:
        return None
    try:
        sg = _SG()
        ctx = sg.Open()
        try:
            ctx.BeginFigure(_WPoint(0.0, cell), False, False)
            ctx.LineTo(_WPoint(cell, 0.0), True, False)
        finally:
            ctx.Dispose()
        gd = _GeomDraw()
        gd.Pen = _WPen(_SolidBrush(_Colors.Black), lw)
        gd.Geometry = sg
        br = _DrawingBrush(gd)
        br.TileMode = _TileMode.Tile
        br.Viewport = _WRect(0.0, 0.0, cell, cell)
        br.ViewportUnits = _BMMode.Absolute
        br.Viewbox = _WRect(0.0, 0.0, cell, cell)
        br.ViewboxUnits = _BMMode.Absolute
        return br
    except Exception:
        return _SolidBrush(_WColor.FromRgb(200, 200, 200))

import sbp_geom as G
import sbp_data as SD
import sbp_revit as SR
import sbp_draw

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

CFG_FILE = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "SBPTool", "settings.json")
DEFAULTS = {
    "wall": "SBP1", "type": "", "soft_type": "", "level": "", "spacing_by": "spacing_hh", "spacing_val": "1800",
    "gap": "150", "cutoff": "0", "toe_hard": "-20000", "toe_soft": "", "invisible": True, "close_n": "3",
}
SAME = "(same as HARD)"          # SOFT pile type choice: the HARD type
MAX_LISTED = 20                  # warnings / errors listed in the report (the rest are counted)


def load_cfg():
    d = dict(DEFAULTS)
    try:
        with open(CFG_FILE) as f:
            saved = json.load(f)
    except Exception:
        saved = {}
    d.update(saved)
    if "spacing_val" not in saved and saved.get("spacing"):    # settings.json from before 30 Sep: HARD to SOFT
        try:
            d["spacing_by"], d["spacing_val"] = "spacing_hh", SD.fmt_num(2.0 * float(saved["spacing"]))
        except ValueError:
            pass
    return d


def save_cfg(values):
    """Remember the last-used values (the Number button keeps its label settings in the same file)."""
    try:
        with open(CFG_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    try:
        d.update(values)
        d.pop("spacing", None)                                 # the old HARD to SOFT value
        folder = os.path.dirname(CFG_FILE)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(CFG_FILE, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def fail(msg):
    forms.alert(msg, title="SBP Wall", exitscript=True)


def get_line_source():
    """(items, closed) of the wall line, from (in this order):
    1. lines selected before clicking, 2. reference planes selected before clicking,
    3. lines just drawn with the Draw tools, 4. otherwise start drawing.
    Items from reference planes have no line element yet (made with the wall)."""
    pre = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    curves = [e for e in pre if isinstance(e, CurveElement)]
    planes = [e for e in pre if isinstance(e, ReferencePlane)]
    if curves or planes:
        sbp_draw.stop(__revit__)
    try:
        if curves:
            return SR.build_chain(curves)
        if planes:
            return SR.plane_chain(planes, doc.ActiveView)
        drawn = sbp_draw.take_drawn(doc)
        if drawn:
            return SR.build_chain(drawn)
    except ValueError as ex:
        fail(str(ex))
    # Nothing selected: open Revit's Modify | Place Lines tab (Draw panel). When the drafter finishes
    # (Modify / Esc), sbp_draw runs SBP Wall again with the new lines.
    sbp_draw.start_draw(__revit__, doc)
    script.exit()


def num(v, label, allow_blank=False):
    v = (v or "").strip()
    if not v and allow_blank:
        return None
    try:
        return float(v)
    except ValueError:
        fail("'{}' must be a number (mm). You entered: '{}'".format(label, v))


def ask_kind(end, mark):
    """Only asked when this wall touches a pile whose type cannot be read."""
    return forms.CommandSwitchWindow.show(
        ["HARD", "SOFT"],
        message="The {} of this wall joins pile '{}', but its type (HARD/SOFT) is unknown.\n"
                "Which type is that pile?".format(end, mark or "without a mark"))


def ask_choice(question, options):
    """One question of the pile family set-up (asked once per family; the answer is saved in the model)."""
    return forms.SelectFromList.show(options, title=question, multiselect=False, button_name="Use this")


def allow_template(name):
    return forms.alert("This view's template '{}' controls filters.\n\nAdd the SBP HARD/SOFT filters to the "
                       "template? Every view that uses it will show them.".format(name),
                       title="SBP Wall", yes=True, no=True)


def allow_template_lines(name):
    return forms.alert("Revit refused <Invisible lines> for your line, so it uses the line style '{}'.\n"
                       "This view's template '{}' controls line visibility.\n\nTurn '{}' off in the template? "
                       "Every view that uses it will hide these lines.".format(SR.SBP_LINE_STYLE, name, SR.SBP_LINE_STYLE),
                       title="SBP Wall", yes=True, no=True)


SPACING_BOX = {"spacing_hh": "hh_tb", "cut": "cut_tb", "web": "web_tb"}


class SBPWallWindow(forms.WPFWindow):
    """SBP Wall settings, with the three linked spacing boxes recalculating live.

    HARD to HARD is the master: it always sets cutting depth and leftover web (1500mm piles at 2000 -> 500 / 500).
    Type a cutting depth or web to set HARD to HARD instead; changing HARD to HARD again restores the computed
    defaults. Clearing any box never crashes: the derived boxes just go blank. result = the settings dict or None.
    diams: {type label: diameter in mm or None (size read after Next, e.g. a family not set up yet)}."""

    def __init__(self, cfg, types, diams, levels, default_level):
        self._ready = False
        self._sync = False
        self.types = types
        self.diams = diams
        self.levels = levels
        self.result = None
        self.driver = cfg["spacing_by"] if cfg.get("spacing_by") in SD.SPACING_KEYS else "spacing_hh"
        # preview / animation state
        self._prev_centres = []
        self._prev_kinds = []
        self._prev_dh = 0.0
        self._prev_ds = 0.0
        self._prev_hh = 0.0
        self._anim_step = 0
        self._soft_br = None     # cached soft-pile hatch brush
        if _PREVIEW_OK:
            self._timer = _DTimer()
            self._timer.Interval = _TimeSpan.FromMilliseconds(300)
            self._timer.Tick += self._anim_tick
        else:
            self._timer = None
        forms.WPFWindow.__init__(self, "SBPWallWindow.xaml")
        self.wall_tb.Text = cfg["wall"]
        self._fill_combo(self.hard_cb, sorted(types.keys()), cfg["type"] if cfg["type"] in types else None)
        self._fill_combo(self.soft_cb, [SAME] + sorted(types.keys()),
                         cfg["soft_type"] if cfg["soft_type"] in types else SAME)
        self._fill_combo(self.level_cb, sorted(levels.keys()), default_level if default_level in levels else None)
        dh0 = self.diams.get(self.hard_cb.SelectedItem)
        if dh0:                                  # a new wall starts at HARD to HARD = D + 600 (Akash, 6 Oct)
            self.driver = "spacing_hh"
            self.hh_tb.Text = SD.fmt_num(SD.default_hh(dh0))
        else:
            self._box(self.driver).Text = SD.fmt_num(cfg.get("spacing_val"))
        self.close_tb.Text = str(SD.close_n(cfg))
        self.gap_tb.Text = str(cfg["gap"])
        self.cutoff_tb.Text = "0"
        self.toe_hard_tb.Text = "-20000"
        self.toe_soft_tb.Text = ""
        self.invisible_cb.IsChecked = bool(cfg["invisible"])
        self._ready = True
        self._apply(self.driver)

    def _fill_combo(self, cb, items, want):
        for it in items:
            cb.Items.Add(it)
        cb.SelectedIndex = items.index(want) if want in items else 0

    def _box(self, key):
        return getattr(self, SPACING_BOX[key])

    def _parse(self, tb):
        t = (tb.Text or "").strip()
        if not t:
            return None
        try:
            return float(t)
        except ValueError:
            return None

    def _diams(self):
        dh = self.diams.get(self.hard_cb.SelectedItem)
        s = self.soft_cb.SelectedItem
        ds = dh if s == SAME else self.diams.get(s)
        return dh, ds

    def _apply(self, driver):
        """Recompute the two boxes the drafter did NOT set, from `driver`'s value and the diameters."""
        if not self._ready:
            return
        self._sync = True
        try:
            dh, ds = self._diams()
            boxes = SD.linked_boxes(driver, self._parse(self._box(driver)), dh, ds)
            for k in SD.SPACING_KEYS:
                if k != driver:
                    self._box(k).Text = SD.fmt_num(boxes[k])
        finally:
            self._sync = False
        self.refresh()
        self._update_preview()

    # events (names bound in SBPWallWindow.xaml) --------------------------------
    def hh_changed(self, sender, args):
        if self._ready and not self._sync:
            self.driver = "spacing_hh"
            self._apply("spacing_hh")

    def cut_changed(self, sender, args):
        if self._ready and not self._sync:
            self.driver = "cut"
            self._apply("cut")

    def web_changed(self, sender, args):
        if self._ready and not self._sync:
            self.driver = "web"
            self._apply("web")

    def type_changed(self, sender, args):
        if not self._ready or self._sync:
            return
        dh = self.diams.get(self.hard_cb.SelectedItem)
        if getattr(sender, "Name", "") == "hard_cb" and dh:
            self.driver = "spacing_hh"        # a new HARD type starts at HARD to HARD = D + 600 (Akash, 6 Oct)
            self._sync = True
            try:
                self.hh_tb.Text = SD.fmt_num(SD.default_hh(dh))
            finally:
                self._sync = False
            self._apply("spacing_hh")
        else:
            self._apply(self.driver)          # keep whatever the drafter set; recompute from the new diameters

    def _size_text(self, dh, ds):
        """'HARD 1300 / SOFT 1300 (type parameter 'Diameter').' with where each size was read."""
        h_lbl = self.hard_cb.SelectedItem
        s_lbl = h_lbl if self.soft_cb.SelectedItem == SAME else self.soft_cb.SelectedItem
        sh, ss = SR._DIAM_SRC.get(h_lbl), SR._DIAM_SRC.get(s_lbl)
        if sh == ss:
            return "HARD {:.0f} / SOFT {:.0f} ({}).".format(dh, ds, sh or "read from the types")
        return "HARD {:.0f} ({}) / SOFT {:.0f} ({}).".format(dh, sh or "?", ds, ss or "?")

    def _close_n(self):
        try:
            n = int((self.close_tb.Text or "").strip())
        except ValueError:
            return None
        return n if 1 <= n <= SD.CLOSE_N_MAX else None

    def levels_changed(self, sender, args):
        if self._ready and not self._sync:
            self.refresh()

    # ---------------------------------------------------------------------- preview tab
    def _update_preview(self):
        """Redraw the preview canvas with a straight placeholder layout. Called on every _apply()."""
        if not _PREVIEW_OK:
            return
        try:
            hh, dh, ds = self._preview_vals()
            if hh is None or hh <= 0 or dh is None or ds is None:
                self._preview_clear("Type spacing values to see the pile pattern.")
                return
            centres, kinds = self._fake_layout(hh, dh, ds)
            if not centres:
                self._preview_clear("Cannot preview: spacing may be too small for these pile types.")
                return
            # stop animation and reset (new layout may have different pile count)
            if self._timer and self._timer.IsEnabled:
                self._timer.Stop()
                self.play_btn.Content = "Play"
                self.anim_info_tb.Text = ""
            self._prev_centres = centres
            self._prev_kinds = kinds
            self._prev_dh = dh
            self._prev_ds = ds
            self._prev_hh = hh
            n_h = sum(1 for k in kinds if k == SR.HARD)
            n_s = len(kinds) - n_h
            self.preview_info_tb.Text = (
                "Preview: {} piles ({} HARD + {} SOFT) at "
                "c/c HARD-to-HARD {:.0f} mm.  "
                "Straight placeholder line -- actual shape used at placement.".format(
                    len(kinds), n_h, n_s, hh))
            self._draw_preview(centres, kinds, dh, ds, hh)
        except Exception:
            self._preview_clear("Preview unavailable.")

    def _preview_vals(self):
        """(hh_mm, dh_mm, ds_mm) from the form, or hh=None when invalid."""
        dh, ds = self._diams()
        val = self._parse(self._box(self.driver))
        if val is None or val <= 0:
            return None, dh, ds
        hh = SD.hh_from(self.driver, val, dh, ds)
        return hh, dh, ds

    def _fake_layout(self, hh_mm, dh_mm, ds_mm):
        """Straight line layout of ~9 piles in mm for the preview canvas."""
        s = hh_mm / 2.0
        ll = hh_mm * 8.0 * 1.04        # enough room for ~9 piles with a little slack
        path = [(ll * i / 100.0, 0.0) for i in range(101)]
        dw = max(1.0, min(200.0, hh_mm - dh_mm))
        try:
            c, k, _ = G.layout_closing(path, False, s, dh_mm, ds_mm, dw, self._close_n() or SD.CLOSE_N_DEFAULT,
                                       n_max=SD.CLOSE_N_MAX, free_end=True, tiny=SD.CLOSE_TOL_MM)
            return c, k
        except Exception:
            return [], []

    def _preview_clear(self, msg=""):
        self.preview_canvas.Children.Clear()
        self.preview_info_tb.Text = msg

    def _get_soft_br(self):
        if self._soft_br is None:
            self._soft_br = _make_soft_brush()
        return self._soft_br

    def _draw_preview(self, centres, kinds, dh_mm, ds_mm, hh_mm, anim_step=None):
        """Render pile circles on preview_canvas.
        anim_step=None: all piles shown full. anim_step=N: first N+1 shown, N highlighted orange."""
        W, H, CY, MX = 756.0, 220.0, 110.0, 16.0
        can = self.preview_canvas
        can.Children.Clear()
        if not centres:
            return
        xs = [c[0] for c in centres]
        span = max(xs) - min(xs)
        if span < 1.0:
            return
        scale = (W - 2.0 * MX) / span
        r_h = max(5.0, min(40.0, dh_mm * scale / 2.0))
        r_s = max(5.0, min(40.0, ds_mm * scale / 2.0))
        x0 = min(xs)

        # centre line (light gray horizontal)
        cl = _Line()
        cl.X1, cl.Y1, cl.X2, cl.Y2 = MX - 4, CY, W - MX + 4, CY
        cl.Stroke = _SolidBrush(_WColor.FromRgb(180, 180, 180))
        cl.StrokeThickness = 1.0
        can.Children.Add(cl)

        # pile circles
        n_show = len(centres) if anim_step is None else (anim_step + 1)
        soft_br = self._get_soft_br()
        hard_fill = _SolidBrush(_WColor.FromRgb(30, 30, 30))
        black_stroke = _SolidBrush(_Colors.Black)
        ghost_fill = _SolidBrush(_WColor.FromArgb(35, 100, 100, 100))
        ghost_stroke = _SolidBrush(_WColor.FromArgb(70, 0, 0, 0))

        for i, (c, k) in enumerate(zip(centres, kinds)):
            xpx = MX + (c[0] - x0) * scale
            is_hard = (k == SR.HARD)
            r = r_h if is_hard else r_s

            e = _Ellipse()
            e.Width = r * 2.0
            e.Height = r * 2.0

            if i >= n_show:                                # future pile: faint ghost
                e.Fill = ghost_fill
                e.Stroke = ghost_stroke
                e.StrokeThickness = 1.0
                lbl_alpha = 60
            elif anim_step is not None and i == anim_step: # current animated pile: orange
                e.Fill = _SolidBrush(_WColor.FromRgb(220, 110, 20))
                e.Stroke = _SolidBrush(_WColor.FromRgb(160, 60, 0))
                e.StrokeThickness = 2.5
                lbl_alpha = 255
            else:                                          # static / past pile
                e.Fill = hard_fill if is_hard else soft_br
                e.Stroke = black_stroke
                e.StrokeThickness = 1.5
                lbl_alpha = 255

            _Canvas.SetLeft(e, xpx - r)
            _Canvas.SetTop(e, CY - r)
            can.Children.Add(e)

            # "H" / "S" label centred in circle
            tb = _TextBlock()
            tb.Text = "H" if is_hard else "S"
            fs = max(8.0, min(14.0, r * 0.75))
            tb.FontSize = fs
            if lbl_alpha < 255:
                tb.Foreground = _SolidBrush(_WColor.FromArgb(lbl_alpha, 0, 0, 0))
            elif i == anim_step:
                tb.Foreground = _SolidBrush(_Colors.White)
            else:
                tb.Foreground = _SolidBrush(_Colors.White if is_hard else _Colors.Black)
            _Canvas.SetLeft(tb, xpx - fs * 0.32)
            _Canvas.SetTop(tb, CY - fs * 0.58)
            can.Children.Add(tb)

        # dimension annotation above first pair of piles (show c/c HARD to HARD)
        if len(centres) >= 2:
            xs2 = [(i, c[0]) for i, (c, k) in enumerate(zip(centres, kinds)) if k == SR.HARD]
            if len(xs2) >= 2:
                ia, xa = xs2[0]
                ib, xb = xs2[1]
                xa_px = MX + (xa - x0) * scale
                xb_px = MX + (xb - x0) * scale
                y_dim = CY - max(r_h, r_s) - 18.0
                tick = _Line()
                tick.X1, tick.Y1, tick.X2, tick.Y2 = xa_px, y_dim - 4, xa_px, y_dim + 4
                tick.Stroke = _SolidBrush(_WColor.FromRgb(80, 80, 80))
                tick.StrokeThickness = 1.0
                can.Children.Add(tick)
                tick2 = _Line()
                tick2.X1, tick2.Y1, tick2.X2, tick2.Y2 = xb_px, y_dim - 4, xb_px, y_dim + 4
                tick2.Stroke = _SolidBrush(_WColor.FromRgb(80, 80, 80))
                tick2.StrokeThickness = 1.0
                can.Children.Add(tick2)
                dline = _Line()
                dline.X1, dline.Y1, dline.X2, dline.Y2 = xa_px, y_dim, xb_px, y_dim
                dline.Stroke = _SolidBrush(_WColor.FromRgb(80, 80, 80))
                dline.StrokeThickness = 1.0
                can.Children.Add(dline)
                dtb = _TextBlock()
                dtb.Text = "{:.0f}".format(hh_mm)
                dtb.FontSize = 11.0
                dtb.Foreground = _SolidBrush(_WColor.FromRgb(60, 60, 60))
                _Canvas.SetLeft(dtb, (xa_px + xb_px) / 2.0 - 16)
                _Canvas.SetTop(dtb, y_dim - 16)
                can.Children.Add(dtb)

    def _anim_tick(self, sender, args):
        self._anim_step += 1
        if self._anim_step >= len(self._prev_kinds):
            self._anim_step = 0
        self._draw_preview(self._prev_centres, self._prev_kinds,
                           self._prev_dh, self._prev_ds, self._prev_hh,
                           anim_step=self._anim_step)
        self.anim_info_tb.Text = "Pile {} of {}".format(self._anim_step + 1, len(self._prev_kinds))

    def play_click(self, sender, args):
        if self._timer is None:
            return
        if self._timer.IsEnabled:
            self._timer.Stop()
            self.play_btn.Content = "Play"
            self.anim_info_tb.Text = ""
            self._draw_preview(self._prev_centres, self._prev_kinds,
                               self._prev_dh, self._prev_ds, self._prev_hh)
        else:
            if not self._prev_centres:
                return
            self._anim_step = -1
            self._timer.Start()
            self.play_btn.Content = "Pause"

    def refresh(self):
        val = self._parse(self._box(self.driver))
        if val is None or val <= 0:
            self.live_tb.Text = "Type c/c HARD to HARD, a cutting depth or a leftover SOFT web."
            self.ok_btn.IsEnabled = False
            return
        dh, ds = self._diams()
        if not (dh and ds):
            lines = []
            hard_lbl = self.hard_cb.SelectedItem
            soft_lbl = self.soft_cb.SelectedItem
            for lbl, kind, d in ((hard_lbl, "HARD", dh), (soft_lbl, "SOFT", ds)):
                if lbl and lbl != SAME and not d:
                    err = SR._DIAM_ERRS.get(lbl)
                    if err:
                        lines.append("{}  '{}': {}".format(kind, lbl, err))
                    else:
                        lines.append("{}  '{}': size will be read after Next.".format(kind, lbl))
            if not lines:
                lines = ["{} {}: pile size will be read after Next, then the rest is worked out.".format(
                    SD.SPACING_LABELS[self.driver], SD.fmt_num(val))]
            self.live_tb.Text = "\n".join(lines)
            self.ok_btn.IsEnabled = True
            return
        hh = SD.hh_from(self.driver, val, dh, ds)
        v = SD.spacing_values(hh, dh, ds)
        errs, warns = SD.check_spacing(hh, dh, ds)
        soft_lbl = self.soft_cb.SelectedItem
        for kind, lbl, d in ((SR.HARD, self.hard_cb.SelectedItem, dh), (SR.SOFT, soft_lbl, ds)):
            if lbl in self.types and not (kind == SR.SOFT and soft_lbl == SAME):
                msg = SD.size_name_mismatch(kind, SR.type_name(self.types[lbl]), d)
                if msg:
                    errs.append(msg)
        lines = [self._size_text(dh, ds),
                 "c/c HARD to HARD {:.0f}, HARD to SOFT {:.0f}.".format(v["spacing_hh"], v["spacing"]),
                 "Cutting depth {:.0f} each side, leftover SOFT web {:.0f}.".format(v["cut"], v["web"])]
        n_close = self._close_n()
        if n_close is None:
            errs.append("Closing SOFT piles: a whole number from 1 to {}.".format(SD.CLOSE_N_MAX))
        else:
            lines.append("Every bay is exactly {:.0f} (straight c/c, through corners and curves). Only the end / the "
                         "loop seam is adjusted, only when needed: 1 SOFT first, else {} up to {} bays.".format(
                             v["spacing_hh"], n_close, SD.CLOSE_N_MAX))
        # pile depth preview.  The ICSPL_Pile family adds 150 mm to the displayed top, so the
        # actual Depth parameter = cutoff - toe - 150.  Check this, not abs(cutoff - toe).
        try:
            co = float((self.cutoff_tb.Text or "").strip())
            th = float((self.toe_hard_tb.Text or "").strip())
            ts_txt = (self.toe_soft_tb.Text or "").strip()
            ts = float(ts_txt) if ts_txt else th
            depth_h = co - th - 150.0
            depth_s = co - ts - 150.0
            if depth_h <= 0:
                errs.append("Cut-off ({:.0f}) must be at least 150 mm above Toe-HARD ({:.0f}).".format(co, th))
            if depth_s <= 0 and ts != th:
                errs.append("Cut-off ({:.0f}) must be at least 150 mm above Toe-SOFT ({:.0f}).".format(co, ts))
            if depth_h > 0 and depth_s > 0:
                if th == ts:
                    lines.append("Pile depth: {:.0f} mm  (cut-off {:.0f}, toe {:.0f}).".format(depth_h, co, th))
                else:
                    lines.append("Pile depth: HARD {:.0f} mm, SOFT {:.0f} mm  (cut-off {:.0f}).".format(
                        depth_h, depth_s, co))
        except (ValueError, TypeError):
            pass
        self.live_tb.Text = "\n".join(lines + errs + warns)
        self.ok_btn.IsEnabled = not errs

    def _num(self, tb, label, allow_blank=False):
        t = (tb.Text or "").strip()
        if not t:
            if allow_blank:
                return None, True
            self.live_tb.Text = "'{}' must be a number (mm).".format(label)
            return None, False
        try:
            return float(t), True
        except ValueError:
            self.live_tb.Text = "'{}' must be a number (mm). You typed: '{}'".format(label, t)
            return None, False

    def ok_click(self, sender, args):
        if self._timer and self._timer.IsEnabled:
            self._timer.Stop()
        val = self._parse(self._box(self.driver))
        if val is None or val <= 0:
            self.live_tb.Text = "Type a spacing value first."
            self.main_tabs.SelectedIndex = 0    # switch to Settings tab to show the error
            return
        nums = {}
        for key, tb, blank in (("gap", self.gap_tb, False), ("cutoff", self.cutoff_tb, False),
                               ("toe_hard", self.toe_hard_tb, False), ("toe_soft", self.toe_soft_tb, True)):
            nums[key], ok = self._num(tb, key, blank)
            if not ok:
                self.main_tabs.SelectedIndex = 0
                return
        n_close = self._close_n()
        if n_close is None:
            self.live_tb.Text = "Closing SOFT piles: a whole number from 1 to {}.".format(SD.CLOSE_N_MAX)
            self.main_tabs.SelectedIndex = 0
            return
        soft = self.soft_cb.SelectedItem
        self.result = {
            "wall": (self.wall_tb.Text or "").strip(),
            "sym": self.types[self.hard_cb.SelectedItem],
            "soft": SAME if soft == SAME else self.types[soft],
            "level": self.levels[self.level_cb.SelectedItem],
            "spacing_by": self.driver, "spacing_val": val,
            "gap": nums["gap"], "cutoff": nums["cutoff"], "toe_hard": nums["toe_hard"],
            "toe_soft": nums["toe_soft"], "invisible": bool(self.invisible_cb.IsChecked), "close_n": n_close,
        }
        self.Close()

    def cancel_click(self, sender, args):
        if self._timer and self._timer.IsEnabled:
            self._timer.Stop()
        self.Close()


def ask_inputs(cfg, types, diams, levels, default_level):
    """Settings dict from the WPF window, or the simple-prompt fallback. spacing_by / spacing_val record which box
    the drafter set and its value; gap / cutoff / toes are floats (toe_soft may be None)."""
    try:
        win = SBPWallWindow(cfg, types, diams, levels, default_level)
    except Exception:
        win = None                                             # WPF not available: simple prompts below
    if win is not None:
        win.show_dialog()                                      # outside the try, so a cancel's script.exit() is not caught
        if not win.result:
            script.exit()
        return win.result

    t = forms.SelectFromList.show(sorted(types.keys()), title="HARD pile type", multiselect=False)
    st = forms.SelectFromList.show([SAME] + sorted(types.keys()), title="SOFT pile type", multiselect=False)
    lv = forms.SelectFromList.show(sorted(levels.keys()), title="Placement level", multiselect=False)
    if not t or not st or not lv:
        script.exit()
    dh = diams.get(t)
    ds = dh if st == SAME else diams.get(st)
    ask = lambda k, p: forms.ask_for_string(default=str(cfg.get(k, "")), prompt=p, title="SBP Wall")
    res = {"sym": types[t], "soft": SAME if st == SAME else types[st], "level": levels[lv]}
    res["wall"] = (ask("wall", "Wall name") or "").strip()
    by, val = cfg["spacing_by"], num(cfg.get("spacing_val"), "spacing", allow_blank=True)
    if dh:                                                     # start at HARD to HARD = D + 600 (Akash, 6 Oct)
        by, val = "spacing_hh", SD.default_hh(dh)
    if dh and ds:
        shown = SD.linked_boxes(by, val, dh, ds)
        entered = dict((k, num(ask(k, SD.SPACING_LABELS[k] + " (mm). Change ANY ONE of the three, the others follow"),
                               SD.SPACING_LABELS[k], allow_blank=True)) for k in SD.SPACING_KEYS)
        changed = SD.changed_spacing(entered, dict(shown, spacing=None))
        key, v, note, err = SD.spacing_driver(changed, dh, ds)
        if err:
            fail(err)
        if key is not None:
            by, val = key, v
    else:                                                      # size unknown: only HARD to HARD can be resolved now
        by = "spacing_hh"
        val = num(ask("spacing_hh", "c/c HARD to HARD (mm)"), "HARD to HARD")
    res["spacing_by"], res["spacing_val"] = by, val
    res["close_n"] = num(ask("close_n", "Closing SOFT piles (adjust, 1 to {})".format(SD.CLOSE_N_MAX)),
                         "Closing SOFT piles")
    res["gap"] = num(ask("gap", "Gap line to SBP inner edge (mm, min 10)"), "Gap")
    res["cutoff"] = num(ask("cutoff", "Cut-off Level (mm)"), "Cut-off Level")
    res["toe_hard"] = num(ask("toe_hard", "Toe Level - HARD pile (mm)"), "Toe Level - HARD")
    res["toe_soft"] = num(ask("toe_soft", "Toe Level - SOFT pile (mm, blank = same as hard)"),
                          "Toe Level - SOFT", allow_blank=True)
    res["invisible"] = forms.alert("Make your line <Invisible lines>?", yes=True, no=True)
    return res


def print_list(title, lines):
    if lines:
        more = len(lines) - MAX_LISTED
        output.print_md("**{}:**<br>{}".format(title, "<br>".join(SR.html(x) for x in lines[:MAX_LISTED]) + (
            "<br>... and {} more".format(more) if more > 0 else "")))


# ================================================================== MAIN
if not isinstance(doc.ActiveView, ViewPlan):
    fail("Open a plan view first (you need to click the wall side in plan).")

SR.clear_pile_specs()                      # this engine stays alive between runs: read the set-ups again
types = SR.pile_types(doc)
if not types:
    fail("No pile family is loaded in this project (a Structural Foundation family with a diameter or radius, "
         "or 'pile' in its name). Load one, or set one up with Shift+Click on SBP Wall.")
levels = SR.all_levels(doc)

items, closed = get_line_source()

cfg = load_cfg()
used = SR.wall_names(doc)
cfg["wall"] = SD.next_free_name(cfg.get("wall"), used)     # SBP Wall never reuses a name
gl = doc.ActiveView.GenLevel
default_level = gl.Name if gl else cfg["level"]
level0 = levels.get(default_level) or sorted(levels.values(), key=lambda l: l.Elevation)[0]
# read each pile type's diameter once (rolled-back probe), so the form recalculates cutting / web live.
# A family not yet set up gives None; _DIAM_ERRS[label] records why, and the form shows it.
diams = {}
for label, sym in types.items():
    d = SR.type_diameter(doc, sym, level0, label=label)
    diams[label] = SR.to_mm(d) if d is not None else None
inp = ask_inputs(cfg, types, diams, levels, default_level)

wall = inp["wall"] or cfg["wall"]
if wall in used:
    fail("Wall '{}' already exists. SBP Wall never deletes or replaces piles.\n\n"
         "- To change that wall, use SBP Edit.\n"
         "- For a new wall, use another name (next free: {}).".format(wall, SD.next_free_name(wall, used)))
level = inp["level"]
symbols = {SR.HARD: inp["sym"], SR.SOFT: inp["sym"] if inp["soft"] == SAME else inp["soft"]}
# the pile families' diameter / length / cut-off parameters: recognised, or asked once and saved in the model
try:
    for sym in (symbols[SR.HARD], symbols[SR.SOFT]):
        if SR.ensure_pile_spec(doc, sym, level, ask_choice) is None:
            script.exit()
except Exception as ex:
    fail(str(ex))
# the real diameters, read fresh from each pile type: type parameter 'Diameter', else a test pile (Radius x 2)
dia, size_src = {}, {}
for kind in (SR.HARD, SR.SOFT):
    label = SR.type_label(symbols[kind])
    dia[kind], size_src[kind] = SR.type_size(doc, symbols[kind], level, label=label)
    if dia[kind] is None:
        fail("Cannot read the diameter of pile type '{}'.\n\n{}".format(label, SR._DIAM_ERRS.get(label, "")))
dh_mm, ds_mm = SR.to_mm(dia[SR.HARD]), SR.to_mm(dia[SR.SOFT])
errs = [m for m in (SD.size_name_mismatch(kind, SR.type_name(symbols[kind]), SR.to_mm(dia[kind]))
                    for kind in ((SR.HARD,) if symbols[SR.SOFT].Id == symbols[SR.HARD].Id else (SR.HARD, SR.SOFT)))
        if m]
if errs:
    fail("\n\n".join(errs))
# the drafter set ONE spacing box in the form; the other two are worked out from these diameters
hh = SD.hh_from(inp["spacing_by"], inp["spacing_val"], dh_mm, ds_mm)
how = SD.SPACING_LABELS[inp["spacing_by"]] + " you set"
errs, spacing_warns = SD.check_spacing(hh, dh_mm, ds_mm)
if errs:
    fail("\n".join(errs))
s = {
    "spacing_hh": hh, "spacing_by": inp["spacing_by"], "spacing_val": inp["spacing_val"],
    "gap": inp["gap"], "cutoff": inp["cutoff"], "toe_hard": inp["toe_hard"],
    "toe_soft": inp["toe_soft"] if inp["toe_soft"] is not None else inp["toe_hard"],
    "invisible": bool(inp["invisible"]), "close_n": inp.get("close_n", SD.CLOSE_N_DEFAULT),
}
errs = SD.check_settings(s)
if errs:
    fail("\n".join(errs))
s["close_n"] = int(s["close_n"])

save_cfg({
    "wall": wall, "type": SR.type_label(symbols[SR.HARD]),
    "soft_type": "" if inp["soft"] == SAME else SR.type_label(symbols[SR.SOFT]), "level": level.Name,
    "spacing_by": inp["spacing_by"], "spacing_val": SD.fmt_num(inp["spacing_val"]),
    "gap": SD.fmt_num(inp["gap"]),
    "toe_hard": SD.fmt_num(inp["toe_hard"]), "toe_soft": SD.fmt_num(inp["toe_soft"]), "invisible": s["invisible"],
    "close_n": str(s["close_n"]),
})

try:
    pk = uidoc.Selection.PickPoint("Click on the side of the line where the SBP wall should go")
except OperationCanceledException:
    script.exit()
side = G.pick_side(SR.chain_samples(items), (pk.X, pk.Y))

# ------------------------------------------------------------------ plan and check (nothing written yet)
others = SR.all_piles(doc)
try:
    centres, kinds, info = SR.plan_wall(doc, items, closed, side, s, dia[SR.HARD], dia[SR.SOFT], others, ask_kind)
except Exception as ex:
    fail("Cannot lay out this wall: {}".format(ex))
if not centres:
    fail("No piles to place: the line is too short.")
rows, warns, errs = SR.plan_rows(wall, s, symbols[SR.HARD], symbols[SR.SOFT], centres, kinds, info, closed, how,
                                 size_src)
warns = spacing_warns + warns
output.print_md("## SBP Wall **{}**: check before placing (nothing written yet)".format(SR.html(wall)))
output.print_table(table_data=[[SR.html(a), SR.html(b)] for a, b in rows], columns=["Item", "Value"])
print_list("WARNINGS", warns)
print_list("ERRORS", errs)
bay_rows, bay_cols = SR.bay_table(wall, s, centres, kinds, info, closed)
if bay_rows:
    output.print_md("### Every bay: SOFT with its two HARD piles (straight c/c, corners never adjusted)")
    output.print_table(table_data=[[SR.html(c) for c in r] for r in bay_rows], columns=bay_cols)
v = SD.spacing_values(hh, dh_mm, ds_mm)
nh = sum(1 for k in kinds if k == SR.HARD)
cl = info["layout"]["close"]
summary = ("HARD {:.0f} / SOFT {:.0f} ({})\n"
           "HARD to HARD {:.0f}, cutting depth {:.0f}, leftover web {:.0f}\n"
           "{} piles: {} HARD + {} SOFT\n"
           "Closing zone: {}\n"
           "{} warning(s), {} error(s)").format(
    dh_mm, ds_mm, size_src[SR.HARD] if size_src[SR.HARD] == size_src[SR.SOFT] else "read from the types",
    v["spacing_hh"], v["cut"], v["web"], len(kinds), nh, len(kinds) - nh,
    SD.closing_text(dict(cl, gap=SR.to_mm(cl["gap"]))), len(warns), len(errs))
if not forms.alert(summary, title="SBP Wall {}: check before placing".format(wall),
                   sub_msg="All values are in the report window. Place the piles?" +
                           (" There are ERRORS (see the report)." if errs else ""),
                   yes=True, no=True, warn_icon=bool(warns or errs)):
    output.print_md("Cancelled: nothing was placed.")
    script.exit()

t = Transaction(doc, "SBP Wall - " + wall)
t.Start()
try:
    # --- model lines along reference planes are made now (not earlier: a cancel leaves nothing behind)
    items = SR.make_model_lines(doc, items)
    elements = [e for c, e, r in items]
    styles = SR.visible_styles(elements)

    placed = SR.place_piles(doc, symbols, level, wall, centres, kinds)

    # --- set Cut-off / Toe (calibrated against what Revit displays, per pile type)
    check = SR.apply_levels(doc, placed, s["cutoff"], s["toe_hard"], s["toe_soft"])

    # --- make the drawn line invisible (<Invisible lines>, else our 'SBP Invisible' style turned off)
    line_errors = SR.hide_lines(doc, elements, doc.ActiveView, allow_template_lines) if s["invisible"] else []

    # --- remember everything, so SBP Edit can change the wall later
    SR.save_wall(doc, SR.wall_data(wall, symbols, level, s, items, closed, side, styles))
    t.Commit()
except Exception as ex:
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    fail("Nothing was placed.\n\n{}".format(ex))

# --- SOFT piles cut by HARD piles + HARD/SOFT look (separate step: never undoes the piles)
look = {}
tg = Transaction(doc, "SBP Wall - cut SOFT piles, HARD/SOFT look")
tg.Start()
try:
    joined, jfail, jerr = SR.cut_soft_by_hard(doc, SR.hard_soft_pairs(placed, closed, info["ends"]))
    look["cut"] = "{} overlaps joined (HARD cuts SOFT)".format(joined) + (
        ", {} failed: {}".format(jfail, jerr) if jfail else "")
    look["2D"] = SR.apply_view_filters(doc, doc.ActiveView, allow_template)
    look["3D"] = SR.set_material(doc, [fi for fi, k in placed])
    tg.Commit()
except Exception as ex:
    if tg.HasStarted() and not tg.HasEnded():
        tg.RollBack()
    look = {"cut": "not done: {}".format(ex), "2D": "not applied", "3D": "not applied"}

uidoc.Selection.SetElementIds(List[ElementId]([fi.Id for fi, _ in placed]))

# ------------------------------------------------------------------ report (html(): keeps <...> visible)
big = max(dia[SR.HARD], dia[SR.SOFT])
done = []
if not closed:
    done += [["Start", SR.end_text(info["ends"]["start"], big)], ["End", SR.end_text(info["ends"]["end"], big)]]
done += [
    ["Cut-off / Toe HARD (mm)", "{:.0f} / {:.0f}".format(*check.get(SR.HARD, (0, 0)))],
    ["Cut-off / Toe SOFT (mm)", "{:.0f} / {:.0f}".format(*check.get(SR.SOFT, (0, 0)))],
    ["Drawn line", "left as is" if not s["invisible"] else
     ("NOT made invisible (see below)" if line_errors else "<Invisible lines>")],
    ["SOFT piles cut", look["cut"]],
    ["Settings saved with the wall", "Yes (SBP Edit can change this wall)"],
    ["HARD/SOFT look (2D)", look["2D"]],
    ["Material (3D)", look["3D"]],
]
output.print_md("## SBP Wall **{}**: placed".format(SR.html(wall)))
output.print_table(table_data=[[SR.html(a), SR.html(b)] for a, b in done], columns=["Item", "Value"])
for msg in line_errors:
    output.print_md("**Line style:** {}".format(SR.html(msg)))

comp_rows, n_below, n_above = SR.spacing_compliance_table(placed, {SR.HARD: dh_mm, SR.SOFT: ds_mm}, closed)
output.print_md("### Spacing Compliance  (HARD to next HARD, SOFT to next SOFT; min = diameter + 600 mm)  "
                "{} below / {} above / {} OK".format(
                    n_below, n_above, len(comp_rows) - n_below - n_above))
output.print_table(table_data=[[SR.html(r[0]), r[1], r[2], r[3], SR.html(r[4])] for r in comp_rows],
                   columns=["Pile", "Diam (mm)", "Same-type c/c (mm)", "Required (mm)", "Spacing Compliance"])

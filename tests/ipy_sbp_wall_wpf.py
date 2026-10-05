# -*- coding: utf-8 -*-
"""SBP Wall's spacing window in pyRevit's own IronPython 2.7.12 engine, outside Revit.

    powershell -STA -ExecutionPolicy Bypass -File tools\\ipy_host.ps1 -Py tests\\ipy_sbp_wall_wpf.py
Checks that SBPWallWindow.xaml loads with its named controls and events, and that the three linked spacing boxes
recalculate live: HARD to HARD 2000 with 1500/1500 gives cutting 500 and web 500 (not 300 / 600), and clearing a
box does not crash (the derived boxes just go blank). Revit is not needed; json is stubbed.
"""
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")
clr.AddReference("System.IO")
clr.AddReference("System.Threading")
clr.AddReference("System.Windows")
import imp
import sys
from System.IO import File, Path

sys.modules["json"] = imp.new_module("json")          # stdlib package, supplied inside Revit
# REPO and ENGINE_DIR are injected by ipy_host.ps1; derive from __file__ when not present.
if "REPO" not in globals():
    REPO = Path.GetFullPath(Path.Combine(Path.GetDirectoryName(__file__), ".."))
_lib = Path.Combine(REPO, "pyRevit", "SBP.extension", "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)
import sbp_data as SD

BUTTON = Path.Combine(REPO, "pyRevit", "SBP.extension", "ERSS.tab", "Piling.panel", "SBP Wall.pushbutton")
clr.AddReferenceToFileAndPath(Path.Combine(ENGINE_DIR, "pyRevitLabs.IronPython.Wpf.dll"))
import _wpf as wpf
from System.Threading import Thread, ThreadStart, ApartmentState
from System.Windows import Window

SPACING_BOX = {"spacing_hh": "hh_tb", "cut": "cut_tb", "web": "web_tb"}
NAMES = ["wall_tb", "hard_cb", "soft_cb", "level_cb", "hh_tb", "cut_tb", "web_tb", "gap_tb", "cutoff_tb",
         "toe_hard_tb", "toe_soft_tb", "invisible_cb", "live_tb", "ok_btn", "close_tb",
         "main_tabs", "preview_canvas", "preview_info_tb", "play_btn", "anim_info_tb"]
result = []


def run():
    try:
        # a cut-down SBPWallWindow: the same XAML, the live logic (SD.linked_boxes) as the real class
        class W(Window):
            def __init__(self):
                self._ready = False
                self._sync = False
                self.driver = "spacing_hh"
                self.dh = self.ds = 1500.0
                wpf.LoadComponent(self, Path.Combine(BUTTON, "SBPWallWindow.xaml"))
                self._ready = True

            def _box(self, key):
                return getattr(self, SPACING_BOX[key])

            def _parse(self, tb):
                t = (tb.Text or "").strip()
                try:
                    return float(t) if t else None
                except ValueError:
                    return None

            def _apply(self, driver):
                if not self._ready:
                    return
                self._sync = True
                try:
                    boxes = SD.linked_boxes(driver, self._parse(self._box(driver)), self.dh, self.ds)
                    for k in SD.SPACING_KEYS:
                        if k != driver:
                            self._box(k).Text = SD.fmt_num(boxes[k])
                finally:
                    self._sync = False

            def hh_changed(self, s, a):
                if self._ready and not self._sync:
                    self.driver = "spacing_hh"
                    self._apply("spacing_hh")

            def cut_changed(self, s, a):
                if self._ready and not self._sync:
                    self.driver = "cut"
                    self._apply("cut")

            def web_changed(self, s, a):
                if self._ready and not self._sync:
                    self.driver = "web"
                    self._apply("web")

            def type_changed(self, s, a):
                pass

            def levels_changed(self, s, a):
                if self._ready and not self._sync:
                    self.refresh()

            def play_click(self, s, a):
                pass

            def ok_click(self, s, a):
                pass

            def cancel_click(self, s, a):
                pass

        w = W()
        missing = [n for n in NAMES if getattr(w, n, None) is None]
        w.hh_tb.Text = "2000"                                  # user types HARD to HARD -> cut/web recalc live
        live1 = (w.cut_tb.Text, w.web_tb.Text)
        w.cut_tb.Text = "350"                                  # user types a cutting depth -> HH and web follow
        live2 = (w.hh_tb.Text, w.web_tb.Text)
        w.hh_tb.Text = ""                                      # clearing must not crash; derived boxes blank
        live3 = (w.cut_tb.Text, w.web_tb.Text)
        result.append("XAML LOADED: {} controls, missing {}; HH2000->cut/web {}; cut350->hh/web {}; cleared->{}".format(
            len(NAMES) - len(missing), missing or "none", live1, live2, live3))
        w.Close()
    except Exception as ex:
        inner = getattr(ex, "clsException", None)
        while inner is not None and inner.InnerException is not None:
            inner = inner.InnerException
        result.append("XAML FAILED: {}: {}{}".format(type(ex).__name__, ex,
                      ("\n  inner: " + inner.GetType().Name + ": " + inner.Message) if inner else ""))


t = Thread(ThreadStart(run))
t.SetApartmentState(ApartmentState.STA)
t.Start()
t.Join()
print(result[0])

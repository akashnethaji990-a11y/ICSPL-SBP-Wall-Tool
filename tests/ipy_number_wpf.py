# -*- coding: utf-8 -*-
"""Number button in pyRevit's own IronPython 2.7.12 engine, outside Revit (28 Sep bug: No module named Windows).

Run it with the host (Windows PowerShell 5.1, .NET Framework engine):
    powershell -STA -ExecutionPolicy Bypass -File tools\\ipy_host.ps1 -Py tests\\ipy_number_wpf.py
    ... -Arg before   drops the clr.AddReference lines: must fail with the old import error.
Checks: the script's real import block (Revit API lines and stdlib files skipped: Revit supplies them), then the
real NumberWindow.xaml loaded with wpf.LoadComponent as pyRevit does, with its events bound to Python methods.
"""
import clr
from System.IO import File, Path

BUTTON = Path.Combine(REPO, "pyRevit", "SBP.extension", "ERSS.tab", "Piling.panel", "Number.pushbutton")
src = File.ReadAllText(Path.Combine(BUTTON, "script.py")).splitlines()

# the script's own import block: from "import json" to just before "from pyrevit import"
start = [i for i, l in enumerate(src) if l.startswith("import json")][0]
stop = [i for i, l in enumerate(src) if l.startswith("from pyrevit import")][0]
block = []
for l in src[start:stop]:
    if l.startswith("from Autodesk") or l in ("import json", "import os"):
        continue                              # Revit API / stdlib files: supplied inside Revit
    if ARG == "before" and ("clr.AddReference" in l or l.strip() == "import clr"):
        continue
    block.append(l)
print("import block, %d lines, mode %s" % (len(block), ARG or "after"))
exec("\n".join(block))
print("IMPORTS OK: Visibility, VerticalAlignment, Thickness, StackPanel, TextBlock, ComboBox, Orientation")

# pyRevit loads its wpf module like this (pyrevit/framework.py); "wpf" is a stdlib wrapper around _wpf
clr.AddReferenceToFileAndPath(Path.Combine(ENGINE_DIR, "pyRevitLabs.IronPython.Wpf.dll"))
import _wpf as wpf
from System.Threading import Thread, ThreadStart, ApartmentState
from System.Windows import Window

NAMES = ["walls_tb", "soft_tb", "hard_tb", "continue_rb", "new_rb", "label_grid", "tag_cb", "offset_tb",
         "rot_along", "rot_across", "rot_fixed", "angle_tb", "side_panel", "labels_note", "live_tb", "ok_btn"]
result = []


def run():
    try:
        class NumberWindow(Window):
            def __init__(self):
                self._ready = False
                self.calls = 0
                wpf.LoadComponent(self, Path.Combine(BUTTON, "NumberWindow.xaml"))
                self._ready = True

            def refresh(self, sender, args):
                if getattr(self, "_ready", False):
                    self.calls += 1

            def ok_click(self, sender, args):
                pass

            def cancel_click(self, sender, args):
                pass

        w = NumberWindow()
        fixed_default, angle_default = w.rot_fixed.IsChecked, w.angle_tb.Text     # before any clicks below
        missing = [n for n in NAMES if getattr(w, n, None) is None]
        # a per-wall side row, built exactly as script.py does
        row = StackPanel()
        row.Orientation = Orientation.Horizontal
        row.Margin = Thickness(0, 2, 0, 2)
        tb = TextBlock()
        tb.Text = "SBP1"
        tb.Width = 170
        tb.VerticalAlignment = VerticalAlignment.Center
        cb = ComboBox()
        cb.Width = 120
        cb.Items.Add("Outside")
        cb.Items.Add("Inside")
        cb.SelectedIndex = 0
        cb.SelectionChanged += w.refresh
        row.Children.Add(tb)
        row.Children.Add(cb)
        w.side_panel.Children.Add(row)
        # events from the XAML (and the built row) reach the Python methods
        before = w.calls
        w.soft_tb.Text = "C1-SP"
        w.rot_along.IsChecked = True
        cb.SelectedIndex = 1
        w.labels_note.Visibility = Visibility.Visible
        result.append("XAML LOADED: %d named controls found, missing %s; default rotation Fixed=%s angle=%s; "
                      "events handled %d" % (len(NAMES) - len(missing), missing or "none", fixed_default,
                                             angle_default, w.calls - before))
        w.Close()
    except Exception as ex:
        inner = getattr(ex, "clsException", None)
        while inner is not None and inner.InnerException is not None:
            inner = inner.InnerException
        result.append("XAML FAILED: %s: %s%s" % (type(ex).__name__, ex,
                                                ("\n  inner: " + inner.GetType().Name + ": " + inner.Message) if inner else ""))


t = Thread(ThreadStart(run))
t.SetApartmentState(ApartmentState.STA)          # WPF needs an STA thread, as in Revit
t.Start()
t.Join()
print(result[0])

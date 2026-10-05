# -*- coding: utf-8 -*-
"""Import sbp_revit in pyRevit's IronPython 2.7 engine against the Revit API DLLs on this PC (outside Revit).

    powershell -STA -ExecutionPolicy Bypass -File tools\\ipy_host.ps1 -Py tests\\ipy_import_smoke.py
Proves every Revit API name the library imports exists (a misspelt class or enum fails here, not in Revit).
Nothing is called: the Revit API only works inside Revit. json (a stdlib package Revit supplies) is stubbed.
"""
import clr
import sys
import imp
from System.IO import Path, Directory, File

api = None
for year in ("2026", "2025", "2024"):
    d = r"C:\Program Files\Autodesk\Revit {}".format(year)
    if File.Exists(Path.Combine(d, "RevitAPI.dll")):
        api = d
        break
if api is None:
    print("SKIPPED: no Revit API DLL found")
else:
    clr.AddReferenceToFileAndPath(Path.Combine(api, "RevitAPI.dll"))
    # RevitAPIUI.dll needs Revit's native parts; the library takes only ISelectionFilter from it
    ui = imp.new_module("Autodesk.Revit.UI")
    ui.Selection = imp.new_module("Autodesk.Revit.UI.Selection")
    ui.Selection.ISelectionFilter = object
    sys.modules["Autodesk.Revit.UI"] = ui
    sys.modules["Autodesk.Revit.UI.Selection"] = ui.Selection
    sys.modules["json"] = imp.new_module("json")          # stdlib package, supplied inside Revit
    sys.path.append(Path.Combine(REPO, "pyRevit", "SBP.extension", "lib"))
    import sbp_geom
    import sbp_data
    import sbp_revit
    need = ["pile_types", "ensure_pile_spec", "pile_spec", "all_piles", "diameter_of", "radius_of", "apply_levels",
            "label_types", "unusable_label_types", "place_pile_tags", "place_pile_notes", "delete_number_notes",
            "type_label", "all_foundation_types", "clear_pile_specs"]
    missing = [n for n in need if not hasattr(sbp_revit, n)]
    print("IMPORT OK against {} (Revit API {}); functions missing: {}".format(
        Path.GetFileName(api), sbp_revit.BuiltInCategory.OST_StructuralFoundationTags.GetType().Assembly.GetName().Version,
        missing or "none"))

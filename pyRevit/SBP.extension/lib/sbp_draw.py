# -*- coding: utf-8 -*-
"""Draw-then-build for SBP Wall (IronPython 2.7: no f-strings, use .format()).

SBP Wall with nothing selected calls start_draw(): Revit's own Model Line tool starts, so the drafter
gets Revit's Modify | Place Lines tab with the full Draw panel (Line, Rectangle, Polygon, Circle, Arcs,
Spline, Ellipse, Pick Lines). Revit raises the Idling event only when no tool is active, so the first
Idling after drawing means the drafter has finished (Modify / Esc). The handler then stores the new
lines and runs SBP Wall again, which picks them up with take_drawn().

The handler lives in SBP Wall's pyRevit engine, so that script sets __persistentengine__ = True.
It is subscribed only while waiting and removes itself: no permanent Idling hook.
"""
import time

from Autodesk.Revit.DB import FilteredElementCollector, CurveElement, CurveElementType
from Autodesk.Revit.UI import RevitCommandId, PostableCommand

from pyrevit import script

# pyRevit's id for the SBP Wall button (tab SBP, panel Piling): see GenericUICommand.control_id
WALL_CMD_ID = "CustomCtrl_%CustomCtrl_%SBP%Piling%SBP Wall"
ENV_DRAWN = "SBP_DRAWN"          # "<document title>|<uid>,<uid>,..." of the lines just drawn
START_DELAY_S = 0.8              # ignore the Idling that can come before the line tool has started

_state = {}


def _curve_uids(doc):
    return set(e.UniqueId for e in FilteredElementCollector(doc).OfClass(CurveElement))


def is_waiting():
    return bool(_state.get("on"))


def stop(uiapp):
    """Stop waiting for a drawing (safe to call at any time)."""
    if _state.get("on"):
        try:
            uiapp.Idling -= _on_idle
        except Exception:
            pass
    _state.clear()


def start_draw(uiapp, doc):
    """Remember the existing lines, wait for the drafter to finish, start Revit's Model Line tool."""
    stop(uiapp)
    _state.update({"doc": doc, "title": doc.Title, "t0": time.time(), "known": _curve_uids(doc)})
    uiapp.Idling += _on_idle
    _state["on"] = True
    uiapp.PostCommand(RevitCommandId.LookupPostableCommandId(PostableCommand.ModelLine))


def _on_idle(sender, args):
    """First Idling after the line tool ends: hand the new lines to SBP Wall."""
    uiapp = sender
    try:
        if time.time() - _state.get("t0", 0.0) < START_DELAY_S:
            return
        doc = _state.get("doc")
        uidoc = uiapp.ActiveUIDocument
        if doc is None or not doc.IsValidObject or uidoc is None or not uidoc.Document.Equals(doc):
            stop(uiapp)                     # the drafter switched or closed the document: give up
            return
        known = _state.get("known", set())
        new = [e for e in FilteredElementCollector(doc).OfClass(CurveElement)
               if e.UniqueId not in known and e.CurveElementType == CurveElementType.ModelCurve]
        stop(uiapp)
        if not new:                         # left the tool without drawing: nothing to do
            return
        script.set_envvar(ENV_DRAWN, "{}|{}".format(doc.Title, ",".join(e.UniqueId for e in new)))
        cid = RevitCommandId.LookupCommandId(WALL_CMD_ID)
        if cid is not None and uiapp.CanPostCommand(cid):
            uiapp.PostCommand(cid)          # else: the next SBP Wall click picks the lines up
    except Exception:
        stop(uiapp)


def take_drawn(doc):
    """The lines drawn for SBP Wall in this document (and forget them), or None."""
    value = script.get_envvar(ENV_DRAWN)
    if not value:
        return None
    script.set_envvar(ENV_DRAWN, "")
    title, _, uids = value.partition("|")
    if title != doc.Title:
        return None
    lines = [doc.GetElement(u) for u in uids.split(",") if u]
    lines = [e for e in lines if e is not None]
    return lines or None

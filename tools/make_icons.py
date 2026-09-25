# -*- coding: utf-8 -*-
"""Render the SBP ribbon icons (96x96 PNG, transparent) with headless Edge.

Run from anywhere:  python tools/make_icons.py   (Windows, Microsoft Edge installed)
Then click pyRevit -> Reload in Revit.

icon.png      = dark lines, for Revit's light theme
icon.dark.png = light lines, for Revit's dark theme (pyRevit picks it automatically)
To change an icon, edit its SVG in ICONS below and run the script again.
"""
import os
import struct
import subprocess
import tempfile
import zlib

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "pyRevit", "SBP.extension", "SBP.tab", "Piling.panel")

PAL = {
    "light": dict(ink="#2B3A48", pile="#7D93A9", soft="#FFFFFF", orange="#D97A00", blue="#1F74D0", bluefill="#A9CFF5"),
    "dark":  dict(ink="#E6ECF2", pile="#9FB3C8", soft="none",    orange="#FFB454", blue="#5AA8F0", bluefill="#2F6FB3"),
}

ICONS = {
    "SBP Wall": """
      <line x1="6" y1="18" x2="90" y2="18" stroke="{ink}" stroke-width="7" stroke-linecap="round"/>
      <circle cx="48" cy="58" r="19" fill="{soft}" stroke="{ink}" stroke-width="5"/>
      <circle cx="23" cy="58" r="19" fill="{pile}" stroke="{ink}" stroke-width="5"/>
      <circle cx="73" cy="58" r="19" fill="{pile}" stroke="{ink}" stroke-width="5"/>""",
    "SBP Edit": """
      <circle cx="34" cy="58" r="24" fill="{pile}" stroke="{ink}" stroke-width="5"/>
      <path d="M50 84 L54 68 L80 42 L92 54 L66 80 Z" fill="{orange}" stroke="{ink}" stroke-width="4" stroke-linejoin="round"/>
      <line x1="74" y1="48" x2="86" y2="60" stroke="{ink}" stroke-width="4"/>""",
    "SBP Select": """
      <rect x="6" y="12" width="84" height="72" rx="4" fill="none" stroke="{blue}" stroke-width="5" stroke-dasharray="12 8"/>
      <circle cx="36" cy="48" r="17" fill="{bluefill}" stroke="{blue}" stroke-width="5"/>
      <circle cx="62" cy="48" r="17" fill="none" stroke="{ink}" stroke-width="5"/>""",
    "SBP Line": """
      <path d="M10 84 L40 36 L72 36" fill="none" stroke="{ink}" stroke-width="7" stroke-dasharray="14 8" stroke-linecap="butt" stroke-linejoin="round"/>
      <rect x="64" y="22" width="26" height="26" rx="3" fill="{blue}" stroke="{ink}" stroke-width="3"/>
      <rect x="4" y="76" width="14" height="14" rx="2" fill="{blue}"/>""",
    "SBP Count": """
      <rect x="14" y="8" width="68" height="80" rx="6" fill="none" stroke="{ink}" stroke-width="6"/>
      <circle cx="30" cy="30" r="6" fill="{pile}"/><line x1="42" y1="30" x2="70" y2="30" stroke="{ink}" stroke-width="6" stroke-linecap="round"/>
      <circle cx="30" cy="50" r="6" fill="{pile}"/><line x1="42" y1="50" x2="70" y2="50" stroke="{ink}" stroke-width="6" stroke-linecap="round"/>
      <line x1="26" y1="70" x2="70" y2="70" stroke="{ink}" stroke-width="6" stroke-linecap="round"/>""",
}


def png_info(path):
    """(width, height, colour type, alpha of the top-left pixel): enough to check transparency."""
    data = open(path, "rb").read()
    w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
    pos, idat = 8, b""
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        if typ == b"IDAT":
            idat += data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
    raw = zlib.decompress(idat)
    alpha = raw[1 + 3] if ctype == 6 else None   # first scanline: filter byte, then RGBA of pixel 0
    return w, h, ctype, alpha


def render(src, out, tries=3):
    """Screenshot one icon. Own throw-away Edge profile, so it never attaches to an open Edge;
    retried if Edge hangs."""
    profile = os.path.join(tempfile.gettempdir(), "sbp_icon_edge_profile")
    for attempt in range(tries):
        try:
            subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                            "--user-data-dir=" + profile, "--default-background-color=00000000",
                            "--window-size=96,96", "--screenshot=" + out, "file:///" + src.replace("\\", "/")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
            return
        except subprocess.TimeoutExpired:
            if attempt == tries - 1:
                raise


def main():
    src = os.path.join(tempfile.gettempdir(), "sbp_icon_src.html")
    for name, body in ICONS.items():
        for theme, fname in (("light", "icon.png"), ("dark", "icon.dark.png")):
            html = ('<html><head><style>html,body{{margin:0;padding:0;background:transparent;overflow:hidden}}'
                    'svg{{display:block}}</style></head><body><svg xmlns="http://www.w3.org/2000/svg" width="96" '
                    'height="96" viewBox="0 0 96 96">{}</svg></body></html>').format(body.format(**PAL[theme]))
            with open(src, "w") as f:
                f.write(html)
            out = os.path.join(PANEL, name + ".pushbutton", fname)
            render(src, out)
            print("{:11s} {:14s} {}x{} colour type {} top-left alpha {}".format(name, fname, *png_info(out)))


if __name__ == "__main__":
    main()

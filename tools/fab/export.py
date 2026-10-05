"""PHASE 9: flat 2D laser output per sheet — DXF (primary), SVG, PDF preview.

Layers / colours (common laser-driver convention, confirm with your shop):
  CUT       red   (ACI 1, RGB 255,0,0)   closed polylines, kerf-compensated
  SCORE     blue  (ACI 5, RGB 0,0,255)   fold / bend scores (vector, low power)
  ENGRAVE   black (ACI 7, RGB 0,0,0)     guides, alignment marks, outlines (vector engrave)
  NUMBERS   black (ACI 7, RGB 0,0,0)     part tags, sheet info (vector engrave)
  BOUNDARY  grey  (ACI 8)                30x20 sheet edge + margin  - DO NOT CUT
"""
import os
import ezdxf
from ezdxf import units
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union
from geom import as_polys
import nest as NE

LAYERS = {"CUT": (1, (255, 0, 0)), "SCORE": (5, (0, 0, 255)), "ENGRAVE": (7, (0, 0, 0)),
          "NUMBERS": (7, (0, 0, 0)), "BOUNDARY": (8, (128, 128, 128))}


def lines_of(g):
    if g.is_empty:
        return []
    if isinstance(g, LineString):
        return [g]
    return [l for l in getattr(g, "geoms", []) if isinstance(l, LineString) and not l.is_empty]


def sheet_geometry(sheet, P):
    """Dict layer -> list of geometries in sheet inches. CUT entries are closed polygons."""
    out = {k: [] for k in LAYERS}
    k2 = P.kerf_in / 2.0
    for pc in sheet.pieces:
        cut, score, eng, txt = NE.place(pc)
        for poly in as_polys(cut):
            comp = poly.buffer(k2, join_style=2) if k2 > 0 else poly   # outer out, holes in
            for pp in as_polys(comp):
                out["CUT"].append(pp)
        for l in score:
            out["SCORE"] += lines_of(l)
        for l in eng:
            out["ENGRAVE"] += lines_of(l)
        for l in txt:
            out["NUMBERS"] += lines_of(l)
    boundary, margin, marks, info = NE.sheet_annotations(sheet, P)
    out["BOUNDARY"] += [boundary, margin]
    out["ENGRAVE"] += marks
    out["NUMBERS"] += info
    return out


def write_dxf(geo, fn):
    doc = ezdxf.new("R2013", setup=False)
    doc.units = units.IN
    doc.header["$INSUNITS"] = 1
    doc.header["$MEASUREMENT"] = 0
    for name, (aci, rgb) in LAYERS.items():
        lay = doc.layers.add(name, color=aci)
        lay.rgb = rgb
    msp = doc.modelspace()
    for name, items in geo.items():
        for g in items:
            if isinstance(g, Polygon):
                for ring in [g.exterior] + list(g.interiors):
                    msp.add_lwpolyline(list(ring.coords)[:-1], close=True, dxfattribs={"layer": name})
            else:
                msp.add_lwpolyline(list(g.coords), close=False, dxfattribs={"layer": name})
    doc.saveas(fn)


def write_svg(geo, fn, P):
    W, H = P.sheet_w_in, P.sheet_h_in
    col = {"CUT": "#ff0000", "SCORE": "#0000ff", "ENGRAVE": "#000000", "NUMBERS": "#000000", "BOUNDARY": "#808080"}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}in" height="{H}in" viewBox="0 0 {W} {H}">']
    for name, items in geo.items():
        out.append(f'<g id="{name}" fill="none" stroke="{col[name]}" stroke-width="0.001">')
        for g in items:
            rings = ([g.exterior] + list(g.interiors)) if isinstance(g, Polygon) else [g]
            for r in rings:
                pts = " ".join(f"{x:.4f},{H - y:.4f}" for x, y in r.coords)
                tag = "polygon" if isinstance(g, Polygon) else "polyline"
                out.append(f'<{tag} points="{pts}"/>')
        out.append("</g>")
    out.append("</svg>")
    open(fn, "w").write("\n".join(out))


def preview(geo, fn, title, P):
    W, H = P.sheet_w_in, P.sheet_h_in
    fig, ax = plt.subplots(figsize=(15, 10.3))
    for name, c, lw in (("BOUNDARY", "0.6", 0.5), ("CUT", "r", 0.5), ("SCORE", "b", 0.5),
                        ("ENGRAVE", "k", 0.3), ("NUMBERS", "k", 0.3)):
        for g in geo[name]:
            rings = ([g.exterior] + list(g.interiors)) if isinstance(g, Polygon) else [g]
            for r in rings:
                x, y = r.xy
                ax.plot(x, y, color=c, lw=lw)
    ax.set_xlim(-0.2, W + 0.2); ax.set_ylim(-0.2, H + 0.2); ax.set_aspect("equal")
    ax.set_title(title, fontsize=9); ax.tick_params(labelsize=6)
    fig.savefig(fn, dpi=150, bbox_inches="tight"); plt.close(fig)

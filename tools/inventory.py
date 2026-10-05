"""Phase 1 inventory of the original architectural model (read-only).

Writes docs/inventory.csv: one row per object with real and 1:192 scaled
bounding-box dimensions and a proposed fabrication class
(FABRICATE / SIMPLIFY / OMIT / EXCLUDE / NON-PHYSICAL).
"""
import csv, sys
import rhino3dm as r

SRC = sys.argv[1] if len(sys.argv) > 1 else "model/Bagneux_Swimming_Pool_Extension.3dm"
OUT = sys.argv[2] if len(sys.argv) > 2 else "docs/inventory.csv"
SCALE = 192.0                     # 1/16" = 1'-0"
T_MAT_MM = 1.5875                 # nominal 1/16" chipboard (measure actual stock)
mm = lambda metres: metres * 1000.0 / SCALE

m = r.File3dm.Read(SRC)
layers = [l.FullPath for l in m.Layers]

def classify(obj, layer, name, bb):
    n = name.upper()
    if bb.Min.Y > 50:                                 # stray copy offset +104.53 m
        return "EXCLUDE", "duplicate set offset +104.53 m in Y"
    if layer == "Default":
        return "EXCLUDE", "unnamed stray surface outside building"
    if layer.startswith(("REFERENCE", "GRID", "LEVELS", "CONSTRUCTION", "ANALYSIS::SPACES", "MASSING")):
        return "NON-PHYSICAL", "reference / setting-out / analysis volume"
    if layer == "WALLS::WALLS-EXTERIOR" and n == "EXT N WALL" and not obj.Attributes.GetUserString("pass"):
        return "EXCLUDE", "untagged duplicate of pass-06 N wall (x3 coincident)"
    if layer == "ANALYSIS::WATER":
        return "SIMPLIFY", "water surface -> pool basin floor / tint"
    if layer == "STRUCTURE::STRUCTURE-COLUMNS":
        return ("OMIT", "GF column under pool tank, hidden") if n.startswith("S-GC") else ("FABRICATE", "inclined hall leg")
    if layer in ("STRUCTURE::STRUCTURE-BEAMS", "SLABS", "ROOF"):
        return "FABRICATE", ""
    if layer == "STRUCTURE::STRUCTURE-OTHER":
        if n.startswith("POOL 1.07 STEP"):
            return "SIMPLIFY", "5 steps -> engraved lines / 1 stepped strip"
        return "FABRICATE", ""
    if layer == "WALLS::WALLS-EXTERIOR":
        return "FABRICATE", ""
    if layer == "WALLS::WALLS-INTERIOR":
        if "CURVED" in n:
            return "FABRICATE", "curved wall at oval light well / stair drum (scored bend)"
        return "OMIT", "interior partition, not visible in closed model (see clarification)"
    if layer == "WINDOWS":
        if n.startswith("CW UP POST") or n.startswith("CW LOW POST"):
            return "SIMPLIFY", "grid posts -> 1-ply strips"
        if "TRANSOM" in n or "MULLION" in n:
            return "SIMPLIFY", "engrave on glazing panel / omit physically"
        return "SIMPLIFY", "glazing zone -> opening or clear panel"
    if layer == "DOORS":
        return "SIMPLIFY", "engraved outline; major entrances as openings"
    if layer == "STAIRS":
        if n.startswith("BLEACHER"):
            return "FABRICATE", "stacked strips"
        return "SIMPLIFY", "stepped block / scored; mostly enclosed"
    if layer == "RAILINGS":
        return "SIMPLIFY", "solid curved guard strip"
    if layer == "DETAILS":
        if "FASCIA" in n:
            return "FABRICATE", "roof-edge fascia strip"
        return "SIMPLIFY", "engrave"
    return "REVIEW", ""

rows = []
for m_obj in m.Objects:
    a, g = m_obj.Attributes, m_obj.Geometry
    layer, name = layers[a.LayerIndex], a.Name or ""
    bb = g.GetBoundingBox()
    dx, dy, dz = bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y, bb.Max.Z - bb.Min.Z
    cls, why = classify(m_obj, layer, name, bb)
    rows.append(dict(
        guid=str(a.Id), layer=layer, name=name, type=type(g).__name__,
        status=a.GetUserString("status") or "", pass_=a.GetUserString("pass") or "",
        min_x=round(bb.Min.X, 3), min_y=round(bb.Min.Y, 3), min_z=round(bb.Min.Z, 3),
        dx_m=round(dx, 3), dy_m=round(dy, 3), dz_m=round(dz, 3),
        dx_mm=round(mm(dx), 2), dy_mm=round(mm(dy), 2), dz_mm=round(mm(dz), 2),
        min_dim_plies=round(mm(min(v for v in (dx, dy, dz) if v > 1e-6) if any(v > 1e-6 for v in (dx, dy, dz)) else 0) / T_MAT_MM, 2),
        fab_class=cls, note=why, source=a.GetUserString("source") or ""))

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

from collections import Counter
print(Counter(r["fab_class"] for r in rows))
print(Counter((r["layer"], r["fab_class"]) for r in rows))

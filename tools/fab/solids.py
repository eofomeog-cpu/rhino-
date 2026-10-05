"""3D prisms for fabrication parts (assembled model, exploded views, QC)."""
import numpy as np
import mapbox_earcut as earcut
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from geom import as_polys


def poly_mesh(poly, frame, w0, w1):
    """Closed triangle mesh of a planar polygon (with holes) extruded from w0 to w1."""
    poly = orient(poly, 1.0)
    rings = [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in poly.interiors]
    pts2 = np.vstack(rings)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    tri = earcut.triangulate_float64(pts2, ends).reshape(-1, 3)
    n = len(pts2)
    bot = frame.world(pts2[:, 0], pts2[:, 1], np.full(n, w0))
    top = frame.world(pts2[:, 0], pts2[:, 1], np.full(n, w1))
    V = np.vstack([bot, top])
    F = [t[::-1] for t in tri] + [t + n for t in tri]
    start = 0
    for r in rings:
        m = len(r)
        for i in range(m):
            a = start + i; b = start + (i + 1) % m
            F.append([a, b, b + n]); F.append([a, b + n, a + n])
        start += m
    return V, np.array(F)


def part_solids(part, T):
    """[(V, F)] for every instance of a part (laminated plies shown as one block)."""
    out = []
    if getattr(part, "solids3d", None):
        for fr, pr, w0, w1 in part.solids3d:
            for p in as_polys(pr):
                out.append(poly_mesh(p, fr, w0, w1))
        return out
    for fr in part.frames:
        for p in as_polys(part.profile):
            out.append(poly_mesh(p, fr, part.w0, part.w0 + part.plies * T))
    return out

"""Orthographic section through the fabrication model (compare with original)."""
import sys, os
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from shapely.geometry import Polygon
from shapely.ops import unary_union
from solids import part_solids
from render3d import KIT_COL
sys.path.insert(0, os.path.dirname(__file__))
from source import triangles


def slice_mesh(V, F, axis, c):
    """Polygons (2D) of a closed mesh cut by plane coord[axis]=c -> approximate via triangle-plane segments."""
    segs = []
    for f in F:
        P = V[f]; d = P[:, axis] - c
        pts = []
        for i in range(3):
            a, b = P[i], P[(i + 1) % 3]; da, db = d[i], d[(i + 1) % 3]
            if (da < 0) != (db < 0):
                t = da / (da - db); pts.append(a + t * (b - a))
        if len(pts) == 2:
            segs.append(pts)
    return segs


def section(parts, T, axis, c, fn, src=None, xlim=None, title=""):
    other = [i for i in range(3) if i != axis]
    fig, ax = plt.subplots(figsize=(18, 7))
    if src is not None:
        for o in src:
            Tr = triangles(o)
            if len(Tr) == 0: continue
            bb = o.Geometry.GetBoundingBox()
            lo = (bb.Min.X, bb.Min.Y, bb.Min.Z)[axis]; hi = (bb.Max.X, bb.Max.Y, bb.Max.Z)[axis]
            if lo <= c <= hi:
                ax.add_collection(PolyCollection(Tr[:, :, other], facecolor="0.85", edgecolor="none", alpha=0.6))
    for p in parts:
        for V, F in part_solids(p, T):
            if not (V[:, axis].min() <= c <= V[:, axis].max()):
                continue
            for s in slice_mesh(V, F, axis, c):
                s = np.array(s)[:, other]
                ax.plot(s[:, 0], s[:, 1], color=KIT_COL[p.kit], lw=1.2)
    ax.set_aspect("equal"); ax.grid(True, lw=0.3)
    if xlim: ax.set_xlim(*xlim)
    ax.set_ylim(-2, 16); ax.set_title(title)
    fig.savefig(fn, dpi=110, bbox_inches="tight"); plt.close(fig)

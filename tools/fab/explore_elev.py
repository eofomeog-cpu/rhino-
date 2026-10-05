import sys; sys.path.insert(0, "tools/fab")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from source import Source, triangles
from explore_plans import col, skip, S
def view(axes, rng, fn, title, xlim):
    i, j, k = axes  # horizontal, vertical, depth index
    fig, ax = plt.subplots(figsize=(18, 6))
    for o in S.objs:
        lp = S.layers[o.Attributes.LayerIndex]
        if lp.startswith(skip) or lp not in col: continue
        bb = o.Geometry.GetBoundingBox()
        lo = (bb.Min.X, bb.Min.Y, bb.Min.Z)[k]; hi = (bb.Max.X, bb.Max.Y, bb.Max.Z)[k]
        if bb.Min.Y > 50 or hi < rng[0] or lo > rng[1]: continue
        T = triangles(o)
        if len(T) == 0: continue
        ax.add_collection(PolyCollection(T[:, :, [i, j]], facecolor=col[lp], edgecolor="none", alpha=0.5))
    ax.set_xlim(*xlim); ax.set_ylim(-2, 16); ax.set_aspect("equal"); ax.grid(True, lw=0.3)
    ax.set_yticks(range(-2, 17)); ax.tick_params(labelsize=6); ax.set_title(title)
    fig.savefig(fn, dpi=100, bbox_inches="tight"); plt.close(fig)
out = sys.argv[1]
view((1, 2, 0), (10, 13), f"{out}/sec_X11.png", "section slab X 10..13 (Y horiz, Z up)", (-48, 4))
view((1, 2, 0), (35, 40), f"{out}/sec_X37.png", "section slab X 35..40", (-48, 4))
view((0, 2, 1), (-60, -26.5), f"{out}/elev_S.png", "south: everything Y<-26.5 (X horiz)", (-8, 56))

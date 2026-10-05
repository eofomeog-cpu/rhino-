import sys; sys.path.insert(0, "tools/fab")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from source import Source, triangles
S = Source()
skip = ("REFERENCE", "GRID", "LEVELS", "CONSTRUCTION", "MASSING", "ANALYSIS::SPACES", "Default")
col = {"WALLS::WALLS-EXTERIOR": "k", "WALLS::WALLS-INTERIOR": "0.5", "SLABS": "#c8b88a", "STRUCTURE::STRUCTURE-COLUMNS": "r",
       "STRUCTURE::STRUCTURE-BEAMS": "m", "STRUCTURE::STRUCTURE-OTHER": "orange", "ROOF": "#88aacc", "WINDOWS": "c",
       "STAIRS": "g", "ANALYSIS::WATER": "b", "RAILINGS": "y", "DETAILS": "brown"}
def plan(z0, z1, fn, title):
    fig, ax = plt.subplots(figsize=(16, 13))
    for o in S.objs:
        lp = S.layers[o.Attributes.LayerIndex]
        if lp.startswith(skip) or lp not in col: continue
        bb = o.Geometry.GetBoundingBox()
        if bb.Min.Y > 50 or bb.Max.Z < z0 or bb.Min.Z > z1: continue
        T = triangles(o)
        if len(T) == 0: continue
        pc = PolyCollection(T[:, :, :2], facecolor=col[lp], edgecolor="none", alpha=0.35 if lp in ("SLABS","ROOF","ANALYSIS::WATER") else 0.9)
        ax.add_collection(pc)
        if lp in ("WALLS::WALLS-EXTERIOR","SLABS","ROOF","STRUCTURE::STRUCTURE-OTHER","STAIRS") :
            n = (o.Attributes.Name or "")[:22]
            ax.text((bb.Min.X+bb.Max.X)/2, (bb.Min.Y+bb.Max.Y)/2, n, fontsize=5, ha="center")
    ax.set_xlim(-10, 58); ax.set_ylim(-48, 6); ax.set_aspect("equal"); ax.grid(True, lw=0.3)
    ax.set_xticks(range(-10, 59, 2)); ax.set_yticks(range(-48, 7, 2)); ax.tick_params(labelsize=6)
    ax.set_title(title); fig.savefig(fn, dpi=110, bbox_inches="tight"); plt.close(fig)
out = sys.argv[1]
plan(-1, 3.9, f"{out}/plan_GF.png", "GF objects (Z<3.9)")
plan(3.9, 7.0, f"{out}/plan_L1.png", "L1 objects 3.9-7.0")
plan(7.0, 20, f"{out}/plan_L2_roof.png", "L2 + roof (Z>7)")

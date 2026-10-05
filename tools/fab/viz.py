"""Quick-look renders of part profiles (debug + documentation)."""
import math
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path
import numpy as np
from geom import as_polys
import params as PM


def poly_patch(p, **kw):
    verts, codes = [], []
    for ring in [p.exterior] + list(p.interiors):
        c = np.asarray(ring.coords)
        verts += c.tolist(); codes += [Path.MOVETO] + [Path.LINETO] * (len(c) - 2) + [Path.CLOSEPOLY]
    return PathPatch(Path(verts, codes), **kw)


def draw_part(ax, p, scale=1.0, dx=0, dy=0, fc="#d9c9a3"):
    from shapely import affinity
    for g in as_polys(p.profile):
        g = affinity.translate(affinity.scale(g, scale, scale, origin=(0, 0)), dx, dy)
        ax.add_patch(poly_patch(g, facecolor=fc, edgecolor="r", lw=0.6))
    for col, ls in (("k", p.engrave), ("b", p.score), ("0.2", p.text)):
        for l in ls:
            l = affinity.translate(affinity.scale(l, scale, scale, origin=(0, 0)), dx, dy)
            for g in getattr(l, "geoms", [l]):
                c = np.asarray(g.coords); ax.plot(c[:, 0], c[:, 1], color=col, lw=0.4)


def grid(parts, fn, cols=3):
    rows = math.ceil(len(parts) / cols)
    fig, axs = plt.subplots(rows, cols, figsize=(6 * cols, 2.6 * rows))
    for ax, p in zip(np.ravel(axs), parts):
        draw_part(ax, p)
        b = p.profile.bounds
        ax.set_xlim(b[0] - 0.5, b[2] + 0.5); ax.set_ylim(b[1] - 0.5, b[3] + 0.5)
        ax.set_aspect("equal"); ax.tick_params(labelsize=5)
        ax.set_title(f"{p.pid} {p.name[:40]} x{p.qty}", fontsize=7)
    for ax in np.ravel(axs)[len(parts):]:
        ax.axis("off")
    fig.tight_layout(); fig.savefig(fn, dpi=90); plt.close(fig)

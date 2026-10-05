"""Axonometric renders of the fabrication model (matplotlib, painter's algorithm)."""
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from solids import part_solids
import params as PM

KIT_COL = {"SITE": "#cfc6b4", "STRUCT": "#c0504d", "FLOOR": "#e8dcc0", "ROOF": "#9db4c8", "ENV": "#d8c8a0",
           "GLAZ": "#7fb8c4", "CIRC": "#8fae6b", "POOL": "#5a8fd0", "DETAIL": "#b08a5a"}


def axo_project(V, az=-50, el=32):
    a, e = np.radians(az), np.radians(el)
    R1 = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    R2 = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]])
    P = V @ R1.T @ R2.T
    return P[:, [0, 2]], P[:, 1]       # screen xy, depth (larger = farther)


def render(parts, T, fn, offsets=None, az=-50, el=32, title="", hide=None, labels=None, figsize=(16, 11)):
    polys, depth, cols = [], [], []
    light = np.array([0.4, -0.6, 0.8]); light /= np.linalg.norm(light)
    for p in parts:
        if hide and hide(p):
            continue
        off = np.zeros(3) if offsets is None else offsets(p)
        for V, F in part_solids(p, T):
            V = V + off
            S, D = axo_project(V, az, el)
            for f in F:
                tri = V[f]
                n = np.cross(tri[1] - tri[0], tri[2] - tri[0]); nn = np.linalg.norm(n)
                if nn < 1e-12:
                    continue
                n /= nn
                shade = 0.55 + 0.45 * abs(n @ light)
                c = np.array(matplotlib.colors.to_rgb(KIT_COL[p.kit])) * shade
                polys.append(S[f]); depth.append(D[f].mean()); cols.append(np.clip(c, 0, 1))
    order = np.argsort(depth)[::-1]
    fig, ax = plt.subplots(figsize=figsize)
    ax.add_collection(PolyCollection([polys[i] for i in order], facecolors=[cols[i] for i in order],
                                     edgecolors=[tuple(cols[i] * 0.6) for i in order], linewidths=0.15))
    if labels:
        for txt, xyz in labels:
            s, _ = axo_project(np.array([xyz]), az, el)
            ax.text(s[0, 0], s[0, 1], txt, fontsize=8, ha="left", va="center")
    ax.autoscale(); ax.set_aspect("equal"); ax.axis("off"); ax.set_title(title)
    fig.savefig(fn, dpi=120, bbox_inches="tight"); plt.close(fig)

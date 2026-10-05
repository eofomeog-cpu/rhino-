"""Geometry core: local part frames, mesh projection, 2D cleaning, Part record.

Fabrication parts are flat chipboard plates. Each part has
  * a Frame (origin O, in-plane axes u, v, normal n) in REAL metres, model coords;
  * a 2D profile (shapely) in (u, v) real metres;
  * a ply count; the part occupies w in [w0, w0 + plies*T] along n.
Physical sizes are produced only at output time (x M_TO_IN).
"""
from dataclasses import dataclass, field
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString, box, Point
from shapely.ops import unary_union
from shapely import affinity

from source import triangles


# ----------------------------------------------------------------- frames
@dataclass(eq=False)
class Frame:
    O: np.ndarray
    u: np.ndarray
    v: np.ndarray

    def __post_init__(self):
        self.O = np.asarray(self.O, float)
        self.u = np.asarray(self.u, float); self.u /= np.linalg.norm(self.u)
        self.v = np.asarray(self.v, float)
        self.v = self.v - self.u * (self.v @ self.u)
        self.v /= np.linalg.norm(self.v)
        self.n = np.cross(self.u, self.v)

    def local(self, P):
        d = np.asarray(P, float) - self.O
        return np.stack([d @ self.u, d @ self.v, d @ self.n], axis=-1)

    def world(self, U, V, W=0.0):
        return self.O + np.multiply.outer(U, self.u) + np.multiply.outer(V, self.v) + np.multiply.outer(W, self.n)

    def offset(self, dw):
        return Frame(self.O + self.n * dw, self.u, self.v)

    def to_dict(self):
        return {"O": self.O.round(5).tolist(), "u": self.u.round(6).tolist(), "v": self.v.round(6).tolist()}


def vertical_frame(p0, p1, z0=0.0, inward=None):
    """u along plan segment p0->p1, v = +Z, n horizontal.
    If `inward` (xy point) given, flip so n points toward it."""
    p0 = np.array([p0[0], p0[1], z0]); p1 = np.array([p1[0], p1[1], z0])
    f = Frame(p0, p1 - p0, [0, 0, 1])
    if inward is not None and (np.array([inward[0], inward[1], z0]) - p0) @ f.n < 0:
        f = Frame(p1, p0 - p1, [0, 0, 1])
    return f


def plan_frame(z):
    """Horizontal plate: u = +X, v = +Y, n = +Z, origin at height z."""
    return Frame([0, 0, z], [1, 0, 0], [0, 1, 0])


# ------------------------------------------------------------- projection
def clean(g, tol=0.004, simplify=0.01):
    """Merge mesh seams and drop slivers (all in real metres)."""
    if g.is_empty:
        return g
    g = g.buffer(tol, join_style=2).buffer(-tol, join_style=2)
    g = g.simplify(simplify, preserve_topology=True)
    if isinstance(g, MultiPolygon):
        g = MultiPolygon([p for p in g.geoms if p.area > 1e-4])
    return g.buffer(0)


def project(objs, frame, wrange=None):
    """Union of the objects' render-mesh triangles projected onto frame (u, v).
    Optionally keep only triangles whose centroid w lies in wrange."""
    polys = []
    for o in objs:
        T = triangles(o)
        if len(T) == 0:
            continue
        L = frame.local(T.reshape(-1, 3)).reshape(-1, 3, 3)
        for tri in L:
            if wrange is not None:
                wc = tri[:, 2].mean()
                if not (wrange[0] <= wc <= wrange[1]):
                    continue
            p = Polygon(tri[:, :2])
            if p.area > 1e-7:
                polys.append(p.buffer(1e-4, join_style=2))
    return clean(unary_union(polys))


def plan_footprint(objs):
    return project(objs, plan_frame(0.0))


def as_polys(g):
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    return [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]


def largest(g):
    ps = as_polys(g)
    return max(ps, key=lambda p: p.area) if ps else Polygon()


def short_side(poly):
    r = poly.minimum_rotated_rectangle
    c = list(r.exterior.coords)
    a = Point(c[0]).distance(Point(c[1])); b = Point(c[1]).distance(Point(c[2]))
    return min(a, b), max(a, b)


def thin_regions(g, min_w):
    """Material narrower than min_w (same units as g)."""
    opened = g.buffer(-min_w / 2, join_style=2).buffer(min_w / 2, join_style=2)
    d = g.difference(opened)
    return [p for p in as_polys(d) if p.area > (min_w * min_w) * 0.15]


def strip_u(g, u0, u1):
    return g.intersection(box(u0, -1e3, u1, 1e3))


def strip_v(g, v0, v1):
    return g.intersection(box(-1e3, v0, 1e3, v1))


# ------------------------------------------------------------------ parts
@dataclass(eq=False)
class Part:
    pid: str                     # e.g. ENV-003
    kit: str                     # SITE / STRUCT / FLOOR / ROOF / ENV / GLAZ / CIRC / POOL / DETAIL
    name: str
    frame: Frame
    profile: object              # shapely (u, v) real metres
    plies: int = 1
    w0: float = 0.0              # occupies w in [w0, w0 + plies*T]
    instances: list = None       # extra frames for identical repeats (incl. the first)
    engrave: list = field(default_factory=list)   # LineStrings (u, v): guides, centre lines, outlines
    score: list = field(default_factory=list)     # LineStrings (u, v): fold / bend lines
    text: list = field(default_factory=list)      # LineStrings (u, v): tags / lettering (engrave)
    face: int = +1               # which face is engraved / up on the laser bed: +1 = +n side
    step: int = 0
    category: str = "MUST FABRICATE"
    status: str = "DER"
    sources: list = field(default_factory=list)   # original object GUIDs
    note: str = ""
    joint: str = "butt joint, PVA"
    exaggeration: list = field(default_factory=list)   # (element, original_mm, fab_mm, reason)
    hidden: bool = False         # not visible in the finished model (support / stiffener)
    material: str = "1/16\" chipboard"
    tag_ok: bool = True          # tag engraved on the part (False -> tag on sheet beside part)

    @property
    def frames(self):
        return self.instances or [self.frame]

    @property
    def qty(self):
        return len(self.frames) * self.plies

    @property
    def tag(self):
        prefix = {"SITE": "SI", "STRUCT": "ST", "FLOOR": "FL", "ROOF": "RF", "ENV": "EN",
                  "GLAZ": "GL", "CIRC": "CI", "POOL": "PO", "DETAIL": "DE"}[self.kit]
        return prefix + self.pid.split("-")[1]

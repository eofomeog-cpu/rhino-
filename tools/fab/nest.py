"""PHASE 6: nest every physical piece onto 30" x 20" sheets (physical inches).

Pieces keep their kit grouping (one kit family per sheet group), are rotated to
their minimum-area orientation (0/90 deg allowed in packing), and are packed with
a MaxRects best-short-side-fit packer. Kerf compensation is applied only to CUT
geometry, at export time, from the KERF parameter.
"""
import math
from dataclasses import dataclass, field
import numpy as np
from shapely.geometry import box, Polygon, LineString
from shapely.ops import unary_union
from shapely import affinity
import params as PM
import font
from geom import as_polys

SHEET_GROUPS = [
    ("SITE BASE + GF SLAB + POOL (KIT 01, 07)", ["SITE", "POOL"]),
    ("STRUCTURE + FLOORS + GLAZING FRAMES + CIRCULATION + DETAILS (KIT 02, 03, 05b, 06, 08)",
     ["STRUCT", "FLOOR", "GLAZ", "CIRC", "DETAIL"]),
    ("EXTERIOR ENVELOPE + ROOF (KIT 05, 04)", ["ENV", "ROOF"]),
    ("OPTIONAL ACETATE GLAZING (clear 0.010 in sheet, NOT chipboard)", ["ACETATE"]),
]
LABEL_H = 0.05      # sheet-side label text height (in)


@dataclass
class Piece:
    part: object
    index: int            # 1-based instance number among part.qty
    geom: object          # shapely in sheet-local orientation (inches), bbox at origin
    engrave: list
    score: list
    text: list
    label: list           # sheet-side label strokes (relative to piece origin)
    w: float = 0
    h: float = 0
    x: float = 0
    y: float = 0
    rot90: bool = False


@dataclass
class Sheet:
    number: int
    title: str
    kits: list
    pieces: list = field(default_factory=list)

    @property
    def name(self):
        return f"SHEET-{self.number:02d}"


def prepare(part, index, P):
    k = PM.M_TO_IN
    mir = part.face < 0
    def tf(g):
        if mir:
            g = affinity.scale(g, -1, 1, origin=(0, 0))
        return affinity.scale(g, k, k, origin=(0, 0))
    g = tf(part.profile)
    eng = [tf(l) for l in part.engrave]; sco = [tf(l) for l in part.score]; txt = [tf(l) for l in part.text]
    # rotate to minimum-area orientation (long side horizontal)
    r = g.minimum_rotated_rectangle
    c = list(r.exterior.coords)
    e = max(((c[i], c[i + 1]) for i in range(4)), key=lambda e: math.dist(*e))
    ang = -math.degrees(math.atan2(e[1][1] - e[0][1], e[1][0] - e[0][0]))
    if abs(ang) < 0.5 or abs(abs(ang) - 180) < 0.5:
        ang = 0.0
    rot = lambda q: affinity.rotate(q, ang, origin=(0, 0))
    g = rot(g); eng = [rot(l) for l in eng]; sco = [rot(l) for l in sco]; txt = [rot(l) for l in txt]
    b = g.bounds
    mv = lambda q: affinity.translate(q, -b[0], -b[1])
    g = mv(g); eng = [mv(l) for l in eng]; sco = [mv(l) for l in sco]; txt = [mv(l) for l in txt]
    w, h = b[2] - b[0], b[3] - b[1]
    lab = f"{part.tag}" + (f" {index}/{part.qty}" if part.qty > 1 else "")
    if part.qty == 1 and part.tag_ok:
        lab = ""                       # tag already engraved on the part
    label = font.text_lines(lab, LABEL_H, 0, -LABEL_H - 0.04) if lab else []
    lw = font.text_size(lab, LABEL_H)[0] if lab else 0
    pc = Piece(part, index, g, eng, sco, txt, label)
    pc.w = max(w, lw); pc.h = h + LABEL_H + 0.04
    return pc


class MaxRects:
    def __init__(self, W, H):
        self.W, self.H = W, H
        self.free = [(0.0, 0.0, W, H)]

    def insert(self, w, h, allow_rot=True):
        best = None
        for (fx, fy, fw, fh) in self.free:
            for rw, rh, rot in ((w, h, False), (h, w, True)) if allow_rot else ((w, h, False),):
                if rw <= fw + 1e-9 and rh <= fh + 1e-9:
                    ss = min(fw - rw, fh - rh); ls = max(fw - rw, fh - rh)
                    key = (fy, ss, ls)                  # bottom-left preference, then best short side
                    if best is None or key < best[0]:
                        best = (key, fx, fy, rw, rh, rot)
        if best is None:
            return None
        _, x, y, rw, rh, rot = best
        self.split(x, y, rw, rh)
        return x, y, rot

    def split(self, x, y, w, h):
        new = []
        for (fx, fy, fw, fh) in self.free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                new.append((fx, fy, fw, fh)); continue
            if x > fx: new.append((fx, fy, x - fx, fh))
            if x + w < fx + fw: new.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy: new.append((fx, fy, fw, y - fy))
            if y + h < fy + fh: new.append((fx, y + h, fw, fy + fh - y - h))
        # prune contained rectangles
        pr = []
        for i, a in enumerate(new):
            if not any(i != j and a[0] >= b[0] - 1e-9 and a[1] >= b[1] - 1e-9 and a[0] + a[2] <= b[0] + b[2] + 1e-9
                       and a[1] + a[3] <= b[1] + b[3] + 1e-9 and (a != b or j < i) for j, b in enumerate(new)):
                pr.append(a)
        self.free = pr


def nest(parts, P):
    k = max(P.kerf_in, 0.0)                       # compensated outlines grow by kerf/2 on every side
    W = P.sheet_w_in - 2 * P.margin_in - k
    H = P.sheet_h_in - 2 * P.margin_in - 0.25 - k  # bottom band reserved for the sheet info block
    gap = P.part_gap_in + k
    sheets = []
    for title, kits in SHEET_GROUPS:
        if kits == ["ACETATE"]:
            sel = [p for p in parts if getattr(p, "acetate", False)]
        else:
            sel = [p for p in parts if p.kit in kits and not getattr(p, "acetate", False)]
        pieces = [prepare(p, i + 1, P) for p in sel for i in range(p.qty)]
        pieces.sort(key=lambda pc: (-max(pc.w, pc.h), -pc.w * pc.h))
        open_sheets = []
        for pc in pieces:
            placed = False
            for sh, mr in open_sheets:
                r = mr.insert(pc.w + gap, pc.h + gap)
                if r:
                    placed = True; break
            if not placed:
                sh = Sheet(len(sheets) + 1, title, kits); mr = MaxRects(W + gap, H + gap)
                sheets.append(sh); open_sheets.append((sh, mr))
                r = mr.insert(pc.w + gap, pc.h + gap)
                assert r, f"piece too large for a sheet: {pc.part.name} {pc.w:.2f}x{pc.h:.2f}"
            x, y, rot = r
            pc.x = P.margin_in + k / 2 + x; pc.y = P.margin_in + 0.25 + k / 2 + y; pc.rot90 = rot
            sh.pieces.append(pc)
    for s in sheets:
        if len([x for x in sheets if x.title == s.title]) > 1:
            k = [x for x in sheets if x.title == s.title].index(s) + 1
            s.subtitle = f"({k} of {len([x for x in sheets if x.title == s.title])})"
        else:
            s.subtitle = ""
    return sheets


def place(pc):
    """Return (cut polygons, score lines, engrave lines, number/text lines) in sheet inches."""
    def t(g):
        if pc.rot90:
            g = affinity.rotate(g, 90, origin=(0, 0))
            g = affinity.translate(g, pc.h, 0)
        return affinity.translate(g, pc.x, pc.y)
    lab_dy = LABEL_H + 0.04
    geom = affinity.translate(pc.geom, 0, lab_dy)
    sh = lambda l: affinity.translate(l, 0, lab_dy)
    cut = t(geom)
    score = [t(sh(l)) for l in pc.score]
    eng = [t(sh(l)) for l in pc.engrave]
    txt = [t(sh(l)) for l in pc.text] + [t(sh(l)) for l in pc.label]
    return cut, score, eng, txt


def sheet_annotations(sheet, P, n_parts_total=None):
    """Boundary, margin guide, orientation indicator and info block (engraved in the margin)."""
    W, H, m = P.sheet_w_in, P.sheet_h_in, P.margin_in
    boundary = box(0, 0, W, H)
    margin = box(m, m, W - m, H - m)
    h = 0.10
    info = (f"{sheet.name}  {sheet.title} {sheet.subtitle}   SCALE 1:192 (1/16 IN = 1 FT)   "
            f"MATERIAL {'0.010 IN ACETATE' if 'ACETATE' in sheet.kits else '1/16 IN CHIPBOARD'}  "
            f"T={P.t_mat_in:.4f} IN   KERF={P.kerf_in:.4f} IN (USER ADJUSTABLE)   30 X 20 IN")
    txt = font.text_lines(info.replace("/", "/"), h * 0.8, m + 0.05, 0.2)
    # orientation indicator: arrow + TOP at upper-left margin, origin cross lower-left
    ox, oy = 0.18, H - 0.42
    arrow = [LineString([(ox, oy), (ox, oy + 0.3)]), LineString([(ox - 0.08, oy + 0.2), (ox, oy + 0.3), (ox + 0.08, oy + 0.2)])]
    txt += font.text_lines("TOP " + sheet.name, h * 0.8, ox + 0.15, oy + 0.1)
    cross = [LineString([(0.1, 0.25), (0.4, 0.25)]), LineString([(0.25, 0.1), (0.25, 0.4)])]
    return boundary, margin, arrow + cross, txt

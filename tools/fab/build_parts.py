"""PHASES 2-5: fabrication hierarchy, part geometry, joints, part numbers.

Every physical chipboard part is defined here from the ORIGINAL model
(read-only). Geometry is computed in real metres; physical size is applied
only at output. See docs/02_FABRICATION_NOTES.md for the reasoning.
"""
import sys, os, math
from collections import defaultdict
import numpy as np
from shapely.geometry import box, Polygon, LineString, MultiPolygon, Point, MultiLineString
from shapely.ops import unary_union
from shapely import affinity

sys.path.insert(0, os.path.dirname(__file__))
from source import Source, vertices
from geom import (Frame, Part, vertical_frame, plan_frame, project, plan_footprint, clean,
                  as_polys, largest, short_side, strip_u, strip_v)
import params as PM
import font

PART_MAT = "1/16\" chipboard"
ACETATE = "0.010\" clear acetate/PETG (optional)"
GRID = [7.71, 15.10, 22.45, 29.79, 37.14, 44.49]
L1, L2, TOP = 4.00, 7.05, 14.55


def rings(g):
    out = []
    for p in as_polys(g):
        out.append(LineString(p.exterior.coords))
        out += [LineString(i.coords) for i in p.interiors]
    return out


class Builder:
    def __init__(self, P):
        self.P = P
        self.S = Source()
        self.T = P.t_real
        self.fit = P.fit_in / PM.M_TO_IN
        self.parts = []
        self.walls = []        # priority-ordered vertical parts that run continuous through plates
        self.plates = []
        self.log = []

    # ------------------------------------------------------------ helpers
    def add(self, kit, name, frame, profile, **kw):
        p = Part(pid=f"{kit}-000", kit=kit, name=name, frame=frame, profile=profile, **kw)
        self.parts.append(p)
        return p

    def guids(self, objs):
        return [str(o.Attributes.Id) for o in objs]

    def status(self, objs):
        st = {o.Attributes.GetUserString("status") for o in objs}
        return "ASM" if "ASM" in st else "DER"

    def uvbox(self, frame, xy0, xy1, z0, z1):
        a = frame.local([xy0[0], xy0[1], z0]); b = frame.local([xy1[0], xy1[1], z1])
        return box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))

    def wall(self, objs, inward, kit, name, step, plies=None, align="ext", continuous=True,
             mode="bbox", z_range=None, openings=True, **kw):
        """Vertical wall plate. Outline by `mode`:
        bbox   - bounding rectangle of the projection (plain walls; fills slab bands/seams)
        hull   - convex hull (trapezoids: sloped tops/bottoms)
        filled - morphological closing + holes filled (stepped outlines)
        Openings come only from WINDOWS / DOORS objects in the wall plane."""
        fp = largest(plan_footprint(objs))
        c = list(fp.minimum_rotated_rectangle.exterior.coords)[:4]
        edges = [(c[i], c[(i + 1) % 4]) for i in range(4)]
        L = [math.dist(a, b) for a, b in edges]
        i = int(np.argmax(L))
        long_edges = [edges[i], edges[(i + 2) % 4]]
        thick = min(L)
        pin = Point(inward)
        ext = max(long_edges, key=lambda e: LineString(e).distance(pin))
        frame = vertical_frame(ext[0], ext[1], inward=inward)
        raw = project(objs, frame)
        if mode == "bbox":
            prof = box(*raw.bounds)
        elif mode == "hull":
            prof = raw.convex_hull
        else:
            g = raw.buffer(1.0, join_style=2).buffer(-1.0, join_style=2)
            prof = unary_union([Polygon(p.exterior) for p in as_polys(g)])
        if z_range is not None:
            b = prof.bounds
            prof = prof.intersection(box(b[0], z_range[0], b[2], z_range[1])) if mode != "bbox" else \
                box(b[0], z_range[0], b[2], z_range[1])
        n = plies or self.P.plies_for(thick)
        w0 = 0.0 if align == "ext" else (thick - n * self.T) / 2
        part = self.add(kit, name, frame, clean(prof), plies=n, w0=w0, step=step,
                        status=self.status(objs), sources=self.guids(objs), **kw)
        part.real_thickness = thick
        if openings:
            self.openings(part, thick)
        if abs(n * self.T - thick) / thick > 0.15:
            part.exaggeration.append((f"{name} thickness {thick:.2f} m", round(PM.m2in(thick) * 25.4, 2),
                                      round(n * self.P.t_mat_in * 25.4, 2),
                                      "whole plies of chipboard" if n * self.T > thick else
                                      "rounded to nearest whole ply"))
        if continuous:
            self.walls.append(part)
        return part

    def opening_objects(self):
        if not hasattr(self, "_openobjs"):
            res = []
            for o in self.S.find(layer="WINDOWS") + self.S.find(layer="DOORS"):
                n = o.Attributes.Name or ""
                if n.startswith(("CW ", "GF S MULLION", "GF VESTIBULE MULLION")):
                    continue
                bb = o.Geometry.GetBoundingBox()
                corners = np.array([[x, y, z] for x in (bb.Min.X, bb.Max.X) for y in (bb.Min.Y, bb.Max.Y)
                                    for z in (bb.Min.Z, bb.Max.Z)])
                res.append((o, corners))
            self._openobjs = res
        return self._openobjs

    def openings(self, part, thick, keep_short=1.8, keep_area=4.0):
        """Cut large window/door openings in the wall plane; omit small ones (noted)."""
        rects, used = [], []
        for o, C in self.opening_objects():
            L_ = part.frame.local(C)
            if L_[:, 2].mean() < -0.6 or L_[:, 2].mean() > thick + 0.6:
                continue
            r = box(L_[:, 0].min(), L_[:, 1].min(), L_[:, 0].max(), L_[:, 1].max())
            if r.intersection(part.profile).area > 0.05:
                rects.append(r.buffer(0.04, join_style=2)); used.append(o)
        if not rects:
            return
        cut, omitted = [], []
        for comp in as_polys(unary_union(rects)):
            r = box(*comp.bounds).buffer(-0.04, join_style=2)
            s, l = short_side(r)
            if s >= keep_short and r.area >= keep_area:
                cut.append(r)
            else:
                omitted.append(f"{l:.1f}x{s:.1f}")
        if cut:
            part.cut_openings = [c for c, o in zip(cut, cut)]
            part.profile = clean(part.profile.difference(unary_union(cut)))
            part.note += ("; " if part.note else "") + f"{len(cut)} large opening(s) cut"
        if omitted:
            part.note += ("; " if part.note else "") + f"{len(omitted)} small door/window(s) omitted ({', '.join(omitted)} m)"
        part.sources = sorted(set(part.sources + self.guids(used)))

    def plan_rect(self, part, u0=None, u1=None):
        b = part.profile.bounds
        u0 = b[0] if u0 is None else u0; u1 = b[2] if u1 is None else u1
        w0, w1 = part.w0, part.w0 + part.plies * self.T
        f = part.frame
        pts = [f.world(u0, 0, w0), f.world(u1, 0, w0), f.world(u1, 0, w1), f.world(u0, 0, w1)]
        return Polygon([(p[0], p[1]) for p in pts])

    # ------------------------------------------------------- resolution
    def resolve_walls(self):
        """Earlier (higher-priority) continuous walls win at corners/T-junctions."""
        for i, A in enumerate(self.walls):
            rA = self.plan_rect(A)
            for B in self.walls[i + 1:]:
                rB = self.plan_rect(B)
                ov = rA.intersection(rB)
                if ov.area < 1e-4:
                    continue
                pts = np.array(ov.exterior.coords)
                P3 = np.c_[pts, np.zeros(len(pts))]
                uA = A.frame.local(P3)[:, 0]; uB = B.frame.local(P3)[:, 0]
                s = strip_u(A.profile, uA.min() - 1e-3, uA.max() + 1e-3)
                if s.is_empty:
                    continue
                z0, z1 = s.bounds[1], s.bounds[3]
                cut = box(uB.min() - 1e-3, z0, uB.max() + 1e-3, z1)
                before = B.profile.area
                B.profile = clean(B.profile.difference(cut))
                B.profile = unary_union([p for p in as_polys(B.profile) if p.area > 0.05])
                self.log.append(f"trim {B.name} by {A.name}: -{before - B.profile.area:.2f} m2")

    def wall_plan_at(self, W, z0, z1):
        """Plan footprint of vertical part W where its profile spans [z0, z1]."""
        s = strip_v(W.profile, z0 + 0.01, z1 - 0.01)
        rects = []
        for p in as_polys(s):
            b = p.bounds
            rects.append(self.plan_rect(W, b[0], b[2]))
        return unary_union(rects) if rects else Polygon()

    def plate(self, kit, name, objs_or_poly, z_top, plies=1, step=0, trim=True, keep="all", **kw):
        zb = z_top - plies * self.T
        prof = objs_or_poly if not isinstance(objs_or_poly, list) else plan_footprint(objs_or_poly)
        if kw.pop("solid", False):
            g = prof.buffer(0.6, join_style=2).buffer(-0.6, join_style=2)
            prof = unary_union([Polygon(p.exterior) for p in as_polys(g)])
        part = self.add(kit, name, plan_frame(zb), prof, plies=plies, step=step, **kw)
        if isinstance(objs_or_poly, list):
            part.sources = self.guids(objs_or_poly); part.status = self.status(objs_or_poly)
        part.trim = trim; part.keep = keep
        self.plates.append(part)
        return part

    def resolve_plates(self):
        for P in self.plates:
            if not P.trim:
                continue
            zb = P.frame.O[2]; zt = zb + P.plies * self.T
            cuts = [self.wall_plan_at(W, zb, zt) for W in self.walls]
            cuts += [c for c in getattr(P, "extra_cuts", [])]
            g = P.profile.difference(unary_union([c for c in cuts if not c.is_empty]).buffer(1e-3, join_style=2))
            comps = sorted(as_polys(clean(g)), key=lambda p: -p.area)
            if P.keep == "largest":
                comps = comps[:1]
            P.profile = unary_union([c for c in comps if c.area > 0.3])

    # ----------------------------------------------------------- the kit
    def build(self):
        S, T = self.S, self.T
        self.build_site()
        self.build_structure()
        self.build_envelope()
        self.build_glazing()
        self.resolve_walls()
        self.finish_fins()
        self.build_leaning_wall()
        self.build_floors()
        self.build_roofs()
        self.resolve_plates()
        self.build_slots()
        self.build_pools()
        self.build_circulation()
        self.build_details()
        self.finish_profiles()
        self.build_acetate()
        self.build_guides()
        self.number()
        self.build_tags()
        return self.parts

    # ---------------------------------------------------------- KIT 01
    def build_site(self):
        P, T = self.P, self.T
        bw, bh = P.base_w_in / PM.M_TO_IN, P.base_h_in / PM.M_TO_IN
        cx, cy = 23.73, -21.13
        base = box(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
        for k in range(3):
            p = self.add("SITE", f"BASE PLY {k + 1} of 3 (laminated)", plan_frame(-(5 - k) * T + T * 0),
                         base, step=1, status="DER-FAB", category="MUST FABRICATE",
                         note="site base; laminate 3 plies with PVA under weight, edges flush",
                         joint="face-laminated, PVA, edges flush")
            p.frame = plan_frame(-T - (3 - k) * T)
            p.hidden = k < 2
        top = self.parts[-1]
        gf = self.S.one(name="SL-00 GF SLAB")
        slab = plan_footprint([gf])
        # GF slab footprint is engraved by build_guides (part standing on this ply)
        top.base_engrave = True
        x0, y0 = base.bounds[0], base.bounds[1]
        hh = 0.10 / PM.M_TO_IN                     # 0.10" lettering on the visible base
        top.text += font.text_lines("BAGNEUX SWIMMING POOL EXTENSION", hh, x0 + 2.5, y0 + 6.0)
        top.text += font.text_lines("DOMINIQUE COULON & ASSOCIES   1:192 (1/16 IN = 1 FT)", hh * 0.6, x0 + 2.5, y0 + 3.2)
        # scale bar 0-10-20 m
        sx, sy = base.bounds[2] - 26.0, y0 + 3.0
        top.engrave += [LineString([(sx, sy), (sx + 20, sy)])]
        for k in (0, 5, 10, 20):
            top.engrave.append(LineString([(sx + k, sy), (sx + k, sy + (1.2 if k in (0, 10, 20) else 0.7))]))
        top.text += font.text_lines("0", hh * 0.6, sx - 0.4, sy + 1.6) + font.text_lines("10", hh * 0.6, sx + 9.2, sy + 1.6) \
            + font.text_lines("20 M", hh * 0.6, sx + 19.2, sy + 1.6)
        # north arrow (model +Y = north)
        nx, ny = base.bounds[2] - 5.0, base.bounds[3] - 9.0
        top.engrave += [LineString([(nx, ny - 3), (nx, ny + 3)]), LineString([(nx - 1.2, ny + 1.5), (nx, ny + 3), (nx + 1.2, ny + 1.5)])]
        top.text += font.text_lines("N", hh, nx - 0.9, ny + 4.0)
        top.tag_ok = False
        self.base = base
        # GF slab = building plinth (SL-00, 0.30 m = 1 ply)
        self.gf = self.plate("SITE", "GF SLAB SL-00 (plinth)", [gf], 0.0, plies=1, step=2, trim=False,
                             joint="butt onto base, aligned to engraved footprint, PVA")

    # ---------------------------------------------------------- KIT 02
    def build_structure(self):
        S, T, fit = self.S, self.T, self.fit
        # Spine: N bar south face, bearing for the six roof beams (massing M01 S face).
        self.hallW_in, self.hallE_in = 0.0 + T, 52.24 - T     # set after walls; refined below
        m01 = S.one(prefix="M01 NORTH BAR")
        f = vertical_frame((0.0, -4.77), (52.24, -4.77), inward=(26, 0))
        prof = box(0, 0, 52.24, TOP)
        self.spine = self.add("STRUCT", "N-BAR SPINE WALL (beam bearing)", f, prof, plies=1, w0=0.0, step=5,
                              status="DER", sources=self.guids([m01]),
                              note="S face of massing M01 (not modelled as a wall in pass 06); "
                                   "carries the 6 hall roof beams in slots",
                              joint="butt on GF slab; beams key into 6 slots")
        self.walls.append(self.spine)
        # Hall roof beams S-B1..B6: 2 plies each
        beams = [S.one(prefix=f"S-B{i} HALL ROOF BEAM") for i in range(1, 7)]
        self.beam_frames = [Frame([x + T, -4.77, 0], [0, -1, 0], [0, 0, 1]) for x in GRID]
        prof = project([beams[0]], self.beam_frames[0])
        tab = box(-T, 8.64, 0.0, 9.30)
        self.beam_tab = (8.64, 9.30)
        p = self.add("STRUCT", "HALL ROOF BEAM S-B1..B6 (tapered, laminated)", self.beam_frames[0],
                     clean(prof.union(tab)), plies=2, w0=0.0, instances=self.beam_frames, step=11,
                     status="DER", sources=self.guids(beams),
                     joint="2 plies laminated; N-end tab into spine slot; S end glued on leg top",
                     note="top edge = roof slope 0.2059")
        p.exaggeration.append(("roof beam width 0.50 m", 2.6, round(2 * self.P.t_mat_in * 25.4, 2),
                               "2 plies for stiffness/bearing (+22%)"))
        # Inclined legs S-C1..C6
        legs = [S.one(prefix=f"S-C{i} HALL LEG") for i in range(1, 7)]
        prof = project([legs[0]], self.beam_frames[0])
        y0, y1 = -26.74, -26.24
        tab = box(-(y1 + 4.77), L1 - T, -(y0 + 4.77), L1)
        self.leg_slot = (y0, y1)
        p = self.add("STRUCT", "INCLINED HALL LEG S-C1..C6 (laminated)", self.beam_frames[0],
                     clean(prof.union(tab)), plies=2, instances=self.beam_frames, step=11,
                     status="DER", sources=self.guids(legs),
                     joint="2 plies laminated; foot tab through L1 plate slot onto GF bearing rib")
        p.exaggeration.append(("inclined leg width 0.40 m", 2.08, round(2 * self.P.t_mat_in * 25.4, 2),
                               "45 mm slender member; 1 ply would snap"))
        # Sunshade fins S-F1..F7 (1 ply): finished (trimmed, tabbed, grouped) after wall resolution
        self.fins = []
        for fo in [S.one(prefix=f"S-F{i} SUNSHADE FIN") for i in range(1, 8)]:
            bb = fo.Geometry.GetBoundingBox(); x = (bb.Min.X + bb.Max.X) / 2
            fr = Frame([x + T / 2, -4.77, 0], [0, -1, 0], [0, 0, 1])
            self.fins.append(self.add("STRUCT", "SUNSHADE FIN " + fo.Attributes.Name.split()[0], fr,
                                      project([fo], fr), plies=1, step=13, status=self.status([fo]),
                                      sources=self.guids([fo])))
        # S-B7 sunshade top beam (plate under its top at 14.505, sits on fins at 14.20)
        sb7 = S.one(prefix="S-B7 SUNSHADE TOP BEAM")
        self.sb7 = self.plate("STRUCT", "SUNSHADE TOP BEAM S-B7", [sb7], 14.20 + T, plies=1, step=13,
                              face=-1, joint="glued on fin tops; fin lines engraved on underside")
        # Hidden GF bearing rib under the leg line (represents GF wall line at Y~-27, pass 06)
        self.rib("GF BEARING RIB under hall legs (Y -26.5)", (T + 0.01, -26.5), (52.24 - T - 0.01, -26.5), 0, L1 - T, 4,
                 "represents GF interior wall line Y-27 (DER), simplified to one continuous rib")
        # N-bar bulkheads (hidden): at interior wall lines X 14.47 / 33.6
        for x in (14.47, 33.60):
            self.rib(f"N-BAR BULKHEAD X{x:.1f} (hidden stiffener)", (x, -0.31), (x, -4.46), 0, TOP - T, 5,
                     "hidden stiffener at interior wall line; supports RF-02")
        # Wing / podium ribs (hidden)
        for x in (6.52, 18.20):
            self.rib(f"GF WING RIB X{x:.1f}", (x, -42.95), (x, -36.0), 0, L1 - T, 4,
                     "GF interior wall line (DER) simplified to support rib")
        self.rib("GF WALL Y-37 (INT GROUND H, entrance rooms)", (30.68, -36.88), (42.30, -36.88), 0, L1 - T, 4,
                 "real GF interior wall X30.68-42.97 (DER); carries the solarium plate", hidden=False)
        self.rib("L1 WING RIB X6.5 (INT L1 V)", (6.52, -42.95), (6.52, -35.9), L1, L2 - T, 7,
                 "real L1 interior wall X6.39-6.75 (DER)")
        self.rib("L1 WING RIB X22.9 (support)", (22.9, -42.95), (22.9, -36.6), L1, L2 - T, 7,
                 "ASSUMED support line (model leaves wing E side open at L1)", status="ASM")
        self.rib("L1 WALL X24.6 (INT L1 V)", (24.61, -29.62), (24.61, -33.2), L1, L2 - T, 7,
                 "real L1 wall facing solarium (DER, interior layer)", hidden=False)
        for x in (6.52, 18.20):
            self.rib(f"SOUTH BLOCK RIB X{x:.1f} (hidden)", (x, -42.55), (x, -37.0), L2, 14.0 - T, 10,
                     "hidden stiffener; supports RF-03")

    def rib(self, name, xy0, xy1, z0, z1, step, note, status="DER-FAB", hidden=True, kit="STRUCT"):
        T = self.T
        d = np.subtract(xy1, xy0); d = d / np.linalg.norm(d)
        nrm = np.array([-d[1], d[0]])
        p0 = np.array(xy0) - nrm * T / 2; p1 = np.array(xy1) - nrm * T / 2
        f = Frame([p0[0], p0[1], 0], [d[0], d[1], 0], [0, 0, 1])
        Lg = float(np.linalg.norm(np.subtract(xy1, xy0)))
        if np.dot(f.n[:2], nrm) < 0:
            f = Frame([p1[0] + nrm[0] * T, p1[1] + nrm[1] * T, 0], [-d[0], -d[1], 0], [0, 0, 1])
        p = self.add(kit, name, f, box(0, z0, Lg, z1), plies=1, step=step, status=status,
                     note=note, hidden=hidden, category="MUST FABRICATE" if not hidden else "SUPPORT (hidden)",
                     joint="butt on plate below, PVA")
        return p

    # ---------------------------------------------------------- KIT 05
    def build_envelope(self):
        S, T = self.S, self.T
        ext = lambda n: [o for o in S.find(layer="WALLS::WALLS-EXTERIOR", name=n)]
        tagged = lambda objs: [o for o in objs if o.Attributes.GetUserString("pass")]
        W = self.wall
        self.hallW = W(ext("EXT HALL W"), (10, -15), "ENV", "HALL W WALL", 5)
        self.hallE = W(ext("EXT HALL E"), (30, -15), "ENV", "HALL E WALL", 5, mode="filled")
        # refine spine & hall-roof extents to the hall walls' inner faces
        self.hallW_in = self.plan_rect(self.hallW).bounds[2]
        self.hallE_in = self.plan_rect(self.hallE).bounds[0]
        f = self.spine.frame
        a = f.local([self.hallE_in, -4.77, 0])[0]; b = f.local([self.hallW_in, -4.77, 0])[0]
        self.spine.profile = box(min(a, b), 0, max(a, b), TOP)
        W(tagged(ext("EXT N WALL")), (26, -2), "ENV", "N WALL (N bar)", 5)
        W(ext("EXT E OUTER (thin)") + ext("EXT E OUTER (NE box part)") + ext("EXT E OUTER (south, low)"),
          (40, -15), "ENV", "E OUTER SKIN", 5, mode="filled")
        W(ext("EXT N BAR W (0.01 slant)"), (5, -2), "ENV", "N BAR W SLANT", 5)
        W(ext("EXT W SLANT (block)"), (5, -40), "ENV", "W SLANT WALL (south block)", 5)
        W(ext("EXT W SLANT (west zone)"), (2, -30), "ENV", "W SLANT WALL (west zone)", 5)
        W(ext("EXT GARDEN N"), (-2, -30), "ENV", "GARDEN N WALL", 5)
        W(ext("EXT BLOCK NOTCH"), (-3, -40), "ENV", "NOTCH WALL (west zone S)", 7)
        wz = [o for o in S.find(layer="WALLS::WALLS-INTERIOR")
              if o.Geometry.GetBoundingBox().Min.X > -0.3 and o.Geometry.GetBoundingBox().Max.X < 0.6
              and o.Geometry.GetBoundingBox().Max.Y < -25.9 and o.Geometry.GetBoundingBox().Min.Y > -36.0
              and o.Geometry.GetBoundingBox().Max.Z > 7.0]
        p = W(wz, (-3, -30), "ENV", "WEST ZONE E FACE (to terrace)", 7, plies=1, z_range=(L1, TOP))
        p.status = "ASM"
        p.note = ("built from interior-layer walls INT L1 V / INT L2 V facing the terrace; gaps between "
                  "those pieces closed (simplified); stands on L1 plate; " + p.note)
        W(ext("EXT S WALL GF-L1"), (10, -38), "ENV", "WING S WALL (GF-L1)", 5, z_range=(0, L2 - T))
        W(ext("EXT BLOCK S"), (10, -40), "ENV", "SOUTH BLOCK S WALL", 10)
        W(ext("EXT BLOCK E"), (10, -40), "ENV", "SOUTH BLOCK E WALL", 10, mode="hull")
        W(ext("EXT BLOCK S (cantilever)"), (18, -43), "ENV", "CANTILEVER FRONT (S block L1)", 7, mode="hull")
        # Solarium: parapet + 1 m slab-edge band (3.01-4.00) as one plate per side
        for n, inward in (("EXT SOLARIUM PARAPET S", (40, -35)), ("EXT SOLARIUM PARAPET E", (40, -35))):
            p = W(ext(n), inward, "ENV", n.replace("EXT ", "") + " + SLAB EDGE", 7, mode="hull")
            b = p.profile.bounds
            p.profile = clean(p.profile.union(box(b[0], 3.01, b[2], L1 + 0.01)).convex_hull)
            p.note = "parapet (pass 06) + solarium slab edge band 3.01-4.00 (SL-16 soffit)"
        # GF elements under the solarium canopy run up to the L1 plate underside (they carry it)
        p = W(ext("EXT FORECOURT SLANT"), (48, -26), "ENV", "FORECOURT SLANT WALL (PISCINE)", 4,
              z_range=(0, L1 - T), face=-1, tag_ok=False)
        p.note = "top raised from soffit +3.01 to L1 plate underside (+3.70) so it carries the canopy plate"
        p.exaggeration.append(("forecourt wall height 3.01 m", 15.7, round(PM.m2in(L1 - T) * 25.4, 1),
                               "carries the 1-ply solarium plate (real slab 1 m deep)"))
        self.forecourt = p
        # PISCINE lettering (S elevation x693-807): engraved on the OUTER face, stretched to the modelled extent
        let = S.find(prefix="PISCINE LETTER")
        xs = [o.Geometry.GetBoundingBox() for o in let]
        a = p.frame.local([min(b.Min.X for b in xs), -29.3, 0.2])[0]; b_ = p.frame.local([max(b.Max.X for b in xs), -29.3, 0.2])[0]
        fu0, fu1 = sorted([-a, -b_])                      # face view = mirrored u (face = -1)
        lines = font.text_lines("PISCINE", 1.0, 0, 0)
        w_, h_ = font.text_size("PISCINE", 1.0)
        lines = [affinity.translate(affinity.scale(l, (fu1 - fu0) / w_, 2.4 / h_, origin=(0, 0)), fu0, 0.2) for l in lines]
        p.text += [affinity.scale(l, -1, 1, origin=(0, 0)) for l in lines]
        p.sources += self.guids(let)
        p.note += "; PISCINE lettering engraved on the outer face (stroke font stretched to 9.9 x 2.4 m)"
        ret = [o for o in S.find(layer="WALLS::WALLS-INTERIOR") if (o.Attributes.Name or "").startswith("INT GROUND V")
               and abs(o.Geometry.GetBoundingBox().Min.X - 31.04) < 0.05 and o.Geometry.GetBoundingBox().Min.Y < -41.9]
        W(ret, (35, -37), "ENV", "ENTRANCE RETURN WALL X31.2", 4, align="center", z_range=(0, L1 - T))
        self.ne_walls = [W([o], (50, 1.2), "DETAIL", "NE BOX WALL", 14) for o in ext("EXT NE BOX")]

    def trim_by_walls(self, B):
        rB = self.plan_rect(B)
        for A in self.walls:
            ov = self.plan_rect(A).intersection(rB)
            if ov.area < 1e-4:
                continue
            pts = np.array(ov.exterior.coords); P3 = np.c_[pts, np.zeros(len(pts))]
            uA = A.frame.local(P3)[:, 0]; uB = B.frame.local(P3)[:, 0]
            s_ = strip_u(A.profile, uA.min() - 1e-3, uA.max() + 1e-3)
            if s_.is_empty:
                continue
            B.profile = clean(B.profile.difference(box(uB.min() - 1e-3, s_.bounds[1], uB.max() + 1e-3, s_.bounds[3])))
            B.profile = largest(B.profile)
            B.note += ("; " if B.note else "") + f"trimmed where it meets {A.name}"

    def finish_fins(self):
        T = self.T
        self.fin_slots = []
        for f in self.fins:
            self.trim_by_walls(f)
            zb = f.profile.bounds[1]
            if min(abs(zb - L1), abs(zb - L2)) < 0.05:
                seg = strip_v(f.profile, zb, zb + 0.02).bounds
                a, b = seg[0], seg[2]; m = (b - a) * 0.2
                f.profile = clean(f.profile.union(box(a + m, zb - T, b - m, zb)))
                x = f.frame.O[0] - T / 2
                self.fin_slots.append((x, -(a + m) - 4.77, -(b - m) - 4.77, zb))
                f.joint = "tab into plate slot; top glued under S-B7"
            else:
                f.joint = "stands on parapet top (no slot); top glued under S-B7"
        # group identical profiles
        kept = []
        for f in list(self.fins):
            for k in kept:
                if abs(k.profile.area - f.profile.area) < 1e-3 and \
                        k.profile.symmetric_difference(f.profile).area < 0.02:
                    k.instances = (k.instances or [k.frame]) + [f.frame]
                    k.name += "," + f.name.split()[-1]; k.sources += f.sources
                    if f.status == "ASM": k.status = "ASM"
                    self.parts.remove(f); break
            else:
                kept.append(f)

    def occupancy_plan(self, p, z0, z1, step=0.1):
        """Plan footprint of any (possibly inclined) part between heights z0..z1 (convex parts)."""
        b = p.profile.bounds
        U, V, W = np.meshgrid(np.arange(b[0], b[2] + step, step), np.arange(b[1], b[3] + step, step),
                              [p.w0, p.w0 + p.plies * self.T])
        P3 = p.frame.world(U.ravel(), V.ravel(), W.ravel())
        m = (P3[:, 2] >= z0) & (P3[:, 2] <= z1)
        from shapely.geometry import MultiPoint
        return MultiPoint(P3[m][:, :2]).convex_hull.buffer(0.01) if m.sum() > 2 else Polygon()

    def build_leaning_wall(self):
        """South block N face, leaning 3.27 m over 7.50 m: 2-ply plate in its own plane."""
        T = self.T
        o = self.S.one(name="EXT BLOCK N (leaning)")
        d = np.array([0, -3.27, 7.5]); Ls = float(np.linalg.norm(d))
        f = Frame([0, -32.9, L2], [1, 0, 0], d)
        if f.n[1] > 0:
            f = Frame([24.94, -32.9, L2], [-1, 0, 0], d)
        # u limits: W zone E face (exterior x~0.4) to S-block E wall inner face
        east_in = min(self.plan_rect(w).bounds[0] for w in self.walls if w.name == "SOUTH BLOCK E WALL")
        wz = [w for w in self.walls if w.name.startswith("WEST ZONE E FACE")][0]
        west = self.plan_rect(wz).bounds[2]
        u = sorted([f.local([west, -32.9, L2])[0], f.local([east_in, -32.9, L2])[0]])
        perp = 0.5 * 7.5 / Ls
        n = self.P.plies_for(perp)
        p = self.add("ENV", "SOUTH BLOCK N WALL (leaning)", f, box(u[0], 0, u[1], Ls), plies=n, step=10,
                     status="DER", sources=self.guids([o]),
                     note="flat plate in the leaning plane; ends butt S-block E wall and west-zone face; "
                          "bottom edge glued on L2 plate along engraved line",
                     joint="butt, PVA; SAND the inner bottom arris to a ~24 deg bevel so the face sits flush "
                           "on the L2 plate (2-ply edge meets plate at 66 deg)")
        p.qc_allow = {"FL": "intentional: leaning plate edge bevelled by sanding (theoretical 1.2 mm corner)"}
        p.exaggeration.append(("leaning wall thickness 0.46 m", 2.39, round(n * self.P.t_mat_in * 25.4, 2),
                               "whole plies; large unsupported plate"))
        self.leaning = p

    # ---------------------------------------------------------- KIT 05b
    def build_glazing(self):
        S, T = self.S, self.T
        mm = 0.32   # frame member width (real m) = 1.67 mm physical (>= min feature)
        # Hall south curtain wall frame
        wzr = self.plan_rect([w for w in self.walls if w.name.startswith("WEST ZONE E FACE")][0])
        xl, xr = max(self.hallW_in, wzr.bounds[2]), self.hallE_in
        yb = -26.79          # back face against the legs; front = yb - T
        f = vertical_frame((xl, yb - T), (xr, yb - T), inward=(26, -10))
        up = self.uvbox(f, (xl, 0), (xr, 0), L2, 13.86)
        lo = self.uvbox(f, (22.49, 0), (xr, 0), L1, L2 + 0.1)
        g = up.union(lo)
        posts = [xl] + GRID + [xr]
        def hole(x0, x1, z0, z1):
            return self.uvbox(f, (x0, 0), (x1, 0), z0, z1)
        holes = []
        for a, b in zip(posts[:-1], posts[1:]):
            a2 = a + (mm / 2 if a in GRID else 0.02); b2 = b - (mm / 2 if b in GRID else 0.02)
            if a == xl: a2 = xl + mm
            if b == xr: b2 = xr - mm
            for z0, z1 in ((L2 + 0.32, 8.50 - mm / 2), (8.50 + mm / 2, 10.50 - mm / 2), (10.50 + mm / 2, 13.86 - mm)):
                holes.append(hole(a2, b2, z0, z1))
        lposts = [22.49] + GRID[3:] + [xr]
        for a, b in zip(lposts[:-1], lposts[1:]):
            a2 = a + (mm / 2 if a in GRID else mm); b2 = b - (mm / 2 if b in GRID else mm)
            holes.append(hole(a2, b2, L1 + mm, 6.44))
        src = [o for o in S.find(layer="WINDOWS") if (o.Attributes.Name or "").startswith("CW ")]
        p = self.add("GLAZ", "HALL S CURTAIN WALL FRAME", f, clean(g.difference(unary_union(holes))),
                     plies=1, step=12, status="DER", sources=self.guids(src),
                     note="posts at grid C1-C6 + 2 transom bands (8.50, 10.50) kept; 216 transoms/55 mullions "
                          "engraved on optional acetate; frame placed 0.11 m outboard of glass line to clear legs",
                     joint="stands on L1 plate / L2 terrace edge; leg feet glued to back face")
        p.exaggeration.append(("CW posts/transoms 0.08-0.20 m", "0.4-1.0", round(mm * PM.M_TO_IN * 25.4, 2),
                               "minimum laser-cut bar width in chipboard"))
        self.cw = p
        self.walls.append(p)
        self.glaze_src = {"CW": src}
        # GF entrance glazing frames (glazing open; bars at modelled mullions)
        specs = [("GL 0.11 S", "GF S MULLION", (28, -30), "GF ENTRANCE GLAZING 0.11 S"),
                 ("GL 0.18/0.19 S", "GF S MULLION", (36, -36), "GF GLAZING 0.18/0.19 S"),
                 ("GL VESTIBULE E", "GF VESTIBULE MULLION", (38, -35), "GF VESTIBULE GLAZING E")]
        for gname, mname, inward, label in specs:
            glass = S.find(layer="WINDOWS", prefix=gname)
            fp = unary_union([plan_footprint([o]) for o in glass])
            r = fp.minimum_rotated_rectangle
            c = np.array(r.exterior.coords)[:4]
            ax = 0 if np.ptp(c[:, 0]) > np.ptp(c[:, 1]) else 1
            lo_, hi_ = c[:, ax].min(), c[:, ax].max()
            mid = c[:, 1 - ax].mean()
            if ax == 0:
                p0, p1 = (lo_, mid - T / 2), (hi_, mid - T / 2)
            else:
                p0, p1 = (mid - T / 2, lo_), (mid - T / 2, hi_)
            fr = vertical_frame(p0, p1, inward=inward)
            ua = sorted([fr.local([*p0, 0])[0], fr.local([*p1, 0])[0]])
            outer = box(ua[0], 0, ua[1], L1 - T)
            mulls = [o for o in S.find(layer="WINDOWS", prefix=mname)]
            cs = []
            for o in mulls:
                b = o.Geometry.GetBoundingBox(); ctr = [(b.Min.X + b.Max.X) / 2, (b.Min.Y + b.Max.Y) / 2, 0]
                if outer.buffer(0.2).contains(Point(fr.local(ctr)[:2] * [1, 0] + [0, 1])) and \
                        abs(fr.local(ctr)[2]) < 0.6:
                    cs.append(fr.local(ctr)[0])
            bars = sorted(set([ua[0] + mm / 2, ua[1] - mm / 2] + cs))
            hs = []
            for a, b in zip(bars[:-1], bars[1:]):
                if b - a > 2 * mm:
                    hs.append(box(a + mm / 2, mm, b - mm / 2, 3.01))
            prof = clean(outer.difference(unary_union(hs))) if hs else outer
            p = self.add("GLAZ", label, fr, prof, plies=1, w0=0.0, step=4, status=self.status(glass),
                         sources=self.guids(glass + mulls),
                         note="glazing left open (default); bars at modelled mullions; head band 3.01 -> "
                              "plate underside represents solarium slab depth",
                         joint="butt on GF slab under L1 plate, PVA")
            p.exaggeration.append(("GF mullions 0.10 m", 0.52, round(mm * PM.M_TO_IN * 25.4, 2),
                                   "minimum laser-cut bar width"))
            p.glass_rect = (ua[0], 0.0, ua[1], 3.31)

    # ---------------------------------------------------------- KIT 03
    def build_floors(self):
        S, T = self.S, self.T
        l1src = [S.one(name=n) for n in ("SL-13 L1 HALL DECK", "SL-14 L1 HALL DECK EAST",
                                         "SL-15 L1 EXTENSION WING", "SL-16 L1 SOLARIUM")]
        self.l1 = self.plate("FLOOR", "L1 PLATE: pool deck + wing + solarium (+4.00)", l1src, L1, step=6,
                             keep="largest", joint="drops inside continuous walls onto ribs/pool boxes; PVA",
                             note="one plate for the whole +4.00 level; pools and 1.12 void cut out")
        l2src = [S.one(name="SL-22 L2 TERRACE"), S.one(prefix="M06 L1 WING"), S.one(prefix="M08 SOUTH BLOCK")]
        poly = plan_footprint(l2src[:1])
        poly = poly.union(project(l2src[1:2], plan_frame(0), wrange=(L2 - 0.05, L2 + 0.05)))
        poly = poly.union(project(l2src[2:3], plan_frame(0), wrange=(L2 - 0.05, L2 + 0.05)))
        self.l2 = self.plate("FLOOR", "L2 PLATE: terrace + south block floor (+7.05)", clean(poly), L2, step=9,
                             keep="largest", joint="on wing walls/ribs; PVA",
                             note="outline from SL-22 + massing M06 top / M08 bottom (no L2 slab modelled)")
        self.l2.sources = self.guids(l2src); self.l2.status = "DER"

    # ---------------------------------------------------------- KIT 04
    def build_roofs(self):
        S, T = self.S, self.T
        clr = self.P.roof_clear_in / PM.M_TO_IN
        # RF-01 sloped hall roof (2 plies), removable, between hall walls
        k = 0.2059
        v = np.array([0, 1, -k]); cosv = 1 / math.sqrt(1 + k * k)
        xl, xr = self.hallW_in + clr, self.hallE_in - clr
        zu = lambda y: 8.954 - k * y - 0.6
        f = Frame([xl, -26.9, zu(-26.9)], [1, 0, 0], v)
        Ls = (26.9 - 4.77) / cosv
        rf1 = S.one(prefix="RF-01 HALL ROOF SLAB")
        p = self.add("ROOF", "HALL ROOF RF-01 (sloped, REMOVABLE)", f, box(0, 0, xr - xl, Ls), plies=2, step=15,
                     face=-1, status="DER", sources=self.guids([rf1]),
                     joint="2 plies laminated; NOT glued - rests on beams, CW frame and spine, between hall walls",
                     note="true sloped length; lift off to see pools, bleachers, beams")
        for x in GRID:
            for dx in (-T, T):
                p.engrave.append(LineString([(x + dx - xl, 0), (x + dx - xl, Ls)]))
        self.rf1 = p
        fas = S.one(prefix="CW FASCIA")
        ff = vertical_frame((xl, -26.9 - T), (xr, -26.9 - T), inward=(26, -10))
        self.add("ROOF", "HALL ROOF FASCIA (glued to RF-01 S edge)", ff, self.uvbox(ff, (xl, 0), (xr, 0), 13.89, TOP),
                 plies=1, step=15, status="DER", sources=self.guids([fas]),
                 joint="glued to roof south edge; lifts off with the roof")
        z = lambda n: S.one(prefix=n)
        self.plate("ROOF", "N BAR ROOF RF-02", [z("RF-02 NORTH BAR ROOF")], TOP, step=14, keep="largest", solid=True,
                   joint="inset between walls on bulkheads, PVA")
        r3 = self.plate("ROOF", "SOUTH BLOCK ROOF RF-03", [z("RF-03 SOUTH BLOCK ROOF")], 14.0, step=14,
                        keep="largest", solid=True, joint="inset inside parapets on 2 hidden ribs, PVA")
        r3.note = "real 0.60 m; 1 ply used (thickness hidden inside parapets)"
        self.r3 = r3
        zb3 = 14.0 - T
        r3.extra_cuts = [self.occupancy_plan(self.leaning, zb3 - 0.01, 14.01)]
        self.plate("ROOF", "WEST ZONE ROOF RF-06", [z("RF-06 WEST ZONE ROOF")], TOP, step=14, keep="largest", solid=True,
                   joint="inset between walls, PVA")
        self.plate("ROOF", "E STRIP ROOF RF-04", [z("RF-04 EAST STRIP ROOF")], TOP, step=14, keep="largest", solid=True,
                   joint="inset strip between hall E wall and E skin, PVA")
        self.plate("ROOF", "E STRIP LOW ROOF RF-04b", [z("RF-04b EAST STRIP ROOF")], 7.17, step=14,
                   keep="largest", solid=True, joint="inset, PVA")
        self.plate("DETAIL", "NE BOX ROOF RF-05", [z("RF-05 NE BOX ROOF")], 3.02, step=14, keep="largest", solid=True,
                   joint="on NE box walls, PVA")

    # ---------------------------------------------------------- joints
    def build_slots(self):
        T, fit = self.T, self.fit
        # leg slots in L1 plate (2 plies wide)
        y0, y1 = self.leg_slot
        slots = [box(x - T - fit / 2, y0 - fit / 2, x + T + fit / 2, y1 + fit / 2) for x in GRID]
        for x, ya, yb, zb in self.fin_slots:
            s = box(x - T / 2 - fit / 2, min(ya, yb) - fit / 2, x + T / 2 + fit / 2, max(ya, yb) + fit / 2)
            tgt = self.l1 if zb < 5 else self.l2
            if tgt.profile.contains(s):
                tgt.profile = tgt.profile.difference(s)
            else:
                self.log.append(f"WARNING fin slot at x={x:.2f} not inside {tgt.name}")
        for s in slots:
            assert self.l1.profile.contains(s), "leg slot outside L1 plate"
        self.l1.profile = self.l1.profile.difference(unary_union(slots))
        # beam slots in the spine (2 plies wide, tab height + fit)
        z0, z1 = self.beam_tab
        f = self.spine.frame
        for x in GRID:
            a = f.local([x - T - fit / 2, -4.77, z0 - fit / 2]); b = f.local([x + T + fit / 2, -4.77, z1 + fit / 2])
            self.spine.profile = self.spine.profile.difference(
                box(min(a[0], b[0]), a[1], max(a[0], b[0]), b[1]))
        self.spine.joint = "butt on GF slab; 6 through-slots receive beam tabs"

    # ---------------------------------------------------------- KIT 07
    def build_pools(self):
        S, T = self.S, self.T
        def box_walls(name, x0, x1, y0, y1, ztop, step):
            parts = []
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2      # "inward" points AWAY from the pool => ply outside
            for (a, b, inward, lbl) in (((x0 - T, y1), (x1 + T, y1), (cx, y1 + 100), "N"),
                                        ((x0 - T, y0), (x1 + T, y0), (cx, y0 - 100), "S"),
                                        ((x0, y0), (x0, y1), (x0 - 100, cy), "W"),
                                        ((x1, y0), (x1, y1), (x1 + 100, cy), "E")):
                f = vertical_frame(a, b, inward=inward)     # n points AWAY from pool
                # wall occupies the outside of the opening line
                ua = sorted([f.local([*a, 0])[0], f.local([*b, 0])[0]])
                parts.append(self.add("POOL", f"{name} BOX WALL {lbl}", f, box(ua[0], 0, ua[1], ztop), plies=1,
                                      step=step, face=+1, joint="butt on GF slab, box corners overlap N/S over E/W",
                                      note="inner face = pool side (visible through deck opening)"))
            return parts
        # main pool 1.09 — opening from the L1 plate hole
        w = S.one(name="WATER 1.09 SWIMMING POOL")
        bb = w.Geometry.GetBoundingBox()
        x0, x1, y0, y1 = bb.Min.X, bb.Max.X, bb.Min.Y, bb.Max.Y
        for p in box_walls("MAIN POOL 1.09", x0, x1, y0, y1, L1 - T, 3):
            p.sources = self.guids([w, S.one(name="POOL TANK 1.09")]); p.status = "ASM"
        prof_pts = [(x0, 2.10), (38.9, 0.79), (42.8, 0.30), (44.8, 0.30), (x1, 1.45)]
        segs = [math.dist(prof_pts[i], prof_pts[i + 1]) for i in range(len(prof_pts) - 1)]
        Ldev = sum(segs)
        floor = box(0, y0, Ldev, y1)
        p = self.add("POOL", "MAIN POOL FLOOR (folded on 3 scores)", plan_frame(0), floor, plies=1, step=3,
                     status="DER", sources=self.guids([w]), tag_ok=False,
                     joint="rests on 2 profiled ribs; fold gently at scored lines",
                     note="floor profile from WATER 1.09 sec8 (shallow W 2.10 -> deep 0.30 -> E 1.45)")
        acc = 0
        for s in segs[:-1]:
            acc += s; p.score.append(LineString([(acc, y0), (acc, y1)]))
        for yl in (-11.63, -14.12, -16.70, -19.19, -21.67):
            p.engrave.append(LineString([(0.3, yl), (Ldev - 0.3, yl)]))
        # 3D display: one solid per folded segment
        p.solids3d = []
        acc = 0
        for (xa, za), (xb, zb_), s in zip(prof_pts[:-1], prof_pts[1:], segs):
            fr = Frame([xa, 0, za - T], [xb - xa, 0, zb_ - za], [0, 1, 0])
            if fr.n[2] < 0:
                fr = Frame([xa, 0, za - T], [xb - xa, 0, zb_ - za], [0, -1, 0])
            p.solids3d.append((fr, box(0, y0, s, y1) if fr.v[1] > 0 else box(0, -y1, s, -y0), 0.0, T))
            acc += s
        p.dev_pts = prof_pts
        for yr in (y0 + 3.0, y1 - 3.0):
            f = Frame([x0, yr - T / 2, 0], [1, 0, 0], [0, 0, 1])
            pts = [(0, 0)] + [(x - x0, z - T - 0.02) for x, z in prof_pts] + [(x1 - x0, 0)]
            rp = Polygon(pts).buffer(0).intersection(box(0, 0.0, x1 - x0, 10))
            for k, comp in enumerate(sorted(as_polys(clean(rp)), key=lambda c: c.bounds[0])):
                if comp.area < 0.3:
                    continue
                self.add("POOL", f"MAIN POOL FLOOR RIB {'WE'[k]}", f, comp, plies=1, step=3, hidden=True,
                         category="SUPPORT (hidden)", status="DER-FAB",
                         joint="stands on GF slab inside box; deep zone of floor rests on GF slab")
        # merge the two identical ribs
        self.merge_identical("MAIN POOL FLOOR RIB W")
        self.merge_identical("MAIN POOL FLOOR RIB E")
        # learners' pool 1.07
        w = S.one(name="WATER 1.07 LEARNERS POOL")
        bb = w.Geometry.GetBoundingBox()
        x0, x1, y0, y1 = bb.Min.X, bb.Max.X, bb.Min.Y, bb.Max.Y
        for p in box_walls("LEARNERS POOL 1.07", x0, x1, y0, y1, L1 - T, 3):
            p.sources = self.guids([w, S.one(name="POOL TANK 1.07")]); p.status = "ASM"
        fl = self.add("POOL", "LEARNERS POOL FLOOR", plan_frame(2.77 - T), box(x0, y0, x1, y1), plies=1, step=3,
                      status="DER", sources=self.guids([w]), tag_ok=False, joint="rests on 2 ribs, PVA")
        for st in S.find(prefix="POOL 1.07 STEP"):
            b = st.Geometry.GetBoundingBox()
            fl.engrave.append(LineString([(x0 + 0.2, b.Max.Y), (x1 - 0.2, b.Max.Y)]))
        fl.engrave.append(LineString([(x0 + 0.2, y0 + 0.02), (x1 - 0.2, y0 + 0.02)]))
        for yr in (y0 + 3.0, y1 - 3.0):
            f = Frame([x0, yr - T / 2, 0], [1, 0, 0], [0, 0, 1])
            self.add("POOL", "LEARNERS POOL FLOOR RIB", f, box(0, 0, x1 - x0, 2.77 - T - 0.02), plies=1, step=3,
                     hidden=True, category="SUPPORT (hidden)", status="DER-FAB", joint="stands on GF slab")
        self.merge_identical("LEARNERS POOL FLOOR RIB")
        # paddling pool 1.10: outline engraved on the L1 plate (hidden under the terrace)
        pw = S.one(name="WATER 1.10 PADDLING POOL")
        self.l1.engrave += rings(plan_footprint([pw]))
        self.merge_identical("MAIN POOL 1.09 BOX WALL", by_shape=True)
        self.merge_identical("LEARNERS POOL 1.07 BOX WALL", by_shape=True)

    def merge_identical(self, prefix, by_shape=False):
        group = [p for p in self.parts if p.name.startswith(prefix)]
        kept = []
        for p in group:
            for k in kept:
                moved = affinity.translate(p.profile, k.profile.bounds[0] - p.profile.bounds[0],
                                           k.profile.bounds[1] - p.profile.bounds[1])
                if k.plies == p.plies and abs(k.profile.area - p.profile.area) < 1e-3 and \
                        k.profile.buffer(0).symmetric_difference(moved.buffer(0)).area < 1e-3:
                    k.instances = (k.instances or [k.frame]) + [p.frame]
                    k.sources = sorted(set(k.sources + p.sources))
                    k.name = prefix + " (" + "/".join(sorted({k.name[len(prefix):].strip() or "x",
                                                            p.name[len(prefix):].strip() or "x"})) + ")" \
                        if by_shape else k.name
                    self.parts.remove(p)
                    break
            else:
                kept.append(p)
        for k in kept:
            k.name = k.name.replace("( ", "(")

    # ---------------------------------------------------------- KIT 06
    def build_circulation(self):
        S, T = self.S, self.T
        tiers = sorted(S.find(prefix="BLEACHER TIER"), key=lambda o: o.Geometry.GetBoundingBox().Min.Y)
        x0 = max(t.Geometry.GetBoundingBox().Min.X for t in tiers)
        x1 = min(t.Geometry.GetBoundingBox().Max.X for t in tiers)
        ynorth = self.plan_rect(self.spine).bounds[1]
        for k, t in enumerate(tiers):
            b = t.Geometry.GetBoundingBox()
            z = L1 + (k + 1) * 2 * T
            p = self.add("CIRC", f"BLEACHER STACK LEVEL {k + 1} (2 plies)", plan_frame(z - 2 * T),
                         box(x0, b.Min.Y, x1, ynorth), plies=2, step=8, status="ASM",
                         sources=self.guids([t]), joint="stacked and laminated, PVA; north edge against spine",
                         face=-1)
            p.hidden = False
        self.parts[-1].exaggeration.append(("bleacher tier rise 0.45-0.50 m (ASM)", 2.5,
                                            round(2 * self.P.t_mat_in * 25.4, 2),
                                            "whole plies: 2 per tier (+23%)"))

    # ---------------------------------------------------------- KIT 08
    def build_details(self):
        S, T = self.S, self.T
        front = [w for w in self.walls if w.name.startswith("CANTILEVER FRONT")][0]
        wing = [w for w in self.walls if w.name.startswith("WING S WALL")][0]
        rf, rw = self.plan_rect(front), self.plan_rect(wing)
        m = S.one(prefix="M08b SOUTH BLOCK CANTILEVER")
        xa, xb = rf.bounds[0] + T, min(rf.bounds[2], 24.97) - T
        region = box(xa, -46.0, xb, -42.0).difference(rf.buffer(1e-3)).difference(rw.buffer(1e-3))
        cands = [c for c in as_polys(region) if c.bounds[1] > rf.bounds[1] + 0.2 and c.bounds[3] < rw.bounds[3]]
        sof = max(cands, key=lambda c: c.area)
        self.add("DETAIL", "CANTILEVER SOFFIT (S block L1)", plan_frame(5.55), sof, plies=1, step=7,
                 status="DER", sources=self.guids([m]), joint="between front and wing S wall, PVA")
        for x, nm in ((xa, "W"), (xb + T, "E")):
            xm = xa + 0.05 if nm == "W" else xb - 0.05
            seg = LineString([(xm, -50), (xm, -40)]).intersection(sof).bounds
            yf, yw = seg[1], seg[3]
            f = Frame([x, yw, 0], [0, -1, 0], [0, 0, 1])          # n = -X: ply sits inside the box
            self.add("DETAIL", f"CANTILEVER END CAP {nm}", f, box(0, 5.55, yw - yf, L2 - T), plies=1, step=7,
                     status="DER", sources=self.guids([m]), joint="between front and wing S wall, PVA")

    def finish_profiles(self):
        """Remove material thinner than the minimum laser-cut feature (morphological opening)."""
        w = self.P.min_feature_in / PM.M_TO_IN
        for p in self.parts:
            g = p.profile
            op = g.buffer(-w / 2, join_style=2).buffer(w / 2, join_style=2).intersection(g)
            op = unary_union([c for c in as_polys(clean(op, tol=0.002)) if c.area > w * w])
            lost = g.area - op.area
            if lost > 1e-4:
                self.log.append(f"thin-feature cleanup {p.name}: removed {lost:.3f} m2 "
                                f"({100 * lost / g.area:.1f}%)")
                p.profile = op

    def build_acetate(self):
        """OPTIONAL clear glazing panels (0.010" acetate/PETG), glued to the inner face of
        each glazed opening. Separate material and sheet; not required for the chipboard model."""
        m = 0.20                          # overlap onto the frame / wall (real m, ~1 mm)
        S = self.S
        hosts = [p for p in self.parts if p.kit in ("ENV", "GLAZ") and getattr(p, "cut_openings", None)]
        for h in list(self.parts):
            if h.kit != "GLAZ" or h.material != PART_MAT:
                continue
            outer = unary_union([Polygon(p.exterior) for p in as_polys(h.profile)])
            ac = self.add("GLAZ", f"ACETATE for {h.name}", h.frame, outer.buffer(-m / 2, join_style=2), plies=1,
                          step=12 if "CURTAIN" in h.name else 4, material=ACETATE, w0=h.w0 + h.plies * self.T,
                          face=h.face, category="OPTIONAL (acetate)", status=h.status,
                          joint="glue to inner face of frame with tacky glue (spot, not solvent)")
            ac.acetate = True; ac.tag_ok = False
            if "CURTAIN" in h.name:
                for o in S.find(layer="WINDOWS"):
                    n = o.Attributes.Name or ""
                    if not n.startswith(("CW UP MULLION", "CW LOW MULLION", "CW UP TRANSOM", "CW LOW TRANSOM")):
                        continue
                    bb = o.Geometry.GetBoundingBox()
                    a = h.frame.local([bb.Min.X, bb.Min.Y, bb.Min.Z]); b = h.frame.local([bb.Max.X, bb.Max.Y, bb.Max.Z])
                    if "MULLION" in n:
                        u = (a[0] + b[0]) / 2; ln = LineString([(u, min(a[1], b[1])), (u, max(a[1], b[1]))])
                    else:
                        v = (a[1] + b[1]) / 2; ln = LineString([(min(a[0], b[0]), v), (max(a[0], b[0]), v)])
                    ln = ln.intersection(ac.profile.buffer(-0.05))
                    if not ln.is_empty and ln.length > 0.3:
                        ac.score += list(getattr(ln, "geoms", [ln]))
                ac.note = "transom + mullion lines from the model scored (vector score, low power)"
        for h in hosts:
            for k, r in enumerate(h.cut_openings):
                if h.name.startswith("HALL"):
                    continue                    # hall wall openings are doors: no glazing
                ac = self.add("GLAZ", f"ACETATE window {k + 1} in {h.name}", h.frame, r.buffer(m, join_style=2),
                              plies=1, step=h.step, material=ACETATE, w0=h.w0 + h.plies * self.T, face=h.face,
                              category="OPTIONAL (acetate)", status=h.status,
                              joint="glue to inner face of wall over the opening")
                ac.acetate = True; ac.tag_ok = False

    # ---------------------------------------------------------- guides
    def all_occupancy(self):
        """(part, plan polygon, zbottom) for parts that stand on a horizontal surface."""
        occ = []
        for p in self.parts:
            for fr in p.frames:
                if abs(fr.v[2]) > 0.999:          # vertical part
                    b = p.profile.bounds
                    zb = fr.O[2] + b[1]
                    pp = Part(pid=p.pid, kit=p.kit, name=p.name, frame=fr, profile=p.profile, plies=p.plies, w0=p.w0)
                    occ.append((p, self.plan_rect(pp), zb, strip_v(p.profile, b[1], b[1] + 0.05)))
                elif abs(fr.n[2]) > 0.999:
                    occ.append((p, p.profile if fr.u[0] > 0 else Polygon(), fr.O[2], None))
        return occ

    def build_guides(self):
        """Engrave footprints of parts that stand on a plate, onto that plate's top face."""
        T = self.T
        occ = self.all_occupancy()
        plates = [p for p in self.parts if abs(p.frame.n[2]) > 0.999 and p.frame.u[0] > 0 and p.instances is None]
        for P in plates:
            zt = P.frame.O[2] + P.plies * T
            covered = []
            for q, poly, zb, _ in occ:
                if q is P or poly.is_empty or abs(zb - zt) > 0.03:
                    continue
                inter = poly.intersection(P.profile)
                if inter.area > 1e-3:
                    covered.append(inter)
                    if P.face == +1:
                        keep = P.profile.buffer(-0.12, join_style=2)     # stay ~0.6 mm off cut edges
                        for l in rings(inter):
                            c = l.intersection(keep)
                            P.engrave += [g for g in getattr(c, "geoms", [c]) if not g.is_empty
                                          and g.geom_type == "LineString" and g.length > 0.1]
            P.covered = unary_union(covered) if covered else Polygon()
        # plate contact lines on the interior face of continuous walls
        for W in self.walls:
            for P in self.plates:
                zb = P.frame.O[2]; zt = zb + P.plies * T
                rect = self.plan_rect(W).buffer(0.02, join_style=2)
                if not rect.intersects(P.profile):
                    continue
                inter = rect.intersection(P.profile.buffer(0.02))
                if inter.area < 1e-3:
                    continue
                pts = np.array([c for g in as_polys(inter) for c in g.exterior.coords])
                u = W.frame.local(np.c_[pts, np.full(len(pts), zt)])[:, 0]
                for zz in (zt,):
                    seg = LineString([(u.min(), zz), (u.max(), zz)]).intersection(W.profile)
                    if not seg.is_empty and seg.length > 0.2:
                        W.engrave += list(getattr(seg, "geoms", [seg]))

    # ---------------------------------------------------------- numbering
    def number(self):
        order = ["SITE", "STRUCT", "FLOOR", "ROOF", "ENV", "GLAZ", "CIRC", "POOL", "DETAIL"]
        cnt = defaultdict(int)
        for p in sorted(self.parts, key=lambda p: (order.index(p.kit), getattr(p, 'acetate', False), p.step, self.parts.index(p))):
            cnt[p.kit] += 1
            p.pid = f"{p.kit}-{cnt[p.kit]:03d}"
        self.parts.sort(key=lambda p: (order.index(p.kit), int(p.pid.split("-")[1])))

    # ---------------------------------------------------------- tags
    def build_tags(self):
        h = self.P.tag_height_in / PM.M_TO_IN
        for p in self.parts:
            if not p.tag_ok:
                continue
            label = p.tag
            w_, h_ = font.text_size(label, h)
            prof = p.profile
            # face coordinates: mirror u if the engraved face is -n
            mir = p.face < 0
            facep = affinity.scale(prof, -1, 1, origin=(0, 0)) if mir else prof
            pref = getattr(p, "covered", None)
            pref = affinity.scale(pref, -1, 1, origin=(0, 0)) if (pref is not None and mir and not pref.is_empty) else pref
            spot = self.find_spot(facep, w_, h_, pref)
            if spot is None:
                p.tag_ok = False
                continue
            x, y, ang = spot
            lines = font.text_lines(label, h, 0, 0)
            lines = font.transform(lines, angle=ang, origin=(0, 0), dx=x, dy=y)
            if mir:
                lines = [affinity.scale(l, -1, 1, origin=(0, 0)) for l in lines]
            p.text += lines

    def find_spot(self, poly, w, h, pref=None):
        pad = h * 0.6
        inner = poly.buffer(-pad, join_style=2)
        if inner.is_empty:
            return None
        r = poly.minimum_rotated_rectangle
        c = list(r.exterior.coords)
        e = max(((c[i], c[i + 1]) for i in range(4)), key=lambda e: math.dist(*e))
        ang0 = math.degrees(math.atan2(e[1][1] - e[0][1], e[1][0] - e[0][0])) % 180
        if ang0 > 90:
            ang0 -= 180
        b = inner.bounds
        best = None
        for ang in (0.0, ang0, 90.0):
            for fx in np.linspace(0, 1, 15):
                for fy in np.linspace(0, 1, 9):
                    x = b[0] + fx * (b[2] - b[0]); y = b[1] + fy * (b[3] - b[1])
                    tb = affinity.rotate(box(0, 0, w, h), ang, origin=(0, 0))
                    tb = affinity.translate(tb, x, y)
                    if not inner.contains(tb):
                        continue
                    score = fx * 0.3 + fy + (0.5 if ang else 0)
                    if pref is not None and not pref.is_empty:
                        score -= 5 * (pref.buffer(-pad * 0.5).contains(tb))
                    if best is None or score < best[0]:
                        best = (score, x, y, ang)
        return None if best is None else best[1:]


def build(P=None):
    P = P or PM.load()
    B = Builder(P)
    parts = B.build()
    return B, parts


if __name__ == "__main__":
    B, parts = build()
    for p in parts:
        b = p.profile.bounds
        print(f"{p.pid:11s} {p.tag:6s} q{p.qty:<3d} st{p.step:<3d} {p.name[:46]:46s} "
              f"{PM.m2in(b[2]-b[0]):6.2f} x {PM.m2in(b[3]-b[1]):5.2f} in  tag={'Y' if p.tag_ok else '-'}")
    print("\n".join(B.log[-60:]))

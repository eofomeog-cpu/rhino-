"""Write the fabrication master .3dm (inches).

Four separate systems, separated by layer AND by location:
  ORIGINAL MODEL            original 31 layers, untouched except metres -> inches unit conversion, locked; at origin
  10_FABRICATION_MODEL      assembled physical 1:192 model (extrusions, physical inches)       at X+3000
  20_LASER_SHEETS           flat 30x20 sheet layouts (CUT/SCORE/ENGRAVE/NUMBERS/BOUNDARY)        at X+3000, Y-40...
  30_DOCUMENTATION          exploded axo, kit overview, sheet index, part schedule, sequence    at X+3000, Y-100... / X+3060
"""
import numpy as np
import rhino3dm as r
from shapely.geometry import Polygon, LineString
from shapely.geometry.polygon import orient
from shapely import affinity
import params as PM
import font
import export as EX
from geom import as_polys

M2IN = 1000.0 / 25.4                     # unit conversion for the ORIGINAL model only (1:1)
FAB_O = np.array([3000.0, 0.0, 0.0])     # assembled physical model origin
SHEETS_O = np.array([3000.0, -40.0, 0.0])
DOC_O = np.array([3000.0, -100.0, 0.0])
EXPL_O = np.array([3030.0, 0.0, 0.0])
STAGE_O = np.array([3070.0, 0.0, 0.0])

KIT_LAYER = {"SITE": "FAB-SITE", "STRUCT": "FAB-STRUCTURE", "FLOOR": "FAB-SLABS", "ROOF": "FAB-ROOF",
             "ENV": "FAB-ENVELOPE", "GLAZ": "FAB-GLAZING", "CIRC": "FAB-CIRCULATION", "POOL": "FAB-POOL",
             "DETAIL": "FAB-DETAILS"}
KIT_COLOR = {"FAB-BASE": (200, 190, 170), "FAB-SITE": (205, 195, 175), "FAB-STRUCTURE": (192, 80, 77),
             "FAB-SLABS": (232, 220, 192), "FAB-WALLS": (216, 200, 160), "FAB-ROOF": (157, 180, 200),
             "FAB-ENVELOPE": (200, 185, 150), "FAB-GLAZING": (127, 184, 196), "FAB-CIRCULATION": (143, 174, 107),
             "FAB-POOL": (90, 143, 208), "FAB-DETAILS": (176, 138, 90), "FAB-TABS": (255, 128, 0)}
EXPLODE = {"SITE": 0.0, "POOL": 2.0, "STRUCT": 9.0, "FLOOR": 5.0, "CIRC": 6.0, "ENV": 12.0, "GLAZ": 15.0,
           "ROOF": 18.0, "DETAIL": 13.5}


class Writer:
    def __init__(self, model):
        self.m = model
        self.layer_idx = {}

    def layer(self, path, color=(0, 0, 0)):
        if path in self.layer_idx:
            return self.layer_idx[path]
        parent = None
        if "::" in path:
            parent = self.layer(path.rsplit("::", 1)[0])
        L = r.Layer()
        L.Name = path.rsplit("::", 1)[-1]
        L.Color = (*color, 255)
        if parent is not None:
            L.ParentLayerId = self.m.Layers[parent].Id
        idx = self.m.Layers.Add(L)
        self.layer_idx[path] = idx
        return idx

    def attrs(self, layer, name="", strings=None, group=None):
        a = r.ObjectAttributes()
        a.LayerIndex = self.layer(layer)
        a.Name = name
        for k, v in (strings or {}).items():
            a.SetUserString(str(k), str(v))
        if group is not None:
            a.AddToGroup(group)
        return a

    def group(self, name):
        g = r.Group(); g.Name = name
        self.m.Groups.Add(g)
        return len(self.m.Groups) - 1

    # ------------------------------------------------------------- curves
    def polyline(self, pts3, layer, name="", strings=None, group=None, closed=False):
        P = [r.Point3d(*map(float, p)) for p in pts3]
        if closed and (P[0].DistanceTo(P[-1]) > 1e-9):
            P.append(P[0])
        if len(P) < 2:
            return
        self.m.Objects.AddCurve(r.PolylineCurve(P), self.attrs(layer, name, strings, group))

    def flat(self, geoms, layer, origin, group=None, name="", strings=None):
        ox, oy, oz = origin
        for g in geoms:
            rings = ([g.exterior] + list(g.interiors)) if isinstance(g, Polygon) else [g]
            for ring in rings:
                c = np.asarray(ring.coords)
                self.polyline([(x + ox, y + oy, oz) for x, y in c], layer, name, strings, group,
                              closed=isinstance(g, Polygon))

    def text(self, s, h, origin, layer, align="left"):
        ox, oy, oz = origin
        for l in font.text_lines(s, h, 0, 0, align):
            self.polyline([(x + ox, y + oy, oz) for x, y in l.coords], layer)

    # ------------------------------------------------------------- solids
    def extrusion(self, poly, frame, w0, w1, offset, layer, name, strings, scale=PM.M_TO_IN):
        poly = orient(poly, 1.0)
        def world(c, w):
            P = frame.world(c[:, 0], c[:, 1], np.full(len(c), w)) * scale + offset
            return P
        ext = np.asarray(poly.exterior.coords)
        outer = r.PolylineCurve([r.Point3d(*map(float, p)) for p in world(ext, w0)])
        h = (w1 - w0) * scale
        e = r.Extrusion.Create(outer, h, True)
        if e is None:
            return False
        # make sure the extrusion goes along +n
        nn = frame.n
        ps, pe = e.PathStart, e.PathEnd
        d = np.array([pe.X - ps.X, pe.Y - ps.Y, pe.Z - ps.Z])
        if d @ nn < 0:
            e = r.Extrusion.Create(outer, -h, True)
        pl = e.GetProfilePlane(0)
        o = np.array([pl.Origin.X, pl.Origin.Y, pl.Origin.Z])
        X = np.array([pl.XAxis.X, pl.XAxis.Y, pl.XAxis.Z]); Y = np.array([pl.YAxis.X, pl.YAxis.Y, pl.YAxis.Z])
        for ring in poly.interiors:
            W = world(np.asarray(ring.coords), w0) - o
            h2 = r.PolylineCurve([r.Point3d(float(p @ X), float(p @ Y), 0.0) for p in W])
            e.AddInnerProfile(h2)
        self.m.Objects.AddExtrusion(e, self.attrs(layer, name, strings))
        return True

    def part_solids(self, part, T, offset, layer, strings, scale=PM.M_TO_IN):
        name = f"{part.pid} {part.name}"
        if getattr(part, "solids3d", None):
            for fr, pr, w0, w1 in part.solids3d:
                for p in as_polys(pr):
                    self.extrusion(p, fr, w0, w1, offset, layer, name, strings, scale)
            return
        for fr in part.frames:
            for p in as_polys(part.profile):
                self.extrusion(p, fr, part.w0, part.w0 + part.plies * T, offset, layer, name, strings, scale)


def fab_layer(part):
    if part.kit == "SITE" and "BASE" in part.name:
        return "FAB-BASE"
    if part.kit == "ENV" and part.step == 5:
        return "FAB-WALLS"
    return KIT_LAYER[part.kit]


def part_strings(part, sheets_of):
    return {"part_no": part.pid, "tag": part.tag, "kit": part.kit, "qty": part.qty, "plies": part.plies,
            "material": part.material, "assembly_step": part.step, "sheet": ",".join(sheets_of.get(part.pid, [])),
            "category": part.category, "status": part.status, "joint": part.joint, "note": part.note,
            "exaggeration": "; ".join(f"{a}: {b}->{c} mm ({d})" for a, b, c, d in part.exaggeration),
            "source_guids": ",".join(part.sources[:40])}


def write(path, src_path, parts, sheets, P, T, docs):
    m = r.File3dm.Read(src_path)
    # ---------------------------------------------------------------- ORIGINAL
    xf = r.Transform.Scale(r.Point3d(0, 0, 0), M2IN)
    bad = 0
    for o in m.Objects:
        g = o.Geometry
        before = g.GetBoundingBox()
        g.Transform(xf)
        after = m.Objects.FindId(o.Attributes.Id).Geometry.GetBoundingBox() if hasattr(m.Objects, "FindId") else g.GetBoundingBox()
        if before.IsValid and abs(after.Max.X - before.Max.X * M2IN) > 1e-3 * max(1, abs(before.Max.X * M2IN)):
            bad += 1
    m.Settings.ModelUnitSystem = r.UnitSystem.Inches
    m.Settings.ModelAbsoluteTolerance = 0.001
    for i in range(len(m.Layers)):
        L = m.Layers[i]
        L.Locked = True
        L.SetUserString("system", "ORIGINAL MODEL (unit-converted m->in 1:1, geometry otherwise untouched)")
    W = Writer(m)
    note = W.layer("00_ORIGINAL_MODEL_NOTE", (120, 120, 120))
    W.text("ORIGINAL ARCHITECTURAL MODEL (FULL SIZE, INCHES) - LAYERS LOCKED - DO NOT EDIT", 40, (-300, 300, 0), "00_ORIGINAL_MODEL_NOTE")

    sheets_of = {}
    for s in sheets:
        for pc in s.pieces:
            sheets_of.setdefault(pc.part.pid, [])
            if s.name not in sheets_of[pc.part.pid]:
                sheets_of[pc.part.pid].append(s.name)

    # ---------------------------------------------------------------- FABRICATION MODEL
    root = "10_FABRICATION_MODEL"
    for lay, col in KIT_COLOR.items():
        W.layer(f"{root}::{lay}", col)
    for p in parts:
        if getattr(p, "acetate", False):
            continue
        W.part_solids(p, T, FAB_O, f"{root}::{fab_layer(p)}", part_strings(p, sheets_of))
    # tabs / slots reference curves (FAB-TABS): outline of every through-slot cut in plates
    for p in parts:
        if abs(p.frame.n[2]) > 0.999 and p.kit in ("FLOOR",):
            for poly in as_polys(p.profile):
                for ring in poly.interiors:
                    if Polygon(ring).area < 1.0:
                        c = np.asarray(ring.coords)
                        P3 = p.frame.world(c[:, 0], c[:, 1], np.full(len(c), p.plies * T)) * PM.M_TO_IN + FAB_O
                        W.polyline(P3, f"{root}::FAB-TABS", f"SLOT in {p.pid}", closed=True)
    pd_loc = r.Point3d(*map(float, FAB_O + [0, 2.0, 0]))
    a = W.attrs(f"{root}::FAB-TABS", "FAB-PARAMETERS",
                {"SCALE": "1:192", "T_MAT_IN": P.t_mat_in, "KERF_IN": f"{P.kerf_in} (USER ADJUSTABLE)",
                 "FIT_IN": P.fit_in, "SHEET": f"{P.sheet_w_in} x {P.sheet_h_in} in", "MARGIN_IN": P.margin_in,
                 "REGENERATE": "python tools/fab/run.py --kerf <in> --thickness <in>"})
    m.Objects.AddTextDot("FAB-PARAMETERS", pd_loc, a)
    W.text("FABRICATION MODEL 1:192 (PHYSICAL INCHES) - ASSEMBLED", 0.25, FAB_O + [-2, 2.2, 0], f"{root}::FAB-TABS")

    # ---------------------------------------------------------------- LASER SHEETS
    root2 = "20_LASER_SHEETS"
    lay = {"CUT": (f"{root2}::FAB-CUT", (255, 0, 0)), "SCORE": (f"{root2}::FAB-SCORE", (0, 0, 255)),
           "ENGRAVE": (f"{root2}::FAB-ENGRAVE", (0, 0, 0)), "NUMBERS": (f"{root2}::FAB-NUMBERS", (0, 0, 0)),
           "BOUNDARY": (f"{root2}::FAB-SHEET-BOUNDARY", (128, 128, 128))}
    for k_, (pth, col) in lay.items():
        W.layer(pth, col)
    W.layer(f"{root2}::FAB-GUIDES", (180, 180, 180))
    for i, s in enumerate(sheets):
        o = SHEETS_O + [i * (P.sheet_w_in + 2.0), 0, 0]
        g = EX.sheet_geometry(s, P)
        grp = W.group(s.name)
        for k_, items in g.items():
            W.flat(items, lay[k_][0], o, grp, s.name, {"sheet": s.name})
        W.text(f"{s.name}  {s.title} {s.subtitle}", 0.3, o + [0, P.sheet_h_in + 0.4, 0], f"{root2}::FAB-GUIDES")

    # ---------------------------------------------------------------- DOCUMENTATION
    root3 = "30_DOCUMENTATION"
    # A exploded axonometric (3D, vertically exploded by assembly)
    for p in parts:
        if getattr(p, "acetate", False):
            continue
        off = EXPL_O + [0, 0, EXPLODE[p.kit]]
        W.part_solids(p, T, off, f"{root3}::DOC-EXPLODED-AXO::{fab_layer(p)}", {"part_no": p.pid})
    for kit, z in EXPLODE.items():
        m.Objects.AddTextDot(f"KIT {kit}", r.Point3d(*map(float, EXPL_O + [-2.5, 0, z + 0.5])),
                             W.attrs(f"{root3}::DOC-EXPLODED-AXO", f"KIT {kit}"))
    W.text("A  EXPLODED AXONOMETRIC (view in Perspective / Parallel from SE)", 0.3, EXPL_O + [-2, 2.5, 0],
           f"{root3}::DOC-EXPLODED-AXO")
    # E assembly sequence: cumulative build-up stages
    steps = sorted({p.step for p in parts})
    for j, st in enumerate(steps):
        o = STAGE_O + [(j % 5) * 16.0, -(j // 5) * 14.0, 0]
        for p in parts:
            if p.step <= st and not getattr(p, "acetate", False):
                W.part_solids(p, T, o, f"{root3}::DOC-ASSEMBLY-SEQUENCE::STAGES", {"part_no": p.pid, "stage": st})
        W.text(f"STEP {st}: {docs['step_titles'].get(st, '')}", 0.3, o + [-2, -11.5, 0], f"{root3}::DOC-ASSEMBLY-SEQUENCE")
    # B kit overview, C sheet index, D part schedule, E sequence text, notes, QC (flat 2D)
    y = 0.0
    for title, lines, h in docs["text_blocks"]:
        lay_ = f"{root3}::{title.split()[0]}"
        W.text(title, 0.35, DOC_O + [0, y, 0], lay_)
        y -= 0.6
        for ln in lines:
            W.text(ln, h, DOC_O + [0, y, 0], lay_)
            y -= h * 1.7
        y -= 1.0
    # kit overview drawing: every part type once, rows by kit, physical size
    ko = DOC_O + [60, 0, 0]
    W.text("B  KIT OVERVIEW (ONE OF EACH PART TYPE, PHYSICAL SIZE)", 0.35, ko, f"{root3}::DOC-KIT-OVERVIEW")
    yy = -1.0
    for kit in ["SITE", "STRUCT", "FLOOR", "ROOF", "ENV", "GLAZ", "CIRC", "POOL", "DETAIL"]:
        W.text(f"KIT {kit}", 0.25, ko + [0, yy, 0], f"{root3}::DOC-KIT-OVERVIEW")
        yy -= 0.5; x = 0.0; rowh = 0.0
        for p in [q for q in parts if q.kit == kit and not getattr(q, "acetate", False)]:
            g = affinity.scale(p.profile, PM.M_TO_IN, PM.M_TO_IN, origin=(0, 0))
            b = g.bounds; g = affinity.translate(g, -b[0], -b[1])
            w, h = b[2] - b[0], b[3] - b[1]
            if x + w > 40:
                x = 0; yy -= rowh + 0.5; rowh = 0
            W.flat([g], f"{root3}::DOC-KIT-OVERVIEW", ko + [x, yy - h, 0])
            W.text(f"{p.tag} x{p.qty}", 0.08, ko + [x, yy - h - 0.15, 0], f"{root3}::DOC-KIT-OVERVIEW")
            x += w + 0.4; rowh = max(rowh, h + 0.2)
        yy -= rowh + 1.0
    m.Write(path, 8)
    return bad

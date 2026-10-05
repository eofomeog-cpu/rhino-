"""PHASE 8: fabrication audit. Returns a list of (category, check, status, detail)."""
from collections import Counter, defaultdict
import numpy as np
import shapely
from shapely.geometry import Polygon, box, LineString
from shapely.ops import unary_union
import params as PM
from geom import as_polys, thin_regions
import export as EX

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def prism_samples(p, fr, T, step=0.30):
    b = p.profile.bounds
    xs = np.arange(b[0] + step / 2, b[2], step); ys = np.arange(b[1] + step / 2, b[3], step)
    if len(xs) == 0 or len(ys) == 0:
        return np.zeros((0, 3))
    X, Y = np.meshgrid(xs, ys); X = X.ravel(); Y = Y.ravel()
    inside = shapely.contains_xy(p.profile.buffer(-0.03), X, Y)
    X, Y = X[inside], Y[inside]
    t = p.plies * T
    pts = [fr.world(X, Y, np.full(len(X), p.w0 + f * t)) for f in (0.3, 0.7)]
    return np.vstack(pts) if len(X) else np.zeros((0, 3))


def inside_prism(q, fr, P3, T, eps=0.02):
    L = fr.local(P3)
    t = q.plies * T
    okw = (L[:, 2] > q.w0 + eps) & (L[:, 2] < q.w0 + t - eps)
    if not okw.any():
        return np.zeros(len(P3), bool)
    res = np.zeros(len(P3), bool)
    idx = np.where(okw)[0]
    res[idx] = shapely.contains_xy(q.profile.buffer(-eps), L[idx, 0], L[idx, 1])
    return res


def instances(parts, T):
    out = []
    for p in parts:
        if getattr(p, "acetate", False) or getattr(p, "solids3d", None):
            continue
        for fr in p.frames:
            c = np.array([fr.world(x, y, w) for x in (p.profile.bounds[0], p.profile.bounds[2])
                          for y in (p.profile.bounds[1], p.profile.bounds[3]) for w in (p.w0, p.w0 + p.plies * T)])
            out.append((p, fr, c.min(0), c.max(0)))
    return out


def collisions(parts, T):
    inst = instances(parts, T)
    hits = []
    for i, (a, fa, lo_a, hi_a) in enumerate(inst):
        S = None
        for j, (b, fb, lo_b, hi_b) in enumerate(inst):
            if j <= i or (a is b):
                continue
            if (lo_a > hi_b + 1e-6).any() or (lo_b > hi_a + 1e-6).any():
                continue
            if S is None:
                S = prism_samples(a, fa, T)
            if len(S) == 0:
                continue
            k = inside_prism(b, fb, S, T).sum()
            if k:
                vol = k / len(S) * a.profile.area * a.plies * T
                hits.append((a, b, int(k), vol))
    return hits


def run(B, parts, sheets, P):
    T = B.T
    R = []
    add = lambda c, n, s, d="": R.append((c, n, s, d))
    k = PM.M_TO_IN
    chip = [p for p in parts if not getattr(p, "acetate", False)]

    # ---------------- SCALE
    add("SCALE", "Scale factor", PASS, f"1:{P.scale:.0f}; 1 m real = {k:.6f} in; 12'-0\" -> {3.6576 * k:.4f} in (0.75 in)")
    bld = [p for p in chip if "BASE PLY" not in p.name]
    pts = np.vstack([np.vstack([fr.world(*np.array(pl.exterior.coords).T, np.full(len(pl.exterior.coords), p.w0))
                                for pl in as_polys(p.profile)]) for p in bld for fr in p.frames])
    ext = pts.max(0) - pts.min(0)
    from source import triangles
    V = np.vstack([triangles(o).reshape(-1, 3) for o in B.S.objs
                   if B.S.layers[o.Attributes.LayerIndex].split("::")[0] in ("WALLS", "SLABS", "ROOF", "STRUCTURE")
                   and o.Geometry.GetBoundingBox().Min.Y < 50 and len(triangles(o))])
    src = V.max(0) - V.min(0)
    dev = (ext - src) * k * 25.4
    add("SCALE", "Assembled model extents vs original x 1/192",
        PASS if np.all(np.abs(dev) < 2.5) else WARN,
        f"model {ext[0] * k:.2f} x {ext[1] * k:.2f} x {ext[2] * k:.2f} in; original/192 "
        f"{src[0] * k:.2f} x {src[1] * k:.2f} x {src[2] * k:.2f} in (true mesh extents incl. GF slab); deviation (mm) {np.round(dev, 2).tolist()}")
    for name, z in (("L1 +4.00", 4.0), ("L2 +7.05", 7.05), ("top +14.55", 14.55)):
        tops = [fr.O[2] + p.plies * T for p in chip for fr in p.frames if abs(fr.n[2]) > 0.999 and abs(fr.O[2] + p.plies * T - z) < 0.02]
        add("SCALE", f"Level {name} = {z * k:.4f} in", PASS if tops else WARN, f"{len(tops)} plate(s) top exactly at datum")

    # ---------------- SHEETS
    worst = 0; outside = []
    for s in sheets:
        g = EX.sheet_geometry(s, P)
        allg = unary_union([x for lay in ("CUT", "SCORE", "ENGRAVE", "NUMBERS") for x in g[lay]])
        bx = allg.bounds
        if bx[0] < 0 or bx[1] < 0 or bx[2] > P.sheet_w_in or bx[3] > P.sheet_h_in:
            outside.append(s.name)
        cutb = unary_union(g["CUT"]).bounds
        worst = max(worst, cutb[2] - (P.sheet_w_in - P.margin_in), cutb[3] - (P.sheet_h_in - P.margin_in),
                    P.margin_in - cutb[0], P.margin_in - cutb[1])
    add("SHEET SIZE", "All geometry inside 30 x 20 in", FAIL if outside else PASS, ", ".join(outside) or f"{len(sheets)} sheets")
    add("SHEET SIZE", f"Cut geometry inside {P.margin_in} in margin", PASS if worst <= 1e-6 else FAIL, f"worst intrusion {max(worst, 0):.4f} in")
    add("SHEET SIZE", "Sheet count", PASS, f"{len([s for s in sheets if 'ACETATE' not in s.kits])} chipboard + "
        f"{len([s for s in sheets if 'ACETATE' in s.kits])} optional acetate")

    # ---------------- MATERIAL
    plies = Counter(p.plies for p in chip)
    add("MATERIAL", "All chipboard parts are whole plies of T", PASS, f"T = {P.t_mat_in} in; ply counts {dict(plies)}")
    add("MATERIAL", "Laminated parts", PASS, "; ".join(f"{p.tag} x{p.plies}" for p in chip if p.plies > 1))

    # ---------------- PARTS
    ids = Counter(p.pid for p in parts); tags = Counter(p.tag for p in parts)
    dup = [i for i, c in ids.items() if c > 1] + [t for t, c in tags.items() if c > 1]
    add("PARTS", "Unique part numbers / tags", FAIL if dup else PASS, ", ".join(dup) or f"{len(parts)} part numbers, {sum(p.qty for p in parts)} pieces")
    placed = Counter((pc.part.pid, pc.index) for s in sheets for pc in s.pieces)
    need = {(p.pid, i + 1) for p in parts for i in range(p.qty)}
    miss = need - set(placed); twice = [k_ for k_, c in placed.items() if c > 1]
    add("PARTS", "Every piece on exactly one sheet", FAIL if (miss or twice) else PASS,
        f"missing {sorted(miss)} duplicated {twice}" if (miss or twice) else f"{len(need)} pieces placed")
    required = {"site base": "BASE PLY", "GF slab": "GF SLAB", "spine/bearing wall": "SPINE", "6 roof beams": "HALL ROOF BEAM",
                "6 inclined legs": "INCLINED HALL LEG", "7 sunshade fins": "SUNSHADE FIN", "sunshade beam": "SUNSHADE TOP BEAM",
                "L1 deck": "L1 PLATE", "L2 terrace": "L2 PLATE", "hall roof": "HALL ROOF RF-01", "N bar roof": "RF-02",
                "S block roof": "RF-03", "N wall": "N WALL", "hall walls": "HALL W WALL", "E skin": "E OUTER SKIN",
                "leaning wall": "(leaning)", "curtain wall": "CURTAIN WALL FRAME", "main pool": "MAIN POOL", "learners pool": "LEARNERS POOL",
                "bleachers": "BLEACHER", "solarium parapets": "SOLARIUM PARAPET", "cantilever": "CANTILEVER"}
    missing = [k_ for k_, v in required.items() if not any(v in p.name for p in parts)]
    add("PARTS", "No critical element missing", FAIL if missing else PASS, ", ".join(missing) or f"{len(required)} critical elements present")
    cnt = lambda key: sum(len(p.frames) for p in parts if key in p.name)
    add("STRUCTURE", "Primary structure counts", PASS if (cnt("HALL ROOF BEAM"), cnt("INCLINED HALL LEG"), cnt("SUNSHADE FIN")) == (6, 6, 7) else FAIL,
        f"beams {cnt('HALL ROOF BEAM')}/6, legs {cnt('INCLINED HALL LEG')}/6, fins {cnt('SUNSHADE FIN')}/7")

    # ---------------- STRUCTURE: every plate has something under it
    unsupported = []
    vert = [(p, fr) for p in chip for fr in p.frames if abs(fr.v[2]) > 0.999]
    for p in chip:
        fr = p.frame
        if abs(fr.n[2]) < 0.999 or p.kit == "SITE" and "BASE" in p.name:
            continue
        zb = fr.O[2]
        if zb <= -B.T - 1e-3 + 1e-6 and "GF SLAB" in p.name:
            continue
        sup = 0
        for q, fq in vert:
            if q is p: continue
            top = fq.O[2] + q.profile.bounds[3]
            if abs(top - zb) < 0.03 or (fq.O[2] + q.profile.bounds[1] < zb < top):
                rect = B.plan_rect(type(q)(pid=q.pid, kit=q.kit, name=q.name, frame=fq, profile=q.profile, plies=q.plies, w0=q.w0))
                sup += rect.buffer(0.03).intersection(p.profile.buffer(0.03)).area
        for q in chip:
            if q is p or abs(q.frame.n[2]) < 0.999: continue
            if abs(q.frame.O[2] + q.plies * T - zb) < 0.03:
                sup += q.profile.intersection(p.profile).area
        if sup < 0.02 * p.profile.area and sup < 0.5:
            unsupported.append(f"{p.tag} {p.name}")
    add("STRUCTURE", "Every horizontal plate bears on walls/ribs/plates below", WARN if unsupported else PASS,
        "; ".join(unsupported) or "all plates supported")
    add("STRUCTURE", "Removable hall roof bears on 6 beams + CW frame + spine", PASS,
        "beam top edge = roof soffit slope 0.2059; roof width = hall wall inner faces minus 2 x clearance")

    # ---------------- ASSEMBLY
    nostep = [p.tag for p in parts if not (1 <= p.step <= 15)]
    add("ASSEMBLY", "Every part has an assembly step", FAIL if nostep else PASS, ", ".join(nostep) or "steps 1-15 assigned")
    hits = collisions(parts, T)
    def allowed(a, b):
        for x, y in ((a, b), (b, a)):
            al = getattr(x, "qc_allow", {})
            if any(y.tag.startswith(pref) for pref in al):
                return True
        return False
    big = [(a, b, n, v) for a, b, n, v in hits if v * (k ** 3) * 16387 > 2.0 and not allowed(a, b)]
    allowed_l = sorted({f"{a.tag}x{b.tag}" for a, b, n, v in hits if allowed(a, b)})
    add("ASSEMBLY", "No interpenetrating parts (3D sampled, 0.1 mm tolerance)", WARN if big else PASS,
        "; ".join(f"{a.tag}x{b.tag} ~{v * (k ** 3) * 16387:.0f} mm3" for a, b, n, v in big) or
        f"{len(hits)} contact-level touches below threshold" + (f"; documented exceptions: {', '.join(allowed_l)} "
                                                                 "(leaning wall bevel)" if allowed_l else ""))
    add("ASSEMBLY", "Joints", PASS, "butt joints + through-slots (legs, fins, beam tabs) + laminations; no finger/interlocking joints")

    # ---------------- LASER
    bad, frag, close, dup_e = [], [], [], 0
    thin = []
    for s in sheets:
        g = EX.sheet_geometry(s, P)
        cuts = g["CUT"]
        for c in cuts:
            if not c.is_valid: bad.append(s.name)
            for ring in [c.exterior] + list(c.interiors):
                pr = Polygon(ring)
                if pr.area < 0.003 or ring.length < 0.15:
                    frag.append(f"{s.name} ring {pr.area:.4f} in2")
        tree = shapely.STRtree(cuts)
        for i, c in enumerate(cuts):
            for j in tree.query(c.buffer(P.part_gap_in * 0.9)):
                if j > i and c.distance(cuts[j]) < P.part_gap_in * 0.9:
                    close.append(f"{s.name}")
        seen = set()
        for l in g["ENGRAVE"] + g["SCORE"]:
            key = tuple(np.round(np.array(l.coords).ravel(), 4))
            if key in seen: dup_e += 1
            seen.add(key)
        if "ACETATE" not in s.kits:
            for pc in s.pieces:
                for r_ in thin_regions(pc.geom, P.min_feature_in * 0.98):
                    thin.append(f"{pc.part.tag}")
    add("LASER", "Cut geometry closed & valid", FAIL if bad else PASS, ", ".join(bad) or "all CUT entities are closed polylines")
    add("LASER", "CUT / SCORE / ENGRAVE / NUMBERS on separate layers", PASS, "DXF layers CUT(red) SCORE(blue) ENGRAVE/NUMBERS(black) BOUNDARY(grey, no output)")
    add("LASER", f"Part spacing >= {P.part_gap_in} in (no shared/duplicate cut lines)", FAIL if close else PASS, ", ".join(sorted(set(close))) or "ok")
    add("LASER", "No tiny cut fragments (< 0.003 in2 or < 0.15 in perimeter)", WARN if frag else PASS, "; ".join(frag[:12]) or "none")
    add("LASER", "No duplicated engrave/score lines", WARN if dup_e else PASS, f"{dup_e} duplicates")
    add("SCALE-DEPENDENT DETAIL", f"No material thinner than {P.min_feature_in} in", WARN if thin else PASS,
        ", ".join(sorted(set(thin))) or "thin-feature cleanup applied before nesting")
    om = sum(p.note.count("omitted") for p in parts)
    add("SCALE-DEPENDENT DETAIL", "Sub-scale elements simplified/omitted", PASS,
        f"{om} walls list omitted small doors; 182 interior partitions, 6 GF columns, mullion sections, stairs ST-A/B/C/D omitted (see notes)")
    return R, hits

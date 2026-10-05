"""PHASE 7: documentation — schedules, notes, renders, drawing-set PDF."""
import csv, os, math
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from shapely import affinity
import params as PM
import export as EX
import render3d as R3
import viz
from geom import as_polys

STEP_TITLES = {
    1: "Laminate the 3 base plies (PVA, weight, edges flush)",
    2: "Glue GF slab / plinth onto engraved footprint on base",
    3: "Pool boxes, floor ribs and pool floors on GF slab",
    4: "GF bearing ribs, GF walls and GF glazing frames",
    5: "Continuous walls: spine (beam slots), N wall, hall W/E, E skin, slants, garden, wing S wall, N-bar bulkheads",
    6: "Drop in L1 plate (pool deck + wing + solarium)",
    7: "L1 elements: wing ribs, west-zone face, notch wall, solarium parapet bands, cantilever box",
    8: "Bleacher stacks (4 x 2 plies) against spine",
    9: "L2 plate (terrace + south block floor)",
    10: "South block: S, E and leaning N walls (bevel), hidden ribs",
    11: "Hall structure: 6 inclined legs into L1 slots, 6 roof beams into spine slots",
    12: "Curtain-wall frame against leg feet (+ optional acetate)",
    13: "Sunshade fins into slots, S-B7 top beam on fin tops",
    14: "Roofs RF-02, RF-03, RF-06, E strips; NE box walls + roof",
    15: "Hall roof RF-01 (2 plies) + fascia: REMOVABLE, do not glue",
}

OMITTED = [
    ("Interior partitions (INT GROUND/L1/L2)", "182 objects", "enclosed; 0.24 m = 1.25 mm; not visible with roofs on"),
    ("GF columns under main pool tank (S-GC)", "6", "hidden inside pool tank volume; 1.6 mm square"),
    ("Stairs ST-A1/A2, ST-B1/B2, ST-C, ST-D1/D2, landings LD-A/LD-D", "9", "riser 0.83-0.95 mm < 1 ply; enclosed in north bar / under south block"),
    ("Oval stair drum guard, curved walls 1.04 / 2.05", "6", "inside wing / south block, not visible"),
    ("Small doors (< 4 m2 or < 1.8 m wide)", "15", "4.6-9 mm openings; would weaken walls; listed per wall in schedule notes"),
    ("CW glass, 216 transoms, 55 mullions (sections 0.02-0.10 m)", "~440", "0.1-0.5 mm; scored on optional acetate instead"),
    ("N-bar slabs SL-11, SL-12, SL-21; hall deck thickness", "3", "hidden; replaced by 2 bulkheads"),
    ("Lane lines, learners' pool steps, paddling pool 1.10, PISCINE letters", "-",
     "ENGRAVED (pool floors / L1 plate / forecourt wall outer face) instead of built"),
    ("Analysis volumes, massing, reference images, grid, levels", "47", "non-physical"),
    ("Stray / duplicate geometry (3x N wall, massing copy +104.5 m, Default surface)", "16", "excluded (left untouched in original)"),
]


def category(p):
    if getattr(p, "acetate", False):
        return "OPTIONAL (acetate)"
    if p.hidden:
        return "SUPPORT (hidden)"
    if p.kit == "GLAZ" or "BLEACHER" in p.name or "POOL FLOOR" in p.name or "WEST ZONE E FACE" in p.name \
            or "SLAB EDGE" in p.name:
        return "SIMPLIFY"
    return "MUST FABRICATE"


def schedule_rows(parts, sheets, P):
    sheets_of = {}
    for s in sheets:
        for pc in s.pieces:
            sheets_of.setdefault(pc.part.pid, [])
            if s.name not in sheets_of[pc.part.pid]:
                sheets_of[pc.part.pid].append(s.name)
    rows = []
    for p in parts:
        b = p.profile.bounds
        ac = getattr(p, "acetate", False)
        rows.append({
            "PART NUMBER": p.pid, "TAG": p.tag, "NAME": p.name, "CATEGORY": category(p), "QUANTITY": p.qty,
            "MATERIAL": "0.010 in clear acetate/PETG" if ac else "1/16 in chipboard",
            "THICKNESS": "0.010 in" if ac else f"{p.plies} x {P.t_mat_in:.4f} = {p.plies * P.t_mat_in:.4f} in",
            "ASSEMBLY": f"KIT {p.kit} / step {p.step}", "SHEET NUMBER": ",".join(sheets_of.get(p.pid, [])),
            "SIZE (in)": f"{PM.m2in(b[2] - b[0]):.2f} x {PM.m2in(b[3] - b[1]):.2f}",
            "STATUS": p.status, "TAG ON PART": "yes" if p.tag_ok else "sheet label",
            "JOINT": p.joint, "NOTE": p.note})
    return rows


def write_tables(B, parts, sheets, P, qc_rows, out):
    os.makedirs(out, exist_ok=True)
    rows = schedule_rows(parts, sheets, P)
    with open(f"{out}/PART_SCHEDULE.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    k = PM.M_TO_IN
    # ---------------------------------------------------------------- markdown
    md = ["# Bagneux Swimming Pool Extension — 1:192 Chipboard Kit", "",
          f"Scale 1:192 (1/16\" = 1'-0\"), material 1/16\" chipboard (T = {P.t_mat_in} in), "
          f"KERF = {P.kerf_in} in (**user adjustable**, 0 = no compensation), FIT = {P.fit_in} in.", "",
          f"**{len(parts)} part numbers, {sum(p.qty for p in parts)} pieces, "
          f"{len([s for s in sheets if 'ACETATE' not in s.kits])} chipboard sheets + "
          f"{len([s for s in sheets if 'ACETATE' in s.kits])} optional acetate sheet (30\" x 20\").**", ""]
    md += ["## C. Sheet index", "", "| Sheet | Contents | Pieces | Material use | Files |", "|---|---|---|---|---|"]
    for s in sheets:
        fill = sum(pc.geom.area for pc in s.pieces) / (P.sheet_w_in * P.sheet_h_in)
        tags = sorted({pc.part.tag for pc in s.pieces})
        md.append(f"| {s.name} | {s.title} {s.subtitle} — {', '.join(tags)} | {len(s.pieces)} | {fill:.0%} | "
                  f"`laser/{s.name}.dxf` `.svg`, `previews/{s.name}.pdf` |")
    md += ["", "## D. Part schedule", "",
           "| Part number | Tag | Name | Category | Qty | Material | Thickness | Assembly | Sheet | Size (in) | Status |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r_ in rows:
        md.append(f"| {r_['PART NUMBER']} | {r_['TAG']} | {r_['NAME']} | {r_['CATEGORY']} | {r_['QUANTITY']} | "
                  f"{r_['MATERIAL']} | {r_['THICKNESS']} | {r_['ASSEMBLY']} | {r_['SHEET NUMBER']} | "
                  f"{r_['SIZE (in)']} | {r_['STATUS']} |")
    md += ["", "Status: DER = derived from the traced drawings in the original model; ASM = assumed in the original "
           "model; DER-FAB = support/stiffener added for fabrication (hidden, not architecture).", ""]
    md += ["## E. Assembly sequence", ""]
    for st in sorted({p.step for p in parts}):
        ps = [p for p in parts if p.step == st and not getattr(p, "acetate", False)]
        ac = [p for p in parts if p.step == st and getattr(p, "acetate", False)]
        md.append(f"{st}. **{STEP_TITLES[st]}** — " + ", ".join(f"{p.tag}" + (f"×{p.qty}" if p.qty > 1 else "") for p in ps)
                  + (f" (optional acetate: {', '.join(p.tag for p in ac)})" if ac else ""))
    md += ["", "Glue: PVA wood glue for chipboard; tacky glue (no solvent) for acetate. Clean edges with a #11 blade. "
           "Engraved lines on plates mark where the next part stands; part tags are engraved on hidden faces.", ""]
    open(f"{out}/KIT_README.md", "w").write("\n".join(md))

    # ---------------------------------------------------------------- fabrication notes
    nt = ["# Fabrication notes — simplifications, exaggerations, omissions", "",
          "## Dimensional exaggerations (only where the real element is thinner than practical)", "",
          "| Part | Element | Original scaled (mm) | Fabricated (mm) | Reason |", "|---|---|---|---|---|"]
    for p in parts:
        for e, a, b, rsn in p.exaggeration:
            nt.append(f"| {p.tag} | {e} | {a} | {b} | {rsn} |")
    nt += ["", "Building plan dimensions, floor/roof elevations, the roof slope and all major geometry are **not** "
           "exaggerated: the assembled kit measures exactly the original/192 (see QC).", "",
           "## Category C — omitted", "", "| Element | Count | Reason |", "|---|---|---|"]
    nt += [f"| {a} | {b} | {c} |" for a, b, c in OMITTED]
    nt += ["", "## Category B — simplified", "",
           "* Curtain wall: chipboard frame with posts on grid C1–C6 and two transom bands (8.50 / 10.50); bars 0.32 m "
           "(1.67 mm) minimum; glazing open, optional acetate with scored mullions/transoms.",
           "* GF entrance / vestibule glazing: frames with bars at the modelled mullions; head band carries the solarium plate.",
           "* Bleachers: 4 stacked 2-ply plates (rise 2 plies per tier).",
           "* Main pool floor: one plate folded on 3 scored lines following section 8 (2.10 -> 0.30 -> 1.45).",
           "* Solarium slab edge (1 m deep) + parapet: one plate per side; GF elements under the canopy rise to the "
           "1-ply L1 plate underside (+3.70) to carry it.",
           "* N-bar interior and floors replaced by 2 hidden bulkheads; south block by 2 hidden ribs.",
           "* West-zone east face: built from interior-layer wall pieces facing the terrace; gaps between them closed.",
           "* Walls whose real thickness is <= 1.5 plies are 1 ply; 0.46-0.50 m walls are 2 plies (see table above).",
           "", "## Geometry derived for fabrication (not modelled as a separate object in the original)", "",
           "* N-bar spine wall = south face of massing M01 (beam bearing).",
           "* L2 plate outline = SL-22 terrace + massing M06 top + M08 bottom.",
           "* Hidden ribs/bulkheads at interior-wall lines (status DER-FAB / one ASM support at X 22.9).",
           "", "## Model issues carried from the Phase 1 analysis", "",
           "* Hall roof: modelled slope used (top +12.60 at section 8), not LEVELS +11.90 (default Q8).",
           "* Triplicated N wall, massing copy at +104.53 m Y, stray Default surface: excluded.",
           "* The model leaves the L1 wing's east side (facing the solarium) open; the kit leaves it open.",
           "", "## Kerf / thickness / fit", "",
           "Change in `tools/fab/fab_params.json` or `python tools/fab/run.py --kerf 0.006 --thickness 0.0625 --fit 0` "
           "and rerun: outer profiles are offset out by KERF/2, holes and slots in by KERF/2; slots are sized to "
           "n x T + FIT; engrave/score/number geometry is never offset.", ""]
    for line in B.log:
        if "cleanup" in line or "WARNING" in line:
            nt.append(f"* build log: {line}")
    open(f"{out}/FABRICATION_NOTES.md", "w").write("\n".join(nt))

    # ---------------------------------------------------------------- QC
    q = ["# Fabrication QC audit", "", "| Category | Check | Result | Detail |", "|---|---|---|---|"]
    q += [f"| {c} | {n} | **{s}** | {d} |" for c, n, s, d in qc_rows]
    open(f"{out}/QC_REPORT.md", "w").write("\n".join(q))
    return rows


def text_blocks(parts, sheets, P, rows, qc_rows):
    """Plain text blocks drawn into the Rhino documentation layers."""
    tb = []
    tb.append(("DOC-SHEET-INDEX  C  SHEET INDEX", [f"{s.name}  {s.title} {s.subtitle}  - {len(s.pieces)} PIECES" for s in sheets], 0.16))
    tb.append(("DOC-PART-SCHEDULE  D  PART SCHEDULE  (PART / CATEGORY / QTY / MATERIAL / THICKNESS / ASSEMBLY / SHEET)",
               [f"{r_['PART NUMBER']:<11} {r_['TAG']:<6} {r_['CATEGORY'][:16]:<16} QTY {r_['QUANTITY']:<3} "
                f"{'ACETATE' if 'acetate' in r_['MATERIAL'] else '1/16 CHIPBOARD':<15} {r_['THICKNESS'][:20]:<20} "
                f"{r_['ASSEMBLY']:<22} {r_['SHEET NUMBER']:<18} {r_['NAME'][:44]}" for r_ in rows], 0.11))
    tb.append(("DOC-ASSEMBLY-SEQUENCE  E  ASSEMBLY SEQUENCE",
               [f"{st:>2}. {STEP_TITLES[st]}" for st in sorted({p.step for p in parts})], 0.14))
    ex = [f"{p.tag}: {e} {a} MM -> {b} MM ({rsn})" for p in parts for e, a, b, rsn in p.exaggeration]
    tb.append(("DOC-FABRICATION-NOTES  EXAGGERATIONS: ORIGINAL SCALED -> FABRICATED (REASON)", ex, 0.11))
    tb.append(("DOC-QC  FABRICATION QC", [f"{s:<5} {c:<22} {n}" for c, n, s, d in qc_rows], 0.12))
    return tb


def renders(B, parts, out):
    T = B.T
    os.makedirs(out, exist_ok=True)
    chip = [p for p in parts if not getattr(p, "acetate", False)]
    hide_base = lambda p: "BASE PLY" in p.name
    R3.render(chip, T, f"{out}/axo_assembled_SE.png", az=-35, el=30, title="Assembled kit 1:192 — from SE")
    R3.render(chip, T, f"{out}/axo_assembled_NW.png", az=145, el=30, title="Assembled kit — from NW")
    R3.render(chip, T, f"{out}/axo_hall_roof_removed.png", az=-35, el=45, title="Hall roof RF-01 lifted off (removable)",
              hide=lambda p: p.name.startswith("HALL ROOF"))
    from rhino_out import EXPLODE
    R3.render(chip, T, f"{out}/A_exploded_axo.png", az=-40, el=28, figsize=(14, 18),
              title="A. Exploded axonometric (vertical explode by kit)",
              offsets=lambda p: np.array([0, 0, EXPLODE[p.kit] / PM.M_TO_IN]),
              labels=[(f"KIT {k}", (-14, -20, (v + 0.4) / PM.M_TO_IN)) for k, v in EXPLODE.items()])
    steps = sorted({p.step for p in parts})
    fig, axs = plt.subplots(3, 5, figsize=(25, 13))
    for ax, st in zip(np.ravel(axs), steps):
        fn = f"{out}/_stage_{st:02d}.png"
        R3.render([p for p in chip if p.step <= st], T, fn, az=-35, el=30, figsize=(6, 4.5))
        ax.imshow(plt.imread(fn)); ax.axis("off")
        ax.set_title(f"{st}. {STEP_TITLES[st]}", fontsize=8, wrap=True)
        os.remove(fn)
    fig.suptitle("E. Assembly sequence (cumulative)"); fig.tight_layout()
    fig.savefig(f"{out}/E_assembly_sequence.png", dpi=110); plt.close(fig)


def kit_overview_page(parts, pdf):
    kits = ["SITE", "STRUCT", "FLOOR", "ROOF", "ENV", "GLAZ", "CIRC", "POOL", "DETAIL"]
    fig, ax = plt.subplots(figsize=(17, 11))
    y = 0.0
    for kit in kits:
        ps = [p for p in parts if p.kit == kit and not getattr(p, "acetate", False)]
        ax.text(0, y + 0.15, f"KIT {kit}", fontsize=9, weight="bold")
        x, rowh = 0.0, 0.0
        for p in ps:
            g = affinity.scale(p.profile, PM.M_TO_IN, PM.M_TO_IN, origin=(0, 0))
            b = g.bounds; w, h = b[2] - b[0], b[3] - b[1]
            if x + w > 44:
                x = 0; y -= rowh + 0.45; rowh = 0
            for pp in as_polys(affinity.translate(g, x - b[0], y - h - b[1])):
                ax.add_patch(viz.poly_patch(pp, facecolor=R3.KIT_COL[kit], edgecolor="k", lw=0.3))
            ax.text(x, y - h - 0.22, f"{p.tag} x{p.qty}", fontsize=4.5)
            x += w + 0.35; rowh = max(rowh, h)
        y -= rowh + 0.8
    ax.set_xlim(-0.5, 45); ax.set_ylim(y, 0.8); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("B. Kit overview — one of each part type at physical scale (inches), grouped by kit")
    pdf.savefig(fig); plt.close(fig)


def table_pages(rows, pdf, cols, title, per=38):
    for i in range(0, len(rows), per):
        fig, ax = plt.subplots(figsize=(17, 11)); ax.axis("off")
        chunk = rows[i:i + per]
        t = ax.table(cellText=[[str(r_[c])[:60] for c in cols] for r_ in chunk], colLabels=cols, loc="upper center",
                     cellLoc="left", colLoc="left")
        t.auto_set_font_size(False); t.set_fontsize(6.5); t.scale(1, 1.15)
        ax.set_title(f"{title} ({i // per + 1})")
        pdf.savefig(fig); plt.close(fig)


def drawing_set(B, parts, sheets, P, rows, qc_rows, ren, fn):
    with PdfPages(fn) as pdf:
        for img, ttl in ((f"{ren}/axo_assembled_SE.png", "BAGNEUX SWIMMING POOL EXTENSION — 1:192 CHIPBOARD KIT"),
                         (f"{ren}/A_exploded_axo.png", ""), (f"{ren}/axo_hall_roof_removed.png", "")):
            fig, ax = plt.subplots(figsize=(17, 11)); ax.imshow(plt.imread(img)); ax.axis("off")
            if ttl:
                ax.set_title(ttl + f"\n1/16\" = 1'-0\" | 1/16\" chipboard T={P.t_mat_in}\" | KERF={P.kerf_in}\" (adjustable) | "
                             f"{len(parts)} part numbers / {sum(p.qty for p in parts)} pieces / {len(sheets)} sheets", fontsize=11)
            pdf.savefig(fig); plt.close(fig)
        kit_overview_page(parts, pdf)
        # sheet index page with thumbnails
        fig, axs = plt.subplots(2, 3, figsize=(17, 11))
        for ax, s in zip(np.ravel(axs), sheets):
            g = EX.sheet_geometry(s, P)
            for name, c in (("BOUNDARY", "0.6"), ("CUT", "r"), ("SCORE", "b"), ("ENGRAVE", "k")):
                for gg in g[name]:
                    rings = ([gg.exterior] + list(gg.interiors)) if gg.geom_type == "Polygon" else [gg]
                    for rr in rings:
                        xx, yy = rr.xy; ax.plot(xx, yy, color=c, lw=0.3)
            ax.set_aspect("equal"); ax.axis("off")
            ax.set_title(f"{s.name} {s.subtitle}\n{s.title}", fontsize=7)
        for ax in np.ravel(axs)[len(sheets):]:
            ax.axis("off")
        fig.suptitle("C. Sheet index (30\" x 20\")"); pdf.savefig(fig); plt.close(fig)
        for s in sheets:
            g = EX.sheet_geometry(s, P)
            fig, ax = plt.subplots(figsize=(17, 11.5))
            for name, c, lw in (("BOUNDARY", "0.6", 0.4), ("CUT", "r", 0.4), ("SCORE", "b", 0.4), ("ENGRAVE", "k", 0.25), ("NUMBERS", "k", 0.25)):
                for gg in g[name]:
                    rings = ([gg.exterior] + list(gg.interiors)) if gg.geom_type == "Polygon" else [gg]
                    for rr in rings:
                        xx, yy = rr.xy; ax.plot(xx, yy, color=c, lw=lw)
            ax.set_aspect("equal"); ax.set_xlim(-0.2, P.sheet_w_in + 0.2); ax.set_ylim(-0.2, P.sheet_h_in + 0.2)
            ax.set_title(f"{s.name} {s.title} {s.subtitle}", fontsize=9)
            pdf.savefig(fig); plt.close(fig)
        table_pages(rows, pdf, ["PART NUMBER", "TAG", "NAME", "CATEGORY", "QUANTITY", "MATERIAL", "THICKNESS",
                                "ASSEMBLY", "SHEET NUMBER", "SIZE (in)", "STATUS"], "D. Part schedule")
        fig, ax = plt.subplots(figsize=(17, 11)); ax.imshow(plt.imread(f"{ren}/E_assembly_sequence.png")); ax.axis("off")
        pdf.savefig(fig); plt.close(fig)
        ex = [{"PART": p.tag, "ELEMENT": e, "ORIGINAL SCALED (mm)": a, "FABRICATED (mm)": b, "REASON": rsn}
              for p in parts for e, a, b, rsn in p.exaggeration]
        table_pages(ex, pdf, ["PART", "ELEMENT", "ORIGINAL SCALED (mm)", "FABRICATED (mm)", "REASON"], "Fabrication note — exaggerations")
        om = [{"OMITTED ELEMENT": a, "COUNT": b, "REASON": c} for a, b, c in OMITTED]
        table_pages(om, pdf, ["OMITTED ELEMENT", "COUNT", "REASON"], "Fabrication note — omitted (category C)")
        qr = [{"CATEGORY": c, "CHECK": n, "RESULT": s, "DETAIL": d[:120]} for c, n, s, d in qc_rows]
        table_pages(qr, pdf, ["CATEGORY", "CHECK", "RESULT", "DETAIL"], "Fabrication QC audit")

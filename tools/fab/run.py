"""Bagneux 1:192 fabrication pipeline — run all phases and write every deliverable.

    python tools/fab/run.py [--kerf IN] [--thickness IN] [--fit IN]

Outputs (fabrication/):
  Bagneux_Swimming_Pool_Extension_1-192_Fabrication.3dm   master file (4 systems on separate layers)
  laser/SHEET-nn.dxf / .svg                                 flat 2D laser files (inches)
  previews/SHEET-nn.pdf                                     sheet previews
  Bagneux_1-192_Fabrication_Drawings.pdf                    drawing set (A-E + notes + QC)
  docs/*.md, PART_SCHEDULE.csv, renders/*.png
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import params as PM
import build_parts, nest, qc, export as EX, docs, rhino_out

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kerf", type=float); ap.add_argument("--thickness", type=float); ap.add_argument("--fit", type=float)
    ap.add_argument("--out", default=os.path.join(ROOT, "fabrication"))
    ap.add_argument("--no-3dm", action="store_true")
    a = ap.parse_args()
    P = PM.load({"kerf_in": a.kerf, "t_mat_in": a.thickness, "fit_in": a.fit})
    out = a.out
    for d in ("laser", "previews", "docs", "renders"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    t0 = time.time()
    print("PHASE 2-5  parts ...", flush=True)
    B, parts = build_parts.build(P)
    print(f"           {len(parts)} part numbers, {sum(p.qty for p in parts)} pieces")
    print("PHASE 6    nesting ...", flush=True)
    sheets = nest.nest(parts, P)
    print("PHASE 8    QC ...", flush=True)
    qc_rows, hits = qc.run(B, parts, sheets, P)
    for c, n, s, d in qc_rows:
        print(f"           {s:4s} {c:<22} {n}")
    print("PHASE 9    laser export ...", flush=True)
    for s in sheets:
        g = EX.sheet_geometry(s, P)
        EX.write_dxf(g, os.path.join(out, "laser", f"{s.name}.dxf"))
        EX.write_svg(g, os.path.join(out, "laser", f"{s.name}.svg"), P)
        EX.preview(g, os.path.join(out, "previews", f"{s.name}.pdf"), f"{s.name} {s.title} {s.subtitle}", P)
        EX.preview(g, os.path.join(out, "previews", f"{s.name}.png"), f"{s.name} {s.title} {s.subtitle}", P)
    print("PHASE 7    documentation ...", flush=True)
    rows = docs.write_tables(B, parts, sheets, P, qc_rows, os.path.join(out, "docs"))
    docs.renders(B, parts, os.path.join(out, "renders"))
    docs.drawing_set(B, parts, sheets, P, rows, qc_rows, os.path.join(out, "renders"),
                     os.path.join(out, "Bagneux_1-192_Fabrication_Drawings.pdf"))
    json.dump({k: P[k] for k in P}, open(os.path.join(out, "docs", "fab_params_used.json"), "w"), indent=2)
    if not a.no_3dm:
        print("PHASE 9    Rhino master file ...", flush=True)
        tb = docs.text_blocks(parts, sheets, P, rows, qc_rows)
        bad = rhino_out.write(os.path.join(out, "Bagneux_Swimming_Pool_Extension_1-192_Fabrication.3dm"),
                              os.path.join(ROOT, "model", "Bagneux_Swimming_Pool_Extension.3dm"),
                              parts, sheets, P, B.T, {"text_blocks": tb, "step_titles": docs.STEP_TITLES})
        print(f"           original objects not scaled as expected: {bad}")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

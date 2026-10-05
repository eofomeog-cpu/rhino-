# Bagneux Swimming Pool Extension — 1:192 laser-cut chipboard kit

Generated from `model/Bagneux_Swimming_Pool_Extension.3dm` (original reconstruction, unmodified) by
`tools/fab/run.py`. Scale 1/16" = 1'-0" (1:192); material 1/16" chipboard; sheets 30" x 20".

## Deliverables

| File | What |
|---|---|
| `Bagneux_Swimming_Pool_Extension_1-192_Fabrication.3dm` | Rhino 8 master file (inches) — see layer guide below |
| `laser/SHEET-01..04.dxf` | **Laser files** (chipboard), inches, flat 2D, layers CUT / SCORE / ENGRAVE / NUMBERS / BOUNDARY |
| `laser/SHEET-05.dxf` | Optional clear acetate glazing (0.010"), not chipboard |
| `laser/*.svg` | Same geometry as SVG (hairline strokes, true inches) for SVG/AI-based laser drivers |
| `previews/SHEET-nn.pdf/.png` | Sheet previews |
| `Bagneux_1-192_Fabrication_Drawings.pdf` | Drawing set: cover, A exploded axo, B kit overview, C sheet index + every sheet, D part schedule, E assembly sequence, fabrication notes, QC |
| `docs/KIT_README.md` | Sheet index, part schedule, assembly sequence (text) |
| `docs/PART_SCHEDULE.csv` | Part schedule (part no., category, qty, material, thickness, assembly, sheet, size, status, joint, notes) |
| `docs/FABRICATION_NOTES.md` | Exaggerations (original scaled vs fabricated + reason), simplifications, omissions |
| `docs/QC_REPORT.md` | Fabrication audit results |
| `renders/*.png` | Assembled, roof-off, exploded and step-by-step renders |

## Laser setup

* DXF units = inches (`$INSUNITS = 1`). Import at 1:1. **Do not cut layer BOUNDARY** (30x20 edge + margin reference).
* CUT = red (ACI 1) — through cut. SCORE = blue (ACI 5) — light vector score (pool-floor folds, acetate mullions).
  ENGRAVE / NUMBERS = black (ACI 7) — light vector engrave (guides, part tags, sheet info). Run ENGRAVE/SCORE before CUT.
* KERF = **0 in these files** (no compensation). Measure your cutter's kerf on a test square, then regenerate:
  `python tools/fab/run.py --kerf 0.006` (outer profiles grow by kerf/2, openings and slots shrink by kerf/2).
* Measure the real chipboard thickness with calipers; if it is not 0.0625", regenerate with `--thickness`.
  Slot widths and laminations follow automatically. `--fit -0.002` makes slots a press fit.

## Rhino master file — layer guide (four separate systems)

| System | Layers | Location |
|---|---|---|
| ORIGINAL MODEL | original 31 layers (REFERENCE, STRUCTURE, WALLS, …) **locked**; geometry only unit-converted m -> in (1:1) | at origin, full size |
| FABRICATION MODEL | `10_FABRICATION_MODEL::FAB-BASE / FAB-SITE / FAB-STRUCTURE / FAB-SLABS / FAB-WALLS / FAB-ROOF / FAB-ENVELOPE / FAB-GLAZING / FAB-CIRCULATION / FAB-POOL / FAB-DETAILS / FAB-TABS` | X = 3000", physical size; every solid carries user text `part_no, kit, qty, plies, sheet, assembly_step, category, status, joint, exaggeration, source_guids` |
| LASER SHEETS | `20_LASER_SHEETS::FAB-CUT / FAB-SCORE / FAB-ENGRAVE / FAB-NUMBERS / FAB-SHEET-BOUNDARY / FAB-GUIDES`; one Rhino group per sheet | row at Y = -40" |
| DOCUMENTATION | `30_DOCUMENTATION::DOC-EXPLODED-AXO / DOC-KIT-OVERVIEW / DOC-SHEET-INDEX / DOC-PART-SCHEDULE / DOC-ASSEMBLY-SEQUENCE (+ STAGES) / DOC-FABRICATION-NOTES / DOC-QC` | exploded axo X = 3030", stages X = 3070", text Y = -100" |

The `FAB-PARAMETERS` text dot (on FAB-TABS) holds SCALE, T, KERF, FIT and sheet size as user text.

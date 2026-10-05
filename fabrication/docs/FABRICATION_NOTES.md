# Fabrication notes — simplifications, exaggerations, omissions

## Dimensional exaggerations (only where the real element is thinner than practical)

| Part | Element | Original scaled (mm) | Fabricated (mm) | Reason |
|---|---|---|---|---|
| ST013 | roof beam width 0.50 m | 2.6 | 3.17 | 2 plies for stiffness/bearing (+22%) |
| ST014 | inclined leg width 0.40 m | 2.08 | 3.17 | 45 mm slender member; 1 ply would snap |
| EN001 | forecourt wall height 3.01 m | 15.7 | 19.2 | carries the 1-ply solarium plate (real slab 1 m deep) |
| EN003 | HALL W WALL thickness 0.40 m | 2.08 | 1.59 | rounded to nearest whole ply |
| EN004 | HALL E WALL thickness 0.40 m | 2.08 | 1.59 | rounded to nearest whole ply |
| EN006 | E OUTER SKIN thickness 0.20 m | 1.05 | 1.59 | whole plies of chipboard |
| EN007 | N BAR W SLANT thickness 0.40 m | 2.08 | 1.59 | rounded to nearest whole ply |
| EN010 | GARDEN N WALL thickness 0.40 m | 2.08 | 1.59 | rounded to nearest whole ply |
| EN012 | NOTCH WALL (west zone S) thickness 0.50 m | 2.61 | 3.17 | whole plies of chipboard |
| EN013 | WEST ZONE E FACE (to terrace) thickness 0.59 m | 3.06 | 1.59 | rounded to nearest whole ply |
| EN014 | CANTILEVER FRONT (S block L1) thickness 0.50 m | 2.6 | 3.17 | whole plies of chipboard |
| EN017 | SOUTH BLOCK S WALL thickness 0.50 m | 2.61 | 3.17 | whole plies of chipboard |
| EN018 | SOUTH BLOCK E WALL thickness 0.50 m | 2.61 | 3.17 | whole plies of chipboard |
| EN019 | leaning wall thickness 0.46 m | 2.39 | 3.17 | whole plies; large unsupported plate |
| GL001 | GF mullions 0.10 m | 0.52 | 1.67 | minimum laser-cut bar width |
| GL002 | GF mullions 0.10 m | 0.52 | 1.67 | minimum laser-cut bar width |
| GL003 | GF mullions 0.10 m | 0.52 | 1.67 | minimum laser-cut bar width |
| GL004 | CW posts/transoms 0.08-0.20 m | 0.4-1.0 | 1.67 | minimum laser-cut bar width in chipboard |
| CI004 | bleacher tier rise 0.45-0.50 m (ASM) | 2.5 | 3.17 | whole plies: 2 per tier (+23%) |
| DE004 | NE BOX WALL thickness 0.15 m | 0.78 | 1.59 | whole plies of chipboard |
| DE005 | NE BOX WALL thickness 0.15 m | 0.78 | 1.59 | whole plies of chipboard |

Building plan dimensions, floor/roof elevations, the roof slope and all major geometry are **not** exaggerated: the assembled kit measures exactly the original/192 (see QC).

## Category C — omitted

| Element | Count | Reason |
|---|---|---|
| Interior partitions (INT GROUND/L1/L2) | 182 objects | enclosed; 0.24 m = 1.25 mm; not visible with roofs on |
| GF columns under main pool tank (S-GC) | 6 | hidden inside pool tank volume; 1.6 mm square |
| Stairs ST-A1/A2, ST-B1/B2, ST-C, ST-D1/D2, landings LD-A/LD-D | 9 | riser 0.83-0.95 mm < 1 ply; enclosed in north bar / under south block |
| Oval stair drum guard, curved walls 1.04 / 2.05 | 6 | inside wing / south block, not visible |
| Small doors (< 4 m2 or < 1.8 m wide) | 15 | 4.6-9 mm openings; would weaken walls; listed per wall in schedule notes |
| CW glass, 216 transoms, 55 mullions (sections 0.02-0.10 m) | ~440 | 0.1-0.5 mm; scored on optional acetate instead |
| N-bar slabs SL-11, SL-12, SL-21; hall deck thickness | 3 | hidden; replaced by 2 bulkheads |
| Lane lines, learners' pool steps, paddling pool 1.10, PISCINE letters | - | ENGRAVED (pool floors / L1 plate / forecourt wall outer face) instead of built |
| Analysis volumes, massing, reference images, grid, levels | 47 | non-physical |
| Stray / duplicate geometry (3x N wall, massing copy +104.5 m, Default surface) | 16 | excluded (left untouched in original) |

## Category B — simplified

* Curtain wall: chipboard frame with posts on grid C1–C6 and two transom bands (8.50 / 10.50); bars 0.32 m (1.67 mm) minimum; glazing open, optional acetate with scored mullions/transoms.
* GF entrance / vestibule glazing: frames with bars at the modelled mullions; head band carries the solarium plate.
* Bleachers: 4 stacked 2-ply plates (rise 2 plies per tier).
* Main pool floor: one plate folded on 3 scored lines following section 8 (2.10 -> 0.30 -> 1.45).
* Solarium slab edge (1 m deep) + parapet: one plate per side; GF elements under the canopy rise to the 1-ply L1 plate underside (+3.70) to carry it.
* N-bar interior and floors replaced by 2 hidden bulkheads; south block by 2 hidden ribs.
* West-zone east face: built from interior-layer wall pieces facing the terrace; gaps between them closed.
* Walls whose real thickness is <= 1.5 plies are 1 ply; 0.46-0.50 m walls are 2 plies (see table above).

## Geometry derived for fabrication (not modelled as a separate object in the original)

* N-bar spine wall = south face of massing M01 (beam bearing).
* L2 plate outline = SL-22 terrace + massing M06 top + M08 bottom.
* Hidden ribs/bulkheads at interior-wall lines (status DER-FAB / one ASM support at X 22.9).

## Model issues carried from the Phase 1 analysis

* Hall roof: modelled slope used (top +12.60 at section 8), not LEVELS +11.90 (default Q8).
* Triplicated N wall, massing copy at +104.53 m Y, stray Default surface: excluded.
* The model leaves the L1 wing's east side (facing the solarium) open; the kit leaves it open.

## Kerf / thickness / fit

Change in `tools/fab/fab_params.json` or `python tools/fab/run.py --kerf 0.006 --thickness 0.0625 --fit 0` and rerun: outer profiles are offset out by KERF/2, holes and slots in by KERF/2; slots are sized to n x T + FIT; engrave/score/number geometry is never offset.

* build log: thin-feature cleanup SUNSHADE TOP BEAM S-B7: removed 0.412 m2 (0.3%)
* build log: thin-feature cleanup SOLARIUM PARAPET E + SLAB EDGE: removed 0.001 m2 (0.0%)
* build log: thin-feature cleanup L1 PLATE: pool deck + wing + solarium (+4.00): removed 1.973 m2 (0.1%)
* build log: thin-feature cleanup L2 PLATE: terrace + south block floor (+7.05): removed 1.237 m2 (0.3%)
* build log: thin-feature cleanup SOUTH BLOCK ROOF RF-03: removed 1.008 m2 (0.5%)
* build log: thin-feature cleanup MAIN POOL FLOOR RIB W: removed 0.136 m2 (0.7%)
* build log: thin-feature cleanup MAIN POOL FLOOR RIB E: removed 0.002 m2 (0.1%)
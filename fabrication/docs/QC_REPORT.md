# Fabrication QC audit

| Category | Check | Result | Detail |
|---|---|---|---|
| SCALE | Scale factor | **PASS** | 1:192; 1 m real = 0.205052 in; 12'-0" -> 0.7500 in (0.75 in) |
| SCALE | Assembled model extents vs original x 1/192 | **PASS** | model 12.20 x 9.75 x 3.05 in; original/192 12.20 x 9.75 x 3.05 in (true mesh extents incl. GF slab); deviation (mm) [-0.0, 0.0, 0.03] |
| SCALE | Level L1 +4.00 = 0.8202 in | **PASS** | 1 plate(s) top exactly at datum |
| SCALE | Level L2 +7.05 = 1.4456 in | **PASS** | 1 plate(s) top exactly at datum |
| SCALE | Level top +14.55 = 2.9835 in | **PASS** | 3 plate(s) top exactly at datum |
| SHEET SIZE | All geometry inside 30 x 20 in | **PASS** | 5 sheets |
| SHEET SIZE | Cut geometry inside 0.5 in margin | **PASS** | worst intrusion 0.0000 in |
| SHEET SIZE | Sheet count | **PASS** | 4 chipboard + 1 optional acetate |
| MATERIAL | All chipboard parts are whole plies of T | **PASS** | T = 0.0625 in; ply counts {1: 63, 2: 12} |
| MATERIAL | Laminated parts | **PASS** | ST013 x2; ST014 x2; RF006 x2; EN012 x2; EN014 x2; EN017 x2; EN018 x2; EN019 x2; CI001 x2; CI002 x2; CI003 x2; CI004 x2 |
| PARTS | Unique part numbers / tags | **PASS** | 84 part numbers, 125 pieces |
| PARTS | Every piece on exactly one sheet | **PASS** | 125 pieces placed |
| PARTS | No critical element missing | **PASS** | 22 critical elements present |
| STRUCTURE | Primary structure counts | **PASS** | beams 6/6, legs 6/6, fins 7/7 |
| STRUCTURE | Every horizontal plate bears on walls/ribs/plates below | **PASS** | all plates supported |
| STRUCTURE | Removable hall roof bears on 6 beams + CW frame + spine | **PASS** | beam top edge = roof soffit slope 0.2059; roof width = hall wall inner faces minus 2 x clearance |
| ASSEMBLY | Every part has an assembly step | **PASS** | steps 1-15 assigned |
| ASSEMBLY | No interpenetrating parts (3D sampled, 0.1 mm tolerance) | **PASS** | 1 contact-level touches below threshold; documented exceptions: FL002xEN019 (leaning wall bevel) |
| ASSEMBLY | Joints | **PASS** | butt joints + through-slots (legs, fins, beam tabs) + laminations; no finger/interlocking joints |
| LASER | Cut geometry closed & valid | **PASS** | all CUT entities are closed polylines |
| LASER | CUT / SCORE / ENGRAVE / NUMBERS on separate layers | **PASS** | DXF layers CUT(red) SCORE(blue) ENGRAVE/NUMBERS(black) BOUNDARY(grey, no output) |
| LASER | Part spacing >= 0.15 in (no shared/duplicate cut lines) | **PASS** | ok |
| LASER | No tiny cut fragments (< 0.003 in2 or < 0.15 in perimeter) | **PASS** | none |
| LASER | No duplicated engrave/score lines | **PASS** | 0 duplicates |
| SCALE-DEPENDENT DETAIL | No material thinner than 0.055 in | **PASS** | thin-feature cleanup applied before nesting |
| SCALE-DEPENDENT DETAIL | Sub-scale elements simplified/omitted | **PASS** | 3 walls list omitted small doors; 182 interior partitions, 6 GF columns, mullion sections, stairs ST-A/B/C/D omitted (see notes) |
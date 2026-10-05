"""Fabrication parameters for the 1:192 chipboard kit.

Every physical dimension is derived from these values. Change them in
`fab_params.json` (repo root of tools/fab) or on the command line of
run.py and regenerate — nothing downstream hard-codes a thickness or kerf.
"""
import json, os

INCH = 25.4                         # mm
SCALE = 192.0                       # 1/16" = 1'-0"
M_TO_IN = 1000.0 / INCH / SCALE     # real metres -> physical inches (0.2050525)

DEFAULTS = {
    "scale": SCALE,
    "t_mat_in": 0.0625,       # chipboard thickness (1/16" confirmed by user)
    "kerf_in": 0.0,           # KERF = [USER ADJUSTABLE]; 0 = no compensation applied
    "fit_in": 0.0,            # extra clearance added to slots (negative = press fit)
    "roof_clear_in": 0.010,   # side clearance for the removable hall roof
    "sheet_w_in": 30.0,
    "sheet_h_in": 20.0,
    "margin_in": 0.5,
    "part_gap_in": 0.15,      # min clear distance between nested parts
    "min_feature_in": 0.055,  # thinnest bridge/strip allowed in chipboard (~1.4 mm)
    "min_hole_in": 0.10,      # smallest opening worth cutting; smaller -> engrave
    "tag_height_in": 0.06,    # engraved part-tag cap height (1.5 mm)
    "base_w_in": 16.5,
    "base_h_in": 13.0,
}

_HERE = os.path.dirname(__file__)
PARAM_FILE = os.path.join(_HERE, "fab_params.json")


class Params(dict):
    __getattr__ = dict.__getitem__

    @property
    def t_real(self):
        """One ply of chipboard expressed in real-world metres."""
        return self.t_mat_in / M_TO_IN

    def plies_for(self, real_thickness_m, minimum=1):
        """Nearest whole number of plies for a real thickness (never < minimum)."""
        return max(minimum, int(round(real_thickness_m / self.t_real)))


def load(overrides=None):
    p = dict(DEFAULTS)
    if os.path.exists(PARAM_FILE):
        with open(PARAM_FILE) as f:
            p.update(json.load(f))
    if overrides:
        p.update({k: v for k, v in overrides.items() if v is not None})
    return Params(p)


def m2in(x):
    return x * M_TO_IN

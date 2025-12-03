"""Small helper module: BV multiplier matrix and helpers used by the API.

This keeps the BV math isolated so it can be tested without importing the
full FastAPI app and DB layers.
"""
from typing import Dict, Any

# Rows = Gunnery 0..8, Columns = Piloting 0..8
BV_MULTIPLIER_MATRIX = [
    [2.42, 2.31, 2.21, 2.10, 1.93, 1.75, 1.68, 1.59, 1.50],
    [2.21, 2.11, 2.02, 1.92, 1.76, 1.60, 1.54, 1.446, 1.38],
    [1.93, 1.85, 1.76, 1.68, 1.54, 1.40, 1.35, 1.28, 1.21],
    [1.66, 1.58, 1.51, 1.44, 1.32, 1.20, 1.16, 1.10, 1.04],
    [1.38, 1.32, 1.26, 1.20, 1.10, 1.00, 0.95, 0.90, 0.85],
    [1.31, 1.19, 1.13, 1.08, 0.99, 0.90, 0.86, 0.81, 0.77],
    [1.24, 1.12, 1.07, 1.02, 0.94, 0.85, 0.81, 0.77, 0.72],
    [1.17, 1.06, 1.01, 0.96, 0.88, 0.80, 0.76, 0.72, 0.68],
    [1.10, 0.99, 0.95, 0.90, 0.83, 0.75, 0.71, 0.68, 0.64],
]


def get_multiplier_for(gunnery: int, piloting: int) -> float:
    if not (0 <= gunnery <= 8 and 0 <= piloting <= 8):
        raise ValueError("gunnery and piloting must be integers between 0 and 8 inclusive")
    return float(BV_MULTIPLIER_MATRIX[gunnery][piloting])


def compute_adjusted_bv(base_bv: int, base_g: int, base_p: int, target_g: int, target_p: int) -> Dict[str, Any]:
    base_mult = get_multiplier_for(base_g, base_p)
    target_mult = get_multiplier_for(target_g, target_p)
    if base_mult == 0:
        raise ValueError("base multiplier is zero")
    conv = target_mult / base_mult
    adjusted = int(round(base_bv * conv))
    return {"multiplier": conv, "adjusted_bv": adjusted, "target_mult": target_mult, "base_mult": base_mult}

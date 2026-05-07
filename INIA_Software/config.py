# config.py

import numpy as np

NUTRIENTS = ["N", "P2O5", "K2O", "CaO", "MgO", "S"]

FERTILIZER_NAMES = [
    "Fertilizante_2",
    "Fertilizante_12",
    "Fertilizante_17",
    "Fertilizante_21",
    "Fertilizante_25",
]

CURRENT_DOSES = np.array([
    4000,
    200,
    150,
    50,
    100,
], dtype=float)

# Columns: N, P2O5, K2O, CaO, MgO, S
FORMULA_PERCENT = np.array([
    [2.73, 0.62, 0.80, 0.34, 1.00, 0.40],
    [46.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    [18.00, 46.00, 0.00, 0.00, 0.00, 0.00],
    [0.00, 0.00, 60.00, 0.00, 0.00, 0.00],
    [0.00, 0.00, 22.00, 0.00, 18.00, 22.00],
], dtype=float)

FORMULA = FORMULA_PERCENT / 100.0

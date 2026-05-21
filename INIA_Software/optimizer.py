# optimizer.py

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from itertools import combinations

from config import (
    NUTRIENTS,
    CURRENT_DOSES,
)


# ------------------------------------------------------------
# Fertilizer dose bounds
# ------------------------------------------------------------
ESTIERCOL_MIN = 4000.0
ESTIERCOL_MAX = 6000.0

OTHER_FERTILIZER_MIN = 0.0
OTHER_FERTILIZER_MAX = 3000.0


# ------------------------------------------------------------
# Maximum number of fertilizers selected by optimizer
# ------------------------------------------------------------
MAX_FERTILIZERS_USED = 5


# ------------------------------------------------------------
# Estiércol is always included
# ------------------------------------------------------------
REQUIRED_FERTILIZER = "Estiércol de Vacuno"


# ------------------------------------------------------------
# Nutrients optimized
#
# Priority order:
#   1. P2O5
#   2. K2O
#   3. N
#   4. CaO
#   5. MgO
#
# S is ignored because it is not measured.
# ------------------------------------------------------------
OPTIMIZED_NUTRIENTS = ["P2O5", "K2O", "N", "CaO", "MgO"]


# ------------------------------------------------------------
# Molimax has low priority.
# It can be used, but only if needed.
# ------------------------------------------------------------
LOW_PRIORITY_FERTILIZERS = [
    "Molimax (20-20-20)",
    "Molimax (16-16-16)",
]

LOW_PRIORITY_PENALTY = 10_000.0


# ------------------------------------------------------------
# Reporting tolerance
# ------------------------------------------------------------
EXCESS_TOLERANCE = 50.0


# ------------------------------------------------------------
# Retry logic
# ------------------------------------------------------------
MAX_OPTIMIZATION_RETRIES = 5
SAFETY_MARGIN = 0.5


# ------------------------------------------------------------
# Fertilizer table
#
# Nutrient values are percentages.
#
# pH columns:
#   acid     -> pH < 5.5
#   alkaline -> pH > 8.0
#   neutral  -> 5.5 <= pH <= 8.0
# ------------------------------------------------------------
FERTILIZER_TABLE = {
    "Estiércol de Vacuno": {
        "N": 2.73,
        "P2O5": 0.62,
        "K2O": 0.80,
        "CaO": 0.34,
        "MgO": 1.00,
        "S": 0.40,
        "acid": True,
        "alkaline": True,
        "neutral": True,
    },
    "Urea": {
        "N": 46.00,
        "P2O5": 0.00,
        "K2O": 0.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 0.00,
        "acid": False,
        "alkaline": True,
        "neutral": True,
    },
    "Nitrato de Amonio": {
        "N": 33.00,
        "P2O5": 0.00,
        "K2O": 0.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 0.00,
        "acid": True,
        "alkaline": False,
        "neutral": True,
    },
    "Fosfato Diamónico": {
        "N": 18.00,
        "P2O5": 46.00,
        "K2O": 0.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 0.00,
        "acid": True,
        "alkaline": True,
        "neutral": True,
    },
    "Cloruro de Potasio": {
        "N": 0.00,
        "P2O5": 0.00,
        "K2O": 60.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 0.00,
        "acid":

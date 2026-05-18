# optimizer.py

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from config import (
    NUTRIENTS,
    FERTILIZER_NAMES,
    CURRENT_DOSES,
    FORMULA,
)


# ------------------------------------------------------------
# Fertilizer dose bounds
# ------------------------------------------------------------
ESTIERCOL_MIN = 4000.0
ESTIERCOL_MAX = 10000.0

OTHER_FERTILIZER_MIN = 0.0
# Set to a massive ceiling so the optimizer always has room to 
# exceed requirements, preventing any "Infeasible" crash.
OTHER_FERTILIZER_MAX = 100000.0 


# ------------------------------------------------------------
# Soft excess reference
# ------------------------------------------------------------
EXCESS_TOLERANCE = 50.0


# ------------------------------------------------------------
# Fertilizer preference weights
# ------------------------------------------------------------
FERTILIZER_WEIGHTS = np.array([
    -0.02,  # Estiércol de Vacuno, encouraged
     1.00,  # Urea
     1.00,  # Fosfato Diamónico
     3.00,  # Cloruro de Potasio
     3.00,  # Sulfato de Potasio y Magnesio
])


# ------------------------------------------------------------
# Excess penalty weights
#
# Since you don't care how much it exceeds, we drop these weights 
# to 0.0. The optimizer will only look at fertilizer cost preferences.
# ------------------------------------------------------------
EXCESS_WEIGHTS = np.array([
    0.0,  # N
    0.0,  # P2O5
    0.0,  # K2O
    0.0,  # CaO
    0.0,  # MgO
    0.0,  # S
])


def formula_as_fraction():
    formula = np.array(FORMULA, dtype=float)
    if np.nanmax(formula) > 1.0:
        formula = formula / 100.0
    return formula


def effective_requirements(requirements):
    requirements = np.array(requirements, dtype=float)
    return np.maximum(requirements, 0.0)


def nutrient_apport(doses):
    formula = formula_as_fraction()
    return np.array(doses, dtype=float) @ formula


def final_remaining(doses, requirements):
    requirements = effective_requirements(requirements)
    return requirements - nutrient_apport(doses)


def objective(doses, requirements):
    """ Kept for compatibility with the bigger code. """
    requirements = effective_requirements(requirements)
    doses = np.array(doses, dtype=float)
    apport = nutrient_apport(doses)

    remaining = requirements - apport
    excess = np.maximum(apport - requirements, 0.0)

    error = 0.0
    missing = np.maximum(remaining, 0.0)
    error += 10000.0 * np.sum(missing ** 2)
    error += np.sum(EXCESS_WEIGHTS * excess)
    error += np.sum(FERTILIZER_WEIGHTS * doses)
    return error


def make_constraints(requirements):
    """ Kept for compatibility with the bigger code. """
    return []


def solve_linear_program(requirements):
    """
    Linear programming optimizer.
    Guarantees supplied >= required by offering a virtually infinite upper bound ceiling.
    """
    requirements = effective_requirements(requirements)
    formula = formula_as_fraction()

    n_fertilizers = len(FERTILIZER_NAMES)
    n_nutrients = len(NUTRIENTS)

    n_variables = n_fertilizers + n_nutrients

    # Objective vector setup
    c = np.zeros(n_variables)
    c[:n_fertilizers] = FERTILIZER_WEIGHTS
    c[n_fertilizers:] = EXCESS_WEIGHTS

    A_ub = []
    b_ub = []

    for i, req in enumerate(requirements):
        nutrient_vector = formula[:, i]

        # Hard Constraint: supplied >= required  -->  -supplied <= -required
        if req > 0:
            row = np.zeros(n_variables)
            row[:n_fertilizers] = -nutrient_vector
            A_ub.append(row)
            b_ub.append(-req)

        # Excess tracking tracking slot (kept for compatibility)
        row = np.zeros(n_variables)
        row[:n_fertilizers] = nutrient_vector
        row[n_fertilizers + i] = -1.0
        A_ub.append(row)
        b_ub.append(req)

    A_ub = np.array(A_ub, dtype=float)
    b_ub = np.array(b_ub, dtype=float)

    # Apply massive bounds to guarantee feasibility
    bounds = []
    bounds.append((ESTIERCOL_MIN, ESTIERCOL_MAX))  # Estiércol controlled range
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Urea
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Fosfato Diamónico
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Cloruro de Potasio
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Sulfato K-Mg

    for _ in range(n_nutrients):
        bounds.append((0.0, None))  # Excess tracking slots

    result = linprog(
        c=c,
        A_ub=A_ub,
        b_ub=b_ub,
        bounds=bounds,
        method="highs",
    )

    if result.success:
        full_x = result.x.copy()
        result.full_x = full_x
        result.x = full_x[:n_fertilizers]
        result.excess_variables = full_x[n_fertilizers:]

    return result


def optimize_fertilizers(requirements):
    requirements = effective_requirements(requirements)
    result = solve_linear_program(requirements)

    if not result.success:
        print("\nWARNING: Linear optimization failed.")
        print(result.message)

    return result


def save_optimal_values_csv(output_csv, result):
    doses = np.round(result.x, 1)
    df = pd.DataFrame([doses], columns=FERTILIZER_NAMES)
    df.to_csv(output_csv, index=False)
    print(f"Saved optimal values CSV: {output_csv}")
    return doses


def print_optimization_results(requirements, result):
    original_requirements = np.array(requirements, dtype=float)
    requirements = effective_requirements(requirements)

    print("\n[2] Optimization results")

    if not result.success:
        print("WARNING: Optimization did not converge.")
        print(result.message)
        return

    doses = result.x
    apport = nutrient_apport(doses)
    remaining = final_remaining(doses, requirements)
    excess = apport - requirements

    print("\nOriginal requirements:")
    for name, original, effective in zip(NUTRIENTS, original_requirements, requirements):
        status = "NEGATIVE -> USED AS ZERO" if original < 0 else ("ZERO" if original == 0 else "REQUIRED")
        print(f"  {name:5s}: original = {original:10.2f}   used = {effective:10.2f}   {status}")

    print("\nOptimized fertilizer doses:")
    for name, old, new in zip(FERTILIZER_NAMES, CURRENT_DOSES, doses):
        print(f"  {name:35s}: {new:10.1f} kg/ha   {new / 50:8.1f} sacos/ha   change = {new - old:10.1f}")

    print("\nNutrient balance:")
    all_required_covered = True

    for name, req, app, rem, exc in zip(NUTRIENTS, requirements, apport, remaining, excess):
        if req > 0:
            if rem > 1e-6:
                status = "MISSING"
                all_required_covered = False
            else:
                status = "OK (TARGET MET OR EXCEEDED)"
        else:
            status = "NOT REQUIRED"

        print(f"  {name:5s}: required = {req:10.2f}   supplied = {app:10.2f}   remaining = {rem:10.2f}   excess = {exc:10.2f}   {status}")

    print("\nFinal check:")
    if all_required_covered:
        print("  OK: All nutrient requirements are fully covered or exceeded successfully.")
    else:
        print("  WARNING: Deficit found.")

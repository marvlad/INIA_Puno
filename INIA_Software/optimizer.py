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
# Main tolerance.
#
# The optimizer will try smaller tolerances first:
# 10, 20, 30, 40, 50, ...
#
# If you want to force only 50, change AUTO_TOLERANCES to [50.0]
# ------------------------------------------------------------
EXCESS_TOLERANCE = 50.0

AUTO_TOLERANCES = [
    10.0,
    20.0,
    30.0,
    40.0,
    50.0,
    75.0,
    100.0,
    150.0,
    200.0,
]


# ------------------------------------------------------------
# Organic fertilizer rule
#
# Estiércol de Vacuno is organic.
# We want to recommend it first.
# ------------------------------------------------------------
ESTIERCOL_MIN = 4000.0
ESTIERCOL_MAX = 6000.0


# ------------------------------------------------------------
# Fertilizer preference weights
#
# Order:
# 0 = Estiércol de Vacuno
# 1 = Urea
# 2 = Fosfato Diamónico
# 3 = Cloruro de Potasio
# 4 = Sulfato de Potasio y Magnesio
#
# Negative value for Estiércol encourages using more organic fertilizer.
# Positive values for chemical fertilizers penalize them.
# ------------------------------------------------------------
FERTILIZER_WEIGHTS = np.array([
    -0.02,  # Estiércol de Vacuno, encouraged
     1.00,  # Urea
     1.00,  # Fosfato Diamónico
     3.00,  # Cloruro de Potasio
     3.00,  # Sulfato de Potasio y Magnesio
])


def formula_as_fraction():
    """
    Convert FORMULA to fraction if it is written as percentage.

    Example:
        46.0 means 46%, so it becomes 0.46.

    If FORMULA is already in fraction form, for example 0.46,
    then it is kept as it is.
    """

    formula = np.array(FORMULA, dtype=float)

    if np.nanmax(formula) > 1.0:
        return formula / 100.0

    return formula


def effective_requirements(requirements):
    """
    Negative requirements are treated as zero.

    Example:
        [36, 148, -2650, -2438, -53, 27]

    becomes:
        [36, 148, 0, 0, 0, 27]

    This means:
        optimize only what is missing.
    """

    requirements = np.array(requirements, dtype=float)

    return np.maximum(requirements, 0.0)


def nutrient_apport(doses):
    """
    Calculate nutrients supplied by the fertilizer doses.

    doses:
        [Estiércol, Urea, Fosfato Diamónico, Cloruro K, Sulfato K-Mg]

    output:
        [N, P2O5, K2O, CaO, MgO, S]
    """

    formula = formula_as_fraction()

    return np.array(doses, dtype=float) @ formula


def final_remaining(doses, requirements):
    requirements = effective_requirements(requirements)

    return requirements - nutrient_apport(doses)


def objective(doses, requirements):
    """
    Kept for compatibility with your bigger code.

    The real optimization is now done with linprog inside
    optimize_fertilizers().
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(doses)
    remaining = requirements - apport

    error = 0.0

    for req, app, rem in zip(requirements, apport, remaining):
        excess = app - req

        if rem > 0:
            error += 10000.0 * rem**2

        if req > 0 and excess > EXCESS_TOLERANCE:
            error += 10000.0 * (excess - EXCESS_TOLERANCE) ** 2

        if excess > 0:
            error += 0.1 * excess**2

    error += np.sum(FERTILIZER_WEIGHTS * np.array(doses, dtype=float))

    return error


def make_constraints(requirements):
    """
    Kept for compatibility with your bigger code.

    linprog does not use scipy-style constraint dictionaries.
    The real constraints are built inside optimize_fertilizers().
    """

    return []


def solve_linear_program(requirements, tolerance):
    """
    Linear programming optimizer.

    Variables:

        x[0] = Estiércol de Vacuno dose
        x[1] = Urea dose
        x[2] = Fosfato Diamónico dose
        x[3] = Cloruro de Potasio dose
        x[4] = Sulfato de Potasio y Magnesio dose

        x[5]  = excess variable for N
        x[6]  = excess variable for P2O5
        x[7]  = excess variable for K2O
        x[8]  = excess variable for CaO
        x[9]  = excess variable for MgO
        x[10] = excess variable for S

    Why excess variables?

    They allow the optimizer to penalize unnecessary nutrient excess
    while keeping the problem linear.
    """

    requirements = effective_requirements(requirements)
    formula = formula_as_fraction()

    n_fertilizers = len(FERTILIZER_NAMES)
    n_nutrients = len(NUTRIENTS)

    n_variables = n_fertilizers + n_nutrients

    # ------------------------------------------------------------
    # Objective function:
    #
    # Minimize:
    #   fertilizer preference cost
    #   + nutrient excess penalty
    #
    # Estiércol has negative weight, so the optimizer prefers it.
    # Chemical fertilizers have positive weight, so they are used
    # only when needed.
    # ------------------------------------------------------------
    c = np.zeros(n_variables)

    c[:n_fertilizers] = FERTILIZER_WEIGHTS

    for i, req in enumerate(requirements):
        if req > 0:
            c[n_fertilizers + i] = 0.20
        else:
            c[n_fertilizers + i] = 2.00

    A_ub = []
    b_ub = []

    # ------------------------------------------------------------
    # Nutrient constraints.
    #
    # For every nutrient with positive requirement:
    #
    #   supplied_i >= requirement_i
    #   supplied_i <= requirement_i + tolerance
    #
    # For negative original requirements:
    #
    #   they were converted to zero,
    #   so they are not required.
    # ------------------------------------------------------------
    for i, req in enumerate(requirements):

        nutrient_vector = formula[:, i]

        if req > 0:
            # supplied_i >= requirement_i
            # linprog uses A_ub @ x <= b_ub
            # therefore:
            # -supplied_i <= -requirement_i

            row = np.zeros(n_variables)
            row[:n_fertilizers] = -nutrient_vector

            A_ub.append(row)
            b_ub.append(-req)

            # supplied_i <= requirement_i + tolerance

            row = np.zeros(n_variables)
            row[:n_fertilizers] = nutrient_vector

            A_ub.append(row)
            b_ub.append(req + tolerance)

        # --------------------------------------------------------
        # Excess variable definition:
        #
        # excess_i >= supplied_i - requirement_i
        #
        # equivalent:
        #
        # supplied_i - excess_i <= requirement_i
        #
        # This lets the optimizer minimize excess nutrients.
        # --------------------------------------------------------
        row = np.zeros(n_variables)
        row[:n_fertilizers] = nutrient_vector
        row[n_fertilizers + i] = -1.0

        A_ub.append(row)
        b_ub.append(req)

    A_ub = np.array(A_ub, dtype=float)
    b_ub = np.array(b_ub, dtype=float)

    bounds = []

    # Fertilizer dose bounds
    bounds.append((ESTIERCOL_MIN, ESTIERCOL_MAX))  # Estiércol de Vacuno
    bounds.append((0.0, 1000.0))                  # Urea
    bounds.append((0.0, 1000.0))                  # Fosfato Diamónico
    bounds.append((0.0, 1000.0))                  # Cloruro de Potasio
    bounds.append((0.0, 1000.0))                  # Sulfato de Potasio y Magnesio

    # Excess variables bounds
    for _ in range(n_nutrients):
        bounds.append((0.0, None))

    result = linprog(
        c=c,
        A_ub=A_ub,
        b_ub=b_ub,
        bounds=bounds,
        method="highs",
    )

    if result.success:
        full_x = result.x.copy()

        doses = full_x[:n_fertilizers]
        excess_variables = full_x[n_fertilizers:]

        # Keep compatibility with your bigger code:
        # result.x must contain only the 5 fertilizer doses.
        result.full_x = full_x
        result.x = doses
        result.excess_variables = excess_variables
        result.tolerance_used = tolerance

    return result


def optimize_fertilizers(requirements):
    """
    Optimize fertilizer doses using linear programming.

    It tries small tolerance first.

    Example:
        tolerance = 10
        tolerance = 20
        tolerance = 30
        ...

    The first feasible solution is returned.
    """

    requirements = effective_requirements(requirements)

    last_result = None

    for tolerance in AUTO_TOLERANCES:

        result = solve_linear_program(
            requirements=requirements,
            tolerance=tolerance,
        )

        last_result = result

        if result.success:
            set_excess_tolerance(tolerance)
            return result

    print("\nWARNING: Linear optimization failed.")
    print("No feasible solution was found with the tested tolerances.")
    print("Tolerances tested:")
    print(AUTO_TOLERANCES)

    if last_result is not None:
        print(last_result.message)

    return last_result


def set_excess_tolerance(value):
    global EXCESS_TOLERANCE
    EXCESS_TOLERANCE = float(value)


def save_optimal_values_csv(output_csv, result):
    doses = np.round(result.x, 1)

    df = pd.DataFrame(
        [doses],
        columns=FERTILIZER_NAMES,
    )

    df.to_csv(output_csv, index=False)

    print(f"Saved optimal values CSV: {output_csv}")

    return doses


def print_optimization_results(requirements, result):
    original_requirements = np.array(requirements, dtype=float)
    requirements = effective_requirements(requirements)

    doses = result.x
    apport = nutrient_apport(doses)
    remaining = final_remaining(doses, requirements)

    tolerance_used = getattr(result, "tolerance_used", EXCESS_TOLERANCE)

    print("\n[2] Optimization results")

    if not result.success:
        print("WARNING: Optimization did not converge.")
        print(result.message)
        return

    print("\nOriginal requirements:")
    print("Negative values are treated as zero.")

    for name, original, effective in zip(
        NUTRIENTS,
        original_requirements,
        requirements,
    ):
        if original < 0:
            status = "NEGATIVE -> USED AS ZERO"
        elif original == 0:
            status = "ZERO"
        else:
            status = "REQUIRED"

        print(
            f"  {name:5s}: "
            f"original = {original:10.2f}   "
            f"used = {effective:10.2f}   "
            f"{status}"
        )

    print("\nOptimized fertilizer doses:")

    for name, old, new in zip(FERTILIZER_NAMES, CURRENT_DOSES, doses):
        print(
            f"  {name:35s}: "
            f"{new:10.1f} kg/ha   "
            f"{new / 50:8.1f} sacos/ha   "
            f"change = {new - old:10.1f}"
        )

    print("\nNutrient balance:")
    print("Rule for required nutrients:")
    print("  required_i <= supplied_i <= required_i + tolerance")
    print(f"Tolerance used: {tolerance_used:.1f} kg/ha")

    all_ok = True

    for name, req, app, rem in zip(NUTRIENTS, requirements, apport, remaining):
        excess = app - req

        if req > 0:
            if rem > 1e-6:
                status = "MISSING"
                all_ok = False
            elif excess > tolerance_used + 1e-6:
                status = "HIGH EXCESS"
                all_ok = False
            else:
                status = "OK"
        else:
            status = "NOT REQUIRED"

        print(
            f"  {name:5s}: "
            f"required = {req:10.2f}   "
            f"supplied = {app:10.2f}   "
            f"remaining = {rem:10.2f}   "
            f"excess = {excess:10.2f}   "
            f"{status}"
        )

    print("\nFinal check:")

    if all_ok:
        print("  OK: all positive nutrient requirements are covered.")
    else:
        print("  WARNING: at least one required nutrient is missing or above tolerance.")

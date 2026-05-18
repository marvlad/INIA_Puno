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
OTHER_FERTILIZER_MAX = 1000.0


# ------------------------------------------------------------
# Soft excess reference
#
# This is NOT a hard constraint anymore.
# It is only used for printing the status.
#
# The optimizer will still allow more than this if needed,
# but it will try to minimize excess.
# ------------------------------------------------------------
EXCESS_TOLERANCE = 50.0


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
# Smaller value means more preferred.
#
# We give Estiércol a negative cost to encourage organic fertilizer.
# Chemical fertilizers have positive costs, so the optimizer uses
# them only when needed.
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
# These penalize nutrients supplied above the requirement.
#
# Larger value = stronger penalty against excess.
# ------------------------------------------------------------
EXCESS_WEIGHTS = np.array([
    10.0,  # N
    10.0,  # P2O5
    20.0,  # K2O
    20.0,  # CaO
    20.0,  # MgO
    20.0,  # S
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
        formula = formula / 100.0

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
    Calculate nutrients supplied by fertilizer doses.

    doses:
        [Estiércol, Urea, Fosfato Diamónico, Cloruro K, Sulfato K-Mg]

    FORMULA:
        rows = fertilizers
        columns = nutrients [N, P2O5, K2O, CaO, MgO, S]

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
    Kept for compatibility with the bigger code.

    The actual optimization is done with linprog in optimize_fertilizers().
    """

    requirements = effective_requirements(requirements)

    doses = np.array(doses, dtype=float)
    apport = nutrient_apport(doses)

    remaining = requirements - apport
    excess = np.maximum(apport - requirements, 0.0)

    error = 0.0

    # Strong penalty if something is missing.
    missing = np.maximum(remaining, 0.0)
    error += 10000.0 * np.sum(missing ** 2)

    # Soft penalty for excess.
    error += np.sum(EXCESS_WEIGHTS * excess)

    # Fertilizer preference.
    error += np.sum(FERTILIZER_WEIGHTS * doses)

    return error


def make_constraints(requirements):
    """
    Kept for compatibility with the bigger code.

    linprog builds constraints directly inside solve_linear_program().
    """

    return []


def solve_linear_program(requirements):
    """
    Linear programming optimizer with elastic slacks to guarantee a solution always exists.

    Variables setup:
        x[0] = Estiércol de Vacuno
        x[1] = Urea
        x[2] = Fosfato Diamónico
        x[3] = Cloruro de Potasio
        x[4] = Sulfato de Potasio y Magnesio

        x[5] to x[10]  = excess N, P2O5, K2O, CaO, MgO, S
        x[11] to x[16] = deficit slacks for N, P2O5, K2O, CaO, MgO, S (Safety net variables)
    """

    requirements = effective_requirements(requirements)
    formula = formula_as_fraction()

    n_fertilizers = len(FERTILIZER_NAMES)
    n_nutrients = len(NUTRIENTS)

    # Expanded to include n_nutrients deficit slack variables
    n_variables = n_fertilizers + (2 * n_nutrients)

    # ------------------------------------------------------------
    # Objective vector
    # Minimize preference costs + excess penalty + massive deficit penalty
    # ------------------------------------------------------------
    c = np.zeros(n_variables)

    # Fertilizer preference
    c[:n_fertilizers] = FERTILIZER_WEIGHTS

    # Nutrient excess penalty
    c[n_fertilizers : n_fertilizers + n_nutrients] = EXCESS_WEIGHTS

    # Nutrient deficit slack penalty (Very high number to prevent it from activating unless needed)
    DEFICIT_PENALTY = 10000.0
    c[n_fertilizers + n_nutrients :] = DEFICIT_PENALTY

    A_ub = []
    b_ub = []

    for i, req in enumerate(requirements):
        nutrient_vector = formula[:, i]

        # --------------------------------------------------------
        # Elastic lower constraint for required nutrients:
        # supplied_i + deficit_slack_i >= required_i
        #
        # Re-written as standard linprog form (<=):
        # -supplied_i - deficit_slack_i <= -required_i
        # --------------------------------------------------------
        if req > 0:
            row = np.zeros(n_variables)
            row[:n_fertilizers] = -nutrient_vector
            row[n_fertilizers + n_nutrients + i] = -1.0  # Deficit slack variable slot

            A_ub.append(row)
            b_ub.append(-req)

        # --------------------------------------------------------
        # Excess variable evaluation structure:
        # excess_i >= supplied_i - required_i
        #
        # Re-written as standard form (<=):
        # supplied_i - excess_i <= required_i
        # --------------------------------------------------------
        row = np.zeros(n_variables)
        row[:n_fertilizers] = nutrient_vector
        row[n_fertilizers + i] = -1.0  # Excess variable slot

        A_ub.append(row)
        b_ub.append(req)

    A_ub = np.array(A_ub, dtype=float)
    b_ub = np.array(b_ub, dtype=float)

    # ------------------------------------------------------------
    # Bounds setup
    # ------------------------------------------------------------
    bounds = []

    # Fertilizers Bounds
    bounds.append((ESTIERCOL_MIN, ESTIERCOL_MAX))                # Estiércol (4000 to 10000)
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Urea
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Fosfato Diamónico
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Cloruro de Potasio
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Sulfato K-Mg

    # Excess variables Bounds
    for _ in range(n_nutrients):
        bounds.append((0.0, None))

    # Deficit slack variables Bounds
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
        excess_variables = full_x[n_fertilizers : n_fertilizers + n_nutrients]
        deficit_variables = full_x[n_fertilizers + n_nutrients :]

        # Maintain exact internal property signatures for external codes
        result.full_x = full_x
        result.x = doses
        result.excess_variables = excess_variables
        result.deficit_variables = deficit_variables

    return result


def optimize_fertilizers(requirements):
    """
    Optimize fertilizer doses using linear programming.

    This version does not use a hard upper tolerance.
    It only forces:
        supplied_i >= required_i

    Then it minimizes excess.
    """

    requirements = effective_requirements(requirements)

    result = solve_linear_program(requirements)

    if not result.success:
        print("\nWARNING: Linear optimization failed.")
        print(result.message)
        print("\nPossible reasons:")
        print("  1. Estiércol minimum is too high.")
        print("  2. Fertilizer upper bounds are too low.")
        print("  3. Requirements are too high for available fertilizers.")
        print("  4. FORMULA matrix may be wrong or missing a nutrient column.")

    return result


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
    print("Negative requirements are treated as zero.")

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
    print("Hard rule:")
    print("  supplied_i >= required_i")
    print("Soft rule:")
    print("  excess is minimized, but not forbidden")
    print(f"Reference tolerance for status: {EXCESS_TOLERANCE:.1f} kg/ha")

    all_required_covered = True

    for name, req, app, rem, exc in zip(
        NUTRIENTS,
        requirements,
        apport,
        remaining,
        excess,
    ):

        if req > 0:
            if rem > 1e-6:
                status = "MISSING (BOUND LIMIT REACHED)"
                all_required_covered = False
            elif exc > EXCESS_TOLERANCE + 1e-6:
                status = "OK, HIGH EXCESS"
            else:
                status = "OK"
        else:
            if app > EXCESS_TOLERANCE:
                status = "NOT REQUIRED, ADDED"
            else:
                status = "NOT REQUIRED"

        print(
            f"  {name:5s}: "
            f"required = {req:10.2f}   "
            f"supplied = {app:10.2f}   "
            f"remaining = {rem:10.2f}   "
            f"excess = {exc:10.2f}   "
            f"{status}"
        )

    print("\nFinal check:")

    if all_required_covered:
        print("  OK: all positive nutrient requirements are covered.")
    else:
        print("  WARNING: at least one positive nutrient requirement could not be fully met within the specified maximum fertilizer limits.")

    print("\nDebug information:")
    print(f"  FORMULA shape: {np.array(FORMULA).shape}")
    print(f"  Nutrients: {list(NUTRIENTS)}")
    print(f"  Fertilizers: {list(FERTILIZER_NAMES)}")

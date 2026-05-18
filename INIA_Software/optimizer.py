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
ESTIERCOL_MAX = 6000.0

OTHER_FERTILIZER_MIN = 0.0
OTHER_FERTILIZER_MAX = 2000.0


# ------------------------------------------------------------
# Soft excess reference
#
# This is NOT a hard upper limit.
# It is only used for printing the status.
#
# The optimizer will allow more than this if needed,
# but it will try to minimize unnecessary excess.
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
# Important:
# Do NOT make Estiércol strongly negative.
# If it is too negative, the optimizer may push it to the maximum
# even when it creates too much excess.
# ------------------------------------------------------------
FERTILIZER_WEIGHTS = np.array([
    0.01,  # Estiércol de Vacuno, preferred
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

    if formula.ndim != 2:
        raise ValueError(
            f"FORMULA must be a 2D matrix, but got shape {formula.shape}"
        )

    if formula.shape[0] != len(FERTILIZER_NAMES):
        raise ValueError(
            "FORMULA row number must match number of fertilizers.\n"
            f"FORMULA shape: {formula.shape}\n"
            f"FERTILIZER_NAMES length: {len(FERTILIZER_NAMES)}"
        )

    if formula.shape[1] != len(NUTRIENTS):
        raise ValueError(
            "FORMULA column number must match number of nutrients.\n"
            f"FORMULA shape: {formula.shape}\n"
            f"NUTRIENTS length: {len(NUTRIENTS)}\n"
            "Expected columns: [N, P2O5, K2O, CaO, MgO, S]"
        )

    # If values are written as percentages, convert to fractions.
    if np.nanmax(formula) > 1.0:
        formula = formula / 100.0

    return formula


def effective_requirements(requirements):
    """
    Negative requirements are treated as zero.

    Example:
        [299, 609, -150, -2384, -500, 41]

    becomes:
        [299, 609, 0, 0, 0, 41]

    This means:
        optimize only what is missing.
    """

    requirements = np.array(requirements, dtype=float)

    if requirements.shape[0] != len(NUTRIENTS):
        raise ValueError(
            "requirements length must match NUTRIENTS length.\n"
            f"requirements length: {requirements.shape[0]}\n"
            f"NUTRIENTS length: {len(NUTRIENTS)}"
        )

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

    doses = np.array(doses, dtype=float)
    formula = formula_as_fraction()

    return doses @ formula


def final_remaining(doses, requirements):
    requirements = effective_requirements(requirements)

    return requirements - nutrient_apport(doses)


def validate_solution(requirements, doses, tolerance=1e-6):
    """
    Final hard validation.

    This function guarantees that every positive nutrient requirement
    is satisfied.

    If one nutrient is missing, the solution is rejected.
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(doses)
    remaining = requirements - apport

    missing = remaining > tolerance

    if np.any(missing):
        print("\nERROR: invalid fertilizer solution.")
        print("At least one nutrient requirement is still missing.")
        print("This solution will be rejected.")

        for name, req, app, rem in zip(
            NUTRIENTS,
            requirements,
            apport,
            remaining,
        ):
            if rem > tolerance:
                print(
                    f"  {name:5s}: "
                    f"required = {req:10.2f}, "
                    f"supplied = {app:10.2f}, "
                    f"missing = {rem:10.2f}"
                )

        return False

    return True


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
    missing = np.maximum(remaining, 0.0)

    error = 0.0

    # Strong penalty if something is missing.
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
    Linear programming optimizer.

    Variables:

        x[0] = Estiércol de Vacuno
        x[1] = Urea
        x[2] = Fosfato Diamónico
        x[3] = Cloruro de Potasio
        x[4] = Sulfato de Potasio y Magnesio

        x[5]  = excess N
        x[6]  = excess P2O5
        x[7]  = excess K2O
        x[8]  = excess CaO
        x[9]  = excess MgO
        x[10] = excess S

    Main hard rule:

        supplied_i >= required_i

    This is applied to every nutrient where requirement_i > 0.

    Soft rule:

        excess_i is minimized in the objective,
        but it is not forbidden.
    """

    requirements = effective_requirements(requirements)
    formula = formula_as_fraction()

    n_fertilizers = len(FERTILIZER_NAMES)
    n_nutrients = len(NUTRIENTS)

    n_variables = n_fertilizers + n_nutrients

    # ------------------------------------------------------------
    # Objective vector
    #
    # Minimize:
    #
    #   fertilizer cost/preference
    #   + excess nutrient penalties
    # ------------------------------------------------------------
    c = np.zeros(n_variables)

    c[:n_fertilizers] = FERTILIZER_WEIGHTS
    c[n_fertilizers:] = EXCESS_WEIGHTS

    A_ub = []
    b_ub = []

    print("\nDEBUG: hard nutrient constraints")

    for i, req in enumerate(requirements):

        nutrient_vector = formula[:, i]

        # --------------------------------------------------------
        # Hard lower constraint for required nutrients:
        #
        #   supplied_i >= required_i
        #
        # linprog only accepts:
        #
        #   A_ub @ x <= b_ub
        #
        # Therefore:
        #
        #   -supplied_i <= -required_i
        #
        # This is the critical part that guarantees:
        #
        #   required_i <= supplied_i
        # --------------------------------------------------------
        if req > 0:
            row = np.zeros(n_variables)
            row[:n_fertilizers] = -nutrient_vector

            A_ub.append(row)
            b_ub.append(-req)

            print(f"  {NUTRIENTS[i]} must be >= {req:.2f}")
            print(f"    formula column = {nutrient_vector}")

        # --------------------------------------------------------
        # Excess variable definition:
        #
        #   excess_i >= supplied_i - required_i
        #
        # Equivalent:
        #
        #   supplied_i - excess_i <= required_i
        #
        # This lets linprog minimize excess in the objective.
        # --------------------------------------------------------
        row = np.zeros(n_variables)
        row[:n_fertilizers] = nutrient_vector
        row[n_fertilizers + i] = -1.0

        A_ub.append(row)
        b_ub.append(req)

    A_ub = np.array(A_ub, dtype=float)
    b_ub = np.array(b_ub, dtype=float)

    # ------------------------------------------------------------
    # Bounds
    # ------------------------------------------------------------
    bounds = []

    # Fertilizers
    bounds.append((ESTIERCOL_MIN, ESTIERCOL_MAX))                  # Estiércol
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))    # Urea
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))    # Fosfato Diamónico
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))    # Cloruro de Potasio
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))    # Sulfato K-Mg

    # Excess variables
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
        # result.x contains only the 5 fertilizer doses.
        result.full_x = full_x
        result.x = doses
        result.excess_variables = excess_variables

    return result


def optimize_fertilizers(requirements):
    """
    Optimize fertilizer doses using linear programming.

    This version forces:

        supplied_i >= required_i

    for every positive nutrient requirement.

    It does NOT force an upper tolerance as a hard constraint.
    Excess is minimized softly.
    """

    requirements = effective_requirements(requirements)

    result = solve_linear_program(requirements)

    if not result.success:
        print("\nWARNING: Linear optimization failed.")
        print(result.message)
        print("\nPossible reasons:")
        print("  1. Requirements are too high for the fertilizer limits.")
        print("  2. OTHER_FERTILIZER_MAX is too low.")
        print("  3. FORMULA matrix columns are not ordered as [N, P2O5, K2O, CaO, MgO, S].")
        print("  4. FORMULA matrix is missing one nutrient column.")
        print("\nThings to try:")
        print("  - Increase OTHER_FERTILIZER_MAX from 2000 to 3000 or 5000.")
        print("  - Check that FORMULA has shape (5, 6).")
        print("  - Check P2O5 column carefully.")
        return result

    # ------------------------------------------------------------
    # Final validation.
    #
    # This prevents accepting a solution like:
    #
    #   P2O5 required = 609
    #   P2O5 supplied = 522
    #
    # That must be rejected.
    # ------------------------------------------------------------
    if not validate_solution(requirements, result.x):
        result.success = False
        result.message = (
            "Invalid solution: at least one positive nutrient requirement "
            "is still missing."
        )

    return result


def save_optimal_values_csv(output_csv, result):
    if not result.success:
        raise RuntimeError(
            "Cannot save optimal values because optimization failed:\n"
            f"{result.message}"
        )

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
        print("WARNING: Optimization did not converge or solution was invalid.")
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
                status = "MISSING"
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
        print("  WARNING: at least one positive nutrient requirement is missing.")

    print("\nDebug information:")
    print(f"  FORMULA shape: {np.array(FORMULA).shape}")
    print(f"  Nutrients: {list(NUTRIENTS)}")
    print(f"  Fertilizers: {list(FERTILIZER_NAMES)}")

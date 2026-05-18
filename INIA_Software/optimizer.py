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
OTHER_FERTILIZER_MAX = 3000.0


# ------------------------------------------------------------
# This is only for reporting.
# It is NOT a hard upper constraint.
# The hard rule is only:
#
#     supplied_i >= required_i
# ------------------------------------------------------------
EXCESS_TOLERANCE = 50.0


# ------------------------------------------------------------
# Fertilizer preference weights
#
# Smaller = preferred.
#
# Do not use a strong negative value for Estiércol.
# A strong negative value can push Estiércol too high and create
# unnecessary excess.
# ------------------------------------------------------------
FERTILIZER_WEIGHTS = np.array([
    0.01,  # Estiércol de Vacuno
    1.00,  # Urea
    1.00,  # Fosfato Diamónico
    3.00,  # Cloruro de Potasio
    3.00,  # Sulfato de Potasio y Magnesio
], dtype=float)


# ------------------------------------------------------------
# Excess penalty weights
#
# These penalize nutrients supplied above the requirement.
# ------------------------------------------------------------
EXCESS_WEIGHTS = np.array([
    10.0,  # N
    10.0,  # P2O5
    20.0,  # K2O
    20.0,  # CaO
    20.0,  # MgO
    20.0,  # S
], dtype=float)


def formula_as_fraction():
    """
    Convert FORMULA to fraction if it is written as percentage.

    Example:
        46.0 means 46%, so it becomes 0.46.

    If FORMULA is already written as fraction, for example 0.46,
    it is kept unchanged.
    """

    formula = np.array(FORMULA, dtype=float)

    if formula.ndim != 2:
        raise ValueError(
            f"FORMULA must be a 2D matrix. Current shape: {formula.shape}"
        )

    if formula.shape[0] != len(FERTILIZER_NAMES):
        raise ValueError(
            "FORMULA rows must match FERTILIZER_NAMES.\n"
            f"FORMULA shape: {formula.shape}\n"
            f"Number of fertilizers: {len(FERTILIZER_NAMES)}"
        )

    if formula.shape[1] != len(NUTRIENTS):
        raise ValueError(
            "FORMULA columns must match NUTRIENTS.\n"
            f"FORMULA shape: {formula.shape}\n"
            f"Number of nutrients: {len(NUTRIENTS)}\n"
            "Expected nutrient order: [N, P2O5, K2O, CaO, MgO, S]"
        )

    if np.nanmax(formula) > 1.0:
        formula = formula / 100.0

    return formula


def effective_requirements(requirements):
    """
    Convert negative requirements to zero.

    Example:
        [299, 609, -150, -2384, -500, 41]

    becomes:
        [299, 609, 0, 0, 0, 41]

    Meaning:
        optimize only nutrients that are missing.
    """

    requirements = np.array(requirements, dtype=float)

    if requirements.ndim != 1:
        raise ValueError(
            f"requirements must be a 1D vector. Current shape: {requirements.shape}"
        )

    if len(requirements) != len(NUTRIENTS):
        raise ValueError(
            "requirements length must match NUTRIENTS length.\n"
            f"requirements length: {len(requirements)}\n"
            f"NUTRIENTS length: {len(NUTRIENTS)}"
        )

    return np.maximum(requirements, 0.0)


def nutrient_apport(doses):
    """
    Calculate nutrient supplied by fertilizer doses.

    doses:
        [Estiércol, Urea, Fosfato Diamónico, Cloruro K, Sulfato K-Mg]

    FORMULA:
        rows = fertilizers
        columns = nutrients [N, P2O5, K2O, CaO, MgO, S]

    output:
        [N, P2O5, K2O, CaO, MgO, S]
    """

    doses = np.array(doses, dtype=float)

    if doses.ndim != 1:
        raise ValueError(f"doses must be a 1D vector. Current shape: {doses.shape}")

    if len(doses) != len(FERTILIZER_NAMES):
        raise ValueError(
            "doses length must match FERTILIZER_NAMES length.\n"
            f"doses length: {len(doses)}\n"
            f"FERTILIZER_NAMES length: {len(FERTILIZER_NAMES)}"
        )

    formula = formula_as_fraction()

    return doses @ formula


def final_remaining(doses, requirements):
    requirements = effective_requirements(requirements)

    return requirements - nutrient_apport(doses)


def validate_solution(requirements, doses, tolerance=1e-6):
    """
    Strict final validation.

    This guarantees:

        supplied_i >= required_i

    for every positive requirement.

    If not, the solution is rejected.
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(doses)
    remaining = requirements - apport

    missing_mask = remaining > tolerance

    print("\nSTRICT FINAL VALIDATION")
    print("Rule: supplied_i must be >= required_i for every positive requirement.")

    for name, req, app, rem in zip(NUTRIENTS, requirements, apport, remaining):
        print(
            f"  {name:5s}: "
            f"required = {req:10.2f}   "
            f"supplied = {app:10.2f}   "
            f"remaining = {rem:10.2f}"
        )

    if np.any(missing_mask):
        lines = [
            "",
            "INVALID OPTIMIZATION RESULT.",
            "At least one nutrient requirement is still missing.",
            "The program stops here instead of using a wrong fertilizer recommendation.",
            "",
        ]

        for name, req, app, rem in zip(NUTRIENTS, requirements, apport, remaining):
            if rem > tolerance:
                lines.append(
                    f"{name}: required = {req:.2f}, supplied = {app:.2f}, missing = {rem:.2f}"
                )

        raise RuntimeError("\n".join(lines))

    return True


def objective(doses, requirements):
    """
    Kept for compatibility with the bigger code.

    The real optimizer is linprog inside optimize_fertilizers().
    """

    requirements = effective_requirements(requirements)

    doses = np.array(doses, dtype=float)
    apport = nutrient_apport(doses)

    remaining = requirements - apport
    missing = np.maximum(remaining, 0.0)
    excess = np.maximum(apport - requirements, 0.0)

    error = 0.0

    error += 10000.0 * np.sum(missing ** 2)
    error += np.sum(EXCESS_WEIGHTS * excess)
    error += np.sum(FERTILIZER_WEIGHTS * doses)

    return error


def make_constraints(requirements):
    """
    Kept for compatibility with the bigger code.

    linprog constraints are built directly inside solve_linear_program().
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

    Hard rule:

        supplied_i >= required_i

    Soft rule:

        excess_i is minimized, but not forbidden.
    """

    requirements = effective_requirements(requirements)
    formula = formula_as_fraction()

    n_fertilizers = len(FERTILIZER_NAMES)
    n_nutrients = len(NUTRIENTS)
    n_variables = n_fertilizers + n_nutrients

    c = np.zeros(n_variables, dtype=float)

    # Fertilizer preference cost
    c[:n_fertilizers] = FERTILIZER_WEIGHTS

    # Excess nutrient penalty
    c[n_fertilizers:] = EXCESS_WEIGHTS

    A_ub = []
    b_ub = []

    print("\nDEBUG: FORMULA information")
    print(f"  FORMULA shape: {np.array(FORMULA).shape}")
    print(f"  NUTRIENTS: {list(NUTRIENTS)}")
    print(f"  FERTILIZER_NAMES: {list(FERTILIZER_NAMES)}")
    print("  FORMULA as fraction:")
    print(formula)

    print("\nDEBUG: hard nutrient constraints")

    for i, req in enumerate(requirements):
        nutrient_vector = formula[:, i]

        if req > 0:
            # supplied_i >= required_i
            #
            # linprog uses:
            #     A_ub @ x <= b_ub
            #
            # Therefore:
            #     -supplied_i <= -required_i

            row = np.zeros(n_variables, dtype=float)
            row[:n_fertilizers] = -nutrient_vector

            A_ub.append(row)
            b_ub.append(-req)

            print(f"  {NUTRIENTS[i]} must be >= {req:.2f}")
            print(f"    coefficients = {nutrient_vector}")

        # Excess variable:
        #
        # excess_i >= supplied_i - required_i
        #
        # equivalent:
        #
        # supplied_i - excess_i <= required_i

        row = np.zeros(n_variables, dtype=float)
        row[:n_fertilizers] = nutrient_vector
        row[n_fertilizers + i] = -1.0

        A_ub.append(row)
        b_ub.append(req)

    A_ub = np.array(A_ub, dtype=float)
    b_ub = np.array(b_ub, dtype=float)

    bounds = []

    bounds.append((ESTIERCOL_MIN, ESTIERCOL_MAX))                # Estiércol
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Urea
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Fosfato Diamónico
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Cloruro de Potasio
    bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))  # Sulfato K-Mg

    for _ in range(n_nutrients):
        bounds.append((0.0, None))  # excess variables

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

        # Keep compatibility:
        # result.x contains only the 5 fertilizer doses.
        result.full_x = full_x
        result.x = doses
        result.excess_variables = excess_variables

    return result


def optimize_fertilizers(requirements):
    """
    Optimize fertilizer doses using linear programming.

    This version guarantees that every positive requirement is covered.

    If the optimizer gives an invalid result, it raises RuntimeError.
    """

    requirements = effective_requirements(requirements)

    result = solve_linear_program(requirements)

    if not result.success:
        raise RuntimeError(
            "\nLinear optimization failed.\n"
            f"{result.message}\n\n"
            "Possible reasons:\n"
            "  1. Requirements are too high for the fertilizer limits.\n"
            "  2. OTHER_FERTILIZER_MAX is too low.\n"
            "  3. FORMULA columns are not ordered as [N, P2O5, K2O, CaO, MgO, S].\n"
            "  4. FORMULA matrix is missing one nutrient column.\n\n"
            "Things to try:\n"
            "  - Increase OTHER_FERTILIZER_MAX.\n"
            "  - Check FORMULA shape. It must be (5, 6).\n"
            "  - Check that P2O5 is the second column in FORMULA.\n"
        )

    validate_solution(requirements, result.x)

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

    validate_solution(requirements, doses)

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

# optimizer.py

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from config import (
    NUTRIENTS,
    FERTILIZER_NAMES,
    CURRENT_DOSES,
    FORMULA,
)


# ------------------------------------------------------------
# Allowed excess above the required nutrient amount
#
# If requirement = 100 kg/ha, then fertilizer apport can be
# between 100 and 120 kg/ha.
# ------------------------------------------------------------
EXCESS_TOLERANCE = 20.0


# ------------------------------------------------------------
# Fertilizer preference weights
#
# Optimization array order:
# 0 = Estiércol de Vacuno
# 1 = Urea
# 2 = Fosfato Diamónico
# 3 = Cloruro de Potasio
# 4 = Sulfato de Potasio y Magnesio
#
# Smaller weight means the optimizer prefers that fertilizer.
# Larger weight means the optimizer avoids that fertilizer unless needed.
# ------------------------------------------------------------
FERTILIZER_WEIGHTS = np.array([
    0.01,  # Estiércol de Vacuno: strongly preferred
    2.00,  # Urea
    2.00,  # Fosfato Diamónico
    3.00,  # Cloruro de Potasio
    3.00,  # Sulfato de Potasio y Magnesio
])


# ------------------------------------------------------------
# Organic preference
#
# We want to recommend organic fertilizer first.
# Therefore:
#
#   Estiércol de Vacuno must be at least 4000 kg/ha
#   Estiércol de Vacuno can go up to 5000 kg/ha
#
# The optimizer will then complete what is missing using
# Urea and/or Fosfato Diamónico, mainly for N and P.
# ------------------------------------------------------------
ESTIERCOL_MIN = 4000.0
ESTIERCOL_MAX = 5000.0


def effective_requirements(requirements):
    """
    Convert negative requirements to zero.

    This assumes that requirements already represents the missing amount:

        requirement = requerimiento_del_cultivo - SUMA_de_nutrientes

    Therefore:

        requirement > 0 means the nutrient is missing
        requirement = 0 means nothing is missing
        requirement < 0 means there is already excess

    Negative values are ignored.
    """

    requirements = np.array(requirements, dtype=float)

    return np.where(
        requirements > 0,
        requirements,
        0.0,
    )


def nutrient_apport(doses):
    return doses @ FORMULA


def final_remaining(doses, requirements):
    requirements = effective_requirements(requirements)

    return requirements - nutrient_apport(doses)


def objective(doses, requirements):
    requirements = effective_requirements(requirements)

    apport = nutrient_apport(doses)

    error = 0.0

    for i, req in enumerate(requirements):

        if req > 0:
            excess = apport[i] - req

            # We want apport >= requirement.
            # Constraints will force this.
            #
            # But we also prefer apport close to requirement,
            # allowing up to EXCESS_TOLERANCE.
            if excess > EXCESS_TOLERANCE:
                error += 100.0 * (
                    (excess - EXCESS_TOLERANCE) / max(req, 1.0)
                ) ** 2

            # Small penalty for any excess, even inside the tolerance,
            # so the optimizer does not add unnecessary fertilizer.
            if excess > 0:
                error += 0.01 * (
                    excess / max(req, 1.0)
                ) ** 2

        else:
            # This nutrient is not required.
            # Penalize adding nutrients that were not needed.
            error += 10.0 * apport[i] ** 2

    # ------------------------------------------------------------
    # Fertilizer dose penalty with preference weights.
    #
    # Estiércol de Vacuno has a very small weight, so it is preferred.
    # Chemical fertilizers have larger weights, so they are used only
    # when needed.
    # ------------------------------------------------------------
    error += 0.0001 * np.sum(FERTILIZER_WEIGHTS * doses ** 2)

    # ------------------------------------------------------------
    # Prefer estiércol close to 5000, because the recommendation is
    # to go more organic.
    #
    # This does not force exactly 5000. It only encourages it.
    # Bounds and nutrient constraints still control the final answer.
    # ------------------------------------------------------------
    estiercol = doses[0]
    error += 0.00001 * (ESTIERCOL_MAX - estiercol) ** 2

    return error


def make_constraints(requirements):
    requirements = effective_requirements(requirements)

    constraints = []

    for i, req in enumerate(requirements):

        if req > 0:

            # ----------------------------------------------------
            # Lower constraint:
            #
            #   apport >= requirement
            #
            # scipy format:
            #
            #   apport - requirement >= 0
            # ----------------------------------------------------
            def lower_constraint_fun(doses, nutrient_index=i, target=req):
                apport = nutrient_apport(doses)
                return apport[nutrient_index] - target

            constraints.append({
                "type": "ineq",
                "fun": lower_constraint_fun,
            })

            # ----------------------------------------------------
            # Upper constraint:
            #
            #   apport <= requirement + EXCESS_TOLERANCE
            #
            # scipy format:
            #
            #   requirement + tolerance - apport >= 0
            # ----------------------------------------------------
            def upper_constraint_fun(doses, nutrient_index=i, target=req):
                apport = nutrient_apport(doses)
                return target + EXCESS_TOLERANCE - apport[nutrient_index]

            constraints.append({
                "type": "ineq",
                "fun": upper_constraint_fun,
            })

    return constraints


def optimize_fertilizers(requirements):
    requirements = effective_requirements(requirements)

    bounds = [
        (ESTIERCOL_MIN, ESTIERCOL_MAX),  # Estiércol de Vacuno
        (0, 1000),                      # Urea
        (0, 1000),                      # Fosfato Diamónico
        (0, 1000),                      # Cloruro de Potasio
        (0, 1000),                      # Sulfato de Potasio y Magnesio
    ]

    # Make sure the initial guess is inside the new bounds.
    x0 = np.array(CURRENT_DOSES, dtype=float)
    x0[0] = np.clip(x0[0], ESTIERCOL_MIN, ESTIERCOL_MAX)

    result = minimize(
        objective,
        x0,
        args=(requirements,),
        method="SLSQP",
        bounds=bounds,
        constraints=make_constraints(requirements),
        options={
            "maxiter": 3000,
            "ftol": 1e-12,
            "disp": False,
        },
    )

    # ------------------------------------------------------------
    # If the strict 20 kg/ha excess limit makes the problem impossible,
    # SLSQP may fail.
    #
    # We keep the same return behavior, but print a warning.
    # This can happen because fertilizers add several nutrients together.
    # Example: Fosfato Diamónico adds both N and P2O5.
    # ------------------------------------------------------------
    if not result.success:
        print("\nWARNING: Optimization failed with strict constraints.")
        print(result.message)
        print("Possible reason:")
        print("  The nutrient requirements cannot be satisfied while keeping")
        print(f"  every required nutrient within +{EXCESS_TOLERANCE:.1f} kg/ha.")
        print("  This can happen because each fertilizer contributes multiple nutrients.")

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

    doses = result.x
    apport = nutrient_apport(doses)
    remaining = final_remaining(doses, requirements)

    print("\n[2] Optimization results")

    if not result.success:
        print("WARNING: Optimization did not fully converge.")
        print(result.message)

    print("\nInput requirements:")
    print("Only positive requirements are optimized.")
    print("Negative requirements are assumed as zero.")
    print(f"Required rule: suma de nutrientes >= requirement")
    print(f"Allowed excess tolerance: {EXCESS_TOLERANCE:.1f} kg/ha")
    print(
        f"Estiércol de Vacuno constrained between "
        f"{ESTIERCOL_MIN:.1f} and {ESTIERCOL_MAX:.1f} kg/ha"
    )

    for name, original, effective in zip(
        NUTRIENTS,
        original_requirements,
        requirements,
    ):

        if original <= 0:
            status = "IGNORED"
        else:
            status = "OPTIMIZED"

        print(
            f"  {name:5s}: "
            f"original = {original:10.2f}   "
            f"effective = {effective:10.2f}   "
            f"{status}"
        )

    print("\nOptimized fertilizer doses:")
    print("Estiércol de Vacuno is prioritized and constrained to 4000-5000 kg/ha.")

    for name, old, new in zip(FERTILIZER_NAMES, CURRENT_DOSES, doses):

        print(
            f"  {name:30s}: "
            f"{new:10.1f} kg/ha   "
            f"{new / 50:8.1f} sacos/ha   "
            f"change = {new - old:10.1f}"
        )

    print("\nNutrient balance:")
    print("remaining = requirement - fertilizer_apport")
    print("remaining <= 0 means the requirement is covered")
    print(f"excess up to {EXCESS_TOLERANCE:.1f} kg/ha is acceptable")

    all_requirements_covered = True
    all_excess_inside_limit = True

    for name, req, app, rem in zip(NUTRIENTS, requirements, apport, remaining):

        excess = app - req

        if req <= 0:
            status = "IGNORED"

        elif rem > 1e-6:
            status = "MISSING"
            all_requirements_covered = False

        elif excess <= EXCESS_TOLERANCE + 1e-6:
            status = "OK"

        else:
            status = "OK, HIGH EXCESS"
            all_excess_inside_limit = False

        print(
            f"  {name:5s}: "
            f"requirement = {req:10.2f}   "
            f"apport = {app:10.2f}   "
            f"remaining = {rem:10.2f}   "
            f"excess = {excess:10.2f}   "
            f"{status}"
        )

    print("\nFinal check:")

    if all_requirements_covered:
        print("  OK: all positive requirements are covered.")
    else:
        print("  WARNING: some requirements are still missing.")

    if all_excess_inside_limit:
        print(f"  OK: all required nutrients are within +{EXCESS_TOLERANCE:.1f} kg/ha.")
    else:
        print(f"  WARNING: at least one nutrient exceeds +{EXCESS_TOLERANCE:.1f} kg/ha.")

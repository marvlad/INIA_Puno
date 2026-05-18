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
# Example:
# If N requirement = 100 kg/ha,
# then N apport can be between 100 and 140 kg/ha.
#
# The condition is applied individually to:
# N, P2O5, K2O, CaO, MgO, S
# ------------------------------------------------------------
EXCESS_TOLERANCE = 40.0


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
    0.01,  # Estiércol de Vacuno: preferred
    2.00,  # Urea
    2.00,  # Fosfato Diamónico
    3.00,  # Cloruro de Potasio
    3.00,  # Sulfato de Potasio y Magnesio
])


# ------------------------------------------------------------
# Organic recommendation rule
#
# We want to recommend organic fertilizer first.
# Therefore:
#
# Estiércol de Vacuno must be at least 4000 kg/ha.
# It can increase up to 5000 kg/ha.
# ------------------------------------------------------------
ESTIERCOL_MIN = 4000.0
ESTIERCOL_MAX = 5000.0


def effective_requirements(requirements):
    """
    Keep this function for compatibility with the bigger code.

    In this version, we do NOT convert negative values to zero here,
    because the optimization rule is checked nutrient by nutrient.

    However, negative requirements usually mean that the nutrient is
    already in excess. In the constraints, negative requirements will
    only receive the lower condition:

        apport_i >= requirement_i

    The upper tolerance will only be applied to positive requirements.
    """

    return np.array(requirements, dtype=float)


def nutrient_apport(doses):
    return doses @ FORMULA


def final_remaining(doses, requirements):
    requirements = effective_requirements(requirements)

    return requirements - nutrient_apport(doses)


def objective(doses, requirements):
    requirements = effective_requirements(requirements)

    apport = nutrient_apport(doses)
    remaining = requirements - apport

    error = 0.0

    for i, req in enumerate(requirements):

        excess = apport[i] - req

        if req > 0:
            # ----------------------------------------------------
            # Positive requirement:
            #
            # We want:
            #
            #   requirement <= apport <= requirement + tolerance
            #
            # Constraints enforce this strictly.
            # The objective only helps choose the best solution.
            # ----------------------------------------------------

            if remaining[i] > 0:
                # Missing nutrient.
                # This should normally be prevented by constraints,
                # but the penalty helps the optimizer.
                error += 1000.0 * (
                    remaining[i] / max(req, 1.0)
                ) ** 2

            if excess > EXCESS_TOLERANCE:
                # Too much excess.
                # This should normally be prevented by constraints,
                # but the penalty helps the optimizer.
                error += 1000.0 * (
                    (excess - EXCESS_TOLERANCE) / max(req, 1.0)
                ) ** 2

            elif excess > 0:
                # Small penalty for excess even inside the tolerance.
                # This avoids adding unnecessary fertilizer.
                error += 0.01 * (
                    excess / max(req, 1.0)
                ) ** 2

        else:
            # ----------------------------------------------------
            # Negative or zero requirement:
            #
            # This usually means the nutrient is already in excess.
            # We do not apply the upper tolerance because it can make
            # the problem impossible.
            #
            # But we still penalize adding unnecessary nutrient.
            # ----------------------------------------------------
            error += 10.0 * apport[i] ** 2

    # ------------------------------------------------------------
    # Fertilizer dose penalty with preference weights.
    #
    # Estiércol de Vacuno has a small weight, so the optimizer is
    # more willing to use it.
    #
    # Chemical fertilizers have larger weights, so the optimizer
    # uses them only when useful or necessary.
    # ------------------------------------------------------------
    error += 0.0001 * np.sum(FERTILIZER_WEIGHTS * doses ** 2)

    # ------------------------------------------------------------
    # Organic preference:
    #
    # Encourage Estiércol de Vacuno closer to 5000 kg/ha.
    # This does not force exactly 5000, because bounds and nutrient
    # constraints still control the final result.
    # ------------------------------------------------------------
    estiercol = doses[0]
    error += 0.00001 * (ESTIERCOL_MAX - estiercol) ** 2

    return error


def make_constraints(requirements):
    requirements = effective_requirements(requirements)

    constraints = []

    for i, req in enumerate(requirements):

        # --------------------------------------------------------
        # Lower constraint for each nutrient individually:
        #
        #   apport_i >= requirement_i
        #
        # In scipy SLSQP format:
        #
        #   apport_i - requirement_i >= 0
        #
        # This is applied to:
        # N, P2O5, K2O, CaO, MgO, S
        # --------------------------------------------------------
        def lower_constraint_fun(doses, nutrient_index=i, target=req):
            apport = nutrient_apport(doses)
            return apport[nutrient_index] - target

        constraints.append({
            "type": "ineq",
            "fun": lower_constraint_fun,
        })

        # --------------------------------------------------------
        # Upper constraint:
        #
        #   apport_i <= requirement_i + EXCESS_TOLERANCE
        #
        # This allows a controlled excess.
        #
        # Important:
        # Only apply this when requirement is positive.
        #
        # If requirement is negative, for example:
        #
        #   K2O requirement = -2650
        #
        # then this upper condition would become:
        #
        #   K2O apport <= -2650 + 40
        #
        # which is impossible because fertilizer apport is positive.
        # --------------------------------------------------------
        if req > 0:

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

    # Make sure the initial point is inside the bounds.
    x0 = np.array(CURRENT_DOSES, dtype=float)

    x0[0] = np.clip(x0[0], ESTIERCOL_MIN, ESTIERCOL_MAX)
    x0[1] = np.clip(x0[1], bounds[1][0], bounds[1][1])
    x0[2] = np.clip(x0[2], bounds[2][0], bounds[2][1])
    x0[3] = np.clip(x0[3], bounds[3][0], bounds[3][1])
    x0[4] = np.clip(x0[4], bounds[4][0], bounds[4][1])

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
    # If the strict tolerance makes the problem impossible, try
    # again with larger tolerances.
    #
    # This is useful because fertilizer formulas are coupled:
    # for example, Fosfato Diamónico adds both N and P2O5.
    #
    # We keep the same function argument, so the bigger code
    # does not need to change.
    # ------------------------------------------------------------
    if not result.success:
        print("\nWARNING: Optimization failed with initial tolerance.")
        print(result.message)
        print(f"Initial tolerance was: {EXCESS_TOLERANCE:.1f} kg/ha")
        print("Trying again with relaxed tolerances...")

        original_tolerance = EXCESS_TOLERANCE

        for new_tolerance in [60.0, 80.0, 100.0, 150.0, 200.0]:
            set_excess_tolerance(new_tolerance)

            result_retry = minimize(
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

            if result_retry.success:
                print(f"Optimization succeeded with tolerance = {new_tolerance:.1f} kg/ha")
                return result_retry

        set_excess_tolerance(original_tolerance)

        print("\nWARNING: Optimization still failed after relaxed tolerances.")
        print("Possible reason:")
        print("  The nutrient requirements cannot be satisfied with the available fertilizers")
        print("  and the current dose bounds.")
        print("  You may need to increase bounds or allow more excess.")

    return result


def set_excess_tolerance(value):
    """
    Internal helper.

    This changes the global tolerance when retrying the optimization.
    It does not change the function arguments, so the bigger code
    remains compatible.
    """

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

    print("\n[2] Optimization results")

    if not result.success:
        print("WARNING: Optimization did not fully converge.")
        print(result.message)

    print("\nInput requirements:")
    print("Each nutrient is checked individually.")
    print("The rule is:")
    print("  requirement_i <= suma_de_nutrientes_i")
    print("For positive requirements, excess is limited by the tolerance.")
    print(f"Current allowed excess tolerance: {EXCESS_TOLERANCE:.1f} kg/ha")
    print(
        f"Estiércol de Vacuno constrained between "
        f"{ESTIERCOL_MIN:.1f} and {ESTIERCOL_MAX:.1f} kg/ha"
    )

    for name, original, effective in zip(
        NUTRIENTS,
        original_requirements,
        requirements,
    ):

        if original > 0:
            status = "OPTIMIZED WITH LOWER AND UPPER LIMIT"
        else:
            status = "LOWER LIMIT ONLY"

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
    print(f"excess up to {EXCESS_TOLERANCE:.1f} kg/ha is acceptable for positive requirements")

    all_requirements_covered = True
    all_positive_excess_inside_limit = True

    for name, req, app, rem in zip(NUTRIENTS, requirements, apport, remaining):

        excess = app - req

        if rem > 1e-6:
            status = "MISSING"
            all_requirements_covered = False

        elif req > 0 and excess <= EXCESS_TOLERANCE + 1e-6:
            status = "OK"

        elif req > 0 and excess > EXCESS_TOLERANCE + 1e-6:
            status = "OK, HIGH EXCESS"
            all_positive_excess_inside_limit = False

        else:
            status = "OK"

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
        print("  OK: all individual nutrient requirements are covered.")
    else:
        print("  WARNING: at least one individual nutrient requirement is missing.")

    if all_positive_excess_inside_limit:
        print(f"  OK: all positive requirements are within +{EXCESS_TOLERANCE:.1f} kg/ha.")
    else:
        print(f"  WARNING: at least one positive nutrient exceeds +{EXCESS_TOLERANCE:.1f} kg/ha.")

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


# Allowed excess above the required nutrient amount
# Example: if requirement is 100, then apport up to 115 is OK
EXCESS_TOLERANCE = 15.0


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
FERTILIZER_WEIGHTS = np.array([
    0.05,  # Estiércol de Vacuno: preferred
    2.00,  # Urea
    2.00,  # Fosfato Diamónico
    2.00,  # Cloruro de Potasio
    2.00,  # Sulfato de Potasio y Magnesio
])


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
    remaining = requirements - apport

    error = 0.0

    for i, req in enumerate(requirements):
        if req > 0:
            # This nutrient is required.
            # The constraint will force apport >= req.
            # Here we only penalize excess above the tolerance.
            excess = -remaining[i]
            # same as: excess = apport[i] - req

            if excess > EXCESS_TOLERANCE:
                error += 10.0 * (
                    (excess - EXCESS_TOLERANCE) / max(req, 1.0)
                ) ** 2

        else:
            # This nutrient is not required.
            # Penalize adding nutrients that were not needed.
            error += 5.0 * apport[i] ** 2

    # Dose penalty with fertilizer preference.
    #
    # Estiércol de Vacuno has a small weight, so the optimizer
    # is more willing to use it.
    #
    # Chemical fertilizers have larger weights, so the optimizer
    # uses them only when they are useful/necessary.
    error += 0.0001 * np.sum(FERTILIZER_WEIGHTS * doses ** 2)

    return error


def make_constraints(requirements):
    requirements = effective_requirements(requirements)

    constraints = []

    for i, req in enumerate(requirements):
        if req > 0:
            def constraint_fun(doses, nutrient_index=i, target=req):
                apport = nutrient_apport(doses)
                return apport[nutrient_index] - target

            constraints.append({
                "type": "ineq",
                "fun": constraint_fun,
                })

    return constraints


def optimize_fertilizers(requirements):
    requirements = effective_requirements(requirements)

    # Modified bounds to treat Estiércol de Vacuno as a fixed minimum base (4000)
    # up to an organic recommendation ceiling (5000). 
    # Remaining chemical choices are left for Urea and Fosfato Diamónico to close gaps.
    bounds = [
        (4000, 5000),  # Estiércol de Vacuno (Fixed base to 4000, can step up to 5000)
        (0, 1000),     # Urea
        (0, 1000),     # Fosfato Diamónico
        (0, 1000),     # Cloruro de Potasio
        (0, 1000),     # Sulfato de Potasio y Magnesio
    ]

    result = minimize(
        objective,
        CURRENT_DOSES,
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
    print(f"Allowed excess tolerance: {EXCESS_TOLERANCE:.1f} kg/ha")

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
    print("Estiércol de Vacuno is prioritized with a smaller penalty weight.")

    for name, old, new in zip(FERTILIZER_NAMES, CURRENT_DOSES, doses):
        print(
            f"  {name:30s}: "
            f"{new:10.1f} kg/ha   "
            f"{new / 50:8.1f} sacos/ha   "
            f"change = {new - old:10.1f}"
        )

    print("\nNutrient balance:")
    print("remaining = requirement - fertilizer_apport")
    print("remaining <= 0 means OK")
    print(f"excess up to {EXCESS_TOLERANCE:.1f} kg/ha is acceptable")

    for name, req, app, rem in zip(NUTRIENTS, requirements, apport, remaining):
        excess = app - req

        if req <= 0:
            status = "IGNORED"
        elif rem > 1e-6:
            status = "MISSING"
        elif excess <= EXCESS_TOLERANCE:
            status = "OK"
        else:
            status = "OK, HIGH EXCESS"

        print(
            f"  {name:5s}: "
            f"requirement = {req:10.2f}   "
            f"apport = {app:10.2f}   "
            f"remaining = {rem:10.2f}   "
            f"excess = {excess:10.2f}   "
            f"{status}"
        )

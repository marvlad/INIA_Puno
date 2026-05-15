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


def nutrient_apport(doses):
    return doses @ FORMULA


def effective_requirements(requirements):
    """
    Keep only positive requirements.

    This assumes that requirements already represents:

        requerimiento_del_cultivo - SUMA_de_nutrientes

    Therefore:

        requirements > 0  means nutrient is missing
        requirements = 0  means nutrient is balanced
        requirements < 0  means SUMA already surpasses the requirement
                          or crop requirement is negative

    Negative values are ignored by converting them to zero.
    """

    requirements = np.array(requirements, dtype=float)

    return np.where(
        requirements > 0,
        requirements,
        0.0,
    )


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
            excess = -remaining[i]

            if excess > 0:
                error += 10.0 * (excess / max(req, 1.0)) ** 2

        else:
            error += 5.0 * apport[i] ** 2

    error += 0.0001 * np.sum(doses ** 2)

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

    bounds = [
        (0, 6000),
        (0, 1000),
        (0, 1000),
        (0, 1000),
        (0, 1000),
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

    for name, old, new in zip(FERTILIZER_NAMES, CURRENT_DOSES, doses):
        print(
            f"  {name:18s}: "
            f"{new:10.1f} kg/ha   "
            f"{new / 50:8.1f} sacos/ha   "
            f"change = {new - old:10.1f}"
        )

    print("\nNutrient balance:")
    print("remaining = effective_requirement - fertilizer_apport")
    print("remaining <= 0 means OK")
    print("remaining > 0 means still missing")

    for name, req, app, rem in zip(NUTRIENTS, requirements, apport, remaining):
        status = "OK" if rem <= 1e-6 else "MISSING"

        print(
            f"  {name:5s}: "
            f"requirement = {req:10.2f}   "
            f"apport = {app:10.2f}   "
            f"remaining = {rem:10.2f}   "
            f"{status}"
        )

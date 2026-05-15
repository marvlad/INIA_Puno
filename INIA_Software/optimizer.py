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


def convert_difference_to_requirements(difference):
    """
    difference = SUMA_de_nutrientes - requerimiento_del_cultivo

    If difference is positive:
        There is already enough nutrient, so the optimizer should ignore it.

    If difference is negative:
        That nutrient is missing, so the optimizer should add fertilizer
        until the missing amount is covered.

    Example:
        difference = [10, -20, 5, -30]
        requirements = [0, 20, 0, 30]
    """

    difference = np.array(difference, dtype=float)

    requirements = np.where(
        difference < 0,
        -difference,
        0.0,
    )

    return requirements


def final_remaining(doses, requirements):
    return requirements - nutrient_apport(doses)


def objective(doses, requirements):
    apport = nutrient_apport(doses)
    remaining = requirements - apport

    error = 0.0

    for i, req in enumerate(requirements):
        if req > 0:
            # Nutrient is needed.
            # Penalize excess, but constraints will force at least the target.
            excess = -remaining[i]
            if excess > 0:
                error += 10.0 * (excess / max(req, 1.0)) ** 2
        else:
            # Nutrient is not needed.
            # Do not optimize this nutrient.
            # But still lightly penalize adding unnecessary nutrients.
            error += 5.0 * apport[i] ** 2

    # Small penalty to avoid unnecessarily large fertilizer doses
    error += 0.0001 * np.sum(doses ** 2)

    return error


def make_constraints(requirements):
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


def optimize_fertilizers(difference):
    """
    Input:
        difference = SUMA_de_nutrientes - requerimiento_del_cultivo

    Positive values are assumed as zero.
    Negative values are converted into fertilizer requirements.
    """

    requirements = convert_difference_to_requirements(difference)

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

    result.effective_requirements = requirements
    result.original_difference = np.array(difference, dtype=float)

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


def print_optimization_results(difference, result):
    requirements = result.effective_requirements

    doses = result.x
    apport = nutrient_apport(doses)
    remaining = final_remaining(doses, requirements)

    print("\n[2] Optimization results")

    if not result.success:
        print("WARNING: Optimization did not fully converge.")
        print(result.message)

    print("\nOriginal difference:")
    print("difference = SUMA_de_nutrientes - requerimiento_del_cultivo")
    print("positive difference is assumed as zero")

    for name, value in zip(NUTRIENTS, difference):
        effective = max(-value, 0.0)

        print(
            f"  {name:5s}: "
            f"difference = {value:10.2f}   "
            f"effective requirement = {effective:10.2f}"
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
            f"effective requirement = {req:10.2f}   "
            f"apport = {app:10.2f}   "
            f"remaining = {rem:10.2f}   "
            f"{status}"
        )

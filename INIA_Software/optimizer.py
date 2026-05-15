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
    """
    Calculate nutrient contribution from fertilizer doses.

    doses:
        Vector of fertilizer doses in kg/ha.

    FORMULA:
        Matrix with fertilizer composition.

    Returns:
        Nutrient apport vector.
    """

    return doses @ FORMULA


def convert_to_effective_requirements(suma_nutrientes, requerimiento_cultivo):
    """
    Convert the original nutrient balance into optimizer targets.

    Rules:

    1. If requerimiento_cultivo <= 0:
       Ignore this nutrient.
       effective requirement = 0

    2. If suma_nutrientes >= requerimiento_cultivo:
       The nutrient requirement is already covered.
       effective requirement = 0

    3. If suma_nutrientes < requerimiento_cultivo:
       The missing amount is:
       requerimiento_cultivo - suma_nutrientes

    In other words, the optimizer only sees the missing nutrients.
    """

    suma_nutrientes = np.array(suma_nutrientes, dtype=float)
    requerimiento_cultivo = np.array(requerimiento_cultivo, dtype=float)

    if suma_nutrientes.shape != requerimiento_cultivo.shape:
        raise ValueError(
            "suma_nutrientes and requerimiento_cultivo must have the same shape. "
            f"Got {suma_nutrientes.shape} and {requerimiento_cultivo.shape}."
        )

    effective_requirements = np.where(
        (requerimiento_cultivo > 0)
        & (suma_nutrientes < requerimiento_cultivo),
        requerimiento_cultivo - suma_nutrientes,
        0.0,
    )

    return effective_requirements


def final_remaining(doses, effective_requirements):
    """
    remaining = effective_requirement - fertilizer_apport

    remaining <= 0 means OK.
    remaining > 0 means still missing.
    """

    return effective_requirements - nutrient_apport(doses)


def objective(doses, effective_requirements):
    """
    Objective function minimized by scipy.

    It tries to:
    1. Cover nutrients that are missing.
    2. Avoid unnecessary excess.
    3. Avoid very large fertilizer doses.
    """

    apport = nutrient_apport(doses)
    remaining = effective_requirements - apport

    error = 0.0

    for i, req in enumerate(effective_requirements):
        if req > 0:
            # This nutrient is missing and must be covered.
            # Constraints force apport >= req.
            # Here we penalize excess.
            excess = -remaining[i]

            if excess > 0:
                error += 10.0 * (excess / max(req, 1.0)) ** 2

        else:
            # This nutrient is ignored because:
            # - crop requirement was <= 0, or
            # - suma already surpassed the crop requirement.
            #
            # We do not force this nutrient.
            # But we lightly penalize adding unnecessary amounts.
            error += 5.0 * apport[i] ** 2

    # Small penalty to avoid unnecessarily large fertilizer doses.
    error += 0.0001 * np.sum(doses ** 2)

    return error


def make_constraints(effective_requirements):
    """
    Create constraints only for nutrients that are actually missing.

    For each nutrient where effective_requirement > 0:

        fertilizer_apport >= effective_requirement
    """

    constraints = []

    for i, req in enumerate(effective_requirements):
        if req > 0:

            def constraint_fun(doses, nutrient_index=i, target=req):
                apport = nutrient_apport(doses)
                return apport[nutrient_index] - target

            constraints.append(
                {
                    "type": "ineq",
                    "fun": constraint_fun,
                }
            )

    return constraints


def optimize_fertilizers(suma_nutrientes, requerimiento_cultivo):
    """
    Optimize fertilizer doses.

    Inputs:
        suma_nutrientes:
            Current nutrient sum available before adding fertilizer.

        requerimiento_cultivo:
            Crop nutrient requirement.

    The optimizer does not use requerimiento_cultivo directly.
    It first converts it into effective requirements:

        effective_requirements =
            requerimiento_cultivo - suma_nutrientes

    but only when:

        requerimiento_cultivo > 0
        and
        suma_nutrientes < requerimiento_cultivo

    Otherwise the effective requirement is zero.
    """

    effective_requirements = convert_to_effective_requirements(
        suma_nutrientes,
        requerimiento_cultivo,
    )

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
        args=(effective_requirements,),
        method="SLSQP",
        bounds=bounds,
        constraints=make_constraints(effective_requirements),
        options={
            "maxiter": 3000,
            "ftol": 1e-12,
            "disp": False,
        },
    )

    # Store extra useful information inside result
    result.suma_nutrientes = np.array(suma_nutrientes, dtype=float)
    result.requerimiento_cultivo = np.array(requerimiento_cultivo, dtype=float)
    result.effective_requirements = effective_requirements

    return result


def save_optimal_values_csv(output_csv, result):
    """
    Save optimized fertilizer doses into a CSV file.

    The output is one row with one column per fertilizer.
    """

    doses = np.round(result.x, 1)

    df = pd.DataFrame(
        [doses],
        columns=FERTILIZER_NAMES,
    )

    df.to_csv(output_csv, index=False)

    print(f"Saved optimal values CSV: {output_csv}")

    return doses


def print_optimization_results(result):
    """
    Print optimization summary.
    """

    suma_nutrientes = result.suma_nutrientes
    requerimiento_cultivo = result.requerimiento_cultivo
    effective_requirements = result.effective_requirements

    doses = result.x
    apport = nutrient_apport(doses)
    remaining = final_remaining(doses, effective_requirements)

    print("\n[2] Optimization results")

    if not result.success:
        print("WARNING: Optimization did not fully converge.")
        print(result.message)

    print("\nOriginal nutrient balance before fertilizer optimization:")
    print("Only nutrients with positive crop requirement and deficit are optimized.")

    for name, suma, req, eff in zip(
        NUTRIENTS,
        suma_nutrientes,
        requerimiento_cultivo,
        effective_requirements,
    ):
        if req <= 0:
            reason = "IGNORED: crop requirement <= 0"
        elif suma >= req:
            reason = "IGNORED: already covered"
        else:
            reason = "OPTIMIZED: missing nutrient"

        print(
            f"  {name:5s}: "
            f"suma = {suma:10.2f}   "
            f"requirement = {req:10.2f}   "
            f"effective requirement = {eff:10.2f}   "
            f"{reason}"
        )

    print("\nOptimized fertilizer doses:")

    for name, old, new in zip(FERTILIZER_NAMES, CURRENT_DOSES, doses):
        print(
            f"  {name:18s}: "
            f"{new:10.1f} kg/ha   "
            f"{new / 50:8.1f} sacos/ha   "
            f"change = {new - old:10.1f}"
        )

    print("\nNutrient balance after optimized fertilizer:")
    print("remaining = effective_requirement - fertilizer_apport")
    print("remaining <= 0 means OK")
    print("remaining > 0 means still missing")

    for name, req, app, rem in zip(
        NUTRIENTS,
        effective_requirements,
        apport,
        remaining,
    ):
        status = "OK" if rem <= 1e-6 else "MISSING"

        print(
            f"  {name:5s}: "
            f"effective requirement = {req:10.2f}   "
            f"fertilizer apport = {app:10.2f}   "
            f"remaining = {rem:10.2f}   "
            f"{status}"
        )

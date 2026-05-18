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
# Tolerance above the required nutrient amount
#
# Example:
# If the crop needs 100 kg/ha of N,
# the optimizer accepts N supplied between 100 and 150 kg/ha.
# ------------------------------------------------------------
EXCESS_TOLERANCE = 50.0


# ------------------------------------------------------------
# Organic fertilizer rule
#
# Estiércol de Vacuno is organic.
# We want to recommend it first.
#
# Therefore, it must start from 4000 kg/ha
# and can go up to 6000 kg/ha.
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
# Smaller weight = more preferred.
# Larger weight = less preferred.
# ------------------------------------------------------------
FERTILIZER_WEIGHTS = np.array([
    0.01,  # Estiércol de Vacuno, preferred
    1.00,  # Urea, useful for N
    1.00,  # Fosfato Diamónico, useful for P and N
    3.00,  # Cloruro de Potasio
    3.00,  # Sulfato de Potasio y Magnesio
])


def effective_requirements(requirements):
    """
    Keep requirements as they are.

    requirements must contain the nutrient needs in kg/ha:

        [N, P2O5, K2O, CaO, MgO, S]

    The optimizer will compare each nutrient individually with
    the nutrients supplied by the fertilizers.
    """

    return np.array(requirements, dtype=float)


def nutrient_apport(doses):
    """
    Calculate nutrient supply from fertilizer doses.

    doses has shape:

        [5]

    FORMULA has shape:

        [5, 6]

    Therefore:

        doses @ FORMULA

    gives:

        [N, P2O5, K2O, CaO, MgO, S]

    Important:
    FORMULA must be in percentage, so if FORMULA contains values like
    46 for Urea N, then we divide by 100 here.
    """

    return doses @ (FORMULA / 100.0)


def final_remaining(doses, requirements):
    requirements = effective_requirements(requirements)

    return requirements - nutrient_apport(doses)


def objective(doses, requirements):
    requirements = effective_requirements(requirements)

    apport = nutrient_apport(doses)
    remaining = requirements - apport

    error = 0.0

    for i, req in enumerate(requirements):
        app = apport[i]
        rem = remaining[i]
        excess = app - req

        # --------------------------------------------------------
        # Requirement not covered.
        #
        # This should be prevented by constraints, but the penalty
        # helps the optimizer move in the right direction.
        # --------------------------------------------------------
        if rem > 0:
            error += 10000.0 * (rem / max(abs(req), 1.0)) ** 2

        # --------------------------------------------------------
        # Too much excess above tolerance.
        #
        # This should also be prevented by constraints when possible.
        # --------------------------------------------------------
        if excess > EXCESS_TOLERANCE:
            error += 10000.0 * (
                (excess - EXCESS_TOLERANCE) / max(abs(req), 1.0)
            ) ** 2

        # --------------------------------------------------------
        # Small penalty for any excess, even inside tolerance.
        # This avoids adding fertilizer unnecessarily.
        # --------------------------------------------------------
        if excess > 0:
            error += 0.1 * (excess / max(abs(req), 1.0)) ** 2

    # ------------------------------------------------------------
    # Fertilizer-use penalty.
    #
    # Estiércol has a low penalty.
    # Chemical fertilizers have higher penalties.
    # ------------------------------------------------------------
    error += 0.00001 * np.sum(FERTILIZER_WEIGHTS * doses ** 2)

    # ------------------------------------------------------------
    # Encourage organic recommendation.
    #
    # This pushes Estiércol upward, but does not force it to be
    # exactly 6000.
    # ------------------------------------------------------------
    estiercol = doses[0]
    error += 0.000001 * (ESTIERCOL_MAX - estiercol) ** 2

    # ------------------------------------------------------------
    # Prefer using Urea and Fosfato Diamónico before K/Mg products
    # when possible.
    # ------------------------------------------------------------
    error += 0.00005 * doses[3] ** 2
    error += 0.00005 * doses[4] ** 2

    return error


def make_constraints(requirements):
    requirements = effective_requirements(requirements)

    constraints = []

    for i, req in enumerate(requirements):

        # --------------------------------------------------------
        # Lower constraint, nutrient by nutrient:
        #
        #   apport_i >= requirement_i
        #
        # Example:
        #
        #   N_apportado >= N_requerido
        #   P2O5_aportado >= P2O5_requerido
        #   K2O_aportado >= K2O_requerido
        #   CaO_aportado >= CaO_requerido
        #   MgO_aportado >= MgO_requerido
        #   S_aportado >= S_requerido
        #
        # scipy requires:
        #
        #   function(doses) >= 0
        #
        # so:
        #
        #   apport_i - requirement_i >= 0
        # --------------------------------------------------------
        def lower_constraint_fun(doses, nutrient_index=i, target=req):
            apport = nutrient_apport(doses)
            return apport[nutrient_index] - target

        constraints.append({
            "type": "ineq",
            "fun": lower_constraint_fun,
        })

        # --------------------------------------------------------
        # Upper constraint with tolerance:
        #
        #   apport_i <= requirement_i + EXCESS_TOLERANCE
        #
        # scipy form:
        #
        #   requirement_i + tolerance - apport_i >= 0
        # --------------------------------------------------------
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

    x0 = np.array(CURRENT_DOSES, dtype=float)

    # Make sure initial values are inside the allowed bounds.
    for i, (low, high) in enumerate(bounds):
        x0[i] = np.clip(x0[i], low, high)

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
    requirements = effective_requirements(requirements)

    doses = result.x
    apport = nutrient_apport(doses)
    remaining = final_remaining(doses, requirements)

    print("\n[2] Optimization results")

    if not result.success:
        print("WARNING: Optimization did not fully converge.")
        print(result.message)

    print("\nOptimized fertilizer doses:")

    for name, old, new in zip(FERTILIZER_NAMES, CURRENT_DOSES, doses):
        print(
            f"  {name:35s}: "
            f"{new:10.1f} kg/ha   "
            f"{new / 50:8.1f} sacos/ha   "
            f"change = {new - old:10.1f}"
        )

    print("\nNutrient balance:")
    print("Rule applied individually:")
    print("  required_i <= supplied_i <= required_i + tolerance")
    print(f"Tolerance: {EXCESS_TOLERANCE:.1f} kg/ha")

    all_ok = True

    for name, req, app, rem in zip(NUTRIENTS, requirements, apport, remaining):
        excess = app - req

        if rem > 1e-6:
            status = "MISSING"
            all_ok = False
        elif excess > EXCESS_TOLERANCE + 1e-6:
            status = "HIGH EXCESS"
            all_ok = False
        else:
            status = "OK"

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
        print("  OK: every nutrient requirement is covered individually.")
    else:
        print("  WARNING: at least one nutrient is missing or above tolerance.")

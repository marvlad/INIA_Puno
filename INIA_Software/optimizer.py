# optimizer.py

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from itertools import combinations

from config import (
    NUTRIENTS,
    CURRENT_DOSES,
)


# ------------------------------------------------------------
# Fertilizer dose bounds
# ------------------------------------------------------------
ESTIERCOL_MIN = 4000.0
ESTIERCOL_MAX = 6000.0

OTHER_FERTILIZER_MIN = 0.0
OTHER_FERTILIZER_MAX = 3000.0


# ------------------------------------------------------------
# Maximum number of fertilizers selected by optimizer
# ------------------------------------------------------------
MAX_FERTILIZERS_USED = 5


# ------------------------------------------------------------
# Estiércol is always included
# ------------------------------------------------------------
REQUIRED_FERTILIZER = "Estiércol de Vacuno"


# ------------------------------------------------------------
# Nutrients optimized
#
# IMPORTANT:
# Only these nutrients are forced:
#
#   SUMA de nutrientes >= requerimiento del cultivo
#
# CaO, MgO, and S are ignored for optimization.
# ------------------------------------------------------------
OPTIMIZED_NUTRIENTS = ["P2O5", "K2O", "N"]


# ------------------------------------------------------------
# Dynamic excess tolerance
#
# The rule for each optimized nutrient is:
#
#   required <= supplied <= required + excess_tolerance
#
# If no solution exists, the code increases excess_tolerance:
#
#   0, 10, 20, 30, ...
#
# This means the optimizer is allowed to exceed the requirement
# more and more until a feasible solution is found.
# ------------------------------------------------------------
INITIAL_EXCESS_TOLERANCE = 0.0
EXCESS_TOLERANCE_STEP = 10.0
MAX_EXCESS_TOLERANCE = 1000.0


# ------------------------------------------------------------
# Molimax has low priority.
# It can be used, but only if needed.
# Names must match the exact Excel/header names.
# ------------------------------------------------------------
LOW_PRIORITY_FERTILIZERS = [
    "Molimax (20-20-20)",
    "Molimax (16-16-16)",
]

LOW_PRIORITY_PENALTY = 10_000.0


# ------------------------------------------------------------
# Fertilizer table
#
# Nutrient values are percentages.
#
# pH columns:
#   acid      -> pH < 5.5
#   alkaline  -> pH > 8.0
#   neutral   -> 5.5 <= pH <= 8.0
# ------------------------------------------------------------
FERTILIZER_TABLE = {
    "Estiércol de Vacuno": {
        "N": 2.73,
        "P2O5": 0.62,
        "K2O": 0.80,
        "CaO": 0.34,
        "MgO": 1.00,
        "S": 0.40,
        "acid": True,
        "alkaline": True,
        "neutral": True,
    },
    "Urea": {
        "N": 46.00,
        "P2O5": 0.00,
        "K2O": 0.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 0.00,
        "acid": False,
        "alkaline": True,
        "neutral": True,
    },
    "Nitrato de Amonio": {
        "N": 33.00,
        "P2O5": 0.00,
        "K2O": 0.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 0.00,
        "acid": True,
        "alkaline": False,
        "neutral": True,
    },
    "Fosfato Diamónico": {
        "N": 18.00,
        "P2O5": 46.00,
        "K2O": 0.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 0.00,
        "acid": True,
        "alkaline": True,
        "neutral": True,
    },
    "Cloruro de Potasio": {
        "N": 0.00,
        "P2O5": 0.00,
        "K2O": 60.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 0.00,
        "acid": True,
        "alkaline": False,
        "neutral": True,
    },
    "Sulfato de Potasio": {
        "N": 0.00,
        "P2O5": 0.00,
        "K2O": 50.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 18.00,
        "acid": False,
        "alkaline": True,
        "neutral": True,
    },
    "Sulfato de Potasio y Magnesio": {
        "N": 0.00,
        "P2O5": 0.00,
        "K2O": 22.00,
        "CaO": 0.00,
        "MgO": 18.00,
        "S": 22.00,
        "acid": False,
        "alkaline": True,
        "neutral": True,
    },
    "Molimax (20-20-20)": {
        "N": 20.00,
        "P2O5": 20.00,
        "K2O": 20.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 0.00,
        "acid": True,
        "alkaline": True,
        "neutral": True,
    },
    "Molimax (16-16-16)": {
        "N": 16.00,
        "P2O5": 16.00,
        "K2O": 16.00,
        "CaO": 0.00,
        "MgO": 0.00,
        "S": 0.00,
        "acid": True,
        "alkaline": True,
        "neutral": True,
    },
}


FERTILIZER_NAMES = list(FERTILIZER_TABLE.keys())


# ------------------------------------------------------------
# Basic helpers
# ------------------------------------------------------------
def round_up_to_1_decimal(values):
    """
    Round fertilizer doses UP to 1 decimal.

    This helps avoid Excel recalculation producing a nutrient sum
    slightly below the requirement.
    """

    values = np.array(values, dtype=float)
    return np.ceil(values * 10.0 - 1e-9) / 10.0


def get_ph_class(ph):
    """
    Classify soil pH.

    Returns:
        acid      if pH < 5.5
        alkaline  if pH > 8.0
        neutral   if 5.5 <= pH <= 8.0
    """

    if ph is None:
        raise ValueError("ph is required because fertilizer use depends on soil pH.")

    try:
        ph = float(ph)
    except Exception:
        raise ValueError(f"Invalid pH value: {ph}")

    if ph < 5.5:
        return "acid"

    if ph > 8.0:
        return "alkaline"

    return "neutral"


def fertilizer_allowed_for_ph(fertilizer_name, ph):
    """
    Return True if fertilizer can be used for the given pH.
    """

    ph_class = get_ph_class(ph)

    if fertilizer_name not in FERTILIZER_TABLE:
        raise ValueError(f"Unknown fertilizer: {fertilizer_name}")

    return bool(FERTILIZER_TABLE[fertilizer_name][ph_class])


def get_allowed_fertilizers(ph):
    """
    Return fertilizers allowed by pH.
    """

    return [
        fertilizer_name
        for fertilizer_name in FERTILIZER_NAMES
        if fertilizer_allowed_for_ph(fertilizer_name, ph)
    ]


def build_formula_from_table(selected_fertilizers):
    """
    Build fertilizer formula matrix from FERTILIZER_TABLE.

    Rows:
        selected fertilizers

    Columns:
        NUTRIENTS

    Values:
        fractions, not percentages.

    Example:
        46.00 becomes 0.46
    """

    formula = []

    for fertilizer_name in selected_fertilizers:
        if fertilizer_name not in FERTILIZER_TABLE:
            raise ValueError(f"Unknown fertilizer: {fertilizer_name}")

        row = []

        for nutrient in NUTRIENTS:
            if nutrient not in FERTILIZER_TABLE[fertilizer_name]:
                raise ValueError(
                    f"Nutrient '{nutrient}' not found for fertilizer "
                    f"'{fertilizer_name}' in FERTILIZER_TABLE."
                )

            row.append(FERTILIZER_TABLE[fertilizer_name][nutrient])

        formula.append(row)

    formula = np.array(formula, dtype=float)

    # Convert percentages to fractions.
    if np.nanmax(formula) > 1.0:
        formula = formula / 100.0

    return formula


def effective_requirements(requirements):
    """
    Convert negative requirements to zero.
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


def get_optimized_nutrient_indices():
    """
    Convert OPTIMIZED_NUTRIENTS to indices in NUTRIENTS.
    """

    indices = []

    for nutrient in OPTIMIZED_NUTRIENTS:
        if nutrient not in NUTRIENTS:
            raise ValueError(
                f"'{nutrient}' is not found in NUTRIENTS.\n"
                f"NUTRIENTS = {list(NUTRIENTS)}"
            )

        indices.append(list(NUTRIENTS).index(nutrient))

    return indices


def generate_allowed_fertilizer_combinations(ph):
    """
    Generate all possible fertilizer combinations up to MAX_FERTILIZERS_USED.

    Estiércol de Vacuno is always included.
    Fertilizers not allowed by pH are removed before making combinations.
    """

    allowed_fertilizers = get_allowed_fertilizers(ph)

    if REQUIRED_FERTILIZER not in allowed_fertilizers:
        raise RuntimeError(
            f"{REQUIRED_FERTILIZER} is required, but it is not allowed for pH={ph}."
        )

    optional_fertilizers = [
        fertilizer_name
        for fertilizer_name in allowed_fertilizers
        if fertilizer_name != REQUIRED_FERTILIZER
    ]

    all_combinations = []

    max_optional = MAX_FERTILIZERS_USED - 1
    max_optional = min(max_optional, len(optional_fertilizers))

    for size in range(0, max_optional + 1):
        for combo in combinations(optional_fertilizers, size):
            selected = [REQUIRED_FERTILIZER] + list(combo)
            all_combinations.append(selected)

    return all_combinations


def make_bounds_for_combo(selected_fertilizers, ph):
    """
    Create fertilizer bounds for one selected combination.
    """

    bounds = []

    for fertilizer_name in selected_fertilizers:
        if not fertilizer_allowed_for_ph(fertilizer_name, ph):
            bounds.append((0.0, 0.0))

        elif fertilizer_name == REQUIRED_FERTILIZER:
            bounds.append((ESTIERCOL_MIN, ESTIERCOL_MAX))

        else:
            bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))

    return bounds


def nutrient_apport(doses, selected_fertilizers):
    """
    Calculate nutrient supplied by selected fertilizer doses.
    """

    doses = np.array(doses, dtype=float)

    if doses.ndim != 1:
        raise ValueError(f"doses must be 1D. Current shape: {doses.shape}")

    if len(doses) != len(selected_fertilizers):
        raise ValueError(
            "doses length must match selected_fertilizers length.\n"
            f"doses length: {len(doses)}\n"
            f"selected_fertilizers length: {len(selected_fertilizers)}"
        )

    formula = build_formula_from_table(selected_fertilizers)

    return doses @ formula


def final_remaining(doses, requirements, selected_fertilizers):
    """
    Calculate remaining nutrient requirement.

    Positive remaining means nutrient is still missing.
    Negative remaining means nutrient is in excess.
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(doses, selected_fertilizers)

    return requirements - apport


def get_missing_nutrients(requirements, doses, selected_fertilizers, tolerance=1e-6):
    """
    Return missing nutrient amounts after calculating supplied nutrients.

    Only checks:
        P2O5, K2O, N

    Ignores:
        CaO, MgO, S
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(doses, selected_fertilizers)
    remaining = requirements - apport

    missing = {}
    optimized_indices = get_optimized_nutrient_indices()

    for i in optimized_indices:
        nutrient_name = NUTRIENTS[i]

        if remaining[i] > tolerance:
            missing[nutrient_name] = remaining[i]

    return missing


# ------------------------------------------------------------
# Validation
# ------------------------------------------------------------
def validate_solution(
    requirements,
    doses,
    selected_fertilizers,
    tolerance=1e-6,
    excess_tolerance=None,
):
    """
    Final validation.

    For P2O5, K2O, and N:

        supplied_i must be >= required_i

    If excess_tolerance is given:

        supplied_i must be <= required_i + excess_tolerance

    CaO, MgO, and S are ignored.
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(doses, selected_fertilizers)
    remaining = requirements - apport
    excess = apport - requirements

    optimized_indices = get_optimized_nutrient_indices()

    error_lines = []

    print("\nSTRICT FINAL VALIDATION")
    print("Checking only P2O5, K2O, and N.")
    print("Rule 1: SUMA de nutrientes must be >= requerimiento.")

    if excess_tolerance is not None:
        print(
            "Rule 2: SUMA de nutrientes must be <= requerimiento "
            f"+ {excess_tolerance:.2f} kg/ha."
        )

    print("CaO, MgO, and S are ignored for optimization.")

    for i, nutrient_name in enumerate(NUTRIENTS):
        req = requirements[i]
        supplied = apport[i]
        rem = remaining[i]
        exc = excess[i]

        if i in optimized_indices:
            status = "CHECKED"

            # This is the most important rule:
            # never allow supplied < required.
            if supplied + tolerance < req:
                error_lines.append(
                    f"{nutrient_name}: SUMA is lower than requirement. "
                    f"Required = {req:.2f}, "
                    f"Supplied = {supplied:.2f}, "
                    f"Missing = {req - supplied:.2f}"
                )

            # Tolerance means how much excess is allowed.
            if excess_tolerance is not None:
                if supplied > req + excess_tolerance + tolerance:
                    error_lines.append(
                        f"{nutrient_name}: SUMA exceeds allowed tolerance. "
                        f"Required = {req:.2f}, "
                        f"Supplied = {supplied:.2f}, "
                        f"Excess = {exc:.2f}, "
                        f"Allowed excess = {excess_tolerance:.2f}"
                    )

        else:
            status = "IGNORED"

        print(
            f"  {nutrient_name:5s}: "
            f"required = {req:10.2f}   "
            f"supplied = {supplied:10.2f}   "
            f"remaining = {rem:10.2f}   "
            f"excess = {exc:10.2f}   "
            f"{status}"
        )

    if error_lines:
        raise RuntimeError(
            "\nINVALID SOLUTION.\n"
            "The solution does not satisfy the required rule:\n"
            "SUMA de nutrientes >= requerimiento for P2O5, K2O, and N.\n\n"
            + "\n".join(error_lines)
        )

    return True


# ------------------------------------------------------------
# Core optimizer for one combination
# ------------------------------------------------------------
def solve_linear_program_for_combo(
    requirements,
    ph,
    selected_fertilizers,
    excess_tolerance,
):
    """
    Optimizer for one fertilizer combination.

    Hard lower rule for P2O5, K2O, and N:

        supplied_i >= required_i

    Dynamic upper tolerance rule:

        supplied_i <= required_i + excess_tolerance

    If this is not feasible, the main optimizer increases
    excess_tolerance by 10 and tries again.
    """

    requirements = effective_requirements(requirements)
    formula = build_formula_from_table(selected_fertilizers)

    optimized_indices = get_optimized_nutrient_indices()
    n_fertilizers = len(selected_fertilizers)

    A_ub = []
    b_ub = []

    for nutrient_index in optimized_indices:
        req = requirements[nutrient_index]
        nutrient_vector = formula[:, nutrient_index]

        # ----------------------------------------------------
        # HARD LOWER CONSTRAINT:
        #
        # supplied_i >= required_i
        #
        # In scipy linprog form:
        # -supplied_i <= -required_i
        # ----------------------------------------------------
        row = -nutrient_vector
        A_ub.append(row)
        b_ub.append(-req)

        # ----------------------------------------------------
        # DYNAMIC UPPER CONSTRAINT:
        #
        # supplied_i <= required_i + excess_tolerance
        #
        # If no solution is found, excess_tolerance increases.
        # ----------------------------------------------------
        row = nutrient_vector
        A_ub.append(row)
        b_ub.append(req + excess_tolerance)

    bounds = make_bounds_for_combo(selected_fertilizers, ph)

    # --------------------------------------------------------
    # Objective:
    # Minimize total fertilizer dose.
    # Penalize Molimax so it is used only if needed.
    # --------------------------------------------------------
    c = np.zeros(n_fertilizers, dtype=float)

    for i, fertilizer_name in enumerate(selected_fertilizers):
        if fertilizer_name in LOW_PRIORITY_FERTILIZERS:
            c[i] = LOW_PRIORITY_PENALTY
        elif fertilizer_name == REQUIRED_FERTILIZER:
            c[i] = 0.01
        else:
            c[i] = 1.0

    result = linprog(
        c=c,
        A_ub=np.array(A_ub, dtype=float),
        b_ub=np.array(b_ub, dtype=float),
        bounds=bounds,
        method="highs",
    )

    if result.success:
        result.selected_fertilizers = selected_fertilizers
        result.excess_tolerance_used = excess_tolerance

    return result


def solution_priority_key(requirements, doses, selected_fertilizers):
    """
    Compare feasible solutions.

    Lower tuple is better.

    Priority:
        1. smallest excess in P2O5
        2. smallest excess in K2O
        3. smallest excess in N
        4. avoid Molimax
        5. fewer fertilizers
        6. smaller total dose
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(doses, selected_fertilizers)
    excess = np.maximum(apport - requirements, 0.0)

    key = []

    for nutrient_name in OPTIMIZED_NUTRIENTS:
        idx = list(NUTRIENTS).index(nutrient_name)
        key.append(round(float(excess[idx]), 8))

    molimax_count = sum(
        1
        for fertilizer_name in selected_fertilizers
        if fertilizer_name in LOW_PRIORITY_FERTILIZERS
    )

    molimax_dose = sum(
        float(dose)
        for fertilizer_name, dose in zip(selected_fertilizers, doses)
        if fertilizer_name in LOW_PRIORITY_FERTILIZERS
    )

    key.append(molimax_count)
    key.append(round(molimax_dose, 8))
    key.append(len(selected_fertilizers))
    key.append(round(float(np.sum(doses)), 8))

    return tuple(key)


# ------------------------------------------------------------
# Compatibility functions
# ------------------------------------------------------------
def objective(doses, requirements):
    """
    Kept for compatibility with older code.
    """

    return 0.0


def make_constraints(requirements):
    """
    Kept for compatibility with older code.
    """

    return []


# ------------------------------------------------------------
# Main optimizer
# ------------------------------------------------------------
def optimize_fertilizers(requirements, ph):
    """
    Main optimizer.

    Logic:

        1. Try excess tolerance = 0.
        2. Test all fertilizer combinations.
        3. Accept only if, for P2O5, K2O, and N:

             SUMA de nutrientes >= requerimiento

           and:

             SUMA de nutrientes <= requerimiento + tolerance

        4. If no solution exists, increase tolerance by 10.
        5. Repeat until a valid solution is found.

    CaO, MgO, and S are ignored.
    """

    original_requirements = effective_requirements(requirements)

    tolerance_values = np.arange(
        INITIAL_EXCESS_TOLERANCE,
        MAX_EXCESS_TOLERANCE + EXCESS_TOLERANCE_STEP,
        EXCESS_TOLERANCE_STEP,
        dtype=float,
    )

    last_error = None

    for excess_tolerance in tolerance_values:

        print("\n" + "#" * 80)
        print(f"TRYING EXCESS TOLERANCE = {excess_tolerance:.1f} kg/ha")
        print("#" * 80)

        combinations_to_test = generate_allowed_fertilizer_combinations(ph)

        best_result = None
        best_key = None
        best_combo = None

        print("\nSearching best fertilizer combination")
        print(f"pH = {ph}")
        print(f"pH class = {get_ph_class(ph)}")
        print(f"Maximum fertilizers used = {MAX_FERTILIZERS_USED}")
        print(f"Allowed fertilizers = {get_allowed_fertilizers(ph)}")
        print(f"Combinations to test = {len(combinations_to_test)}")
        print(f"Nutrients optimized = {OPTIMIZED_NUTRIENTS}")
        print("Ignored nutrients = CaO, MgO, S")
        print(
            "Current rule: "
            "requerimiento <= SUMA <= requerimiento "
            f"+ {excess_tolerance:.1f}"
        )

        for combo in combinations_to_test:

            result = solve_linear_program_for_combo(
                requirements=original_requirements,
                ph=ph,
                selected_fertilizers=combo,
                excess_tolerance=excess_tolerance,
            )

            if not result.success:
                continue

            # The values that will be used by CSV/Excel.
            rounded_doses = round_up_to_1_decimal(result.x)

            try:
                validate_solution(
                    requirements=original_requirements,
                    doses=rounded_doses,
                    selected_fertilizers=combo,
                    excess_tolerance=excess_tolerance,
                )
            except RuntimeError as err:
                last_error = str(err)
                continue

            key = solution_priority_key(
                requirements=original_requirements,
                doses=rounded_doses,
                selected_fertilizers=combo,
            )

            if best_key is None or key < best_key:
                best_key = key
                best_result = result
                best_combo = combo
                best_result.x = rounded_doses

        if best_result is not None:
            best_result.selected_fertilizers = best_combo
            best_result.best_key = best_key
            best_result.original_requirements = original_requirements
            best_result.working_requirements = original_requirements
            best_result.excess_tolerance_used = excess_tolerance

            print("\nVALID OPTIMIZATION FOUND")
            print(f"Excess tolerance used: {excess_tolerance:.1f} kg/ha")

            print("\nSelected fertilizers:")
            for fertilizer_name in best_combo:
                print(f"  - {fertilizer_name}")

            validate_solution(
                requirements=original_requirements,
                doses=best_result.x,
                selected_fertilizers=best_combo,
                excess_tolerance=excess_tolerance,
            )

            return best_result

        print(
            "\nNo valid solution found with "
            f"excess tolerance = {excess_tolerance:.1f} kg/ha."
        )
        print(
            f"Increasing tolerance by {EXCESS_TOLERANCE_STEP:.1f} kg/ha "
            "and trying again..."
        )

    error_lines = [
        "",
        "Optimization failed.",
        "No fertilizer combination could satisfy the required N, P2O5, and K2O.",
        "",
        "Final rule required:",
        "  SUMA de nutrientes >= requerimiento",
        "",
        "Tolerance was increased dynamically but no valid result was found.",
        f"Initial tolerance: {INITIAL_EXCESS_TOLERANCE:.1f}",
        f"Step: {EXCESS_TOLERANCE_STEP:.1f}",
        f"Maximum tolerance: {MAX_EXCESS_TOLERANCE:.1f}",
    ]

    if last_error:
        error_lines.append("")
        error_lines.append("Last validation error:")
        error_lines.append(last_error)

    raise RuntimeError("\n".join(error_lines))


# ------------------------------------------------------------
# Output helpers
# ------------------------------------------------------------
def get_full_dose_vector(result):
    """
    Convert selected fertilizer result to full fertilizer vector.

    Fertilizers not selected by the optimizer are saved as zero.
    """

    full_doses = np.zeros(len(FERTILIZER_NAMES), dtype=float)

    selected_fertilizers = result.selected_fertilizers
    selected_doses = result.x

    for fertilizer_name, dose in zip(selected_fertilizers, selected_doses):
        idx = FERTILIZER_NAMES.index(fertilizer_name)
        full_doses[idx] = dose

    return full_doses


def save_optimal_values_csv(output_csv, result):
    """
    Save all fertilizers to CSV.

    Fertilizers not selected by the optimizer are saved as zero.
    """

    if not result.success:
        raise RuntimeError(
            "Cannot save optimal values because optimization failed:\n"
            f"{result.message}"
        )

    full_doses = get_full_dose_vector(result)
    full_doses = round_up_to_1_decimal(full_doses)

    df = pd.DataFrame(
        [full_doses],
        columns=FERTILIZER_NAMES,
    )

    df.to_csv(output_csv, index=False)

    print(f"Saved optimal values CSV: {output_csv}")

    return full_doses


def print_optimization_results(requirements, result):
    """
    Print optimization results.
    """

    original_requirements = np.array(requirements, dtype=float)
    requirements = effective_requirements(requirements)

    print("\n[2] Optimization results")

    if not result.success:
        print("WARNING: Optimization did not converge or solution was invalid.")
        print(result.message)
        return

    selected_fertilizers = result.selected_fertilizers
    doses = result.x

    apport = nutrient_apport(doses, selected_fertilizers)
    remaining = requirements - apport
    excess = apport - requirements

    optimized_indices = get_optimized_nutrient_indices()
    used_tolerance = getattr(result, "excess_tolerance_used", None)

    validate_solution(
        requirements=requirements,
        doses=doses,
        selected_fertilizers=selected_fertilizers,
        excess_tolerance=used_tolerance,
    )

    print("\nSelected fertilizers:")

    for fertilizer_name in selected_fertilizers:
        priority = ""

        if fertilizer_name in LOW_PRIORITY_FERTILIZERS:
            priority = "LOW PRIORITY"

        print(f"  - {fertilizer_name} {priority}")

    print("\nOriginal requirements:")
    print("Negative requirements are treated as zero.")
    print("P2O5, K2O, and N are optimized.")
    print("CaO, MgO, and S are ignored for optimization but still reported.")

    for i, name in enumerate(NUTRIENTS):
        original = original_requirements[i]
        effective = requirements[i]

        if i in optimized_indices:
            opt_status = "OPTIMIZED"
        else:
            opt_status = "REPORTED ONLY, NOT OPTIMIZED"

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
            f"{status}   "
            f"{opt_status}"
        )

    print("\nOptimized fertilizer doses:")

    full_doses = get_full_dose_vector(result)

    for fertilizer_name, dose in zip(FERTILIZER_NAMES, full_doses):
        if fertilizer_name in selected_fertilizers:
            status = "SELECTED"
        else:
            status = "NOT USED"

        print(
            f"  {fertilizer_name:35s}: "
            f"{dose:10.1f} kg/ha   "
            f"{dose / 50:8.1f} sacos/ha   "
            f"{status}"
        )

    print("\nNutrient balance:")
    print("Hard lower rule:")
    print("  SUMA de nutrientes >= requerimiento for P2O5, K2O, and N")
    print("Dynamic upper rule:")
    print("  SUMA de nutrientes <= requerimiento + dynamic tolerance")
    print("Priority:")
    print("  P2O5 first, then K2O, then N")
    print("CaO, MgO, and S are ignored for optimization but still reported.")

    if used_tolerance is not None:
        print(f"Dynamic excess tolerance used: {used_tolerance:.1f} kg/ha")
    else:
        print("Dynamic excess tolerance used: unknown")

    all_required_covered = True

    for i, name in enumerate(NUTRIENTS):
        req = requirements[i]
        app = apport[i]
        rem = remaining[i]
        exc = excess[i]

        if i in optimized_indices:
            if req > 0:
                if app + 1e-6 < req:
                    status = "MISSING"
                    all_required_covered = False
                elif used_tolerance is not None and app > req + used_tolerance + 1e-6:
                    status = "TOO MUCH EXCESS"
                    all_required_covered = False
                elif used_tolerance is not None and exc > 1e-6:
                    status = "OK, WITHIN TOLERANCE"
                else:
                    status = "OK"
            else:
                if app > 1e-6:
                    status = "NOT REQUIRED, ADDED"
                else:
                    status = "NOT REQUIRED"
        else:
            status = "REPORTED ONLY, NOT OPTIMIZED"

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
        print("  OK: P2O5, K2O, and N requirements are covered.")
        print("  OK: The selected solution is within the dynamic tolerance.")
        print(f"  OK: {REQUIRED_FERTILIZER} was included.")
    else:
        print("  WARNING: at least one optimized nutrient is outside the allowed range.")

    print("\nDebug information:")
    print(f"  pH-selected fertilizers: {selected_fertilizers}")
    print(f"  Best priority key: {getattr(result, 'best_key', None)}")
    print(f"  Nutrients: {list(NUTRIENTS)}")
    print(f"  Optimized nutrients: {OPTIMIZED_NUTRIENTS}")
    print(f"  Dynamic excess tolerance used: {used_tolerance}")
    print(f"  All fertilizers: {FERTILIZER_NAMES}")

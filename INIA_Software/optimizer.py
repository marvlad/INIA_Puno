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
# Priority order:
#   1. P2O5
#   2. K2O
#   3. N
#
# CaO, MgO, and S are ignored for optimization.
# They will still be reported in the nutrient balance.
# ------------------------------------------------------------
OPTIMIZED_NUTRIENTS = ["P2O5", "K2O", "N"]


# ------------------------------------------------------------
# Dynamic excess tolerance
#
# Final rule:
#   requirement <= supplied <= requirement + tolerance
#
# If no valid solution exists, tolerance increases by 10 kg/ha.
# ------------------------------------------------------------
INITIAL_EXCESS_TOLERANCE = 0.0
EXCESS_TOLERANCE_STEP = 10.0
MAX_EXCESS_TOLERANCE = 300.0


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
# Retry logic
# ------------------------------------------------------------
MAX_OPTIMIZATION_RETRIES = 5
SAFETY_MARGIN = 0.5


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
# Helpers
# ------------------------------------------------------------
def round_up_to_1_decimal(values):
    """
    Round fertilizer doses UP to 1 decimal.

    This avoids Excel recalculation giving a nutrient sum slightly below
    the requirement after normal rounding.
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


def requirements_with_safety_margin(requirements, missing, safety_margin=SAFETY_MARGIN):
    """
    Increase requirements only for nutrients that were still missing.

    This forces the next optimization attempt to supply slightly more.
    """

    new_requirements = effective_requirements(requirements).copy()

    for nutrient_name, missing_amount in missing.items():
        idx = list(NUTRIENTS).index(nutrient_name)
        new_requirements[idx] += missing_amount + safety_margin

    return new_requirements


# ------------------------------------------------------------
# Core optimizer
# ------------------------------------------------------------
def solve_linear_program_for_combo(
    requirements,
    ph,
    selected_fertilizers,
    excess_tolerance,
):
    """
    Lexicographic optimizer for one fertilizer combination.

    Hard constraints for optimized nutrients:

        supplied_i >= required_i
        supplied_i <= required_i + excess_tolerance

    for:
        P2O5, K2O, N

    CaO, MgO, and S are ignored for optimization.

    Priority:
        1. minimize P2O5 excess
        2. minimize K2O excess
        3. minimize N excess
        4. minimize fertilizer dose and avoid Molimax
    """

    requirements = effective_requirements(requirements)
    formula = build_formula_from_table(selected_fertilizers)

    optimized_indices = get_optimized_nutrient_indices()

    n_fertilizers = len(selected_fertilizers)
    n_optimized_nutrients = len(optimized_indices)
    n_variables = n_fertilizers + n_optimized_nutrients

    A_ub = []
    b_ub = []

    for local_j, nutrient_index in enumerate(optimized_indices):
        req = requirements[nutrient_index]
        nutrient_vector = formula[:, nutrient_index]

        # ----------------------------------------------------
        # Lower hard constraint:
        # supplied_i >= required_i
        #
        # -supplied_i <= -required_i
        # ----------------------------------------------------
        if req > 0:
            row = np.zeros(n_variables, dtype=float)
            row[:n_fertilizers] = -nutrient_vector

            A_ub.append(row)
            b_ub.append(-req)

        # ----------------------------------------------------
        # Upper hard constraint:
        # supplied_i <= required_i + excess_tolerance
        #
        # This prevents suma de nutrientes from being too high.
        # ----------------------------------------------------
        row = np.zeros(n_variables, dtype=float)
        row[:n_fertilizers] = nutrient_vector

        A_ub.append(row)
        b_ub.append(req + excess_tolerance)

        # ----------------------------------------------------
        # Excess variable:
        # excess_i >= supplied_i - required_i
        #
        # supplied_i - excess_i <= required_i
        # ----------------------------------------------------
        row = np.zeros(n_variables, dtype=float)
        row[:n_fertilizers] = nutrient_vector
        row[n_fertilizers + local_j] = -1.0

        A_ub.append(row)
        b_ub.append(req)

    bounds = make_bounds_for_combo(selected_fertilizers, ph)

    for _ in range(n_optimized_nutrients):
        bounds.append((0.0, None))

    fixed_A = list(np.array(A_ub, dtype=float))
    fixed_b = list(np.array(b_ub, dtype=float))

    tolerance = 1e-7
    fixed_excess_values = {}

    # Lexicographic optimization
    for local_j, nutrient_index in enumerate(optimized_indices):
        nutrient_name = NUTRIENTS[nutrient_index]

        c = np.zeros(n_variables, dtype=float)
        c[n_fertilizers + local_j] = 1.0

        result = linprog(
            c=c,
            A_ub=np.array(fixed_A, dtype=float),
            b_ub=np.array(fixed_b, dtype=float),
            bounds=bounds,
            method="highs",
        )

        if not result.success:
            return result

        best_excess = result.x[n_fertilizers + local_j]
        fixed_excess_values[nutrient_name] = best_excess

        # Fix this nutrient excess to its best value.
        row = np.zeros(n_variables, dtype=float)
        row[n_fertilizers + local_j] = 1.0

        fixed_A.append(row)
        fixed_b.append(best_excess + tolerance)

    # Final stage:
    # minimize total fertilizer and penalize Molimax.
    c = np.zeros(n_variables, dtype=float)

    for i, fertilizer_name in enumerate(selected_fertilizers):
        if fertilizer_name in LOW_PRIORITY_FERTILIZERS:
            c[i] = LOW_PRIORITY_PENALTY
        elif fertilizer_name == REQUIRED_FERTILIZER:
            c[i] = 0.01
        else:
            c[i] = 1.0

    result = linprog(
        c=c,
        A_ub=np.array(fixed_A, dtype=float),
        b_ub=np.array(fixed_b, dtype=float),
        bounds=bounds,
        method="highs",
    )

    if result.success:
        full_x = result.x.copy()

        result.full_x = full_x
        result.x = full_x[:n_fertilizers]
        result.excess_variables = full_x[n_fertilizers:]
        result.selected_fertilizers = selected_fertilizers
        result.fixed_excess_values = fixed_excess_values
        result.excess_tolerance_used = excess_tolerance

    return result


def solution_priority_key(requirements, doses, selected_fertilizers):
    """
    Compare feasible solutions.

    Lower tuple is better.

    Priority:
        1. smallest P2O5 excess
        2. smallest K2O excess
        3. smallest N excess
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


def validate_solution(
    requirements,
    doses,
    selected_fertilizers,
    tolerance=1e-6,
    excess_tolerance=None,
):
    """
    Strict final validation.

    Checks:
        P2O5, K2O, N

    Ignores:
        CaO, MgO, S

    Rules:
        supplied_i >= required_i
        supplied_i <= required_i + excess_tolerance
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(doses, selected_fertilizers)
    remaining = requirements - apport
    excess = apport - requirements

    optimized_indices = get_optimized_nutrient_indices()

    print("\nSTRICT FINAL VALIDATION")
    print("Rule 1: supplied_i must be >= required_i for P2O5, K2O, and N.")

    if excess_tolerance is not None:
        print(
            "Rule 2: supplied_i must be <= required_i "
            f"+ {excess_tolerance:.2f} kg/ha."
        )

    print("CaO, MgO, and S are ignored for optimization.")

    error_lines = []

    for i, name in enumerate(NUTRIENTS):
        req = requirements[i]
        app = apport[i]
        rem = remaining[i]
        exc = excess[i]

        if i in optimized_indices:
            rule = "CHECKED"

            if rem > tolerance:
                error_lines.append(
                    f"{name}: required = {req:.2f}, "
                    f"supplied = {app:.2f}, "
                    f"missing = {rem:.2f}"
                )

            if excess_tolerance is not None:
                if exc > excess_tolerance + tolerance:
                    error_lines.append(
                        f"{name}: required = {req:.2f}, "
                        f"supplied = {app:.2f}, "
                        f"excess = {exc:.2f}, "
                        f"allowed excess = {excess_tolerance:.2f}"
                    )

        else:
            rule = "IGNORED"

        print(
            f"  {name:5s}: "
            f"required = {req:10.2f}   "
            f"supplied = {app:10.2f}   "
            f"remaining = {rem:10.2f}   "
            f"excess = {exc:10.2f}   "
            f"{rule}"
        )

    if error_lines:
        raise RuntimeError(
            "\nINVALID OPTIMIZATION RESULT.\n"
            "At least one optimized nutrient is outside the allowed range.\n\n"
            + "\n".join(error_lines)
        )

    return True


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


def optimize_fertilizers(requirements, ph):
    """
    Find the best fertilizer combination.

    Rules:
        - Estiércol de Vacuno is always included.
        - Use only fertilizers allowed by pH.
        - Use maximum 5 fertilizers.
        - Optimize P2O5, K2O, and N in that exact priority order.
        - Ignore CaO, MgO, and S.
        - Final supplied nutrient must be >= requirement for P2O5, K2O, and N.
        - Final supplied nutrient must be <= requirement + dynamic tolerance.
        - If no solution is found, dynamic tolerance increases by 10 kg/ha.
        - Molimax (20-20-20) and Molimax (16-16-16) have low priority.
    """

    original_requirements = effective_requirements(requirements)

    tolerance_values = np.arange(
        INITIAL_EXCESS_TOLERANCE,
        MAX_EXCESS_TOLERANCE + EXCESS_TOLERANCE_STEP,
        EXCESS_TOLERANCE_STEP,
        dtype=float,
    )

    last_missing = None
    last_error = None

    for excess_tolerance in tolerance_values:

        print("\n" + "#" * 80)
        print(f"TRYING EXCESS TOLERANCE = {excess_tolerance:.1f} kg/ha")
        print("#" * 80)

        working_requirements = original_requirements.copy()

        for attempt in range(1, MAX_OPTIMIZATION_RETRIES + 1):

            print("\n" + "=" * 80)
            print(f"OPTIMIZATION ATTEMPT {attempt}/{MAX_OPTIMIZATION_RETRIES}")
            print("=" * 80)

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
                "Allowed nutrient range: "
                "requirement <= supplied <= requirement "
                f"+ {excess_tolerance:.1f} kg/ha"
            )

            for combo in combinations_to_test:
                result = solve_linear_program_for_combo(
                    requirements=working_requirements,
                    ph=ph,
                    selected_fertilizers=combo,
                    excess_tolerance=excess_tolerance,
                )

                if not result.success:
                    continue

                # This is the dose that will be written to CSV/Excel.
                rounded_doses = round_up_to_1_decimal(result.x)

                try:
                    validate_solution(
                        requirements=working_requirements,
                        doses=rounded_doses,
                        selected_fertilizers=combo,
                        excess_tolerance=excess_tolerance,
                    )
                except RuntimeError:
                    continue

                key = solution_priority_key(
                    requirements=working_requirements,
                    doses=rounded_doses,
                    selected_fertilizers=combo,
                )

                if best_key is None or key < best_key:
                    best_key = key
                    best_result = result
                    best_combo = combo
                    best_result.x = rounded_doses

            if best_result is None:
                last_error = (
                    "\nNo feasible fertilizer combination was found "
                    f"with excess tolerance = {excess_tolerance:.1f} kg/ha.\n\n"
                    "Possible reasons:\n"
                    "  1. Requirements for P2O5, K2O, or N are too high.\n"
                    "  2. pH removed too many fertilizers.\n"
                    "  3. OTHER_FERTILIZER_MAX is too low.\n"
                    "  4. ESTIERCOL_MAX is too low.\n"
                    "  5. The allowed excess tolerance is still too strict.\n"
                    "  6. CaO, MgO, and S are ignored and cannot help feasibility.\n"
                )

                print(last_error)
                print(
                    f"Increasing tolerance by {EXCESS_TOLERANCE_STEP:.1f} "
                    "kg/ha and trying again..."
                )

                break

            best_result.selected_fertilizers = best_combo
            best_result.best_key = best_key
            best_result.original_requirements = original_requirements
            best_result.working_requirements = working_requirements
            best_result.excess_tolerance_used = excess_tolerance

            print("\nBest fertilizer combination found:")
            for fertilizer_name in best_combo:
                print(f"  - {fertilizer_name}")

            print(f"\nBest priority key: {best_key}")
            print(f"Excess tolerance used: {excess_tolerance:.1f} kg/ha")

            missing = get_missing_nutrients(
                requirements=original_requirements,
                doses=best_result.x,
                selected_fertilizers=best_combo,
                tolerance=1e-6,
            )

            try:
                validate_solution(
                    requirements=original_requirements,
                    doses=best_result.x,
                    selected_fertilizers=best_combo,
                    excess_tolerance=excess_tolerance,
                )
            except RuntimeError as err:
                last_error = str(err)

                print("\nFINAL POST-CHECK FAILED")
                print(last_error)
                print(
                    f"Increasing tolerance by {EXCESS_TOLERANCE_STEP:.1f} "
                    "kg/ha and trying again..."
                )

                break

            if not missing:
                print("\nFINAL POST-CHECK PASSED")
                print("All optimized nutrients satisfy the original requirements.")
                print(
                    "Final rule satisfied: "
                    "requirement <= supplied <= requirement "
                    f"+ {excess_tolerance:.1f} kg/ha"
                )

                return best_result

            last_missing = missing

            print("\nFINAL POST-CHECK FAILED")
            print("Some nutrients are still below the original requirement after rounding:")

            for nutrient_name, missing_amount in missing.items():
                print(f"  {nutrient_name}: missing {missing_amount:.4f} kg/ha")

            print("\nRedoing optimization with safety margin...")

            working_requirements = requirements_with_safety_margin(
                requirements=working_requirements,
                missing=missing,
                safety_margin=SAFETY_MARGIN,
            )

            print("\nNew working requirements:")

            for nutrient_name in OPTIMIZED_NUTRIENTS:
                idx = list(NUTRIENTS).index(nutrient_name)
                print(
                    f"  {nutrient_name}: "
                    f"original = {original_requirements[idx]:.4f}, "
                    f"working = {working_requirements[idx]:.4f}"
                )

    error_lines = [
        "",
        "Optimization failed after trying all dynamic excess tolerances.",
        "The final supplied nutrients could not satisfy the allowed range.",
        "",
        "Required rule:",
        "  requirement <= supplied <= requirement + dynamic_tolerance",
        "",
        f"Initial tolerance: {INITIAL_EXCESS_TOLERANCE:.1f} kg/ha",
        f"Tolerance step: {EXCESS_TOLERANCE_STEP:.1f} kg/ha",
        f"Maximum tolerance: {MAX_EXCESS_TOLERANCE:.1f} kg/ha",
        "",
    ]

    if last_missing:
        error_lines.append("Last missing nutrients:")
        for nutrient_name, missing_amount in last_missing.items():
            error_lines.append(f"  {nutrient_name}: missing {missing_amount:.4f} kg/ha")

    if last_error:
        error_lines.append("")
        error_lines.append(str(last_error))

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

    Doses are rounded UP to 1 decimal to avoid Excel recalculation
    producing nutrient sums slightly below the requirements.
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
    print("Hard rule:")
    print("  supplied_i >= required_i for P2O5, K2O, and N")
    print("Upper rule:")
    print("  supplied_i <= required_i + dynamic tolerance for P2O5, K2O, and N")
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
                if rem > 1e-6:
                    status = "MISSING"
                    all_required_covered = False
                elif used_tolerance is not None and exc > used_tolerance + 1e-6:
                    status = "TOO MUCH EXCESS"
                    all_required_covered = False
                elif used_tolerance is not None and exc > 1e-6:
                    status = "OK, WITHIN TOLERANCE"
                else:
                    status = "OK"
            else:
                if used_tolerance is not None and app > used_tolerance + 1e-6:
                    status = "NOT REQUIRED, TOO MUCH ADDED"
                elif app > 1e-6:
                    status = "NOT REQUIRED, ADDED WITHIN TOLERANCE"
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
        print("  OK: P2O5, K2O, and N are within the dynamic tolerance.")
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

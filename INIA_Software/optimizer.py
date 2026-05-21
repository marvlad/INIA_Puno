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
#
# This includes Estiércol de Vacuno.
# Example:
#   MAX_FERTILIZERS_USED = 5 means:
#       Estiércol de Vacuno + up to 4 additional fertilizers
# ------------------------------------------------------------
MAX_FERTILIZERS_USED = 5


# ------------------------------------------------------------
# Mandatory fertilizer
# ------------------------------------------------------------
MANDATORY_FERTILIZER = "Estiércol de Vacuno"


# ------------------------------------------------------------
# Nutrients optimized
#
# Priority:
#   1. P2O5
#   2. K2O
#   3. N
#   4. CaO
#   5. MgO
#
# S is ignored.
# ------------------------------------------------------------
OPTIMIZED_NUTRIENTS = ["P2O5", "K2O", "N", "CaO", "MgO"]


# ------------------------------------------------------------
# Excess penalty weights
#
# Larger value = optimizer tries harder to avoid excess.
# ------------------------------------------------------------
EXCESS_WEIGHT_BY_NUTRIENT = {
    "P2O5": 1_000_000.0,
    "K2O": 100_000.0,
    "N": 10_000.0,
    "CaO": 1_000.0,
    "MgO": 1_000.0,
}


# ------------------------------------------------------------
# Molimax has low priority.
# It can be used, but only if needed.
# ------------------------------------------------------------
LOW_PRIORITY_FERTILIZERS = [
    "Molimax (20-20-20)",
    "Molimax (16-16-16)",
]

LOW_PRIORITY_PENALTY = 5000.0


# ------------------------------------------------------------
# This is only for reporting.
# It is NOT a hard upper constraint.
# ------------------------------------------------------------
EXCESS_TOLERANCE = 50.0


# ------------------------------------------------------------
# Full fertilizer table
#
# IMPORTANT:
# These names are written exactly as they should appear in Excel.
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
        "N": 21.73,
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


def get_ph_class(ph):
    """
    Classify soil pH.

    Returns:
        acid      if pH < 5.5
        alkaline  if pH > 8.0
        neutral   if 5.5 <= pH <= 8.0
    """

    if ph is None:
        raise ValueError(
            "ph is required because fertilizer use depends on soil pH."
        )

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

    Example:
        [299, 609, -150, -2384, -500, 41]

    becomes:
        [299, 609, 0, 0, 0, 41]
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
    Generate all possible fertilizer combinations.

    Rules:
        - Estiércol de Vacuno is always included.
        - Estiércol de Vacuno must be allowed by pH.
        - Other fertilizers are selected only if allowed by pH.
        - Maximum total fertilizers = MAX_FERTILIZERS_USED.
    """

    allowed_fertilizers = get_allowed_fertilizers(ph)
    ph_class = get_ph_class(ph)

    if MANDATORY_FERTILIZER not in allowed_fertilizers:
        raise RuntimeError(
            f"{MANDATORY_FERTILIZER} is mandatory, but it is not allowed "
            f"for pH = {ph} ({ph_class})."
        )

    optional_fertilizers = [
        fertilizer_name
        for fertilizer_name in allowed_fertilizers
        if fertilizer_name != MANDATORY_FERTILIZER
    ]

    all_combinations = []

    max_optional_size = min(
        MAX_FERTILIZERS_USED - 1,
        len(optional_fertilizers),
    )

    for size in range(0, max_optional_size + 1):
        for optional_combo in combinations(optional_fertilizers, size):
            combo = [MANDATORY_FERTILIZER] + list(optional_combo)
            all_combinations.append(combo)

    return all_combinations


def make_bounds_for_combo(selected_fertilizers, ph):
    """
    Create fertilizer bounds for one selected combination.

    Estiércol de Vacuno:
        4000 <= dose <= 6000

    Other fertilizers:
        0 <= dose <= 3000
    """

    bounds = []

    for fertilizer_name in selected_fertilizers:
        if not fertilizer_allowed_for_ph(fertilizer_name, ph):
            bounds.append((0.0, 0.0))

        elif fertilizer_name == MANDATORY_FERTILIZER:
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
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(doses, selected_fertilizers)

    return requirements - apport


def solve_linear_program_for_combo(requirements, ph, selected_fertilizers):
    """
    Solve the optimizer for one fertilizer combination.

    Hard constraints:
        P2O5 supplied >= P2O5 required
        K2O supplied >= K2O required
        N supplied >= N required
        CaO supplied >= CaO required
        MgO supplied >= MgO required

    S is ignored.

    Estiércol de Vacuno is forced by:
        1. being present in selected_fertilizers
        2. having bounds 4000 <= dose <= 6000
    """

    requirements = effective_requirements(requirements)
    formula = build_formula_from_table(selected_fertilizers)

    optimized_indices = get_optimized_nutrient_indices()

    n_fertilizers = len(selected_fertilizers)
    n_optimized_nutrients = len(optimized_indices)
    n_variables = n_fertilizers + n_optimized_nutrients

    c = np.zeros(n_variables, dtype=float)

    # Fertilizer dose costs
    for i, fertilizer_name in enumerate(selected_fertilizers):
        if fertilizer_name in LOW_PRIORITY_FERTILIZERS:
            c[i] = LOW_PRIORITY_PENALTY
        elif fertilizer_name == MANDATORY_FERTILIZER:
            c[i] = 0.01
        else:
            c[i] = 1.0

    # Excess nutrient penalties
    for local_j, nutrient_index in enumerate(optimized_indices):
        nutrient_name = NUTRIENTS[nutrient_index]
        c[n_fertilizers + local_j] = EXCESS_WEIGHT_BY_NUTRIENT[nutrient_name]

    A_ub = []
    b_ub = []

    for local_j, nutrient_index in enumerate(optimized_indices):
        req = requirements[nutrient_index]
        nutrient_vector = formula[:, nutrient_index]

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

        # Excess variable:
        #
        # excess_i >= supplied_i - required_i
        #
        # equivalent:
        #     supplied_i - excess_i <= required_i

        row = np.zeros(n_variables, dtype=float)
        row[:n_fertilizers] = nutrient_vector
        row[n_fertilizers + local_j] = -1.0

        A_ub.append(row)
        b_ub.append(req)

    A_ub = np.array(A_ub, dtype=float)
    b_ub = np.array(b_ub, dtype=float)

    bounds = make_bounds_for_combo(selected_fertilizers, ph)

    # Bounds for excess variables
    for _ in range(n_optimized_nutrients):
        bounds.append((0.0, None))

    result = linprog(
        c=c,
        A_ub=A_ub,
        b_ub=b_ub,
        bounds=bounds,
        method="highs",
    )

    if result.success:
        full_x = result.x.copy()

        result.full_x = full_x
        result.x = full_x[:n_fertilizers]
        result.excess_variables = full_x[n_fertilizers:]
        result.selected_fertilizers = selected_fertilizers

    return result


def score_solution(requirements, doses, selected_fertilizers):
    """
    Score one feasible solution.

    Lower score is better.

    Priority:
        1. Avoid excess P2O5
        2. Avoid excess K2O
        3. Avoid excess N
        4. Avoid excess CaO
        5. Avoid excess MgO
        6. Prefer fewer fertilizers
        7. Penalize Molimax products
    """

    requirements = effective_requirements(requirements)
    formula = build_formula_from_table(selected_fertilizers)

    apport = doses @ formula
    excess = np.maximum(apport - requirements, 0.0)

    idx_p = list(NUTRIENTS).index("P2O5")
    idx_k = list(NUTRIENTS).index("K2O")
    idx_n = list(NUTRIENTS).index("N")
    idx_ca = list(NUTRIENTS).index("CaO")
    idx_mg = list(NUTRIENTS).index("MgO")

    score = 0.0

    score += 1_000_000.0 * excess[idx_p]
    score += 100_000.0 * excess[idx_k]
    score += 10_000.0 * excess[idx_n]
    score += 1_000.0 * excess[idx_ca]
    score += 1_000.0 * excess[idx_mg]

    # Prefer fewer fertilizers.
    score += 100.0 * len(selected_fertilizers)

    # Prefer lower total dose.
    score += 0.01 * np.sum(doses)

    # Low priority for Molimax fertilizers.
    for fertilizer_name in selected_fertilizers:
        if fertilizer_name in LOW_PRIORITY_FERTILIZERS:
            score += LOW_PRIORITY_PENALTY

    return score


def validate_solution(requirements, doses, selected_fertilizers, tolerance=1e-6):
    """
    Strict final validation.

    Checks:
        P2O5, K2O, N, CaO, MgO

    Ignores:
        S
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(doses, selected_fertilizers)
    remaining = requirements - apport

    optimized_indices = get_optimized_nutrient_indices()

    print("\nSTRICT FINAL VALIDATION")
    print("Rule: supplied_i must be >= required_i for P2O5, K2O, N, CaO, and MgO.")
    print("Rule: Estiércol de Vacuno must be included with at least 4000 kg/ha.")
    print("S is ignored because it is not measured.")

    if MANDATORY_FERTILIZER not in selected_fertilizers:
        raise RuntimeError(
            f"\nINVALID OPTIMIZATION RESULT.\n"
            f"{MANDATORY_FERTILIZER} was not selected."
        )

    estiercol_index = selected_fertilizers.index(MANDATORY_FERTILIZER)
    estiercol_dose = doses[estiercol_index]

    if estiercol_dose < ESTIERCOL_MIN - tolerance:
        raise RuntimeError(
            f"\nINVALID OPTIMIZATION RESULT.\n"
            f"{MANDATORY_FERTILIZER} dose is below minimum.\n"
            f"Required minimum = {ESTIERCOL_MIN:.2f}\n"
            f"Found = {estiercol_dose:.2f}"
        )

    for i, name in enumerate(NUTRIENTS):
        req = requirements[i]
        app = apport[i]
        rem = remaining[i]

        if i in optimized_indices:
            rule = "CHECKED"
        else:
            rule = "IGNORED"

        print(
            f"  {name:5s}: "
            f"required = {req:10.2f}   "
            f"supplied = {app:10.2f}   "
            f"remaining = {rem:10.2f}   "
            f"{rule}"
        )

    missing_lines = []

    for i in optimized_indices:
        if remaining[i] > tolerance:
            missing_lines.append(
                f"{NUTRIENTS[i]}: required = {requirements[i]:.2f}, "
                f"supplied = {apport[i]:.2f}, "
                f"missing = {remaining[i]:.2f}"
            )

    if missing_lines:
        raise RuntimeError(
            "\nINVALID OPTIMIZATION RESULT.\n"
            "At least one optimized nutrient requirement is still missing.\n\n"
            + "\n".join(missing_lines)
        )

    return True


def objective(doses, requirements):
    """
    Kept for compatibility with the bigger code.

    The real optimizer is linprog inside optimize_fertilizers().
    """

    return 0.0


def make_constraints(requirements):
    """
    Kept for compatibility with the bigger code.
    """

    return []


def optimize_fertilizers(requirements, ph):
    """
    Find the best fertilizer combination.

    Rules:
        - Estiércol de Vacuno is always included.
        - Estiércol de Vacuno starts from minimum 4000 kg/ha.
        - Use only fertilizers allowed by pH.
        - Use maximum 5 fertilizers total, including Estiércol de Vacuno.
        - Optimize P2O5, K2O, N, CaO, and MgO.
        - Ignore S.
        - Molimax (20-20-20) and Molimax (16-16-16) have low priority.
        - All optimized nutrient requirements must be covered.
        - Excess nutrients are minimized as much as possible.
    """

    requirements = effective_requirements(requirements)

    combinations_to_test = generate_allowed_fertilizer_combinations(ph)

    best_result = None
    best_score = None
    best_combo = None

    print("\nSearching best fertilizer combination")
    print(f"pH = {ph}")
    print(f"pH class = {get_ph_class(ph)}")
    print(f"Mandatory fertilizer = {MANDATORY_FERTILIZER}")
    print(f"Estiércol minimum dose = {ESTIERCOL_MIN:.1f} kg/ha")
    print(f"Estiércol maximum dose = {ESTIERCOL_MAX:.1f} kg/ha")
    print(f"Maximum fertilizers used = {MAX_FERTILIZERS_USED}")

    print("\nAllowed fertilizers by pH:")
    for fertilizer_name in get_allowed_fertilizers(ph):
        print(f"  - {fertilizer_name}")

    print(f"\nCombinations to test = {len(combinations_to_test)}")

    for combo in combinations_to_test:
        result = solve_linear_program_for_combo(
            requirements=requirements,
            ph=ph,
            selected_fertilizers=combo,
        )

        if not result.success:
            continue

        try:
            validate_solution(
                requirements=requirements,
                doses=result.x,
                selected_fertilizers=combo,
            )
        except RuntimeError:
            continue

        score = score_solution(
            requirements=requirements,
            doses=result.x,
            selected_fertilizers=combo,
        )

        if best_score is None or score < best_score:
            best_score = score
            best_result = result
            best_combo = combo

    if best_result is None:
        raise RuntimeError(
            "\nNo feasible fertilizer combination was found.\n\n"
            "Possible reasons:\n"
            "  1. Requirements are too high.\n"
            "  2. pH removed too many fertilizers.\n"
            "  3. OTHER_FERTILIZER_MAX is too low.\n"
            "  4. ESTIERCOL_MAX is too low.\n"
            "  5. Estiércol de Vacuno is forced with minimum 4000 kg/ha.\n"
            "  6. S is ignored, but P2O5, K2O, N, CaO, and MgO must be satisfied.\n"
        )

    best_result.selected_fertilizers = best_combo
    best_result.best_score = best_score

    print("\nBest fertilizer combination found:")
    for fertilizer_name in best_combo:
        print(f"  - {fertilizer_name}")

    validate_solution(
        requirements=requirements,
        doses=best_result.x,
        selected_fertilizers=best_combo,
    )

    return best_result


def get_full_dose_vector(result):
    """
    Convert selected fertilizer result to full fertilizer vector.

    Fertilizers not selected by the optimizer are saved as zero.

    Output order is the same as FERTILIZER_NAMES:

        Estiércol de Vacuno
        Urea
        Nitrato de Amonio
        Fosfato Diamónico
        Cloruro de Potasio
        Sulfato de Potasio
        Sulfato de Potasio y Magnesio
        Molimax (20-20-20)
        Molimax (16-16-16)
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

    CSV headers use the exact fertilizer names needed by Excel.
    """

    if not result.success:
        raise RuntimeError(
            "Cannot save optimal values because optimization failed:\n"
            f"{result.message}"
        )

    full_doses = get_full_dose_vector(result)
    full_doses = np.round(full_doses, 1)

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

    validate_solution(
        requirements=requirements,
        doses=doses,
        selected_fertilizers=selected_fertilizers,
    )

    print("\nSelected fertilizers:")

    for fertilizer_name in selected_fertilizers:
        priority = ""

        if fertilizer_name == MANDATORY_FERTILIZER:
            priority = "MANDATORY"

        elif fertilizer_name in LOW_PRIORITY_FERTILIZERS:
            priority = "LOW PRIORITY"

        print(f"  - {fertilizer_name} {priority}")

    print("\nOriginal requirements:")
    print("Negative requirements are treated as zero.")
    print("P2O5, K2O, N, CaO, and MgO are optimized.")
    print("S is ignored because it is not measured.")

    for i, name in enumerate(NUTRIENTS):
        original = original_requirements[i]
        effective = requirements[i]

        if name == "S":
            opt_status = "IGNORED, NOT MEASURED"
        elif i in optimized_indices:
            opt_status = "OPTIMIZED"
        else:
            opt_status = "REPORTED ONLY"

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

        if fertilizer_name == MANDATORY_FERTILIZER:
            status += ", MANDATORY"

        print(
            f"  {fertilizer_name:35s}: "
            f"{dose:10.1f} kg/ha   "
            f"{dose / 50:8.1f} sacos/ha   "
            f"{status}"
        )

    print("\nNutrient balance:")
    print("Hard rule:")
    print("  supplied_i >= required_i for P2O5, K2O, N, CaO, and MgO")
    print("  Estiércol de Vacuno is always included with at least 4000 kg/ha.")
    print("Important:")
    print("  Because Estiércol is mandatory, some excess nutrients may be unavoidable.")
    print("  The optimizer minimizes excess, but it cannot remove nutrients already added by Estiércol.")
    print("Priority:")
    print("  P2O5 first, then K2O, then N, then CaO and MgO")
    print("S is ignored because it is not measured.")
    print(f"Reference tolerance for status: {EXCESS_TOLERANCE:.1f} kg/ha")

    all_required_covered = True

    for i, name in enumerate(NUTRIENTS):
        req = requirements[i]
        app = apport[i]
        rem = remaining[i]
        exc = excess[i]

        if name == "S":
            status = "IGNORED, NOT MEASURED"

        elif i in optimized_indices:
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
        print("  OK: P2O5, K2O, N, CaO, and MgO requirements are covered.")
        print(f"  OK: {MANDATORY_FERTILIZER} was included.")
    else:
        print("  WARNING: at least one optimized nutrient requirement is missing.")

    print("\nDebug information:")
    print(f"  pH-selected fertilizers: {selected_fertilizers}")
    print(f"  Best score: {result.best_score}")
    print(f"  Nutrients: {list(NUTRIENTS)}")
    print(f"  All fertilizers: {FERTILIZER_NAMES}")

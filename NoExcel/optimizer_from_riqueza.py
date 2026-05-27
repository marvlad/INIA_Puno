# optimizer_from_riqueza.py

from pathlib import Path
from itertools import combinations
import unicodedata
import re
import math

import numpy as np
import pandas as pd
from scipy.optimize import linprog


# ------------------------------------------------------------
# Files
# ------------------------------------------------------------

RIQUEZA_CSV = "config/Riqueza_Fert.csv"


# ------------------------------------------------------------
# Nutrient order used by optimizer
# ------------------------------------------------------------

NUTRIENTS = ["N", "P2O5", "K2O", "CaO", "MgO", "S"]


# ------------------------------------------------------------
# Fertilizer dose bounds
# ------------------------------------------------------------

ESTIERCOL_MIN = 4000.0
ESTIERCOL_MAX = 6000.0

OTHER_FERTILIZER_MIN = 0.0
OTHER_FERTILIZER_MAX = 3000.0


# ------------------------------------------------------------
# Optimizer settings
# ------------------------------------------------------------

MAX_FERTILIZERS_USED = 5
REQUIRED_FERTILIZER = "Estiércol de Vacuno"

REQUIRED_FERTILIZER_ALIASES = [
    "Estiércol de Vacuno",
    "Estiercol de Vacuno",
    "Estiércol Vacuno",
    "Estiercol Vacuno",
    "Estiércol de vaca",
    "Estiercol de vaca",
    "Guano de Vacuno",
    "Guano de vacuno",
]

# Only these are forced:
#   supplied >= required
# CaO, MgO and S are reported but not optimized.
OPTIMIZED_NUTRIENTS = ["P2O5", "K2O", "N"]

INITIAL_EXCESS_TOLERANCE = 0.0
EXCESS_TOLERANCE_STEP = 10.0
MAX_EXCESS_TOLERANCE = 1000.0

LOW_PRIORITY_FERTILIZERS = [
    "Molimax (20-20-20)",
    "Molimax (16-16-16)",
]

LOW_PRIORITY_PENALTY = 10000.0


# ------------------------------------------------------------
# Text / CSV helpers
# ------------------------------------------------------------

def normalize_text(value):
    """
    Normalize text for matching:
        - lowercase
        - remove accents
        - remove punctuation
        - collapse spaces
    """

    if value is None:
        return ""

    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = " ".join(text.split())

    return text


def normalize_name_for_match(value):
    return normalize_text(value)


def value_to_float(value, default=0.0):
    if value is None:
        return default

    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)

    text = str(value).strip()

    if text == "":
        return default

    if text.upper() in ["NO", "N/A", "NA", "-", "--", "#VALUE!"]:
        return default

    text = text.replace(",", ".")

    try:
        return float(text)
    except Exception:
        return default


def find_column(fieldnames, candidates):
    """
    Find a column by exact normalized match first, then partial match.
    """

    normalized_candidates = [
        normalize_text(candidate)
        for candidate in candidates
    ]

    # Exact normalized match
    for field in fieldnames:
        field_norm = normalize_text(field)

        if field_norm in normalized_candidates:
            return field

    # Partial match
    for field in fieldnames:
        field_norm = normalize_text(field)

        for candidate in normalized_candidates:
            if candidate in field_norm or field_norm in candidate:
                return field

    return None


def find_fertilizer_name_column(df):
    """
    Find the column that contains real fertilizer/product names.

    This is better than only using the header, because Riqueza_Fert.csv
    may have category columns or category rows such as:
        ESTIÉRCOLES
        FERTILIZANTES NITROGENADOS

    The correct column should contain names such as:
        Estiércol de Vacuno
        Urea
        Fosfato Diamónico
        Cloruro de Potasio
    """

    fieldnames = list(df.columns)

    known_fertilizer_words = [
        "estiercol",
        "vacuno",
        "guano",
        "urea",
        "fosfato",
        "diamonico",
        "diamónico",
        "cloruro",
        "potasio",
        "sulfato",
        "molimax",
        "nitrato",
        "amonio",
        "magnesio",
    ]

    best_col = None
    best_score = -1

    for col in fieldnames:
        score = 0

        values = df[col].dropna().astype(str).tolist()

        for value in values:
            value_norm = normalize_text(value)

            for word in known_fertilizer_words:
                if normalize_text(word) in value_norm:
                    score += 1

        if score > best_score:
            best_score = score
            best_col = col

    if best_col is not None and best_score > 0:
        return best_col

    print("\nCould not auto-detect fertilizer-name column.")
    print("Available columns:")
    for field in fieldnames:
        print(f"  - {repr(field)}")

    print("\nFirst 20 rows preview:")
    print(df.head(20).to_string())

    raise ValueError(
        "Could not find fertilizer name column in Riqueza_Fert.csv"
    )


def find_nutrient_column(fieldnames, nutrient):
    """
    Finds nutrient composition columns in Riqueza_Fert.csv.

    The CSV may use:
        N, P2O5, K2O, CaO, MgO, S

    or Spanish labels:
        Nitrógeno, Fósforo, Potasio, Calcio, Magnesio, Azufre
    """

    candidates = {
        "N": [
            "N",
            "Nitrogeno",
            "Nitrógeno",
            "N %",
            "N%",
            "Porcentaje N",
        ],
        "P2O5": [
            "P2O5",
            "P₂O₅",
            "Fosforo P2O5",
            "Fósforo P2O5",
            "Fosforo",
            "Fósforo",
            "P",
        ],
        "K2O": [
            "K2O",
            "K₂O",
            "Potasio K2O",
            "Potasio",
            "K",
        ],
        "CaO": [
            "CaO",
            "Calcio CaO",
            "Calcio",
            "Ca",
        ],
        "MgO": [
            "MgO",
            "Magnesio MgO",
            "Magnesio",
            "Mg",
        ],
        "S": [
            "S",
            "Azufre",
        ],
    }

    return find_column(fieldnames, candidates[nutrient])


def clean_fertilizer_name(value):
    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() == "nan":
        return ""

    return text


def row_has_any_nutrient(row_data):
    """
    True if at least one nutrient value is numeric and non-zero.

    This skips category/header rows such as:
        ESTIÉRCOLES
        FERTILIZANTES NITROGENADOS
        FERTILIZANTES FOSFATADOS
    """

    for nutrient in NUTRIENTS:
        value = value_to_float(row_data.get(nutrient), 0.0)

        if abs(value) > 1e-12:
            return True

    return False


def find_required_fertilizer_name(fertilizer_table, required_name):
    """
    Find required fertilizer ignoring accents/case and allowing aliases.
    """

    possible_names = [required_name] + REQUIRED_FERTILIZER_ALIASES
    possible_norms = [
        normalize_name_for_match(name)
        for name in possible_names
    ]

    for fertilizer_name in fertilizer_table:
        fertilizer_norm = normalize_name_for_match(fertilizer_name)

        if fertilizer_norm in possible_norms:
            return fertilizer_name

    return None


# ------------------------------------------------------------
# Load Riqueza_Fert.csv
# ------------------------------------------------------------

def load_fertilizer_table_from_csv(csv_file=RIQUEZA_CSV):
    """
    Load fertilizer composition table from config/Riqueza_Fert.csv.

    Expected logical format:

        Fertilizante,N,P2O5,K2O,CaO,MgO,S
        Estiércol de Vacuno,0.40,0.01,0.49,0.01,0.04,0.13
        Urea,46,0,0,0,0,0
        Fosfato Diamónico,18,46,0,0,0,0

    The file may contain category rows. Those are skipped automatically.
    """

    csv_file = Path(csv_file)

    if not csv_file.exists():
        raise FileNotFoundError(f"Riqueza_Fert.csv not found: {csv_file}")

    df = pd.read_csv(csv_file, encoding="utf-8-sig")
    fieldnames = list(df.columns)

    # Important:
    # Detect fertilizer name column by content, not only by header.
    name_col = find_fertilizer_name_column(df)

    print(f"\nUsing fertilizer name column: {name_col!r}")

    nutrient_cols = {}

    for nutrient in NUTRIENTS:
        col = find_nutrient_column(fieldnames, nutrient)
        nutrient_cols[nutrient] = col

    missing = [
        nutrient
        for nutrient, col in nutrient_cols.items()
        if col is None
    ]

    if missing:
        print("\nCould not find nutrient columns:")
        for nutrient in missing:
            print(f"  - {nutrient}")

        print("\nAvailable columns:")
        for field in fieldnames:
            print(f"  - {repr(field)}")

        print("\nFirst 20 rows preview:")
        print(df.head(20).to_string())

        raise ValueError("Missing nutrient columns in Riqueza_Fert.csv")

    print("\nUsing nutrient columns:")
    for nutrient, col in nutrient_cols.items():
        print(f"  {nutrient:5s} -> {col!r}")

    fertilizer_table = {}
    skipped_rows = []

    for _, row in df.iterrows():
        fertilizer_name = clean_fertilizer_name(row.get(name_col))

        if not fertilizer_name:
            continue

        data = {}

        for nutrient in NUTRIENTS:
            value = value_to_float(
                row.get(nutrient_cols[nutrient]),
                0.0,
            )
            data[nutrient] = value

        # Skip rows without nutrient composition.
        if not row_has_any_nutrient(data):
            skipped_rows.append(fertilizer_name)
            continue

        fertilizer_table[fertilizer_name] = data

    if not fertilizer_table:
        print("\nNo valid fertilizer rows were found.")
        print("\nFirst 30 rows preview:")
        print(df.head(30).to_string())

        raise ValueError("No fertilizer composition rows found.")

    required_exact_name = find_required_fertilizer_name(
        fertilizer_table,
        REQUIRED_FERTILIZER,
    )

    if required_exact_name is None:
        print("\nRows skipped because they had no nutrient values:")
        for name in skipped_rows[:50]:
            print(f"  - {name}")

        print("\nFertilizer rows loaded:")
        for name in fertilizer_table:
            print(f"  - {name}")

        raise ValueError(
            f"Required fertilizer {REQUIRED_FERTILIZER!r} was not found in {csv_file}.\n"
            "The loader searched also for aliases like:\n"
            "  Estiercol de Vacuno\n"
            "  Estiercol Vacuno\n"
            "  Guano de Vacuno\n"
            "Check the exact product name in Riqueza_Fert.csv."
        )

    # Rename internally to the expected name.
    if required_exact_name != REQUIRED_FERTILIZER:
        fertilizer_table[REQUIRED_FERTILIZER] = fertilizer_table.pop(
            required_exact_name
        )

    print("\nFertilizer rows loaded:")
    for name in fertilizer_table:
        print(f"  - {name}")

    return fertilizer_table


# ------------------------------------------------------------
# pH rules
# ------------------------------------------------------------

PH_ALLOWED_OVERRIDES = {
    "Estiércol de Vacuno": {
        "acid": True,
        "neutral": True,
        "alkaline": True,
    },
    "Urea": {
        "acid": False,
        "neutral": True,
        "alkaline": True,
    },
    "Nitrato de Amonio": {
        "acid": True,
        "neutral": True,
        "alkaline": False,
    },
    "Fosfato Diamónico": {
        "acid": True,
        "neutral": True,
        "alkaline": True,
    },
    "Cloruro de Potasio": {
        "acid": True,
        "neutral": True,
        "alkaline": False,
    },
    "Sulfato de Potasio": {
        "acid": False,
        "neutral": True,
        "alkaline": True,
    },
    "Sulfato de Potasio y Magnesio": {
        "acid": False,
        "neutral": True,
        "alkaline": True,
    },
    "Molimax (20-20-20)": {
        "acid": True,
        "neutral": True,
        "alkaline": True,
    },
    "Molimax (16-16-16)": {
        "acid": True,
        "neutral": True,
        "alkaline": True,
    },
}


def get_ph_class(ph):
    ph = value_to_float(ph, None)

    if ph is None:
        raise ValueError("pH is required for fertilizer optimization.")

    if ph < 5.5:
        return "acid"

    if ph > 8.0:
        return "alkaline"

    return "neutral"


def fertilizer_allowed_for_ph(fertilizer_name, ph):
    ph_class = get_ph_class(ph)

    rules = PH_ALLOWED_OVERRIDES.get(fertilizer_name)

    if rules is None:
        # If no rule is defined, allow by default.
        return True

    return bool(rules.get(ph_class, True))


def get_allowed_fertilizers(fertilizer_names, ph):
    return [
        name
        for name in fertilizer_names
        if fertilizer_allowed_for_ph(name, ph)
    ]


# ------------------------------------------------------------
# Optimizer helpers
# ------------------------------------------------------------

def effective_requirements(requirements):
    """
    Negative requirements are treated as zero for optimization.
    """

    requirements = np.array(requirements, dtype=float)

    if requirements.ndim != 1:
        raise ValueError(
            f"requirements must be 1D. Current shape: {requirements.shape}"
        )

    if len(requirements) != len(NUTRIENTS):
        raise ValueError(
            f"requirements must have length {len(NUTRIENTS)}.\n"
            f"NUTRIENTS = {NUTRIENTS}\n"
            f"requirements length = {len(requirements)}"
        )

    return np.maximum(requirements, 0.0)


def get_optimized_nutrient_indices():
    return [
        NUTRIENTS.index(nutrient)
        for nutrient in OPTIMIZED_NUTRIENTS
    ]


def build_formula_from_table(selected_fertilizers, fertilizer_table):
    """
    Build fertilizer formula matrix.

    Rows:
        selected fertilizers

    Columns:
        N, P2O5, K2O, CaO, MgO, S

    CSV values are percentages. Converted to fractions.
    """

    formula = []

    for fertilizer_name in selected_fertilizers:
        if fertilizer_name not in fertilizer_table:
            raise ValueError(f"Unknown fertilizer: {fertilizer_name}")

        row = []

        for nutrient in NUTRIENTS:
            row.append(
                fertilizer_table[fertilizer_name].get(nutrient, 0.0)
            )

        formula.append(row)

    formula = np.array(formula, dtype=float)

    # Convert percentages to fractions.
    if np.nanmax(formula) > 1.0:
        formula = formula / 100.0

    return formula


def round_up_to_1_decimal(values):
    values = np.array(values, dtype=float)
    return np.ceil(values * 10.0 - 1e-9) / 10.0


def generate_allowed_fertilizer_combinations(ph, fertilizer_table):
    fertilizer_names = list(fertilizer_table.keys())

    allowed_fertilizers = get_allowed_fertilizers(
        fertilizer_names,
        ph,
    )

    if REQUIRED_FERTILIZER not in allowed_fertilizers:
        raise RuntimeError(
            f"{REQUIRED_FERTILIZER} is required, but not allowed for pH={ph}."
        )

    optional_fertilizers = [
        name
        for name in allowed_fertilizers
        if name != REQUIRED_FERTILIZER
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
    bounds = []

    for fertilizer_name in selected_fertilizers:
        if not fertilizer_allowed_for_ph(fertilizer_name, ph):
            bounds.append((0.0, 0.0))

        elif fertilizer_name == REQUIRED_FERTILIZER:
            bounds.append((ESTIERCOL_MIN, ESTIERCOL_MAX))

        else:
            bounds.append((OTHER_FERTILIZER_MIN, OTHER_FERTILIZER_MAX))

    return bounds


def nutrient_apport(doses, selected_fertilizers, fertilizer_table):
    doses = np.array(doses, dtype=float)

    if doses.ndim != 1:
        raise ValueError(f"doses must be 1D. Current shape: {doses.shape}")

    if len(doses) != len(selected_fertilizers):
        raise ValueError(
            "doses length must match selected_fertilizers length."
        )

    formula = build_formula_from_table(
        selected_fertilizers,
        fertilizer_table,
    )

    return doses @ formula


def validate_solution(
    requirements,
    doses,
    selected_fertilizers,
    fertilizer_table,
    excess_tolerance=None,
    tolerance=1e-6,
):
    """
    For P2O5, K2O, and N:

        supplied >= required

    If excess_tolerance is given:

        supplied <= required + excess_tolerance

    CaO, MgO, and S are ignored.
    """

    requirements = effective_requirements(requirements)
    apport = nutrient_apport(
        doses,
        selected_fertilizers,
        fertilizer_table,
    )

    optimized_indices = get_optimized_nutrient_indices()
    errors = []

    for idx in optimized_indices:
        nutrient = NUTRIENTS[idx]
        req = requirements[idx]
        supplied = apport[idx]

        if supplied + tolerance < req:
            errors.append(
                f"{nutrient}: supplied {supplied:.2f} < required {req:.2f}"
            )

        if excess_tolerance is not None:
            if supplied > req + excess_tolerance + tolerance:
                errors.append(
                    f"{nutrient}: supplied {supplied:.2f} > "
                    f"required {req:.2f} + tolerance {excess_tolerance:.2f}"
                )

    if errors:
        raise RuntimeError("\n".join(errors))

    return True


def solve_linear_program_for_combo(
    requirements,
    ph,
    selected_fertilizers,
    fertilizer_table,
    excess_tolerance,
):
    requirements = effective_requirements(requirements)
    formula = build_formula_from_table(
        selected_fertilizers,
        fertilizer_table,
    )

    optimized_indices = get_optimized_nutrient_indices()

    A_ub = []
    b_ub = []

    for nutrient_index in optimized_indices:
        req = requirements[nutrient_index]
        nutrient_vector = formula[:, nutrient_index]

        # supplied >= required
        # -supplied <= -required
        A_ub.append(-nutrient_vector)
        b_ub.append(-req)

        # supplied <= required + excess_tolerance
        A_ub.append(nutrient_vector)
        b_ub.append(req + excess_tolerance)

    bounds = make_bounds_for_combo(
        selected_fertilizers,
        ph,
    )

    c = np.zeros(len(selected_fertilizers), dtype=float)

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


def solution_priority_key(
    requirements,
    doses,
    selected_fertilizers,
    fertilizer_table,
):
    requirements = effective_requirements(requirements)

    apport = nutrient_apport(
        doses,
        selected_fertilizers,
        fertilizer_table,
    )

    excess = np.maximum(apport - requirements, 0.0)

    key = []

    for nutrient_name in OPTIMIZED_NUTRIENTS:
        idx = NUTRIENTS.index(nutrient_name)
        key.append(round(float(excess[idx]), 8))

    molimax_count = sum(
        1
        for name in selected_fertilizers
        if name in LOW_PRIORITY_FERTILIZERS
    )

    molimax_dose = sum(
        float(dose)
        for name, dose in zip(selected_fertilizers, doses)
        if name in LOW_PRIORITY_FERTILIZERS
    )

    key.append(molimax_count)
    key.append(round(molimax_dose, 8))
    key.append(len(selected_fertilizers))
    key.append(round(float(np.sum(doses)), 8))

    return tuple(key)


# ------------------------------------------------------------
# Main optimizer
# ------------------------------------------------------------

def optimize_fertilizers(requirements, ph, riqueza_csv=RIQUEZA_CSV):
    """
    Main optimizer.

    Steps:
        1. Load fertilizer composition from Riqueza_Fert.csv.
        2. Force Estiércol de Vacuno.
        3. Optimize P2O5, K2O, and N only.
        4. Treat negative requirements as zero.
        5. Try tolerance 0, 10, 20, ...
    """

    fertilizer_table = load_fertilizer_table_from_csv(riqueza_csv)
    original_requirements = effective_requirements(requirements)

    tolerance_values = np.arange(
        INITIAL_EXCESS_TOLERANCE,
        MAX_EXCESS_TOLERANCE + EXCESS_TOLERANCE_STEP,
        EXCESS_TOLERANCE_STEP,
        dtype=float,
    )

    last_error = None

    for excess_tolerance in tolerance_values:
        combinations_to_test = generate_allowed_fertilizer_combinations(
            ph=ph,
            fertilizer_table=fertilizer_table,
        )

        best_result = None
        best_key = None
        best_combo = None

        print("\n" + "#" * 80)
        print(f"TRYING EXCESS TOLERANCE = {excess_tolerance:.1f} kg/ha")
        print("#" * 80)
        print(f"pH = {ph}")
        print(f"pH class = {get_ph_class(ph)}")
        print(f"Combinations to test = {len(combinations_to_test)}")
        print(f"Nutrients optimized = {OPTIMIZED_NUTRIENTS}")
        print("Ignored nutrients = CaO, MgO, S")

        for combo in combinations_to_test:
            result = solve_linear_program_for_combo(
                requirements=original_requirements,
                ph=ph,
                selected_fertilizers=combo,
                fertilizer_table=fertilizer_table,
                excess_tolerance=excess_tolerance,
            )

            if not result.success:
                continue

            rounded_doses = round_up_to_1_decimal(result.x)

            try:
                validate_solution(
                    requirements=original_requirements,
                    doses=rounded_doses,
                    selected_fertilizers=combo,
                    fertilizer_table=fertilizer_table,
                    excess_tolerance=excess_tolerance,
                )
            except RuntimeError as err:
                last_error = str(err)
                continue

            key = solution_priority_key(
                requirements=original_requirements,
                doses=rounded_doses,
                selected_fertilizers=combo,
                fertilizer_table=fertilizer_table,
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
            best_result.fertilizer_table = fertilizer_table
            best_result.excess_tolerance_used = excess_tolerance

            print("\nVALID OPTIMIZATION FOUND")
            print(f"Excess tolerance used: {excess_tolerance:.1f} kg/ha")

            return best_result

        print(
            "\nNo valid solution found with "
            f"excess tolerance = {excess_tolerance:.1f} kg/ha."
        )
        print(
            f"Increasing tolerance by {EXCESS_TOLERANCE_STEP:.1f} kg/ha..."
        )

    error_message = (
        "\nOptimization failed.\n"
        "No fertilizer combination could satisfy P2O5, K2O, and N.\n"
        f"Tolerance tested up to {MAX_EXCESS_TOLERANCE:.1f} kg/ha."
    )

    if last_error:
        error_message += "\n\nLast validation error:\n" + last_error

    raise RuntimeError(error_message)


# ------------------------------------------------------------
# Output helpers
# ------------------------------------------------------------

def get_full_dose_vector(result):
    fertilizer_names = list(result.fertilizer_table.keys())
    full_doses = np.zeros(len(fertilizer_names), dtype=float)

    for fertilizer_name, dose in zip(
        result.selected_fertilizers,
        result.x,
    ):
        idx = fertilizer_names.index(fertilizer_name)
        full_doses[idx] = dose

    return fertilizer_names, full_doses


def print_optimization_results(requirements, result):
    requirements_original = np.array(requirements, dtype=float)
    requirements_used = effective_requirements(requirements)
    fertilizer_table = result.fertilizer_table

    apport = nutrient_apport(
        result.x,
        result.selected_fertilizers,
        fertilizer_table,
    )

    print("\nOPTIMIZACIÓN DE FERTILIZANTES")
    print("=" * 100)
    print(f"Excess tolerance used: {result.excess_tolerance_used:.1f} kg/ha")

    print("\nRequerimientos:")
    print("Negative requirements are treated as zero for optimization.")

    for nutrient, original, used in zip(
        NUTRIENTS,
        requirements_original,
        requirements_used,
    ):
        print(
            f"  {nutrient:5s}: "
            f"original = {original:10.2f}   "
            f"used = {used:10.2f} kg/ha"
        )

    print("\nFertilizantes seleccionados:")

    for fertilizer_name, dose in zip(
        result.selected_fertilizers,
        result.x,
    ):
        print(
            f"  {fertilizer_name:35s}: "
            f"{dose:10.1f} kg/ha   "
            f"{dose / 50.0:8.1f} sacos/ha"
        )

    print("\nAporte de nutrientes:")

    for nutrient, req, supplied in zip(
        NUTRIENTS,
        requirements_used,
        apport,
    ):
        print(
            f"  {nutrient:5s}: "
            f"required = {req:10.2f}   "
            f"supplied = {supplied:10.2f}   "
            f"remaining = {req - supplied:10.2f}   "
            f"excess = {supplied - req:10.2f}"
        )

    print("\nFull fertilizer vector:")

    fertilizer_names, full_doses = get_full_dose_vector(result)

    for fertilizer_name, dose in zip(fertilizer_names, full_doses):
        status = "SELECTED" if fertilizer_name in result.selected_fertilizers else "NOT USED"

        print(
            f"  {fertilizer_name:35s}: "
            f"{dose:10.1f} kg/ha   "
            f"{dose / 50.0:8.1f} sacos/ha   "
            f"{status}"
        )


def save_optimization_csv(output_csv, requirements, result):
    """
    Save optimization result to CSV.

    Output columns:
        Fertilizante
        Dosis kg/ha
        Sacos/ha
        Selected
        N
        P2O5
        K2O
        CaO
        MgO
        S
    """

    fertilizer_names, full_doses = get_full_dose_vector(result)

    rows = []

    for fertilizer_name, dose in zip(fertilizer_names, full_doses):
        fertilizer_data = result.fertilizer_table[fertilizer_name]

        row = {
            "Fertilizante": fertilizer_name,
            "Dosis kg/ha": round(float(dose), 1),
            "Sacos/ha": round(float(dose) / 50.0, 2),
            "Selected": "YES" if fertilizer_name in result.selected_fertilizers else "NO",
        }

        for nutrient in NUTRIENTS:
            row[nutrient] = fertilizer_data.get(nutrient, 0.0)

        rows.append(row)

    df = pd.DataFrame(rows)

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    print(f"\nSaved optimization CSV: {output_csv}")

    return output_csv


def save_nutrient_balance_csv(output_csv, requirements, result):
    """
    Save nutrient balance to CSV.

    Output columns:
        Nutrient
        Required original
        Required used
        Supplied
        Remaining
        Excess
    """

    requirements_original = np.array(requirements, dtype=float)
    requirements_used = effective_requirements(requirements)

    apport = nutrient_apport(
        result.x,
        result.selected_fertilizers,
        result.fertilizer_table,
    )

    rows = []

    for nutrient, original, used, supplied in zip(
        NUTRIENTS,
        requirements_original,
        requirements_used,
        apport,
    ):
        rows.append({
            "Nutrient": nutrient,
            "Required original kg/ha": float(original),
            "Required used kg/ha": float(used),
            "Supplied kg/ha": float(supplied),
            "Remaining kg/ha": float(used - supplied),
            "Excess kg/ha": float(supplied - used),
        })

    df = pd.DataFrame(rows)

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    print(f"Saved nutrient balance CSV: {output_csv}")

    return output_csv

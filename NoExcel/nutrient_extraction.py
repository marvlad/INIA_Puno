# nutrient_extraction.py

from pathlib import Path
import csv
import math
import unicodedata


EXTRACTION_CSV = "config/Extraccion_Nut.csv"
CONVERSION_FACTORS_CSV = "config/fertilizer_conversion_factors.csv"


NUTRIENTS = [
    {
        "symbol": "N",
        "csv_keywords": ["nitrogeno"],
    },
    {
        "symbol": "P",
        "csv_keywords": ["fosforo"],
    },
    {
        "symbol": "K",
        "csv_keywords": ["potasio"],
    },
    {
        "symbol": "Ca",
        "csv_keywords": ["calcio"],
    },
    {
        "symbol": "Mg",
        "csv_keywords": ["magnesio"],
    },
    {
        "symbol": "S",
        "csv_keywords": ["azufre"],
    },
]


def normalize_text(value):
    if value is None:
        return ""

    value = str(value).strip().lower()

    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )

    value = " ".join(value.split())

    return value


def normalize_header(value):
    text = normalize_text(value)

    replacements = {
        "(": " ",
        ")": " ",
        "/": " ",
        "\\": " ",
        ".": " ",
        ",": " ",
        "%": " porcentaje ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = " ".join(text.split())

    return text


def value_to_float(value, default=None):
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


def find_column(fieldnames, exact_candidates=None, contains_all=None, contains_any=None):
    exact_candidates = exact_candidates or []
    contains_all = contains_all or []
    contains_any = contains_any or []

    normalized_map = {
        field: normalize_header(field)
        for field in fieldnames
    }

    for field, normalized in normalized_map.items():
        if normalized in exact_candidates:
            return field

    if contains_all:
        for field, normalized in normalized_map.items():
            if all(word in normalized for word in contains_all):
                return field

    if contains_any:
        for field, normalized in normalized_map.items():
            if any(word in normalized for word in contains_any):
                return field

    return None


def load_conversion_factors(csv_file=CONVERSION_FACTORS_CSV):
    csv_file = Path(csv_file)

    if not csv_file.exists():
        raise FileNotFoundError(f"Conversion factor CSV not found: {csv_file}")

    factors = {}

    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required = {"nutrient", "fertilizer_form", "factor"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(
                f"{csv_file} must contain columns: nutrient, fertilizer_form, factor"
            )

        for row in reader:
            nutrient = str(row.get("nutrient", "")).strip()
            fertilizer_form = str(row.get("fertilizer_form", "")).strip()
            factor = value_to_float(row.get("factor"))

            if not nutrient:
                continue

            if factor is None:
                raise ValueError(f"Invalid factor for nutrient {nutrient}: {row}")

            factors[nutrient] = {
                "fertilizer_form": fertilizer_form,
                "factor": factor,
            }

    return factors


def load_extraction_rows(csv_file=EXTRACTION_CSV):
    csv_file = Path(csv_file)

    if not csv_file.exists():
        raise FileNotFoundError(f"Extraction CSV not found: {csv_file}")

    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError(f"No headers found in CSV: {csv_file}")

        rows = list(reader)

    return reader.fieldnames, rows


def find_crop_row(cultivo, csv_file=EXTRACTION_CSV):
    fieldnames, rows = load_extraction_rows(csv_file)

    crop_col = find_column(
        fieldnames,
        exact_candidates=["nombre comun", "cultivo"],
        contains_all=["nombre", "comun"],
    )

    code_col = find_column(
        fieldnames,
        exact_candidates=["codigo"],
        contains_any=["codigo"],
    )

    if crop_col is None:
        raise ValueError(
            "Could not find crop column. Expected something like 'Nombre Común'."
        )

    cultivo_norm = normalize_text(cultivo)

    # Exact crop match
    for row in rows:
        crop_value = row.get(crop_col, "")
        if normalize_text(crop_value) == cultivo_norm:
            return row, fieldnames, crop_col, code_col

    # Partial crop match
    matches = []
    for row in rows:
        crop_value = row.get(crop_col, "")
        crop_norm = normalize_text(crop_value)

        if cultivo_norm in crop_norm or crop_norm in cultivo_norm:
            matches.append(row)

    if len(matches) == 1:
        return matches[0], fieldnames, crop_col, code_col

    if len(matches) > 1:
        print("\nMore than one crop matched. Be more specific.")
        for row in matches:
            code_text = row.get(code_col, "") if code_col else ""
            print(f"  - {code_text} | {row.get(crop_col, '')}")

        raise ValueError(f"Multiple matches found for cultivo={cultivo!r}")

    raise ValueError(f"No crop found for cultivo={cultivo!r}")


def find_rendimiento_column(fieldnames):
    col = find_column(
        fieldnames,
        exact_candidates=["rendimiento kg ha", "rendimiento"],
        contains_all=["rendimiento"],
    )

    if col is None:
        raise ValueError(
            "Could not find rendimiento column. Expected something like "
            "'Rendimiento (kg/ha)'."
        )

    return col


def find_nutrient_column(fieldnames, nutrient_info):
    for keyword in nutrient_info["csv_keywords"]:
        col = find_column(
            fieldnames,
            contains_all=[keyword],
        )

        if col is not None:
            return col

    raise ValueError(
        f"Could not find column for nutrient {nutrient_info['symbol']}"
    )


def build_nutrient_extraction_rows(
    cultivo,
    extraction_csv=EXTRACTION_CSV,
    conversion_factors_csv=CONVERSION_FACTORS_CSV,
):
    row, fieldnames, crop_col, code_col = find_crop_row(
        cultivo=cultivo,
        csv_file=extraction_csv,
    )

    factors = load_conversion_factors(conversion_factors_csv)

    rendimiento_col = find_rendimiento_column(fieldnames)

    rendimiento = value_to_float(row.get(rendimiento_col))

    if rendimiento is None:
        raise ValueError(
            f"Invalid rendimiento for cultivo {cultivo!r}: "
            f"{row.get(rendimiento_col)!r}"
        )

    crop_name = row.get(crop_col, "")
    crop_code = row.get(code_col, "") if code_col else ""

    result_rows = []

    for nutrient_info in NUTRIENTS:
        nutrient = nutrient_info["symbol"]

        nutrient_col = find_nutrient_column(
            fieldnames,
            nutrient_info,
        )

        requirement_kg_ton = value_to_float(row.get(nutrient_col))

        if requirement_kg_ton is None:
            requirement_kg_ton = 0.0

        estimated_requirement_kg_ha = requirement_kg_ton * rendimiento

        factor_info = factors.get(nutrient)

        if factor_info is None:
            raise ValueError(
                f"No conversion factor found for nutrient {nutrient}"
            )

        factor = factor_info["factor"]
        fertilizer_form = factor_info["fertilizer_form"]

        fertilizer_need = estimated_requirement_kg_ha * factor

        result_rows.append({
            "nutriente": nutrient,
            "requerimiento_kg_ton": requirement_kg_ton,
            "rendimiento_kg_ha": rendimiento,
            "requerimiento_estimado_kg_ha": estimated_requirement_kg_ha,
            "fc_forma_fertilizante": factor,
            "forma_fertilizante": fertilizer_form,
            "necesidad_forma_fertilizante": fertilizer_need,
        })

    return {
        "cultivo": crop_name,
        "codigo": crop_code,
        "rendimiento_kg_ha": rendimiento,
        "rows": result_rows,
    }


def format_number(value, digits=2):
    number = value_to_float(value)

    if number is None:
        return ""

    return f"{number:.{digits}f}"


def print_nutrient_extraction_table(cultivo):
    result = build_nutrient_extraction_rows(cultivo)

    print("\n" + "=" * 100)
    print(f"EXTRACCIÓN DE NUTRIENTES CULTIVO: {result['codigo']} {result['cultivo']}")
    print(f"Rendimiento estimado: {format_number(result['rendimiento_kg_ha'], 2)} kg/ha")
    print("=" * 100)

    print(
        f"{'Nutriente':<12}"
        f"{'Requerimiento (kg/ton)':>25}"
        f"{'Req. estimado (kg/ha)':>25}"
        f"{'FC':>10}"
        f"{'Forma':>10}"
        f"{'Necesidad fertilizante':>25}"
    )

    print("-" * 100)

    for item in result["rows"]:
        print(
            f"{item['nutriente']:<12}"
            f"{format_number(item['requerimiento_kg_ton'], 2):>25}"
            f"{format_number(item['requerimiento_estimado_kg_ha'], 1):>25}"
            f"{format_number(item['fc_forma_fertilizante'], 2):>10}"
            f"{item['forma_fertilizante']:>10}"
            f"{format_number(item['necesidad_forma_fertilizante'], 0):>25}"
        )


if __name__ == "__main__":
    print_nutrient_extraction_table("OLIVO")

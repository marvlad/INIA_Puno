# get_optimized_fertilization_by_name.py

import argparse
import sqlite3
import unicodedata
from pathlib import Path

from fertilization_dose import calculate_fertilization_dose
from nutrient_extraction import find_crop_row, value_to_float

from optimizer_from_riqueza import (
    NUTRIENTS,
    optimize_fertilizers,
    print_optimization_results,
)


DB_FILE = "database/inia_database.sqlite"
TABLE_NAME = "muestras"
EXTRACTION_CSV = "config/Extraccion_Nut.csv"
CONVERSION_FACTORS_CSV = "config/fertilizer_conversion_factors.csv"
RIQUEZA_CSV = "config/Riqueza_Fert.csv"


def normalize_text(value):
    if value is None:
        return ""

    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )
    text = " ".join(text.split())

    return text


def find_column_by_words(fieldnames, words):
    words = [normalize_text(w) for w in words]

    for field in fieldnames:
        field_norm = normalize_text(field)

        if all(word in field_norm for word in words):
            return field

    return None


def get_crop_period_months(cultivo, extraction_csv=EXTRACTION_CSV):
    """
    Get Periodo vegetativo (meses) from config/Extraccion_Nut.csv.
    """

    crop_row, fieldnames, crop_col, code_col = find_crop_row(
        cultivo=cultivo,
        csv_file=extraction_csv,
    )

    period_col = find_column_by_words(
        fieldnames,
        ["periodo", "vegetativo"],
    )

    if period_col is None:
        print("\nCould not find Periodo vegetativo column.")
        print("Available columns:")

        for field in fieldnames:
            print(f"  - {repr(field)}")

        raise ValueError(
            f"Could not find Periodo vegetativo column in {extraction_csv}"
        )

    period = value_to_float(crop_row.get(period_col))

    if period is None:
        raise ValueError(
            f"Invalid Periodo vegetativo for cultivo={cultivo!r}: "
            f"{crop_row.get(period_col)!r}"
        )

    return period


def get_row_by_name_and_crop(db_file, name, cultivo):
    """
    Search one row in SQLite using name and cultivo.
    First exact normalized match, then partial normalized match.
    """

    db_file = Path(db_file)

    if not db_file.exists():
        raise FileNotFoundError(f"Database not found: {db_file}")

    name_norm = normalize_text(name)
    cultivo_norm = normalize_text(cultivo)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado = ?
              AND cultivo_normalizado = ?
            LIMIT 1
        """

        cur.execute(query, (name_norm, cultivo_norm))
        row = cur.fetchone()

        if row is not None:
            return dict(row)

        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado LIKE ?
              AND cultivo_normalizado LIKE ?
            LIMIT 1
        """

        cur.execute(query, (f"%{name_norm}%", f"%{cultivo_norm}%"))
        row = cur.fetchone()

        if row is not None:
            return dict(row)

    return None


def requirements_from_dose_result(dose_result):
    """
    Convert dose_result rows into optimizer order.

    optimizer NUTRIENTS:
        ["N", "P2O5", "K2O", "CaO", "MgO", "S"]

    fertilization_dose.py rows use:
        N, P, K, Ca, Mg, S
    """

    by_symbol = {
        item["nutriente"]: item
        for item in dose_result["rows"]
    }

    mapping = {
        "N": "N",
        "P2O5": "P",
        "K2O": "K",
        "CaO": "Ca",
        "MgO": "Mg",
        "S": "S",
    }

    requirements = []

    for optimizer_nutrient in NUTRIENTS:
        dose_symbol = mapping[optimizer_nutrient]

        value = by_symbol[dose_symbol]["requerimiento_final_fertilizante_kg_ha"]

        requirements.append(
            value_to_float(value, 0.0)
        )

    return requirements


def print_requirement_table(requirements):
    print("\nREQUERIMIENTO FINAL PARA OPTIMIZAR")
    print("=" * 80)

    for nutrient, req in zip(NUTRIENTS, requirements):
        print(f"{nutrient:5s}: {req:10.2f} kg/ha")


def main():
    parser = argparse.ArgumentParser(
        description="Calculate and optimize fertilization dose by name and crop."
    )

    parser.add_argument(
        "--name",
        required=True,
        help="NOMBRES Y APELLIDOS",
    )

    parser.add_argument(
        "--cultivo",
        required=True,
        help="CULTIVO A INSTALAR",
    )

    parser.add_argument(
        "--db",
        default=DB_FILE,
        help="SQLite database file.",
    )

    parser.add_argument(
        "--extraction-csv",
        default=EXTRACTION_CSV,
        help="Path to config/Extraccion_Nut.csv",
    )

    parser.add_argument(
        "--conversion-factors-csv",
        default=CONVERSION_FACTORS_CSV,
        help="Path to config/fertilizer_conversion_factors.csv",
    )

    parser.add_argument(
        "--riqueza-csv",
        default=RIQUEZA_CSV,
        help="Path to config/Riqueza_Fert.csv",
    )

    args = parser.parse_args()

    row = get_row_by_name_and_crop(
        db_file=args.db,
        name=args.name,
        cultivo=args.cultivo,
    )

    if row is None:
        raise ValueError(
            f"No record found for name={args.name!r}, cultivo={args.cultivo!r}"
        )

    cultivo = row.get("cultivo_a_instalar", args.cultivo)

    permanencia_meses = get_crop_period_months(
        cultivo=cultivo,
        extraction_csv=args.extraction_csv,
    )

    dose_result = calculate_fertilization_dose(
        row=row,
        permanencia_cultivo_meses=permanencia_meses,
        cultivo=cultivo,
        extraction_csv=args.extraction_csv,
        conversion_factors_csv=args.conversion_factors_csv,
    )

    requirements = requirements_from_dose_result(dose_result)

    print_requirement_table(requirements)

    result = optimize_fertilizers(
        requirements=requirements,
        ph=row.get("ph"),
        riqueza_csv=args.riqueza_csv,
    )

    print_optimization_results(
        requirements=requirements,
        result=result,
    )


if __name__ == "__main__":
    main()

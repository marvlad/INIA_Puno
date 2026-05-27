# get_fertilization_dose_by_name.py

import argparse
import sqlite3
import unicodedata
from pathlib import Path

from fertilization_dose import (
    calculate_fertilization_dose,
    format_number,
)

from nutrient_extraction import (
    find_crop_row,
    value_to_float,
)


DB_FILE = "database/inia_database.sqlite"
TABLE_NAME = "muestras"
EXTRACTION_CSV = "config/Extraccion_Nut.csv"
CONVERSION_FACTORS_CSV = "config/fertilizer_conversion_factors.csv"


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


def find_column_by_words(fieldnames, words):
    """
    Find a CSV column whose normalized name contains all words.
    Example:
        words = ["periodo", "vegetativo"]
        matches "Periodo vegetativo (meses)"
    """

    words = [normalize_text(w) for w in words]

    for field in fieldnames:
        field_norm = normalize_text(field)

        if all(word in field_norm for word in words):
            return field

    return None


def get_crop_period_months(cultivo, extraction_csv=EXTRACTION_CSV):
    """
    Get Periodo vegetativo (meses) from Extraccion_Nut.csv.
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
        raise ValueError(
            "Could not find 'Periodo vegetativo (meses)' column "
            f"in {extraction_csv}"
        )

    period = value_to_float(crop_row.get(period_col))

    if period is None:
        raise ValueError(
            f"Invalid periodo vegetativo for cultivo={cultivo!r}: "
            f"{crop_row.get(period_col)!r}"
        )

    return period


def get_rows_by_name(db_file, name):
    """
    Search sample records by person name.
    First exact normalized match, then partial normalized match.
    """

    db_file = Path(db_file)

    if not db_file.exists():
        raise FileNotFoundError(f"Database not found: {db_file}")

    name_norm = normalize_text(name)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado = ?
        """

        cur.execute(query, (name_norm,))
        rows = cur.fetchall()

        if rows:
            return [dict(row) for row in rows]

        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado LIKE ?
        """

        cur.execute(query, (f"%{name_norm}%",))
        rows = cur.fetchall()

        return [dict(row) for row in rows]


def get_row_by_name_and_crop(db_file, name, cultivo):
    """
    Search one sample by person name and cultivo.
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


def print_fertilization_dose_by_row(
    row,
    extraction_csv=EXTRACTION_CSV,
    conversion_factors_csv=CONVERSION_FACTORS_CSV,
):
    """
    Print the complete fertilization dose table for one SQLite row.
    """

    cultivo = row.get("cultivo_a_instalar", "")

    if not cultivo:
        raise ValueError("This record does not have cultivo_a_instalar.")

    permanencia_meses = get_crop_period_months(
        cultivo=cultivo,
        extraction_csv=extraction_csv,
    )

    dose_result = calculate_fertilization_dose(
        row=row,
        permanencia_cultivo_meses=permanencia_meses,
        cultivo=cultivo,
        extraction_csv=extraction_csv,
        conversion_factors_csv=conversion_factors_csv,
    )

    print("\n" + "=" * 180)
    print("DATOS DE LA MUESTRA")
    print("=" * 180)
    print(f"Nombre:                 {row.get('nombres_y_apellidos', '')}")
    print(f"Cultivo en DB:          {row.get('cultivo_a_instalar', '')}")
    print(f"Cultivo tabla:          {dose_result['codigo_cultivo']} {dose_result['cultivo']}")
    print(f"Código laboratorio:     {row.get('codigo', '')}")
    print(f"pH:                     {row.get('ph', '')}")
    print(f"CICe:                   {row.get('cice_cmol_plus_kg', '')}")
    print(f"MO (%):                 {row.get('mo_porcentaje', '')}")
    print(f"Clase textural:         {row.get('clase_textural', '')}")
    print(f"Clima:                  {row.get('clima', '')}")
    print(f"Periodo vegetativo:     {permanencia_meses} meses")
    print(f"Rendimiento estimado:   {dose_result['rendimiento_kg_ha']} kg/ha")
    print(f"Índice de cosecha:      {dose_result['indice_cosecha']}")

    print("\nDOSIS DE FERTILIZACIÓN - RENDIMIENTO PROYECTADO")
    print("=" * 180)

    print(
        f"{'Nutriente':22s} "
        f"{'Elemental':>12s} "
        f"{'FD':>8s} "
        f"{'FC':>8s} "
        f"{'Suelo fert.':>14s} "
        f"{'Fruto':>12s} "
        f"{'Foliar':>12s} "
        f"{'Efic. %':>10s} "
        f"{'Req. final':>14s}"
    )

    print("-" * 180)

    for item in dose_result["rows"]:
        print(
            f"{item['nutriente_forma']:22s} "
            f"{format_number(item['cantidad_elemental_kg_ha'], 0):>12s} "
            f"{format_number(item['factor_disponibilidad'], 2):>8s} "
            f"{format_number(item['fc_forma_fertilizante'], 2):>8s} "
            f"{format_number(item['suministro_suelo_fertilizante_kg_ha'], 0):>14s} "
            f"{format_number(item['necesidad_fruto_fertilizante_kg_ha'], 0):>12s} "
            f"{format_number(item['necesidad_foliar_fertilizante_kg_ha'], 0):>12s} "
            f"{format_number(item['eficiencia_porcentaje'], 0):>10s} "
            f"{format_number(item['requerimiento_final_fertilizante_kg_ha'], 0):>14s}"
        )

    print("-" * 180)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Calculate complete fertilization dose by person name and crop."
        )
    )

    parser.add_argument(
        "--name",
        required=True,
        help="NOMBRES Y APELLIDOS",
    )

    parser.add_argument(
        "--cultivo",
        default=None,
        help="CULTIVO A INSTALAR. Recommended if the person has multiple records.",
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

    args = parser.parse_args()

    if args.cultivo:
        row = get_row_by_name_and_crop(
            db_file=args.db,
            name=args.name,
            cultivo=args.cultivo,
        )

        if row is None:
            raise ValueError(
                f"No record found for name={args.name!r}, "
                f"cultivo={args.cultivo!r}"
            )

        print_fertilization_dose_by_row(
            row=row,
            extraction_csv=args.extraction_csv,
            conversion_factors_csv=args.conversion_factors_csv,
        )

        return

    rows = get_rows_by_name(
        db_file=args.db,
        name=args.name,
    )

    if not rows:
        raise ValueError(f"No record found for name={args.name!r}")

    if len(rows) > 1:
        print("\nMore than one record found for this name.")
        print("Use --cultivo to choose one.\n")

        for i, row in enumerate(rows, start=1):
            print(
                f"{i}. "
                f"{row.get('nombres_y_apellidos', '')} | "
                f"Cultivo: {row.get('cultivo_a_instalar', '')} | "
                f"Código: {row.get('codigo', '')} | "
                f"pH: {row.get('ph', '')} | "
                f"CICe: {row.get('cice_cmol_plus_kg', '')} | "
                f"Textura: {row.get('clase_textural', '')}"
            )

        return

    print_fertilization_dose_by_row(
        row=rows[0],
        extraction_csv=args.extraction_csv,
        conversion_factors_csv=args.conversion_factors_csv,
    )


if __name__ == "__main__":
    main()

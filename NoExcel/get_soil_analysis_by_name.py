# get_soil_analysis_by_name.py

import argparse
import sqlite3
import unicodedata
from pathlib import Path

from soil_characterization import (
    build_soil_analysis_table_rows,
    format_number,
)


DB_FILE = "database/inia_database.sqlite"
TABLE_NAME = "muestras"


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


def get_rows_by_name(db_file, name):
    db_file = Path(db_file)

    if not db_file.exists():
        raise FileNotFoundError(f"Database not found: {db_file}")

    name_norm = normalize_text(name)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # First try exact normalized name
        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado = ?
        """

        cur.execute(query, (name_norm,))
        rows = cur.fetchall()

        if rows:
            return [dict(row) for row in rows]

        # If exact name fails, try partial match
        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado LIKE ?
        """

        cur.execute(query, (f"%{name_norm}%",))
        rows = cur.fetchall()

        return [dict(row) for row in rows]


def get_row_by_name_and_crop(db_file, name, cultivo):
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


def print_soil_analysis(row):
    print("\n" + "=" * 80)
    print("DATOS DE LA MUESTRA")
    print("=" * 80)
    print(f"Nombre:      {row.get('nombres_y_apellidos', '')}")
    print(f"Cultivo:     {row.get('cultivo_a_instalar', '')}")
    print(f"Código:      {row.get('codigo', '')}")
    print(f"Laboratorio: {row.get('laboratorio', '')}")
    print(f"Textura:     {row.get('clase_textural', '')}")
    print(f"Clima:       {row.get('clima', '')}")

    rows = build_soil_analysis_table_rows(row)

    print("\nANÁLISIS DE SUELOS")
    print("-" * 80)
    print(f"{'CARACTERIZACIÓN':35s} {'UNIDAD':15s} {'VALOR':>12s}")
    print("-" * 80)

    for item in rows:
        value_text = format_number(
            item["valor"],
            digits=item.get("digits", 2),
        )

        print(
            f"{item['caracterizacion']:35s} "
            f"{item['unidad']:15s} "
            f"{value_text:>12s}"
        )

    print("-" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Return soil-analysis values from SQLite by name."
    )

    parser.add_argument(
        "--name",
        required=True,
        help="NOMBRES Y APELLIDOS",
    )

    parser.add_argument(
        "--cultivo",
        default=None,
        help="Optional: CULTIVO A INSTALAR. Use this if the person has multiple records.",
    )

    parser.add_argument(
        "--db",
        default=DB_FILE,
        help="SQLite database file.",
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
                f"No record found for name={args.name!r}, cultivo={args.cultivo!r}"
            )

        print_soil_analysis(row)
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
                f"Código: {row.get('codigo', '')}"
            )

        return

    print_soil_analysis(rows[0])


if __name__ == "__main__":
    main()

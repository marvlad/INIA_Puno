# get_efficiency_by_name.py

import argparse
import sqlite3
import unicodedata
from pathlib import Path

from config.get_efficiency import get_efficiencies


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


def print_efficiency_table(row):
    ph = row.get("ph")
    texture = row.get("clase_textural")

    if ph is None:
        raise ValueError("This record does not have pH value.")

    if texture is None or str(texture).strip() == "":
        raise ValueError("This record does not have clase_textural value.")

    efficiencies = get_efficiencies(
        ph=ph,
        texture=texture,
        decimals=0,
    )

    print("\n" + "=" * 60)
    print("DATOS DE LA MUESTRA")
    print("=" * 60)
    print(f"Nombre:  {row.get('nombres_y_apellidos', '')}")
    print(f"Cultivo: {row.get('cultivo_a_instalar', '')}")
    print(f"Código:  {row.get('codigo', '')}")
    print(f"pH:      {ph}")
    print(f"Textura: {texture}")

    print("\nEFICIENCIA FERTILIZANTES")
    print("-" * 35)
    print(f"{'Nutriente':<15} {'Eficiencia (%)':>15}")
    print("-" * 35)

    for nutrient in ["N", "P", "K", "Ca", "Mg", "S"]:
        print(f"{nutrient:<15} {efficiencies[nutrient]:>15.0f}")

    print("-" * 35)


def main():
    parser = argparse.ArgumentParser(
        description="Get fertilizer efficiency by person name from SQLite."
    )

    parser.add_argument(
        "--name",
        required=True,
        help="NOMBRES Y APELLIDOS",
    )

    parser.add_argument(
        "--cultivo",
        default=None,
        help="Optional crop name if person has multiple records.",
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

        print_efficiency_table(row)
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
                f"Textura: {row.get('clase_textural', '')}"
            )

        return

    print_efficiency_table(rows[0])


if __name__ == "__main__":
    main()

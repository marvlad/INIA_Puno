# load_db.py

from pathlib import Path
import sqlite3
import unicodedata
import re

from openpyxl import load_workbook


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

<<<<<<< Updated upstream
INPUT_EXCEL = "RESULTADOS USUARIOS 2M_Illpa_2.0.xlsx"
SHEET_NAME = "BD2024"
=======
INPUT_EXCEL = "RESULTADOS USUARIOS 2M_Illpa 2.0.2_CORREGIDO.xlsx"
SHEET_NAME = "Base_Datos"
>>>>>>> Stashed changes

OUTPUT_DB = "database/inia_database.sqlite"
TABLE_NAME = "muestras"

HEADER_ROW = 6
DATA_START_ROW = 7

START_COLUMN = "A"
END_COLUMN = "AT"


# ------------------------------------------------------------
# Text cleaning helpers
# ------------------------------------------------------------

def normalize_text(value):
    """
    Normalize text for safe searching:
    - lowercase
    - remove accents
    - remove repeated spaces
    """

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


def clean_su_code(value):
    """
    Clean SU codes.

    Some Excel files may contain values like:
        'SU001-IL-26

    This removes the leading apostrophe.
    """

    if value is None:
        return ""

    value = str(value).strip()

    if value.startswith("'"):
        value = value[1:]

    return value.strip().upper()


def make_sql_column_name(header, fallback_name):
    """
    Convert Excel headers into SQLite-safe column names.

    Example:
        "NOMBRES Y APELLIDOS" -> "nombres_y_apellidos"
        "pH" -> "ph"
        "C.E._mS/m" -> "ce_ms_m"
    """

    if header is None or str(header).strip() == "":
        return fallback_name

    text = str(header).strip().lower()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    text = text.replace("%", "porcentaje")
    text = text.replace("+", "plus")

    text = re.sub(r"[^a-zA-Z0-9]+", "_", text)
    text = text.strip("_")

    if text == "":
        return fallback_name

    if text[0].isdigit():
        text = f"col_{text}"

    return text


def make_unique_columns(headers):
    """
    Make column names unique.

    If two headers produce the same SQL name, add:
        _2, _3, etc.
    """

    seen = {}
    columns = []

    for i, header in enumerate(headers, start=1):
        base = make_sql_column_name(header, f"col_{i}")

        if base not in seen:
            seen[base] = 1
            columns.append(base)
        else:
            seen[base] += 1
            columns.append(f"{base}_{seen[base]}")

    return columns


def convert_value(value):
    """
    Convert Excel values into SQLite-friendly values.
    """

    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()

        if value == "":
            return None

        # Keep text as text.
        return value

    return value


# ------------------------------------------------------------
# Main loader
# ------------------------------------------------------------

def load_excel_to_sqlite(
    input_excel=INPUT_EXCEL,
    output_db=OUTPUT_DB,
    sheet_name=SHEET_NAME,
):
    input_excel = Path(input_excel)
    output_db = Path(output_db)

    if not input_excel.exists():
        raise FileNotFoundError(f"Excel file not found: {input_excel}")

    output_db.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("LOADING EXCEL DATABASE INTO SQLITE")
    print("=" * 80)
    print(f"Excel file: {input_excel}")
    print(f"Sheet: {sheet_name}")
    print(f"SQLite DB: {output_db}")
    print(f"Table: {TABLE_NAME}")
    print(f"Header range: {START_COLUMN}{HEADER_ROW}:{END_COLUMN}{HEADER_ROW}")
    print(f"Data starts at row: {DATA_START_ROW}")

    wb = None

    try:
        wb = load_workbook(
            input_excel,
            data_only=True,
            read_only=True,
        )

        if sheet_name not in wb.sheetnames:
            raise ValueError(
                f"Sheet not found: {sheet_name}\n"
                f"Available sheets: {wb.sheetnames}"
            )

        ws = wb[sheet_name]

        # ------------------------------------------------------------
        # Read headers from A6:AT6
        # ------------------------------------------------------------

        header_cells = ws[f"{START_COLUMN}{HEADER_ROW}:{END_COLUMN}{HEADER_ROW}"][0]

        original_headers = [
            cell.value
            for cell in header_cells
        ]

        sql_columns = make_unique_columns(original_headers)

        print("\nDetected columns:")
        for original, sql_name in zip(original_headers, sql_columns):
            print(f"  {original!r} -> {sql_name}")

        # ------------------------------------------------------------
        # Read data from row 7 down
        # ------------------------------------------------------------

        rows_to_insert = []

        min_col = header_cells[0].column
        max_col = header_cells[-1].column

        empty_row_count = 0
        max_empty_rows_allowed = 20

        for row in ws.iter_rows(
            min_row=DATA_START_ROW,
            min_col=min_col,
            max_col=max_col,
            values_only=True,
        ):
            values = [
                convert_value(value)
                for value in row
            ]

            # Stop after many empty rows.
            # This prevents reading forever in messy Excel files.
            if all(value is None for value in values):
                empty_row_count += 1

                if empty_row_count >= max_empty_rows_allowed:
                    break

                continue

            empty_row_count = 0

            rows_to_insert.append(values)

        print(f"\nRows found: {len(rows_to_insert)}")

    finally:
        if wb is not None:
            wb.close()

    # ------------------------------------------------------------
    # Add helper normalized columns
    # ------------------------------------------------------------

    extra_columns = [
        "nombre_normalizado",
        "cultivo_normalizado",
        "codigo_normalizado",
    ]

    final_columns = sql_columns + extra_columns

    # Try to identify important columns after SQL renaming.
    # These names should match your A6:AT6 headers after cleaning.
    nombre_col = None
    cultivo_col = None
    codigo_col = None

    for col in sql_columns:
        if col in ["nombres_y_apellidos", "nombre_y_apellidos"]:
            nombre_col = col

        if col in ["cultivo_a_instalar", "cultivo_instalar"]:
            cultivo_col = col

        if col == "codigo":
            codigo_col = col

    if nombre_col is None:
        print("\nWARNING: Could not find column for NOMBRES Y APELLIDOS")

    if cultivo_col is None:
        print("WARNING: Could not find column for CULTIVO A INSTALAR")

    if codigo_col is None:
        print("WARNING: Could not find column for CODIGO / CÓDIGO")

    # ------------------------------------------------------------
    # Build final rows with normalized helper values
    # ------------------------------------------------------------

    final_rows = []

    for values in rows_to_insert:
        row_dict = dict(zip(sql_columns, values))

        nombre_value = row_dict.get(nombre_col, "") if nombre_col else ""
        cultivo_value = row_dict.get(cultivo_col, "") if cultivo_col else ""
        codigo_value = row_dict.get(codigo_col, "") if codigo_col else ""

        final_row = list(values)

        final_row.append(normalize_text(nombre_value))
        final_row.append(normalize_text(cultivo_value))
        final_row.append(clean_su_code(codigo_value))

        final_rows.append(final_row)

    # ------------------------------------------------------------
    # Create SQLite table and insert rows
    # ------------------------------------------------------------

    with sqlite3.connect(output_db) as conn:
        cur = conn.cursor()

        cur.execute(f'DROP TABLE IF EXISTS "{TABLE_NAME}"')

        column_definitions = []

        column_definitions.append('"id" INTEGER PRIMARY KEY AUTOINCREMENT')

        for col in final_columns:
            column_definitions.append(f'"{col}"')

        create_sql = f'''
            CREATE TABLE "{TABLE_NAME}" (
                {", ".join(column_definitions)}
            )
        '''

        cur.execute(create_sql)

        quoted_columns = [
            f'"{col}"'
            for col in final_columns
        ]

        placeholders = ", ".join(["?"] * len(final_columns))

        insert_sql = f'''
            INSERT INTO "{TABLE_NAME}" (
                {", ".join(quoted_columns)}
            )
            VALUES ({placeholders})
        '''

        cur.executemany(insert_sql, final_rows)

        # Indexes for fast search
        cur.execute(
            f'CREATE INDEX IF NOT EXISTS idx_muestras_nombre '
            f'ON "{TABLE_NAME}" ("nombre_normalizado")'
        )

        cur.execute(
            f'CREATE INDEX IF NOT EXISTS idx_muestras_cultivo '
            f'ON "{TABLE_NAME}" ("cultivo_normalizado")'
        )

        cur.execute(
            f'CREATE INDEX IF NOT EXISTS idx_muestras_codigo '
            f'ON "{TABLE_NAME}" ("codigo_normalizado")'
        )

        conn.commit()

    print("\nSQLite database created successfully.")
    print(f"Database file: {output_db}")
    print(f"Table name: {TABLE_NAME}")
    print(f"Rows inserted: {len(final_rows)}")
    print(f"Columns inserted: {len(final_columns)}")


if __name__ == "__main__":
    load_excel_to_sqlite()

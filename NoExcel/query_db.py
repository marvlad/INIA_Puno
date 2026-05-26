# query_db.py

import sqlite3
import unicodedata
from pathlib import Path


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


def clean_su_code(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.startswith("'"):
        value = value[1:]

    return value.strip().upper()


def get_by_name_and_crop(name, cultivo):
    db_file = Path(DB_FILE)

    if not db_file.exists():
        raise FileNotFoundError(f"Database not found: {db_file}")

    name_norm = normalize_text(name)
    cultivo_norm = normalize_text(cultivo)

    query = f'''
        SELECT *
        FROM "{TABLE_NAME}"
        WHERE nombre_normalizado = ?
          AND cultivo_normalizado = ?
        LIMIT 5
    '''

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, (name_norm, cultivo_norm))
        rows = cur.fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_by_codigo(codigo):
    db_file = Path(DB_FILE)

    if not db_file.exists():
        raise FileNotFoundError(f"Database not found: {db_file}")

    codigo_norm = clean_su_code(codigo)

    query = f'''
        SELECT *
        FROM "{TABLE_NAME}"
        WHERE codigo_normalizado = ?
        LIMIT 5
    '''

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, (codigo_norm,))
        rows = cur.fetchall()

    return [
        dict(row)
        for row in rows
    ]


if __name__ == "__main__":
    rows = get_by_codigo("SU723-ILL-24")

    for row in rows:
        print(row)

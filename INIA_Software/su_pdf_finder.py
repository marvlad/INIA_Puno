# su_pdf_finder.py

import os
import re
import unicodedata
from pathlib import Path

from openpyxl import load_workbook

from utils import copy_file_to_dir


def norm(text):
    if text is None:
        return ""

    text = str(text).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.upper()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\n", " ")
    return text.strip()


def extract_su_number_from_text(text):
    """
    Extracts 723 from strings like:

        SU723-ILL-24
        SU0723-ILL-24
        SU 723
        SU723
        SU723-724
    """

    if not text:
        return None

    m = re.search(r"SU\s*0*(\d+)", str(text), re.IGNORECASE)

    if not m:
        return None

    return int(m.group(1))


def find_header_row(ws, required_header="NOMBRES Y APELLIDOS", max_rows=30):
    required = norm(required_header)

    for row_index, row in enumerate(
        ws.iter_rows(min_row=1, max_row=max_rows, values_only=True),
        start=1,
    ):
        normalized_row = [norm(cell) for cell in row]

        if required in normalized_row:
            return row_index, row

    raise ValueError(f"Could not find header row with: {required_header}")


def get_headers_from_values(header_row_values):
    headers = {}

    for index, value in enumerate(header_row_values, start=1):
        if value is not None:
            key = norm(value)
            headers.setdefault(key, []).append(index)

    return headers


def find_person_row(ws, headers, name, start_row):
    name_cols = headers.get(norm("NOMBRES Y APELLIDOS"))

    if name_cols is None:
        raise ValueError("Column 'NOMBRES Y APELLIDOS' was not found.")

    name_col = name_cols[0]
    possible_matches = []

    for row_index, row in enumerate(
        ws.iter_rows(min_row=start_row + 1, values_only=True),
        start=start_row + 1,
    ):
        cell_value = row[name_col - 1] if name_col - 1 < len(row) else None

        if norm(cell_value) == norm(name):
            return row_index, row

        if norm(name) in norm(cell_value) or norm(cell_value) in norm(name):
            possible_matches.append((row_index, cell_value))

    print(f"\nPersona no encontrada exactamente: {name}")

    if possible_matches:
        print("\nPosibles coincidencias:")
        for row_index, value in possible_matches:
            print(f"  Row {row_index}: {value}")

    raise ValueError("Person not found.")


def get_value_from_row(row_values, headers, header_name):
    cols = headers.get(norm(header_name))

    if cols is None:
        return None

    for col in cols:
        if col - 1 < len(row_values):
            value = row_values[col - 1]

            if value not in (None, ""):
                return value

    return None


def get_su_number_from_resultados_excel(resultados_excel, person_name):
    """
    Opens RESULTADOS USUARIOS 2M_Illpa_2.0.xlsx,
    finds the row for person_name,
    reads column CODIGO,
    and extracts the SU number.

    Example:
        CODIGO = SU723-ILL-24
        returns 723
    """

    resultados_excel = Path(resultados_excel).resolve()

    if not resultados_excel.exists():
        raise FileNotFoundError(f"RESULTADOS Excel file not found: {resultados_excel}")

    wb = load_workbook(resultados_excel, data_only=True, read_only=True)
    ws = wb.active

    header_row_number, header_row_values = find_header_row(ws)
    headers = get_headers_from_values(header_row_values)

    person_row_number, person_row_values = find_person_row(
        ws,
        headers,
        person_name,
        header_row_number,
    )

    codigo = get_value_from_row(person_row_values, headers, "CODIGO")
    su_number = extract_su_number_from_text(codigo)

    if su_number is None:
        raise ValueError(
            f"Could not extract SU number from CODIGO value: {codigo}"
        )

    print("\n[6] SU number extracted from RESULTADOS Excel")
    print(f"Person row: {person_row_number}")
    print(f"CODIGO: {codigo}")
    print(f"SU number: {su_number}")

    return su_number, codigo


def find_su_pdfs(su_number, folder_path):
    folder_path = Path(folder_path).resolve()

    if not folder_path.exists():
        raise FileNotFoundError(f"PDF folder not found: {folder_path}")

    range_pattern = re.compile(
        r"SU\s*0*(\d+)\s*(?:-\s*0*(\d+))?",
        re.IGNORECASE,
    )

    matches = []

    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if not filename.lower().endswith(".pdf"):
                continue

            m = range_pattern.search(filename)

            if not m:
                continue

            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else start

            if start <= su_number <= end:
                matches.append(Path(root) / filename)

    return matches


def copy_su_pdfs_to_report_dir(su_number, pdf_folder, report_dir):
    print("\n[7] Searching and copying original SU PDF files")

    if su_number is None:
        print("No SU number provided or detected. Skipping original PDF copy.")
        return []

    print(f"SU number: SU{su_number:04d}")
    print(f"Search folder: {pdf_folder}")

    matches = find_su_pdfs(su_number, pdf_folder)

    if not matches:
        print(f"No PDF found for SU{su_number:04d}")
        return []

    copied = []

    for pdf in matches:
        dst = copy_file_to_dir(pdf, report_dir)

        if dst:
            copied.append(dst)
            print(f"Copied: {pdf}")
            print(f"    to: {dst}")

    return copied

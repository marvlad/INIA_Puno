# excel_writer.py

from pathlib import Path
import csv

from openpyxl import load_workbook


# ------------------------------------------------------------
# Read vector from CSV
# ------------------------------------------------------------

def read_vector_from_csv(csv_file):
    """
    Reads a CSV containing fertilizer optimal values.

    It supports either:

    1) A simple one-row vector:
        10,20,30,40,50

    2) A CSV with one value per row:
        value
        10
        20
        30
        40
        50

    3) A CSV with a column named:
        value, values, dose, dosis, optimal, kg_ha, kg/ha
    """
    csv_file = Path(csv_file)

    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    values = []

    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        # Try DictReader first
        reader = csv.DictReader(f)

        if reader.fieldnames:
            normalized_headers = [
                str(h).strip().lower()
                for h in reader.fieldnames
                if h is not None
            ]

            possible_columns = [
                "value",
                "values",
                "dose",
                "dosis",
                "optimal",
                "kg_ha",
                "kg/ha",
            ]

            selected_column = None

            for col in possible_columns:
                if col in normalized_headers:
                    selected_column = reader.fieldnames[
                        normalized_headers.index(col)
                    ]
                    break

            if selected_column is not None:
                for row in reader:
                    raw_value = row.get(selected_column, "")

                    if raw_value is None or str(raw_value).strip() == "":
                        continue

                    values.append(
                        float(str(raw_value).replace(",", ".").strip())
                    )

                if values:
                    return values

        # If DictReader did not work, parse as normal CSV
        f.seek(0)
        reader2 = csv.reader(f)

        for row in reader2:
            for item in row:
                item = str(item).strip()

                if not item:
                    continue

                try:
                    values.append(float(item.replace(",", ".")))
                except ValueError:
                    # Skip headers or text
                    continue

    if not values:
        raise ValueError(f"No numeric values found in CSV: {csv_file}")

    return values


# ------------------------------------------------------------
# Write optimal vector to Excel
# ------------------------------------------------------------

def write_vector_to_excel(
    excel_file,
    csv_file,
    output_excel,
    sheet_name="Nec_fert",
    start_row=53,
    column="C",
):
    """
    Writes optimal fertilizer values from CSV into Excel.

    Default target:
        Nec_fert!C53:C57
    """
    excel_file = Path(excel_file)
    csv_file = Path(csv_file)
    output_excel = Path(output_excel)

    if not excel_file.exists():
        raise FileNotFoundError(f"Input Excel file not found: {excel_file}")

    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    values = read_vector_from_csv(csv_file)

    output_excel.parent.mkdir(parents=True, exist_ok=True)

    wb = load_workbook(excel_file)

    if sheet_name not in wb.sheetnames:
        raise ValueError(
            f"Sheet not found: {sheet_name}\n"
            f"Available sheets: {wb.sheetnames}"
        )

    ws = wb[sheet_name]

    for i, value in enumerate(values):
        ws[f"{column}{start_row + i}"] = value

    wb.save(output_excel)

    print("Values written to Excel:")
    print(f"  Input Excel: {excel_file}")
    print(f"  CSV values: {csv_file}")
    print(f"  Output Excel: {output_excel}")
    print(f"  Sheet: {sheet_name}")
    print(f"  Start cell: {column}{start_row}")
    print(f"  Number of values: {len(values)}")


# ------------------------------------------------------------
# Recalculate Excel with xlwings
# ------------------------------------------------------------

def recalculate_excel_with_xlwings(excel_file):
    """
    Open an Excel file with xlwings, force recalculation, save, and close.

    This is the simple working-style version.
    """
    import xlwings as xw

    excel_file = Path(excel_file).resolve()

    if not excel_file.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_file}")

    app = None
    wb = None

    try:
        app = xw.App(visible=False, add_book=False)
        app.display_alerts = False
        app.screen_updating = False

        wb = app.books.open(str(excel_file))

        # Force Excel recalculation
        app.calculate()

        wb.save()
        wb.close()
        wb = None

        print(f"Recalculated and saved: {excel_file}")

    finally:
        try:
            if wb is not None:
                wb.close()
        except Exception:
            pass

        try:
            if app is not None:
                app.quit()
        except Exception:
            pass

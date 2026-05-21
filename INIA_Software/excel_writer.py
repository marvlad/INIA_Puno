# excel_writer.py

from pathlib import Path
import csv
from openpyxl import load_workbook


# ------------------------------------------------------------
# Read fertilizer names and doses from CSV
# ------------------------------------------------------------
def read_fertilizer_names_and_doses_from_csv(csv_file):
    """
    Read fertilizer names and optimized doses from the CSV created by optimizer.py.

    Expected CSV format:

        Estiércol de Vacuno,Urea,Nitrato de Amonio,Fosfato Diamónico,...
        4000.0,0.0,0.0,300.5,...

    Returns only fertilizers with dose > 0:

        [
            ("Estiércol de Vacuno", 4000.0),
            ("Fosfato Diamónico", 300.5),
            ...
        ]
    """

    csv_file = Path(csv_file)

    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError(f"CSV file has no header: {csv_file}")

        rows = list(reader)

    if not rows:
        raise ValueError(f"CSV file has no data rows: {csv_file}")

    row = rows[0]

    fertilizer_data = []

    for fertilizer_name in reader.fieldnames:
        if fertilizer_name is None:
            continue

        fertilizer_name = str(fertilizer_name).strip()

        if fertilizer_name == "":
            continue

        raw_value = row.get(fertilizer_name, "")

        if raw_value is None:
            continue

        raw_value = str(raw_value).strip()

        if raw_value == "":
            continue

        try:
            dose = float(raw_value.replace(",", "."))
        except ValueError:
            continue

        # Only write fertilizers that were really selected.
        if dose > 0:
            fertilizer_data.append((fertilizer_name, dose))

    if not fertilizer_data:
        raise ValueError(
            f"No positive fertilizer doses found in CSV: {csv_file}"
        )

    return fertilizer_data


# ------------------------------------------------------------
# Read simple vector from CSV
# Kept for compatibility with the previous code.
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
# Write fertilizer names and optimal doses to Excel
# ------------------------------------------------------------
def write_vector_to_excel(
    excel_file,
    csv_file,
    output_excel,
    sheet_name="Nec_fert",
    start_row=53,
    end_row=59,
    name_column="B",
    dose_column="C",
):
    """
    Writes optimized fertilizer names and doses into Excel.

    The Excel fertilizer table in Nec_fert has rows:

        B53:C59

    Therefore this function only clears and writes rows 53 to 59.

    Default output:

        Nec_fert!B53 = fertilizer name 1
        Nec_fert!C53 = fertilizer dose 1

        Nec_fert!B54 = fertilizer name 2
        Nec_fert!C54 = fertilizer dose 2

        ...

        Nec_fert!B59 = fertilizer name 7
        Nec_fert!C59 = fertilizer dose 7

    The optimizer should normally return maximum 5 fertilizers, so rows 53 to 59
    are enough.
    """

    excel_file = Path(excel_file)
    csv_file = Path(csv_file)
    output_excel = Path(output_excel)

    if not excel_file.exists():
        raise FileNotFoundError(f"Input Excel file not found: {excel_file}")

    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    if end_row < start_row:
        raise ValueError(
            f"end_row must be >= start_row. Got start_row={start_row}, end_row={end_row}"
        )

    fertilizer_data = read_fertilizer_names_and_doses_from_csv(csv_file)

    available_rows = end_row - start_row + 1

    if len(fertilizer_data) > available_rows:
        raise ValueError(
            f"Too many fertilizers to write.\n"
            f"Excel has {available_rows} rows from {start_row} to {end_row}, "
            f"but optimizer returned {len(fertilizer_data)} fertilizers.\n"
            f"Fertilizers returned: {[name for name, _ in fertilizer_data]}"
        )

    output_excel.parent.mkdir(parents=True, exist_ok=True)

    wb = load_workbook(excel_file)

    if sheet_name not in wb.sheetnames:
        raise ValueError(
            f"Sheet not found: {sheet_name}\n"
            f"Available sheets: {wb.sheetnames}"
        )

    ws = wb[sheet_name]

    # ------------------------------------------------------------
    # Clean only the real fertilizer input table.
    #
    # IMPORTANT:
    # Do NOT clear start_row + 30.
    # In this template, rows below 59 contain merged/formatted cells.
    # Writing into those cells can produce:
    #
    # AttributeError: 'MergedCell' object attribute 'value' is read-only
    # ------------------------------------------------------------
    for row in range(start_row, end_row + 1):
        ws[f"{name_column}{row}"] = None
        ws[f"{dose_column}{row}"] = None

    # ------------------------------------------------------------
    # Fill B53:B59 and C53:C59
    # ------------------------------------------------------------
    for i, (fertilizer_name, dose) in enumerate(fertilizer_data):
        row = start_row + i

        ws[f"{name_column}{row}"] = fertilizer_name
        ws[f"{dose_column}{row}"] = round(dose, 1)

    wb.save(output_excel)

    print("\nFertilizer names and doses written to Excel:")
    print(f"  Input Excel: {excel_file}")
    print(f"  CSV values: {csv_file}")
    print(f"  Output Excel: {output_excel}")
    print(f"  Sheet: {sheet_name}")
    print(f"  First name cell: {name_column}{start_row}")
    print(f"  First dose cell: {dose_column}{start_row}")
    print(f"  Last row used by writer: {end_row}")
    print(f"  Available rows: {available_rows}")
    print(f"  Number of fertilizers written: {len(fertilizer_data)}")

    for i, (fertilizer_name, dose) in enumerate(fertilizer_data):
        row = start_row + i
        print(
            f"  {name_column}{row} = {fertilizer_name}   "
            f"{dose_column}{row} = {dose:.1f}"
        )


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

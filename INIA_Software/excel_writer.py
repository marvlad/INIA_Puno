# excel_writer.py

import csv
from pathlib import Path

import xlwings as xw
from openpyxl import load_workbook


def read_vector_from_csv(csv_file):
    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)

        header = next(reader)
        row = next(reader)

    values = []

    for x in row:
        x = x.strip()

        if x == "":
            continue

        values.append(round(float(x), 1))

    if len(values) != 5:
        raise ValueError(
            f"Expected 5 values, but found {len(values)}.\n"
            f"Header: {header}\n"
            f"Row: {row}\n"
            f"Values: {values}"
        )

    return values


def write_vector_to_excel(
    excel_file,
    csv_file,
    output_excel,
    sheet_name="Nec_fert",
    start_row=53,
    column="C",
):
    excel_file = Path(excel_file).resolve()
    csv_file = Path(csv_file).resolve()
    output_excel = Path(output_excel).resolve()

    print("\n[3] Writing optimal values to Excel")
    print(f"Input Excel: {excel_file}")
    print(f"Optimal CSV: {csv_file}")
    print(f"Output Excel: {output_excel}")

    values = read_vector_from_csv(csv_file)

    wb = load_workbook(excel_file)
    ws = wb[sheet_name]

    for i, value in enumerate(values):
        cell = f"{column}{start_row + i}"
        ws[cell] = value
        print(f"  {cell} = {value}")

    wb.save(output_excel)

    print(f"Saved optimized Excel: {output_excel}")

    return output_excel


def recalculate_excel_with_xlwings(excel_file):
    excel_file = Path(excel_file).resolve()

    print("\n[4] Recalculating optimized Excel with Excel")

    app = xw.App(visible=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(str(excel_file))
        app.calculate()
        wb.save()
        wb.close()

    finally:
        app.quit()

    print(f"Recalculated and saved: {excel_file}")

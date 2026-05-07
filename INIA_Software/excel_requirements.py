# excel_requirements.py

import csv
from pathlib import Path

import numpy as np
import xlwings as xw

from config import NUTRIENTS


def get_requirements_with_excel(excel_file, output_csv):
    excel_file = Path(excel_file).resolve()
    output_csv = Path(output_csv).resolve()

    if not excel_file.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_file}")

    print("\n[1] Reading requirements from Excel")
    print(f"Excel file: {excel_file}")

    app = xw.App(visible=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(str(excel_file))
        app.calculate()

        ws = wb.sheets["Nec_fert"]
        values = ws.range("J37:J42").value

        wb.save()
        wb.close()

    finally:
        app.quit()

    flat_values = []

    for v in values:
        if isinstance(v, list):
            flat_values.append(v[0])
        else:
            flat_values.append(v)

    rounded_values = [round(float(v)) for v in flat_values]

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(NUTRIENTS)
        writer.writerow(rounded_values)

    print(f"Saved requirements CSV: {output_csv}")
    print(dict(zip(NUTRIENTS, rounded_values)))

    return np.array(rounded_values, dtype=float)

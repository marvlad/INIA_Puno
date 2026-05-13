# test_original_template.py

from pathlib import Path
import xlwings as xw

template = Path(
    r"D:\INIA_CODE\INIA_Puno_Software_v1.0.0.2\INIA_Software\Software_Mejorado_Cultivos_Anuales_2025-2026_Arapa.xlsx"
)

print("Testing original template:")
print(template)

if not template.exists():
    raise FileNotFoundError(f"Template not found: {template}")

app = None
wb = None

try:
    app = xw.App(visible=True, add_book=False)
    app.display_alerts = False
    app.screen_updating = False

    wb = app.books.open(str(template))

    print("SUCCESS: Excel opened the original template.")
    print("Workbook name:", wb.name)

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

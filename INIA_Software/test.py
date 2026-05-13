from pathlib import Path
from openpyxl import load_workbook
import xlwings as xw

template = Path(r"D:\INIA_CODE\INIA_Puno_Software_v1.0.0.2\INIA_Software\Software_Mejorado_Cultivos_Anuales_2025-2026_Arapa.xlsx")
output = Path(r"C:\INIA_TEMPLATE_TEST.xlsx")

wb = load_workbook(template)
wb.save(output)

app = xw.App(visible=True, add_book=False)
book = app.books.open(str(output))
print("Opened successfully:", book.name)
book.close()
app.quit()

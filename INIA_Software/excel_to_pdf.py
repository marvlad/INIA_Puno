# excel_to_pdf.py

from pathlib import Path
import xlwings as xw


def export_excel_sheets_to_pdf(
    excel_file,
    output_pdf,
    sheets=("Gráfico_Int", "Rec_fert"),
):
    """
    Export selected Excel sheets to one PDF.

    Example:
        sheets=("Gráfico_Int", "Rec_fert")

    This creates a 2-page PDF if both sheets are selected
    and each sheet has its print area/page setup correctly.
    """

    excel_file = Path(excel_file).resolve()
    output_pdf = Path(output_pdf).resolve()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    if not excel_file.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_file}")

    app = xw.App(visible=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(str(excel_file))

        # Force calculation before export
        app.calculate()

        existing_sheets = [s.name for s in wb.sheets]

        selected_sheets = []

        for sheet_name in sheets:
            if sheet_name in existing_sheets:
                selected_sheets.append(sheet_name)
            else:
                print(f"WARNING: Sheet not found: {sheet_name}")

        if not selected_sheets:
            raise ValueError(
                f"None of the requested sheets were found: {sheets}"
            )

        # Page setup for each sheet
        for sheet_name in selected_sheets:
            ws = wb.sheets[sheet_name]

            # Use landscape because your layout is wide
            ws.api.PageSetup.Orientation = 2  # 1 portrait, 2 landscape

            # Fit each sheet to one page
            ws.api.PageSetup.Zoom = False
            ws.api.PageSetup.FitToPagesWide = 1
            ws.api.PageSetup.FitToPagesTall = 1

            # Optional margins
            ws.api.PageSetup.LeftMargin = app.api.InchesToPoints(0.15)
            ws.api.PageSetup.RightMargin = app.api.InchesToPoints(0.15)
            ws.api.PageSetup.TopMargin = app.api.InchesToPoints(0.15)
            ws.api.PageSetup.BottomMargin = app.api.InchesToPoints(0.15)

            # Optional: center on page
            ws.api.PageSetup.CenterHorizontally = True
            ws.api.PageSetup.CenterVertically = False

        # Select sheets together and export as one PDF
        wb.sheets[selected_sheets].api.Select()

        wb.api.ActiveSheet.ExportAsFixedFormat(
            Type=0,  # PDF
            Filename=str(output_pdf),
            Quality=0,
            IncludeDocProperties=True,
            IgnorePrintAreas=False,
            OpenAfterPublish=False,
        )

        wb.save()
        wb.close()

    finally:
        app.quit()

    print(f"Saved Excel PDF: {output_pdf}")
    return output_pdf

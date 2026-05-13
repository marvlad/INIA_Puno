# main.py

import argparse
from pathlib import Path

from excel_builder import build_excel_from_template
from excel_requirements import get_requirements_with_excel

from optimizer import (
    optimize_fertilizers,
    save_optimal_values_csv,
    print_optimization_results,
)

from excel_writer import (
    write_vector_to_excel,
    recalculate_excel_with_xlwings,
)

from excel_to_pdf import export_excel_sheets_to_pdf
from report_runner import generate_pdf_report

from su_pdf_finder import (
    get_su_info_from_resultados_excel,
    copy_su_pdfs_to_report_dir,
)

from utils import (
    safe_filename,
    make_report_directory,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Full fertilizer workflow: build Excel from RESULTADOS + template, "
            "read requirements, optimize fertilizer doses, write final Excel, "
            "export Excel sheets to PDF, generate report PDF, and copy original SU PDF reports."
        )
    )

    parser.add_argument(
        "--resultados-excel",
        default="RESULTADOS USUARIOS 2M_Illpa_2.0.xlsx",
        help=(
            "Main Excel database where the person data and CODIGO are stored. "
            "Example CODIGO: SU723-ILL-24."
        ),
    )

    parser.add_argument(
        "--template-excel",
        default="Software_Mejorado_Cultivos_Anuales_2025-2026_Arapa.xlsx",
        help="Base fertilizer Excel template.",
    )

    parser.add_argument(
        "--name",
        required=True,
        help='Person name, example: "Huaman Huaman Arturo".',
    )

    parser.add_argument(
        "--cultivo",
        required=True,
        help='Crop name, example: "PAPA MEJORADA".',
    )

    parser.add_argument(
        "--report-root",
        default="reports",
        help="Central output report directory.",
    )

    parser.add_argument(
        "--pdf-folder",
        default="",
        help="Folder where original SU PDF reports are located.",
    )

    parser.add_argument(
        "--report-script",
        default="report_pdf.py",
        help="Path to your existing PDF report generator script.",
    )

    parser.add_argument(
        "--excel-pdf-sheets",
        nargs="+",
        default=["Gráfico_Int", "Rec_fert"],
        help=(
            "Excel sheets to export into one PDF. "
            "Default: Gráfico_Int Rec_fert"
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    resultados_excel = Path(args.resultados_excel).resolve()
    template_excel = Path(args.template_excel).resolve()
    report_script = Path(args.report_script).resolve()

    if not resultados_excel.exists():
        raise FileNotFoundError(
            f"RESULTADOS Excel not found: {resultados_excel}"
        )

    if not template_excel.exists():
        raise FileNotFoundError(
            f"Template Excel not found: {template_excel}"
        )

    # ------------------------------------------------------------
    # Create central report directory
    # ------------------------------------------------------------
    report_dir = make_report_directory(
        args.report_root,
        args.name,
        args.cultivo,
    )

    print("=" * 80)
    print("FERTILIZER PIPELINE")
    print("=" * 80)
    print(f"Person: {args.name}")
    print(f"Cultivo: {args.cultivo}")
    print(f"RESULTADOS Excel: {resultados_excel}")
    print(f"Template Excel: {template_excel}")
    print(f"Report directory: {report_dir}")

    # ------------------------------------------------------------
    # Output files
    # ------------------------------------------------------------
    base_name = f"{safe_filename(args.name)}_{safe_filename(args.cultivo)}"

    filled_excel = report_dir / (
        f"Software_Mejorado_Cultivos_Anuales_2025-2026_Arapa_"
        f"{base_name}_FILLED.xlsx"
    )

    optimized_excel = report_dir / (
        f"Software_Mejorado_Cultivos_Anuales_2025-2026_Arapa_"
        f"{base_name}_OPTIMIZED.xlsx"
    )

    requirements_csv = report_dir / "requirements.csv"
    optimal_csv = report_dir / "optimal_values.csv"

    excel_pdf = report_dir / f"Excel_Report_{base_name}.pdf"
    output_pdf = report_dir / f"Informe_{base_name}.pdf"

    # Initialize variables for final summary
    generated_pdf = None
    copied_su_pdfs = []

    # ------------------------------------------------------------
    # 1. Build filled Excel from RESULTADOS + template
    # ------------------------------------------------------------
    print("\n[1] Building filled Excel from RESULTADOS + template")

    build_excel_from_template(
        resultados_excel=resultados_excel,
        template_excel=template_excel,
        name=args.name,
        cultivo=args.cultivo,
        output_excel=filled_excel,
        image_dir="extracted_images",
    )

    if not filled_excel.exists():
        raise FileNotFoundError(
            f"Filled Excel was not created: {filled_excel}"
        )

    print(f"Filled Excel created: {filled_excel}")

    # ------------------------------------------------------------
    # 2. Recalculate filled Excel before reading requirements
    # ------------------------------------------------------------
    print("\n[2] Recalculating filled Excel")

    recalculate_excel_with_xlwings(
        filled_excel,
        max_retries=5,
        wait_seconds=10,
        kill_excel_on_retry=True,
    )

    # ------------------------------------------------------------
    # 3. Read requirements from filled Excel: Nec_fert!J37:J42
    # ------------------------------------------------------------
    print("\n[3] Reading fertilizer requirements")

    requirements = get_requirements_with_excel(
        excel_file=filled_excel,
        output_csv=requirements_csv,
    )

    # ------------------------------------------------------------
    # 4. Optimize fertilizer values
    # ------------------------------------------------------------
    print("\n[4] Optimizing fertilizer doses")

    result = optimize_fertilizers(requirements)

    print_optimization_results(
        requirements,
        result,
    )

    save_optimal_values_csv(
        output_csv=optimal_csv,
        result=result,
    )

    # ------------------------------------------------------------
    # 5. Write optimal values to final Excel: Nec_fert!C53:C57
    # ------------------------------------------------------------
    print("\n[5] Writing optimized doses to final Excel")

    write_vector_to_excel(
        excel_file=filled_excel,
        csv_file=optimal_csv,
        output_excel=optimized_excel,
    )

    if not optimized_excel.exists():
        raise FileNotFoundError(
            f"Optimized Excel was not created: {optimized_excel}"
        )

    # ------------------------------------------------------------
    # 6. Recalculate optimized Excel
    # ------------------------------------------------------------
    print("\n[6] Recalculating optimized Excel")

    recalculate_excel_with_xlwings(
        optimized_excel,
        max_retries=5,
        wait_seconds=10,
        kill_excel_on_retry=True,
    )

    # ------------------------------------------------------------
    # 7. Export Excel sheets to PDF
    # Example: Gráfico_Int + Rec_fert -> 2-page PDF
    # ------------------------------------------------------------
    print("\n[7] Exporting Excel sheets to PDF")

    export_excel_sheets_to_pdf(
        excel_file=optimized_excel,
        output_pdf=excel_pdf,
        sheets=tuple(args.excel_pdf_sheets),
    )

    if not excel_pdf.exists():
        raise FileNotFoundError(
            f"Excel PDF was not created: {excel_pdf}"
        )

    # ------------------------------------------------------------
    # 8. Generate PDF report using report_pdf.py
    # ------------------------------------------------------------
    print("\n[8] Generating PDF report")

    generated_pdf = generate_pdf_report(
        report_script=report_script,
        name=args.name,
        cultivo=args.cultivo,
        output_pdf=output_pdf,
    )

    # ------------------------------------------------------------
    # 9. Do not copy original input Excel files
    # ------------------------------------------------------------
    print("\n[9] Skipping copy of original input Excel files")
    print("RESULTADOS Excel and template Excel will not be copied to the report directory.")

    # ------------------------------------------------------------
    # 10. Get SU information from RESULTADOS Excel
    # Example CODIGO: SU723-ILL-24 -> SU number 723, year 24
    # ------------------------------------------------------------
    if args.pdf_folder:
        print("\n[10] Getting SU information from RESULTADOS Excel")

        su_info = get_su_info_from_resultados_excel(
            resultados_excel=resultados_excel,
            person_name=args.name,
        )

        print("\nSU information:")
        print(f"  CODIGO: {su_info.get('codigo')}")
        print(f"  SU number: {su_info.get('su_number')}")
        print(f"  Year: {su_info.get('year')}")
        print(f"  Place: {su_info.get('place')}")
        print(f"  Lab: {su_info.get('lab')}")

        copied_su_pdfs = copy_su_pdfs_to_report_dir(
            su_info,
            args.pdf_folder,
            report_dir,
        )

    else:
        print("\nNo --pdf-folder provided. Skipping original SU PDF search.")

    # ------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------
    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)

    print("\nCentral report directory:")
    print(f"  {report_dir}")

    print("\nGenerated/copied files:")

    files_to_show = [
        requirements_csv,
        optimal_csv,
        filled_excel,
        optimized_excel,
        excel_pdf,
        generated_pdf,
    ]

    for file_path in files_to_show:
        if file_path:
            print(f"  {file_path}")

    for pdf_path in copied_su_pdfs:
        print(f"  {pdf_path}")


if __name__ == "__main__":
    main()

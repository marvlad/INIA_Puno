# main.py

import argparse
from pathlib import Path

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

from report_runner import generate_pdf_report

from su_pdf_finder import (
    get_su_number_from_resultados_excel,
    copy_su_pdfs_to_report_dir,
)

from utils import (
    safe_filename,
    make_report_directory,
    copy_file_to_dir,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Full fertilizer workflow: read Excel requirements, optimize doses, "
            "write optimized Excel, generate report PDF, and copy original SU PDFs."
        )
    )

    parser.add_argument(
        "--excel",
        required=True,
        help="Input Excel file already generated for the person/crop.",
    )

    parser.add_argument(
        "--name",
        required=True,
        help='Person name, example: "Huaman Huaman Arturo"',
    )

    parser.add_argument(
        "--cultivo",
        required=True,
        help='Crop name, example: "PAPA MEJORADA"',
    )

    parser.add_argument(
        "--resultados-excel",
        default="RESULTADOS USUARIOS 2M_Illpa_2.0.xlsx",
        help=(
            "Main input database Excel where CODIGO and person name are stored. "
            "The script reads CODIGO, for example SU723-ILL-24, and extracts 723."
        ),
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

    return parser.parse_args()


def main():
    args = parse_args()

    input_excel = Path(args.excel).resolve()
    resultados_excel = Path(args.resultados_excel).resolve()
    report_script = Path(args.report_script).resolve()

    if not input_excel.exists():
        raise FileNotFoundError(f"Input Excel not found: {input_excel}")

    if not resultados_excel.exists():
        raise FileNotFoundError(f"RESULTADOS Excel not found: {resultados_excel}")

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
    print(f"Report directory: {report_dir}")

    # ------------------------------------------------------------
    # Define output files
    # ------------------------------------------------------------

    requirements_csv = report_dir / "requirements.csv"
    optimal_csv = report_dir / "optimal_values.csv"

    output_excel = report_dir / f"{input_excel.stem}_OPTIMIZED.xlsx"

    output_pdf = report_dir / (
        f"Informe_{safe_filename(args.name)}_{safe_filename(args.cultivo)}.pdf"
    )

    # ------------------------------------------------------------
    # 1. Read requirements from Excel: Nec_fert!J37:J42
    # ------------------------------------------------------------

    requirements = get_requirements_with_excel(
        input_excel,
        requirements_csv,
    )

    # ------------------------------------------------------------
    # 2. Optimize fertilizer values
    # ------------------------------------------------------------

    result = optimize_fertilizers(requirements)

    print_optimization_results(
        requirements,
        result,
    )

    save_optimal_values_csv(
        optimal_csv,
        result,
    )

    # ------------------------------------------------------------
    # 3. Write optimal values to output Excel: Nec_fert!C53:C57
    # ------------------------------------------------------------

    write_vector_to_excel(
        excel_file=input_excel,
        csv_file=optimal_csv,
        output_excel=output_excel,
    )

    # ------------------------------------------------------------
    # 4. Recalculate optimized Excel with real Excel
    # ------------------------------------------------------------

    recalculate_excel_with_xlwings(output_excel)

    # ------------------------------------------------------------
    # 5. Generate PDF report using report_pdf.py
    # ------------------------------------------------------------

    generated_pdf = generate_pdf_report(
        report_script=report_script,
        name=args.name,
        cultivo=args.cultivo,
        output_pdf=output_pdf,
    )

    # ------------------------------------------------------------
    # 6. Copy original input Excel into report directory
    # ------------------------------------------------------------

    copied_input_excel = copy_file_to_dir(
        input_excel,
        report_dir,
    )

    # ------------------------------------------------------------
    # 7. Get SU number from RESULTADOS Excel column CODIGO
    #    Example CODIGO: SU723-ILL-24 -> SU number 723
    # ------------------------------------------------------------

    copied_su_pdfs = []

    if args.pdf_folder:
        su_number, codigo = get_su_number_from_resultados_excel(
            resultados_excel=args.resultados_excel,
            person_name=args.name,
        )

        print("\nSU information:")
        print(f"  CODIGO: {codigo}")
        print(f"  SU number: {su_number}")

        copied_su_pdfs = copy_su_pdfs_to_report_dir(
            su_number=su_number,
            pdf_folder=args.pdf_folder,
            report_dir=report_dir,
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
        copied_input_excel,
        output_excel,
        generated_pdf,
    ]

    for file_path in files_to_show:
        if file_path:
            print(f"  {file_path}")

    for pdf_path in copied_su_pdfs:
        print(f"  {pdf_path}")


if __name__ == "__main__":
    main()

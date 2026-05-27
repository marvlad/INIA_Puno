# generate_both_reports.py

import argparse
import subprocess
import sys
import unicodedata
from pathlib import Path

from pypdf import PdfReader, PdfWriter


OUTPUT_DIR = "final_reports"

STANDARD_LAB_SCRIPT = "standard_lab_report.py"
RECOMMENDATION_SCRIPT = "make_recommendation_by_name.py"


def normalize_text(value):
    if value is None:
        return ""

    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )
    text = " ".join(text.split())

    return text


def safe_filename(value):
    text = normalize_text(value)
    text = text.replace(" ", "_")

    allowed = []

    for char in text:
        if char.isalnum() or char in ["_", "-"]:
            allowed.append(char)

    text = "".join(allowed).strip("_")

    if not text:
        text = "reporte"

    return text


def run_command(command):
    print("\nRunning:")
    print(" ".join(command))
    print("-" * 80)

    result = subprocess.run(
        command,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}:\n"
            + " ".join(command)
        )


def merge_pdfs(pdf_files, output_pdf):
    """
    Merge multiple PDFs into one PDF.

    Parameters
    ----------
    pdf_files : list[str | Path]
        PDFs to merge, in order.

    output_pdf : str | Path
        Final merged PDF.
    """

    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    writer = PdfWriter()

    for pdf_file in pdf_files:
        pdf_file = Path(pdf_file)

        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_file}")

        reader = PdfReader(str(pdf_file))

        for page in reader.pages:
            writer.add_page(page)

    with open(output_pdf, "wb") as f:
        writer.write(f)

    return output_pdf


def generate_both_reports(
    name,
    cultivo,
    output_dir=OUTPUT_DIR,
    db=None,
    extraction_csv=None,
    conversion_factors_csv=None,
    riqueza_csv=None,
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = safe_filename(name)
    safe_crop = safe_filename(cultivo)

    lab_pdf = output_dir / f"lab_report_{safe_name}_{safe_crop}.pdf"
    recommendation_pdf = output_dir / f"recommendation_{safe_name}_{safe_crop}.pdf"
    merged_pdf = output_dir / f"full_report_{safe_name}_{safe_crop}.pdf"

    # ------------------------------------------------------------
    # 1. Standard lab report
    # ------------------------------------------------------------

    lab_command = [
        sys.executable,
        STANDARD_LAB_SCRIPT,
        "--name",
        name,
        "--cultivo",
        cultivo,
        "--output",
        str(lab_pdf),
    ]

    if db:
        lab_command.extend(["--db", db])

    run_command(lab_command)

    # ------------------------------------------------------------
    # 2. Fertilization recommendation report
    # ------------------------------------------------------------

    recommendation_command = [
        sys.executable,
        RECOMMENDATION_SCRIPT,
        "--name",
        name,
        "--cultivo",
        cultivo,
        "--output",
        str(recommendation_pdf),
    ]

    if db:
        recommendation_command.extend(["--db", db])

    if extraction_csv:
        recommendation_command.extend(["--extraction-csv", extraction_csv])

    if conversion_factors_csv:
        recommendation_command.extend([
            "--conversion-factors-csv",
            conversion_factors_csv,
        ])

    if riqueza_csv:
        recommendation_command.extend(["--riqueza-csv", riqueza_csv])

    run_command(recommendation_command)

    # ------------------------------------------------------------
    # 3. Merge both PDFs
    # ------------------------------------------------------------

    merge_pdfs(
        pdf_files=[
            lab_pdf,
            recommendation_pdf,
        ],
        output_pdf=merged_pdf,
    )

    print("\nReports generated:")
    print(f"  Standard lab report:        {lab_pdf}")
    print(f"  Recommendation report:      {recommendation_pdf}")
    print(f"  Merged final report:        {merged_pdf}")

    return lab_pdf, recommendation_pdf, merged_pdf


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate standard lab report, fertilization recommendation report, "
            "and merge both into one final PDF."
        )
    )

    parser.add_argument(
        "--name",
        required=True,
        help="NOMBRES Y APELLIDOS",
    )

    parser.add_argument(
        "--cultivo",
        required=True,
        help="CULTIVO A INSTALAR",
    )

    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Directory where PDFs will be saved.",
    )

    parser.add_argument(
        "--db",
        default=None,
        help="Optional SQLite database path.",
    )

    parser.add_argument(
        "--extraction-csv",
        default=None,
        help="Optional path to config/Extraccion_Nut.csv.",
    )

    parser.add_argument(
        "--conversion-factors-csv",
        default=None,
        help="Optional path to config/fertilizer_conversion_factors.csv.",
    )

    parser.add_argument(
        "--riqueza-csv",
        default=None,
        help="Optional path to config/Riqueza_Fert.csv.",
    )

    args = parser.parse_args()

    generate_both_reports(
        name=args.name,
        cultivo=args.cultivo,
        output_dir=args.output_dir,
        db=args.db,
        extraction_csv=args.extraction_csv,
        conversion_factors_csv=args.conversion_factors_csv,
        riqueza_csv=args.riqueza_csv,
    )


if __name__ == "__main__":
    main()

# report_runner.py

import subprocess
import sys
from pathlib import Path


def generate_pdf_report(report_script, name, cultivo, output_pdf):
    report_script = Path(report_script).resolve()
    output_pdf = Path(output_pdf).resolve()

    if not report_script.exists():
        print(f"WARNING: report script not found: {report_script}")
        print("Skipping PDF generation.")
        return None

    print("\n[5] Generating PDF report")
    print(f"Report script: {report_script}")
    print(f"Output PDF: {output_pdf}")

    cmd = [
        sys.executable,
        str(report_script),
        "--name",
        name,
        "--cultivo",
        cultivo,
        "--output",
        str(output_pdf),
    ]

    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
    )

    print("\n--- report_pdf.py STDOUT ---")
    print(result.stdout)

    if result.stderr.strip():
        print("\n--- report_pdf.py STDERR ---")
        print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError("PDF report generation failed.")

    if output_pdf.exists():
        print(f"Saved PDF report: {output_pdf}")
        return output_pdf

    print("WARNING: report_pdf.py finished, but output PDF was not found.")
    return None

# app.py

from flask import Flask, render_template, request
from pathlib import Path
import subprocess
import sys
import os

from products import ALLOWED_PRODUCTS

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_RESULTADOS_EXCEL = BASE_DIR / "RESULTADOS USUARIOS 2M_Illpa_2.0.xlsx"
DEFAULT_TEMPLATE_EXCEL = BASE_DIR / "Software_Mejorado_Cultivos_Anuales_2025-2026_Arapa.xlsx"
DEFAULT_REPORT_SCRIPT = BASE_DIR / "report_pdf.py"

DEFAULT_REPORT_ROOT = r"G:\Mi unidad\REPORTES_GENERADOS"
DEFAULT_PDF_FOLDER = r"G:\Mi unidad\LABSAF ILLPA\CAMPAÑA PERU 2M- LABSAF ILLPA\INFORMES DE ENSAYO"

@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        cultivos=ALLOWED_PRODUCTS,
        resultados_excel=str(DEFAULT_RESULTADOS_EXCEL),
        template_excel=str(DEFAULT_TEMPLATE_EXCEL),
        report_root=DEFAULT_REPORT_ROOT,
        pdf_folder=DEFAULT_PDF_FOLDER,
        report_script=str(DEFAULT_REPORT_SCRIPT),
    )


@app.route("/generate", methods=["POST"])
def generate():
    name = request.form.get("name", "").strip()
    cultivo = request.form.get("cultivo", "").strip()

    resultados_excel = request.form.get("resultados_excel", "").strip()
    template_excel = request.form.get("template_excel", "").strip()
    report_root = request.form.get("report_root", "").strip()
    pdf_folder = request.form.get("pdf_folder", "").strip()
    report_script = request.form.get("report_script", "").strip()

    if not name:
        return render_template(
            "result.html",
            success=False,
            message="Missing name.",
            stdout="",
            stderr="",
        )

    if not cultivo:
        return render_template(
            "result.html",
            success=False,
            message="Missing cultivo.",
            stdout="",
            stderr="",
        )

    cmd = [
        sys.executable,
        str(BASE_DIR / "main.py"),
        "--resultados-excel",
        resultados_excel,
        "--template-excel",
        template_excel,
        "--name",
        name,
        "--cultivo",
        cultivo,
        "--report-root",
        report_root,
        "--pdf-folder",
        pdf_folder,
        "--report-script",
        report_script,
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            text=True,
            capture_output=True,
            timeout=600,
        )

        success = result.returncode == 0

        if success:
            message = "Report generated successfully."
        else:
            message = "Report generation failed."

        return render_template(
            "result.html",
            success=success,
            message=message,
            stdout=result.stdout,
            stderr=result.stderr,
            command=" ".join(f'"{x}"' if " " in x else x for x in cmd),
        )

    except subprocess.TimeoutExpired as e:
        return render_template(
            "result.html",
            success=False,
            message="The process took too long and timed out.",
            stdout=e.stdout or "",
            stderr=e.stderr or "",
            command=" ".join(cmd),
        )

    except Exception as e:
        return render_template(
            "result.html",
            success=False,
            message=f"Unexpected error: {e}",
            stdout="",
            stderr="",
            command=" ".join(cmd),
        )


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )

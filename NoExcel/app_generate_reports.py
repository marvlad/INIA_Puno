# app_generate_reports.py

import argparse
import subprocess
import sys
from pathlib import Path

from flask import Flask, render_template, request, send_from_directory


app = Flask(__name__)
app.secret_key = "inia-generate-reports-secret-key"


DEFAULT_DB = "database/inia_database.sqlite"
DEFAULT_OUTPUT_DIR = "final_reports_ayaviri"
GENERATE_REPORTS_SCRIPT = "generate_reports_by_district.py"


def list_output_files(output_dir):
    output_dir = Path(output_dir)

    if not output_dir.exists():
        return []

    files = []

    for path in sorted(output_dir.glob("*")):
        if path.is_file() and path.suffix.lower() in [".pdf", ".csv", ".txt", ".log"]:
            files.append({
                "name": path.name,
                "size_kb": round(path.stat().st_size / 1024.0, 1),
            })

    return files


def run_generate_reports(form):
    district = form.get("district", "AYAVIRI").strip()
    db = form.get("db", DEFAULT_DB).strip()
    output_dir = form.get("output_dir", DEFAULT_OUTPUT_DIR).strip()

    extraction_csv = form.get("extraction_csv", "").strip()
    conversion_factors_csv = form.get("conversion_factors_csv", "").strip()
    riqueza_csv = form.get("riqueza_csv", "").strip()

    limit = form.get("limit", "").strip()

    skip_both = form.get("skip_both") == "on"
    skip_technical = form.get("skip_technical") == "on"
    technical_print_out = form.get("technical_print_out") == "on"
    technical_debug = form.get("technical_debug") == "on"

    command = [
        sys.executable,
        GENERATE_REPORTS_SCRIPT,
        "--district",
        district,
        "--db",
        db,
        "--output-dir",
        output_dir,
    ]

    if extraction_csv:
        command.extend(["--extraction-csv", extraction_csv])

    if conversion_factors_csv:
        command.extend(["--conversion-factors-csv", conversion_factors_csv])

    if riqueza_csv:
        command.extend(["--riqueza-csv", riqueza_csv])

    if limit:
        command.extend(["--limit", limit])

    if skip_both:
        command.append("--skip-both")

    if skip_technical:
        command.append("--skip-technical")

    if technical_print_out:
        command.append("--technical-print-out")

    if technical_debug:
        command.append("--technical-debug")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
    )

    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "output_dir": output_dir,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    files = []
    output_dir = request.form.get("output_dir", DEFAULT_OUTPUT_DIR)

    if request.method == "POST":
        result = run_generate_reports(request.form)
        output_dir = result["output_dir"]
        files = list_output_files(output_dir)
    else:
        files = list_output_files(output_dir)

    return render_template(
        "generate_reports.html",
        result=result,
        files=files,
        default_db=DEFAULT_DB,
        default_output_dir=DEFAULT_OUTPUT_DIR,
        output_dir=output_dir,
    )


@app.route("/download/<path:output_dir>/<path:filename>")
def download_file(output_dir, filename):
    return send_from_directory(
        output_dir,
        filename,
        as_attachment=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Browser app to run generate_reports_by_district.py"
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address.",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=5100,
        help="Port number.",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run Flask in debug mode.",
    )

    args = parser.parse_args()

    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()

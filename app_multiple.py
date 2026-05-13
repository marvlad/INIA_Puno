# app.py

from flask import Flask, render_template_string, request, redirect, url_for, jsonify
from pathlib import Path
import subprocess
import threading
import time
import os
import sys
import uuid


app = Flask(__name__)


# ------------------------------------------------------------
# Default paths
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DEFAULTS = {
    "batch_script": str(BASE_DIR / "run_main_from_csv_parallel.py"),
    "main_script": str(BASE_DIR / "main.py"),
    "resultados_excel": r"D:\INIA_CODE\INIA_Puno_Software_v1.0.0.2\INIA_Software\RESULTADOS USUARIOS 2M_Illpa 2.0.2.xlsx",
    "template_excel": r"D:\INIA_CODE\INIA_Puno_Software_v1.0.0.2\INIA_Software\Software_Mejorado_Cultivos_Anuales_2025-2026_Arapa.xlsx",
    "report_root": r"G:\Mi unidad\REPORTES_GENERADOS",
    "pdf_folder": r"G:\Mi unidad\LABSAF ILLPA\CAMPAÑA PERU 2M- LABSAF ILLPA\INFORMES DE ENSAYO",
    "report_script": str(BASE_DIR / "report_pdf.py"),
    "workers": "1",
    "delay_between_jobs": "10",
    "retries": "2",
}


UPLOAD_DIR = BASE_DIR / "uploads"
RUNS_DIR = BASE_DIR / "web_runs"

UPLOAD_DIR.mkdir(exist_ok=True)
RUNS_DIR.mkdir(exist_ok=True)


# ------------------------------------------------------------
# Runtime state
# ------------------------------------------------------------

current_run = {
    "running": False,
    "run_id": None,
    "log_file": None,
    "returncode": None,
    "started_at": None,
    "finished_at": None,
    "command": None,
}


# ------------------------------------------------------------
# HTML template
# ------------------------------------------------------------

HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>INIA Batch Report Generator</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 30px;
            background: #f6f7f9;
            color: #222;
        }

        .container {
            max-width: 1000px;
            margin: auto;
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        }

        h1 {
            margin-top: 0;
        }

        label {
            font-weight: bold;
            display: block;
            margin-top: 14px;
        }

        input[type="text"],
        input[type="number"],
        input[type="file"] {
            width: 100%;
            padding: 9px;
            margin-top: 5px;
            box-sizing: border-box;
        }

        .row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
        }

        .checkbox {
            margin-top: 15px;
        }

        button {
            margin-top: 22px;
            padding: 12px 18px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            background: #0b5ed7;
            color: white;
            font-size: 16px;
        }

        button:disabled {
            background: #999;
        }

        .status {
            margin-top: 20px;
            padding: 12px;
            background: #eef3ff;
            border-radius: 8px;
        }

        pre {
            background: #111;
            color: #eee;
            padding: 15px;
            border-radius: 8px;
            height: 420px;
            overflow: auto;
            white-space: pre-wrap;
        }

        .small {
            color: #666;
            font-size: 13px;
        }

        .warning {
            background: #fff3cd;
            padding: 10px;
            border-radius: 8px;
            margin-top: 12px;
        }
    </style>
</head>
<body>
<div class="container">
    <h1>INIA Batch Report Generator</h1>

    <p>
        Select the CSV file and click <b>Run batch</b>. The app will call
        <code>run_main_from_csv_parallel.py</code> automatically.
    </p>

    <div class="warning">
        Recommended settings for Excel/xlwings stability:
        <b>Workers = 1</b>, <b>Delay = 10 seconds</b>, <b>Retries = 2</b>.
    </div>

    {% if running %}
        <div class="status">
            <b>Status:</b> Running<br>
            <b>Run ID:</b> {{ run_id }}
        </div>
    {% elif finished %}
        <div class="status">
            <b>Status:</b> Finished<br>
            <b>Return code:</b> {{ returncode }}<br>
            <b>Run ID:</b> {{ run_id }}
        </div>
    {% else %}
        <div class="status">
            <b>Status:</b> Ready
        </div>
    {% endif %}

    <form action="/run" method="post" enctype="multipart/form-data">
        <label>Input CSV</label>
        <input type="file" name="input_csv" accept=".csv" required>

        <label>Batch script</label>
        <input type="text" name="batch_script" value="{{ defaults.batch_script }}">

        <div class="row">
            <div>
                <label>Main script</label>
                <input type="text" name="main_script" value="{{ defaults.main_script }}">
            </div>

            <div>
                <label>Report PDF script</label>
                <input type="text" name="report_script" value="{{ defaults.report_script }}">
            </div>
        </div>

        <label>RESULTADOS Excel</label>
        <input type="text" name="resultados_excel" value="{{ defaults.resultados_excel }}">

        <label>Template Excel</label>
        <input type="text" name="template_excel" value="{{ defaults.template_excel }}">

        <label>Report output folder</label>
        <input type="text" name="report_root" value="{{ defaults.report_root }}">

        <label>Original PDF folder</label>
        <input type="text" name="pdf_folder" value="{{ defaults.pdf_folder }}">

        <div class="row">
            <div>
                <label>Workers</label>
                <input type="number" name="workers" value="{{ defaults.workers }}" min="1" max="8">
            </div>

            <div>
                <label>Delay between jobs, seconds</label>
                <input type="number" name="delay_between_jobs" value="{{ defaults.delay_between_jobs }}" min="0">
            </div>
        </div>

        <label>Retries</label>
        <input type="number" name="retries" value="{{ defaults.retries }}" min="0">

        <div class="checkbox">
            <input type="checkbox" name="kill_excel_before_retry" checked>
            Kill Excel before retry
        </div>

        <div class="checkbox">
            <input type="checkbox" name="kill_excel_before_job">
            Kill Excel before every job
            <span class="small">(use only if Excel keeps freezing)</span>
        </div>

        <button type="submit" {% if running %}disabled{% endif %}>
            Run batch
        </button>
    </form>

    <h2>Live log</h2>
    <pre id="logbox">Loading log...</pre>
</div>

<script>
function updateLog() {
    fetch("/log")
        .then(response => response.json())
        .then(data => {
            document.getElementById("logbox").textContent = data.log || "";
        });
}

setInterval(updateLog, 2000);
updateLog();
</script>

</body>
</html>
"""


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def write_line(log_file, text):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def run_batch_in_background(command, log_file, run_id):
    global current_run

    write_line(log_file, "Starting batch...")
    write_line(log_file, "")
    write_line(log_file, "Command:")
    write_line(log_file, " ".join(f'"{x}"' if " " in x else x for x in command))
    write_line(log_file, "")
    write_line(log_file, "-" * 80)
    write_line(log_file, "")

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        with open(log_file, "a", encoding="utf-8", errors="replace") as f:
            for line in process.stdout:
                f.write(line)
                f.flush()

        returncode = process.wait()

    except Exception as e:
        returncode = -1
        write_line(log_file, "")
        write_line(log_file, "ERROR running batch:")
        write_line(log_file, str(e))

    current_run["running"] = False
    current_run["returncode"] = returncode
    current_run["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    write_line(log_file, "")
    write_line(log_file, "-" * 80)
    write_line(log_file, f"Finished with return code: {returncode}")


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(
        HTML,
        defaults=DEFAULTS,
        running=current_run["running"],
        finished=current_run["returncode"] is not None,
        returncode=current_run["returncode"],
        run_id=current_run["run_id"],
    )


@app.route("/run", methods=["POST"])
def run():
    global current_run

    if current_run["running"]:
        return redirect(url_for("index"))

    uploaded_file = request.files.get("input_csv")

    if uploaded_file is None or uploaded_file.filename.strip() == "":
        return "No CSV file uploaded", 400

    run_id = str(uuid.uuid4())[:8]
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    input_csv = run_dir / "input.csv"
    uploaded_file.save(input_csv)

    log_file = run_dir / "web_batch.log"

    batch_script = request.form.get("batch_script", DEFAULTS["batch_script"])
    main_script = request.form.get("main_script", DEFAULTS["main_script"])
    resultados_excel = request.form.get("resultados_excel", DEFAULTS["resultados_excel"])
    template_excel = request.form.get("template_excel", DEFAULTS["template_excel"])
    report_root = request.form.get("report_root", DEFAULTS["report_root"])
    pdf_folder = request.form.get("pdf_folder", DEFAULTS["pdf_folder"])
    report_script = request.form.get("report_script", DEFAULTS["report_script"])
    workers = request.form.get("workers", DEFAULTS["workers"])
    delay_between_jobs = request.form.get("delay_between_jobs", DEFAULTS["delay_between_jobs"])
    retries = request.form.get("retries", DEFAULTS["retries"])

    batch_logs_dir = run_dir / "batch_logs"

    command = [
        sys.executable,
        batch_script,

        "--input-csv",
        str(input_csv),

        "--main-script",
        main_script,

        "--resultados-excel",
        resultados_excel,

        "--template-excel",
        template_excel,

        "--report-root",
        report_root,

        "--pdf-folder",
        pdf_folder,

        "--report-script",
        report_script,

        "--workers",
        str(workers),

        "--delay-between-jobs",
        str(delay_between_jobs),

        "--retries",
        str(retries),

        "--logs-dir",
        str(batch_logs_dir),
    ]

    if request.form.get("kill_excel_before_retry"):
        command.append("--kill-excel-before-retry")

    if request.form.get("kill_excel_before_job"):
        command.append("--kill-excel-before-job")

    current_run = {
        "running": True,
        "run_id": run_id,
        "log_file": str(log_file),
        "returncode": None,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": None,
        "command": command,
    }

    thread = threading.Thread(
        target=run_batch_in_background,
        args=(command, log_file, run_id),
        daemon=True,
    )
    thread.start()

    return redirect(url_for("index"))


@app.route("/log")
def log():
    log_file = current_run.get("log_file")

    if not log_file or not Path(log_file).exists():
        return jsonify({"log": "No log yet."})

    try:
        text = Path(log_file).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        text = f"Could not read log: {e}"

    return jsonify({"log": text})


if __name__ == "__main__":
    app.run(debug=True)

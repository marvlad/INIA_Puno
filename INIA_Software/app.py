# app.py

from flask import Flask, render_template, request, jsonify, Response
from pathlib import Path
from werkzeug.utils import secure_filename

import subprocess
import threading
import queue
import sys
import os
import signal


# ------------------------------------------------------------
# Import crop/product list from products.py
# ------------------------------------------------------------
from products import ALLOWED_PRODUCTS


app = Flask(__name__)


# ------------------------------------------------------------
# Defaults
# ------------------------------------------------------------
DEFAULT_RESULTADOS_EXCEL = "RESULTADOS USUARIOS 2M_Illpa_2.0.xlsx"
DEFAULT_TEMPLATE_EXCEL = "Software_Mejorado_Cultivos_Anuales_2025-2026_Arapa.xlsx"
DEFAULT_REPORT_SCRIPT = "report_pdf.py"
DEFAULT_REPORT_ROOT = "reports"
DEFAULT_PDF_FOLDER = "pdfs"


# ------------------------------------------------------------
# Upload folder
# ------------------------------------------------------------
UPLOAD_DIR = Path("uploaded_inputs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# Crop/product options from products.py
# ------------------------------------------------------------
CULTIVOS = ALLOWED_PRODUCTS


# ------------------------------------------------------------
# Process state
# ------------------------------------------------------------
process = None
output_queue = queue.Queue()
process_lock = threading.Lock()


def clear_output_queue():
    """
    Clear old terminal output before starting a new process.
    """

    while not output_queue.empty():
        try:
            output_queue.get_nowait()
        except queue.Empty:
            break


def save_uploaded_file(file_storage, default_path):
    """
    Save uploaded file if the user selected one.

    If the user did not select a file, return the default path.
    """

    if file_storage is None:
        return default_path

    if file_storage.filename is None:
        return default_path

    if file_storage.filename.strip() == "":
        return default_path

    filename = secure_filename(file_storage.filename)

    if filename == "":
        return default_path

    saved_path = UPLOAD_DIR / filename
    file_storage.save(saved_path)

    return str(saved_path.resolve())


def enqueue_output(proc):
    """
    Read subprocess output line by line and send it to the queue.
    """

    try:
        for line in iter(proc.stdout.readline, ""):
            if line:
                output_queue.put(line.rstrip())
    except Exception as e:
        output_queue.put(f"[ERROR READING PROCESS OUTPUT] {e}")

    return_code = proc.wait()

    if return_code == 0:
        output_queue.put("[PROCESS_FINISHED]")
    else:
        output_queue.put(f"[PROCESS_FINISHED_WITH_ERROR] return code = {return_code}")


@app.route("/")
def index():
    return render_template(
        "index.html",
        cultivos=CULTIVOS,
        resultados_excel=DEFAULT_RESULTADOS_EXCEL,
        template_excel=DEFAULT_TEMPLATE_EXCEL,
        report_script=DEFAULT_REPORT_SCRIPT,
        report_root=DEFAULT_REPORT_ROOT,
        pdf_folder=DEFAULT_PDF_FOLDER,
    )


@app.route("/generate", methods=["POST"])
def generate():
    """
    Start report generation.

    Uploaded files are optional:
        - If uploaded, use uploaded file.
        - If not uploaded, use default file.
    """

    global process

    with process_lock:
        if process is not None and process.poll() is None:
            return jsonify({
                "ok": False,
                "error": "Ya hay un proceso ejecutándose. Deténlo antes de iniciar otro.",
            })

        clear_output_queue()

        name = request.form.get("name", "").strip()
        cultivo = request.form.get("cultivo", "").strip()

        if not name:
            return jsonify({
                "ok": False,
                "error": "El nombre es obligatorio.",
            })

        if not cultivo:
            return jsonify({
                "ok": False,
                "error": "El cultivo es obligatorio.",
            })

        # ------------------------------------------------------------
        # Uploaded files from index.html
        #
        # These names must match the HTML:
        #   resultados_excel_file
        #   template_excel_file
        #   report_script_file
        # ------------------------------------------------------------
        resultados_excel = save_uploaded_file(
            request.files.get("resultados_excel_file"),
            DEFAULT_RESULTADOS_EXCEL,
        )

        template_excel = save_uploaded_file(
            request.files.get("template_excel_file"),
            DEFAULT_TEMPLATE_EXCEL,
        )

        report_script = save_uploaded_file(
            request.files.get("report_script_file"),
            DEFAULT_REPORT_SCRIPT,
        )

        report_root = request.form.get(
            "report_root",
            DEFAULT_REPORT_ROOT,
        ).strip() or DEFAULT_REPORT_ROOT

        pdf_folder = request.form.get(
            "pdf_folder",
            DEFAULT_PDF_FOLDER,
        ).strip() or DEFAULT_PDF_FOLDER

        cmd = [
            sys.executable,
            "-u",
            "main.py",
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

        output_queue.put("Ejecutando comando:")
        output_queue.put(" ".join(f'"{x}"' if " " in x else x for x in cmd))
        output_queue.put("")
        output_queue.put(f"Base de Datos Excel: {resultados_excel}")
        output_queue.put(f"Plantilla de Excel: {template_excel}")
        output_queue.put(f"Script de reporte: {report_script}")
        output_queue.put(f"Carpeta de reportes: {report_root}")
        output_queue.put(f"Carpeta PDFs SU: {pdf_folder}")
        output_queue.put("")

        try:
            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 1,
                "universal_newlines": True,
                "cwd": Path(__file__).resolve().parent,
            }

            # On Linux/macOS, create a new process group
            # so /stop can kill child processes too.
            if os.name != "nt":
                popen_kwargs["preexec_fn"] = os.setsid

            # On Windows, create a new process group when possible.
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            process = subprocess.Popen(
                cmd,
                **popen_kwargs,
            )

            thread = threading.Thread(
                target=enqueue_output,
                args=(process,),
                daemon=True,
            )
            thread.start()

            return jsonify({"ok": True})

        except Exception as e:
            process = None
            return jsonify({
                "ok": False,
                "error": str(e),
            })


@app.route("/stream")
def stream():
    """
    Server-Sent Events endpoint for live terminal output.
    """

    def generate_events():
        while True:
            try:
                line = output_queue.get(timeout=0.5)

                # Avoid breaking SSE if a line contains newlines.
                line = str(line).replace("\r", "").replace("\n", " ")

                yield f"data: {line}\n\n"

                if (
                    "[PROCESS_FINISHED]" in line
                    or "[PROCESS_FINISHED_WITH_ERROR]" in line
                    or "[PROCESS_STOPPED]" in line
                ):
                    break

            except queue.Empty:
                # Keep connection alive.
                yield "data: \n\n"

    return Response(
        generate_events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/stop", methods=["POST"])
def stop():
    """
    Stop currently running process.
    """

    global process

    with process_lock:
        if process is None or process.poll() is not None:
            return jsonify({
                "ok": False,
                "error": "No hay un proceso activo para detener.",
            })

        try:
            if os.name == "nt":
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    process.terminate()
            else:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except Exception:
                    process.terminate()

            output_queue.put("[PROCESS_STOPPED]")

            return jsonify({"ok": True})

        except Exception as e:
            return jsonify({
                "ok": False,
                "error": str(e),
            })


if __name__ == "__main__":
    import webbrowser
    import time
    import traceback

    url = "http://127.0.0.1:5000"

    try:
        print("=" * 80)
        print("Generador de Reportes INIA Puno")
        print("=" * 80)
        print(f"Abriendo navegador en: {url}")
        print("No cierres esta ventana mientras usas la aplicación.")
        print("=" * 80)

        def open_browser():
            time.sleep(1.5)
            webbrowser.open(url)

        threading.Thread(
            target=open_browser,
            daemon=True,
        ).start()

        app.run(
            host="127.0.0.1",
            port=5000,
            debug=False,
            threaded=True,
            use_reloader=False,
        )

    except Exception:
        print("\nERROR:")
        traceback.print_exc()
        input("\nPresiona ENTER para cerrar...")

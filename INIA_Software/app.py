# app.py

from flask import Flask, render_template, request, jsonify, Response
from pathlib import Path

import subprocess
import threading
import queue
import sys
import os
import webbrowser
import time
import traceback


# ------------------------------------------------------------
# Products / crops from products.py
# ------------------------------------------------------------
try:
    from products import ALLOWED_PRODUCTS
except Exception as e:
    print("WARNING: Could not import ALLOWED_PRODUCTS from products.py")
    print("Error:", e)

    ALLOWED_PRODUCTS = [
        "PAPA NATIVA",
        "PAPA MEJORADA",
        "QUINUA",
        "CAÑIHUA",
        "AVENA",
        "CEBADA",
        "HABA",
        "TRIGO",
    ]


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
# Base directory
# ------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent


# ------------------------------------------------------------
# Crop/product options
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


def enqueue_output(proc):
    """
    Read subprocess output line by line and send it to the live terminal queue.
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


@app.route("/browse-file")
def browse_file():
    """
    Open native Windows file selector and return the real file path.

    This works because Flask is running locally on the same Windows machine.
    """

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        path = filedialog.askopenfilename(
            title="Seleccionar archivo",
            filetypes=[
                ("Excel files", "*.xlsx *.xlsm *.xls"),
                ("Python files", "*.py"),
                ("All files", "*.*"),
            ],
        )

        root.destroy()

        return jsonify({
            "path": path,
            "error": "",
        })

    except Exception as e:
        return jsonify({
            "path": "",
            "error": str(e),
        })


@app.route("/browse-folder")
def browse_folder():
    """
    Open native Windows folder selector and return the real folder path.

    This works because Flask is running locally on the same Windows machine.
    """

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        path = filedialog.askdirectory(
            title="Seleccionar carpeta"
        )

        root.destroy()

        return jsonify({
            "path": path,
            "error": "",
        })

    except Exception as e:
        return jsonify({
            "path": "",
            "error": str(e),
        })


@app.route("/generate", methods=["POST"])
def generate():
    """
    Start report generation.

    The paths come directly from the text inputs.
    They are filled manually or with the Windows selector.
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

        resultados_excel = request.form.get(
            "resultados_excel",
            DEFAULT_RESULTADOS_EXCEL,
        ).strip() or DEFAULT_RESULTADOS_EXCEL

        template_excel = request.form.get(
            "template_excel",
            DEFAULT_TEMPLATE_EXCEL,
        ).strip() or DEFAULT_TEMPLATE_EXCEL

        report_script = request.form.get(
            "report_script",
            DEFAULT_REPORT_SCRIPT,
        ).strip() or DEFAULT_REPORT_SCRIPT

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
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=BASE_DIR,
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
                # Keep the connection alive.
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

    Windows version: use process.terminate().
    """

    global process

    with process_lock:
        if process is None or process.poll() is not None:
            return jsonify({
                "ok": False,
                "error": "No hay un proceso activo para detener.",
            })

        try:
            process.terminate()
            output_queue.put("[PROCESS_STOPPED]")

            return jsonify({"ok": True})

        except Exception as e:
            return jsonify({
                "ok": False,
                "error": str(e),
            })


if __name__ == "__main__":
    url = "http://127.0.0.1:5000"

    try:
        print("=" * 80)
        print("Generador de Reportes INIA Puno")
        print("=" * 80)
        print(f"Carpeta actual: {BASE_DIR}")
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

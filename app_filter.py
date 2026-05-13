# app.py

from flask import Flask, request, render_template_string, send_file, url_for
from pathlib import Path
import uuid
import traceback

from filter_excel_general import (
    filter_excel_general,
    parse_filters_from_text,
    make_output_name_from_filters,
)


app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


HTML = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Filtro General de Excel</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f4f6f8;
            margin: 0;
            padding: 30px;
            color: #222;
        }

        .container {
            max-width: 980px;
            margin: auto;
            background: white;
            padding: 28px;
            border-radius: 14px;
            box-shadow: 0 3px 14px rgba(0,0,0,0.10);
        }

        h1 {
            margin-top: 0;
            color: #1f3b57;
        }

        label {
            display: block;
            margin-top: 16px;
            font-weight: bold;
        }

        input[type="text"],
        input[type="file"],
        select,
        textarea {
            width: 100%;
            box-sizing: border-box;
            padding: 10px;
            margin-top: 6px;
            border: 1px solid #bbb;
            border-radius: 7px;
            font-size: 15px;
            font-family: Arial, sans-serif;
        }

        textarea {
            min-height: 130px;
            resize: vertical;
            font-family: Consolas, monospace;
        }

        button {
            margin-top: 24px;
            padding: 12px 20px;
            background: #0b5ed7;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
        }

        button:hover {
            background: #084db3;
        }

        .note {
            background: #eef4ff;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            line-height: 1.45;
        }

        .examples {
            background: #f8f9fa;
            padding: 12px;
            border-radius: 8px;
            margin-top: 12px;
            line-height: 1.5;
        }

        .error {
            background: #ffe5e5;
            color: #7a0000;
            padding: 14px;
            border-radius: 8px;
            white-space: pre-wrap;
            margin-top: 20px;
            overflow-x: auto;
        }

        .success {
            background: #e8f8ec;
            color: #145c25;
            padding: 14px;
            border-radius: 8px;
            margin-top: 20px;
            line-height: 1.5;
        }

        .download {
            display: inline-block;
            margin-top: 12px;
            padding: 10px 15px;
            background: #198754;
            color: white;
            text-decoration: none;
            border-radius: 7px;
        }

        .small {
            color: #666;
            font-size: 13px;
            line-height: 1.4;
        }

        code {
            background: #eee;
            padding: 2px 5px;
            border-radius: 4px;
        }

        .filters-box {
            background: #fffaf0;
            padding: 12px;
            border-radius: 8px;
            margin-top: 12px;
            border: 1px solid #f0d38a;
        }
    </style>
</head>

<body>
<div class="container">
    <h1>Filtro General de Excel</h1>

    <div class="note">
        Esta herramienta permite filtrar un Excel por una o varias columnas.
        Por ejemplo: <code>DIST</code>, <code>PROV</code>,
        <code>CULTIVO A INSTALAR</code>, <code>ESTADO</code>,
        <code>LABORATORIO</code>, etc.
    </div>

    <form method="post" action="/filter" enctype="multipart/form-data">
        <label>Archivo Excel</label>
        <input type="file" name="input_excel" accept=".xlsx,.xlsm,.xls" required>

        <label>Filtros</label>
        <textarea name="filters_text" required placeholder="DIST=AYAVIRI&#10;PROV=MELGAR&#10;CULTIVO A INSTALAR=ALFALFA"></textarea>

        <div class="small">
            Escriba un filtro por línea usando <code>COLUMNA=VALOR</code>.
            También puede usar <code>:</code>, por ejemplo <code>DIST: AYAVIRI</code>.
            Si escribe varios filtros, la fila debe cumplir todos.
        </div>

        <label>Tipo de búsqueda</label>
        <select name="match_mode">
            <option value="exact" selected>Exacta</option>
            <option value="contains">Contiene</option>
        </select>

        <div class="small">
            <b>Exacta:</b> <code>DIST=AYAVIRI</code> solo encuentra AYAVIRI.<br>
            <b>Contiene:</b> <code>NOMBRES Y APELLIDOS=MARIA</code> encuentra nombres que contienen MARIA.
        </div>

        <label>Nombre de hoja, opcional</label>
        <input type="text" name="sheet" placeholder="Dejar vacío para buscar automáticamente">

        <label>Columnas de salida</label>
        <input type="text" name="output_columns" value="">

        <div class="small">
            Deje vacío para exportar las columnas estándar INIA.
            Escriba <code>ALL</code> para exportar todas las columnas encontradas.
            O escriba columnas específicas separadas por coma.
        </div>

        <label>Nombre del CSV de salida, opcional</label>
        <input type="text" name="output_name" value="" placeholder="Dejar vacío para generar nombre automático">

        <div class="small">
            Si deja este campo vacío, el nombre del archivo se generará usando los filtros.
        </div>

        <button type="submit">Generar CSV</button>
    </form>

    <div class="examples">
        <b>Ejemplo de un filtro:</b><br>
        <code>DIST=AYAVIRI</code><br><br>

        <b>Ejemplo de varios filtros:</b><br>
        <code>PROV=MELGAR</code><br>
        <code>DIST=AYAVIRI</code><br>
        <code>CULTIVO A INSTALAR=ALFALFA</code><br><br>

        <b>Ejemplo con búsqueda por contenido:</b><br>
        Seleccione <b>Contiene</b> y use:<br>
        <code>NOMBRES Y APELLIDOS=MARIA</code>
    </div>

    {% if error %}
        <div class="error">{{ error }}</div>
    {% endif %}

    {% if result %}
        <div class="success">
            <b>CSV generado correctamente.</b><br>
            Hoja usada: {{ result.sheet_used }}<br>
            Fila de encabezados: {{ result.header_row }}<br>
            Tipo de búsqueda: {{ result.match_mode }}<br>
            Coincidencias encontradas: {{ result.matches_found }}<br>
            Archivo: {{ result.output_csv }}<br>

            <div class="filters-box">
                <b>Filtros aplicados:</b><br>
                {% for item in result.filters %}
                    {{ item.column }} = {{ item.value }}<br>
                {% endfor %}
            </div>

            <a class="download" href="{{ download_url }}">Descargar CSV</a>
        </div>
    {% endif %}
</div>
</body>
</html>
"""


def safe_output_name(filename):
    filename = filename.strip()

    if not filename:
        filename = "filtered_output.csv"

    filename = Path(filename).name

    if not filename.lower().endswith(".csv"):
        filename += ".csv"

    return filename


@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        HTML,
        error=None,
        result=None,
        download_url=None,
    )


@app.route("/filter", methods=["POST"])
def filter_excel():
    try:
        uploaded_file = request.files.get("input_excel")

        if uploaded_file is None or uploaded_file.filename.strip() == "":
            return render_template_string(
                HTML,
                error="No se seleccionó ningún archivo Excel.",
                result=None,
                download_url=None,
            )

        filters_text = request.form.get("filters_text", "").strip()

        if not filters_text:
            return render_template_string(
                HTML,
                error="Debe ingresar al menos un filtro.",
                result=None,
                download_url=None,
            )

        filters = parse_filters_from_text(filters_text)

        sheet = request.form.get("sheet", "").strip()
        sheet = sheet if sheet else None

        output_columns = request.form.get("output_columns", "").strip()
        match_mode = request.form.get("match_mode", "exact").strip()

        manual_output_name = request.form.get("output_name", "").strip()

        if manual_output_name:
            output_name = safe_output_name(manual_output_name)
        else:
            output_name = make_output_name_from_filters(filters)

        run_id = str(uuid.uuid4())[:8]

        input_suffix = Path(uploaded_file.filename).suffix
        if not input_suffix:
            input_suffix = ".xlsx"

        input_excel = UPLOAD_DIR / f"input_{run_id}{input_suffix}"
        output_csv = OUTPUT_DIR / f"{run_id}_{output_name}"

        uploaded_file.save(input_excel)

        result = filter_excel_general(
            input_excel=input_excel,
            filters=filters,
            output_csv=output_csv,
            output_dir=OUTPUT_DIR,
            sheet_name=sheet,
            output_columns=output_columns,
            match_mode=match_mode,
        )

        return render_template_string(
            HTML,
            error=None,
            result=result,
            download_url=url_for("download_csv", filename=output_csv.name),
        )

    except Exception:
        error_message = traceback.format_exc()

        return render_template_string(
            HTML,
            error=error_message,
            result=None,
            download_url=None,
        )


@app.route("/download/<filename>")
def download_csv(filename):
    filename = Path(filename).name
    file_path = OUTPUT_DIR / filename

    if not file_path.exists():
        return "Archivo no encontrado.", 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype="text/csv",
    )


if __name__ == "__main__":
    app.run(debug=True)

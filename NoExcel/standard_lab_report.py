# standard_lab_report.py

from pathlib import Path
import argparse
import sqlite3
import unicodedata
import re
import math
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


DB_FILE = "database/inia_database.sqlite"
TABLE_NAME = "muestras"
OUTPUT_DIR = "reports_lab"


# ------------------------------------------------------------
# General helpers
# ------------------------------------------------------------

def normalize_text(value):
    if value is None:
        return ""

    value = str(value).strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )
    value = " ".join(value.split())

    return value


def safe_filename(value):
    value = str(value).strip()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value)
    value = value.strip("_")

    if not value:
        value = "report"

    return value


def escape_text(value):
    """
    Escape text for ReportLab Paragraph.
    This prevents issues with &, <, > characters.
    """

    if value is None:
        value = ""

    value = str(value)

    value = (
        value.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
    )

    return value


def value_to_float(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)

    text = str(value).strip()

    if text == "":
        return None

    if text.upper() in ["#VALUE!", "#N/A", "N/A", "NA", "-", "--", "NO"]:
        return None

    text = text.replace(",", ".")

    try:
        return float(text)
    except Exception:
        return None


def format_value(value, digits=2):
    number = value_to_float(value)

    if number is None:
        if value is None:
            return ""
        return str(value)

    return f"{number:.{digits}f}"


def format_date(value):
    if value is None:
        return ""

    text = str(value).strip()

    if text == "":
        return ""

    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return text


def get(row, key, default=""):
    value = row.get(key)

    if value is None:
        return default

    return value


def safe_divide(a, b):
    a = value_to_float(a)
    b = value_to_float(b)

    if a is None or b is None:
        return None

    if b == 0:
        return None

    return a / b


# ------------------------------------------------------------
# Styles
# ------------------------------------------------------------

def styles():
    base = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontSize=13,
            leading=15,
            alignment=1,
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            alignment=1,
        ),
        "normal": ParagraphStyle(
            "normal",
            parent=base["Normal"],
            fontSize=6.5,
            leading=7.8,
            wordWrap="CJK",
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontSize=6.2,
            leading=7.5,
            wordWrap="CJK",
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.black,
            wordWrap="CJK",
        ),
    }


def cell(value, s):
    """
    Normal table cell as Paragraph.
    Long text wraps instead of overwriting other columns.
    """

    return Paragraph(
        escape_text(value),
        s["normal"],
    )


def label_cell(value, s):
    """
    Bold label cell as Paragraph.
    Long labels also wrap correctly.
    """

    return Paragraph(
        f"<b>{escape_text(value)}</b>",
        s["normal"],
    )


# ------------------------------------------------------------
# Database helpers
# ------------------------------------------------------------

def get_row_by_name_and_cultivo(db_file, name, cultivo):
    db_file = Path(db_file)

    if not db_file.exists():
        raise FileNotFoundError(f"Database not found: {db_file}")

    name_norm = normalize_text(name)
    cultivo_norm = normalize_text(cultivo)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado = ?
              AND cultivo_normalizado = ?
            LIMIT 1
        """

        cur.execute(query, (name_norm, cultivo_norm))
        row = cur.fetchone()

        if row is not None:
            return dict(row)

        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado LIKE ?
              AND cultivo_normalizado LIKE ?
            LIMIT 10
        """

        cur.execute(query, (f"%{name_norm}%", f"%{cultivo_norm}%"))
        rows = cur.fetchall()

        if rows:
            if len(rows) > 1:
                print("\nWARNING: More than one matching record was found. Using the first one.")
                for r in rows:
                    print(
                        "  -",
                        r["nombres_y_apellidos"],
                        "|",
                        r["cultivo_a_instalar"],
                        "|",
                        r["codigo"],
                    )

            return dict(rows[0])

        query = f"""
            SELECT nombres_y_apellidos, cultivo_a_instalar, codigo
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado LIKE ?
            LIMIT 20
        """

        cur.execute(query, (f"%{name_norm}%",))
        name_rows = cur.fetchall()

        if name_rows:
            print("\nName found, but not with the requested cultivo.")
            print(f"Requested cultivo: {cultivo}")
            print("\nAvailable records:")

            for r in name_rows:
                print(
                    "  -",
                    r["nombres_y_apellidos"],
                    "| cultivo:",
                    r["cultivo_a_instalar"],
                    "| codigo:",
                    r["codigo"],
                )

        return None


# ------------------------------------------------------------
# General interpretation helpers
# ------------------------------------------------------------

def classify_range(value, low=None, high=None):
    """
    Simple lab flag:
        Bajo
        Dentro del rango
        Alto
        Sin dato
    """

    number = value_to_float(value)

    if number is None:
        return "Sin dato"

    if low is not None and number < low:
        return "Bajo"

    if high is not None and number > high:
        return "Alto"

    return "Dentro del rango"


def classify_ph(value):
    number = value_to_float(value)

    if number is None:
        return "Sin dato"

    if number < 5.5:
        return "Ácido fuerte"
    if number < 6.6:
        return "Ácido moderado"
    if number <= 7.3:
        return "Dentro del rango"
    if number <= 8.5:
        return "Alcalino moderado"

    return "Alcalino fuerte"


def classify_ce(value):
    number = value_to_float(value)

    if number is None:
        return "Sin dato"

    if number < 100:
        return "Normal"
    if number < 200:
        return "Ligeramente salino"
    if number < 400:
        return "Moderadamente salino"
    if number < 800:
        return "Salino"

    return "Fuertemente salino"


def flag_color(flag):
    flag_norm = normalize_text(flag)

    if flag_norm in [
        "dentro del rango",
        "normal",
        "adecuado",
        "ideal",
        "aceptable",
        "adecuado para k",
    ]:
        return colors.HexColor("#e7f4e4")

    if (
        "bajo" in flag_norm
        or "acido" in flag_norm
        or "ligeramente" in flag_norm
        or "def" in flag_norm
        or "fuera" in flag_norm
    ):
        return colors.HexColor("#fff4cc")

    if "alto" in flag_norm or "salino" in flag_norm or "alcalino" in flag_norm:
        return colors.HexColor("#fde4e1")

    return colors.white


# ------------------------------------------------------------
# Cation-ratio interpretation
#
# Source implemented:
# AQM Laboratorios, "Relaciones catiónicas y su interpretación
# en los análisis de suelos".
#
# Ca/Mg:
#   <1     Deficiencia de calcio
#   1-2    Bajo nivel de calcio respecto al magnesio
#   2-5    Ideal
#   >5     Deficiencia de magnesio
#
# Mg/K:
#   <1     Deficiencia de magnesio
#   1-3    Aceptable
#   3      Ideal
#   3-18   Aceptable
#   >18    Deficiencia de potasio
#
# Ca/K:
#   <30    Adecuado
#   >30    Deficiencia de potasio
#
# (Ca+Mg)/K:
#   <40    Adecuado para el potasio
#   >40    Deficiencia de potasio
#
# These are reference values. The source says they can vary depending
# on crop, climate, and other factors.
# ------------------------------------------------------------

def classify_ca_k(value):
    number = value_to_float(value)

    if number is None:
        return "Sin dato"

    if number <= 30:
        return "Adecuado"

    return "Def. de K"


def classify_mg_k(value):
    number = value_to_float(value)

    if number is None:
        return "Sin dato"

    if number < 1:
        return "Def. de Mg"

    if number < 3:
        return "Aceptable"

    if abs(number - 3.0) < 1e-9:
        return "Ideal"

    if number <= 18:
        return "Aceptable"

    return "Def. de K"


def classify_ca_mg_k(value):
    number = value_to_float(value)

    if number is None:
        return "Sin dato"

    if number <= 40:
        return "Adecuado para K"

    return "Def. de K"


def classify_ca_mg(value):
    number = value_to_float(value)

    if number is None:
        return "Sin dato"

    if number < 1:
        return "Def. de Ca"

    if number < 2:
        return "Bajo Ca respecto a Mg"

    if number <= 5:
        return "Ideal"

    return "Def. de Mg"


def classify_saturation(cation_name, value):
    """
    Simple base-saturation interpretation.

    These limits are general reference values and should be replaced if
    the lab has official saturation ranges.
    """

    number = value_to_float(value)

    if number is None:
        return "Sin dato"

    key = normalize_text(cation_name)

    if key == "calcio":
        if number < 60:
            return "Bajo"
        if number <= 80:
            return "Adecuado"
        return "Alto"

    if key == "magnesio":
        if number < 10:
            return "Bajo"
        if number <= 20:
            return "Adecuado"
        return "Alto"

    if key == "potasio":
        if number < 2:
            return "Bajo"
        if number <= 6:
            return "Adecuado"
        return "Alto"

    if key == "sodio":
        if number < 0:
            return "Sin dato"
        if number <= 3:
            return "Adecuado"
        return "Alto"

    if key == "aluminio":
        if number <= 5:
            return "Adecuado"
        return "Alto"

    return "Sin dato"


def saturation_color(flag):
    flag_norm = normalize_text(flag)

    if flag_norm == "alto":
        return colors.HexColor("#fde4e1")

    if flag_norm == "adecuado":
        return colors.HexColor("#e7f4e4")

    if flag_norm == "bajo":
        return colors.HexColor("#e8f4fb")

    return colors.white


# ------------------------------------------------------------
# Report sections
# ------------------------------------------------------------

def make_header(s):
    data = [
        [
            Paragraph("<b>PERÚ</b><br/>Ministerio de Desarrollo Agrario y Riego", s["small"]),
            Paragraph("<b>INIA</b><br/>Instituto Nacional de Innovación Agraria", s["small"]),
            Paragraph("<b>LABSAF</b><br/>Laboratorio de Suelos", s["small"]),
        ]
    ]

    table = Table(
        data,
        colWidths=[5.8 * cm, 6.0 * cm, 5.8 * cm],
    )

    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2f2f2")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    return table


def make_section_title(text, s):
    table = Table(
        [[Paragraph(f"<b>{escape_text(text)}</b>", s["section"])]],
        colWidths=[18.0 * cm],
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#d9d9d9")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return table


def make_sample_info(row, s):
    cultivo = str(get(row, "cultivo_a_instalar", ""))
    variedad = str(get(row, "variedad_a_instalar", ""))

    if variedad and variedad.upper() not in ["NO", "N/A", "NA", "-", "--"]:
        cultivo_variedad = f"{cultivo} / {variedad}"
    else:
        cultivo_variedad = cultivo

    distrito_prov_dep = (
        f"{get(row, 'dist')} / "
        f"{get(row, 'prov')} / "
        f"{get(row, 'dep')}"
    )

    data = [
        [
            label_cell("Cliente / Agricultor", s),
            cell(get(row, "nombres_y_apellidos"), s),
            label_cell("Código de laboratorio", s),
            cell(get(row, "codigo"), s),
        ],
        [
            label_cell("DNI", s),
            cell(get(row, "dni"), s),
            label_cell("Laboratorio", s),
            cell(get(row, "laboratorio"), s),
        ],
        [
            label_cell("Localidad", s),
            cell(get(row, "localidad_comunidad_caserio_asociacion_etc"), s),
            label_cell("Zona", s),
            cell(get(row, "zona"), s),
        ],
        [
            label_cell("Distrito / Provincia / Departamento", s),
            cell(distrito_prov_dep, s),
            label_cell("Altitud", s),
            cell(get(row, "altitud_m_s_n_m"), s),
        ],
        [
            label_cell("Cultivo / Variedad", s),
            cell(cultivo_variedad, s),
            label_cell("Fecha de muestreo", s),
            cell(format_date(get(row, "fecha_de_muestreo")), s),
        ],
        [
            label_cell("Clima", s),
            cell(get(row, "clima"), s),
            label_cell("Responsable", s),
            cell(get(row, "responsable"), s),
        ],
    ]

    table = Table(
        data,
        colWidths=[
            3.8 * cm,
            5.4 * cm,
            3.8 * cm,
            5.0 * cm,
        ],
    )

    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),

        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f5f5f5")),

        ("VALIGN", (0, 0), (-1, -1), "TOP"),

        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    return table


def analytical_rows(row):
    return [
        {
            "parameter": "pH",
            "value": get(row, "ph"),
            "unit": "unidad pH",
            "range": "6.6 - 7.3",
            "flag": classify_ph(get(row, "ph")),
        },
        {
            "parameter": "Conductividad eléctrica",
            "value": get(row, "ce_ms_m"),
            "unit": "mS/m",
            "range": "< 100 - 200",
            "flag": classify_ce(get(row, "ce_ms_m")),
        },
        {
            "parameter": "Materia orgánica",
            "value": get(row, "mo_porcentaje"),
            "unit": "%",
            "range": "1.6 - 3.5",
            "flag": classify_range(get(row, "mo_porcentaje"), 1.6, 3.5),
        },
        {
            "parameter": "Nitrógeno total",
            "value": get(row, "n_porcentaje"),
            "unit": "%",
            "range": "0.10 - 0.15",
            "flag": classify_range(get(row, "n_porcentaje"), 0.10, 0.15),
        },
        {
            "parameter": "Fósforo disponible",
            "value": get(row, "p_mg_kg"),
            "unit": "mg/kg",
            "range": "5.5 - 11",
            "flag": classify_range(get(row, "p_mg_kg"), 5.5, 11),
        },
        {
            "parameter": "Potasio disponible",
            "value": get(row, "k_ppm"),
            "unit": "mg/kg",
            "range": "120 - 240",
            "flag": classify_range(get(row, "k_ppm"), 120, 240),
        },
        {
            "parameter": "Calcio intercambiable",
            "value": get(row, "calcio_ca_cmol_plus_kg"),
            "unit": "cmol(+)/kg",
            "range": "5.0 - 10.0",
            "flag": classify_range(get(row, "calcio_ca_cmol_plus_kg"), 5.0, 10.0),
        },
        {
            "parameter": "Magnesio intercambiable",
            "value": get(row, "magnesio_mg_cmol_plus_kg"),
            "unit": "cmol(+)/kg",
            "range": "1.3 - 3.0",
            "flag": classify_range(get(row, "magnesio_mg_cmol_plus_kg"), 1.3, 3.0),
        },
        {
            "parameter": "Potasio intercambiable",
            "value": get(row, "potasio_k_cmol_plus_kg"),
            "unit": "cmol(+)/kg",
            "range": "0.3 - 0.6",
            "flag": classify_range(get(row, "potasio_k_cmol_plus_kg"), 0.3, 0.6),
        },
        {
            "parameter": "Sodio intercambiable",
            "value": get(row, "sodio_na_cmol_plus_kg"),
            "unit": "cmol(+)/kg",
            "range": "< 0.3",
            "flag": classify_range(get(row, "sodio_na_cmol_plus_kg"), None, 0.3),
        },
        {
            "parameter": "Aluminio intercambiable",
            "value": get(row, "aluminio_intercambiable_cmol_plus_kg"),
            "unit": "cmol(+)/kg",
            "range": "< 0.25",
            "flag": classify_range(get(row, "aluminio_intercambiable_cmol_plus_kg"), None, 0.25),
        },
        {
            "parameter": "Acidez intercambiable",
            "value": get(row, "acidez_hplus_cmol_plus_kg"),
            "unit": "cmol(+)/kg",
            "range": "< 0.5",
            "flag": classify_range(get(row, "acidez_hplus_cmol_plus_kg"), None, 0.5),
        },
        {
            "parameter": "CICe",
            "value": get(row, "cice_cmol_plus_kg"),
            "unit": "cmol(+)/kg",
            "range": "15 - 25",
            "flag": classify_range(get(row, "cice_cmol_plus_kg"), 15, 25),
        },
        {
            "parameter": "Carbonato de calcio equivalente",
            "value": get(row, "caco3_porcentaje_equivalente"),
            "unit": "%",
            "range": "< 5",
            "flag": classify_range(get(row, "caco3_porcentaje_equivalente"), None, 5),
        },
    ]


def make_results_table(row, s):
    data = [
        [
            Paragraph("<b>Determinación</b>", s["normal"]),
            Paragraph("<b>Resultado</b>", s["normal"]),
            Paragraph("<b>Unidad</b>", s["normal"]),
            Paragraph("<b>Rango referencial</b>", s["normal"]),
            Paragraph("<b>Interpretación</b>", s["normal"]),
        ]
    ]

    bg_styles = []

    for i, item in enumerate(analytical_rows(row), start=1):
        data.append([
            cell(item["parameter"], s),
            cell(format_value(item["value"]), s),
            cell(item["unit"], s),
            cell(item["range"], s),
            cell(item["flag"], s),
        ])

        bg_styles.append(
            ("BACKGROUND", (4, i), (4, i), flag_color(item["flag"]))
        )

    table = Table(
        data,
        colWidths=[
            5.4 * cm,
            2.2 * cm,
            2.6 * cm,
            3.4 * cm,
            4.4 * cm,
        ],
        repeatRows=1,
    )

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (1, 1), (4, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    style.extend(bg_styles)
    table.setStyle(TableStyle(style))

    return table


def make_texture_table(row, s):
    data = [
        [
            Paragraph("<b>Arena</b>", s["normal"]),
            Paragraph("<b>Arcilla</b>", s["normal"]),
            Paragraph("<b>Limo</b>", s["normal"]),
            Paragraph("<b>Clase textural</b>", s["normal"]),
        ],
        [
            cell(format_value(get(row, "arena")), s),
            cell(format_value(get(row, "arcilla")), s),
            cell(format_value(get(row, "limo")), s),
            cell(get(row, "clase_textural"), s),
        ],
    ]

    table = Table(
        data,
        colWidths=[
            4.5 * cm,
            4.5 * cm,
            4.5 * cm,
            4.5 * cm,
        ],
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return table


def make_cation_ratios_table(row, s):
    ca = get(row, "calcio_ca_cmol_plus_kg")
    mg = get(row, "magnesio_mg_cmol_plus_kg")
    k = get(row, "potasio_k_cmol_plus_kg")

    ca_k = safe_divide(ca, k)
    mg_k = safe_divide(mg, k)

    ca_num = value_to_float(ca)
    mg_num = value_to_float(mg)

    ca_mg_sum = None
    if ca_num is not None and mg_num is not None:
        ca_mg_sum = ca_num + mg_num

    ca_plus_mg_k = safe_divide(ca_mg_sum, k)
    ca_mg = safe_divide(ca, mg)

    data = [
        [
            Paragraph("<b>Relación</b>", s["normal"]),
            Paragraph("<b>Ca/K</b>", s["normal"]),
            Paragraph("<b>Mg/K</b>", s["normal"]),
            Paragraph("<b>(Ca+Mg)/K</b>", s["normal"]),
            Paragraph("<b>Ca/Mg</b>", s["normal"]),
        ],
        [
            Paragraph("<b>Resultado</b>", s["normal"]),
            cell(format_value(ca_k), s),
            cell(format_value(mg_k), s),
            cell(format_value(ca_plus_mg_k), s),
            cell(format_value(ca_mg), s),
        ],
        [
            Paragraph("<b>Interpretación</b>", s["normal"]),
            cell(classify_ca_k(ca_k), s),
            cell(classify_mg_k(mg_k), s),
            cell(classify_ca_mg_k(ca_plus_mg_k), s),
            cell(classify_ca_mg(ca_mg), s),
        ],
        [
            Paragraph("<b>Criterio usado</b>", s["normal"]),
            cell("≤30: Adecuado; >30: Def. K", s),
            cell("<1: Def. Mg; 1-18: Aceptable; 3: Ideal; >18: Def. K", s),
            cell("≤40: Adecuado para K; >40: Def. K", s),
            cell("<1: Def. Ca; 1-2: Bajo Ca/Mg; 2-5: Ideal; >5: Def. Mg", s),
        ],
    ]

    table = Table(
        data,
        colWidths=[
            3.2 * cm,
            3.7 * cm,
            3.7 * cm,
            3.7 * cm,
            3.7 * cm,
        ],
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#f2f2f2")),
        ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#fafafa")),

        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),

        ("ALIGN", (1, 0), (-1, 2), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return table


def make_cation_saturation_table(row, s):
    ca = value_to_float(get(row, "calcio_ca_cmol_plus_kg"))
    mg = value_to_float(get(row, "magnesio_mg_cmol_plus_kg"))
    k = value_to_float(get(row, "potasio_k_cmol_plus_kg"))
    na = value_to_float(get(row, "sodio_na_cmol_plus_kg"))
    al = value_to_float(get(row, "aluminio_intercambiable_cmol_plus_kg"))
    cice = value_to_float(get(row, "cice_cmol_plus_kg"))

    cations = [
        ("Calcio", ca),
        ("Magnesio", mg),
        ("Potasio", k),
        ("Sodio", na),
        ("Aluminio", al),
    ]

    saturation_values = []

    for name, value in cations:
        if value is None or cice is None or cice == 0:
            sat = None
        else:
            sat = value / cice * 100.0

        flag = classify_saturation(name, sat)

        saturation_values.append({
            "name": name,
            "value": sat,
            "flag": flag,
        })

    data = [
        [
            Paragraph("<b>Catión intercambiable</b>", s["normal"]),
            Paragraph("<b>% Saturación</b>", s["normal"]),
            Paragraph("<b>Interpretación</b>", s["normal"]),
        ]
    ]

    bg_styles = []

    for i, item in enumerate(saturation_values, start=1):
        data.append([
            cell(item["name"], s),
            cell(format_value(item["value"]), s),
            cell(item["flag"], s),
        ])

        bg_styles.append(
            ("BACKGROUND", (2, i), (2, i), saturation_color(item["flag"]))
        )

    table = Table(
        data,
        colWidths=[
            6.0 * cm,
            5.0 * cm,
            7.0 * cm,
        ],
    )

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),

        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    style.extend(bg_styles)
    table.setStyle(TableStyle(style))

    return table


def make_notes_table(s):
    data = [
        [
            Paragraph(
                "<b>Observaciones:</b> "
                "Los rangos referenciales son orientativos y deben interpretarse "
                "considerando el cultivo, textura del suelo, clima, manejo agronómico "
                "y criterio técnico del especialista.",
                s["small"],
            )
        ],
        [
            Paragraph(
                "<b>Nota sobre relaciones catiónicas:</b> "
                "La interpretación de Ca/K, Mg/K, (Ca+Mg)/K y Ca/Mg se incluye "
                "como criterio referencial de balance de bases. Estos valores pueden "
                "variar según cultivo, clima y otros factores; no deben usarse como "
                "único criterio de recomendación de fertilización.",
                s["small"],
            )
        ],
        [
            Paragraph(
                "<b>Nota:</b> Este informe fue generado automáticamente desde la base "
                "de datos SQLite del laboratorio.",
                s["small"],
            )
        ],
    ]

    table = Table(data, colWidths=[18.0 * cm])

    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    return table


def make_signature_table(s):
    data = [
        [
            "",
            "",
        ],
        [
            Paragraph("<b>Responsable técnico</b>", s["normal"]),
            Paragraph("<b>Fecha de emisión</b>", s["normal"]),
        ],
        [
            "____________________________",
            datetime.now().strftime("%d/%m/%Y"),
        ],
    ]

    table = Table(
        data,
        colWidths=[9.0 * cm, 9.0 * cm],
        rowHeights=[0.8 * cm, 0.35 * cm, 0.5 * cm],
    )

    table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))

    return table


# ------------------------------------------------------------
# Main report generator
# ------------------------------------------------------------

def generate_report(name, cultivo, db_file=DB_FILE, output_pdf=None):
    row = get_row_by_name_and_cultivo(
        db_file=db_file,
        name=name,
        cultivo=cultivo,
    )

    if row is None:
        raise ValueError(
            f"No record found for name={name!r}, cultivo={cultivo!r}"
        )

    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_pdf is None:
        output_pdf = output_dir / (
            f"Informe_Laboratorio_{safe_filename(name)}_{safe_filename(cultivo)}.pdf"
        )
    else:
        output_pdf = Path(output_pdf)

    s = styles()

    doc = SimpleDocTemplate(
        str(output_pdf),
        pagesize=A4,
        leftMargin=1.0 * cm,
        rightMargin=1.0 * cm,
        topMargin=0.8 * cm,
        bottomMargin=0.8 * cm,
    )

    story = []

    story.append(make_header(s))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("<b>INFORME DE ANÁLISIS DE SUELO</b>", s["title"]))
    story.append(Paragraph("Resultados analíticos de muestra de suelo", s["subtitle"]))
    story.append(Spacer(1, 0.25 * cm))

    story.append(make_section_title("1. INFORMACIÓN DE LA MUESTRA", s))
    story.append(make_sample_info(row, s))
    story.append(Spacer(1, 0.25 * cm))

    story.append(make_section_title("2. RESULTADOS ANALÍTICOS", s))
    story.append(make_results_table(row, s))
    story.append(Spacer(1, 0.25 * cm))

    story.append(make_section_title("3. TEXTURA DEL SUELO", s))
    story.append(make_texture_table(row, s))
    story.append(Spacer(1, 0.25 * cm))

    story.append(make_section_title("4. RELACIONES ENTRE CATIONES", s))
    story.append(make_cation_ratios_table(row, s))
    story.append(Spacer(1, 0.25 * cm))

    story.append(make_section_title("5. SATURACIÓN DE CATIONES INTERCAMBIABLES", s))
    story.append(make_cation_saturation_table(row, s))
    story.append(Spacer(1, 0.25 * cm))

    story.append(make_section_title("6. OBSERVACIONES", s))
    story.append(make_notes_table(s))
    story.append(Spacer(1, 0.45 * cm))

    story.append(make_signature_table(s))

    doc.build(story)

    print(f"Report created: {output_pdf}")

    return output_pdf


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate standard soil laboratory report from SQLite database."
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
        "--db",
        default=DB_FILE,
        help="SQLite database file.",
    )

    parser.add_argument(
        "--output",
        default=None,
        help="Output PDF file. Optional.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    generate_report(
        name=args.name,
        cultivo=args.cultivo,
        db_file=args.db,
        output_pdf=args.output,
    )

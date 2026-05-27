# make_report_from_db.py

from pathlib import Path
import argparse
import sqlite3
import unicodedata
import re
import math

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
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
OUTPUT_DIR = "reports_db"


# ------------------------------------------------------------
# Colors
# ------------------------------------------------------------

PH_STRONG_ACID = colors.HexColor("#e53935")
PH_MODERATE_ACID = colors.HexColor("#f4a300")
PH_NEUTRAL = colors.HexColor("#7fdc7f")
PH_MODERATE_ALK = colors.HexColor("#58c7e8")
PH_STRONG_ALK = colors.HexColor("#2467d8")

NORMAL_GREEN = colors.HexColor("#7fdc7f")
VERY_LOW_RED = colors.HexColor("#ff0000")
LOW_ORANGE = colors.HexColor("#f4a300")
MEDIUM_GREEN = colors.HexColor("#7fdc7f")
HIGH_BLUE = colors.HexColor("#22aeea")
VERY_HIGH_BLUE = colors.HexColor("#2474c9")

ALTO_RED = colors.HexColor("#ff0000")
ADECUADO_GREEN = colors.HexColor("#00b050")
BAJO_BLUE = colors.HexColor("#00a6d6")
MEDIO_ORANGE = colors.HexColor("#f4a300")
SIN_COLOR = colors.white


# ------------------------------------------------------------
# Text helpers
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
        value = "reporte"

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


def row_get(row, key, default=""):
    try:
        value = row[key]
    except Exception:
        return default

    if value is None:
        return default

    return value


# ------------------------------------------------------------
# Styles
# ------------------------------------------------------------

def normal_style():
    styles = getSampleStyleSheet()
    style = styles["Normal"]
    style.fontSize = 6.8
    style.leading = 8
    return style


def small_style():
    styles = getSampleStyleSheet()
    style = styles["Normal"]
    style.fontSize = 6.5
    style.leading = 7.5
    return style


def title_style():
    styles = getSampleStyleSheet()
    style = styles["Title"]
    style.fontSize = 11
    style.leading = 13
    style.alignment = 1
    return style


# ------------------------------------------------------------
# Database helpers
# ------------------------------------------------------------

def get_table_columns(conn):
    cur = conn.cursor()
    cur.execute(f'PRAGMA table_info("{TABLE_NAME}")')
    rows = cur.fetchall()
    return [row[1] for row in rows]


def find_column(columns, candidates, contains_all=None):
    column_set = set(columns)

    for candidate in candidates:
        if candidate in column_set:
            return candidate

    if contains_all:
        for col in columns:
            ok = True

            for word in contains_all:
                if word not in col:
                    ok = False
                    break

            if ok:
                return col

    return None


def get_row_by_name_and_cultivo(db_file, name, cultivo):
    db_file = Path(db_file)

    if not db_file.exists():
        raise FileNotFoundError(f"Database not found: {db_file}")

    name_norm = normalize_text(name)
    cultivo_norm = normalize_text(cultivo)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # ------------------------------------------------------------
        # 1. Exact name and exact crop
        # ------------------------------------------------------------

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

        # ------------------------------------------------------------
        # 2. Partial name and exact crop
        # ------------------------------------------------------------

        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado LIKE ?
              AND cultivo_normalizado = ?
            LIMIT 10
        """

        cur.execute(query, (f"%{name_norm}%", cultivo_norm))
        rows = cur.fetchall()

        if rows:
            if len(rows) > 1:
                print("\nWARNING: More than one row matched. Using the first one:")
                for r in rows:
                    print(
                        "  -",
                        row_get(r, "nombres_y_apellidos", ""),
                        "|",
                        row_get(r, "cultivo_a_instalar", ""),
                        "|",
                        row_get(r, "codigo", ""),
                    )

            return dict(rows[0])

        # ------------------------------------------------------------
        # 3. Exact name and partial crop
        # ------------------------------------------------------------

        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado = ?
              AND cultivo_normalizado LIKE ?
            LIMIT 10
        """

        cur.execute(query, (name_norm, f"%{cultivo_norm}%"))
        rows = cur.fetchall()

        if rows:
            if len(rows) > 1:
                print("\nWARNING: More than one row matched. Using the first one:")
                for r in rows:
                    print(
                        "  -",
                        row_get(r, "nombres_y_apellidos", ""),
                        "|",
                        row_get(r, "cultivo_a_instalar", ""),
                        "|",
                        row_get(r, "codigo", ""),
                    )

            return dict(rows[0])

        # ------------------------------------------------------------
        # 4. Partial name and partial crop
        # ------------------------------------------------------------

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
                print("\nWARNING: More than one row matched. Using the first one:")
                for r in rows:
                    print(
                        "  -",
                        row_get(r, "nombres_y_apellidos", ""),
                        "|",
                        row_get(r, "cultivo_a_instalar", ""),
                        "|",
                        row_get(r, "codigo", ""),
                    )

            return dict(rows[0])

        # ------------------------------------------------------------
        # 5. Debug: name exists but crop is different
        # ------------------------------------------------------------

        query = f"""
            SELECT *
            FROM "{TABLE_NAME}"
            WHERE nombre_normalizado LIKE ?
            LIMIT 20
        """

        cur.execute(query, (f"%{name_norm}%",))
        name_rows = cur.fetchall()

        if name_rows:
            print("\nName was found, but not with the requested crop.")
            print(f"Requested cultivo: {cultivo}")
            print("\nAvailable records for this name:")

            for r in name_rows:
                print(
                    "  -",
                    row_get(r, "nombres_y_apellidos", ""),
                    "| cultivo:",
                    row_get(r, "cultivo_a_instalar", ""),
                    "| codigo:",
                    row_get(r, "codigo", ""),
                )

        return None


# ------------------------------------------------------------
# Interpretation helpers
# ------------------------------------------------------------

def interpret_ph(value):
    ph = value_to_float(value)

    if ph is None:
        return "", SIN_COLOR

    if ph < 5.5:
        return "Fuertemente ácido", PH_STRONG_ACID
    if ph < 6.5:
        return "Moderadamente ácido", PH_MODERATE_ACID
    if ph <= 7.5:
        return "Neutro", PH_NEUTRAL
    if ph <= 8.5:
        return "Moderadamente alcalino", PH_MODERATE_ALK

    return "Fuertemente alcalino", PH_STRONG_ALK


def interpret_ce(value):
    ce = value_to_float(value)

    if ce is None:
        return "", SIN_COLOR

    if ce < 100:
        return "Normal", NORMAL_GREEN
    if ce < 200:
        return "Muy ligeramente salino", colors.HexColor("#7fdde3")
    if ce < 400:
        return "Moderadamente salino", colors.HexColor("#6f8be8")
    if ce < 800:
        return "Suelo salino", colors.HexColor("#2d35f0")

    return "Fuertemente salino", VERY_HIGH_BLUE


def interpret_5levels(value, very_low, low, medium, high):
    number = value_to_float(value)

    if number is None:
        return "", SIN_COLOR

    if number < very_low:
        return "Muy bajo", VERY_LOW_RED
    if number < low:
        return "Bajo", LOW_ORANGE
    if number < medium:
        return "Medio", MEDIUM_GREEN
    if number < high:
        return "Alto", HIGH_BLUE

    return "Muy alto", VERY_HIGH_BLUE


def interpret_4levels(value, low, medium, high):
    number = value_to_float(value)

    if number is None:
        return "", SIN_COLOR

    if number < low:
        return "Bajo", LOW_ORANGE
    if number < medium:
        return "Medio", MEDIUM_GREEN
    if number < high:
        return "Alto", HIGH_BLUE

    return "Muy alto", VERY_HIGH_BLUE


def interpret_high_bad(value, adequate_max):
    number = value_to_float(value)

    if number is None:
        return "", SIN_COLOR

    if number <= adequate_max:
        return "Adecuado", ADECUADO_GREEN

    return "Alto", ALTO_RED


def get_interpretation(label, value):
    key = normalize_text(label)

    if key == "ph":
        return interpret_ph(value)

    if key == "ce":
        return interpret_ce(value)

    if "materia organica" in key:
        return interpret_5levels(
            value,
            very_low=1.6,
            low=3.0,
            medium=5.0,
            high=7.0,
        )

    if "nitrogeno total" in key:
        return interpret_5levels(
            value,
            very_low=0.10,
            low=0.15,
            medium=0.25,
            high=0.50,
        )

    if "fosforo disponible" in key:
        return interpret_5levels(
            value,
            very_low=5.5,
            low=11.0,
            medium=20.0,
            high=40.0,
        )

    if "potasio disponible" in key:
        return interpret_5levels(
            value,
            very_low=120,
            low=240,
            medium=400,
            high=600,
        )

    if "calcio intercambiable" in key:
        return interpret_4levels(
            value,
            low=5.0,
            medium=10.0,
            high=20.0,
        )

    if "magnesio intercambiable" in key:
        return interpret_4levels(
            value,
            low=1.3,
            medium=3.0,
            high=8.0,
        )

    if "potasio intercambiable" in key:
        return interpret_4levels(
            value,
            low=0.3,
            medium=0.6,
            high=1.2,
        )

    if "sodio intercambiable" in key:
        number = value_to_float(value)

        if number is None:
            return "", SIN_COLOR

        if number < 0.1:
            return "Bajo", BAJO_BLUE
        if number <= 0.3:
            return "Adecuado", ADECUADO_GREEN

        return "Alto", ALTO_RED

    if "aluminio intercambiable" in key:
        number = value_to_float(value)

        if number is None:
            return "", SIN_COLOR

        if number < 0.1:
            return "Bajo", BAJO_BLUE
        if number <= 0.25:
            return "Adecuado", ADECUADO_GREEN

        return "Alto", ALTO_RED

    if key == "cice":
        return interpret_4levels(
            value,
            low=15,
            medium=25,
            high=40,
        )

    if "carbonato de calcio equivalente" in key:
        number = value_to_float(value)

        if number is None:
            return "", SIN_COLOR

        if number < 1:
            return "Bajo", BAJO_BLUE
        if number <= 5:
            return "Adecuado", ADECUADO_GREEN

        return "Alto", ALTO_RED

    if "acidez intercambiable" in key:
        number = value_to_float(value)

        if number is None:
            return "", SIN_COLOR

        if number < 0.5:
            return "Bajo", BAJO_BLUE
        if number < 1.0:
            return "Medio", MEDIO_ORANGE

        return "Alto", ALTO_RED

    return "", SIN_COLOR


# ------------------------------------------------------------
# Column mapping
# ------------------------------------------------------------

def build_column_mapping(columns):
    col = {}

    col["nombre"] = find_column(
        columns,
        ["nombres_y_apellidos", "nombre_y_apellidos"],
        ["nombres", "apellidos"],
    )

    col["direccion"] = find_column(
        columns,
        ["direccion"],
        ["direccion"],
    )

    col["parcela"] = find_column(
        columns,
        ["nombre_p_parcela", "nombre_parcela"],
        ["parcela"],
    )

    col["altitud"] = find_column(
        columns,
        ["altitud_m_s_n_m", "altitud"],
        ["altitud"],
    )

    col["cultivo"] = find_column(
        columns,
        ["cultivo_a_instalar", "cultivo_instalar"],
        ["cultivo", "instalar"],
    )

    col["variedad"] = find_column(
        columns,
        ["variedad_a_instalar"],
        ["variedad", "instalar"],
    )

    col["codigo"] = find_column(
        columns,
        ["codigo"],
        ["codigo"],
    )

    col["fecha_recepcion"] = find_column(
        columns,
        ["fecha_de_recepcion", "fecha_recepcion"],
        ["fecha", "recepcion"],
    )

    col["fecha_analisis"] = find_column(
        columns,
        ["fecha_de_analisis", "fecha_analisis"],
        ["fecha", "analisis"],
    )

    col["zona"] = find_column(
        columns,
        ["zona"],
        ["zona"],
    )

    col["laboratorio"] = find_column(
        columns,
        ["laboratorio"],
        ["laboratorio"],
    )

    col["ph"] = find_column(
        columns,
        ["ph"],
        ["ph"],
    )

    col["ce"] = find_column(
        columns,
        ["ce_ms_m", "ce_m_s_m", "c_e_ms_m", "ce"],
        ["ce"],
    )

    col["materia_organica"] = find_column(
        columns,
        ["mo_porcentaje", "materia_organica_porcentaje", "materia_organica"],
        ["mo"],
    )

    col["nitrogeno_total"] = find_column(
        columns,
        ["nitrogeno_total", "n_porcentaje"],
        ["n_porcentaje"],
    )

    col["fosforo_disponible"] = find_column(
        columns,
        ["fosforo_disponible", "p_mg_kg"],
        ["p_mg_kg"],
    )

    col["potasio_disponible"] = find_column(
        columns,
        ["potasio_disponible", "k_ppm"],
        ["k_ppm"],
    )

    col["calcio"] = find_column(
        columns,
        ["calcio_ca_cmol_plus_kg"],
        ["calcio", "cmol"],
    )

    col["magnesio"] = find_column(
        columns,
        ["magnesio_mg_cmol_plus_kg"],
        ["magnesio", "cmol"],
    )

    col["sodio"] = find_column(
        columns,
        ["sodio_na_cmol_plus_kg"],
        ["sodio", "cmol"],
    )

    col["potasio"] = find_column(
        columns,
        ["potasio_k_cmol_plus_kg"],
        ["potasio", "cmol"],
    )

    col["aluminio"] = find_column(
        columns,
        [
            "aluminio_intercambiable",
            "aluminio_al_cmol_plus_kg",
            "aluminio_intercambiable_cmol_plus_kg",
        ],
        ["aluminio"],
    )

    col["cice"] = find_column(
        columns,
        ["cice_cmol_plus_kg"],
        ["cice"],
    )

    col["carbonato"] = find_column(
        columns,
        [
            "caco3_porcentaje_equivalente",
            "carbonato_de_calcio_equivalente",
            "carbonato_calcio_equivalente",
        ],
        ["caco3"],
    )

    col["acidez"] = find_column(
        columns,
        ["acidez_hplus_cmol_plus_kg", "acidez_intercambiable"],
        ["acidez"],
    )

    col["arena"] = find_column(
        columns,
        ["arena"],
        ["arena"],
    )

    col["arcilla"] = find_column(
        columns,
        ["arcilla"],
        ["arcilla"],
    )

    col["limo"] = find_column(
        columns,
        ["limo"],
        ["limo"],
    )

    col["clase_textural"] = find_column(
        columns,
        ["clase_textural"],
        ["clase", "textural"],
    )

    return col


# ------------------------------------------------------------
# PDF sections
# ------------------------------------------------------------

def make_title_table():
    data = [
        [
            Paragraph(
                "<b>PERÚ</b><br/>Ministerio de Desarrollo Agrario y Riego",
                small_style(),
            ),
            Paragraph(
                "<b>INIA</b><br/>Instituto Nacional de Innovación Agraria",
                small_style(),
            ),
            Paragraph(
                "<b>LABSAF</b><br/>Laboratorio de Suelos",
                small_style(),
            ),
        ]
    ]

    table = Table(
        data,
        colWidths=[5.8 * cm, 6.0 * cm, 5.8 * cm],
    )

    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    return table


def section_title(text):
    table = Table(
        [[Paragraph(f"<b>{text}</b>", normal_style())]],
        colWidths=[18.0 * cm],
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.lightgrey),
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return table


def make_general_info(row, col):
    def get(name):
        c = col.get(name)
        if not c:
            return ""

        value = row.get(c)

        if value is None:
            return ""

        return str(value)

    cultivo_variedad = get("cultivo")

    variedad = get("variedad")
    if variedad:
        cultivo_variedad = f"{cultivo_variedad} / {variedad}"

    data = [
        [
            Paragraph("<b>DATOS DEL SOLICITANTE</b>", normal_style()),
            "",
            Paragraph("<b>DATOS DE LA MUESTRA</b>", normal_style()),
            "",
        ],
        ["Nombre agricultor", get("nombre"), "Código laboratorio", get("codigo")],
        ["Dirección", get("direccion"), "Fecha recepción", get("fecha_recepcion")],
        ["Nombre parcela", get("parcela"), "Fecha análisis", get("fecha_analisis")],
        ["Altitud", get("altitud"), "Zona", get("zona")],
        ["Cultivo / variedad", cultivo_variedad, "Laboratorio", get("laboratorio")],
    ]

    table = Table(
        data,
        colWidths=[3.1 * cm, 5.9 * cm, 3.1 * cm, 5.9 * cm],
    )

    table.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("SPAN", (2, 0), (3, 0)),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("INNERGRID", (0, 1), (-1, -1), 0.25, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return table


def make_interpretation_table(row, col):
    rows = [
        ("pH", col.get("ph"), "Unidad pH", "6.6 - 7.3"),
        ("CE", col.get("ce"), "mS/m", "<100 - 200"),
        ("Materia Orgánica", col.get("materia_organica"), "%", "1.6 - 3.5"),
        ("Nitrógeno Total", col.get("nitrogeno_total"), "%", "0.10 - 0.15"),
        ("Fósforo disponible", col.get("fosforo_disponible"), "mg/kg", "5.5 - 11"),
        ("Potasio disponible", col.get("potasio_disponible"), "mg/kg", "120 - 240"),
        ("Calcio intercambiable", col.get("calcio"), "cmol(+)/kg", "5.0 - 10"),
        ("Magnesio intercambiable", col.get("magnesio"), "cmol(+)/kg", "1.3 - 3.0"),
        ("Potasio intercambiable", col.get("potasio"), "cmol(+)/kg", "0.3 - 0.6"),
        ("Sodio intercambiable", col.get("sodio"), "cmol(+)/kg", "<0.1 - 0.3"),
        ("Aluminio intercambiable", col.get("aluminio"), "cmol(+)/kg", "<0.1 - 0.25"),
        ("CICe", col.get("cice"), "cmol(+)/kg", "15 - 25"),
        ("Carbonato de Calcio Equivalente", col.get("carbonato"), "%", "<1 - 5"),
        ("Acidez Intercambiable", col.get("acidez"), "cmol(+)/kg", "<0.5"),
    ]

    data = [
        [
            Paragraph("<b>Determinación</b>", normal_style()),
            Paragraph("<b>Result.</b>", normal_style()),
            Paragraph("<b>Unid.</b>", normal_style()),
            Paragraph("<b>Rango adecuado</b>", normal_style()),
            Paragraph("<b>Interpretación</b>", normal_style()),
        ]
    ]

    bg_styles = []

    for i, (label, column_name, unit, rango) in enumerate(rows, start=1):
        value = row.get(column_name) if column_name else None

        result = format_value(value)
        interpretation, bg = get_interpretation(label, value)

        data.append([
            label,
            result,
            unit,
            rango,
            interpretation,
        ])

        bg_styles.append(("BACKGROUND", (4, i), (4, i), bg))

    table = Table(
        data,
        colWidths=[
            4.9 * cm,
            1.9 * cm,
            2.3 * cm,
            3.0 * cm,
            5.9 * cm,
        ],
        repeatRows=1,
    )

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (1, 1), (3, -1), "CENTER"),
        ("ALIGN", (4, 1), (4, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.7),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]

    style.extend(bg_styles)

    table.setStyle(TableStyle(style))

    return table


def make_texture_table(row, col):
    def get(name):
        c = col.get(name)

        if not c:
            return ""

        return format_value(row.get(c))

    def get_text(name):
        c = col.get(name)

        if not c:
            return ""

        value = row.get(c)

        if value is None:
            return ""

        return str(value)

    data = [
        [
            Paragraph("<b>Arena</b>", normal_style()),
            Paragraph("<b>Arcilla</b>", normal_style()),
            Paragraph("<b>Limo</b>", normal_style()),
            Paragraph("<b>Clase textural</b>", normal_style()),
        ],
        [
            get("arena"),
            get("arcilla"),
            get("limo"),
            get_text("clase_textural"),
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
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.8),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return table


def make_simple_note():
    text = (
        "Reporte generado automáticamente desde la base de datos SQLite. "
        "Las interpretaciones son referenciales y pueden ajustarse posteriormente "
        "según las reglas oficiales del laboratorio."
    )

    return Paragraph(text, small_style())


# ------------------------------------------------------------
# Main report generator
# ------------------------------------------------------------

def generate_report(name, cultivo, db_file=DB_FILE, output_pdf=None):
    db_file = Path(db_file)

    row = get_row_by_name_and_cultivo(
        db_file=db_file,
        name=name,
        cultivo=cultivo,
    )

    if row is None:
        raise ValueError(
            f"No record found for name={name!r}, cultivo={cultivo!r}"
        )

    with sqlite3.connect(db_file) as conn:
        columns = get_table_columns(conn)

    col = build_column_mapping(columns)

    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_pdf is None:
        output_pdf = output_dir / (
            f"Informe_{safe_filename(name)}_{safe_filename(cultivo)}.pdf"
        )
    else:
        output_pdf = Path(output_pdf)

    doc = SimpleDocTemplate(
        str(output_pdf),
        pagesize=A4,
        leftMargin=0.8 * cm,
        rightMargin=0.8 * cm,
        topMargin=0.7 * cm,
        bottomMargin=0.7 * cm,
    )

    story = []

    story.append(make_title_table())
    story.append(Spacer(1, 0.18 * cm))

    story.append(Paragraph("<b>INFORMACIÓN GENERAL</b>", title_style()))
    story.append(Spacer(1, 0.12 * cm))

    story.append(make_general_info(row, col))
    story.append(Spacer(1, 0.18 * cm))

    story.append(section_title("INTERPRETACIÓN - ANÁLISIS DE SUELO"))
    story.append(make_interpretation_table(row, col))
    story.append(Spacer(1, 0.18 * cm))

    story.append(section_title("TEXTURA DEL SUELO"))
    story.append(make_texture_table(row, col))
    story.append(Spacer(1, 0.18 * cm))

    story.append(make_simple_note())

    doc.build(story)

    print(f"Report created: {output_pdf}")

    return output_pdf


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate simple soil report PDF from SQLite database."
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

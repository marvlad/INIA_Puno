# app_simulator.py

import argparse
import unicodedata
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, send_from_directory

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from fertilization_dose import calculate_fertilization_dose
from nutrient_extraction import value_to_float
from nutrient_extraction import build_nutrient_extraction_rows

from optimizer_from_riqueza import (
    NUTRIENTS,
    optimize_fertilizers,
    nutrient_apport,
    effective_requirements,
)

from get_optimized_fertilization_by_name import (
    requirements_from_dose_result,
)

from get_fertilization_dose_by_name import (
    get_crop_period_months,
)


DB_FILE = "database/inia_database.sqlite"

EXTRACTION_CSV = "config/Extraccion_Nut.csv"
CONVERSION_FACTORS_CSV = "config/fertilizer_conversion_factors.csv"
RIQUEZA_CSV = "config/Riqueza_Fert.csv"

OUTPUT_DIR = "simulator_outputs"

app = Flask(__name__)
app.secret_key = "inia-simulator-secret-key"


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_text(value):
    if value is None:
        return ""

    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )

    cleaned = []

    for char in text:
        if char.isalnum() or char.isspace():
            cleaned.append(char)
        else:
            cleaned.append(" ")

    text = "".join(cleaned)
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
        text = "simulacion"

    return text


def as_float(value, default=0.0):
    result = value_to_float(value, None)

    if result is None:
        return default

    return result


def fmt(value, digits=2):
    value = value_to_float(value, None)

    if value is None:
        return ""

    return f"{value:.{digits}f}"


def form_value(form, key, default=""):
    return form.get(key, default)


# ============================================================
# FORM ROW BUILDER
# ============================================================

def build_row_from_form(form):
    """
    Build a row dictionary compatible with the NoExcel calculation modules.
    """

    name = form_value(form, "name", "").strip()
    cultivo = form_value(form, "cultivo", "").strip()
    codigo = form_value(form, "codigo", "").strip()
    distrito = form_value(form, "distrito", "").strip()
    clima = form_value(form, "clima", "").strip()
    clase_textural = form_value(form, "clase_textural", "").strip()

    row = {
        "nombres_y_apellidos": name,
        "cultivo_a_instalar": cultivo,
        "codigo": codigo,
        "distrito": distrito,
        "dist": distrito,
        "clima": clima,
        "clase_textural": clase_textural,

        # Soil / lab values
        "ph": as_float(form_value(form, "ph")),
        "ce_ms_m": as_float(form_value(form, "ce_ms_m")),
        "carbonato_de_calcio_equivalente": as_float(form_value(form, "caco3")),
        "materia_organica": as_float(form_value(form, "mo")),
        "mo": as_float(form_value(form, "mo")),

        # Texture
        "arena": as_float(form_value(form, "arena")),
        "arcilla": as_float(form_value(form, "arcilla")),
        "limo": as_float(form_value(form, "limo")),

        # Exchangeable cations
        "calcio_ca_cmol_plus_kg": as_float(form_value(form, "ca")),
        "magnesio_mg_cmol_plus_kg": as_float(form_value(form, "mg")),
        "sodio_na_cmol_plus_kg": as_float(form_value(form, "na")),
        "potasio_k_cmol_plus_kg": as_float(form_value(form, "k_cmol")),

        # Exact Al + H columns
        "aluminio_intercambiable_cmol_plus_kg": as_float(form_value(form, "aluminio")),
        "acidez_hplus_cmol_plus_kg": as_float(form_value(form, "acidez")),

        # Nutrients
        "n": as_float(form_value(form, "n_percent")),
        "n_": as_float(form_value(form, "n_percent")),
        "k_ppm": as_float(form_value(form, "k_ppm")),
        "p_mg_kg": as_float(form_value(form, "p_mg_kg")),

        # Extra aliases, useful if other modules expect them
        "ce": as_float(form_value(form, "ce_ms_m")),
        "caco3": as_float(form_value(form, "caco3")),
        "ca": as_float(form_value(form, "ca")),
        "mg": as_float(form_value(form, "mg")),
        "na": as_float(form_value(form, "na")),
        "k": as_float(form_value(form, "k_cmol")),
        "aluminio": as_float(form_value(form, "aluminio")),
        "acidez": as_float(form_value(form, "acidez")),
    }

    return row


# ============================================================
# SIMULATION
# ============================================================

def get_rdto_estimado_from_extraction(cultivo):
    """
    Uses the same convention as the reports:
    the value in Rendimiento is treated as ton/ha.
    """

    extraction = build_nutrient_extraction_rows(
        cultivo=cultivo,
        extraction_csv=EXTRACTION_CSV,
        conversion_factors_csv=CONVERSION_FACTORS_CSV,
    )

    crop_row = extraction.get("crop_row", {})

    for key, value in crop_row.items():
        if "rendimiento" in normalize_text(key):
            return as_float(value, 0.0)

    return 0.0


def build_extraction_table(cultivo, rdto_estimado):
    extraction = build_nutrient_extraction_rows(
        cultivo=cultivo,
        extraction_csv=EXTRACTION_CSV,
        conversion_factors_csv=CONVERSION_FACTORS_CSV,
    )

    rows = []

    for item in extraction["rows"]:
        req_kg_ton = as_float(item.get("requerimiento_kg_ton"))
        fc = as_float(item.get("fc_forma_fertilizante"))
        req_rdto = req_kg_ton * rdto_estimado
        necesidad = req_rdto * fc

        rows.append({
            "nutriente": item.get("nutriente", ""),
            "requerimiento_kg_ton": req_kg_ton,
            "requerimiento_rdto_kg_ha": req_rdto,
            "fc_forma_fertilizante": fc,
            "necesidad_forma_fertilizante": necesidad,
        })

    return rows


def build_balance_rows(optimizer_result, requirements):
    selected_names = list(getattr(optimizer_result, "selected_fertilizers", []))
    doses = list(getattr(optimizer_result, "x", []))
    fertilizer_table = getattr(optimizer_result, "fertilizer_table", {})

    formula_rows = []
    aporte_rows = []
    total_aporte = {nutrient: 0.0 for nutrient in NUTRIENTS}

    for fertilizer_name, dose in zip(selected_names, doses):
        dose = as_float(dose)

        if dose <= 0:
            continue

        formula_data = fertilizer_table.get(fertilizer_name, {})

        formula_row = {
            "fertilizer": fertilizer_name,
            "dose_kg_ha": dose,
            "sacks_ha": dose / 50.0,
            "formula": {},
        }

        aporte_row = {
            "fertilizer": fertilizer_name,
            "aporte": {},
        }

        for nutrient in NUTRIENTS:
            formula_value = as_float(formula_data.get(nutrient))
            aporte = dose * formula_value / 100.0

            total_aporte[nutrient] += aporte
            formula_row["formula"][nutrient] = formula_value
            aporte_row["aporte"][nutrient] = aporte

        formula_rows.append(formula_row)
        aporte_rows.append(aporte_row)

    summary = []

    for nutrient, req in zip(NUTRIENTS, requirements):
        req_value = as_float(req)
        supplied = total_aporte[nutrient]

        summary.append({
            "nutrient": nutrient,
            "supplied": supplied,
            "requirement": req_value,
            "difference": supplied - req_value,
        })

    return {
        "formula_rows": formula_rows,
        "aporte_rows": aporte_rows,
        "summary": summary,
        "total_aporte": total_aporte,
    }


def simulate_from_row(row):
    cultivo = row.get("cultivo_a_instalar", "")

    permanencia_meses = get_crop_period_months(
        cultivo=cultivo,
        extraction_csv=EXTRACTION_CSV,
    )

    rdto_estimado = get_rdto_estimado_from_extraction(cultivo)

    extraction_rows = build_extraction_table(
        cultivo=cultivo,
        rdto_estimado=rdto_estimado,
    )

    dose_result = calculate_fertilization_dose(
        row=row,
        permanencia_cultivo_meses=permanencia_meses,
        cultivo=cultivo,
        extraction_csv=EXTRACTION_CSV,
        conversion_factors_csv=CONVERSION_FACTORS_CSV,
    )

    requirements = requirements_from_dose_result(dose_result)
    requirements_used = effective_requirements(requirements)

    optimizer_result = optimize_fertilizers(
        requirements=requirements,
        ph=row.get("ph"),
        riqueza_csv=RIQUEZA_CSV,
    )

    supplied = nutrient_apport(
        optimizer_result.x,
        optimizer_result.selected_fertilizers,
        optimizer_result.fertilizer_table,
    )

    nutrient_rows = []

    for i, nutrient in enumerate(NUTRIENTS):
        nutrient_rows.append({
            "nutrient": nutrient,
            "requirement_real": requirements[i],
            "requirement_used": requirements_used[i],
            "supplied": supplied[i],
            "difference": supplied[i] - requirements[i],
        })

    fertilizer_rows = []

    for name, dose in zip(
        optimizer_result.selected_fertilizers,
        optimizer_result.x,
    ):
        dose = as_float(dose)

        if dose <= 0:
            continue

        fertilizer_rows.append({
            "fertilizer": name,
            "dose_kg_ha": dose,
            "sacks_ha": dose / 50.0,
        })

    balance = build_balance_rows(
        optimizer_result=optimizer_result,
        requirements=requirements,
    )

    soil_rows = [
        {"label": "pH", "value": row.get("ph"), "unit": ""},
        {"label": "CE", "value": row.get("ce_ms_m"), "unit": "mS/m"},
        {"label": "CaCO3", "value": row.get("carbonato_de_calcio_equivalente"), "unit": "%"},
        {"label": "Aluminio intercambiable", "value": row.get("aluminio_intercambiable_cmol_plus_kg"), "unit": "cmol(+)/kg"},
        {"label": "Acidez H+", "value": row.get("acidez_hplus_cmol_plus_kg"), "unit": "cmol(+)/kg"},
        {
            "label": "Al3+ + H+",
            "value": as_float(row.get("aluminio_intercambiable_cmol_plus_kg")) + as_float(row.get("acidez_hplus_cmol_plus_kg")),
            "unit": "cmol(+)/kg",
        },
        {"label": "MO", "value": row.get("materia_organica"), "unit": "%"},
        {"label": "Arena", "value": row.get("arena"), "unit": "%"},
        {"label": "Arcilla", "value": row.get("arcilla"), "unit": "%"},
        {"label": "Limo", "value": row.get("limo"), "unit": "%"},
        {"label": "Clase textural", "value": row.get("clase_textural"), "unit": ""},
        {"label": "Calcio Ca", "value": row.get("calcio_ca_cmol_plus_kg"), "unit": "cmol(+)/kg"},
        {"label": "Magnesio Mg", "value": row.get("magnesio_mg_cmol_plus_kg"), "unit": "cmol(+)/kg"},
        {"label": "Sodio Na", "value": row.get("sodio_na_cmol_plus_kg"), "unit": "cmol(+)/kg"},
        {"label": "Potasio K", "value": row.get("potasio_k_cmol_plus_kg"), "unit": "cmol(+)/kg"},
        {"label": "N", "value": row.get("n"), "unit": "%"},
        {"label": "K", "value": row.get("k_ppm"), "unit": "ppm"},
        {"label": "P", "value": row.get("p_mg_kg"), "unit": "mg/kg"},
    ]

    return {
        "row": row,
        "cultivo": cultivo,
        "permanencia_meses": permanencia_meses,
        "rdto_estimado": rdto_estimado,
        "soil_rows": soil_rows,
        "extraction_rows": extraction_rows,
        "dose_result": dose_result,
        "requirements": requirements,
        "requirements_used": requirements_used,
        "optimizer_result": optimizer_result,
        "supplied": supplied,
        "nutrient_rows": nutrient_rows,
        "fertilizer_rows": fertilizer_rows,
        "balance": balance,
    }


# ============================================================
# PDF GENERATION
# ============================================================

def pdf_paragraph(text, style):
    return Paragraph(str(text), style)


def make_pdf_table(data, col_widths=None, font_size=7, header_rows=1):
    table = Table(data, colWidths=col_widths, repeatRows=header_rows)

    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.black),
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#555555")),
        ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white),
        ("FONTNAME", (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
        ("FONTNAME", (0, header_rows), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    return table


def section_title(text, page_width):
    table = Table([[text]], colWidths=[page_width])

    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e9e6db")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    return table


def create_simulation_pdf(simulation, output_pdf):
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    page_size = landscape(A4)

    doc = SimpleDocTemplate(
        str(output_pdf),
        pagesize=page_size,
        leftMargin=0.7 * cm,
        rightMargin=0.7 * cm,
        topMargin=0.7 * cm,
        bottomMargin=0.7 * cm,
    )

    page_width = page_size[0] - doc.leftMargin - doc.rightMargin

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CenterTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        alignment=1,
        leading=16,
    ))

    story = []

    row = simulation["row"]

    story.append(pdf_paragraph("SIMULADOR INIA - REPORTE DE FERTILIZACIÓN", styles["CenterTitle"]))
    story.append(Spacer(1, 0.2 * cm))

    general_data = [
        ["Nombre", row.get("nombres_y_apellidos", ""), "Cultivo", row.get("cultivo_a_instalar", ""), "Código", row.get("codigo", "")],
        ["Distrito", row.get("distrito", ""), "Clima", row.get("clima", ""), "Clase textural", row.get("clase_textural", "")],
        ["RDTO estimado", fmt(simulation["rdto_estimado"], 2), "Permanencia meses", fmt(simulation["permanencia_meses"], 1), "Fecha", datetime.now().strftime("%Y-%m-%d %H:%M")],
    ]

    story.append(make_pdf_table(
        general_data,
        col_widths=[
            page_width * 0.12,
            page_width * 0.20,
            page_width * 0.10,
            page_width * 0.18,
            page_width * 0.12,
            page_width * 0.28,
        ],
        font_size=7,
        header_rows=0,
    ))
    story.append(Spacer(1, 0.2 * cm))

    story.append(section_title("DATOS DE ANÁLISIS DE SUELO", page_width))
    soil_data = [["Variable", "Valor", "Unidad"]]
    for item in simulation["soil_rows"]:
        soil_data.append([
            item["label"],
            fmt(item["value"], 3) if isinstance(item["value"], (int, float)) else item["value"],
            item["unit"],
        ])

    story.append(make_pdf_table(
        soil_data,
        col_widths=[page_width * 0.45, page_width * 0.25, page_width * 0.30],
        font_size=7,
        header_rows=1,
    ))
    story.append(Spacer(1, 0.2 * cm))

    story.append(section_title("EXTRACCIÓN DE NUTRIENTES", page_width))
    extraction_data = [[
        "Nutriente",
        "Requerimiento kg/ton",
        "Requerimiento RDTO kg/ha",
        "FC forma fert.",
        "Necesidad forma fert.",
    ]]

    for item in simulation["extraction_rows"]:
        extraction_data.append([
            item["nutriente"],
            fmt(item["requerimiento_kg_ton"], 2),
            fmt(item["requerimiento_rdto_kg_ha"], 2),
            fmt(item["fc_forma_fertilizante"], 2),
            fmt(item["necesidad_forma_fertilizante"], 2),
        ])

    story.append(make_pdf_table(
        extraction_data,
        col_widths=[
            page_width * 0.18,
            page_width * 0.20,
            page_width * 0.22,
            page_width * 0.18,
            page_width * 0.22,
        ],
        font_size=7,
        header_rows=1,
    ))
    story.append(Spacer(1, 0.2 * cm))

    story.append(section_title("REQUERIMIENTOS, SUMA DE NUTRIENTES Y DIFERENCIA", page_width))
    nutrient_data = [[
        "Nutriente",
        "Requerimiento real",
        "Req. usado optimizador",
        "Suma de nutrientes",
        "Diferencia",
    ]]

    for item in simulation["nutrient_rows"]:
        nutrient_data.append([
            item["nutrient"],
            fmt(item["requirement_real"], 2),
            fmt(item["requirement_used"], 2),
            fmt(item["supplied"], 2),
            fmt(item["difference"], 2),
        ])

    story.append(make_pdf_table(
        nutrient_data,
        col_widths=[
            page_width * 0.16,
            page_width * 0.21,
            page_width * 0.21,
            page_width * 0.21,
            page_width * 0.21,
        ],
        font_size=7,
        header_rows=1,
    ))
    story.append(Spacer(1, 0.2 * cm))

    story.append(section_title("FERTILIZANTES SELECCIONADOS POR EL OPTIMIZADOR", page_width))
    fert_data = [["Fertilizante", "Dosis kg/ha", "Sacos/ha"]]

    for item in simulation["fertilizer_rows"]:
        fert_data.append([
            item["fertilizer"],
            fmt(item["dose_kg_ha"], 1),
            fmt(item["sacks_ha"], 1),
        ])

    story.append(make_pdf_table(
        fert_data,
        col_widths=[page_width * 0.60, page_width * 0.20, page_width * 0.20],
        font_size=7,
        header_rows=1,
    ))
    story.append(Spacer(1, 0.2 * cm))

    story.append(section_title("BALANCEO DE ENMIENDAS Y FERTILIZANTES", page_width))

    formula_data = [[
        "Fertilizante",
        "Dosis kg/ha",
        "Sacos/ha",
        "N",
        "P2O5",
        "K2O",
        "CaO",
        "MgO",
        "S",
    ]]

    for item in simulation["balance"]["formula_rows"]:
        formula_data.append([
            item["fertilizer"],
            fmt(item["dose_kg_ha"], 0),
            fmt(item["sacks_ha"], 1),
            fmt(item["formula"]["N"], 2),
            fmt(item["formula"]["P2O5"], 2),
            fmt(item["formula"]["K2O"], 2),
            fmt(item["formula"]["CaO"], 2),
            fmt(item["formula"]["MgO"], 2),
            fmt(item["formula"]["S"], 2),
        ])

    story.append(make_pdf_table(
        formula_data,
        col_widths=[
            page_width * 0.30,
            page_width * 0.10,
            page_width * 0.10,
            page_width * 0.08,
            page_width * 0.08,
            page_width * 0.08,
            page_width * 0.08,
            page_width * 0.08,
            page_width * 0.10,
        ],
        font_size=6.5,
        header_rows=1,
    ))
    story.append(Spacer(1, 0.15 * cm))

    aporte_data = [[
        "Fertilizante",
        "N",
        "P2O5",
        "K2O",
        "CaO",
        "MgO",
        "S",
    ]]

    for item in simulation["balance"]["aporte_rows"]:
        aporte_data.append([
            item["fertilizer"],
            fmt(item["aporte"]["N"], 2),
            fmt(item["aporte"]["P2O5"], 2),
            fmt(item["aporte"]["K2O"], 2),
            fmt(item["aporte"]["CaO"], 2),
            fmt(item["aporte"]["MgO"], 2),
            fmt(item["aporte"]["S"], 2),
        ])

    story.append(make_pdf_table(
        aporte_data,
        col_widths=[
            page_width * 0.34,
            page_width * 0.11,
            page_width * 0.11,
            page_width * 0.11,
            page_width * 0.11,
            page_width * 0.11,
            page_width * 0.11,
        ],
        font_size=6.5,
        header_rows=1,
    ))

    doc.build(story)

    return output_pdf


# ============================================================
# ROUTES
# ============================================================

@app.route("/", methods=["GET", "POST"])
def index():
    simulation = None
    pdf_file = None
    error = None

    if request.method == "POST":
        action = request.form.get("action", "simulate")
        row = build_row_from_form(request.form)

        try:
            simulation = simulate_from_row(row)

            if action == "download_pdf":
                safe_name = safe_filename(row.get("nombres_y_apellidos", ""))
                safe_crop = safe_filename(row.get("cultivo_a_instalar", ""))

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"simulador_{safe_name}_{safe_crop}_{timestamp}.pdf"

                output_pdf = Path(OUTPUT_DIR) / filename

                create_simulation_pdf(
                    simulation=simulation,
                    output_pdf=output_pdf,
                )

                pdf_file = filename

        except Exception as exc:
            error = str(exc)

    return render_template(
        "index.html",
        simulation=simulation,
        pdf_file=pdf_file,
        error=error,
        fmt=fmt,
        nutrients=NUTRIENTS,
    )


@app.route("/outputs/<path:filename>")
def outputs(filename):
    return send_from_directory(
        OUTPUT_DIR,
        filename,
        as_attachment=True,
    )


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="INIA fertilizer simulator web app."
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

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()

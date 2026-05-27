# make_recommendation_by_name.py

import argparse
import sqlite3
import unicodedata
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)

from fertilization_dose import calculate_fertilization_dose
from nutrient_extraction import find_crop_row, value_to_float

from optimizer_from_riqueza import (
    NUTRIENTS,
    optimize_fertilizers,
    effective_requirements,
    nutrient_apport,
)


DB_FILE = "database/inia_database.sqlite"
TABLE_NAME = "muestras"

EXTRACTION_CSV = "config/Extraccion_Nut.csv"
CONVERSION_FACTORS_CSV = "config/fertilizer_conversion_factors.csv"
RIQUEZA_CSV = "config/Riqueza_Fert.csv"

OUTPUT_DIR = "recommendation_reports"

PAGE_WIDTH_CM = 19.8


def normalize_text(value):
    if value is None:
        return ""

    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )
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
        text = "reporte"

    return text


def find_column_by_words(fieldnames, words):
    words = [normalize_text(w) for w in words]

    for field in fieldnames:
        field_norm = normalize_text(field)

        if all(word in field_norm for word in words):
            return field

    return None


def get_crop_period_months(cultivo, extraction_csv=EXTRACTION_CSV):
    crop_row, fieldnames, crop_col, code_col = find_crop_row(
        cultivo=cultivo,
        csv_file=extraction_csv,
    )

    period_col = find_column_by_words(
        fieldnames,
        ["periodo", "vegetativo"],
    )

    if period_col is None:
        raise ValueError(
            f"Could not find Periodo vegetativo column in {extraction_csv}"
        )

    period = value_to_float(crop_row.get(period_col))

    if period is None:
        raise ValueError(
            f"Invalid Periodo vegetativo for cultivo={cultivo!r}: "
            f"{crop_row.get(period_col)!r}"
        )

    return period


def get_row_by_name_and_crop(db_file, name, cultivo):
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
            LIMIT 1
        """

        cur.execute(query, (f"%{name_norm}%", f"%{cultivo_norm}%"))
        row = cur.fetchone()

        if row is not None:
            return dict(row)

    return None


def requirements_from_dose_result(dose_result):
    by_symbol = {
        item["nutriente"]: item
        for item in dose_result["rows"]
    }

    mapping = {
        "N": "N",
        "P2O5": "P",
        "K2O": "K",
        "CaO": "Ca",
        "MgO": "Mg",
        "S": "S",
    }

    requirements = []

    for optimizer_nutrient in NUTRIENTS:
        dose_symbol = mapping[optimizer_nutrient]
        value = by_symbol[dose_symbol]["requerimiento_final_fertilizante_kg_ha"]
        requirements.append(value_to_float(value, 0.0))

    return requirements


def format_number(value, digits=0):
    value = value_to_float(value, None)

    if value is None:
        return ""

    return f"{value:.{digits}f}"


def get_selected_fertilizers(result):
    selected = []

    for name, dose in zip(result.selected_fertilizers, result.x):
        dose = value_to_float(dose, 0.0)

        if dose > 0:
            selected.append({
                "name": name,
                "dose_kg_ha": dose,
                "sacos_ha": dose / 50.0,
            })

    return selected


def classify_application_time(fertilizer_name):
    name = normalize_text(fertilizer_name)

    if "estiercol" in name or "guano" in name:
        return "Aplicar antes de la siembra"

    if "urea" in name or "nitrato" in name or "amonio" in name:
        return "Aplicar al primer aporque"

    return "Aplicar a la siembra"


def split_fertilizers_by_application(selected_fertilizers):
    before_sowing = []
    sowing = []
    first_hilling = []

    for item in selected_fertilizers:
        application = classify_application_time(item["name"])

        item = dict(item)
        item["application"] = application

        if application == "Aplicar antes de la siembra":
            before_sowing.append(item)
        elif application == "Aplicar al primer aporque":
            first_hilling.append(item)
        else:
            sowing.append(item)

    return before_sowing, sowing, first_hilling


def build_recommendation_data(
    row,
    extraction_csv=EXTRACTION_CSV,
    conversion_factors_csv=CONVERSION_FACTORS_CSV,
    riqueza_csv=RIQUEZA_CSV,
):
    cultivo = row.get("cultivo_a_instalar", "")

    permanencia_meses = get_crop_period_months(
        cultivo=cultivo,
        extraction_csv=extraction_csv,
    )

    dose_result = calculate_fertilization_dose(
        row=row,
        permanencia_cultivo_meses=permanencia_meses,
        cultivo=cultivo,
        extraction_csv=extraction_csv,
        conversion_factors_csv=conversion_factors_csv,
    )

    requirements = requirements_from_dose_result(dose_result)

    result = optimize_fertilizers(
        requirements=requirements,
        ph=row.get("ph"),
        riqueza_csv=riqueza_csv,
    )

    selected_fertilizers = get_selected_fertilizers(result)

    before_sowing, sowing, first_hilling = split_fertilizers_by_application(
        selected_fertilizers
    )

    requirements_used = effective_requirements(requirements)

    supplied = nutrient_apport(
        result.x,
        result.selected_fertilizers,
        result.fertilizer_table,
    )

    return {
        "row": row,
        "cultivo": cultivo,
        "permanencia_meses": permanencia_meses,
        "dose_result": dose_result,
        "requirements": requirements,
        "requirements_used": requirements_used,
        "optimization_result": result,
        "supplied": supplied,
        "selected_fertilizers": selected_fertilizers,
        "before_sowing": before_sowing,
        "sowing": sowing,
        "first_hilling": first_hilling,
    }


def make_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="TitleCenter",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        alignment=1,
        leading=14,
    ))

    styles.add(ParagraphStyle(
        name="Small",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        name="SmallBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        name="Tiny",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=8,
    ))

    styles.add(ParagraphStyle(
        name="TinyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8,
    ))

    styles.add(ParagraphStyle(
        name="BlueTiny",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=8,
        textColor=colors.blue,
    ))

    return styles


def p(text, style):
    return Paragraph(str(text), style)


def section_title(title, styles, width=PAGE_WIDTH_CM * cm):
    table = Table(
        [[p(title, styles["SmallBold"])]],
        colWidths=[width],
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#c9c9c9")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    return table


def make_header(row, data, styles):
    title = Table(
        [[
            p("<b>PERÚ</b><br/>Ministerio de Desarrollo Agrario y Riego", styles["Tiny"]),
            p("<b>INIA</b><br/>Instituto Nacional de Innovación Agraria", styles["Tiny"]),
            p("<b>LABSAF</b><br/>Laboratorio de Suelos", styles["Tiny"]),
        ]],
        colWidths=[6.0 * cm, 7.0 * cm, 6.8 * cm],
    )

    title.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    info_title = Table(
        [[p("INFORMACIÓN GENERAL", styles["TitleCenter"])]],
        colWidths=[PAGE_WIDTH_CM * cm],
    )

    info_title.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    general = [
        [
            p("AGRICULTOR", styles["TinyBold"]),
            p(row.get("nombres_y_apellidos", ""), styles["Tiny"]),
            p("SIST. PRODUCCIÓN", styles["TinyBold"]),
            p("Convencional", styles["Tiny"]),
        ],
        [
            p("UBICACIÓN PARCELA", styles["TinyBold"]),
            p(row.get("dist", ""), styles["Tiny"]),
            p("FECHA DE EMISIÓN", styles["TinyBold"]),
            p("-", styles["Tiny"]),
        ],
        [
            p("NOMBRE PARCELA", styles["TinyBold"]),
            p(row.get("localidad_comunidad_caserio_asociacion_etc", ""), styles["Tiny"]),
            p("RDTO ESTIMADO (t/ha)", styles["TinyBold"]),
            p(format_number(data["dose_result"].get("rendimiento_kg_ha", 0), 1), styles["Tiny"]),
        ],
        [
            p("CULTIVO / VAR.", styles["TinyBold"]),
            p(row.get("cultivo_a_instalar", ""), styles["Tiny"]),
            p("PERMANENCIA CULT. (meses)", styles["TinyBold"]),
            p(format_number(data["permanencia_meses"], 1), styles["Tiny"]),
        ],
        [
            p("CÓDIGO LABORATORIO", styles["TinyBold"]),
            p(row.get("codigo", ""), styles["Tiny"]),
            p("", styles["TinyBold"]),
            p("", styles["Tiny"]),
        ],
    ]

    table = Table(
        general,
        colWidths=[
            4.0 * cm,
            6.5 * cm,
            5.0 * cm,
            4.3 * cm,
        ],
    )

    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#595959")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#595959")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    return [title, info_title, table, Spacer(1, 0.18 * cm)]


def make_general_recommendation_table(data, styles):
    req = {
        nutrient: value_to_float(value, 0.0)
        for nutrient, value in zip(NUTRIENTS, data["requirements"])
    }

    table_data = [
        [
            p("CULTIVO", styles["TinyBold"]),
            p("N<br/>(kg/ha)", styles["TinyBold"]),
            p("P2O5<br/>(kg/ha)", styles["TinyBold"]),
            p("K2O<br/>(kg/ha)", styles["TinyBold"]),
            p("RECOMENDACIÓN DE ENCALAMIENTO", styles["TinyBold"]),
        ],
        [
            p(data["cultivo"], styles["Tiny"]),
            p(format_number(max(req.get("N", 0.0), 0.0), 0), styles["Tiny"]),
            p(format_number(max(req.get("P2O5", 0.0), 0.0), 0), styles["Tiny"]),
            p(format_number(max(req.get("K2O", 0.0), 0.0), 0), styles["Tiny"]),
            p("No es necesario aplicar cal", styles["Tiny"]),
        ],
    ]

    table = Table(
        table_data,
        colWidths=[
            3.3 * cm,
            2.5 * cm,
            2.7 * cm,
            2.5 * cm,
            8.8 * cm,
        ],
    )

    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c9c9c9")),
        ("ALIGN", (1, 0), (3, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    return table


def make_product_table(data, styles):
    selected = data["selected_fertilizers"]

    rows = [
        [
            p("PRODUCTO COMERCIAL RECOMENDADO", styles["TinyBold"]),
            p("DOSIS (kg/ha)", styles["TinyBold"]),
            p("ÉPOCA DE APLICACIÓN", styles["TinyBold"]),
        ]
    ]

    for item in selected:
        rows.append([
            p(item["name"], styles["Tiny"]),
            p(format_number(item["dose_kg_ha"], 1), styles["Tiny"]),
            p(classify_application_time(item["name"]), styles["TinyBold"]),
        ])

    table = Table(
        rows,
        colWidths=[
            8.0 * cm,
            3.0 * cm,
            8.8 * cm,
        ],
    )

    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c9c9c9")),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    return table


def make_observations(data, styles):
    rendimiento = data["dose_result"].get("rendimiento_kg_ha", "")

    table_data = [
        [p("OBSERVACIONES", styles["SmallBold"])],
        [
            p(
                "La dosis de fertilización es de acuerdo a los análisis de suelos, "
                "demanda nutricional de la planta y un rendimiento proyectado de: "
                f"<b>{format_number(rendimiento, 1)} t/ha</b>",
                styles["Small"],
            )
        ],
    ]

    table = Table(
        table_data,
        colWidths=[PAGE_WIDTH_CM * cm],
    )

    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c9c9c9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    return table


def make_dosis_section(data, styles):
    before_sowing = data["before_sowing"]
    sowing = data["sowing"]
    first_hilling = data["first_hilling"]

    story = []

    story.append(section_title("DOSIS DE FERTILIZACIÓN", styles))
    story.append(Spacer(1, 0.18 * cm))

    story.append(
        p(
            "<b>1. Primera Fertilización (A la Siembra)</b>",
            styles["SmallBold"],
        )
    )
    story.append(Spacer(1, 0.08 * cm))

    story.append(
        p(
            "Se recomienda aplicar el abono orgánico antes de sembrar, "
            "esparciéndolo parejo sobre el terreno, o durante la siembra, "
            "colocándolo en el fondo del surco a chorro continuo.",
            styles["Small"],
        )
    )
    story.append(Spacer(1, 0.20 * cm))

    if before_sowing:
        organic_rows = [
            [
                p("Abono Orgánico", styles["TinyBold"]),
                p("Producto", styles["TinyBold"]),
                p("Dosis", styles["TinyBold"]),
                p("Unidad", styles["TinyBold"]),
                p("Recomendación", styles["TinyBold"]),
            ]
        ]

        for item in before_sowing:
            organic_rows.append([
                p("Abono Orgánico", styles["Tiny"]),
                p(item["name"], styles["Tiny"]),
                p(format_number(item["dose_kg_ha"], 1), styles["TinyBold"]),
                p("kg/ha", styles["TinyBold"]),
                p("Aplicar descompuesto", styles["TinyBold"]),
            ])

        organic_table = Table(
            organic_rows,
            colWidths=[
                3.2 * cm,
                4.7 * cm,
                2.0 * cm,
                1.8 * cm,
                8.1 * cm,
            ],
        )

        organic_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
            ("ALIGN", (2, 0), (3, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))

        story.append(organic_table)
        story.append(Spacer(1, 0.20 * cm))

    if sowing:
        rows = [
            [
                p("Fertilizantes Químicos", styles["TinyBold"]),
                p("Producto", styles["TinyBold"]),
                p("Dosis", styles["TinyBold"]),
                p("Unidad", styles["TinyBold"]),
                p("Instrucción", styles["TinyBold"]),
            ]
        ]

        total = 0.0

        for item in sowing:
            total += item["dose_kg_ha"]

            rows.append([
                p("Mezclar bien los siguientes fertilizantes:", styles["Tiny"]),
                p(item["name"], styles["Tiny"]),
                p(format_number(item["dose_kg_ha"], 1), styles["Tiny"]),
                p("kg/ha", styles["Tiny"]),
                p(
                    "Aplicar la mezcla de fertilizantes a 5-10 cm de las semillas, "
                    "evitando el contacto directo.",
                    styles["BlueTiny"],
                ),
            ])

        rows.append([
            p("", styles["Tiny"]),
            p("<b>Total Mezcla:</b>", styles["TinyBold"]),
            p(f"<b>{format_number(total, 1)}</b>", styles["TinyBold"]),
            p("<b>kg/ha</b>", styles["TinyBold"]),
            p("", styles["Tiny"]),
        ])

        chemical_table = Table(
            rows,
            colWidths=[
                3.6 * cm,
                4.5 * cm,
                2.0 * cm,
                1.8 * cm,
                7.9 * cm,
            ],
        )

        chemical_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
            ("ALIGN", (2, 0), (3, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))

        story.append(chemical_table)
        story.append(Spacer(1, 0.30 * cm))

    story.append(
        p(
            "<b>2. Segunda Fertilización (Al primer aporque)</b>",
            styles["SmallBold"],
        )
    )
    story.append(Spacer(1, 0.08 * cm))

    story.append(
        p(
            "Aplicar pequeñas cantidades de fertilizante a 5-10 cm de las plantas, "
            "evitando el contacto directo para prevenir quemaduras, y cubrirlo con "
            "tierra durante el aporque.",
            styles["Small"],
        )
    )
    story.append(Spacer(1, 0.20 * cm))

    if first_hilling:
        rows = [
            [
                p("Fertilizante", styles["TinyBold"]),
                p("Producto", styles["TinyBold"]),
                p("Dosis", styles["TinyBold"]),
                p("Unidad", styles["TinyBold"]),
                p("Época", styles["TinyBold"]),
            ]
        ]

        total = 0.0

        for item in first_hilling:
            total += item["dose_kg_ha"]

            rows.append([
                p("Fertilizante", styles["Tiny"]),
                p(item["name"], styles["Tiny"]),
                p(format_number(item["dose_kg_ha"], 1), styles["Tiny"]),
                p("kg/ha", styles["Tiny"]),
                p("Aplicar al primer aporque", styles["Tiny"]),
            ])

        rows.append([
            p("", styles["Tiny"]),
            p("<b>Total</b>", styles["TinyBold"]),
            p(f"<b>{format_number(total, 1)}</b>", styles["TinyBold"]),
            p("<b>kg/ha</b>", styles["TinyBold"]),
            p("", styles["Tiny"]),
        ])

        table = Table(
            rows,
            colWidths=[
                3.2 * cm,
                4.7 * cm,
                2.0 * cm,
                1.8 * cm,
                8.1 * cm,
            ],
        )

        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
            ("ALIGN", (2, 0), (3, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))

        story.append(table)
        story.append(Spacer(1, 0.30 * cm))

    story.append(
        p(
            "3. Los abonos deben cubrirse con al menos 3-5 cm de tierra para evitar "
            "que se pierdan con el agua o el aire y asegurar que lleguen a las raíces. "
            "Aplique los abonos en suelo húmedo o riegue después para que se disuelvan "
            "y las plantas los absorban mejor.",
            styles["Small"],
        )
    )

    return story


def create_recommendation_pdf(data, output_pdf):
    styles = make_styles()

    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_pdf),
        pagesize=A4,
        rightMargin=0.6 * cm,
        leftMargin=0.6 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
    )

    row = data["row"]

    story = []

    story.extend(make_header(row, data, styles))

    story.append(section_title(
        "RECOMENDACIONES GENERALES SEGÚN RESULTADOS DEL ANÁLISIS DE SUELOS",
        styles,
    ))
    story.append(Spacer(1, 0.08 * cm))

    story.append(make_general_recommendation_table(data, styles))
    story.append(Spacer(1, 0.10 * cm))

    story.append(make_product_table(data, styles))
    story.append(Spacer(1, 0.10 * cm))

    story.append(make_observations(data, styles))
    story.append(Spacer(1, 0.14 * cm))

    story.extend(make_dosis_section(data, styles))

    doc.build(story)

    print(f"\nRecommendation PDF created: {output_pdf}")

    return output_pdf


def print_terminal_summary(data):
    print("\nRECOMENDACIÓN DE FERTILIZACIÓN")
    print("=" * 90)

    row = data["row"]

    print(f"Agricultor: {row.get('nombres_y_apellidos', '')}")
    print(f"Cultivo:    {row.get('cultivo_a_instalar', '')}")
    print(f"Código:     {row.get('codigo', '')}")
    print(f"pH:         {row.get('ph', '')}")

    print("\nProductos recomendados:")
    print("-" * 90)

    for item in data["selected_fertilizers"]:
        print(
            f"{item['name']:35s} "
            f"{format_number(item['dose_kg_ha'], 1):>10s} kg/ha   "
            f"{format_number(item['sacos_ha'], 1):>8s} sacos/ha   "
            f"{classify_application_time(item['name'])}"
        )

    print("-" * 90)


def main():
    parser = argparse.ArgumentParser(
        description="Generate fertilizer recommendation report by name and crop."
    )

    parser.add_argument("--name", required=True, help="NOMBRES Y APELLIDOS")
    parser.add_argument("--cultivo", required=True, help="CULTIVO A INSTALAR")
    parser.add_argument("--db", default=DB_FILE, help="SQLite database file.")
    parser.add_argument("--extraction-csv", default=EXTRACTION_CSV)
    parser.add_argument("--conversion-factors-csv", default=CONVERSION_FACTORS_CSV)
    parser.add_argument("--riqueza-csv", default=RIQUEZA_CSV)
    parser.add_argument(
        "--output",
        default=None,
        help="Output PDF path. If omitted, an automatic name is used.",
    )

    args = parser.parse_args()

    row = get_row_by_name_and_crop(
        db_file=args.db,
        name=args.name,
        cultivo=args.cultivo,
    )

    if row is None:
        raise ValueError(
            f"No record found for name={args.name!r}, cultivo={args.cultivo!r}"
        )

    data = build_recommendation_data(
        row=row,
        extraction_csv=args.extraction_csv,
        conversion_factors_csv=args.conversion_factors_csv,
        riqueza_csv=args.riqueza_csv,
    )

    print_terminal_summary(data)

    if args.output is None:
        safe_name = safe_filename(args.name)
        safe_crop = safe_filename(args.cultivo)
        output_pdf = Path(OUTPUT_DIR) / f"recomendacion_{safe_name}_{safe_crop}.pdf"
    else:
        output_pdf = Path(args.output)

    create_recommendation_pdf(
        data=data,
        output_pdf=output_pdf,
    )


if __name__ == "__main__":
    main()

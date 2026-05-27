# technical_inform_name_cultivo.py

import argparse
import unicodedata
from pathlib import Path

import pandas as pd

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)

from soil_characterization import (
    build_soil_analysis_table_rows,
    value_to_float,
)

from nutrient_extraction import (
    build_nutrient_extraction_rows,
)

from fertilization_dose import (
    calculate_fertilization_dose,
)

from get_fertilization_dose_by_name import (
    get_row_by_name_and_crop,
    get_crop_period_months,
)

from get_optimized_fertilization_by_name import (
    requirements_from_dose_result,
)

from optimizer_from_riqueza import (
    NUTRIENTS,
    optimize_fertilizers,
    load_fertilizer_table_from_csv,
)


DB_FILE = "database/inia_database.sqlite"
EXTRACTION_CSV = "config/Extraccion_Nut.csv"
CONVERSION_FACTORS_CSV = "config/fertilizer_conversion_factors.csv"
RIQUEZA_CSV = "config/Riqueza_Fert.csv"


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
        text = "reporte"

    return text


def fmt(value, digits=2):
    number = value_to_float(value, None)

    if number is None:
        return ""

    return f"{number:.{digits}f}"


def fmt0(value):
    return fmt(value, 0)


def read_csv_flexible(path):
    encodings = [
        "utf-8-sig",
        "utf-8",
        "latin1",
    ]

    last_error = None

    for encoding in encodings:
        try:
            return pd.read_csv(
                path,
                sep=None,
                engine="python",
                encoding=encoding,
                dtype=str,
            )
        except Exception as error:
            last_error = error

    raise RuntimeError(
        f"Could not read CSV file: {path}\n"
        f"Last error: {last_error}"
    )


# ============================================================
# RDTO ESTIMADO FROM Extraccion_Nut.csv
# ============================================================

def get_rdto_estimado_from_extraction_csv(
    cultivo,
    extraction_csv=EXTRACTION_CSV,
    default=0.0,
    debug=True,
):
    """
    Get RDTO ESTIMADO (ton/ha) from config/Extraccion_Nut.csv.

    The CSV has:
        Nombre Común
        Rendimiento (kg/ha)

    Example:
        Nombre Común = ALFALFA
        Rendimiento (kg/ha) = 70

    In your current Excel/report logic, that 70 is used as ton/ha.
    Therefore this function DOES NOT divide by 1000.
    """

    path = Path(extraction_csv)

    if not path.exists():
        print(f"\nERROR: extraction CSV not found: {path.resolve()}")
        return default

    df = read_csv_flexible(path)

    if df.empty:
        print(f"\nERROR: extraction CSV is empty: {path.resolve()}")
        return default

    if debug:
        print("\n" + "=" * 100)
        print("DEBUG RDTO ESTIMADO FROM Extraccion_Nut.csv")
        print("=" * 100)
        print(f"FILE: {path.resolve()}")

        print("\nCOLUMNS:")
        for col in df.columns:
            print(f"  {col!r} -> {normalize_text(col)!r}")

    crop_col = None

    for col in df.columns:
        col_norm = normalize_text(col)

        if col_norm in [
            "nombre comun",
            "cultivo",
            "cultivo a instalar",
            "cultivo variedad",
            "cultivo y variedad",
        ]:
            crop_col = col
            break

    if crop_col is None:
        for col in df.columns:
            col_norm = normalize_text(col)

            if "nombre comun" in col_norm or "cultivo" in col_norm:
                crop_col = col
                break

    rendimiento_col = None

    for col in df.columns:
        col_norm = normalize_text(col)

        if "rendimiento" in col_norm:
            rendimiento_col = col
            break

    if crop_col is None:
        print("\nERROR: Could not find crop column.")
        print("Expected column like 'Nombre Común'.")
        print("Available columns:")

        for col in df.columns:
            print(f"  {col!r}")

        return default

    if rendimiento_col is None:
        print("\nERROR: Could not find Rendimiento column.")
        print("Expected column like 'Rendimiento (kg/ha)'.")
        print("Available columns:")

        for col in df.columns:
            print(f"  {col!r}")

        return default

    target = normalize_text(cultivo)

    df["_crop_norm_tmp"] = df[crop_col].astype(str).map(normalize_text)

    mask = df["_crop_norm_tmp"].eq(target)

    if not mask.any():
        mask = df["_crop_norm_tmp"].str.contains(target, na=False)

    if not mask.any():
        mask = df["_crop_norm_tmp"].apply(
            lambda value: target in value or value in target
        )

    if not mask.any():
        print(f"\nERROR: cultivo={cultivo!r} was not found in column {crop_col!r}.")
        print(f"Normalized input cultivo: {target!r}")
        print("\nAvailable crops in CSV:")

        for value in df[crop_col].dropna().unique():
            print(f"  {value!r} -> {normalize_text(value)!r}")

        return default

    selected_row = df.loc[mask].iloc[0]

    rendimiento_raw = selected_row[rendimiento_col]
    rendimiento = value_to_float(rendimiento_raw, None)

    if rendimiento is None:
        print(f"\nERROR: Could not convert rendimiento value {rendimiento_raw!r}")
        return default

    rdto_ton_ha = rendimiento

    if debug:
        print("\nMATCHED CROP:")
        print(f"  cultivo input        = {cultivo!r}")
        print(f"  cultivo matched      = {selected_row[crop_col]!r}")
        print(f"  rendimiento raw      = {rendimiento_raw!r}")
        print(f"  RDTO estimado ton/ha = {rdto_ton_ha}")
        print("=" * 100)
        print()

    return rdto_ton_ha


# ============================================================
# PDF HELPERS
# ============================================================

def make_table(data, col_widths=None, font_size=6, header_rows=1):
    table = Table(
        data,
        colWidths=col_widths,
        repeatRows=header_rows,
    )

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
        ("TOPPADDING", (0, 0), (-1, -1), 1.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
    ]))

    return table


def make_section_title(text, width):
    table = Table(
        [[text]],
        colWidths=[width],
    )

    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e9e6db")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return table


# ============================================================
# ACIDEZ + ALUMINIO
# ============================================================

def get_acidez_aluminio_from_row(row):
    """
    Calculate:

        Al3+ + H+ =
            aluminio_intercambiable_cmol_plus_kg
            +
            acidez_hplus_cmol_plus_kg

    using the exact database column names.
    """

    aluminio = value_to_float(
        row.get("aluminio_intercambiable_cmol_plus_kg"),
        0.0,
    )

    acidez = value_to_float(
        row.get("acidez_hplus_cmol_plus_kg"),
        0.0,
    )

    if aluminio is None:
        aluminio = 0.0

    if acidez is None:
        acidez = 0.0

    return aluminio + acidez


def apply_alh_to_soil_rows(row, soil_rows):
    """
    Force Al3+H+ in the soil table to use:

        aluminio_intercambiable_cmol_plus_kg
        +
        acidez_hplus_cmol_plus_kg
    """

    alh = get_acidez_aluminio_from_row(row)

    for item in soil_rows:
        label = normalize_text(item.get("caracterizacion", ""))

        if label in [
            "al3 h",
            "al3h",
            "al h",
            "aluminio acidez",
        ] or ("al" in label and "h" in label):
            item["valor"] = alh
            item["digits"] = 2

    return soil_rows


def get_soil_value(soil_rows, label, default=0.0):
    target = normalize_text(label)

    for item in soil_rows:
        item_label = normalize_text(item.get("caracterizacion", ""))

        if item_label == target:
            return value_to_float(item.get("valor"), default)

    return default


# ============================================================
# OPTIMIZER HELPERS
# ============================================================

def get_optimizer_fertilizers_and_doses(optimizer_result):
    """
    Supports optimizer result object and dictionary fallback.
    """

    selected_names = list(getattr(optimizer_result, "selected_fertilizers", []))
    doses = list(getattr(optimizer_result, "x", []))

    if not selected_names and isinstance(optimizer_result, dict):
        selected_names = list(optimizer_result.get("fertilizers", []))
        doses = list(optimizer_result.get("doses", []))

    return selected_names, doses


def get_optimizer_fertilizer_table(optimizer_result, riqueza_csv):
    fertilizer_table = getattr(optimizer_result, "fertilizer_table", None)

    if fertilizer_table is None and isinstance(optimizer_result, dict):
        fertilizer_table = optimizer_result.get("fertilizer_table")

    if fertilizer_table is None:
        fertilizer_table = load_fertilizer_table_from_csv(riqueza_csv)

    return fertilizer_table


# ============================================================
# REPORT TABLE BUILDERS
# ============================================================

def build_general_info(
    row,
    permanencia_meses,
    rdto_estimado_ton_ha,
):
    return [
        ["INFORMACIÓN GENERAL", "", "", ""],
        [
            "NOMBRE AGRICULTOR",
            row.get("nombres_y_apellidos", ""),
            "SIST. PRODUCCIÓN",
            "Convencional",
        ],
        [
            "DIRECCIÓN",
            row.get("distrito", row.get("dist", "")),
            "RDTO ESTIMADO (ton/ha)",
            fmt(rdto_estimado_ton_ha, 2),
        ],
        [
            "NOMBRE PARCELA",
            row.get(
                "nombre_parcela",
                row.get("localidad_comunidad_caserio_asociacion_etc", ""),
            ),
            "PERMANENCIA CULTIVO (meses)",
            fmt(permanencia_meses, 0),
        ],
        [
            "CULTIVO / VARIEDAD",
            row.get("cultivo_a_instalar", ""),
            "CÓDIGO LAB.",
            row.get("codigo", ""),
        ],
    ]


def build_soil_pdf_rows(row):
    soil_rows = build_soil_analysis_table_rows(row)

    soil_rows = apply_alh_to_soil_rows(row, soil_rows)

    data = [
        ["ANÁLISIS DE SUELOS", "", ""],
        ["CARACTERIZACIÓN", "UNIDAD", "VALOR"],
    ]

    for item in soil_rows:
        data.append([
            item.get("caracterizacion", ""),
            item.get("unidad", ""),
            fmt(
                item.get("valor"),
                item.get("digits", 2),
            ),
        ])

    return data, soil_rows


def build_extraction_pdf_rows(
    cultivo,
    extraction_csv,
    conversion_factors_csv,
    rdto_estimado_ton_ha,
):
    result = build_nutrient_extraction_rows(
        cultivo=cultivo,
        extraction_csv=extraction_csv,
        conversion_factors_csv=conversion_factors_csv,
    )

    rdto = value_to_float(rdto_estimado_ton_ha, 0.0)

    if rdto is None:
        rdto = 0.0

    data = [
        [
            f"EXTRACCIÓN DE NUTRIENTES CULTIVO: {result['cultivo']}",
            "",
            "",
            "",
            "",
        ],
        [
            "Nutriente",
            "Requerimiento\nkg/ton",
            "Requerimiento Rdt Estimado\nkg/ha",
            "FC forma fert.",
            "Necesidad\nforma fert.",
        ],
    ]

    for item in result["rows"]:
        req_kg_ton = value_to_float(
            item.get("requerimiento_kg_ton"),
            0.0,
        )

        if req_kg_ton is None:
            req_kg_ton = 0.0

        req_rdto_estimado = req_kg_ton * rdto

        fc = value_to_float(
            item.get("fc_forma_fertilizante"),
            0.0,
        )

        if fc is None:
            fc = 0.0

        necesidad_forma_fertilizante = req_rdto_estimado * fc

        data.append([
            item.get("nutriente", ""),
            fmt(req_kg_ton, 2),
            fmt(req_rdto_estimado, 1),
            fmt(fc, 2),
            fmt(necesidad_forma_fertilizante, 0),
        ])

    return data, result


def build_efficiency_rows(dose_result):
    data = [
        ["EFICIENCIA FERTILIZANTES", ""],
        ["Nutriente", "Eficiencia (%)"],
    ]

    for item in dose_result["rows"]:
        data.append([
            item.get("nutriente", ""),
            fmt(item.get("eficiencia_porcentaje"), 0),
        ])

    return data


def build_dose_rows(dose_result, rdto_estimado_ton_ha):
    rdto_label = fmt(rdto_estimado_ton_ha, 0)

    data = [
        [
            "SUMINISTRO DEL SUELO",
            "",
            "",
            "",
            f"DEMANDA DEL CULTIVO; FRUTO\n({rdto_label} TON/HA)",
            "",
            f"DEMANDA DEL CULTIVO: FOLIAR\n({rdto_label} TON/HA)",
            "",
            "DOSIS DE FERTILIZACIÓN +\nBIOMASA FOLIAR",
            "",
        ],
        [
            "Nutriente",
            "Cantidad en forma\nelemental (kg/ha)",
            "Factor de\nDisponibilidad",
            "Cantidad en forma\nde fertilizante\n(kg/ha)",

            "Nutriente",
            "Necesidad en\nforma de\nfertilizante (kg/ha)",

            "Nutriente",
            "Necesidad en forma\nde fertilizante\n(kg/ha)",

            "Nutriente",
            "Requerimiento\nforma fertilizante\n(kg/ha)",
        ],
    ]

    for item in dose_result["rows"]:
        necesidad_fruto = item.get(
            "necesidad_fruto_fertilizante_kg_ha",
            item.get(
                "necesidad_cultivo_fertilizante_kg_ha",
                item.get(
                    "necesidad_forma_fertilizante_kg_ha",
                    item.get(
                        "necesidad_cultivo_suelo_fertilizante_kg_ha",
                        0,
                    ),
                ),
            ),
        )

        data.append([
            item.get("nutriente_forma", ""),
            fmt0(item.get("cantidad_elemental_kg_ha")),
            fmt(item.get("factor_disponibilidad"), 2),
            fmt0(item.get("suministro_suelo_fertilizante_kg_ha")),

            item.get("nutriente", ""),
            fmt0(necesidad_fruto),

            item.get("nutriente_forma", ""),
            fmt0(item.get("necesidad_foliar_fertilizante_kg_ha")),

            item.get("nutriente_forma", ""),
            fmt0(item.get("requerimiento_final_fertilizante_kg_ha")),
        ])

    return data


def build_acidity_rows(row, soil_rows):
    ca = get_soil_value(soil_rows, "Ca++", 0.0)
    mg = get_soil_value(soil_rows, "Mg ++", 0.0)
    k = get_soil_value(soil_rows, "K+", 0.0)
    na = get_soil_value(soil_rows, "Na+", 0.0)

    alh = get_acidez_aluminio_from_row(row)

    suma_bases = ca + mg + k + na
    cic = suma_bases + alh

    if cic > 0:
        sat_bases = 100.0 * suma_bases / cic
        sat_acidez = 100.0 * alh / cic
    else:
        sat_bases = 0.0
        sat_acidez = 0.0

    sat_necesaria = 70.0

    data = [
        [
            "VNRT CAL",
            "Aluminio meq/100 g suelo",
            "Suma de bases",
            "CIC",
            "% Saturación Bases",
            "% Saturación Acidez",
            "% Saturación Necesaria",
            "Necesidades Cal ton/ha",
            "Necesidades Cal kg/ha",
        ]
    ]

    for vnrt in [110, 120, 275]:
        if sat_bases >= sat_necesaria:
            necesidad_ton = 0.0
        else:
            necesidad_ton = (
                (sat_necesaria - sat_bases)
                * cic
                / max(vnrt, 1.0)
            )

        data.append([
            fmt0(vnrt),
            fmt(alh, 2),
            fmt(suma_bases, 2),
            fmt(cic, 2),
            fmt(sat_bases, 0),
            fmt(sat_acidez, 0),
            fmt(sat_necesaria, 0),
            fmt(necesidad_ton, 2),
            fmt(necesidad_ton * 1000.0, 2),
        ])

    return data


def build_balance_rows(
    requirements,
    optimizer_result,
    riqueza_csv,
    sack_kg=50.0,
):
    fertilizer_table = get_optimizer_fertilizer_table(
        optimizer_result=optimizer_result,
        riqueza_csv=riqueza_csv,
    )

    selected_names, doses = get_optimizer_fertilizers_and_doses(
        optimizer_result=optimizer_result,
    )

    data = [
        [
            "Enmienda y/o Fertilizante",
            "Dosis de\nFertilizantes (kg/ha)",
            "Dosis de\nFertilizantes\n(sacos/ha)",
            "Fórmula del Fertilizante",
            "",
            "",
            "",
            "",
            "",
        ],
        [
            "",
            "",
            "",
            "N",
            "P2O5",
            "K2O",
            "CaO",
            "MgO",
            "S",
        ],
    ]

    total_aporte = {nutrient: 0.0 for nutrient in NUTRIENTS}

    formula_rows = []
    aporte_rows = []

    for fertilizer_name, dose in zip(selected_names, doses):
        dose = value_to_float(dose, 0.0)

        if dose is None:
            dose = 0.0

        formula_data = fertilizer_table.get(fertilizer_name, {})

        sacks = dose / sack_kg if sack_kg > 0 else 0.0

        formula_row = [
            fertilizer_name,
            fmt(dose, 0),
            fmt(sacks, 1),
        ]

        aporte_row = [
            "",
            "",
            "",
        ]

        for nutrient in NUTRIENTS:
            formula_value = value_to_float(
                formula_data.get(nutrient),
                0.0,
            )

            if formula_value is None:
                formula_value = 0.0

            aporte = dose * formula_value / 100.0

            total_aporte[nutrient] += aporte

            formula_row.append(fmt(formula_value, 2))
            aporte_row.append(fmt(aporte, 2))

        formula_rows.append(formula_row)
        aporte_rows.append(aporte_row)

    data.extend(formula_rows)

    while len(data) < 9:
        data.append([
            "",
            "",
            "",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
        ])

    data.append([
        "",
        "",
        "",
        "Aporte de Nutrientes del Fertilizante",
        "",
        "",
        "",
        "",
        "",
    ])

    data.append([
        "",
        "",
        "",
        "N",
        "P2O5",
        "K2O",
        "CaO",
        "MgO",
        "S",
    ])

    data.extend(aporte_rows)

    while len(data) < 18:
        data.append([
            "",
            "",
            "",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
        ])

    total_dose = sum(
        value_to_float(dose, 0.0) or 0.0
        for dose in doses
    )

    total_sacks = total_dose / sack_kg if sack_kg > 0 else 0.0

    data.append([
        "SUMA DE NUTRIENTES",
        fmt(total_dose, 0),
        fmt(total_sacks, 1),
        fmt(total_aporte["N"], 0),
        fmt(total_aporte["P2O5"], 0),
        fmt(total_aporte["K2O"], 0),
        fmt(total_aporte["CaO"], 0),
        fmt(total_aporte["MgO"], 0),
        fmt(total_aporte["S"], 0),
    ])

    data.append([
        "Requerimiento del cultivo (kg/ha)",
        "",
        "",
        fmt(requirements[0], 0),
        fmt(requirements[1], 0),
        fmt(requirements[2], 0),
        fmt(requirements[3], 0),
        fmt(requirements[4], 0),
        fmt(requirements[5], 0),
    ])

    diff_values = []

    for nutrient, req in zip(NUTRIENTS, requirements):
        req_value = value_to_float(req, 0.0)

        if req_value is None:
            req_value = 0.0

        diff_values.append(total_aporte[nutrient] - req_value)

    data.append([
        "Diferencia (Si es negativa existe déficit del fertilizante)",
        "",
        "",
        fmt(diff_values[0], 0),
        fmt(diff_values[1], 0),
        fmt(diff_values[2], 0),
        fmt(diff_values[3], 0),
        fmt(diff_values[4], 0),
        fmt(diff_values[5], 0),
    ])

    return data


# ============================================================
# TERMINAL PRINT
# ============================================================

def print_table(title, rows):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)

    if not rows:
        print("No data")
        return

    rows_str = [[str(value) for value in row] for row in rows]

    ncols = max(len(row) for row in rows_str)

    for row in rows_str:
        while len(row) < ncols:
            row.append("")

    widths = []

    for col in range(ncols):
        width = max(len(row[col].replace("\n", " ")) for row in rows_str)
        widths.append(min(width, 28))

    for i, row in enumerate(rows_str):
        line_parts = []

        for col, value in enumerate(row):
            value = value.replace("\n", " ")

            if len(value) > widths[col]:
                value = value[:widths[col] - 3] + "..."

            line_parts.append(value.ljust(widths[col]))

        print(" | ".join(line_parts))

        if i == 0:
            print("-" * 100)


def print_report_to_terminal(
    row,
    soil_table_rows,
    extraction_rows,
    efficiency_rows,
    dose_rows,
    acidity_rows,
    balance_rows,
    permanencia_meses,
    rdto_estimado_ton_ha,
):
    print("\n")
    print("#" * 100)
    print("INFORME TÉCNICO DE FERTILIZACIÓN")
    print("#" * 100)

    print("\nINFORMACIÓN GENERAL")
    print("-" * 100)
    print(f"NOMBRE AGRICULTOR:      {row.get('nombres_y_apellidos', '')}")
    print(f"DIRECCIÓN:              {row.get('distrito', row.get('dist', ''))}")
    print(f"NOMBRE PARCELA:         {row.get('nombre_parcela', row.get('localidad_comunidad_caserio_asociacion_etc', ''))}")
    print(f"CULTIVO:                {row.get('cultivo_a_instalar', '')}")
    print(f"CÓDIGO LAB:             {row.get('codigo', '')}")
    print(f"RDTO ESTIMADO (ton/ha): {fmt(rdto_estimado_ton_ha, 2)}")
    print(f"PERMANENCIA:            {fmt(permanencia_meses, 0)} meses")
    print(f"DEBUG Aluminio:         {row.get('aluminio_intercambiable_cmol_plus_kg')}")
    print(f"DEBUG Acidez H+:        {row.get('acidez_hplus_cmol_plus_kg')}")
    print(f"Al3+H+ = Al + H:        {fmt(get_acidez_aluminio_from_row(row), 2)}")

    print_table("ANÁLISIS DE SUELOS", soil_table_rows)
    print_table("EXTRACCIÓN DE NUTRIENTES", extraction_rows)
    print_table("EFICIENCIA DE FERTILIZANTES", efficiency_rows)
    print_table("DOSIS DE FERTILIZACIÓN", dose_rows)
    print_table("CÁLCULO CAL EN CASO DE ACIDEZ", acidity_rows)
    print_table("BALANCEO DE ENMIENDAS Y FERTILIZANTES", balance_rows)

    print("\n" + "#" * 100)
    print("FIN DEL INFORME TÉCNICO")
    print("#" * 100)


# ============================================================
# PDF BUILDER
# ============================================================

def build_pdf(
    output_pdf,
    row,
    soil_table_rows,
    extraction_rows,
    efficiency_rows,
    dose_rows,
    acidity_rows,
    balance_rows,
    permanencia_meses,
    rdto_estimado_ton_ha,
):
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    page_size = A4

    doc = SimpleDocTemplate(
        str(output_pdf),
        pagesize=page_size,
        leftMargin=0.6 * cm,
        rightMargin=0.6 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
    )

    page_width = page_size[0] - doc.leftMargin - doc.rightMargin

    title_style = ParagraphStyle(
        "title",
        fontName="Helvetica-Bold",
        fontSize=10,
        alignment=TA_CENTER,
        leading=12,
    )

    story = []

    story.append(Paragraph("INFORME TÉCNICO DE FERTILIZACIÓN", title_style))
    story.append(Spacer(1, 0.10 * cm))

    # ------------------------------------------------------------
    # INFORMACIÓN GENERAL
    # ------------------------------------------------------------

    info_data = build_general_info(
        row=row,
        permanencia_meses=permanencia_meses,
        rdto_estimado_ton_ha=rdto_estimado_ton_ha,
    )

    info_table = Table(
        info_data,
        colWidths=[
            page_width * 0.26,
            page_width * 0.30,
            page_width * 0.24,
            page_width * 0.20,
        ],
    )

    info_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.black),

        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9e6db")),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#555555")),
        ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#555555")),

        ("TEXTCOLOR", (0, 1), (0, -1), colors.white),
        ("TEXTCOLOR", (2, 1), (2, -1), colors.white),

        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),

        ("FONTSIZE", (0, 0), (-1, -1), 5.8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))

    story.append(info_table)
    story.append(Spacer(1, 0.10 * cm))

    # ------------------------------------------------------------
    # ANÁLISIS DE SUELOS
    # ------------------------------------------------------------

    story.append(make_section_title(
        "ANÁLISIS DE SUELOS",
        page_width,
    ))
    story.append(Spacer(1, 0.05 * cm))

    soil_table = make_table(
        soil_table_rows,
        col_widths=[
            page_width * 0.50,
            page_width * 0.25,
            page_width * 0.25,
        ],
        font_size=5.6,
        header_rows=2,
    )

    soil_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
    ]))

    story.append(soil_table)
    story.append(Spacer(1, 0.10 * cm))

    # ------------------------------------------------------------
    # EXTRACCIÓN DE NUTRIENTES
    # ------------------------------------------------------------

    story.append(make_section_title(
        "EXTRACCIÓN DE NUTRIENTES",
        page_width,
    ))
    story.append(Spacer(1, 0.05 * cm))

    extraction_table = make_table(
        extraction_rows,
        col_widths=[
            page_width * 0.18,
            page_width * 0.22,
            page_width * 0.22,
            page_width * 0.16,
            page_width * 0.22,
        ],
        font_size=5.4,
        header_rows=2,
    )

    extraction_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
    ]))

    story.append(extraction_table)
    story.append(Spacer(1, 0.10 * cm))

    # ------------------------------------------------------------
    # EFICIENCIA DE FERTILIZANTES
    # ------------------------------------------------------------

    story.append(make_section_title(
        "EFICIENCIA DE FERTILIZANTES",
        page_width,
    ))
    story.append(Spacer(1, 0.05 * cm))

    efficiency_table = make_table(
        efficiency_rows,
        col_widths=[
            page_width * 0.50,
            page_width * 0.50,
        ],
        font_size=5.6,
        header_rows=2,
    )

    efficiency_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
    ]))

    story.append(efficiency_table)
    story.append(Spacer(1, 0.10 * cm))

    # ------------------------------------------------------------
    # DOSIS DE FERTILIZACIÓN
    # ------------------------------------------------------------

    story.append(make_section_title(
        "DOSIS DE FERTILIZACIÓN - RENDIMIENTO PROYECTADO",
        page_width,
    ))
    story.append(Spacer(1, 0.05 * cm))

    dose_table = make_table(
        dose_rows,
        col_widths=[
            page_width * 0.14,
            page_width * 0.10,
            page_width * 0.08,
            page_width * 0.10,
            page_width * 0.10,
            page_width * 0.10,
            page_width * 0.10,
            page_width * 0.10,
            page_width * 0.10,
            page_width * 0.08,
        ],
        font_size=3.8,
        header_rows=2,
    )

    dose_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (3, 0)),
        ("SPAN", (4, 0), (5, 0)),
        ("SPAN", (6, 0), (7, 0)),
        ("SPAN", (8, 0), (9, 0)),
    ]))

    story.append(dose_table)
    story.append(Spacer(1, 0.10 * cm))

    # ------------------------------------------------------------
    # CÁLCULO CAL
    # ------------------------------------------------------------

    story.append(make_section_title(
        "CÁLCULO CAL EN CASO DE ACIDEZ",
        page_width,
    ))
    story.append(Spacer(1, 0.05 * cm))

    acidity_table = make_table(
        acidity_rows,
        col_widths=[
            page_width * 0.09,
            page_width * 0.12,
            page_width * 0.10,
            page_width * 0.08,
            page_width * 0.12,
            page_width * 0.12,
            page_width * 0.12,
            page_width * 0.12,
            page_width * 0.13,
        ],
        font_size=4.4,
        header_rows=1,
    )

    story.append(acidity_table)
    story.append(Spacer(1, 0.10 * cm))

    # ------------------------------------------------------------
    # BALANCEO
    # ------------------------------------------------------------

    story.append(make_section_title(
        "BALANCEO DE ENMIENDAS Y FERTILIZANTES",
        page_width,
    ))
    story.append(Spacer(1, 0.05 * cm))

    balance_table = make_table(
        balance_rows,
        col_widths=[
            page_width * 0.25,
            page_width * 0.12,
            page_width * 0.12,
            page_width * 0.085,
            page_width * 0.085,
            page_width * 0.085,
            page_width * 0.085,
            page_width * 0.085,
            page_width * 0.085,
        ],
        font_size=4.0,
        header_rows=2,
    )

    balance_style = TableStyle([
        ("SPAN", (3, 0), (8, 0)),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#555555")),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
    ])

    for row_idx, row_data in enumerate(balance_rows):
        first_cell = str(row_data[0])
        fourth_cell = str(row_data[3]) if len(row_data) > 3 else ""

        if fourth_cell == "Aporte de Nutrientes del Fertilizante":
            balance_style.add("SPAN", (3, row_idx), (8, row_idx))
            balance_style.add("BACKGROUND", (3, row_idx), (8, row_idx), colors.HexColor("#555555"))
            balance_style.add("TEXTCOLOR", (3, row_idx), (8, row_idx), colors.white)
            balance_style.add("FONTNAME", (3, row_idx), (8, row_idx), "Helvetica-Bold")
            balance_style.add("ALIGN", (3, row_idx), (8, row_idx), "CENTER")

        if first_cell == "SUMA DE NUTRIENTES":
            balance_style.add("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#555555"))
            balance_style.add("TEXTCOLOR", (0, row_idx), (-1, row_idx), colors.white)
            balance_style.add("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Bold")

        if first_cell == "Requerimiento del cultivo (kg/ha)":
            balance_style.add("TEXTCOLOR", (0, row_idx), (-1, row_idx), colors.blue)
            balance_style.add("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Bold")

        if first_cell.startswith("Diferencia"):
            balance_style.add("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#d9d9d9"))
            balance_style.add("TEXTCOLOR", (0, row_idx), (-1, row_idx), colors.red)
            balance_style.add("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Bold")

    balance_table.setStyle(balance_style)

    story.append(balance_table)

    doc.build(story)

    return output_pdf


# ============================================================
# MAIN GENERATOR
# ============================================================

def generate_technical_report(
    name,
    cultivo,
    db,
    output,
    extraction_csv=EXTRACTION_CSV,
    conversion_factors_csv=CONVERSION_FACTORS_CSV,
    riqueza_csv=RIQUEZA_CSV,
    print_out=False,
    debug=True,
):
    row = get_row_by_name_and_crop(
        db_file=db,
        name=name,
        cultivo=cultivo,
    )

    if row is None:
        raise ValueError(
            f"No record found for name={name!r}, cultivo={cultivo!r}. "
            "Check the exact name/cultivo in the database."
        )

    if debug:
        print("DEBUG Aluminio:", row.get("aluminio_intercambiable_cmol_plus_kg"))
        print("DEBUG Acidez H+:", row.get("acidez_hplus_cmol_plus_kg"))
        print("DEBUG Al3+H+:", get_acidez_aluminio_from_row(row))

    cultivo_db = row.get("cultivo_a_instalar", cultivo)

    permanencia_meses = get_crop_period_months(
        cultivo=cultivo_db,
        extraction_csv=extraction_csv,
    )

    rdto_estimado_ton_ha = get_rdto_estimado_from_extraction_csv(
        cultivo=cultivo_db,
        extraction_csv=extraction_csv,
        default=0.0,
        debug=debug,
    )

    soil_pdf_rows, soil_analysis_rows = build_soil_pdf_rows(row)

    extraction_pdf_rows, extraction_result = build_extraction_pdf_rows(
        cultivo=cultivo_db,
        extraction_csv=extraction_csv,
        conversion_factors_csv=conversion_factors_csv,
        rdto_estimado_ton_ha=rdto_estimado_ton_ha,
    )

    dose_result = calculate_fertilization_dose(
        row=row,
        permanencia_cultivo_meses=permanencia_meses,
        cultivo=cultivo_db,
        extraction_csv=extraction_csv,
        conversion_factors_csv=conversion_factors_csv,
    )

    efficiency_rows = build_efficiency_rows(dose_result)

    dose_rows = build_dose_rows(
        dose_result=dose_result,
        rdto_estimado_ton_ha=rdto_estimado_ton_ha,
    )

    acidity_rows = build_acidity_rows(
        row=row,
        soil_rows=soil_analysis_rows,
    )

    requirements = requirements_from_dose_result(dose_result)

    optimizer_result = optimize_fertilizers(
        requirements=requirements,
        ph=row.get("ph"),
        riqueza_csv=riqueza_csv,
    )

    balance_rows = build_balance_rows(
        requirements=requirements,
        optimizer_result=optimizer_result,
        riqueza_csv=riqueza_csv,
    )

    if print_out:
        print_report_to_terminal(
            row=row,
            soil_table_rows=soil_pdf_rows,
            extraction_rows=extraction_pdf_rows,
            efficiency_rows=efficiency_rows,
            dose_rows=dose_rows,
            acidity_rows=acidity_rows,
            balance_rows=balance_rows,
            permanencia_meses=permanencia_meses,
            rdto_estimado_ton_ha=rdto_estimado_ton_ha,
        )

    pdf = build_pdf(
        output_pdf=output,
        row=row,
        soil_table_rows=soil_pdf_rows,
        extraction_rows=extraction_pdf_rows,
        efficiency_rows=efficiency_rows,
        dose_rows=dose_rows,
        acidity_rows=acidity_rows,
        balance_rows=balance_rows,
        permanencia_meses=permanencia_meses,
        rdto_estimado_ton_ha=rdto_estimado_ton_ha,
    )

    print("\nTechnical report generated:")
    print(f"  Name:                   {row.get('nombres_y_apellidos', '')}")
    print(f"  Cultivo:                {row.get('cultivo_a_instalar', '')}")
    print(f"  Código:                 {row.get('codigo', '')}")
    print(f"  RDTO estimado (ton/ha): {fmt(rdto_estimado_ton_ha, 2)}")
    print(f"  Al3+H+ Al+H:            {fmt(get_acidez_aluminio_from_row(row), 2)}")

    selected_names, doses = get_optimizer_fertilizers_and_doses(
        optimizer_result=optimizer_result,
    )

    print("  Optimizer fertilizers:")
    for fertilizer_name, dose in zip(selected_names, doses):
        print(f"    - {fertilizer_name}: {fmt(dose, 1)} kg/ha")

    print(f"  PDF:                    {pdf}")

    return pdf


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate vertical technical fertilization PDF using the NoExcel modules."
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
        help="SQLite database path.",
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output PDF file. If omitted, the script creates "
            "technical_inform_<name>_<cultivo>.pdf"
        ),
    )

    parser.add_argument(
        "--extraction-csv",
        default=EXTRACTION_CSV,
        help="Path to config/Extraccion_Nut.csv",
    )

    parser.add_argument(
        "--conversion-factors-csv",
        default=CONVERSION_FACTORS_CSV,
        help="Path to config/fertilizer_conversion_factors.csv",
    )

    parser.add_argument(
        "--riqueza-csv",
        default=RIQUEZA_CSV,
        help="Path to config/Riqueza_Fert.csv",
    )

    parser.add_argument(
        "--print-out",
        action="store_true",
        help="Print the technical report tables in the terminal.",
    )

    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Disable debug prints for CSV column and cultivo matching.",
    )

    args = parser.parse_args()

    if args.output is None:
        safe_name = safe_filename(args.name)
        safe_crop = safe_filename(args.cultivo)
        output_pdf = f"technical_inform_{safe_name}_{safe_crop}.pdf"
    else:
        output_pdf = args.output

    generate_technical_report(
        name=args.name,
        cultivo=args.cultivo,
        db=args.db,
        output=output_pdf,
        extraction_csv=args.extraction_csv,
        conversion_factors_csv=args.conversion_factors_csv,
        riqueza_csv=args.riqueza_csv,
        print_out=args.print_out,
        debug=not args.no_debug,
    )


if __name__ == "__main__":
    main()

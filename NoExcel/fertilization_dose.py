# fertilization_dose.py

from soil_characterization import (
    build_soil_analysis_table_rows,
    value_to_float,
)

from nutrient_extraction import (
    build_nutrient_extraction_rows,
    find_crop_row,
    load_conversion_factors,
)

from config.get_efficiency import get_efficiencies


CONVERSION_FACTORS_CSV = "config/fertilizer_conversion_factors.csv"
EXTRACTION_CSV = "config/Extraccion_Nut.csv"


NUTRIENT_LABELS = {
    "N": "Nitrógeno N",
    "P": "Fósforo P2O5",
    "K": "Potasio K2O",
    "Ca": "Calcio CaO",
    "Mg": "Magnesio MgO",
    "S": "Azufre S",
}


# ------------------------------------------------------------
# Factor de Disponibilidad
# ------------------------------------------------------------

def get_phosphorus_availability_factor(ph):
    """
    Factor de Disponibilidad para Fósforo.

    Rules:
        0.08 if pH <= 4.5
        0.10 if pH <= 5.0
        0.15 if pH <= 6.0
        0.30 if pH <= 7.0
        0.15 if pH > 7.0
    """

    ph = value_to_float(ph)

    if ph is None:
        return None

    if ph <= 4.5:
        return 0.08

    if ph <= 5.0:
        return 0.10

    if ph <= 6.0:
        return 0.15

    if ph <= 7.0:
        return 0.30

    return 0.15


def get_potassium_availability_factor(cice):
    """
    Factor de Disponibilidad para Potasio.

    Rules:
        0.50 when CICe < 10
        0.40 when 10 <= CICe < 15
        0.30 when 15 <= CICe < 20
        0.20 when CICe >= 20
    """

    cice = value_to_float(cice)

    if cice is None:
        return None

    if cice < 10:
        return 0.50

    if cice < 15:
        return 0.40

    if cice < 20:
        return 0.30

    return 0.20


def get_availability_factors(row):
    """
    Returns Factor de Disponibilidad for each nutrient.

    Constants:
        N  = 1.00
        Ca = 0.45
        Mg = 0.20
        S  = 1.00

    Calculated:
        P from pH
        K from CICe
    """

    ph = row.get("ph")
    cice = row.get("cice_cmol_plus_kg")

    return {
        "N": 1.00,
        "P": get_phosphorus_availability_factor(ph),
        "K": get_potassium_availability_factor(cice),
        "Ca": 0.45,
        "Mg": 0.20,
        "S": 1.00,
    }


# ------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------

def normalize_for_search(value):
    """
    Normalize text for flexible column matching.

    Handles:
        Índice de Cosecha
        Indice de Cosecha
        Índice de Cocecha
        Indice de Cocecha
        line breaks
        extra spaces
        punctuation
    """

    import unicodedata
    import re

    if value is None:
        return ""

    text = str(value).strip().lower()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = " ".join(text.split())

    return text


def find_column_by_words(fieldnames, words):
    """
    Find a column where all words appear in the normalized header.
    """

    words = [normalize_for_search(word) for word in words]

    for field in fieldnames:
        field_norm = normalize_for_search(field)

        if all(word in field_norm for word in words):
            return field

    return None


def rows_to_dict(soil_rows):
    data = {}

    for item in soil_rows:
        name = item["caracterizacion"]
        data[name] = item

    return data


def get_value(data, name, default=0.0):
    item = data.get(name)

    if item is None:
        return default

    return value_to_float(item.get("valor"), default)


def get_harvest_index(cultivo, extraction_csv=EXTRACTION_CSV):
    """
    Get Índice de Cosecha from Extraccion_Nut.csv.

    It searches flexible column names like:
        Índice de Cosecha
        Indice de Cosecha
        Índice de Cocecha
        Indice de Cocecha
    """

    crop_row, fieldnames, crop_col, code_col = find_crop_row(
        cultivo=cultivo,
        csv_file=extraction_csv,
    )

    possible_word_groups = [
        ["indice", "cosecha"],
        ["indice", "cocecha"],
    ]

    index_col = None

    for words in possible_word_groups:
        index_col = find_column_by_words(
            fieldnames,
            words,
        )

        if index_col is not None:
            break

    if index_col is None:
        print("\nCould not find harvest index column.")
        print(f"File: {extraction_csv}")
        print("\nAvailable columns:\n")

        for field in fieldnames:
            print(f"  - {repr(field)}")

        raise ValueError(
            f"Could not find 'Indice de Cosecha' column in {extraction_csv}"
        )

    harvest_index = value_to_float(crop_row.get(index_col))

    if harvest_index is None or harvest_index == 0:
        raise ValueError(
            f"Invalid Índice de Cosecha for cultivo={cultivo!r}: "
            f"{crop_row.get(index_col)!r} from column {index_col!r}"
        )

    return harvest_index


# ------------------------------------------------------------
# Suministro del suelo: forma elemental
# ------------------------------------------------------------

def calculate_soil_supply_elemental(row, permanencia_cultivo_meses):
    """
    Calculates:

        Cantidad en forma elemental (kg/ha)

    Formulas:

    N =
        (Peso del suelo * 1000)
        * (MO / 100)
        * (Porcentaje N en MO / 100)
        * (Porcentaje mineraliz. N / 100)
        * (Permanencia cultivo / 12)

    P =
        Fósforo * ((Peso del suelo * 1000) / 1000000)

    K =
        K+ * (((Peso del suelo * 1000) / 100000) * 39)

    Ca =
        Ca++ * (((Peso del suelo * 1000) / 100000) * 20)

    Mg =
        Mg++ * (((Peso del suelo * 1000) / 100000) * 12)
    """

    soil_rows = build_soil_analysis_table_rows(row)
    soil = rows_to_dict(soil_rows)

    peso_suelo = get_value(soil, "Peso del suelo")
    mo = get_value(soil, "MO")
    porcentaje_n_en_mo = get_value(soil, "Porcentaje N en MO")
    porcentaje_mineraliz_n = get_value(soil, "Porcentaje mineraliz. N")

    fosforo = get_value(soil, "Fósforo")
    potasio_intercambiable = get_value(soil, "K+")
    calcio_intercambiable = get_value(soil, "Ca++")
    magnesio_intercambiable = get_value(soil, "Mg ++")

    permanencia = value_to_float(permanencia_cultivo_meses, 0.0)

    nitrogeno_kg_ha = (
        (peso_suelo * 1000.0)
        * (mo / 100.0)
        * (porcentaje_n_en_mo / 100.0)
        * (porcentaje_mineraliz_n / 100.0)
        * (permanencia / 12.0)
    )

    fosforo_kg_ha = (
        fosforo
        * ((peso_suelo * 1000.0) / 1_000_000.0)
    )

    potasio_kg_ha = (
        potasio_intercambiable
        * (((peso_suelo * 1000.0) / 100_000.0) * 39.0)
    )

    calcio_kg_ha = (
        calcio_intercambiable
        * (((peso_suelo * 1000.0) / 100_000.0) * 20.0)
    )

    magnesio_kg_ha = (
        magnesio_intercambiable
        * (((peso_suelo * 1000.0) / 100_000.0) * 12.0)
    )

    # For now S is zero until you define the sulfur soil-supply formula.
    azufre_kg_ha = 0.0

    return [
        {
            "nutriente": "N",
            "descripcion": "Nitrógeno kg/ha de N",
            "cantidad_elemental_kg_ha": nitrogeno_kg_ha,
        },
        {
            "nutriente": "P",
            "descripcion": "Fósforo kg/ha de P",
            "cantidad_elemental_kg_ha": fosforo_kg_ha,
        },
        {
            "nutriente": "K",
            "descripcion": "Potasio kg/ha de K",
            "cantidad_elemental_kg_ha": potasio_kg_ha,
        },
        {
            "nutriente": "Ca",
            "descripcion": "Calcio kg/ha de Ca",
            "cantidad_elemental_kg_ha": calcio_kg_ha,
        },
        {
            "nutriente": "Mg",
            "descripcion": "Magnesio kg/ha de Mg",
            "cantidad_elemental_kg_ha": magnesio_kg_ha,
        },
        {
            "nutriente": "S",
            "descripcion": "Azufre kg/ha de S",
            "cantidad_elemental_kg_ha": azufre_kg_ha,
        },
    ]


# ------------------------------------------------------------
# Suministro del suelo: forma fertilizante
# ------------------------------------------------------------

def calculate_soil_supply_with_availability(
    row,
    permanencia_cultivo_meses,
    conversion_factors_csv=CONVERSION_FACTORS_CSV,
):
    """
    Calculates:

        Cantidad en forma elemental (kg/ha)
        Factor de Disponibilidad
        FC para pasar a forma de fertilizante
        Cantidad en forma de fertilizante (kg/ha)

    Formula:

        cantidad_fertilizante =
            cantidad_elemental
            * factor_disponibilidad
            * fc_forma_fertilizante
    """

    elemental_rows = calculate_soil_supply_elemental(
        row=row,
        permanencia_cultivo_meses=permanencia_cultivo_meses,
    )

    availability_factors = get_availability_factors(row)
    conversion_factors = load_conversion_factors(conversion_factors_csv)

    final_rows = []

    for item in elemental_rows:
        nutrient = item["nutriente"]

        cantidad_elemental = value_to_float(
            item["cantidad_elemental_kg_ha"],
            0.0,
        )

        factor_disponibilidad = value_to_float(
            availability_factors.get(nutrient),
            0.0,
        )

        factor_info = conversion_factors.get(nutrient)

        if factor_info is None:
            raise ValueError(
                f"No conversion factor found for nutrient {nutrient} "
                f"in {conversion_factors_csv}"
            )

        fc_forma_fertilizante = value_to_float(
            factor_info.get("factor"),
            0.0,
        )

        forma_fertilizante = factor_info.get(
            "fertilizer_form",
            nutrient,
        )

        cantidad_fertilizante = (
            cantidad_elemental
            * factor_disponibilidad
            * fc_forma_fertilizante
        )

        final_rows.append({
            "nutriente": nutrient,
            "descripcion": item["descripcion"],
            "cantidad_elemental_kg_ha": cantidad_elemental,
            "factor_disponibilidad": factor_disponibilidad,
            "fc_forma_fertilizante": fc_forma_fertilizante,
            "forma_fertilizante": forma_fertilizante,
            "cantidad_fertilizante_kg_ha": cantidad_fertilizante,
        })

    return final_rows


# ------------------------------------------------------------
# Dosis de fertilización completa
# ------------------------------------------------------------

def calculate_fertilization_dose(
    row,
    permanencia_cultivo_meses,
    cultivo=None,
    extraction_csv=EXTRACTION_CSV,
    conversion_factors_csv=CONVERSION_FACTORS_CSV,
):
    """
    Full fertilization dose.

    Uses:

    1. Soil supply in fertilizer form:
        E37 = elemental * FD * FC

    2. Fruit demand:
        G37 = necesidad_forma_fertilizante from Extraccion_Nut.csv

    3. Foliar demand:
        I37 = G37 * (1 / indice_cosecha) - G37

    4. Final requirement:
        Req = ((G37 + I37) - E37) / (efficiency / 100)

    Excel equivalent:
        =((G37+I37)-E37)/(G27/100)
    """

    if cultivo is None:
        cultivo = row.get("cultivo_a_instalar", "")

    if not cultivo:
        raise ValueError(
            "No cultivo provided and row has no cultivo_a_instalar."
        )

    soil_supply_rows = calculate_soil_supply_with_availability(
        row=row,
        permanencia_cultivo_meses=permanencia_cultivo_meses,
        conversion_factors_csv=conversion_factors_csv,
    )

    extraction_result = build_nutrient_extraction_rows(
        cultivo=cultivo,
        extraction_csv=extraction_csv,
        conversion_factors_csv=conversion_factors_csv,
    )

    harvest_index = get_harvest_index(
        cultivo=cultivo,
        extraction_csv=extraction_csv,
    )

    efficiencies = get_efficiencies(
        ph=row.get("ph"),
        texture=row.get("clase_textural"),
        decimals=0,
    )

    extraction_by_nutrient = {
        item["nutriente"]: item
        for item in extraction_result["rows"]
    }

    final_rows = []

    for soil_item in soil_supply_rows:
        nutrient = soil_item["nutriente"]

        extraction_item = extraction_by_nutrient.get(nutrient)

        if extraction_item is None:
            raise ValueError(
                f"Nutrient {nutrient} was not found in extraction table."
            )

        # G37: Necesidad en forma de fertilizante del fruto
        necesidad_fruto = value_to_float(
            extraction_item["necesidad_forma_fertilizante"],
            0.0,
        )

        # I37: Necesidad en forma de fertilizante foliar
        necesidad_foliar = (
            necesidad_fruto
            * (1.0 / harvest_index)
            - necesidad_fruto
        )

        # E37: Cantidad en forma de fertilizante del suelo
        suministro_suelo_fertilizante = value_to_float(
            soil_item["cantidad_fertilizante_kg_ha"],
            0.0,
        )

        # G27: eficiencia fertilizante (%)
        eficiencia = value_to_float(
            efficiencies.get(nutrient),
            0.0,
        )

        # Excel:
        # =((G37+I37)-E37)/(G27/100)
        if eficiencia == 0:
            requerimiento_final = None
        else:
            requerimiento_final = (
                (
                    necesidad_fruto
                    + necesidad_foliar
                )
                - suministro_suelo_fertilizante
            ) / (eficiencia / 100.0)

        final_rows.append({
            "nutriente": nutrient,
            "nutriente_forma": NUTRIENT_LABELS.get(nutrient, nutrient),

            # Suministro del suelo
            "cantidad_elemental_kg_ha": soil_item["cantidad_elemental_kg_ha"],
            "factor_disponibilidad": soil_item["factor_disponibilidad"],
            "fc_forma_fertilizante": soil_item["fc_forma_fertilizante"],
            "suministro_suelo_fertilizante_kg_ha": suministro_suelo_fertilizante,

            # Demanda del cultivo: fruto
            "necesidad_fruto_fertilizante_kg_ha": necesidad_fruto,

            # Demanda del cultivo: foliar / biomasa foliar
            "necesidad_foliar_fertilizante_kg_ha": necesidad_foliar,

            # Eficiencia
            "eficiencia_porcentaje": eficiencia,

            # Final
            "requerimiento_final_fertilizante_kg_ha": requerimiento_final,
        })

    return {
        "cultivo": extraction_result["cultivo"],
        "codigo_cultivo": extraction_result["codigo"],
        "rendimiento_kg_ha": extraction_result["rendimiento_kg_ha"],
        "indice_cosecha": harvest_index,
        "rows": final_rows,
    }


# ------------------------------------------------------------
# Printing helpers
# ------------------------------------------------------------

def format_number(value, digits=0):
    number = value_to_float(value)

    if number is None:
        return ""

    return f"{number:.{digits}f}"


def print_fertilization_dose(
    row,
    permanencia_cultivo_meses,
    cultivo=None,
    extraction_csv=EXTRACTION_CSV,
    conversion_factors_csv=CONVERSION_FACTORS_CSV,
):
    result = calculate_fertilization_dose(
        row=row,
        permanencia_cultivo_meses=permanencia_cultivo_meses,
        cultivo=cultivo,
        extraction_csv=extraction_csv,
        conversion_factors_csv=conversion_factors_csv,
    )

    print("\nDOSIS DE FERTILIZACIÓN - RENDIMIENTO PROYECTADO")
    print("=" * 180)
    print(f"Cultivo: {result['cultivo']} | Código: {result['codigo_cultivo']}")
    print(f"Rendimiento: {result['rendimiento_kg_ha']} kg/ha")
    print(f"Índice de Cosecha: {result['indice_cosecha']}")
    print("-" * 180)

    print(
        f"{'Nutriente':22s} "
        f"{'Elemental':>12s} "
        f"{'FD':>8s} "
        f"{'FC':>8s} "
        f"{'Suelo fert.':>14s} "
        f"{'Fruto':>12s} "
        f"{'Foliar':>12s} "
        f"{'Efic. %':>10s} "
        f"{'Req. final':>14s}"
    )

    print("-" * 180)

    for item in result["rows"]:
        print(
            f"{item['nutriente_forma']:22s} "
            f"{format_number(item['cantidad_elemental_kg_ha'], 0):>12s} "
            f"{format_number(item['factor_disponibilidad'], 2):>8s} "
            f"{format_number(item['fc_forma_fertilizante'], 2):>8s} "
            f"{format_number(item['suministro_suelo_fertilizante_kg_ha'], 0):>14s} "
            f"{format_number(item['necesidad_fruto_fertilizante_kg_ha'], 0):>12s} "
            f"{format_number(item['necesidad_foliar_fertilizante_kg_ha'], 0):>12s} "
            f"{format_number(item['eficiencia_porcentaje'], 0):>10s} "
            f"{format_number(item['requerimiento_final_fertilizante_kg_ha'], 0):>14s}"
        )

    print("-" * 180)


# ------------------------------------------------------------
# Test
# ------------------------------------------------------------

if __name__ == "__main__":
    test_row = {
        "mo_porcentaje": 1.50,
        "clase_textural": "Franco",
        "clima": "Frío y seco",
        "ph": 6.70,
        "ce_ms_m": 5.20,
        "p_mg_kg": 152.10,
        "k_ppm": 32.00,
        "calcio_ca_cmol_plus_kg": 6.10,
        "magnesio_mg_cmol_plus_kg": 1.60,
        "potasio_k_cmol_plus_kg": 0.10,
        "sodio_na_cmol_plus_kg": 3.70,
        "aluminio_intercambiable_cmol_plus_kg": 0.00,
        "cice_cmol_plus_kg": 11.50,
        "azufre_ppm": 0.00,
        "cultivo_a_instalar": "OLIVO",
    }

    print_fertilization_dose(
        row=test_row,
        permanencia_cultivo_meses=12,
        cultivo="OLIVO",
    )

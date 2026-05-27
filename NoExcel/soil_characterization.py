# soil_characterization.py

from pathlib import Path
import csv
import math

from config.get_nitrogen_mineralization import get_mineralization_percentage


CONSTANTS_CSV = "config/constants.csv"


def value_to_float(value, default=None):
    if value is None:
        return default

    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)

    text = str(value).strip()

    if text == "":
        return default

    if text.upper() in ["NO", "N/A", "NA", "-", "--", "#VALUE!"]:
        return default

    text = text.replace(",", ".")

    try:
        return float(text)
    except Exception:
        return default


def load_constants(constants_csv=CONSTANTS_CSV):
    constants_csv = Path(constants_csv)

    if not constants_csv.exists():
        raise FileNotFoundError(
            f"Constants file not found: {constants_csv}\n"
            "Create config/constants.csv with:\n"
            "name,unit,value\n"
            "Profundidad,m,0.28\n"
            "Porcentaje N en MO,%,5\n"
        )

    constants = {}

    with open(constants_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required_columns = {"name", "unit", "value"}
        fieldnames = set(reader.fieldnames or [])

        if not required_columns.issubset(fieldnames):
            raise ValueError(
                f"{constants_csv} must contain columns: name, unit, value"
            )

        for row in reader:
            name = str(row.get("name", "")).strip()
            unit = str(row.get("unit", "")).strip()
            value = str(row.get("value", "")).strip()

            if not name:
                continue

            constants[name] = {
                "unit": unit,
                "value": value_to_float(value, value),
            }

    return constants


def get_constant_value(constants, name, default=None):
    item = constants.get(name)

    if item is None:
        return default

    return item.get("value", default)


def get_constant_unit(constants, name, default=""):
    item = constants.get(name)

    if item is None:
        return default

    return item.get("unit", default)


def get_db_value(row, key, default=None):
    value = row.get(key, default)

    if value is None:
        return default

    return value


def calculate_bulk_density(mo):
    """
    Densidad aparente = 1 / (0.563 + 0.055 * MO)

    MO is in percent.
    Result is ton/m3.
    """

    mo = value_to_float(mo, 0.0)

    denominator = 0.563 + (0.055 * mo)

    if denominator == 0:
        return None

    return 1.0 / denominator


def calculate_soil_weight(profundidad, densidad_aparente):
    """
    Peso del suelo = Profundidad * Densidad aparente * 10000

    profundidad: m
    densidad_aparente: ton/m3
    result: ton/ha
    """

    profundidad = value_to_float(profundidad)
    densidad_aparente = value_to_float(densidad_aparente)

    if profundidad is None or densidad_aparente is None:
        return None

    return profundidad * densidad_aparente * 10000.0


def format_number(value, digits=2):
    number = value_to_float(value)

    if number is None:
        if value is None:
            return ""
        return str(value)

    return f"{number:.{digits}f}"


def build_soil_analysis_table_rows(row, constants_csv=CONSTANTS_CSV):
    """
    Builds:

        CARACTERIZACIÓN | UNIDAD | VALOR

    Sources:
        constants.csv:
            Profundidad
            Porcentaje N en MO

        calculated:
            Densidad aparente
            Peso del suelo
            Porcentaje mineraliz. N

        SQLite row:
            pH, CE, MO, P, K, Ca, Mg, Na, Al, S
    """

    constants = load_constants(constants_csv)

    profundidad = value_to_float(
        get_constant_value(constants, "Profundidad", 0.28),
        0.28,
    )

    porcentaje_n_en_mo = value_to_float(
        get_constant_value(constants, "Porcentaje N en MO", 5.0),
        5.0,
    )

    mo = value_to_float(get_db_value(row, "mo_porcentaje"), 0.0)

    textura = get_db_value(row, "clase_textural", "")
    clima = get_db_value(row, "clima", "")

    densidad_aparente = calculate_bulk_density(mo)

    peso_suelo = calculate_soil_weight(
        profundidad=profundidad,
        densidad_aparente=densidad_aparente,
    )

    try:
        porcentaje_mineralizacion_n = get_mineralization_percentage(
            texture=textura,
            clima=clima,
        )
    except Exception as e:
        print(f"WARNING: Could not calculate Porcentaje mineraliz. N: {e}")
        porcentaje_mineralizacion_n = None

    table_rows = [
        {
            "caracterizacion": "Profundidad",
            "unidad": get_constant_unit(constants, "Profundidad", "m"),
            "valor": profundidad,
            "digits": 2,
        },
        {
            "caracterizacion": "Densidad aparente",
            "unidad": "ton/m3",
            "valor": densidad_aparente,
            "digits": 2,
        },
        {
            "caracterizacion": "Peso del suelo",
            "unidad": "ton/ha",
            "valor": peso_suelo,
            "digits": 0,
        },
        {
            "caracterizacion": "Porcentaje N en MO",
            "unidad": get_constant_unit(constants, "Porcentaje N en MO", "%"),
            "valor": porcentaje_n_en_mo,
            "digits": 2,
        },
        {
            "caracterizacion": "Porcentaje mineraliz. N",
            "unidad": "%",
            "valor": porcentaje_mineralizacion_n,
            "digits": 2,
        },
        {
            "caracterizacion": "pH",
            "unidad": "(1:2.5)",
            "valor": get_db_value(row, "ph"),
            "digits": 2,
        },
        {
            "caracterizacion": "CE",
            "unidad": "mS/m",
            "valor": get_db_value(row, "ce_ms_m"),
            "digits": 2,
        },
        {
            "caracterizacion": "MO",
            "unidad": "%",
            "valor": get_db_value(row, "mo_porcentaje"),
            "digits": 2,
        },
        {
            "caracterizacion": "Fósforo",
            "unidad": "ppm",
            "valor": get_db_value(row, "p_mg_kg"),
            "digits": 2,
        },
        {
            "caracterizacion": "Potasio",
            "unidad": "ppm",
            "valor": get_db_value(row, "k_ppm"),
            "digits": 2,
        },
        {
            "caracterizacion": "Ca++",
            "unidad": "Cmol/kg",
            "valor": get_db_value(row, "calcio_ca_cmol_plus_kg"),
            "digits": 2,
        },
        {
            "caracterizacion": "Mg ++",
            "unidad": "Cmol/kg",
            "valor": get_db_value(row, "magnesio_mg_cmol_plus_kg"),
            "digits": 2,
        },
        {
            "caracterizacion": "K+",
            "unidad": "Cmol/kg",
            "valor": get_db_value(row, "potasio_k_cmol_plus_kg"),
            "digits": 2,
        },
        {
            "caracterizacion": "Na+",
            "unidad": "Cmol/kg",
            "valor": get_db_value(row, "sodio_na_cmol_plus_kg"),
            "digits": 2,
        },
        {
            "caracterizacion": "Al3+ + H+",
            "unidad": "Cmol/kg",
            "valor": get_db_value(row, "aluminio_intercambiable_cmol_plus_kg"),
            "digits": 2,
        },
        {
            "caracterizacion": "Azufre",
            "unidad": "ppm",
            "valor": get_db_value(row, "azufre_ppm", 0.0),
            "digits": 2,
        },
    ]

    return table_rows


def print_soil_analysis_table(row):
    rows = build_soil_analysis_table_rows(row)

    print("\nANÁLISIS DE SUELOS")
    print("-" * 75)
    print(f"{'CARACTERIZACIÓN':35s} {'UNIDAD':15s} {'VALOR':>12s}")
    print("-" * 75)

    for item in rows:
        value_text = format_number(
            item["valor"],
            digits=item.get("digits", 2),
        )

        print(
            f"{item['caracterizacion']:35s} "
            f"{item['unidad']:15s} "
            f"{value_text:>12s}"
        )

    print("-" * 75)


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
        "azufre_ppm": 0.00,
    }

    print_soil_analysis_table(test_row)

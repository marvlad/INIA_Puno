# generate_reports_by_district.py

import argparse
import sqlite3
import subprocess
import sys
import unicodedata
from pathlib import Path


DB_FILE = "database/inia_database.sqlite"
TABLE_NAME = "muestras"

GENERATE_BOTH_SCRIPT = "generate_both_reports.py"
TECHNICAL_INFORM_SCRIPT = "technical_inform_name_cultivo.py"

DEFAULT_OUTPUT_DIR = "final_reports_ayaviri"


def normalize_text(value):
    if value is None:
        return ""

    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
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


def get_records_by_district(db_file, district):
    """
    Get unique name + cultivo records from SQLite for one district.
    """

    db_file = Path(db_file)

    if not db_file.exists():
        raise FileNotFoundError(f"Database not found: {db_file}")

    district_norm = normalize_text(district)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        query = f"""
            SELECT
                nombres_y_apellidos,
                cultivo_a_instalar,
                codigo,
                dist
            FROM "{TABLE_NAME}"
            WHERE nombres_y_apellidos IS NOT NULL
              AND cultivo_a_instalar IS NOT NULL
              AND TRIM(nombres_y_apellidos) != ''
              AND TRIM(cultivo_a_instalar) != ''
            ORDER BY nombres_y_apellidos, cultivo_a_instalar
        """

        cur.execute(query)
        rows = [dict(row) for row in cur.fetchall()]

    filtered = []
    seen = set()

    for row in rows:
        row_dist_norm = normalize_text(row.get("dist"))

        if row_dist_norm != district_norm:
            continue

        name = str(row.get("nombres_y_apellidos", "")).strip()
        cultivo = str(row.get("cultivo_a_instalar", "")).strip()
        codigo = str(row.get("codigo", "")).strip()

        key = (
            normalize_text(name),
            normalize_text(cultivo),
            normalize_text(codigo),
        )

        if key in seen:
            continue

        seen.add(key)

        filtered.append({
            "name": name,
            "cultivo": cultivo,
            "codigo": codigo,
            "district": row.get("dist", ""),
        })

    return filtered


def run_command(command, title):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)
    print(" ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print("\nSTDOUT:")
        print(result.stdout)

    if result.stderr:
        print("\nSTDERR:")
        print(result.stderr)

    return result.returncode


def run_generate_both(
    name,
    cultivo,
    output_dir,
    db_file,
    extraction_csv=None,
    conversion_factors_csv=None,
    riqueza_csv=None,
):
    command = [
        sys.executable,
        GENERATE_BOTH_SCRIPT,
        "--name",
        name,
        "--cultivo",
        cultivo,
        "--output-dir",
        str(output_dir),
        "--db",
        str(db_file),
    ]

    if extraction_csv:
        command.extend(["--extraction-csv", extraction_csv])

    if conversion_factors_csv:
        command.extend(["--conversion-factors-csv", conversion_factors_csv])

    if riqueza_csv:
        command.extend(["--riqueza-csv", riqueza_csv])

    return run_command(
        command=command,
        title=f"Generating merged lab + recommendation report for: {name} | {cultivo}",
    )


def run_technical_inform(
    name,
    cultivo,
    output_dir,
    db_file,
    extraction_csv=None,
    conversion_factors_csv=None,
    riqueza_csv=None,
    print_out=False,
    no_debug=True,
):
    safe_name = safe_filename(name)
    safe_crop = safe_filename(cultivo)

    technical_pdf = Path(output_dir) / f"technical_inform_{safe_name}_{safe_crop}.pdf"

    command = [
        sys.executable,
        TECHNICAL_INFORM_SCRIPT,
        "--name",
        name,
        "--cultivo",
        cultivo,
        "--db",
        str(db_file),
        "--output",
        str(technical_pdf),
    ]

    if extraction_csv:
        command.extend(["--extraction-csv", extraction_csv])

    if conversion_factors_csv:
        command.extend(["--conversion-factors-csv", conversion_factors_csv])

    if riqueza_csv:
        command.extend(["--riqueza-csv", riqueza_csv])

    if print_out:
        command.append("--print-out")

    if no_debug:
        command.append("--no-debug")

    return run_command(
        command=command,
        title=f"Generating technical inform report for: {name} | {cultivo}",
    )


def write_failed_log(failed_records, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    failed_log = output_dir / "failed_reports.csv"

    with open(failed_log, "w", encoding="utf-8-sig") as f:
        f.write("name,cultivo,codigo,report_type,error_code\n")

        for item in failed_records:
            f.write(
                f'"{item["name"]}",'
                f'"{item["cultivo"]}",'
                f'"{item["codigo"]}",'
                f'"{item["report_type"]}",'
                f'{item["error_code"]}\n'
            )

    print(f"\nFailed log written to: {failed_log}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate merged lab + recommendation reports and technical inform "
            "reports for all records in one district."
        )
    )

    parser.add_argument(
        "--district",
        default="AYAVIRI",
        help="District name, e.g. AYAVIRI",
    )

    parser.add_argument(
        "--db",
        default=DB_FILE,
        help="SQLite database file.",
    )

    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where all generated PDFs will be saved.",
    )

    parser.add_argument(
        "--extraction-csv",
        default=None,
        help="Optional path to config/Extraccion_Nut.csv.",
    )

    parser.add_argument(
        "--conversion-factors-csv",
        default=None,
        help="Optional path to config/fertilizer_conversion_factors.csv.",
    )

    parser.add_argument(
        "--riqueza-csv",
        default=None,
        help="Optional path to config/Riqueza_Fert.csv.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for testing, e.g. --limit 5.",
    )

    parser.add_argument(
        "--skip-both",
        action="store_true",
        help="Skip generate_both_reports.py and only generate technical inform PDFs.",
    )

    parser.add_argument(
        "--skip-technical",
        action="store_true",
        help="Skip technical_inform_name_cultivo.py and only generate merged reports.",
    )

    parser.add_argument(
        "--technical-print-out",
        action="store_true",
        help="Pass --print-out to technical_inform_name_cultivo.py.",
    )

    parser.add_argument(
        "--technical-debug",
        action="store_true",
        help="Do not pass --no-debug to technical_inform_name_cultivo.py.",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = get_records_by_district(
        db_file=args.db,
        district=args.district,
    )

    if args.limit is not None:
        records = records[:args.limit]

    print("\nRecords found:")
    print("=" * 100)

    for i, record in enumerate(records, start=1):
        print(
            f"{i:4d}. "
            f"{record['name']} | "
            f"{record['cultivo']} | "
            f"{record['codigo']}"
        )

    print("=" * 100)
    print(f"Total records to process: {len(records)}")

    failed = []

    success_both = 0
    success_technical = 0

    for i, record in enumerate(records, start=1):
        print("\n" + "#" * 100)
        print(f"Processing {i}/{len(records)}")
        print(f"{record['name']} | {record['cultivo']} | {record['codigo']}")
        print("#" * 100)

        if not args.skip_both:
            return_code_both = run_generate_both(
                name=record["name"],
                cultivo=record["cultivo"],
                output_dir=output_dir,
                db_file=args.db,
                extraction_csv=args.extraction_csv,
                conversion_factors_csv=args.conversion_factors_csv,
                riqueza_csv=args.riqueza_csv,
            )

            if return_code_both == 0:
                success_both += 1
            else:
                failed.append({
                    "name": record["name"],
                    "cultivo": record["cultivo"],
                    "codigo": record["codigo"],
                    "report_type": "merged_lab_recommendation",
                    "error_code": return_code_both,
                })

        if not args.skip_technical:
            return_code_technical = run_technical_inform(
                name=record["name"],
                cultivo=record["cultivo"],
                output_dir=output_dir,
                db_file=args.db,
                extraction_csv=args.extraction_csv,
                conversion_factors_csv=args.conversion_factors_csv,
                riqueza_csv=args.riqueza_csv,
                print_out=args.technical_print_out,
                no_debug=not args.technical_debug,
            )

            if return_code_technical == 0:
                success_technical += 1
            else:
                failed.append({
                    "name": record["name"],
                    "cultivo": record["cultivo"],
                    "codigo": record["codigo"],
                    "report_type": "technical_inform",
                    "error_code": return_code_technical,
                })

    print("\nDONE")
    print("=" * 100)

    if not args.skip_both:
        print(f"Successful merged reports:    {success_both}")

    if not args.skip_technical:
        print(f"Successful technical reports: {success_technical}")

    print(f"Failed reports:               {len(failed)}")
    print(f"Output directory:             {output_dir}")

    if failed:
        write_failed_log(failed, output_dir)

        print("\nFailed records:")
        for item in failed:
            print(
                f"  - {item['name']} | "
                f"{item['cultivo']} | "
                f"{item['codigo']} | "
                f"{item['report_type']} | "
                f"error={item['error_code']}"
            )


if __name__ == "__main__":
    main()

# run_main_from_csv_parallel.py
#
# Recommended for Excel/xlwings stability:
#
# python run_main_from_csv_parallel.py ^
#   --input-csv "out.csv" ^
#   --main-script "D:\INIA_CODE\INIA_Puno_Software_v1.0.0.2\INIA_Software\main.py" ^
#   --resultados-excel "D:\INIA_CODE\INIA_Puno_Software_v1.0.0.2\INIA_Software\RESULTADOS USUARIOS 2M_Illpa 2.0.2.xlsx" ^
#   --template-excel "D:\INIA_CODE\INIA_Puno_Software_v1.0.0.2\INIA_Software\Software_Mejorado_Cultivos_Anuales_2025-2026_Arapa.xlsx" ^
#   --report-root "G:\Mi unidad\REPORTES_GENERADOS" ^
#   --pdf-folder "G:\Mi unidad\LABSAF ILLPA\CAMPAÑA PERU 2M- LABSAF ILLPA\INFORMES DE ENSAYO" ^
#   --report-script "D:\INIA_CODE\INIA_Puno_Software_v1.0.0.2\INIA_Software\report_pdf.py" ^
#   --workers 1 ^
#   --delay-between-jobs 10 ^
#   --retries 2 ^
#   --kill-excel-before-retry

from pathlib import Path
import argparse
import csv
import subprocess
import sys
import re
import unicodedata
import time
from concurrent.futures import ProcessPoolExecutor, as_completed


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def safe_filename(text):
    """
    Convert a person name/cultivo into a safe filename.
    """
    if text is None:
        return "unknown"

    text = str(text).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "_", text)

    return text.strip("_") or "unknown"


def read_jobs_from_csv(csv_file):
    """
    Reads CSV with columns:

        NOMBRES Y APELLIDOS
        CULTIVO A INSTALAR
    """
    csv_file = Path(csv_file)

    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    jobs = []

    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required_columns = [
            "NOMBRES Y APELLIDOS",
            "CULTIVO A INSTALAR",
        ]

        for col in required_columns:
            if col not in reader.fieldnames:
                raise ValueError(
                    f"Missing column in CSV: {col}\n"
                    f"Found columns: {reader.fieldnames}"
                )

        for row in reader:
            name = row.get("NOMBRES Y APELLIDOS", "").strip()
            cultivo = row.get("CULTIVO A INSTALAR", "").strip()

            if not name or not cultivo:
                continue

            jobs.append({
                "name": name,
                "cultivo": cultivo,
            })

    return jobs


def kill_excel_processes():
    """
    Force-close all Excel processes.

    WARNING:
    This closes every open Excel window on the computer.
    Use only when the machine is dedicated to running this batch.
    """
    subprocess.run(
        ["taskkill", "/F", "/IM", "EXCEL.EXE"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def run_one_job(job, args_dict, attempt=1):
    """
    Runs main.py for one person/cultivo.
    """
    name = job["name"]
    cultivo = job["cultivo"]

    logs_dir = Path(args_dict["logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)

    base_log_name = f"{safe_filename(name)}_{safe_filename(cultivo)}"

    if attempt == 1:
        log_file = logs_dir / f"{base_log_name}.log"
    else:
        log_file = logs_dir / f"{base_log_name}_retry_{attempt}.log"

    command = [
        sys.executable,
        args_dict["main_script"],

        "--resultados-excel",
        args_dict["resultados_excel"],

        "--template-excel",
        args_dict["template_excel"],

        "--name",
        name,

        "--cultivo",
        cultivo,

        "--report-root",
        args_dict["report_root"],

        "--pdf-folder",
        args_dict["pdf_folder"],

        "--report-script",
        args_dict["report_script"],
    ]

    with open(log_file, "w", encoding="utf-8") as log:
        log.write("Running command:\n")
        log.write(" ".join(f'"{x}"' if " " in x else x for x in command))
        log.write("\n\n")

        result = subprocess.run(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

    return {
        "name": name,
        "cultivo": cultivo,
        "returncode": result.returncode,
        "log_file": str(log_file),
        "attempt": attempt,
    }


def run_one_job_with_retries(job, args_dict, retries=2, delay=10, kill_excel_before_retry=False):
    """
    Runs one job and retries if it fails.

    This is useful for random Excel/xlwings/COM/RPC failures.
    """
    last_result = None
    total_attempts = retries + 1

    for attempt in range(1, total_attempts + 1):
        result = run_one_job(job, args_dict, attempt=attempt)
        last_result = result

        if result["returncode"] == 0:
            return result

        print(
            f"[RETRY NEEDED] {job['name']} | {job['cultivo']} "
            f"failed on attempt {attempt}/{total_attempts}"
        )
        print(f"               Log: {result['log_file']}")

        if attempt < total_attempts:
            if kill_excel_before_retry:
                print("Closing leftover Excel processes before retry...")
                kill_excel_processes()
                time.sleep(3)

            print(f"Waiting {delay} seconds before retry...")
            time.sleep(delay)

    return last_result


def print_result(result):
    """
    Prints one job result and returns True if successful.
    """
    name = result["name"]
    cultivo = result["cultivo"]
    returncode = result["returncode"]
    log_file = result["log_file"]
    attempt = result.get("attempt", 1)

    if returncode == 0:
        if attempt == 1:
            print(f"[OK] {name} | {cultivo}")
        else:
            print(f"[OK after retry {attempt}] {name} | {cultivo}")
        return True

    print(f"[FAILED] {name} | {cultivo}")
    print(f"         Log: {log_file}")
    return False


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run main.py for all rows in a CSV file."
    )

    parser.add_argument(
        "--input-csv",
        required=True,
        help="CSV generated by filter_by_distrito.py.",
    )

    parser.add_argument(
        "--main-script",
        default="main.py",
        help="Path to main.py.",
    )

    parser.add_argument(
        "--resultados-excel",
        required=True,
        help="Input RESULTADOS Excel file.",
    )

    parser.add_argument(
        "--template-excel",
        required=True,
        help="Template Excel file.",
    )

    parser.add_argument(
        "--report-root",
        required=True,
        help="Output folder for generated reports.",
    )

    parser.add_argument(
        "--pdf-folder",
        required=True,
        help="Folder containing original laboratory PDF reports.",
    )

    parser.add_argument(
        "--report-script",
        required=True,
        help="Path to report_pdf.py.",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Number of parallel workers. "
            "Use 1 if Excel/xlwings/COM is involved. Default: 1."
        ),
    )

    parser.add_argument(
        "--logs-dir",
        default="batch_logs",
        help="Folder where logs will be saved.",
    )

    parser.add_argument(
        "--delay-between-jobs",
        type=float,
        default=10.0,
        help=(
            "Seconds to wait between jobs in sequential mode. "
            "Useful for Excel/xlwings cleanup. Default: 10."
        ),
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retries for failed jobs in sequential mode. Default: 2.",
    )

    parser.add_argument(
        "--kill-excel-before-job",
        action="store_true",
        help=(
            "Force-close Excel before each job. "
            "WARNING: closes all open Excel windows."
        ),
    )

    parser.add_argument(
        "--kill-excel-before-retry",
        action="store_true",
        help=(
            "Force-close Excel before retrying a failed job. "
            "WARNING: closes all open Excel windows."
        ),
    )

    args = parser.parse_args()

    jobs = read_jobs_from_csv(args.input_csv)

    if not jobs:
        print("No jobs found in CSV.")
        return

    print(f"Jobs found: {len(jobs)}")
    print(f"Workers: {args.workers}")

    if args.workers == 1:
        print("Sequential mode enabled.")
        print(f"Delay between jobs: {args.delay_between_jobs} seconds")
        print(f"Retries per failed job: {args.retries}")
    else:
        print("Parallel mode enabled.")
        print("WARNING: parallel mode is not recommended if main.py uses Excel/xlwings.")

    if args.kill_excel_before_job:
        print("WARNING: Excel will be force-closed before every job.")

    if args.kill_excel_before_retry:
        print("WARNING: Excel will be force-closed before every retry.")

    args_dict = {
        "main_script": str(Path(args.main_script)),
        "resultados_excel": str(Path(args.resultados_excel)),
        "template_excel": str(Path(args.template_excel)),
        "report_root": str(Path(args.report_root)),
        "pdf_folder": str(Path(args.pdf_folder)),
        "report_script": str(Path(args.report_script)),
        "logs_dir": str(Path(args.logs_dir)),
    }

    successes = 0
    failures = 0

    # ------------------------------------------------------------
    # Sequential mode: safest for Excel/xlwings
    # ------------------------------------------------------------
    if args.workers == 1:
        for index, job in enumerate(jobs, start=1):
            print()
            print(f"[{index}/{len(jobs)}] Starting: {job['name']} | {job['cultivo']}")

            if args.kill_excel_before_job:
                print("Closing leftover Excel processes before job...")
                kill_excel_processes()
                time.sleep(3)

            result = run_one_job_with_retries(
                job=job,
                args_dict=args_dict,
                retries=args.retries,
                delay=args.delay_between_jobs,
                kill_excel_before_retry=args.kill_excel_before_retry,
            )

            if print_result(result):
                successes += 1
            else:
                failures += 1

            if index < len(jobs):
                print(f"Waiting {args.delay_between_jobs} seconds before next job...")
                time.sleep(args.delay_between_jobs)

    # ------------------------------------------------------------
    # Parallel mode: kept for non-Excel-safe workflows
    # ------------------------------------------------------------
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(run_one_job, job, args_dict, 1)
                for job in jobs
            ]

            for future in as_completed(futures):
                result = future.result()

                if print_result(result):
                    successes += 1
                else:
                    failures += 1

    print()
    print("Batch finished.")
    print(f"Successful: {successes}")
    print(f"Failed: {failures}")
    print(f"Logs folder: {args.logs_dir}")


if __name__ == "__main__":
    main()

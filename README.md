# INIA Puno — Soil Analysis & Fertilizer Recommendation System

Automated soil-data processing, fertilizer optimization, and report generation system developed for the INIA Puno soil laboratory workflow.

The project takes laboratory soil-analysis data, combines it with crop information and an Excel fertilizer-recommendation model, calculates nutrient requirements, optimizes fertilizer doses, and automatically produces Excel and PDF reports for multiple producers.

## Main Application

The main user interface is:

```text
app_multiple.py
```

It provides a local Flask web interface where the operator can:

- Upload a CSV containing the producers/samples to process.
- Select or upload the laboratory Excel database.
- Select or upload the fertilizer recommendation Excel template.
- Configure output and laboratory-PDF directories.
- Launch the complete batch-processing pipeline.
- Monitor execution logs in real time.
- Retry jobs that fail because of Excel/COM errors.
- Stop a running batch.

The application launches:

```text
app_multiple.py
        │
        ▼
run_main_from_csv_parallel.py
        │
        ▼
INIA_Software/main.py
        │
        ├── Read laboratory soil data
        ├── Build producer-specific Excel workbook
        ├── Calculate nutrient efficiencies
        ├── Calculate nitrogen mineralization
        ├── Recalculate Excel formulas
        ├── Extract crop nutrient requirements
        ├── Optimize fertilizer doses
        ├── Write fertilizer recommendations
        ├── Recalculate final workbook
        ├── Export Excel sheets to PDF
        ├── Generate final report
        └── Find/copy original SU laboratory PDFs
```

---

## Processing Workflow

For every producer/crop combination, the software performs the following workflow.

### 1. Read laboratory data

The main data source is an Excel workbook containing the INIA soil laboratory results.

Typical information includes:

```text
NOMBRES Y APELLIDOS
DEP
PROV
DIST
CULTIVO A INSTALAR
CODIGO
pH
CE
Materia Orgánica
Arena
Arcilla
Limo
Clase Textural
Ca
Mg
Na
K
N
P
CICe
Clima
```

The producer is identified using `NOMBRES Y APELLIDOS`.

### 2. Populate the fertilizer Excel model

`INIA_Software/excel_builder.py` copies the relevant laboratory values into the fertilizer recommendation template.

The program also determines the phosphorus interpretation method from soil pH and inserts calculated parameters required by the Excel model.

### 3. Nutrient-efficiency calculation

`get_efficiency.py` calculates nutrient-use efficiencies as a function of:

```text
Soil pH
+
Soil texture
```

Efficiencies are calculated for:

```text
N
P
K
Ca
Mg
S
```

### 4. Nitrogen mineralization

`get_nitrogen_mineralization.py` estimates nitrogen mineralization using soil texture and climatic classification.

### 5. Excel recalculation

The generated workbook is opened using `xlwings`.

Microsoft Excel recalculates the formulas before the nutrient requirements are extracted.

This is important because `openpyxl` can read/write formulas but does not calculate Excel formulas itself.

### 6. Read crop nutrient requirements

The calculated nutrient requirements are obtained from the fertilizer workbook, currently from:

```text
Nec_fert!K37:K42
```

### 7. Fertilizer optimization

`INIA_Software/optimizer.py` uses numerical optimization to determine appropriate fertilizer doses.

The optimizer is built with:

```text
NumPy
pandas
SciPy
scipy.optimize.linprog
```

It considers nutrient requirements, fertilizer compositions, fertilizer dose limits, soil pH restrictions, and the maximum number of fertilizer products to use.

The optimization primarily targets:

```text
N
P₂O₅
K₂O
```

while additional nutrients such as CaO, MgO and S remain available in the fertilizer composition model.

### 8. Write optimized recommendation

The selected fertilizers and doses are written into the recommendation workbook.

Typical output is expressed in fertilizer dose units such as:

```text
kg/ha
```

### 9. Generate PDF

Selected Excel sheets such as:

```text
Gráfico_Int
Rec_fert
```

are exported to PDF using Microsoft Excel through `xlwings`.

### 10. Attach original laboratory report

The software extracts the producer's SU laboratory number and searches the configured PDF archive for the corresponding original laboratory report.

The relevant PDF files are copied into the producer's final report directory.

---

## Technology Stack

| Technology | Role |
|---|---|
| Python | Main application and scientific processing |
| Flask | Web interface |
| HTML / CSS / JavaScript | Browser frontend and live log viewer |
| openpyxl | Excel workbook reading/writing |
| xlwings | Microsoft Excel automation |
| Microsoft Excel | Formula recalculation and PDF export |
| NumPy | Numerical calculations |
| pandas | Structured numerical data |
| SciPy | Fertilizer optimization |
| ReportLab | Programmatic PDF generation |
| MySQL Connector | Optional MySQL database support |
| Pillow | Excel image support |
| Google Drive Desktop | Optional synchronized report/PDF storage |

---

## Data Storage

### Primary workflow — Excel database

The main application currently uses an Excel workbook as the operational soil-analysis database.

Example:

```text
RESULTADOS USUARIOS 2M_Illpa 2.0.2.xlsx
```

This database is combined with the fertilizer recommendation template:

```text
Software_Mejorado_Cultivos_Anuales_2025-2026_Arapa.xlsx
```

Therefore, **MySQL is not required to run the main `app_multiple.py` workflow**.

### Optional MySQL workflow

The repository also contains utilities that work with MySQL:

```text
db_to_xlsx.py
report_pdf_db.py
```

The current configuration expects approximately:

```text
Host:     127.0.0.1
Port:     3306
Database: soil_db
Table:    soil_samples
```

For production use, database credentials should be stored in environment variables rather than directly in Python files.

---

## System Requirements

The main pipeline is currently designed primarily for **Windows**.

Required software:

```text
Python 3
Microsoft Excel
```

Recommended when the default report locations are used:

```text
Google Drive for Desktop
```

Microsoft Excel is required because the project uses `xlwings` for workbook recalculation and PDF generation.

The batch runner also contains Windows-specific recovery commands for terminating frozen Excel processes.

---

## Python Dependencies

A practical installation is:

```bash
pip install flask openpyxl xlwings numpy pandas scipy pillow reportlab mysql-connector-python pywin32
```

The core Excel workflow mainly requires:

```text
flask
openpyxl
xlwings
numpy
pandas
scipy
pillow
```

The MySQL/report utilities additionally require:

```text
mysql-connector-python
reportlab
```

A `requirements.txt` file is recommended for reproducible installations.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/marvlad/INIA_Puno.git
cd INIA_Puno
```

Create a virtual environment:

```bash
python -m venv .venv
```

On Windows:

```bash
.venv\Scripts\activate
```

Install the dependencies:

```bash
pip install flask openpyxl xlwings numpy pandas scipy pillow reportlab mysql-connector-python pywin32
```

---

## Input CSV

`app_multiple.py` expects a CSV containing at least:

```csv
NOMBRES Y APELLIDOS,CULTIVO A INSTALAR
Juan Perez,PAPA MEJORADA
Maria Quispe,CEBADA
```

The repository contains helper scripts for producing these batch CSV files from the laboratory Excel database.

For example:

```text
filter_by_distrito.py
filter_excel_general.py
```

---

## Running the Web Interface

Start the application with:

```bash
python app_multiple.py
```

Open the address displayed by Flask in a browser.

Typically:

```text
http://127.0.0.1:5000
```

The interface allows the operator to select the CSV, database workbook, Excel template, output directories and processing configuration.

For Excel stability, the recommended configuration is:

```text
Workers: 1
Delay between jobs: 10 seconds
Retries: 2
Close Excel before retry: enabled
```

Using several parallel workers is not recommended when Microsoft Excel/xlwings is involved.

---

## Output

Each producer receives a dedicated output directory.

A typical result may contain:

```text
requirements.csv
optimal_values.csv
..._FILLED.xlsx
..._OPTIMIZED.xlsx
Excel_Report_<producer>_<crop>.pdf
Informe_<producer>_<crop>.pdf
original_SU_report.pdf
```

Batch execution logs are stored separately so unsuccessful producers can be diagnosed without stopping the entire processing campaign.

The Flask application also stores web-run information under:

```text
web_runs/
```

and uploaded temporary files under:

```text
uploads/
```

---

## Repository Structure

```text
INIA_Puno/
│
├── app_multiple.py
│   Web interface and main operator entry point.
│
├── run_main_from_csv_parallel.py
│   Batch execution, retries and optional parallel processing.
│
├── filter_by_distrito.py
│   Creates batch CSVs by district.
│
├── filter_excel_general.py
│   General Excel filtering and CSV generation.
│
├── db_to_xlsx.py
│   Alternative MySQL-to-Excel workflow.
│
├── report_pdf_db.py
│   MySQL-based PDF report generator.
│
├── get_path_GDrive.py
│   Finds SU laboratory PDFs in a local/Google Drive directory.
│
├── INIA_Software/
│   ├── main.py
│   ├── excel_builder.py
│   ├── excel_requirements.py
│   ├── excel_writer.py
│   ├── excel_to_pdf.py
│   ├── optimizer.py
│   ├── get_efficiency.py
│   ├── get_nitrogen_mineralization.py
│   ├── su_pdf_finder.py
│   ├── report_runner.py
│   ├── config.py
│   └── utils.py
│
├── extracted_images/
│   Images used by the Excel/report templates when available.
│
└── README.md
```

---

## Batch Processing and Excel Stability

Excel automation through COM/xlwings may occasionally leave an Excel process open after an error.

For this reason the batch runner supports:

```text
Retries
Delay between jobs
Close Excel before retry
Close Excel before each job
```

The safest configuration is one worker at a time.

Be aware that the "close Excel" options terminate **all running Microsoft Excel processes**, including unrelated workbooks opened by the operator.

---

## Current Configuration Notes

Several paths in the application are currently Windows-specific and installation-specific, for example:

```text
D:\INIA_CODE\...
G:\Mi unidad\...
```

These paths should be changed through the web interface or moved to a configuration file/environment variables when installing the system on another computer.

The application currently references a report generator named:

```text
report_pdf.py
```

Before deploying a clean clone, verify that this script is present and that `app_multiple.py` points to the intended report generator.

The repository also contains:

```text
report_pdf_db.py
```

which is the MySQL-based report implementation.

---

## Security / Production Notes

The Flask interface is currently intended primarily as a local operator tool.

For deployment on a network or public server:

- Disable Flask debug mode.
- Validate uploaded file names and file types.
- Move database credentials to environment variables.
- Move machine-specific paths into a configuration file.
- Restrict access to the application.
- Back up the laboratory database before batch processing.
- Do not expose personally identifiable laboratory/customer information publicly.

---

## Scientific / Operational Scope

This software automates an INIA soil-laboratory and fertilizer-recommendation workflow. It combines laboratory measurements, agronomic calculation tables and numerical fertilizer optimization.

Generated recommendations should remain subject to the scientific and agronomic validation procedures adopted by INIA and the corresponding laboratory/agricultural specialists.

---

## Project

**INIA Puno Soil Analysis & Fertilizer Recommendation Automation**

Main application:

```text
app_multiple.py
```

Repository:

```text
https://github.com/marvlad/INIA_Puno
```

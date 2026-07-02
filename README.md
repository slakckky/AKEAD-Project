# AKEAD Invoice Importer

Desktop app (Tkinter / Python) that reads PDF invoices and matches line items
against products in the AKEAD MySQL database.

## Files

```
app.py                        GUI (main entry point)
auto_pdf_import.py            PDF parser — extracts items, writes to staging DB
professional_product_match.py Rule-based product matching
ai_product_match.py           Claude AI matching for unresolved items
import_to_invoices.py         Writes approved results into AKEAD tables
test_db.py                    DB connection test

create_pdf_import_tables.sql  Staging table schema
setup.bat                     Windows one-time setup
start_akead_importer.bat      Windows launcher
AKEAD.command                 macOS double-click launcher
```

## Workflow

```
1. Load Invoice     → select PDF, copied to pdf_eingang/
2. Preview          → extract items without writing anything
3. Save to Staging  → write to pdf_import_documents + pdf_import_items
4. Product Matching → rule-based match, then AI for unresolved items
5. Finalize Invoice → write to AKEAD invoices tables
```

Every write step shows a dry-run first and asks for confirmation.

## Matching Pipeline

```
1. Exact ref code       (produits.ref_prd)
2. Barcode              (codebarres table, found via regex on raw_line)
3. Barcode → Open Food Facts → product name → fuzzy match
4. Fuzzy name match     (difflib, ≥90% auto / ≥75% suggestion)
5. Claude AI            (uses invoice name + AKEAD candidates + OFF data)
```

## Setup

### Windows

```bat
setup.bat                  # one-time: creates .venv and installs packages
start_akead_importer.bat   # launch the app
```

### macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --prefer-binary -r requirements.txt
```

Then double-click `AKEAD.command` to launch, or `python app.py` from terminal.

## Configuration

Create `.env` in the project root:

```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=codex_read
DB_PASSWORD=yourpassword
DB_NAME=datenbank
ANTHROPIC_API_KEY=sk-ant-...
```

`ANTHROPIC_API_KEY` is only required for the AI matching step (step 4b).
The MySQL server must be reachable at the configured host — run the app on the office PC.

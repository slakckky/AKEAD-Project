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
5. Finalize Invoice → write to AKEAD invoices + invoices_details tables
```

Every write step shows a dry-run first and asks for confirmation.

## Matching Pipeline

```
1. Exact ref code            (produits.ref_prd)
2. Barcode                   (codebarres table)
3. Barcode → Open Food Facts → product name → fuzzy match
4. Fuzzy name match          (difflib, ≥90% auto / ≥75% suggestion)
5. Claude AI                 (invoice name + AKEAD candidates + OFF data)
```

New products not found in AKEAD are created automatically with a generated
article number (`IMP000001`, `IMP000002`, …) and the supplier's article number
stored in `lib_tech`.

## Tax Handling

- Austrian supplier invoices (UID starting with `ATU`): VAT rate is read from
  the PDF and written to `invoices_details.taux_tva`.
- Foreign supplier invoices (no `ATU` in PDF): `taux_tva` is always written
  as 0 (no Austrian VAT applies).

Detection is automatic at Step 3; the result is stored in
`pdf_import_documents.is_austrian_supplier`.

## Supplier / Vendor Lookup

Step 5 searches the `clients` table first, then `vendors`. Fuzzy matching
(≥55% similarity) is used as a fallback. If the supplier is not found in
either table, a new record is created automatically.

## Units

| Invoice text       | Written to DB |
|--------------------|---------------|
| Kolli / Karton / Kart / PK | `KOL` |
| Stk / Stück        | `St`  |
| Kg                 | `Kg`  |
| Fl / Flasche       | `Fl`  |

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

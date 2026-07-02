# AKEAD Invoice Importer

Desktop application (Tkinter / Python) that reads PDF invoices and matches the line items
against products in the AKEAD MySQL database.
Runs on Windows (office PC) and macOS (development).

## Architecture — 6 active files

```
app.py                        Main entry point — Tkinter GUI
auto_pdf_import.py            PDF parser: text/table extraction, writes to staging DB
professional_product_match.py Rule-based product matching (exact / barcode / fuzzy)
ai_product_match.py           Claude AI suggestions for hard-to-match items
import_to_invoices.py         Writes approved matches into the real AKEAD tables
test_db.py                    MySQL connection test (utility script)
```

```
create_pdf_import_tables.sql  Staging table schema
requirements.txt              Python dependencies
setup.bat                     One-click Windows setup (venv + pip install)
start_akead_importer.bat      Windows launcher
```

## 5-Step Workflow (GUI)

```
1. Load Invoice     Copy PDF into pdf_eingang/
2. Preview          auto_pdf_import.py --preview  (shows extracted rows, writes nothing)
3. Save to Staging  auto_pdf_import.py            (writes to pdf_import_documents + pdf_import_items)
4. Product Matching professional_product_match.py (rule-based, dry-run then confirm)
                    ai_product_match.py           (AI report, optional)
5. Finalize Invoice import_to_invoices.py         (dry-run then confirm, writes to AKEAD invoices)
```

Every write step requires explicit confirmation (dry-run output shown first, then Yes/No).

## Setup

### Windows (office PC)

```bat
:: One-time setup:
setup.bat

:: On subsequent launches:
start_akead_importer.bat
```

### macOS / Linux (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --prefer-binary -r requirements.txt
python app.py
```

## Configuration (.env)

Create a `.env` file in the project root:

```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=codex_read
DB_PASSWORD=yourpassword
DB_NAME=datenbank
ANTHROPIC_API_KEY=sk-ant-...
```

Steps 1–3 and 4a (rule-based matching) work without `ANTHROPIC_API_KEY`.
Only the "Get AI Suggestions" button requires the API key.

The MySQL server runs on the office PC (127.0.0.1); run the app on that machine.

## Barcode Matching

### Invoices with barcodes (EAN-8 / EAN-13 / EAN-14)

`auto_pdf_import.py` writes all cell values for each line into the `raw_line` field.
`barcode_candidates()` in `professional_product_match.py` finds barcodes in that field
using the regex `\b\d{8,14}\b` and looks them up in AKEAD's `codebarres` table.

Example: EAN-13 codes in Hunkar / SRGL invoices (e.g. 3760091938473) are matched
automatically this way.

### Invoices without barcodes

Four-layer matching strategy applied in order:

1. **Exact reference code** — direct lookup against `produits.ref_prd`
2. **Barcode** — `codebarres.barcode` table (via regex on `raw_line`)
3. **Fuzzy name** — `difflib.SequenceMatcher` on product name
4. **AI suggestion** — Claude `claude-opus-4-8` for abbreviated, truncated, or
   cross-language names (e.g. "Honig Sy" → "Honig Sirup")

All four layers run even when no barcode is present, so suppliers like Brajlovic,
Bursam, Bazar and Demka still achieve high match rates.

### Unmatched items

`professional_product_match.py` classifies each row in its report:

| Status | Meaning |
|--------|---------|
| `auto_match` | High-confidence, matched automatically |
| `vorschlag` | Suggestion found, awaiting manual approval |
| `manuell pruefen` | No match found, sent to AI |

Rows classified as `manuell pruefen` are forwarded to `ai_product_match.py`.
Claude selects the most likely AKEAD product; if none fits it returns `no_match`
(it never invents barcodes or product IDs).

## Supported Invoice Formats

| Supplier | Format | Barcode | Positions |
|----------|--------|---------|-----------|
| Brajlovic GmbH | Free text (pdfplumber) | No | 88+ |
| Bursam e.K. / AY Market | Table | No | 33 |
| Onkel-Sahingoz / Bazar | Free text | No | 56+ |
| Demka GmbH | Table | No | 56 |
| SRGL KG / Hunkar | Transposed matrix table | EAN-13 | 11 |

## MySQL Staging Schema

```sql
-- Schema file:
create_pdf_import_tables.sql
```

Two staging tables:
- `pdf_import_documents` — invoice header (supplier, date, document number, type)
- `pdf_import_items` — invoice line items linked to a document

Real AKEAD tables (`orders`, `invoices`, `produits`, `clients`, `vendors`) are only
written to in step 5.

## Platform Notes

### Windows
`app.py` tries two Python paths: `.venv\Scripts\python.exe` (Windows) and
`.venv/bin/python3` (macOS/Linux). If it starts under the wrong interpreter it
re-launches itself under the `.venv` Python via `subprocess.Popen`.

### macOS
Uses `os.execv()` to switch to the `.venv` interpreter.
Opens files/folders with the `open` shell command.

## Sensitive Files (never commit)

`.gitignore` excludes:
- `.env` — database password and API key
- `pdf_eingang/`, `pdf_importiert/`, `pdf_fehler/` — real customer invoices
- `*.csv`, `*.md` (except this README and SQL schema)
- `backup_vor_codex.sql`, `debug_*.txt`

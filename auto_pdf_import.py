from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import hashlib
import json
import logging
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from typing import Any

import pdfplumber
import pymysql


BASE_DIR = Path(__file__).resolve().parent
PDF_INPUT_DIR = BASE_DIR / "pdf_eingang"
PDF_IMPORTED_DIR = BASE_DIR / "pdf_importiert"
PDF_ERROR_DIR = BASE_DIR / "pdf_fehler"
CREATE_TABLES_SQL = BASE_DIR / "create_pdf_import_tables.sql"
ENV_CANDIDATES = (BASE_DIR / ".env", BASE_DIR / "Textdokument.env")
LOG_FILE = BASE_DIR / "auto_pdf_import.log"
PDF_REPORT = BASE_DIR / "auto_pdf_import_report.csv"
ERROR_REPORT = BASE_DIR / "import_errors.csv"
DATABASE_NAME = "datenbank"

MIN_POSITIONS_BEFORE_OCR = 10

DDG_AVAILABLE = True

# Load own company name from .env to exclude from supplier detection
def _load_own_company() -> str:
    for path in ENV_CANDIDATES:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("OWN_COMPANY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

OWN_COMPANY_NAME: str = _load_own_company()


def duckduckgo_company_lookup(name: str) -> str:
    """Search DuckDuckGo Instant Answers for company address info.
    Returns a short address/description string, or '' if nothing found.
    Best-effort: small/unknown suppliers will likely return nothing.
    """
    global DDG_AVAILABLE
    if not DDG_AVAILABLE or not name:
        return ""
    try:
        query = urllib.parse.quote(f"{name} Adresse")
        url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "akead-pdf-import/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        DDG_AVAILABLE = False
        logging.warning("DuckDuckGo lookup failed: %s", exc)
        return ""

    # Infobox: structured company data (best source)
    infobox = data.get("Infobox") or {}
    for entry in infobox.get("content") or []:
        label = (entry.get("label") or "").lower()
        if any(k in label for k in ("headquarter", "sitz", "adresse", "address", "standort")):
            value = str(entry.get("value") or "").strip()
            if value:
                return value[:300]

    # AbstractText: Wikipedia-style summary (often has location)
    abstract = (data.get("AbstractText") or "").strip()
    if abstract:
        # Keep only if it contains something address-like (zip, city, country)
        if re.search(r"\d{4,5}|\b(GmbH|str\.|strasse|straße|platz|weg)\b", abstract, re.IGNORECASE):
            return abstract[:300]

    return ""
UNKNOWN_FALLBACK_TYPES = {"unknown", "unbekannt", "parser_unsicher"}


def setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def find_env_file() -> Path:
    for path in ENV_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("Keine env-Datei gefunden.")


def connect_db(config: dict[str, str]):
    database = config.get("DB_NAME", DATABASE_NAME)
    if database != DATABASE_NAME:
        raise ValueError(f"DB_NAME muss exakt '{DATABASE_NAME}' sein, ist aber: {database!r}")
    return pymysql.connect(
        host=config["DB_HOST"],
        port=int(config.get("DB_PORT", "3306")),
        user=config["DB_USER"],
        password=config["DB_PASSWORD"],
        database=database,
        charset="utf8",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=10,
        read_timeout=10,
        write_timeout=10,
    )


def fetch_one(cursor, sql: str, params: tuple = ()) -> dict | None:
    cursor.execute(sql, params)
    return cursor.fetchone()


def fetch_all(cursor, sql: str, params: tuple = ()) -> list[dict]:
    cursor.execute(sql, params)
    return list(cursor.fetchall())


def execute_create_tables(connection) -> None:
    statements = [statement.strip() for statement in CREATE_TABLES_SQL.read_text(encoding="utf-8").split(";") if statement.strip()]
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    ensure_column(connection, "pdf_import_documents", "processing_notes", "ALTER TABLE pdf_import_documents ADD COLUMN processing_notes text")
    ensure_column(connection, "pdf_import_documents", "layout_signature", "ALTER TABLE pdf_import_documents ADD COLUMN layout_signature varchar(255) NOT NULL DEFAULT ''")
    ensure_column(connection, "pdf_import_documents", "ocr_used", "ALTER TABLE pdf_import_documents ADD COLUMN ocr_used tinyint(4) unsigned NOT NULL DEFAULT '0'")
    ensure_column(connection, "pdf_import_documents", "is_safe_invoice", "ALTER TABLE pdf_import_documents ADD COLUMN is_safe_invoice tinyint(4) unsigned NOT NULL DEFAULT '0'")
    ensure_column(connection, "pdf_import_documents", "is_austrian_supplier", "ALTER TABLE pdf_import_documents ADD COLUMN is_austrian_supplier tinyint(4) unsigned NOT NULL DEFAULT '0'")
    ensure_column(connection, "pdf_import_documents", "supplier_address", "ALTER TABLE pdf_import_documents ADD COLUMN supplier_address varchar(500) NOT NULL DEFAULT ''")


def ensure_column(connection, table: str, column: str, alter_sql: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
        if cursor.fetchone() is None:
            cursor.execute(alter_sql)


def repair_mojibake(text: str) -> str:
    if "Ã" not in text and "â" not in text:
        return text
    try:
        return text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    return re.sub(r"\s+", " ", text).strip()


def read_pdf_text_all_pages(pdf_path: Path) -> tuple[str, list[str], list[list[list[str]]]]:
    pages: list[str] = []
    page_lines: list[str] = []
    tables: list[list[list[str]]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            text = repair_mojibake(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
            pages.append(f"--- Seite {page_number} ---\n{text}".strip())
            page_lines.extend(text.splitlines())
            try:
                for table in page.extract_tables() or []:
                    cleaned = [[" ".join((cell or "").split()) for cell in row] for row in table if row]
                    if cleaned:
                        tables.append(cleaned)
            except Exception as exc:
                logging.info("Tabellenextraktion fehlgeschlagen fuer %s Seite %s: %s", pdf_path.name, page_number, exc)
    return "\n\n".join(pages).strip(), page_lines, tables


def extract_text_pdfplumber(pdf_path: Path) -> dict[str, Any]:
    text, lines, tables = read_pdf_text_all_pages(pdf_path)
    return {"method": "pdfplumber", "text": text, "lines": lines, "tables": tables, "ocr_used": False, "notes": ["Text mit pdfplumber extrahiert"]}


def extract_text_pymupdf(pdf_path: Path) -> dict[str, Any]:
    try:
        import fitz  # type: ignore
    except Exception as exc:
        return {"method": "pymupdf", "text": "", "lines": [], "tables": [], "ocr_used": False, "notes": [f"PyMuPDF nicht verfuegbar: {exc}"]}
    pages = []
    with fitz.open(str(pdf_path)) as doc:
        for page_number, page in enumerate(doc, 1):
            pages.append(f"--- Seite {page_number} ---\n{repair_mojibake(page.get_text('text') or '')}".strip())
    text = "\n\n".join(pages).strip()
    return {"method": "pymupdf", "text": text, "lines": text.splitlines(), "tables": [], "ocr_used": False, "notes": ["Text mit PyMuPDF extrahiert"]}


def extract_text_pdfminer(pdf_path: Path) -> dict[str, Any]:
    try:
        from pdfminer.high_level import extract_text  # type: ignore
    except Exception as exc:
        return {"method": "pdfminer.six", "text": "", "lines": [], "tables": [], "ocr_used": False, "notes": [f"pdfminer.six nicht verfuegbar: {exc}"]}
    try:
        text = repair_mojibake(extract_text(str(pdf_path)) or "")
    except Exception as exc:
        return {"method": "pdfminer.six", "text": "", "lines": [], "tables": [], "ocr_used": False, "notes": [f"pdfminer.six fehlgeschlagen: {exc}"]}
    return {"method": "pdfminer.six", "text": text, "lines": text.splitlines(), "tables": [], "ocr_used": False, "notes": ["Text mit pdfminer.six extrahiert"]}


def collect_text_candidates(pdf_path: Path) -> list[dict[str, Any]]:
    candidates = [
        extract_text_pdfplumber(pdf_path),
        extract_text_pymupdf(pdf_path),
        extract_text_pdfminer(pdf_path),
    ]
    return candidates


def quality_for_candidate(pdf_path: Path, candidate: dict[str, Any]) -> dict[str, Any]:
    text = candidate.get("text") or ""
    lines = candidate.get("lines") or text.splitlines()
    tables = candidate.get("tables") or []
    items, parser_name, item_notes = extract_items_all_parsers(pdf_path, text, lines, tables)
    invoice_no = detect_document_no(text, pdf_path.name)
    date_raw = detect_date(text)
    supplier = detect_supplier(lines, text)
    score = (
        len(items) * 10000
        + min(len(text), 10000) // 100
        + min(len([line for line in lines if line.strip()]), 500)
        + (200 if invoice_no and not invoice_no.startswith("PDF-") else 0)
        + (100 if date_raw else 0)
        + (100 if supplier else 0)
    )
    candidate = dict(candidate)
    candidate.update(
        {
            "lines": lines,
            "items": items,
            "position_parser": parser_name,
            "item_notes": item_notes,
            "invoice_no": invoice_no,
            "date_raw": date_raw,
            "supplier": supplier,
            "quality": {
                "score": score,
                "chars": len(text),
                "lines": len([line for line in lines if line.strip()]),
                "positions": len(items),
                "invoice_no_found": bool(invoice_no and not invoice_no.startswith("PDF-")),
                "date_found": bool(date_raw),
                "supplier_found": bool(supplier),
            },
        }
    )
    return candidate


def ocr_candidates(pdf_path: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    text, ok, note = run_ocr_tesseract_if_available(pdf_path)
    candidates.append({"method": "tesseract_ocr", "text": text if ok else "", "lines": text.splitlines() if ok else [], "tables": [], "ocr_used": ok, "notes": [note]})
    text, ok, note = run_ocrmypdf_if_available(pdf_path)
    candidates.append({"method": "ocrmypdf", "text": text if ok else "", "lines": text.splitlines() if ok else [], "tables": [], "ocr_used": ok, "notes": [note]})
    return candidates


def run_ocr_if_available(pdf_path: Path) -> tuple[str, bool, str]:
    ocr_text, ocr_ok, ocr_note = run_ocr_tesseract_if_available(pdf_path)
    if ocr_ok:
        return ocr_text, ocr_ok, ocr_note
    return run_ocrmypdf_if_available(pdf_path)


def run_ocr_tesseract_if_available(pdf_path: Path) -> tuple[str, bool, str]:
    tesseract = shutil.which("tesseract")
    pdftoppm = shutil.which("pdftoppm")
    if tesseract and pdftoppm:
        with tempfile.TemporaryDirectory() as tmp:
            prefix = str(Path(tmp) / "page")
            ppm = subprocess.run([pdftoppm, "-png", str(pdf_path), prefix], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if ppm.returncode != 0:
                return "", False, f"pdftoppm fehlgeschlagen: {ppm.stdout[-1000:]}"
            texts = []
            for image in sorted(Path(tmp).glob("page-*.png")):
                out_base = image.with_suffix("")
                result = subprocess.run([tesseract, str(image), str(out_base), "-l", "deu+eng"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                if result.returncode == 0 and out_base.with_suffix(".txt").exists():
                    texts.append(out_base.with_suffix(".txt").read_text(encoding="utf-8", errors="replace"))
            return "\n".join(texts).strip(), bool(texts), "OCR mit tesseract/pdftoppm ausgefuehrt"

    return "", False, "Tesseract-OCR nicht verfuegbar: tesseract+pdftoppm nicht gefunden"


def run_ocrmypdf_if_available(pdf_path: Path) -> tuple[str, bool, str]:
    ocrmypdf = shutil.which("ocrmypdf")
    if not ocrmypdf:
        return "", False, "OCRmyPDF nicht verfuegbar"
    with tempfile.TemporaryDirectory() as tmp:
        out_pdf = Path(tmp) / "ocr.pdf"
        result = subprocess.run(
            [ocrmypdf, "--force-ocr", "--skip-text", str(pdf_path), str(out_pdf)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode == 0 and out_pdf.exists():
            text, _lines, _tables = read_pdf_text_all_pages(out_pdf)
            return text, True, "OCR mit ocrmypdf ausgefuehrt"
        return "", False, f"ocrmypdf fehlgeschlagen: {result.stdout[-1000:]}"


def first_match(patterns: list[str], text: str, flags: int = re.IGNORECASE) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return " ".join(match.group(1).split())
    return ""


def detect_document_no(text: str, source_file: str) -> str:
    patterns = [
        # Specific known formats (highest confidence)
        r"\b(R-\d{2}-\d{6})\b",
        r"\b(RE\d{2}-\d{7})\b",
        r"\b(RE-[A-Z0-9][A-Z0-9._/-]+)\b",
        r"\b(RG-[A-Z0-9][A-Z0-9._/-]+)\b",
        # Rechnung / Rechnungs-Nr with alphanumeric or pure numeric value
        r"Rechnungs(?:nummer|nr)\.?\s*:?\s*([A-Z0-9][A-Z0-9._/ -]{1,30})",
        r"Rechnung\s*(?:Nr\.?|Nummer|No\.?)\s*:?\s*([A-Z0-9][A-Z0-9._/ -]{1,30})",
        r"Rechnung\s*(?:Nr\.?|Nummer|No\.?)\s*:?\s*(\d+[A-Z0-9._/-]*)",
        r"Rechnung\s*:?\s*(?:Nr\.?|#)?\s*(\d{3,}[A-Z0-9._/-]*)",
        # Lieferschein / Lieferung number
        r"Lieferschein\s*(?:Nr\.?|Nummer|No\.?)?\s*:?\s*([A-Z0-9]\S{1,20})",
        r"Lieferschein\s*(?:Nr\.?|Nummer|No\.?)?\s*:?\s*(\d+[A-Z0-9._/-]*)",
        r"Lieferung\s*(?:Nr\.?|Nummer|No\.?)?\s*:?\s*([A-Z0-9]\S{1,20})",
        r"Lieferung\s*(?:Nr\.?|Nummer|No\.?)?\s*:?\s*(\d+[A-Z0-9._/-]*)",
        # Beleg / generic
        r"Beleg\s*(?:Nr\.?|Nummer|No\.?)\s*:?\s*([A-Z0-9][A-Z0-9._/-]+)",
        r"Beleg\s*(?:Nr\.?|Nummer|No\.?)\s*:?\s*(\d+[A-Z0-9._/-]*)",
    ]
    value = first_match(patterns, text)
    if value:
        return value.strip()[:50]
    digest = hashlib.sha1((source_file + text[:1000]).encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"PDF-{digest}"


def detect_date(text: str) -> str:
    return first_match(
        [
            r"Rechnungsdatum\s*:?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            r"Belegdatum\s*:?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            r"Datum\s*:?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{4})\b",
        ],
        text,
    )


def parse_date(value: str) -> str | None:
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _trim_to_company_name(raw: str) -> str:
    """Strip address/street parts after the company name.

    Examples:
      'Demka GmbH / Lembacher Str. 28' -> 'Demka GmbH'
      'Demka GmbH, Musterstr. 1, 12345 Stadt' -> 'Demka GmbH'
      'Demka GmbH 68229 Mannheim' -> 'Demka GmbH'
      'Aymarkt GmbH Mariahilfer Str. 1 1060 Wien' -> 'Aymarkt GmbH'
    """
    street_cut = re.compile(
        # compound: "Industriestraße", "Industriestr.", "Hauptgasse" etc.
        r"\s+\S+(?:str\.|straße|strasse|gasse|weg|platz|allee|ring|damm|chaussee)"
        # spaced: "Mariahilfer Str.", "Muster Gasse" etc.
        r"|\s+\w+\s+(?:str\.|strasse|straße|gasse|weg|platz|allee|ring|damm|chaussee)"
        r"|\s+(?:str\.|strasse|straße|gasse|weg|platz|allee|ring|damm|chaussee)"
        r"|\s+\d{4,5}\b",   # postal code (4-5 digits)
        re.IGNORECASE,
    )

    # First split on explicit separators (slash, comma, em-dash)
    parts = re.split(r"\s*/\s*|,\s*|\s+[-–]\s+", raw)
    for part in parts:
        part = part.strip()
        if not part or not re.search(r"[A-Za-zÄÖÜäöüß]", part):
            continue
        # Within this part, cut at the first street/postal-code indicator
        m = street_cut.search(part)
        if m:
            candidate = part[: m.start()].strip()
            if re.search(r"[A-Za-zÄÖÜäöüß]", candidate):
                return candidate[:255]
        return part[:255]
    return raw.split(",")[0].strip()[:255]


def detect_supplier(lines: list[str], text: str) -> str:
    """Detect the supplier (invoice issuer) from PDF text.

    Strategy:
    1. Collect all company-suffix lines in the first 60 lines.
    2. Score each candidate by proximity to supplier anchors (IBAN, USt-Id,
       Steuernummer, HRB) and penalise proximity to customer anchors
       (Kundennr, Rg.an, Lieferanschrift).
    3. Return the best-scoring candidate after trimming address fragments.
    4. Fall back to first non-ignored line with letters if no suffix found.
    """
    company_suffix = re.compile(
        r"\b(GmbH|e\.?K\.?|KG|AG|Ltd|Inc|Corp|OHG|GbR|S\.A\.)\b", re.IGNORECASE
    )
    supplier_anchor = re.compile(
        r"\b(ust.?id|uid.?nr|steuernr|steuer.?nr|iban|bic|bankverbindung|hrb|amtsgericht|inhaber)\b",
        re.IGNORECASE,
    )
    customer_anchor = re.compile(
        r"\b(kundennr|kunden.?nr|kunden.?nummer|rg\.?\s*an|rechnung\s*an"
        r"|lieferanschrift|rechnungsanschrift|lieferadresse|rechnungsadresse)\b"
        r"|^\s*(an\s*:|empf[aä]nger\s*:)",
        re.IGNORECASE,
    )
    ignore = re.compile(
        r"^(nr\.?|artikel|beschreibung|menge|einheit|preis|betrag)$"
        r"|^(rechnung|beleg|datum|seite)\b"
        r"|^(tel\.?|fax|email|web|www)\b",
        re.IGNORECASE,
    )

    # Collect company candidates and anchor positions in first 60 lines
    candidates: list[tuple[int, str]] = []
    supplier_anchors: list[int] = []
    customer_anchors: list[int] = []

    own_name = OWN_COMPANY_NAME.lower()
    for i, line in enumerate(lines[:60]):
        clean = " ".join(line.split()).strip(":- ")
        if len(clean) < 3:
            continue
        # Skip own company — it is always the buyer, never the supplier
        if own_name and own_name in clean.lower():
            customer_anchors.append(i)
            continue
        if company_suffix.search(clean) and not ignore.search(clean):
            candidates.append((i, clean))
        if supplier_anchor.search(clean):
            supplier_anchors.append(i)
        if customer_anchor.search(clean):
            customer_anchors.append(i)

    def proximity(idx: int, anchors: list[int], window: int = 8) -> int:
        return sum(1 for a in anchors if abs(idx - a) <= window)

    if candidates:
        if len(candidates) == 1:
            return _trim_to_company_name(candidates[0][1])

        # Score: +points near supplier anchors, -points near customer anchors
        best_name = ""
        best_score = -999
        for idx, name in candidates:
            score = proximity(idx, supplier_anchors) - proximity(idx, customer_anchors) * 2
            # Prefer candidates that appear EARLIER (letterhead position) as tiebreaker
            score -= idx * 0.01
            if score > best_score:
                best_score = score
                best_name = name
        return _trim_to_company_name(best_name)

    # Fallback: first non-ignored line with letters in first 20 lines
    for line in lines[:20]:
        clean = " ".join(line.split()).strip(":- ")
        if len(clean) < 3 or ignore.search(clean):
            continue
        if re.search(r"[A-Za-zÄÖÜäöüß]", clean):
            return _trim_to_company_name(clean)

    return ""


def detect_customer(text: str) -> str:
    return first_match([r"Kunde(?:nname)?\s*:?\s*(.+)", r"Rechnungsempf[aä]nger\s*:?\s*(.+)"], text)[:255]


def detect_customer_no(text: str) -> str:
    return first_match([r"Kundennummer\s*:?\s*([A-Z0-9._/-]+)", r"Kunden-Nr\.?\s*:?\s*([A-Z0-9._/-]+)"], text)[:50]


def detect_document_type(text: str, item_count: int) -> tuple[str, bool, list[str]]:
    normalized = normalize_text(text)
    notes = []
    is_invoice_keyword = "rechnung" in normalized or re.search(r"\b(?:re|rg|r)-", normalized) is not None
    unsafe_keywords = ["proforma", "angebot", "kostenvoranschlag", "bestellung", "auftragsbest"]
    if "proforma" in normalized or "pro-forma" in normalized:
        return "proforma", False, ["Proforma erkannt, keine echte Rechnung"]
    if "angebot" in normalized or "kostenvoranschlag" in normalized:
        return "angebot", False, ["Angebot/Kostenvoranschlag erkannt"]
    if "bestellung" in normalized or "auftragsbest" in normalized:
        return "bestellung", False, ["Bestellung/Auftragsbestaetigung erkannt"]
    if is_invoice_keyword and not any(keyword in normalized for keyword in unsafe_keywords) and item_count > 0:
        notes.append("Rechnungsschluesselwort und Positionen gefunden")
        return "rechnung", True, notes
    if item_count > 0:
        return "unknown", False, ["Positionen gefunden, Dokumenttyp aber nicht sicher Rechnung"]
    return "unknown", False, ["Keine Positionen und kein sicherer Dokumenttyp"]


def parse_decimal(value: str | Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(" ", "")
    match = re.search(r"-?\d+(?:[.,]\d+)?", text)
    if match:
        text = match.group(0)
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def valid_item(item: dict) -> bool:
    return bool(
        str(item.get("article_no") or "").strip()
        and str(item.get("article_name") or "").strip()
        and parse_decimal(item.get("quantity")) != 0
        and (parse_decimal(item.get("unit_price")) != 0 or parse_decimal(item.get("line_total")) != 0)
    )


def normalize_unit(value: str) -> str:
    raw_text = value or ""
    unit_match = re.search(r"\b(Stk?|Stück|PK|Paket|Packung|Pack|Kart(?:on)?|Kolli?|Kg|kg|KG|g|Gr|L|lt|Fl(?:asche)?|Dose)\b", raw_text, re.IGNORECASE)
    raw = (unit_match.group(1) if unit_match else raw_text).strip().casefold()
    mapping = {
        "pk": "KOL",
        "pak": "KOL",
        "paket": "KOL",
        "packung": "KOL",
        "pack": "KOL",
        "kart": "KOL",
        "karton": "KOL",
        "kolli": "KOL",
        "koll": "KOL",
        "ct": "KOL",
        "fl": "Fl",
        "flasche": "Fl",
        "flaschen": "Fl",
        "dose": "Dose",
        "dosen": "Dose",
        "st": "St",
        "stk": "St",
        "stück": "St",
        "kg": "Kg",
        "g": "St",
        "gr": "St",
    }
    if raw not in mapping and raw.replace(".", "").isdigit():
        return "St"
    return mapping.get(raw, raw_text[:4] if raw_text else "St")


def split_quantity_unit(value: str) -> tuple[Decimal, str]:
    text = " ".join((value or "").split())
    quantity = parse_decimal(text)
    unit_match = re.search(r"\b(Stk?\.?|Stueck|Stück|PK|Paket|Packung|Pack|Kart\.?|Karton|Kolli?|Kg|kg|KG|g|Gr)\b", text, re.IGNORECASE)
    unit = unit_match.group(1) if unit_match else text
    return quantity, normalize_unit(unit)


def invoice_base_unit(pdf_unit: str, article_name: str = "") -> str:
    raw = f"{pdf_unit or ''} {article_name or ''}".casefold()
    if "kg" in raw:
        return "Kg"
    if "kol" in raw or "kart" in raw or "pk" in raw or "pak" in raw:
        return "KOL"
    return normalize_unit(pdf_unit or "St")


def tax_from_cell(value: str) -> str:
    match = re.search(r"\d{1,2}(?:[,.]\d+)?", value or "")
    return match.group(0).replace(",", ".") if match else ""


def row_has_header(row: list[str]) -> bool:
    joined = normalize_text(" ".join(row))
    groups = [
        ("artikel", "artnr", "art nr", "pos"),
        ("beschreibung", "bezeichnung", "artikelname", "text"),
        ("menge", "qty", "anzahl"),
        ("einheit", "einh", "unit"),
        ("preis", "stpreis", "ep", "e preis"),
        ("betrag", "gesamt", "gpreis", "summe"),
    ]
    hits = sum(1 for group in groups if any(term in joined for term in group))
    return hits >= 4


def extract_from_tables(tables: list[list[list[str]]]) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    notes: list[str] = []
    for table_index, table in enumerate(tables, 1):
        header_index = None
        for index, row in enumerate(table):
            if row_has_header(row):
                header_index = index
                break
        if header_index is None:
            continue
        header = [normalize_text(cell) for cell in table[header_index]]
        notes.append(f"Tabelle {table_index}: Header erkannt: {table[header_index]}")
        for row in table[header_index + 1 :]:
            item = item_from_cells(header, row)
            if item and valid_item(item):
                items.append(item)
    return dedupe_items(items), notes


def column_index(header: list[str], terms: list[str], exclude_if: list[str] | None = None) -> int | None:
    for index, value in enumerate(header):
        if exclude_if and any(excl in value for excl in exclude_if):
            continue
        if any(term in value for term in terms):
            return index
    return None


def item_from_cells(header: list[str], row: list[str]) -> dict | None:
    # Use specific terms first; fall back to bare "nr." only when nothing else matches
    idx_article = column_index(header, ["artnr", "art nr", "artikel", "nummer", "ref"])
    if idx_article is None:
        idx_article = column_index(header, ["nr."])
    idx_name = column_index(header, ["beschreibung", "bezeichnung", "artikelname", "text"])
    idx_qty = column_index(header, ["menge", "qty", "anzahl"])
    idx_unit = column_index(header, ["einheit", "einh", "unit"])
    idx_stk_kg = column_index(header, ["stk/kg", "stk kg", "vpe", "stk", "kg"])
    idx_price = column_index(header, ["preis", "stpreis", "ep"], exclude_if=["letzte", "g."])
    # "kz" (Kennzeichen) is a tax-category code, not a percentage — excluded
    idx_tax = column_index(header, ["mwst", "tax", "ust"])
    idx_total = column_index(header, ["betrag", "gesamt", "summe", "gpreis", "g.preis", "g. preis", "g preis", "gesamtpreis", "total"])
    if idx_qty is None or idx_total is None:
        return None
    cells = row + [""] * 10
    article_no = cells[idx_article].strip() if idx_article is not None else ""
    article_name = cells[idx_name].strip() if idx_name is not None else " ".join(cell for cell in cells if cell).strip()
    carton_qty, pdf_unit = split_quantity_unit(cells[idx_qty])
    if idx_stk_kg is not None and parse_decimal(cells[idx_stk_kg]) != 0:
        stk_kg_value = parse_decimal(cells[idx_stk_kg])
        explicit_unit = cells[idx_unit].strip() if idx_unit is not None else ""
        base_unit = invoice_base_unit(explicit_unit or pdf_unit, article_name)
        if base_unit == "KOL":
            # Menge = cases ordered; VPE/Stk column = pieces per case
            quantity = carton_qty
            unit = "KOL"
            kolli = carton_qty
            inhalt = stk_kg_value
        else:
            # Stk/Kg column is the main quantity in base units
            quantity = stk_kg_value
            unit = base_unit
            kolli = carton_qty if "kart" in (cells[idx_qty] or "").casefold() else Decimal("0")
            inhalt = stk_kg_value
        tax_rate = tax_from_cell(cells[idx_tax]) if idx_tax is not None else ""
    else:
        quantity = carton_qty
        unit = normalize_unit(cells[idx_unit] if idx_unit is not None else pdf_unit)
        kolli = Decimal("0")
        inhalt = Decimal("0")
        tax_rate = tax_from_cell(cells[idx_tax]) if idx_tax is not None else ""
    total = parse_decimal(cells[idx_total])
    if quantity == 0 or not article_name or not article_no:
        return None
    return {
        "position_no": 0,
        "article_no": article_no[:50],
        "article_name": article_name[:255],
        "tax_rate": tax_rate,
        "kolli": kolli,
        "inhalt": inhalt,
        "quantity": quantity,
        "unit": unit,
        "price_kolli": Decimal("0"),
        "unit_price": parse_decimal(cells[idx_price] if idx_price is not None else "0"),
        "line_total": total,
        "raw_line": " | ".join(row),
    }


def extract_from_lines(lines: list[str]) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    notes: list[str] = []
    money = r"\d{1,3}(?:[.\s]\d{3})*[,.]\d{2,3}|\d+[,.]\d{2,3}"
    pattern = re.compile(
        rf"^\s*(?:(?P<pos>\d{{1,4}})\s+)?"
        rf"(?P<article>[A-Z0-9][A-Z0-9._/-]{{1,30}})\s+"
        rf"(?P<name>.+?)\s+"
        rf"(?P<qty>\d+(?:[,.]\d+)?)\s+"
        rf"(?P<unit>St|Stk|Stück|PK|Paket|Packung|Pack|Kart|Karton|Kolli?|Kg|kg|KG|g|Gr|L|lt|Fl|Flasche|Dose)\.?\s+"
        rf"(?:(?P<vpe>\d+(?:[,.]\d+)?)\s+)?"
        rf"(?:\d+\s+\w+\.?\s+)?"          # optional inhalt text field ("12 St.", "12 Kilo")
        rf"(?:\d{{1,3}}\s+)*"             # optional integer columns before price (pieces, tax codes)
        rf"(?P<price>{money})\s+"
        rf"(?:(?P<tax>\d{{1,3}})\s+)?"   # optional tax code integer before total
        rf"(?:\d{{1,3}}\s+)*"            # optional discount/extra integer columns
        rf"(?P<total>{money})"
        rf"(?:\s+\d{{1,3}})*"            # optional trailing integer columns
        rf"\s*$",
        re.IGNORECASE,
    )
    for raw_line in lines:
        line = " ".join(raw_line.split())
        if not line or row_has_header([line]):
            continue
        match = pattern.match(line)
        if not match:
            continue
        data = match.groupdict()
        name = (data["name"] or "").strip()
        if len(name) < 3:
            continue
        article = data["article"] or ""
        if article and article.isdigit() and len(article) <= 2 and not data["pos"]:
            data["pos"] = article
            article = ""
        item = {
            "position_no": int(data["pos"] or 0),
            "article_no": article[:50],
            "article_name": name[:255],
            "tax_rate": (data["tax"] or "").replace("%", ""),
            "kolli": Decimal("0"),
            "inhalt": parse_decimal(data["vpe"] or "0"),
            "quantity": parse_decimal(data["qty"]),
            "unit": normalize_unit(data["unit"] or ""),
            "price_kolli": Decimal("0"),
            "unit_price": parse_decimal(data["price"]),
            "line_total": parse_decimal(data["total"]),
            "raw_line": line,
        }
        if valid_item(item):
            items.append(item)
    if items:
        notes.append(f"{len(items)} Positionen per generischer Zeilenregex erkannt")
    return dedupe_items(items), notes


def dedupe_items(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        key = (item["article_no"], item["article_name"], str(item["quantity"]), str(item["line_total"]), item["raw_line"])
        if key in seen:
            continue
        seen.add(key)
        item = dict(item)
        item["position_no"] = int(item["position_no"] or len(result) + 1)
        result.append(item)
    return result


def extract_items(text: str, lines: list[str], tables: list[list[list[str]]]) -> tuple[list[dict], list[str]]:
    table_items, table_notes = extract_from_tables(tables)
    line_items, line_notes = extract_from_lines(text.splitlines() or lines)
    if len(table_items) >= len(line_items):
        return table_items, table_notes + [f"Tabellenparser gewaehlt ({len(table_items)} Positionen)"]
    return line_items, line_notes + [f"Zeilenparser gewaehlt ({len(line_items)} Positionen)"]


_TRANSPOSED_HEADERS: dict[int, list[str]] = {
    11: ["pos", "art nr", "bezeichnung", "ean", "inhalt", "kolli", "menge",
         "vk-preis", "kolli-preis", "mwst", "betrag"],
}


def _expand_transposed_table(rows: list[list[str | None]]) -> list[list[str | None]]:
    """Detect and expand tables where all item values are packed row-wise with newlines.
    This happens in some PDFs (e.g. SRGL/Hunkar) where pdfplumber puts all data in one row."""
    if len(rows) != 2:
        return rows
    data_row = rows[1]
    nl_cells = sum(1 for c in data_row if c and "\n" in c)
    if nl_cells < 3:
        return rows
    n_items = max((len(c.split("\n")) for c in data_row if c), default=0)
    if n_items <= 1:
        return rows
    n_cols = len(data_row)
    header = _TRANSPOSED_HEADERS.get(n_cols)
    if header is None:
        best_line = max((rows[0][0] or "").split("\n"), key=lambda l: len(l.split()), default="")
        tokens = best_line.split()
        while len(tokens) < n_cols:
            tokens.append("")
        header = tokens[:n_cols]
    proper_rows: list[list[str | None]] = [list(header)]
    for i in range(n_items):
        row: list[str | None] = []
        for cell in data_row:
            vals = (cell or "").split("\n")
            row.append(vals[i].strip() if i < len(vals) else "")
        proper_rows.append(row)
    return proper_rows


def tables_from_pdfplumber_find_tables(pdf_path: Path) -> tuple[list[list[list[str]]], list[str]]:
    tables: list[list[list[str]]] = []
    notes: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_number, page in enumerate(pdf.pages, 1):
                for table in page.find_tables() or []:
                    rows = table.extract()
                    raw_rows = [[(cell or "") for cell in row] for row in rows if row]
                    expanded = _expand_transposed_table(raw_rows)
                    cleaned = [[" ".join((cell or "").split()) for cell in row] for row in expanded]
                    if cleaned:
                        tables.append(cleaned)
                notes.append(f"pdfplumber.find_tables Seite {page_number} verarbeitet")
    except Exception as exc:
        notes.append(f"pdfplumber.find_tables fehlgeschlagen: {exc}")
    return tables, notes


def tables_from_camelot(pdf_path: Path) -> tuple[list[list[list[str]]], list[str]]:
    try:
        import camelot  # type: ignore
    except Exception as exc:
        return [], [f"Camelot nicht verfuegbar: {exc}"]
    tables: list[list[list[str]]] = []
    notes: list[str] = []
    for flavor in ("lattice", "stream"):
        try:
            found = camelot.read_pdf(str(pdf_path), pages="all", flavor=flavor)
            for table in found:
                rows = table.df.fillna("").astype(str).values.tolist()
                cleaned = [[" ".join(cell.split()) for cell in row] for row in rows]
                if cleaned:
                    tables.append(cleaned)
            notes.append(f"Camelot {flavor}: {len(found)} Tabellen")
        except Exception as exc:
            notes.append(f"Camelot {flavor} fehlgeschlagen: {exc}")
    return tables, notes


def tables_from_tabula(pdf_path: Path) -> tuple[list[list[list[str]]], list[str]]:
    try:
        import tabula  # type: ignore
    except Exception as exc:
        return [], [f"Tabula nicht verfuegbar: {exc}"]
    tables: list[list[list[str]]] = []
    notes: list[str] = []
    try:
        dfs = tabula.read_pdf(str(pdf_path), pages="all", multiple_tables=True)
        for df in dfs or []:
            rows = [list(map(str, df.columns.tolist()))]
            rows.extend(df.fillna("").astype(str).values.tolist())
            cleaned = [[" ".join(cell.split()) for cell in row] for row in rows]
            if cleaned:
                tables.append(cleaned)
        notes.append(f"Tabula: {len(tables)} Tabellen")
    except Exception as exc:
        notes.append(f"Tabula fehlgeschlagen: {exc}")
    return tables, notes


def extract_items_all_parsers(pdf_path: Path, text: str, lines: list[str], tables: list[list[list[str]]]) -> tuple[list[dict], str, list[str]]:
    results: list[tuple[str, list[dict], list[str]]] = []
    base_items, base_notes = extract_items(text, lines, tables)
    results.append(("pdfplumber.extract_tables+regex", base_items, base_notes))

    for parser_name, loader in (
        ("pdfplumber.find_tables", tables_from_pdfplumber_find_tables),
        ("camelot", tables_from_camelot),
        ("tabula", tables_from_tabula),
    ):
        parser_tables, parser_notes = loader(pdf_path)
        parser_items, parser_item_notes = extract_from_tables(parser_tables)
        results.append((parser_name, parser_items, parser_notes + parser_item_notes))

    best = max(results, key=lambda row: len(row[1]))
    notes: list[str] = []
    for parser_name, parser_items, parser_notes in results:
        notes.append(f"{parser_name}: {len(parser_items)} gueltige Positionen")
        notes.extend(parser_notes)
    notes.append(f"Positionsparser final: {best[0]}")
    return best[1], best[0], notes


def layout_signature(text: str, items: list[dict]) -> str:
    headers = []
    for line in text.splitlines():
        if row_has_header([line]):
            headers.append(normalize_text(line))
    seed = "|".join(headers[:3]) or "|".join(item["raw_line"] for item in items[:3])
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()


def duplicate_document(cursor, source_file: str, document_no: str) -> dict | None:
    return fetch_one(
        cursor,
        """
        SELECT d.id, COUNT(i.id) AS item_count
        FROM pdf_import_documents d
        LEFT JOIN pdf_import_items i ON i.document_id = d.id
        WHERE d.source_file = %s AND d.document_no = %s
        GROUP BY d.id
        LIMIT 1
        """,
        (source_file, document_no),
    )


def insert_item(cursor, document_id: int, item: dict, now: str) -> None:
    cursor.execute(
        """
        INSERT INTO pdf_import_items
          (document_id, position_no, article_no, article_name, tax_rate,
           kolli, inhalt, quantity, unit, price_kolli, unit_price,
           line_total, raw_line, created_at)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            document_id,
            item["position_no"],
            item["article_no"],
            item["article_name"],
            item["tax_rate"],
            item["kolli"],
            item["inhalt"],
            item["quantity"],
            item["unit"],
            item["price_kolli"],
            item["unit_price"],
            item["line_total"],
            item["raw_line"],
            now,
        ),
    )


def repair_duplicate_items(cursor, document_id: int, items: list[dict], notes: list[str]) -> int:
    inserted = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in items:
        existing = fetch_one(
            cursor,
            """
            SELECT id
            FROM pdf_import_items
            WHERE document_id = %s
              AND article_no = %s
              AND quantity = %s
              AND line_total = %s
            LIMIT 1
            """,
            (document_id, item["article_no"], item["quantity"], item["line_total"]),
        )
        if existing:
            continue
        insert_item(cursor, document_id, item, now)
        inserted += 1
    if inserted:
        notes.append(f"Duplikat repariert: {inserted} fehlende Positionen ergaenzt")
    return inserted


def insert_document(cursor, pdf_path: Path, header: dict, items: list[dict], raw_text: str, notes: list[str]) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO pdf_import_documents
          (source_file, document_type, document_no, document_date, supplier_name,
           customer_name, customer_no, delivery_address, raw_text, import_status, created_at,
           processing_notes, layout_signature, ocr_used, is_safe_invoice, is_austrian_supplier,
           supplier_address)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'staged', %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            pdf_path.name,
            header["document_type"],
            header["document_no"],
            parse_date(header["document_date_raw"]),
            header["supplier_name"],
            header["customer_name"],
            header["customer_no"],
            header["delivery_address"],
            raw_text,
            now,
            "\n".join(notes),
            header["layout_signature"],
            1 if header["ocr_used"] else 0,
            1 if header["is_safe_invoice"] else 0,
            1 if header.get("is_austrian_supplier") else 0,
            header.get("supplier_address") or "",
        ),
    )
    document_id = int(cursor.lastrowid)
    for item in items:
        insert_item(cursor, document_id, item, now)
    return document_id


def learn_layout(cursor, header: dict, items: list[dict], pdf_path: Path) -> None:
    if not header["supplier_name"] or not items:
        return
    columns = {
        "article_no": bool(any(item["article_no"] for item in items)),
        "article_name": True,
        "quantity": True,
        "unit": bool(any(item["unit"] for item in items)),
        "unit_price": bool(any(item["unit_price"] for item in items)),
        "line_total": bool(any(item["line_total"] for item in items)),
    }
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO pdf_import_vendor_layouts
          (supplier_name, document_type, layout_signature, columns_detected, line_pattern,
           sample_source_file, sample_document_no, confidence, created_at, updated_at)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          document_type = VALUES(document_type),
          columns_detected = VALUES(columns_detected),
          line_pattern = VALUES(line_pattern),
          sample_source_file = VALUES(sample_source_file),
          sample_document_no = VALUES(sample_document_no),
          confidence = VALUES(confidence),
          updated_at = VALUES(updated_at)
        """,
        (
            header["supplier_name"],
            header["document_type"],
            header["layout_signature"],
            json.dumps(columns, ensure_ascii=False),
            "generic-table-or-line-regex",
            pdf_path.name,
            header["document_no"],
            Decimal("0.8500") if len(items) >= MIN_POSITIONS_BEFORE_OCR else Decimal("0.6500"),
            now,
            now,
        ),
    )


def save_preisanfrage_fallback(cursor, document_id: int, header: dict, pdf_path: Path, items: list[dict], reason: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO pdf_import_preisanfragen
          (document_id, source_file, document_type, document_no, supplier_name, reason, item_count, created_at)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          document_type = VALUES(document_type),
          document_no = VALUES(document_no),
          supplier_name = VALUES(supplier_name),
          reason = VALUES(reason),
          item_count = VALUES(item_count)
        """,
        (
            document_id,
            pdf_path.name,
            header["document_type"],
            header["document_no"],
            header["supplier_name"],
            reason[:255],
            len(items),
            now,
        ),
    )


def write_errors(errors: list[dict]) -> None:
    fieldnames = ["timestamp", "source_file", "document_type", "document_no", "item_count", "error"]
    try:
        with ERROR_REPORT.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(errors)
    except OSError as exc:
        # Rapor dosyasi baska bir programda (orn. Excel) acik olabilir.
        # Import zaten tamamlandi (commit yapildi); rapor yazilamamasi
        # import'u geçersiz kilmamali, sadece uyari verip devam etmeli.
        logging.warning("Fehlerreport konnte nicht geschrieben werden (%s): %s", ERROR_REPORT, exc)
        for error in errors:
            logging.warning("Fehler: %s", error)


def write_pdf_report(results: list[dict]) -> None:
    fieldnames = [
        "timestamp",
        "source_file",
        "document_id",
        "document_type",
        "document_no",
        "supplier_name",
        "item_count",
        "extraction",
        "parser",
        "ocr_used",
        "status",
    ]
    try:
        with PDF_REPORT.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            for result in results:
                writer.writerow(
                    {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "source_file": result.get("source_file", ""),
                        "document_id": result.get("document_id", ""),
                        "document_type": result.get("document_type", ""),
                        "document_no": result.get("document_no", ""),
                        "supplier_name": result.get("supplier_name", ""),
                        "item_count": result.get("item_count", ""),
                        "extraction": result.get("extraction", ""),
                        "parser": result.get("parser", ""),
                        "ocr_used": "ja" if result.get("ocr_used") else "nein",
                        "status": result.get("status", ""),
                    }
                )
    except OSError as exc:
        # Rapor dosyasi baska bir programda (orn. Excel) acik olabilir.
        # Import zaten tamamlandi (commit yapildi); rapor yazilamamasi
        # import'u geçersiz kilmamali, sadece uyari verip devam etmeli.
        logging.warning("Import-Report konnte nicht geschrieben werden (%s): %s", PDF_REPORT, exc)


def move_pdf(pdf_path: Path, target_dir: Path) -> None:
    """Islenen PDF'i pdf_eingang'dan cikarip sonucuna gore pdf_importiert ya
    da pdf_fehler'e tasir - boylece pdf_eingang sadece henuz islenmemis
    PDF'leri icerir, ayni dosya tekrar tekrar islenmez."""
    target = target_dir / pdf_path.name
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = target_dir / f"{pdf_path.stem}_{stamp}{pdf_path.suffix}"
    try:
        shutil.move(str(pdf_path), str(target))
    except OSError as exc:
        logging.warning("PDF tasinamadi (%s -> %s): %s", pdf_path, target, exc)


def process_pdf(connection, pdf_path: Path) -> dict:
    logging.info("Starte Verarbeitung: %s", pdf_path.name)
    evaluated = [quality_for_candidate(pdf_path, candidate) for candidate in collect_text_candidates(pdf_path)]
    best_without_ocr = max(evaluated, key=lambda candidate: candidate["quality"]["score"])
    if best_without_ocr["quality"]["positions"] < MIN_POSITIONS_BEFORE_OCR:
        evaluated.extend(quality_for_candidate(pdf_path, candidate) for candidate in ocr_candidates(pdf_path))

    best = max(evaluated, key=lambda candidate: candidate["quality"]["score"])
    text = best["text"]
    lines = best["lines"]
    items = best["items"]
    ocr_used = bool(best["ocr_used"])
    notes: list[str] = []
    for candidate in evaluated:
        quality = candidate["quality"]
        notes.append(
            "Extraktion {method}: score={score}, chars={chars}, lines={lines}, "
            "positions={positions}, invoice_no={invoice_no_found}, date={date_found}, supplier={supplier_found}".format(
                method=candidate["method"],
                **quality,
            )
        )
        notes.extend(candidate.get("notes") or [])
    notes.extend(best.get("item_notes") or [])
    notes.append(f"Beste Extraktion: {best['method']}")
    notes.append(f"Verwendeter Positionsparser: {best['position_parser']}")

    document_type, is_safe_invoice, type_notes = detect_document_type(text, len(items))
    notes.extend(type_notes)
    if len(items) == 0:
        document_type = "unknown"
        notes.append("Keine Positionen gefunden: Fallback als unbekanntes Preisanfrage-Dokument im Staging")

    is_austrian_supplier = bool(re.search(r'\bATU\d{8}\b', text, re.IGNORECASE))
    supplier_name = best["supplier"] or ""
    supplier_address = duckduckgo_company_lookup(supplier_name) if supplier_name else ""
    if supplier_address:
        notes.append(f"Supplier address via web: {supplier_address[:120]}")
    header = {
        "document_type": document_type,
        "document_no": best["invoice_no"],
        "document_date_raw": best["date_raw"],
        "supplier_name": supplier_name,
        "customer_name": detect_customer(text),
        "customer_no": detect_customer_no(text),
        "delivery_address": "",
        "layout_signature": layout_signature(text, items),
        "ocr_used": ocr_used,
        "is_safe_invoice": is_safe_invoice,
        "is_austrian_supplier": is_austrian_supplier,
        "supplier_address": supplier_address,
    }
    notes.append(f"Lieferant erkannt: {header['supplier_name'] or 'nicht erkannt'}")
    notes.append(f"Belegnummer erkannt: {header['document_no']}")
    notes.append(f"Dokumenttyp: {document_type}, sichere Rechnung: {'ja' if is_safe_invoice else 'nein'}")

    with connection.cursor() as cursor:
        existing = duplicate_document(cursor, pdf_path.name, header["document_no"])
        if existing:
            added_items = 0
            if len(items) > int(existing.get("item_count") or 0):
                added_items = repair_duplicate_items(cursor, int(existing["id"]), items, notes)
            if not is_safe_invoice:
                save_preisanfrage_fallback(cursor, int(existing["id"]), header, pdf_path, items, "Dokument ist keine sichere Rechnung")
            notes.append(f"Duplikat bereits vorhanden: pdf_import_documents.id={existing['id']}")
            logging.info("%s: Duplikat, kein neuer Import", pdf_path.name)
            return {
                "source_file": pdf_path.name,
                "document_type": document_type,
                "document_no": header["document_no"],
                "supplier_name": header["supplier_name"],
                "item_count": len(items),
                "document_id": existing["id"],
                "status": "duplicate_repaired" if added_items else "duplicate",
                "parser": best["position_parser"],
                "extraction": best["method"],
                "ocr_used": ocr_used,
                "notes": notes,
            }
        document_id = insert_document(cursor, pdf_path, header, items, text, notes)
        learn_layout(cursor, header, items, pdf_path)
        if not is_safe_invoice:
            save_preisanfrage_fallback(cursor, document_id, header, pdf_path, items, "Dokument ist keine sichere Rechnung")

    logging.info("%s importiert: document_id=%s, type=%s, items=%s", pdf_path.name, document_id, document_type, len(items))
    return {
        "source_file": pdf_path.name,
        "document_type": document_type,
        "document_no": header["document_no"],
        "supplier_name": header["supplier_name"],
        "item_count": len(items),
        "document_id": document_id,
        "status": "imported",
        "parser": best["position_parser"],
        "extraction": best["method"],
        "ocr_used": ocr_used,
        "notes": notes,
    }


def analyze_pdf_preview(pdf_path: Path) -> dict:
    evaluated = [quality_for_candidate(pdf_path, candidate) for candidate in collect_text_candidates(pdf_path)]
    best_without_ocr = max(evaluated, key=lambda candidate: candidate["quality"]["score"])
    if best_without_ocr["quality"]["positions"] < MIN_POSITIONS_BEFORE_OCR:
        evaluated.extend(quality_for_candidate(pdf_path, candidate) for candidate in ocr_candidates(pdf_path))

    best = max(evaluated, key=lambda candidate: candidate["quality"]["score"])
    text = best["text"]
    lines = best["lines"]
    items = best["items"]
    document_type, is_safe_invoice, _type_notes = detect_document_type(text, len(items))
    if len(items) == 0:
        document_type = "unknown"
    return {
        "source_file": pdf_path.name,
        "supplier_name": best["supplier"],
        "document_no": best["invoice_no"],
        "document_date_raw": best["date_raw"],
        "document_type": document_type,
        "is_safe_invoice": is_safe_invoice,
        "item_count": len(items),
        "parser": best["position_parser"],
        "extraction": best["method"],
        "ocr_used": bool(best["ocr_used"]),
        "items": items,
        "quality": best["quality"],
    }


def product_mapping_status(config: dict[str, str], items: list[dict]) -> str:
    if not items:
        return "keine Positionen"
    try:
        connection = connect_db(config)
        try:
            with connection.cursor() as cursor:
                mapped = 0
                for item in items:
                    product = None
                    if item.get("article_no"):
                        product = fetch_one(cursor, "SELECT id FROM produits WHERE ref_prd = %s LIMIT 1", (item["article_no"],))
                    if not product and item.get("article_no"):
                        product = fetch_one(cursor, "SELECT id FROM produits WHERE ref_manufacturer = %s LIMIT 1", (item["article_no"],))
                    if product:
                        mapped += 1
                return f"{mapped}/{len(items)} per Referenz direkt zuordenbar"
        finally:
            connection.close()
    except Exception as exc:
        return f"nicht prüfbar: {exc}"


def preview_mode(config: dict[str, str], pdfs: list[Path]) -> int:
    print("AKEAD PDF Analyse-Vorschau")
    print("==========================")
    for pdf_path in pdfs:
        result = analyze_pdf_preview(pdf_path)
        print()
        print(f"PDF: {pdf_path.name}")
        print(f"Lieferant: {result['supplier_name'] or 'nicht erkannt'}")
        print(f"Belegnummer: {result['document_no'] or 'nicht erkannt'}")
        print(f"Datum: {result['document_date_raw'] or 'nicht erkannt'}")
        print(f"Dokumenttyp: {result['document_type']}")
        print(f"Sichere Rechnung: {'ja' if result['is_safe_invoice'] else 'nein'}")
        print(f"Erkannte Positionen: {result['item_count']}")
        print(f"Verwendete Textextraktion: {result['extraction']}")
        print(f"Verwendeter Parser: {result['parser']}")
        print(f"OCR verwendet: {'ja' if result['ocr_used'] else 'nein'}")
        print(f"Produkt-Mapping-Status: {product_mapping_status(config, result['items'])}")
        quality = result["quality"]
        print(
            "Qualität: chars={chars}, lines={lines}, positions={positions}, "
            "invoice_no={invoice_no_found}, date={date_found}, supplier={supplier_found}".format(**quality)
        )
    print()
    print("Nur Analyse. Es wurden keine Staging- oder AKEAD-Daten geschrieben.")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    setup_logging()
    PDF_INPUT_DIR.mkdir(exist_ok=True)
    PDF_IMPORTED_DIR.mkdir(exist_ok=True)
    PDF_ERROR_DIR.mkdir(exist_ok=True)
    errors: list[dict] = []
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        pdfs = sorted(PDF_INPUT_DIR.glob("*.pdf"))
        if not pdfs:
            print("Keine PDF-Dateien in pdf_eingang gefunden.")
            return 0

        if "--preview" in sys.argv:
            return preview_mode(config, pdfs)

        connection = connect_db(config)
        processed: list[tuple[Path, bool]] = []
        try:
            execute_create_tables(connection)
            results = []
            for pdf_path in pdfs:
                try:
                    result = process_pdf(connection, pdf_path)
                    results.append(result)
                    processed.append((pdf_path, True))
                except Exception as exc:
                    connection.rollback()
                    logging.exception("Fehler bei %s", pdf_path.name)
                    errors.append(
                        {
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "source_file": pdf_path.name,
                            "document_type": "unknown",
                            "document_no": "",
                            "item_count": 0,
                            "error": str(exc),
                        }
                    )
                    processed.append((pdf_path, False))
                    continue
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        # Commit basariyla tamamlandi - simdi PDF'leri sonuclarina gore tasi:
        # basarili olanlar pdf_importiert'e, hata alanlar pdf_fehler'e. Boylece
        # pdf_eingang sadece henuz islenmemis PDF'leri icerir.
        for pdf_path, success in processed:
            move_pdf(pdf_path, PDF_IMPORTED_DIR if success else PDF_ERROR_DIR)

        write_errors(errors)
        write_pdf_report(results)
        print(f"Nutze env-Datei: {env_file.name}")
        print(f"PDFs verarbeitet: {len(pdfs)}")
        for result in results:
            print(
                f"{result['source_file']}: {result['status']} | id={result['document_id']} | "
                f"type={result['document_type']} | no={result['document_no']} | positions={result['item_count']}"
            )
            for note in result["notes"]:
                print(f"  - {note}")
        if errors:
            print(f"Fehler: {len(errors)} siehe {ERROR_REPORT}")
        print(f"Log-Datei: {LOG_FILE}")
        print(f"Import-Report: {PDF_REPORT}")

        zero_item_results = [r for r in results if r.get("item_count", 0) == 0]
        if zero_item_results and not errors:
            for r in zero_item_results:
                print(
                    f"HATA: {r['source_file']} icin hic urun satiri cikartilamadi. "
                    "PDF'in metin tabanli oldugunu kontrol edin (taramali/gorsel PDF desteklenmeyebilir). "
                    "Bir sonraki adima gecmeden once bu sorunu cozun."
                )
            return 1
        return 0
    except Exception as exc:
        logging.exception("Auto-PDF-Import abgebrochen")
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

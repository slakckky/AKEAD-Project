from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sys

import pdfplumber
import pymysql


BASE_DIR = Path(__file__).resolve().parent
PDF_INPUT_DIR = BASE_DIR / "pdf_eingang"
DEBUG_TEXT_FILE = BASE_DIR / "debug_text.txt"
IMPORT_PLAN_FILE = BASE_DIR / "import_plan.md"
ENV_CANDIDATES = (
    BASE_DIR / ".env",
    BASE_DIR / "Textdokument.env",
)
DATABASE_NAME = "datenbank"
DESCRIBE_TABLES = (
    "invoices",
    "invoices_details",
    "produits",
    "tax_rates",
    "clients",
    "vendors",
)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Ungueltige Zeile {line_number} in {path.name}: {raw_line!r}")

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def find_env_file() -> Path:
    for path in ENV_CANDIDATES:
        if path.exists():
            return path

    names = ", ".join(path.name for path in ENV_CANDIDATES)
    raise FileNotFoundError(f"Keine env-Datei gefunden. Gesucht: {names}")


def find_first_pdf() -> Path:
    if not PDF_INPUT_DIR.exists():
        raise FileNotFoundError(f"PDF-Ordner nicht gefunden: {PDF_INPUT_DIR}")

    pdf_files = sorted(PDF_INPUT_DIR.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"Keine PDF-Datei in {PDF_INPUT_DIR} gefunden")

    return pdf_files[0]


def extract_pdf_text(pdf_path: Path) -> str:
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            text = repair_mojibake(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
            pages.append(f"--- Seite {page_number} ---\n{text}".strip())

    return "\n\n".join(pages).strip()


def repair_mojibake(text: str) -> str:
    if "Ã" not in text and "â" not in text:
        return text

    try:
        return text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text


def first_match(patterns: list[str], text: str, flags: int = re.IGNORECASE) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return " ".join(match.group(1).split())
    return None


def parse_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None

    normalized = value.strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def extract_invoice_header(text: str) -> dict[str, str | None]:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("--- Seite")
    ]

    supplier = first_match(
        [
            r"(?:Lieferant|Vendor|Supplier)\s*:?\s*(.+)",
            r"(?:Von|From)\s*:?\s*(.+)",
        ],
        text,
    )
    if not supplier and lines:
        supplier_parts = []
        for line in lines[:6]:
            if re.search(r"\b(?:Tel\.|Datum|AUFTRAG|Rechnung|Invoice)\b", line, re.IGNORECASE):
                break
            supplier_parts.append(line)
        supplier = " ".join(supplier_parts) if supplier_parts else lines[0]

    return {
        "lieferant": supplier,
        "rechnungsnummer": first_match(
            [
                r"(?:Rechnungs(?:nummer|nr\.?|-Nr\.?)|Invoice\s*(?:No\.?|Number))\s*:?\s*([A-Z0-9][A-Z0-9._/-]+)",
                r"\b(?:Rechnung|Invoice)\s+#?\s*([A-Z0-9][A-Z0-9._/-]+)",
                r"\b(B\d{6,})\b",
            ],
            text,
        ),
        "rechnungsdatum": first_match(
            [
                r"(?:Rechnungsdatum|Invoice\s*Date|Datum)\s*:?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
                r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{4})\b",
            ],
            text,
        ),
        "mwst": first_match(
            [
                r"(?:MwSt|USt|VAT|Tax)\s*:?\s*([0-9]{1,2}(?:[,.][0-9]+)?\s*%)",
                r"([0-9]{1,2}(?:[,.][0-9]+)?\s*%)\s*(?:MwSt|USt|VAT|Tax)",
                r"\bMwSt\s*\(([0-9]{1,2}(?:[,.][0-9]+)?%)\)",
            ],
            text,
        ),
        "gesamtbetrag": first_match(
            [
                r"(?:Gesamtbetrag|Gesamt|Total|Amount\s*Due)\s*:?\s*(?:EUR|€)?\s*([0-9][0-9.,]*)",
                r"(?:EUR|€)\s*([0-9][0-9.,]*)\s*(?:Gesamt|Total)",
                r"\bBrutto\s+([0-9][0-9.,]*)\s*€",
            ],
            text,
        ),
    }


def extract_items(text: str) -> list[dict[str, str | Decimal | None]]:
    items: list[dict[str, str | Decimal | None]] = []
    item_pattern = re.compile(
        r"^\s*(?P<pos>\d+)\s+"
        r"(?P<article>\d{4,})\s+"
        r"(?P<name>.+?)\s+"
        r"(?P<tax>\d{1,2}(?:[,.]\d+)?%)\s+"
        r"(?P<kolli>\d+(?:[,.]\d+)?)\s+"
        r"(?P<inhalt>\d+(?:[,.]\d+)?)\s+"
        r"(?P<quantity>\d+(?:[,.]\d+)?)\s+"
        r"(?P<unit>[A-Za-z]{1,5})\s+"
        r"(?P<price_kolli>\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2})\s+"
        r"(?P<unit_price>\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2})\s+"
        r"(?P<line_total>\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2})\s*$",
        re.IGNORECASE,
    )

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        match = item_pattern.match(line)
        if not match:
            continue

        items.append(
            {
                "artikelnummer": match.group("article"),
                "artikelname": match.group("name"),
                "menge": parse_decimal(match.group("quantity")),
                "einkaufspreis": parse_decimal(match.group("unit_price")),
                "mwst": match.group("tax"),
                "gesamtbetrag": parse_decimal(match.group("line_total")),
                "rohzeile": line,
            }
        )

    return items


def connect_db(config: dict[str, str]):
    database = config.get("DB_NAME", DATABASE_NAME)
    if database != DATABASE_NAME:
        raise ValueError(f"DB_NAME muss '{DATABASE_NAME}' sein, ist aber: {database!r}")

    return pymysql.connect(
        host=config["DB_HOST"],
        port=int(config.get("DB_PORT", "3306")),
        user=config["DB_USER"],
        password=config["DB_PASSWORD"],
        database=database,
        charset="utf8",
        cursorclass=pymysql.cursors.Cursor,
        connect_timeout=10,
        read_timeout=10,
        write_timeout=10,
    )


def describe_tables(connection) -> dict[str, list[dict[str, str | None]]]:
    schemas: dict[str, list[dict[str, str | None]]] = {}
    with connection.cursor() as cursor:
        for table in DESCRIBE_TABLES:
            cursor.execute(f"DESCRIBE `{table}`")
            rows = cursor.fetchall()
            schemas[table] = [
                {
                    "field": row[0],
                    "type": row[1],
                    "null": row[2],
                    "key": row[3],
                    "default": row[4],
                    "extra": row[5],
                }
                for row in rows
            ]
    return schemas


def schema_markdown(schemas: dict[str, list[dict[str, str | None]]]) -> str:
    parts = ["## Tabellenstruktur aus DESCRIBE", ""]
    for table, columns in schemas.items():
        parts.append(f"### {table}")
        parts.append("")
        parts.append("| Feld | Typ | Null | Key | Default | Extra |")
        parts.append("| --- | --- | --- | --- | --- | --- |")
        for column in columns:
            parts.append(
                "| {field} | {type} | {null} | {key} | {default} | {extra} |".format(
                    field=column["field"] or "",
                    type=column["type"] or "",
                    null=column["null"] or "",
                    key=column["key"] or "",
                    default="" if column["default"] is None else column["default"],
                    extra=column["extra"] or "",
                )
            )
        parts.append("")
    return "\n".join(parts)


def write_import_plan(
    pdf_path: Path,
    header: dict[str, str | None],
    items: list[dict[str, str | Decimal | None]],
    schemas: dict[str, list[dict[str, str | None]]],
) -> None:
    lines = [
        "# Import-Plan PDF-Rechnungen",
        "",
        "Status: Vorschau, noch kein Import. Das Skript fuehrt keine INSERT-, UPDATE- oder DELETE-Befehle aus.",
        "",
        f"Quelle: `{pdf_path.relative_to(BASE_DIR)}`",
        "",
        "## Erkannte Daten",
        "",
        f"- Lieferant: {header.get('lieferant') or 'nicht erkannt'}",
        f"- Rechnungsnummer: {header.get('rechnungsnummer') or 'nicht erkannt'}",
        f"- Rechnungsdatum: {header.get('rechnungsdatum') or 'nicht erkannt'}",
        f"- MwSt: {header.get('mwst') or 'nicht erkannt'}",
        f"- Gesamtbetrag: {header.get('gesamtbetrag') or 'nicht erkannt'}",
        f"- Positionen: {len(items)} erkannt",
        "",
        "## Moegliche spaetere Zuordnung",
        "",
        "- `vendors`: Lieferant suchen oder spaeter neu anlegen, wenn keine passende Vendor-ID existiert.",
        "- `invoices`: Rechnungsnummer, Rechnungsdatum, Lieferant/Vendor-ID, MwSt-/Steuerbezug und Gesamtbetrag speichern.",
        "- `invoices_details`: Jede erkannte Rechnungsposition mit Artikelnummer, Artikelname, Menge, Einkaufspreis und Positionsbetrag speichern.",
        "- `produits`: Artikelnummer/Artikelname gegen vorhandene Produkte abgleichen; spaeter ggf. Produkt-ID in `invoices_details` referenzieren.",
        "- `tax_rates`: Erkannte MwSt gegen vorhandene Steuersaetze abgleichen und spaeter die passende Steuer-ID verwenden.",
        "- `clients`: Nur verwenden, falls das bestehende Schema Rechnungen zwingend einem Client zuordnet.",
        "",
        "## Offene Punkte vor echtem Import",
        "",
        "- Pflichtfelder, Fremdschluessel und Default-Werte aus der Tabellenstruktur pruefen.",
        "- Eindeutigkeit der Rechnung klaeren, z. B. Vendor plus Rechnungsnummer.",
        "- Positionsparser an echte PDF-Layouts anpassen, falls Positionen nicht stabil erkannt werden.",
        "- Erst danach INSERT-Logik mit Transaktion und Dublettenpruefung ergaenzen.",
        "",
        schema_markdown(schemas),
    ]
    IMPORT_PLAN_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def print_preview(
    pdf_path: Path,
    header: dict[str, str | None],
    items: list[dict[str, str | Decimal | None]],
    schemas: dict[str, list[dict[str, str | None]]],
) -> None:
    print(f"PDF: {pdf_path}")
    print(f"Debug-Text: {DEBUG_TEXT_FILE}")
    print()
    print("Vorschau erkannte Rechnungsdaten:")
    print(f"  Lieferant: {header.get('lieferant') or 'nicht erkannt'}")
    print(f"  Rechnungsnummer: {header.get('rechnungsnummer') or 'nicht erkannt'}")
    print(f"  Rechnungsdatum: {header.get('rechnungsdatum') or 'nicht erkannt'}")
    print(f"  MwSt: {header.get('mwst') or 'nicht erkannt'}")
    print(f"  Gesamtbetrag: {header.get('gesamtbetrag') or 'nicht erkannt'}")
    print()
    print(f"Positionen: {len(items)} erkannt")
    for index, item in enumerate(items, 1):
        print(f"  Position {index}:")
        print(f"    Artikelnummer: {item.get('artikelnummer') or 'nicht erkannt'}")
        print(f"    Artikelname: {item.get('artikelname') or 'nicht erkannt'}")
        print(f"    Menge: {item.get('menge') if item.get('menge') is not None else 'nicht erkannt'}")
        print(f"    Einkaufspreis: {item.get('einkaufspreis') if item.get('einkaufspreis') is not None else 'nicht erkannt'}")
        print(f"    Gesamtbetrag: {item.get('gesamtbetrag') if item.get('gesamtbetrag') is not None else 'nicht erkannt'}")
        print(f"    Rohzeile: {item.get('rohzeile')}")
    print()
    print("DESCRIBE Tabellen:")
    for table, columns in schemas.items():
        print(f"  {table}: {len(columns)} Spalten")
    print()
    print(f"Import-Plan geschrieben: {IMPORT_PLAN_FILE}")


def main() -> int:
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        pdf_path = find_first_pdf()

        print(f"Nutze env-Datei: {env_file.name}")
        print("Nur Vorschau: keine INSERT-, UPDATE- oder DELETE-Befehle.")
        print()

        text = extract_pdf_text(pdf_path)
        DEBUG_TEXT_FILE.write_text(text + "\n", encoding="utf-8")

        header = extract_invoice_header(text)
        items = extract_items(text)

        connection = connect_db(config)
        try:
            schemas = describe_tables(connection)
        finally:
            connection.close()

        write_import_plan(pdf_path, header, items, schemas)
        print_preview(pdf_path, header, items, schemas)
        return 0

    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path
import csv
import re
import sys

import pdfplumber
import pymysql


BASE_DIR = Path(__file__).resolve().parent
PDF_INPUT_DIR = BASE_DIR / "pdf_eingang"
DEBUG_TEXT_FILE = BASE_DIR / "debug_text.txt"
PREVIEW_ITEMS_FILE = BASE_DIR / "preview_items.csv"
PREVIEW_SUMMARY_FILE = BASE_DIR / "preview_summary.txt"
BESTELLUNG_IMPORT_PLAN_FILE = BASE_DIR / "bestellung_import_plan.md"
ENV_CANDIDATES = (
    BASE_DIR / ".env",
    BASE_DIR / "Textdokument.env",
)
DATABASE_NAME = "datenbank"
ORDER_TABLE_KEYWORDS = (
    "order",
    "orders",
    "purchase",
    "command",
    "commande",
    "supplier",
    "vendor",
    "document",
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


def repair_mojibake(text: str) -> str:
    if "Ã" not in text and "â" not in text:
        return text

    try:
        return text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text


def extract_pdf_text(pdf_path: Path) -> str:
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            text = repair_mojibake(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
            pages.append(f"--- Seite {page_number} ---\n{text}".strip())

    return "\n\n".join(pages).strip()


def detect_document_type(text: str) -> str:
    normalized = text.casefold()
    if is_bursam_invoice(text):
        return "rechnung"
    if "auftragsbestätig".casefold() in normalized or "auftragsbest" in normalized or "bestellung" in normalized:
        return "bestellung"
    if "rechnung" in normalized:
        return "rechnung"
    return "unbekannt"


def is_bursam_invoice(text: str) -> bool:
    normalized = text.casefold()
    return (
        "bursam e.k." in normalized
        and "rechnung" in normalized
        and "rechnungsnr" in normalized
    )


def first_match(patterns: list[str], text: str, flags: int = re.IGNORECASE) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return " ".join(match.group(1).split())
    return None


def clean_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("--- Seite")
    ]


def extract_supplier(lines: list[str]) -> str | None:
    supplier_parts = []
    for line in lines[:8]:
        if re.search(r"(?:Tel\.|Datum|AUFTRAG|Bestellung|Rechnung)", line, re.IGNORECASE):
            break
        supplier_parts.append(line)
    return " ".join(supplier_parts) if supplier_parts else None


def extract_customer_name(text: str) -> str | None:
    lines = clean_lines(text)
    for index, line in enumerate(lines):
        if re.fullmatch(r"B\d{6,}", line) and index + 1 < len(lines):
            return lines[index + 1]
    return None


def extract_order_header(text: str) -> dict[str, str | None]:
    lines = clean_lines(text)
    return {
        "lieferant": extract_supplier(lines),
        "kundename": extract_customer_name(text),
        "lieferadresse": first_match([r"Lieferadresse\s*:\s*(.+)"], text),
        "belegnummer": first_match([r"\b(B\d{6,})\b"], text),
        "datum": first_match([r"Datum\s*:\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"], text),
        "kundennummer": first_match([r"Kundennummer\s*:\s*([A-Z0-9._/-]+)"], text),
    }


def extract_bursam_header(text: str) -> dict[str, str | None]:
    return {
        "lieferant": "Bursam e.K.",
        "kundename": "Ay Market GmbH",
        "lieferadresse": first_match([r"Ay Market GmbH.*?\n(?:.*\n){0,3}?(\d{4}\s+Linz)"], text),
        "belegnummer": first_match([r"Rechnungsnr\.\s*:\s*([A-Z0-9._/-]+)"], text),
        "datum": first_match([r"Rechnungsdatum\s*:\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"], text),
        "kundennummer": first_match([r"Kundennummer\s*:\s*([A-Z0-9._/-]+)"], text),
        "gesamtbetrag": first_match(
            [
                r"Rechnungsbetrag\s*\(EUR\)\s*:\s*([0-9][0-9.,]*)",
                r"Gesamtbetrag\s*\(EUR\)\s*:\s*([0-9][0-9.,]*)",
            ],
            text,
        ),
    }


def extract_order_items(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    item_pattern = re.compile(
        r"^\s*(?P<position>\d+)\s+"
        r"(?P<artikelnummer>\d{4,})\s+"
        r"(?P<artikelname>.+?)\s+"
        r"(?P<mwst>\d{1,2}(?:[,.]\d+)?%)\s+"
        r"(?P<kolli>\d+(?:[,.]\d+)?)\s+"
        r"(?P<inhalt>\d+(?:[,.]\d+)?)\s+"
        r"(?P<menge>\d+(?:[,.]\d+)?)\s+"
        r"(?P<einheit>[A-Za-z]{1,5})\s+"
        r"(?P<preis_kolli>\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2})\s+"
        r"(?P<preis_einheit>\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2})\s+"
        r"(?P<betrag>\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2})\s*$",
        re.IGNORECASE,
    )

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        match = item_pattern.match(line)
        if not match:
            continue

        item = match.groupdict()
        item["rohzeile"] = line
        items.append(item)

    return items


def extract_bursam_items(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    item_pattern = re.compile(
        r"^\s*(?P<position>\d+)\s+"
        r"(?P<artikelnummer>\d+)\s+"
        r"(?P<artikelname>.+?)\s+"
        r"(?:(?P<letzter_preis>\d+,\d{3})\s+)?"
        r"(?P<menge>\d+(?:[,.]\d+)?)\s+"
        r"(?P<einheit>PK)\s+"
        r"(?P<vpe>\d+(?:[,.]\d+)?)\s+"
        r"(?P<preis_einheit>\d+,\d{3})\s+"
        r"(?P<betrag>\d+,\d{3})\s+"
        r"(?P<mwst>\d+)\s*$",
        re.IGNORECASE,
    )

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        match = item_pattern.match(line)
        if not match:
            continue
        data = match.groupdict()
        items.append(
            {
                "position": data["position"],
                "artikelnummer": data["artikelnummer"],
                "artikelname": data["artikelname"].strip(),
                "mwst": data["mwst"] or "0",
                "kolli": data["menge"],
                "inhalt": data["vpe"],
                "menge": data["menge"],
                "einheit": data["einheit"].upper(),
                "preis_kolli": data["letzter_preis"] or "",
                "preis_einheit": data["preis_einheit"],
                "betrag": data["betrag"],
                "rohzeile": line,
            }
        )

    return items


def write_preview_items(items: list[dict[str, str]]) -> None:
    fieldnames = [
        "position",
        "artikelnummer",
        "artikelname",
        "mwst",
        "kolli",
        "inhalt",
        "menge",
        "einheit",
        "preis_kolli",
        "preis_einheit",
        "betrag",
        "rohzeile",
    ]
    with PREVIEW_ITEMS_FILE.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(items)


def write_preview_summary(
    pdf_path: Path,
    document_type: str,
    header: dict[str, str | None],
    items: list[dict[str, str]],
) -> None:
    lines = [
        f"PDF: {pdf_path}",
        f"document_type: {document_type}",
        "",
        "Erkannte Kopfdaten:",
        f"Lieferant: {header.get('lieferant') or 'nicht erkannt'}",
        f"Kundename: {header.get('kundename') or 'nicht erkannt'}",
        f"Lieferadresse: {header.get('lieferadresse') or 'nicht erkannt'}",
        f"Belegnummer: {header.get('belegnummer') or 'nicht erkannt'}",
        f"Datum: {header.get('datum') or 'nicht erkannt'}",
        f"Kundennummer: {header.get('kundennummer') or 'nicht erkannt'}",
        f"Gesamtbetrag: {header.get('gesamtbetrag') or 'nicht erkannt'}",
        "",
        f"Positionen: {len(items)}",
        "",
        "Hinweis: Nur Vorschau. Kein Import in MySQL.",
    ]
    PREVIEW_SUMMARY_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def show_tables(connection) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        return sorted(row[0] for row in cursor.fetchall())


def find_possible_order_tables(tables: list[str]) -> list[str]:
    candidates = []
    for table in tables:
        table_lower = table.lower()
        if any(keyword in table_lower for keyword in ORDER_TABLE_KEYWORDS):
            candidates.append(table)
    return candidates


def describe_tables(connection, tables: list[str]) -> dict[str, list[dict[str, str | None]]]:
    descriptions: dict[str, list[dict[str, str | None]]] = {}
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f"DESCRIBE `{table}`")
            descriptions[table] = [
                {
                    "field": row[0],
                    "type": row[1],
                    "null": row[2],
                    "key": row[3],
                    "default": row[4],
                    "extra": row[5],
                }
                for row in cursor.fetchall()
            ]
    return descriptions


def table_has_order_shape(columns: list[dict[str, str | None]]) -> bool:
    fields = {str(column["field"]).lower() for column in columns}
    has_doc_number = bool(fields & {"no_doc", "order_no", "order_number", "numero", "belegnummer"})
    has_date = bool(fields & {"dat_doc", "date", "order_date", "datum"})
    has_partner = bool(fields & {"id_vendor", "id_supplier", "supplier_id", "vendor_id", "id_clt"})
    return has_doc_number and has_date and has_partner


def write_bestellung_import_plan(
    document_type: str,
    tables: list[str],
    candidates: list[str],
    descriptions: dict[str, list[dict[str, str | None]]],
) -> None:
    safe_tables = [
        table
        for table, columns in descriptions.items()
        if table_has_order_shape(columns) and table.lower() not in {"vendors", "vendor", "suppliers", "supplier"}
    ]

    lines = [
        "# Import-Plan Bestellungen",
        "",
        "Status: Nur Analyse und Vorschau. Es wurden keine INSERT-, UPDATE- oder DELETE-Befehle ausgefuehrt.",
        "",
        f"Erkannter Dokumenttyp: `{document_type}`",
        "",
        "## Ergebnis",
        "",
    ]

    if document_type == "bestellung":
        lines.append("Das Dokument ist eine Bestellung/Auftragsbestaetigung und wird nicht in `invoices` importiert.")
    elif document_type == "rechnung":
        lines.append("Das Dokument wurde als Rechnung erkannt. Diese Datei behandelt hier nur die Vorschau.")
    else:
        lines.append("Der Dokumenttyp ist nicht sicher erkannt.")

    lines.extend(
        [
            "",
            "## Suche nach moeglichen Bestell-Tabellen",
            "",
            "Es wurde `SHOW TABLES` ausgefuehrt und nach diesen Namensbestandteilen gesucht:",
            ", ".join(f"`{keyword}`" for keyword in ORDER_TABLE_KEYWORDS),
            "",
            f"Anzahl Tabellen gesamt: {len(tables)}",
            f"Namens-Kandidaten: {', '.join(candidates) if candidates else 'keine'}",
            "",
        ]
    )

    if safe_tables:
        lines.append(f"Moegliche Bestell-Tabelle(n) nach Namens- und Spaltenpruefung: {', '.join(safe_tables)}")
        lines.append("Trotzdem ist vor einem Import eine fachliche Bestaetigung der Zieltabellen erforderlich.")
    else:
        lines.append("Keine sichere Bestell-Tabelle gefunden, deshalb kein Import.")

    lines.extend(["", "## Kandidaten-Struktur", ""])
    if descriptions:
        for table, columns in descriptions.items():
            lines.append(f"### {table}")
            lines.append("")
            lines.append("| Feld | Typ | Null | Key | Default | Extra |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for column in columns:
                default = "" if column["default"] is None else str(column["default"])
                lines.append(
                    f"| {column['field'] or ''} | {column['type'] or ''} | {column['null'] or ''} | "
                    f"{column['key'] or ''} | {default} | {column['extra'] or ''} |"
                )
            lines.append("")
    else:
        lines.append("Keine Tabellen mit passenden Namensbestandteilen gefunden.")
        lines.append("")

    BESTELLUNG_IMPORT_PLAN_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def print_preview(
    document_type: str,
    header: dict[str, str | None],
    items: list[dict[str, str]],
    candidates: list[str],
) -> None:
    print(f"document_type: {document_type}")
    print("Nur Vorschau: keine INSERT-, UPDATE- oder DELETE-Befehle.")
    print()
    print("Kopfdaten:")
    print(f"  Lieferant: {header.get('lieferant') or 'nicht erkannt'}")
    print(f"  Kundename: {header.get('kundename') or 'nicht erkannt'}")
    print(f"  Lieferadresse: {header.get('lieferadresse') or 'nicht erkannt'}")
    print(f"  Belegnummer: {header.get('belegnummer') or 'nicht erkannt'}")
    print(f"  Datum: {header.get('datum') or 'nicht erkannt'}")
    print(f"  Kundennummer: {header.get('kundennummer') or 'nicht erkannt'}")
    if header.get("gesamtbetrag"):
        print(f"  Gesamtbetrag: {header.get('gesamtbetrag')}")
    print()
    print(f"Positionen: {len(items)}")
    for item in items:
        print(
            "  {position}: {artikelnummer} | {artikelname} | MwSt {mwst} | "
            "Kolli {kolli} | Inhalt {inhalt} | Menge {menge} {einheit}".format(**item)
        )
    print()
    print(f"Moegliche Bestell-Tabellen laut Name: {', '.join(candidates) if candidates else 'keine'}")
    print(f"CSV: {PREVIEW_ITEMS_FILE}")
    print(f"Summary: {PREVIEW_SUMMARY_FILE}")
    print(f"Import-Plan: {BESTELLUNG_IMPORT_PLAN_FILE}")


def main() -> int:
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        pdf_path = find_first_pdf()

        text = extract_pdf_text(pdf_path)
        DEBUG_TEXT_FILE.write_text(text + "\n", encoding="utf-8")

        document_type = detect_document_type(text)
        if is_bursam_invoice(text):
            header = extract_bursam_header(text)
            items = extract_bursam_items(text)
        elif document_type == "bestellung":
            header = extract_order_header(text)
            items = extract_order_items(text)
        else:
            header = {}
            items = []

        if document_type in {"bestellung", "rechnung"}:
            write_preview_items(items)
            write_preview_summary(pdf_path, document_type, header, items)

        connection = connect_db(config)
        try:
            tables = show_tables(connection)
            candidates = find_possible_order_tables(tables)
            descriptions = describe_tables(connection, candidates)
        finally:
            connection.close()

        write_bestellung_import_plan(document_type, tables, candidates, descriptions)
        print(f"Nutze env-Datei: {env_file.name}")
        print(f"PDF: {pdf_path}")
        print_preview(document_type, header, items, candidates)
        return 0

    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

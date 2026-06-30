from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sys

import pymysql

from scan_invoice import scan_or_load


BASE_DIR = Path(__file__).resolve().parent
PDF_INPUT_DIR = BASE_DIR / "pdf_eingang"
EXTRACTED_DIR = BASE_DIR / "extracted"
CREATE_TABLES_SQL = BASE_DIR / "create_pdf_import_tables.sql"
ENV_CANDIDATES = (
    BASE_DIR / ".env",
    BASE_DIR / "Textdokument.env",
)
DATABASE_NAME = "datenbank"


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
    pdf_files = sorted(PDF_INPUT_DIR.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"Keine PDF-Datei in {PDF_INPUT_DIR} gefunden")
    return pdf_files[0]


def extract_pdf_text(pdf_path: Path) -> str:
    """PDF metnini dogrudan acmak yerine scan_invoice'in uretttigi/onbelleledigi
    JSON'dan okur (extracted/<isim>.json) - PDF sadece bir kere, scan_invoice
    tarafindan acilir; sonraki adimlar JSON'u paylasir."""
    result = scan_or_load(pdf_path, EXTRACTED_DIR)
    return result["full_text"]


def detect_document_type(text: str) -> str:
    normalized = text.casefold()
    if is_bursam_invoice(text):
        return "rechnung"
    if "auftragsbest" in normalized or "bestellung" in normalized:
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


def first_match(patterns: list[str], text: str, flags: int = re.IGNORECASE) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return " ".join(match.group(1).split())
    return ""


def clean_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("--- Seite")
    ]


def extract_supplier(lines: list[str]) -> str:
    supplier_parts = []
    for line in lines[:8]:
        if re.search(r"(?:Tel\.|Datum|AUFTRAG|Bestellung|Rechnung)", line, re.IGNORECASE):
            break
        supplier_parts.append(line)
    return " ".join(supplier_parts)


def extract_customer_name(text: str) -> str:
    lines = clean_lines(text)
    for index, line in enumerate(lines):
        if re.fullmatch(r"B\d{6,}", line) and index + 1 < len(lines):
            return lines[index + 1]
    return ""


def extract_header(text: str, document_type: str) -> dict[str, str]:
    if is_bursam_invoice(text):
        return {
            "document_type": document_type,
            "supplier_name": "Bursam e.K.",
            "customer_name": "Ay Market GmbH",
            "delivery_address": first_match([r"Ay Market GmbH.*?\n(?:.*\n){0,3}?(\d{4}\s+Linz)"], text),
            "document_no": first_match([r"Rechnungsnr\.\s*:\s*([A-Z0-9._/-]+)"], text),
            "document_date_raw": first_match([r"Rechnungsdatum\s*:\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"], text),
            "customer_no": first_match([r"Kundennummer\s*:\s*([A-Z0-9._/-]+)"], text),
            "total_amount": first_match(
                [
                    r"Rechnungsbetrag\s*\(EUR\)\s*:\s*([0-9][0-9.,]*)",
                    r"Gesamtbetrag\s*\(EUR\)\s*:\s*([0-9][0-9.,]*)",
                ],
                text,
            ),
        }

    lines = clean_lines(text)
    return {
        "document_type": document_type,
        "supplier_name": extract_supplier(lines),
        "customer_name": extract_customer_name(text),
        "delivery_address": first_match([r"Lieferadresse\s*:\s*(.+)"], text),
        "document_no": first_match(
            [
                r"\b(B\d{6,})\b",
                r"(?:Rechnungs(?:nummer|nr\.?|-Nr\.?)|Invoice\s*(?:No\.?|Number))\s*:?\s*([A-Z0-9][A-Z0-9._/-]+)",
            ],
            text,
        ),
        "document_date_raw": first_match(
            [
                r"Datum\s*:\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
                r"(?:Rechnungsdatum|Invoice\s*Date)\s*:?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            ],
            text,
        ),
        "customer_no": first_match([r"Kundennummer\s*:\s*([A-Z0-9._/-]+)"], text),
        "total_amount": "",
    }


def parse_decimal(value: str) -> Decimal:
    normalized = value.strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return Decimal("0")


def parse_date(value: str) -> str | None:
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%y", "%d-%m-%y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def extract_items(text: str) -> list[dict[str, object]]:
    if is_bursam_invoice(text):
        return extract_bursam_items(text)

    items: list[dict[str, object]] = []
    item_pattern = re.compile(
        r"^\s*(?P<position_no>\d+)\s+"
        r"(?P<article_no>\d{4,})\s+"
        r"(?P<article_name>.+?)\s+"
        r"(?P<tax_rate>\d{1,2}(?:[,.]\d+)?%)\s+"
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
        match = item_pattern.match(line)
        if not match:
            continue
        data = match.groupdict()
        items.append(
            {
                "position_no": int(data["position_no"]),
                "article_no": data["article_no"],
                "article_name": data["article_name"],
                "tax_rate": data["tax_rate"],
                "kolli": parse_decimal(data["kolli"]),
                "inhalt": parse_decimal(data["inhalt"]),
                "quantity": parse_decimal(data["quantity"]),
                "unit": data["unit"],
                "price_kolli": parse_decimal(data["price_kolli"]),
                "unit_price": parse_decimal(data["unit_price"]),
                "line_total": parse_decimal(data["line_total"]),
                "raw_line": line,
            }
        )
    return items


def extract_bursam_items(text: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    item_pattern = re.compile(
        r"^\s*(?P<position_no>\d+)\s+"
        r"(?P<article_no>\d+)\s+"
        r"(?P<article_name>.+?)\s+"
        r"(?:(?P<last_price>\d+,\d{3})\s+)?"
        r"(?P<quantity>\d+(?:[,.]\d+)?)\s+"
        r"(?P<unit>PK)\s+"
        r"(?P<vpe>\d+(?:[,.]\d+)?)\s+"
        r"(?P<unit_price>\d+,\d{3})\s+"
        r"(?P<line_total>\d+,\d{3})\s+"
        r"(?P<tax_rate>\d+)\s*$",
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
                "position_no": int(data["position_no"]),
                "article_no": data["article_no"],
                "article_name": data["article_name"].strip(),
                "tax_rate": data["tax_rate"] or "0",
                "kolli": parse_decimal(data["quantity"]),
                "inhalt": parse_decimal(data["vpe"]),
                "quantity": parse_decimal(data["quantity"]),
                "unit": data["unit"].upper(),
                "price_kolli": parse_decimal(data["last_price"] or "0"),
                "unit_price": parse_decimal(data["unit_price"]),
                "line_total": parse_decimal(data["line_total"]),
                "raw_line": line,
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
        autocommit=False,
        connect_timeout=10,
        read_timeout=10,
        write_timeout=10,
    )


def execute_create_tables(connection) -> None:
    sql = CREATE_TABLES_SQL.read_text(encoding="utf-8")
    statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


def find_existing_document(connection, source_file: str, document_no: str) -> tuple[int, int] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM pdf_import_documents
            WHERE source_file = %s AND document_no = %s
            LIMIT 1
            """,
            (source_file, document_no),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        document_id = int(row[0])
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM pdf_import_items
            WHERE document_id = %s
            """,
            (document_id,),
        )
        item_count = int(cursor.fetchone()[0])
        return document_id, item_count


def insert_staging_items(
    cursor,
    document_id: int,
    items: list[dict[str, object]],
    now: str,
) -> None:
    for item in items:
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


def insert_staging(
    connection,
    source_file: str,
    header: dict[str, str],
    items: list[dict[str, object]],
    raw_text: str,
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    document_date = parse_date(header["document_date_raw"])

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO pdf_import_documents
              (source_file, document_type, document_no, document_date, supplier_name,
               customer_name, customer_no, delivery_address, raw_text, import_status, created_at)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'staged', %s)
            """,
            (
                source_file,
                header["document_type"],
                header["document_no"],
                document_date,
                header["supplier_name"],
                header["customer_name"],
                header["customer_no"],
                header["delivery_address"],
                raw_text,
                now,
            ),
        )
        document_id = int(cursor.lastrowid)
        insert_staging_items(cursor, document_id, items, now)

    return document_id


def repair_empty_staging_document(
    connection,
    document_id: int,
    header: dict[str, str],
    items: list[dict[str, object]],
    raw_text: str,
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    document_date = parse_date(header["document_date_raw"])

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE pdf_import_documents
            SET document_type = %s,
                document_date = %s,
                supplier_name = %s,
                customer_name = %s,
                customer_no = %s,
                delivery_address = %s,
                raw_text = %s,
                import_status = 'staged'
            WHERE id = %s
            """,
            (
                header["document_type"],
                document_date,
                header["supplier_name"],
                header["customer_name"],
                header["customer_no"],
                header["delivery_address"],
                raw_text,
                document_id,
            ),
        )
        insert_staging_items(cursor, document_id, items, now)


def print_preview(pdf_path: Path, header: dict[str, str], items: list[dict[str, object]]) -> None:
    print("Staging-Vorschau")
    print("================")
    print(f"PDF: {pdf_path}")
    print(f"document_type: {header['document_type']}")
    print(f"document_no: {header['document_no'] or 'nicht erkannt'}")
    print(f"document_date: {header['document_date_raw'] or 'nicht erkannt'}")
    print(f"supplier_name: {header['supplier_name'] or 'nicht erkannt'}")
    print(f"customer_name: {header['customer_name'] or 'nicht erkannt'}")
    print(f"customer_no: {header['customer_no'] or 'nicht erkannt'}")
    print(f"delivery_address: {header['delivery_address'] or 'nicht erkannt'}")
    if header.get("total_amount"):
        print(f"total_amount: {header['total_amount']}")
    print(f"items: {len(items)}")
    print()
    for item in items:
        print(
            "{position_no}: {article_no} | {article_name} | MwSt {tax_rate} | "
            "Kolli {kolli} | Inhalt {inhalt} | Menge {quantity} {unit}".format(**item)
        )
    print()
    print("Zieltabellen bei Bestätigung:")
    print("  pdf_import_documents")
    print("  pdf_import_items")
    print("AKEAD-Haupttabellen werden nicht beschrieben.")


def print_example_selects() -> None:
    print()
    print("Beispiel-SELECTs fuer die Staging-Tabellen:")
    print("  SELECT id, source_file, document_type, document_no, document_date")
    print("  FROM pdf_import_documents")
    print("  ORDER BY id DESC")
    print("  LIMIT 10;")
    print()
    print("  SELECT document_id, position_no, article_no, article_name, tax_rate,")
    print("         kolli, inhalt, quantity, unit, price_kolli, unit_price, line_total")
    print("  FROM pdf_import_items")
    print("  WHERE document_id = <document_id>")
    print("  ORDER BY position_no;")


def main() -> int:
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        pdf_path = find_first_pdf()
        raw_text = extract_pdf_text(pdf_path)
        document_type = detect_document_type(raw_text)
        header = extract_header(raw_text, document_type)
        items = extract_items(raw_text)

        print(f"Nutze env-Datei: {env_file.name}")
        print_preview(pdf_path, header, items)

        confirmation = input("Import in Staging-Tabellen ausfuehren? Exakt JA eingeben: ").strip()
        if confirmation != "JA":
            print("Abgebrochen. Es wurde nichts importiert.")
            return 0

        source_file = pdf_path.name
        document_no = header["document_no"]
        if not document_no:
            raise ValueError("Keine Belegnummer erkannt. Import abgebrochen, um Dubletten zu vermeiden.")

        connection = connect_db(config)
        try:
            execute_create_tables(connection)
            existing_document = find_existing_document(connection, source_file, document_no)
            if existing_document is not None:
                existing_document_id, existing_item_count = existing_document
                if existing_item_count > 0:
                    connection.rollback()
                    print(f"Duplikat gefunden: source_file={source_file}, document_no={document_no}")
                    print(f"Vorhandener Staging-Datensatz: pdf_import_documents.id={existing_document_id}, Positionen={existing_item_count}")
                    print("Es wurde nichts importiert.")
                    return 1

                repair_empty_staging_document(connection, existing_document_id, header, items, raw_text)
                connection.commit()
                print(
                    "Unvollstaendiger Staging-Datensatz repariert. "
                    f"pdf_import_documents.id={existing_document_id}, Positionen={len(items)}"
                )
                print_example_selects()
                return 0

            document_id = insert_staging(connection, source_file, header, items, raw_text)
            connection.commit()
            print(f"Import abgeschlossen. pdf_import_documents.id={document_id}, Positionen={len(items)}")
            print_example_selects()
            return 0
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

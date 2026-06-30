from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
import subprocess
import sys

import pymysql


BASE_DIR = Path(__file__).resolve().parent
ENV_CANDIDATES = (BASE_DIR / ".env", BASE_DIR / "Textdokument.env")
ERROR_REPORT = BASE_DIR / "import_errors.csv"
DATABASE_NAME = "datenbank"
PYTHON = sys.executable

INVOICE_SAFE_TYPES = {"rechnung"}
ORDER_TYPES = {"bestellung"}
PREISANFRAGE_TYPES = {"proforma", "angebot"}
UNKNOWN_TYPES = {"unknown", "unbekannt", "parser_unsicher"}

ORDERS_MAPPING_SAFE = False
PREISANFRAGE_MAPPING_SAFE = False


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


def fetch_documents(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT d.id, d.source_file, d.document_type, d.document_no, d.document_date,
               d.supplier_name, d.customer_name, COUNT(i.id) AS item_count
        FROM pdf_import_documents d
        LEFT JOIN pdf_import_items i ON i.document_id = d.id
        GROUP BY d.id, d.source_file, d.document_type, d.document_no, d.document_date,
                 d.supplier_name, d.customer_name
        ORDER BY d.id
        """
    )
    return list(cursor.fetchall())


def error_row(document: dict, route: str, message: str) -> dict:
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "document_id": document.get("id", ""),
        "source_file": document.get("source_file", ""),
        "document_type": document.get("document_type", ""),
        "document_no": document.get("document_no", ""),
        "item_count": document.get("item_count", ""),
        "route": route,
        "error": message,
    }


def write_errors(errors: list[dict]) -> None:
    fieldnames = ["timestamp", "document_id", "source_file", "document_type", "document_no", "item_count", "route", "error"]
    with ERROR_REPORT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(errors)


def is_invoice_safe(document: dict) -> bool:
    document_type = (document.get("document_type") or "").strip().casefold()
    return document_type in INVOICE_SAFE_TYPES and int(document.get("item_count") or 0) > 0


def route_document(document: dict) -> tuple[str, str | None]:
    document_type = (document.get("document_type") or "").strip().casefold()
    item_count = int(document.get("item_count") or 0)

    if document_type in INVOICE_SAFE_TYPES:
        if is_invoice_safe(document):
            return "invoices", None
        return "error", "Rechnung ohne Positionen oder unsichere Rechnung, kein invoices-Import."

    if document_type in ORDER_TYPES:
        if not ORDERS_MAPPING_SAFE:
            return "error", "Bestellung erkannt, aber orders/Warenbestellung-Mapping ist nicht sicher."
        return "orders", None

    if document_type in PREISANFRAGE_TYPES:
        if item_count == 0:
            return "error", "Preisanfrage-Dokument ohne Positionen."
        if not PREISANFRAGE_MAPPING_SAFE:
            return "error", "Keine sichere Preisanfrage-Tabelle gefunden, deshalb kein Import."
        return "preisanfrage", None

    if document_type in UNKNOWN_TYPES or not document_type:
        if item_count == 0:
            return "error", "Unbekanntes Dokument ohne Positionen."
        if not PREISANFRAGE_MAPPING_SAFE:
            return "error", "Unbekanntes Dokument mit Positionen, aber keine sichere Preisanfrage-Tabelle gefunden."
        return "preisanfrage", None

    return "error", f"Nicht unterstützter document_type: {document.get('document_type')!r}"


def run_script(script_name: str) -> int:
    return subprocess.call([PYTHON, str(BASE_DIR / script_name)], cwd=str(BASE_DIR))


def main() -> int:
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        auto_stage_code = run_script("auto_pdf_import.py")
        if auto_stage_code != 0:
            raise ValueError(f"auto_pdf_import.py endete mit Exit-Code {auto_stage_code}")
        product_code = run_script("auto_product_match.py")
        if product_code != 0:
            raise ValueError(f"auto_product_match.py endete mit Exit-Code {product_code}")

        connection = connect_db(config)
        try:
            with connection.cursor() as cursor:
                documents = fetch_documents(cursor)
            connection.rollback()
        finally:
            connection.close()

        errors: list[dict] = []
        invoice_candidates = []
        preisanfrage_needed = False

        for document in documents:
            route, error = route_document(document)
            if error:
                errors.append(error_row(document, route, error))
                continue
            if route == "invoices":
                invoice_candidates.append(document)
            elif route == "preisanfrage":
                preisanfrage_needed = True
            elif route == "orders":
                errors.append(error_row(document, route, "orders-Import ist in auto_import_all.py noch gesperrt."))

        if invoice_candidates:
            errors.append(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "document_id": "",
                    "source_file": "",
                    "document_type": "rechnung",
                    "document_no": "",
                    "item_count": "",
                    "route": "invoices",
                    "error": "Rechnungs-Haupttabellenimport blockiert: Pflichtfeld-/Produktmapping ist noch nicht vollstaendig sicher automatisiert.",
                }
            )

        if preisanfrage_needed:
            run_script("import_to_preisanfrage.py")

        if not documents:
            errors.append(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "document_id": "",
                    "source_file": "",
                    "document_type": "",
                    "document_no": "",
                    "item_count": "",
                    "route": "none",
                    "error": "Keine Staging-Dokumente gefunden.",
                }
            )

        write_errors(errors)
        print(f"Nutze env-Datei: {env_file.name}")
        print(f"Staging-Dokumente geprüft: {len(documents)}")
        print(f"Fehler/Blocker: {len(errors)}")
        print(f"Fehlerreport: {ERROR_REPORT}")
        print("Keine automatischen AKEAD-Haupttabellenimporte ausgeführt.")
        return 0
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

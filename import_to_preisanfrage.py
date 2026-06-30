from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
import sys

import pymysql


BASE_DIR = Path(__file__).resolve().parent
ENV_CANDIDATES = (BASE_DIR / ".env", BASE_DIR / "Textdokument.env")
ERROR_REPORT = BASE_DIR / "import_errors.csv"
DATABASE_NAME = "datenbank"

ELIGIBLE_TYPES = {"proforma", "angebot", "unknown", "unbekannt", "parser_unsicher"}
MAPPING_SAFE = False
UNSAFE_MAPPING_REASON = "Keine sichere Preisanfrage-Tabelle gefunden, deshalb kein Import."


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


def fetch_all(cursor, sql: str, params: tuple = ()) -> list[dict]:
    cursor.execute(sql, params)
    return list(cursor.fetchall())


def load_candidate_documents(cursor) -> list[dict]:
    rows = fetch_all(
        cursor,
        """
        SELECT d.id, d.source_file, d.document_type, d.document_no, d.document_date,
               d.supplier_name, d.customer_name, COUNT(i.id) AS item_count
        FROM pdf_import_documents d
        LEFT JOIN pdf_import_items i ON i.document_id = d.id
        GROUP BY d.id, d.source_file, d.document_type, d.document_no, d.document_date,
                 d.supplier_name, d.customer_name
        ORDER BY d.id
        """,
    )
    candidates = []
    for row in rows:
        document_type = (row.get("document_type") or "").strip().casefold()
        if document_type in ELIGIBLE_TYPES:
            candidates.append(row)
    return candidates


def write_errors(errors: list[dict]) -> None:
    fieldnames = [
        "timestamp",
        "document_id",
        "source_file",
        "document_type",
        "document_no",
        "item_count",
        "error",
    ]
    with ERROR_REPORT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(errors)


def build_error(document: dict, message: str) -> dict:
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "document_id": document.get("id", ""),
        "source_file": document.get("source_file", ""),
        "document_type": document.get("document_type", ""),
        "document_no": document.get("document_no", ""),
        "item_count": document.get("item_count", ""),
        "error": message,
    }


def main() -> int:
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        connection = connect_db(config)
        try:
            with connection.cursor() as cursor:
                documents = load_candidate_documents(cursor)

            errors: list[dict] = []
            for document in documents:
                if int(document.get("item_count") or 0) == 0:
                    errors.append(build_error(document, "Keine Positionen erkannt, kein Preisanfrage-Import."))
                    continue
                if not MAPPING_SAFE:
                    errors.append(build_error(document, UNSAFE_MAPPING_REASON))
                    continue

                errors.append(build_error(document, "Interner Schutz: Mapping ist nicht implementiert."))

            if not documents:
                errors.append(
                    {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "document_id": "",
                        "source_file": "",
                        "document_type": "",
                        "document_no": "",
                        "item_count": "",
                        "error": "Keine geeigneten Fallback-Dokumente gefunden.",
                    }
                )

            write_errors(errors)
            connection.rollback()
            print(f"Nutze env-Datei: {env_file.name}")
            print("Preisanfrage-Fallback geprüft.")
            print(f"Geeignete Dokumente: {len(documents)}")
            print(f"Fehlerreport: {ERROR_REPORT}")
            print("Keine AKEAD-Haupttabellen beschrieben.")
            return 0
        finally:
            connection.close()
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

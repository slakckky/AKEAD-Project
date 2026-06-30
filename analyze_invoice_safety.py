from __future__ import annotations

from pathlib import Path
import sys

import pymysql


BASE_DIR = Path(__file__).resolve().parent
ENV_CANDIDATES = (BASE_DIR / ".env", BASE_DIR / "Textdokument.env")
OUTPUT_FILE = BASE_DIR / "invoice_mapping.md"
DATABASE_NAME = "datenbank"


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
    raise FileNotFoundError("Keine env-Datei gefunden")


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


def fetch_all(cursor, sql: str, params: tuple = ()) -> list[tuple]:
    cursor.execute(sql, params)
    return list(cursor.fetchall())


def table_exists(tables: set[str], name: str) -> bool:
    return name.lower() in {table.lower() for table in tables}


def find_tables(tables: set[str], keywords: tuple[str, ...]) -> list[str]:
    return sorted(table for table in tables if any(keyword in table.lower() for keyword in keywords))


def one_or_none(rows: list[tuple]) -> tuple | None:
    return rows[0] if len(rows) == 1 else None


def analyze() -> tuple[str, bool]:
    env_file = find_env_file()
    config = load_env(env_file)
    unsafe_fields: list[str] = []
    lines: list[str] = [
        "# Invoice Mapping Sicherheitsanalyse",
        "",
        "Status: Read-only Analyse. Es wurden keine Daten importiert.",
        "",
        "Erlaubte SQL-Arten fuer diese Analyse: `SHOW TABLES`, `DESCRIBE`, `SELECT`.",
        "",
        "## Ergebnis",
        "",
    ]

    connection = connect_db(config)
    try:
        with connection.cursor() as cursor:
            tables = {row[0] for row in fetch_all(cursor, "SHOW TABLES")}

            recent_invoices = fetch_all(
                cursor,
                """
                SELECT id, no_doc, sy_uk, id_org, id_dept, id_vendor, id_clt
                FROM invoices
                ORDER BY id DESC
                LIMIT 20
                """,
            )
            invoice_patterns = fetch_all(
                cursor,
                """
                SELECT no_doc, sy_uk
                FROM invoices
                WHERE no_doc <> '' AND sy_uk <> 0
                ORDER BY id DESC
                LIMIT 50
                """,
            )

            vendor_candidates = fetch_all(
                cursor,
                """
                SELECT id, code, nom, b_actif
                FROM vendors
                WHERE nom LIKE %s OR code LIKE %s
                """,
                ("%KAVAK%", "%KAVAK%"),
            )
            active_vendor_candidates = [row for row in vendor_candidates if row[3] == 1]

            client_candidates = fetch_all(
                cursor,
                """
                SELECT id, cod_clt, cod_clt_four, nom, b_actif
                FROM clients
                WHERE nom LIKE %s OR cod_clt = %s OR cod_clt_four = %s
                """,
                ("%AY Markt%", "227494", "227494"),
            )
            active_client_candidates = [row for row in client_candidates if row[4] == 1]

            stock_tables = find_tables(tables, ("stock", "stck"))
            org_tables = find_tables(tables, ("org",))
            dept_tables = find_tables(tables, ("dept", "department", "depart"))

            stock_candidates: list[tuple] = []
            for table in ("stocks", "stock", "stck"):
                if table_exists(tables, table):
                    try:
                        stock_candidates = fetch_all(cursor, f"SELECT * FROM `{table}` LIMIT 20")
                    except Exception:
                        stock_candidates = []
                    break

    finally:
        connection.close()

    # Conservative checks: these fields are unsafe unless the rule is provably met.
    unsafe_fields.append(
        "sy_uk: Aus vorhandenen `invoices` ist keine sichere Erzeugungsregel abgeleitet. "
        "Ein `MAX(sy_uk)+1` waere nicht ausreichend sicher."
    )
    unsafe_fields.append(
        "no_doc: Der Nummernkreis aus vorhandenen `invoices` wurde nicht als eindeutig freigegeben. "
        "Externe PDF-Belegnummern duerfen nicht automatisch als AKEAD-`no_doc` verwendet werden."
    )

    if not one_or_none(active_vendor_candidates):
        unsafe_fields.append(
            f"id_vendor: Lieferant `KAVAK` wurde nicht eindeutig als genau ein aktiver Vendor gefunden "
            f"(aktive Treffer: {len(active_vendor_candidates)}, Treffer gesamt: {len(vendor_candidates)})."
        )

    unsafe_fields.append(
        "id_clt: Die Bedeutung ist nicht eindeutig. Es ist nicht geklaert, ob PDF-Kundennummer/Kundename "
        "`clients.cod_clt`, `clients.cod_clt_four`, `clients.nom` oder eine andere Beziehung meint."
    )

    unsafe_fields.append(
        "id_org: Darf nur gesetzt werden, wenn genau ein passender aktiver Organisationsdatensatz fachlich "
        "bestimmt ist. Das ist aktuell nicht sicher."
    )
    unsafe_fields.append(
        "id_dept: Darf nur gesetzt werden, wenn genau ein passender aktiver Abteilungsdatensatz fachlich "
        "bestimmt ist. Das ist aktuell nicht sicher."
    )
    unsafe_fields.append(
        "id_stock: Darf nur gesetzt werden, wenn genau ein passender aktiver Lagerdatensatz bestimmt ist. "
        f"Moegliche Stock-Tabellen: {', '.join(stock_tables) if stock_tables else 'keine sicher erkannt'}."
    )

    lines.extend(
        [
            "IMPORT GESTOPPT, FELD UNSICHER",
            "",
            "Es wird kein Import in `invoices` oder `invoices_details` ausgefuehrt.",
            "Neue Daten duerfen automatisch nur in `pdf_import_` Tabellen gespeichert werden.",
            "",
            "## Unsichere Pflicht- und Systemfelder",
            "",
        ]
    )
    for field in unsafe_fields:
        lines.append(f"- {field}")

    lines.extend(
        [
            "",
            "## Read-only Befunde",
            "",
            f"- Env-Datei: `{env_file.name}`",
            f"- Letzte gelesene `invoices` Datensaetze: {len(recent_invoices)}",
            f"- Gelesene `no_doc`/`sy_uk` Muster aus `invoices`: {len(invoice_patterns)}",
            f"- Vendor-Kandidaten fuer `KAVAK`: {len(vendor_candidates)}",
            f"- Aktive Vendor-Kandidaten fuer `KAVAK`: {len(active_vendor_candidates)}",
            f"- Client-Kandidaten fuer `AY Markt`/`227494`: {len(client_candidates)}",
            f"- Aktive Client-Kandidaten: {len(active_client_candidates)}",
            f"- Organisationsnahe Tabellen: {', '.join(org_tables) if org_tables else 'keine'}",
            f"- Abteilungsnahe Tabellen: {', '.join(dept_tables) if dept_tables else 'keine'}",
            f"- Lagernahe Tabellen: {', '.join(stock_tables) if stock_tables else 'keine'}",
            f"- Stock-Kandidaten gelesen: {len(stock_candidates)}",
            "",
            "## Regeln fuer einen spaeteren AKEAD-Import",
            "",
            "- `sy_uk` nur erzeugen, wenn die AKEAD-Bildungsregel aus vorhandenen Daten eindeutig belegt ist.",
            "- `no_doc` nur setzen, wenn der Nummernkreis eindeutig bestimmt ist.",
            "- `id_org`, `id_dept` und `id_stock` nur setzen, wenn genau ein passender aktiver Datensatz existiert.",
            "- `id_vendor` nur setzen, wenn genau ein passender aktiver Vendor gefunden wird.",
            "- `id_clt` nur setzen, wenn die Bedeutung eindeutig geklaert ist.",
            "- Keine automatischen Neuanlagen in `vendors`, `clients`, `produits` oder Stock-Tabellen.",
            "- Schreiben in `invoices` und `invoices_details` erst, wenn alle Pflichtfelder sicher sind und exakt `JA` bestaetigt wurde.",
            "",
            "## Empfehlung",
            "",
            "Import in AKEAD-Haupttabellen nicht empfohlen. Aktuell ist nur der Staging-Import in `pdf_import_` Tabellen sicher.",
        ]
    )

    OUTPUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(OUTPUT_FILE), bool(unsafe_fields)


def main() -> int:
    try:
        output_file, has_unsafe_fields = analyze()
        if has_unsafe_fields:
            print("IMPORT GESTOPPT, FELD UNSICHER")
            print(f"Details: {output_file}")
            return 1
        print("Alle Pflichtfelder sicher. AKEAD-Import waere nach JA-Bestaetigung moeglich.")
        return 0
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

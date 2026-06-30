from pathlib import Path
import sys

import pymysql


ENV_CANDIDATES = (
    Path(__file__).with_name(".env"),
    Path(__file__).with_name("Textdokument.env"),
)
REQUIRED_TABLES = {"produits", "tickets", "invoices", "invoices_details"}


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f".env Datei nicht gefunden: {path}")

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
    raise FileNotFoundError(f"Keine .env Datei gefunden. Gesucht: {names}")


def main() -> int:
    env_file = find_env_file()

    try:
        config = load_env(env_file)

        host = config["DB_HOST"]
        port = int(config.get("DB_PORT", "3306"))
        database = config.get("DB_NAME", "datenbank")
        user = config["DB_USER"]
        password = config["DB_PASSWORD"]

        if database != "datenbank":
            raise ValueError(f"DB_NAME muss 'datenbank' sein, ist aber: {database!r}")

        print(f"Nutze env-Datei: {env_file.name}")
        print(f"Verbinde mit MySQL: host={host}, port={port}, database={database}, user={user}")

        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8",
            cursorclass=pymysql.cursors.Cursor,
            connect_timeout=10,
            read_timeout=10,
            write_timeout=10,
        )

        try:
            print("Verbindung erfolgreich.")
            with connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                tables = {row[0] for row in cursor.fetchall()}

            print()
            print("Gefundene Tabellen:")
            if tables:
                for table in sorted(tables):
                    print(f"  - {table}")
            else:
                print("  Keine Tabellen gefunden.")

            print()
            print("Pruefung erwarteter Tabellen:")
            missing = REQUIRED_TABLES - tables
            for table in sorted(REQUIRED_TABLES):
                status = "OK" if table in tables else "FEHLT"
                print(f"  {status}: {table}")

            if missing:
                print()
                print(f"Ergebnis: {len(missing)} Tabelle(n) fehlen.")
                return 1

            print()
            print("Ergebnis: Alle erwarteten Tabellen existieren.")
            return 0
        finally:
            connection.close()

    except KeyError as exc:
        print(f"Fehlender Eintrag in {env_file.name}: {exc.args[0]}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

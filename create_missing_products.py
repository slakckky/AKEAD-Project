from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json
import sys
import urllib.parse
import urllib.request

import pymysql


BASE_DIR = Path(__file__).resolve().parent
ENV_CANDIDATES = (BASE_DIR / ".env", BASE_DIR / "Textdokument.env")
REPORT_FILE = BASE_DIR / "product_creation_mapping.md"
DATABASE_NAME = "datenbank"
PDF_IMPORT_FAMILY_NAME = "PDF Import"
OPEN_FOOD_FACTS_AVAILABLE = True


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


def column_exists(cursor, table: str, column: str) -> bool:
    row = fetch_one(cursor, f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
    return row is not None


def ensure_product_id_column(cursor) -> None:
    if not column_exists(cursor, "pdf_import_items", "product_id"):
        cursor.execute("ALTER TABLE pdf_import_items ADD COLUMN product_id int(11) NOT NULL DEFAULT '0'")
        cursor.execute("ALTER TABLE pdf_import_items ADD KEY idx_pdf_import_items_product_id (product_id)")


def latest_product_template(cursor) -> dict:
    row = fetch_one(cursor, "SELECT * FROM produits ORDER BY id DESC LIMIT 1")
    if not row:
        raise ValueError("Keine Produktvorlage in produits gefunden.")
    return row


def family_template(cursor) -> dict:
    row = fetch_one(cursor, "SELECT * FROM familles_prds ORDER BY id DESC LIMIT 1")
    if not row:
        raise ValueError("Keine Artikelgruppen-Vorlage in familles_prds gefunden.")
    return row


def next_numeric_sy_uk(cursor, table: str) -> int:
    stats = fetch_one(
        cursor,
        f"SELECT COUNT(*) AS row_count, COUNT(DISTINCT sy_uk) AS distinct_count, MAX(sy_uk) AS max_sy_uk FROM `{table}`",
    )
    if not stats or stats["row_count"] == 0 or stats["max_sy_uk"] is None:
        raise ValueError(f"Kann sy_uk fuer {table} nicht erzeugen.")
    if stats["row_count"] != stats["distinct_count"]:
        raise ValueError(f"Kann sy_uk fuer {table} nicht erzeugen: Werte sind nicht eindeutig.")
    return int(stats["max_sy_uk"]) + 1


def next_family_code(cursor) -> str:
    rows = fetch_all(cursor, "SELECT cod_fam_prd FROM familles_prds")
    used = {row["cod_fam_prd"] for row in rows}
    for number in range(1, 1000):
        code = f"P{number:02d}" if number < 100 else f"{number:03d}"
        if code not in used:
            return code
    raise ValueError("Kein freier dreistelliger Familiencode gefunden.")


def find_pdf_import_family(cursor) -> dict | None:
    return fetch_one(cursor, "SELECT * FROM familles_prds WHERE lib = %s LIMIT 1", (PDF_IMPORT_FAMILY_NAME,))


def planned_pdf_import_family(cursor) -> dict:
    existing = find_pdf_import_family(cursor)
    if existing:
        return existing

    template = family_template(cursor)
    now = datetime.now().replace(microsecond=0)
    today = now.date()
    code = next_family_code(cursor)
    row = {key: value for key, value in template.items() if key != "id"}
    row.update(
        {
            "sy_uk": next_numeric_sy_uk(cursor, "familles_prds"),
            "cod_fam_prd": code,
            "cod_fam_prd_path": code,
            "lib": PDF_IMPORT_FAMILY_NAME,
            "lib_path": PDF_IMPORT_FAMILY_NAME,
            "unite": "St",
            "unite_contenu": "St",
            "usr_cre": "PDF_IMPORT",
            "dat_cre": today,
            "usr_upd": "PDF_IMPORT",
            "dat_upd": now,
        }
    )
    row["_needs_insert"] = True
    return row


def open_food_facts_barcode(article_name: str) -> tuple[str, str]:
    global OPEN_FOOD_FACTS_AVAILABLE
    if not OPEN_FOOD_FACTS_AVAILABLE:
        return "", "OpenFoodFacts nach vorherigem Fehler uebersprungen"

    query = urllib.parse.urlencode(
        {
            "search_terms": article_name,
            "search_simple": "1",
            "action": "process",
            "json": "1",
            "page_size": "3",
        }
    )
    url = f"https://world.openfoodfacts.org/cgi/search.pl?{query}"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "pdf-import-test/1.0"})
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        OPEN_FOOD_FACTS_AVAILABLE = False
        return "", f"Internet/OpenFoodFacts nicht verfuegbar: {exc}"

    products = payload.get("products") or []
    good_matches = []
    normalized_name = article_name.strip().lower()
    for product in products:
        code = str(product.get("code") or "").strip()
        product_name = str(product.get("product_name") or "").strip().lower()
        if not code or not product_name:
            continue
        if normalized_name in product_name or product_name in normalized_name:
            good_matches.append((code, product_name))

    if len(good_matches) == 1:
        return good_matches[0][0], "genau ein sicherer OpenFoodFacts-Treffer"
    if len(good_matches) > 1:
        return "", f"mehrere moegliche OpenFoodFacts-Treffer: {len(good_matches)}"
    return "", "kein sicherer OpenFoodFacts-Treffer"


def missing_items(cursor) -> list[dict]:
    items = fetch_all(
        cursor,
        """
        SELECT i.*
        FROM pdf_import_items i
        LEFT JOIN produits p_ref ON p_ref.ref_prd = i.article_no
        LEFT JOIN produits p_name ON p_name.lib_prd = i.article_name
        WHERE COALESCE(i.product_id, 0) = 0
          AND p_ref.id IS NULL
          AND p_name.id IS NULL
        ORDER BY i.document_id, i.position_no
        """,
    )
    return items


def update_existing_product_ids(cursor) -> int:
    if not column_exists(cursor, "pdf_import_items", "product_id"):
        return 0
    cursor.execute(
        """
        UPDATE pdf_import_items i
        INNER JOIN produits p ON p.ref_prd = i.article_no
        SET i.product_id = p.id
        WHERE i.product_id = 0
        """
    )
    return cursor.rowcount


def product_row(template: dict, item: dict, family: dict, sy_uk: int) -> dict:
    now = datetime.now().replace(microsecond=0)
    today = now.date()
    unit = (item["unit"] or "St")[:3]
    name = item["article_name"][:255]
    row = {key: value for key, value in template.items() if key != "id"}
    row.update(
        {
            "ref_prd": item["article_no"][:20],
            "typ_prd": 1,
            "lib_prd": name,
            "lib_prd_rtf": name,
            "lib_prd_html": None,
            "lib_ticket": name[:50],
            "lib_tech": None,
            "cod_fam_prd_path": family["cod_fam_prd_path"],
            "cod_grp_prd_path_1": "",
            "cod_grp_prd_path_2": "",
            "unite": unit,
            "packet_unit": unit,
            "packet_qty": Decimal("1"),
            "contenu": Decimal("0"),
            "unite_contenu": "",
            "id_stock": 1,
            "b_actif": 1,
            "sy_uk": sy_uk,
            "usr_cre": "PDF_IMPORT",
            "dat_cre": today,
            "usr_upd": "PDF_IMPORT",
            "dat_upd": now,
        }
    )
    return row


def barcode_row(product_id: int, barcode: str, unit: str) -> dict:
    now = datetime.now().replace(microsecond=0)
    today = now.date()
    return {
        "cod_barr": barcode,
        "id_prd": product_id,
        "unite": unit[:3],
        "sy_uk_var": 0,
        "id_taille": 0,
        "id_couleur": 0,
        "usr_cre": "PDF_IMPORT",
        "dat_cre": today,
        "usr_upd": "PDF_IMPORT",
        "dat_upd": now,
    }


def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, Decimal)):
        return str(value)
    if hasattr(value, "strftime"):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S" if hasattr(value, "hour") else "%Y-%m-%d") + "'"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def render_insert(table: str, row: dict) -> str:
    columns = [column for column in row.keys() if not column.startswith("_")]
    return "INSERT INTO `{}` ({}) VALUES ({});".format(
        table,
        ", ".join(f"`{column}`" for column in columns),
        ", ".join(sql_literal(row[column]) for column in columns),
    )


def insert_row(cursor, table: str, row: dict) -> int:
    clean_row = {key: value for key, value in row.items() if not key.startswith("_")}
    columns = list(clean_row.keys())
    cursor.execute(
        "INSERT INTO `{}` ({}) VALUES ({})".format(
            table,
            ", ".join(f"`{column}`" for column in columns),
            ", ".join(["%s"] * len(columns)),
        ),
        tuple(clean_row[column] for column in columns),
    )
    return int(cursor.lastrowid)


def prepare_plan(cursor) -> dict:
    has_product_id = column_exists(cursor, "pdf_import_items", "product_id")
    template = latest_product_template(cursor)
    family = planned_pdf_import_family(cursor)
    items = missing_items(cursor) if has_product_id else fetch_all(
        cursor,
        """
        SELECT i.*
        FROM pdf_import_items i
        LEFT JOIN produits p_ref ON p_ref.ref_prd = i.article_no
        LEFT JOIN produits p_name ON p_name.lib_prd = i.article_name
        WHERE p_ref.id IS NULL AND p_name.id IS NULL
        ORDER BY i.document_id, i.position_no
        """,
    )

    next_sy_uk = next_numeric_sy_uk(cursor, "produits")
    products = []
    for index, item in enumerate(items):
        barcode, barcode_note = open_food_facts_barcode(item["article_name"])
        products.append(
            {
                "item": item,
                "product": product_row(template, item, family, next_sy_uk + index),
                "barcode": barcode,
                "barcode_note": barcode_note,
            }
        )

    return {"has_product_id": has_product_id, "family": family, "products": products}


def write_report(plan: dict) -> None:
    lines = REPORT_FILE.read_text(encoding="utf-8").rstrip().splitlines() if REPORT_FILE.exists() else []
    lines.extend(
        [
            "",
            "## Aktueller DRY RUN",
            "",
            f"- `pdf_import_items.product_id` vorhanden: {'ja' if plan['has_product_id'] else 'nein, wird bei JA angelegt'}",
            f"- Artikelgruppe: `{plan['family']['lib']}` / `{plan['family']['cod_fam_prd_path']}`",
            f"- Neue Artikel geplant: {len(plan['products'])}",
            "",
            "| Referenz | Artikelbezeichnung | Einheit | Gruppe | Barcode | Hinweis |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for entry in plan["products"]:
        product = entry["product"]
        barcode = entry["barcode"] or ""
        lines.append(
            f"| {product['ref_prd']} | {product['lib_prd']} | {product['unite']} | "
            f"{product['cod_fam_prd_path']} | {barcode} | {entry['barcode_note']} |"
        )
    REPORT_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def print_dry_run(plan: dict) -> None:
    print("DRY RUN: fehlende Produkte anlegen")
    print("==================================")
    print(f"product_id-Spalte vorhanden: {'ja' if plan['has_product_id'] else 'nein, wird bei JA angelegt'}")
    if plan["family"].get("_needs_insert"):
        print("Geplante Artikelgruppe:")
        print(render_insert("familles_prds", plan["family"]))
    print(f"Neue Artikel geplant: {len(plan['products'])}")
    print()
    for entry in plan["products"]:
        product = entry["product"]
        print(f"- {product['lib_prd']} | Ref {product['ref_prd']} | Einheit {product['unite']} | Gruppe {product['cod_fam_prd_path']} | Barcode {'ja' if entry['barcode'] else 'nein'}")
        print(render_insert("produits", product))
        if entry["barcode"]:
            print("  codebarres INSERT geplant nach Produktanlage")
        print(f"  Barcode-Hinweis: {entry['barcode_note']}")
    print()
    print(f"Report: {REPORT_FILE}")


def execute_import(connection, plan: dict) -> None:
    with connection.cursor() as cursor:
        ensure_product_id_column(cursor)
        if plan["family"].get("_needs_insert"):
            family_id = insert_row(cursor, "familles_prds", plan["family"])
            plan["family"]["id"] = family_id

        for entry in plan["products"]:
            article_no = entry["product"]["ref_prd"]
            existing = fetch_one(cursor, "SELECT id FROM produits WHERE ref_prd = %s LIMIT 1", (article_no,))
            if existing:
                product_id = int(existing["id"])
            else:
                product_id = insert_row(cursor, "produits", entry["product"])
                if entry["barcode"]:
                    existing_barcode = fetch_one(cursor, "SELECT id FROM codebarres WHERE cod_barr = %s LIMIT 1", (entry["barcode"],))
                    if not existing_barcode:
                        insert_row(cursor, "codebarres", barcode_row(product_id, entry["barcode"], entry["product"]["unite"]))
            cursor.execute("UPDATE pdf_import_items SET product_id = %s WHERE article_no = %s", (product_id, article_no))

        update_existing_product_ids(cursor)
    connection.commit()


def main() -> int:
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        connection = connect_db(config)
        try:
            with connection.cursor() as cursor:
                plan = prepare_plan(cursor)
            write_report(plan)
            print(f"Nutze env-Datei: {env_file.name}")
            print_dry_run(plan)

            confirmation = input("Fehlende Produkte wirklich anlegen? Exakt JA eingeben: ").strip()
            if confirmation != "JA":
                connection.rollback()
                print("Abgebrochen. Keine Produkte angelegt.")
                return 0

            execute_import(connection, plan)
            print(f"Produktanlage abgeschlossen. Neue Artikel geplant/abgearbeitet: {len(plan['products'])}")
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

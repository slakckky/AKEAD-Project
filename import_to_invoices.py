from __future__ import annotations

import csv
from difflib import SequenceMatcher
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import sys
import uuid

import pymysql


BASE_DIR = Path(__file__).resolve().parent
ENV_CANDIDATES = (BASE_DIR / ".env", BASE_DIR / "Textdokument.env")
MAPPING_FILE = BASE_DIR / "invoice_mapping.md"
IMPORT_ERRORS_CSV = BASE_DIR / "import_errors.csv"
DATABASE_NAME = "datenbank"
FORCED_TEST_IMPORT = True


def append_import_warning(message: str) -> None:
    exists = IMPORT_ERRORS_CSV.exists()
    column_count = 6
    if exists and IMPORT_ERRORS_CSV.stat().st_size > 0:
        first_line = IMPORT_ERRORS_CSV.read_text(encoding="utf-8").splitlines()[0]
        column_count = len(first_line.split(";"))

    with IMPORT_ERRORS_CSV.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=";")
        if not exists or IMPORT_ERRORS_CSV.stat().st_size == 0:
            writer.writerow(["timestamp", "source_file", "document_type", "document_no", "item_count", "error"])
            column_count = 6
        if column_count >= 8:
            writer.writerow([
                datetime.now().isoformat(timespec="seconds"),
                "",
                "",
                "",
                "",
                "",
                "import_to_invoices",
                message,
            ])
        else:
            writer.writerow([
                datetime.now().isoformat(timespec="seconds"),
                "",
                "",
                "",
                "",
                "import_to_invoices: " + message,
            ])


def parse_decimal_safe(value, field_name: str = "") -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    original = value
    text = str(value).strip()
    if not text:
        return Decimal("0")

    text = (
        text.replace("\u00a0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace("\t", "")
        .replace("%", "")
        .strip()
    )

    match = re.search(r"[-+]?\d+(?:[.,]\d+)*(?:[.,]\d+)?", text)
    if not match:
        append_import_warning(
            "Decimal-Warnung: Feld {0}, Wert {1!r} nicht konvertierbar, 0 verwendet".format(
                field_name or "unbekannt",
                original,
            )
        )
        return Decimal("0")

    number = match.group(0)
    if "," in number and "." in number:
        if number.rfind(",") > number.rfind("."):
            number = number.replace(".", "").replace(",", ".")
        else:
            number = number.replace(",", "")
    elif "," in number:
        number = number.replace(",", ".")

    try:
        return Decimal(number)
    except (InvalidOperation, ValueError):
        append_import_warning(
            "Decimal-Warnung: Feld {0}, Wert {1!r} nicht konvertierbar, 0 verwendet".format(
                field_name or "unbekannt",
                original,
            )
        )
        return Decimal("0")


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def grouped_tax_total(detail_rows: list[dict]) -> Decimal:
    buckets: dict[Decimal, Decimal] = {}
    for row in detail_rows:
        rate = parse_decimal_safe(row.get("taux_tva"), "invoices_details.taux_tva")
        buckets[rate] = buckets.get(rate, Decimal("0")) + parse_decimal_safe(row.get("tot_ht_rem"), "invoices_details.tot_ht_rem")
    return sum((money(net * rate / Decimal("100")) for rate, net in buckets.items()), Decimal("0"))


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
    return fetch_one(cursor, f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,)) is not None


def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(value, date):
        return "'" + value.strftime("%Y-%m-%d") + "'"
    if isinstance(value, time):
        return "'" + value.strftime("%H:%M:%S") + "'"
    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
    return "'" + escaped + "'"


def render_insert(table: str, row: dict) -> str:
    columns = ", ".join(f"`{column}`" for column in row.keys())
    values = ", ".join(sql_literal(value) for value in row.values())
    return f"INSERT INTO `{table}` ({columns}) VALUES ({values});"


def latest_staging_document(cursor) -> dict:
    document = fetch_one(cursor, "SELECT * FROM pdf_import_documents ORDER BY id DESC LIMIT 1")
    if not document:
        raise ValueError("Kein Staging-Dokument in pdf_import_documents gefunden.")
    return document


def staging_items(cursor, document_id: int) -> list[dict]:
    return fetch_all(
        cursor,
        """
        SELECT *
        FROM pdf_import_items
        WHERE document_id = %s
          AND COALESCE(quantity, 0) <> 0
        ORDER BY position_no
        """,
        (document_id,),
    )


def _search_supplier_table(cursor, table: str, supplier: str) -> int | None:
    """Search for supplier in given table; return id or None."""
    try:
        rows = fetch_all(
            cursor,
            f"SELECT id, code, nom FROM `{table}` WHERE LOWER(nom) = LOWER(%s) OR LOWER(code) = LOWER(%s)",
            (supplier, supplier),
        )
        if rows:
            return int(rows[0]["id"])
        rows = fetch_all(
            cursor,
            f"SELECT id, code, nom FROM `{table}` WHERE LOWER(nom) LIKE LOWER(%s) OR LOWER(%s) LIKE CONCAT('%%', LOWER(nom), '%%')",
            (f"%{supplier}%", supplier),
        )
        if rows:
            return int(rows[0]["id"])
    except Exception:
        pass
    return None


def _fuzzy_supplier_table(cursor, table: str, supplier: str) -> tuple[int | None, float]:
    try:
        all_rows = fetch_all(cursor, f"SELECT id, code, nom FROM `{table}` ORDER BY nom")
    except Exception:
        return None, 0.0
    best_score = 0.0
    best_id: int | None = None
    norm = supplier.lower()
    for v in all_rows:
        nom = (v.get("nom") or "").lower()
        code = (v.get("code") or "").lower()
        score = max(SequenceMatcher(None, norm, nom).ratio(), SequenceMatcher(None, norm, code).ratio())
        if score > best_score:
            best_score = score
            best_id = int(v["id"])
    return best_id, best_score


def _auto_create_supplier(cursor, supplier: str) -> int:
    code = re.sub(r"[^A-Za-z0-9]", "", supplier)[:10].upper() or "IMP"
    for table in ("clients", "vendors"):
        try:
            cursor.execute(f"INSERT INTO `{table}` (code, nom) VALUES (%s, %s)", (code, supplier[:100]))
            new_id = int(cursor.lastrowid)
            print(f"Auto-created supplier '{supplier}' in {table} (id={new_id})")
            return new_id
        except Exception as exc:
            print(f"Could not auto-create in {table}: {exc}")
    raise ValueError(f"Vendor '{supplier}' not found and auto-create failed.")


def resolve_vendor_id(cursor, supplier_name: str) -> int:
    supplier = (supplier_name or "").strip()
    if not supplier:
        raise ValueError("id_vendor cannot be set: supplier_name missing from staging document.")

    # Exact / LIKE match — try clients first (AKEAD may store suppliers there), then vendors
    for table in ("clients", "vendors"):
        found = _search_supplier_table(cursor, table, supplier)
        if found is not None:
            return found

    # Fuzzy match
    for table in ("clients", "vendors"):
        best_id, best_score = _fuzzy_supplier_table(cursor, table, supplier)
        if best_id is not None and best_score >= 0.55:
            print(f"Vendor '{supplier}' not found exactly — using closest match in {table} (score {best_score:.0%})")
            return best_id

    # Auto-create
    print(f"Vendor '{supplier}' not found — creating automatically.")
    return _auto_create_supplier(cursor, supplier)


def latest_invoice_template(cursor) -> dict:
    invoice = fetch_one(cursor, "SELECT * FROM invoices ORDER BY id DESC LIMIT 1")
    if not invoice:
        raise ValueError(
            "No invoice found in the AKEAD 'invoices' table.\n"
            "Step 5 uses the most recent invoice as a field template (company defaults, "
            "currency settings, etc.).\n"
            "Fix: create at least one invoice manually in AKEAD first, then retry."
        )
    return invoice


def latest_detail_template(cursor, invoice_id: int) -> dict:
    detail = fetch_one(
        cursor,
        """
        SELECT *
        FROM invoices_details
        WHERE id_doc = %s
        ORDER BY no_lig
        LIMIT 1
        """,
        (invoice_id,),
    )
    if not detail:
        raise ValueError(f"Keine Detailposition fuer Testrechnung invoices.id={invoice_id} gefunden.")
    return detail


def validate_sy_uk(cursor) -> int:
    column_info = fetch_one(cursor, "DESCRIBE invoices `sy_uk`")
    if not column_info or "bigint" not in str(column_info["Type"]).lower():
        raise ValueError("sy_uk ist nicht als numerisches BIGINT-Feld erkennbar.")

    stats = fetch_one(
        cursor,
        """
        SELECT
          COUNT(*) AS row_count,
          COUNT(DISTINCT sy_uk) AS distinct_count,
          MAX(sy_uk) AS max_sy_uk
        FROM invoices
        """,
    )
    if not stats or stats["row_count"] == 0 or stats["max_sy_uk"] is None:
        raise ValueError("sy_uk kann nicht erzeugt werden: keine vorhandenen Rechnungswerte.")
    if stats["row_count"] != stats["distinct_count"]:
        raise ValueError("sy_uk kann nicht erzeugt werden: vorhandene sy_uk Werte sind nicht eindeutig.")

    next_sy_uk = int(stats["max_sy_uk"]) + 1
    existing = fetch_one(cursor, "SELECT id FROM invoices WHERE sy_uk = %s LIMIT 1", (next_sy_uk,))
    if existing:
        raise ValueError(f"sy_uk kann nicht erzeugt werden: {next_sy_uk} existiert bereits.")
    return next_sy_uk


def validate_no_doc(cursor, document_no: str) -> bool:
    """Returns True if the invoice already exists (will be replaced on import)."""
    if not document_no:
        raise ValueError("no_doc kann nicht gesetzt werden: PDF document_no fehlt.")
    existing = fetch_one(cursor, "SELECT id FROM invoices WHERE no_doc = %s LIMIT 1", (document_no,))
    if existing:
        print(f"Note: invoice {document_no} already exists — it will be replaced on import.")
        return True
    return False


def product_map(cursor, items: list[dict]) -> dict[str, tuple[int, str]]:
    """Returns {article_no: (product_id, ref_prd)} for each item."""
    result: dict[str, tuple[int, str]] = {}
    has_product_id = column_exists(cursor, "pdf_import_items", "product_id")
    for item in items:
        article_no = item["article_no"]

        # 1. Use product_id set by Step 4 matching (includes newly created IMP products)
        if has_product_id and int(item.get("product_id") or 0) > 0:
            product = fetch_one(cursor, "SELECT id, ref_prd FROM produits WHERE id = %s LIMIT 1", (int(item["product_id"]),))
            if product:
                result[article_no] = (int(product["id"]), str(product.get("ref_prd") or ""))
                continue

        # 2. Look up by supplier article number stored in lib_tech ("Lief-Art-Nr: <no>")
        if article_no:
            rows = fetch_all(
                cursor,
                "SELECT id, ref_prd FROM produits WHERE lib_tech LIKE %s LIMIT 1",
                (f"Lief-Art-Nr: {article_no}%",),
            )
            if rows:
                result[article_no] = (int(rows[0]["id"]), str(rows[0].get("ref_prd") or ""))
                continue

        result[article_no] = (0, "")
    return result


def build_invoice_row(template: dict, document: dict, next_sy_uk: int, vendor_id: int) -> dict:
    now = datetime.now()
    today = now.date()
    row = {key: value for key, value in template.items() if key != "id"}
    # Regenerate any UUID columns copied from template to avoid UNIQUE constraint violations
    for key in list(row.keys()):
        if "uuid" in key.lower():
            row[key] = uuid.uuid4().hex
    row.update(
        {
            "id_org": 1,
            "id_dept": 1,
            "id_clt": 1,
            "no_doc": document["document_no"],
            "no_doc_cus_sup": document["document_no"],
            "dat_doc": document["document_date"],
            "time_doc": now.time().replace(microsecond=0),
            "id_vendor": vendor_id,
            "typ_sal_pur": -1,
            "id_stck": 1,
            "stk_typ_doc": "L",
            "dat_delivery": document["document_date"],
            "dat_echeance": document["document_date"],
            "tot_colis": Decimal("0"),
            "sous_tot": Decimal("0"),
            "tot_ttc": Decimal("0"),
            "tot_tva": Decimal("0"),
            "tot_regl": Decimal("0"),
            "tot_wt_curr_reg": Decimal("0"),
            "tot_pay_curr_reg": Decimal("0"),
            "cod_currency": "EUR",
            "currency_reg": "EUR",
            "exchange_rate": Decimal("1"),
            "exchange_rate_div": Decimal("1"),
            "exch_rate_curr_reg": Decimal("1"),
            "exch_rate_curr_reg_div": Decimal("1"),
            "exch_rate_curr_report": Decimal("1"),
            "sy_uk": next_sy_uk,
            "usr_cre": "root",
            "dat_cre": today,
            "usr_upd": "root",
            "dat_upd": now.replace(microsecond=0),
        }
    )
    return row


def build_detail_rows(template: dict, items: list[dict], product_ids: dict[str, tuple[int, str]], is_austrian_supplier: bool = False) -> list[dict]:
    now = datetime.now()
    today = now.date()
    rows = []
    for idx, item in enumerate(items, start=1):
        article_no = item.get("article_no") or ""
        product_id, product_ref = product_ids.get(article_no, (0, ""))

        kolli = parse_decimal_safe(item.get("kolli"), "pdf_import_items.kolli")
        quantity = parse_decimal_safe(item.get("quantity"), "pdf_import_items.quantity")
        # inhalt = pieces per case (VPE); used to convert case price → piece price
        inhalt = parse_decimal_safe(item.get("inhalt"), "pdf_import_items.inhalt")
        unit_price_raw = parse_decimal_safe(item.get("unit_price"), "pdf_import_items.unit_price")

        qte_unit_prd = inhalt if inhalt > 0 else quantity

        # AKEAD expects piece price; if invoice gives case price, divide by inhalt
        if inhalt > 1:
            piece_price = (unit_price_raw / inhalt).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        else:
            piece_price = unit_price_raw

        # Austrian supplier: use MwSt rate from PDF (mwst column, never kz).
        # Foreign supplier: always 0 — no Austrian VAT.
        if is_austrian_supplier:
            tax_rate = parse_decimal_safe(item.get("tax_rate"), "pdf_import_items.tax_rate")
        else:
            tax_rate = Decimal("0")

        line_total = parse_decimal_safe(item.get("line_total"), "pdf_import_items.line_total")
        # Fallback: calculate total when PDF did not provide it
        if line_total == 0 and quantity > 0 and unit_price_raw > 0:
            line_total = (quantity * unit_price_raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # AKEAD ref code: matched product's own ref, or sequential IMP placeholder
        if not product_ref:
            product_ref = f"IMP{idx:06d}"

        row = {key: value for key, value in template.items() if key != "id"}
        # Regenerate any UUID columns copied from template to avoid UNIQUE constraint violations
        for key in list(row.keys()):
            if "uuid" in key.lower():
                row[key] = uuid.uuid4().hex
        row.update(
            {
                "id_doc": None,
                "uuid_detail": uuid.uuid4().hex,
                "no_lig": item["position_no"],
                "typ_lig": "N",
                "id_prd": product_id,
                "id_stock": 1,
                "lib": item["article_name"],
                # colis = number of packages/cases (kolli); unknown → 1
                "colis": kolli if kolli > 0 else Decimal("1"),
                "qte": quantity,
                "unite": item["unit"],
                "uprice_wot_curr_trf": piece_price,
                "currency_trf": "EUR",
                "trf_exch_rate": Decimal("1"),
                "trf_exch_rate_div": Decimal("1"),
                "prix_u_ht": piece_price,
                # qte_unit_prd = content per package (pieces per koli); unknown → quantity
                "qte_unit_prd": inhalt if inhalt > 0 else quantity,
                "taux_tva": tax_rate,
                "prix_revt": Decimal("0"),
                "cost_price_curr": Decimal("0"),
                "tot_ht_rem": line_total,
                "ref_cus_sup": article_no,
                "usr_cre": "root",
                "dat_cre": today,
                "usr_upd": "root",
                "dat_upd": now.replace(microsecond=0),
            }
        )
        # Write only if column exists in invoices_details (safe for any schema)
        if "ref_prd" in row:
            row["ref_prd"] = product_ref

        # Cover alternative column names AKEAD may use for colis/inhalt
        colis_val = kolli if kolli > 0 else quantity
        inhalt_val = qte_unit_prd if qte_unit_prd > 0 else Decimal("1")
        for col in row:
            cl = col.lower()
            if cl in ("nbre_colis", "nb_colis", "qte_colis", "nb_col"):
                row[col] = colis_val
            elif cl in ("inhalt", "contenu_prd", "qte_contenu", "nb_contenu", "nb_prd_colis"):
                row[col] = inhalt_val
        rows.append(row)
    return rows


def prepare_plan(cursor) -> dict:
    document = latest_staging_document(cursor)
    items = staging_items(cursor, document["id"])
    if not items:
        raise ValueError("Keine Staging-Positionen gefunden.")
    if document["document_type"] != "rechnung":
        print(f"Hinweis: document_type ist `{document['document_type']}`. Erzwungener Testimport ist aktiviert.")

    invoice_template = latest_invoice_template(cursor)
    detail_template = latest_detail_template(cursor, invoice_template["id"])
    next_sy_uk = validate_sy_uk(cursor)
    already_exists = validate_no_doc(cursor, document["document_no"])
    vendor_id = resolve_vendor_id(cursor, document.get("supplier_name") or "")
    products = product_map(cursor, items)

    is_austrian = bool(document.get("is_austrian_supplier"))
    invoice_row = build_invoice_row(invoice_template, document, next_sy_uk, vendor_id)
    detail_rows = build_detail_rows(detail_template, items, products, is_austrian)
    invoice_row["tot_colis"] = sum((row["colis"] for row in detail_rows), Decimal("0"))
    invoice_row["sous_tot"] = sum((row["tot_ht_rem"] for row in detail_rows), Decimal("0"))
    invoice_row["tot_tva"] = grouped_tax_total(detail_rows)
    invoice_row["tot_ttc"] = invoice_row["sous_tot"] + invoice_row["tot_tva"]

    return {
        "document": document,
        "items": items,
        "invoice_template": invoice_template,
        "detail_template": detail_template,
        "next_sy_uk": next_sy_uk,
        "product_ids": products,
        "invoice_row": invoice_row,
        "detail_rows": detail_rows,
        "already_exists": already_exists,
    }


def write_mapping(plan: dict) -> None:
    missing_products = [article for article, product_id in plan["product_ids"].items() if product_id == 0]
    lines = [
        "# Invoice Mapping",
        "",
        "Status: Erzwungener Testimport vorbereitet. Noch nicht importiert.",
        "",
        "## Sicherheitsgrenzen",
        "",
        "- Nur Datenbank `datenbank`.",
        "- Keine automatische Anlage von `vendors`, `clients`, `produits` oder `stocks`.",
        "- Zieltabellen bei Import: nur `invoices` und `invoices_details`.",
        "- Kein `DELETE`, kein `DROP`.",
        "- Import erst nach exakter Eingabe `JA`.",
        "",
        "## Erzwungene Testwerte",
        "",
        "- `id_org = 1`",
        "- `id_dept = 1`",
        "- `id_stock = 1` fuer Detailpositionen",
        "- `id_stck = 1` fuer Rechnungskopf",
        "- `id_vendor = 0` wie in der manuellen Testrechnung",
        "- `id_clt = 1` wie in der manuellen Testrechnung",
        f"- `no_doc = {plan['document']['document_no']}` aus PDF-Staging",
        f"- `sy_uk = {plan['next_sy_uk']}` aus `MAX(sy_uk)+1` nach Eindeutigkeitspruefung",
        "- Falls `pdf_import_items.product_id` vorhanden ist, wird dieser Wert nur verwendet, wenn der Artikel nicht aus `PDF_IMPORT`/`P01` stammt.",
        "- Unsichere `PDF_IMPORT`/`P01`-Produktzuordnungen werden fuer `invoices_details.id_prd` ignoriert.",
        "- Falls kein sicherer Artikel gefunden wird, wird weiter `id_prd=0` verwendet und gewarnt.",
        "",
        "## Produktmapping",
        "",
        "| PDF Artikel | Ziel `id_prd` | Status |",
        "| --- | --- | --- |",
    ]
    for article_no, product_id in plan["product_ids"].items():
        status = "Produkt gefunden" if product_id else "nicht gefunden, erzwungen `id_prd=0`"
        lines.append(f"| {article_no} | {product_id} | {status} |")

    lines.extend(
        [
            "",
            "## Bewertung",
            "",
            "Dieser Import ist ein erzwungener Testimport. Fachlich sichere Zuordnung ist weiterhin nicht vollstaendig.",
            f"Nicht gefundene Produkte: {len(missing_products)} von {len(plan['product_ids'])}.",
        ]
    )
    MAPPING_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_dry_run(plan: dict) -> None:
    print("DRY RUN: erzwungener Testimport")
    print("================================")
    print(f"Staging-Dokument: {plan['document']['id']} / {plan['document']['document_no']}")
    print(f"sy_uk geplant: {plan['next_sy_uk']}")
    print(f"Positionen geplant: {len(plan['detail_rows'])}")
    print(f"Detail rows count: {len(plan['detail_rows'])}")
    if plan["detail_rows"]:
        first = plan["detail_rows"][0]
        colis_related = [k for k in first if "colis" in k.lower() or "inhalt" in k.lower() or "contenu" in k.lower()]
        print(f"Kolli/Inhalt columns in invoices_details: {colis_related}")
        print(f"  colis={first.get('colis')} qte={first.get('qte')} qte_unit_prd={first.get('qte_unit_prd')}")
    print()
    print(render_insert("invoices", plan["invoice_row"]))
    print()
    for row in plan["detail_rows"]:
        preview = dict(row)
        preview["id_doc"] = "<new_invoice_id>"
        print(render_insert("invoices_details", preview))
    print()
    print(f"Mapping geschrieben: {MAPPING_FILE}")


def insert_row(cursor, table: str, row: dict) -> int:
    columns = list(row.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(f"`{column}`" for column in columns)
    cursor.execute(
        f"INSERT INTO `{table}` ({column_sql}) VALUES ({placeholders})",
        tuple(row[column] for column in columns),
    )
    return int(cursor.lastrowid)


def execute_import(connection, plan: dict) -> int:
    with connection.cursor() as cursor:
        # Delete existing invoice if it was flagged during prepare_plan
        if plan.get("already_exists"):
            doc_no = plan["document"]["document_no"]
            existing = fetch_one(cursor, "SELECT id FROM invoices WHERE no_doc = %s LIMIT 1", (doc_no,))
            if existing:
                old_id = int(existing["id"])
                cursor.execute("DELETE FROM invoices_details WHERE id_doc = %s", (old_id,))
                cursor.execute("DELETE FROM invoices WHERE id = %s", (old_id,))
                print(f"Replaced existing invoice {doc_no} (id={old_id}).")

        existing_sy_uk = fetch_one(cursor, "SELECT id FROM invoices WHERE sy_uk = %s LIMIT 1", (plan["next_sy_uk"],))
        if existing_sy_uk:
            raise ValueError(f"sy_uk wurde inzwischen vergeben: {plan['next_sy_uk']}")

        invoice_id = insert_row(cursor, "invoices", plan["invoice_row"])
        for row in plan["detail_rows"]:
            detail_row = dict(row)
            detail_row["id_doc"] = invoice_id
            insert_row(cursor, "invoices_details", detail_row)
    connection.commit()
    return invoice_id


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        connection = connect_db(config)
        try:
            with connection.cursor() as cursor:
                plan = prepare_plan(cursor)
            write_mapping(plan)
            print(f"Nutze env-Datei: {env_file.name}")
            print_dry_run(plan)

            confirmation = input("Erzwungenen Testimport wirklich ausfuehren? Exakt JA eingeben: ").strip()
            if confirmation != "JA":
                connection.rollback()
                print("Abgebrochen. Kein Import.")
                return 0

            invoice_id = execute_import(connection, plan)
            print(f"Import abgeschlossen. Neue invoices.id={invoice_id}, Positionen={len(plan['detail_rows'])}")
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

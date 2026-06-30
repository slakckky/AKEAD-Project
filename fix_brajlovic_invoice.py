from __future__ import annotations

import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import pymysql


BASE_DIR = Path(__file__).resolve().parent
ENV_CANDIDATES = (BASE_DIR / ".env", BASE_DIR / "Textdokument.env")
DATABASE_NAME = "datenbank"
DOCUMENT_ID = 3
DOCUMENT_NO = "R-25-005207"
SUPPLIER_NAME = "Brajlovic GmbH"
PDF_IMPORT_USER = "PDF_IMPORT_AUTO"


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
    )


def fetch_one(cursor, sql: str, params: tuple = ()) -> dict | None:
    cursor.execute(sql, params)
    return cursor.fetchone()


def fetch_all(cursor, sql: str, params: tuple = ()) -> list[dict]:
    cursor.execute(sql, params)
    return list(cursor.fetchall())


def parse_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return Decimal("0")
    text = text.replace("\u00a0", "").replace("\u202f", "").replace(" ", "").replace("%", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return Decimal("0")
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return Decimal("0")


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def grouped_tax_total(items: list[dict]) -> Decimal:
    buckets: dict[Decimal, Decimal] = {}
    for item in items:
        buckets[item["tax_rate"]] = buckets.get(item["tax_rate"], Decimal("0")) + item["line_total"]
    return sum((money(net * rate / Decimal("100")) for rate, net in buckets.items()), Decimal("0"))


def split_quantity_unit(value: str) -> tuple[Decimal, str]:
    text = " ".join((value or "").split())
    qty = parse_decimal(text)
    unit_match = re.search(r"\b(Stk?\.?|Stueck|Stück|Kart\.?|Karton|Kg|kg|KG)\b", text, re.IGNORECASE)
    unit = unit_match.group(1).lower() if unit_match else ""
    return qty, unit


def base_unit(pdf_unit: str, article_name: str) -> str:
    raw = f"{pdf_unit or ''} {article_name or ''}".casefold()
    if "kg" in raw:
        return "Kg"
    return "St"


def tax_from_cell(value: str) -> Decimal:
    match = re.search(r"\d{1,2}(?:[,.]\d+)?", value or "")
    return parse_decimal(match.group(0)) if match else Decimal("0")


def parse_pipe_item(item: dict) -> dict | None:
    raw_line = item.get("raw_line") or ""
    if "|" not in raw_line:
        return None
    cells = [cell.strip() for cell in raw_line.split("|")]
    if len(cells) < 8:
        return None
    position_no = int(parse_decimal(cells[0]))
    article_no = cells[1]
    article_name = cells[2]
    carton_qty, pdf_unit = split_quantity_unit(cells[3])
    stk_kg = parse_decimal(cells[4])
    unit_price = parse_decimal(cells[5])
    tax_rate = tax_from_cell(cells[6])
    line_total = parse_decimal(cells[7])
    if not position_no or not article_no or not article_name or stk_kg == 0:
        return None
    unit = base_unit(pdf_unit, article_name)
    kolli = carton_qty if "kart" in pdf_unit else Decimal("0")
    return {
        "item_id": int(item["id"]),
        "position_no": position_no,
        "article_no": article_no,
        "article_name": article_name,
        "kolli": kolli,
        "inhalt": stk_kg,
        "quantity": stk_kg,
        "unit": unit,
        "unit_price": unit_price,
        "line_total": line_total,
        "tax_rate": tax_rate,
        "product_id": int(item.get("product_id") or 0),
        "raw_line": raw_line,
    }


def load_canonical_items(cursor) -> tuple[list[dict], list[dict]]:
    rows = fetch_all(
        cursor,
        """
        SELECT id, position_no, article_no, article_name, kolli, inhalt, quantity, unit,
               unit_price, line_total, tax_rate, product_id, raw_line
        FROM pdf_import_items
        WHERE document_id = %s
        ORDER BY position_no, id
        """,
        (DOCUMENT_ID,),
    )
    canonical: dict[int, dict] = {}
    duplicates: list[dict] = []
    for row in rows:
        parsed = parse_pipe_item(row)
        if not parsed:
            duplicates.append(row)
            continue
        existing = canonical.get(parsed["position_no"])
        if existing is None:
            canonical[parsed["position_no"]] = parsed
        else:
            duplicates.append(row)
    return [canonical[key] for key in sorted(canonical)], duplicates


def find_or_plan_vendor(cursor) -> tuple[int | None, bool]:
    rows = fetch_all(
        cursor,
        """
        SELECT id, code, nom
        FROM vendors
        WHERE LOWER(nom) = LOWER(%s)
           OR LOWER(code) = LOWER(%s)
        """,
        (SUPPLIER_NAME, "BRAJLOVIC"),
    )
    if len(rows) == 1:
        return int(rows[0]["id"]), False
    if len(rows) > 1:
        raise ValueError("Brajlovic-Lieferant ist in vendors nicht eindeutig.")
    return None, True


def insert_vendor(cursor) -> int:
    now = datetime.now().replace(microsecond=0)
    cursor.execute(
        """
        INSERT INTO vendors
          (code, nom, id_stck, b_actif, no_sub, cod_tour, usr_cre, dat_cre, usr_upd, dat_upd)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        ("BRAJLOVIC", SUPPLIER_NAME, 1, 1, "", "", PDF_IMPORT_USER, now.date(), PDF_IMPORT_USER, now),
    )
    return int(cursor.lastrowid)


def invoice_ids(cursor) -> list[int]:
    rows = fetch_all(cursor, "SELECT id FROM invoices WHERE no_doc = %s ORDER BY id", (DOCUMENT_NO,))
    return [int(row["id"]) for row in rows]


def print_plan(items: list[dict], duplicates: list[dict], vendor_id: int | None, create_vendor: bool, invoices: list[int]) -> None:
    net_total = sum((item["line_total"] for item in items), Decimal("0"))
    tax_total = grouped_tax_total(items)
    print("DRY RUN: Brajlovic-Fix")
    print("=======================")
    print(f"Staging-Dokument: {DOCUMENT_ID} / {DOCUMENT_NO}")
    print(f"Kanonische Positionen: {len(items)}")
    print(f"Zu neutralisierende Duplikat-/Altpositionen: {len(duplicates)}")
    print(f"Netto geplant: {money(net_total)}")
    print(f"MwSt geplant: {money(tax_total)}")
    print(f"Brutto geplant: {money(net_total + tax_total)}")
    if create_vendor:
        print("Lieferant geplant: vendors INSERT code=BRAJLOVIC, nom=Brajlovic GmbH")
    else:
        print(f"Lieferant vorhanden: vendors.id={vendor_id}")
    print(f"Zu korrigierende invoices IDs: {', '.join(str(value) for value in invoices) or 'keine'}")
    print("")
    print("Beispiele:")
    for item in items[:8]:
        print(
            "  Pos {position_no}: {article_no} | qte={quantity} {unit} | preis={unit_price} | "
            "betrag={line_total} | steuer={tax_rate}".format(**item)
        )


def apply_fix(cursor, items: list[dict], duplicates: list[dict], vendor_id: int, invoices: list[int]) -> None:
    now = datetime.now().replace(microsecond=0)
    for item in items:
        cursor.execute(
            """
            UPDATE pdf_import_items
            SET article_no = %s,
                article_name = %s,
                kolli = %s,
                inhalt = %s,
                quantity = %s,
                unit = %s,
                unit_price = %s,
                line_total = %s,
                tax_rate = %s
            WHERE id = %s
            """,
            (
                item["article_no"],
                item["article_name"],
                item["kolli"],
                item["inhalt"],
                item["quantity"],
                item["unit"],
                item["unit_price"],
                item["line_total"],
                item["tax_rate"],
                item["item_id"],
            ),
        )
        if item["product_id"]:
            cursor.execute(
                """
                UPDATE produits
                SET unite = %s,
                    packet_unit = %s,
                    usr_upd = %s,
                    dat_upd = %s
                WHERE id = %s
                  AND usr_cre = %s
                """,
                (item["unit"], item["unit"], PDF_IMPORT_USER, now, item["product_id"], PDF_IMPORT_USER),
            )

    for duplicate in duplicates:
        cursor.execute(
            """
            UPDATE pdf_import_items
            SET kolli = 0,
                inhalt = 0,
                quantity = 0,
                unit = 'St',
                unit_price = 0,
                line_total = 0,
                tax_rate = 0
            WHERE id = %s
            """,
            (duplicate["id"],),
        )

    item_by_position = {item["position_no"]: item for item in items}
    net_total = sum((item["line_total"] for item in items), Decimal("0"))
    tax_total = grouped_tax_total(items)
    gross_total = net_total + tax_total

    for invoice_id in invoices:
        cursor.execute(
            """
            UPDATE invoices
            SET id_vendor = %s,
                sous_tot = %s,
                tot_tva = %s,
                tot_ttc = %s,
                usr_upd = %s,
                dat_upd = %s
            WHERE id = %s
            """,
            (vendor_id, money(net_total), money(tax_total), money(gross_total), "root", now, invoice_id),
        )

        details = fetch_all(
            cursor,
            """
            SELECT id, no_lig, ref_cus_sup
            FROM invoices_details
            WHERE id_doc = %s
            ORDER BY no_lig, id
            """,
            (invoice_id,),
        )
        seen_positions: set[int] = set()
        for detail in details:
            position_no = int(detail["no_lig"] or 0)
            item = item_by_position.get(position_no)
            if not item or position_no in seen_positions or str(detail.get("ref_cus_sup") or "") != item["article_no"]:
                cursor.execute(
                    """
                    UPDATE invoices_details
                    SET colis = 0,
                        qte = 0,
                        unite = 'St',
                        uprice_wot_curr_trf = 0,
                        prix_u_ht = 0,
                        qte_unit_prd = 0,
                        taux_tva = 0,
                        tot_ht_rem = 0,
                        usr_upd = %s,
                        dat_upd = %s
                    WHERE id = %s
                    """,
                    ("root", now, detail["id"]),
                )
                continue

            seen_positions.add(position_no)
            cursor.execute(
                """
                UPDATE invoices_details
                SET id_prd = %s,
                    lib = %s,
                    colis = %s,
                    qte = %s,
                    unite = %s,
                    uprice_wot_curr_trf = %s,
                    prix_u_ht = %s,
                    qte_unit_prd = %s,
                    taux_tva = %s,
                    tot_ht_rem = %s,
                    ref_cus_sup = %s,
                    usr_upd = %s,
                    dat_upd = %s
                WHERE id = %s
                """,
                (
                    item["product_id"],
                    item["article_name"],
                    item["kolli"],
                    item["quantity"],
                    item["unit"],
                    item["unit_price"],
                    item["unit_price"],
                    item["quantity"],
                    item["tax_rate"],
                    item["line_total"],
                    item["article_no"],
                    "root",
                    now,
                    detail["id"],
                ),
            )


def main() -> int:
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        connection = connect_db(config)
        try:
            with connection.cursor() as cursor:
                document = fetch_one(cursor, "SELECT id, document_no, supplier_name FROM pdf_import_documents WHERE id = %s", (DOCUMENT_ID,))
                if not document:
                    raise ValueError(f"pdf_import_documents.id={DOCUMENT_ID} nicht gefunden.")
                if document["document_no"] != DOCUMENT_NO:
                    raise ValueError(f"Unerwartete Belegnummer fuer document_id={DOCUMENT_ID}: {document['document_no']}")
                if (document.get("supplier_name") or "").strip() != SUPPLIER_NAME:
                    raise ValueError(f"Unerwarteter Lieferant im Staging: {document.get('supplier_name')!r}")

                items, duplicates = load_canonical_items(cursor)
                if len(items) != 181:
                    raise ValueError(f"Es wurden {len(items)} kanonische Positionen erkannt, erwartet sind 181.")

                vendor_id, create_vendor = find_or_plan_vendor(cursor)
                invoices = invoice_ids(cursor)
                print(f"Nutze env-Datei: {env_file.name}")
                print_plan(items, duplicates, vendor_id, create_vendor, invoices)

                answer = input("Brajlovic-Fix wirklich schreiben? Exakt JA eingeben: ").strip()
                if answer != "JA":
                    connection.rollback()
                    print("Abgebrochen. Keine Aenderungen geschrieben.")
                    return 0

                if create_vendor:
                    vendor_id = insert_vendor(cursor)
                if vendor_id is None:
                    raise ValueError("vendor_id konnte nicht bestimmt werden.")
                apply_fix(cursor, items, duplicates, vendor_id, invoices)
            connection.commit()
            print("Brajlovic-Fix geschrieben.")
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

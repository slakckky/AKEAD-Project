from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

import pymysql


BASE_DIR = Path(__file__).resolve().parent
ENV_CANDIDATES = (BASE_DIR / ".env", BASE_DIR / "Textdokument.env")
DATABASE_NAME = "datenbank"
PDF_IMPORT_USER = "PDF_IMPORT_AUTO"
PDF_IMPORT_FAMILY = "P01"
AUTO_MATCH_THRESHOLD = 90
NEW_PRODUCT_SIMILARITY_THRESHOLD = 60
OPEN_FOOD_FACTS_AVAILABLE = True


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and "=" in line and not line.startswith("#"):
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


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(word for word in text.split() if word not in {"x", "st", "stk", "pk", "pet", "gl"})


def score(left: str, right: str) -> int:
    left_n = normalize(left)
    right_n = normalize(right)
    if not left_n or not right_n:
        return 0
    try:
        from rapidfuzz import fuzz  # type: ignore

        return int(round(fuzz.token_set_ratio(left_n, right_n)))
    except Exception:
        pass
    return int(round(SequenceMatcher(None, left_n, right_n).ratio() * 100))


def normalize_unit(value: str, fallback: str = "St") -> str:
    raw = (value or "").strip().casefold()
    mapping = {
        "pk": "St",
        "paket": "St",
        "packung": "St",
        "pack": "St",
        "kar": "St",
        "kart": "St",
        "kart.": "St",
        "karton": "St",
        "fl": "St",
        "flasche": "St",
        "flaschen": "St",
        "dose": "St",
        "dosen": "St",
        "st": "St",
        "stk": "St",
        "stück": "St",
        "stueck": "St",
        "kg": "Kg",
        "g": "St",
        "gr": "St",
    }
    return mapping.get(raw, fallback or "St")[:4]


def product_unit_from_item(item: dict, similar: dict | None = None) -> str:
    item_unit = normalize_unit(item.get("unit") or "", "St")
    similar_unit = normalize_unit((similar or {}).get("unite") or "", item_unit)
    if similar_unit in {"St", "Kg"}:
        return similar_unit
    return item_unit if item_unit in {"St", "Kg"} else "St"


def open_food_facts_barcode(article_name: str) -> str:
    global OPEN_FOOD_FACTS_AVAILABLE
    if not OPEN_FOOD_FACTS_AVAILABLE:
        return ""
    query = urllib.parse.urlencode(
        {
            "search_terms": article_name,
            "search_simple": "1",
            "action": "process",
            "json": "1",
            "page_size": "5",
        }
    )
    try:
        req = urllib.request.Request(f"https://world.openfoodfacts.org/cgi/search.pl?{query}", headers={"User-Agent": "akead-pdf-import/1.0"})
        with urllib.request.urlopen(req, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        OPEN_FOOD_FACTS_AVAILABLE = False
        return ""
    matches = []
    for product in payload.get("products") or []:
        code = str(product.get("code") or "").strip()
        compare = " ".join(str(product.get(key) or "") for key in ("brands", "product_name", "quantity"))
        if code and score(article_name, compare) >= 90:
            matches.append(code)
    unique = sorted(set(matches))
    return unique[0] if len(unique) == 1 else ""


def gs1_barcode(article_name: str) -> str:
    api_url = os.environ.get("GS1_API_URL", "").strip()
    api_key = os.environ.get("GS1_API_KEY", "").strip()
    if not api_url:
        return ""
    query = urllib.parse.urlencode({"q": article_name})
    separator = "&" if "?" in api_url else "?"
    request = urllib.request.Request(
        f"{api_url}{separator}{query}",
        headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""

    candidates = []
    if isinstance(payload, dict):
        raw_items = payload.get("items") or payload.get("products") or payload.get("results") or []
    elif isinstance(payload, list):
        raw_items = payload
    else:
        raw_items = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("gtin") or entry.get("barcode") or entry.get("code") or "").strip()
        compare = " ".join(str(entry.get(key) or "") for key in ("name", "productName", "brand", "description", "quantity"))
        if re.fullmatch(r"\d{8,14}", code) and score(article_name, compare) >= 90:
            candidates.append(code)
    unique = sorted(set(candidates))
    return unique[0] if len(unique) == 1 else ""


def barcode_candidates(item: dict) -> list[str]:
    text_codes = re.findall(r"\b\d{8,14}\b", f"{item.get('article_no') or ''} {item.get('article_name') or ''} {item.get('raw_line') or ''}")
    internet_codes = [open_food_facts_barcode(item.get("article_name") or ""), gs1_barcode(item.get("article_name") or "")]
    return sorted(set(code for code in text_codes + internet_codes if code))


def find_product_by_barcode(cursor, codes: list[str]) -> dict | None:
    if not codes:
        return None
    return fetch_one(
        cursor,
        "SELECT p.* FROM codebarres cb INNER JOIN produits p ON p.id = cb.id_prd WHERE cb.cod_barr IN ({}) LIMIT 1".format(
            ", ".join(["%s"] * len(codes))
        ),
        tuple(codes),
    )


def best_similar_product(products: list[dict], article_name: str) -> tuple[dict | None, int]:
    best = None
    best_score = 0
    for candidate in products:
        current = score(article_name, candidate.get("lib_prd") or "")
        if current > best_score:
            best = candidate
            best_score = current
    return best, best_score


def next_sy_uk(cursor) -> int:
    row = fetch_one(cursor, "SELECT COUNT(*) c, COUNT(DISTINCT sy_uk) d, MAX(sy_uk) m FROM produits")
    if not row or row["c"] != row["d"] or row["m"] is None:
        raise ValueError("sy_uk fuer Produkte ist nicht sicher erzeugbar.")
    return int(row["m"]) + 1


def latest_template(cursor) -> dict:
    row = fetch_one(
        cursor,
        """
        SELECT *
        FROM produits
        WHERE usr_cre <> 'PDF_IMPORT'
          AND usr_cre <> 'PDF_IMPORT_AUTO'
          AND cod_fam_prd_path <> 'P01'
        ORDER BY id DESC
        LIMIT 1
        """,
    )
    if row:
        return row
    row = fetch_one(cursor, "SELECT * FROM produits ORDER BY id DESC LIMIT 1")
    if not row:
        raise ValueError("Keine Produktvorlage gefunden.")
    return row


def load_products(cursor) -> list[dict]:
    return fetch_all(
        cursor,
        """
        SELECT p.*, cb.cod_barr
        FROM produits p
        LEFT JOIN codebarres cb ON cb.id_prd = p.id
        WHERE p.usr_cre <> 'PDF_IMPORT'
          AND p.usr_cre <> 'PDF_IMPORT_AUTO'
          AND p.cod_fam_prd_path <> 'P01'
        """,
    )


def product_insert_row(template: dict, item: dict, similar: dict, sy_uk: int) -> dict:
    now = datetime.now().replace(microsecond=0)
    today = now.date()
    name = (item["article_name"] or "")[:255]
    unit = product_unit_from_item(item, similar)
    row = {key: value for key, value in template.items() if key != "id"}
    row.update(
        {
            "ref_prd": str(item["article_no"] or "")[:20],
            "typ_prd": 1,
            "lib_prd": name,
            "lib_prd_rtf": name,
            "lib_prd_html": None,
            "lib_ticket": name[:50],
            "lib_tech": None,
            "cod_fam_prd_path": similar.get("cod_fam_prd_path") or template.get("cod_fam_prd_path") or "",
            "unite": unit,
            "packet_unit": unit,
            "packet_qty": Decimal("1"),
            "id_taxclass": similar.get("id_taxclass") or template.get("id_taxclass") or 0,
            "id_stock": 1,
            "b_actif": 1,
            "sy_uk": sy_uk,
            "usr_cre": PDF_IMPORT_USER,
            "dat_cre": today,
            "usr_upd": PDF_IMPORT_USER,
            "dat_upd": now,
        }
    )
    return row


def insert_row(cursor, table: str, row: dict) -> int:
    columns = list(row.keys())
    cursor.execute(
        "INSERT INTO `{}` ({}) VALUES ({})".format(
            table,
            ", ".join(f"`{column}`" for column in columns),
            ", ".join(["%s"] * len(columns)),
        ),
        tuple(row[column] for column in columns),
    )
    return int(cursor.lastrowid)


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
        "usr_cre": PDF_IMPORT_USER,
        "dat_cre": today,
        "usr_upd": PDF_IMPORT_USER,
        "dat_upd": now,
    }


def main() -> int:
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        connection = connect_db(config)
        try:
            with connection.cursor() as cursor:
                items = fetch_all(
                    cursor,
                    """
                    SELECT *
                    FROM pdf_import_items
                    WHERE COALESCE(product_id, 0) = 0
                    ORDER BY document_id, position_no
                    """,
                )
                products = load_products(cursor)
                template = latest_template(cursor)
                sy_uk = next_sy_uk(cursor)
                matched = 0
                created = 0
                skipped = 0

                for item in items:
                    product = None
                    barcode = ""
                    if item.get("article_no"):
                        product = fetch_one(
                            cursor,
                            """
                            SELECT *
                            FROM produits
                            WHERE ref_prd = %s
                            LIMIT 1
                            """,
                            (item["article_no"],),
                        )
                    if not product:
                        codes = barcode_candidates(item)
                        barcode = codes[0] if len(codes) == 1 else ""
                        product = find_product_by_barcode(cursor, codes)
                    if not product and item.get("article_no"):
                        product = fetch_one(
                            cursor,
                            """
                            SELECT *
                            FROM produits
                            WHERE ref_manufacturer = %s
                              AND usr_cre <> 'PDF_IMPORT'
                              AND usr_cre <> 'PDF_IMPORT_AUTO'
                              AND cod_fam_prd_path <> 'P01'
                            LIMIT 1
                            """,
                            (item["article_no"],),
                        )
                    if not product:
                        best, best_score = best_similar_product(products, item["article_name"])
                        if best and best_score > AUTO_MATCH_THRESHOLD:
                            product = best
                        elif item.get("article_no"):
                            existing_any = fetch_one(cursor, "SELECT * FROM produits WHERE ref_prd = %s LIMIT 1", (item["article_no"],))
                            if existing_any:
                                cursor.execute("UPDATE pdf_import_items SET product_id = %s WHERE id = %s", (existing_any["id"], item["id"]))
                                matched += 1
                                continue
                            if not best:
                                skipped += 1
                                continue
                            row = product_insert_row(template, item, best, sy_uk)
                            sy_uk += 1
                            product_id = insert_row(cursor, "produits", row)
                            if barcode:
                                exists = fetch_one(cursor, "SELECT id FROM codebarres WHERE cod_barr = %s LIMIT 1", (barcode,))
                                if not exists:
                                    insert_row(cursor, "codebarres", barcode_row(product_id, barcode, row["unite"]))
                            cursor.execute("UPDATE pdf_import_items SET product_id = %s WHERE id = %s", (product_id, item["id"]))
                            created += 1
                            continue

                    if product:
                        cursor.execute("UPDATE pdf_import_items SET product_id = %s WHERE id = %s", (product["id"], item["id"]))
                        matched += 1
                    else:
                        skipped += 1

            connection.commit()
            print(f"Nutze env-Datei: {env_file.name}")
            print(f"Produktabgleich automatisch abgeschlossen: matched={matched}, created={created}, skipped={skipped}")
            print("Bestehende Produkte wurden nicht überschrieben. Produktsteuer wurde nicht geändert.")
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

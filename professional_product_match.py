from __future__ import annotations

import csv
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

import pymysql


BASE_DIR = Path(__file__).resolve().parent
ENV_CANDIDATES = (BASE_DIR / ".env", BASE_DIR / "Textdokument.env")
CSV_REPORT = BASE_DIR / "product_match_report.csv"
MD_REPORT = BASE_DIR / "product_match_report.md"
DATABASE_NAME = "datenbank"
PDF_IMPORT_FAMILY = "P01"
PDF_IMPORT_USER = "PDF_IMPORT"
AUTO_MATCH_THRESHOLD = 90
SUGGESTION_THRESHOLD = 75
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


def fetch_one(cursor, sql: str, params: tuple = ()) -> dict | None:
    cursor.execute(sql, params)
    return cursor.fetchone()


def fetch_all(cursor, sql: str, params: tuple = ()) -> list[dict]:
    cursor.execute(sql, params)
    return list(cursor.fetchall())


def column_exists(cursor, table: str, column: str) -> bool:
    return fetch_one(cursor, f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,)) is not None


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = []
    for word in text.split():
        if word in {"x", "st", "stk", "pk", "gl", "pet", "promo"}:
            continue
        words.append(word)
    return " ".join(words)


def token_set_score(left: str, right: str) -> int:
    left_tokens = set(normalize_text(left).split())
    right_tokens = set(normalize_text(right).split())
    if not left_tokens or not right_tokens:
        return 0
    intersection = left_tokens & right_tokens
    left_only = left_tokens - intersection
    right_only = right_tokens - intersection
    combined_left = " ".join(sorted(intersection | left_only))
    combined_right = " ".join(sorted(intersection | right_only))
    sorted_intersection = " ".join(sorted(intersection))
    ratios = [
        SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio(),
        SequenceMatcher(None, combined_left, combined_right).ratio(),
    ]
    if sorted_intersection:
        ratios.append(SequenceMatcher(None, sorted_intersection, combined_left).ratio())
        ratios.append(SequenceMatcher(None, sorted_intersection, combined_right).ratio())
    return int(round(max(ratios) * 100))


def parse_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace("%", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(value, date):
        return "'" + value.strftime("%Y-%m-%d") + "'"
    if isinstance(value, time):
        return "'" + value.strftime("%H:%M:%S") + "'"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def render_insert(table: str, row: dict) -> str:
    columns = [column for column in row.keys() if not column.startswith("_")]
    return "INSERT INTO `{}` ({}) VALUES ({});".format(
        table,
        ", ".join(f"`{column}`" for column in columns),
        ", ".join(sql_literal(row[column]) for column in columns),
    )


def insert_row(cursor, table: str, row: dict) -> int:
    clean = {key: value for key, value in row.items() if not key.startswith("_")}
    columns = list(clean.keys())
    cursor.execute(
        "INSERT INTO `{}` ({}) VALUES ({})".format(
            table,
            ", ".join(f"`{column}`" for column in columns),
            ", ".join(["%s"] * len(columns)),
        ),
        tuple(clean[column] for column in columns),
    )
    return int(cursor.lastrowid)


def latest_document_id(cursor) -> int:
    row = fetch_one(cursor, """
        SELECT d.id
        FROM pdf_import_documents d
        WHERE EXISTS (SELECT 1 FROM pdf_import_items i WHERE i.document_id = d.id)
        ORDER BY d.id DESC
        LIMIT 1
    """)
    if not row:
        raise ValueError(
            "Staging'de satir iceren bir belge bulunamadi. "
            "Adim 3 (Faturayi Sisteme Kaydet) once calistirilmali ve "
            "PDF'den en az bir urun satiri cikarilmis olmali."
        )
    return int(row["id"])


def load_items(cursor, document_id: int) -> list[dict]:
    return fetch_all(
        cursor,
        """
        SELECT *
        FROM pdf_import_items
        WHERE document_id = %s
        ORDER BY position_no
        """,
        (document_id,),
    )


def load_products(cursor) -> list[dict]:
    return fetch_all(
        cursor,
        """
        SELECT p.*, cb.cod_barr AS barcode, f.lib AS family_name, f.lib_path AS family_path,
               tr.tax_rate AS product_tax_rate
        FROM produits p
        LEFT JOIN codebarres cb ON cb.id_prd = p.id
        LEFT JOIN familles_prds f ON f.cod_fam_prd_path = p.cod_fam_prd_path
        LEFT JOIN tax_rates tr ON tr.id_taxclass = p.id_taxclass
        ORDER BY p.id
        """,
    )


def load_families(cursor) -> list[dict]:
    return fetch_all(
        cursor,
        """
        SELECT *
        FROM familles_prds
        ORDER BY cod_fam_prd_path
        """,
    )


def allowed_units(cursor) -> set[str]:
    rows = fetch_all(cursor, "SELECT cod_unit FROM param_unit WHERE b_active = 1")
    return {row["cod_unit"] for row in rows}


def product_template(cursor) -> dict:
    row = fetch_one(
        cursor,
        """
        SELECT *
        FROM produits
        WHERE usr_cre <> %s
          AND cod_fam_prd_path <> %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (PDF_IMPORT_USER, PDF_IMPORT_FAMILY),
    )
    if row:
        return row
    row = fetch_one(cursor, "SELECT * FROM produits ORDER BY id DESC LIMIT 1")
    if not row:
        raise ValueError("Keine Produktvorlage in produits gefunden.")
    return row


def next_numeric_sy_uk(cursor, table: str) -> int:
    stats = fetch_one(
        cursor,
        f"""
        SELECT COUNT(*) AS row_count,
               COUNT(DISTINCT sy_uk) AS distinct_count,
               MAX(sy_uk) AS max_sy_uk
        FROM `{table}`
        """,
    )
    if not stats or stats["row_count"] == 0 or stats["max_sy_uk"] is None:
        raise ValueError(f"Kann sy_uk fuer {table} nicht erzeugen.")
    if stats["row_count"] != stats["distinct_count"]:
        raise ValueError(f"Kann sy_uk fuer {table} nicht erzeugen: Werte sind nicht eindeutig.")
    return int(stats["max_sy_uk"]) + 1


def is_pdf_import_product(product: dict | None) -> bool:
    if not product:
        return False
    return product.get("usr_cre") == PDF_IMPORT_USER or product.get("cod_fam_prd_path") == PDF_IMPORT_FAMILY


def barcode_candidates(item: dict) -> list[str]:
    text = f"{item.get('article_name') or ''} {item.get('raw_line') or ''}"
    return sorted(set(re.findall(r"\b\d{8,14}\b", text)))


def normalize_unit(pdf_unit: str, units: set[str]) -> tuple[str, str]:
    # AKEAD'de kullanilan birimler: KOL (Koli/karton - birden fazla ST icerir),
    # KG (kilogram), ST (Stueck/tekil adet). "Karton"/"Kolli" ASLA ST'ye
    # normalize edilmemeli - bir koli icinde birden fazla ST/parca olur, bu
    # yuzden koli/karton tek bir adet gibi sayilirsa icindeki parca sayisi
    # kaybolur (bkz. build_product_row -> packet_qty).
    raw = (pdf_unit or "").strip().casefold().rstrip(".")
    mapping = {
        # Tekil/paket bazli satilan urunler (hepsi ST - icinde baska parca yok).
        # Gramaj (g/gr) ve hacim (ml/l/lt) urun adinda zaten yaziyor, ayrica
        # birim olarak kullanilmaz - hepsi ST'ye duser:
        "pkg": "ST",
        "package": "ST",
        "paket": "ST",
        "ct": "ST",
        "st": "ST",
        "stk": "ST",
        "stuck": "ST",
        "stück": "ST",
        "g": "ST",
        "gr": "ST",
        "ml": "ST",
        "l": "ST",
        "lt": "ST",
        "bd": "ST",   # Bund (demet)
        "bl": "ST",   # Bündel/Blatt
        "bt": "ST",   # Beutel/Bouteille
        "cc": "ST",
        "pa": "ST",   # Packung
        "pt": "ST",
        "rl": "ST",   # Rolle
        "tb": "ST",   # Tube
        "wg": "ST",
        "mt": "ST",
        "bund": "ST",
        "bündel": "ST",
        # Agirlik:
        "kg": "KG",
        # Koli/karton - icinde birden fazla ST var, ASLA tek bir ST sayilmaz:
        "karton": "KOL",
        "kartoon": "KOL",
        "kart": "KOL",
        "kar": "KOL",
        "koli": "KOL",
        "kolli": "KOL",
        "colli": "KOL",
        "ctn": "KOL",
        "pk": "KOL",
    }
    unit = mapping.get(raw, pdf_unit[:3].upper() if pdf_unit else "ST")
    if unit in units:
        note = "aus PDF normalisiert"
        if raw in {"g", "gr"}:
            note = "g/Gr nicht als Haupteinheit genutzt, auf ST normalisiert"
        elif unit == "KOL":
            note = "Karton/Kolli als KOL (Koli) normalisiert, nicht als Einzelstueck (ST)"
        return unit, note
    if "ST" in units:
        return "ST", f"PDF-Einheit {pdf_unit!r} nicht erlaubt, Fallback ST"
    return "", f"PDF-Einheit {pdf_unit!r} nicht erlaubt, keine sichere Einheit"


def resolve_unit(item: dict, units: set[str]) -> tuple[str, str]:
    """normalize_unit() sadece ham birim metnine (orn. "Paket") bakar - ama
    faturada ayri bir "Inhalt" kolonu (orn. icinde 6 adet oldugunu gosteren)
    olabilir. "1 Paket" tek bir ST degil, icinde N adet barindiran bir kap
    olabilir. Bu fonksiyon normalize_unit()'i cagirip, eger sonuc ST ama
    Inhalt kolonu 1'den buyukse, KOL'e yukseltir (icindeki adet sayisi
    packet_qty'de kaybolmasin diye)."""
    unit, note = normalize_unit(item.get("unit") or "", units)
    inhalt = item.get("inhalt")
    if unit == "ST" and inhalt and inhalt > 1 and "KOL" in units:
        return "KOL", (
            f"'{item.get('unit') or ''}' icin Inhalt kolonu {inhalt} adet gosteriyor - "
            "tek bir ST degil, KOL olarak normalisiert"
        )
    return unit, note


def family_score(article_name: str, family: dict) -> int:
    name = normalize_text(article_name)
    family_text = normalize_text(f"{family.get('lib') or ''} {family.get('lib_path') or ''}")
    rules = [
        (("honig", "syrup", "sirup", "marmalet"), ("honig", "marmalet", "suss", "suess", "sirup")),
        (("oliv", "olive", "oliven"), ("oliv", "feinkost")),
        (("gewurz", "baharat", "kofte", "adana", "grillwurz"), ("gewurz",)),
        (("reis", "pirinc", "mehl", "bulgur", "irmik", "nisasta", "galeta", "nohut"), ("mehl", "zucker", "nudeln", "hulsen", "lebensmittel")),
        (("getrank", "saft", "250ml", "500ml", "1000ml"), ("getrank",)),
        (("sauce", "sose", "essig", "nareksi", "granatapf"), ("essig", "sose")),
        (("konserve", "tursu", "salatalik", "lahana", "jalapeno", "biberiye", "patlican", "gemuse"), ("konserve", "gemuse", "feinkost")),
        (("keks", "kurabiye", "kekse"), ("suss", "suess", "knabber", "brot", "backwaren")),
        (("tee", "linde", "minze"), ("kaffe", "tee")),
    ]
    best = 0
    for article_terms, family_terms in rules:
        if any(term in name for term in article_terms) and any(term in family_text for term in family_terms):
            best = max(best, 95)
    lexical = token_set_score(article_name, f"{family.get('lib') or ''} {family.get('lib_path') or ''}")
    return max(best, lexical)


def derive_family(item: dict, families: list[dict]) -> tuple[dict | None, str, int]:
    candidates = [
        (family_score(item["article_name"], family), family)
        for family in families
        if family.get("cod_fam_prd_path") != PDF_IMPORT_FAMILY
    ]
    candidates.sort(key=lambda row: row[0], reverse=True)
    if not candidates or candidates[0][0] < 90:
        return None, "keine sichere vorhandene Artikelgruppe gefunden", candidates[0][0] if candidates else 0
    return candidates[0][1], "Artikelgruppe aus Name/Regeln abgeleitet", candidates[0][0]


def open_food_facts_lookup(item: dict) -> dict:
    global OPEN_FOOD_FACTS_AVAILABLE
    if not OPEN_FOOD_FACTS_AVAILABLE:
        return {"barcode": "", "note": "Open Food Facts nach vorherigem Fehler uebersprungen", "suggestions": ""}

    query = urllib.parse.urlencode(
        {
            "search_terms": item["article_name"],
            "search_simple": "1",
            "action": "process",
            "json": "1",
            "page_size": "5",
        }
    )
    url = f"https://world.openfoodfacts.org/cgi/search.pl?{query}"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "akead-pdf-import/1.0"})
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        OPEN_FOOD_FACTS_AVAILABLE = False
        return {"barcode": "", "note": f"Internet/Open Food Facts nicht erreichbar: {exc}", "suggestions": ""}

    matches = []
    pdf_name = normalize_text(item["article_name"])
    for product in payload.get("products") or []:
        code = str(product.get("code") or "").strip()
        product_name = str(product.get("product_name") or "").strip()
        brands = str(product.get("brands") or "").strip()
        quantity = str(product.get("quantity") or "").strip()
        compare = normalize_text(f"{brands} {product_name} {quantity}")
        score = token_set_score(pdf_name, compare)
        if code and score >= 92:
            matches.append((code, product_name, brands, quantity, score))

    if len(matches) == 1:
        return {"barcode": matches[0][0], "note": "genau ein sehr sicherer Open-Food-Facts-Treffer", "suggestions": ""}
    if len(matches) > 1:
        suggestions = "; ".join(f"{m[0]} {m[2]} {m[1]} {m[3]} ({m[4]}%)" for m in matches[:3])
        return {"barcode": "", "note": "mehrere sichere Treffer, kein Barcode gespeichert", "suggestions": suggestions}
    return {"barcode": "", "note": "kein sehr sicherer Open-Food-Facts-Treffer", "suggestions": ""}


def open_food_facts_by_barcode(barcode: str) -> dict:
    """Query Open Food Facts by exact barcode; return product names for fuzzy matching."""
    global OPEN_FOOD_FACTS_AVAILABLE
    if not OPEN_FOOD_FACTS_AVAILABLE:
        return {"names": [], "note": "Open Food Facts skipped after previous error"}

    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "akead-pdf-import/1.0"})
        with urllib.request.urlopen(req, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        OPEN_FOOD_FACTS_AVAILABLE = False
        return {"names": [], "note": f"Open Food Facts not reachable: {exc}"}

    if payload.get("status") != 1:
        return {"names": [], "note": f"Barcode {barcode} not in Open Food Facts"}

    p = payload.get("product") or {}
    names: list[str] = []
    for field in ("product_name_de", "product_name_en", "product_name"):
        val = str(p.get(field) or "").strip()
        if val and val not in names:
            names.append(val)
    brands = str(p.get("brands") or "").strip()
    quantity = str(p.get("quantity") or "").strip()
    label = f"{brands} {names[0]} {quantity}".strip() if names else barcode
    return {"names": names, "brands": brands, "quantity": quantity,
            "note": f"OFF barcode hit: {label}"}


def best_barcode_match(item: dict, products: list[dict]) -> dict | None:
    candidates = set(barcode_candidates(item))
    if not candidates:
        return None
    for product in products:
        barcode = str(product.get("barcode") or "")
        if barcode and barcode in candidates and not is_pdf_import_product(product):
            return product
    return None


def best_fuzzy_match(item: dict, products: list[dict]) -> tuple[dict | None, int]:
    best_product = None
    best_score = 0
    for product in products:
        if is_pdf_import_product(product):
            continue
        score = token_set_score(item["article_name"], product.get("lib_prd") or "")
        if score > best_score:
            best_product = product
            best_score = score
    return best_product, best_score


def exact_ref_match(item: dict, products: list[dict], include_pdf_import: bool) -> dict | None:
    article_no = str(item.get("article_no") or "").strip()
    if not article_no:
        return None
    for product in products:
        if str(product.get("ref_prd") or "").strip() == article_no:
            if include_pdf_import or not is_pdf_import_product(product):
                return product
    return None


def tax_info(item: dict, product: dict | None) -> tuple[str, str, str]:
    invoice_tax = parse_decimal(item.get("tax_rate"))
    product_tax = parse_decimal(product.get("product_tax_rate")) if product else Decimal("0")
    if product is None:
        return str(invoice_tax), "", "nein"
    difference = "ja" if invoice_tax != product_tax else "nein"
    return str(invoice_tax), str(product_tax), difference


def product_barcode(product: dict | None) -> str:
    return str(product.get("barcode") or "") if product else ""


def build_product_row(template: dict, item: dict, family: dict, unit: str, sy_uk: int) -> dict:
    now = datetime.now().replace(microsecond=0)
    today = now.date()
    name = (item["article_name"] or "")[:255]

    # KOL (koli/karton) tek basina bir "adet" degil, icinde birden fazla ST
    # (Stueck) iceren bir paket. Temel birim her zaman ST kalmali, KOL sadece
    # paketleme birimi (packet_unit); icindeki adet sayisi packet_qty'de
    # tutulur (faturadan "Inhalt" alani cikarilmissa oradan, yoksa 1).
    if unit == "KOL":
        base_unit = "ST"
        packet_unit = "KOL"
        inhalt = item.get("inhalt")
        packet_qty = inhalt if inhalt and inhalt > 0 else Decimal("1")
    else:
        base_unit = unit
        packet_unit = unit
        packet_qty = Decimal("1")

    row = {key: value for key, value in template.items() if key != "id"}
    row.update(
        {
            "ref_prd": f"IMP{sy_uk:06d}",
            "typ_prd": 1,
            "lib_prd": name,
            "lib_prd_rtf": name,
            "lib_prd_html": None,
            "lib_ticket": name[:50],
            "lib_tech": (f"Lief-Art-Nr: {item['article_no']}"
                         if str(item.get("article_no") or "").strip() else None),
            "cod_fam_prd_path": family["cod_fam_prd_path"],
            "cod_grp_prd_path_1": "",
            "cod_grp_prd_path_2": "",
            "unite": base_unit,
            "packet_unit": packet_unit,
            "packet_qty": packet_qty,
            "contenu": Decimal("0"),
            "unite_contenu": "",
            "id_taxclass": family.get("id_taxclass") or template.get("id_taxclass") or 0,
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


def build_barcode_row(product_id: int, barcode: str, unit: str) -> dict:
    now = datetime.now().replace(microsecond=0)
    today = now.date()
    return {
        "cod_barr": barcode,
        "id_prd": product_id,
        "unite": unit,
        "sy_uk_var": 0,
        "id_taille": 0,
        "id_couleur": 0,
        "usr_cre": PDF_IMPORT_USER,
        "dat_cre": today,
        "usr_upd": PDF_IMPORT_USER,
        "dat_upd": now,
    }


def evaluate_item(item: dict, products: list[dict], families: list[dict], units: set[str], template: dict, sy_uk: int) -> dict:
    notes = []
    product = exact_ref_match(item, products, include_pdf_import=False)
    match_type = "exact ref_prd"
    score = 100 if product else 0

    if not product:
        product = best_barcode_match(item, products)
        match_type = "barcode" if product else ""
        score = 100 if product else 0

    # barcode in invoice but not in AKEAD codebarres → ask Open Food Facts
    # for the product name, then try fuzzy-matching that name against AKEAD
    if not product:
        for bc in barcode_candidates(item):
            off = open_food_facts_by_barcode(bc)
            for name in off.get("names", []):
                fp, fs = best_fuzzy_match(dict(item, article_name=name), products)
                if fp and fs >= AUTO_MATCH_THRESHOLD:
                    product = fp
                    match_type = "OFF barcode→fuzzy"
                    score = fs
                    notes.append(f"OFF: {bc} → {name}")
                    break
            if product:
                break

    if not product:
        fuzzy_product, fuzzy_score = best_fuzzy_match(item, products)
        if fuzzy_product and fuzzy_score >= AUTO_MATCH_THRESHOLD:
            product = fuzzy_product
            match_type = "fuzzy"
            score = fuzzy_score
        elif fuzzy_product and fuzzy_score >= SUGGESTION_THRESHOLD:
            product = fuzzy_product
            match_type = "fuzzy suggestion"
            score = fuzzy_score

    pdf_import_exact = exact_ref_match(item, products, include_pdf_import=True)
    if pdf_import_exact and is_pdf_import_product(pdf_import_exact):
        notes.append("bestehender PDF_IMPORT-Artikel gefunden, nicht als fachlich sicher gewertet")

    if product and match_type != "fuzzy suggestion":
        invoice_tax, product_tax, tax_diff = tax_info(item, product)
        if tax_diff == "ja":
            notes.append("Steuerabweichung Produkt/Rechnung")
        return {
            "item": item,
            "matched_product": product,
            "match_percent": score,
            "match_type": match_type,
            "action": "uebernehmen",
            "unit": product.get("unite") or "",
            "family": product.get("cod_fam_prd_path") or "",
            "family_name": product.get("family_path") or product.get("family_name") or "",
            "barcode": product_barcode(product),
            "invoice_tax": invoice_tax,
            "product_tax": product_tax,
            "tax_difference": tax_diff,
            "note": "; ".join(notes),
            "planned_product": None,
            "planned_barcode": "",
            "barcode_suggestions": "",
        }

    if product and match_type == "fuzzy suggestion":
        invoice_tax, product_tax, tax_diff = tax_info(item, product)
        if tax_diff == "ja":
            notes.append("Steuerabweichung Produkt/Rechnung")
        return {
            "item": item,
            "matched_product": product,
            "match_percent": score,
            "match_type": match_type,
            "action": "vorschlag",
            "unit": product.get("unite") or "",
            "family": product.get("cod_fam_prd_path") or "",
            "family_name": product.get("family_path") or product.get("family_name") or "",
            "barcode": product_barcode(product),
            "invoice_tax": invoice_tax,
            "product_tax": product_tax,
            "tax_difference": tax_diff,
            "note": "; ".join(notes),
            "planned_product": None,
            "planned_barcode": "",
            "barcode_suggestions": "",
        }

    if pdf_import_exact and is_pdf_import_product(pdf_import_exact):
        unit, unit_note = resolve_unit(item, units)
        family, family_note, _family_match = derive_family(item, families)
        notes.extend([unit_note, family_note])
        invoice_tax, product_tax, tax_diff = tax_info(item, pdf_import_exact)
        if tax_diff == "ja":
            notes.append("Steuerabweichung Produkt/Rechnung")
        return {
            "item": item,
            "matched_product": pdf_import_exact,
            "match_percent": 100,
            "match_type": "exact ref_prd, aber PDF_IMPORT",
            "action": "manuell pruefen",
            "unit": unit or pdf_import_exact.get("unite") or "",
            "family": family["cod_fam_prd_path"] if family else pdf_import_exact.get("cod_fam_prd_path") or "",
            "family_name": family.get("lib_path") if family else pdf_import_exact.get("family_path") or pdf_import_exact.get("family_name") or "",
            "barcode": product_barcode(pdf_import_exact),
            "invoice_tax": invoice_tax,
            "product_tax": product_tax,
            "tax_difference": tax_diff,
            "note": "; ".join(note for note in notes if note),
            "planned_product": None,
            "planned_barcode": "",
            "barcode_suggestions": "",
        }

    unit, unit_note = resolve_unit(item, units)
    family, family_note, family_match = derive_family(item, families)
    internet = open_food_facts_lookup(item)
    notes.extend([unit_note, family_note, internet["note"]])

    # Create new product whenever a unit can be determined.
    # Family is best-effort: use whatever derive_family found (any score), or
    # fall back to the generic PDF_IMPORT placeholder family so the product is
    # at least in the system and can be re-classified later.
    if unit:
        action = "neu anlegen"
        if not family:
            family = {"cod_fam_prd_path": PDF_IMPORT_FAMILY, "lib_path": "PDF_IMPORT", "id_taxclass": 0}
            notes.append("no family matched — using PDF_IMPORT placeholder")
    else:
        action = "manuell pruefen"

    planned_product = build_product_row(template, item, family, unit, sy_uk) if action == "neu anlegen" else None
    invoice_tax, product_tax, tax_diff = tax_info(item, None)
    return {
        "item": item,
        "matched_product": None,
        "match_percent": 0,
        "match_type": "kein sicherer AKEAD-Treffer",
        "action": action,
        "unit": unit,
        "family": family["cod_fam_prd_path"] if family else "",
        "family_name": family.get("lib_path") if family else "",
        "barcode": internet["barcode"],
        "invoice_tax": invoice_tax,
        "product_tax": product_tax,
        "tax_difference": tax_diff,
        "note": "; ".join(note for note in notes if note),
        "planned_product": planned_product,
        "planned_barcode": internet["barcode"],
        "barcode_suggestions": internet["suggestions"],
    }


def prepare_plan(cursor) -> dict:
    document_id = latest_document_id(cursor)
    items = load_items(cursor, document_id)
    if not items:
        raise ValueError(f"Keine Positionen in pdf_import_items fuer document_id={document_id}.")
    products = load_products(cursor)
    families = load_families(cursor)
    units = allowed_units(cursor)
    template = product_template(cursor)
    next_sy_uk = next_numeric_sy_uk(cursor, "produits")
    evaluations = []
    for index, item in enumerate(items):
        evaluations.append(evaluate_item(item, products, families, units, template, next_sy_uk + index))
    return {"document_id": document_id, "items": items, "evaluations": evaluations}


def report_row(evaluation: dict) -> dict:
    item = evaluation["item"]
    product = evaluation["matched_product"]
    return {
        "pdf_article_no": item.get("article_no") or "",
        "pdf_article_name": item.get("article_name") or "",
        "akead_product_id": product.get("id") if product else "",
        "akead_ref": product.get("ref_prd") if product else "",
        "akead_article_name": product.get("lib_prd") if product else "",
        "match_percent": evaluation["match_percent"],
        "match_type": evaluation["match_type"],
        "action": evaluation["action"],
        "unit": evaluation["unit"],
        "article_group": evaluation["family"],
        "article_group_name": evaluation["family_name"],
        "barcode": evaluation["barcode"],
        "barcode_missing": "evet" if not evaluation["barcode"] else "",
        "invoice_tax": evaluation["invoice_tax"],
        "product_tax": evaluation["product_tax"],
        "tax_difference": evaluation["tax_difference"],
        "note": evaluation["note"],
        "barcode_suggestions": evaluation["barcode_suggestions"],
    }


def write_reports(plan: dict) -> None:
    rows = [report_row(evaluation) for evaluation in plan["evaluations"]]
    fieldnames = list(rows[0].keys()) if rows else []
    with CSV_REPORT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

    counts = {}
    for row in rows:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    missing_barcode_rows = [row for row in rows if row["barcode_missing"]]
    manual_review_rows = [row for row in rows if row["action"] == "manuell pruefen"]

    lines = [
        "# Product Match Report",
        "",
        f"Staging-Dokument: `{plan['document_id']}`",
        f"Positionen: {len(rows)}",
        "",
        "## Zusammenfassung",
        "",
    ]
    for action in ["uebernehmen", "vorschlag", "neu anlegen", "manuell pruefen"]:
        lines.append(f"- {action}: {counts.get(action, 0)}")
    lines.append(f"- **barkodu eksik (elle doldurulmali): {len(missing_barcode_rows)}**")
    lines.append(f"- **manuel kontrol gerekli: {len(manual_review_rows)}**")

    lines.extend(["", "## BARKODU EKSIK - ELLE DOLDURULMALI", ""])
    if missing_barcode_rows:
        lines.append(
            "Bu satirlar icin ne MySQL'de (AKEAD) ne de faturada/internette "
            "guvenilir bir barkod bulunamadi. Barkod alani bos kaldi, elle "
            "doldurulmasi gerekiyor:"
        )
        lines.append("")
        lines.append("| PDF ArtNr | PDF Artikel | Aksiyon | AKEAD Urun | Not |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in missing_barcode_rows:
            akead = f"{row['akead_product_id']} {row['akead_article_name']}".strip()
            lines.append(
                f"| {row['pdf_article_no']} | {row['pdf_article_name']} | "
                f"{row['action']} | {akead or '-'} | {row['note']} |"
            )
    else:
        lines.append("Bu faturada barkodu eksik kalan satir yok.")

    lines.extend(["", "## MANUEL KONTROL GEREKLI", ""])
    if manual_review_rows:
        lines.append(
            "Sistem bu satirlari guvenli sekilde otomatik eslestiremedi/olusturamadi - "
            "birinin elle bakmasi gerekiyor:"
        )
        lines.append("")
        lines.append("| PDF ArtNr | PDF Artikel | AKEAD Urun | Not |")
        lines.append("| --- | --- | --- | --- |")
        for row in manual_review_rows:
            akead = f"{row['akead_product_id']} {row['akead_article_name']}".strip()
            lines.append(
                f"| {row['pdf_article_no']} | {row['pdf_article_name']} | {akead or '-'} | {row['note']} |"
            )
    else:
        lines.append("Bu faturada manuel kontrol gerektiren satir yok.")

    lines.extend(
        [
            "",
            "## Regeln",
            "",
            "- Exact Match gegen `produits.ref_prd` wird nur automatisch uebernommen, wenn der Treffer nicht aus `PDF_IMPORT`/`P01` stammt.",
            "- Barcode-Match nutzt nur vorhandene AKEAD-Barcodes oder sehr sichere Open-Food-Facts-Treffer.",
            "- Fuzzy Match ab 90% wird automatisch uebernommen.",
            "- Fuzzy Match von 75% bis 89% wird nur als Vorschlag gemeldet.",
            "- Unter 75% wird nicht automatisch uebernommen.",
            "- Produktsteuer wird nie geaendert; Rechnungsteuer bleibt positionsbezogen.",
            "",
            "## Positionen",
            "",
            "| PDF ArtNr | PDF Artikel | AKEAD Artikel | Match | Aktion | Einheit | Gruppe | Barcode | Rechnungsteuer | Produktsteuer | Abweichung | Hinweis |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        akead = f"{row['akead_product_id']} {row['akead_article_name']}".strip()
        lines.append(
            f"| {row['pdf_article_no']} | {row['pdf_article_name']} | {akead} | "
            f"{row['match_percent']}% | {row['action']} | {row['unit']} | "
            f"{row['article_group']} {row['article_group_name']} | {row['barcode']} | "
            f"{row['invoice_tax']} | {row['product_tax']} | {row['tax_difference']} | {row['note']} |"
        )
    MD_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_dry_run(plan: dict) -> None:
    print("DRY RUN: professionelles Produktmatching")
    print("=======================================")
    print(f"Staging-Dokument: {plan['document_id']}")
    print(f"Positionen: {len(plan['evaluations'])}")
    print()

    rows = [report_row(evaluation) for evaluation in plan["evaluations"]]
    missing_barcode_rows = [row for row in rows if row["barcode_missing"]]
    manual_review_rows = [row for row in rows if row["action"] == "manuell pruefen"]

    print(f">>> BARCODE MISSING (fill manually): {len(missing_barcode_rows)} rows <<<")
    for row in missing_barcode_rows:
        akead = f"{row['akead_product_id']} {row['akead_article_name']}".strip()
        print(f"  - {row['pdf_article_no']} | {row['pdf_article_name']} | action: {row['action']} | AKEAD: {akead or '-'}")
    print()

    print(f">>> MANUAL REVIEW REQUIRED: {len(manual_review_rows)} rows <<<")
    for row in manual_review_rows:
        akead = f"{row['akead_product_id']} {row['akead_article_name']}".strip()
        print(f"  - {row['pdf_article_no']} | {row['pdf_article_name']} | AKEAD: {akead or '-'} | note: {row['note'] or '-'}")
    print()

    print("--- All rows detail ---")
    for evaluation in plan["evaluations"]:
        row = report_row(evaluation)
        marker = ""
        if row["action"] == "manuell pruefen":
            marker = ">>> MANUAL REVIEW REQUIRED <<< "
        elif row["barcode_missing"]:
            marker = ">>> BARCODE MISSING <<< "
        print(
            f"{marker}{row['pdf_article_no']} | {row['pdf_article_name']} | "
            f"Match {row['match_percent']}% | Action: {row['action']} | "
            f"Unit: {row['unit'] or '-'} | Group: {row['article_group'] or '-'} | "
            f"Barcode: {'yes' if row['barcode'] else 'no'} | "
            f"Invoice tax: {row['invoice_tax']} | Product tax: {row['product_tax'] or '-'} | "
            f"Tax diff: {row['tax_difference']}"
        )
        if row["akead_product_id"]:
            print(f"  AKEAD: {row['akead_product_id']} / {row['akead_article_name']}")
        if row["note"]:
            print(f"  Note: {row['note']}")
        if evaluation["planned_product"]:
            print("  Planned produits INSERT:")
            print("  " + render_insert("produits", evaluation["planned_product"]))
            if evaluation["planned_barcode"]:
                print("  Planned codebarres INSERT after product creation")
    print()
    print(f"CSV-Report: {CSV_REPORT}")
    print(f"Markdown-Report: {MD_REPORT}")


def execute_plan(connection, plan: dict) -> None:
    with connection.cursor() as cursor:
        for evaluation in plan["evaluations"]:
            item = evaluation["item"]
            action = evaluation["action"]
            product = evaluation["matched_product"]
            product_id = 0
            if action == "uebernehmen" and product:
                product_id = int(product["id"])
            elif action == "neu anlegen" and evaluation["planned_product"]:
                existing = fetch_one(cursor, "SELECT id FROM produits WHERE ref_prd = %s LIMIT 1", (item["article_no"],))
                if existing:
                    product_id = int(existing["id"])
                else:
                    product_id = insert_row(cursor, "produits", evaluation["planned_product"])
                    barcode = evaluation["planned_barcode"]
                    if barcode:
                        existing_barcode = fetch_one(cursor, "SELECT id FROM codebarres WHERE cod_barr = %s LIMIT 1", (barcode,))
                        if not existing_barcode:
                            insert_row(cursor, "codebarres", build_barcode_row(product_id, barcode, evaluation["unit"]))
            else:
                continue

            cursor.execute(
                """
                UPDATE pdf_import_items
                SET product_id = %s
                WHERE id = %s
                """,
                (product_id, item["id"]),
            )
    connection.commit()


def main() -> int:
    try:
        env_file = find_env_file()
        config = load_env(env_file)
        connection = connect_db(config)
        try:
            with connection.cursor() as cursor:
                if not column_exists(cursor, "pdf_import_items", "product_id"):
                    raise ValueError("pdf_import_items.product_id fehlt. Bitte Staging-Tabelle zuerst erweitern.")
                plan = prepare_plan(cursor)
            write_reports(plan)
            print(f"Nutze env-Datei: {env_file.name}")
            print_dry_run(plan)

            confirmation = input("Produktzuordnung/Produktanlage wirklich schreiben? Exakt JA eingeben: ").strip()
            if confirmation != "JA":
                connection.rollback()
                print("Abgebrochen. Keine Produkte angelegt und keine product_id aktualisiert.")
                return 0

            execute_plan(connection, plan)
            print("Produktmatching geschrieben. Bestehende Produkte wurden nicht ueberschrieben.")
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

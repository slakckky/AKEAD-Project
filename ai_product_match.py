"""
AKEAD Invoice Matcher - AI destekli urun eslestirme.

professional_product_match.py'nin regex/bulanik eslestirmeyle cozemedigi
satirlari (action: "manuell pruefen" veya "vorschlag") Claude'a gonderip
en olasi AKEAD urununu bulmasini ister. Fatura satirlarindaki urun adlari
sik sik kisaltilmis/kesilmis oluyor (orn. "Beybal Honig Sirup" yerine
"Honig Sy") - AI bu tur kisaltmalari bulanik metin eslestirmeden daha iyi
cozebiliyor.

Mevcut bir AKEAD urunuyle eslesme bulunamayan satirlar icin AI ayrica:
- urun turunu/kategorisini (familles_prds'den bir aday) ve
- dogru birimi (KOL koli, KG kilogram, ST stueck/tekil adet) ve
- birim KOL ise bir kolide kac ST/adet oldugunu (pieces_per_kol)
belirlemeye calisir. "Karton" AKEAD'de KOL olarak gecer - tekil bir ST
DEGILDIR, icinde birden fazla ST barindirir.

GUVENLIK: Bu script de projenin geri kalani gibi temkinli calisir. AI
onerisi DOGRUDAN pdf_import_items.product_id'ye yazilmaz - sadece rapor
olarak sunulur (ai_match_report.md/.csv) ve sadece --apply + tam JA
onayiyla, sadece yuksek guvenli (>= AUTO_APPLY_THRESHOLD) oneriler yazilir.
Dusuk guvenli oneriler her zaman "manuel kontrol" olarak kalir. AI hicbir
zaman barkod uydurmaz - sadece dogru AKEAD urununu bulmaya calisir; o
urunun barkodu AKEAD'de zaten yoksa, barkod eksikligi gene de devam eder.
Yeni urun turu/birim onerileri de sadece raporda gosterilir - bu script
henuz produits tablosuna yeni urun YAZMAZ (bu, professional_product_match.py
"neu anlegen" akisinin isi).

Kurulum:
    .env dosyasina ANTHROPIC_API_KEY ekleyin (bkz. .env.example).

Kullanim:
    python ai_product_match.py            # sadece oneri raporu (dry run)
    python ai_product_match.py --apply    # JA onayiyla yuksek guvenli eslesmeleri yazar
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

import professional_product_match as ppm

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
AI_REPORT_MD = BASE_DIR / "ai_match_report.md"
AI_REPORT_CSV = BASE_DIR / "ai_match_report.csv"

MODEL = "claude-opus-4-8"
MAX_CANDIDATES = 20
AUTO_APPLY_THRESHOLD = 85  # --apply sadece bu guven puaninin uzerindekileri yazar

SYSTEM_PROMPT = """You are a product matching assistant for AKEAD, a wholesale food distributor.

Your job is to match each invoice line item to the correct product in the AKEAD catalog.

## Input fields per item

- article_name: product name as it appears on the invoice (often abbreviated or truncated
  due to narrow PDF columns, e.g. "Honig Sy" instead of "Beybal Honig Sirup")
- raw_unit / raw_kolli / raw_inhalt: raw unit/packing data from the invoice
- rule_based_unit: unit pre-computed by a rule engine (may be wrong, check it)
- supplier_name: same supplier tends to use the same abbreviations and sell the same
  product families — use this context to resolve abbreviations
- candidates: top fuzzy-matched AKEAD products (id, name, family, fuzzy_score)
- candidate_families: top product family suggestions
- off_product: Open Food Facts lookup result (may be empty)

## off_product — international barcode database

If the invoice contains a barcode and it was found in the Open Food Facts database,
off_product contains:
  - barcode: the EAN/UPC code from the invoice
  - names: product name in one or more languages (German first if available,
    then English, then original). Example: ["Ayran", "Turkish Yogurt Drink"]
  - brands: brand name(s) from Open Food Facts
  - quantity: package size string, e.g. "500ml", "1kg"

How to use off_product:
1. If off_product is present, it is strong evidence about what the product actually is.
   Cross-reference its names and brand against the candidates list.
2. OFF names may be in German, English, or French — mentally translate if needed to
   match against German AKEAD product names in candidates.
3. If a candidate's name matches the OFF product name or brand closely, raise your
   confidence score accordingly.
4. If off_product is empty or none of its names match any candidate, ignore it and
   rely on article_name + candidates alone.
5. Never invent a product_id not in the candidates list.

## Product matching rules

- If you are reasonably confident one candidate is the correct product, return its id
  and a confidence score 0-100.
- If no candidate is a genuine match, set product_id to null and confidence to 0.
- Use ONLY ids from the candidates list — never invent an id.
- In the reasoning field, briefly explain WHY you chose this product (or none), in
  English. Show how you resolved abbreviations or used off_product, e.g.:
  "Honig Sy -> Honig Sirup (honey syrup), matches candidate 2; OFF confirms brand Beybal"

## Unit validation (required for EVERY row, even if no product match)

AKEAD uses exactly three units: KOL (carton/case), KG (kilogram), ST (piece/unit).
No other unit is valid — gramage (500g, 90g) is part of the product name, not a unit.

Rules:
- "Karton"/"Kart"/"Kar"/"Kartoon" / "Kolli"/"Koli" / "PK" → KOL
  A carton/case is NOT a single ST — it contains multiple pieces.
- "Bund", BD, BL, BT, CC, PA, PT, RL, TB, WG, MT, "Package"/"PKG", "Paket", "Stk" → ST
  BUT only if there is genuinely one piece. If raw_inhalt or the product name indicates
  multiple pieces (e.g. "6x90g", "12 Stk", "6'li"), set unit=KOL and fill pieces_per_kol.
- Volume/length units (ML, L, LT) are not standalone units → ST (same KOL rule applies).
- "KG" only for products genuinely sold by weight (bulk/loose products).
- Always write exactly KOL, KG, or ST — never leave unit empty.
- If unit=KOL, fill pieces_per_kol from clues in the product name or raw_kolli/raw_inhalt.
  Leave null if uncertain — do not guess.
- rule_based_unit already checks raw_inhalt for KOL upgrades, but only you can see
  clues inside the product name itself, so always verify.

## Product family (only if product_id is null)

- Set family_code to the best matching code from candidate_families.
- If none fits, set null. Use ONLY codes from candidate_families — never invent one."""


class ItemMatch(BaseModel):
    item_id: int
    product_id: Optional[int] = None
    confidence: int
    reasoning: str
    unit: Optional[str] = None
    pieces_per_kol: Optional[int] = None
    family_code: Optional[str] = None


class MatchResult(BaseModel):
    matches: list[ItemMatch]


def get_top_candidates(item: dict, products: list[dict], limit: int = MAX_CANDIDATES) -> list[dict]:
    scored = []
    for product in products:
        if ppm.is_pdf_import_product(product):
            continue
        score = ppm.token_set_score(item.get("article_name") or "", product.get("lib_prd") or "")
        if score <= 0:
            continue
        scored.append((score, product))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "id": product["id"],
            "ref_prd": product.get("ref_prd") or "",
            "name": product.get("lib_prd") or "",
            "family": product.get("family_path") or product.get("family_name") or "",
            "barcode": product.get("barcode") or "",
            "fuzzy_score": score,
        }
        for score, product in scored[:limit]
    ]


def get_top_families(item: dict, families: list[dict], limit: int = MAX_CANDIDATES) -> list[dict]:
    scored = [
        (ppm.family_score(item.get("article_name") or "", family), family)
        for family in families
        if family.get("cod_fam_prd_path") != ppm.PDF_IMPORT_FAMILY
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "code": family["cod_fam_prd_path"],
            "name": family.get("lib_path") or family.get("lib") or "",
        }
        for score, family in scored[:limit]
        if score > 0
    ]


def build_unresolved_payload(
    evaluations: list[dict], products: list[dict], families: list[dict], allowed_units: set[str]
) -> list[dict]:
    unresolved = []
    for evaluation in evaluations:
        if evaluation["action"] not in ("manuell pruefen", "vorschlag"):
            continue
        item = evaluation["item"]
        candidates = get_top_candidates(item, products)
        rule_based_unit, rule_based_note = ppm.resolve_unit(item, allowed_units)
        # barcode lookup in Open Food Facts for extra context sent to Claude
        off_product: dict = {}
        for bc in ppm.barcode_candidates(item):
            off = ppm.open_food_facts_by_barcode(bc)
            if off.get("names"):
                off_product = {
                    "barcode": bc,
                    "names": off["names"],
                    "brands": off.get("brands", ""),
                    "quantity": off.get("quantity", ""),
                }
                break

        unresolved.append(
            {
                "item_id": item["id"],
                "article_no": item.get("article_no") or "",
                "article_name": item.get("article_name") or "",
                "raw_unit": item.get("unit") or "",
                "raw_kolli": str(item.get("kolli")) if item.get("kolli") is not None else "",
                "raw_inhalt": str(item.get("inhalt")) if item.get("inhalt") is not None else "",
                "rule_based_unit": rule_based_unit,
                "rule_based_unit_note": rule_based_note,
                "candidates": [
                    {k: v for k, v in candidate.items() if k != "barcode"}
                    for candidate in candidates
                ],
                "candidate_families": get_top_families(item, families),
                "off_product": off_product,
            }
        )
    return unresolved


def call_claude(client: anthropic.Anthropic, supplier_name: str, unresolved: list[dict]) -> MatchResult:
    payload = {"supplier_name": supplier_name, "items": unresolved}
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}],
            output_format=MatchResult,
        )
    except anthropic.AuthenticationError as exc:
        raise RuntimeError(
            "Claude API anahtari gecersiz/eksik. .env dosyasina ANTHROPIC_API_KEY ekleyin."
        ) from exc
    except anthropic.RateLimitError as exc:
        raise RuntimeError(f"Claude API rate limit: {exc}") from exc
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Claude API hatasi ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError(f"Claude API'ye baglanilamadi: {exc}") from exc
    return response.parsed_output


def write_report(unresolved: list[dict], result: MatchResult, products_by_id: dict[int, dict]) -> None:
    matches_by_item = {match.item_id: match for match in result.matches}

    lines = [
        "# AI Urun Eslestirme Onerileri",
        "",
        f"Toplam degerlendirilen satir: {len(unresolved)}",
        "",
        "## Mevcut urunlerle eslesenler",
        "",
        "| PDF ArtNr | PDF Artikel | AI Onerisi (AKEAD) | Guven | Barkod | Aciklama |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    new_product_lines = [
        "",
        "## Mevcut urun bulunamayanlar - AI'nin onerdigi tur/birim",
        "",
        "Bu satirlar icin AKEAD'de uygun bir mevcut urun bulunamadi. AI'nin "
        "urun turu/birim onerisi asagida - yeni urun olusturma henuz bu "
        "script'ten degil, manuel olarak ya da professional_product_match.py'nin "
        "\"neu anlegen\" akisiyla yapilmali.",
        "",
        "| PDF ArtNr | PDF Artikel | Onerilen Tur | Birim | Koli icindeki adet (ST) | Aciklama |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    csv_rows = [
        ["item_id", "pdf_article_no", "pdf_article_name", "ai_product_id", "ai_product_name",
         "confidence", "barcode", "barcode_missing", "suggested_family", "suggested_unit",
         "suggested_pieces_per_kol", "reasoning"]
    ]

    has_new_product_rows = False
    for item in unresolved:
        match = matches_by_item.get(item["item_id"])
        if match is None or match.product_id is None:
            confidence = match.confidence if match else 0
            reasoning = match.reasoning if match else ""
            family = match.family_code if match else ""
            unit = match.unit if match else ""
            pieces = match.pieces_per_kol if match else None
            new_product_lines.append(
                f"| {item['article_no']} | {item['article_name']} | {family or '-'} | "
                f"{unit or '-'} | {pieces if pieces is not None else '-'} | {reasoning} |"
            )
            has_new_product_rows = True
            csv_rows.append([
                item["item_id"], item["article_no"], item["article_name"],
                "", "", confidence, "", "evet", family or "", unit or "",
                pieces if pieces is not None else "", reasoning,
            ])
            continue

        product = products_by_id.get(match.product_id)
        ai_product_name = f"{match.product_id} {product.get('lib_prd') if product else ''}".strip()
        barcode = (product.get("barcode") or "") if product else ""

        lines.append(
            f"| {item['article_no']} | {item['article_name']} | {ai_product_name} | "
            f"{match.confidence}% | {barcode or 'EKSIK'} | {match.reasoning} |"
        )
        csv_rows.append([
            item["item_id"], item["article_no"], item["article_name"],
            match.product_id, ai_product_name,
            match.confidence, barcode, "evet" if not barcode else "", "", "", "", match.reasoning,
        ])

    if not has_new_product_rows:
        new_product_lines.append("(yok)")

    AI_REPORT_MD.write_text("\n".join(lines + new_product_lines) + "\n", encoding="utf-8")

    import csv
    with AI_REPORT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerows(csv_rows)


def validate_matches(
    result: MatchResult, unresolved: list[dict], allowed_units: set[str]
) -> tuple[MatchResult, list[str]]:
    """AI ciktisini gonderdigimiz adaylarla karsilastirip dogrular.

    Prompt 'sadece candidates/candidate_families listesindeki id/kodlari kullan'
    diyor, ama bu sadece bir talimat - sunucu tarafinda da dogrulamadan AI'nin
    uydurdugu bir product_id/family_code sessizce DB'ye yazilabilirdi. Burada
    gecersiz degerler yok sayilip uyari olarak raporlanir, asla oldugu gibi
    kabul edilmez.
    """
    warnings: list[str] = []
    unresolved_by_id = {item["item_id"]: item for item in unresolved}
    sanitized: list[ItemMatch] = []
    seen_ids: set[int] = set()

    for match in result.matches:
        item = unresolved_by_id.get(match.item_id)
        if item is None:
            warnings.append(f"item {match.item_id}: AI gonderilmeyen bir item_id dondurdu, yok sayildi.")
            continue
        if match.item_id in seen_ids:
            warnings.append(f"item {match.item_id}: AI ayni satir icin birden fazla sonuc dondurdu, ilki kullanildi.")
            continue
        seen_ids.add(match.item_id)

        product_id = match.product_id
        if product_id is not None:
            valid_ids = {candidate["id"] for candidate in item["candidates"]}
            if product_id not in valid_ids:
                warnings.append(
                    f"item {match.item_id}: AI gonderilmeyen bir product_id ({product_id}) "
                    "dondurdu, yok sayildi (manuel kontrole dustu)."
                )
                product_id = None

        unit = match.unit
        if unit is not None and unit not in allowed_units:
            warnings.append(
                f"item {match.item_id}: AI gecersiz bir birim ({unit!r}) dondurdu, "
                f"kural-tabanli tahmine ({item['rule_based_unit'] or 'yok'}) dusuldu."
            )
            unit = item["rule_based_unit"] or None

        family_code = match.family_code
        if family_code is not None:
            valid_families = {family["code"] for family in item["candidate_families"]}
            if family_code not in valid_families:
                warnings.append(
                    f"item {match.item_id}: AI gonderilmeyen bir family_code ({family_code!r}) "
                    "dondurdu, yok sayildi."
                )
                family_code = None

        pieces = match.pieces_per_kol
        if pieces is not None and pieces <= 0:
            warnings.append(f"item {match.item_id}: gecersiz pieces_per_kol ({pieces}), yok sayildi.")
            pieces = None

        sanitized.append(
            ItemMatch(
                item_id=match.item_id,
                product_id=product_id,
                confidence=match.confidence,
                reasoning=match.reasoning,
                unit=unit,
                pieces_per_kol=pieces,
                family_code=family_code,
            )
        )

    for item_id in set(unresolved_by_id) - seen_ids:
        warnings.append(f"item {item_id}: AI bu satir icin hic sonuc dondurmedi - manuel kontrole dusuyor.")

    return MatchResult(matches=sanitized), warnings


def apply_matches(connection, unresolved: list[dict], result: MatchResult) -> int:
    matches_by_item = {match.item_id: match for match in result.matches}
    applied = 0
    with connection.cursor() as cursor:
        for item in unresolved:
            match = matches_by_item.get(item["item_id"])
            if match is None or match.product_id is None:
                continue
            if match.confidence < AUTO_APPLY_THRESHOLD:
                continue
            cursor.execute(
                "UPDATE pdf_import_items SET product_id = %s WHERE id = %s",
                (match.product_id, item["item_id"]),
            )
            applied += 1
    connection.commit()
    return applied


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="AI destekli urun eslestirme")
    parser.add_argument(
        "--apply", action="store_true",
        help=f"JA onayiyla guven puani >= {AUTO_APPLY_THRESHOLD} olan eslesmeleri yazar",
    )
    args = parser.parse_args()

    try:
        env_file = ppm.find_env_file()
        config = ppm.load_env(env_file)

        connection = ppm.connect_db(config)
        try:
            with connection.cursor() as cursor:
                plan = ppm.prepare_plan(cursor)
                products = ppm.load_products(cursor)
                families = ppm.load_families(cursor)
                allowed_units = ppm.allowed_units(cursor)
                document = ppm.fetch_one(
                    cursor, "SELECT supplier_name FROM pdf_import_documents WHERE id = %s",
                    (plan["document_id"],),
                )
        finally:
            connection.close()

        supplier_name = (document or {}).get("supplier_name") or ""

        unresolved = build_unresolved_payload(plan["evaluations"], products, families, allowed_units)
        if not unresolved:
            print("No rows requiring manual review/suggestion - nothing to send to AI.")
            return 0

        print(f"Sending {len(unresolved)} rows to AI (model: {MODEL}, supplier: {supplier_name or 'unknown'})...")
        client = anthropic.Anthropic()
        result = call_claude(client, supplier_name, unresolved)

        result, warnings = validate_matches(result, unresolved, allowed_units)
        if warnings:
            print(f"{len(warnings)} validation warning(s) in AI output (invalid entries skipped):")
            for warning in warnings:
                print(f"  - {warning}")

        products_by_id = {p["id"]: p for p in products}
        write_report(unresolved, result, products_by_id)

        high_confidence = [m for m in result.matches if m.product_id and m.confidence >= AUTO_APPLY_THRESHOLD]
        print(f"AI report written: {AI_REPORT_MD}")
        print(f"High-confidence ({AUTO_APPLY_THRESHOLD}%+) suggestions: {len(high_confidence)} / {len(unresolved)}")

        if not args.apply:
            print("Report only (dry run). Use --apply to write.")
            return 0

        confirmation = input(
            f"Type exactly JA to write {len(high_confidence)} high-confidence AI suggestions "
            "to pdf_import_items.product_id: "
        ).strip()
        if confirmation != "JA":
            print("Cancelled. Nothing written.")
            return 0

        write_connection = ppm.connect_db(config)
        try:
            applied = apply_matches(write_connection, unresolved, result)
        finally:
            write_connection.close()
        print(f"{applied} rows updated.")
        return 0

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# Product Creation Mapping

Status: Analyse fuer fehlende PDF-Artikel. Es wurde noch nichts importiert.

## Gepruefte Tabellen

- `produits`
- `codebarres`
- `familles_prds`
- `param_unit`
- `invoices_details`
- `pdf_import_items`

Hinweis: Der angefragte Beispiel-SELECT `SELECT * FROM produits ORDER BY id_prd DESC LIMIT 5;` funktioniert nicht, weil `produits` keine Spalte `id_prd` hat. Der Primaerschluessel heisst `id`.

## Zentrale Spalten

| Bedeutung | Tabelle | Spalte |
| --- | --- | --- |
| Artikel-ID | `produits` | `id` |
| Artikelreferenz | `produits` | `ref_prd` |
| Artikelbezeichnung | `produits` | `lib_prd` |
| Kurzbezeichnung / Bontext | `produits` | `lib_ticket` |
| Haupteinheit | `produits` | `unite` |
| Verpackungseinheit | `produits` | `packet_unit` |
| Artikelgruppe | `produits` | `cod_fam_prd_path` |
| Artikelgruppen-Stamm | `familles_prds` | `cod_fam_prd_path`, `lib` |
| Einheiten-Stamm | `param_unit` | `cod_unit`, `lab_unit` |
| Barcode | `codebarres` | `cod_barr` |
| Barcode-Zuordnung zum Produkt | `codebarres` | `id_prd` |

## Beobachtungen aus vorhandenen Artikeln

Vorhandene Artikel nutzen:

- `ref_prd`: meist kurze interne Referenz, z. B. `02175`
- `lib_prd`: Klartextbezeichnung
- `lib_ticket`: oft identisch zu `lib_prd`
- `cod_fam_prd_path`: vorhandene Artikelgruppe, z. B. `001`
- `unite` und `packet_unit`: vorhandene Einheiten wie `Kg` oder `St`
- `id_taxclass`: wird aus der Artikelgruppe oder Vorlage uebernommen
- `sy_uk`: eindeutiger numerischer Wert; fuer Testanlage wird `MAX(sy_uk)+1` mit Eindeutigkeitspruefung verwendet

## Barcode-Regel

Barcodes liegen in `codebarres.cod_barr` und verweisen mit `codebarres.id_prd` auf `produits.id`.

Fuer PDF-Importe wird kein Barcode erfunden. Ein Barcode wird nur geplant, wenn eine Internet-/Open-Food-Facts-Suche genau einen sehr sicheren Treffer liefert. Wenn kein Internetzugriff moeglich ist, mehrere Treffer gefunden werden oder der Treffer unsicher ist, bleibt der Barcode leer und wird nur im Report dokumentiert.

## Artikelgruppe

Wenn keine sichere Kategorie ableitbar ist, wird die Gruppe `PDF Import` verwendet. Falls sie nicht existiert, plant `create_missing_products.py` deren Anlage in `familles_prds`.

## Staging-Spalte

`pdf_import_items.product_id` wird fuer die Zuordnung neu erzeugter oder gefundener Artikel verwendet. Diese Spalte gehoert zur eigenen Staging-Tabelle und nicht zu AKEAD-Haupttabellen.

## Aktueller DRY RUN

- `pdf_import_items.product_id` vorhanden: nein, wird bei JA angelegt
- Artikelgruppe: `PDF Import` / `P01`
- Neue Artikel geplant: 26

| Referenz | Artikelbezeichnung | Einheit | Gruppe | Barcode | Hinweis |
| --- | --- | --- | --- | --- | --- |
| 101567 | Eget Emre Knoblauchwurst Ring 1kg | St | P01 |  | Internet/OpenFoodFacts nicht verfuegbar: HTTP Error 503: Service Temporarily Unavailable |
| 101599 | Efepasa Pasa Knoblauchwurst 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 101600 | Efepasa Knoblauchwurst scharf 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 101557 | Eget Saray Sefasi Rinderwurst in Sch 125g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 101604 | Efepasa Arzum Geflügelwurst in Sch 200g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 101093 | Erciyes Hühnerwurst Gechnitten 200g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 100888 | Gazi Schafkäse 50% 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 100882 | Gazi Weisskäse 45% 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 100844 | Gazi Weisskäse 45% 500g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 100883 | Gazi Weisskäse 55% 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 128868 | Gazi Weisskäse 55% Kremig 500g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 100830 | Gazi Joghurt Natur 3,5% 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 127860 | Duru Rundkorn Reis 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 108563 | Duru Weizengrütze extra grob 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 127573 | Duru Vollkorn Weizengrütze grob 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 106640 | Ankara Nudeln Hörnchen 500g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 106802 | Dr. Oetker Hefe 35g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 105023 | MB schw Oliven Kuru Sele S 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 129673 | MB schw Oliven Kuru Sele XS 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 105025 | MB schw Oliven Kuru Sele 2XS 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 105024 | MB schw Oliven Kuru Sele 2XS 400g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 109712 | Köy Sefasi schw Oliven 700g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 107150 | Koska Maulbeeren Sirup 380g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 109281 | Öncü Paprikamark mild 360g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 130460 | Cicek Weisser Essig 1000ml | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 125044 | Cicek Eingelegte Rundpfefferoni scharf 1500g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |

## Aktueller DRY RUN

- `pdf_import_items.product_id` vorhanden: ja
- Artikelgruppe: `PDF Import` / `P01`
- Neue Artikel geplant: 26

| Referenz | Artikelbezeichnung | Einheit | Gruppe | Barcode | Hinweis |
| --- | --- | --- | --- | --- | --- |
| 101567 | Eget Emre Knoblauchwurst Ring 1kg | St | P01 |  | Internet/OpenFoodFacts nicht verfuegbar: HTTP Error 503: Service Temporarily Unavailable |
| 101599 | Efepasa Pasa Knoblauchwurst 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 101600 | Efepasa Knoblauchwurst scharf 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 101557 | Eget Saray Sefasi Rinderwurst in Sch 125g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 101604 | Efepasa Arzum Geflügelwurst in Sch 200g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 101093 | Erciyes Hühnerwurst Gechnitten 200g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 100888 | Gazi Schafkäse 50% 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 100882 | Gazi Weisskäse 45% 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 100844 | Gazi Weisskäse 45% 500g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 100883 | Gazi Weisskäse 55% 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 128868 | Gazi Weisskäse 55% Kremig 500g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 100830 | Gazi Joghurt Natur 3,5% 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 127860 | Duru Rundkorn Reis 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 108563 | Duru Weizengrütze extra grob 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 127573 | Duru Vollkorn Weizengrütze grob 1kg | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 106640 | Ankara Nudeln Hörnchen 500g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 106802 | Dr. Oetker Hefe 35g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 105023 | MB schw Oliven Kuru Sele S 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 129673 | MB schw Oliven Kuru Sele XS 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 105025 | MB schw Oliven Kuru Sele 2XS 800g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 105024 | MB schw Oliven Kuru Sele 2XS 400g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 109712 | Köy Sefasi schw Oliven 700g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 107150 | Koska Maulbeeren Sirup 380g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 109281 | Öncü Paprikamark mild 360g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 130460 | Cicek Weisser Essig 1000ml | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 125044 | Cicek Eingelegte Rundpfefferoni scharf 1500g | St | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |

## Aktueller DRY RUN

- `pdf_import_items.product_id` vorhanden: ja
- Artikelgruppe: `PDF Import` / `P01`
- Neue Artikel geplant: 0

| Referenz | Artikelbezeichnung | Einheit | Gruppe | Barcode | Hinweis |
| --- | --- | --- | --- | --- | --- |

## Aktueller DRY RUN

- `pdf_import_items.product_id` vorhanden: ja
- Artikelgruppe: `PDF Import` / `P01`
- Neue Artikel geplant: 0

| Referenz | Artikelbezeichnung | Einheit | Gruppe | Barcode | Hinweis |
| --- | --- | --- | --- | --- | --- |

## Aktueller DRY RUN

- `pdf_import_items.product_id` vorhanden: ja
- Artikelgruppe: `PDF Import` / `P01`
- Neue Artikel geplant: 33

| Referenz | Artikelbezeichnung | Einheit | Gruppe | Barcode | Hinweis |
| --- | --- | --- | --- | --- | --- |
| 27018 | Beybal honig syrup PET FLASCHE 300g x12st | PK | P01 |  | kein sicherer OpenFoodFacts-Treffer |
| 2262 | BE GARDEN Syruphonig OHNE WABEN 460g GL x12St | PK | P01 |  | Internet/OpenFoodFacts nicht verfuegbar: HTTP Error 503: Service Temporarily Unavailable |
| 2393 | BURAM 430g WABENHONIG im schale / tabak balx12 St4*,490 | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 3130 | Buram 1000g BLÜTENHONIG PROMO 5,99€x6st | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26223 | BURSAM KURAB.BUKLEGRANÜRSEKERL/Süße Kekse1 3,60900gx7st | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26012 | BURSAM KURABIYEVANILYALI/VanileKeks (UN)300gx71,S69t 0 | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26015 | BURSAM KURAB.BUKLEHINDIS.CEVIZ/Kokosn.keks3001g,6x970St | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26017 | BURSAM KURAB.KOKOLINGRANÜR/Bukle kakaolu300g1x,679s0t | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26512 | BURSAM 1500 Biberiye / Babyparika PET x6St* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26514 | BURSAM 1500 Lahana / Weißkohl PET 6 St* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26604 | BURSAM 1500 Jalapeno paprika PET x6 St* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26510 | BURSAM 1500 Salatalik / Gurke PET x6St* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 27134 | BURSAM 3000cc Jalapeno paprika PET x6 St* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26677 | BURSAM 660 közlen.patlican/geröstet obergi GLx2st* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 1262 | CEBEL 500g schw oliv PETcokiri L-M 231-290 x12St | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 2246 | CEBEL 450g SALAMURA gr.oliv.4XL 141-160 PET x12S3t,350 | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 1869 | CEBEL 1kg schw.Oliv COKIRI L-M 231-290 petx6st * | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 1473 | CEBEL 1kg schwrz oliv S IRI PET x6st * | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 2594 | SELEN Grüner LINDE-Minze(ihlamur-Nane) | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 27038 | Basak köfte harci / fleischbällchen 100g x12st | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 27042 | Basak adanaSiS köfte harci/ fleischbäll.65gg x12st | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26388 | CEBELl 200g Gr olive4XLsALAMURA vakum 141-160 x121,590 | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 2996 | CEBEL400g schw oliven vakum ORTA 2Xs 351-380 x12s1t,990 | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 1317 | LEZZET Et baharati LammGrillwürzsalz400g x12St* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 1627 | LEZZET 400g BARBEKÜ -cizbiz -grillx12St* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 2489 | T.ODUNPAZARI 250ml%100 NAREKSI/granatapfSosex122,990 | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 2490 | T.ODUNPAZARI 500ml%100NAREKSISI/Granatapf.sosex4,13290s | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 2903 | BASAK Pirinc unu, Reismehl 12x250gr / x12 St* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 3041 | BASAK Nohut unu /kichererbsenmehl 500gx12st* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 2825 | BASAK Misir nisastasi/mais nisast 12x200 gr / * | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 2827 | BASAK Irmik 12x500 gr / x12 St* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 3043 | BASAK Galeta unu / Semmelbrösel 250gx12st* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |
| 26509 | BURSAM 1500 Türlü tursu / Mischgemüse PET x6 St* | PK | P01 |  | OpenFoodFacts nach vorherigem Fehler uebersprungen |

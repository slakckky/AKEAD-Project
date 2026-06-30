# PDF-Staging-Import

Dieses Verzeichnis enthaelt einen sicheren Staging-Import fuer PDF-Dokumente.

Der Import schreibt nicht in AKEAD-Haupttabellen wie `orders`, `orders_details`, `invoices`, `invoices_details`, `produits`, `clients` oder `vendors`. Geschrieben wird nur in eigene Tabellen mit Prefix `pdf_import_`.

## Dateien

- `create_pdf_import_tables.sql`: Erstellt `pdf_import_documents` und `pdf_import_items`.
- `import_staging.py`: Liest die erste PDF aus `pdf_eingang`, zeigt eine Vorschau und importiert erst nach exakter Bestaetigung mit `JA`.
- `preview_document.py`: Reine Vorschau fuer PDF-Dokumente.

## Staging-Tabellen

`pdf_import_documents` speichert den Dokumentkopf.

`pdf_import_items` speichert Positionen mit diesen Spaltennamen:

- `position_no`
- `article_no`
- `article_name`
- `tax_rate`
- `kolli`
- `inhalt`
- `quantity`
- `unit`
- `price_kolli`
- `unit_price`
- `line_total`

## Beispiel-SELECTs

Letzte importierte Dokumente:

```sql
SELECT
  id,
  source_file,
  document_type,
  document_no,
  document_date,
  supplier_name,
  customer_name,
  created_at
FROM pdf_import_documents
ORDER BY id DESC
LIMIT 10;
```

Positionen zu einem Staging-Dokument:

```sql
SELECT
  document_id,
  position_no,
  article_no,
  article_name,
  tax_rate,
  kolli,
  inhalt,
  quantity,
  unit,
  price_kolli,
  unit_price,
  line_total
FROM pdf_import_items
WHERE document_id = 1
ORDER BY position_no;
```

Dublettenpruefung:

```sql
SELECT
  id,
  source_file,
  document_no
FROM pdf_import_documents
WHERE source_file = 'Bestellung_B26060012.pdf'
  AND document_no = 'B26060012';
```

## Sicherheit

Der Importer verhindert doppelte Dokumente ueber `source_file + document_no`.

Der Importer fuehrt erst nach Eingabe von exakt `JA` Schreibzugriffe aus. Diese Schreibzugriffe betreffen ausschliesslich:

- `pdf_import_documents`
- `pdf_import_items`

## AKEAD-Haupttabellen

Ein Import in `invoices`, `invoices_details`, `orders` oder andere AKEAD-Haupttabellen ist gesperrt, solange wichtige Systemfelder nicht sicher bestimmt sind.

Vor einem spaeteren AKEAD-Import muss [invoice_mapping.md](invoice_mapping.md) ohne unsichere Felder auskommen. Insbesondere gilt:

- `sy_uk` nur erzeugen, wenn die AKEAD-Bildungsregel aus vorhandenen `invoices` eindeutig erkennbar ist.
- `no_doc` nur setzen, wenn der Nummernkreis aus vorhandenen `invoices` eindeutig erkennbar ist.
- `id_org`, `id_dept` und `id_stock` nur automatisch setzen, wenn genau ein passender aktiver Datensatz existiert.
- `id_vendor` nur setzen, wenn der Lieferant eindeutig in `vendors` gefunden wird.
- `id_clt` nur setzen, wenn die Bedeutung eindeutig ist.
- Keine automatische Neuanlage von `vendors`, `clients`, `produits` oder Stock-Daten.

Wenn ein Feld unsicher ist, muss die Konsole melden:

```text
IMPORT GESTOPPT, FELD UNSICHER
```

Das Skript `analyze_invoice_safety.py` fuehrt diese Read-only-Pruefung aus und schreibt `invoice_mapping.md`.

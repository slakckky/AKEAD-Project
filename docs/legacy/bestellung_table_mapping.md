# Tabellenmapping fuer Bestellungen

Status: Analyse abgeschlossen. Es wurde nicht importiert. Verwendete SQL-Arten: `SHOW TABLES`, `DESCRIBE`, `SHOW CREATE TABLE`.

## Gepruefte Tabellen

Vorhanden:

- `orders`
- `orders_details`
- `vendors`
- `clients`
- `produits`

Nicht vorhanden, deshalb uebersprungen:

- `purchase_orders`
- `order_details`

## Ergebnis der Tabellenanalyse

### Bestellkopf

Geeigneter technischer Kandidat: `orders`

Gruende:

- Tabelle enthaelt eine Belegnummer: `no_doc`
- Tabelle enthaelt ein Belegdatum: `dat_doc`
- Tabelle enthaelt Kundenzuordnung: `id_clt`
- Tabelle enthaelt Lieferantenzuordnung: `id_vendor`
- Tabelle ist mit `orders_details.id_doc` ueber Detailpositionen verknuepfbar
- `SHOW CREATE TABLE` bestaetigt `ENGINE=InnoDB DEFAULT CHARSET=utf8`

Wichtige Spalten aus `orders`:

| PDF-Feld | Moegliches Zielfeld | Bewertung |
| --- | --- | --- |
| Belegnummer `B26060012` | `orders.no_doc` oder `orders.no_doc_cus_sup` | `no_doc` ist eindeutig, aber es muss geklaert werden, ob externe Belege dort oder in `no_doc_cus_sup` gespeichert werden. |
| Datum `16/06/2026` | `orders.dat_doc` | Passt technisch. Muss ins Format `YYYY-MM-DD` umgewandelt werden. |
| Lieferant | `orders.id_vendor` via `vendors.id` | Nur moeglich, wenn Lieferant sicher in `vendors` gefunden wird. |
| Kundename / Kundennummer | `orders.id_clt` via `clients.id` | Nur moeglich, wenn Kunde sicher in `clients` gefunden wird. |
| Lieferadresse | wahrscheinlich Adresstabellen oder `orders.id_adr_liv` | Nicht sicher aus den geprueften Tabellen ableitbar. |
| Summe / Steuer | `sous_tot`, `tot_ttc`, `tot_tva` | In der aktuellen PDF alles `0,00`; fachlich wenig belastbar. |

### Bestellpositionen

Geeigneter technischer Kandidat: `orders_details`

Gruende:

- Tabelle enthaelt Fremdschluessel auf den Kopf: `id_doc`
- Tabelle enthaelt Positionsnummer: `no_lig`
- Tabelle enthaelt Produktbezug: `id_prd`
- Tabelle enthaelt Text: `lib`
- Tabelle enthaelt Menge und Einheit: `qte`, `unite`
- Tabelle enthaelt Kolli: `colis`
- Tabelle enthaelt MwSt: `taux_tva`
- Tabelle enthaelt Preisfelder: `prix_u_ht`, `uprice_wot_curr_trf`, `tot_ht_rem`

Wichtige Spalten aus `orders_details`:

| PDF-Feld | Moegliches Zielfeld | Bewertung |
| --- | --- | --- |
| Position | `orders_details.no_lig` | Passt technisch. |
| Artikelnummer | Lookup `produits.ref_prd` -> `orders_details.id_prd` | Nur sicher, wenn Artikelnummer eindeutig in `produits.ref_prd` gefunden wird. |
| Artikelnummer alternativ | `orders_details.ref_cus_sup` | Moeglich als externe Lieferantenreferenz, falls `id_prd` nicht sicher ist. |
| Artikelname | `orders_details.lib` | Passt technisch. |
| MwSt `10%` | `orders_details.taux_tva` | Passt als Dezimalwert `10.000000`. |
| Kolli | `orders_details.colis` | Passt technisch. |
| Inhalt | `orders_details.qte_unit_prd` oder Produktstammdaten | Nicht eindeutig. In der PDF ist `Inhalt` getrennt von `Menge`; Ziel muss fachlich bestaetigt werden. |
| Menge | `orders_details.qte` | Passt technisch. |
| Einheit `St` | `orders_details.unite` | Passt technisch, Feld ist `varchar(3)`. |
| Preis je Kolli / Einheit | `uprice_wot_curr_trf`, `prix_u_ht` | In der aktuellen PDF `0,00`; fuer echte Preise muss die Bedeutung geprueft werden. |
| Positionsbetrag | `orders_details.tot_ht_rem` | Technisch moeglich, aktuell `0,00`. |

### Lookup-Tabellen

`vendors`:

- Geeignet zur Ermittlung von `orders.id_vendor`.
- Relevante Felder: `id`, `code`, `nom`.
- Problem: `nom` ist nur `varchar(30)`, der erkannte Lieferant ist laenger als 30 Zeichen. Ein direkter Namensvergleich kann unzuverlaessig sein.

`clients`:

- Geeignet zur Ermittlung von `orders.id_clt`.
- Relevante Felder: `id`, `cod_clt`, `cod_clt_four`, `nom`, Lieferadressfelder.
- PDF-Kundennummer `227494` koennte zu `cod_clt`, `cod_clt_four` oder einem externen Kundenkonto gehoeren. Das ist noch nicht sicher.

`produits`:

- Geeignet zur Ermittlung von `orders_details.id_prd`.
- Relevante Felder: `id`, `ref_prd`, `lib_prd`, `unite`, `id_taxclass`.
- PDF-Artikelnummern sehen passend fuer `ref_prd` aus, muessen aber per `SELECT` eindeutig abgeglichen werden.

## Pflichtfelder und Risiken

### `orders`

Technisch haben fast alle `NOT NULL` Felder Defaults. Fuer einen fachlich korrekten Import fehlen trotzdem sichere Werte:

- `no_doc`: Eindeutiger Bestellbeleg. Muss eindeutig und im richtigen Nummernkreis sein.
- `sy_uk`: Ist eindeutig (`UNIQUE KEY`). Default `0` ist fuer mehrere neue Datensaetze nicht verwendbar.
- `id_org`, `id_dept`: Organisation/Abteilung muessen fachlich korrekt gesetzt werden, Default `0` ist vermutlich nicht ausreichend.
- `id_clt`: Kunde muss eindeutig aus `clients` ermittelt werden.
- `id_vendor`: Lieferant muss eindeutig aus `vendors` ermittelt werden.
- `status`, `chain_status`, `typ_sal_pur`, `type_reflect`, `flag`: Haben Defaults bzw. leere Defaults, aber Bedeutung und erlaubte Werte muessen aus der Anwendung bestaetigt werden.
- `cod_currency`, `currency_reg`, Wechselkursfelder: Fuer reale Bestellungen muessen Waehrung und Kurse geklaert werden.

### `orders_details`

Technisch haben auch hier fast alle `NOT NULL` Felder Defaults. Fuer valide Positionen fehlen bzw. sind kritisch:

- `id_doc`: Muss die ID des Bestellkopfs aus `orders.id` sein.
- `no_lig`: Positionsnummer aus der PDF passt.
- `id_prd`: Produkt muss sicher ueber `produits.ref_prd` gefunden werden; sonst waere `0` fachlich unsicher.
- `uuid_detail`: Hat Default leer, ist aber indiziert und wird von der Anwendung moeglicherweise erwartet.
- `id_stock`: Default `0`; Lager/Stock muss fachlich geklaert werden.
- `unite`: Kann aus PDF kommen, muss mit Produktstamm kompatibel sein.
- `qte`, `colis`, `qte_unit_prd`: PDF liefert Werte, aber Bedeutung von `Inhalt` zu `qte_unit_prd` ist noch nicht sicher.
- Preisfelder: Aktuelle PDF hat `0,00`; Import echter Preiswerte muss gegen Systemlogik geprueft werden.

## Mapping-Vorschlag fuer die aktuelle PDF

Bestellkopf:

| PDF-Feld | Wert aus Vorschau | Zielkandidat |
| --- | --- | --- |
| Dokumenttyp | `bestellung` | Kein Import in `invoices` |
| Lieferant | `KAVAK GESELLSCHAFT M.B.H. ...` | Lookup in `vendors`, Ergebnis nach `orders.id_vendor` |
| Kundename | `AY Markt GmbH` | Lookup in `clients`, Ergebnis nach `orders.id_clt` |
| Lieferadresse | `AY Markt GmbH Gruberstrasse 53 4020 LINZ` | Nicht sicher; evtl. Adress-ID statt Freitext |
| Belegnummer | `B26060012` | `orders.no_doc` oder `orders.no_doc_cus_sup` |
| Datum | `16/06/2026` | `orders.dat_doc` |
| Kundennummer | `227494` | Lookup in `clients.cod_clt` oder `clients.cod_clt_four`, noch unklar |

Bestellpositionen:

| PDF-Feld | Zielkandidat |
| --- | --- |
| Artikelnummer | Lookup `produits.ref_prd`, Ergebnis nach `orders_details.id_prd`; optional `orders_details.ref_cus_sup` |
| Artikelname | `orders_details.lib` |
| MwSt | `orders_details.taux_tva` |
| Kolli | `orders_details.colis` |
| Inhalt | vermutlich `orders_details.qte_unit_prd`, aber unsicher |
| Menge | `orders_details.qte` |
| Einheit | `orders_details.unite` |

## Empfehlung

Import unsicher.

`orders` und `orders_details` sind sehr wahrscheinlich die passenden Tabellen fuer Bestellkopf und Bestellpositionen. Ein Import ist aber noch nicht empfohlen, bis diese Punkte geklaert sind:

- Wie `sy_uk` korrekt erzeugt wird.
- Welcher Nummernkreis fuer `orders.no_doc` gilt und ob externe Belegnummern in `no_doc_cus_sup` gehoeren.
- Wie `id_org`, `id_dept`, `id_clt`, `id_vendor`, `id_stock` und Waehrung korrekt bestimmt werden.
- Ob `Inhalt` wirklich `orders_details.qte_unit_prd` entspricht.
- Ob alle PDF-Artikelnummern eindeutig in `produits.ref_prd` gefunden werden.

## Sicherer Staging-Import

Bis diese Punkte geklaert sind, ist nur der Staging-Import in eigene Tabellen empfohlen. Dabei werden keine AKEAD-Haupttabellen beschrieben.

Zieltabellen:

- `pdf_import_documents`
- `pdf_import_items`

Korrektes Mapping fuer `pdf_import_items`:

| PDF-Feld | Staging-Spalte |
| --- | --- |
| Position | `position_no` |
| Artikelnummer | `article_no` |
| Artikelname | `article_name` |
| MwSt | `tax_rate` |
| Kolli | `kolli` |
| Inhalt | `inhalt` |
| Menge | `quantity` |
| Einheit | `unit` |
| Preis pro Kolli | `price_kolli` |
| Einkaufspreis / Einzelpreis | `unit_price` |
| Positionsbetrag | `line_total` |

Beispiel-SELECT:

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

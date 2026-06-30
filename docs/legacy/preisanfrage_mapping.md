# Preisanfrage Mapping

Status: Analyse abgeschlossen. Es wurde nichts importiert.

## Geprüfte Kandidaten

Vorhanden und per `DESCRIBE` geprüft:

- `orders`
- `orders_details`
- `orders_axes`
- `orders_tax`
- `pos_orders`
- `pos_orders_details`
- `sta_recommended_order`
- `vendors`
- `clients`

Zusätzlich geprüft, weil semantisch relevant:

- `quotations`
- `quotations_details`
- `quotations_tax`
- `offres`
- `offres_details`
- `pur_request`
- `doc_pur_folders`

## Beispieldaten

Die angeforderten Prüfungen ergaben:

```sql
SELECT * FROM orders ORDER BY id DESC LIMIT 10;
-- 0 Zeilen

SELECT * FROM orders_details ORDER BY id DESC LIMIT 20;
-- 0 Zeilen
```

Auch `orders_tax`, `orders_axes`, `quotations`, `quotations_details`, `offres`, `pur_request` und `doc_pur_folders` enthalten in der Testdatenbank keine Beispieldaten.

## Mögliche Tabellen

`orders` und `orders_details` haben dieselbe grundsätzliche Struktur wie typische AKEAD-Belegtabellen:

- Kopf: `orders`
- Positionen: `orders_details`
- Steuerzeilen: `orders_tax`
- Achsen/Kostenstellen: `orders_axes`

`quotations` und `quotations_details` sehen ebenfalls wie Angebots-/Anfragebelege aus. Ohne Datensätze ist aber nicht erkennbar, ob sie in dieser AKEAD-Installation für Verkaufsangebote, Einkaufsanfragen oder andere Vorgänge verwendet werden.

`pur_request` klingt nach Einkaufsanforderung, hat aber keine klassische Kopf-/Positionsstruktur und keine Beispieldaten.

## Unsichere Steuerfelder

Folgende Felder könnten zwischen Preisanfrage, Warenbestellung, Wareneingang und Warenrechnung unterscheiden:

- `typ_sal_pur`
- `status`
- `chain_status`
- `flag`
- `type_reflect`
- `src_type`
- `src_sy_uk`
- `ctrl_reserve`
- `is_collected`
- `prep_status`

Da `orders` leer ist, kann nicht sicher bestimmt werden, welche Werte eine Preisanfrage gegenüber Warenbestellung, Wareneingang oder Rechnung kennzeichnen.

## Pflichtfelder

Für einen sicheren Import wären mindestens diese Kopfwerte nötig:

- `id_org`
- `id_dept`
- `id_clt`
- `id_vendor`
- `no_doc`
- `dat_doc`
- `typ_sal_pur`
- `status`
- `cod_currency`
- `currency_reg`
- `exchange_rate`
- `exchange_rate_div`
- `id_stck`
- `sy_uk`
- `usr_cre`
- `dat_cre`
- `usr_upd`
- `dat_upd`

Für Positionen wären mindestens nötig:

- `id_doc`
- `uuid_detail`
- `no_lig`
- `typ_lig`
- `id_prd`
- `lib`
- `colis`
- `qte`
- `unite`
- `prix_u_ht`
- `uprice_wot_curr_trf`
- `currency_trf`
- `taux_tva`
- `tot_ht_rem`
- `ref_cus_sup`
- `usr_cre`
- `dat_cre`
- `usr_upd`
- `dat_upd`

## Bewertung

Eine sichere Preisanfrage-Zieltabelle konnte nicht nachgewiesen werden.

`orders`/`orders_details` sind strukturell möglich, aber nicht sicher, weil keine vorhandenen Belege zeigen, welche Werte für eine Preisanfrage gelten. `quotations`/`quotations_details` sind ebenfalls möglich, aber ohne Beispiele nicht eindeutig als Einkaufs-Preisanfrage belegbar.

## Empfehlung

Import in AKEAD-Haupttabellen: **nicht empfohlen**.

Automatischer Fallback für unsichere PDF-Dokumente soll deshalb aktuell nur Fehlerberichte schreiben und keinen Datensatz in `orders`, `quotations`, `invoices` oder andere AKEAD-Haupttabellen erzeugen.

Klare Begründung:

> Keine sichere Preisanfrage-Tabelle gefunden, deshalb kein Import.

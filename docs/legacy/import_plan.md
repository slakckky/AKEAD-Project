# Import-Plan PDF-Rechnungen

Status: Vorschau, noch kein Import. Das Skript fuehrt keine INSERT-, UPDATE- oder DELETE-Befehle aus.

## Sicherer Staging-Import

Fuer PDF-Dokumente wird zunaechst nur in eigene Staging-Tabellen importiert:

- `pdf_import_documents`
- `pdf_import_items`

Die AKEAD-Haupttabellen wie `orders`, `invoices`, `produits`, `clients` und `vendors` werden dabei nicht beschrieben.

Korrekte Spalten in `pdf_import_items`:

- `position_no`
- `article_no`
- `price_kolli`
- `unit_price`
- `line_total`

Beispiel-SELECT fuer Staging-Positionen:

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

## Sperre fuer AKEAD-Haupttabellen

Ein Import in `invoices` und `invoices_details` darf nicht erfolgen, solange eines dieser Felder unsicher ist:

- `sy_uk`
- `no_doc`
- `id_org`
- `id_dept`
- `id_stock`
- `id_vendor`
- `id_clt`

Bei Unsicherheit gilt:

```text
IMPORT GESTOPPT, FELD UNSICHER
```

Die Details werden in `invoice_mapping.md` dokumentiert. Neue Daten duerfen automatisch nur in `pdf_import_` Tabellen gespeichert werden.

Quelle: `pdf_eingang\Bestellung_B26060012.pdf`

## Erkannte Daten

- Lieferant: KAVAK GESELLSCHAFT M.B.H. Bayerhamer Straße 22 5020 Salzburg, Österreich 5020 SALZBURG Tel.: +43 662 87 34 11
- Rechnungsnummer: B26060012
- Rechnungsdatum: 16/06/2026
- MwSt: 10%
- Gesamtbetrag: 0,00
- Positionen: 26 erkannt

## Moegliche spaetere Zuordnung

- `vendors`: Lieferant suchen oder spaeter neu anlegen, wenn keine passende Vendor-ID existiert.
- `invoices`: Rechnungsnummer, Rechnungsdatum, Lieferant/Vendor-ID, MwSt-/Steuerbezug und Gesamtbetrag speichern.
- `invoices_details`: Jede erkannte Rechnungsposition mit Artikelnummer, Artikelname, Menge, Einkaufspreis und Positionsbetrag speichern.
- `produits`: Artikelnummer/Artikelname gegen vorhandene Produkte abgleichen; spaeter ggf. Produkt-ID in `invoices_details` referenzieren.
- `tax_rates`: Erkannte MwSt gegen vorhandene Steuersaetze abgleichen und spaeter die passende Steuer-ID verwenden.
- `clients`: Nur verwenden, falls das bestehende Schema Rechnungen zwingend einem Client zuordnet.

## Offene Punkte vor echtem Import

- Pflichtfelder, Fremdschluessel und Default-Werte aus der Tabellenstruktur pruefen.
- Eindeutigkeit der Rechnung klaeren, z. B. Vendor plus Rechnungsnummer.
- Positionsparser an echte PDF-Layouts anpassen, falls Positionen nicht stabil erkannt werden.
- Erst danach INSERT-Logik mit Transaktion und Dublettenpruefung ergaenzen.

## Tabellenstruktur aus DESCRIBE

### invoices

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| id_org | int(11) | NO | MUL | 0 |  |
| id_dept | int(11) | NO | MUL | 0 |  |
| id_clt | int(11) | NO | MUL | 0 |  |
| no_doc | varchar(16) | NO | UNI |  |  |
| uuid | varchar(50) | NO | MUL |  |  |
| ettn | varchar(50) | NO | MUL |  |  |
| no_doc_last | varchar(16) | NO |  |  |  |
| no_doc_cus_sup | varchar(20) | NO |  |  |  |
| dat_doc | date | YES | MUL |  |  |
| time_doc | time | YES |  |  |  |
| id_deal | int(11) | NO | MUL | 0 |  |
| id_quotation | int(11) unsigned | NO | MUL | 0 |  |
| id_order | int(11) | NO | MUL | 0 |  |
| id_serie | int(11) | NO | MUL | 0 |  |
| id_interv | int(11) | NO | MUL | 0 |  |
| id_vendor | int(11) | NO | MUL | 0 |  |
| sy_uk_contact | bigint(20) unsigned | NO | MUL | 0 |  |
| sy_uk_folder | bigint(20) unsigned | NO | MUL | 0 |  |
| typ_sal_pur | tinyint(4) | NO |  | 0 |  |
| type_reflect | varchar(1) | NO |  |  |  |
| type_edi | varchar(10) | NO |  |  |  |
| is_printed | tinyint(4) unsigned | NO |  | 0 |  |
| is_mailed | tinyint(4) unsigned | NO |  | 0 |  |
| edi_status | tinyint(4) unsigned | NO |  | 0 |  |
| status | varchar(2) | NO |  |  |  |
| chain_status | varchar(2) | NO |  |  |  |
| valide | tinyint(4) unsigned | NO |  | 0 |  |
| typ_doc | varchar(1) | NO |  | D |  |
| id_invoice_org | int(11) | NO |  | 0 |  |
| subject_doc | varchar(100) | NO |  |  |  |
| flag | varchar(2) | NO |  |  |  |
| no_cde_cli | varchar(20) | NO |  |  |  |
| dat_delivery | date | YES |  |  |  |
| sous_tot | decimal(24,6) | NO |  | 0.000000 |  |
| tot_ttc | decimal(24,6) | NO |  | 0.000000 |  |
| tot_tva | decimal(24,6) | NO |  | 0.000000 |  |
| tot_regl | decimal(24,6) | NO |  | 0.000000 |  |
| tot_wt_curr_reg | decimal(24,6) | NO |  | 0.000000 |  |
| tot_pay_curr_reg | decimal(24,6) | NO |  | 0.000000 |  |
| b_fac_ttc | tinyint(4) unsigned | NO |  | 0 |  |
| b_tax_manual | tinyint(4) unsigned | NO |  | 0 |  |
| regim_tva | tinyint(4) unsigned | NO |  | 1 |  |
| tot_colis | decimal(24,6) | NO |  | 0.000000 |  |
| deduct1_val | decimal(24,6) | NO |  | 0.000000 |  |
| deduct1_unt | tinyint(4) | NO |  | 1 |  |
| deduct1_lib | varchar(30) | NO |  |  |  |
| deduct2_val | decimal(24,6) | NO |  | 0.000000 |  |
| deduct2_unt | tinyint(4) | NO |  | 1 |  |
| deduct2_lib | varchar(30) | NO |  |  |  |
| cout_prd | decimal(24,6) | NO |  | 0.000000 |  |
| cout_div | decimal(24,6) | NO |  | 0.000000 |  |
| id_adr_liv | bigint(20) | NO |  | 0 |  |
| id_adr_fac | bigint(20) | NO |  | 0 |  |
| id_pay_cond | int(11) | NO |  | 0 |  |
| dat_echeance | date | YES |  |  |  |
| nb_reminder | tinyint(4) | NO |  | 0 |  |
| dat_rappel1 | date | YES |  |  |  |
| dat_rappel2 | date | YES |  |  |  |
| dat_rappel3 | date | YES |  |  |  |
| nb_dec_prix_u_fac | tinyint(4) unsigned | NO |  | 2 |  |
| nb_disc_rate | tinyint(4) unsigned | NO |  | 0 |  |
| cod_currency | varchar(3) | NO |  |  |  |
| exchange_rate | decimal(24,6) | NO |  | 0.000000 |  |
| exchange_rate_div | decimal(24,6) | NO |  | 0.000000 |  |
| currency_reg | varchar(3) | NO |  |  |  |
| exch_rate_curr_reg | decimal(24,6) | NO |  | 0.000000 |  |
| exch_rate_curr_reg_div | decimal(24,6) | NO |  | 0.000000 |  |
| exch_rate_curr_report | decimal(38,12) | NO |  | 0.000000000000 |  |
| id_stck | tinyint(4) | NO |  | 0 |  |
| stk_typ_doc | varchar(1) | NO |  |  |  |
| ship_code | varchar(10) | NO |  |  |  |
| ship_ref | varchar(50) | NO |  |  |  |
| id_carrier | int(11) | NO |  | 0 |  |
| cod_tourn | varchar(5) | NO |  |  |  |
| deb_regime | tinyint(4) unsigned | NO |  | 0 |  |
| deb_nature_trans | varchar(2) | NO |  |  |  |
| deb_cond_liv | varchar(4) | NO |  |  |  |
| deb_mod_trans | varchar(1) | NO |  |  |  |
| point_before | decimal(24,6) | NO |  | 0.000000 |  |
| point_get | decimal(24,6) | NO |  | 0.000000 |  |
| ctrl_cmpta | tinyint(4) | NO |  | 0 |  |
| withholding | tinyint(4) unsigned | NO |  | 0 |  |
| no_cashbox | tinyint(4) unsigned | NO |  | 0 |  |
| sy_uk | bigint(20) unsigned | NO | UNI | 0 |  |
| sy_dat_upd_serv | datetime | YES |  |  |  |
| sy_status | tinyint(4) | NO |  | 0 |  |
| prep_status | varchar(1) | NO |  |  |  |
| term_delivery | varchar(10) | NO |  |  |  |
| src_type | varchar(1) | NO |  |  |  |
| src_sy_uk | bigint(20) unsigned | NO |  | 0 |  |
| no_sub | smallint(6) | NO |  | 0 |  |
| ctrl_str | varchar(1000) | NO |  |  |  |
| edi_profile | varchar(1) | NO |  |  |  |
| edi_destination | varchar(100) | NO |  |  |  |
| edi_source | varchar(100) | NO |  |  |  |
| edi_param | varchar(256) | NO |  |  |  |
| export_decleration_no | varchar(20) | NO |  |  |  |
| date_export_closing | date | YES |  |  |  |
| ctrl_reserve | tinyint(4) unsigned | NO |  | 0 |  |
| is_collected | tinyint(4) unsigned | NO |  | 0 |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

### invoices_details

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | bigint(20) unsigned | NO | PRI |  | auto_increment |
| id_doc | int(11) | NO | MUL | 0 |  |
| uuid_detail | varchar(50) | NO | MUL |  |  |
| no_lig | smallint(6) | NO |  | 0 |  |
| typ_lig | varchar(1) | NO |  | N |  |
| link_detail | int(11) | NO |  | 0 |  |
| id_prd | int(11) | NO | MUL | 0 |  |
| sy_uk_var | bigint(20) unsigned | NO | MUL | 0 |  |
| id_taille | int(11) | NO |  | 0 |  |
| id_couleur | int(11) | NO |  | 0 |  |
| id_stock | int(11) | NO | MUL | 0 |  |
| lib | longtext | YES |  |  |  |
| note | varchar(255) | NO |  |  |  |
| colis | decimal(24,6) | NO |  | 0.000000 |  |
| qte | decimal(24,6) | NO |  | 0.000000 |  |
| unite | varchar(3) | NO |  |  |  |
| uprice_wot_curr_trf | decimal(24,6) | NO |  | 0.000000 |  |
| currency_trf | varchar(3) | NO |  |  |  |
| trf_exch_rate | decimal(24,6) | NO |  | 0.000000 |  |
| trf_exch_rate_div | decimal(24,6) | NO |  | 0.000000 |  |
| prix_u_ht | decimal(24,6) | NO |  | 0.000000 |  |
| qte_unit_prd | decimal(24,6) | NO |  | 0.000000 |  |
| taux_tva | decimal(24,6) | NO |  | 0.000000 |  |
| prix_revt | decimal(24,6) | NO |  | 0.000000 |  |
| cost_price_curr | decimal(24,6) | NO |  | 0.000000 |  |
| discount_rate1 | decimal(24,6) | NO |  | 0.000000 |  |
| discount_rate2 | decimal(24,6) | NO |  | 0.000000 |  |
| discount_rate3 | decimal(24,6) | NO |  | 0.000000 |  |
| tot_ht_rem | decimal(24,6) | NO |  | 0.000000 |  |
| tot_acc | decimal(24,6) | NO |  | 0.000000 |  |
| ref_cus_sup | varchar(20) | NO |  |  |  |
| chap | varchar(12) | NO |  |  |  |
| no_serie_un | varchar(30) | NO |  |  |  |
| dat_dlc_un | date | YES |  |  |  |
| note_un | varchar(20) | NO |  |  |  |
| rate_commission | decimal(24,6) | NO |  | 0.000000 |  |
| id_taxclass | int(11) | NO |  | 0 |  |
| ctrl_stock | tinyint(4) | NO |  | 0 |  |
| ctrl_cost_price | tinyint(4) | NO |  | 0 |  |
| withholding_num | tinyint(4) unsigned | NO |  | 0 |  |
| withholding_den | tinyint(4) unsigned | NO |  | 0 |  |
| fix_tax1 | decimal(24,6) | NO |  | 0.000000 |  |
| fix_tax2 | decimal(24,6) | NO |  | 0.000000 |  |
| fix_tax3 | decimal(24,6) | NO |  | 0.000000 |  |
| extra_cost_unit_prd | decimal(24,6) | NO |  | 0.000000 |  |
| tax_info | varchar(255) | NO |  |  |  |
| id_pcm_configuration | int(11) | NO |  | 0 |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

### produits

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| ref_prd | varchar(20) | NO | UNI |  |  |
| typ_prd | tinyint(4) unsigned | NO |  | 0 |  |
| lib_prd | varchar(255) | NO | MUL |  |  |
| lib_prd_rtf | longtext | YES |  |  |  |
| lib_prd_html | longtext | YES |  |  |  |
| lib_ticket | varchar(50) | NO |  |  |  |
| lib_tech | longtext | YES |  |  |  |
| cod_fam_prd_path | varchar(15) | NO | MUL |  |  |
| cod_grp_prd_path_1 | varchar(15) | NO | MUL |  |  |
| cod_grp_prd_path_2 | varchar(15) | NO | MUL |  |  |
| unite | varchar(3) | NO |  |  |  |
| packet_unit | varchar(3) | NO |  |  |  |
| packet_qty | decimal(24,6) | NO |  | 0.000000 |  |
| contenu | decimal(24,6) | NO |  | 0.000000 |  |
| unite_contenu | varchar(3) | NO |  |  |  |
| id_taxclass | int(11) | NO | MUL | 0 |  |
| id_manufacturer | int(11) | NO | MUL | 0 |  |
| id_stock | int(11) | NO | MUL | 0 |  |
| ref_manufacturer | varchar(20) | NO |  |  |  |
| seuil_qte_min | decimal(24,6) | NO |  | 0.000000 |  |
| id_process | int(11) | NO | MUL | 0 |  |
| seuil_qte_max | decimal(24,6) | NO |  | 0.000000 |  |
| stk_location_def | varchar(30) | NO |  |  |  |
| prix_revt | decimal(24,6) | NO |  | 0.000000 |  |
| uprice_wot_min | decimal(24,6) | NO |  | 0.000000 |  |
| uprice_wot_max | decimal(24,6) | NO |  | 0.000000 |  |
| qte_lot | decimal(24,6) | NO |  | 0.000000 |  |
| unite_lot | varchar(3) | NO |  |  |  |
| poids | decimal(24,6) | NO |  | 0.000000 |  |
| volume | decimal(24,6) | NO |  | 0.000000 |  |
| nb_colis | smallint(6) unsigned | NO |  | 0 |  |
| note | longtext | YES |  |  |  |
| b_calc_auto_prix_revt | tinyint(4) unsigned | NO |  | 1 |  |
| b_actif | tinyint(4) unsigned | NO | MUL | 1 |  |
| b_web | tinyint(4) unsigned | NO |  | 0 |  |
| dat_dern_inventaire | date | YES |  |  |  |
| b_a_pese_caisse | tinyint(4) unsigned | NO |  | 0 |  |
| cod_tare | varchar(20) | NO |  |  |  |
| b_multi_taille | tinyint(4) unsigned | NO |  | 0 |  |
| b_multi_couleur | tinyint(4) unsigned | NO |  | 0 |  |
| b_variant | tinyint(4) unsigned | NO |  | 0 |  |
| selected_variants | varchar(10) | NO |  |  |  |
| origine | varchar(5) | NO |  |  |  |
| categorie | varchar(4) | NO |  |  |  |
| etiq_gond_a_impr | tinyint(4) | NO |  | 0 |  |
| nomencl_nc8 | varchar(20) | NO |  |  |  |
| deb_qte_unite_duppl | decimal(24,6) | NO |  | 0.000000 |  |
| withholding_num_sal | tinyint(4) unsigned | NO |  | 0 |  |
| withholding_den_sal | tinyint(4) unsigned | NO |  | 0 |  |
| withholding_num_pur | tinyint(4) unsigned | NO |  | 0 |  |
| withholding_den_pur | tinyint(4) unsigned | NO |  | 0 |  |
| withholding_exemption_code | varchar(5) | NO |  |  |  |
| fix_tax1 | decimal(24,6) | NO |  | 0.000000 |  |
| fix_tax2 | decimal(24,6) | NO |  | 0.000000 |  |
| fix_tax3 | decimal(24,6) | NO |  | 0.000000 |  |
| weight_net | decimal(24,6) | NO |  | 0.000000 |  |
| weight_gross | decimal(24,6) | NO |  | 0.000000 |  |
| volume_net | decimal(24,6) | NO |  | 0.000000 |  |
| volume_gross | decimal(24,6) | NO |  | 0.000000 |  |
| length_net | decimal(24,6) | NO |  | 0.000000 |  |
| length_gross | decimal(24,6) | NO |  | 0.000000 |  |
| width_net | decimal(24,6) | NO |  | 0.000000 |  |
| width_gross | decimal(24,6) | NO |  | 0.000000 |  |
| height_net | decimal(24,6) | NO |  | 0.000000 |  |
| height_gross | decimal(24,6) | NO |  | 0.000000 |  |
| attribute | varchar(1000) | NO |  |  |  |
| param_prd_lie | longtext | YES |  |  |  |
| b_auto_order | tinyint(4) unsigned | NO |  | 0 |  |
| b_mobile_app | tinyint(4) unsigned | NO |  | 0 |  |
| b_not_price | tinyint(4) unsigned | NO |  | 0 |  |
| last_synch_time_pos | datetime | YES |  |  |  |
| sy_dat_upd_serv | datetime | YES |  |  |  |
| sy_uk | bigint(20) unsigned | NO | UNI | 0 |  |
| no_order | decimal(24,6) | NO |  | 0.000000 |  |
| specifications | longtext | YES |  |  |  |
| av_delivery_duration | smallint(6) unsigned | NO |  | 0 |  |
| id_default_label_model | int(11) | NO | MUL | 0 |  |
| caliber | varchar(10) | NO |  |  |  |
| pricing_type | tinyint(4) unsigned | NO |  | 0 |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

### tax_rates

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| id_tax | int(11) | NO | MUL | 0 |  |
| id_taxclass | int(11) | NO | MUL | 0 |  |
| id_taxregime | int(11) | NO | MUL | 0 |  |
| id_comp | int(11) | NO | MUL | 0 |  |
| tax_rate | decimal(24,6) | NO |  | 0.000000 |  |
| tax_order | tinyint(4) | NO |  | 0 |  |
| tax_base_code | tinyint(4) | NO |  | 1 |  |
| tax_base_formula | varchar(250) | NO |  |  |  |
| date_validity_start | date | YES |  |  |  |
| date_validity_finish | date | YES |  |  |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

### clients

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| cod_clt | varchar(15) | NO | UNI |  |  |
| cod_fam_clt_path | varchar(10) | NO | MUL |  |  |
| typ_cus_sup | tinyint(4) unsigned | NO |  | 0 |  |
| b_soc | tinyint(4) unsigned | NO |  | 0 |  |
| cod_clt_four | varchar(20) | NO |  |  |  |
| civ | varchar(5) | NO |  |  |  |
| nom | varchar(100) | NO |  |  |  |
| lname | varchar(50) | NO |  |  |  |
| pnom | varchar(20) | NO |  |  |  |
| dat_nais | date | YES |  |  |  |
| adr1 | varchar(50) | NO |  |  |  |
| adr2 | varchar(50) | NO |  |  |  |
| cod_pst | varchar(20) | NO |  |  |  |
| ville | varchar(40) | NO |  |  |  |
| cod_pays | varchar(2) | NO |  |  |  |
| adr1_liv | varchar(50) | NO |  |  |  |
| adr2_liv | varchar(50) | NO |  |  |  |
| cod_pst_liv | varchar(10) | NO |  |  |  |
| ville_liv | varchar(40) | NO |  |  |  |
| pays_liv | varchar(20) | NO |  |  |  |
| tel1 | varchar(20) | NO |  |  |  |
| tel2 | varchar(20) | NO |  |  |  |
| mobil | varchar(20) | NO |  |  |  |
| fax | varchar(20) | NO |  |  |  |
| mail | varchar(50) | NO |  |  |  |
| url | varchar(50) | NO |  |  |  |
| note | longtext | YES |  |  |  |
| edi_parameter | varchar(255) | NO |  |  |  |
| reminder_type | tinyint(4) unsigned | NO |  | 1 |  |
| niveau_trf | tinyint(4) unsigned | NO | MUL | 1 |  |
| b_fac_ht | tinyint(4) unsigned | NO |  | 0 |  |
| regim_tva | tinyint(4) unsigned | NO |  | 1 |  |
| mod_reg_def | varchar(3) | NO |  |  |  |
| del_paie | int(11) | NO |  | 0 |  |
| due_date_adj | tinyint(4) unsigned | NO |  | 0 |  |
| rib | varchar(50) | NO |  |  |  |
| cod_swift | varchar(50) | NO |  |  |  |
| cod_tourn | varchar(10) | NO |  |  |  |
| no_siret | varchar(20) | NO |  |  |  |
| cod_ape | varchar(10) | NO |  |  |  |
| no_tva | varchar(30) | NO |  |  |  |
| tax_office_cod | varchar(10) | NO |  |  |  |
| tax_no | varchar(30) | NO |  |  |  |
| dat_deb_val | date | YES |  |  |  |
| dat_fin_val | date | YES |  |  |  |
| suivie_par | varchar(15) | NO |  |  |  |
| b_actif | tinyint(4) unsigned | NO |  | 1 |  |
| tpv_mnt_credit | decimal(24,6) | NO |  | 0.000000 |  |
| id_pay_cond | int(11) | NO |  | 0 |  |
| b_auto_pay | tinyint(4) unsigned | NO |  | 0 |  |
| encours_max | decimal(24,6) | NO |  | -1.000000 |  |
| cod_currency | varchar(3) | NO |  |  |  |
| currency_reg | varchar(3) | NO |  |  |  |
| compte | varchar(15) | NO |  |  |  |
| id_vendor | int(11) | NO |  | 0 |  |
| id_langue_impr | smallint(6) unsigned | NO |  | 0 |  |
| nb_exempl_fac | smallint(6) unsigned | NO |  | 0 |  |
| msg_alerte | longtext | YES |  |  |  |
| cond_liv | longtext | YES |  |  |  |
| deb_cond_liv | varchar(4) | NO |  |  |  |
| deb_mod_trans | varchar(1) | NO |  |  |  |
| deb_nature_trans | varchar(2) | NO |  |  |  |
| deb_regime | tinyint(4) unsigned | NO |  | 0 |  |
| ship_code | varchar(10) | NO |  | 0 |  |
| b_web | tinyint(4) unsigned | NO |  | 0 |  |
| web_pwd | varchar(50) | NO |  |  |  |
| withholding_sal | tinyint(4) unsigned | NO |  | 0 |  |
| withholding_pur | tinyint(4) unsigned | NO |  | 0 |  |
| sy_uk | bigint(20) unsigned | NO | UNI | 0 |  |
| sy_dat_upd_serv | datetime | YES |  |  |  |
| global_location_number | varchar(13) | NO |  |  |  |
| id_carrier | int(11) | NO |  | 0 |  |
| delivery_sort_no | int(11) unsigned | NO |  | 0 |  |
| ticket_printing_option | tinyint(4) unsigned | NO |  | 0 |  |
| tax_no_check_datetime | datetime | YES |  |  |  |
| tax_no_check_status | smallint(6) unsigned | NO |  | 0 |  |
| vat_no_check_datetime | datetime | YES |  |  |  |
| vat_no_check_status | tinyint(4) | NO |  | 0 |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

### vendors

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| code | varchar(20) | NO | UNI |  |  |
| nom | varchar(30) | NO | UNI |  |  |
| id_stck | tinyint(4) | NO |  | 0 |  |
| b_actif | tinyint(4) unsigned | NO |  | 0 |  |
| no_sub | smallint(6) | NO |  | 0 |  |
| cod_tour | varchar(100) | NO |  |  |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

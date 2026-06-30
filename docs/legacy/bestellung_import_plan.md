# Import-Plan Bestellungen

Status: Nur Analyse und Vorschau. Es wurden keine INSERT-, UPDATE- oder DELETE-Befehle ausgefuehrt.

Erkannter Dokumenttyp: `rechnung`

## Ergebnis

Das Dokument wurde als Rechnung erkannt. Diese Datei behandelt hier nur die Vorschau.

## Suche nach moeglichen Bestell-Tabellen

Es wurde `SHOW TABLES` ausgefuehrt und nach diesen Namensbestandteilen gesucht:
`order`, `orders`, `purchase`, `command`, `commande`, `supplier`, `vendor`, `document`

Anzahl Tabellen gesamt: 363
Namens-Kandidaten: orders, orders_axes, orders_details, orders_tax, pdf_import_documents, pdf_import_vendor_layouts, pos_orders, pos_orders_details, sta_recommended_order, vendor_goals, vendors

Moegliche Bestell-Tabelle(n) nach Namens- und Spaltenpruefung: orders
Trotzdem ist vor einem Import eine fachliche Bestaetigung der Zieltabellen erforderlich.

## Kandidaten-Struktur

### orders

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| id_org | int(11) | NO | MUL | 0 |  |
| id_dept | int(11) | NO | MUL | 0 |  |
| id_clt | int(11) | NO | MUL | 0 |  |
| no_doc | varchar(16) | NO | UNI |  |  |
| no_doc_cus_sup | varchar(20) | NO |  |  |  |
| dat_doc | date | YES | MUL |  |  |
| id_deal | int(11) | NO | MUL | 0 |  |
| id_quotation | int(11) unsigned | NO | MUL | 0 |  |
| id_serie | int(11) | NO | MUL | 0 |  |
| id_interv | int(11) | NO | MUL | 0 |  |
| id_vendor | int(11) | NO | MUL | 0 |  |
| sy_uk_contact | bigint(20) unsigned | NO | MUL | 0 |  |
| typ_sal_pur | tinyint(4) | NO |  | 0 |  |
| status | varchar(2) | NO | MUL |  |  |
| chain_status | varchar(2) | NO |  |  |  |
| flag | varchar(2) | NO |  |  |  |
| type_reflect | varchar(1) | NO |  |  |  |
| is_printed | tinyint(4) unsigned | NO |  | 0 |  |
| is_mailed | tinyint(4) unsigned | NO |  | 0 |  |
| subject_doc | varchar(100) | NO |  |  |  |
| no_cde_cli | varchar(20) | NO |  |  |  |
| dat_delivery_wanted | date | YES |  |  |  |
| dat_delivery_planned | date | YES |  |  |  |
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
| ship_code | varchar(10) | NO |  |  |  |
| ship_ref | varchar(50) | NO |  |  |  |
| id_carrier | int(11) | NO |  | 0 |  |
| withholding | tinyint(4) unsigned | NO |  | 0 |  |
| term_time | tinyint(4) | NO |  | -1 |  |
| sy_uk | bigint(20) unsigned | NO | UNI | 0 |  |
| sy_dat_upd_serv | datetime | YES |  |  |  |
| sy_status | tinyint(4) | NO |  | 0 |  |
| prep_status | varchar(1) | NO |  |  |  |
| no_sub | smallint(6) | NO |  | 0 |  |
| src_type | varchar(1) | NO |  |  |  |
| src_sy_uk | bigint(20) unsigned | NO |  | 0 |  |
| ctrl_reserve | tinyint(4) unsigned | NO |  | 0 |  |
| is_collected | tinyint(4) unsigned | NO |  | 0 |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

### orders_axes

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| id_doc | int(11) | NO | MUL | 0 |  |
| axe_type | varchar(1) | NO |  |  |  |
| axe_code | varchar(20) | NO |  |  |  |
| amount | decimal(24,6) | NO |  | 0.000000 |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

### orders_details

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
| ref_cus_sup | varchar(20) | NO |  |  |  |
| chap | varchar(12) | NO |  |  |  |
| no_serie_un | varchar(30) | NO |  |  |  |
| id_taxclass | int(11) | NO |  | 0 |  |
| ctrl_stock | tinyint(4) | NO |  | 0 |  |
| ctrl_cost_price | tinyint(4) | NO |  | 0 |  |
| withholding_num | tinyint(4) unsigned | NO |  | 0 |  |
| withholding_den | tinyint(4) unsigned | NO |  | 0 |  |
| fix_tax1 | decimal(24,6) | NO |  | 0.000000 |  |
| fix_tax2 | decimal(24,6) | NO |  | 0.000000 |  |
| fix_tax3 | decimal(24,6) | NO |  | 0.000000 |  |
| supply_duration | smallint(6) unsigned | NO |  | 0 |  |
| dat_delivery_planned | date | YES |  |  |  |
| extra_cost_unit_prd | decimal(24,6) | NO |  | 0.000000 |  |
| tax_info | varchar(255) | NO |  |  |  |
| id_pcm_configuration | int(11) | NO |  | 0 |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

### orders_tax

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | bigint(20) unsigned | NO | PRI |  | auto_increment |
| id_doc | int(11) | NO | MUL | 0 |  |
| id_tax | int(11) | NO |  | 0 |  |
| id_taxclass | int(11) | NO |  | 0 |  |
| tax_rate | decimal(24,6) | NO |  | 0.000000 |  |
| tax_base | decimal(24,6) | NO |  | 0.000000 |  |
| tax_amount | decimal(24,6) | NO |  | 0.000000 |  |
| withholding_num | tinyint(4) unsigned | NO |  | 0 |  |
| withholding_den | tinyint(4) unsigned | NO |  | 0 |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

### pdf_import_documents

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| source_file | varchar(255) | NO | MUL |  |  |
| document_type | varchar(30) | NO | MUL |  |  |
| document_no | varchar(50) | NO | MUL |  |  |
| document_date | date | YES |  |  |  |
| supplier_name | varchar(255) | NO |  |  |  |
| customer_name | varchar(255) | NO |  |  |  |
| customer_no | varchar(50) | NO |  |  |  |
| delivery_address | varchar(255) | NO |  |  |  |
| raw_text | mediumtext | YES |  |  |  |
| import_status | varchar(30) | NO |  | staged |  |
| created_at | datetime | NO |  |  |  |
| processing_notes | text | YES |  |  |  |
| layout_signature | varchar(255) | NO |  |  |  |
| ocr_used | tinyint(4) unsigned | NO |  | 0 |  |
| is_safe_invoice | tinyint(4) unsigned | NO |  | 0 |  |

### pdf_import_vendor_layouts

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| supplier_name | varchar(255) | NO | MUL |  |  |
| document_type | varchar(30) | NO |  |  |  |
| layout_signature | varchar(255) | NO |  |  |  |
| columns_detected | text | YES |  |  |  |
| line_pattern | text | YES |  |  |  |
| sample_source_file | varchar(255) | NO |  |  |  |
| sample_document_no | varchar(50) | NO |  |  |  |
| confidence | decimal(8,4) | NO |  | 0.0000 |  |
| created_at | datetime | NO |  |  |  |
| updated_at | datetime | NO |  |  |  |

### pos_orders

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| no_order | varchar(20) | NO | UNI |  |  |
| id_clt | int(11) | NO | MUL | 0 |  |
| status_order | varchar(2) | NO |  |  |  |
| date_order | datetime | YES |  |  |  |
| datetime_delivery | datetime | YES |  |  |  |
| datetime_delivery_wanted | datetime | YES |  |  |  |
| note | varchar(2000) | NO |  | 0 |  |
| sy_uk | bigint(20) unsigned | NO | UNI | 0 |  |
| location | varchar(10) | NO |  |  |  |
| no_sub | smallint(6) | NO |  | 0 |  |
| dat_cre | date | YES |  |  |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |

### pos_orders_details

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| id_order | int(11) | NO | MUL | 0 |  |
| id_prd | int(11) | NO | MUL | 0 |  |
| id_ref | int(11) | NO |  | 0 |  |
| no_order_detail | varchar(20) | NO |  |  |  |
| id_size | int(11) | NO |  | 0 |  |
| id_color | int(11) | NO |  | 0 |  |
| sy_uk_var | bigint(20) unsigned | NO | MUL | 0 |  |
| status_line | varchar(2) | NO |  |  |  |
| qte | decimal(24,6) | NO |  | 0.000000 |  |
| unite | varchar(3) | NO |  |  |  |
| note | varchar(2000) | NO |  | 0 |  |
| attribute | varchar(60) | NO |  |  |  |
| link_detail | int(11) | NO |  | 0 |  |
| type_line | varchar(1) | NO |  |  |  |
| package_no | varchar(10) | NO |  |  |  |
| course_no | smallint(6) unsigned | NO |  | 0 |  |
| to_print | tinyint(4) unsigned | NO |  | 1 |  |
| dat_upd_status_line | datetime | YES |  |  |  |
| datetime_send_prod | datetime | YES |  |  |  |
| datetime_start_prod | datetime | YES |  |  |  |
| datetime_finish_prod | datetime | YES |  |  |  |
| datetime_in_workshop | datetime | YES |  |  |  |
| datetime_out_workshop | datetime | YES |  |  |  |
| dat_cre | date | YES |  |  |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |

### sta_recommended_order

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| id_prd | int(11) | NO | MUL | 0 |  |
| sy_uk_var | bigint(20) unsigned | NO | MUL | 0 |  |
| order_period | smallint(6) unsigned | NO |  | 0 |  |
| average_qty | decimal(24,6) | NO |  | 0.000000 |  |
| recommended_qty | decimal(24,6) | NO |  | 0.000000 |  |
| usr_cre | varchar(15) | NO |  |  |  |
| dat_cre | datetime | YES |  |  |  |
| usr_upd | varchar(15) | NO |  |  |  |
| dat_upd | datetime | YES |  |  |  |

### vendor_goals

| Feld | Typ | Null | Key | Default | Extra |
| --- | --- | --- | --- | --- | --- |
| id | int(11) unsigned | NO | PRI |  | auto_increment |
| typ_goal | varchar(1) | NO |  |  |  |
| goal_value | decimal(24,6) | NO |  | 0.000000 |  |
| id_vendor | int(11) | NO | MUL | 0 |  |
| goal_year | smallint(6) unsigned | NO |  | 0 |  |
| goal_month | tinyint(4) unsigned | NO |  | 0 |  |
| cod_fam_prd_path | varchar(15) | NO | MUL |  |  |
| id_pay_cond | int(11) | NO |  | 0 |  |
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

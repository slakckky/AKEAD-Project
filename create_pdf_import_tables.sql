CREATE TABLE IF NOT EXISTS `pdf_import_documents` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `source_file` varchar(255) NOT NULL DEFAULT '',
  `document_type` varchar(30) NOT NULL DEFAULT '',
  `document_no` varchar(50) NOT NULL DEFAULT '',
  `document_date` date DEFAULT NULL,
  `supplier_name` varchar(255) NOT NULL DEFAULT '',
  `customer_name` varchar(255) NOT NULL DEFAULT '',
  `customer_no` varchar(50) NOT NULL DEFAULT '',
  `delivery_address` varchar(255) NOT NULL DEFAULT '',
  `raw_text` mediumtext,
  `import_status` varchar(30) NOT NULL DEFAULT 'staged',
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pdf_import_source_doc` (`source_file`, `document_no`),
  KEY `idx_pdf_import_document_type` (`document_type`),
  KEY `idx_pdf_import_document_no` (`document_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE IF NOT EXISTS `pdf_import_items` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `document_id` int(11) unsigned NOT NULL,
  `position_no` int(11) NOT NULL DEFAULT '0',
  `article_no` varchar(50) NOT NULL DEFAULT '',
  `product_id` int(11) unsigned NULL DEFAULT NULL,
  `article_name` varchar(255) NOT NULL DEFAULT '',
  `tax_rate` varchar(20) NOT NULL DEFAULT '',
  `kolli` decimal(24,6) NOT NULL DEFAULT '0.000000',
  `inhalt` decimal(24,6) NOT NULL DEFAULT '0.000000',
  `quantity` decimal(24,6) NOT NULL DEFAULT '0.000000',
  `unit` varchar(10) NOT NULL DEFAULT '',
  `price_kolli` decimal(24,6) NOT NULL DEFAULT '0.000000',
  `unit_price` decimal(24,6) NOT NULL DEFAULT '0.000000',
  `line_total` decimal(24,6) NOT NULL DEFAULT '0.000000',
  `raw_line` text,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_pdf_import_items_document_id` (`document_id`),
  KEY `idx_pdf_import_items_article_no` (`article_no`),
  KEY `idx_pdf_import_items_product_id` (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE IF NOT EXISTS `pdf_import_vendor_layouts` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `supplier_name` varchar(255) NOT NULL DEFAULT '',
  `document_type` varchar(30) NOT NULL DEFAULT '',
  `layout_signature` varchar(255) NOT NULL DEFAULT '',
  `columns_detected` text,
  `line_pattern` text,
  `sample_source_file` varchar(255) NOT NULL DEFAULT '',
  `sample_document_no` varchar(50) NOT NULL DEFAULT '',
  `confidence` decimal(8,4) NOT NULL DEFAULT '0.0000',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pdf_import_vendor_layout` (`supplier_name`, `layout_signature`),
  KEY `idx_pdf_import_vendor_layout_supplier` (`supplier_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE IF NOT EXISTS `pdf_import_preisanfragen` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `document_id` int(11) unsigned NOT NULL,
  `source_file` varchar(255) NOT NULL DEFAULT '',
  `document_type` varchar(30) NOT NULL DEFAULT '',
  `document_no` varchar(50) NOT NULL DEFAULT '',
  `supplier_name` varchar(255) NOT NULL DEFAULT '',
  `reason` varchar(255) NOT NULL DEFAULT '',
  `item_count` int(11) NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pdf_import_preisanfrage_doc` (`document_id`),
  KEY `idx_pdf_import_preisanfrage_type` (`document_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

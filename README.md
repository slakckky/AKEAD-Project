# AKEAD Invoice Matcher

PDF faturaları okuyup AKEAD'in MySQL veritabanindaki urunlerle eslestiren masaustu uygulamasi.
Tkinter (Python) ile yazilmistir, Mac ve Windows'ta calisir.

## Mimari (6 aktif dosya)

```
app.py                      → Tkinter GUI (ana giris noktasi)
auto_pdf_import.py          → PDF parser: metin/tablo cikarimi, staging DB'ye yazma
professional_product_match.py → Kural tabanli urun eslestirme (exact / barcode / fuzzy)
ai_product_match.py         → Claude AI ile zor eslestirmeler icin oneri
import_to_invoices.py       → Onayli eslestirmeleri gercek AKEAD tablolarina aktarma
test_db.py                  → MySQL baglanti testi (yardimci arac)
```

```
create_pdf_import_tables.sql → Staging tablolari sema SQL'i
requirements.txt             → Python bagimliliklari
setup.bat                    → Windows kurulum (venv + pip install)
start_akead_importer.bat     → Windows baslatic
```

## 5 Adimli Is Akisi (GUI)

```
1. Fatura Yukle     → PDF'i pdf_eingang/ klasorune kopyalar
2. Onizle           → auto_pdf_import.py --preview (DB'ye yazmadan satirlari gosterir)
3. Sisteme Kaydet   → auto_pdf_import.py (pdf_import_documents + pdf_import_items tablolarina yazar)
4. Urun Eslestirme  → professional_product_match.py (kural tabanli)
                     → ai_product_match.py (AI onerisi, istenirse)
5. Faturayi Tamamla → import_to_invoices.py (AKEAD invoices tablolarina aktarim)
```

Her yazma adimi onay gerektirir (dry-run + JA/NEIN).

## Kurulum

### Windows (ofis PC)

```bat
:: Tek seferlik kurulum:
setup.bat

:: Sonraki kullanimlarda:
start_akead_importer.bat
```

### Mac / Linux (gelistirme)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --prefer-binary -r requirements.txt
python app.py
```

## Konfigurasyun (.env)

Proje dizininde `.env` dosyasi olusturun:

```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=codex_read
DB_PASSWORD=sifreniz
DB_NAME=datenbank
ANTHROPIC_API_KEY=sk-ant-...
```

`ANTHROPIC_API_KEY` olmadan adim 1-3 ve 4a (kural tabanli eslestirme) tam calisir.
Sadece "AI'dan Oneri Al" butonu API anahtari gerektirir.

MySQL sunucusu ofis PC'sindedir (127.0.0.1); uygulamayi o PC'de calistirin.

## Barkod Eslestirme

### Faturada barkod VARSA (EAN-8 / EAN-13 / EAN-14)

`auto_pdf_import.py` her satirin `raw_line` alanina tum hucre degerlerini yazar.
`professional_product_match.py`'daki `barcode_candidates()` bu alanda
`\b\d{8,14}\b` regex'iyle barkodlari otomatik bulur ve AKEAD'in `codebarres`
tablosunda arar.

Ornek: Hunkar / SRGL faturasindaki EAN-13 kodlari (3760091938473 vb.)
otomatik eslenir.

### Faturada barkod YOKSA

Sirali eslestirme stratejisi:

1. **Tam referans kodu** → `produits.ref_prd` ile birebir eslesme
2. **Barkod** → `codebarres.barcode` tablosu (ham satirdan regex ile)
3. **Bulanik isim** → `difflib.SequenceMatcher` ile urun adi benzerligi
4. **AI onerisi** → Claude `claude-opus-4-8` - eksik, kisaltilmis veya
   dil farki olan isimler icin (orn. "Honig Sy" → "Honig Sirup")

Bu 4 katman birlestigi icin barkod olmayan faturalar da yuksek eslesme
orani saglar.

### Barkod bulunamayan urunler

`professional_product_match.py` raporu (`product_match_report.md`) soyle siniflandirir:

- `auto_match` → yuksek guvenli, otomatik eslendi
- `vorschlag` → onerisi var, manual onay bekliyor
- `manuell_pruefen` → eslesme bulunamadi, AI'a gonderilir

`manuell_pruefen` satirlar `ai_product_match.py` ile Claude'a gonderilir.
Claude AKEAD urun listesinden en olasi eslemeyi secer; yoksa `no_match`
doner (barkod uydurmaz).

## Desteklenen Fatura Formatlari

| Tedarikci | Format | Barkod | Pozisyon |
|-----------|--------|--------|----------|
| Brajlovic GmbH | Serbest metin (pdfplumber) | Yok | 88+ |
| Bursam e.K. / AY Market | Tablo | Yok | 33 |
| Onkel-Sahingoz / Bazar | Serbest metin | Yok | 56+ |
| Demka GmbH | Tablo | Yok | 56 |
| SRGL KG / Hunkar | Ozel matris tablo | EAN-13 | 11 |

## MySQL Staging Semasi

```sql
-- Sema dosyasi:
create_pdf_import_tables.sql
```

Iki staging tablosu:
- `pdf_import_documents` → fatura baslik bilgisi
- `pdf_import_items` → fatura kalemleri (bir belgeye bagli)

Gercek AKEAD tablolari (orders, invoices, produits, clients, vendors)
sadece adim 5'te yazilir.

## Platform Notlari

### Windows
- `app.py` iki farkli Python yolu dener:
  `.venv\Scripts\python.exe` (Windows) / `.venv/bin/python3` (Mac/Linux)
- Yanlis Python'la baslarsa `subprocess.Popen` ile `.venv` Python'uyla
  kendini yeniden baslatir

### Mac
- `os.execv()` ile `.venv` Python'una gecis yapar
- Klasor/dosya acma: `open` komutu kullanilir

## Hassas Dosyalar (asla commit etme)

`.gitignore` bunlari disarda tutar:
- `.env` - DB sifresi ve API anahtari
- `pdf_eingang/`, `pdf_importiert/`, `pdf_fehler/` - gercek musteri faturalari
- `*.csv`, `*.md` (raporlar haric)
- `backup_vor_codex.sql`, `debug_*.txt`

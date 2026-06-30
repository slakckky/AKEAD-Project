# AKEAD Invoice Matcher

AKEAD icin fatura (invoice) tarama ve barkod/referans eslestirme projesi.
Toptancilardan/marketlerden gelen PDF faturalari okuyup, AKEAD'in gercek
MySQL veritabanindaki urunlerle (ve onlarin barkodlariyla) eslestirmeyi
hedefler.

## Amac

- PDF faturalari taratip (scan) icerigini extract etmek.
- Fatura satirindaki tedarikci urun kodunu/adini AKEAD'deki urune (`produits`)
  eslestirmek; o urunun AKEAD'de zaten kayitli barkodu varsa, faturadaki
  referans numarasiyla iliskilendirmek. Faturalarda genelde barkod
  basilmiyor - barkod AKEAD'in kendi veritabanindan geliyor, fatura sadece
  "bu referans numarasi su urune ait" bilgisini tasiyor.
- Eslestirme sonucunda AKEAD'deki hicbir barkodun bosta (eslesmemis)
  kalmamasini saglamak.

## Gelisim hikayesi (neler yapildi, sirasiyla)

Proje su asamalardan gecti:

1. **Baslangic - sade bir PDF tarayici.** Ilk adimda elimizde hicbir
   gercek fatura ornegi yokken, genel amacli bir PDF tarama araci
   yazildi: [scan_invoice.py](scan_invoice.py). pdfplumber ile metin/tablo
   cikarir, taranmis (gorsel) PDF'lerde OCR'a (pytesseract + Poppler)
   duser, sonucu JSON olarak kaydeder. Olasi barkod numaralarini
   (8/12/13/14 haneli rakam dizileri) regex ile isaretler.

2. **Web arayuzu denemesi (sonradan iptal edildi).** Kullanici icin
   basit bir arayuz istendiginde once Streamlit (tarayici tabanli)
   secildi: dosya yukle, "Tara" tusu, sonuc tablosu. Bu calisiyordu
   ve test edildi, ama asagida 4. adimda aciklanan nedenle daha sonra
   **iptal edildi** - proje artik Streamlit kullanmiyor.

3. **MySQL baglanti altyapisi.** AKEAD'in MySQL kullandigi, ama henuz
   tablo semasinin bilinmedigi soylendi. Genel bir baglanti modulu
   ([db.py](db.py), SQLAlchemy + PyMySQL, `.env` ile yapilandirilir)
   hazirlandi - henuz gercek sorgu icermiyordu.

4. **Donum noktasi: hazir, gercek bir proje bulundu.** Kullanici
   Desktop'taki `akead_codex_test.zip` dosyasini paylasti. Bu, baska bir
   AI ajani ("codex") tarafindan daha once gelistirilmis, **gercek AKEAD
   MySQL veritabanina baglanan**, cok daha olgun bir projeydi: gercek
   tablolar (`orders`, `invoices`, `produits`, `clients`, `vendors`),
   guvenlik amacli bir staging katmani (`pdf_import_documents`/
   `pdf_import_items`), urun/barkod eslestirme script'leri, ve gercek bir
   ornek fatura (Brajlovic GmbH, 10 sayfa, 181 kalem).

   Bu zip derinlemesine incelendi (mimari, gercek MySQL semasi, guvenlik
   kurallari, hangi script'in calistigi/calismadigi, ornek faturanin
   icerigi). Onemli bulgu: **gercek faturalarda barkod yok**, sadece
   tedarikcinin kendi urun kodu var. Barkod AKEAD'in kendi
   veritabanindan geliyor - yani asil is, fatura satirini dogru urune
   eslestirip, o urunun zaten kayitli barkodunu faturadaki referansla
   iliskilendirmek.

   Bu netligin isiginda, sifirdan basit bir versiyon yazmak yerine
   **mevcut projeyi temel almaya** karar verildi.

5. **Entegrasyon.** Zip'teki proje bu repoya tasindi:
   - Hassas/buyuk dosyalar (gercek musteri faturasi, 20 MB SQL backup,
     DB sifresi iceren `.env`) **bilerek git'e dahil edilmedi** (asagida
     "Hassas dosyalar" bolumune bakin) - sadece kod ve semaya
     calisabilmek icin lokal diskte tutuldu.
   - Isim catismasi cozuldu: zip'teki `app.py` (Tkinter masaustu
     arayuzu) gecici olarak `desktop_gui.py` yapildi, cunku o sirada
     Streamlit arayuzu `app.py` adini kullaniyordu.
   - `scan_invoice.py`, projenin **tek PDF-okuma noktasi** haline
     getirildi: `scan_or_load()` fonksiyonu eklendi - bir PDF icin JSON
     daha once cikarilmissa onu okur, yoksa tarar ve kaydeder. Boylece
     `import_staging.py` artik kendi pdfplumber kodunu calistirmiyor,
     `scan_invoice`'in urettigi JSON'u kullaniyor (kod tekrari
     kaldirildi).
   - Bu degisiklik test edilirken bir regresyon yakalandi ve duzeltildi:
     `import_staging.py`'nin orijinal kodu pdfplumber'i ozel
     `x_tolerance=1, y_tolerance=3` ayariyla cagiriyordu (dar kolonlari
     ayirt etmek icin); bu ayar `scan_invoice.py`'a tasinirken atlanmisti,
     gercek faturayla test edilince fark edildi ve eklendi.
   - Inceleme sirasinda bulunan iki gercek hata duzeltildi (test edilerek
     dogrulandi):
     - `import_to_invoices.py`: `parse_decimal_safe()` fonksiyonunun
       govdesi yanlislikla baska bir fonksiyonun icinde erisilemez kod
       olarak duruyordu.
     - `auto_pdf_import.py`: rapor CSV dosyasi baska bir programda
       (orn. Excel) aciksa `PermissionError` ile tum import cokuyordu;
       artik sadece uyari basiyor, veritabani yazimini etkilemiyor.

6. **Streamlit'in iptali, masaustu arayuzun ana arayuz olmasi.** Web
   arayuzu yerine, zip'ten gelen Tkinter masaustu arayuzunun
   gelistirilmesine karar verildi. `app.py` (Streamlit) silindi,
   `desktop_gui.py` tekrar `app.py` olarak adlandirildi - artik projenin
   **tek ve ana arayuzu** bu. `requirements.txt`'ten `streamlit`
   kaldirildi.

7. **GitHub'a push (private repo, arkadasla ortak gelistirme icin).**
   Hassas dosyalar (`.env`, `backup_vor_codex.sql`, gercek musteri
   faturasi, raporlar) push'tan once tek tek kontrol edilip disarida
   birakildi. Repo: `https://github.com/slakckky/AKEAD-Project`.

8. **app.py temizligi.** Birlikte gelistirmeye baslamadan once GUI'deki
   sorunlar giderildi:
   - `os.startfile(...)` (sadece Windows'ta var) yerine platforma gore
     `open`/`xdg-open`/`os.startfile` secen `_open_path()` eklendi -
     artik macOS/Linux'ta da klasor/dosya acma butonlari calisiyor.
   - "Auto-Import starten" butonu kaldirildi - `auto_import_all.py`'nin
     invoice/orders/preisanfrage rotalari kod icinde kalici olarak
     kapali (`False`) oldugu icin bu buton hicbir zaman gercek bir is
     yapmiyordu, sadece kafa karistiriyordu.
   - Tum buton/dialog metinleri Turkce'ye cevrildi. **Istisna:**
     `_looks_like_dry_run()` / `_output_blocks_import()` icindeki
     Almanca anahtar kelimeler **bilerek cevrilmedi** - bunlar arka
     plandaki script'lerin (hala Almanca yazilmis) gercek konsol
     ciktisiyla eslesiyor, cevrilirse algilama bozulur.
   - Yeni buton: "PDF -> JSON (onizle / AI'a hazirla)" - artik GUI'den
     dogrudan `scan_invoice.py` calistirilabiliyor (daha once GUI sadece
     `auto_pdf_import.py`'yi kullaniyordu, `scan_invoice.py` entegrasyonu
     GUI'ye hic baglanmamisti).
   - `fix_brajlovic_invoice.py` silindi - tek bir faturaya (Brajlovic,
     `document_id=3`) ozel, hicbir yerden cagrilmayan bir kerelik yama
     script'iydi.

## Mimari: guvenli, kademeli akis

Hicbir script gercek AKEAD ana tablolarina (`orders`, `invoices`, `produits`,
`clients`, `vendors`) dogrudan yazmaz. Akis:

1. **PDF -> JSON** ([scan_invoice.py](scan_invoice.py)): Her PDF, pdfplumber ile
   taranir (gerekirse OCR'a duser), sayfa sayfa metin/tablo/olasi-barkod
   bilgisiyle `extracted/<dosya>.json` olarak kaydedilir. Bu, projedeki
   **tek** PDF-okuma noktasidir - butun diger script'ler PDF'i tekrar acmak
   yerine bu JSON'u (`scan_or_load()` ile) okur/onbellekler.
2. **JSON -> Staging** ([import_staging.py](import_staging.py)): JSON'daki
   metni alip baslik (tedarikci, fatura no, tarih) ve kalem (urun no, miktar,
   fiyat) alanlarina ayristirir, `pdf_import_documents` / `pdf_import_items`
   adinda **ayri staging tablolarina** yazar - sadece tam olarak `JA` yazip
   onaylandiktan sonra.
3. **Urun eslestirme** ([professional_product_match.py](professional_product_match.py)):
   Staging'deki kalemleri AKEAD `produits` tablosundaki urunlerle eslestirir
   (sirayla: tam referans kodu -> barkod -> bulanik isim eslesmesi). Sonucu
   `product_match_report.md/csv` olarak raporlar, yazma icin yine `JA` ister.
   Raporda **barkodu eksik kalan** ve **manuel kontrol gereken** satirlar
   ayri, gozden kacmayacak bolumlerde isaretlenir.
3b. **AI destekli eslestirme** ([ai_product_match.py](ai_product_match.py)):
   Yukaridaki adimin "manuel kontrol" / "vorschlag" olarak biraktigi
   satirlari (orn. fatura kisaltmasi yuzunden - "Honig Sy" -> aslinda
   "Honig Sirup") Claude'a (model: `claude-opus-4-8`) gonderip en olasi
   AKEAD urununu bulmasini ister. Sadece rapor uretir (`ai_match_report.md/csv`);
   `--apply` ile calistirilirsa bile sadece yuksek guvenli (>=85) oneriler,
   yine tam `JA` onayiyla yazilir. AI hicbir zaman barkod uydurmaz.
4. **Ana tablolara aktarim** ([import_to_invoices.py](import_to_invoices.py)):
   Sadece bu adim gercek `invoices`/`invoices_details` tablolarina yazar -
   ve sadece sistem alanlarinin (`sy_uk`, `no_doc`, `id_vendor` vb.) kurali
   kesin biliniyorsa. Emin degilse konsola `IMPORT GESTOPPT, FELD UNSICHER`
   yazip durur. `orders` ve `preisanfrage` (teklif) hedefleri henuz guvenli
   bulunmadigi icin bu adim onlar icin tamamen kapali.

`auto_import_all.py` bu adimlari zincirleyen bir orkestratordur; bugun
itibariyle invoice/orders/preisanfrage rotalari guvenlik geregi kapali
durur (no-op).

## Bilinen sinirlamalar

- `import_staging.py`'deki kalem-satiri regex'i her tedarikci formatinda
  calismiyor (orn. Brajlovic faturasinda 0 kalem buluyor, cunku o faturanin
  kolon sirasi farkli). Daha guvenilir sonuc icin `auto_pdf_import.py`
  camelot tabanli tablo cikarimi kullaniyor (ayni faturada 181 kalem).
- Urun otomatik eslestirme bilincli olarak temkinli: sadece yuksek guvenli
  eslesmeler otomatik kabul edilir, gerisi "manuel kontrol" olarak isaretlenir.
- `ai_product_match.py` henuz gercek bir Claude API anahtariyla, gercek
  MySQL verisiyle test edilmedi (bu ortamda ne API anahtari ne DB erisimi
  var) - mantik birim testlerle (sahte veriyle) dogrulandi, ama uctan uca
  gercek bir calistirma henuz yapilmadi.

## Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --prefer-binary -r requirements.txt

# OCR icin (taranmis/gorsel faturalar) sistem bagimliliklari (macOS):
brew install poppler tesseract tesseract-lang

# MySQL baglantisi icin .env dosyasi olusturun:
cp .env.example .env
# .env icindeki DB_* degerlerini kendi MySQL bilgilerinizle doldurun
python db.py     # baglantiyi test eder (genel/SQLAlchemy yontemiyle)
python test_db.py  # legacy script'lerin kullandigi yontemle baglanti testi
```

Not: Legacy script'ler (`import_staging.py`, `test_db.py` vb.) hem `.env`
hem `Textdokument.env` dosyasini arar; ikisi de `.gitignore`'da, asla
commit edilmez.

## Kullanim

### Adim 1: PDF -> JSON (her zaman ilk adim)

```bash
python scan_invoice.py pdf_eingang/fatura.pdf
python scan_invoice.py pdf_eingang/ --output extracted/
```

### Ana arayuz: masaustu (Tkinter)

```bash
python app.py
```

Butonlar gercek is akisina gore numarali bolumlere ayrilmis (1. Fatura
Yukle -> 2. Tara ve Onizle -> 3. Sisteme Kaydet -> 4. Urun Eslestirme ->
5. Faturayi Tamamla -> Raporlar -> Klasorler). macOS/Linux/Windows'ta
calisir. Windows'ta `start_akead_importer.bat` ile de baslatilabilir.

`auto_pdf_import.py` (3. Sisteme Kaydet adimi) basariyla isledigi PDF'leri
`pdf_eingang/`'dan `pdf_importiert/`'e, hata alanlari `pdf_fehler/`'e
otomatik tasir (DB commit basarili olduktan sonra) - boylece `pdf_eingang/`
sadece henuz islenmemis PDF'leri icerir, ayni dosya tekrar tekrar islenmez.
Ayni isimde dosya zaten varsa zaman damgasi eklenir, ustune yazilmaz.

### Komut satiri (tek tek adimlar)

```bash
python import_staging.py          # pdf_eingang/ icindeki ilk PDF'i staging'e alir (JA onayi ister)
python professional_product_match.py  # staging kalemlerini produits ile eslestirir
python ai_product_match.py        # cozulemeyen satirlar icin AI onerisi (rapor, --apply ile JA onayli yazma)
python import_to_invoices.py      # SADECE guvenli alanlar icin, JA onayi ister
```

## AI analizi

[ai_product_match.py](ai_product_match.py), `professional_product_match.py`'nin
"manuel kontrol" / "vorschlag" olarak biraktigi satirlari Claude API'ye
(`claude-opus-4-8`, structured output ile) gonderip en olasi AKEAD urununu
bulmasini ister - ozellikle fatura metninde kisaltma/kesilme oldugunda
(orn. "Honig Sy" -> "Honig Sirup") bulanik metin eslestirmeden daha iyi
sonuc verir. Kurulum icin `.env`'e `ANTHROPIC_API_KEY` eklemeniz gerekir
(bkz. `.env.example`). Asla otomatik yazmaz - sadece rapor uretir, `--apply`
ile bile sadece yuksek guvenli (>=85) oneriler `JA` onayiyla yazilir.

**Birimler:** AKEAD'de sadece `KOL` (koli/karton), `KG` (kilogram), `ST`
(Stueck/tekil adet) kullanilir. `professional_product_match.py`'deki
`normalize_unit()` faturadaki onlarca kisaltmayi bu uce indirger:
- KOL -> Karton/Kart/Kar/Kartoon, Kolli/Koli/Colli/Ctn, **PK**
- ST -> Bund/BD/BL/BT/CC, Paket/PKG/Package, Stk, ML/L/LT, MT/PA/PT/RL/TB/WG

Karton/koli (ve PK) ASLA tek bir ST sayilmaz (icinde birden fazla adet
olur, `produits.packet_qty` bunu tutar). Kelimenin kendisi yetmez:
`resolve_unit()`, ham birim metni "Paket"/ST gibi gorunse bile, faturadaki
ayri bir "Inhalt" (icerik adedi) kolonu 1'den fazlaysa sonucu otomatik
olarak KOL'e yukseltir - yani "1 Paket" + Inhalt=6 -> KOL, packet_qty=6.
`ai_product_match.py`
her satirda bu kural-tabanli tahmini AI'ya da gosterip dogrulatir/gerekirse
duzelttirir, ayrica mevcut urunle eslesmeyen satirlar icin urun
turunu/kategorisini de oneri olarak verir. Tedarikci adi (`supplier_name`)
da baglam olarak gonderilir - ayni tedarikci genelde ayni kisaltma
aliskanligini kullanir.

**Dogrulama:** AI'nin cevabi `validate_matches()` ile kontrol edilir -
gonderilmeyen bir `product_id`/`family_code` uydurursa, gecersiz bir birim
dönerse, ya da bir satir icin hic cevap vermezse, bu sessizce kabul
edilmez - uyari olarak loglanir ve guvenli bir degere (yok/kural-tabanli
tahmin) dusurulur. AI'nin "sadece verilen listeden sec" talimatina uymasi
varsayilmaz, sunucu tarafinda da dogrulanir.

## MySQL

`db.py`, ortam degiskenlerinden (`.env`) okuyup SQLAlchemy + PyMySQL
uzerinden MySQL'e baglanan genel altyapiyi saglar (`python db.py` ile
test edilir). Gercek tablo semasi (`orders`, `invoices`, `produits`,
`clients`, `vendors`, `pdf_import_documents`, `pdf_import_items`)
`backup_vor_codex.sql` ve `create_pdf_import_tables.sql` icinde -
ikisi de hassas/buyuk oldugu icin `.gitignore`'da, repoya commit edilmez.

## Hassas dosyalar (asla commit etme)

`.gitignore` asagidakileri zaten haric tutuyor - degistirmeyin:

- `.env`, `Textdokument.env`, `*.env` - DB sifresi
- `backup_vor_codex.sql` - gercek (kucuk de olsa) musteri/urun verisi iceren SQL dump
- `pdf_eingang/`, `pdf_importiert/`, `pdf_fehler/` - gercek musteri faturalari
- `debug_text.txt`, `debug_bursam_text.txt`, `*.log`, `*.csv` - gercek fatura
  icerigi/raporlari

## Notlar

- Fatura formati / tedarikci ozel kurallar netlestikce `import_staging.py`
  ve `professional_product_match.py` guncellenecek.
- Repo `https://github.com/slakckky/AKEAD-Project` adresine (private) push
  edildi - hassas dosya listesi push'tan once tek tek kontrol edildi.

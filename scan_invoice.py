"""
AKEAD Invoice Matcher - PDF tarama araci.

Toptanci/market faturalarini (PDF) tarar, her sayfadaki metni ve tablolari
cikarir, gerekirse OCR'a duser (taranmis/gorsel faturalar icin) ve
sonucu JSON olarak kaydeder. Bu JSON ciktisi daha sonra AI ile analiz
edilip barkod/referans eslestirmesinde kullanilacak.

Kullanim:
    python scan_invoice.py fatura.pdf
    python scan_invoice.py faturalar_klasoru/ --output extracted/
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

DEFAULT_OUTPUT_DIR = Path("extracted")

# Barkod olabilecek rakam dizileri: EAN-8 (8), UPC-A (12), EAN-13 (13), ITF-14 (14)
BARCODE_PATTERN = re.compile(r"\b\d{8}\b|\b\d{12,14}\b")

# Bir sayfada bu kadar karakterden az metin cikarsa, sayfa muhtemelen
# taranmis gorsel demektir ve OCR'a dusulur.
MIN_TEXT_CHARS_PER_PAGE = 20


def find_barcode_candidates(text: str) -> list[str]:
    if not text:
        return []
    # tekrarlari kaldir, sirayi koru
    seen = dict.fromkeys(BARCODE_PATTERN.findall(text))
    return list(seen)


def repair_mojibake(text: str) -> str:
    """pdfplumber bazi PDF'lerde UTF-8 metni latin1 olarak okuyup bozabiliyor
    (orn. 'Ã¶' yerine 'ö'). Bu durumun belirtisi gorulurse duzeltmeyi dener."""
    if "Ã" not in text and "â" not in text:
        return text
    try:
        return text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text


def ocr_page(pdf_path: Path, page_number: int) -> str:
    """page_number 1-tabanli. Poppler (pdftoppm) ve tesseract sistemde kurulu olmali."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError(
            "OCR icin pytesseract ve pdf2image gerekli (requirements.txt). "
            f"Eksik paket: {exc.name}"
        ) from exc

    try:
        images = convert_from_path(
            str(pdf_path), first_page=page_number, last_page=page_number
        )
    except Exception as exc:
        raise RuntimeError(
            "PDF sayfasi goruntuye cevrilemedi. Poppler kurulu mu? "
            "(macOS: brew install poppler)"
        ) from exc

    if not images:
        return ""

    try:
        return pytesseract.image_to_string(images[0], lang="tur+eng")
    except Exception as exc:
        raise RuntimeError(
            "Tesseract OCR calistirilamadi. Kurulu mu? "
            "(macOS: brew install tesseract tesseract-lang)"
        ) from exc


def scan_pdf(pdf_path: Path) -> dict:
    pages_data = []
    full_text_parts = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            # x_tolerance=1: AKEAD faturalarindaki dar kolon araliklarini
            # (urun no/miktar/fiyat) birbirine yapistirmadan ayirt etmek icin.
            text = repair_mojibake(
                page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            )
            tables = page.extract_tables() or []
            method = "text"

            if len(text.strip()) < MIN_TEXT_CHARS_PER_PAGE:
                try:
                    ocr_text = ocr_page(pdf_path, i)
                    if len(ocr_text.strip()) > len(text.strip()):
                        text = ocr_text
                        method = "ocr"
                except RuntimeError as exc:
                    print(f"  [uyari] sayfa {i}: {exc}", file=sys.stderr)
                    method = "text (ocr basarisiz)"

            pages_data.append(
                {
                    "page": i,
                    "method": method,
                    "text": text,
                    "tables": tables,
                    "barcode_candidates": find_barcode_candidates(text),
                }
            )
            full_text_parts.append(text)

    full_text = "\n".join(full_text_parts)

    return {
        "file": pdf_path.name,
        "page_count": len(pages_data),
        "pages": pages_data,
        "full_text": full_text,
        "barcode_candidates": find_barcode_candidates(full_text),
    }


def save_result(result: dict, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{Path(result['file']).stem}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def scan_or_load(pdf_path: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict:
    """PDF icin daha once cikarilmis bir JSON varsa onu okur, yoksa PDF'i tarayip
    JSON'u kaydeder. Boylece her script PDF'i kendi basina tekrar tekrar acmaz;
    tek bir tarama sonucu (extracted/<isim>.json) butun adimlarca paylasilir."""
    cached_path = output_dir / f"{pdf_path.stem}.json"
    if cached_path.exists():
        return json.loads(cached_path.read_text(encoding="utf-8"))

    result = scan_pdf(pdf_path)
    save_result(result, output_dir)
    return result


def collect_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_dir():
        return sorted(input_path.glob("*.pdf"))
    if input_path.suffix.lower() == ".pdf":
        return [input_path]
    raise ValueError(f"PDF degil veya klasor degil: {input_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF fatura tarama araci")
    parser.add_argument("input", type=Path, help="PDF dosyasi veya PDF iceren klasor")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Cikti JSON dosyalarinin kaydedilecegi klasor (varsayilan: extracted/)",
    )
    args = parser.parse_args()

    pdfs = collect_pdfs(args.input)
    if not pdfs:
        print(f"PDF bulunamadi: {args.input}", file=sys.stderr)
        sys.exit(1)

    for pdf_path in pdfs:
        print(f"Taraniyor: {pdf_path}")
        result = scan_pdf(pdf_path)
        out_path = save_result(result, args.output)

        print(
            f"  -> {out_path} ({result['page_count']} sayfa, "
            f"{len(result['barcode_candidates'])} olasi barkod)"
        )


if __name__ == "__main__":
    main()

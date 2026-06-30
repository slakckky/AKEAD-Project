"""
AKEAD Invoice Matcher - masaustu (Tkinter) arayuz.

Onceki "akead_codex_test" projesinden tasindi - bu projenin ana
arayuzu. (Daha once denenen Streamlit web arayuzu iptal edildi.)

Kullanim:
    python app.py
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


BASE_DIR = Path(__file__).resolve().parent
PDF_INPUT_DIR = BASE_DIR / "pdf_eingang"
PDF_IMPORTED_DIR = BASE_DIR / "pdf_importiert"
PDF_ERROR_DIR = BASE_DIR / "pdf_fehler"
EXTRACTED_DIR = BASE_DIR / "extracted"

REPORT_FILES = [
    BASE_DIR / "product_match_report.md",
    BASE_DIR / "product_match_report.csv",
    BASE_DIR / "ai_match_report.md",
    BASE_DIR / "ai_match_report.csv",
    BASE_DIR / "product_creation_mapping.md",
    BASE_DIR / "invoice_mapping.md",
    BASE_DIR / "preisanfrage_mapping.md",
    BASE_DIR / "import_plan.md",
]
ERROR_REPORT = BASE_DIR / "import_errors.csv"
AI_REPORT_MD = BASE_DIR / "ai_match_report.md"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AkeadImporterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AKEAD Fatura Aktarici")
        self.geometry("1200x880")
        self.minsize(950, 650)
        self.running = False

        self._ensure_dirs()
        self._build_ui()
        self._warn_if_multiple_pdfs()

    def _ensure_dirs(self) -> None:
        PDF_INPUT_DIR.mkdir(exist_ok=True)
        PDF_IMPORTED_DIR.mkdir(exist_ok=True)
        PDF_ERROR_DIR.mkdir(exist_ok=True)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        # Butonlar gercek is akisina gore numarali bolumlere ayrildi - hangi
        # adimda oldugunuz, sonraki adimin ne oldugu acik olsun diye.
        sections = [
            ("1. Fatura Yukle", [
                ("PDF Sec ve Yukle", self.choose_pdf),
            ]),
            ("2. Tara ve Onizle", [
                ("Faturayi Tara (PDF -> JSON)", lambda: self.run_script("scan_invoice.py", args=[str(PDF_INPUT_DIR)])),
                ("Cikarilanlari Onizle (Kontrol Et)", lambda: self.run_script("auto_pdf_import.py", args=["--preview"])),
            ]),
            ("3. Sisteme Kaydet (Taslak)", [
                ("Faturayi Sisteme Kaydet", lambda: self.run_script("auto_pdf_import.py")),
            ]),
            ("4. Urun Eslestirme", [
                ("AKEAD Urunleriyle Eslestir", lambda: self.run_dry_then_confirm("professional_product_match.py", "Urun eslestirme/olusturma sonuclari AKEAD'e yazilsin mi?")),
                ("AI'dan Oneri Al (Rapor)", lambda: self.run_script("ai_product_match.py")),
                ("AI Onerilerini Onayla ve Kaydet", self.run_ai_apply),
            ]),
            ("5. Faturayi Tamamla", [
                ("Faturayi AKEAD'e Aktar", lambda: self.run_dry_then_confirm("import_to_invoices.py", "Fatura gercekten AKEAD'e aktarilsin mi?")),
            ]),
            ("Raporlar", [
                ("Eslestirme Raporunu Ac", self.open_import_report),
                ("AI Raporunu Ac", lambda: self.open_file(AI_REPORT_MD)),
                ("Hata Raporunu Ac", lambda: self.open_file(ERROR_REPORT)),
            ]),
            ("Klasorler (Gelismis)", [
                ("pdf_eingang", lambda: self.open_folder(PDF_INPUT_DIR)),
                ("pdf_importiert", lambda: self.open_folder(PDF_IMPORTED_DIR)),
                ("pdf_fehler", lambda: self.open_folder(PDF_ERROR_DIR)),
                ("extracted (JSON)", lambda: self.open_folder(EXTRACTED_DIR)),
            ]),
        ]

        for title, items in sections:
            frame = ttk.LabelFrame(root, text=title, padding=6)
            frame.pack(fill=tk.X, pady=3)
            for column, (label, command) in enumerate(items):
                button = ttk.Button(frame, text=label, command=command)
                button.grid(row=0, column=column, sticky="ew", padx=4, pady=2)
            for column in range(len(items)):
                frame.columnconfigure(column, weight=1)

        status_frame = ttk.Frame(root)
        status_frame.pack(fill=tk.X, pady=(10, 6))
        self.status_var = tk.StringVar(value="Hazir")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Button(status_frame, text="Ciktiyi temizle", command=self.clear_output).pack(side=tk.RIGHT)

        self.output = scrolledtext.ScrolledText(root, wrap=tk.WORD, height=18, font=("Consolas", 10))
        self.output.pack(fill=tk.BOTH, expand=True)

    def log(self, text: str) -> None:
        self.output.insert(tk.END, text)
        self.output.see(tk.END)

    def log_line(self, text: str = "") -> None:
        self.log(text + "\n")

    def clear_output(self) -> None:
        self.output.delete("1.0", tk.END)

    def set_running(self, running: bool, status: str) -> None:
        self.running = running
        self.status_var.set(status)
        self.update_idletasks()

    def choose_pdf(self) -> None:
        if self.running:
            messagebox.showwarning("AKEAD Fatura Aktarici", "Zaten bir script calisiyor.")
            return

        path = filedialog.askopenfilename(
            title="PDF sec",
            filetypes=[("PDF Dosyalari", "*.pdf"), ("Tum Dosyalar", "*.*")],
        )
        if not path:
            return

        source = Path(path)
        if source.suffix.casefold() != ".pdf":
            messagebox.showerror("AKEAD Fatura Aktarici", "Lutfen bir PDF dosyasi secin.")
            return

        target = PDF_INPUT_DIR / source.name
        try:
            if target.exists():
                overwrite = messagebox.askyesno(
                    "Dosya zaten var",
                    f"{target.name} pdf_eingang klasorunde zaten var. Uzerine yazilsin mi?",
                )
                if not overwrite:
                    return
            shutil.copy2(source, target)
            self.log_line(f"PDF kopyalandi: {source} -> {target}")
            self._warn_if_multiple_pdfs()
        except Exception as exc:
            messagebox.showerror("Kopyalama hatasi", str(exc))
            self.log_line(f"Kopyalama hatasi: {exc}")

    def _warn_if_multiple_pdfs(self) -> None:
        pdfs = sorted(PDF_INPUT_DIR.glob("*.pdf"))
        if len(pdfs) > 1:
            names = "\n".join(path.name for path in pdfs)
            messagebox.showwarning(
                "Giriste birden fazla PDF var",
                "pdf_eingang klasorunde birden fazla PDF var. Mevcut script'ler genelde ilk dosyayi okur:\n\n"
                + names,
            )
            self.log_line("Uyari: pdf_eingang klasorunde birden fazla PDF var:")
            for path in pdfs:
                self.log_line(f"  - {path.name}")

    def run_script(self, script_name: str, input_text: str | None = None, after=None, args: list[str] | None = None) -> None:
        if self.running:
            messagebox.showwarning("AKEAD Fatura Aktarici", "Zaten bir script calisiyor.")
            return
        script_path = BASE_DIR / script_name
        if not script_path.exists():
            messagebox.showerror("Script bulunamadi", f"{script_name} bulunamadi.")
            return

        def worker() -> None:
            self.after(0, lambda: self.set_running(True, f"Calisiyor: {script_name}"))
            self.after(0, lambda: self.log_line(f"\n=== {script_name} ==="))
            try:
                result = subprocess.run(
                    [sys.executable, str(script_path), *(args or [])],
                    input=input_text,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(BASE_DIR),
                    creationflags=CREATE_NO_WINDOW,
                )
                output = result.stdout or ""
                self.after(0, lambda: self.log(output))
                self.after(0, lambda: self.log_line(f"Cikis kodu: {result.returncode}"))
                if result.returncode != 0:
                    if "ModuleNotFoundError" in output:
                        self.after(0, lambda: messagebox.showerror(
                            "Yanlis Python ortami",
                            "Gerekli bir paket bulunamadi (ModuleNotFoundError).\n\n"
                            "VS Code'da sag alt kosedeki Python surumune tiklayip, "
                            "listeden bu projenin .venv klasorundeki Python'u "
                            "(orn. '.venv/bin/python' yolunu gosteren secenek) "
                            "secin, sonra app.py'i tekrar calistirin.",
                        ))
                    else:
                        self.after(0, lambda: messagebox.showerror("Script hatasi", f"{script_name}, {result.returncode} cikis koduyla sona erdi."))
                if after:
                    self.after(0, lambda: after(result.returncode, output))
            except Exception as exc:
                self.after(0, lambda: self.log_line(f"Hata: {exc}"))
                self.after(0, lambda: messagebox.showerror("Hata", str(exc)))
            finally:
                self.after(0, lambda: self.set_running(False, "Hazir"))

        threading.Thread(target=worker, daemon=True).start()

    def run_dry_then_confirm(self, script_name: str, question: str) -> None:
        script_path = BASE_DIR / script_name
        if not script_path.exists():
            messagebox.showerror("Script bulunamadi", f"{script_name} bulunamadi.")
            return
        if self.running:
            messagebox.showwarning("AKEAD Fatura Aktarici", "Zaten bir script calisiyor.")
            return

        def after_dry_run(exit_code: int, output: str) -> None:
            if exit_code != 0:
                return
            if self._output_blocks_import(output):
                messagebox.showwarning(
                    "Import engellendi",
                    "Deneme calistirmasi bir hata ya da guvensiz alan bildiriyor. JA gonderilmeyecek.",
                )
                return
            if not self._looks_like_dry_run(output):
                messagebox.showwarning(
                    "Deneme calistirmasi guvenilir sekilde algilanamadi",
                    "Ciktida acik bir deneme/on izleme isareti bulunamadi. JA gonderilmeyecek.",
                )
                return
            if messagebox.askyesno("Onay", question):
                self.run_script(script_name, input_text="JA\n")

        self.run_script(script_name, input_text="NEIN\n", after=after_dry_run)

    def run_ai_apply(self) -> None:
        # ai_product_match.py'nin dry-run/onay akisi diger script'lerden farkli:
        # argumansiz calistirma zaten her zaman sadece rapor uretir (zararsiz),
        # gercek yazma sadece --apply ile ve scriptin kendi JA sorusuyla olur.
        # Bu yuzden burada run_dry_then_confirm yerine ayri, basit bir onay var.
        if self.running:
            messagebox.showwarning("AKEAD Fatura Aktarici", "Zaten bir script calisiyor.")
            return
        if not messagebox.askyesno(
            "Onay",
            "AI raporunu incelediginizden emin misiniz? Yuksek guvenli (>=85) "
            "AI onerileri pdf_import_items.product_id'ye yazilacak. Devam edilsin mi?",
        ):
            return
        self.run_script("ai_product_match.py", args=["--apply"], input_text="JA\n")

    def _looks_like_dry_run(self, output: str) -> bool:
        # Bu kelimeler backend script'lerinin (Almanca) ciktisindan geliyor -
        # ceviri yapilmamali, aksi halde algilama calismaz.
        normalized = output.casefold()
        markers = [
            "dry run",
            "dry-run",
            "vorschau",
            "staging-vorschau",
            "abgebrochen. es wurde nichts importiert",
            "abgebrochen. kein import",
            "abgebrochen. keine produkte",
        ]
        return any(marker in normalized for marker in markers)

    def _output_blocks_import(self, output: str) -> bool:
        # Ayni sekilde: backend script ciktisindaki Almanca hata/engel
        # ifadeleriyle eslesmesi gerekiyor, cevrilmemeli.
        normalized = output.casefold()
        blockers = [
            "import gestoppt",
            "feld unsicher",
            "keine sichere preisanfrage-tabelle",
            "mapping ist nicht sicher",
            "keine positionen",
            "fehler:",
            "traceback",
            "duplikat gefunden",
        ]
        return any(blocker in normalized for blocker in blockers)

    def _open_path(self, path: Path) -> None:
        system = platform.system()
        if system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)

    def open_file(self, path: Path) -> None:
        try:
            if not path.exists():
                messagebox.showwarning("Dosya yok", f"{path.name} henuz olusturulmadi.")
                return
            self._open_path(path)
        except Exception as exc:
            messagebox.showerror("Acma basarisiz", str(exc))

    def open_folder(self, path: Path) -> None:
        try:
            path.mkdir(exist_ok=True)
            self._open_path(path)
        except Exception as exc:
            messagebox.showerror("Klasor acma basarisiz", str(exc))

    def open_import_report(self) -> None:
        for path in REPORT_FILES:
            if path.exists():
                self.open_file(path)
                return
        messagebox.showwarning("Rapor yok", "Henuz bir import raporu bulunamadi.")


def _check_environment() -> bool:
    """app.py'nin kendisi pdfplumber kullanmiyor, ama alt script'leri
    sys.executable ile (yani app.py'i acan Python ile) calistiriyor. app.py
    yanlis bir Python ile acilirsa (orn. .venv aktif degilken VS Code'un
    "Run" tusuyla), her buton ayri ayri "ModuleNotFoundError" ile patlar -
    bunun yerine en basta, tek ve net bir mesajla yakalamak daha iyi."""
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Yanlis Python ortami",
            "Gerekli paketler (orn. pdfplumber) bu Python ortaminda kurulu degil.\n\n"
            "VS Code'da sag alt kosedeki Python surumune tiklayip, listeden bu "
            "projenin .venv klasorundeki Python'u (orn. '.venv/bin/python' "
            "yolunu gosteren secenek) secin, sonra app.py'i tekrar calistirin.",
        )
        root.destroy()
        return False
    return True


def main() -> None:
    if not _check_environment():
        sys.exit(1)
    app = AkeadImporterApp()
    app.mainloop()


if __name__ == "__main__":
    main()

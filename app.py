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
    BASE_DIR / "product_creation_mapping.md",
    BASE_DIR / "invoice_mapping.md",
    BASE_DIR / "preisanfrage_mapping.md",
    BASE_DIR / "import_plan.md",
]
ERROR_REPORT = BASE_DIR / "import_errors.csv"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AkeadImporterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AKEAD Fatura Aktarici")
        self.geometry("1120x760")
        self.minsize(900, 600)
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

        button_frame = ttk.Frame(root)
        button_frame.pack(fill=tk.X)

        buttons = [
            ("PDF sec ve pdf_eingang'a kopyala", self.choose_pdf),
            ("PDF -> JSON (onizle / AI'a hazirla)", lambda: self.run_script("scan_invoice.py", args=[str(PDF_INPUT_DIR)])),
            ("PDF analiz et (on izleme)", lambda: self.run_script("auto_pdf_import.py", args=["--preview"])),
            ("Staging'e aktar", lambda: self.run_script("auto_pdf_import.py")),
            ("Eksik urunleri kontrol et/olustur", lambda: self.run_script("auto_product_match.py")),
            ("Faturayi AKEAD'e aktar", lambda: self.run_dry_then_confirm("import_to_invoices.py", "Fatura gercekten AKEAD'e aktarilsin mi?")),
            ("Import raporunu ac", self.open_import_report),
            ("Hata raporunu ac", lambda: self.open_file(ERROR_REPORT)),
            ("pdf_eingang klasorunu ac", lambda: self.open_folder(PDF_INPUT_DIR)),
            ("pdf_importiert klasorunu ac", lambda: self.open_folder(PDF_IMPORTED_DIR)),
            ("pdf_fehler klasorunu ac", lambda: self.open_folder(PDF_ERROR_DIR)),
            ("extracted klasorunu ac (JSON ciktilari)", lambda: self.open_folder(EXTRACTED_DIR)),
        ]

        for index, (label, command) in enumerate(buttons):
            button = ttk.Button(button_frame, text=label, command=command)
            button.grid(row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4)

        for column in range(3):
            button_frame.columnconfigure(column, weight=1)

        status_frame = ttk.Frame(root)
        status_frame.pack(fill=tk.X, pady=(10, 6))
        self.status_var = tk.StringVar(value="Hazir")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Button(status_frame, text="Ciktiyi temizle", command=self.clear_output).pack(side=tk.RIGHT)

        self.output = scrolledtext.ScrolledText(root, wrap=tk.WORD, height=28, font=("Consolas", 10))
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


def main() -> None:
    app = AkeadImporterApp()
    app.mainloop()


if __name__ == "__main__":
    main()

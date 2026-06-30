"""
AKEAD Invoice Matcher - masaustu (Tkinter) arayuz.

Onceki "akead_codex_test" projesinden tasindi - bu projenin ana
arayuzu. (Daha once denenen Streamlit web arayuzu iptal edildi.)

Kullanim:
    python app.py
"""

from __future__ import annotations

import os
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
        self.title("AKEAD PDF Importer")
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
            ("PDF auswählen und nach pdf_eingang kopieren", self.choose_pdf),
            ("PDF analysieren", lambda: self.run_script("auto_pdf_import.py", args=["--preview"])),
            ("In Staging importieren", lambda: self.run_script("auto_pdf_import.py")),
            ("Fehlende Artikel prüfen/erstellen", lambda: self.run_script("auto_product_match.py")),
            ("Rechnung in AKEAD importieren", lambda: self.run_dry_then_confirm("import_to_invoices.py", "Rechnung wirklich in AKEAD importieren?")),
            ("Auto-Import starten", lambda: self.run_script("auto_import_all.py")),
            ("Import-Report öffnen", self.open_import_report),
            ("Fehlerreport öffnen", lambda: self.open_file(ERROR_REPORT)),
            ("Ordner pdf_eingang öffnen", lambda: self.open_folder(PDF_INPUT_DIR)),
            ("Ordner pdf_importiert öffnen", lambda: self.open_folder(PDF_IMPORTED_DIR)),
            ("Ordner pdf_fehler öffnen", lambda: self.open_folder(PDF_ERROR_DIR)),
        ]

        for index, (label, command) in enumerate(buttons):
            button = ttk.Button(button_frame, text=label, command=command)
            button.grid(row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4)

        for column in range(3):
            button_frame.columnconfigure(column, weight=1)

        status_frame = ttk.Frame(root)
        status_frame.pack(fill=tk.X, pady=(10, 6))
        self.status_var = tk.StringVar(value="Bereit")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Button(status_frame, text="Ausgabe leeren", command=self.clear_output).pack(side=tk.RIGHT)

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
            messagebox.showwarning("AKEAD PDF Importer", "Es läuft bereits ein Skript.")
            return

        path = filedialog.askopenfilename(
            title="PDF auswählen",
            filetypes=[("PDF-Dateien", "*.pdf"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return

        source = Path(path)
        if source.suffix.casefold() != ".pdf":
            messagebox.showerror("AKEAD PDF Importer", "Bitte eine PDF-Datei auswählen.")
            return

        target = PDF_INPUT_DIR / source.name
        try:
            if target.exists():
                overwrite = messagebox.askyesno(
                    "Datei existiert",
                    f"{target.name} existiert bereits in pdf_eingang. Überschreiben?",
                )
                if not overwrite:
                    return
            shutil.copy2(source, target)
            self.log_line(f"PDF kopiert: {source} -> {target}")
            self._warn_if_multiple_pdfs()
        except Exception as exc:
            messagebox.showerror("Fehler beim Kopieren", str(exc))
            self.log_line(f"Fehler beim Kopieren: {exc}")

    def _warn_if_multiple_pdfs(self) -> None:
        pdfs = sorted(PDF_INPUT_DIR.glob("*.pdf"))
        if len(pdfs) > 1:
            names = "\n".join(path.name for path in pdfs)
            messagebox.showwarning(
                "Mehrere PDFs im Eingang",
                "Im Ordner pdf_eingang liegen mehrere PDFs. Die vorhandenen Skripte lesen normalerweise die erste Datei:\n\n"
                + names,
            )
            self.log_line("Warnung: Mehrere PDFs in pdf_eingang:")
            for path in pdfs:
                self.log_line(f"  - {path.name}")

    def run_script(self, script_name: str, input_text: str | None = None, after=None, args: list[str] | None = None) -> None:
        if self.running:
            messagebox.showwarning("AKEAD PDF Importer", "Es läuft bereits ein Skript.")
            return
        script_path = BASE_DIR / script_name
        if not script_path.exists():
            messagebox.showerror("Skript fehlt", f"{script_name} wurde nicht gefunden.")
            return

        def worker() -> None:
            self.after(0, lambda: self.set_running(True, f"Läuft: {script_name}"))
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
                self.after(0, lambda: self.log_line(f"Exit-Code: {result.returncode}"))
                if result.returncode != 0:
                    self.after(0, lambda: messagebox.showerror("Skriptfehler", f"{script_name} endete mit Exit-Code {result.returncode}."))
                if after:
                    self.after(0, lambda: after(result.returncode, output))
            except Exception as exc:
                self.after(0, lambda: self.log_line(f"Fehler: {exc}"))
                self.after(0, lambda: messagebox.showerror("Fehler", str(exc)))
            finally:
                self.after(0, lambda: self.set_running(False, "Bereit"))

        threading.Thread(target=worker, daemon=True).start()

    def run_dry_then_confirm(self, script_name: str, question: str) -> None:
        script_path = BASE_DIR / script_name
        if not script_path.exists():
            messagebox.showerror("Skript fehlt", f"{script_name} wurde nicht gefunden.")
            return
        if self.running:
            messagebox.showwarning("AKEAD PDF Importer", "Es läuft bereits ein Skript.")
            return

        def after_dry_run(exit_code: int, output: str) -> None:
            if exit_code != 0:
                return
            if self._output_blocks_import(output):
                messagebox.showwarning(
                    "Import blockiert",
                    "Der DRY-RUN meldet einen Fehler oder ein unsicheres Mapping. Es wird kein JA gesendet.",
                )
                return
            if not self._looks_like_dry_run(output):
                messagebox.showwarning(
                    "DRY-RUN nicht sicher erkannt",
                    "Die Ausgabe enthält keinen eindeutig erkannten DRY-RUN/Vorschau-Hinweis. Es wird kein JA gesendet.",
                )
                return
            if messagebox.askyesno("Bestätigung", question):
                self.run_script(script_name, input_text="JA\n")

        self.run_script(script_name, input_text="NEIN\n", after=after_dry_run)

    def _looks_like_dry_run(self, output: str) -> bool:
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

    def open_file(self, path: Path) -> None:
        try:
            if not path.exists():
                messagebox.showwarning("Datei fehlt", f"{path.name} existiert noch nicht.")
                return
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("Öffnen fehlgeschlagen", str(exc))

    def open_folder(self, path: Path) -> None:
        try:
            path.mkdir(exist_ok=True)
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("Ordner öffnen fehlgeschlagen", str(exc))

    def open_import_report(self) -> None:
        for path in REPORT_FILES:
            if path.exists():
                self.open_file(path)
                return
        messagebox.showwarning("Report fehlt", "Es wurde noch kein Import-Report gefunden.")


def main() -> None:
    app = AkeadImporterApp()
    app.mainloop()


if __name__ == "__main__":
    main()

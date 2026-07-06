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

_IS_WINDOWS = platform.system() == "Windows"
_VENV_PYTHON_HINT = r".venv\Scripts\python" if _IS_WINDOWS else ".venv/bin/python"


class AkeadImporterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AKEAD Invoice Importer")
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
            ("1. Load Invoice", [
                ("Select & Load PDF", self.choose_pdf),
            ]),
            ("2. Preview", [
                ("Preview Extracted Items (Check)", lambda: self.run_script("auto_pdf_import.py", args=["--preview"])),
            ]),
            ("3. Save to Staging", [
                ("Save Invoice to Staging DB", lambda: self.run_script("auto_pdf_import.py")),
            ]),
            ("4. Product Matching", [
                ("Match Products (Rules + AI)", self.run_full_matching),
            ]),
            ("5. Finalize Invoice", [
                ("Import Invoice to AKEAD", lambda: self.run_dry_then_confirm("import_to_invoices.py", "Really import invoice to AKEAD?")),
            ]),
            ("Reports", [
                ("Open Match Report", self.open_import_report),
                ("Open AI Report", lambda: self.open_file(AI_REPORT_MD)),
                ("Open Error Report", lambda: self.open_file(ERROR_REPORT)),
            ]),
            ("Folders (Advanced)", [
                ("pdf_eingang", lambda: self.open_folder(PDF_INPUT_DIR)),
                ("pdf_importiert", lambda: self.open_folder(PDF_IMPORTED_DIR)),
                ("pdf_fehler", lambda: self.open_folder(PDF_ERROR_DIR)),
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
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Button(status_frame, text="Clear output", command=self.clear_output).pack(side=tk.RIGHT)

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
            messagebox.showwarning("AKEAD Invoice Importer", "A script is already running.")
            return

        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return

        source = Path(path)
        if source.suffix.casefold() != ".pdf":
            messagebox.showerror("AKEAD Invoice Importer", "Please select a PDF file.")
            return

        target = PDF_INPUT_DIR / source.name
        try:
            if target.exists():
                overwrite = messagebox.askyesno(
                    "File already exists",
                    f"{target.name} already exists in pdf_eingang. Overwrite?",
                )
                if not overwrite:
                    return
            shutil.copy2(source, target)
            self.log_line(f"PDF copied: {source} -> {target}")
            self._warn_if_multiple_pdfs()
        except Exception as exc:
            messagebox.showerror("Copy error", str(exc))
            self.log_line(f"Copy error: {exc}")

    def _warn_if_multiple_pdfs(self) -> None:
        pdfs = sorted(PDF_INPUT_DIR.glob("*.pdf"))
        if len(pdfs) > 1:
            names = "\n".join(path.name for path in pdfs)
            messagebox.showwarning(
                "Multiple PDFs in input folder",
                "pdf_eingang contains more than one PDF. Scripts will use the first file:\n\n"
                + names,
            )
            self.log_line("Warning: multiple PDFs found in pdf_eingang:")
            for path in pdfs:
                self.log_line(f"  - {path.name}")

    def run_script(self, script_name: str, input_text: str | None = None, after=None, args: list[str] | None = None) -> None:
        if self.running:
            messagebox.showwarning("AKEAD Invoice Importer", "A script is already running.")
            return
        script_path = BASE_DIR / script_name
        if not script_path.exists():
            messagebox.showerror("Script not found", f"{script_name} not found.")
            return

        def worker() -> None:
            self.after(0, lambda: self.set_running(True, f"Running: {script_name}"))
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
                self.after(0, lambda: self.log_line(f"Exit code: {result.returncode}"))
                if result.returncode != 0:
                    if "ModuleNotFoundError" in output:
                        hint = _VENV_PYTHON_HINT
                        self.after(0, lambda hint=hint: messagebox.showerror(
                            "Wrong Python environment",
                            "A required package was not found (ModuleNotFoundError).\n\n"
                            "In VS Code click the Python version in the bottom-right corner "
                            "and select the .venv interpreter for this project "
                            f"(the option showing '{hint}'), then restart app.py.",
                        ))
                    else:
                        self.after(0, lambda: messagebox.showerror("Script error", f"{script_name} exited with code {result.returncode}."))
                if after:
                    self.after(0, lambda: after(result.returncode, output))
            except Exception as exc:
                self.after(0, lambda: self.log_line(f"Error: {exc}"))
                self.after(0, lambda: messagebox.showerror("Error", str(exc)))
            finally:
                self.after(0, lambda: self.set_running(False, "Ready"))

        threading.Thread(target=worker, daemon=True).start()

    def run_dry_then_confirm(self, script_name: str, question: str) -> None:
        script_path = BASE_DIR / script_name
        if not script_path.exists():
            messagebox.showerror("Script not found", f"{script_name} not found.")
            return
        if self.running:
            messagebox.showwarning("AKEAD Invoice Importer", "A script is already running.")
            return

        def after_dry_run(exit_code: int, output: str) -> None:
            if exit_code != 0:
                return
            if self._output_blocks_import(output):
                messagebox.showwarning(
                    "Import blocked",
                    "Dry run reported an error or unsafe field. JA will not be sent.",
                )
                return
            if not self._looks_like_dry_run(output):
                messagebox.showwarning(
                    "Dry run not detected",
                    "No clear dry-run marker found in output. JA will not be sent.",
                )
                return
            if messagebox.askyesno("Confirm", question):
                self.run_script(script_name, input_text="JA\n")

        self.run_script(script_name, input_text="NEIN\n", after=after_dry_run)

    def run_full_matching(self) -> None:
        """Rule-based matching → AI report → AI apply, all in sequence."""
        if self.running:
            messagebox.showwarning("AKEAD Invoice Importer", "A script is already running.")
            return

        def after_ai_report(exit_code: int, output: str) -> None:
            if exit_code != 0:
                return
            if not messagebox.askyesno(
                "Apply AI Suggestions?",
                "AI matching report generated.\n\n"
                "High-confidence (>=85) suggestions will be written to pdf_import_items.product_id.\n\n"
                "Apply?",
            ):
                return
            self.run_script("ai_product_match.py", args=["--apply"], input_text="JA\n")

        def after_rules_applied(exit_code: int, output: str) -> None:
            if exit_code != 0:
                return
            self.log_line("\n--- Rule-based done. Running AI matching... ---")
            self.run_script("ai_product_match.py", after=after_ai_report)

        def after_dry_run(exit_code: int, output: str) -> None:
            if exit_code != 0:
                return
            if self._output_blocks_import(output):
                messagebox.showwarning("Import blocked", "Dry run reported an error or unsafe field. Cancelled.")
                return
            if not self._looks_like_dry_run(output):
                messagebox.showwarning("Dry run not detected", "No clear dry-run marker found. Cancelled.")
                return
            if messagebox.askyesno("Confirm Rule-based Matching", "Write rule-based matching results to AKEAD?"):
                self.run_script("professional_product_match.py", input_text="JA\n", after=after_rules_applied)

        self.run_script("professional_product_match.py", input_text="NEIN\n", after=after_dry_run)

    def run_ai_apply(self) -> None:
        # ai_product_match.py dry-run/confirm flow differs from other scripts:
        # running without args always produces only a report (safe); actual writes
        # happen only with --apply and the script's own JA prompt.
        if self.running:
            messagebox.showwarning("AKEAD Invoice Importer", "A script is already running.")
            return
        if not messagebox.askyesno(
            "Confirm",
            "Have you reviewed the AI report? High-confidence (>=85) "
            "AI suggestions will be written to pdf_import_items.product_id. Continue?",
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
                messagebox.showwarning("File not found", f"{path.name} has not been created yet.")
                return
            self._open_path(path)
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

    def open_folder(self, path: Path) -> None:
        try:
            path.mkdir(exist_ok=True)
            self._open_path(path)
        except Exception as exc:
            messagebox.showerror("Folder open failed", str(exc))

    def open_import_report(self) -> None:
        for path in REPORT_FILES:
            if path.exists():
                self.open_file(path)
                return
        messagebox.showwarning("No report", "No import report has been generated yet.")


def _relaunch_with_venv_if_needed() -> None:
    """app.py'nin kendisi pdfplumber kullanmiyor, ama alt script'leri
    sys.executable ile (yani app.py'i acan Python ile) calistiriyor.
    Kullanicidan VS Code'da dogru Python'u sececek elle adim beklemek
    yerine, yanlis bir Python ile acildigi anlasilirsa app.py kendini
    projenin .venv Python'uyla otomatik olarak yeniden baslatir - boylece
    nasil acilirsa acilsin (Run tusu, terminal, cift tik) hep dogru
    ortamda calisir."""
    try:
        import pdfplumber  # noqa: F401
        return
    except ImportError:
        pass

    if _IS_WINDOWS:
        venv_python = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_dir = BASE_DIR / ".venv" / "bin"
        venv_python = venv_dir / "python3"
        if not venv_python.exists():
            venv_python = venv_dir / "python"

    if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
        launch_args = [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]]
        if _IS_WINDOWS:
            subprocess.Popen(launch_args)
            sys.exit(0)
        else:
            os.execv(launch_args[0], launch_args)
    # .venv bulunamadi (orn. henuz kurulmadi) - _check_environment() asagida
    # kullaniciya acik bir hata mesaji gosterecek.


def _check_environment() -> bool:
    """Catch missing .venv / pdfplumber up front with a clear message so
    individual buttons don't each explode with ModuleNotFoundError."""
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        root = tk.Tk()
        root.withdraw()
        if _IS_WINDOWS:
            setup_cmds = (
                "python -m venv .venv\n"
                ".venv\\Scripts\\activate\n"
                "pip install --prefer-binary -r requirements.txt"
            )
        else:
            setup_cmds = (
                "python3 -m venv .venv\n"
                "source .venv/bin/activate\n"
                "pip install --prefer-binary -r requirements.txt"
            )
        messagebox.showerror(
            "Setup incomplete",
            "Required packages (e.g. pdfplumber) not found and .venv is missing "
            "or incomplete.\n\nRun these commands in the project folder:\n\n"
            + setup_cmds,
        )
        root.destroy()
        return False
    return True


def main() -> None:
    _relaunch_with_venv_if_needed()
    if not _check_environment():
        sys.exit(1)
    app = AkeadImporterApp()
    app.mainloop()


if __name__ == "__main__":
    main()

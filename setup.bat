@echo off
cd /d "%~dp0"

echo AKEAD Invoice Matcher - Kurulum
echo ================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo HATA: Python bulunamadi. python.org adresinden kurun.
    pause
    exit /b 1
)

if exist .venv (
    echo .venv zaten mevcut, atlaniyor.
) else (
    echo .venv olusturuluyor...
    python -m venv .venv
    if errorlevel 1 (
        echo HATA: venv olusturulamadi.
        pause
        exit /b 1
    )
)

echo Paketler yukleniyor...
.venv\Scripts\pip install --prefer-binary -r requirements.txt
if errorlevel 1 (
    echo HATA: pip install basarisiz.
    pause
    exit /b 1
)

echo.
echo Kurulum tamamlandi. start_akead_importer.bat ile baslatabilirsiniz.
pause

"""
AKEAD Invoice Matcher - MySQL baglanti modulu.

Ortam degiskenlerinden (.env dosyasi) baglanti bilgilerini okuyup
SQLAlchemy engine olusturur. Tablo semasi henuz netlesmedi; bu modul
sadece baglanti altyapisini saglar - gercek tablo/sorgu fonksiyonlari
sema netlestiginde eklenecek.

Kurulum: .env.example dosyasini .env olarak kopyalayip kendi MySQL
bilgilerinizi girin.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, text

load_dotenv()

REQUIRED_ENV_VARS = [
    "DB_HOST",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
]


def _build_url() -> str:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Eksik ortam degiskenleri: "
            + ", ".join(missing)
            + ". .env.example dosyasini .env olarak kopyalayip doldurun."
        )

    host = os.environ["DB_HOST"]
    port = os.environ.get("DB_PORT", "3306")
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    name = os.environ["DB_NAME"]
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(_build_url(), pool_pre_ping=True)


def test_connection() -> bool:
    """Baglantiyi dener. Basarili olursa True doner, aksi halde exception firlatir."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return True


if __name__ == "__main__":
    test_connection()
    print("MySQL baglantisi basarili.")

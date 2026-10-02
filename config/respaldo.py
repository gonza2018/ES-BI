"""Respaldo consistente de DATA_DIR: bases SQLite + archivos subidos."""
import sqlite3
import tarfile
from contextlib import closing
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings

CONSERVAR = 5


def crear_respaldo():
    """Crea DATA_DIR/respaldos/respaldo_AAAAMMDD_HHMMSS.tar.gz y devuelve su ruta.

    Las bases se copian con la API de backup de SQLite (segura con el sitio en uso).
    Se conservan los CONSERVAR respaldos más recientes en el disco.
    """
    data_dir = Path(settings.DATA_DIR)
    destino = data_dir / "respaldos"
    destino.mkdir(exist_ok=True)
    archivo = destino / f"respaldo_{datetime.now():%Y%m%d_%H%M%S}.tar.gz"

    with tempfile.TemporaryDirectory() as tmp, tarfile.open(archivo, "w:gz") as tar:
        for db in sorted(data_dir.glob("*.sqlite3")):
            copia = Path(tmp) / db.name
            # closing(): `with sqlite3.connect()` solo confirma la transacción, NO cierra
            # la conexión. En Windows un archivo abierto no se puede borrar.
            with closing(sqlite3.connect(db)) as origen, closing(sqlite3.connect(copia)) as dest:
                origen.backup(dest)
            tar.add(copia, arcname=f"bases/{db.name}")
        if Path(settings.FIRMA_ARCHIVO).is_file():
            tar.add(settings.FIRMA_ARCHIVO, arcname="firma.png")
        for carpeta in ("media_publica", "paquetes_privados"):
            ruta = data_dir / carpeta
            if ruta.exists():
                tar.add(ruta, arcname=carpeta)

    for viejo in sorted(destino.glob("respaldo_*.tar.gz"))[:-CONSERVAR]:
        viejo.unlink()
    return archivo

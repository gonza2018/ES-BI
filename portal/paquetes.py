"""Carga y servido seguro de paquetes (contrato v2).

Un paquete es un zip con esta forma (la carpeta raíz es opcional):

    <slug>/
      index.html        punto de entrada
      meta.json         {"slug","titulo","tipo","organismo","descripcion","version","fecha","estado"}
      miniatura.png     opcional, 1200x630
      assets/           opcional: js, css, fuentes, imágenes (rutas RELATIVAS)
      descargas/        opcional: xlsx, pdf, csv
"""
import json
import os
import re
import shutil
import stat
import unicodedata
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.template.defaultfilters import filesizeformat
from django.http import Http404
from django.utils import timezone

# Extensiones que se SIRVEN: (Content-Type, ¿como descarga?). Cualquier otra -> 404.
TIPOS_SERVIDOS = {
    ".html": ("text/html; charset=utf-8", False),
    ".js": ("application/javascript; charset=utf-8", False),
    ".css": ("text/css; charset=utf-8", False),
    ".json": ("application/json", False),
    ".woff2": ("font/woff2", False),
    ".png": ("image/png", False),
    ".jpg": ("image/jpeg", False),
    ".jpeg": ("image/jpeg", False),
    ".svg": ("image/svg+xml", False),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", True),
    ".pdf": ("application/pdf", True),
    ".csv": ("text/csv; charset=utf-8", True),
}

# Extensiones que hacen RECHAZAR el zip: código que un servidor podría ejecutar.
EXTENSIONES_PROHIBIDAS = {
    ".py", ".pyc", ".pyo", ".pyw", ".wsgi", ".asgi",
    ".php", ".php3", ".php4", ".php5", ".php7", ".phtml", ".phar", ".phps",
    ".cgi", ".fcgi", ".pl", ".pm", ".rb", ".sh", ".bash", ".zsh",
    ".exe", ".dll", ".so", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".msi",
    ".jsp", ".jspx", ".asp", ".aspx", ".ashx", ".jar", ".war", ".class",
    ".shtml", ".htaccess", ".htpasswd",
}

# Basura habitual de zips hechos en Mac/Windows: se ignora en silencio.
IGNORADOS_NOMBRE = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORADOS_PREFIJO = ("__MACOSX/",)

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TIPOS = {"dashboard", "sitio"}


class PaqueteInvalido(Exception):
    """El zip no cumple el contrato. El mensaje se muestra tal cual en el admin."""


# ---------------------------------------------------------------------------
# Validación de meta.json
# ---------------------------------------------------------------------------

def _sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _estado(valor):
    clave = re.sub(r"[\s_-]+", "_", _sin_acentos(str(valor or "")).strip().lower())
    estados = {"borrador": "borrador", "en_revision": "en_revision", "revision": "en_revision", "aprobado": "aprobado"}
    if not clave:
        return "borrador"
    if clave not in estados:
        raise PaqueteInvalido(f'meta.json: estado "{valor}" no válido (borrador, en revisión o aprobado).')
    return estados[clave]


def _fecha(valor):
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valor).strip(), formato).date()
        except ValueError:
            pass
    raise PaqueteInvalido(f'meta.json: fecha "{valor}" no válida (usar AAAA-MM-DD).')


def validar_meta(meta):
    if not isinstance(meta, dict):
        raise PaqueteInvalido("meta.json tiene que ser un objeto JSON {...}.")
    slug = str(meta.get("slug", "")).strip()
    if not SLUG_RE.match(slug) or len(slug) > 80:
        raise PaqueteInvalido(
            f'meta.json: slug "{slug}" no válido. Solo minúsculas, números y guiones (ej. pbg-sde).'
        )
    titulo = str(meta.get("titulo", "")).strip()
    if not titulo:
        raise PaqueteInvalido("meta.json: falta el título (titulo).")
    tipo = str(meta.get("tipo") or "dashboard").strip().lower()
    if tipo not in TIPOS:
        raise PaqueteInvalido(f'meta.json: tipo "{tipo}" no válido (dashboard o sitio).')
    return {
        "slug": slug,
        "titulo": titulo[:200],
        "tipo": tipo,
        "organismo": str(meta.get("organismo") or "").strip()[:200],
        "descripcion": str(meta.get("descripcion") or "").strip(),
        "version": str(meta.get("version") or "").strip()[:40],
        "fecha": _fecha(meta.get("fecha")),
        "estado": _estado(meta.get("estado")),
    }


# ---------------------------------------------------------------------------
# Validación y extracción del zip
# ---------------------------------------------------------------------------

def _ruta_segura_en_zip(nombre):
    """Rechaza rutas absolutas, con '..' o con barras invertidas (zip slip)."""
    if "\\" in nombre or "\x00" in nombre:
        raise PaqueteInvalido(f'Ruta no válida en el zip: "{nombre}".')
    if nombre.startswith("/") or re.match(r"^[A-Za-z]:", nombre):
        raise PaqueteInvalido(f'El zip contiene una ruta absoluta: "{nombre}".')
    partes = PurePosixPath(nombre).parts
    if ".." in partes:
        raise PaqueteInvalido(f'El zip contiene una ruta que sale de la carpeta ("..") : "{nombre}".')
    return partes


def _es_enlace_simbolico(info):
    return stat.S_ISLNK(info.external_attr >> 16)


def _ignorado(nombre):
    return nombre.startswith(IGNORADOS_PREFIJO) or PurePosixPath(nombre).name in IGNORADOS_NOMBRE


def extraer_y_validar(archivo):
    """Valida el zip y lo extrae a una carpeta temporal dentro de PAQUETES_ROOT.

    Devuelve (carpeta_temporal, meta_limpio, meta_original, cantidad_archivos, bytes_totales).
    Si algo falla, no deja nada en disco y levanta PaqueteInvalido.
    """
    maximo = settings.PAQUETE_MAX_BYTES
    tamano_subido = getattr(archivo, "size", None)
    if tamano_subido and tamano_subido > maximo:
        raise PaqueteInvalido(f"El zip pesa más de {filesizeformat(maximo)}.")

    try:
        zf = zipfile.ZipFile(archivo)
    except (zipfile.BadZipFile, OSError):
        raise PaqueteInvalido("El archivo no es un zip válido.")

    with zf:
        entradas = [i for i in zf.infolist() if not _ignorado(i.filename)]
        if len(entradas) > settings.PAQUETE_MAX_ARCHIVOS:
            raise PaqueteInvalido(f"El zip tiene demasiados archivos (máximo {settings.PAQUETE_MAX_ARCHIVOS}).")

        archivos = []
        for info in entradas:
            if _es_enlace_simbolico(info):
                raise PaqueteInvalido(f'El zip contiene un enlace simbólico: "{info.filename}".')
            partes = _ruta_segura_en_zip(info.filename)
            if not info.is_dir():
                archivos.append((info, partes))

        if not archivos:
            raise PaqueteInvalido("El zip está vacío.")
        if sum(i.file_size for i, _ in archivos) > maximo:
            raise PaqueteInvalido(f"El paquete pesa más de {filesizeformat(maximo)} descomprimido.")

        # Carpeta raíz opcional: si todo está dentro de una sola carpeta, se quita.
        primeras = {p[0] for _, p in archivos}
        quitar = 1 if len(primeras) == 1 and all(len(p) > 1 for _, p in archivos) else 0
        relativos = [(i, PurePosixPath(*p[quitar:])) for i, p in archivos]

        for _, rel in relativos:
            sufijos = {s.lower() for s in rel.suffixes} | {rel.name.lower()}
            prohibidos = sufijos & EXTENSIONES_PROHIBIDAS
            if prohibidos:
                raise PaqueteInvalido(
                    f'El zip contiene un archivo no permitido ("{rel}"): {", ".join(sorted(prohibidos))}.'
                )

        nombres = {str(rel) for _, rel in relativos}
        for requerido in ("index.html", "meta.json"):
            if requerido not in nombres:
                raise PaqueteInvalido(f"Falta {requerido} en la raíz del paquete.")

        info_meta = next(i for i, rel in relativos if str(rel) == "meta.json")
        try:
            meta_original = json.loads(zf.read(info_meta).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PaqueteInvalido(f"meta.json no es un JSON válido: {error}")
        meta = validar_meta(meta_original)

        raiz = Path(settings.PAQUETES_ROOT)
        tmp = raiz / "_tmp" / uuid.uuid4().hex
        tmp.mkdir(parents=True)
        tmp_resuelto = tmp.resolve()
        total = 0
        try:
            for info, rel in relativos:
                destino = tmp / rel
                if not destino.resolve().is_relative_to(tmp_resuelto):  # doble control de zip slip
                    raise PaqueteInvalido(f'Ruta no válida en el zip: "{info.filename}".')
                destino.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as origen, open(destino, "wb") as salida:
                    # Se cuentan los bytes reales: el tamaño declarado en el zip puede mentir.
                    while bloque := origen.read(1024 * 1024):
                        total += len(bloque)
                        if total > maximo:
                            raise PaqueteInvalido(f"El paquete pesa más de {filesizeformat(maximo)} descomprimido.")
                        salida.write(bloque)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    return tmp, meta, meta_original, len(relativos), total


# ---------------------------------------------------------------------------
# Instalación (crear o actualizar, con historial)
# ---------------------------------------------------------------------------

def instalar(archivo, usuario=None):
    """Valida e instala un zip. Devuelve (paquete, creado). meta.json manda.

    Si ya existe un paquete con ese slug, se agrega una versión nueva y la anterior
    queda en el historial (sus archivos no se borran).
    """
    from .models import Paquete, VersionPaquete

    tmp, meta, meta_original, cantidad, total = extraer_y_validar(archivo)
    # Fecha para ordenar a simple vista + sufijo aleatorio para que el nombre sea único
    # aunque dos subidas caigan en el mismo instante (en Windows el reloj salta de a ~15 ms).
    carpeta = f"{meta['slug']}/{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    destino = Path(settings.PAQUETES_ROOT) / carpeta
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, destino)
        with transaction.atomic():
            paquete, creado = Paquete.objects.get_or_create(slug=meta["slug"], defaults={"titulo": meta["titulo"]})
            for campo in ("titulo", "tipo", "organismo", "descripcion", "version", "fecha", "estado"):
                setattr(paquete, campo, meta[campo])
            version = VersionPaquete.objects.create(
                paquete=paquete,
                version=meta["version"],
                fecha=meta["fecha"],
                estado=meta["estado"],
                meta=meta_original,
                carpeta=carpeta,
                archivo_nombre=getattr(archivo, "name", "")[:255],
                tamano_bytes=total,
                cantidad_archivos=cantidad,
                subido_por=usuario if getattr(usuario, "pk", None) else None,
            )
            paquete.version_actual = version
            paquete.save()
            if creado and meta["organismo"]:
                # Preasignación: grupo con el mismo nombre que el organismo (sin distinguir mayúsculas).
                paquete.grupos.add(*Group.objects.filter(name__iexact=meta["organismo"]))
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(destino, ignore_errors=True)
        raise
    return paquete, creado


def activar_version(version):
    """Vuelve a publicar una versión anterior (y su metadata)."""
    meta = validar_meta(version.meta) if version.meta else {}
    paquete = version.paquete
    for campo in ("titulo", "tipo", "organismo", "descripcion", "version", "fecha", "estado"):
        if campo in meta:
            setattr(paquete, campo, meta[campo])
    paquete.version_actual = version
    paquete.save()


# ---------------------------------------------------------------------------
# Servido seguro
# ---------------------------------------------------------------------------

def resolver_ruta(base, ruta):
    """Devuelve el Path del archivo pedido si es seguro servirlo; si no, Http404.

    Rechaza: '..', rutas absolutas, barras invertidas, enlaces simbólicos (en cualquier
    tramo), lo que quede fuera de la carpeta del paquete y extensiones no permitidas.
    Una ruta que termina en '/' sirve el index.html de esa carpeta (paquetes tipo sitio).
    """
    ruta = ruta or "index.html"
    if ruta.endswith("/"):
        ruta += "index.html"
    if "\\" in ruta or "\x00" in ruta:
        raise Http404
    relativa = PurePosixPath(ruta)
    if relativa.is_absolute() or ".." in relativa.parts:
        raise Http404
    if relativa.suffix.lower() not in TIPOS_SERVIDOS:
        raise Http404

    base = Path(base)
    actual = base
    for parte in relativa.parts:
        actual = actual / parte
        if actual.is_symlink():
            raise Http404

    base_resuelta = base.resolve()
    destino = (base / relativa).resolve()
    if not destino.is_relative_to(base_resuelta) or not destino.is_file():
        raise Http404
    return destino

"""Datos de libre acceso: paquetes marcados como públicos, visibles sin iniciar sesión.

Diferencias con el portal privado (/portal/): sin login ni grupos, sin descargas
(.xlsx, .pdf, .csv y descargas/ dan 404) y con la CSP de paquetes más un `sandbox`.
"""
from pathlib import PurePosixPath

from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_safe

from config.middleware import CSP_DATOS_PUBLICOS
from portal.models import Paquete
from portal.paquetes import TIPOS_SERVIDOS, resolver_ruta

# Lo único que se sirve sin login. Nada de planillas, PDF ni CSV.
EXTENSIONES_PUBLICAS = {".html", ".js", ".css", ".json", ".woff2", ".png", ".jpg", ".jpeg", ".svg"}
CARPETA_DESCARGAS = "descargas"


def _publico_o_404(slug):
    """El paquete si es público y está publicado; si no, 404 (no revela que existe)."""
    paquete = Paquete.publicos().filter(slug=slug).first()
    if paquete is None:
        raise Http404
    return paquete


@require_safe
def lista(request):
    paquetes = list(Paquete.publicos())
    if not paquetes:  # sin paquetes públicos, la pestaña tampoco existe
        raise Http404
    return render(request, "datos/lista.html", {"paquetes": paquetes})


@require_safe
def visor(request, slug):
    paquete = _publico_o_404(slug)
    return render(request, "datos/visor.html", {"paquete": paquete})


@require_safe
def ver_sin_barra(request, slug):
    """/datos/ver/<slug> -> /datos/ver/<slug>/ (sin la barra, las rutas relativas no cargan)."""
    _publico_o_404(slug)
    return redirect(reverse("datos:ver_indice", args=[slug]), permanent=False)


def _es_descarga(partes):
    return bool(partes) and partes[0].lower() == CARPETA_DESCARGAS


@require_safe
def ver_archivo(request, slug, ruta=""):
    """Sirve un archivo del paquete público. Cada pedido verifica público, publicado y ruta."""
    paquete = _publico_o_404(slug)

    pedida = ruta or "index.html"
    if pedida.endswith("/"):
        pedida += "index.html"
    relativa = PurePosixPath(pedida)
    if relativa.suffix.lower() not in EXTENSIONES_PUBLICAS or _es_descarga(relativa.parts):
        raise Http404

    base = paquete.directorio
    # Misma validación que el portal: sin "..", rutas absolutas, enlaces simbólicos ni salidas de la carpeta.
    archivo = resolver_ruta(base, ruta)
    if _es_descarga(archivo.relative_to(base.resolve()).parts):  # por si el disco no distingue mayúsculas
        raise Http404

    sufijo = archivo.suffix.lower()
    tipo, _ = TIPOS_SERVIDOS[sufijo]
    respuesta = FileResponse(open(archivo, "rb"), content_type=tipo, as_attachment=False)
    respuesta["Content-Security-Policy"] = CSP_DATOS_PUBLICOS
    respuesta["Cache-Control"] = "public, max-age=300"
    if sufijo == ".woff2":
        # Con `sandbox` el documento tiene origen opaco: sin esto el navegador rechaza la fuente.
        respuesta["Access-Control-Allow-Origin"] = "*"
    return respuesta

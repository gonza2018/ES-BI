"""Vistas de operación: descarga de respaldos y diagnóstico de IP."""
import hmac
import io
from pathlib import Path

from django.conf import settings
from django.contrib import admin, messages
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from sitio.views import modo_contacto

from .ip_cliente import obtener_ip
from .respaldo import crear_respaldo


def _token_valido(request):
    token = settings.RESPALDO_TOKEN
    enviado = request.headers.get("Authorization", "")
    return bool(token) and len(token) >= 32 and hmac.compare_digest(enviado, f"Bearer {token}")


@never_cache
@require_GET
def descargar_respaldo(request):
    """Genera un respaldo y lo descarga. Acceso: superusuario con sesión, o script con
    `Authorization: Bearer <RESPALDO_TOKEN>`. Así el respaldo sale del disco de Render."""
    es_superusuario = request.user.is_authenticated and request.user.is_superuser
    if not (es_superusuario or _token_valido(request)):
        return HttpResponseForbidden("No autorizado.")
    archivo = crear_respaldo()
    return FileResponse(open(archivo, "rb"), as_attachment=True, filename=archivo.name)


@never_cache
@require_GET
def diagnostico_ip(request):
    """Muestra los encabezados de IP que llegan, para confirmar la configuración en Render."""
    if not (request.user.is_authenticated and request.user.is_superuser):
        return HttpResponseForbidden("No autorizado.")
    claves = ["REMOTE_ADDR", "HTTP_X_FORWARDED_FOR", "HTTP_CF_CONNECTING_IP", "HTTP_TRUE_CLIENT_IP", "HTTP_X_REAL_IP"]
    lineas = [f"{c}: {request.META.get(c, '(no viene)')}" for c in claves]
    lineas += [
        "",
        f"Configuración: IP_CLIENTE_ENCABEZADO={settings.IP_CLIENTE_ENCABEZADO} IP_CLIENTE_PROXIES={settings.IP_CLIENTE_PROXIES}",
        f"IP que usa el bloqueo por intentos fallidos: {obtener_ip(request)}",
        "",
        "Tiene que coincidir con tu IP pública (buscá 'cuál es mi IP' en el navegador).",
        "",
        f"Formulario de contacto: envía por {modo_contacto()}",
        f"WhatsApp: {settings.WHATSAPP_NUMERO or '(sin número: botones ocultos)'}",
    ]
    return HttpResponse("\n".join(lineas) + "\n", content_type="text/plain; charset=utf-8")


MAX_FIRMA_BYTES = 1024 * 1024


def _solo_superusuario(request):
    return request.user.is_authenticated and request.user.is_superuser


@never_cache
@require_http_methods(["GET", "POST"])
def firma(request):
    """Subir, ver o quitar la firma manuscrita de la carta (solo superusuario)."""
    if not _solo_superusuario(request):
        return HttpResponseForbidden("No autorizado.")
    from PIL import Image, UnidentifiedImageError

    destino = Path(settings.FIRMA_ARCHIVO)
    if request.method == "POST":
        if request.POST.get("accion") == "quitar":
            destino.unlink(missing_ok=True)
            messages.success(request, "Firma quitada: las cartas van solo con el texto de la firma.")
            return redirect("firma")
        archivo = request.FILES.get("archivo")
        if not archivo:
            messages.error(request, "Elegí un archivo PNG.")
        elif archivo.size > MAX_FIRMA_BYTES:
            messages.error(request, "La imagen pesa más de 1 MB.")
        else:
            try:
                with Image.open(archivo) as img:
                    if img.format != "PNG":
                        raise ValueError("no es PNG")
                    img.load()
                    if max(img.size) > 4000:
                        raise ValueError("demasiado grande")
                    # Se vuelve a guardar: descarta metadatos y cualquier contenido extra.
                    salida = io.BytesIO()
                    img.convert("RGBA").save(salida, format="PNG", optimize=True)
            except (UnidentifiedImageError, ValueError, OSError):
                messages.error(request, "El archivo tiene que ser una imagen PNG válida (idealmente con fondo transparente).")
            else:
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(salida.getvalue())
                messages.success(request, "Firma guardada. Va a aparecer en las próximas cartas.")
                return redirect("firma")
    contexto = {
        **admin.site.each_context(request),
        "title": "Firma de la carta",
        "hay_firma": destino.is_file(),
    }
    return render(request, "admin/firma.html", contexto)


@never_cache
@require_GET
def firma_imagen(request):
    if not _solo_superusuario(request):
        return HttpResponseForbidden("No autorizado.")
    destino = Path(settings.FIRMA_ARCHIVO)
    if not destino.is_file():
        raise Http404
    return FileResponse(open(destino, "rb"), content_type="image/png")

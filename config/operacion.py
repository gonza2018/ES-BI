"""Vistas de operación: descarga de respaldos y diagnóstico de IP."""
import hmac

from django.conf import settings
from django.http import FileResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

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
    ]
    return HttpResponse("\n".join(lineas) + "\n", content_type="text/plain; charset=utf-8")

"""IP real del visitante detrás del proxy de Render.

La usa django-axes (AXES_CLIENT_IP_CALLABLE) para bloquear por usuario + IP.
Si la IP sale mal, el bloqueo falla de una de dos formas:
  - IP del proxy para todos -> 5 intentos fallidos bloquean a ese usuario para todo el mundo;
  - IP que manda el cliente -> el atacante la inventa en cada intento y nunca se bloquea.

Por eso no se usa la IP de más a la IZQUIERDA de X-Forwarded-For (la puede escribir
cualquiera), sino la que agregó nuestro proxy de confianza, contando desde la DERECHA.

Configuración (variables de entorno, ver README):
  IP_CLIENTE_ENCABEZADO   Encabezado a leer. Por defecto HTTP_X_FORWARDED_FOR.
                          Para uno de un solo valor (p. ej. HTTP_CF_CONNECTING_IP) se toma tal cual.
  IP_CLIENTE_PROXIES      Cuántas IPs contar desde la derecha en X-Forwarded-For (defecto 1:
                          un solo proxy de confianza que agrega la IP del cliente al final).
Para confirmar los valores en Render: /gestion/diagnostico-ip/ (solo superusuario).
"""
import ipaddress

from django.conf import settings


def _valida(ip):
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except (ValueError, AttributeError):
        return None


def obtener_ip(request):
    encabezado = settings.IP_CLIENTE_ENCABEZADO
    valor = request.META.get(encabezado, "")
    if valor:
        if encabezado == "HTTP_X_FORWARDED_FOR":
            partes = [p.strip() for p in valor.split(",") if p.strip()]
            n = settings.IP_CLIENTE_PROXIES
            if 1 <= n <= len(partes):
                ip = _valida(partes[-n])
                if ip:
                    return ip
        else:
            ip = _valida(valor)
            if ip:
                return ip
    return _valida(request.META.get("REMOTE_ADDR", "")) or "0.0.0.0"

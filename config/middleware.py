from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound, HttpResponsePermanentRedirect, HttpResponseRedirect


class HostCanonicoMiddleware:
    """Redirige gserelic.com -> www.gserelic.com (301), conservando ruta y query."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        canonico = settings.HOST_CANONICO
        host = request.get_host().split(":")[0].lower()
        if canonico and host in settings.REDIRIGIR_A_CANONICO:
            return HttpResponsePermanentRedirect(f"https://{canonico}{request.get_full_path()}")
        return self.get_response(request)


# CSP estricta para el sitio público y el portal.
# Las páginas de paquetes del portal (Paso 2) definirán su propia CSP.
CSP_ESTRICTA = "; ".join(
    [
        "default-src 'self'",
        "img-src 'self' data:",
        "style-src 'self'",
        "script-src 'self'",
        "font-src 'self'",
        "frame-src 'self'",
        "frame-ancestors 'self'",
        "form-action 'self'",
        "base-uri 'self'",
        "object-src 'none'",
    ]
)


# CSP de los archivos de paquetes (/portal/ver/...). Probada con pbg-sde v1.1: todo local
# (Plotly y fuentes en assets/), JS y estilos inline, sin 'unsafe-eval' ni CDNs.
# El sitio público y el portal conservan la CSP estricta de arriba.
CSP_PAQUETES = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'self'",
        "object-src 'none'",
        "base-uri 'self'",
    ]
)


# CSP de los archivos de paquetes de LIBRE ACCESO (/datos/ver/...). Igual que la de paquetes,
# más `sandbox` sin allow-same-origin: lo ve cualquiera, incluso Gonzalo con la sesión del admin
# abierta, y así el dashboard no puede usar esa sesión (su origen es opaco). Por eso las fuentes
# necesitan `Access-Control-Allow-Origin: *` y el dashboard no puede usar localStorage ni fetch.
CSP_DATOS_PUBLICOS = CSP_PAQUETES + "; sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox"


class CabecerasSeguridadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # El admin de Django usa estilos inline: no se le aplica la CSP estricta.
        if not request.path.startswith("/gestion/"):
            response.headers.setdefault("Content-Security-Policy", CSP_ESTRICTA)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


class HostTableroMiddleware:
    """Host de los tableros institucionales (settings.HOST_TABLERO, p. ej. tablero.gserelic.com).

    En ese host solo existe /portal/: la raíz va a /portal/, robots.txt bloquea todo y cualquier
    otra ruta (sitio, CV, /datos/, admin) da 404. Además, en ese host y para quien solo ve
    tableros institucionales, las páginas del portal no se guardan en caché (Cache-Control: no-store),
    así «atrás» después de salir no vuelve a mostrar el tablero.
    Va después de AuthenticationMiddleware (necesita request.user).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from portal.marca import es_neutro, host_tablero

        en_host = host_tablero(request)
        if en_host:
            if request.path == "/robots.txt":
                return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
            if request.path == "/":
                return HttpResponseRedirect("/portal/")
            if not request.path.startswith("/portal/"):
                return HttpResponseNotFound("No encontrado", content_type="text/plain")
        response = self.get_response(request)
        if en_host:
            response["X-Robots-Tag"] = "noindex, nofollow"
        if request.path.startswith("/portal/") and es_neutro(request):
            response["Cache-Control"] = "no-store"
        return response
